from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUALITY_PYTHON = PROJECT_ROOT / ".venv-quality" / "Scripts" / "python.exe"


@dataclass(slots=True)
class QualityGenerationResult:
    glb_path: Path
    prepared_image_path: Path
    vertices: int
    triangles: int
    file_size: int
    elapsed_seconds: float
    peak_vram_bytes: int


class TripoSGProvider:
    """Runs official TripoSG in an isolated environment so Fast remains stable."""

    name = "Quality"
    model_id = "VAST-AI/TripoSG"

    @staticmethod
    def is_installed() -> bool:
        return QUALITY_PYTHON.is_file()

    def generate(
        self,
        source: Path,
        output_dir: Path,
        progress: Callable[[str, int], None],
        cancelled: Callable[[], bool],
        variation: int = 0,
        detail: str = "Balanced",
        trim: str = "Balanced",
        subject_mode: str = "General",
    ) -> QualityGenerationResult:
        if not self.is_installed():
            raise RuntimeError("Quality mode is not installed yet. Run setup-quality.bat once, then retry.")
        output_dir.mkdir(parents=True, exist_ok=True)
        progress("Starting TripoSG Quality worker…", 8)
        command = [
            str(QUALITY_PYTHON), str(PROJECT_ROOT / "scripts" / "run_quality.py"),
            "--image", str(source), "--output-dir", str(output_dir),
            "--seed", str(42 + variation),
            "--detail", detail, "--trim", trim,
            "--subject-mode", subject_mode,
        ]
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            # Hugging Face / model progress output is UTF-8, whereas Windows
            # otherwise defaults to a legacy code page that cannot decode it.
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        output: list[str] = []
        try:
            assert process.stdout is not None
            for raw_line in process.stdout:
                line = raw_line.strip()
                output.append(line)
                if line.startswith("STATUS:"):
                    _, percent, message = line.split(":", 2)
                    progress(message, int(percent))
                if cancelled():
                    process.terminate()
                    raise RuntimeError("Generation was cancelled.")
            code = process.wait()
        finally:
            if process.poll() is None:
                process.kill()
        if code != 0:
            detail = "\n".join(output[-20:])
            if "out of memory" in detail.lower() or "cuda oom" in detail.lower():
                raise RuntimeError("TripoSG Quality ran out of GPU memory. This 8 GB GPU is below its official >8 GB recommendation; close GPU-heavy apps or use Fast mode.")
            raise RuntimeError(f"TripoSG Quality failed: {detail[-1200:]}")
        result_line = next((line for line in reversed(output) if line.startswith("RESULT:")), None)
        if not result_line:
            raise RuntimeError("TripoSG Quality finished without reporting a GLB result.")
        data = json.loads(result_line.removeprefix("RESULT:"))
        return QualityGenerationResult(
            glb_path=Path(data["glb_path"]), prepared_image_path=Path(data["prepared_image_path"]),
            vertices=int(data["vertices"]), triangles=int(data["triangles"]),
            file_size=int(data["file_size"]), elapsed_seconds=float(data["elapsed_seconds"]),
            peak_vram_bytes=int(data["peak_vram_bytes"]),
        )
