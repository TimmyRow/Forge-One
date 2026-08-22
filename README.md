# Forge One — local image to 3D

Forge One turns one object image into a real, vertex-colored GLB using local NVIDIA GPU inference.

## Launch on Windows

1. Run `setup.bat` once. The first setup downloads Python/PyTorch dependencies.
2. Run `run.bat`.
3. Open <http://127.0.0.1:7860> if it does not open automatically.
4. Upload a PNG, JPG/JPEG, or WebP image and select **Generate real 3D**.

The first generation downloads and caches official TripoSR, DINO configuration, and rembg weights under `models/`. Generated files are stored under `outputs/<generation-id>/model.glb`; original uploads remain under `uploads/<generation-id>/`.

## Modes

- **Fast — TripoSR:** the tested local path for an 8 GB GPU. It uses a 256³ extraction grid, tighter object framing, and light Taubin surface refinement to reduce marching-cubes blockiness.
- **Quality — TripoSG:** install once with `setup-quality.bat`; its official model weights download on the first Quality generation. The exported GLB now includes vertex colors baked from the processed source view. The official TripoSG model recommends more than 8 GB VRAM, so Forge One uses its non-DISO hierarchical decoder and reports a clear CUDA-memory error if it cannot fit rather than returning a placeholder.

## Profiles and saved models

Use **Create profile** in the top bar, then create a name and password. Models generated while signed in are automatically saved to that profile. On a different device, open the same public link, use **Create profile** → **Sign in**, then open **My library** to view or download the prior models. Profile metadata and GLBs persist locally under `data/forge-one.sqlite3` and `outputs/` on this PC.

## Temporary public link

Current development demo: <https://hitachi-manor-breakdown-cafe.trycloudflare.com/>

This PC can expose the app through a Cloudflare Quick Tunnel while the backend and `cloudflared` processes are running. It is intentionally unrestricted when shared publicly, so do not expose images or outputs you would not want other visitors to access. A Quick Tunnel URL changes after restart; check `logs/public-tunnel.out.log` for the current address.

Before publishing the code or sharing a tunnel, follow [PUBLIC_RELEASE.md](PUBLIC_RELEASE.md). In particular, use `FORGE_ACCESS_TOKEN` for a personal tunnel and `FORGE_PUBLIC_MODE=1` to enable public workload guardrails. A `trycloudflare.com` address is temporary and is not a permanent project homepage.

## Reliability choices for 8 GB VRAM

- CUDA PyTorch 2.5.1 with CUDA 12.1 runtime wheels.
- FP16 autocast and inference-only execution.
- 4,096-point renderer chunks and a 192³ Fast marching-cubes grid.
- GPU neural inference and density sampling; CPU marching cubes avoids requiring a CUDA/C++ compiler.
- One generation at a time, with CUDA cache cleanup after extraction.
- TripoSR's X-up reconstruction is baked to standard glTF Y-up orientation.

Set `FAST_CHUNK_SIZE` or `FAST_MC_RESOLUTION` before `run.bat` only for diagnostics. The tested defaults prioritize successful 8 GB generation.

## Licenses

The official TripoSR source and MIT license are preserved in `third_party/TripoSR/`. Dependency notices are summarized in `THIRD_PARTY_LICENSES.md`.
