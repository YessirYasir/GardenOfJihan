from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from garden_jihan.config import Settings
from garden_jihan.jobs import JobManager
from garden_jihan.media.render import render_clip
from garden_jihan.media.sources import inspect_source
from garden_jihan.models import AnalyzeRequest, ExportRequest, SourceInspectRequest
from garden_jihan.security import LocalSecurityMiddleware, new_session_token, safe_job_path


ALLOWED_UPLOAD_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


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
        return {"ok": True, "local": True, "version": "0.1.0"}

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
    async def upload(request: Request, file: UploadFile = File(...)):
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
                    str(payload.url), payload.mode, payload.min_clip_seconds, payload.max_clip_seconds, payload.max_clips
                )
            else:
                source_job = app.state.jobs.get(payload.upload_id)
                if not source_job.source_path:
                    raise ValueError("Uploaded source is missing")
                job = app.state.jobs.submit_uploaded(
                    source_job.id, source_job.source_path, payload.mode, payload.min_clip_seconds, payload.max_clip_seconds, payload.max_clips
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
            requested.append(candidate)

        output_dir = safe_job_path(settings.jobs_dir, job.id) / "output"
        files = []
        for index, candidate in enumerate(requested, start=1):
            filename = f"clip_{index:02d}_{candidate.id}.mp4"
            destination = output_dir / filename
            try:
                render_clip(job.source_path, destination, candidate.start, candidate.end, payload.aspect)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Render failed: {exc}") from exc
            files.append({"name": filename, "url": f"/api/jobs/{job.id}/output/{filename}"})
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
