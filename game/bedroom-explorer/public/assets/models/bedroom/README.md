# Cozy Bedroom Asset

Runtime-ready bedroom authored for Forge One Bedroom Explorer.

## Coordinate contract

- glTF/Three.js units: meters, Y-up
- Room footprint: 9 m wide (X) × 8 m deep (Z)
- Floor: Y = 0
- Back wall: Z = -4
- Open front/entry: Z = +4
- Player spawn remains clear around `(0, 1, 2.8)`

Furniture is aligned with the game layout:

| Node | Runtime X/Z |
| --- | --- |
| `Furniture_Bed` | `0, -2.3` |
| `Furniture_Nightstand_Left` | `-1.65, -2.75` |
| `Furniture_Nightstand_Right` | `1.65, -2.75` |
| `Furniture_Wardrobe` | `3.55, -2.65` |
| `Furniture_Desk` | `-3.35, 1.65` |

The front-center `DoorFrame` contains no door slab. The game owns the exit-door
visual and interaction.

## Gameplay nodes

- Collision meshes use the `COLLIDER_` prefix and the `collision=true` extra.
- Decorative interaction targets are `PROP_Key_Decor`,
  `PROP_PhotoFrame_Decor`, and `PROP_Journal_Decor`.
- The browser runtime can hide every `COLLIDER_` mesh after deriving physics
  shapes from its world bounds.

## Rebuild and validate

```powershell
& 'C:\Program Files\Blender Foundation\Blender 4.2\blender.exe' --background --python tools\build_bedroom_scene.py
& 'C:\Program Files\Blender Foundation\Blender 4.2\blender.exe' --background --python tools\validate_bedroom_exports.py
```

The GLB is intentionally uncompressed. At under 0.5 MB, requiring a Draco or
Meshopt decoder would add integration complexity without a meaningful first-load
benefit. All materials are reusable PBR materials and require no external files.
