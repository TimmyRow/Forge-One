"""Render top, three-quarter, side, and underside views of a horizontal GLB."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args(values)


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def main() -> None:
    options = args()
    output_dir = Path(options.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(Path(options.input).resolve()))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    points = [obj.matrix_world @ vertex.co for obj in meshes for vertex in obj.data.vertices]
    minimum = Vector(tuple(min(point[index] for point in points) for index in range(3)))
    maximum = Vector(tuple(max(point[index] for point in points) for index in range(3)))
    center = (minimum + maximum) * 0.5
    extent = maximum - minimum
    radius = max(extent.x, extent.y) * 1.35

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 720
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    if scene.world is None:
        scene.world = bpy.data.worlds.new("REVIEW_World")
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes["Background"]
    background.inputs["Color"].default_value = (0.012, 0.018, 0.032, 1)
    background.inputs["Strength"].default_value = 0.30

    for name, offset, energy, size in (
        ("Key", Vector((-radius, -radius, radius * 1.4)), 1100, radius),
        ("Fill", Vector((radius, 0, radius)), 650, radius * 0.8),
        ("Under", Vector((0, radius, -radius)), 500, radius * 0.7),
    ):
        bpy.ops.object.light_add(type="AREA", location=center + offset)
        light = bpy.context.object
        light.name = f"REVIEW_{name}"
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = size
        look_at(light, center)

    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = max(extent.x, extent.y) * 1.25
    scene.camera = camera
    views = {
        "top": Vector((0, 0, radius)),
        "three_quarter": Vector((radius * 0.72, -radius * 0.72, radius * 0.65)),
        "side": Vector((radius, 0, radius * 0.12)),
        "underside": Vector((0, 0, -radius)),
    }
    for name, offset in views.items():
        camera.location = center + offset
        look_at(camera, center)
        scene.render.filepath = str(output_dir / f"candidate_{name}.png")
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
