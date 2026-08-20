import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import "./style.css";

document.querySelector("#app").innerHTML = `
  <header class="topbar">
    <div class="brand"><span class="brand-mark">F1</span><div><strong>Forge One</strong><small>Local image → 3D</small></div></div>
    <div class="top-actions"><button id="libraryButton" class="tool">My library</button><button id="profileButton" class="profile-button">Create profile</button><div id="gpuPill" class="gpu-pill"><span></span> Checking CUDA…</div></div>
  </header>
  <main class="shell">
    <aside class="panel controls-panel">
      <div class="eyebrow">SOURCE IMAGE</div>
      <label id="dropZone" class="drop-zone" tabindex="0">
        <input id="fileInput" type="file" accept="image/png,image/jpeg,image/webp" />
        <img id="imagePreview" alt="Selected object" />
        <div id="dropPrompt" class="drop-prompt">
          <div class="upload-icon">↑</div>
          <strong>Drop one object image</strong>
          <span>PNG, JPG, or WebP · up to 25 MB</span>
        </div>
      </label>
      <div class="mode-block">
        <div class="eyebrow">GENERATION MODE</div>
        <button id="fastMode" type="button" class="mode-card selected"><span class="mode-icon">⚡</span><div><strong>Fast</strong><small>TripoSR · refined 256³ detail for 8 GB VRAM</small></div><span class="check">✓</span></button>
        <button id="qualityMode" type="button" class="mode-card"><span class="mode-icon">◇</span><div><strong>Quality</strong><small>TripoSG · colored GLB · first run downloads weights</small></div><span class="check">✓</span></button></div>
      </div>
      <button id="generateButton" class="primary" disabled>Generate real 3D</button>
      <button id="cancelButton" class="secondary hidden">Cancel safely</button>
      <section id="statusCard" class="status-card hidden" aria-live="polite">
        <div class="status-heading"><span id="statusLabel">Preparing</span><span id="statusPercent">0%</span></div>
        <div class="progress-track"><div id="progressBar"></div></div>
        <p id="statusMessage"></p>
      </section>
      <div id="errorCard" class="error-card hidden"></div>
      <p id="saveHint" class="privacy">Sign in to a profile before generating to save models and resume them on another device.</p>
    </aside>
    <section class="viewer-panel">
      <div class="viewer-toolbar">
        <div><span class="eyebrow">3D INSPECTOR</span><strong id="viewerTitle">Waiting for an image</strong></div>
        <div class="tool-actions">
          <button id="gridButton" class="tool active">Grid</button>
          <button id="wireButton" class="tool" disabled>Wireframe</button>
          <button id="resetButton" class="tool" disabled>Reset view</button><button id="remakeButton" class="tool" disabled title="Make a new reconstruction from this image">Remake</button>
        </div>
      </div>
      <div id="viewer">
        <canvas id="sceneCanvas"></canvas>
        <div id="emptyState" class="empty-state"><div class="orb"><span></span></div><h2>Your generated mesh appears here</h2><p>Upload a clear image of one object to begin.</p></div>
        <div id="loadingModel" class="model-loading hidden">Loading validated GLB…</div>
      </div>
      <footer class="result-bar">
        <div class="metric"><span>Vertices</span><strong id="vertices">—</strong></div>
        <div class="metric"><span>Triangles</span><strong id="triangles">—</strong></div>
        <div class="metric"><span>GLB size</span><strong id="fileSize">—</strong></div>
        <div class="metric"><span>Generation</span><strong id="elapsed">—</strong></div>
        <a id="downloadButton" class="download disabled" aria-disabled="true">Download GLB</a>
      </footer>
    </section>
  </main>
  <section id="profileDialog" class="overlay hidden" aria-modal="true" role="dialog">
    <form id="profileForm" class="dialog-card"><button id="profileClose" type="button" class="dialog-close">×</button><div class="eyebrow">YOUR PROFILE</div><h2 id="profileHeading">Save your work</h2><p>Create a profile, then sign in on any device using this public link to open your saved models.</p><label>Profile name<input id="profileName" maxlength="40" required autocomplete="username" /></label><label>Password<input id="profilePassword" type="password" minlength="8" required autocomplete="current-password" /></label><div class="dialog-actions"><button id="loginButton" type="button" class="secondary">Sign in</button><button class="primary" type="submit">Create profile</button></div><p id="profileError" class="dialog-error"></p><button id="logoutButton" type="button" class="text-button hidden">Sign out</button></form>
  </section>
  <aside id="libraryDrawer" class="library-drawer hidden"><div class="drawer-heading"><div><div class="eyebrow">SAVED MODELS</div><strong id="libraryTitle">My library</strong></div><button id="libraryClose" class="tool">Close</button></div><p id="libraryEmpty" class="library-empty">Sign in to save models and open them from another device.</p><div id="libraryList" class="library-list"></div></aside>
`;

const elements = Object.fromEntries(
  ["gpuPill", "libraryButton", "profileButton", "dropZone", "fileInput", "imagePreview", "dropPrompt", "fastMode", "qualityMode", "generateButton", "cancelButton", "statusCard", "statusLabel", "statusPercent", "progressBar", "statusMessage", "errorCard", "saveHint", "viewerTitle", "gridButton", "wireButton", "resetButton", "remakeButton", "viewer", "sceneCanvas", "emptyState", "loadingModel", "vertices", "triangles", "fileSize", "elapsed", "downloadButton", "profileDialog", "profileForm", "profileClose", "profileHeading", "profileName", "profilePassword", "loginButton", "logoutButton", "profileError", "libraryDrawer", "libraryButton", "libraryClose", "libraryTitle", "libraryEmpty", "libraryList"].map((id) => [id, document.getElementById(id)])
);

let selectedFile = null;
let activeGeneration = null;
let currentObject = null;
let pollTimer = null;
let selectedMode = "Fast";
let profile = null;
let remakeGenerationId = null;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x080b12);
const camera = new THREE.PerspectiveCamera(42, 1, 0.01, 100);
camera.position.set(3.2, 2.3, 3.6);
const renderer = new THREE.WebGLRenderer({ canvas: elements.sceneCanvas, antialias: true, alpha: false });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.12;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.minDistance = 0.35;
controls.maxDistance = 14;

scene.add(new THREE.HemisphereLight(0xc9dcff, 0x18131d, 2.3));
const keyLight = new THREE.DirectionalLight(0xffffff, 4.5);
keyLight.position.set(4, 6, 3);
keyLight.castShadow = true;
scene.add(keyLight);
const rimLight = new THREE.DirectionalLight(0x6d8cff, 2.4);
rimLight.position.set(-4, 2, -4);
scene.add(rimLight);
const grid = new THREE.GridHelper(12, 24, 0x314060, 0x182135);
grid.position.y = -1.05;
grid.material.opacity = 0.55;
grid.material.transparent = true;
scene.add(grid);

function resizeViewer() {
  const width = elements.viewer.clientWidth;
  const height = elements.viewer.clientHeight;
  renderer.setSize(width, height, false);
  camera.aspect = width / Math.max(height, 1);
  camera.updateProjectionMatrix();
}
new ResizeObserver(resizeViewer).observe(elements.viewer);

function animate() {
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(animate);
}
animate();

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return "—";
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function showError(message) {
  elements.errorCard.textContent = message;
  elements.errorCard.classList.remove("hidden");
}

function clearError() {
  elements.errorCard.classList.add("hidden");
  elements.errorCard.textContent = "";
}

async function api(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { message = (await response.json()).detail || message; } catch {}
    throw new Error(message);
  }
  return response.json();
}

async function detectSystem() {
  try {
    const system = await api("/api/system");
    if (system.cuda_available) {
      elements.gpuPill.innerHTML = `<span></span>${system.gpu_name} · ${formatBytes(system.total_vram_bytes)}`;
      elements.gpuPill.classList.add("ready");
    } else {
      elements.gpuPill.textContent = "CUDA unavailable";
      elements.gpuPill.classList.add("error");
      showError(system.diagnostic);
    }
  } catch (error) {
    elements.gpuPill.textContent = "Backend unavailable";
    showError("The local backend is not responding. Launch the app with run.bat.");
  }
}

function setProfile(nextProfile) {
  profile = nextProfile;
  elements.profileButton.textContent = profile ? profile.display_name : "Create profile";
  elements.saveHint.textContent = profile
    ? `Signed in as ${profile.display_name}. Completed models save automatically to this profile.`
    : "Sign in to a profile before generating to save models and resume them on another device.";
  elements.libraryTitle.textContent = profile ? `${profile.display_name}'s library` : "My library";
  elements.logoutButton.classList.toggle("hidden", !profile);
}

function openProfile() {
  elements.profileError.textContent = "";
  elements.profileHeading.textContent = profile ? `Signed in as ${profile.display_name}` : "Save your work";
  elements.profileDialog.classList.remove("hidden");
}

async function loadProfile() {
  try { setProfile((await api("/api/profile")).profile); } catch { setProfile(null); }
}

async function submitProfile(endpoint) {
  const form = new FormData();
  form.append("display_name", elements.profileName.value);
  form.append("password", elements.profilePassword.value);
  try {
    const result = await api(endpoint, { method: "POST", body: form });
    setProfile(result.profile);
    elements.profilePassword.value = "";
    elements.profileDialog.classList.add("hidden");
    await loadLibrary();
  } catch (error) { elements.profileError.textContent = error.message; }
}

async function loadLibrary() {
  if (!profile) {
    elements.libraryEmpty.textContent = "Sign in to save models and open them from another device.";
    elements.libraryEmpty.classList.remove("hidden");
    elements.libraryList.replaceChildren();
    return;
  }
  try {
    const { models } = await api("/api/library");
    elements.libraryList.replaceChildren(...models.map((entry) => {
      const item = document.createElement("div");
      item.className = "library-item";
      const open = document.createElement("button");
      open.className = "library-open";
      open.textContent = entry.title;
      open.addEventListener("click", async () => {
        await loadModel({ ...entry, updated_at: entry.created_at, vertices: NaN, triangles: NaN, file_size: NaN, elapsed_seconds: NaN });
        elements.vertices.textContent = "—"; elements.triangles.textContent = "—"; elements.fileSize.textContent = "Saved"; elements.elapsed.textContent = "—";
      });
      const download = document.createElement("a");
      download.href = entry.download_url; download.textContent = "Download"; download.className = "library-download";
      item.append(open, document.createElement("small"), download);
      item.querySelector("small").textContent = `${entry.backend} · ${new Date(entry.created_at).toLocaleDateString()}`;
      return item;
    }));
    elements.libraryEmpty.textContent = models.length ? "" : "No saved models yet. Generate while signed in and it will appear here.";
    elements.libraryEmpty.classList.toggle("hidden", Boolean(models.length));
  } catch (error) { elements.libraryEmpty.textContent = error.message; elements.libraryEmpty.classList.remove("hidden"); }
}

elements.profileButton.addEventListener("click", openProfile);
elements.profileClose.addEventListener("click", () => elements.profileDialog.classList.add("hidden"));
elements.profileForm.addEventListener("submit", (event) => { event.preventDefault(); submitProfile("/api/profiles"); });
elements.loginButton.addEventListener("click", () => submitProfile("/api/profiles/login"));
elements.logoutButton.addEventListener("click", async () => { await api("/api/profiles/logout", { method: "POST" }); setProfile(null); elements.profileDialog.classList.add("hidden"); await loadLibrary(); });
elements.libraryButton.addEventListener("click", async () => { elements.libraryDrawer.classList.remove("hidden"); await loadLibrary(); });
elements.libraryClose.addEventListener("click", () => elements.libraryDrawer.classList.add("hidden"));

function selectFile(file) {
  clearError();
  if (!file || !["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
    showError("Choose a PNG, JPG/JPEG, or WebP image.");
    return;
  }
  selectedFile = file;
  elements.imagePreview.src = URL.createObjectURL(file);
  elements.imagePreview.classList.add("visible");
  elements.dropPrompt.classList.add("hidden");
  elements.generateButton.disabled = false;
  elements.generateButton.textContent = currentObject ? "Regenerate 3D" : "Generate real 3D";
}

function selectMode(mode) {
  selectedMode = mode;
  elements.fastMode.classList.toggle("selected", mode === "Fast");
  elements.qualityMode.classList.toggle("selected", mode === "Quality");
  clearError();
  if (mode === "Quality") {
    elements.viewerTitle.textContent = "Quality · TripoSG";
  }
}

elements.fastMode.addEventListener("click", () => selectMode("Fast"));
elements.qualityMode.addEventListener("click", () => selectMode("Quality"));

elements.fileInput.addEventListener("change", () => selectFile(elements.fileInput.files[0]));
elements.dropZone.addEventListener("dragover", (event) => { event.preventDefault(); elements.dropZone.classList.add("dragging"); });
elements.dropZone.addEventListener("dragleave", () => elements.dropZone.classList.remove("dragging"));
elements.dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  elements.dropZone.classList.remove("dragging");
  selectFile(event.dataTransfer.files[0]);
});
elements.dropZone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") elements.fileInput.click();
});

function updateStatus(job) {
  elements.statusCard.classList.remove("hidden");
  elements.statusLabel.textContent = job.status === "complete" ? "Complete" : job.status === "failed" ? "Failed" : `${job.mode} · ${job.backend}`;
  elements.statusPercent.textContent = `${job.progress || 0}%`;
  elements.progressBar.style.width = `${job.progress || 0}%`;
  elements.statusMessage.textContent = job.message;
}

async function startGeneration() {
  if (!selectedFile) return;
  clearError();
  elements.generateButton.disabled = true;
  elements.cancelButton.classList.remove("hidden");
  elements.statusCard.classList.remove("hidden");
  elements.viewerTitle.textContent = `Generating with ${selectedMode === "Quality" ? "TripoSG" : "TripoSR"}`;
  const form = new FormData();
  form.append("image", selectedFile);
  form.append("mode", selectedMode);
  try {
    activeGeneration = await api("/api/generations", { method: "POST", body: form });
    localStorage.setItem("activeGenerationId", activeGeneration.id);
    updateStatus(activeGeneration);
    pollGeneration();
  } catch (error) {
    showError(error.message);
    elements.generateButton.disabled = false;
    elements.cancelButton.classList.add("hidden");
  }
}

async function pollGeneration() {
  clearTimeout(pollTimer);
  if (!activeGeneration) return;
  try {
    activeGeneration = await api(`/api/generations/${activeGeneration.id}`);
    updateStatus(activeGeneration);
    if (activeGeneration.status === "complete") {
      localStorage.setItem("activeGenerationId", activeGeneration.id);
      elements.cancelButton.classList.add("hidden");
      elements.generateButton.disabled = !selectedFile;
      await loadModel(activeGeneration);
      if (profile) await loadLibrary();
      return;
    }
    if (["failed", "cancelled"].includes(activeGeneration.status)) {
      elements.cancelButton.classList.add("hidden");
      elements.generateButton.disabled = !selectedFile;
      if (activeGeneration.status === "failed") showError(activeGeneration.message);
      elements.viewerTitle.textContent = "Generation did not complete";
      return;
    }
    pollTimer = setTimeout(pollGeneration, 900);
  } catch (error) {
    showError(error.message);
    pollTimer = setTimeout(pollGeneration, 2000);
  }
}

elements.generateButton.addEventListener("click", startGeneration);
elements.cancelButton.addEventListener("click", async () => {
  if (!activeGeneration) return;
  try {
    activeGeneration = await api(`/api/generations/${activeGeneration.id}/cancel`, { method: "POST" });
    updateStatus(activeGeneration);
  } catch (error) { showError(error.message); }
});

function disposeCurrent() {
  if (!currentObject) return;
  currentObject.traverse((node) => {
    if (!node.isMesh) return;
    node.geometry?.dispose();
    const materials = Array.isArray(node.material) ? node.material : [node.material];
    materials.forEach((material) => {
      Object.values(material || {}).forEach((value) => value?.isTexture && value.dispose());
      material?.dispose();
    });
  });
  scene.remove(currentObject);
  currentObject = null;
}

function frameObject(object) {
  const box = new THREE.Box3().setFromObject(object);
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  const fov = THREE.MathUtils.degToRad(camera.fov);
  const distance = Math.max(sphere.radius / Math.sin(fov / 2), 2.2);
  controls.target.copy(sphere.center);
  camera.position.copy(sphere.center).add(new THREE.Vector3(1, 0.65, -1.25).normalize().multiplyScalar(distance));
  camera.near = Math.max(distance / 1000, 0.005);
  camera.far = distance * 20;
  camera.updateProjectionMatrix();
  controls.update();
}

async function loadModel(job) {
  elements.loadingModel.classList.remove("hidden");
  elements.emptyState.classList.add("hidden");
  clearError();
  try {
    const gltf = await new GLTFLoader().loadAsync(`${job.model_url}?v=${job.updated_at}`);
    disposeCurrent();
    currentObject = gltf.scene;
    currentObject.traverse((node) => {
      if (node.isMesh) {
        node.castShadow = true;
        node.receiveShadow = true;
      }
    });
    scene.add(currentObject);
    frameObject(currentObject);
    elements.viewerTitle.textContent = `Generated ${job.backend} mesh`;
    elements.vertices.textContent = job.vertices.toLocaleString();
    elements.triangles.textContent = job.triangles.toLocaleString();
    elements.fileSize.textContent = formatBytes(job.file_size);
    elements.elapsed.textContent = `${job.elapsed_seconds.toFixed(1)} s`;
    elements.downloadButton.href = job.download_url;
    elements.downloadButton.classList.remove("disabled");
    elements.downloadButton.removeAttribute("aria-disabled");
    elements.wireButton.disabled = false;
    elements.resetButton.disabled = false;
    remakeGenerationId = job.id || job.generation_id || null;
    elements.remakeButton.disabled = !remakeGenerationId;
  } catch (error) {
    elements.emptyState.classList.remove("hidden");
    showError(`The GLB was generated but the viewer could not load it: ${error.message}`);
  } finally {
    elements.loadingModel.classList.add("hidden");
  }
}

elements.gridButton.addEventListener("click", () => {
  grid.visible = !grid.visible;
  elements.gridButton.classList.toggle("active", grid.visible);
});
elements.wireButton.addEventListener("click", () => {
  if (!currentObject) return;
  const enabled = !elements.wireButton.classList.contains("active");
  currentObject.traverse((node) => {
    if (node.isMesh) {
      const materials = Array.isArray(node.material) ? node.material : [node.material];
      materials.forEach((material) => { material.wireframe = enabled; });
    }
  });
  elements.wireButton.classList.toggle("active", enabled);
});
elements.resetButton.addEventListener("click", () => currentObject && frameObject(currentObject));
elements.remakeButton.addEventListener("click", async () => {
  if (!remakeGenerationId) return;
  clearError();
  elements.remakeButton.disabled = true;
  elements.generateButton.disabled = true;
  elements.cancelButton.classList.remove("hidden");
  elements.viewerTitle.textContent = "Remaking a new reconstruction variant";
  try {
    activeGeneration = await api(`/api/generations/${remakeGenerationId}/remake`, { method: "POST" });
    localStorage.setItem("activeGenerationId", activeGeneration.id);
    updateStatus(activeGeneration);
    pollGeneration();
  } catch (error) {
    showError(error.message);
    elements.remakeButton.disabled = false;
    elements.generateButton.disabled = !selectedFile;
    elements.cancelButton.classList.add("hidden");
  }
});

async function resumeGeneration() {
  const id = localStorage.getItem("activeGenerationId");
  if (!id) return;
  try {
    activeGeneration = await api(`/api/generations/${id}`);
    updateStatus(activeGeneration);
    if (activeGeneration.status === "complete") await loadModel(activeGeneration);
    else if (["queued", "running"].includes(activeGeneration.status)) pollGeneration();
  } catch { localStorage.removeItem("activeGenerationId"); }
}

detectSystem();
loadProfile();
resumeGeneration();
