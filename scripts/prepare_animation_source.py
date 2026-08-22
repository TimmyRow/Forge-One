"""Create a local, editable Blender character scene from a generated GLB.

This is deliberately a *character* route: it builds a simple human-shaped
armature from the model bounds and lets Blender calculate weights.  It cannot
make a chair, vehicle, prop, or partial body walk convincingly, so callers
must opt in only for an upright, full-body humanoid.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def argument(name: str) -> Path | str:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    try:
        return args[args.index(name) + 1]
    except (ValueError, IndexError) as exc:
        raise SystemExit(f"Missing {name}") from exc


def key_rotation(pose_bone, frame: int, degrees: float) -> None:
    pose_bone.rotation_mode = "XYZ"
    pose_bone.rotation_euler = (degrees * 0.01745329252, 0.0, 0.0)
    pose_bone.keyframe_insert(data_path="rotation_euler", frame=frame)


def add_motion(rig, motion: str) -> str:
    """Add a small, editable procedural clip to the generated armature."""
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    rig.animation_data_create()
    action = bpy.data.actions.new(name=f"Forge {motion.title()}")
    rig.animation_data.action = action
    frames = (1, 16, 32)
    if motion == "jump":
        thigh, shin, arm, root = (20, -35, -35, 0.20)
    elif motion == "run":
        thigh, shin, arm, root = (36, -42, -40, 0.08)
    else:
        thigh, shin, arm, root = (22, -28, -24, 0.04)
    for frame, direction in zip(frames, (1, -1, 1)):
        for name, multiplier in (("thigh.L", 1), ("thigh.R", -1), ("upper_arm.L", -1), ("upper_arm.R", 1)):
            key_rotation(rig.pose.bones[name], frame, direction * multiplier * (thigh if "thigh" in name else arm))
        for name, multiplier in (("shin.L", 1), ("shin.R", -1), ("forearm.L", -1), ("forearm.R", 1)):
            key_rotation(rig.pose.bones[name], frame, direction * multiplier * (shin if "shin" in name else arm * 0.35))
        rig.location.z = root if frame == 16 else 0.0
        rig.keyframe_insert(data_path="location", index=2, frame=frame)
    action.frame_range = (1, 32)
    return action.name


def has_skin(meshes, rig) -> bool:
    return all(
        mesh.parent == rig
        and any(modifier.type == "ARMATURE" and modifier.object == rig for modifier in mesh.modifiers)
        and len(mesh.vertex_groups) >= 4
        and sum(1 for vertex in mesh.data.vertices if vertex.groups) >= max(1, len(mesh.data.vertices) // 20)
        for mesh in meshes
    )


def point_segment_distance(point: Vector, start: Vector, end: Vector) -> float:
    segment = end - start
    length_squared = segment.length_squared
    if length_squared < 1e-10:
        return (point - start).length
    fraction = max(0.0, min(1.0, (point - start).dot(segment) / length_squared))
    return (point - (start + segment * fraction)).length


def assign_procedural_weights(meshes, rig) -> None:
    """Fallback for dense AI meshes that Blender heat weighting cannot solve.

    This is still a genuine skin: every vertex is assigned to its two nearest
    generated bones. It is intentionally labeled as a starter rig because a
    reconstructed one-photo mesh has no reliable anatomical topology.
    """
    bone_segments = [(bone.name, bone.head_local.copy(), bone.tail_local.copy()) for bone in rig.data.bones]
    for mesh in meshes:
        mesh.parent = rig
        for group in list(mesh.vertex_groups):
            mesh.vertex_groups.remove(group)
        groups = {name: mesh.vertex_groups.new(name=name) for name, _, _ in bone_segments}
        modifier = next((item for item in mesh.modifiers if item.type == "ARMATURE"), None)
        if modifier is None:
            modifier = mesh.modifiers.new(name="ForgeOne_AutoRig", type="ARMATURE")
        modifier.object = rig
        for vertex in mesh.data.vertices:
            position = mesh.matrix_world @ vertex.co
            nearest = sorted(
                ((point_segment_distance(position, head, tail), name) for name, head, tail in bone_segments),
                key=lambda item: item[0],
            )[:2]
            if len(nearest) == 1:
                groups[nearest[0][1]].add([vertex.index], 1.0, "REPLACE")
                continue
            first_distance, first_name = nearest[0]
            second_distance, second_name = nearest[1]
            total = max(first_distance + second_distance, 1e-8)
            groups[first_name].add([vertex.index], second_distance / total, "REPLACE")
            groups[second_name].add([vertex.index], first_distance / total, "REPLACE")


def main() -> None:
    source = Path(str(argument("--input"))).resolve()
    blend = Path(str(argument("--blend"))).resolve()
    glb = Path(str(argument("--glb"))).resolve()
    report = Path(str(argument("--report"))).resolve()
    motion = str(argument("--motion")).lower()
    blend.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("The GLB did not contain a mesh to rig.")

    # Apply the importer transforms before building the armature around it.
    bpy.ops.object.select_all(action="DESELECT")
    for mesh in meshes:
        mesh.select_set(True)
        bpy.context.view_layer.objects.active = mesh
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    points = [mesh.matrix_world @ Vector(corner) for mesh in meshes for corner in mesh.bound_box]
    low = Vector((min(point.x for point in points), min(point.y for point in points), min(point.z for point in points)))
    high = Vector((max(point.x for point in points), max(point.y for point in points), max(point.z for point in points)))
    width, depth, height = high.x - low.x, high.y - low.y, high.z - low.z
    if height <= 0.001:
        raise RuntimeError("The GLB has no usable height for a character rig.")
    width_ratio, depth_ratio = width / height, depth / height
    if not 0.12 <= width_ratio <= 1.05 or depth_ratio > 0.75:
        raise RuntimeError(
            "This mesh does not have safe full-body humanoid proportions. Use an upright front-facing character with visible arms and legs."
        )

    center_x, center_y = (low.x + high.x) / 2, (low.y + high.y) / 2
    def point(x: float, y: float, z: float) -> Vector:
        return Vector((center_x + x * width, center_y + y * depth, low.z + z * height))

    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.object.armature_add(enter_editmode=True, location=(0, 0, 0))
    rig = bpy.context.object
    rig.name = "ForgeOne_AutoRig"
    rig.data.name = "ForgeOne_AutoRig"
    edit = rig.data.edit_bones
    edit.remove(edit[0])

    bones = {}
    def bone(name, head, tail, parent=None):
        created = edit.new(name)
        created.head, created.tail = head, tail
        if parent:
            created.parent = bones[parent]
            created.use_connect = False
        bones[name] = created

    bone("root", point(0, 0, 0.02), point(0, 0, 0.52))
    bone("spine", point(0, 0, 0.52), point(0, 0, 0.66), "root")
    bone("chest", point(0, 0, 0.66), point(0, 0, 0.78), "spine")
    bone("neck", point(0, 0, 0.78), point(0, 0, 0.86), "chest")
    bone("head", point(0, 0, 0.86), point(0, 0, 0.98), "neck")
    for side, sign in (("L", -1), ("R", 1)):
        bone(f"thigh.{side}", point(sign * .12, 0, .54), point(sign * .14, 0, .29), "root")
        bone(f"shin.{side}", point(sign * .14, 0, .29), point(sign * .14, .02, .07), f"thigh.{side}")
        bone(f"foot.{side}", point(sign * .14, .02, .07), point(sign * .14, -.15, .025), f"shin.{side}")
        bone(f"upper_arm.{side}", point(sign * .18, 0, .76), point(sign * .38, 0, .59), "chest")
        bone(f"forearm.{side}", point(sign * .38, 0, .59), point(sign * .48, 0, .43), f"upper_arm.{side}")
        bone(f"hand.{side}", point(sign * .48, 0, .43), point(sign * .52, -.02, .37), f"forearm.{side}")
    bpy.ops.object.mode_set(mode="OBJECT")

    bpy.ops.object.select_all(action="DESELECT")
    for mesh in meshes:
        mesh.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    weighting = "Blender heat weights"
    try:
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    except RuntimeError:
        pass
    if not has_skin(meshes, rig):
        assign_procedural_weights(meshes, rig)
        weighting = "local procedural fallback weights"
    if not has_skin(meshes, rig):
        raise RuntimeError("Forge Animate could not bind this mesh to the generated character skeleton.")
    weighted_vertices = sum(1 for mesh in meshes for vertex in mesh.data.vertices if vertex.groups)
    total_vertices = sum(len(mesh.data.vertices) for mesh in meshes)
    weighted_coverage = weighted_vertices / max(total_vertices, 1)
    rig_confidence = "good starter rig" if weighting == "Blender heat weights" and weighted_coverage > 0.95 else "review required"

    action_name = add_motion(rig, motion)
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, 32
    bpy.context.scene.render.fps = 30
    bpy.context.scene["forge_one_animation"] = motion
    bpy.context.scene["forge_one_note"] = "Automatic local character rig. Review weights before production use."
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))

    # Export only the selected clip, preserving the editable multi-object scene in .blend.
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    for mesh in meshes:
        mesh.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", use_selection=True, export_animations=True)
    report.write_text(json.dumps({
        "status": "complete", "motion": motion, "action": action_name,
        "mesh_objects": len(meshes), "width": round(width, 4), "depth": round(depth, 4), "height": round(height, 4),
        "weighting": weighting,
        "weighted_coverage": round(weighted_coverage, 4),
        "rig_confidence": rig_confidence,
        "bone_count": len(rig.data.bones),
        "skin_verified": True,
        "message": f"Local automatic rig and editable motion clip created ({rig_confidence}). Review the result before production use.",
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
