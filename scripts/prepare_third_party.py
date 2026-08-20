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
    if not target.is_dir():
        run("git", "clone", url, str(target))
    run("git", "-C", str(target), "fetch", "--depth", "1", "origin", commit)
    run("git", "-C", str(target), "checkout", "--detach", commit)


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Expected upstream text was not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def apply_patches() -> None:
    sg = THIRD_PARTY / "TripoSG"
    replace_once(
        sg / "triposg" / "inference_utils.py",
        "from diso import DiffDMC",
        "try:\n    from diso import DiffDMC\nexcept ImportError:\n    # The app uses the non-DISO hierarchical decoder on Windows.\n    DiffDMC = None",
    )
    replace_once(
        sg / "scripts" / "image_process.py",
        "def prepare_image(image_path, bg_color, rmbg_net=None):\n    if os.path.isfile(image_path):\n        img_tensor = load_image(image_path, bg_color=bg_color, rmbg_net=rmbg_net)",
        "def prepare_image(image_path, bg_color, rmbg_net=None, padding_ratio=0.06):\n    if os.path.isfile(image_path):\n        img_tensor = load_image(image_path, bg_color=bg_color, rmbg_net=rmbg_net, padding_ratio=padding_ratio)",
    )


if __name__ == "__main__":
    THIRD_PARTY.mkdir(exist_ok=True)
    for source_name, (source_url, source_commit) in SOURCES.items():
        ensure_source(source_name, source_url, source_commit)
    apply_patches()
    print("Pinned TripoSR and TripoSG sources are ready.")
