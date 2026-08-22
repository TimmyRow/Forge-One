"""Normalize a semantic rug GLB to a Z-up, bottom-center runtime pivot."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector


def parse_args() -> argparse.Namespace:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--archive", required=True)
    return parser.parse_args(args)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def triangles(objects: list[bpy.types.Object]) -> int:
    total = 0
    for obj in objects:
        obj.data.calc_loop_triangles()
        total += len(obj.data.loop_triangles)
    return total


def bounds(objects: list[bpy.types.Object]) -> tuple[np.ndarray, np.ndarray]:
    points = np.array(
        [tuple(obj.matrix_world @ vertex.co) for obj in objects for vertex in obj.data.vertices]
    )
    return points.min(axis=0), points.max(axis=0)


def main() -> None:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    archive_path = Path(args.archive).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not archive_path.exists():
        raise RuntimeError(f"Pre-normalized archive is missing: {archive_path}")

    clear_scene()
    bpy.ops.import_scene.gltf(filepath=str(input_path))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError(f"Expected one rug mesh, found {len(meshes)}")
    obj = meshes[0]
    before_triangles = triangles(meshes)
    before_materials = sorted(
        slot.material.name for slot in obj.material_slots if slot.material
    )

    # Bake the imported world transform into the mesh before deriving PCA.
    obj.data.transform(obj.matrix_world)
    obj.matrix_world = Matrix.Identity(4)
    points = np.array([tuple(vertex.co) for vertex in obj.data.vertices])
    center = points.mean(axis=0)
    covariance = np.cov(points - center, rowvar=False)
    values, vectors = np.linalg.eigh(covariance)
    order = np.argsort(values)[::-1]
    long_axis = vectors[:, order[0]]
    plane_normal = vectors[:, order[-1]]
    if plane_normal[2] < 0:
        plane_normal *= -1.0

    to_up = Vector(plane_normal).rotation_difference(Vector((0.0, 0.0, 1.0)))
    rotated_long = to_up @ Vector(long_axis)
    z_rotation = Matrix.Rotation(-math.atan2(rotated_long.y, rotated_long.x), 4, "Z")

    for vertex in obj.data.vertices:
        local = vertex.co - Vector(center)
        vertex.co = z_rotation @ (to_up @ local)
    obj.data.update()

    normalized_points = np.array([tuple(vertex.co) for vertex in obj.data.vertices])
    minimum = normalized_points.min(axis=0)
    maximum = normalized_points.max(axis=0)
    shift = Vector(
        (
            -(minimum[0] + maximum[0]) * 0.5,
            -(minimum[1] + maximum[1]) * 0.5,
            -minimum[2],
        )
    )
    for vertex in obj.data.vertices:
        vertex.co += shift
    obj.data.update()
    obj.name = "RoomOne_Rug_ZUp"
    obj.data.name = "RoomOne_Rug_ZUp_Mesh"

    # Ensure the upper exposed surface faces +Z after PCA alignment.
    # Polygon normals are recalculated by Mesh.update() in Blender 4.2.
    final_points = np.array([tuple(vertex.co) for vertex in obj.data.vertices])
    final_minimum = final_points.min(axis=0)
    final_maximum = final_points.max(axis=0)
    height = final_maximum[2] - final_minimum[2]
    top_polygons = [
        polygon
        for polygon in obj.data.polygons
        if polygon.center.z > final_minimum[2] + height * 0.62
    ]
    top_area = sum(polygon.area for polygon in top_polygons)
    upward_area = sum(
        polygon.area for polygon in top_polygons if polygon.normal.z > 0.25
    )
    upward_ratio = upward_area / top_area if top_area else 0.0
    if upward_ratio < 0.70:
        raise RuntimeError(f"Visible rug face is not reliably upward: {upward_ratio:.3f}")

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(
        filepath=str(output_path),
        export_format="GLB",
        use_selection=True,
        export_materials="EXPORT",
        export_yup=True,
        export_apply=False,
        export_draco_mesh_compression_enable=True,
        export_draco_mesh_compression_level=6,
        export_draco_position_quantization=14,
        export_draco_normal_quantization=10,
    )

    clear_scene()
    bpy.ops.import_scene.gltf(filepath=str(output_path))
    reloaded = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    after_triangles = triangles(reloaded)
    after_materials = sorted(
        {slot.material.name for obj in reloaded for slot in obj.material_slots if slot.material}
    )
    reloaded_minimum, reloaded_maximum = bounds(reloaded)
    dimensions = reloaded_maximum - reloaded_minimum
    bottom_center_error = np.array(
        [
            (reloaded_minimum[0] + reloaded_maximum[0]) * 0.5,
            (reloaded_minimum[1] + reloaded_maximum[1]) * 0.5,
            reloaded_minimum[2],
        ]
    )
    if after_triangles != before_triangles:
        raise RuntimeError(f"Triangle count changed: {before_triangles} -> {after_triangles}")
    if len(after_materials) != len(before_materials):
        raise RuntimeError(f"Material count changed: {before_materials} -> {after_materials}")
    if np.max(np.abs(bottom_center_error)) > 2e-3:
        raise RuntimeError(f"Bottom-center pivot validation failed: {bottom_center_error.tolist()}")
    if dimensions[2] >= min(dimensions[0], dimensions[1]) * 0.25:
        raise RuntimeError(f"Rug is not horizontal after reload: {dimensions.tolist()}")

    report = {
        "kind": "rug_runtime_normalization",
        "input": str(input_path),
        "archive": str(archive_path),
        "output": str(output_path),
        "triangles_before": before_triangles,
        "triangles_after_reload": after_triangles,
        "materials_before": before_materials,
        "materials_after_reload": after_materials,
        "visible_face_upward_area_ratio": upward_ratio,
        "bounds_min": reloaded_minimum.tolist(),
        "bounds_max": reloaded_maximum.tolist(),
        "game_space_dimensions": {
            "x_width": float(dimensions[0]),
            "y_depth": float(dimensions[1]),
            "z_height": float(dimensions[2]),
        },
        "bottom_center_pivot_error": bottom_center_error.tolist(),
        "file_size": output_path.stat().st_size,
        "valid_reload": True,
    }
    output_path.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("FORGE_RUG_NORMALIZED=" + json.dumps(report))


if __name__ == "__main__":
    main()
