"""Create a conservative, game-ready GLB copy with Blender 4.2.

This script is intentionally isolated from Forge One's generation workers.  It
imports a finished GLB, performs only reversible work on the imported scene,
exports to a different path, and then imports that export again for validation.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import struct
import sys
import traceback
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector


PRESETS = {
    "high": {"label": "High Detail", "ratio": 0.90},
    "game": {"label": "Game Ready", "ratio": 0.72},
    "low": {"label": "Low Poly", "ratio": 0.45},
}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--progress", required=True)
    parser.add_argument("--preset", choices=tuple(PRESETS), default="game")
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp.replace(path)


def progress(path: Path, percent: int, message: str) -> None:
    write_json(path, {"status": "running", "progress": percent, "message": message})


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.cameras, bpy.data.lights):
        for block in list(collection):
            if block.users == 0:
                collection.remove(block)


def import_glb(path: Path) -> None:
    clear_scene()
    bpy.ops.import_scene.gltf(filepath=str(path), merge_vertices=False)


def mesh_objects() -> list[bpy.types.Object]:
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and obj.data]


def triangle_count(obj: bpy.types.Object) -> int:
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def scene_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    if not points:
        raise RuntimeError("The GLB contains no renderable mesh bounds.")
    return (
        Vector((min(point.x for point in points), min(point.y for point in points), min(point.z for point in points))),
        Vector((max(point.x for point in points), max(point.y for point in points), max(point.z for point in points))),
    )


def used_images(objects: list[bpy.types.Object]) -> set[str]:
    names: set[str] = set()
    materials = {slot.material for obj in objects for slot in obj.material_slots if slot.material}
    for material in materials:
        if not material.use_nodes or not material.node_tree:
            continue
        for node in material.node_tree.nodes:
            if node.type == "TEX_IMAGE" and getattr(node, "image", None):
                names.add(node.image.name)
    return names


def glb_attributes(path: Path) -> set[str]:
    """Read declared vertex semantics without decoding the binary mesh data."""
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        return set()
    json_length, json_type = struct.unpack_from("<II", data, 12)
    if json_type != 0x4E4F534A:
        return set()
    document = json.loads(data[20 : 20 + json_length].decode("utf-8").rstrip("\x00 "))
    return {
        semantic
        for mesh in document.get("meshes", [])
        for primitive in mesh.get("primitives", [])
        for semantic in primitive.get("attributes", {})
    }


def glb_alpha_modes(path: Path) -> list[str]:
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        return []
    json_length, json_type = struct.unpack_from("<II", data, 12)
    if json_type != 0x4E4F534A:
        return []
    document = json.loads(data[20 : 20 + json_length].decode("utf-8").rstrip("\x00 "))
    return sorted(material.get("alphaMode", "OPAQUE") for material in document.get("materials", []))


def stats(objects: list[bpy.types.Object]) -> dict:
    low, high = scene_bounds(objects)
    dimensions = high - low
    materials = {slot.material.name for obj in objects for slot in obj.material_slots if slot.material}
    return {
        "meshes": len(objects),
        "vertices": sum(len(obj.data.vertices) for obj in objects),
        "triangles": sum(triangle_count(obj) for obj in objects),
        "materials": len(materials),
        "images": len(used_images(objects)),
        "uv_meshes": sum(1 for obj in objects if len(obj.data.uv_layers) > 0),
        "invalid_normals": sum(
            1 for obj in objects for polygon in obj.data.polygons
            if polygon.normal.length_squared < 1.0e-16 or any(not math.isfinite(value) for value in polygon.normal)
        ),
        "invalid_transforms": sum(
            1 for obj in objects if any(not math.isfinite(value) for row in obj.matrix_world for value in row)
        ),
        "dimensions": [float(dimensions.x), float(dimensions.y), float(dimensions.z)],
        "bounds_min": [float(low.x), float(low.y), float(low.z)],
        "bounds_max": [float(high.x), float(high.y), float(high.z)],
    }


def repair_invalid_data(objects: list[bpy.types.Object], actions: list[str], skipped: list[str]) -> None:
    for obj in objects:
        mesh = obj.data
        changed = mesh.validate(verbose=False, clean_customdata=False)
        mesh.update(calc_edges=True)
        bad_normals = any(not math.isfinite(component) for polygon in mesh.polygons for component in polygon.normal)
        bad_normals = bad_normals or any(polygon.normal.length_squared < 1.0e-16 for polygon in mesh.polygons)
        if bad_normals:
            bm = bmesh.new()
            bm.from_mesh(mesh)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bm.to_mesh(mesh)
            bm.free()
            mesh.update()
            actions.append(f"Repaired invalid face normals in {obj.name}.")
        elif changed:
            actions.append(f"Blender repaired invalid mesh records in {obj.name}.")
    if not any("normal" in action.lower() for action in actions):
        skipped.append("Normal recalculation was not needed; the source normals were valid.")


def remove_tiny_object_artifacts(objects: list[bpy.types.Object], global_diagonal: float, actions: list[str], skipped: list[str]) -> list[bpy.types.Object]:
    """Remove only whole mesh objects that are tiny by faces *and* dimensions.

    Internal connected islands are left alone because disconnected pieces can be
    intentional (eyes, buttons, straps, leaves, etc.).  This is reported rather
    than pretending semantic certainty that the pipeline does not have.
    """
    candidates = []
    total_triangles = sum(triangle_count(obj) for obj in objects)
    face_limit = max(4, min(16, int(total_triangles * 0.00001)))
    size_limit = global_diagonal * 0.002
    for obj in objects:
        low, high = scene_bounds([obj])
        if triangle_count(obj) <= face_limit and (high - low).length <= size_limit:
            candidates.append(obj)
    if candidates and len(candidates) < len(objects):
        for obj in candidates:
            actions.append(f"Removed tiny detached artifact {obj.name} ({triangle_count(obj)} triangles).")
            bpy.data.objects.remove(obj, do_unlink=True)
        objects = mesh_objects()
    else:
        skipped.append("No disconnected component was removed without high confidence; ambiguous pieces were preserved.")
    return objects


def adaptive_ratio(base_ratio: float, triangles: int) -> float:
    if triangles < 2_500:
        return 1.0
    if triangles < 10_000:
        return 1.0 - ((1.0 - base_ratio) * 0.45)
    return base_ratio


def decimate(objects: list[bpy.types.Object], base_ratio: float, actions: list[str], skipped: list[str]) -> None:
    for obj in objects:
        before = triangle_count(obj)
        ratio = adaptive_ratio(base_ratio, before)
        if ratio >= 0.995:
            skipped.append(f"Kept small mesh {obj.name} at full detail ({before} triangles).")
            continue
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        modifier = obj.modifiers.new(name="Forge One Game Ready", type="DECIMATE")
        modifier.decimate_type = "COLLAPSE"
        modifier.ratio = ratio
        modifier.use_collapse_triangulate = True
        try:
            bpy.ops.object.modifier_apply(modifier=modifier.name)
            after = triangle_count(obj)
            if after >= before:
                skipped.append(f"Simplification did not safely reduce {obj.name}; its geometry was retained.")
            else:
                actions.append(f"Reduced {obj.name} from {before:,} to {after:,} triangles ({ratio:.0%} relative target).")
        except Exception as exc:
            if modifier.name in obj.modifiers:
                obj.modifiers.remove(modifier)
            skipped.append(f"Skipped simplification for {obj.name}: {exc}")
        finally:
            obj.select_set(False)


def add_game_origin(objects: list[bpy.types.Object], actions: list[str], skipped: list[str]) -> None:
    low, high = scene_bounds(objects)
    dimensions = high - low
    longest = max(dimensions)
    root = bpy.data.objects.new("ForgeOne_GameReady_Root", None)
    bpy.context.scene.collection.objects.link(root)
    top_level = [obj for obj in bpy.context.scene.objects if obj is not root and obj.parent is None]
    for obj in top_level:
        world = obj.matrix_world.copy()
        obj.parent = root
        obj.matrix_world = world
    # Blender is Z-up; glTF export converts this cleanly back to glTF Y-up.
    root.location = Vector((-(low.x + high.x) / 2.0, -(low.y + high.y) / 2.0, -low.z))
    actions.append("Centered the copy and set its pivot to the bottom-center of the visible bounds.")
    if longest > 10_000.0 or longest < 0.0001:
        scale = 1.0 / longest
        root.scale = (scale, scale, scale)
        actions.append(f"Normalized an unreasonable source scale by {scale:.6g} without changing proportions.")
    else:
        skipped.append("Scale was already reasonable and was preserved.")


def export_glb(path: Path, include_normals: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=False,
        export_yup=True,
        export_texcoords=True,
        export_normals=include_normals,
        export_vertex_color="MATERIAL",
        export_all_vertex_colors=True,
        export_materials="EXPORT",
        export_cameras=False,
        export_lights=False,
        export_apply=False,
        export_draco_mesh_compression_enable=True,
        export_draco_mesh_compression_level=6,
        export_draco_position_quantization=16,
        export_draco_normal_quantization=12,
        export_draco_texcoord_quantization=14,
        export_draco_color_quantization=12,
    )


def normalized_dimensions(values: list[float]) -> list[float]:
    largest = max(values)
    return [value / largest if largest else 0.0 for value in values]


def validate_round_trip(
    source_stats: dict,
    prepared_stats: dict,
    output: Path,
    source_alpha_modes: list[str],
    source_attributes: set[str],
) -> tuple[dict, list[str]]:
    import_glb(output)
    reloaded = stats(mesh_objects())
    failures: list[str] = []
    if reloaded["triangles"] <= 0 or reloaded["meshes"] <= 0:
        failures.append("The exported GLB contains no renderable triangles.")
    if reloaded["meshes"] < prepared_stats["meshes"]:
        failures.append("One or more intended meshes were lost during export.")
    if reloaded["materials"] < prepared_stats["materials"]:
        failures.append("Materials were lost during export.")
    if reloaded["images"] < prepared_stats["images"]:
        failures.append("Embedded texture images were lost during export.")
    if reloaded["uv_meshes"] < prepared_stats["uv_meshes"]:
        failures.append("UV coordinates were lost during export.")
    if reloaded["invalid_normals"]:
        failures.append("The exported mesh contains invalid or zero-length face normals.")
    if reloaded["invalid_transforms"]:
        failures.append("The exported mesh contains a non-finite transform.")
    output_alpha_modes = glb_alpha_modes(output)
    output_attributes = glb_attributes(output)
    for semantic in ("COLOR_0", "NORMAL", "TANGENT"):
        if semantic in source_attributes and semantic not in output_attributes:
            failures.append(f"The source {semantic} vertex data was lost during export.")
    source_transparency = sorted(mode for mode in source_alpha_modes if mode != "OPAQUE")
    output_transparency = sorted(mode for mode in output_alpha_modes if mode != "OPAQUE")
    if source_transparency and not output_transparency:
        failures.append("Material transparency was lost during export.")
    source_shape = normalized_dimensions(source_stats["dimensions"])
    output_shape = normalized_dimensions(reloaded["dimensions"])
    if any(abs(a - b) > 0.06 for a, b in zip(source_shape, output_shape)):
        failures.append("The exported bounds changed enough to risk visible silhouette damage.")
    if not output.is_file() or output.stat().st_size < 1_000:
        failures.append("The exported GLB file is missing or invalid.")
    return reloaded, failures


def main() -> None:
    args = arguments()
    source = Path(args.input).resolve()
    output = Path(args.output).resolve()
    report_path = Path(args.report).resolve()
    progress_path = Path(args.progress).resolve()
    preset = PRESETS[args.preset]
    actions: list[str] = []
    skipped: list[str] = []
    warnings: list[str] = []
    if not source.is_file():
        raise FileNotFoundError(source)
    source_attributes = glb_attributes(source)
    source_alpha_modes = glb_alpha_modes(source)

    progress(progress_path, 8, "Validating the generated GLB…")
    import_glb(source)
    objects = mesh_objects()
    source_stats = stats(objects)
    if source_stats["triangles"] <= 0:
        raise RuntimeError("The source GLB contains no triangles.")

    progress(progress_path, 22, "Checking mesh records and normals…")
    repair_invalid_data(objects, actions, skipped)
    low, high = scene_bounds(objects)
    objects = remove_tiny_object_artifacts(objects, (high - low).length, actions, skipped)

    progress(progress_path, 42, f"Applying the {preset['label']} silhouette-preserving reduction…")
    decimate(objects, preset["ratio"], actions, skipped)

    progress(progress_path, 66, "Setting a game-friendly center and pivot…")
    add_game_origin(objects, actions, skipped)
    optimized_scene_stats = stats(objects)

    progress(progress_path, 78, "Embedding materials and exporting a separate GLB…")
    temp_output = output.with_name(output.stem + ".candidate.glb")
    export_glb(temp_output, include_normals="NORMAL" in source_attributes)

    progress(progress_path, 90, "Reloading the optimized GLB for safety checks…")
    reloaded, failures = validate_round_trip(
        source_stats, optimized_scene_stats, temp_output, source_alpha_modes, source_attributes
    )
    fallback = False
    if failures:
        fallback = True
        warnings.extend(failures)
        warnings.append("Unsafe optimization was rejected; the game-ready download uses the untouched source bytes.")
        shutil.copy2(source, output)
        try:
            temp_output.unlink()
        except FileNotFoundError:
            pass
        import_glb(output)
        reloaded = stats(mesh_objects())
    else:
        temp_output.replace(output)

    original_size = source.stat().st_size
    optimized_size = output.stat().st_size
    original_triangles = source_stats["triangles"]
    optimized_triangles = reloaded["triangles"]
    reduction = max(0.0, (1.0 - optimized_triangles / original_triangles) * 100.0)
    report = {
        "status": "complete",
        "progress": 100,
        "message": "Game-ready copy created and reloaded successfully." if not fallback else "Unsafe operations were skipped; a verified safe copy is ready.",
        "preset": args.preset,
        "preset_label": preset["label"],
        "original_triangles": original_triangles,
        "optimized_triangles": optimized_triangles,
        "reduction_percent": round(reduction, 1),
        "original_file_size": original_size,
        "optimized_file_size": optimized_size,
        "vertices": reloaded["vertices"],
        "triangles": optimized_triangles,
        "file_size": optimized_size,
        "source_stats": source_stats,
        "optimized_stats": reloaded,
        "source_attributes": sorted(source_attributes),
        "operations": actions,
        "skipped_operations": skipped,
        "warnings": warnings,
        "fallback_to_original": fallback,
        "round_trip_verified": True,
        "preserved": {
            "uvs": source_stats["uv_meshes"] == 0 or reloaded["uv_meshes"] > 0,
            "materials": source_stats["materials"] == 0 or reloaded["materials"] > 0,
            "textures": source_stats["images"] == 0 or reloaded["images"] > 0,
            "vertex_colors": "COLOR_0" not in source_attributes or "COLOR_0" in glb_attributes(output),
        },
    }
    write_json(report_path, report)
    write_json(progress_path, report)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        try:
            args = arguments()
            write_json(Path(args.progress), {
                "status": "failed",
                "progress": 100,
                "message": str(exc) or "Game-ready optimization failed.",
                "technical_error": traceback.format_exc()[-4000:],
            })
        except Exception:
            pass
        traceback.print_exc()
        raise
