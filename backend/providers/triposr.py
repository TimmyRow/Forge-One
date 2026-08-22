from __future__ import annotations

import gc
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRIPOSR_ROOT = PROJECT_ROOT / "third_party" / "TripoSR"
MODEL_ROOT = PROJECT_ROOT / "models"

os.environ.setdefault("HF_HOME", str(MODEL_ROOT / "huggingface"))
os.environ.setdefault("U2NET_HOME", str(MODEL_ROOT / "rembg"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(TRIPOSR_ROOT) not in sys.path:
    sys.path.insert(1, str(TRIPOSR_ROOT))

import numpy as np
import rembg
import torch
import trimesh
from PIL import Image, ImageOps

from tsr.system import TSR
from tsr.utils import remove_background, resize_foreground

LOGGER = logging.getLogger("image_to_3d.triposr")


class GenerationCancelled(RuntimeError):
    pass


@dataclass(slots=True)
class FastGenerationResult:
    glb_path: Path
    prepared_image_path: Path
    vertices: int
    triangles: int
    file_size: int
    elapsed_seconds: float
    peak_vram_bytes: int


class TripoSRProvider:
    """Lazy, single-model TripoSR provider tuned for an 8 GB NVIDIA GPU."""

    name = "Fast"
    model_id = "stabilityai/TripoSR"

    def __init__(self) -> None:
        self._model: TSR | None = None
        self._rembg_session = None
        self._device = torch.device("cuda:0")
        self._chunk_size = int(os.getenv("FAST_CHUNK_SIZE", "4096"))
        # 256³ is materially smoother than the original conservative 192³
        # preset, while the renderer's chunking keeps it within the tested 8 GB
        # GPU class.
        self._mc_resolution = int(os.getenv("FAST_MC_RESOLUTION", "256"))

    def unload(self) -> None:
        """Release Fast mode before launching the separate Quality worker."""
        self._model = None
        self._rembg_session = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    @staticmethod
    def assert_cuda() -> None:
        if not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA is unavailable to PyTorch. Re-run setup.bat and verify the NVIDIA driver."
            )
        total = torch.cuda.get_device_properties(0).total_memory
        if total < 7 * 1024**3:
            raise RuntimeError("Fast mode requires an NVIDIA GPU with at least 7 GB VRAM.")

    def _load_model(self, progress: Callable[[str, int], None]) -> TSR:
        if self._model is not None:
            return self._model
        self.assert_cuda()
        progress("Loading TripoSR (first run downloads official weights)…", 24)
        LOGGER.info("Loading %s on %s", self.model_id, torch.cuda.get_device_name(0))
        model = TSR.from_pretrained(
            self.model_id,
            config_name="config.yaml",
            weight_name="model.ckpt",
        )
        model.renderer.set_chunk_size(self._chunk_size)
        model.eval()
        model.to(self._device)
        self._model = model
        return model

    def _prepare_image(self, source: Path, destination: Path, variation: int = 0) -> Image.Image:
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGBA")

        if self._rembg_session is None:
            self._rembg_session = rembg.new_session("u2net")
        cutout = remove_background(image, self._rembg_session)
        alpha = np.asarray(cutout.getchannel("A"))
        if alpha.max() == 0 or np.count_nonzero(alpha > 8) < 64:
            raise RuntimeError(
                "Background removal could not find a clear object. Try a clean image with one centered subject."
            )
        # Give the reconstruction network more pixels of the actual object
        # rather than background/padding.  A small margin still protects the
        # silhouette from clipping.
        # Keep remake framing close to the proven default. Large crop shifts
        # changed the inferred silhouette too much and often made a candidate
        # visibly worse than the original.
        framing = (0.90, 0.91, 0.89)[variation % 3]
        cutout = resize_foreground(cutout, framing)
        cutout.save(destination, format="PNG")

        rgba = np.asarray(cutout).astype(np.float32) / 255.0
        rgb = rgba[:, :, :3] * rgba[:, :, 3:4] + (1.0 - rgba[:, :, 3:4]) * 0.5
        return Image.fromarray(np.clip(rgb * 255.0, 0, 255).astype(np.uint8), mode="RGB")

    @staticmethod
    def _normalize_and_validate_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        if mesh.vertices.shape[0] < 4 or mesh.faces.shape[0] < 4:
            raise RuntimeError("TripoSR returned an empty or invalid mesh.")
        mesh.remove_unreferenced_vertices()
        # TripoSR's reconstruction height is the X axis. glTF/Three.js use Y-up.
        # Bake the conversion so both the viewer and downloaded GLB stand upright.
        mesh.apply_transform(
            trimesh.transformations.rotation_matrix(np.pi / 2.0, [0.0, 0.0, 1.0])
        )
        bounds = mesh.bounds
        extents = bounds[1] - bounds[0]
        longest = float(extents.max())
        if not np.isfinite(longest) or longest <= 1e-8:
            raise RuntimeError("TripoSR returned a mesh with invalid dimensions.")
        mesh.apply_translation(-mesh.bounding_box.centroid)
        mesh.apply_scale(2.0 / longest)
        trimesh.repair.fix_normals(mesh, multibody=True)
        return mesh

    @staticmethod
    def _refine_surface(mesh: trimesh.Trimesh, detail: str = "Balanced") -> trimesh.Trimesh:
        """Subtly remove marching-cubes stair steps without erasing features."""
        iterations = {"Soft": 4, "Balanced": 2, "Sharp": 1}.get(detail, 2)
        trimesh.smoothing.filter_taubin(mesh, lamb=0.35, nu=0.40, iterations=iterations)
        trimesh.repair.fix_normals(mesh, multibody=True)
        return mesh

    @staticmethod
    def _remove_floating_clumps(mesh: trimesh.Trimesh, trim: str = "Balanced") -> trimesh.Trimesh:
        """Discard only tiny disconnected marching-cubes artifacts."""
        pieces = list(mesh.split(only_watertight=False))
        if len(pieces) < 2:
            return mesh
        largest_area = max(float(piece.area) for piece in pieces)
        trim_ratio = {"Gentle": 0.001, "Balanced": 0.002, "Clean": 0.004}.get(trim, 0.002)
        face_floor = max(80, int(len(mesh.faces) * trim_ratio))
        keep = [piece for piece in pieces if len(piece.faces) >= face_floor and piece.area >= largest_area * 0.01]
        result = trimesh.util.concatenate(keep or [max(pieces, key=lambda piece: piece.area)])
        result.remove_unreferenced_vertices()
        trimesh.repair.fix_normals(result, multibody=True)
        return result

    @staticmethod
    def _validate_glb(path: Path) -> tuple[int, int]:
        data = path.read_bytes()
        if len(data) < 20 or data[:4] != b"glTF":
            raise RuntimeError("The generated file is not a valid binary glTF file.")
        loaded = trimesh.load(path, force="scene")
        geometries = list(loaded.geometry.values())
        vertices = sum(len(geometry.vertices) for geometry in geometries)
        triangles = sum(len(geometry.faces) for geometry in geometries)
        if vertices < 4 or triangles < 4:
            raise RuntimeError("The exported GLB contains no usable mesh geometry.")
        return vertices, triangles

    @staticmethod
    def _check_cancel(cancelled: Callable[[], bool]) -> None:
        if cancelled():
            raise GenerationCancelled("Generation was cancelled.")

    def generate(
        self,
        source: Path,
        output_dir: Path,
        progress: Callable[[str, int], None],
        cancelled: Callable[[], bool],
        variation: int = 0,
        detail: str = "Balanced",
        trim: str = "Balanced",
        subject_mode: str = "General",
    ) -> FastGenerationResult:
        started = time.perf_counter()
        self.assert_cuda()
        output_dir.mkdir(parents=True, exist_ok=True)
        prepared_path = output_dir / "prepared-input.png"
        glb_path = output_dir / "model.glb"

        progress("Isolating and centering the object…", 12)
        prepared = self._prepare_image(source, prepared_path, variation)
        self._check_cancel(cancelled)

        model = self._load_model(progress)
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(self._device)
        self._check_cancel(cancelled)

        progress("Reconstructing the 3D scene on the NVIDIA GPU…", 42)
        try:
            with torch.inference_mode(), torch.autocast(
                device_type="cuda", dtype=torch.float16
            ):
                scene_codes = model([prepared], device=str(self._device))

            self._check_cancel(cancelled)
            progress(
                f"Extracting a {self._mc_resolution}³ surface (GPU sampling, CPU meshing)…",
                70,
            )
            with torch.inference_mode(), torch.autocast(
                device_type="cuda", dtype=torch.float16
            ):
                meshes = model.extract_mesh(
                    scene_codes,
                    has_vertex_color=True,
                    resolution=self._mc_resolution,
                    # Alternate reconstructions sample a nearby isosurface and
                    # framing rather than returning a byte-for-byte rerun.
                    threshold=(25.0, 25.0, 24.8)[variation % 3],
                )
            peak_vram = torch.cuda.max_memory_allocated(self._device)
            del scene_codes
        except torch.cuda.OutOfMemoryError as exc:
            raise RuntimeError(
                "Fast mode ran out of GPU memory. Close GPU-heavy applications and try again."
            ) from exc
        finally:
            gc.collect()
            torch.cuda.empty_cache()

        self._check_cancel(cancelled)
        progress("Validating and packaging the generated mesh as GLB…", 90)
        mesh = self._remove_floating_clumps(
            self._refine_surface(self._normalize_and_validate_mesh(meshes[0]), detail), trim
        )
        # The Create stage is geometry-only. A separate reversible Color pass
        # applies source colours later without forcing reconstruction and
        # texture projection to compete in one inference step.
        neutral = np.tile(np.array([184, 188, 194, 255], dtype=np.uint8), (len(mesh.vertices), 1))
        mesh.visual = trimesh.visual.ColorVisuals(mesh=mesh, vertex_colors=neutral)
        del meshes
        exported = trimesh.Scene(mesh).export(file_type="glb")
        glb_path.write_bytes(exported)
        vertices, triangles = self._validate_glb(glb_path)

        return FastGenerationResult(
            glb_path=glb_path,
            prepared_image_path=prepared_path,
            vertices=vertices,
            triangles=triangles,
            file_size=glb_path.stat().st_size,
            elapsed_seconds=time.perf_counter() - started,
            peak_vram_bytes=peak_vram,
        )
