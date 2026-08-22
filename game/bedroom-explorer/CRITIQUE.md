# Room One independent final playtest

Date: 2026-08-22

Build reviewed: latest local build at `http://127.0.0.1:4175/games/room-one/`
Verdict: **CONDITIONAL NO-SHIP — no known P0/P1 product defect remains, but the release QA gate is not cleared until one human-controlled 3/3/door run succeeds.**

The new build is a large improvement over the first review. It boots at the intended base path, presents a strong title screen, loads the authored bedroom GLB, supports drag-look when pointer lock is unavailable, encloses the room, gives the exit physical collision, makes pickups recognizable, and cleans up the HUD/mobile layout. I successfully collected the photograph through the real UI, resumed the saved 1/3 state after reload, aimed at the locked bedroom door and received its contextual prompt, and exercised desktop look/pause/resize behavior.

I did not obtain a valid 3/3 completion run. The in-app browser controller emits key presses but cannot hold WASD long enough for a dependable first-person route, so the last two pickups/door-open path could not be completed by automation. This is an automation limitation, not evidence that keyboard movement is broken for a human player. It still prevents an evidence-based ship verdict.

## Evidence captured

- `qa/retest-title-desktop.png` — latest desktop title composition.
- `qa/retest-gameplay-start.png` — latest enclosed gameplay frame and low-chrome HUD.
- `qa/retest-drag-look.png` — camera rotation through the embedded mouse drag-look fallback.
- `qa/retest-movement.png` — navigated gameplay view.
- `qa/retest-photo-collected.png` — real UI run after the photograph advanced progress to 1/3.
- `qa/retest-key-collected.png` — close inspection of the new readable key mesh/marker; despite the legacy filename, this frame still shows 1/3 and does not prove key collection.
- `qa/pause-desktop.png`, `qa/title-mobile.png`, and `qa/gameplay-mobile.png` — pause and narrow-layout checks from the same review series.

## Release-gate finding

### QA gate — complete the 3/3/door loop once with human-held WASD

**Observed:** Photograph collection and save/continue worked. The key and journal are now visually discoverable, and the locked door exposes `Try the bedroom door` when aimed at. The automation surface could not sustain directional keys long enough to finish the remaining route, so I did not see 3/3, the unlocked-door transition, the completion panel, or Play Again after a completed run.

**Required final check:**

1. In a normal browser, start a fresh room.
2. Collect the photograph, key, and journal using mouse + held WASD.
3. Confirm each pickup advances exactly once and the third changes the objective to the door.
4. Confirm the closed door blocks passage before unlock.
5. Open the door, walk through the released collider, and see the completion overlay immediately after the authored delay.
6. Choose **Play again** and confirm position, yaw, pitch, collectibles, timer, door mesh, and door collider all reset.
7. Reload a partial run once and confirm Continue restores collection state without hiding an uncollected pickup.

**Likely owner:** QA/gameplay. This is a verification task, not a request for another architectural change.

## Verified fixes from the first review

- **Embedded input:** Mouse drag-look now rotates the view when pointer lock is denied. The advertised fallback is real.
- **Exit integrity:** Source now creates front-wall segments and a locked-door collider, and removes the door collider only on successful unlock. The contextual locked-door target was visible in-browser.
- **Architecture:** A runtime ceiling now closes the room; the previous open-set void is gone.
- **Lighting:** Moon/lamp levels and shadow bias were reduced. The room is more readable and less blown out, although the contrast remains stylized.
- **Collectible discovery:** The key and journal now have recognizable meshes plus floating diamond markers. They are obvious from the starting frame rather than tiny anonymous boxes.
- **Interaction forgiveness:** The latest source adds a 2.35 m proximity-cone fallback after the direct mesh raycast, addressing the thin-key/ring pixel-hunt found during the retest. The build passes; this final small change was source-verified but not replayed after rebuild.
- **HUD:** The reticle is contextual, the control sentence fades, and the pause screen repeats controls.
- **Mobile layout:** Narrow status moved above the touch-control area, eliminating the earlier bottom-right overlap by CSS inspection and narrow screenshots. True coarse-pointer input was not available in this browser harness.
- **Camera/state:** Restart now resets yaw and pitch, and completion updates the HUD before the overlay.
- **Physics pipeline:** Authored GLB collider boxes now feed Rapier rather than relying only on the old duplicate table.
- **Runtime warning:** Rapier was upgraded and the reviewed production build passes.

## Remaining non-blocking polish

### P2 — Gameplay lighting still has abrupt authored contrast

The ceiling is very dark and the warm lamp region remains much brighter than the wardrobe/left-wall zones. It is usable and substantially improved, but a softer fill or gentler tone mapping would better match the title image and reveal furniture materials.

**Likely owner:** Lighting/color.

### P3 — Final mobile result needs one real coarse-pointer device check

The responsive layout is sane and the overlap fix is present, but this browser harness could not emulate `pointer: coarse`; touch movement, touch-look, and the Interact button therefore remain source-reviewed rather than fully exercised.

**Likely owner:** QA/frontend.

## What passed

- Latest production TypeScript/Vite build passes.
- Correct hosted base route is `/games/room-one/`.
- The real bedroom GLB loads without a visible asset failure.
- Title hierarchy and desktop/narrow compositions are strong.
- Embedded drag-look visibly changes camera yaw/pitch.
- Photograph interaction advances the real HUD to 1/3.
- Partial progress survives reload and **Continue saved game**.
- The locked door exposes a contextual interaction prompt.
- Pause/Resume UI is clear and includes control rediscovery.
- Desktop-to-narrow resize did not crash WebGL.
- The room now has a ceiling, physical front boundary, and recognizable collectible silhouettes/markers.

## Final recommendation

Do not call the demo fully ship-verified yet. Run the short seven-step human-input gate above on the exact production deployment. If that passes without a stuck pickup, collider mismatch, or stale completion state, I would change the verdict to **SHIP WITH P2 POLISH BACKLOG**; the earlier release-blocking defects have otherwise been addressed.
