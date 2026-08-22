"""Reload and validate the bedroom GLB and FBX in clean Blender scenes."""

from __future__ import annotations

import json
from pathlib import Path

import bpy


HERE = Path(__file__).resolve().parent
ASSET_DIR = HERE.parent / "public" / "assets" / "models" / "bedroom"
GLB_PATH = ASSET_DIR / "cozy_bedroom.glb"
FBX_PATH = ASSET_DIR / "cozy_bedroom.fbx"
REPORT_PATH = ASSET_DIR / "cozy_bedroom_validation.json"


def clear() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def scene_report(label: str) -> dict:
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    empties = [obj for obj in bpy.context.scene.objects if obj.type == "EMPTY"]
    triangles = 0
    invalid_meshes: list[str] = []
    degenerate_faces = 0
    for obj in meshes:
        mesh = obj.data
        mesh.calc_loop_triangles()
        triangles += len(mesh.loop_triangles)
        if mesh.validate(clean_customdata=False):
            invalid_meshes.append(obj.name)
        degenerate_faces += sum(1 for poly in mesh.polygons if poly.area <= 1e-10)

    collider_names = sorted(obj.name for obj in bpy.context.scene.objects if obj.name.startswith("COLLIDER_"))
    interactables = sorted(
        obj.name
        for obj in bpy.context.scene.objects
        if bool(obj.get("interactable", False)) or obj.name.startswith("PROP_")
    )
    return {
        "label": label,
        "mesh_objects": len(meshes),
        "empty_objects": len(empties),
        "materials": len({slot.material.name for obj in meshes for slot in obj.material_slots if slot.material}),
        "triangles": triangles,
        "invalid_meshes": invalid_meshes,
        "degenerate_faces": degenerate_faces,
        "colliders": collider_names,
        "interactables": interactables,
        "required_nodes_present": all(
            bpy.data.objects.get(name) is not None
            for name in (
                "Room_FloorSlab",
                "Wall_Back",
                "Furniture_Bed",
                "Furniture_Wardrobe",
                "Furniture_Desk",
                "Furniture_Chair",
                "PROP_Key_Decor",
                "PROP_PhotoFrame_Decor",
                "PROP_Journal_Decor",
                "DoorFrame",
                "COLLIDER_Floor",
            )
        ),
    }


def main() -> None:
    clear()
    bpy.ops.import_scene.gltf(filepath=str(GLB_PATH))
    glb_report = scene_report("GLB reload")

    clear()
    bpy.ops.import_scene.fbx(filepath=str(FBX_PATH), automatic_bone_orientation=True)
    fbx_report = scene_report("FBX reload")

    report = {
        "glb": glb_report,
        "fbx": fbx_report,
        "file_sizes_bytes": {
            "blend": (ASSET_DIR / "cozy_bedroom.blend").stat().st_size,
            "glb": GLB_PATH.stat().st_size,
            "fbx": FBX_PATH.stat().st_size,
            "preview": (ASSET_DIR / "cozy_bedroom_preview.png").stat().st_size,
        },
        "passed": (
            glb_report["required_nodes_present"]
            and len(glb_report["colliders"]) >= 10
            and len(glb_report["interactables"]) >= 3
            and not glb_report["invalid_meshes"]
            and glb_report["degenerate_faces"] == 0
            and not fbx_report["invalid_meshes"]
            and fbx_report["degenerate_faces"] == 0
        ),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("FORGE_BEDROOM_VALIDATION=" + json.dumps(report))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
