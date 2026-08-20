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
from scipy.spatial import cKDTree
from image_process import prepare_image
from briarmbg import BriaRMBG
from triposg.pipelines.pipeline_triposg import TripoSGPipeline


def status(percent: int, message: str) -> None:
    print(f"STATUS:{percent}:{message}", flush=True)


def bake_source_colors(mesh: trimesh.Trimesh, image: Image.Image) -> None:
    """Cover every vertex with a source-derived color, including hidden sides."""
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
    pairs = ((0, 1), (0, 2), (1, 2))
    axis_u, axis_v = min(
        pairs,
        key=lambda pair: abs(np.log(max(extents[pair[0]], 1e-6) / max(extents[pair[1]], 1e-6)) - np.log(image_ratio)),
    )
    u = (vertices[:, axis_u] - vertices[:, axis_u].min()) / max(np.ptp(vertices[:, axis_u]), 1e-6)
    v = 1.0 - (vertices[:, axis_v] - vertices[:, axis_v].min()) / max(np.ptp(vertices[:, axis_v]), 1e-6)
    # Map mesh bounds to the image's foreground bounds (not its padded canvas).
    u = (xmin + u * (xmax - xmin)) / max(pixels.shape[1] - 1, 1)
    v = (ymin + v * (ymax - ymin)) / max(pixels.shape[0] - 1, 1)
    px = np.clip(np.rint(u * (pixels.shape[1] - 1)).astype(int), 0, pixels.shape[1] - 1)
    py = np.clip(np.rint(v * (pixels.shape[0] - 1)).astype(int), 0, pixels.shape[0] - 1)
    colors = pixels[py, px]

    # Projection misses occluded/back-facing regions.  Propagate the nearest
    # non-background projected color in 3D so *every* surface has appearance
    # rather than white/gray holes.
    colored = np.max(255 - colors, axis=1) > 18
    if colored.any():
        missing = ~colored
        if missing.any():
            nearest = cKDTree(vertices[colored]).query(vertices[missing], k=1)[1]
            colors[missing] = colors[colored][nearest]
    else:
        # A white object still needs an explicit, opaque vertex color layer.
        colors[:] = np.median(pixels[foreground], axis=0).astype(np.uint8)
    rgba = np.column_stack((colors, np.full(len(vertices), 255, dtype=np.uint8)))
    mesh.visual.vertex_colors = rgba


def remove_floating_clumps(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Remove only tiny disconnected reconstruction artifacts, not real parts."""
    pieces = list(mesh.split(only_watertight=False))
    if len(pieces) < 2:
        return mesh
    largest_area = max(float(piece.area) for piece in pieces)
    face_floor = max(80, int(len(mesh.faces) * 0.002))
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
    image = prepare_image(args.image, bg_color=np.array([1.0, 1.0, 1.0]), rmbg_net=rmbg, padding_ratio=0.06)
    status(62, "Generating Quality mesh (TripoSG)…")
    # Prefer a visibly sharper extraction.  RTX 8 GB systems may not have the
    # headroom for it, so retry the prior bounded preset rather than failing.
    try:
        status(62, "Generating sharp Quality mesh (TripoSG)…")
        output = pipe(image=image, generator=torch.Generator(device=device).manual_seed(args.seed),
                      num_inference_steps=32, num_tokens=1536, guidance_scale=7.0,
                      dense_octree_depth=7, hierarchical_octree_depth=9,
                      use_flash_decoder=False).samples[0]
    except torch.cuda.OutOfMemoryError:
        torch.cuda.empty_cache()
        status(68, "Sharp Quality preset exceeded VRAM; using the detailed 8 GB fallback…")
        output = pipe(image=image, generator=torch.Generator(device=device).manual_seed(args.seed),
                      num_inference_steps=28, num_tokens=1024, guidance_scale=7.0,
                      dense_octree_depth=7, hierarchical_octree_depth=8,
                      use_flash_decoder=False).samples[0]
    status(86, "Removing floating clumps and baking full-surface colors…")
    mesh = trimesh.Trimesh(output[0].astype(np.float32), np.ascontiguousarray(output[1]))
    mesh = remove_floating_clumps(mesh)
    bake_source_colors(mesh, image)
    status(93, "Exporting colored Quality GLB…")
    glb = output_dir / "model.glb"
    mesh.export(glb)
    image.save(output_dir / "prepared-input.png")
    peak = torch.cuda.max_memory_allocated()
    print("RESULT:" + json.dumps({"glb_path": str(glb), "prepared_image_path": str(output_dir / "prepared-input.png"),
        "vertices": len(mesh.vertices), "triangles": len(mesh.faces), "file_size": glb.stat().st_size,
        "elapsed_seconds": time.perf_counter() - start, "peak_vram_bytes": peak}), flush=True)


if __name__ == "__main__":
    main()
