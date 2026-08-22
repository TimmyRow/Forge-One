"""Fetch pinned upstream 3D sources and apply the Windows-safe patches."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THIRD_PARTY = ROOT / "third_party"
SOURCES = {
    "TripoSR": ("https://github.com/VAST-AI-Research/TripoSR.git", "107cefdc244c39106fa830359024f6a2f1c78871"),
    "TripoSG": ("https://github.com/VAST-AI-Research/TripoSG.git", "fc5c40990181e2a756c4e0b1c2f4d6b5202faf8c"),
}


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def ensure_source(name: str, url: str, commit: str) -> None:
    target = THIRD_PARTY / name
    if target.is_dir():
        return
    run("git", "clone", url, str(target))
    run("git", "-C", str(target), "fetch", "--depth", "1", "origin", commit)
    run("git", "-C", str(target), "checkout", "--detach", commit)


def apply_patches() -> None:
    sg = THIRD_PARTY / "TripoSG"
    inference = sg / "triposg" / "inference_utils.py"
    text = inference.read_text(encoding="utf-8")
    marker, tail = "from einops import repeat\n", "import torch.nn.functional as F\n"
    if marker not in text or tail not in text:
        raise RuntimeError("Unsupported TripoSG inference_utils.py layout")
    prefix, remaining = text.split(marker, 1)
    _old_import, suffix = remaining.split(tail, 1)
    optional_diso = "try:\n    from diso import DiffDMC\nexcept ImportError:\n    # The app uses the non-DISO hierarchical decoder on Windows.\n    DiffDMC = None\n"
    inference.write_text(prefix + marker + optional_diso + tail + suffix, encoding="utf-8")

    image_process = sg / "scripts" / "image_process.py"
    text = image_process.read_text(encoding="utf-8")
    text = text.replace(
        "def prepare_image(image_path, bg_color, rmbg_net=None):\n    if os.path.isfile(image_path):\n        img_tensor = load_image(image_path, bg_color=bg_color, rmbg_net=rmbg_net)",
        "def prepare_image(image_path, bg_color, rmbg_net=None, padding_ratio=0.06):\n    if os.path.isfile(image_path):\n        img_tensor = load_image(image_path, bg_color=bg_color, rmbg_net=rmbg_net, padding_ratio=padding_ratio)",
    )
    image_process.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    THIRD_PARTY.mkdir(exist_ok=True)
    for source_name, (source_url, source_commit) in SOURCES.items():
        ensure_source(source_name, source_url, source_commit)
    apply_patches()
    print("Pinned TripoSR and TripoSG sources are ready.")
