import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { GLTFExporter } from "three/examples/jsm/exporters/GLTFExporter.js";
import { DRACOLoader } from "three/examples/jsm/loaders/DRACOLoader.js";
import "./style.css";

document.querySelector("#app").innerHTML = `
  <header class="topbar">
    <div class="brand"><span class="brand-mark"><i></i><i></i><i></i></span><div><strong>Forge One</strong><small>IMAGE TO 3D STUDIO</small></div></div>
    <div class="workspace-name"><span class="workspace-cube">◇</span><span>Model workshop</span></div>
    <div class="top-actions"><div id="gpuPill" class="gpu-pill"><span></span> Checking CUDA…</div><button id="clearWorkspaceButton" class="tool clear-workspace" title="Clear the current image and 3D preview">Clear workspace</button><button id="profileButton" class="profile-button">Create profile</button></div>
  </header>
  <main class="shell">
    <nav class="app-nav" aria-label="Main navigation">
      <button class="nav-item active" title="3D Generation"><span>✦</span><small>Create</small></button>
      <button id="textToImageButton" class="nav-item" title="Text to image and 3D model"><span>✎</span><small>Imagine</small></button>
      <button id="colorButton" class="nav-item" title="Color a generated model"><span>◉</span><small>Color</small></button>
      <button id="animateButton" class="nav-item" title="Animate characters"><span>↝</span><small>Animate</small></button>
      <button id="playGameButton" class="nav-item" title="Play Forge One games"><span>▶</span><small>Play</small></button>
      <button id="libraryButton" class="nav-item" title="My library"><span>▦</span><small>Library</small></button>
      <div class="nav-spacer"></div>
      <button id="profileNavButton" class="nav-item" title="Your profile"><span>◌</span><small>Profile</small></button>
    </nav>
    <aside class="panel controls-panel">
      <div class="control-heading"><div><div class="eyebrow">NEW RECONSTRUCTION</div><h1>Build a 3D model</h1></div><span class="step-pill">01 / 02</span></div>
      <div class="input-label"><span>Source image</span><small>One clear object works best</small></div>
      <label id="dropZone" class="drop-zone" tabindex="0">
        <input id="fileInput" type="file" accept="image/png,image/jpeg,image/webp" />
        <img id="imagePreview" alt="Selected object" />
        <div id="dropPrompt" class="drop-prompt">
          <div class="upload-icon">↑</div>
          <strong>Drop one object image</strong>
          <span>PNG, JPG, or WebP · up to 25 MB</span>
        </div>
      </label>
      <div class="source-tools"><button id="editMaskButton" class="tool" type="button" disabled>Clean background</button><button id="importGlbButton" class="tool" type="button">Import GLB</button><input id="importGlbInput" type="file" accept=".glb,model/gltf-binary" hidden /></div>
      <div class="mode-block">
        <div class="input-label"><span>Reconstruction level</span><small>Choose speed or fidelity</small></div>
        <button id="fastMode" type="button" class="mode-card"><span class="mode-icon">⚡</span><div><strong>Fast</strong><small>TripoSR · refined 256³ detail for 8 GB VRAM</small></div><span class="check">✓</span></button>
        <button id="qualityMode" type="button" class="mode-card selected"><span class="mode-icon">◇</span><div><strong>Quality</strong><small>TripoSG · neutral geometry · sharp-detail default</small></div><span class="check">✓</span></button></div>
      <details class="advanced-create"><summary>More options <span>color, portrait &amp; cleanup</span></summary><div class="advanced-create-body"><label class="color-finish">Color result<select id="colorFinishSelect"><option value="later" selected>Keep uncolored — add color later</option><option value="now">Add color automatically</option></select><small>Both choices build the shape first. “Add later” lets you preview and adjust it.</small></label><section class="input-options"><label>Subject<select id="subjectModeSelect"><option value="General">General object</option><option value="Portrait">Portrait / character</option></select></label><div class="input-label"><span>Extra views</span><small>Optional</small></div><div class="view-inputs"><label>Side<input id="sideFileInput" type="file" accept="image/png,image/jpeg,image/webp" /></label><label>Back<input id="backFileInput" type="file" accept="image/png,image/jpeg,image/webp" /></label></div><p class="field-note">Extra photos are saved with the project for a compatible multi-view engine.</p></section><section class="advanced-controls"><div class="input-label"><span>Finish controls</span><small>Optional</small></div><label>Surface detail<select id="detailSelect"><option>Soft</option><option>Balanced</option><option selected>Sharp</option></select></label><label>Artifact trim<select id="trimSelect"><option>Gentle</option><option>Balanced</option><option selected>Clean</option></select></label></section></div></details>
      <button id="generateButton" class="primary" disabled><span>Generate model</span><b>→</b></button>
      <button id="cancelButton" class="secondary hidden">Cancel safely</button>
      <section id="statusCard" class="status-card hidden" aria-live="polite">
        <div class="status-heading"><span id="statusLabel">Preparing</span><span id="statusPercent">0%</span></div>
        <div class="progress-track"><div id="progressBar"></div></div>
        <p id="statusMessage"></p>
      </section>
      <div id="errorCard" class="error-card hidden"></div>
      <p id="saveHint" class="privacy">Sign in to keep your generations organized and available on your other devices.</p>
    </aside>
    <section class="viewer-panel">
      <div class="viewer-toolbar">
        <div><span class="eyebrow">CANVAS</span><strong id="viewerTitle">Waiting for an image</strong></div>
        <div class="tool-actions"><div class="quick-tools"><button id="frontViewButton" class="tool" disabled>Front</button><button id="sideViewButton" class="tool" disabled>Side</button><button id="resetButton" class="tool" disabled>Reset</button></div><details id="moreTools" class="toolbar-menu is-disabled"><summary>More tools</summary><div class="toolbar-menu-list"><button id="fullscreenButton" class="tool" disabled>Fullscreen</button><button id="studioButton" class="tool" disabled>Lighting</button><button id="snapshotButton" class="tool" disabled>Snapshot</button><button id="gridButton" class="tool active" disabled>Grid</button><button id="wireButton" class="tool" disabled>Wireframe</button><button id="removeColorButton" class="tool" disabled>Remove color</button><button id="polishButton" class="tool" disabled>Polish mesh</button><button id="restoreOriginalButton" class="tool hidden">Show original</button><button id="keepRemakeButton" class="tool keep-remake hidden">Keep remake</button><button id="remakeButton" class="tool" disabled title="Create a separate candidate from this image">Try remake</button></div></details></div>
      </div>
      <div id="viewer">
        <canvas id="sceneCanvas"></canvas>
        <div id="emptyState" class="empty-state"><div class="orb"><span></span></div><div class="empty-kicker">READY WHEN YOU ARE</div><h2>Turn a single image into a 3D asset</h2><p>Choose a source image, select a reconstruction level, then generate.</p><div class="empty-steps"><span>01 Upload</span><i></i><span>02 Generate</span><i></i><span>03 Inspect</span></div></div>
        <div id="loadingModel" class="model-loading hidden">Loading validated GLB…</div>
      </div>
      <footer class="result-bar">
        <div class="metric"><span>Vertices</span><strong id="vertices">—</strong></div>
        <div class="metric"><span>Triangles</span><strong id="triangles">—</strong></div>
        <div class="metric"><span>GLB size</span><strong id="fileSize">—</strong></div>
        <div class="metric"><span>Generation</span><strong id="elapsed">—</strong></div>
        <button id="gameReadyButton" class="game-ready-cta" type="button" disabled><span>◇</span> Game Ready</button>
        <div class="export-control"><select id="exportFormat" aria-label="Export format"><option value="glb">GLB</option><option value="obj">OBJ</option><option value="stl">STL</option></select><a id="downloadButton" class="download disabled" aria-disabled="true">Download GLB</a></div>
      </footer>
    </section>
  </main>
  <section id="profileDialog" class="overlay hidden" aria-modal="true" role="dialog">
    <form id="profileForm" class="dialog-card"><button id="profileClose" type="button" class="dialog-close">×</button><div class="eyebrow">YOUR PROFILE</div><h2 id="profileHeading">Save your work</h2><p>Create a profile, then sign in on any device using this public link to open your saved models.</p><label>Profile name<input id="profileName" maxlength="40" required autocomplete="username" /></label><label>Password<input id="profilePassword" type="password" minlength="8" required autocomplete="current-password" /></label><div class="dialog-actions"><button id="loginButton" type="button" class="secondary">Sign in</button><button class="primary" type="submit">Create profile</button></div><p id="profileError" class="dialog-error"></p><button id="logoutButton" type="button" class="text-button hidden">Sign out</button></form>
  </section>
  <section id="textToImageDialog" class="overlay hidden" aria-modal="true" role="dialog">
    <form id="textToImageForm" class="dialog-card text-to-image-card"><button id="textToImageClose" type="button" class="dialog-close">×</button><div class="eyebrow">FORGE ONE IMAGINE · LOCAL</div><h2>Text → image + 3D model</h2><p>Describe one clear object. Forge One first creates a 512px source image locally, then reconstructs it as a GLB. The generated image stays saved with the model for color and remakes.</p><label>What should Forge One make?<textarea id="textPrompt" maxlength="500" placeholder="A friendly golden retriever standing, full body, isolated on a clean studio background"></textarea></label><div class="prompt-examples"><button type="button" data-prompt="A detailed fantasy sword standing upright, isolated on a clean studio background">Fantasy sword</button><button type="button" data-prompt="A small red vintage toy robot, full body, isolated on a clean studio background">Toy robot</button><button type="button" data-prompt="A modern wooden desk chair, isolated on a clean studio background">Wood chair</button></div><details class="batch-list"><summary>Make a list of models <span>one object per line</span></summary><p>Forge One creates each image and 3D model in order. Add 2–12 objects here; this replaces the single prompt above.</p><textarea id="batchPromptList" maxlength="6000" placeholder="A medieval wooden treasure chest, isolated on white&#10;A blue ceramic coffee mug, isolated on white&#10;A small orange fox figurine, isolated on white"></textarea></details><p class="text-to-image-note">Uses the free local SD-Turbo model. Each batch item is queued safely so the GPU makes one at a time.</p><button id="startTextToImageButton" class="primary" type="submit">Create image + 3D model</button></form>
  </section>
  <section id="colorDialog" class="overlay hidden" aria-modal="true" role="dialog">
    <div class="dialog-card color-card"><button id="colorClose" type="button" class="dialog-close">×</button><div class="eyebrow">COLOR</div><h2>Add color without changing shape</h2><p id="colorModelHint">Forge One keeps the model fixed and transfers material color from your photo. It first isolates the object from its backdrop, then retains useful texture such as wood grain without rebuilding the shape.</p><div class="color-source"><img id="colorSourcePreview" alt="Saved source image for color matching" /><span>Your photo</span></div><label class="color-style">Color approach<select id="colorStyle"><option value="colour" selected>Material color transfer · recommended</option><option value="detail">Exact photo placement · advanced</option></select><small id="colorStyleNote">Keeps material character such as wood grain and fabric while allowing for small shape differences. Best for most models.</small></label><details class="color-palette"><summary>Choose exact colors <span>optional guided palette</span></summary><p>Forge One uses the photo to decide <em>where</em> the dark, middle, and bright material areas are. Your three colors decide exactly <em>which</em> colors those regions use.</p><div class="palette-grid"><label><input id="paletteShadow" type="color" value="#5a351d" /><span>Shadow</span></label><label><input id="paletteBase" type="color" value="#a96b39" /><span>Base</span></label><label><input id="paletteHighlight" type="color" value="#e6c18c" /><span>Highlight</span></label></div></details><details class="color-adjustments"><summary>Fine-tune color <span>optional</span></summary><div class="slider-grid"><label>Brightness <output id="colorBrightnessValue">100%</output><input id="colorBrightness" type="range" min="70" max="140" value="100" /></label><label>Saturation <output id="colorSaturationValue">100%</output><input id="colorSaturation" type="range" min="0" max="180" value="100" /></label><label>Coverage <output id="colorCoverageValue">100%</output><input id="colorCoverage" type="range" min="70" max="125" value="100" /></label></div></details><button id="startColorButton" class="primary" type="button">Apply material color</button><div id="colorStatus" class="animation-status hidden"></div><div id="colorDownloads" class="animation-downloads hidden"><button id="showGeometryButton" class="secondary" type="button">Use uncolored model</button><button id="previewColorButton" class="secondary" type="button">Preview color</button><a id="colorDownload" class="secondary" download>Save colored GLB</a></div><p class="animate-note">Use Preview to decide. You can always return to the uncolored model—nothing is overwritten.</p></div>
  </section>
  <section id="animateDialog" class="overlay hidden" aria-modal="true" role="dialog">
    <div class="dialog-card animate-card"><button id="animateClose" type="button" class="dialog-close">×</button><div class="eyebrow">FORGE ONE ANIMATE · LOCAL</div><h2>Rig and animate a character</h2><p id="animateModelHint">Open a generated character in the viewer, or drop a character photo below. Forge One uses your local Blender installation—nothing is uploaded.</p><div id="animationDropZone" class="animation-drop-zone" tabindex="0"><input id="animationFileInput" type="file" accept="image/png,image/jpeg,image/webp" /><img id="animationImagePreview" alt="Animation source preview" /><div id="animationDropPrompt"><b>Drop a full-body character photo</b><span>or click to choose PNG, JPG, or WebP</span></div></div><label class="animation-quality">Photo reconstruction quality<select id="animationQuality"><option value="Quality" selected>Quality · sharp detail</option><option value="Fast">Fast · lower-detail draft</option></select></label><div class="motion-chips"><button data-motion="walk" class="selected" type="button">Walk</button><button data-motion="run" type="button">Run</button><button data-motion="jump" type="button">Jump</button></div><label class="humanoid-check"><input id="humanoidConfirm" type="checkbox" /> This is a full, upright humanoid with arms and legs.</label><button id="startAnimationButton" class="primary" type="button">Create local animation</button><div id="animationStatus" class="animation-status hidden"></div><div id="animationDownloads" class="animation-downloads hidden"><button id="previewAnimationButton" class="secondary" type="button">Preview animation</button><a id="animationGlbDownload" class="secondary" download>Download animated GLB</a><a id="animationBlendDownload" class="secondary" download>Download editable Blender file</a></div><div class="playback-controls"><button id="animationPlayButton" class="tool" type="button">Pause</button><label>Speed<select id="animationSpeed"><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="1.5">1.5×</option><option value="2">2×</option></select></label><label class="humanoid-check"><input id="animationLoop" type="checkbox" checked /> Loop</label></div><p class="animate-note">A photo is first reconstructed into a 3D character, then locally auto-rigged. Quality gives the model more geometric detail, but a single photo still cannot reveal an exact face, hairstyle, back, or hidden side.</p></div>
  </section>
  <section id="maskDialog" class="overlay hidden" aria-modal="true" role="dialog"><div class="dialog-card mask-card"><button id="maskClose" type="button" class="dialog-close">×</button><div class="eyebrow">BACKGROUND CLEANUP</div><h2>Erase unwanted parts</h2><p>Paint away the background before generation. Restore brings back the original pixels.</p><canvas id="maskCanvas"></canvas><div class="mask-controls"><label>Brush <input id="maskBrush" type="range" min="8" max="120" value="42" /></label><button id="maskEraseButton" class="tool active" type="button">Erase</button><button id="maskRestoreButton" class="tool" type="button">Restore</button><button id="maskApplyButton" class="primary" type="button">Use cleaned image</button></div></div></section>
  <section id="polishDialog" class="overlay hidden" aria-modal="true" role="dialog"><div class="dialog-card"><button id="polishClose" type="button" class="dialog-close">×</button><div class="eyebrow">GEOMETRY CLEANUP</div><h2>Polish a copy of this mesh</h2><p>The original stays untouched so you can compare before keeping the result.</p><div class="slider-grid"><label>Smoothing<input id="polishSmooth" type="range" min="0" max="5" value="1" /></label><label>Trim loose clumps<select id="polishTrim"><option value="none">Off</option><option value="light">Light</option><option value="strong" selected>Strong</option></select></label><label>Triangle target<select id="polishSimplify"><option value="1">Keep all</option><option value="0.75" selected>75%</option><option value="0.5">50%</option></select></label></div><button id="startPolishButton" class="primary" type="button">Create polished copy</button><div id="polishStatus" class="animation-status hidden"></div><div id="polishDownloads" class="animation-downloads hidden"><button id="showPolishOriginalButton" class="secondary" type="button">Show original</button><button id="previewPolishButton" class="secondary" type="button">Preview polished</button><a id="polishDownload" class="secondary" download>Download polished GLB</a></div></div></section>
  <section id="gameReadyDialog" class="overlay hidden" aria-modal="true" role="dialog"><div class="dialog-card game-ready-card"><button id="gameReadyClose" type="button" class="dialog-close">×</button><div class="eyebrow">GAME READY EXPORT</div><h2>Optimize a safe copy</h2><p>The generated model stays untouched. Choose how strongly to reduce unnecessary geometry while preserving its silhouette, UVs, materials, and textures.</p><div id="gameReadyPresets" class="game-ready-presets"><button type="button" data-preset="high"><strong>High Detail</strong><small>Minimal reduction · close-up objects</small></button><button type="button" data-preset="game" class="selected"><span>Recommended</span><strong>Game Ready</strong><small>Balanced quality and performance</small></button><button type="button" data-preset="low"><strong>Low Poly</strong><small>Stronger reduction · distant objects</small></button></div><button id="startGameReadyButton" class="primary" type="button">Create Game Ready copy</button><div id="gameReadyProgress" class="game-ready-progress hidden"><div><strong id="gameReadyStatus">Preparing…</strong><b id="gameReadyPercent">0%</b></div><div class="progress-track"><i id="gameReadyProgressBar"></i></div></div><div id="gameReadyResults" class="game-ready-results hidden"><div class="game-ready-comparison"><div><span>Original triangles</span><strong id="gameReadyOriginalTriangles">—</strong></div><div><span>Optimized triangles</span><strong id="gameReadyOptimizedTriangles">—</strong></div><div class="reduction"><span>Reduction</span><strong id="gameReadyReduction">—</strong></div><div><span>Original size</span><strong id="gameReadyOriginalSize">—</strong></div><div><span>Optimized size</span><strong id="gameReadyOptimizedSize">—</strong></div></div><p id="gameReadyReport" class="game-ready-report"></p><div class="game-ready-compare"><button id="showGameReadyOriginalButton" class="secondary" type="button">View Original</button><button id="previewGameReadyButton" class="secondary" type="button">View Game Ready</button></div><div class="game-ready-downloads"><a id="gameReadyOriginalDownload" class="secondary" download>Download Original GLB</a><a id="gameReadyDownload" class="primary" download>Download Game Ready GLB</a></div></div></div></section>
  <aside id="libraryDrawer" class="library-drawer hidden"><div class="drawer-heading"><div><div class="eyebrow">SAVED MODELS</div><strong id="libraryTitle">My library</strong></div><button id="libraryClose" class="tool">Close</button></div><div class="library-actions"><input id="librarySearch" type="search" placeholder="Search models or tags" /><button id="newFolderButton" class="tool" type="button">＋ New folder</button></div><p id="libraryEmpty" class="library-empty">Sign in to save models and open them from another device.</p><div id="libraryList" class="library-list"></div></aside>
`;

document.getElementById("playGameButton")?.addEventListener("click", () => { window.location.href = "/games/room-one/"; });

document.querySelector(".color-palette")?.insertAdjacentHTML("afterend", `
  <details class="paint-map"><summary>Paint exact placement <span>front-view precision</span></summary>
    <p>Choose a color, then drag over the matching part of the photo. These marks control <em>where</em> that color goes on the visible side of the model.</p>
    <div class="paint-map-tools"><label>Color <input id="paintColor" type="color" value="#a96b39" /></label><label>Brush <input id="paintBrush" type="range" min="8" max="110" value="34" /></label><button id="paintClear" class="tool" type="button">Clear marks</button></div>
    <canvas id="paintMapCanvas" aria-label="Paint exact color placement on source image"></canvas><small id="paintMapHint">Open this panel after your photo loads. Use small marks for precise details.</small>
  </details>`);
document.getElementById("colorDownloads")?.insertAdjacentHTML("beforeend", `<button id="bakeTextureButton" class="secondary" type="button">Bake 1K texture GLB</button>`);
document.querySelector(".game-ready-downloads")?.insertAdjacentHTML("beforeend", `<button id="gamePackageButton" class="secondary" type="button">Build complete game package</button><a id="gamePackageDownload" class="primary hidden" download>Download LOD package</a>`);
document.querySelector(".quick-tools")?.insertAdjacentHTML("beforeend", `<button id="zoomOutButton" class="tool" type="button" title="Zoom out">−</button><button id="zoomInButton" class="tool" type="button" title="Zoom in">+</button><button id="compareButton" class="tool" type="button" title="Compare original and current model">Compare</button><button id="paint3dButton" class="tool" type="button" title="Paint directly on the 3D model">Paint 3D</button><button id="captureIssueButton" class="tool" type="button" title="Capture the current 3D view">Report view</button>`);
document.getElementById("viewer")?.insertAdjacentHTML("beforeend", `<div id="compareLabels" class="compare-labels hidden"><span>Original</span><span>Current</span></div>`);
document.querySelector(".toolbar-menu-list")?.insertAdjacentHTML("beforeend", `<button id="versionsButton" class="tool" type="button" disabled>Versions</button>`);
document.querySelector(".toolbar-menu-list")?.insertAdjacentHTML("beforeend", `<button id="turntableButton" class="tool" type="button" disabled>Turntable</button><button id="backgroundButton" class="tool" type="button" disabled>Background</button><button id="saveViewButton" class="tool" type="button" disabled>Save view</button><button id="restoreViewButton" class="tool" type="button" disabled>Restore view</button>`);
document.body.insertAdjacentHTML("beforeend", `<section id="issueDialog" class="overlay hidden" aria-modal="true" role="dialog"><div class="dialog-card issue-card"><button id="issueClose" type="button" class="dialog-close">×</button><div class="eyebrow">VIEW CAPTURE</div><h2>Show Forge One the problem</h2><p>Capture the current model view, then describe the issue. The screenshot is downloaded locally so you can keep it with the model or share it when requesting a repair.</p><img id="issuePreview" alt="Captured 3D model view" /><textarea id="issueDescription" maxlength="500" placeholder="Example: wood grain is missing from the seat, or this clump should be removed."></textarea><button id="issueSave" class="primary" type="button">Save issue screenshot</button><p id="issueHint" class="animate-note">For colour problems, use Paint exact placement. For stray geometry, use Polish mesh or Try remake.</p></div></section>`);
document.getElementById("issueDescription")?.insertAdjacentHTML("beforebegin", `<label class="issue-type">Problem type<select id="issueType"><option value="general">Not sure</option><option value="color">Color placement</option><option value="clumps">Extra clumps</option><option value="detail">Missing shape detail</option><option value="scale">Scale or pivot</option><option value="animation">Animation</option></select></label>`);
document.getElementById("issueSave")?.insertAdjacentHTML("beforebegin", `<button id="issueAnalyze" class="secondary" type="button">Run local repair check</button>`);
document.body.insertAdjacentHTML("beforeend", `<section id="paint3dDialog" class="overlay hidden" aria-modal="true" role="dialog"><div class="dialog-card paint3d-card"><button id="paint3dClose" type="button" class="dialog-close">×</button><div class="eyebrow">DIRECT 3D PAINT</div><h2>Paint on the model</h2><p>Rotate to the area first, enable painting, then click or drag on the model. Smart region fills visually similar material; Brush paints only near the pointer.</p><div class="paint3d-controls"><label>Color<input id="paint3dColor" type="color" value="#a96b39" /></label><label>Tool<select id="paint3dTool"><option value="brush">Brush</option><option value="region">Smart region</option></select></label><label>Brush size<input id="paint3dSize" type="range" min="1" max="22" value="5" /></label><label>Region tolerance<input id="paint3dTolerance" type="range" min="5" max="90" value="28" /></label></div><button id="paint3dToggle" class="primary" type="button">Enable painting</button><div class="paint3d-actions"><button id="paint3dUndo" class="secondary" type="button" disabled>Undo</button><button id="paint3dReset" class="secondary" type="button">Reset paint</button><button id="paint3dDownload" class="secondary" type="button">Download painted GLB</button></div><p id="paint3dStatus" class="animate-note">Painting changes only the viewer copy until you download it.</p></div></section>`);
document.body.insertAdjacentHTML("beforeend", `<section id="versionsDialog" class="overlay hidden" aria-modal="true" role="dialog"><div class="dialog-card versions-card"><button id="versionsClose" type="button" class="dialog-close">×</button><div class="eyebrow">MODEL HISTORY</div><h2>Versions and comparisons</h2><p>Every generated derivative is a separate GLB. Open any version to compare it with the original; nothing here overwrites another version.</p><div id="versionsList" class="versions-list"></div></div></section>`);

const elements = Object.fromEntries(
  ["gpuPill", "clearWorkspaceButton", "textToImageButton", "colorButton", "animateButton", "libraryButton", "profileButton", "profileNavButton", "dropZone", "fileInput", "imagePreview", "dropPrompt", "editMaskButton", "importGlbButton", "importGlbInput", "colorFinishSelect", "subjectModeSelect", "sideFileInput", "backFileInput", "fastMode", "qualityMode", "detailSelect", "trimSelect", "generateButton", "cancelButton", "statusCard", "statusLabel", "statusPercent", "progressBar", "statusMessage", "errorCard", "saveHint", "viewerTitle", "frontViewButton", "sideViewButton", "moreTools", "fullscreenButton", "studioButton", "snapshotButton", "gridButton", "wireButton", "resetButton", "removeColorButton", "polishButton", "remakeButton", "restoreOriginalButton", "keepRemakeButton", "viewer", "sceneCanvas", "emptyState", "loadingModel", "vertices", "triangles", "fileSize", "elapsed", "exportFormat", "downloadButton", "gameReadyButton", "gameReadyDialog", "gameReadyClose", "gameReadyPresets", "startGameReadyButton", "gameReadyProgress", "gameReadyStatus", "gameReadyPercent", "gameReadyProgressBar", "gameReadyResults", "gameReadyOriginalTriangles", "gameReadyOptimizedTriangles", "gameReadyReduction", "gameReadyOriginalSize", "gameReadyOptimizedSize", "gameReadyReport", "showGameReadyOriginalButton", "previewGameReadyButton", "gameReadyOriginalDownload", "gameReadyDownload", "profileDialog", "profileForm", "profileClose", "profileHeading", "profileName", "profilePassword", "loginButton", "logoutButton", "profileError", "textToImageDialog", "textToImageForm", "textToImageClose", "textPrompt", "startTextToImageButton", "colorDialog", "colorClose", "colorModelHint", "colorSourcePreview", "colorStyle", "colorStyleNote", "paletteShadow", "paletteBase", "paletteHighlight", "colorBrightness", "colorBrightnessValue", "colorSaturation", "colorSaturationValue", "colorCoverage", "colorCoverageValue", "startColorButton", "colorStatus", "colorDownloads", "showGeometryButton", "previewColorButton", "colorDownload", "animateDialog", "animateClose", "animateModelHint", "animationDropZone", "animationFileInput", "animationImagePreview", "animationDropPrompt", "animationQuality", "humanoidConfirm", "startAnimationButton", "animationStatus", "animationDownloads", "previewAnimationButton", "animationGlbDownload", "animationBlendDownload", "animationPlayButton", "animationSpeed", "animationLoop", "maskDialog", "maskClose", "maskCanvas", "maskBrush", "maskEraseButton", "maskRestoreButton", "maskApplyButton", "polishDialog", "polishClose", "polishSmooth", "polishTrim", "polishSimplify", "startPolishButton", "polishStatus", "polishDownloads", "showPolishOriginalButton", "previewPolishButton", "polishDownload", "libraryDrawer", "libraryClose", "libraryTitle", "newFolderButton", "librarySearch", "libraryEmpty", "libraryList"].map((id) => [id, document.getElementById(id)])
);

Object.assign(elements, {
  paintColor: document.getElementById("paintColor"), paintBrush: document.getElementById("paintBrush"),
  paintClear: document.getElementById("paintClear"), paintMapCanvas: document.getElementById("paintMapCanvas"),
  paintMapHint: document.getElementById("paintMapHint"),
  bakeTextureButton: document.getElementById("bakeTextureButton"),
  gamePackageButton: document.getElementById("gamePackageButton"), gamePackageDownload: document.getElementById("gamePackageDownload"),
  zoomOutButton: document.getElementById("zoomOutButton"), zoomInButton: document.getElementById("zoomInButton"),
  captureIssueButton: document.getElementById("captureIssueButton"), issueDialog: document.getElementById("issueDialog"),
  issueClose: document.getElementById("issueClose"), issuePreview: document.getElementById("issuePreview"),
  issueDescription: document.getElementById("issueDescription"), issueSave: document.getElementById("issueSave"),
  issueType: document.getElementById("issueType"), issueAnalyze: document.getElementById("issueAnalyze"),
  issueHint: document.getElementById("issueHint"),
  paint3dButton: document.getElementById("paint3dButton"), paint3dDialog: document.getElementById("paint3dDialog"),
  compareButton: document.getElementById("compareButton"), compareLabels: document.getElementById("compareLabels"),
  paint3dClose: document.getElementById("paint3dClose"), paint3dColor: document.getElementById("paint3dColor"),
  paint3dTool: document.getElementById("paint3dTool"), paint3dSize: document.getElementById("paint3dSize"),
  paint3dTolerance: document.getElementById("paint3dTolerance"), paint3dToggle: document.getElementById("paint3dToggle"),
  paint3dUndo: document.getElementById("paint3dUndo"), paint3dReset: document.getElementById("paint3dReset"),
  paint3dDownload: document.getElementById("paint3dDownload"), paint3dStatus: document.getElementById("paint3dStatus"),
  versionsButton: document.getElementById("versionsButton"), versionsDialog: document.getElementById("versionsDialog"),
  versionsClose: document.getElementById("versionsClose"), versionsList: document.getElementById("versionsList"),
  turntableButton: document.getElementById("turntableButton"), backgroundButton: document.getElementById("backgroundButton"),
  saveViewButton: document.getElementById("saveViewButton"), restoreViewButton: document.getElementById("restoreViewButton"),
});

let selectedFile = null;
let sideFile = null;
let backFile = null;
let activeGeneration = null;
let currentObject = null;
let pollTimer = null;
let selectedMode = "Quality";
let profile = null;
let remakeGenerationId = null;
let remakeOriginal = null;
let remakeCandidate = null;
let displayedJob = null;
let selectedMotion = "walk";
let animationPollTimer = null;
let animationImageFile = null;
let readyAnimation = null;
let currentMixer = null;
let currentAction = null;
let colorPollTimer = null;
let readyColor = null;
let colorOriginalJob = null;
let geometryMasterJob = null;
let polishOriginalJob = null;
let readyPolish = null;
let maskMode = "erase";
let maskDrawing = false;
let maskOriginalCanvas = null;
let libraryCache = null;
let batchGenerationIds = [];
let batchPollTimer = null;
let gameReadyPollTimer = null;
let selectedGameReadyPreset = "game";
let gameReadyOriginalJob = null;
let readyGameReady = null;
let paintGuides = [];
let paintMapImage = null;
let paintMapDrawing = false;
let paint3dEnabled = false;
let paint3dDrawing = false;
let paint3dBaseline = [];
let paint3dUndoStack = [];
let turntableEnabled = false;
let savedViewerPose = null;
let compareObject = null;
let splitCompareEnabled = false;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x131824);
const camera = new THREE.PerspectiveCamera(42, 1, 0.01, 100);
camera.position.set(3.2, 2.3, 3.6);
const renderer = new THREE.WebGLRenderer({ canvas: elements.sceneCanvas, antialias: true, alpha: false });
const dracoLoader = new DRACOLoader();
dracoLoader.setDecoderPath("/");
const gltfLoader = new GLTFLoader();
gltfLoader.setDRACOLoader(dracoLoader);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.42;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.minDistance = 0.35;
controls.maxDistance = 14;

const hemisphereLight = new THREE.HemisphereLight(0xe4efff, 0x303746, 3.4);
scene.add(hemisphereLight);
const keyLight = new THREE.DirectionalLight(0xffffff, 5.8);
keyLight.position.set(4, 6, 3);
keyLight.castShadow = true;
scene.add(keyLight);
const rimLight = new THREE.DirectionalLight(0x8ca7ff, 3.2);
rimLight.position.set(-4, 2, -4);
scene.add(rimLight);
const fillLight = new THREE.DirectionalLight(0xd7f1ff, 2.1);
fillLight.position.set(-3, 3, 4);
scene.add(fillLight);
const grid = new THREE.GridHelper(12, 24, 0x314060, 0x182135);
grid.position.y = -1.05;
grid.material.opacity = 0.7;
grid.material.transparent = true;
scene.add(grid);
const animationClock = new THREE.Clock();

function resizeViewer() {
  const width = elements.viewer.clientWidth;
  const height = elements.viewer.clientHeight;
  renderer.setSize(width, height, false);
  camera.aspect = width / Math.max(height, 1);
  camera.updateProjectionMatrix();
}
new ResizeObserver(resizeViewer).observe(elements.viewer);

function animate() {
  const delta = animationClock.getDelta();
  currentMixer?.update(delta);
  if (turntableEnabled && currentObject && !paint3dEnabled) currentObject.rotation.y += delta * 0.42;
  controls.update();
  if (splitCompareEnabled && compareObject && currentObject) {
    const width = elements.viewer.clientWidth;
    const height = elements.viewer.clientHeight;
    renderer.setScissorTest(true);
    currentObject.visible = false; compareObject.visible = true;
    renderer.setViewport(0, 0, width / 2, height); renderer.setScissor(0, 0, width / 2, height); renderer.render(scene, camera);
    currentObject.visible = true; compareObject.visible = false;
    renderer.setViewport(width / 2, 0, width / 2, height); renderer.setScissor(width / 2, 0, width / 2, height); renderer.render(scene, camera);
    compareObject.visible = true; renderer.setScissorTest(false); renderer.setViewport(0, 0, width, height);
  } else {
    renderer.render(scene, camera);
  }
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
    elements.newFolderButton.disabled = true;
    return;
  }
  try {
    const { models, folders } = await api("/api/library");
    libraryCache = { models, folders };
    const search = elements.librarySearch.value.trim().toLowerCase();
    const visibleModels = search
      ? models.filter((entry) => `${entry.title} ${entry.backend} ${entry.tags || ""}`.toLowerCase().includes(search))
      : models;
    elements.newFolderButton.disabled = false;
    const makeModelItem = (entry) => {
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
      const rename = document.createElement("button");
      rename.type = "button"; rename.textContent = "Rename"; rename.className = "library-rename";
      rename.addEventListener("click", async () => {
        const title = window.prompt("Name this model", entry.title);
        if (title === null || title.trim() === entry.title) return;
        try {
          const form = new FormData(); form.append("title", title.trim());
          await api(`/api/library/${entry.id}`, { method: "PATCH", body: form });
          await loadLibrary();
        } catch (error) { showError(error.message); }
      });
      const remove = document.createElement("button");
      remove.type = "button"; remove.textContent = "Remove"; remove.className = "library-remove";
      remove.addEventListener("click", async () => {
        if (!window.confirm(`Remove “${entry.title}” from your library? The GLB file itself will stay on this PC.`)) return;
        try {
          await api(`/api/library/${entry.id}`, { method: "DELETE" });
          await loadLibrary();
        } catch (error) { showError(error.message); }
      });
      const move = document.createElement("select");
      move.className = "library-move";
      move.setAttribute("aria-label", `Move ${entry.title} to folder`);
      move.append(new Option("Unfiled", ""), ...folders.map((folder) => new Option(folder.name, folder.id)));
      move.value = entry.folder_id || "";
      move.addEventListener("change", async () => {
        try {
          const form = new FormData(); form.append("folder_id", move.value);
          await api(`/api/library/${entry.id}/folder`, { method: "PATCH", body: form });
          await loadLibrary();
        } catch (error) { showError(error.message); move.value = entry.folder_id || ""; }
      });
      const tag = document.createElement("button");
      tag.type = "button"; tag.textContent = "Tags"; tag.className = "library-rename";
      tag.addEventListener("click", async () => {
        const tags = window.prompt("Comma-separated tags", entry.tags || "");
        if (tags === null) return;
        try { const form = new FormData(); form.append("tags", tags); await api(`/api/library/${entry.id}/tags`, { method: "PATCH", body: form }); await loadLibrary(); }
        catch (error) { showError(error.message); }
      });
      const share = document.createElement("button");
      share.type = "button"; share.textContent = "Share"; share.className = "library-download";
      share.addEventListener("click", async () => {
        const daysText = window.prompt("How many days should this private link work? (1–30)", "7");
        if (daysText === null) return;
        const days = Math.max(1, Math.min(30, Number.parseInt(daysText, 10) || 7));
        const allowDownload = window.confirm("Allow people with the private link to download the GLB? Choose Cancel for preview only.");
        try {
          const form = new FormData(); form.append("days", String(days)); form.append("allow_download", String(allowDownload));
          const result = await api(`/api/library/${entry.id}/share`, { method: "POST", body: form });
          const shareUrl = result.share.url;
          await navigator.clipboard?.writeText(shareUrl);
          window.prompt("Private link copied. Anyone with this link can view it until it expires.", shareUrl);
        } catch (error) { showError(error.message); }
      });
      item.append(open, document.createElement("small"), download, rename, tag, share, remove, move);
      item.querySelector("small").textContent = `${entry.backend} · ${new Date(entry.created_at).toLocaleDateString()}${entry.tags ? ` · ${entry.tags}` : ""}`;
      return item;
    };
    const makeSection = (title, entries, folder = null) => {
      const section = document.createElement("section");
      section.className = "library-folder";
      const heading = document.createElement("div");
      heading.className = "folder-heading";
      const name = document.createElement("strong");
      name.textContent = title;
      heading.append(name);
      if (folder) {
        const rename = document.createElement("button");
        rename.type = "button"; rename.className = "folder-action"; rename.textContent = "Rename";
        rename.addEventListener("click", async () => {
          const nextName = window.prompt("Folder name", folder.name);
          if (nextName === null || nextName.trim() === folder.name) return;
          try { const form = new FormData(); form.append("name", nextName.trim()); await api(`/api/library/folders/${folder.id}`, { method: "PATCH", body: form }); await loadLibrary(); } catch (error) { showError(error.message); }
        });
        const remove = document.createElement("button");
        remove.type = "button"; remove.className = "folder-action folder-delete"; remove.textContent = "Delete";
        remove.addEventListener("click", async () => {
          if (!window.confirm(`Delete “${folder.name}”? Its models will stay in Unfiled.`)) return;
          try { await api(`/api/library/folders/${folder.id}`, { method: "DELETE" }); await loadLibrary(); } catch (error) { showError(error.message); }
        });
        heading.append(rename, remove);
      }
      const content = document.createElement("div");
      content.className = "folder-models";
      if (entries.length) content.append(...entries.map(makeModelItem));
      else { const empty = document.createElement("p"); empty.className = "folder-empty"; empty.textContent = "No models in this folder yet."; content.append(empty); }
      section.append(heading, content);
      return section;
    };
    const sections = folders.map((folder) => makeSection(folder.name, visibleModels.filter((entry) => entry.folder_id === folder.id), folder));
    const unfiled = visibleModels.filter((entry) => !entry.folder_id);
    if (unfiled.length || !folders.length) sections.unshift(makeSection("Unfiled", unfiled));
    elements.libraryList.replaceChildren(...sections);
    elements.libraryEmpty.textContent = visibleModels.length ? "" : search ? "No models match that search." : "No saved models yet. Generate while signed in and it will appear here.";
    elements.libraryEmpty.classList.toggle("hidden", Boolean(visibleModels.length));
  } catch (error) { elements.libraryEmpty.textContent = error.message; elements.libraryEmpty.classList.remove("hidden"); }
}

function redrawPaintMap() {
  const canvas = elements.paintMapCanvas;
  if (!canvas || !paintMapImage) return;
  const context = canvas.getContext("2d");
  canvas.width = paintMapImage.naturalWidth;
  canvas.height = paintMapImage.naturalHeight;
  context.drawImage(paintMapImage, 0, 0);
  for (const mark of paintGuides) {
    context.beginPath();
    context.arc(mark.x * canvas.width, mark.y * canvas.height, mark.radius * Math.min(canvas.width, canvas.height), 0, Math.PI * 2);
    context.fillStyle = `${mark.color}99`;
    context.fill();
    context.lineWidth = Math.max(1, Math.min(canvas.width, canvas.height) / 180);
    context.strokeStyle = "#ffffffcc";
    context.stroke();
  }
  elements.paintMapHint.textContent = paintGuides.length
    ? `${paintGuides.length} placement mark${paintGuides.length === 1 ? "" : "s"} ready. They affect only the matching visible photo region.`
    : "Choose a color and paint where it belongs on the photo. Use small marks for precise details.";
}

function loadPaintMap(sourceUrl) {
  paintGuides = [];
  paintMapImage = new Image();
  paintMapImage.onload = redrawPaintMap;
  paintMapImage.onerror = () => { elements.paintMapHint.textContent = "The saved source photo could not be loaded for paint mapping."; };
  paintMapImage.src = sourceUrl;
}

function addPaintGuide(event) {
  if (!paintMapImage) return;
  const rect = elements.paintMapCanvas.getBoundingClientRect();
  const x = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
  const y = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height));
  const radius = Number(elements.paintBrush.value) / Math.min(elements.paintMapCanvas.width, elements.paintMapCanvas.height);
  const previous = paintGuides[paintGuides.length - 1];
  if (previous && Math.hypot(previous.x - x, previous.y - y) < radius * 0.22 && previous.color === elements.paintColor.value) return;
  paintGuides.push({ x, y, radius, color: elements.paintColor.value });
  redrawPaintMap();
}

elements.paintMapCanvas.addEventListener("pointerdown", (event) => { paintMapDrawing = true; elements.paintMapCanvas.setPointerCapture(event.pointerId); addPaintGuide(event); });
elements.paintMapCanvas.addEventListener("pointermove", (event) => { if (paintMapDrawing) addPaintGuide(event); });
elements.paintMapCanvas.addEventListener("pointerup", () => { paintMapDrawing = false; });
elements.paintMapCanvas.addEventListener("pointercancel", () => { paintMapDrawing = false; });
elements.paintClear.addEventListener("click", () => { paintGuides = []; redrawPaintMap(); });
function zoomViewer(amount) {
  const offset = camera.position.clone().sub(controls.target);
  const distance = offset.length();
  const next = THREE.MathUtils.clamp(distance * amount, controls.minDistance, controls.maxDistance);
  camera.position.copy(controls.target).add(offset.normalize().multiplyScalar(next));
  controls.update();
}
elements.zoomInButton.addEventListener("click", () => zoomViewer(0.78));
elements.zoomOutButton.addEventListener("click", () => zoomViewer(1.28));
function clearCompareObject() {
  if (!compareObject) return;
  compareObject.traverse((node) => {
    if (!node.isMesh) return;
    node.geometry?.dispose();
    const materials = Array.isArray(node.material) ? node.material : [node.material];
    materials.forEach((material) => material?.dispose());
  });
  scene.remove(compareObject); compareObject = null; splitCompareEnabled = false;
  elements.compareLabels.classList.add("hidden"); elements.compareButton.classList.remove("active"); elements.compareButton.textContent = "Compare";
}
elements.compareButton.addEventListener("click", async () => {
  if (splitCompareEnabled) { clearCompareObject(); return; }
  const generationId = displayedJob?.generation_id || displayedJob?.id;
  if (!generationId || !currentObject) return;
  elements.compareButton.disabled = true; elements.compareButton.textContent = "Loading original…";
  try {
    const original = await gltfLoader.loadAsync(`/api/generations/${generationId}/model?v=${Date.now()}`);
    compareObject = original.scene; scene.add(compareObject);
    const currentSphere = new THREE.Box3().setFromObject(currentObject).getBoundingSphere(new THREE.Sphere());
    const compareSphere = new THREE.Box3().setFromObject(compareObject).getBoundingSphere(new THREE.Sphere());
    if (compareSphere.radius > 1e-7) compareObject.scale.multiplyScalar(currentSphere.radius / compareSphere.radius);
    const alignedSphere = new THREE.Box3().setFromObject(compareObject).getBoundingSphere(new THREE.Sphere());
    compareObject.position.add(currentSphere.center.clone().sub(alignedSphere.center));
    splitCompareEnabled = true; elements.compareLabels.classList.remove("hidden"); elements.compareButton.classList.add("active"); elements.compareButton.textContent = "Stop compare";
  } catch (error) { clearCompareObject(); showError(`Comparison failed: ${error.message}`); }
  finally { elements.compareButton.disabled = false; }
});
elements.captureIssueButton.addEventListener("click", () => {
  if (!currentObject) return;
  elements.issuePreview.src = renderer.domElement.toDataURL("image/png");
  elements.issueDescription.value = "";
  delete elements.issueAnalyze.dataset.action;
  elements.issueAnalyze.textContent = "Run local repair check";
  elements.issueHint.textContent = "The check uses the actual mesh data. Save the screenshot too when the problem is mainly visual.";
  elements.issueDialog.classList.remove("hidden");
});
elements.issueClose.addEventListener("click", () => elements.issueDialog.classList.add("hidden"));
elements.issueSave.addEventListener("click", () => {
  const note = elements.issueDescription.value.trim() || "forge-one-view";
  const link = document.createElement("a");
  link.href = elements.issuePreview.src;
  link.download = `${note.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "").slice(0, 52) || "forge-one-view"}.png`;
  link.click();
  elements.issueHint.textContent = "Screenshot saved. Keep it with the model when you want Forge One to target a specific visible issue.";
});
elements.issueAnalyze.addEventListener("click", async () => {
  const existingAction = elements.issueAnalyze.dataset.action;
  if (existingAction) {
    elements.issueDialog.classList.add("hidden");
    const routes = {
      color: elements.colorButton, polish: elements.polishButton, game_ready: elements.gameReadyButton,
      remake: elements.remakeButton, animation: elements.animateButton,
    };
    routes[existingAction]?.click();
    return;
  }
  const generationId = displayedJob?.generation_id || displayedJob?.id;
  if (!generationId) return;
  elements.issueAnalyze.disabled = true;
  elements.issueAnalyze.textContent = "Inspecting mesh…";
  try {
    const form = new FormData(); form.append("issue", elements.issueType.value);
    const result = await api(`/api/generations/${generationId}/diagnose`, { method: "POST", body: form });
    elements.issueHint.textContent = `${result.summary} Mesh check: ${result.checks.connected_components} component(s), ${result.checks.tiny_components} tiny, ${result.checks.triangles.toLocaleString()} triangles.`;
    elements.issueAnalyze.dataset.action = result.recommended_action;
    elements.issueAnalyze.textContent = `Open suggested ${result.recommended_action.replace("_", " ")} tool`;
  } catch (error) { elements.issueHint.textContent = error.message; elements.issueAnalyze.textContent = "Retry local repair check"; }
  finally { elements.issueAnalyze.disabled = false; }
});
const paintRaycaster = new THREE.Raycaster();
const paintPointer = new THREE.Vector2();
let paint3dStroke = null;

function ensurePaintAttribute(mesh) {
  const geometry = mesh.geometry;
  const position = geometry.getAttribute("position");
  let color = geometry.getAttribute("color");
  if (!color || color.count !== position.count) {
    const values = new Float32Array(position.count * 3);
    const material = Array.isArray(mesh.material) ? mesh.material[0] : mesh.material;
    const fallback = material?.color || new THREE.Color(1, 1, 1);
    for (let index = 0; index < position.count; index += 1) {
      values[index * 3] = fallback.r; values[index * 3 + 1] = fallback.g; values[index * 3 + 2] = fallback.b;
    }
    color = new THREE.Float32BufferAttribute(values, 3);
    geometry.setAttribute("color", color);
  }
  const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
  for (const material of materials) { if (material) { material.vertexColors = true; material.needsUpdate = true; } }
  return color;
}

function capturePaintBaseline() {
  paint3dBaseline = [];
  paint3dUndoStack = [];
  paint3dEnabled = false;
  controls.enabled = true;
  elements.paint3dToggle.textContent = "Enable painting";
  elements.paint3dButton.textContent = "Paint 3D";
  elements.paint3dUndo.disabled = true;
  currentObject?.traverse((node) => {
    if (!node.isMesh || !node.geometry?.getAttribute("position")) return;
    const color = ensurePaintAttribute(node);
    paint3dBaseline.push({ mesh: node, colors: color.array.slice() });
  });
}

function rememberPaintVertex(mesh, index, color) {
  if (!paint3dStroke) return;
  let record = paint3dStroke.get(mesh.uuid);
  if (!record) {
    record = { mesh, indices: [], colors: [], seen: new Set() };
    paint3dStroke.set(mesh.uuid, record);
  }
  if (record.seen.has(index)) return;
  record.seen.add(index); record.indices.push(index);
  record.colors.push(color.getX(index), color.getY(index), color.getZ(index));
}

function paintIntersection(intersection) {
  const mesh = intersection.object;
  const position = mesh.geometry.getAttribute("position");
  const color = ensurePaintAttribute(mesh);
  const target = new THREE.Color(elements.paint3dColor.value);
  const point = mesh.worldToLocal(intersection.point.clone());
  if (elements.paint3dTool.value === "region") {
    const face = intersection.face;
    if (!face) return;
    const seed = new THREE.Color(
      (color.getX(face.a) + color.getX(face.b) + color.getX(face.c)) / 3,
      (color.getY(face.a) + color.getY(face.b) + color.getY(face.c)) / 3,
      (color.getZ(face.a) + color.getZ(face.b) + color.getZ(face.c)) / 3,
    );
    const tolerance = Number(elements.paint3dTolerance.value) / 255;
    for (let index = 0; index < color.count; index += 1) {
      const difference = Math.hypot(color.getX(index) - seed.r, color.getY(index) - seed.g, color.getZ(index) - seed.b);
      if (difference <= tolerance) {
        rememberPaintVertex(mesh, index, color);
        color.setXYZ(index, target.r, target.g, target.b);
      }
    }
  } else {
    if (!mesh.geometry.boundingSphere) mesh.geometry.computeBoundingSphere();
    const radius = Math.max(mesh.geometry.boundingSphere.radius * Number(elements.paint3dSize.value) / 100, 1e-5);
    const candidate = new THREE.Vector3();
    for (let index = 0; index < position.count; index += 1) {
      candidate.fromBufferAttribute(position, index);
      const distance = candidate.distanceTo(point);
      if (distance <= radius) {
        rememberPaintVertex(mesh, index, color);
        const weight = THREE.MathUtils.smoothstep(1 - distance / radius, 0, 1);
        color.setXYZ(
          index,
          THREE.MathUtils.lerp(color.getX(index), target.r, weight),
          THREE.MathUtils.lerp(color.getY(index), target.g, weight),
          THREE.MathUtils.lerp(color.getZ(index), target.b, weight),
        );
      }
    }
  }
  color.needsUpdate = true;
}

function paint3dFromPointer(event) {
  if (!paint3dEnabled || !currentObject) return;
  const rect = renderer.domElement.getBoundingClientRect();
  paintPointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  paintPointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  paintRaycaster.setFromCamera(paintPointer, camera);
  const intersection = paintRaycaster.intersectObject(currentObject, true).find((hit) => hit.object.isMesh);
  if (intersection) paintIntersection(intersection);
}

renderer.domElement.addEventListener("pointerdown", (event) => {
  if (!paint3dEnabled || event.button !== 0) return;
  event.preventDefault(); paint3dDrawing = true; paint3dStroke = new Map();
  renderer.domElement.setPointerCapture(event.pointerId); paint3dFromPointer(event);
});
renderer.domElement.addEventListener("pointermove", (event) => { if (paint3dDrawing && elements.paint3dTool.value === "brush") paint3dFromPointer(event); });
renderer.domElement.addEventListener("pointerup", () => {
  if (!paint3dDrawing) return;
  paint3dDrawing = false;
  const records = paint3dStroke ? [...paint3dStroke.values()].filter((record) => record.indices.length) : [];
  if (records.length) { paint3dUndoStack.push(records); elements.paint3dUndo.disabled = false; elements.paint3dStatus.textContent = "Paint applied to the viewer copy. Undo, continue painting, or download the GLB."; }
  paint3dStroke = null;
});
renderer.domElement.addEventListener("pointercancel", () => { paint3dDrawing = false; paint3dStroke = null; });
elements.paint3dButton.addEventListener("click", () => {
  if (!currentObject) return;
  elements.paint3dDialog.classList.remove("hidden");
});
elements.paint3dClose.addEventListener("click", () => { paint3dEnabled = false; controls.enabled = true; elements.paint3dToggle.textContent = "Enable painting"; elements.paint3dButton.textContent = "Paint 3D"; elements.paint3dDialog.classList.add("hidden"); });
elements.paint3dToggle.addEventListener("click", () => {
  paint3dEnabled = !paint3dEnabled; controls.enabled = !paint3dEnabled;
  elements.paint3dToggle.textContent = paint3dEnabled ? "Painting enabled — drag on model" : "Enable painting";
  elements.paint3dStatus.textContent = paint3dEnabled ? "Painting is active. Disable it whenever you want to rotate the model." : "Navigation restored. Rotate the model, then enable painting again.";
  elements.paint3dButton.textContent = paint3dEnabled ? "Painting active" : "Paint 3D";
  if (paint3dEnabled) elements.paint3dDialog.classList.add("hidden");
});
elements.paint3dUndo.addEventListener("click", () => {
  const records = paint3dUndoStack.pop();
  if (!records) return;
  for (const record of records) {
    const color = record.mesh.geometry.getAttribute("color");
    record.indices.forEach((index, offset) => color.setXYZ(index, record.colors[offset * 3], record.colors[offset * 3 + 1], record.colors[offset * 3 + 2]));
    color.needsUpdate = true;
  }
  elements.paint3dUndo.disabled = paint3dUndoStack.length === 0;
  elements.paint3dStatus.textContent = "Last paint stroke undone.";
});
elements.paint3dReset.addEventListener("click", () => {
  for (const baseline of paint3dBaseline) {
    const color = baseline.mesh.geometry.getAttribute("color"); color.array.set(baseline.colors); color.needsUpdate = true;
  }
  paint3dUndoStack = []; elements.paint3dUndo.disabled = true; elements.paint3dStatus.textContent = "Paint reset to the loaded model.";
});
elements.paint3dDownload.addEventListener("click", async () => {
  if (!currentObject) return;
  elements.paint3dDownload.disabled = true; elements.paint3dStatus.textContent = "Packaging painted GLB…";
  try {
    const binary = await new GLTFExporter().parseAsync(currentObject, { binary: true, onlyVisible: true });
    const link = document.createElement("a"); link.href = URL.createObjectURL(new Blob([binary], { type: "model/gltf-binary" })); link.download = "forge-one-painted.glb"; link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000); elements.paint3dStatus.textContent = "Painted GLB downloaded. The loaded original remains available in the library.";
  } catch (error) { elements.paint3dStatus.textContent = `Painted export failed: ${error.message}`; }
  finally { elements.paint3dDownload.disabled = false; }
});
elements.versionsButton.addEventListener("click", async () => {
  const generationId = displayedJob?.generation_id || displayedJob?.id;
  if (!generationId) return;
  elements.versionsList.innerHTML = `<p class="animate-note">Loading saved versions…</p>`;
  elements.versionsDialog.classList.remove("hidden");
  try {
    const result = await api(`/api/generations/${generationId}/versions`);
    elements.versionsList.replaceChildren();
    for (const version of [...result.versions].reverse()) {
      const item = document.createElement("article"); item.className = "version-item";
      const information = document.createElement("div");
      const title = document.createElement("strong"); title.textContent = version.label;
      const details = document.createElement("small");
      details.textContent = `${version.triangles.toLocaleString()} triangles · ${formatBytes(version.file_size)} · ${new Date(version.created_at).toLocaleString()}`;
      information.append(title, details);
      const view = document.createElement("button"); view.type = "button"; view.className = "tool"; view.textContent = version.kind === "original" ? "View original" : "Compare view";
      view.addEventListener("click", async () => {
        await loadModel({
          ...displayedJob, generation_id: generationId, backend: `${displayedJob.backend} · ${version.label}`,
          model_url: version.model_url, download_url: version.download_url, vertices: version.vertices,
          triangles: version.triangles, file_size: version.file_size, updated_at: Date.now(),
        });
        elements.versionsDialog.classList.add("hidden");
      });
      const download = document.createElement("a"); download.className = "tool"; download.textContent = "Download"; download.href = version.download_url; download.download = "";
      item.append(information, view, download); elements.versionsList.append(item);
    }
  } catch (error) { elements.versionsList.textContent = error.message; }
});
elements.versionsClose.addEventListener("click", () => elements.versionsDialog.classList.add("hidden"));
window.addEventListener("keydown", (event) => {
  if (event.target.matches("input, textarea, select")) return;
  if (event.key === "+" || event.key === "=") zoomViewer(0.78);
  if (event.key === "-") zoomViewer(1.28);
  if (event.key.toLowerCase() === "f" && currentObject) frameObject(currentObject);
});

elements.profileButton.addEventListener("click", openProfile);
elements.profileNavButton.addEventListener("click", openProfile);
elements.colorButton.addEventListener("click", async () => {
  const generationId = displayedJob?.generation_id || displayedJob?.id;
  const hasSource = Boolean(generationId) && displayedJob?.source_image_id !== null && displayedJob?.backend !== "Imported GLB";
  colorOriginalJob = displayedJob ? { ...displayedJob } : null;
  elements.colorModelHint.textContent = hasSource
    ? "The 3D shape stays unchanged. Material color transfer isolates the object from its backdrop and retains useful surface character without rebuilding the mesh."
    : generationId ? "Imported GLBs need a saved source photo before Forge One can match their color." : "Open a generated model from the workspace or library first.";
  elements.startColorButton.disabled = !hasSource;
  elements.colorDownloads.classList.add("hidden");
  elements.colorStatus.classList.add("hidden");
  if (hasSource) {
    const colorSourceUrl = `/api/generations/${generationId}/source-image?v=${Date.now()}`;
    elements.colorSourcePreview.src = colorSourceUrl;
    loadPaintMap(colorSourceUrl);
    try { showColorStatus(await api(`/api/generations/${generationId}/color`)); } catch {}
  } else {
    elements.colorSourcePreview.removeAttribute("src");
  }
  elements.colorDialog.classList.remove("hidden");
});
elements.colorClose.addEventListener("click", () => { elements.colorDialog.classList.add("hidden"); clearTimeout(colorPollTimer); });
elements.animateButton.addEventListener("click", () => {
  const generationId = displayedJob?.generation_id || displayedJob?.id;
  elements.animateModelHint.textContent = generationId
    ? "Selected model is ready for a local Blender auto-rig. Choose a motion, confirm it is a full-body humanoid, and begin."
    : "Open a generated model from the workspace or library first. Forge One will then prepare it locally in Blender."
  elements.startAnimationButton.disabled = !generationId && !animationImageFile;
  elements.animateDialog.classList.remove("hidden");
});
elements.animateClose.addEventListener("click", () => { elements.animateDialog.classList.add("hidden"); clearTimeout(animationPollTimer); });
elements.profileClose.addEventListener("click", () => elements.profileDialog.classList.add("hidden"));
elements.profileForm.addEventListener("submit", (event) => { event.preventDefault(); submitProfile("/api/profiles"); });
elements.loginButton.addEventListener("click", () => submitProfile("/api/profiles/login"));
elements.logoutButton.addEventListener("click", async () => { await api("/api/profiles/logout", { method: "POST" }); setProfile(null); elements.profileDialog.classList.add("hidden"); await loadLibrary(); });
elements.libraryButton.addEventListener("click", async () => { elements.libraryDrawer.classList.remove("hidden"); await loadLibrary(); });
elements.libraryClose.addEventListener("click", () => elements.libraryDrawer.classList.add("hidden"));
elements.librarySearch.addEventListener("input", () => loadLibrary());
elements.newFolderButton.addEventListener("click", async () => {
  const name = window.prompt("Name your new folder");
  if (name === null || !name.trim()) return;
  try {
    const form = new FormData(); form.append("name", name.trim());
    await api("/api/library/folders", { method: "POST", body: form });
    await loadLibrary();
  } catch (error) { showError(error.message); }
});

function selectAnimationImage(file) {
  if (!file || !["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
    elements.animationStatus.textContent = "Choose a PNG, JPG/JPEG, or WebP character photo.";
    elements.animationStatus.classList.remove("hidden");
    return;
  }
  animationImageFile = file;
  elements.animationImagePreview.src = URL.createObjectURL(file);
  elements.animationImagePreview.classList.add("visible");
  elements.animationDropPrompt.classList.add("hidden");
  elements.animateModelHint.textContent = `“${file.name}” will be rebuilt into a 3D character, then auto-rigged locally.`;
  elements.startAnimationButton.disabled = false;
  elements.startAnimationButton.textContent = "Build and animate photo";
}
elements.animationFileInput.addEventListener("change", () => selectAnimationImage(elements.animationFileInput.files[0]));
elements.animationDropZone.addEventListener("click", () => elements.animationFileInput.click());
elements.animationDropZone.addEventListener("dragover", (event) => { event.preventDefault(); elements.animationDropZone.classList.add("dragging"); });
elements.animationDropZone.addEventListener("dragleave", () => elements.animationDropZone.classList.remove("dragging"));
elements.animationDropZone.addEventListener("drop", (event) => {
  event.preventDefault(); elements.animationDropZone.classList.remove("dragging"); selectAnimationImage(event.dataTransfer.files[0]);
});
elements.animationDropZone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") elements.animationFileInput.click();
});

document.querySelectorAll("[data-motion]").forEach((button) => button.addEventListener("click", () => {
  selectedMotion = button.dataset.motion;
  document.querySelectorAll("[data-motion]").forEach((item) => item.classList.toggle("selected", item === button));
}));

function showColorStatus(color) {
  elements.colorStatus.classList.remove("hidden");
  elements.colorStatus.textContent = color.message || (color.status === "complete" ? "Color ready." : "Preparing color…");
  if (color.status === "complete") {
    readyColor = color;
    elements.colorDownload.href = color.download_url;
    elements.colorDownloads.classList.remove("hidden");
    elements.startColorButton.disabled = false;
    elements.startColorButton.textContent = "Reapply material color";
  } else if (color.status === "failed") {
    elements.startColorButton.disabled = false;
    elements.startColorButton.textContent = "Try material color again";
  }
}

async function pollColor(generationId) {
  clearTimeout(colorPollTimer);
  try {
    const color = await api(`/api/generations/${generationId}/color`);
    showColorStatus(color);
    if (["queued", "running"].includes(color.status)) colorPollTimer = setTimeout(() => pollColor(generationId), 700);
  } catch (error) {
    elements.startColorButton.disabled = false;
    elements.colorStatus.textContent = error.message;
  }
}

elements.startColorButton.addEventListener("click", async () => {
  const generationId = displayedJob?.generation_id || displayedJob?.id;
  if (!generationId) return;
  clearError();
  const isDetailProjection = elements.colorStyle.value === "detail";
  elements.startColorButton.disabled = true;
  elements.startColorButton.textContent = isDetailProjection ? "Projecting photo details…" : "Applying material color…";
  elements.colorStatus.classList.remove("hidden");
  elements.colorStatus.textContent = isDetailProjection
    ? "Projecting exact photo detail onto the fixed model…"
    : "Isolating the object and transferring its material color without changing the model…";
  try {
    const form = new FormData();
    form.append("brightness", String(Number(elements.colorBrightness.value) / 100));
    form.append("saturation", String(Number(elements.colorSaturation.value) / 100));
    form.append("coverage", String(Number(elements.colorCoverage.value) / 100));
    form.append("style", elements.colorStyle.value);
    const palettePanel = document.querySelector(".color-palette");
    if (palettePanel?.open) {
      form.append("palette", JSON.stringify([
        elements.paletteShadow.value,
        elements.paletteBase.value,
        elements.paletteHighlight.value,
      ]));
    }
    if (paintGuides.length) form.append("paint_guides", JSON.stringify(paintGuides));
    showColorStatus(await api(`/api/generations/${generationId}/color`, { method: "POST", body: form }));
    pollColor(generationId);
  } catch (error) {
    elements.startColorButton.disabled = false;
    elements.startColorButton.textContent = "Apply material color";
    elements.colorStatus.textContent = error.message;
  }
});
elements.colorStyle.addEventListener("change", () => {
  const isDetailProjection = elements.colorStyle.value === "detail";
  elements.colorStyleNote.textContent = isDetailProjection
    ? "Uses a sharper photo projection. Choose this only when the generated shape already matches the photo closely."
    : "Keeps material character such as wood grain and fabric while allowing for small shape differences. Best for most models.";
  elements.startColorButton.textContent = isDetailProjection ? "Apply photo detail" : "Apply material color";
});

elements.previewColorButton.addEventListener("click", async () => {
  if (!readyColor || !displayedJob) return;
  try {
    await loadModel({
      ...displayedJob,
      backend: `${displayedJob.backend} · Color`,
      model_url: readyColor.model_url,
      download_url: readyColor.download_url,
      geometry_master: colorOriginalJob,
      updated_at: Date.now(),
    });
    elements.colorDialog.classList.add("hidden");
  } catch (error) { showError(error.message); }
});
elements.showGeometryButton.addEventListener("click", async () => {
  if (!colorOriginalJob) return;
  try { await loadModel(colorOriginalJob); elements.colorDialog.classList.add("hidden"); }
  catch (error) { showError(error.message); }
});
elements.bakeTextureButton.addEventListener("click", async () => {
  const generationId = displayedJob?.generation_id || displayedJob?.id;
  if (!generationId) return;
  elements.bakeTextureButton.disabled = true;
  elements.bakeTextureButton.textContent = "Baking UV texture…";
  elements.colorStatus.classList.remove("hidden");
  elements.colorStatus.textContent = "Blender is creating UVs, baking a 1024px texture, and reloading the exported GLB for validation…";
  try {
    const form = new FormData(); form.append("resolution", "1024");
    const result = await api(`/api/generations/${generationId}/texture-bake`, { method: "POST", body: form });
    elements.colorStatus.textContent = result.message;
    await loadModel({
      ...displayedJob, backend: `${displayedJob.backend} · UV Texture`, model_url: result.model_url,
      download_url: result.download_url, file_size: result.file_size, updated_at: Date.now(), geometry_master: colorOriginalJob,
    });
    elements.colorDialog.classList.add("hidden");
  } catch (error) { elements.colorStatus.textContent = error.message; }
  finally { elements.bakeTextureButton.disabled = false; elements.bakeTextureButton.textContent = "Bake 1K texture GLB"; }
});
[[elements.colorBrightness, elements.colorBrightnessValue], [elements.colorSaturation, elements.colorSaturationValue], [elements.colorCoverage, elements.colorCoverageValue]].forEach(([input, output]) => {
  input.addEventListener("input", () => { output.value = `${input.value}%`; output.textContent = `${input.value}%`; });
});

function showAnimationStatus(animation) {
  elements.animationStatus.classList.remove("hidden");
  elements.animationStatus.textContent = animation.message || (animation.status === "complete" ? "Animation ready." : "Preparing local animation…");
  if (animation.status === "complete") {
    readyAnimation = animation;
    elements.animationGlbDownload.href = animation.model_url;
    elements.animationBlendDownload.href = animation.blend_url;
    elements.animationDownloads.classList.remove("hidden");
    elements.startAnimationButton.disabled = false;
    elements.startAnimationButton.textContent = "Animation ready";
  } else if (animation.status === "failed") {
    elements.startAnimationButton.disabled = false;
    elements.startAnimationButton.textContent = "Try local animation again";
  }
}

async function pollAnimation(generationId) {
  clearTimeout(animationPollTimer);
  try {
    const animation = await api(`/api/generations/${generationId}/animation/${selectedMotion}`);
    showAnimationStatus(animation);
    if (["queued", "running"].includes(animation.status)) animationPollTimer = setTimeout(() => pollAnimation(generationId), 1000);
  } catch (error) {
    elements.startAnimationButton.disabled = false;
    showError(error.message);
  }
}

async function pollPhotoAnimation(generationId) {
  clearTimeout(animationPollTimer);
  try {
    const job = await api(`/api/generations/${generationId}`);
    elements.animationStatus.classList.remove("hidden");
    elements.animationStatus.textContent = job.message;
    if (job.status === "complete") {
      await loadModel(job);
      elements.animateModelHint.textContent = "3D character complete. Blender is now building the selected motion.";
      pollAnimation(generationId);
      return;
    }
    if (["failed", "cancelled"].includes(job.status)) {
      elements.startAnimationButton.disabled = false;
      elements.startAnimationButton.textContent = "Build and animate photo";
      elements.animationStatus.textContent = job.message;
      return;
    }
    animationPollTimer = setTimeout(() => pollPhotoAnimation(generationId), 1000);
  } catch (error) {
    elements.startAnimationButton.disabled = false;
    elements.startAnimationButton.textContent = "Build and animate photo";
    elements.animationStatus.textContent = error.message;
  }
}

elements.startAnimationButton.addEventListener("click", async () => {
  const generationId = displayedJob?.generation_id || displayedJob?.id;
  if (!elements.humanoidConfirm.checked) {
    elements.animationStatus.textContent = "Confirm that this is a complete upright humanoid before automatic rigging.";
    elements.animationStatus.classList.remove("hidden");
    return;
  }
  clearError();
  elements.animationDownloads.classList.add("hidden");
  elements.animationStatus.classList.remove("hidden");
  elements.animationStatus.textContent = animationImageFile ? "Queueing local 3D character reconstruction…" : "Queueing local Blender auto-rig…";
  elements.startAnimationButton.disabled = true;
  elements.startAnimationButton.textContent = animationImageFile ? "Building 3D character…" : "Preparing animation…";
  try {
    if (animationImageFile) {
      const form = new FormData();
      form.append("image", animationImageFile);
      form.append("mode", elements.animationQuality.value);
      form.append("detail", elements.animationQuality.value === "Quality" ? "Sharp" : "Balanced");
      form.append("trim", "Clean");
      form.append("auto_animate_motion", selectedMotion);
      form.append("auto_animate_full_body", "true");
      const job = await api("/api/generations", { method: "POST", body: form });
      activeGeneration = job;
      pollPhotoAnimation(job.id);
      return;
    }
    if (!generationId) throw new Error("Drop a full-body character photo or open a generated model first.");
    const form = new FormData();
    form.append("motion", selectedMotion);
    form.append("full_body_humanoid", "true");
    showAnimationStatus(await api(`/api/generations/${generationId}/animation`, { method: "POST", body: form }));
    pollAnimation(generationId);
  } catch (error) {
    elements.startAnimationButton.disabled = false;
    elements.startAnimationButton.textContent = animationImageFile ? "Build and animate photo" : "Create local animation";
    elements.animationStatus.textContent = error.message;
  }
});

elements.previewAnimationButton.addEventListener("click", async () => {
  if (!readyAnimation || !displayedJob) return;
  try {
    await loadModel({
      ...displayedJob,
      backend: `Animated ${readyAnimation.motion}`,
      model_url: readyAnimation.model_url,
      download_url: readyAnimation.model_url,
      updated_at: Date.now(),
    });
    elements.animateDialog.classList.add("hidden");
  } catch (error) { showError(error.message); }
});

elements.animationPlayButton.addEventListener("click", () => {
  if (!currentAction) { elements.animationStatus.textContent = "Preview an animated GLB first."; elements.animationStatus.classList.remove("hidden"); return; }
  currentAction.paused = !currentAction.paused;
  elements.animationPlayButton.textContent = currentAction.paused ? "Play" : "Pause";
});
elements.animationSpeed.addEventListener("change", () => { if (currentMixer) currentMixer.timeScale = Number(elements.animationSpeed.value); });
elements.animationLoop.addEventListener("change", () => {
  if (!currentAction) return;
  currentAction.setLoop(elements.animationLoop.checked ? THREE.LoopRepeat : THREE.LoopOnce, elements.animationLoop.checked ? Infinity : 1);
  currentAction.clampWhenFinished = !elements.animationLoop.checked;
  if (!currentAction.isRunning()) currentAction.reset().play();
});

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
  elements.editMaskButton.disabled = false;
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

elements.textToImageButton.addEventListener("click", () => {
  clearError();
  elements.textToImageDialog.classList.remove("hidden");
  elements.textPrompt.focus();
});
elements.textToImageClose.addEventListener("click", () => elements.textToImageDialog.classList.add("hidden"));
document.querySelectorAll("[data-prompt]").forEach((button) => button.addEventListener("click", () => {
  elements.textPrompt.value = button.dataset.prompt || "";
  elements.textPrompt.focus();
}));
elements.textToImageForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const prompt = elements.textPrompt.value.trim();
  const batchText = document.getElementById("batchPromptList").value;
  const batchPrompts = batchText.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (batchPrompts.length < 2 && prompt.length < 3) {
    showError("Describe one object, or add at least two objects in the batch list.");
    return;
  }
  clearError();
  elements.startTextToImageButton.disabled = true;
  elements.startTextToImageButton.textContent = "Starting local image AI…";
  elements.cancelButton.classList.remove("hidden");
  elements.statusCard.classList.remove("hidden");
  elements.viewerTitle.textContent = "Text → image → 3D";
  try {
    const form = new FormData();
    if (batchPrompts.length >= 2) form.append("prompts", batchText);
    else form.append("prompt", prompt);
    form.append("mode", selectedMode);
    form.append("detail", elements.detailSelect.value); form.append("trim", elements.trimSelect.value);
    form.append("auto_color", String(elements.colorFinishSelect.value === "now"));
    form.append("subject_mode", elements.subjectModeSelect.value);
    const response = await api(batchPrompts.length >= 2 ? "/api/text-to-model/batch" : "/api/text-to-model", { method: "POST", body: form });
    if (batchPrompts.length >= 2) {
      batchGenerationIds = response.jobs.map((job) => job.id);
      activeGeneration = response.jobs[0];
    } else {
      batchGenerationIds = [];
      activeGeneration = response;
    }
    localStorage.setItem("activeGenerationId", activeGeneration.id);
    elements.textToImageDialog.classList.add("hidden");
    updateStatus(activeGeneration);
    if (batchGenerationIds.length) pollBatchGeneration(); else pollGeneration();
  } catch (error) {
    showError(error.message);
    elements.cancelButton.classList.add("hidden");
  } finally {
    elements.startTextToImageButton.disabled = false;
    elements.startTextToImageButton.textContent = "Create image + 3D model";
  }
});

elements.fileInput.addEventListener("change", () => selectFile(elements.fileInput.files[0]));
elements.sideFileInput.addEventListener("change", () => { sideFile = elements.sideFileInput.files[0] || null; });
elements.backFileInput.addEventListener("change", () => { backFile = elements.backFileInput.files[0] || null; });
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

elements.importGlbButton.addEventListener("click", () => elements.importGlbInput.click());
elements.importGlbInput.addEventListener("change", async () => {
  const model = elements.importGlbInput.files[0];
  if (!model) return;
  clearError(); elements.importGlbButton.disabled = true; elements.importGlbButton.textContent = "Importing…";
  try {
    const form = new FormData(); form.append("model", model);
    const job = await api("/api/imports", { method: "POST", body: form });
    activeGeneration = job; localStorage.setItem("activeGenerationId", job.id); await loadModel(job);
    if (profile) await loadLibrary();
  } catch (error) { showError(error.message); }
  finally { elements.importGlbButton.disabled = false; elements.importGlbButton.textContent = "Import GLB"; elements.importGlbInput.value = ""; }
});

function maskPoint(event) {
  const rect = elements.maskCanvas.getBoundingClientRect();
  return { x: (event.clientX - rect.left) * elements.maskCanvas.width / rect.width, y: (event.clientY - rect.top) * elements.maskCanvas.height / rect.height };
}
function paintMask(event) {
  if (!maskDrawing || !maskOriginalCanvas) return;
  const { x, y } = maskPoint(event); const radius = Number(elements.maskBrush.value) / 2;
  const ctx = elements.maskCanvas.getContext("2d");
  if (maskMode === "erase") {
    ctx.save(); ctx.globalCompositeOperation = "destination-out"; ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.fill(); ctx.restore();
  } else {
    ctx.save(); ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.clip(); ctx.drawImage(maskOriginalCanvas, 0, 0); ctx.restore();
  }
}
elements.editMaskButton.addEventListener("click", async () => {
  if (!selectedFile) return;
  const image = await createImageBitmap(selectedFile);
  const scale = Math.min(1, 760 / image.width, 620 / image.height);
  elements.maskCanvas.width = Math.max(1, Math.round(image.width * scale)); elements.maskCanvas.height = Math.max(1, Math.round(image.height * scale));
  maskOriginalCanvas = document.createElement("canvas"); maskOriginalCanvas.width = elements.maskCanvas.width; maskOriginalCanvas.height = elements.maskCanvas.height;
  maskOriginalCanvas.getContext("2d").drawImage(image, 0, 0, maskOriginalCanvas.width, maskOriginalCanvas.height);
  elements.maskCanvas.getContext("2d").drawImage(maskOriginalCanvas, 0, 0); image.close();
  elements.maskDialog.classList.remove("hidden");
});
elements.maskClose.addEventListener("click", () => elements.maskDialog.classList.add("hidden"));
elements.maskEraseButton.addEventListener("click", () => { maskMode = "erase"; elements.maskEraseButton.classList.add("active"); elements.maskRestoreButton.classList.remove("active"); });
elements.maskRestoreButton.addEventListener("click", () => { maskMode = "restore"; elements.maskRestoreButton.classList.add("active"); elements.maskEraseButton.classList.remove("active"); });
elements.maskCanvas.addEventListener("pointerdown", (event) => { maskDrawing = true; elements.maskCanvas.setPointerCapture(event.pointerId); paintMask(event); });
elements.maskCanvas.addEventListener("pointermove", paintMask);
elements.maskCanvas.addEventListener("pointerup", () => { maskDrawing = false; });
elements.maskCanvas.addEventListener("pointercancel", () => { maskDrawing = false; });
elements.maskApplyButton.addEventListener("click", () => {
  elements.maskCanvas.toBlob((blob) => {
    if (!blob) return;
    selectFile(new File([blob], `${selectedFile?.name?.replace(/\.[^.]+$/, "") || "cleaned"}-masked.png`, { type: "image/png" }));
    elements.maskDialog.classList.add("hidden");
  }, "image/png");
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
  form.append("detail", elements.detailSelect.value);
  form.append("trim", elements.trimSelect.value);
  form.append("auto_color", String(elements.colorFinishSelect.value === "now"));
  form.append("subject_mode", elements.subjectModeSelect.value);
  if (sideFile) form.append("side_image", sideFile);
  if (backFile) form.append("back_image", backFile);
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
      if (activeGeneration.text_prompt) {
        elements.imagePreview.src = `/api/generations/${activeGeneration.id}/source-image?v=${Date.now()}`;
        elements.imagePreview.classList.add("visible");
        elements.dropPrompt.classList.add("hidden");
      }
      elements.generateButton.disabled = !selectedFile;
      await loadModel(activeGeneration);
      if (activeGeneration.auto_color) {
        elements.viewerTitle.textContent = "Shape ready · applying color automatically";
        pollAutomaticColor({ ...activeGeneration });
      }
      if (activeGeneration.candidate_of) {
        remakeCandidate = activeGeneration;
        elements.restoreOriginalButton.classList.remove("hidden");
        elements.keepRemakeButton.classList.remove("hidden");
        elements.viewerTitle.textContent = "Remake candidate — compare before keeping";
      } else if (profile) await loadLibrary();
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

async function pollBatchGeneration() {
  clearTimeout(batchPollTimer);
  if (!batchGenerationIds.length) return;
  try {
    const jobs = await Promise.all(batchGenerationIds.map((id) => api(`/api/generations/${id}`)));
    const finished = jobs.filter((job) => ["complete", "failed", "cancelled"].includes(job.status));
    const current = jobs.find((job) => ["running", "queued"].includes(job.status));
    activeGeneration = current || jobs[jobs.length - 1];
    updateStatus({
      status: finished.length === jobs.length ? "complete" : "running",
      mode: "Batch", backend: `${finished.length}/${jobs.length} complete`,
      progress: Math.round(finished.length / jobs.length * 100),
      message: current ? `Making ${finished.length + 1} of ${jobs.length}: ${current.message}` : "Batch finished.",
    });
    if (finished.length === jobs.length) {
      elements.cancelButton.classList.add("hidden");
      batchGenerationIds = [];
      const newestModel = [...jobs].reverse().find((job) => job.status === "complete");
      if (newestModel) {
        activeGeneration = newestModel;
        localStorage.setItem("activeGenerationId", newestModel.id);
        await loadModel(newestModel);
      }
      if (profile) await loadLibrary();
      return;
    }
    batchPollTimer = setTimeout(pollBatchGeneration, 1200);
  } catch (error) {
    showError(error.message);
    batchPollTimer = setTimeout(pollBatchGeneration, 2200);
  }
}

async function pollAutomaticColor(geometryJob) {
  clearTimeout(colorPollTimer);
  const generationId = geometryJob.generation_id || geometryJob.id;
  try {
    const color = await api(`/api/generations/${generationId}/color`);
    if (["queued", "running"].includes(color.status)) {
      elements.viewerTitle.textContent = "Shape ready · applying color automatically";
      colorPollTimer = setTimeout(() => pollAutomaticColor(geometryJob), 700);
      return;
    }
    if (color.status === "complete") {
      readyColor = color;
      await loadModel({
        ...geometryJob,
        backend: `${geometryJob.backend} · Color`,
        model_url: color.model_url,
        download_url: color.download_url,
        geometry_master: geometryJob,
        updated_at: Date.now(),
      });
      return;
    }
    showError(`Geometry is ready, but automatic color did not complete: ${color.message}`);
  } catch (error) { showError(`Geometry is ready, but automatic color could not start: ${error.message}`); }
}

elements.generateButton.addEventListener("click", startGeneration);
elements.cancelButton.addEventListener("click", async () => {
  if (!activeGeneration) return;
  try {
    if (batchGenerationIds.length) {
      await Promise.all(batchGenerationIds.map((id) => api(`/api/generations/${id}/cancel`, { method: "POST" }).catch(() => null)));
      elements.statusMessage.textContent = "Cancelling the remaining batch safely…";
      return;
    }
    activeGeneration = await api(`/api/generations/${activeGeneration.id}/cancel`, { method: "POST" });
    updateStatus(activeGeneration);
  } catch (error) { showError(error.message); }
});

function disposeCurrent() {
  clearCompareObject();
  if (!currentObject) return;
  currentMixer = null;
  currentAction = null;
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

async function clearWorkspace() {
  const active = activeGeneration && ["queued", "running"].includes(activeGeneration.status);
  const message = active
    ? "Clear this workspace and cancel the generation? Saved models will not be removed."
    : "Clear this workspace? Saved models will not be removed.";
  if (!window.confirm(message)) return;
  if (active) {
    try { await api(`/api/generations/${activeGeneration.id}/cancel`, { method: "POST" }); } catch {}
  }
  clearTimeout(pollTimer);
  disposeCurrent();
  selectedFile = null; sideFile = null; backFile = null; activeGeneration = null; remakeGenerationId = null; remakeOriginal = null; remakeCandidate = null; displayedJob = null; gameReadyOriginalJob = null; readyGameReady = null;
  clearTimeout(gameReadyPollTimer);
  localStorage.removeItem("activeGenerationId");
  elements.fileInput.value = "";
  elements.sideFileInput.value = ""; elements.backFileInput.value = ""; elements.colorFinishSelect.value = "later"; elements.subjectModeSelect.value = "General";
  elements.imagePreview.removeAttribute("src");
  elements.imagePreview.classList.remove("visible");
  elements.dropPrompt.classList.remove("hidden");
  elements.statusCard.classList.add("hidden"); elements.cancelButton.classList.add("hidden"); clearError();
  elements.emptyState.classList.remove("hidden"); elements.viewerTitle.textContent = "Waiting for an image";
  elements.generateButton.disabled = true; elements.generateButton.textContent = "Generate model";
  elements.editMaskButton.disabled = true;
  [elements.fullscreenButton, elements.studioButton, elements.snapshotButton, elements.gridButton, elements.wireButton, elements.resetButton, elements.frontViewButton, elements.sideViewButton, elements.removeColorButton, elements.polishButton, elements.remakeButton, elements.gameReadyButton].forEach((button) => { button.disabled = true; });
  elements.moreTools.classList.add("is-disabled"); elements.moreTools.open = false;
  elements.restoreOriginalButton.classList.add("hidden"); elements.keepRemakeButton.classList.add("hidden");
  [elements.vertices, elements.triangles, elements.fileSize, elements.elapsed].forEach((metric) => { metric.textContent = "—"; });
  elements.downloadButton.removeAttribute("href"); elements.downloadButton.textContent = "Download GLB"; elements.downloadButton.classList.add("disabled"); elements.downloadButton.setAttribute("aria-disabled", "true");
  elements.exportFormat.value = "glb"; elements.exportFormat.disabled = true;
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
    const cacheSeparator = String(job.model_url).includes("?") ? "&" : "?";
    const gltf = await gltfLoader.loadAsync(`${job.model_url}${cacheSeparator}v=${job.updated_at}`);
    disposeCurrent();
    currentObject = gltf.scene;
    currentObject.traverse((node) => {
      if (node.isMesh) {
        node.castShadow = true;
        node.receiveShadow = true;
      }
    });
    scene.add(currentObject);
    capturePaintBaseline();
    frameObject(currentObject);
    if (gltf.animations.length) {
      currentMixer = new THREE.AnimationMixer(currentObject);
      currentAction = currentMixer.clipAction(gltf.animations[0]);
      currentAction.setLoop(elements.animationLoop.checked ? THREE.LoopRepeat : THREE.LoopOnce, elements.animationLoop.checked ? Infinity : 1);
      currentAction.clampWhenFinished = !elements.animationLoop.checked;
      currentAction.reset().play(); currentMixer.timeScale = Number(elements.animationSpeed.value);
      elements.animationPlayButton.textContent = "Pause";
      elements.viewerTitle.textContent = `${job.backend} preview · playing`;
    } else {
      elements.viewerTitle.textContent = `Generated ${job.backend} mesh`;
    }
    elements.vertices.textContent = Number.isFinite(job.vertices) ? job.vertices.toLocaleString() : "—";
    elements.triangles.textContent = Number.isFinite(job.triangles) ? job.triangles.toLocaleString() : "—";
    elements.fileSize.textContent = formatBytes(job.file_size);
    elements.elapsed.textContent = Number.isFinite(job.elapsed_seconds) ? `${job.elapsed_seconds.toFixed(1)} s` : "—";
    elements.downloadButton.href = job.download_url;
    elements.exportFormat.value = "glb";
    elements.exportFormat.disabled = !job.id;
    elements.downloadButton.textContent = "Download GLB";
    elements.downloadButton.classList.remove("disabled");
    elements.downloadButton.removeAttribute("aria-disabled");
    elements.wireButton.disabled = false;
    elements.resetButton.disabled = false;
    elements.frontViewButton.disabled = false;
    elements.sideViewButton.disabled = false;
    [elements.fullscreenButton, elements.studioButton, elements.snapshotButton, elements.gridButton].forEach((button) => { button.disabled = false; });
    elements.moreTools.classList.remove("is-disabled");
    [elements.zoomInButton, elements.zoomOutButton, elements.compareButton, elements.paint3dButton, elements.captureIssueButton, elements.versionsButton, elements.turntableButton, elements.backgroundButton, elements.saveViewButton, elements.restoreViewButton].forEach((button) => { button.disabled = false; });
    elements.polishButton.disabled = !job.id && !job.generation_id;
    elements.gameReadyButton.disabled = !job.id && !job.generation_id;
    remakeGenerationId = job.generation_id || job.id || null;
    geometryMasterJob = job.geometry_master ? { ...job.geometry_master } : null;
    elements.removeColorButton.disabled = !geometryMasterJob;
    displayedJob = { ...job };
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
elements.clearWorkspaceButton.addEventListener("click", clearWorkspace);
function setPresetView(direction) {
  if (!currentObject) return;
  const box = new THREE.Box3().setFromObject(currentObject);
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  const distance = Math.max(sphere.radius * 2.5, 2.2);
  controls.target.copy(sphere.center);
  camera.position.copy(sphere.center).add(direction.clone().normalize().multiplyScalar(distance));
  controls.update();
}
elements.frontViewButton.addEventListener("click", () => setPresetView(new THREE.Vector3(0, 0.18, 1)));
elements.sideViewButton.addEventListener("click", () => setPresetView(new THREE.Vector3(1, 0.18, 0)));
elements.fullscreenButton.addEventListener("click", async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await elements.viewer.requestFullscreen();
  } catch (error) { showError(`Fullscreen is unavailable: ${error.message}`); }
});
elements.exportFormat.addEventListener("change", () => {
  if (!displayedJob) return;
  const format = elements.exportFormat.value;
  elements.downloadButton.textContent = `Download ${format.toUpperCase()}`;
  elements.downloadButton.href = format === "glb"
    ? displayedJob.download_url
    : `/api/generations/${displayedJob.id}/export/${format}`;
});
const studioPresets = [
  { name: "Bright", exposure: 1.42, hemi: 3.4, key: 5.8, fill: 2.1 },
  { name: "Neutral", exposure: 1.15, hemi: 2.5, key: 4.2, fill: 1.4 },
  { name: "Contrast", exposure: 1.02, hemi: 1.6, key: 5.4, fill: 0.7 },
];
let studioPreset = 0;
elements.studioButton.addEventListener("click", () => {
  studioPreset = (studioPreset + 1) % studioPresets.length;
  const preset = studioPresets[studioPreset];
  renderer.toneMappingExposure = preset.exposure;
  hemisphereLight.intensity = preset.hemi; keyLight.intensity = preset.key; fillLight.intensity = preset.fill;
  elements.studioButton.textContent = `Studio: ${preset.name}`;
});
elements.snapshotButton.addEventListener("click", () => {
  const priorSize = renderer.getSize(new THREE.Vector2());
  const priorRatio = renderer.getPixelRatio();
  renderer.setPixelRatio(Math.min(priorRatio * 2, 4));
  renderer.setSize(priorSize.x, priorSize.y, false);
  renderer.render(scene, camera);
  const link = document.createElement("a");
  link.href = renderer.domElement.toDataURL("image/png");
  link.download = `forge-one-preview-${Date.now()}.png`;
  link.click();
  renderer.setPixelRatio(priorRatio);
  renderer.setSize(priorSize.x, priorSize.y, false);
});
elements.turntableButton.addEventListener("click", () => {
  turntableEnabled = !turntableEnabled;
  elements.turntableButton.classList.toggle("active", turntableEnabled);
  elements.turntableButton.textContent = turntableEnabled ? "Stop turntable" : "Turntable";
});
const viewerBackgrounds = [0x131824, 0x25272c, 0xeeeeea, 0x0b0d10];
let viewerBackgroundIndex = 0;
elements.backgroundButton.addEventListener("click", () => {
  viewerBackgroundIndex = (viewerBackgroundIndex + 1) % viewerBackgrounds.length;
  scene.background.setHex(viewerBackgrounds[viewerBackgroundIndex]);
  elements.backgroundButton.textContent = `Background ${viewerBackgroundIndex + 1}/4`;
});
elements.saveViewButton.addEventListener("click", () => {
  savedViewerPose = { position: camera.position.clone(), target: controls.target.clone(), zoom: camera.zoom };
  elements.saveViewButton.textContent = "View saved";
});
elements.restoreViewButton.addEventListener("click", () => {
  if (!savedViewerPose) return;
  camera.position.copy(savedViewerPose.position); controls.target.copy(savedViewerPose.target); camera.zoom = savedViewerPose.zoom;
  camera.updateProjectionMatrix(); controls.update();
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
elements.removeColorButton.addEventListener("click", async () => {
  if (!geometryMasterJob) return;
  try {
    await loadModel(geometryMasterJob);
    elements.viewerTitle.textContent = "Geometry master — color removed";
  } catch (error) { showError(error.message); }
});

function gameReadySourceKind(job) {
  if (job?.game_ready_source_kind) return job.game_ready_source_kind;
  return String(job?.model_url || "").includes("/color/") ? "colored" : "original";
}

function updateGameReadyProgress(result) {
  const percent = Math.max(0, Math.min(100, Number(result.progress) || 0));
  elements.gameReadyProgress.classList.remove("hidden");
  elements.gameReadyStatus.textContent = result.message || "Optimizing the copy…";
  elements.gameReadyPercent.textContent = `${percent}%`;
  elements.gameReadyProgressBar.style.width = `${percent}%`;
}

function showGameReadyResult(result) {
  readyGameReady = result;
  updateGameReadyProgress(result);
  elements.gameReadyOriginalTriangles.textContent = Number(result.original_triangles).toLocaleString();
  elements.gameReadyOptimizedTriangles.textContent = Number(result.optimized_triangles).toLocaleString();
  elements.gameReadyReduction.textContent = `${Number(result.reduction_percent).toFixed(1)}%`;
  elements.gameReadyOriginalSize.textContent = formatBytes(result.original_file_size);
  elements.gameReadyOptimizedSize.textContent = formatBytes(result.optimized_file_size);
  const notes = [...(result.warnings || []), ...(result.skipped_operations || [])];
  elements.gameReadyReport.textContent = notes.length
    ? `Safety report: ${notes.join(" ")}`
    : "Verified by reloading the final GLB. UVs, materials, textures, transforms, and visible bounds passed validation.";
  elements.gameReadyOriginalDownload.href = result.original_download_url;
  elements.gameReadyDownload.href = result.download_url;
  elements.gameReadyResults.classList.remove("hidden");
  elements.startGameReadyButton.disabled = false;
  elements.startGameReadyButton.textContent = "Rebuild this preset";
}

async function pollGameReady(generationId, sourceKind) {
  clearTimeout(gameReadyPollTimer);
  try {
    const result = await api(`/api/generations/${generationId}/game-ready?preset=${selectedGameReadyPreset}&source_kind=${sourceKind}`);
    updateGameReadyProgress(result);
    if (result.status === "complete") {
      showGameReadyResult(result);
      return;
    }
    if (result.status === "failed") {
      elements.startGameReadyButton.disabled = false;
      elements.startGameReadyButton.textContent = "Retry Game Ready";
      return;
    }
    gameReadyPollTimer = setTimeout(() => pollGameReady(generationId, sourceKind), 700);
  } catch (error) {
    elements.gameReadyStatus.textContent = error.message;
    elements.startGameReadyButton.disabled = false;
    elements.startGameReadyButton.textContent = "Retry Game Ready";
  }
}

elements.gameReadyButton.addEventListener("click", () => {
  if (!displayedJob) return;
  const generationId = displayedJob.generation_id || displayedJob.id;
  if (!readyGameReady || readyGameReady.generation_id !== generationId) {
    gameReadyOriginalJob = { ...displayedJob };
    readyGameReady = null;
    elements.gameReadyResults.classList.add("hidden");
    elements.gameReadyProgress.classList.add("hidden");
    elements.startGameReadyButton.textContent = "Create Game Ready copy";
  }
  elements.gameReadyDialog.classList.remove("hidden");
});
elements.gameReadyClose.addEventListener("click", () => elements.gameReadyDialog.classList.add("hidden"));
elements.gameReadyPresets.querySelectorAll("button").forEach((button) => button.addEventListener("click", () => {
  selectedGameReadyPreset = button.dataset.preset;
  elements.gameReadyPresets.querySelectorAll("button").forEach((candidate) => candidate.classList.toggle("selected", candidate === button));
  readyGameReady = null;
  gameReadyOriginalJob = { ...displayedJob };
  elements.gameReadyResults.classList.add("hidden");
  elements.gameReadyProgress.classList.add("hidden");
  elements.startGameReadyButton.textContent = `Create ${button.querySelector("strong").textContent} copy`;
}));
elements.startGameReadyButton.addEventListener("click", async () => {
  const generationId = displayedJob?.generation_id || displayedJob?.id;
  if (!generationId) return;
  const sourceKind = gameReadySourceKind(displayedJob);
  gameReadyOriginalJob = { ...displayedJob, game_ready_source_kind: sourceKind };
  elements.gameReadyResults.classList.add("hidden");
  elements.startGameReadyButton.disabled = true;
  elements.startGameReadyButton.textContent = "Optimizing safely…";
  updateGameReadyProgress({ progress: 1, message: "Keeping the original untouched and preparing a separate copy…" });
  try {
    const form = new FormData();
    form.append("preset", selectedGameReadyPreset);
    form.append("source_kind", sourceKind);
    form.append("force", readyGameReady ? "true" : "false");
    const result = await api(`/api/generations/${generationId}/game-ready`, { method: "POST", body: form });
    if (result.status === "complete") showGameReadyResult(result);
    else pollGameReady(generationId, sourceKind);
  } catch (error) {
    elements.gameReadyStatus.textContent = error.message;
    elements.startGameReadyButton.disabled = false;
    elements.startGameReadyButton.textContent = "Retry Game Ready";
  }
});
elements.showGameReadyOriginalButton.addEventListener("click", async () => {
  if (!readyGameReady || !gameReadyOriginalJob) return;
  await loadModel({
    ...gameReadyOriginalJob,
    backend: `${gameReadyOriginalJob.backend || "Forge One"} · Original`,
    model_url: readyGameReady.original_model_url,
    download_url: readyGameReady.original_download_url,
    vertices: Number.isFinite(gameReadyOriginalJob.vertices) ? gameReadyOriginalJob.vertices : NaN,
    triangles: readyGameReady.original_triangles,
    file_size: readyGameReady.original_file_size,
    updated_at: Date.now(),
    game_ready_source_kind: readyGameReady.source_kind,
  });
  elements.gameReadyDialog.classList.add("hidden");
});
elements.previewGameReadyButton.addEventListener("click", async () => {
  if (!readyGameReady || !gameReadyOriginalJob) return;
  await loadModel({
    ...gameReadyOriginalJob,
    backend: `${gameReadyOriginalJob.backend || "Forge One"} · ${readyGameReady.preset_label}`,
    model_url: readyGameReady.model_url,
    download_url: readyGameReady.download_url,
    vertices: readyGameReady.vertices,
    triangles: readyGameReady.optimized_triangles,
    file_size: readyGameReady.optimized_file_size,
    updated_at: Date.now(),
    game_ready_source_kind: readyGameReady.source_kind,
    game_ready_result: true,
  });
  elements.gameReadyDialog.classList.add("hidden");
});
elements.gamePackageButton.addEventListener("click", async () => {
  const generationId = displayedJob?.generation_id || displayedJob?.id;
  if (!generationId) return;
  const sourceKind = gameReadySourceKind(displayedJob);
  elements.gamePackageButton.disabled = true;
  elements.gamePackageButton.textContent = "Building 3 LODs…";
  elements.gameReadyProgress.classList.remove("hidden");
  elements.gameReadyStatus.textContent = "Creating and validating High, Game Ready, Low Poly, and collision files…";
  elements.gameReadyPercent.textContent = "Working";
  try {
    const form = new FormData(); form.append("source_kind", sourceKind);
    const result = await api(`/api/generations/${generationId}/game-package`, { method: "POST", body: form });
    elements.gameReadyStatus.textContent = `${result.message} Package size: ${formatBytes(result.file_size)}.`;
    elements.gameReadyPercent.textContent = "100%";
    elements.gamePackageDownload.href = result.download_url;
    elements.gamePackageDownload.classList.remove("hidden");
  } catch (error) { elements.gameReadyStatus.textContent = error.message; elements.gameReadyPercent.textContent = "Failed"; }
  finally { elements.gamePackageButton.disabled = false; elements.gamePackageButton.textContent = "Rebuild complete game package"; }
});
elements.polishButton.addEventListener("click", () => {
  if (!displayedJob) return;
  polishOriginalJob = { ...displayedJob }; readyPolish = null;
  elements.polishStatus.classList.add("hidden"); elements.polishDownloads.classList.add("hidden");
  elements.polishDialog.classList.remove("hidden");
});
elements.polishClose.addEventListener("click", () => elements.polishDialog.classList.add("hidden"));
elements.startPolishButton.addEventListener("click", async () => {
  const generationId = displayedJob?.generation_id || displayedJob?.id;
  if (!generationId) return;
  elements.startPolishButton.disabled = true; elements.startPolishButton.textContent = "Polishing…";
  elements.polishStatus.classList.remove("hidden"); elements.polishStatus.textContent = "Creating a separate cleanup candidate…";
  try {
    const trimValues = { none: 0, light: 0.0005, strong: 0.002 };
    const form = new FormData(); form.append("smooth", elements.polishSmooth.value); form.append("trim", String(trimValues[elements.polishTrim.value])); form.append("simplify", elements.polishSimplify.value);
    readyPolish = await api(`/api/generations/${generationId}/refine`, { method: "POST", body: form });
    elements.polishStatus.textContent = `${readyPolish.message} ${readyPolish.vertices.toLocaleString()} vertices · ${readyPolish.triangles.toLocaleString()} triangles.`;
    elements.polishDownload.href = readyPolish.download_url; elements.polishDownloads.classList.remove("hidden");
  } catch (error) { elements.polishStatus.textContent = error.message; }
  finally { elements.startPolishButton.disabled = false; elements.startPolishButton.textContent = "Create polished copy"; }
});
elements.previewPolishButton.addEventListener("click", async () => {
  if (!readyPolish || !polishOriginalJob) return;
  await loadModel({ ...polishOriginalJob, backend: `${polishOriginalJob.backend} · Polished`, ...readyPolish, updated_at: Date.now() });
  elements.polishDialog.classList.add("hidden");
});
elements.showPolishOriginalButton.addEventListener("click", async () => {
  if (!polishOriginalJob) return; await loadModel(polishOriginalJob); elements.polishDialog.classList.add("hidden");
});
elements.remakeButton.addEventListener("click", async () => {
  if (!remakeGenerationId) return;
  clearError();
  elements.remakeButton.disabled = true;
  elements.generateButton.disabled = true;
  elements.cancelButton.classList.remove("hidden");
  elements.viewerTitle.textContent = "Remaking a new reconstruction variant";
  try {
    remakeOriginal = { ...displayedJob };
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
elements.restoreOriginalButton.addEventListener("click", async () => {
  if (!remakeOriginal) return;
  await loadModel(remakeOriginal);
  elements.viewerTitle.textContent = "Original model — remake candidate kept separate";
});
elements.keepRemakeButton.addEventListener("click", async () => {
  if (!remakeCandidate) return;
  try {
    await api(`/api/generations/${remakeCandidate.id}/keep-remake`, { method: "POST" });
    elements.keepRemakeButton.disabled = true;
    elements.keepRemakeButton.textContent = "Remake saved";
    if (profile) await loadLibrary();
  } catch (error) { showError(error.message); }
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

async function resumeSharedAnimation() {
  const query = new URLSearchParams(window.location.search);
  const generationId = query.get("animation");
  const motion = query.get("motion") || "walk";
  if (!generationId || !["walk", "run", "jump"].includes(motion)) return;
  try {
    const [job, animation] = await Promise.all([
      api(`/api/generations/${generationId}`),
      api(`/api/generations/${generationId}/animation/${motion}`),
    ]);
    if (animation.status !== "complete") throw new Error("This shared animation is not ready yet.");
    readyAnimation = animation;
    await loadModel({
      ...job,
      backend: `Animated ${motion}`,
      model_url: animation.model_url,
      download_url: animation.model_url,
      updated_at: Date.now(),
    });
  } catch (error) { showError(error.message); }
}

async function resumeSharedModel() {
  const token = new URLSearchParams(window.location.search).get("share");
  if (!token) return;
  try {
    const shared = await api(`/api/shares/${encodeURIComponent(token)}`);
    await loadModel({
      id: null, generation_id: shared.generation_id, title: shared.title, backend: "Private shared model",
      model_url: shared.model_url, download_url: shared.download_url || shared.model_url,
      vertices: NaN, triangles: NaN, file_size: NaN, elapsed_seconds: NaN, updated_at: Date.now(), source_image_id: null,
    });
    elements.viewerTitle.textContent = `${shared.title} · private preview`;
    if (!shared.allow_download) {
      elements.downloadButton.removeAttribute("href"); elements.downloadButton.textContent = "Preview only";
      elements.downloadButton.classList.add("disabled"); elements.downloadButton.setAttribute("aria-disabled", "true"); elements.exportFormat.disabled = true;
    }
  } catch (error) { showError(error.message); }
}

detectSystem();
loadProfile();
const startupQuery = new URLSearchParams(window.location.search);
if (startupQuery.has("share")) resumeSharedModel();
else if (startupQuery.has("animation")) resumeSharedAnimation();
else resumeGeneration();
