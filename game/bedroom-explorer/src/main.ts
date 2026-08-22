import * as THREE from "three";
import { InputController } from "./game/input/InputController";
import { collectItem, createGameState, loadGame, objectiveText, resetGame, saveGame, type CollectibleId } from "./game/simulation/state";
import { BedroomPhysics } from "./physics/BedroomPhysics";
import { createBedroomScene, type Interactable } from "./render/BedroomScene";
import { installVisualTheme } from "./content/visualTheme";
import "./ui/style.css";
import "./ui/polish.css";

installVisualTheme();

document.querySelector<HTMLDivElement>("#app")!.innerHTML = `
  <canvas id="gameCanvas" aria-label="Room One 3D game"></canvas>
  <div id="loading" class="loading">Preparing Room One…</div>
  <div class="hud">
    <div class="objective"><small>Current objective</small><strong id="objectiveText">Find three memory fragments.</strong></div>
    <div class="status"><span><small>Fragments</small><b id="fragmentCount">0 / 3</b></span><span><small>Time</small><b id="timer">0:00</b></span></div>
    <div id="reticle" class="reticle"></div><div id="prompt" class="prompt"><kbd>E</kbd><span></span></div>
    <div id="toast" class="toast"></div><div id="controlsHint" class="controls">WASD move · Mouse/drag look · Shift sprint · E interact · Esc pause</div>
    <div class="touch-controls" aria-label="Touch controls"><div class="touch-move"><button data-game-key="KeyW" aria-label="Move forward">▲</button><button data-game-key="KeyA" aria-label="Move left">◀</button><button data-game-key="KeyS" aria-label="Move backward">▼</button><button data-game-key="KeyD" aria-label="Move right">▶</button></div><button class="touch-action" data-game-key="KeyE">Interact</button></div>
  </div>
  <section id="menu" class="menu"><div class="menu-card"><div class="eyebrow">A Forge One game</div><h1>Room One</h1><p>Something happened here. Search the quiet bedroom, recover three fragments, and find the way out.</p><button id="startButton" class="primary">Enter the room</button><button id="continueButton" class="secondary" hidden>Continue saved game</button></div></section>
  <section id="pause" class="pause hidden"><div class="pause-card"><div class="eyebrow">Paused</div><h2>Room One</h2><p class="pause-help">WASD move · Mouse/drag look · Shift sprint · E interact</p><button id="resumeButton" class="primary">Resume</button><button id="restartButton" class="secondary">Restart room</button></div></section>
  <section id="complete" class="complete hidden"><div class="complete-card"><div class="eyebrow">Room cleared</div><h2>The door opens.</h2><p>You recovered every fragment and made it out of Room One.</p><button id="playAgainButton" class="primary">Play again</button></div></section>`;

const canvas = document.querySelector<HTMLCanvasElement>("#gameCanvas")!;
const loading = document.querySelector<HTMLElement>("#loading")!;
const menu = document.querySelector<HTMLElement>("#menu")!;
const pause = document.querySelector<HTMLElement>("#pause")!;
const complete = document.querySelector<HTMLElement>("#complete")!;
const objectiveElement = document.querySelector<HTMLElement>("#objectiveText")!;
const fragmentCount = document.querySelector<HTMLElement>("#fragmentCount")!;
const timerElement = document.querySelector<HTMLElement>("#timer")!;
const prompt = document.querySelector<HTMLElement>("#prompt")!;
const promptText = prompt.querySelector("span")!;
const reticle = document.querySelector<HTMLElement>("#reticle")!;
const controlsHint = document.querySelector<HTMLElement>("#controlsHint")!;
const toast = document.querySelector<HTMLElement>("#toast")!;
const state = createGameState();
const hasSave = loadGame(state);
document.querySelector<HTMLButtonElement>("#continueButton")!.hidden = !hasSave;

const world = await createBedroomScene(canvas);
const physics = await BedroomPhysics.create(world.collisionBoxes);
const input = new InputController(canvas);
loading.classList.add("hidden");
const { scene, camera, renderer, interactables, door } = world;
const raycaster = new THREE.Raycaster();
raycaster.far = 2.15;
let yaw = 0;
let pitch = -0.05;
let nearby: Interactable | null = null;
let toastTimer = 0;
let doorOpen = 0;
let lastTime = performance.now();
let controlsHintTimer = 0;

for (const item of interactables) {
  if (item.kind !== "door" && state.collected.has(item.kind as CollectibleId)) {
    item.collected = true;
    item.object.visible = false;
  }
}

function updateHud(): void {
  objectiveElement.textContent = objectiveText(state);
  fragmentCount.textContent = `${state.collected.size} / 3`;
  const seconds = Math.floor(state.elapsedSeconds);
  timerElement.textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function showToast(message: string): void {
  toast.textContent = message;
  toast.classList.add("show");
  toastTimer = 2.7;
}

function playTone(frequency: number, duration = 0.12): void {
  const audio = new AudioContext();
  const oscillator = audio.createOscillator();
  const gain = audio.createGain();
  oscillator.frequency.value = frequency;
  oscillator.type = "sine";
  gain.gain.setValueAtTime(0.05, audio.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + duration);
  oscillator.connect(gain).connect(audio.destination);
  oscillator.start(); oscillator.stop(audio.currentTime + duration);
  oscillator.addEventListener("ended", () => void audio.close());
}

function beginPlay(): void {
  state.phase = "playing";
  menu.classList.add("hidden"); pause.classList.add("hidden"); complete.classList.add("hidden");
  input.requestPointerLock();
}

function restart(): void {
  resetGame(state);
  physics.reset();
  yaw = 0; pitch = -0.05;
  controlsHintTimer = 0;
  controlsHint.classList.remove("hidden-hint");
  doorOpen = 0; door.rotation.y = 0;
  for (const item of interactables) { item.collected = false; item.object.visible = true; }
  updateHud(); beginPlay();
}

document.querySelector<HTMLButtonElement>("#startButton")!.addEventListener("click", restart);
document.querySelector<HTMLButtonElement>("#continueButton")!.addEventListener("click", beginPlay);
document.querySelector<HTMLButtonElement>("#resumeButton")!.addEventListener("click", beginPlay);
document.querySelector<HTMLButtonElement>("#restartButton")!.addEventListener("click", restart);
document.querySelector<HTMLButtonElement>("#playAgainButton")!.addEventListener("click", restart);
canvas.addEventListener("click", () => { if (state.phase === "playing") input.requestPointerLock(); });
window.addEventListener("keydown", (event) => {
  if (event.code !== "Escape") return;
  if (state.phase === "playing") {
    state.phase = "paused";
    pause.classList.remove("hidden");
    if (document.pointerLockElement === canvas) document.exitPointerLock();
    saveGame(state);
  } else if (state.phase === "paused") {
    beginPlay();
  }
});
document.addEventListener("pointerlockchange", () => {
  if (document.pointerLockElement !== canvas && state.phase === "playing") {
    state.phase = "paused"; pause.classList.remove("hidden"); saveGame(state);
  }
});

function interactionTarget(): Interactable | null {
  raycaster.setFromCamera(new THREE.Vector2(0, 0), camera);
  const candidates = interactables.filter((item) => !item.collected && item.object.visible);
  const hits = raycaster.intersectObjects(candidates.map((item) => item.object), true);
  const directHit = hits.length ? candidates.find((item) => {
    let object: THREE.Object3D | null = hits[0].object;
    while (object) { if (object === item.object) return true; object = object.parent; }
    return false;
  }) : undefined;
  if (directHit) return directHit;

  // A small proximity cone keeps interaction friendly on touch screens and in
  // embedded browsers without turning the room into an automatic pickup zone.
  const forward = camera.getWorldDirection(new THREE.Vector3());
  let best: { item: Interactable; score: number } | null = null;
  for (const item of candidates) {
    const center = new THREE.Box3().setFromObject(item.object).getCenter(new THREE.Vector3());
    const toTarget = center.sub(camera.position);
    const distance = toTarget.length();
    if (distance > 2.35 || distance < 0.05) continue;
    const alignment = forward.dot(toTarget.normalize());
    if (alignment < 0.42) continue;
    const score = alignment * 2 - distance * 0.18;
    if (!best || score > best.score) best = { item, score };
  }
  return best?.item ?? null;
}

function interact(item: Interactable): void {
  if (item.kind === "door") {
    if (!state.doorUnlocked) { showToast(`The door is locked. ${3 - state.collected.size} fragment${state.collected.size === 2 ? "" : "s"} remain.`); playTone(110); return; }
    doorOpen = 1;
    physics.unlockDoor();
    state.phase = "complete";
    updateHud();
    document.exitPointerLock();
    setTimeout(() => complete.classList.remove("hidden"), 700);
    playTone(523, 0.5);
    return;
  }
  if (collectItem(state, item.kind)) {
    item.collected = true; item.object.visible = false;
    const labels: Record<CollectibleId, string> = { key: "The key is warmer than it should be.", photo: "A familiar room, before it went quiet.", journal: "One sentence is underlined: remember the door." };
    showToast(labels[item.kind]); playTone(330 + state.collected.size * 90, 0.24); updateHud();
  }
}

function frame(now: number): void {
  const dt = Math.min((now - lastTime) / 1000, 0.05);
  lastTime = now;
  if (state.phase === "playing") {
    state.elapsedSeconds += dt;
    controlsHintTimer += dt;
    if (controlsHintTimer > 6) controlsHint.classList.add("hidden-hint");
    const look = input.consumeLook();
    yaw -= look.x * 0.0022;
    pitch = THREE.MathUtils.clamp(pitch - look.y * 0.0018, -1.28, 1.28);
    const movement = input.movement;
    const forward = new THREE.Vector3(-Math.sin(yaw), 0, -Math.cos(yaw));
    const right = new THREE.Vector3(-forward.z, 0, forward.x);
    const direction = forward.multiplyScalar(movement.forward).add(right.multiplyScalar(movement.right));
    if (direction.lengthSq() > 0) direction.normalize();
    const eye = physics.update(dt, direction, movement.sprint);
    camera.position.copy(eye);
    camera.rotation.set(pitch, yaw, 0, "YXZ");
    nearby = interactionTarget();
    prompt.classList.toggle("visible", Boolean(nearby));
    reticle.classList.toggle("active", Boolean(nearby));
    if (nearby) promptText.textContent = nearby.label;
    if (nearby && input.consumeInteract()) interact(nearby);
    updateHud();
  }
  if (toastTimer > 0) { toastTimer -= dt; if (toastTimer <= 0) toast.classList.remove("show"); }
  for (const item of interactables) {
    if (item.kind !== "door" && !item.collected) {
      item.object.rotation.y += dt * 0.9;
      item.object.position.y += Math.sin(now * 0.002 + item.object.id) * dt * 0.025;
    }
  }
  door.rotation.y = THREE.MathUtils.lerp(door.rotation.y, -Math.PI * 0.52 * doorOpen, 1 - Math.exp(-dt * 5));
  renderer.render(scene, camera);
}

renderer.setAnimationLoop(frame);
window.addEventListener("resize", () => {
  camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.8)); renderer.setSize(innerWidth, innerHeight);
});
window.addEventListener("beforeunload", () => saveGame(state));
updateHud();
