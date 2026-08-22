import { defineConfig } from "vite";

export default defineConfig({
  // Ship Three.js' official Draco decoder beside the built app so optimized
  // GLBs load locally and through the public tunnel without a third-party CDN.
  publicDir: "node_modules/three/examples/jsm/libs/draco",
});
