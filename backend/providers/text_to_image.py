"""Local text-to-image worker used by Forge One's Text → Image → Model flow."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Callable

from backend.providers.triposr import GenerationCancelled

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUALITY_PYTHON = PROJECT_ROOT / ".venv-quality" / "Scripts" / "python.exe"


class TextToImageProvider:
    """Run SD-Turbo locally, isolated from the reconstruction environment."""

    model_id = "stabilityai/sd-turbo"

    @staticmethod
    def is_installed() -> bool:
        return QUALITY_PYTHON.is_file()

    def generate(
        self,
        prompt: str,
        output: Path,
        progress: Callable[[str, int], None],
        cancelled: Callable[[], bool],
        seed: int = 42,
    ) -> None:
        if not self.is_installed():
            raise RuntimeError("Text to Image is not installed yet. Run setup-quality.bat once, then retry.")
        output.parent.mkdir(parents=True, exist_ok=True)
        command = [
            str(QUALITY_PYTHON), str(PROJECT_ROOT / "scripts" / "run_text_to_image.py"),
            "--prompt", prompt, "--output", str(output), "--seed", str(seed),
        ]
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        process = subprocess.Popen(
            command, cwd=PROJECT_ROOT, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        output_lines: list[str] = []
        try:
            assert process.stdout is not None
            for raw_line in process.stdout:
                line = raw_line.strip()
                output_lines.append(line)
                if line.startswith("STATUS:"):
                    _, percent, message = line.split(":", 2)
                    progress(message, int(percent))
                if cancelled():
                    process.terminate()
                    raise GenerationCancelled("Generation was cancelled.")
            code = process.wait()
        finally:
            if process.poll() is None:
                process.kill()
        if code != 0 or not output.is_file():
            detail = "\n".join(output_lines[-20:])
            if "out of memory" in detail.lower() or "cuda oom" in detail.lower():
                raise RuntimeError("Text to Image ran out of GPU memory. Close GPU-heavy apps and retry.")
            raise RuntimeError(f"Text to Image failed: {detail[-1200:]}")
        result_line = next((line for line in reversed(output_lines) if line.startswith("RESULT:")), None)
        if result_line:
            data = json.loads(result_line.removeprefix("RESULT:"))
            if Path(data.get("image_path", "")) != output:
                raise RuntimeError("Text to Image returned an unexpected output path.")
