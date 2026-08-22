from __future__ import annotations

import json
import logging
import mimetypes
import hmac
import os
import re
import shutil
import subprocess
import threading
import traceback
import uuid
import time
import zipfile
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import torch
import trimesh
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError

from backend.providers import TripoSGProvider, TripoSRProvider
from backend.providers.triposr import GenerationCancelled
from backend.providers.text_to_image import TextToImageProvider
from backend.profiles import ProfileStore
from backend.colorize import colorize_glb

ROOT = Path(__file__).resolve().parents[1]
UPLOADS = ROOT / "uploads"
OUTPUTS = ROOT / "outputs"
LOGS = ROOT / "logs"
DATA = ROOT / "data"
FRONTEND = ROOT / "frontend" / "dist"
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_FORMATS = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}

for directory in (UPLOADS, OUTPUTS, LOGS, DATA):
    directory.mkdir(parents=True, exist_ok=True)

handler = RotatingFileHandler(LOGS / "app.log", maxBytes=4_000_000, backupCount=3)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[handler, logging.StreamHandler()],
)
LOGGER = logging.getLogger("image_to_3d.api")

app = FastAPI(title="Local Image to 3D", version="0.1.0")
fast_provider = TripoSRProvider()
quality_provider = TripoSGProvider()
text_to_image_provider = TextToImageProvider()
generation_lock = threading.Lock()
jobs_lock = threading.Lock()
jobs: dict[str, dict[str, Any]] = {}
animation_jobs: dict[str, dict[str, Any]] = {}
animation_lock = threading.Lock()
game_ready_jobs: dict[str, dict[str, Any]] = {}
game_ready_lock = threading.Lock()
game_package_lock = threading.Lock()
color_lock = threading.Lock()
profiles = ProfileStore(DATA / "forge-one.sqlite3")
PUBLIC_ACCESS_TOKEN = os.getenv("FORGE_ACCESS_TOKEN", "")
PUBLIC_MODE = os.getenv("FORGE_PUBLIC_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}
PUBLIC_JOBS_PER_HOUR = max(1, int(os.getenv("FORGE_PUBLIC_JOBS_PER_HOUR", "4")))
public_usage: dict[str, list[float]] = {}
public_usage_lock = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def enforce_public_job_limit(request: Request, cost: int = 1) -> None:
    """Bound anonymous GPU/disk use when a personal instance is public."""
    if not PUBLIC_MODE:
        return
    forwarded = request.headers.get("cf-connecting-ip", "").strip()
    client_key = forwarded or (request.client.host if request.client else "unknown")
    cutoff = time.time() - 3600
    with public_usage_lock:
        recent = [stamp for stamp in public_usage.get(client_key, []) if stamp >= cutoff]
        if len(recent) + cost > PUBLIC_JOBS_PER_HOUR:
            raise HTTPException(
                429,
                f"This public Forge One allows {PUBLIC_JOBS_PER_HOUR} generation jobs per visitor each hour. Try again later.",
            )
        recent.extend([time.time()] * cost)
        public_usage[client_key] = recent


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key not in {"source_path", "profile_id"}}


def persist_job(job: dict[str, Any]) -> None:
    output_dir = OUTPUTS / job["id"]
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "generation.json").write_text(
        json.dumps(public_job(job), indent=2), encoding="utf-8"
    )


def update_job(job_id: str, **changes: Any) -> None:
    with jobs_lock:
        jobs[job_id].update(changes)
        jobs[job_id]["updated_at"] = utc_now()
        snapshot = dict(jobs[job_id])
    persist_job(snapshot)


def record_model_version(
    job_id: str,
    source: Path,
    label: str,
    kind: str,
    *,
    preserve_copy: bool = True,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Preserve a generated derivative so later work never erases a good one."""
    if not source.is_file():
        raise FileNotFoundError(source)
    version_id = uuid.uuid4().hex[:16]
    if preserve_copy:
        target = OUTPUTS / job_id / "versions" / f"{version_id}.glb"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    else:
        target = source
    scene = trimesh.load(target, force="scene")
    entry = {
        "id": version_id,
        "label": label,
        "kind": kind,
        "created_at": utc_now(),
        "file": str(target.relative_to(OUTPUTS / job_id)).replace("\\", "/"),
        "file_size": target.stat().st_size,
        "vertices": sum(len(mesh.vertices) for mesh in scene.geometry.values()),
        "triangles": sum(len(mesh.faces) for mesh in scene.geometry.values()),
        **(details or {}),
    }
    with jobs_lock:
        versions = jobs[job_id].setdefault("versions", [])
        versions.append(entry)
        snapshot = dict(jobs[job_id])
    persist_job(snapshot)
    return entry


def friendly_error(exc: BaseException) -> str:
    message = str(exc).strip()
    if isinstance(exc, UnidentifiedImageError):
        return "The uploaded file is not a readable image."
    if "401" in message or "gated repo" in message.lower():
        return "The official TripoSR weights could not be downloaded. Check the internet connection and retry."
    if "No space left" in message:
        return "There is not enough disk space to download the model or save the GLB."
    if "out of memory" in message.lower() or "cuda oom" in message.lower():
        return "The selected model ran out of GPU memory. Close GPU-heavy applications or use Fast mode."
    return message or "Generation failed. See logs/app.log for technical details."


def animation_key(job_id: str, motion: str) -> str:
    return f"{job_id}:{motion}"


GAME_READY_PRESETS = {"high": "High Detail", "game": "Game Ready", "low": "Low Poly"}


def game_ready_key(job_id: str, preset: str, source_kind: str) -> str:
    return f"{job_id}:{preset}:{source_kind}"


def game_ready_source(job_id: str, source_kind: str) -> Path:
    if source_kind == "colored":
        colored = color_output_path(job_id)
        if colored.is_file():
            return colored
        raise HTTPException(409, "The colored model is not ready. Optimize the original or finish the color pass first.")
    if source_kind != "original":
        raise HTTPException(400, "Source must be original or colored.")
    return OUTPUTS / job_id / "model.glb"


def game_ready_paths(job_id: str, preset: str, source_kind: str) -> dict[str, Path]:
    directory = OUTPUTS / job_id / "game-ready" / f"{source_kind}-{preset}"
    return {
        "directory": directory,
        "glb": directory / "model_game_ready.glb",
        "report": directory / "report.json",
        "progress": directory / "progress.json",
        "log": directory / "blender.log",
    }


def public_game_ready(job_id: str, preset: str, source_kind: str) -> dict[str, Any]:
    key = game_ready_key(job_id, preset, source_kind)
    paths = game_ready_paths(job_id, preset, source_kind)
    result = dict(game_ready_jobs.get(key, {}))
    for candidate in (paths["progress"], paths["report"]):
        if candidate.is_file():
            try:
                disk_result = json.loads(candidate.read_text(encoding="utf-8"))
                if disk_result:
                    result.update(disk_result)
            except (OSError, json.JSONDecodeError):
                pass
    if not result:
        result = {"status": "not_started", "progress": 0, "message": "Ready to create an optimized copy."}
    result.update(
        generation_id=job_id,
        preset=preset,
        preset_label=GAME_READY_PRESETS[preset],
        source_kind=source_kind,
        original_model_url=(f"/api/generations/{job_id}/color/model" if source_kind == "colored" else f"/api/generations/{job_id}/model"),
        original_download_url=f"/api/generations/{job_id}/game-ready/original/download?source_kind={source_kind}",
    )
    if result.get("status") == "complete" and paths["glb"].is_file():
        result.update(
            model_url=f"/api/generations/{job_id}/game-ready/{preset}/model?source_kind={source_kind}",
            download_url=f"/api/generations/{job_id}/game-ready/{preset}/download?source_kind={source_kind}",
        )
    return result


def run_game_ready(job_id: str, preset: str, source_kind: str) -> None:
    key = game_ready_key(job_id, preset, source_kind)
    paths = game_ready_paths(job_id, preset, source_kind)
    paths["directory"].mkdir(parents=True, exist_ok=True)
    with game_ready_lock:
        try:
            if not BLENDER.is_file():
                raise RuntimeError("Blender 4.2 was not found. Install Blender, then retry Game Ready.")
            source = game_ready_source(job_id, source_kind)
            game_ready_jobs[key] = {"status": "running", "progress": 4, "message": "Starting the local mesh optimizer…"}
            command = [
                str(BLENDER), "--background", "--python", str(ROOT / "scripts" / "prepare_game_ready.py"), "--",
                "--input", str(source), "--output", str(paths["glb"]), "--report", str(paths["report"]),
                "--progress", str(paths["progress"]), "--preset", preset,
            ]
            completed = subprocess.run(
                command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900
            )
            paths["log"].write_text(f"{completed.stdout}\n{completed.stderr}", encoding="utf-8")
            result: dict[str, Any] = {}
            if paths["progress"].is_file():
                result = json.loads(paths["progress"].read_text(encoding="utf-8"))
            if completed.returncode != 0 or result.get("status") != "complete" or not paths["glb"].is_file():
                detail = result.get("message") or completed.stderr or completed.stdout or "Blender did not create a verified GLB."
                raise RuntimeError(str(detail)[-1600:])
            game_ready_jobs[key] = result
            try:
                record_model_version(
                    job_id, paths["glb"], f"{GAME_READY_PRESETS[preset]} export", "game_ready",
                    details={"preset": preset, "source_kind": source_kind},
                )
            except Exception:
                LOGGER.exception("Could not archive the Game Ready version for %s", job_id)
        except Exception as exc:
            LOGGER.exception("Game Ready optimization failed for %s", job_id)
            failed = {"status": "failed", "progress": 100, "message": friendly_error(exc)}
            game_ready_jobs[key] = failed
            try:
                paths["progress"].write_text(json.dumps(failed, indent=2), encoding="utf-8")
            except OSError:
                pass


def animation_paths(job_id: str, motion: str) -> dict[str, Path]:
    directory = OUTPUTS / job_id / "animation" / motion
    return {
        "directory": directory,
        "blend": directory / "forge-one-animation.blend",
        "glb": directory / "forge-one-animation.glb",
        "report": directory / "report.json",
        "log": directory / "blender.log",
    }


def public_animation(job_id: str, motion: str) -> dict[str, Any]:
    key = animation_key(job_id, motion)
    result = dict(animation_jobs.get(key, {}))
    paths = animation_paths(job_id, motion)
    if not result and paths["report"].is_file():
        try:
            result = json.loads(paths["report"].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            result = {}
    if not result:
        return {"status": "not_started", "motion": motion}
    # Early local test exports did not contain a skinned mesh. Treat those
    # reports as stale so the corrected rigging route rebuilds them.
    if result.get("status") == "complete" and (not result.get("weighting") or not result.get("skin_verified")):
        return {"status": "not_started", "motion": motion}
    if result.get("status") == "complete":
        result.update(
            blend_url=f"/api/generations/{job_id}/animation/{motion}/download",
            model_url=f"/api/generations/{job_id}/animation/{motion}/model",
        )
    return result


def run_animation(job_id: str, motion: str) -> None:
    key = animation_key(job_id, motion)
    paths = animation_paths(job_id, motion)
    paths["directory"].mkdir(parents=True, exist_ok=True)
    with animation_lock:
        animation_jobs[key] = {"status": "running", "motion": motion, "message": "Importing the model into Blender…"}
        try:
            if not BLENDER.is_file():
                raise RuntimeError("Blender 4.2 was not found. Install Blender, then retry Animate.")
            source = OUTPUTS / job_id / "model.glb"
            command = [
                str(BLENDER), "--background", "--python", str(ROOT / "scripts" / "prepare_animation_source.py"), "--",
                "--input", str(source), "--blend", str(paths["blend"]), "--glb", str(paths["glb"]),
                "--report", str(paths["report"]), "--motion", motion,
            ]
            completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
            paths["log"].write_text(f"{completed.stdout}\n{completed.stderr}", encoding="utf-8")
            if completed.returncode != 0 or not paths["report"].is_file():
                detail = (completed.stderr or completed.stdout or "Blender did not create an animation.").strip()
                raise RuntimeError(detail[-1400:])
            result = json.loads(paths["report"].read_text(encoding="utf-8"))
            animation_jobs[key] = result
        except Exception as exc:
            LOGGER.exception("Animation preparation failed for %s", job_id)
            animation_jobs[key] = {"status": "failed", "motion": motion, "message": friendly_error(exc)}


def color_output_path(job_id: str) -> Path:
    return OUTPUTS / job_id / "model-colored.glb"


def public_color_status(job_id: str) -> dict[str, Any]:
    job = jobs[job_id]
    status = job.get("color_status", "not_started")
    result: dict[str, Any] = {"status": status, "message": job.get("color_message", "Ready to apply source colours.")}
    colored = color_output_path(job_id)
    if status == "complete" and colored.is_file():
        result.update(
            model_url=f"/api/generations/{job_id}/color/model",
            download_url=f"/api/generations/{job_id}/color/download",
            vertices=job.get("color_vertices"),
            triangles=job.get("color_triangles"),
            file_size=job.get("color_file_size"),
        )
    return result


def run_color(job_id: str) -> None:
    with color_lock:
        try:
            update_job(job_id, color_status="running", color_message="Projecting source colours onto the finished geometry…")
            source = OUTPUTS / job_id / "prepared-input.png"
            if not source.is_file():
                source = Path(jobs[job_id]["source_path"])
            extra_view_paths = {
                name: OUTPUTS / job_id / filename
                for name, filename in (jobs[job_id].get("extra_views") or {}).items()
                if name in {"side", "back"}
            }
            vertices, triangles, file_size = colorize_glb(
                OUTPUTS / job_id / "model.glb", source, color_output_path(job_id),
                float(jobs[job_id].get("color_brightness", 1.0)),
                float(jobs[job_id].get("color_saturation", 1.0)),
                float(jobs[job_id].get("color_coverage", 1.0)),
                str(jobs[job_id].get("color_style", "colour")),
                jobs[job_id].get("color_palette") or None,
                jobs[job_id].get("color_paint_guides") or None,
                extra_view_paths,
            )
            update_job(
                job_id,
                color_status="complete",
                color_message="Source colours applied without changing the geometry.",
                color_vertices=vertices,
                color_triangles=triangles,
                color_file_size=file_size,
            )
            try:
                record_model_version(
                    job_id, color_output_path(job_id), "Color pass", "color",
                    details={"style": jobs[job_id].get("color_style", "colour")},
                )
            except Exception:
                LOGGER.exception("Could not archive the completed color version for %s", job_id)
        except Exception as exc:
            LOGGER.exception("Colour pass failed for %s", job_id)
            update_job(job_id, color_status="failed", color_message=friendly_error(exc))


def run_generation(job_id: str) -> None:
    def progress(message: str, percent: int) -> None:
        update_job(job_id, status="running", message=message, progress=percent)

    try:
        with generation_lock:
            if jobs[job_id]["cancel_requested"]:
                raise GenerationCancelled("Generation was cancelled.")
            source = Path(jobs[job_id]["source_path"])
            if jobs[job_id].get("text_prompt") and not source.is_file():
                progress("Turning your text prompt into a source image…", 5)
                text_to_image_provider.generate(
                    jobs[job_id]["text_prompt"], source, progress,
                    cancelled=lambda: bool(jobs[job_id]["cancel_requested"]),
                    seed=42 + int(jobs[job_id].get("variation", 0)),
                )
                archive = OUTPUTS / job_id / "source.png"
                archive.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, archive)
                update_job(job_id, text_image_url=f"/api/generations/{job_id}/source-image")
            mode = jobs[job_id]["mode"]
            active_provider = quality_provider if mode == "Quality" else fast_provider
            reconstruct_progress = progress
            if jobs[job_id].get("text_prompt"):
                # The image stage occupies the first half of the visible
                # progress bar; keep reconstruction progress monotonic after it.
                reconstruct_progress = lambda message, percent: progress(
                    message, 56 + round(max(0, min(100, percent)) * 0.44)
                )
            if mode == "Quality":
                # Do not hold the Fast model in VRAM while the isolated TripoSG
                # worker is trying to fit on an 8 GB GPU.
                fast_provider.unload()
            result = active_provider.generate(
                source=source,
                output_dir=OUTPUTS / job_id,
                progress=reconstruct_progress,
                cancelled=lambda: bool(jobs[job_id]["cancel_requested"]),
                variation=int(jobs[job_id].get("variation", 0)),
                detail=jobs[job_id].get("detail", "Balanced"),
                trim=jobs[job_id].get("trim", "Balanced"),
                subject_mode=jobs[job_id].get("subject_mode", "General"),
            )
            update_job(
                job_id,
                status="complete",
                message=f"Real {jobs[job_id]['backend']} mesh generated and validated.",
                progress=100,
                model_url=f"/api/generations/{job_id}/model",
                download_url=f"/api/generations/{job_id}/download",
                prepared_image_url=f"/api/generations/{job_id}/prepared-image",
                vertices=result.vertices,
                triangles=result.triangles,
                file_size=result.file_size,
                elapsed_seconds=round(result.elapsed_seconds, 2),
                peak_vram_bytes=result.peak_vram_bytes,
            )
            if not jobs[job_id].get("versions"):
                record_model_version(
                    job_id, OUTPUTS / job_id / "model.glb", "Original generation", "original",
                    preserve_copy=False,
                )
            if jobs[job_id].get("auto_color", False):
                update_job(
                    job_id,
                    color_status="queued",
                    color_message="Shape ready — applying the separate colour pass automatically…",
                    color_brightness=1.0,
                    color_saturation=1.0,
                    color_coverage=1.0,
                    color_style="colour",
                )
                threading.Thread(target=run_color, args=(job_id,), daemon=True).start()
            profile_id = jobs[job_id].get("profile_id")
            if profile_id and jobs[job_id].get("save_to_library", True):
                title = Path(jobs[job_id]["original_name"]).stem or "Untitled model"
                profiles.save_model(profile_id, job_id, title, jobs[job_id].get("library_folder_id"))
            animation_motion = jobs[job_id].get("auto_animate_motion")
            if animation_motion:
                key = animation_key(job_id, animation_motion)
                animation_jobs[key] = {
                    "status": "queued",
                    "motion": animation_motion,
                    "message": "3D character ready. Queued for local Blender auto-rigging…",
                }
                threading.Thread(target=run_animation, args=(job_id, animation_motion), daemon=True).start()
    except GenerationCancelled as exc:
        update_job(job_id, status="cancelled", message=str(exc), progress=0)
    except Exception as exc:
        LOGGER.error("Generation %s failed\n%s", job_id, traceback.format_exc())
        update_job(job_id, status="failed", message=friendly_error(exc), progress=0)


def restore_jobs() -> None:
    for metadata in OUTPUTS.glob("*/generation.json"):
        try:
            job = json.loads(metadata.read_text(encoding="utf-8"))
            if job.get("status") in {"queued", "running"}:
                job.update(
                    status="failed",
                    message="The backend stopped before this generation completed. Please retry.",
                    progress=0,
                )
            # Older remake metadata did not retain a source-image ID. Its
            # parent generation is the durable source in that case.
            source_id = job.get("source_image_id") or job.get("candidate_of") or job["id"]
            source_matches = list((UPLOADS / source_id).glob("original.*"))
            # Keep an archival copy with the completed model too. This makes
            # remakes survive a restart even if the temporary upload folder is
            # moved or cleaned later.
            if not source_matches:
                source_matches = list((OUTPUTS / source_id).glob("source.*"))
            job["source_image_id"] = source_id
            job["source_path"] = str(source_matches[0]) if source_matches else ""
            if source_matches:
                archive = OUTPUTS / source_id / f"source{source_matches[0].suffix.lower()}"
                if not archive.is_file():
                    archive.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_matches[0], archive)
            job.setdefault("cancel_requested", False)
            jobs[job["id"]] = job
        except Exception:
            LOGGER.warning("Ignoring unreadable generation metadata: %s", metadata)


restore_jobs()


@app.middleware("http")
async def require_public_access(request, call_next):
    """Optionally protect a temporary public tunnel with an unguessable share link."""
    if not PUBLIC_ACCESS_TOKEN or request.url.path == "/access":
        return await call_next(request)
    supplied = request.cookies.get("forge_access", "")
    if hmac.compare_digest(supplied, PUBLIC_ACCESS_TOKEN):
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        return PlainTextResponse("Public access token required.", status_code=401)
    return RedirectResponse(url="/access", status_code=302)


@app.get("/access")
def grant_public_access(token: str = ""):
    if not PUBLIC_ACCESS_TOKEN:
        return RedirectResponse(url="/", status_code=302)
    if not hmac.compare_digest(token, PUBLIC_ACCESS_TOKEN):
        return PlainTextResponse(
            "This temporary share link requires its full access token.", status_code=403
        )
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        "forge_access",
        PUBLIC_ACCESS_TOKEN,
        httponly=True,
        samesite="strict",
        secure=True,
        max_age=24 * 60 * 60,
    )
    return response


def current_profile(request: Request) -> dict[str, str] | None:
    return profiles.profile_for_token(request.cookies.get("forge_profile"))


def require_profile(request: Request) -> dict[str, str]:
    profile = current_profile(request)
    if profile is None:
        raise HTTPException(401, "Create or sign in to a profile to save models.")
    return profile


def begin_profile_session(response: Response, profile: dict[str, str]) -> None:
    token = profiles.create_session(profile["id"])
    response.set_cookie("forge_profile", token, httponly=True, samesite="lax", max_age=30 * 24 * 60 * 60)


@app.get("/api/profile")
def profile_me(request: Request) -> dict[str, Any]:
    return {"profile": current_profile(request)}


@app.post("/api/profiles")
def create_profile(response: Response, display_name: str = Form(...), password: str = Form(...)) -> dict[str, Any]:
    try:
        profile = profiles.create_profile(display_name, password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    begin_profile_session(response, profile)
    return {"profile": profile}


@app.post("/api/profiles/login")
def login_profile(response: Response, display_name: str = Form(...), password: str = Form(...)) -> dict[str, Any]:
    profile = profiles.authenticate(display_name, password)
    if profile is None:
        raise HTTPException(401, "Profile name or password is incorrect.")
    begin_profile_session(response, profile)
    return {"profile": profile}


@app.post("/api/profiles/logout")
def logout_profile(request: Request, response: Response) -> dict[str, bool]:
    profiles.delete_session(request.cookies.get("forge_profile"))
    response.delete_cookie("forge_profile")
    return {"ok": True}


@app.get("/api/library")
def library(request: Request) -> dict[str, Any]:
    profile = require_profile(request)
    entries = profiles.list_models(profile["id"])
    for entry in entries:
        job = jobs.get(entry["generation_id"], {})
        entry.update(
            backend=job.get("backend", "Saved model"),
            model_url=f"/api/library/{entry['id']}/model",
            download_url=f"/api/library/{entry['id']}/download",
            source_image_url=f"/api/generations/{entry['generation_id']}/source-image",
        )
    return {"models": entries, "folders": profiles.list_folders(profile["id"])}


@app.post("/api/library/folders")
def create_library_folder(request: Request, name: str = Form(...)) -> dict[str, Any]:
    profile = require_profile(request)
    try:
        folder = profiles.create_folder(profile["id"], name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"folder": folder}


@app.patch("/api/library/folders/{folder_id}")
def rename_library_folder(request: Request, folder_id: str, name: str = Form(...)) -> dict[str, Any]:
    profile = require_profile(request)
    try:
        folder = profiles.rename_folder(profile["id"], folder_id, name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if folder is None:
        raise HTTPException(404, "Folder not found.")
    return {"folder": folder}


@app.delete("/api/library/folders/{folder_id}")
def remove_library_folder(request: Request, folder_id: str) -> dict[str, bool]:
    profile = require_profile(request)
    if not profiles.delete_folder(profile["id"], folder_id):
        raise HTTPException(404, "Folder not found.")
    return {"ok": True}


def library_file(request: Request, model_id: str) -> tuple[dict[str, str], Path]:
    profile = require_profile(request)
    entry = profiles.get_model(profile["id"], model_id)
    if entry is None:
        raise HTTPException(404, "Saved model not found.")
    path = OUTPUTS / entry["generation_id"] / "model.glb"
    if not path.is_file():
        raise HTTPException(410, "The saved GLB is no longer available on this PC.")
    return entry, path


@app.get("/api/library/{model_id}/model")
def view_saved_model(request: Request, model_id: str) -> FileResponse:
    _entry, path = library_file(request, model_id)
    return FileResponse(path, media_type="model/gltf-binary")


@app.patch("/api/library/{model_id}")
def rename_saved_model(request: Request, model_id: str, title: str = Form(...)) -> dict[str, Any]:
    profile = require_profile(request)
    try:
        entry = profiles.rename_model(profile["id"], model_id, title)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if entry is None:
        raise HTTPException(404, "Saved model not found.")
    return {"model": entry}


@app.patch("/api/library/{model_id}/folder")
def move_saved_model(request: Request, model_id: str, folder_id: str = Form("")) -> dict[str, Any]:
    profile = require_profile(request)
    entry = profiles.move_model(profile["id"], model_id, folder_id.strip() or None)
    if entry is None:
        raise HTTPException(404, "Model or destination folder not found.")
    return {"model": entry}


@app.patch("/api/library/{model_id}/tags")
def tag_saved_model(request: Request, model_id: str, tags: str = Form("")) -> dict[str, Any]:
    profile = require_profile(request)
    entry = profiles.tag_model(profile["id"], model_id, tags)
    if entry is None:
        raise HTTPException(404, "Saved model not found.")
    return {"model": entry}


@app.post("/api/library/{model_id}/share")
def share_saved_model(
    request: Request,
    model_id: str,
    allow_download: bool = Form(False),
    days: int = Form(7),
) -> dict[str, Any]:
    profile = require_profile(request)
    try:
        share = profiles.create_share(profile["id"], model_id, allow_download, days)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    share["url"] = f"{str(request.base_url).rstrip('/')}/?share={share['token']}"
    return {"share": share}


@app.delete("/api/library/{model_id}")
def remove_saved_model(request: Request, model_id: str) -> dict[str, bool]:
    profile = require_profile(request)
    if not profiles.delete_model(profile["id"], model_id):
        raise HTTPException(404, "Saved model not found.")
    return {"ok": True}


@app.get("/api/library/{model_id}/download")
def download_saved_model(request: Request, model_id: str) -> FileResponse:
    entry, path = library_file(request, model_id)
    return FileResponse(path, media_type="model/gltf-binary", filename=f"{entry['title']}.glb")


@app.get("/api/shares/{token}")
def shared_model(token: str) -> dict[str, Any]:
    share = profiles.get_share(token)
    if share is None:
        raise HTTPException(404, "This private share link is invalid or expired.")
    return {
        "title": share["title"], "generation_id": share["generation_id"],
        "allow_download": bool(share["allow_download"]),
        "model_url": f"/api/shares/{token}/model",
        "download_url": f"/api/shares/{token}/download" if share["allow_download"] else None,
        "expires_at": share["expires_at"],
    }


@app.get("/api/shares/{token}/model")
def view_shared_model(token: str) -> FileResponse:
    share = profiles.get_share(token)
    if share is None:
        raise HTTPException(404, "This private share link is invalid or expired.")
    path = OUTPUTS / str(share["generation_id"]) / "model.glb"
    if not path.is_file():
        raise HTTPException(410, "The shared model is no longer available.")
    return FileResponse(path, media_type="model/gltf-binary")


@app.get("/api/shares/{token}/download")
def download_shared_model(token: str) -> FileResponse:
    share = profiles.get_share(token)
    if share is None or not share["allow_download"]:
        raise HTTPException(403, "Download permission is not enabled for this share.")
    path = OUTPUTS / str(share["generation_id"]) / "model.glb"
    if not path.is_file():
        raise HTTPException(410, "The shared model is no longer available.")
    return FileResponse(path, media_type="model/gltf-binary", filename=f"{share['title']}.glb")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/system")
def system_info() -> dict[str, Any]:
    cuda = torch.cuda.is_available()
    result: dict[str, Any] = {
        "cuda_available": cuda,
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "fast_available": cuda,
        "quality_available": quality_provider.is_installed() and cuda,
        "quality_backend": "TripoSG",
        "mode": "Fast",
        "public_mode": PUBLIC_MODE,
        "public_jobs_per_hour": PUBLIC_JOBS_PER_HOUR if PUBLIC_MODE else None,
    }
    if cuda:
        props = torch.cuda.get_device_properties(0)
        free, total = torch.cuda.mem_get_info(0)
        result.update(
            gpu_name=props.name,
            total_vram_bytes=total,
            free_vram_bytes=free,
            target_class="8 GB laptop GPU",
        )
    else:
        result["diagnostic"] = (
            "CUDA is unavailable. Run setup.bat and verify the NVIDIA driver installation."
        )
    return result


@app.post("/api/generations/{job_id}/diagnose")
def diagnose_generation(job_id: str, issue: str = Form("general")) -> dict[str, Any]:
    """Inspect actual mesh data and recommend a safe, existing repair path."""
    _job, path = generation_file(job_id, "model.glb")
    if issue not in {"general", "color", "clumps", "detail", "scale", "animation"}:
        raise HTTPException(400, "Choose a supported issue type.")
    scene = trimesh.load(path, force="scene")
    meshes = tuple(scene.geometry.values())
    combined = trimesh.util.concatenate(meshes)
    # Splitting a dense reconstruction can allocate several copies of a mesh and
    # freeze the browser for minutes.  Keep the quick repair assistant bounded:
    # run the exact component check for ordinary assets and defer dense topology
    # cleanup to the existing Blender/Game Ready pipeline, which shows progress.
    exhaustive_component_scan = len(combined.faces) <= 250_000
    if exhaustive_component_scan:
        pieces = list(combined.split(only_watertight=False))
        largest_faces = max((len(piece.faces) for piece in pieces), default=0)
        tiny_pieces = sum(1 for piece in pieces if len(piece.faces) < max(40, int(largest_faces * 0.002)))
        connected_components = len(pieces)
    else:
        tiny_pieces = 0
        connected_components = len(meshes)
    extents = np.maximum(scene.extents, 1e-9)
    scale_ratio = float(extents.max() / extents.min())
    has_vertex_color = any(
        getattr(mesh.visual, "vertex_colors", np.empty((0, 4))).shape[0] == len(mesh.vertices)
        for mesh in meshes
    )
    checks = {
        "mesh_objects": len(meshes), "connected_components": connected_components, "tiny_components": tiny_pieces,
        "component_scan": "complete" if exhaustive_component_scan else "deferred_to_game_ready",
        "vertices": len(combined.vertices), "triangles": len(combined.faces),
        "watertight": bool(combined.is_watertight), "scale_ratio": round(scale_ratio, 2),
        "vertex_color_present": has_vertex_color,
    }
    if issue == "color":
        action = "color"
        summary = "Use Material color transfer for the base, then Paint exact placement or Paint 3D for local corrections."
    elif issue == "clumps" or tiny_pieces:
        action = "polish"
        summary = f"The mesh contains {tiny_pieces} safely identifiable tiny component(s). Create a polished copy and compare it before keeping it."
    elif issue == "animation":
        action = "animation"
        summary = "Use Animate only for a complete upright humanoid, then review the skinned GLB and editable Blender file."
    elif issue == "detail":
        action = "remake"
        summary = "Geometry detail cannot be invented safely after reconstruction. Keep the original and create a separate Quality remake candidate."
    elif issue == "scale" or scale_ratio > 40:
        action = "game_ready"
        summary = "Game Ready creates a normalized copy with a sensible pivot and validates the exported GLB."
    else:
        action = "game_ready"
        summary = "No destructive automatic repair is justified by the mesh checks. Build a Game Ready copy and compare it with the original."
    return {"status": "complete", "summary": summary, "recommended_action": action, "checks": checks}


@app.post("/api/imports", status_code=201)
async def import_glb(request: Request, model: UploadFile = File(...)) -> dict[str, Any]:
    enforce_public_job_limit(request)
    content = await model.read(200 * 1024 * 1024 + 1)
    if not content or len(content) > 200 * 1024 * 1024:
        raise HTTPException(413, "GLB is empty or larger than 200 MB.")
    if content[:4] != b"glTF":
        raise HTTPException(415, "Choose a valid binary GLB file.")
    job_id = uuid.uuid4().hex
    output_dir = OUTPUTS / job_id
    output_dir.mkdir(parents=True, exist_ok=False)
    path = output_dir / "model.glb"
    path.write_bytes(content)
    try:
        scene = trimesh.load(path, force="scene")
        vertices = sum(len(mesh.vertices) for mesh in scene.geometry.values())
        triangles = sum(len(mesh.faces) for mesh in scene.geometry.values())
        if vertices < 4:
            raise ValueError("no mesh")
    except Exception as exc:
        raise HTTPException(400, "The GLB does not contain usable mesh geometry.") from exc
    job = {
        "id": job_id, "mode": "Imported", "backend": "Imported GLB", "status": "complete",
        "message": "Imported GLB validated.", "progress": 100, "created_at": utc_now(), "updated_at": utc_now(),
        "original_name": model.filename or "imported.glb", "source_image_id": None, "source_path": "",
        "profile_id": (current_profile(request) or {}).get("id"), "save_to_library": True,
        "cancel_requested": False, "model_url": f"/api/generations/{job_id}/model",
        "download_url": f"/api/generations/{job_id}/download", "vertices": vertices,
        "triangles": triangles, "file_size": len(content), "elapsed_seconds": 0.0,
    }
    with jobs_lock:
        jobs[job_id] = job
    persist_job(job)
    if job["profile_id"]:
        profiles.save_model(job["profile_id"], job_id, Path(job["original_name"]).stem)
    return public_job(job)


def queue_text_to_model(
    request: Request,
    prompt: str = Form(...),
    mode: str = Form("Quality"),
    detail: str = Form("Sharp"),
    trim: str = Form("Clean"),
    auto_color: bool = Form(False),
    subject_mode: str = Form("General"),
    start: bool = True,
) -> dict[str, Any]:
    prompt = " ".join(prompt.split())
    if not 3 <= len(prompt) <= 500:
        raise HTTPException(400, "Describe the object in 3 to 500 characters.")
    if mode not in {"Fast", "Quality"} or detail not in {"Soft", "Balanced", "Sharp"} or trim not in {"Gentle", "Balanced", "Clean"}:
        raise HTTPException(400, "Choose valid Text to Model settings.")
    if subject_mode not in {"General", "Portrait"}:
        raise HTTPException(400, "Choose a valid subject type.")
    if not torch.cuda.is_available():
        raise HTTPException(503, "CUDA is unavailable to Text to Image.")
    if not text_to_image_provider.is_installed():
        raise HTTPException(503, "Text to Image is not installed yet. Run setup-quality.bat once, then retry.")
    if mode == "Quality" and not quality_provider.is_installed():
        raise HTTPException(503, "Quality mode is not installed yet. Run setup-quality.bat once, then retry.")

    job_id = uuid.uuid4().hex
    upload_dir = UPLOADS / job_id
    upload_dir.mkdir(parents=True, exist_ok=False)
    (OUTPUTS / job_id).mkdir(parents=True, exist_ok=True)
    source_path = upload_dir / "original.png"
    job: dict[str, Any] = {
        "id": job_id, "mode": mode, "backend": "TripoSG" if mode == "Quality" else "TripoSR",
        "variation": 0, "detail": detail, "trim": trim, "auto_color": auto_color,
        "subject_mode": subject_mode, "extra_views": {}, "multi_view_status": "text_generated_source",
        "text_prompt": prompt, "status": "queued", "message": "Queued to create an image and 3D model locally…",
        "progress": 2, "created_at": utc_now(), "updated_at": utc_now(),
        "original_name": "text-to-model.png", "source_image_id": job_id, "source_path": str(source_path),
        "profile_id": (current_profile(request) or {}).get("id"), "save_to_library": True,
        "auto_animate_motion": None, "cancel_requested": False,
    }
    with jobs_lock:
        jobs[job_id] = job
    persist_job(job)
    if start:
        threading.Thread(target=run_generation, args=(job_id,), daemon=True).start()
    return public_job(job)


def run_batch_generation(job_ids: list[str]) -> None:
    """Keep a user batch in written order and avoid competing GPU workers."""
    for job_id in job_ids:
        run_generation(job_id)


@app.post("/api/text-to-model", status_code=202)
def create_text_to_model(
    request: Request,
    prompt: str = Form(...),
    mode: str = Form("Quality"),
    detail: str = Form("Sharp"),
    trim: str = Form("Clean"),
    auto_color: bool = Form(False),
    subject_mode: str = Form("General"),
) -> dict[str, Any]:
    enforce_public_job_limit(request)
    return queue_text_to_model(request, prompt, mode, detail, trim, auto_color, subject_mode)


@app.post("/api/text-to-model/batch", status_code=202)
def create_text_to_model_batch(
    request: Request,
    prompts: str = Form(...),
    mode: str = Form("Quality"),
    detail: str = Form("Sharp"),
    trim: str = Form("Clean"),
    auto_color: bool = Form(False),
    subject_mode: str = Form("General"),
) -> dict[str, Any]:
    # One prompt per line avoids trying to cram several objects into one
    # generated picture.  Each job enters the existing GPU lock in turn.
    unique_prompts: list[str] = []
    seen: set[str] = set()
    for line in prompts.splitlines():
        value = " ".join(line.split())
        key = value.casefold()
        if value and key not in seen:
            unique_prompts.append(value)
            seen.add(key)
    if not 2 <= len(unique_prompts) <= 12:
        raise HTTPException(400, "Add between 2 and 12 different object prompts, one per line.")
    enforce_public_job_limit(request, len(unique_prompts))
    jobs = [
        queue_text_to_model(request, prompt, mode, detail, trim, auto_color, subject_mode, start=False)
        for prompt in unique_prompts
    ]
    profile = current_profile(request)
    if profile:
        try:
            folder = profiles.create_folder(profile["id"], f"Batch {datetime.now().strftime('%Y-%m-%d %H-%M-%S')}")
            for queued in jobs:
                update_job(queued["id"], library_folder_id=folder["id"])
        except ValueError:
            LOGGER.warning("Could not create an automatic library folder for the batch.")
    threading.Thread(target=run_batch_generation, args=([job["id"] for job in jobs],), daemon=True).start()
    return {"jobs": jobs, "message": f"Queued {len(jobs)} models. Forge One will make them one at a time."}


@app.post("/api/generations", status_code=202)
async def create_generation(
    request: Request,
    image: UploadFile = File(...),
    mode: str = Form("Fast"),
    detail: str = Form("Balanced"),
    trim: str = Form("Balanced"),
    auto_animate_motion: str = Form(""),
    auto_animate_full_body: bool = Form(False),
    auto_color: bool = Form(False),
    subject_mode: str = Form("General"),
    side_image: UploadFile | None = File(None),
    back_image: UploadFile | None = File(None),
) -> dict[str, Any]:
    enforce_public_job_limit(request)
    if mode not in {"Fast", "Quality"}:
        raise HTTPException(400, "Generation mode must be Fast or Quality.")
    if detail not in {"Soft", "Balanced", "Sharp"} or trim not in {"Gentle", "Balanced", "Clean"}:
        raise HTTPException(400, "Choose a valid detail and trim setting.")
    if subject_mode not in {"General", "Portrait"}:
        raise HTTPException(400, "Subject mode must be General or Portrait.")
    auto_animate_motion = auto_animate_motion.strip().lower()
    if auto_animate_motion and auto_animate_motion not in {"walk", "run", "jump"}:
        raise HTTPException(400, "Choose Walk, Run, or Jump for automatic animation.")
    if auto_animate_motion and not auto_animate_full_body:
        raise HTTPException(400, "Automatic animation needs a full, upright humanoid with arms and legs.")
    content = await image.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Image is larger than the 25 MB limit.")
    if not content:
        raise HTTPException(400, "Choose a non-empty image file.")

    from io import BytesIO

    try:
        with Image.open(BytesIO(content)) as inspected:
            inspected.verify()
            image_format = inspected.format
        if image_format not in ALLOWED_FORMATS:
            raise HTTPException(415, "Use a PNG, JPG/JPEG, or WebP image.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, "The uploaded file is corrupt or is not a supported image.") from exc

    if not torch.cuda.is_available():
        raise HTTPException(503, "CUDA is unavailable to the Fast backend.")
    if mode == "Quality" and not quality_provider.is_installed():
        raise HTTPException(503, "Quality mode is not installed yet. Run setup-quality.bat once, then retry.")

    job_id = uuid.uuid4().hex
    upload_dir = UPLOADS / job_id
    upload_dir.mkdir(parents=True, exist_ok=False)
    source_path = upload_dir / f"original{ALLOWED_FORMATS[image_format]}"
    source_path.write_bytes(content)
    archive_dir = OUTPUTS / job_id
    archive_dir.mkdir(parents=True, exist_ok=True)
    archived_source = archive_dir / f"source{ALLOWED_FORMATS[image_format]}"
    archived_source.write_bytes(content)
    extra_views: dict[str, str] = {}
    for view_name, upload in (("side", side_image), ("back", back_image)):
        if upload is None or not upload.filename:
            continue
        view_content = await upload.read(MAX_UPLOAD_BYTES + 1)
        if not view_content or len(view_content) > MAX_UPLOAD_BYTES:
            raise HTTPException(400, f"The {view_name} image is empty or larger than 25 MB.")
        try:
            with Image.open(BytesIO(view_content)) as inspected:
                inspected.verify()
                view_format = inspected.format
            if view_format not in ALLOWED_FORMATS:
                raise HTTPException(415, f"Use PNG, JPG/JPEG, or WebP for the {view_name} image.")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(400, f"The {view_name} image is corrupt.") from exc
        view_path = archive_dir / f"view-{view_name}{ALLOWED_FORMATS[view_format]}"
        view_path.write_bytes(view_content)
        extra_views[view_name] = str(view_path.name)
    job: dict[str, Any] = {
        "id": job_id,
        "mode": mode,
        "backend": "TripoSG" if mode == "Quality" else "TripoSR",
        "variation": 0,
        "detail": detail,
        "trim": trim,
        "auto_color": auto_color,
        "subject_mode": subject_mode,
        "extra_views": extra_views,
        "multi_view_status": "stored_for_compatible_engine" if extra_views else "single_view",
        "status": "queued",
        "message": "Queued for local generation…",
        "progress": 2,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "original_name": image.filename or source_path.name,
        "source_image_id": job_id,
        "source_path": str(source_path),
        "profile_id": (current_profile(request) or {}).get("id"),
        "save_to_library": True,
        "auto_animate_motion": auto_animate_motion or None,
        "cancel_requested": False,
    }
    with jobs_lock:
        jobs[job_id] = job
    persist_job(job)
    threading.Thread(target=run_generation, args=(job_id,), daemon=True).start()
    return public_job(job)


@app.post("/api/generations/{job_id}/remake", status_code=202)
def remake_generation(job_id: str, request: Request) -> dict[str, Any]:
    """Queue a distinct reconstruction from the same original image."""
    with jobs_lock:
        previous = jobs.get(job_id)
        if previous is None:
            raise HTTPException(404, "Generation not found.")
        if not Path(previous["source_path"]).is_file():
            raise HTTPException(410, "The original image for this model is no longer available.")
        new_id = uuid.uuid4().hex
        job = {
            **{key: value for key, value in previous.items() if key not in {
                "model_url", "download_url", "prepared_image_url", "vertices", "triangles",
                "file_size", "elapsed_seconds", "peak_vram_bytes"
            }},
            "id": new_id,
            "status": "queued",
            "message": "Queued as a new reconstruction variant…",
            "progress": 2,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "cancel_requested": False,
            "variation": int(previous.get("variation", 0)) + 1,
            # A remake is a reviewable candidate. It never overwrites or
            # auto-saves over the original model.
            "candidate_of": job_id,
            "save_to_library": False,
            # Preserve the original owner's library association rather than
            # letting another public visitor claim their source image.
            "profile_id": previous.get("profile_id") or (current_profile(request) or {}).get("id"),
        }
        jobs[new_id] = job
    persist_job(job)
    threading.Thread(target=run_generation, args=(new_id,), daemon=True).start()
    return public_job(job)


@app.post("/api/generations/{job_id}/keep-remake")
def keep_remake(job_id: str, request: Request) -> dict[str, Any]:
    """Explicitly add a remake candidate to the owner's library."""
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Generation not found.")
        if not job.get("candidate_of") or job.get("status") != "complete":
            raise HTTPException(400, "This generation is not a completed remake candidate.")
        owner = job.get("profile_id")
    if owner:
        profile = require_profile(request)
        if profile["id"] != owner:
            raise HTTPException(403, "Only the profile that made this candidate can save it.")
        title = f"{Path(job['original_name']).stem or 'Untitled model'} remake"
        profiles.save_model(owner, job_id, title)
    return {"ok": True, "generation": public_job(job)}


@app.get("/api/generations/{job_id}")
def get_generation(job_id: str) -> dict[str, Any]:
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Generation not found.")
        return public_job(dict(job))


def model_version_file(job_id: str, version_id: str) -> tuple[dict[str, Any], Path]:
    generation_file(job_id, "model.glb")
    with jobs_lock:
        entry = next((item for item in jobs[job_id].get("versions", []) if item.get("id") == version_id), None)
    if entry is None:
        raise HTTPException(404, "Model version not found.")
    root = (OUTPUTS / job_id).resolve()
    path = (root / str(entry["file"])).resolve()
    if root not in path.parents and path != root:
        raise HTTPException(400, "Invalid model version path.")
    if not path.is_file():
        raise HTTPException(410, "This model version file is missing.")
    return entry, path


@app.get("/api/generations/{job_id}/versions")
def list_model_versions(job_id: str) -> dict[str, Any]:
    generation_file(job_id, "model.glb")
    if not jobs[job_id].get("versions"):
        record_model_version(job_id, OUTPUTS / job_id / "model.glb", "Original generation", "original", preserve_copy=False)
    with jobs_lock:
        versions = [dict(item) for item in jobs[job_id].get("versions", [])]
    for item in versions:
        item.update(
            model_url=f"/api/generations/{job_id}/versions/{item['id']}/model",
            download_url=f"/api/generations/{job_id}/versions/{item['id']}/download",
        )
        item.pop("file", None)
    return {"versions": versions}


@app.get("/api/generations/{job_id}/versions/{version_id}/model")
def view_model_version(job_id: str, version_id: str) -> FileResponse:
    _entry, path = model_version_file(job_id, version_id)
    return FileResponse(path, media_type="model/gltf-binary")


@app.get("/api/generations/{job_id}/versions/{version_id}/download")
def download_model_version(job_id: str, version_id: str) -> FileResponse:
    entry, path = model_version_file(job_id, version_id)
    safe_label = re.sub(r"[^a-z0-9]+", "-", str(entry["label"]).lower()).strip("-") or "model-version"
    return FileResponse(path, media_type="model/gltf-binary", filename=f"{safe_label}.glb")


@app.post("/api/generations/{job_id}/cancel")
def cancel_generation(job_id: str) -> dict[str, Any]:
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Generation not found.")
        if job["status"] in {"complete", "failed", "cancelled"}:
            return public_job(dict(job))
        job["cancel_requested"] = True
        job["message"] = "Cancellation requested; stopping at the next safe checkpoint…"
        snapshot = dict(job)
    persist_job(snapshot)
    return public_job(snapshot)


def generation_file(job_id: str, filename: str) -> tuple[dict[str, Any], Path]:
    with jobs_lock:
        job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Generation not found.")
    if job["status"] != "complete":
        raise HTTPException(409, "The generated model is not ready.")
    path = OUTPUTS / job_id / filename
    if not path.is_file():
        raise HTTPException(404, "The generated file is missing.")
    return job, path


@app.get("/api/generations/{job_id}/source-image")
def source_image(job_id: str) -> FileResponse:
    with jobs_lock:
        job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Generation not found.")
    source = Path(job.get("source_path", ""))
    if not source.is_file():
        source_id = job.get("source_image_id", job_id)
        candidates = list((OUTPUTS / source_id).glob("source.*"))
        if not candidates:
            raise HTTPException(410, "The saved source image is unavailable.")
        source = candidates[0]
    return FileResponse(source)


@app.get("/api/generations/{job_id}/model")
def view_model(job_id: str) -> FileResponse:
    _job, path = generation_file(job_id, "model.glb")
    return FileResponse(path, media_type="model/gltf-binary")


@app.get("/api/generations/{job_id}/download")
def download_model(job_id: str) -> FileResponse:
    _job, path = generation_file(job_id, "model.glb")
    return FileResponse(path, media_type="model/gltf-binary", filename=f"triposr-{job_id[:8]}.glb")


@app.post("/api/generations/{job_id}/color", status_code=202)
def start_color_pass(
    job_id: str,
    brightness: float = Form(1.0),
    saturation: float = Form(1.0),
    coverage: float = Form(1.0),
    style: str = Form("colour"),
    palette: str = Form(""),
    paint_guides: str = Form(""),
) -> dict[str, Any]:
    generation_file(job_id, "model.glb")
    if not 0.5 <= brightness <= 1.5 or not 0.0 <= saturation <= 2.0 or not 0.25 <= coverage <= 1.5:
        raise HTTPException(400, "Choose valid brightness, saturation, and coverage settings.")
    if style not in {"colour", "detail"}:
        raise HTTPException(400, "Choose natural colour transfer or exact photo projection.")
    try:
        palette_values = json.loads(palette) if palette else []
        if not isinstance(palette_values, list) or len(palette_values) > 3:
            raise ValueError
        # Validate before starting a background job, keeping failed requests
        # responsive and the existing colored copy intact.
        if any(not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value) for value in palette_values):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(400, "Choose up to three valid palette colours.")
    try:
        guide_values = json.loads(paint_guides) if paint_guides else []
        if not isinstance(guide_values, list) or len(guide_values) > 1200:
            raise ValueError
        for guide in guide_values:
            if not isinstance(guide, dict) or not re.fullmatch(r"#[0-9a-fA-F]{6}", str(guide.get("color", ""))):
                raise ValueError
            if not 0 <= float(guide.get("x")) <= 1 or not 0 <= float(guide.get("y")) <= 1 or not 0.003 <= float(guide.get("radius", 0.04)) <= 0.35:
                raise ValueError
    except (TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(400, "Paint-map guides must be valid marks on the source image.")
    with jobs_lock:
        job = jobs[job_id]
        current = public_color_status(job_id)
        if current["status"] in {"queued", "running"}:
            return current
        job["color_status"] = "queued"
        job["color_message"] = "Queued for a separate local colour pass…"
        job["color_brightness"] = brightness
        job["color_saturation"] = saturation
        job["color_coverage"] = coverage
        job["color_style"] = style
        job["color_palette"] = palette_values
        job["color_paint_guides"] = guide_values
        snapshot = dict(job)
    persist_job(snapshot)
    threading.Thread(target=run_color, args=(job_id,), daemon=True).start()
    return public_color_status(job_id)


@app.get("/api/generations/{job_id}/color")
def color_status(job_id: str) -> dict[str, Any]:
    generation_file(job_id, "model.glb")
    with jobs_lock:
        return public_color_status(job_id)


@app.get("/api/generations/{job_id}/color/model")
def view_colored_model(job_id: str) -> FileResponse:
    path = color_output_path(job_id)
    if not path.is_file():
        raise HTTPException(404, "The separate colour pass is not ready yet.")
    return FileResponse(path, media_type="model/gltf-binary")


@app.get("/api/generations/{job_id}/color/download")
def download_colored_model(job_id: str) -> FileResponse:
    path = color_output_path(job_id)
    if not path.is_file():
        raise HTTPException(404, "The separate colour pass is not ready yet.")
    return FileResponse(path, media_type="model/gltf-binary", filename=f"forge-one-colored-{job_id[:8]}.glb")


@app.post("/api/generations/{job_id}/texture-bake")
def bake_model_texture(
    job_id: str,
    resolution: int = Form(1024),
) -> dict[str, Any]:
    """Bake vertex colour into a UV texture on a separate, verified GLB."""
    generation_file(job_id, "model.glb")
    if resolution not in {512, 1024, 2048}:
        raise HTTPException(400, "Choose a 512, 1024, or 2048 pixel texture.")
    source = color_output_path(job_id)
    if not source.is_file():
        raise HTTPException(409, "Apply color first, then bake it into a game texture.")
    if not BLENDER.is_file():
        raise HTTPException(503, "Blender 4.2 is required for texture baking.")
    directory = OUTPUTS / job_id / "texture-bake"
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / "model_textured.glb"
    report = directory / "report.json"
    completed = subprocess.run(
        [
            str(BLENDER), "--background", "--python", str(ROOT / "scripts" / "bake_vertex_color_texture.py"), "--",
            "--input", str(source), "--output", str(output), "--report", str(report), "--resolution", str(resolution),
        ],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
    )
    if completed.returncode != 0 or not report.is_file() or not output.is_file():
        detail = (completed.stderr or completed.stdout or "Texture baking did not finish.").strip()
        raise HTTPException(500, f"Texture baking failed safely: {detail[-900:]}")
    result = json.loads(report.read_text(encoding="utf-8"))
    result.update(
        model_url=f"/api/generations/{job_id}/texture-bake/model",
        download_url=f"/api/generations/{job_id}/texture-bake/download",
    )
    try:
        record_model_version(
            job_id, output, f"Baked {resolution}px texture", "texture",
            details={"texture_resolution": resolution},
        )
    except Exception:
        LOGGER.exception("Could not archive the textured version for %s", job_id)
    return result


@app.get("/api/generations/{job_id}/texture-bake/model")
def view_baked_texture(job_id: str) -> FileResponse:
    path = OUTPUTS / job_id / "texture-bake" / "model_textured.glb"
    if not path.is_file():
        raise HTTPException(404, "No baked texture GLB exists yet.")
    return FileResponse(path, media_type="model/gltf-binary")


@app.get("/api/generations/{job_id}/texture-bake/download")
def download_baked_texture(job_id: str) -> FileResponse:
    path = OUTPUTS / job_id / "texture-bake" / "model_textured.glb"
    if not path.is_file():
        raise HTTPException(404, "No baked texture GLB exists yet.")
    return FileResponse(path, media_type="model/gltf-binary", filename="model_textured.glb")


@app.post("/api/generations/{job_id}/refine")
def refine_model(
    job_id: str,
    smooth: int = Form(1),
    trim: float = Form(0.002),
    simplify: float = Form(1.0),
) -> dict[str, Any]:
    _job, source = generation_file(job_id, "model.glb")
    if not 0 <= smooth <= 5 or not 0 <= trim <= 0.02 or not 0.2 <= simplify <= 1.0:
        raise HTTPException(400, "Choose valid mesh polish settings.")
    scene = trimesh.load(source, force="scene")
    mesh = trimesh.util.concatenate(tuple(scene.geometry.values()))
    pieces = list(mesh.split(only_watertight=False))
    if len(pieces) > 1 and trim > 0:
        floor = max(40, int(len(mesh.faces) * trim))
        mesh = trimesh.util.concatenate([piece for piece in pieces if len(piece.faces) >= floor] or [max(pieces, key=lambda part: len(part.faces))])
    if smooth:
        trimesh.smoothing.filter_taubin(mesh, lamb=0.25, nu=0.3, iterations=smooth)
    if simplify < 0.999:
        try:
            mesh = mesh.simplify_quadric_decimation(face_count=max(100, int(len(mesh.faces) * simplify)))
        except Exception:
            LOGGER.warning("Mesh simplification unavailable; exported cleaned mesh without decimation.")
    mesh.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(mesh, multibody=True)
    output = OUTPUTS / job_id / "model-refined.glb"
    output.write_bytes(trimesh.Scene(mesh).export(file_type="glb"))
    try:
        record_model_version(
            job_id, output, "Polished mesh", "polish",
            details={"smooth": smooth, "trim": trim, "simplify": simplify},
        )
    except Exception:
        LOGGER.exception("Could not archive the polished version for %s", job_id)
    return {
        "status": "complete", "message": "Mesh polish candidate created; geometry master preserved.",
        "model_url": f"/api/generations/{job_id}/refine/model", "download_url": f"/api/generations/{job_id}/refine/download",
        "vertices": len(mesh.vertices), "triangles": len(mesh.faces), "file_size": output.stat().st_size,
    }


@app.get("/api/generations/{job_id}/refine/model")
def view_refined_model(job_id: str) -> FileResponse:
    path = OUTPUTS / job_id / "model-refined.glb"
    if not path.is_file():
        raise HTTPException(404, "No refined candidate exists yet.")
    return FileResponse(path, media_type="model/gltf-binary")


@app.get("/api/generations/{job_id}/refine/download")
def download_refined_model(job_id: str) -> FileResponse:
    path = OUTPUTS / job_id / "model-refined.glb"
    if not path.is_file():
        raise HTTPException(404, "No refined candidate exists yet.")
    return FileResponse(path, media_type="model/gltf-binary", filename=f"forge-one-refined-{job_id[:8]}.glb")


@app.get("/api/generations/{job_id}/export/{file_format}")
def export_model(job_id: str, file_format: str) -> FileResponse:
    """Create a portable OBJ or print-friendly STL beside a finished GLB."""
    if file_format not in {"obj", "stl"}:
        raise HTTPException(400, "Export format must be OBJ or STL.")
    _job, path = generation_file(job_id, "model.glb")
    export_path = path.with_suffix(f".{file_format}")
    if not export_path.is_file() or export_path.stat().st_mtime < path.stat().st_mtime:
        scene = trimesh.load(path, force="scene")
        mesh = trimesh.util.concatenate(tuple(scene.geometry.values()))
        mesh.export(export_path, file_type=file_format)
    media_type = "model/stl" if file_format == "stl" else "text/plain"
    return FileResponse(export_path, media_type=media_type, filename=f"forge-one-{job_id[:8]}.{file_format}")


@app.post("/api/generations/{job_id}/game-ready", status_code=202)
def start_game_ready(
    job_id: str,
    preset: str = Form("game"),
    source_kind: str = Form("original"),
    force: bool = Form(False),
) -> dict[str, Any]:
    """Optimize a separate copy of a completed GLB; generation is never modified."""
    generation_file(job_id, "model.glb")
    preset = preset.strip().lower()
    source_kind = source_kind.strip().lower()
    if preset not in GAME_READY_PRESETS:
        raise HTTPException(400, "Choose High Detail, Game Ready, or Low Poly.")
    source = game_ready_source(job_id, source_kind)
    paths = game_ready_paths(job_id, preset, source_kind)
    current = public_game_ready(job_id, preset, source_kind)
    if current.get("status") in {"queued", "running"}:
        return current
    if (
        not force
        and
        current.get("status") == "complete"
        and paths["glb"].is_file()
        and paths["glb"].stat().st_mtime >= source.stat().st_mtime
    ):
        return current
    paths["directory"].mkdir(parents=True, exist_ok=True)
    for stale in (paths["progress"], paths["report"]):
        try:
            stale.unlink()
        except FileNotFoundError:
            pass
    key = game_ready_key(job_id, preset, source_kind)
    game_ready_jobs[key] = {"status": "queued", "progress": 2, "message": "Game Ready optimization queued locally…"}
    threading.Thread(target=run_game_ready, args=(job_id, preset, source_kind), daemon=True).start()
    return public_game_ready(job_id, preset, source_kind)


@app.get("/api/generations/{job_id}/game-ready")
def game_ready_status(job_id: str, preset: str = "game", source_kind: str = "original") -> dict[str, Any]:
    generation_file(job_id, "model.glb")
    preset = preset.strip().lower()
    source_kind = source_kind.strip().lower()
    if preset not in GAME_READY_PRESETS:
        raise HTTPException(400, "Unknown Game Ready preset.")
    game_ready_source(job_id, source_kind)
    return public_game_ready(job_id, preset, source_kind)


@app.get("/api/generations/{job_id}/game-ready/original/download")
def download_game_ready_original(job_id: str, source_kind: str = "original") -> FileResponse:
    generation_file(job_id, "model.glb")
    source = game_ready_source(job_id, source_kind.strip().lower())
    return FileResponse(source, media_type="model/gltf-binary", filename="model_original.glb")


@app.get("/api/generations/{job_id}/game-ready/{preset}/model")
def view_game_ready(job_id: str, preset: str, source_kind: str = "original") -> FileResponse:
    preset = preset.strip().lower()
    source_kind = source_kind.strip().lower()
    if preset not in GAME_READY_PRESETS:
        raise HTTPException(404, "Unknown Game Ready preset.")
    if public_game_ready(job_id, preset, source_kind).get("status") != "complete":
        raise HTTPException(409, "The optimized GLB is still being prepared.")
    path = game_ready_paths(job_id, preset, source_kind)["glb"]
    if not path.is_file():
        raise HTTPException(404, "The optimized GLB is not ready yet.")
    return FileResponse(path, media_type="model/gltf-binary")


@app.get("/api/generations/{job_id}/game-ready/{preset}/download")
def download_game_ready(job_id: str, preset: str, source_kind: str = "original") -> FileResponse:
    preset = preset.strip().lower()
    source_kind = source_kind.strip().lower()
    if preset not in GAME_READY_PRESETS:
        raise HTTPException(404, "Unknown Game Ready preset.")
    if public_game_ready(job_id, preset, source_kind).get("status") != "complete":
        raise HTTPException(409, "The optimized GLB is still being prepared.")
    path = game_ready_paths(job_id, preset, source_kind)["glb"]
    if not path.is_file():
        raise HTTPException(404, "The optimized GLB is not ready yet.")
    return FileResponse(path, media_type="model/gltf-binary", filename="model_game_ready.glb")


@app.post("/api/generations/{job_id}/game-package")
def create_game_package(job_id: str, source_kind: str = Form("original")) -> dict[str, Any]:
    """Build a validated three-LOD GLB package and a simple collision proxy."""
    generation_file(job_id, "model.glb")
    source_kind = source_kind.strip().lower()
    source = game_ready_source(job_id, source_kind)
    if not BLENDER.is_file():
        raise HTTPException(503, "Blender 4.2 is required for a game package.")
    directory = OUTPUTS / job_id / "game-package" / source_kind
    directory.mkdir(parents=True, exist_ok=True)
    reports: dict[str, Any] = {}
    with game_package_lock:
        for preset, filename in (("high", "model_lod0_high.glb"), ("game", "model_lod1_game.glb"), ("low", "model_lod2_low.glb")):
            output = directory / filename
            report = directory / f"{preset}.json"
            progress = directory / f"{preset}-progress.json"
            completed = subprocess.run(
                [
                    str(BLENDER), "--background", "--python", str(ROOT / "scripts" / "prepare_game_ready.py"), "--",
                    "--input", str(source), "--output", str(output), "--report", str(report),
                    "--progress", str(progress), "--preset", preset,
                ],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
            )
            if completed.returncode != 0 or not report.is_file() or not output.is_file():
                detail = (completed.stderr or completed.stdout or f"{preset} LOD failed.").strip()
                raise HTTPException(500, f"Game package stopped safely: {detail[-900:]}")
            reports[preset] = json.loads(report.read_text(encoding="utf-8"))
            # Independent reload outside Blender catches malformed packages.
            loaded = trimesh.load(output, force="scene")
            if not loaded.geometry:
                raise HTTPException(500, f"The {preset} LOD did not reload as a valid GLB.")

        source_scene = trimesh.load(source, force="scene")
        bounds = source_scene.bounds
        extents = np.maximum(bounds[1] - bounds[0], 1e-5)
        collision_transform = np.eye(4)
        collision_transform[:3, 3] = (bounds[0] + bounds[1]) * 0.5
        collision = trimesh.creation.box(extents=extents, transform=collision_transform)
        collision.metadata["name"] = "COLLISION_SIMPLE_BOX"
        collision_path = directory / "collision_simple_box.glb"
        collision_path.write_bytes(trimesh.Scene(collision).export(file_type="glb"))
        if not trimesh.load(collision_path, force="scene").geometry:
            raise HTTPException(500, "The collision proxy failed validation.")

        manifest = {
            "format": "glTF 2.0 GLB", "units": "meters", "up_axis": "Y", "source_kind": source_kind,
            "lods": {
                "LOD0": {"file": "model_lod0_high.glb", "purpose": "close camera", "report": reports["high"]},
                "LOD1": {"file": "model_lod1_game.glb", "purpose": "recommended gameplay", "report": reports["game"]},
                "LOD2": {"file": "model_lod2_low.glb", "purpose": "distance/performance", "report": reports["low"]},
            },
            "collision": {"file": collision_path.name, "type": "simple box proxy"},
            "engine_notes": {
                "Unity": "Import as glTF/GLB, keep scale factor 1, and use collision_simple_box as a BoxCollider reference.",
                "Unreal": "Import as a static mesh in meters; assign LOD0/1/2 in order and use the collision GLB as a simple collision guide.",
                "Godot": "Import the GLBs at scale 1; use LOD visibility ranges and create a StaticBody3D from the collision proxy.",
            },
            "texture_compression": "Textures remain embedded and lossless. KTX2 is intentionally skipped because no verified BasisU encoder is installed.",
        }
        manifest_path = directory / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        archive = directory / "forge-one-game-package.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as package:
            for name in ("model_lod0_high.glb", "model_lod1_game.glb", "model_lod2_low.glb", collision_path.name, manifest_path.name):
                package.write(directory / name, arcname=name)
    return {
        "status": "complete", "message": "Three LODs, collision proxy, and engine notes built and verified.",
        "download_url": f"/api/generations/{job_id}/game-package/download?source_kind={source_kind}",
        "file_size": archive.stat().st_size, "manifest": manifest,
    }


@app.get("/api/generations/{job_id}/game-package/download")
def download_game_package(job_id: str, source_kind: str = "original") -> FileResponse:
    path = OUTPUTS / job_id / "game-package" / source_kind.strip().lower() / "forge-one-game-package.zip"
    if not path.is_file():
        raise HTTPException(404, "Build the game package before downloading it.")
    return FileResponse(path, media_type="application/zip", filename="forge-one-game-package.zip")


@app.post("/api/generations/{job_id}/animation", status_code=202)
def start_animation(
    job_id: str,
    motion: str = Form("walk"),
    full_body_humanoid: bool = Form(False),
) -> dict[str, Any]:
    """Create a local automatic character rig and a small editable motion clip."""
    motion = motion.strip().lower()
    if motion not in {"walk", "run", "jump"}:
        raise HTTPException(400, "Choose Walk, Run, or Jump.")
    if not full_body_humanoid:
        raise HTTPException(400, "Forge Animate only rigs a full, upright humanoid. Props and partial models are not safe to animate.")
    _job, source = generation_file(job_id, "model.glb")
    if not source.is_file():
        raise HTTPException(410, "The model file is no longer available on this PC.")
    key = animation_key(job_id, motion)
    current = public_animation(job_id, motion)
    if current.get("status") in {"queued", "running"}:
        return current
    if current.get("status") == "complete":
        return current
    animation_jobs[key] = {"status": "queued", "motion": motion, "message": "Queued for local Blender auto-rigging…"}
    threading.Thread(target=run_animation, args=(job_id, motion), daemon=True).start()
    return public_animation(job_id, motion)


@app.get("/api/generations/{job_id}/animation/{motion}")
def animation_status(job_id: str, motion: str) -> dict[str, Any]:
    generation_file(job_id, "model.glb")
    return public_animation(job_id, motion.strip().lower())


@app.get("/api/generations/{job_id}/animation/{motion}/download")
def download_animation_blend(job_id: str, motion: str) -> FileResponse:
    paths = animation_paths(job_id, motion.strip().lower())
    if not paths["blend"].is_file():
        raise HTTPException(404, "The editable animation source is not ready yet.")
    return FileResponse(paths["blend"], media_type="application/octet-stream", filename=f"forge-one-{motion}-editable.blend")


@app.get("/api/generations/{job_id}/animation/{motion}/model")
def download_animation_glb(job_id: str, motion: str) -> FileResponse:
    paths = animation_paths(job_id, motion.strip().lower())
    if not paths["glb"].is_file():
        raise HTTPException(404, "The animated GLB is not ready yet.")
    return FileResponse(paths["glb"], media_type="model/gltf-binary", filename=f"forge-one-{motion}.glb")


@app.get("/api/generations/{job_id}/prepared-image")
def prepared_image(job_id: str) -> FileResponse:
    _job, path = generation_file(job_id, "prepared-input.png")
    return FileResponse(path, media_type="image/png")


if FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=7860, reload=False)
