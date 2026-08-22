"""Create an isolated decimation test copy of a Forge candidate GLB."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils.kdtree import KDTree


def args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--ratio", type=float, required=True)
    return parser.parse_args(values)


def triangles(obj: bpy.types.Object) -> int:
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def restore_nearest_vertex_colors(source: bpy.types.Object, target: bpy.types.Object) -> None:
    """Transfer CORNER colors from a dense source by nearest source vertex.

    Blender's Decimate modifier keeps the color layer name but fills newly
    generated corners with zeros. Nearest-vertex transfer is stable here because
    decimation follows the exact same surface and the source color is continuous.
    """
    source_attr = source.data.color_attributes.active_color or source.data.color_attributes[0]
    source_loops = np.empty(len(source.data.loops), dtype=np.int32)
    source.data.loops.foreach_get("vertex_index", source_loops)
    source_colors = np.empty(len(source_attr.data) * 4, dtype=np.float32)
    # glTF stores vertex colors in linear space; write Blender's linear color
    # property because the exporter reads that property directly.
    source_attr.data.foreach_get("color", source_colors)
    source_colors = source_colors.reshape((-1, 4))

    # Tripo geometry uses consistent corner color around each vertex. Selecting
    # the first loop avoids a costly multi-million-element averaging pass.
    source_vertex_colors = np.ones((len(source.data.vertices), 4), dtype=np.float32)
    unique_vertices, first_loops = np.unique(source_loops, return_index=True)
    source_vertex_colors[unique_vertices] = source_colors[first_loops]

    tree = KDTree(len(source.data.vertices))
    for vertex in source.data.vertices:
        tree.insert(vertex.co, vertex.index)
    tree.balance()
    target_vertex_colors = np.empty((len(target.data.vertices), 4), dtype=np.float32)
    for vertex in target.data.vertices:
        _position, source_index, _distance = tree.find(vertex.co)
        target_vertex_colors[vertex.index] = source_vertex_colors[source_index]

    target_attr = target.data.color_attributes.get(source_attr.name)
    if target_attr is None or target_attr.domain != "CORNER":
        if target_attr is not None:
            target.data.color_attributes.remove(target_attr)
        target_attr = target.data.color_attributes.new(name=source_attr.name, type="BYTE_COLOR", domain="CORNER")
    target_loops = np.empty(len(target.data.loops), dtype=np.int32)
    target.data.loops.foreach_get("vertex_index", target_loops)
    target_attr.data.foreach_set("color", target_vertex_colors[target_loops].ravel())
    target.data.color_attributes.active_color = target_attr
    target.data.update()
    check = np.empty(len(target_attr.data) * 4, dtype=np.float32)
    target_attr.data.foreach_get("color", check)
    print(
        "FORGE_COLOR_TRANSFER="
        + json.dumps(
            {
                "attribute": target_attr.name,
                "domain": target_attr.domain,
                "type": target_attr.data_type,
                "minimum": float(check.min()),
                "maximum": float(check.max()),
                "unique_sample": int(len(np.unique(check.reshape((-1, 4))[:: max(1, len(target_attr.data) // 5000)], axis=0))),
            }
        )
    )


def bind_vertex_color_material(obj: bpy.types.Object) -> None:
    color_attribute = obj.data.color_attributes.active_color
    if color_attribute is None:
        return
    mat = bpy.data.materials.new(f"MAT_{obj.name}_VertexColor")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    vertex_color = nodes.new("ShaderNodeVertexColor")
    vertex_color.layer_name = color_attribute.name
    links.new(vertex_color.outputs["Color"], shader.inputs["Base Color"])
    links.new(vertex_color.outputs["Alpha"], shader.inputs["Alpha"])
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def has_meaningful_vertex_color(obj: bpy.types.Object) -> bool:
    attr = obj.data.color_attributes.active_color
    if attr is None or not attr.data:
        return False
    first = np.array(attr.data[0].color, dtype=np.float32)
    stride = max(1, len(attr.data) // 4096)
    return any(np.max(np.abs(np.array(attr.data[index].color, dtype=np.float32) - first)) > 1e-5 for index in range(0, len(attr.data), stride))


def main() -> None:
    options = args()
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=str(Path(options.input).resolve()))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    before = sum(triangles(obj) for obj in meshes)
    for obj in meshes:
        color_source = None
        meaningful_color = has_meaningful_vertex_color(obj)
        if meaningful_color:
            # Blender's Collapse modifier does not reliably interpolate CORNER
            # colors. Keep a private source copy and transfer colors back from
            # the original surface after simplification.
            color_source = obj.copy()
            color_source.data = obj.data.copy()
            color_source.name = f"{obj.name}_COLOR_SOURCE"
            bpy.context.scene.collection.objects.link(color_source)
            color_source.hide_render = True
        bpy.context.view_layer.objects.active = obj
        modifier = obj.modifiers.new("Candidate decimation test", "DECIMATE")
        modifier.decimate_type = "COLLAPSE"
        modifier.ratio = options.ratio
        modifier.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        if color_source is not None:
            restore_nearest_vertex_colors(color_source, obj)
            bpy.data.objects.remove(color_source, do_unlink=True)
            bind_vertex_color_material(obj)
        elif obj.data.color_attributes:
            # Neutral generation GLBs sometimes contain a single constant
            # COLOR_0. Drop it so Draco cannot turn a meaningless layer into
            # visible quantization/faceting.
            for attribute in list(obj.data.color_attributes):
                obj.data.color_attributes.remove(attribute)
    after = sum(triangles(obj) for obj in meshes)
    output = Path(options.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(output),
        export_format="GLB",
        export_apply=True,
        export_yup=True,
        export_normals=True,
        export_materials="EXPORT",
        export_vertex_color="MATERIAL",
        export_all_vertex_colors=True,
        export_active_vertex_color_when_no_material=True,
        export_draco_mesh_compression_enable=True,
        export_draco_mesh_compression_level=6,
    )
    print("FORGE_DECIMATION_TEST=" + json.dumps({"ratio": options.ratio, "before": before, "after": after, "output": str(output)}))


if __name__ == "__main__":
    main()
