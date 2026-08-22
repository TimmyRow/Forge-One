"""Build and export Forge One's cozy bedroom game environment.

Run with Blender 4.2+:
  blender --background --python tools/build_bedroom_scene.py

The script intentionally uses only Blender-native geometry and PBR materials so
the result remains editable, deterministic, and lightweight for the web.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


HERE = Path(__file__).resolve().parent
OUT_DIR = HERE.parent / "public" / "assets" / "models" / "bedroom"
BLEND_PATH = OUT_DIR / "cozy_bedroom.blend"
GLB_PATH = OUT_DIR / "cozy_bedroom.glb"
FBX_PATH = OUT_DIR / "cozy_bedroom.fbx"
PREVIEW_PATH = OUT_DIR / "cozy_bedroom_preview.png"
REPORT_PATH = OUT_DIR / "cozy_bedroom_report.json"


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def collection(name: str) -> bpy.types.Collection:
    result = bpy.data.collections.get(name)
    if result is None:
        result = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(result)
    return result


def move_to_collection(obj: bpy.types.Object, target: bpy.types.Collection) -> None:
    for existing in list(obj.users_collection):
        existing.objects.unlink(obj)
    target.objects.link(obj)


def material(
    name: str,
    color: tuple[float, float, float, float],
    roughness: float = 0.55,
    metallic: float = 0.0,
    emission: tuple[float, float, float, float] | None = None,
    emission_strength: float = 0.0,
) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = color
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if emission is not None:
        emission_input = bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission")
        if emission_input:
            emission_input.default_value = emission
        strength_input = bsdf.inputs.get("Emission Strength")
        if strength_input:
            strength_input.default_value = emission_strength
    return mat


def assign(obj: bpy.types.Object, mat: bpy.types.Material) -> bpy.types.Object:
    if obj.data and hasattr(obj.data, "materials"):
        obj.data.materials.append(mat)
    return obj


def apply_mesh_transforms(obj: bpy.types.Object) -> None:
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    obj.select_set(False)


def smooth(obj: bpy.types.Object, angle: float = math.radians(50.0)) -> None:
    if obj.type != "MESH":
        return
    for poly in obj.data.polygons:
        poly.use_smooth = True
    obj.data.set_sharp_from_angle(angle=angle)


def box(
    name: str,
    location: tuple[float, float, float],
    size: tuple[float, float, float],
    mat: bpy.types.Material,
    *,
    bevel: float = 0.0,
    bevel_segments: int = 2,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    target_collection: bpy.types.Collection,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    apply_mesh_transforms(obj)
    assign(obj, mat)
    if bevel > 0:
        mod = obj.modifiers.new("Edge softness", "BEVEL")
        mod.width = min(bevel, min(size) * 0.45)
        mod.segments = bevel_segments
        mod.limit_method = "ANGLE"
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=mod.name)
        smooth(obj)
    move_to_collection(obj, target_collection)
    return obj


def cylinder(
    name: str,
    location: tuple[float, float, float],
    radius: float,
    depth: float,
    mat: bpy.types.Material,
    *,
    vertices: int = 20,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    target_collection: bpy.types.Collection,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    assign(obj, mat)
    apply_mesh_transforms(obj)
    smooth(obj)
    move_to_collection(obj, target_collection)
    return obj


def uv_sphere(
    name: str,
    location: tuple[float, float, float],
    scale: tuple[float, float, float],
    mat: bpy.types.Material,
    *,
    segments: int = 20,
    rings: int = 12,
    target_collection: bpy.types.Collection,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    apply_mesh_transforms(obj)
    assign(obj, mat)
    smooth(obj)
    move_to_collection(obj, target_collection)
    return obj


def empty(name: str, location: tuple[float, float, float], target_collection: bpy.types.Collection) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, None)
    obj.location = location
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 0.15
    target_collection.objects.link(obj)
    return obj


def parent_keep_world(child: bpy.types.Object, parent: bpy.types.Object) -> None:
    world = child.matrix_world.copy()
    child.parent = parent
    child.matrix_world = world


def add_frame(
    prefix: str,
    center: tuple[float, float, float],
    outer: tuple[float, float],
    thickness: float,
    depth: float,
    mat: bpy.types.Material,
    target_collection: bpy.types.Collection,
) -> list[bpy.types.Object]:
    cx, cy, cz = center
    width, height = outer
    parts = [
        box(f"{prefix}_Top", (cx, cy, cz + height / 2), (width, depth, thickness), mat, bevel=0.012, target_collection=target_collection),
        box(f"{prefix}_Bottom", (cx, cy, cz - height / 2), (width, depth, thickness), mat, bevel=0.012, target_collection=target_collection),
        box(f"{prefix}_Left", (cx - width / 2, cy, cz), (thickness, depth, height), mat, bevel=0.012, target_collection=target_collection),
        box(f"{prefix}_Right", (cx + width / 2, cy, cz), (thickness, depth, height), mat, bevel=0.012, target_collection=target_collection),
    ]
    return parts


def collision_box(name: str, location: tuple[float, float, float], size: tuple[float, float, float], target_collection: bpy.types.Collection, mat: bpy.types.Material) -> bpy.types.Object:
    obj = box(name, location, size, mat, target_collection=target_collection)
    obj["collision"] = True
    obj["collision_shape"] = "box"
    obj["visible_in_game"] = False
    obj.display_type = "WIRE"
    return obj


def setup_world_and_render() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world.color = (0.018, 0.025, 0.045)
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.018, 0.025, 0.055, 1.0)
    bg.inputs["Strength"].default_value = 0.25


def add_camera_and_lights(render_collection: bpy.types.Collection) -> None:
    bpy.ops.object.camera_add(location=(9.5, -12.0, 7.8))
    camera = bpy.context.object
    camera.name = "Preview_Camera"
    camera.data.lens = 48
    target = Vector((0.0, 0.15, 1.15))
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    move_to_collection(camera, render_collection)
    bpy.context.scene.camera = camera

    def area(name: str, location: tuple[float, float, float], energy: float, size: float, color: tuple[float, float, float], target: tuple[float, float, float]) -> None:
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.name = name
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = size
        light.data.color = color
        light.rotation_euler = (Vector(target) - light.location).to_track_quat("-Z", "Y").to_euler()
        move_to_collection(light, render_collection)

    area("Preview_Key_Light", (0.0, -3.2, 5.0), 1500, 5.5, (1.0, 0.78, 0.58), (0.0, 0.4, 0.8))
    area("Preview_Window_Light", (-3.0, 2.5, 3.0), 900, 2.8, (0.45, 0.65, 1.0), (-0.5, 0.0, 1.0))
    area("Preview_Fill_Light", (4.2, -1.0, 3.2), 700, 3.0, (0.78, 0.9, 1.0), (0.8, 0.5, 1.0))


def build_scene() -> None:
    clear_scene()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    setup_world_and_render()

    arch = collection("ARCHITECTURE")
    furniture = collection("FURNITURE")
    props = collection("INTERACTABLES")
    details = collection("DECOR")
    collisions = collection("COLLISION")
    render_helpers = collection("RENDER_HELPERS")

    # Reusable, web-friendly PBR materials.
    wall = material("MAT_WarmPlaster", (0.73, 0.69, 0.62, 1), 0.88)
    trim = material("MAT_CreamTrim", (0.88, 0.83, 0.72, 1), 0.7)
    wood = material("MAT_Walnut", (0.20, 0.075, 0.035, 1), 0.43)
    wood_light = material("MAT_Oak", (0.49, 0.25, 0.095, 1), 0.5)
    wood_dark = material("MAT_DarkWood", (0.075, 0.032, 0.018, 1), 0.42)
    metal = material("MAT_BrushedBrass", (0.55, 0.29, 0.075, 1), 0.26, 0.65)
    black_metal = material("MAT_BlackMetal", (0.018, 0.024, 0.032, 1), 0.28, 0.72)
    linen = material("MAT_Linen", (0.89, 0.84, 0.73, 1), 0.92)
    duvet = material("MAT_DuvetSage", (0.22, 0.35, 0.27, 1), 0.9)
    accent = material("MAT_AccentRust", (0.48, 0.12, 0.055, 1), 0.82)
    rug_mat = material("MAT_Rug", (0.34, 0.18, 0.15, 1), 0.96)
    paper = material("MAT_Paper", (0.88, 0.81, 0.66, 1), 0.95)
    photo = material("MAT_Photo", (0.12, 0.28, 0.34, 1), 0.6)
    glass = material("MAT_WindowGlass", (0.025, 0.09, 0.15, 1), 0.12, 0.1, emission=(0.04, 0.12, 0.24, 1), emission_strength=0.25)
    lampshade = material("MAT_LampShade", (0.82, 0.56, 0.26, 1), 0.72, emission=(1.0, 0.45, 0.12, 1), emission_strength=1.2)
    collision_mat = material("MAT_CollisionInvisible", (0.05, 0.8, 0.2, 0.0), 1.0)
    bsdf = collision_mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Alpha"].default_value = 0.0
    collision_mat.diffuse_color = (0.05, 0.8, 0.2, 0.0)
    try:
        collision_mat.surface_render_method = "DITHERED"
    except Exception:
        pass

    # Runtime contract: Blender +Y becomes glTF -Z. This creates a 9 x 8 m
    # playable room with its back wall at runtime Z=-4 and front at Z=+4.
    box("Room_FloorSlab", (0, 0, -0.04), (9.0, 8.0, 0.08), wood_dark, target_collection=arch)
    plank_width = 9.0 / 18.0
    plank_mats = (wood, wood_light, wood_dark)
    for i in range(18):
        x = -4.5 + plank_width * (i + 0.5)
        box(f"Floor_Plank_{i+1:02d}", (x, 0, 0.015), (plank_width - 0.012, 8.0, 0.03), plank_mats[i % 3], bevel=0.006, target_collection=arch)
    box("Wall_Back", (0, 4.05, 1.6), (9.1, 0.10, 3.2), wall, target_collection=arch)
    box("Wall_Left", (-4.55, 0, 1.6), (0.10, 8.0, 3.2), wall, target_collection=arch)
    box("Wall_Right", (4.55, 0, 1.6), (0.10, 8.0, 3.2), wall, target_collection=arch)
    for name, loc, size in (
        ("Trim_Back", (0, 3.96, 0.09), (9.0, 0.07, 0.18)),
        ("Trim_Left", (-4.46, 0, 0.09), (0.07, 7.9, 0.18)),
        ("Trim_Right", (4.46, 0, 0.09), (0.07, 7.9, 0.18)),
    ):
        box(name, loc, size, trim, bevel=0.01, target_collection=arch)

    # Large window and curtains on the back wall.
    box("Window_Glass", (-2.25, 3.985, 1.92), (1.85, 0.025, 1.32), glass, target_collection=arch)
    add_frame("Window_Frame", (-2.25, 3.94, 1.92), (2.0, 1.45), 0.08, 0.11, trim, arch)
    box("Window_Mullion_V", (-2.25, 3.92, 1.92), (0.055, 0.13, 1.32), trim, bevel=0.008, target_collection=arch)
    box("Window_Mullion_H", (-2.25, 3.92, 1.92), (1.85, 0.13, 0.055), trim, bevel=0.008, target_collection=arch)
    cylinder("Curtain_Rod", (-2.25, 3.81, 2.73), 0.025, 2.35, black_metal, rotation=(0, math.pi / 2, 0), target_collection=details)
    for side, x in (("Left", -3.24), ("Right", -1.26)):
        box(f"Curtain_{side}", (x, 3.79, 1.79), (0.34, 0.08, 1.82), accent, bevel=0.06, bevel_segments=4, target_collection=details)

    # Open front-center door frame. The runtime supplies the interactive door,
    # so there is deliberately no opaque door slab to overlap it.
    door_frame = empty("DoorFrame", (0.0, -3.93, 0.0), arch)
    door_frame["entry"] = True
    for frame_part in (
        box("DoorFrame_Left", (-0.73, -3.93, 1.15), (0.14, 0.18, 2.30), trim, bevel=0.018, target_collection=arch),
        box("DoorFrame_Right", (0.73, -3.93, 1.15), (0.14, 0.18, 2.30), trim, bevel=0.018, target_collection=arch),
        box("DoorFrame_Top", (0.0, -3.93, 2.30), (1.60, 0.18, 0.14), trim, bevel=0.018, target_collection=arch),
    ):
        parent_keep_world(frame_part, door_frame)

    # Bed assembly with layered bedding and real gameplay pivot at floor center.
    bed_root = empty("Furniture_Bed", (-0.70, 0.72, 0.0), furniture)
    bed_root["category"] = "furniture"
    for child in (
        box("Bed_Frame", (-0.70, 0.72, 0.30), (1.62, 2.08, 0.26), wood_dark, bevel=0.06, target_collection=furniture),
        box("Bed_Headboard", (-0.70, 1.75, 0.87), (1.72, 0.12, 1.30), wood, bevel=0.055, target_collection=furniture),
        box("Bed_Mattress", (-0.70, 0.67, 0.53), (1.54, 1.94, 0.30), linen, bevel=0.11, bevel_segments=4, target_collection=furniture),
        box("Bed_Duvet", (-0.70, 0.43, 0.72), (1.58, 1.44, 0.24), duvet, bevel=0.12, bevel_segments=5, target_collection=furniture),
        box("Bed_Throw", (-0.70, -0.05, 0.84), (1.60, 0.42, 0.10), accent, bevel=0.045, bevel_segments=4, target_collection=furniture),
        uv_sphere("Bed_Pillow_Left", (-1.10, 1.30, 0.82), (0.48, 0.27, 0.13), linen, target_collection=furniture),
        uv_sphere("Bed_Pillow_Right", (-0.31, 1.30, 0.82), (0.48, 0.27, 0.13), linen, target_collection=furniture),
    ):
        parent_keep_world(child, bed_root)
    for x in (-1.40, 0.00):
        for y in (-0.22, 1.65):
            leg = box(f"Bed_Leg_{x:.2f}_{y:.2f}", (x, y, 0.15), (0.10, 0.10, 0.30), wood_dark, bevel=0.012, target_collection=furniture)
            parent_keep_world(leg, bed_root)

    # Two detailed nightstands with drawer fronts and brass pulls.
    for side, x in (("Left", -1.87), ("Right", 0.47)):
        root = empty(f"Furniture_Nightstand_{side}", (x, 1.38, 0), furniture)
        body = box(f"Nightstand_{side}_Body", (x, 1.38, 0.43), (0.60, 0.54, 0.76), wood, bevel=0.04, target_collection=furniture)
        drawer = box(f"Nightstand_{side}_Drawer", (x, 1.085, 0.53), (0.47, 0.025, 0.25), wood_light, bevel=0.015, target_collection=furniture)
        pull = cylinder(f"Nightstand_{side}_Pull", (x, 1.045, 0.53), 0.034, 0.07, metal, rotation=(math.pi / 2, 0, 0), target_collection=furniture)
        foot1 = box(f"Nightstand_{side}_FootA", (x - 0.22, 1.38, 0.06), (0.07, 0.40, 0.12), wood_dark, bevel=0.01, target_collection=furniture)
        foot2 = box(f"Nightstand_{side}_FootB", (x + 0.22, 1.38, 0.06), (0.07, 0.40, 0.12), wood_dark, bevel=0.01, target_collection=furniture)
        for child in (body, drawer, pull, foot1, foot2):
            parent_keep_world(child, root)

    # Warm bedside lamp.
    lamp_root = empty("Prop_BedsideLamp", (0.47, 1.38, 0.81), details)
    for child in (
        cylinder("Lamp_Base", (0.47, 1.38, 0.85), 0.16, 0.06, metal, vertices=24, target_collection=details),
        cylinder("Lamp_Stem", (0.47, 1.38, 1.10), 0.025, 0.48, metal, vertices=16, target_collection=details),
    ):
        parent_keep_world(child, lamp_root)
    bpy.ops.mesh.primitive_cone_add(vertices=28, radius1=0.24, radius2=0.15, depth=0.35, location=(0.47, 1.38, 1.36))
    shade = bpy.context.object
    shade.name = "Lamp_Shade"
    assign(shade, lampshade)
    smooth(shade)
    move_to_collection(shade, details)
    parent_keep_world(shade, lamp_root)

    # Wardrobe in the rear-right corner.
    wardrobe_root = empty("Furniture_Wardrobe", (1.70, 1.58, 0), furniture)
    wardrobe_parts = [
        box("Wardrobe_Carcass", (1.70, 1.64, 1.12), (1.10, 0.66, 2.24), wood_dark, bevel=0.045, target_collection=furniture),
        box("Wardrobe_Door_Left", (1.43, 1.295, 1.15), (0.49, 0.045, 2.06), wood, bevel=0.025, target_collection=furniture),
        box("Wardrobe_Door_Right", (1.97, 1.295, 1.15), (0.49, 0.045, 2.06), wood, bevel=0.025, target_collection=furniture),
        cylinder("Wardrobe_Handle_Left", (1.63, 1.245, 1.13), 0.025, 0.32, metal, target_collection=furniture),
        cylinder("Wardrobe_Handle_Right", (1.77, 1.245, 1.13), 0.025, 0.32, metal, target_collection=furniture),
    ]
    for part in wardrobe_parts:
        parent_keep_world(part, wardrobe_root)

    # Desk and chair along the right wall, leaving a clear navigation lane.
    desk_root = empty("Furniture_Desk", (1.62, -0.72, 0), furniture)
    desk_parts = [
        box("Desk_Top", (1.62, -0.72, 0.78), (1.38, 0.64, 0.10), wood_light, bevel=0.035, target_collection=furniture),
        box("Desk_Leg_FL", (1.06, -0.98, 0.38), (0.09, 0.09, 0.76), black_metal, bevel=0.012, target_collection=furniture),
        box("Desk_Leg_FR", (2.18, -0.98, 0.38), (0.09, 0.09, 0.76), black_metal, bevel=0.012, target_collection=furniture),
        box("Desk_Leg_BL", (1.06, -0.46, 0.38), (0.09, 0.09, 0.76), black_metal, bevel=0.012, target_collection=furniture),
        box("Desk_Leg_BR", (2.18, -0.46, 0.38), (0.09, 0.09, 0.76), black_metal, bevel=0.012, target_collection=furniture),
        box("Desk_Drawer", (1.88, -1.05, 0.63), (0.48, 0.07, 0.20), wood, bevel=0.018, target_collection=furniture),
        cylinder("Desk_DrawerPull", (1.88, -1.10, 0.63), 0.025, 0.08, metal, rotation=(math.pi / 2, 0, 0), target_collection=furniture),
    ]
    for part in desk_parts:
        parent_keep_world(part, desk_root)

    chair_root = empty("Furniture_Chair", (1.60, -1.40, 0), furniture)
    chair_parts = [
        box("Chair_Seat", (1.60, -1.40, 0.48), (0.60, 0.55, 0.12), duvet, bevel=0.06, target_collection=furniture),
        box("Chair_Back", (1.60, -1.65, 0.92), (0.60, 0.10, 0.76), wood_dark, bevel=0.055, target_collection=furniture),
    ]
    for x in (1.36, 1.84):
        for y in (-1.61, -1.19):
            chair_parts.append(cylinder(f"Chair_Leg_{x:.2f}_{y:.2f}", (x, y, 0.24), 0.035, 0.48, black_metal, vertices=12, target_collection=furniture))
    for part in chair_parts:
        parent_keep_world(part, chair_root)

    # Rug with simple woven stripe geometry.
    rug = box("Rug_Main", (0.0, -0.45, 0.055), (2.35, 1.35, 0.05), rug_mat, bevel=0.055, bevel_segments=4, target_collection=details)
    rug["walkable"] = True
    for i in range(-4, 5):
        box(f"Rug_Stripe_{i+5:02d}", (i * 0.24, -0.45, 0.083), (0.055, 1.18, 0.012), accent if i % 2 else linen, bevel=0.008, target_collection=details)

    # Collectible 1: brass key on the desk, with pivot at its center.
    key_root = empty("PROP_Key_Decor", (1.38, -0.72, 0.86), props)
    key_root["interactable"] = True
    key_root["interaction"] = "collect"
    key_root["item_id"] = "bedroom_key"
    bpy.ops.mesh.primitive_torus_add(major_radius=0.075, minor_radius=0.016, major_segments=20, minor_segments=8, location=(1.29, -0.72, 0.86), rotation=(math.pi / 2, 0, 0))
    key_ring = bpy.context.object
    key_ring.name = "Key_Ring"
    assign(key_ring, metal)
    move_to_collection(key_ring, props)
    key_shaft = box("Key_Shaft", (1.43, -0.72, 0.86), (0.22, 0.032, 0.032), metal, bevel=0.008, target_collection=props)
    key_tooth_a = box("Key_Tooth_A", (1.52, -0.72, 0.825), (0.035, 0.032, 0.08), metal, bevel=0.006, target_collection=props)
    key_tooth_b = box("Key_Tooth_B", (1.57, -0.72, 0.84), (0.035, 0.032, 0.05), metal, bevel=0.006, target_collection=props)
    for child in (key_ring, key_shaft, key_tooth_a, key_tooth_b):
        parent_keep_world(child, key_root)

    # Collectible 2: framed photo on the left nightstand.
    photo_root = empty("PROP_PhotoFrame_Decor", (-1.87, 1.37, 0.88), props)
    photo_root["interactable"] = True
    photo_root["interaction"] = "inspect"
    photo_root["item_id"] = "family_photo"
    frame_parts = add_frame("PhotoFrame", (-1.87, 1.36, 1.08), (0.36, 0.46), 0.045, 0.055, wood_dark, props)
    photo_plane = box("PhotoFrame_Image", (-1.87, 1.387, 1.08), (0.27, 0.018, 0.35), photo, bevel=0.008, target_collection=props)
    photo_stand = box("PhotoFrame_Stand", (-1.87, 1.50, 0.93), (0.08, 0.24, 0.035), wood_dark, bevel=0.008, rotation=(math.radians(18), 0, 0), target_collection=props)
    for child in [*frame_parts, photo_plane, photo_stand]:
        parent_keep_world(child, photo_root)

    # Collectible 3: small journal at the foot of the bed.
    journal_root = empty("PROP_Journal_Decor", (-0.52, 0.02, 0.94), props)
    journal_root["interactable"] = True
    journal_root["interaction"] = "read"
    journal_root["item_id"] = "journal"
    cover = box("Journal_Cover", (-0.52, 0.02, 0.95), (0.34, 0.24, 0.055), accent, bevel=0.022, rotation=(0, 0, math.radians(-8)), target_collection=props)
    pages = box("Journal_Pages", (-0.52, 0.02, 0.958), (0.31, 0.215, 0.04), paper, bevel=0.016, rotation=(0, 0, math.radians(-8)), target_collection=props)
    band = box("Journal_Band", (-0.44, 0.01, 0.985), (0.035, 0.25, 0.018), wood_dark, bevel=0.006, rotation=(0, 0, math.radians(-8)), target_collection=props)
    for child in (cover, pages, band):
        parent_keep_world(child, journal_root)

    # A few low-cost details make the environment feel authored without bloating it.
    for idx, (x, color_mat) in enumerate(((-0.12, accent), (0.0, paper), (0.12, duvet)), 1):
        box(f"Desk_Book_{idx}", (1.93 + x, -0.68, 0.88 + idx * 0.025), (0.20, 0.30, 0.04), color_mat, bevel=0.012, rotation=(0, 0, math.radians(4 * idx)), target_collection=details)
    cylinder("Plant_Pot", (-2.15, -1.42, 0.20), 0.18, 0.36, accent, vertices=20, target_collection=details)
    for i, angle in enumerate((-0.6, -0.25, 0.12, 0.45, 0.72)):
        leaf = uv_sphere(f"Plant_Leaf_{i+1}", (-2.15 + math.sin(angle) * 0.18, -1.42, 0.52 + math.cos(angle) * 0.12), (0.07, 0.15, 0.28), duvet, segments=14, rings=8, target_collection=details)
        leaf.rotation_euler = (angle, 0, angle)

    # Align authored groups with the game's fixed furniture/collision layout.
    # Moving the named pivots moves every child while preserving local offsets.
    root_offsets = {
        "Furniture_Bed": (0.70, 1.58, 0.0),                 # runtime (0, -2.3)
        "Furniture_Nightstand_Left": (0.22, 1.37, 0.0),    # runtime (-1.65, -2.75)
        "Furniture_Nightstand_Right": (1.18, 1.37, 0.0),   # runtime (+1.65, -2.75)
        "Prop_BedsideLamp": (1.18, 1.37, 0.0),
        "Furniture_Wardrobe": (1.85, 1.07, 0.0),           # runtime (+3.55, -2.65)
        "Furniture_Desk": (-4.97, -0.93, 0.0),             # runtime (-3.35, +1.65)
        "Furniture_Chair": (-4.95, -1.05, 0.0),            # runtime (-3.35, +2.45)
        "PROP_Key_Decor": (-4.93, -0.93, 0.0),
        "PROP_PhotoFrame_Decor": (0.22, 1.38, 0.0),
        "PROP_Journal_Decor": (0.70, 1.58, 0.0),
    }
    for root_name, offset in root_offsets.items():
        root = bpy.data.objects[root_name]
        root.location += Vector(offset)

    # Desk-top decor was intentionally kept separate from the desk hierarchy.
    for obj in bpy.context.scene.objects:
        if obj.name.startswith("Desk_Book_"):
            obj.location += Vector((-4.97, -0.93, 0.0))

    # Explicit collision proxies. These are exported and identified by prefix.
    collision_box("COLLIDER_Floor", (0, 0, -0.03), (9.0, 8.0, 0.10), collisions, collision_mat)
    collision_box("COLLIDER_WallBack", (0, 4.05, 1.6), (9.1, 0.10, 3.2), collisions, collision_mat)
    collision_box("COLLIDER_WallLeft", (-4.55, 0, 1.6), (0.10, 8.0, 3.2), collisions, collision_mat)
    collision_box("COLLIDER_WallRight", (4.55, 0, 1.6), (0.10, 8.0, 3.2), collisions, collision_mat)
    collision_box("COLLIDER_Bed", (0.0, 2.30, 0.48), (1.66, 2.08, 0.96), collisions, collision_mat)
    collision_box("COLLIDER_NightstandLeft", (-1.65, 2.75, 0.43), (0.62, 0.56, 0.86), collisions, collision_mat)
    collision_box("COLLIDER_NightstandRight", (1.65, 2.75, 0.43), (0.62, 0.56, 0.86), collisions, collision_mat)
    collision_box("COLLIDER_Wardrobe", (3.55, 2.65, 1.12), (1.12, 0.70, 2.24), collisions, collision_mat)
    collision_box("COLLIDER_Desk", (-3.35, -1.65, 0.45), (1.40, 0.66, 0.90), collisions, collision_mat)
    collision_box("COLLIDER_Chair", (-3.35, -2.45, 0.50), (0.64, 0.60, 1.00), collisions, collision_mat)

    add_camera_and_lights(render_helpers)

    # Scene metadata used by the browser runtime and future rebuilds.
    scene = bpy.context.scene
    scene["asset_name"] = "Forge One Cozy Bedroom"
    scene["units"] = "meters"
    scene["room_dimensions"] = "9.0 x 8.0 x 3.2"
    scene["collision_prefix"] = "COLLIDER_"
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0

    # Make current transforms explicit and normals consistent.
    for obj in scene.objects:
        if obj.type != "MESH":
            continue
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode="OBJECT")
        obj.select_set(False)


def triangle_count() -> int:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    count = 0
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        mesh.calc_loop_triangles()
        count += len(mesh.loop_triangles)
        evaluated.to_mesh_clear()
    return count


def export_all() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(PREVIEW_PATH)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))

    # Produce an architectural cutaway preview. These visibility changes are
    # restored before export, so gameplay walls and colliders remain in GLB/FBX.
    collision_collection = bpy.data.collections.get("COLLISION")
    right_wall = bpy.data.objects.get("Wall_Right")
    if collision_collection:
        collision_collection.hide_render = True
    if right_wall:
        right_wall.hide_render = True
    bpy.ops.render.render(write_still=True)
    if collision_collection:
        collision_collection.hide_render = False
    if right_wall:
        right_wall.hide_render = False

    bpy.ops.export_scene.gltf(
        filepath=str(GLB_PATH),
        export_format="GLB",
        export_yup=True,
        export_apply=True,
        export_normals=True,
        export_materials="EXPORT",
        export_cameras=False,
        export_lights=False,
        export_extras=True,
    )
    bpy.ops.export_scene.fbx(
        filepath=str(FBX_PATH),
        use_selection=False,
        apply_unit_scale=True,
        apply_scale_options="FBX_SCALE_UNITS",
        axis_forward="-Z",
        axis_up="Y",
        use_mesh_modifiers=True,
        add_leaf_bones=False,
        bake_anim=False,
    )
    report = {
        "name": "Forge One Cozy Bedroom",
        "scale_meters": [9.0, 8.0, 3.2],
        "triangles_in_blend": triangle_count(),
        "mesh_objects": sum(1 for obj in bpy.context.scene.objects if obj.type == "MESH"),
        "materials": len(bpy.data.materials),
        "colliders": sorted(obj.name for obj in bpy.context.scene.objects if obj.name.startswith("COLLIDER_")),
        "interactables": sorted(obj.name for obj in bpy.context.scene.objects if bool(obj.get("interactable", False))),
        "files": {
            "blend": BLEND_PATH.name,
            "glb": GLB_PATH.name,
            "fbx": FBX_PATH.name,
            "preview": PREVIEW_PATH.name,
        },
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("FORGE_BEDROOM_REPORT=" + json.dumps(report))


if __name__ == "__main__":
    build_scene()
    export_all()
