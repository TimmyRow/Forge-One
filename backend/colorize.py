"""Local colour-first finishing for a completed Forge One geometry GLB."""
from __future__ import annotations

from pathlib import Path
import re

import numpy as np
import trimesh
from PIL import Image
from scipy import ndimage


def _subject_mask(image: Image.Image, pixels: np.ndarray) -> np.ndarray:
    """Find the photographed subject without treating its backdrop as colour.

    The generation providers normally save a clean, white prepared image, but
    text-to-image sources can include a studio wall and floor.  A colour pass
    must never use those as part of the object's palette or projection bounds.
    """
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    alpha = rgba[..., 3]
    if 100 < np.count_nonzero(alpha > 8) < alpha.size * 0.98:
        return alpha > 8

    height, width = pixels.shape[:2]
    # The prepared image has a near-white backdrop.  This keeps pale subjects
    # (such as light wood) while still excluding the backdrop from its bounds.
    brightness = pixels.mean(axis=2)
    white_background = (
        np.mean(brightness > 247) > 0.30
        and np.mean(pixels.std(axis=2) < 7) > 0.20
    )
    if white_background:
        mask = brightness < 248
        if np.count_nonzero(mask) > 100:
            return mask

    # For a photographic studio background, use GrabCut's conservative
    # foreground estimate.  It is only a mask for sampling/bounds; no mesh
    # components are removed based on it.
    try:
        import cv2

        gc_mask = np.zeros((height, width), dtype=np.uint8)
        margin_x = max(2, round(width * 0.055))
        margin_y = max(2, round(height * 0.045))
        rectangle = (margin_x, margin_y, width - margin_x * 2, height - margin_y * 2)
        background_model = np.zeros((1, 65), dtype=np.float64)
        foreground_model = np.zeros((1, 65), dtype=np.float64)
        cv2.grabCut(pixels, gc_mask, rectangle, background_model, foreground_model, 5, cv2.GC_INIT_WITH_RECT)
        mask = (gc_mask == cv2.GC_FGD) | (gc_mask == cv2.GC_PR_FGD)
        area = np.count_nonzero(mask) / mask.size
        if 0.015 < area < 0.80:
            return mask
    except Exception:
        # The safe fallback below still permits colour transfer.  GrabCut is
        # an enhancement, not a dependency that can block a finished model.
        pass

    mask = np.max(255 - pixels, axis=2) > 18
    return mask if np.count_nonzero(mask) > 100 else np.ones((height, width), dtype=bool)


def _palette_colours(values: list[str] | None) -> np.ndarray | None:
    """Parse the optional shadow/base/highlight colour guide safely."""
    if not values:
        return None
    if not 1 <= len(values) <= 3:
        raise ValueError("Choose one to three palette colours.")
    parsed: list[list[int]] = []
    for value in values:
        if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("Palette colours must be valid six-digit hex colours.")
        parsed.append([int(value[index:index + 2], 16) for index in (1, 3, 5)])
    return np.asarray(parsed, dtype=np.float32)


def _apply_palette(source_colours: np.ndarray, subject_pixels: np.ndarray, palette: np.ndarray | None) -> np.ndarray:
    """Use the photo's light/dark layout to place an explicit colour palette.

    This deliberately does not infer new geometry: darkest, middle, and lightest
    material regions in the source drive the shadow, base, and highlight guides.
    The continuous interpolation keeps grain and fabric variation alive.
    """
    if palette is None:
        return source_colours
    subject_luma = subject_pixels.astype(np.float32).mean(axis=1)
    low, high = np.percentile(subject_luma, (7, 93))
    lightness = np.clip((source_colours.mean(axis=1) - low) / max(high - low, 1.0), 0.0, 1.0)
    if len(palette) == 1:
        target = np.broadcast_to(palette[0], source_colours.shape).copy()
        # Retain subtle source detail rather than making a single flat paint.
        return np.clip(target * (0.76 + 0.24 * lightness[:, None]), 0, 255)
    if len(palette) == 2:
        return palette[0] * (1.0 - lightness[:, None]) + palette[1] * lightness[:, None]
    lower = np.clip(lightness * 2.0, 0.0, 1.0)[:, None]
    upper = np.clip((lightness - 0.5) * 2.0, 0.0, 1.0)[:, None]
    low_to_base = palette[0] * (1.0 - lower) + palette[1] * lower
    base_to_high = palette[1] * (1.0 - upper) + palette[2] * upper
    return np.where((lightness < 0.5)[:, None], low_to_base, base_to_high)


def _apply_paint_guides(
    source_colours: np.ndarray,
    sample_x: np.ndarray,
    sample_y: np.ndarray,
    image_width: int,
    image_height: int,
    guides: list[dict[str, object]] | None,
) -> np.ndarray:
    """Apply explicit user-painted colour guides in the source-photo space."""
    if not guides:
        return source_colours
    result = source_colours.copy()
    for guide in guides:
        try:
            x = float(guide["x"])
            y = float(guide["y"])
            radius = float(guide.get("radius", 0.04))
            value = str(guide["color"])
            if not 0 <= x <= 1 or not 0 <= y <= 1 or not 0.003 <= radius <= 0.35:
                raise ValueError
            colour = _palette_colours([value])
            if colour is None:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise ValueError("A paint-map guide is invalid.")
        distance = np.hypot(sample_x / max(image_width - 1, 1) - x, sample_y / max(image_height - 1, 1) - y)
        # A soft edge avoids a hard, sticker-like boundary on the 3D model.
        weight = np.clip(1.0 - distance / radius, 0.0, 1.0)[:, None]
        result = result * (1.0 - weight) + colour[0] * weight
    return result


def _sample_extra_view(
    vertices: np.ndarray,
    normals: np.ndarray,
    image: Image.Image,
    axis_u: int,
    axis_v: int,
    normal_axis: int,
    normal_direction: float,
    style: str,
    palette: list[str] | None,
) -> tuple[np.ndarray, np.ndarray]:
    """Project one optional side/back photograph onto its facing vertices."""
    pixels = np.asarray(image.convert("RGB"), dtype=np.uint8)
    foreground = _subject_mask(image, pixels)
    ys, xs = np.where(foreground)
    xmin, xmax, ymin, ymax = xs.min(), xs.max(), ys.min(), ys.max()
    values_u, values_v = vertices[:, axis_u], vertices[:, axis_v]
    normalized_u = (values_u - values_u.min()) / max(np.ptp(values_u), 1e-6)
    normalized_v = (values_v - values_v.min()) / max(np.ptp(values_v), 1e-6)
    sample_x = np.clip(np.rint(xmin + normalized_u * (xmax - xmin)).astype(np.int32), 0, pixels.shape[1] - 1)
    sample_y = np.clip(np.rint(ymax - normalized_v * (ymax - ymin)).astype(np.int32), 0, pixels.shape[0] - 1)
    _distance, indices = ndimage.distance_transform_edt(~foreground, return_indices=True)
    filled = pixels.copy()
    filled[~foreground] = pixels[indices[0][~foreground], indices[1][~foreground]]
    if style == "colour":
        sigma = max(1.25, min(pixels.shape[0], pixels.shape[1]) / 180.0)
        projected = ndimage.gaussian_filter(filled.astype(np.float32), sigma=(sigma, sigma, 0))
    else:
        projected = filled.astype(np.float32)
    colours = projected[sample_y, sample_x]
    colours = _apply_palette(colours, pixels[foreground], _palette_colours(palette))
    weight = np.clip((normals[:, normal_axis] * normal_direction - 0.03) / 0.72, 0.0, 1.0)[:, None]
    return colours, weight


def apply_source_colours(
    mesh: trimesh.Trimesh,
    image: Image.Image,
    brightness: float = 1.0,
    saturation: float = 1.0,
    coverage: float = 1.0,
    style: str = "colour",
    palette: list[str] | None = None,
    paint_guides: list[dict[str, object]] | None = None,
    extra_views: dict[str, Image.Image] | None = None,
) -> trimesh.Trimesh:
    """Add vertex colours while leaving mesh positions and topology untouched.

    ``colour`` is deliberately a *material colour transfer*, not another
    reconstruction attempt. It keeps medium-scale material texture (wood
    grain, fabric weave, painted panels) while avoiding a second attempt to
    force every sharp photograph feature onto the geometry.
    ``detail`` retains the older, exact-photo projection for the rare case
    where a generated mesh already lines up exceptionally well with its image.
    """
    if style not in {"colour", "detail"}:
        raise ValueError("Colour style must be colour or detail.")
    pixels = np.asarray(image.convert("RGB"), dtype=np.uint8)
    vertices = mesh.vertices
    foreground = _subject_mask(image, pixels)
    palette_colours = _palette_colours(palette)
    ys, xs = np.where(foreground)
    xmin, xmax, ymin, ymax = xs.min(), xs.max(), ys.min(), ys.max()
    # Forge One GLBs use the normal glTF convention: X is horizontal, Y is
    # up, and Z is depth.  Keep that convention rather than guessing axes from
    # shape proportions.  The old guess is what made image details drift onto
    # unrelated body parts when reconstruction proportions differed.
    axis_u, axis_v, depth_axis = 0, 1, 2
    mesh_u, mesh_v = vertices[:, axis_u], vertices[:, axis_v]
    normalized_u = (mesh_u - mesh_u.min()) / max(np.ptp(mesh_u), 1e-6)
    normalized_v = (mesh_v - mesh_v.min()) / max(np.ptp(mesh_v), 1e-6)
    sample_x = np.clip(np.rint(xmin + normalized_u * (xmax - xmin)).astype(np.int32), 0, pixels.shape[1] - 1)
    sample_y = np.clip(np.rint(ymax - normalized_v * (ymax - ymin)).astype(np.int32), 0, pixels.shape[0] - 1)
    distance, indices = ndimage.distance_transform_edt(~foreground, return_indices=True)
    filled = pixels.copy()
    filled[~foreground] = pixels[indices[0][~foreground], indices[1][~foreground]]
    if style == "colour":
        # A light blur makes the pass tolerant of small geometry/photo
        # alignment differences, while retaining real material character.
        # The previous 20+ pixel blur flattened wooden chairs into beige.
        sigma = max(1.25, min(pixels.shape[0], pixels.shape[1]) / 180.0)
        colour_image = ndimage.gaussian_filter(filled.astype(np.float32), sigma=(sigma, sigma, 0))
    else:
        colour_image = filled.astype(np.float32)
    source_colours = colour_image[sample_y, sample_x]
    source_colours = _apply_palette(source_colours, pixels[foreground], palette_colours)
    source_colours = _apply_paint_guides(
        source_colours, sample_x, sample_y, pixels.shape[1], pixels.shape[0], paint_guides,
    )
    normals = mesh.vertex_normals
    if style == "detail":
        # Exact projection is opt-in. Only the frontmost point gets photo
        # details, so the far side cannot paint through the near side.
        depth = vertices[:, depth_axis]
        cell_size = 6
        cells_wide = (pixels.shape[1] + cell_size - 1) // cell_size
        cell_index = (sample_y // cell_size) * cells_wide + (sample_x // cell_size)
        nearest_depth = np.full(((pixels.shape[0] + cell_size - 1) // cell_size) * cells_wide, -np.inf, dtype=np.float64)
        np.maximum.at(nearest_depth, cell_index, depth)
        visible_from_photo = depth >= nearest_depth[cell_index] - max(float(np.ptp(depth)) * 0.004, 1e-5)
        photo_weight = np.clip((normals[:, depth_axis] - 0.04) / 0.62, 0.0, 1.0) * visible_from_photo
    else:
        # Broad colour is allowed around the surface; this avoids a hard
        # photograph-shaped boundary and keeps the colour coherent on sides.
        photo_weight = np.clip((np.abs(normals[:, depth_axis]) - 0.08) / 0.72, 0.0, 1.0)
    photo_weight *= np.clip(1.0 - distance[sample_y, sample_x] / 28.0, 0.0, 1.0)
    photo_weight = np.clip(photo_weight * coverage, 0.0, 1.0)[:, None]
    subject_colour = np.median(pixels[foreground], axis=0).astype(np.float32)
    source_luma = source_colours.mean(axis=1, keepdims=True)
    source_colours = source_luma + (source_colours - source_luma) * saturation
    source_colours *= brightness
    subject_luma = subject_colour.mean()
    subject_colour = (subject_luma + (subject_colour - subject_luma) * saturation) * brightness
    # Hidden surfaces still receive complete colour coverage, but use a low-
    # frequency positional estimate instead of copying sharp front details.
    hidden_colours = source_colours * 0.58 + subject_colour * 0.42
    result_colours = source_colours * photo_weight + hidden_colours * (1.0 - photo_weight)
    # Optional views add real information only to their facing surfaces. The
    # main image still supplies the safe fallback everywhere else.
    for view_name, view_image in (extra_views or {}).items():
        if view_name == "side":
            view_colours, view_weight = _sample_extra_view(vertices, normals, view_image, 2, 1, 0, 1.0, style, palette)
        elif view_name == "back":
            view_colours, view_weight = _sample_extra_view(vertices, normals, view_image, 0, 1, 2, -1.0, style, palette)
        else:
            continue
        result_colours = result_colours * (1.0 - view_weight) + view_colours * view_weight
    rgba = np.empty((len(vertices), 4), dtype=np.uint8)
    rgba[:, :3] = np.clip(result_colours, 0, 255).astype(np.uint8)
    rgba[:, 3] = 255
    mesh.visual = trimesh.visual.ColorVisuals(mesh=mesh, vertex_colors=rgba)
    return mesh


def colorize_glb(
    model_path: Path,
    source_path: Path,
    output_path: Path,
    brightness: float = 1.0,
    saturation: float = 1.0,
    coverage: float = 1.0,
    style: str = "colour",
    palette: list[str] | None = None,
    paint_guides: list[dict[str, object]] | None = None,
    extra_view_paths: dict[str, Path] | None = None,
) -> tuple[int, int, int]:
    scene = trimesh.load(model_path, force="scene")
    geometries = tuple(scene.geometry.values())
    if not geometries:
        raise RuntimeError("The geometry master contains no meshes to colour.")
    opened_views: dict[str, Image.Image] = {}
    try:
        for name, path in (extra_view_paths or {}).items():
            if path.is_file():
                opened_views[name] = Image.open(path).convert("RGB")
        with Image.open(source_path) as source_image:
            for mesh in geometries:
                apply_source_colours(
                    mesh, source_image, brightness, saturation, coverage, style,
                    palette, paint_guides, opened_views,
                )
    finally:
        for view_image in opened_views.values():
            view_image.close()
    # Export the original scene rather than concatenating meshes. Node
    # transforms and separate components stay exactly as generated.
    output_path.write_bytes(scene.export(file_type="glb"))
    return (
        sum(len(mesh.vertices) for mesh in geometries),
        sum(len(mesh.faces) for mesh in geometries),
        output_path.stat().st_size,
    )
