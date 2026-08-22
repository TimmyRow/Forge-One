"""Memory-conscious official TripoSG worker for the Quality mode."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRIPOSG_ROOT = ROOT / "third_party" / "TripoSG"
MODEL_ROOT = ROOT / "models" / "triposg"
sys.path.insert(0, str(TRIPOSG_ROOT))
sys.path.insert(0, str(TRIPOSG_ROOT / "scripts"))
os.environ.setdefault("HF_HOME", str(ROOT / "models" / "huggingface"))

import numpy as np
import torch
import trimesh
from huggingface_hub import snapshot_download
from PIL import Image
from scipy import ndimage
from image_process import prepare_image
from briarmbg import BriaRMBG
from triposg.pipelines.pipeline_triposg import TripoSGPipeline


def status(percent: int, message: str) -> None:
    print(f"STATUS:{percent}:{message}", flush=True)


def bake_source_colors(mesh: trimesh.Trimesh, image: Image.Image) -> None:
    """Apply a full-coverage source-colour pass without UV texture stretching.

    A single flat texture is a poor fit for a reconstructed volume: its UVs
    repeat the same image rows around limbs and depth, which shows up as dark
    horizontal bands.  Use projected vertex colours instead.  Every vertex
    samples the prepared source image, whose background has been filled from
    nearby foreground pixels, so the GLB has colour on every surface but no
    texture seams or blank samples.
    """
    pixels = np.asarray(image.convert("RGB"), dtype=np.uint8)
    vertices = mesh.vertices
    # Find the actual object rectangle rather than sampling the white padding.
    foreground = np.max(255 - pixels, axis=2) > 18
    if foreground.sum() < 100:
        foreground = np.ones(pixels.shape[:2], dtype=bool)
    ys, xs = np.where(foreground)
    xmin, xmax, ymin, ymax = xs.min(), xs.max(), ys.min(), ys.max()

    # Pick the mesh plane whose proportion best matches the visible object,
    # which makes this robust to TripoSG coordinate-convention changes.
    image_ratio = (xmax - xmin + 1) / max(ymax - ymin + 1, 1)
    extents = np.ptp(vertices, axis=0)
    pairs = tuple((u, v) for u in range(3) for v in range(3) if u != v)
    axis_u, axis_v = min(
        pairs,
        key=lambda pair: abs(np.log(max(extents[pair[0]], 1e-6) / max(extents[pair[1]], 1e-6)) - np.log(image_ratio)),
    )
    # Use one uniform scale, centered on the subject.  This keeps features in
    # their photographed proportions instead of stretching them to fit a mesh
    # whose inferred silhouette is slightly different.
    mesh_u = vertices[:, axis_u]
    mesh_v = vertices[:, axis_v]
    mesh_width, mesh_height = max(np.ptp(mesh_u), 1e-6), max(np.ptp(mesh_v), 1e-6)
    scale = min((xmax - xmin + 1) / mesh_width, (ymax - ymin + 1) / mesh_height)
    px_float = (xmin + xmax) / 2 + (mesh_u - mesh_u.mean()) * scale
    py_float = (ymin + ymax) / 2 - (mesh_v - mesh_v.mean()) * scale
    # Dilate real source appearance into the background before sampling.  This
    # supplies coherent inferred-side colour instead of white/empty texels.
    if foreground.any():
        _distance, indices = ndimage.distance_transform_edt(~foreground, return_indices=True)
        texture_pixels = pixels.copy()
        texture_pixels[~foreground] = pixels[indices[0][~foreground], indices[1][~foreground]]
    else:
        texture_pixels = np.broadcast_to(np.median(pixels.reshape(-1, 3), axis=0).astype(np.uint8), pixels.shape).copy()

    sample_x = np.clip(np.rint(px_float).astype(np.int32), 0, texture_pixels.shape[1] - 1)
    sample_y = np.clip(np.rint(py_float).astype(np.int32), 0, texture_pixels.shape[0] - 1)
    source_colors = texture_pixels[sample_y, sample_x].astype(np.float32)
    # A single photo only supplies truthful colour for surfaces facing its
    # camera. Painting the same pixels around a limb causes the horizontal
    # "wrapped image" bands visible from the side. Keep detailed projected
    # colour on surfaces roughly parallel to the photo plane; blend side and
    # back-facing surfaces into the subject's dominant material colour.
    trimesh.repair.fix_normals(mesh, multibody=True)
    normals = mesh.vertex_normals
    view_alignment = np.abs(normals[:, 3 - axis_u - axis_v])
    detailed_weight = np.clip((view_alignment - 0.18) / 0.52, 0.0, 1.0)[:, None]
    subject_median = np.median(pixels[foreground], axis=0).astype(np.float32)
    colors = source_colors * detailed_weight + subject_median * (1.0 - detailed_weight)
    rgba = np.empty((len(vertices), 4), dtype=np.uint8)
    rgba[:, :3] = np.clip(colors, 0, 255).astype(np.uint8)
    rgba[:, 3] = 255
    mesh.visual = trimesh.visual.ColorVisuals(mesh=mesh, vertex_colors=rgba)


def remove_floating_clumps(mesh: trimesh.Trimesh, trim: str = "Balanced") -> trimesh.Trimesh:
    """Remove only tiny disconnected reconstruction artifacts, not real parts."""
    pieces = list(mesh.split(only_watertight=False))
    if len(pieces) < 2:
        return mesh
    largest_area = max(float(piece.area) for piece in pieces)
    trim_ratio = {"Gentle": 0.001, "Balanced": 0.002, "Clean": 0.004}.get(trim, 0.002)
    face_floor = max(80, int(len(mesh.faces) * trim_ratio))
    keep = [piece for piece in pieces if len(piece.faces) >= face_floor and piece.area >= largest_area * 0.01]
    cleaned = trimesh.util.concatenate(keep or [max(pieces, key=lambda piece: piece.area)])
    cleaned.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(cleaned, multibody=True)
    return cleaned


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--detail", choices=("Soft", "Balanced", "Sharp"), default="Balanced")
    parser.add_argument("--trim", choices=("Gentle", "Balanced", "Clean"), default="Balanced")
    parser.add_argument("--subject-mode", choices=("General", "Portrait"), default="General")
    args = parser.parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable to Quality mode.")
    start = time.perf_counter()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    weights = MODEL_ROOT / "TripoSG"
    rmbg_weights = MODEL_ROOT / "RMBG-1.4"
    status(12, "Checking official TripoSG weights (first run is a large download)…")
    snapshot_download("VAST-AI/TripoSG", local_dir=weights)
    snapshot_download("briaai/RMBG-1.4", local_dir=rmbg_weights)
    status(35, "Loading TripoSG Quality model…")
    device = "cuda"
    rmbg = BriaRMBG.from_pretrained(rmbg_weights).to(device).eval()
    pipe = TripoSGPipeline.from_pretrained(weights).to(device, torch.float16)
    status(52, "Preparing image and removing background…")
    padding = 0.025 if args.subject_mode == "Portrait" else 0.06
    image = prepare_image(args.image, bg_color=np.array([1.0, 1.0, 1.0]), rmbg_net=rmbg, padding_ratio=padding)
    status(62, "Generating Quality mesh (TripoSG)…")
    # Prefer a visibly sharper extraction.  RTX 8 GB systems may not have the
    # headroom for it, so retry the prior bounded preset rather than failing.
    try:
        status(62, "Generating sharp Quality mesh (TripoSG)…")
        # Stay close to TripoSG's official 50-step / 2048-token recipe.
        # The prior reduced preset fit comfortably into the RTX 4070's 8 GB
        # VRAM but threw away the very inference capacity needed for coherent
        # anatomy.  These presets use that available headroom; the existing
        # bounded fallback remains in place if another machine cannot fit it.
        detail_settings = {
            "Soft": (38, 1792), "Balanced": (44, 2048), "Sharp": (50, 2048),
        }
        steps, tokens = detail_settings[args.detail]
        output = pipe(image=image, generator=torch.Generator(device=device).manual_seed(args.seed),
                      num_inference_steps=steps, num_tokens=tokens, guidance_scale=7.0,
                      dense_octree_depth=8, hierarchical_octree_depth=9,
                      use_flash_decoder=False).samples[0]
    except torch.cuda.OutOfMemoryError:
        torch.cuda.empty_cache()
        status(68, "Sharp Quality preset exceeded VRAM; using the detailed 8 GB fallback…")
        output = pipe(image=image, generator=torch.Generator(device=device).manual_seed(args.seed),
                      num_inference_steps=28, num_tokens=1024, guidance_scale=7.0,
                      dense_octree_depth=7, hierarchical_octree_depth=8,
                      use_flash_decoder=False).samples[0]
    status(86, "Removing floating clumps and packaging geometry master…")
    mesh = trimesh.Trimesh(output[0].astype(np.float32), np.ascontiguousarray(output[1]))
    mesh = remove_floating_clumps(mesh, args.trim)
    neutral = np.tile(np.array([184, 188, 194, 255], dtype=np.uint8), (len(mesh.vertices), 1))
    mesh.visual = trimesh.visual.ColorVisuals(mesh=mesh, vertex_colors=neutral)
    status(93, "Exporting uncolored Quality geometry GLB…")
    glb = output_dir / "model.glb"
    mesh.export(glb)
    image.save(output_dir / "prepared-input.png")
    peak = torch.cuda.max_memory_allocated()
    print("RESULT:" + json.dumps({"glb_path": str(glb), "prepared_image_path": str(output_dir / "prepared-input.png"),
        "vertices": len(mesh.vertices), "triangles": len(mesh.faces), "file_size": glb.stat().st_size,
        "elapsed_seconds": time.perf_counter() - start, "peak_vram_bytes": peak}), flush=True)


if __name__ == "__main__":
    main()
