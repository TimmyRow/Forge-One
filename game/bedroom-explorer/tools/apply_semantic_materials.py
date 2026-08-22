"""Assign conservative semantic PBR materials to accepted Forge geometry."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np


def parse_args() -> argparse.Namespace:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--kind",
        choices=(
            "bed",
            "nightstand",
            "wardrobe",
            "desk",
            "chair",
            "rug",
            "key",
            "journal",
            "lamp",
            "door",
            "frame",
            "window",
        ),
        required=True,
    )
    return parser.parse_args(args)


def srgb_channel(value: int) -> float:
    channel = value / 255.0
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def hex_linear(value: str) -> tuple[float, float, float, float]:
    value = value.removeprefix("#")
    return tuple(srgb_channel(int(value[index : index + 2], 16)) for index in (0, 2, 4)) + (1.0,)


def material(name: str, color: str, roughness: float, metalness: float) -> bpy.types.Material:
    result = bpy.data.materials.new(name)
    result.use_nodes = True
    shader = result.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = hex_linear(color)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metalness
    result.diffuse_color = hex_linear(color)
    return result


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def assign_bed(obj: bpy.types.Object) -> dict[str, int]:
    walnut = material("Bed_Walnut_Frame", "#3A2418", 0.68, 0.0)
    navy = material("Bed_Navy_Padded_Headboard", "#17233F", 0.92, 0.0)
    cream = material("Bed_Cream_Bedding", "#E8E2D6", 0.98, 0.0)
    obj.data.materials.clear()
    for item in (walnut, navy, cream):
        obj.data.materials.append(item)

    counts = {"walnut_frame": 0, "navy_headboard": 0, "cream_bedding": 0}
    for polygon in obj.data.polygons:
        center = obj.matrix_world @ polygon.center
        # The accepted bed is Y-long: the padded headboard is the raised rear
        # slab, bedding sits above the frame, and the lower structure is wood.
        is_headboard_front = center.y > 0.84 and center.z > 0.12
        is_headboard_hidden_back = center.y > 0.88 and center.z > -0.065
        if is_headboard_front or is_headboard_hidden_back:
            polygon.material_index = 1
            counts["navy_headboard"] += 1
        elif center.z > -0.065:
            polygon.material_index = 2
            counts["cream_bedding"] += 1
        else:
            polygon.material_index = 0
            counts["walnut_frame"] += 1
    return counts


def assign_nightstand(obj: bpy.types.Object) -> dict[str, int]:
    walnut = material("Nightstand_Walnut", "#4E3026", 0.68, 0.0)
    brass = material("Nightstand_Brass_Knobs", "#B88A44", 0.30, 0.75)
    obj.data.materials.clear()
    for item in (walnut, brass):
        obj.data.materials.append(item)

    counts = {"walnut": 0, "brass_knobs": 0}
    for polygon in obj.data.polygons:
        center = obj.matrix_world @ polygon.center
        knob_height = abs(center.z - 0.075) < 0.12 or abs(center.z - 0.585) < 0.12
        is_knob = center.y < -0.54 and abs(center.x - 0.04) < 0.16 and knob_height
        polygon.material_index = 1 if is_knob else 0
        counts["brass_knobs" if is_knob else "walnut"] += 1
    return counts


def assign_wardrobe(obj: bpy.types.Object) -> dict[str, int]:
    walnut = material("Wardrobe_Walnut", "#4E3026", 0.68, 0.0)
    brass = material("Wardrobe_Brass_Handles", "#B88A44", 0.30, 0.75)
    obj.data.materials.clear()
    for item in (walnut, brass):
        obj.data.materials.append(item)

    counts = {"walnut": 0, "brass_handles": 0}
    handle_x = (-0.62, 0.025, 0.64)
    for polygon in obj.data.polygons:
        center = obj.matrix_world @ polygon.center
        near_handle_x = min(abs(center.x - position) for position in handle_x) < 0.075
        is_handle = center.y < -0.292 and -0.07 < center.z < 0.09 and near_handle_x
        polygon.material_index = 1 if is_handle else 0
        counts["brass_handles" if is_handle else "walnut"] += 1
    return counts


def assign_uniform(
    obj: bpy.types.Object,
    material_name: str,
    color: str,
    roughness: float,
    metalness: float,
    count_name: str,
) -> dict[str, int]:
    surface = material(material_name, color, roughness, metalness)
    obj.data.materials.clear()
    obj.data.materials.append(surface)
    for polygon in obj.data.polygons:
        polygon.material_index = 0
    return {count_name: len(obj.data.polygons)}


def assign_chair(obj: bpy.types.Object) -> dict[str, int]:
    navy = material("Chair_Navy_Upholstery", "#24324F", 0.95, 0.0)
    walnut = material("Chair_Walnut_Legs", "#53331F", 0.70, 0.0)
    obj.data.materials.clear()
    for item in (navy, walnut):
        obj.data.materials.append(item)
    counts = {"navy_upholstery": 0, "walnut_legs": 0}
    for polygon in obj.data.polygons:
        center = obj.matrix_world @ polygon.center
        is_leg = center.z < 0.79
        polygon.material_index = 1 if is_leg else 0
        counts["walnut_legs" if is_leg else "navy_upholstery"] += 1
    return counts


def principal_frame(obj: bpy.types.Object) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    points = np.array([tuple(obj.matrix_world @ vertex.co) for vertex in obj.data.vertices])
    origin = points.mean(axis=0)
    covariance = np.cov(points - origin, rowvar=False)
    values, vectors = np.linalg.eigh(covariance)
    order = np.argsort(values)[::-1]
    axes = vectors[:, order].T
    projected = (points - origin) @ axes.T
    return origin, axes, projected.min(axis=0), projected.max(axis=0)


def normalized_principal_position(
    point: tuple[float, float, float],
    origin: np.ndarray,
    axes: np.ndarray,
    minimum: np.ndarray,
    maximum: np.ndarray,
) -> np.ndarray:
    projected = (np.asarray(point) - origin) @ axes.T
    span = np.maximum(maximum - minimum, 1e-8)
    return ((projected - minimum) / span) * 2.0 - 1.0


def assign_rug(obj: bpy.types.Object) -> dict[str, int]:
    navy = material("Rug_Navy_Field", "#162849", 0.98, 0.0)
    cream = material("Rug_Cream_Border", "#E3DAC5", 1.0, 0.0)
    obj.data.materials.clear()
    for item in (navy, cream):
        obj.data.materials.append(item)
    origin, axes, minimum, maximum = principal_frame(obj)
    counts = {"navy_field": 0, "cream_border": 0}
    for polygon in obj.data.polygons:
        center = obj.matrix_world @ polygon.center
        position = normalized_principal_position(tuple(center), origin, axes, minimum, maximum)
        is_border = max(abs(position[0]), abs(position[1])) > 0.78
        polygon.material_index = 1 if is_border else 0
        counts["cream_border" if is_border else "navy_field"] += 1
    return counts


def assign_journal(obj: bpy.types.Object) -> dict[str, int]:
    leather = material("Journal_Navy_Leather", "#1C2944", 0.78, 0.0)
    pages = material("Journal_Cream_Pages", "#E4D8BD", 1.0, 0.0)
    obj.data.materials.clear()
    for item in (leather, pages):
        obj.data.materials.append(item)
    origin, axes, minimum, maximum = principal_frame(obj)
    counts = {"navy_leather": 0, "cream_pages": 0}
    for polygon in obj.data.polygons:
        center = obj.matrix_world @ polygon.center
        position = normalized_principal_position(tuple(center), origin, axes, minimum, maximum)
        # PCA axis 2 is the thin book axis. Outer slabs are leather covers;
        # the recessed middle edge is the page block. No hardware is distinct
        # enough in this accepted mesh to justify a risky brass assignment.
        is_cover = abs(position[2]) > 0.56
        polygon.material_index = 0 if is_cover else 1
        counts["navy_leather" if is_cover else "cream_pages"] += 1
    return counts


def assign_lamp(obj: bpy.types.Object) -> dict[str, int]:
    shade = material("Lamp_Warm_Cream_Shade", "#E8C998", 0.78, 0.0)
    brass = material("Lamp_Antique_Brass_Base", "#B88A44", 0.30, 0.75)
    obj.data.materials.clear()
    for item in (shade, brass):
        obj.data.materials.append(item)

    counts = {"warm_cream_shade": 0, "antique_brass_stem_base": 0}
    for polygon in obj.data.polygons:
        center = obj.matrix_world @ polygon.center
        radius = math.hypot(center.x, center.y)
        # The accepted lamp is centered and Z-up. Its shade is a broad conical
        # shell from z ~= 0.06 to 0.85. A radial gate intentionally leaves the
        # center support, top finial, neck and lower body as antique brass.
        radial_gate = 0.28 if center.z < 0.25 else 0.15
        is_shade = 0.05 < center.z < 0.855 and radius > radial_gate
        polygon.material_index = 0 if is_shade else 1
        counts["warm_cream_shade" if is_shade else "antique_brass_stem_base"] += 1
    return counts


def assign_door(obj: bpy.types.Object) -> dict[str, int]:
    walnut = material("Door_Walnut", "#4E3026", 0.68, 0.0)
    brass = material("Door_Antique_Brass_Lever", "#B88A44", 0.30, 0.75)
    obj.data.materials.clear()
    for item in (walnut, brass):
        obj.data.materials.append(item)

    counts = {"walnut_slab": 0, "antique_brass_lever": 0}
    for polygon in obj.data.polygons:
        center = obj.matrix_world @ polygon.center
        # Both lever assemblies are isolated protrusions around local x=-0.31,
        # z=-0.03. Requiring depth beyond the slab protects the door faces and
        # any shallow panel relief from accidental brass assignment.
        is_lever = (
            abs(center.y) > 0.075
            and -0.43 < center.x < -0.18
            and -0.09 < center.z < 0.045
        )
        polygon.material_index = 1 if is_lever else 0
        counts["antique_brass_lever" if is_lever else "walnut_slab"] += 1
    return counts


def assign_frame(obj: bpy.types.Object) -> dict[str, int]:
    walnut = material("Frame_Dark_Walnut", "#3A2418", 0.72, 0.0)
    inset = material("Frame_Cream_Photo_Panel", "#D8C9AB", 0.96, 0.0)
    obj.data.materials.clear()
    for item in (walnut, inset):
        obj.data.materials.append(item)

    counts = {"dark_walnut_frame_stand": 0, "cream_inset_panel": 0}
    for polygon in obj.data.polygons:
        center = obj.matrix_world @ polygon.center
        # The inset occupies a safe central rectangle on the camera-facing
        # plane. The strong -Y normal gate prevents rear easel and hinge
        # geometry from becoming cream even though the frame leans backward.
        normal = obj.matrix_world.to_3x3() @ polygon.normal
        is_inset = (
            abs(center.x) < 0.47
            and -0.62 < center.z < 0.73
            and normal.y < -0.62
        )
        polygon.material_index = 1 if is_inset else 0
        counts["cream_inset_panel" if is_inset else "dark_walnut_frame_stand"] += 1
    return counts


def assign_window(obj: bpy.types.Object) -> dict[str, int]:
    walnut = material("Window_Walnut_Frame_Rod", "#4E3026", 0.70, 0.0)
    navy = material("Window_Navy_Curtains", "#17233F", 0.94, 0.0)
    obj.data.materials.clear()
    for item in (walnut, navy):
        obj.data.materials.append(item)

    counts = {"walnut_frame_rod": 0, "navy_curtains": 0, "pane_geometry": 0}
    for polygon in obj.data.polygons:
        center = obj.matrix_world @ polygon.center
        # Curtains are the tall outer volumes in front of the window. The rod,
        # rings and finials are retained as walnut above them. The accepted
        # geometry has true open panes, so no artificial glass slab is added.
        is_curtain = center.z < 0.80 and abs(center.x) > 0.62
        polygon.material_index = 1 if is_curtain else 0
        counts["navy_curtains" if is_curtain else "walnut_frame_rod"] += 1
    return counts


def normalize_door(obj: bpy.types.Object, target_height: float = 2.05) -> dict[str, object]:
    """Bake a Z-up, uniformly scaled door with a bottom-center origin."""
    corners = np.array([tuple(obj.matrix_world @ vertex.co) for vertex in obj.data.vertices])
    minimum = corners.min(axis=0)
    maximum = corners.max(axis=0)
    height = maximum[2] - minimum[2]
    if height <= 1e-8:
        raise RuntimeError("Door height is zero; normalization is unsafe")
    scale = target_height / height
    center_x = (minimum[0] + maximum[0]) * 0.5
    center_y = (minimum[1] + maximum[1]) * 0.5
    offset = np.array([center_x, center_y, minimum[2]])

    for vertex in obj.data.vertices:
        world = np.array(tuple(obj.matrix_world @ vertex.co))
        normalized = (world - offset) * scale
        vertex.co = tuple(float(value) for value in normalized)
    obj.matrix_world.identity()
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    obj.data.update()

    normalized_points = np.array([tuple(vertex.co) for vertex in obj.data.vertices])
    normalized_min = normalized_points.min(axis=0)
    normalized_max = normalized_points.max(axis=0)
    dimensions = normalized_max - normalized_min
    return {
        "target_height": target_height,
        "uniform_scale": float(scale),
        "bounds_min": normalized_min.tolist(),
        "bounds_max": normalized_max.tolist(),
        "dimensions": dimensions.tolist(),
        "pivot": "bottom-center",
        "handle_side": "local X minimum",
        "hinge_edge": "local X maximum",
        "hinge_x": float(normalized_max[0]),
    }


def normalize_frame(obj: bpy.types.Object, target_height: float = 0.28) -> dict[str, object]:
    """Uniformly size the frame for a tabletop and bake a bottom-center pivot."""
    points = np.array([tuple(obj.matrix_world @ vertex.co) for vertex in obj.data.vertices])
    minimum = points.min(axis=0)
    maximum = points.max(axis=0)
    height = maximum[2] - minimum[2]
    if height <= 1e-8:
        raise RuntimeError("Frame height is zero; normalization is unsafe")
    scale = target_height / height
    offset = np.array(
        [
            (minimum[0] + maximum[0]) * 0.5,
            (minimum[1] + maximum[1]) * 0.5,
            minimum[2],
        ]
    )
    for vertex in obj.data.vertices:
        world = np.array(tuple(obj.matrix_world @ vertex.co))
        vertex.co = tuple(float(value) for value in (world - offset) * scale)
    obj.matrix_world.identity()
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    obj.data.update()
    normalized_points = np.array([tuple(vertex.co) for vertex in obj.data.vertices])
    normalized_min = normalized_points.min(axis=0)
    normalized_max = normalized_points.max(axis=0)
    return {
        "target_height": target_height,
        "uniform_scale": float(scale),
        "bounds_min": normalized_min.tolist(),
        "bounds_max": normalized_max.tolist(),
        "dimensions": (normalized_max - normalized_min).tolist(),
        "pivot": "bottom-center",
        "placement": "tabletop",
    }


def normalize_window(obj: bpy.types.Object, target_height: float = 1.45) -> dict[str, object]:
    """Uniformly size the window and bake a bottom-center wall placement pivot."""
    points = np.array([tuple(obj.matrix_world @ vertex.co) for vertex in obj.data.vertices])
    minimum = points.min(axis=0)
    maximum = points.max(axis=0)
    height = maximum[2] - minimum[2]
    if height <= 1e-8:
        raise RuntimeError("Window height is zero; normalization is unsafe")
    scale = target_height / height
    offset = np.array(
        [
            (minimum[0] + maximum[0]) * 0.5,
            (minimum[1] + maximum[1]) * 0.5,
            minimum[2],
        ]
    )
    for vertex in obj.data.vertices:
        world = np.array(tuple(obj.matrix_world @ vertex.co))
        vertex.co = tuple(float(value) for value in (world - offset) * scale)
    obj.matrix_world.identity()
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    obj.data.update()
    normalized_points = np.array([tuple(vertex.co) for vertex in obj.data.vertices])
    normalized_min = normalized_points.min(axis=0)
    normalized_max = normalized_points.max(axis=0)
    return {
        "target_height": target_height,
        "uniform_scale": float(scale),
        "bounds_min": normalized_min.tolist(),
        "bounds_max": normalized_max.tolist(),
        "dimensions": (normalized_max - normalized_min).tolist(),
        "pivot": "bottom-center",
        "front_direction": "local -Y (curtains project into room)",
        "rear_direction": "local +Y (faces wall)",
        "pane_treatment": "open; no safely isolated pane geometry existed",
    }


def main() -> None:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    clear_scene()
    bpy.ops.import_scene.gltf(filepath=str(input_path))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError(f"Expected one accepted mesh, found {len(meshes)}")
    obj = meshes[0]
    obj.name = f"RoomOne_{args.kind.title()}"

    # Semantic materials are the only color authority for these candidates.
    # Explicitly remove any inherited COLOR_0-style layers so an old projected
    # pass cannot tint or override the authored PBR regions at runtime.
    for color_attribute in list(obj.data.color_attributes):
        obj.data.color_attributes.remove(color_attribute)

    before_triangles = sum(len(mesh.loop_triangles) for mesh in (obj.data,))
    if args.kind == "bed":
        counts = assign_bed(obj)
    elif args.kind == "nightstand":
        counts = assign_nightstand(obj)
    elif args.kind == "wardrobe":
        counts = assign_wardrobe(obj)
    elif args.kind == "desk":
        counts = assign_uniform(obj, "Desk_Walnut", "#4E3026", 0.68, 0.0, "walnut")
    elif args.kind == "chair":
        counts = assign_chair(obj)
    elif args.kind == "rug":
        counts = assign_rug(obj)
    elif args.kind == "key":
        counts = assign_uniform(obj, "Key_Antique_Brass", "#C59A43", 0.28, 0.85, "brass")
    elif args.kind == "lamp":
        counts = assign_lamp(obj)
    elif args.kind == "door":
        counts = assign_door(obj)
    elif args.kind == "frame":
        counts = assign_frame(obj)
    elif args.kind == "window":
        counts = assign_window(obj)
    else:
        counts = assign_journal(obj)

    if args.kind == "door":
        normalization = normalize_door(obj)
    elif args.kind == "frame":
        normalization = normalize_frame(obj)
    elif args.kind == "window":
        normalization = normalize_window(obj)
    else:
        normalization = None

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
    after_triangles = sum(len(obj.data.loop_triangles) for obj in reloaded)
    material_names = sorted(
        {slot.material.name for obj in reloaded for slot in obj.material_slots if slot.material}
    )
    color_attributes_after_reload = sorted(
        {attribute.name for obj in reloaded for attribute in obj.data.color_attributes}
    )
    if not reloaded or after_triangles != before_triangles:
        raise RuntimeError(
            f"GLB reload validation failed: {before_triangles} -> {after_triangles} triangles"
        )
    expected_material_count = 1 if args.kind in {"desk", "key"} else 2 if args.kind != "bed" else 3
    if len(material_names) < expected_material_count:
        raise RuntimeError(f"Semantic materials missing after reload: {material_names}")
    if color_attributes_after_reload:
        raise RuntimeError(
            f"Projected vertex color attributes survived export: {color_attributes_after_reload}"
        )

    report = {
        "kind": args.kind,
        "input": str(input_path),
        "output": str(output_path),
        "triangles_before": before_triangles,
        "triangles_after_reload": after_triangles,
        "material_faces": counts,
        "materials_after_reload": material_names,
        "vertex_color_attributes_after_reload": color_attributes_after_reload,
        "file_size": output_path.stat().st_size,
        "valid_reload": True,
    }
    if normalization:
        report["normalization"] = normalization
    report_path = output_path.with_suffix(".json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("FORGE_SEMANTIC_MATERIALS=" + json.dumps(report))


if __name__ == "__main__":
    main()
