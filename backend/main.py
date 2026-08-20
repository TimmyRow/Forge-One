from __future__ import annotations

import json
import logging
import mimetypes
import hmac
import os
import threading
import traceback
import uuid
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import torch
import trimesh
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError

from backend.providers import TripoSGProvider, TripoSRProvider
from backend.providers.triposr import GenerationCancelled
from backend.profiles import ProfileStore

ROOT = Path(__file__).resolve().parents[1]
UPLOADS = ROOT / "uploads"
OUTPUTS = ROOT / "outputs"
LOGS = ROOT / "logs"
DATA = ROOT / "data"
FRONTEND = ROOT / "frontend" / "dist"
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
generation_lock = threading.Lock()
jobs_lock = threading.Lock()
jobs: dict[str, dict[str, Any]] = {}
profiles = ProfileStore(DATA / "forge-one.sqlite3")
PUBLIC_ACCESS_TOKEN = os.getenv("FORGE_ACCESS_TOKEN", "")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def run_generation(job_id: str) -> None:
    def progress(message: str, percent: int) -> None:
        update_job(job_id, status="running", message=message, progress=percent)

    try:
        with generation_lock:
            if jobs[job_id]["cancel_requested"]:
                raise GenerationCancelled("Generation was cancelled.")
            source = Path(jobs[job_id]["source_path"])
            mode = jobs[job_id]["mode"]
            active_provider = quality_provider if mode == "Quality" else fast_provider
            if mode == "Quality":
                # Do not hold the Fast model in VRAM while the isolated TripoSG
                # worker is trying to fit on an 8 GB GPU.
                fast_provider.unload()
            result = active_provider.generate(
                source=source,
                output_dir=OUTPUTS / job_id,
                progress=progress,
                cancelled=lambda: bool(jobs[job_id]["cancel_requested"]),
                variation=int(jobs[job_id].get("variation", 0)),
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
            profile_id = jobs[job_id].get("profile_id")
            if profile_id:
                title = Path(jobs[job_id]["original_name"]).stem or "Untitled model"
                profiles.save_model(profile_id, job_id, title)
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
            source_matches = list((UPLOADS / job["id"]).glob("original.*"))
            job["source_path"] = str(source_matches[0]) if source_matches else ""
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
        )
    return {"models": entries}


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


@app.get("/api/library/{model_id}/download")
def download_saved_model(request: Request, model_id: str) -> FileResponse:
    entry, path = library_file(request, model_id)
    return FileResponse(path, media_type="model/gltf-binary", filename=f"{entry['title']}.glb")


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


@app.post("/api/generations", status_code=202)
async def create_generation(request: Request, image: UploadFile = File(...), mode: str = Form("Fast")) -> dict[str, Any]:
    if mode not in {"Fast", "Quality"}:
        raise HTTPException(400, "Generation mode must be Fast or Quality.")
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
    job: dict[str, Any] = {
        "id": job_id,
        "mode": mode,
        "backend": "TripoSG" if mode == "Quality" else "TripoSR",
        "variation": 0,
        "status": "queued",
        "message": "Queued for local generation…",
        "progress": 2,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "original_name": image.filename or source_path.name,
        "source_path": str(source_path),
        "profile_id": (current_profile(request) or {}).get("id"),
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
            # Preserve the original owner's library association rather than
            # letting another public visitor claim their source image.
            "profile_id": previous.get("profile_id") or (current_profile(request) or {}).get("id"),
        }
        jobs[new_id] = job
    persist_job(job)
    threading.Thread(target=run_generation, args=(new_id,), daemon=True).start()
    return public_job(job)


@app.get("/api/generations/{job_id}")
def get_generation(job_id: str) -> dict[str, Any]:
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Generation not found.")
        return public_job(dict(job))


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


@app.get("/api/generations/{job_id}/model")
def view_model(job_id: str) -> FileResponse:
    _job, path = generation_file(job_id, "model.glb")
    return FileResponse(path, media_type="model/gltf-binary")


@app.get("/api/generations/{job_id}/download")
def download_model(job_id: str) -> FileResponse:
    _job, path = generation_file(job_id, "model.glb")
    return FileResponse(path, media_type="model/gltf-binary", filename=f"triposr-{job_id[:8]}.glb")


@app.get("/api/generations/{job_id}/prepared-image")
def prepared_image(job_id: str) -> FileResponse:
    _job, path = generation_file(job_id, "prepared-input.png")
    return FileResponse(path, media_type="image/png")


if FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=7860, reload=False)
