from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from garden_jihan.analysis.quran import QuranReference
from garden_jihan.config import Settings
from garden_jihan.jobs import JobManager
from garden_jihan.media.framing import (
    FramingDecision,
    analyze_auto_framing,
    auto_framing_runtime_status,
)
from garden_jihan.media.probe import probe_media
from garden_jihan.media.render import caption_cues_for_range, render_clip
from garden_jihan.media.sources import inspect_source
from garden_jihan.models import AnalysisMode, AnalyzeRequest, ExportRequest, SourceInspectRequest
from garden_jihan.security import LocalSecurityMiddleware, new_session_token, safe_job_path

ALLOWED_UPLOAD_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
MAX_QURAN_REFERENCE_BYTES = 8 * 1024 * 1024


def _quran_reference_status(reference: QuranReference) -> dict:
    source = {
        key: reference.source.get(key)
        for key in ("name", "version", "profile", "license", "license_url", "url", "updates")
        if reference.source.get(key)
    }
    return {
        "installed": reference.installed,
        "available": reference.available,
        "verified": reference.available,
        "verses": len(reference.records),
        "source": source,
        "integrity": reference.integrity,
        "validation_error": reference.validation_error,
    }


def create_app(port: int, settings: Settings | None = None, session_token: str | None = None) -> FastAPI:
    settings = settings or Settings()
    token = session_token or new_session_token()
    app = FastAPI(title="Garden of Jihan", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.session_token = token
    app.state.jobs = JobManager(settings)

    app.add_middleware(LocalSecurityMiddleware, session_token=token, port=port)
    ui_dir = Path(__file__).parent / "ui"
    app.mount("/static", StaticFiles(directory=ui_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def home():
        html = (ui_dir / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(html.replace("__GOJ_TOKEN__", token))

    @app.get("/api/health")
    async def health():
        auto_framing_available, _message = auto_framing_runtime_status()
        return {
            "ok": True,
            "local": True,
            "version": "0.1.0",
            "auto_framing_available": auto_framing_available,
        }

    @app.get("/api/quran/reference")
    async def quran_reference_status():
        reference = QuranReference(settings.quran_reference)
        return _quran_reference_status(reference)

    @app.post("/api/quran/reference")
    async def install_quran_reference(file: Annotated[UploadFile, File()]):
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".txt", ".text"}:
            raise HTTPException(status_code=415, detail="Choose the official Tanzil UTF-8 text file")
        raw = await file.read(MAX_QURAN_REFERENCE_BYTES + 1)
        if len(raw) > MAX_QURAN_REFERENCE_BYTES:
            raise HTTPException(status_code=413, detail="Quran reference file is unexpectedly large")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="Quran reference must be UTF-8 text") from exc
        try:
            reference = QuranReference.install_tanzil_text(text, settings.quran_reference)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _quran_reference_status(reference)

    @app.post("/api/source/inspect")
    async def inspect(payload: SourceInspectRequest):
        try:
            info = inspect_source(str(payload.url), settings.max_video_seconds)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "provider": info.provider,
            "url": info.url,
            "title": info.title,
            "duration": info.duration,
            "live_status": info.live_status,
        }

    @app.post("/api/upload")
    async def upload(request: Request, file: Annotated[UploadFile, File()]):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.max_upload_bytes + 1024 * 1024:
            raise HTTPException(status_code=413, detail="Upload is too large")
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
            raise HTTPException(status_code=415, detail="Unsupported video file extension")
        job = app.state.jobs.create_upload_job()
        folder = safe_job_path(settings.jobs_dir, job.id)
        destination = folder / f"upload{suffix}"
        total = 0
        try:
            with destination.open("xb") as handle:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > settings.max_upload_bytes:
                        raise HTTPException(status_code=413, detail="Upload is too large")
                    handle.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        job.source_path = destination
        return {"upload_id": job.id, "filename": destination.name, "bytes": total}

    @app.post("/api/jobs/analyze")
    async def analyze(payload: AnalyzeRequest):
        if bool(payload.url) == bool(payload.upload_id):
            raise HTTPException(status_code=400, detail="Provide exactly one source URL or upload ID")
        if payload.min_clip_seconds >= payload.max_clip_seconds:
            raise HTTPException(status_code=400, detail="Minimum clip length must be less than maximum")
        try:
            if payload.url:
                job = app.state.jobs.submit_url(
                    str(payload.url),
                    payload.mode,
                    payload.min_clip_seconds,
                    payload.max_clip_seconds,
                    payload.max_clips,
                )
            else:
                source_job = app.state.jobs.get(payload.upload_id)
                if not source_job.source_path:
                    raise ValueError("Uploaded source is missing")
                job = app.state.jobs.submit_uploaded(
                    source_job.id,
                    source_job.source_path,
                    payload.mode,
                    payload.min_clip_seconds,
                    payload.max_clip_seconds,
                    payload.max_clips,
                )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"job_id": job.id}

    @app.get("/api/jobs/{job_id}")
    async def job_status(job_id: str):
        try:
            return json.loads(app.state.jobs.public(job_id).model_dump_json())
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown job") from exc

    @app.get("/api/jobs/{job_id}/source")
    async def job_source(job_id: str):
        try:
            job = app.state.jobs.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown job") from exc
        if not job.source_path or not job.source_path.exists():
            raise HTTPException(status_code=404, detail="Source media is unavailable")
        return FileResponse(job.source_path)

    @app.post("/api/jobs/{job_id}/export")
    async def export(job_id: str, payload: ExportRequest):
        try:
            job = app.state.jobs.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown job") from exc
        if job.status != "complete" or not job.source_path:
            raise HTTPException(status_code=409, detail="Analysis is not complete")
        by_id = {candidate.id: candidate for candidate in job.candidates}
        requested = []
        for candidate_id in payload.candidate_ids:
            candidate = by_id.get(candidate_id)
            if not candidate:
                raise HTTPException(status_code=400, detail="Unknown clip candidate")
            if payload.captions and candidate.mode == AnalysisMode.QURAN:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Qur'an burn-in captions are disabled until verified acoustic timing "
                        "supports them. Review the reference-backed passage in the editor."
                    ),
                )
            requested.append(candidate)

        output_dir = safe_job_path(settings.jobs_dir, job.id) / "output"
        files = []
        media_info = probe_media(job.source_path, settings.max_video_seconds)
        source_duration = float(media_info["duration"])
        for index, candidate in enumerate(requested, start=1):
            boundary = payload.boundaries.get(candidate.id)
            start = boundary.start if boundary else candidate.start
            end = boundary.end if boundary else candidate.end
            if end <= start:
                raise HTTPException(status_code=400, detail="Clip end must be after clip start")
            if end - start > 180:
                raise HTTPException(status_code=400, detail="Adjusted clip exceeds three minutes")
            if end > source_duration + 0.05:
                raise HTTPException(status_code=400, detail="Adjusted clip exceeds source duration")
            filename = f"clip_{index:02d}_{candidate.id}.mp4"
            destination = output_dir / filename
            caption_cues = None
            if payload.captions:
                caption_cues = caption_cues_for_range(job.transcript_segments, start, end)
                if not caption_cues:
                    raise HTTPException(
                        status_code=409,
                        detail="No timed transcript segments are available for these captions",
                    )
            render_framing = payload.framing
            framing_points = None
            if payload.framing == "auto":
                render_framing = "center"
                if payload.aspect != "9:16":
                    framing_decision = FramingDecision(
                        applied="center",
                        confidence=0.0,
                        message="Auto framing applies only to vertical 9:16 exports.",
                    )
                else:
                    framing_decision = analyze_auto_framing(
                        job.source_path,
                        start,
                        end,
                        job.media_signals,
                    )
                    framing_points = framing_decision.points
            else:
                framing_decision = FramingDecision(
                    applied=payload.framing,
                    confidence=1.0,
                    message=f"Manual {payload.framing} framing applied.",
                )
            try:
                render_clip(
                    job.source_path,
                    destination,
                    start,
                    end,
                    payload.aspect,
                    render_framing,
                    framing_points=framing_points,
                    caption_cues=caption_cues,
                    caption_style=payload.caption_style,
                    caption_position=payload.caption_position,
                )
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Render failed: {exc}") from exc
            files.append(
                {
                    "name": filename,
                    "url": f"/api/jobs/{job.id}/output/{filename}",
                    "framing": framing_decision.public(payload.framing),
                }
            )
        return {"files": files}

    @app.get("/api/jobs/{job_id}/output/{filename}")
    async def output_file(job_id: str, filename: str):
        if not filename.startswith("clip_") or not filename.endswith(".mp4"):
            raise HTTPException(status_code=400, detail="Invalid output filename")
        folder = safe_job_path(settings.jobs_dir, job_id) / "output"
        target = (folder / filename).resolve()
        if folder.resolve() not in target.parents or not target.exists():
            raise HTTPException(status_code=404, detail="Output file not found")
        return FileResponse(target, media_type="video/mp4", filename=filename)

    return app
