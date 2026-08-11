from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    bind_host: str = os.getenv("GOJ_BIND_HOST", "127.0.0.1")
    max_video_seconds: int = int(os.getenv("GOJ_MAX_VIDEO_SECONDS", "7200"))
    max_upload_bytes: int = int(os.getenv("GOJ_MAX_UPLOAD_BYTES", str(4 * 1024**3)))
    job_retention_hours: int = int(os.getenv("GOJ_JOB_RETENTION_HOURS", "24"))
    max_concurrent_jobs: int = int(os.getenv("GOJ_MAX_CONCURRENT_JOBS", "1"))
    app_data: Path = Path(os.getenv("LOCALAPPDATA", Path.home())) / "GardenOfJihan"

    @property
    def jobs_dir(self) -> Path:
        return self.app_data / "jobs"

    @property
    def quran_reference(self) -> Path:
        return self.app_data / "reference" / "quran_reference.json"
