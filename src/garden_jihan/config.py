from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def default_app_data() -> Path:
    configured = os.getenv("GOJ_APP_DATA", "").strip()
    if configured:
        return Path(configured).expanduser()
    if sys.platform == "win32":
        return Path(os.getenv("LOCALAPPDATA", Path.home())) / "GardenOfJihan"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "GardenOfJihan"
    xdg_data = os.getenv("XDG_DATA_HOME", "").strip()
    root = Path(xdg_data).expanduser() if xdg_data else Path.home() / ".local" / "share"
    return root / "GardenOfJihan"


@dataclass(frozen=True, slots=True)
class Settings:
    bind_host: str = os.getenv("GOJ_BIND_HOST", "127.0.0.1")
    max_video_seconds: int = int(os.getenv("GOJ_MAX_VIDEO_SECONDS", "7200"))
    max_upload_bytes: int = int(os.getenv("GOJ_MAX_UPLOAD_BYTES", str(4 * 1024**3)))
    job_retention_hours: int = int(os.getenv("GOJ_JOB_RETENTION_HOURS", "24"))
    max_concurrent_jobs: int = int(os.getenv("GOJ_MAX_CONCURRENT_JOBS", "1"))
    app_data: Path = default_app_data()

    @property
    def jobs_dir(self) -> Path:
        return self.app_data / "jobs"

    @property
    def quran_reference(self) -> Path:
        return self.app_data / "reference" / "quran_reference.json"

    @property
    def bundled_quran_reference(self) -> Path | None:
        value = os.getenv("GOJ_QURAN_REFERENCE_PATH", "").strip()
        return Path(value).expanduser().resolve() if value else None

    @property
    def active_quran_reference(self) -> Path:
        # Packaged reference content is verified every time it is opened. Never
        # silently fall back to another text if that packaged copy is damaged.
        return self.bundled_quran_reference or self.quran_reference

    @property
    def onboarding_complete(self) -> Path:
        return self.app_data / "onboarding-complete"
