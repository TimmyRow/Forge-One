# Room One — Art Direction

## North star

The bedroom should feel like a safe, lived-in room at 1:30 a.m.: cool moonlight makes the space readable, while one warm bedside lamp makes it inviting. The visual story is **quiet discovery**, not horror and not a glossy showroom. Objects can be imperfect, softened, and handmade, but the player must always understand where they can walk and what they can touch.

The frame belongs to the room. Keep the HUD low-chrome: one compact objective chip in the upper-left, one contextual interaction prompt near the lower edge, and deeper information behind pause or journal surfaces. Do not add a dashboard, a permanent toolbar, or large center-screen cards.

## Palette

| Role | Color | Use |
| --- | --- | --- |
| Night void | `#080D15` | Clear color and deepest recesses |
| Room shadow | `#151E2B` | Ambient shadow and UI backing |
| Moonlight | `#9DC7E8` | Window-side rim and navigation light |
| Candle | `#FFD6A0` | Practical lamp highlights |
| Honey | `#E6A45B` | Warm wood and reward warmth |
| Terracotta | `#C96D52` | Rug, small fabric accents |
| Chalk | `#FFF8EB` | Primary interface text |
| Mist | `#AEB8C4` | Secondary interface text |
| Interaction cyan | `#63D5FF` | Optional/usable object cues |
| Objective gold | `#FFD166` | Required collectible or exit cue |
| Completion green | `#8EE6A8` | Confirmed collection state |
| Warning coral | `#FF8B73` | Blocked/error state |
| Focus violet | `#D6A8FF` | Keyboard/gamepad focus ring |

Avoid pure white materials, full black shadows, and oversaturated RGB accents. They break the soft nighttime illusion and obscure material form.

## Materials

Use physically based values from `src/content/visualTheme.ts`. Important defaults:

- Walls: blue-grey `#7A8794`, roughness `0.94`, metalness `0`.
- Dark wood: `#4E3026`, roughness `0.68`, metalness `0`.
- Bedding: `#5D7180`, roughness `0.96`, metalness `0`.
- Rug: terracotta `#7E4C43`, roughness `1`, metalness `0`.
- Painted metal: `#39434D`, roughness `0.48`, metalness `0.58`.
- Lamp shade: `#E8C998`, roughness `0.78`, with restrained `#FFB45E` emission at `0.32`.
- Collectibles: warm ivory base, roughness `0.35`, faint gold emission. Emission is a cue, not a neon surface.

Generated Forge assets may arrive too pale or glossy. Preserve their textures, then correct material response before changing texture color: clamp non-metal roughness to roughly `0.55–1.0`, keep ordinary fabric/wood metalness at `0`, and reduce bright emission that flattens detail.

## Lighting, tone, and atmosphere

- Use ACES filmic tone mapping, sRGB output, exposure `1.12`, and soft shadows.
- Hemisphere light: cool `#7798B9` sky, warm-dark `#33251F` ground, intensity `0.62`.
- Moon key: `#A9D4F5`, intensity `1.7`, high and window-side. It should reveal furniture silhouettes without making the room look like daytime.
- Bedside point light: `#FFB867`, intensity `32 cd`, inverse-square decay, distance `5.2 m`.
- Doorway fill: `#F5D8AC`, intensity `5.5`, distance `4.5 m`. Use it as a subtle destination cue.
- Fog: exponential `#0D1522` at density `0.018`. Keep it low enough that the far wall remains readable.
- Keep important floor edges at least one tonal step brighter than the deepest shadow. A player should not confuse a walkable floor with a void.
- Shadow maps should favor the moon and bedside light. Decorative lights should not all cast shadows.

## Interaction and collectibles

Color is never the only signal:

- **Available:** cyan 2 px outline, `◇` prompt icon, one gentle breathe animation, and a soft neutral chime.
- **Required objective:** gold 3 px outline, `✦` icon, slow halo pulse, and a brighter two-note cue.
- **Collected:** green `✓`, brief scale-and-dissolve, then remove the halo so completed objects do not compete for attention.
- **Blocked:** coral broken/dashed outline, `×` icon, two short nudges, and a dry muted sound.

The collectible itself should remain recognizable without emission. Halos stop pulsing after the player looks directly at an object for a moment. Under `prefers-reduced-motion`, use static outlines and icons only.

## HUD and typography

- Display type: Trebuchet MS/Avenir Next fallback, medium weight, slightly open tracking. It feels friendly and authored without pretending to be a handwritten note.
- Body type: Inter/Segoe UI fallback.
- Primary text `#FFF8EB` on the strong night panel passes accessible contrast comfortably. Muted text uses `#BCC5CE`; do not dim essential instructions below that.
- UI panels use translucent navy, a quiet cool border, 10 px radius, and restrained blur. No glowing glass cards scattered around every edge.
- Buttons and gamepad targets are at least 44 by 44 px. Keyboard focus uses a violet ring separated from the control by a dark gap.
- Objective text uses a short verb: “Find the key,” not a paragraph. Controls disappear after the player demonstrates movement.
- Pause camera input whenever a menu takes pointer focus.

## Camera and motion tone

Camera movement is calm and grounded. Use light acceleration/deceleration, minimal head bob, and no idle camera drift. Rewards may use one clear scale or halo change; routine buttons should not bounce. Respect `prefers-reduced-motion` by disabling head bob, halo pulses, and blurred panel transitions.

## Forge asset review checklist

Before an asset enters the room:

1. Confirm scale against the player and door height.
2. Confirm the silhouette reads in cool moonlight and warm lamp light.
3. Correct roughness/metalness before repainting textures.
4. Check that pale texture gaps do not resemble interaction highlights.
5. Keep collision simpler than the visible mesh and verify walkable gaps.
6. Verify normals under the moon key and bedside point light.
7. Test collectible cues in grayscale and at reduced saturation.
8. Test UI and object outlines at 1280×720 and a narrow mobile viewport.

## Avoid

- Pure black rooms, grey-on-grey prompts, or bloom as the only visibility tool.
- Blue/orange grading so strong that every material becomes the same color.
- White spray-painted fallback textures on Forge models.
- Constant collectible bobbing, flicker, or pulsing around the whole room.
- Permanent crosshairs for a non-combat exploration game; show a small interaction reticle only when useful.
- Large quest panels over the live playfield.
