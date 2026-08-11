from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from garden_jihan.publish.youtube import (
    YouTubePublisher,
    YouTubePublishingError,
    YouTubeUploadMetadata,
)


@dataclass(slots=True)
class PublishJob:
    id: str
    filename: str
    status: str = "queued"
    progress: int = 0
    message: str = "Queued for official YouTube upload"
    error: str | None = None
    video_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def public(self) -> dict[str, str | int | None]:
        return {
            "id": self.id,
            "filename": self.filename,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "error": self.error,
            "video_id": self.video_id,
            "url": f"https://www.youtube.com/watch?v={self.video_id}" if self.video_id else None,
        }


class YouTubePublishManager:
    def __init__(self, publisher: YouTubePublisher):
        self.publisher = publisher
        self._jobs: dict[str, PublishJob] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="goj-youtube")

    def submit(self, path: Path, metadata: YouTubeUploadMetadata) -> PublishJob:
        metadata.validate()
        if path.suffix.lower() != ".mp4" or not path.is_file():
            raise ValueError("Only an existing exported MP4 can be published")
        job = PublishJob(id=uuid.uuid4().hex, filename=path.name)
        with self._lock:
            self._jobs[job.id] = job
        self._pool.submit(self._run, job.id, path, metadata)
        return job

    def _run(self, job_id: str, path: Path, metadata: YouTubeUploadMetadata) -> None:
        job = self.get(job_id)
        with self._lock:
            job.status = "uploading"
            job.progress = 1
            job.message = "Uploading through the official YouTube API"

        def progress(sent: int, total: int) -> None:
            value = min(98, max(1, round(sent / max(total, 1) * 98)))
            with self._lock:
                job.progress = value
                job.message = f"Official YouTube upload {value}%"

        try:
            video_id = self.publisher.upload(path, metadata, progress)
        except (ValueError, YouTubePublishingError) as exc:
            with self._lock:
                job.status = "failed"
                job.error = str(exc)
                job.message = "YouTube upload failed safely"
            return
        except Exception:
            with self._lock:
                job.status = "failed"
                job.error = "Unexpected local publishing error"
                job.message = "YouTube upload failed safely"
            return
        with self._lock:
            job.status = "complete"
            job.progress = 100
            job.message = "YouTube accepted the upload"
            job.video_id = video_id

    def get(self, job_id: str) -> PublishJob:
        with self._lock:
            job = self._jobs.get(job_id)
        if not job:
            raise KeyError(job_id)
        return job
