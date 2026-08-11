from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from garden_jihan.analysis.quran import QuranReference
from garden_jihan.config import Settings
from garden_jihan.jobs import JobManager
from garden_jihan.media.exporting import ExportManager, ExportPlan, PreparedExportClip
from garden_jihan.media.framing import auto_framing_runtime_status
from garden_jihan.media.probe import probe_media
from garden_jihan.media.render import caption_cues_for_range
from garden_jihan.media.sources import inspect_source
from garden_jihan.models import (
    AnalysisMode,
    AnalyzeRequest,
    ExportRequest,
    ProjectReviewRequest,
    SourceInspectRequest,
    YouTubePublishRequest,
)
from garden_jihan.publish.credentials import ProtectedJsonStore, credential_protection_available
from garden_jihan.publish.manager import YouTubePublishManager
from garden_jihan.publish.youtube import (
    YouTubePublisher,
    YouTubePublishingError,
    YouTubeUploadMetadata,
)
from garden_jihan.security import LocalSecurityMiddleware, new_session_token, safe_job_path

ALLOWED_UPLOAD_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
MAX_QURAN_REFERENCE_BYTES = 8 * 1024 * 1024
MAX_OAUTH_CLIENT_BYTES = 64 * 1024


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
    app.state.exports = ExportManager(max_workers=settings.max_concurrent_jobs)
    app.state.youtube_publisher = YouTubePublisher(
        ProtectedJsonStore(settings.app_data / "credentials" / "youtube.bin")
    )
    app.state.youtube_uploads = YouTubePublishManager(app.state.youtube_publisher)

    app.add_middleware(LocalSecurityMiddleware, session_token=token, port=port)
    ui_dir = Path(__file__).parent / "ui"
    app.mount("/static", StaticFiles(directory=ui_dir), name="static")

    def youtube_callback_response(state: str, code: str, error: str) -> HTMLResponse:
        if error:
            safe_error = html.escape(error[:200])
            return HTMLResponse(
                f"<h1>YouTube was not connected</h1><p>{safe_error}</p>"
                "<p>You can close this tab and return to Garden of Jihan.</p>",
                status_code=400,
            )
        try:
            app.state.youtube_publisher.complete_authorization(state, code)
        except (OSError, RuntimeError, YouTubePublishingError) as exc:
            safe_error = html.escape(str(exc))
            return HTMLResponse(
                f"<h1>YouTube was not connected</h1><p>{safe_error}</p>"
                "<p>You can close this tab and return to Garden of Jihan.</p>",
                status_code=400,
            )
        return HTMLResponse(
            "<h1>YouTube connected</h1>"
            "<p>Garden of Jihan received upload-only permission. You can close this tab.</p>"
        )

    @app.get("/", response_class=HTMLResponse)
    def home(state: str = "", code: str = "", error: str = ""):
        if state or code or error:
            return youtube_callback_response(state, code, error)
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
            "credential_protection_available": credential_protection_available(),
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

    @app.get("/api/publish/status")
    async def publishing_status():
        return {
            "youtube": app.state.youtube_publisher.status(),
            "tiktok": {
                "available": False,
                "message": (
                    "Direct TikTok posting remains disabled until Garden of Jihan has an "
                    "audited Content Posting API client and a supported secure OAuth backend."
                ),
            },
        }

    @app.post("/api/publish/youtube/client")
    async def install_youtube_client(file: Annotated[UploadFile, File()]):
        raw = await file.read(MAX_OAUTH_CLIENT_BYTES + 1)
        if len(raw) > MAX_OAUTH_CLIENT_BYTES:
            raise HTTPException(status_code=413, detail="OAuth client file is unexpectedly large")
        try:
            app.state.youtube_publisher.install_client(raw)
        except (OSError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return app.state.youtube_publisher.status()

    @app.post("/api/publish/youtube/connect")
    async def connect_youtube():
        redirect_uri = f"http://127.0.0.1:{port}"
        try:
            authorization_url = app.state.youtube_publisher.start_authorization(redirect_uri)
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"authorization_url": authorization_url}

    @app.delete("/api/publish/youtube/connection")
    async def disconnect_youtube():
        try:
            app.state.youtube_publisher.disconnect()
        except (OSError, RuntimeError) as exc:
            raise HTTPException(status_code=500, detail="Local OAuth data could not be removed") from exc
        return {"connected": False}

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
        job.project.name = (Path(file.filename or "Local video").stem[:80] or "Local video")
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
        if payload.project_name and payload.project_name.strip():
            job.project.name = payload.project_name.strip()
        return {"job_id": job.id}

    @app.get("/api/jobs/{job_id}")
    async def job_status(job_id: str):
        try:
            return json.loads(app.state.jobs.public(job_id).model_dump_json())
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown job") from exc

    @app.get("/api/projects")
    async def projects():
        return {"projects": app.state.jobs.list_projects()}

    @app.put("/api/jobs/{job_id}/project")
    async def update_project(job_id: str, payload: ProjectReviewRequest):
        try:
            job = app.state.jobs.update_project(job_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown project") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=507, detail="Local project could not be saved") from exc
        return json.loads(app.state.jobs.public(job.id).model_dump_json())

    @app.delete("/api/projects/{job_id}")
    async def delete_project(job_id: str):
        try:
            app.state.jobs.delete_project(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown project") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Local project could not be removed") from exc
        return {"removed": True}

    @app.get("/api/jobs/{job_id}/source")
    async def job_source(job_id: str):
        try:
            job = app.state.jobs.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown job") from exc
        if not job.source_path or not job.source_path.exists():
            raise HTTPException(status_code=404, detail="Source media is unavailable")
        return FileResponse(job.source_path)

    @app.post("/api/jobs/{job_id}/export", status_code=202)
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
        prepared = []
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
            caption_cues = None
            if payload.captions:
                caption_cues = caption_cues_for_range(job.transcript_segments, start, end)
                if not caption_cues:
                    raise HTTPException(
                        status_code=409,
                        detail="No timed transcript segments are available for these captions",
                    )
            prepared.append(
                PreparedExportClip(
                    candidate_id=candidate.id,
                    filename=filename,
                    start=start,
                    end=end,
                    caption_cues=tuple(caption_cues or ()),
                )
            )
        plan = ExportPlan(
            project_id=job.id,
            source=job.source_path,
            output_dir=output_dir,
            media_signals=job.media_signals,
            aspect=payload.aspect,
            framing=payload.framing,
            caption_style=payload.caption_style,
            caption_position=payload.caption_position,
            clips=tuple(prepared),
        )
        try:
            return app.state.exports.submit(plan).public()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/exports/{export_id}")
    async def export_status(export_id: str):
        try:
            return app.state.exports.public(export_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown export") from exc

    @app.post("/api/jobs/{job_id}/publish/youtube")
    async def publish_youtube(job_id: str, payload: YouTubePublishRequest):
        try:
            job = app.state.jobs.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown project") from exc
        if job.status != "complete":
            raise HTTPException(status_code=409, detail="Analysis is not complete")
        if not app.state.youtube_publisher.status()["connected"]:
            raise HTTPException(status_code=409, detail="Connect YouTube before publishing")
        output_dir = (safe_job_path(settings.jobs_dir, job.id) / "output").resolve()
        target = (output_dir / payload.filename).resolve()
        if output_dir not in target.parents or not target.is_file():
            raise HTTPException(status_code=404, detail="Exported clip is unavailable")
        metadata = YouTubeUploadMetadata(
            title=payload.title,
            description=payload.description,
            privacy=payload.privacy,
            made_for_kids=payload.made_for_kids,
            contains_synthetic_media=payload.contains_synthetic_media,
        )
        try:
            upload = app.state.youtube_uploads.submit(target, metadata)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return upload.public()

    @app.get("/api/publish/youtube/uploads/{upload_id}")
    async def youtube_upload_status(upload_id: str):
        try:
            return app.state.youtube_uploads.get(upload_id).public()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown YouTube upload") from exc

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
