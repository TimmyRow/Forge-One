"""Bake Forge One vertex colours into an embedded UV texture GLB in Blender."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import bpy


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=1024)
    values = parser.parse_args(__import__("sys").argv[__import__("sys").argv.index("--") + 1 :])
    if values.resolution not in {512, 1024, 2048}:
        raise ValueError("Texture resolution must be 512, 1024, or 2048.")
    return values


def main() -> None:
    args = arguments()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(args.input))
    objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not objects:
        raise RuntimeError("The GLB contains no mesh objects to texture.")
    if not all(obj.data.color_attributes for obj in objects):
        raise RuntimeError("Texture baking needs a colored model with vertex colors.")

    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.025)
    bpy.ops.object.mode_set(mode="OBJECT")

    image = bpy.data.images.new("ForgeOne_BaseColor", width=args.resolution, height=args.resolution, alpha=True)
    image.generated_color = (0.5, 0.5, 0.5, 1.0)
    image.colorspace_settings.name = "sRGB"
    baked_materials = []
    for index, obj in enumerate(objects):
        attribute_name = obj.data.color_attributes.active_color.name if obj.data.color_attributes.active_color else obj.data.color_attributes[0].name
        material = bpy.data.materials.new(f"ForgeOne_Bake_{index}")
        material.use_nodes = True
        nodes = material.node_tree.nodes
        nodes.clear()
        vertex = nodes.new("ShaderNodeVertexColor")
        vertex.layer_name = attribute_name
        emission = nodes.new("ShaderNodeEmission")
        output = nodes.new("ShaderNodeOutputMaterial")
        target = nodes.new("ShaderNodeTexImage")
        target.image = image
        nodes.active = target
        material.node_tree.links.new(vertex.outputs["Color"], emission.inputs["Color"])
        material.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
        obj.data.materials.clear()
        obj.data.materials.append(material)
        baked_materials.append(material)

    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.device = "CPU"
    bpy.context.scene.render.bake.margin = 12
    bpy.context.scene.render.bake.use_clear = True
    bpy.ops.object.bake(type="EMIT")
    image.pack()

    for index, obj in enumerate(objects):
        material = bpy.data.materials.new(f"ForgeOne_Textured_{index}")
        material.use_nodes = True
        nodes = material.node_tree.nodes
        principled = nodes.get("Principled BSDF")
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = image
        material.node_tree.links.new(texture.outputs["Color"], principled.inputs["Base Color"])
        material.node_tree.links.new(texture.outputs["Alpha"], principled.inputs["Alpha"])
        principled.inputs["Roughness"].default_value = 0.62
        obj.data.materials.clear()
        obj.data.materials.append(material)

    bpy.ops.export_scene.gltf(
        filepath=str(args.output), export_format="GLB", export_apply=True,
        export_texcoords=True, export_normals=True, export_materials="EXPORT",
    )
    if not args.output.is_file() or args.output.stat().st_size < 1024:
        raise RuntimeError("Blender did not produce a valid textured GLB.")

    # Reload in a clean scene: export success alone is not enough validation.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(args.output))
    loaded = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not loaded:
        raise RuntimeError("The textured GLB could not be loaded back into Blender.")
    report = {
        "status": "complete", "resolution": args.resolution,
        "mesh_count": len(loaded), "file_size": args.output.stat().st_size,
        "message": "UV texture baked and verified in a separate GLB copy.",
    }
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # The API reads the process error and never advertises a broken file.
        raise SystemExit(str(error)) from error
