from __future__ import annotations

import sys
from pathlib import Path

import torch


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    checks = {
        "TripoSR source": root / "third_party" / "TripoSR" / "tsr" / "system.py",
        "frontend build": root / "frontend" / "dist" / "index.html",
    }
    for label, path in checks.items():
        if not path.is_file():
            print(f"ERROR: {label} is missing: {path}")
            return 1
    if not torch.cuda.is_available():
        print("ERROR: CUDA is not available to PyTorch.")
        return 1
    props = torch.cuda.get_device_properties(0)
    print(f"PyTorch: {torch.__version__}")
    print(f"CUDA runtime: {torch.version.cuda}")
    print(f"GPU: {props.name}")
    print(f"VRAM: {props.total_memory / 1024**3:.2f} GiB")
    print("Fast/TripoSR environment is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

