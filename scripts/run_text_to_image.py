"""Generate one local SD-Turbo image for the Text → Image → Model workflow."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parents[1] / "models" / "huggingface"))

import torch
from diffusers import AutoPipelineForText2Image


MODEL_ID = "stabilityai/sd-turbo"


def status(percent: int, message: str) -> None:
    print(f"STATUS:{percent}:{message}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable to Text to Image.")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    status(8, "Checking the local SD-Turbo image model (first run downloads it)…")
    pipe = AutoPipelineForText2Image.from_pretrained(MODEL_ID, torch_dtype=torch.float16, variant="fp16")
    # CPU offload keeps the combined Text → Image → 3D workflow inside 8 GB.
    pipe.enable_model_cpu_offload()
    status(42, "Creating the source image from your prompt…")
    image = pipe(
        prompt=args.prompt,
        negative_prompt="text, watermark, logo, cropped, duplicate limbs, extra heads, distorted anatomy",
        num_inference_steps=4,
        guidance_scale=0.0,
        height=512,
        width=512,
        generator=torch.Generator(device="cuda").manual_seed(args.seed),
    ).images[0]
    image.save(output, format="PNG")
    status(56, "Source image ready — moving into 3D reconstruction…")
    print("RESULT:" + json.dumps({"image_path": str(output)}), flush=True)


if __name__ == "__main__":
    main()
