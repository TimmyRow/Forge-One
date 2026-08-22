import { defineConfig } from "vite";

export default defineConfig({
  base: "/games/room-one/",
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          three: ["three"],
          physics: ["@dimforge/rapier3d-compat"],
        },
      },
    },
  },
});
