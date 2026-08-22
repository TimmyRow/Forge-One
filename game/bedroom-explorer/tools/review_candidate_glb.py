"""Render neutral multi-angle review images and mesh statistics for a GLB."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    args = []
    if "--" in __import__("sys").argv:
        args = __import__("sys").argv[__import__("sys").argv.index("--") + 1 :]
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args(args)


def clear() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def world_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    return (
        Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points))),
        Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points))),
    )


def main() -> None:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    clear()
    bpy.ops.import_scene.gltf(filepath=str(input_path))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("GLB contains no mesh objects")

    minimum, maximum = world_bounds(meshes)
    center = (minimum + maximum) * 0.5
    extent = maximum - minimum
    triangles = 0
    vertices = 0
    invalid_meshes = []
    degenerate_faces = 0
    for obj in meshes:
        mesh = obj.data
        mesh.calc_loop_triangles()
        triangles += len(mesh.loop_triangles)
        vertices += len(mesh.vertices)
        if mesh.validate(clean_customdata=False):
            invalid_meshes.append(obj.name)
        degenerate_faces += sum(1 for poly in mesh.polygons if poly.area <= 1e-12)

        # Forge's separate Color pass deliberately stores color as COLOR_0 and
        # may not attach a material. Bind the active color layer for an honest
        # review render instead of silently showing the geometry as white.
        if mesh.color_attributes and not obj.data.materials:
            color_attribute = mesh.color_attributes.active_color or mesh.color_attributes[0]
            review_material = bpy.data.materials.new(f"REVIEW_VertexColor_{obj.name}")
            review_material.use_nodes = True
            nodes = review_material.node_tree.nodes
            links = review_material.node_tree.links
            shader = nodes.get("Principled BSDF")
            vertex_color = nodes.new("ShaderNodeVertexColor")
            vertex_color.layer_name = color_attribute.name
            links.new(vertex_color.outputs["Color"], shader.inputs["Base Color"])
            obj.data.materials.append(review_material)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 720
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.012, 0.018, 0.032, 1)
    bg.inputs["Strength"].default_value = 0.35

    # Neutral floor makes floating or trailing geometry unambiguous.
    floor_mat = bpy.data.materials.new("REVIEW_Floor")
    floor_mat.use_nodes = True
    floor_bsdf = floor_mat.node_tree.nodes.get("Principled BSDF")
    floor_bsdf.inputs["Base Color"].default_value = (0.035, 0.045, 0.065, 1)
    floor_bsdf.inputs["Roughness"].default_value = 0.92
    floor_size = max(extent.x, extent.y) * 3.0
    bpy.ops.mesh.primitive_plane_add(size=floor_size, location=(center.x, center.y, minimum.z - max(extent.z * 0.012, 0.002)))
    floor = bpy.context.object
    floor.name = "REVIEW_Ground"
    floor.data.materials.append(floor_mat)

    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.name = "REVIEW_Camera"
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = max(extent.x, extent.z) * 1.30
    scene.camera = camera

    def area(name: str, location: tuple[float, float, float], energy: float, size: float) -> None:
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.name = name
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = size
        look_at(light, center)

    radius = max(extent.x, extent.y, extent.z) * 2.2
    # Scale emitted power with scene size. Fixed studio wattage overexposes
    # tabletop-normalized assets even though the camera and light positions
    # already scale correctly.
    energy_scale = max((radius / 4.2) ** 2, 0.015)
    area("REVIEW_Key", tuple(center + Vector((-radius, -radius, radius))), 1200 * energy_scale, radius)
    area(
        "REVIEW_Fill",
        tuple(center + Vector((radius, -radius * 0.4, radius * 0.5))),
        700 * energy_scale,
        radius * 0.75,
    )
    area("REVIEW_Rim", tuple(center + Vector((0, radius, radius))), 900 * energy_scale, radius * 0.65)

    views = {
        "front": Vector((0, -radius, extent.z * 0.08)),
        "three_quarter": Vector((radius * 0.72, -radius * 0.72, extent.z * 0.18)),
        "side": Vector((radius, 0, extent.z * 0.08)),
        "back": Vector((0, radius, extent.z * 0.08)),
    }
    for name, offset in views.items():
        camera.location = center + offset
        look_at(camera, center)
        scene.render.filepath = str(output_dir / f"candidate_{name}.png")
        bpy.ops.render.render(write_still=True)

    report = {
        "input": str(input_path),
        "mesh_objects": len(meshes),
        "vertices": vertices,
        "triangles": triangles,
        "materials": len({slot.material.name for obj in meshes for slot in obj.material_slots if slot.material}),
        "bounds_min": list(minimum),
        "bounds_max": list(maximum),
        "dimensions": list(extent),
        "aspect_ratios": {
            "width_to_height": extent.x / extent.z if extent.z else None,
            "depth_to_height": extent.y / extent.z if extent.z else None,
        },
        "invalid_meshes": invalid_meshes,
        "degenerate_faces": degenerate_faces,
        "renders": [f"candidate_{name}.png" for name in views],
    }
    (output_dir / "candidate_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("FORGE_CANDIDATE_REVIEW=" + json.dumps(report))


if __name__ == "__main__":
    main()
