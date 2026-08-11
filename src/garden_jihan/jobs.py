from __future__ import annotations

import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from garden_jihan.analysis.audience import youtube_replay_signal
from garden_jihan.analysis.quran import QuranReference
from garden_jihan.analysis.scoring import build_candidates
from garden_jihan.analysis.signals import build_media_signals
from garden_jihan.analysis.transcription import transcribe
from garden_jihan.config import Settings
from garden_jihan.media.downloader import download_remote
from garden_jihan.media.probe import probe_media
from garden_jihan.models import AnalysisMode, ClipCandidate, JobPublic
from garden_jihan.security import safe_job_path


@dataclass
class JobState:
    id: str
    status: str = "queued"
    progress: int = 0
    message: str = "Queued"
    error: str | None = None
    candidates: list[ClipCandidate] = field(default_factory=list)
    source_path: Path | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class JobManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(
            max_workers=settings.max_concurrent_jobs,
            thread_name_prefix="goj",
        )

    def create_upload_job(self) -> JobState:
        job = JobState(id=uuid.uuid4().hex)
        with self._lock:
            self._jobs[job.id] = job
        safe_job_path(self.settings.jobs_dir, job.id).mkdir(parents=True, exist_ok=False)
        return job

    def submit_url(
        self,
        url: str,
        mode: AnalysisMode,
        min_s: int,
        max_s: int,
        max_clips: int,
    ) -> JobState:
        job = self.create_upload_job()
        self._pool.submit(self._run_url, job.id, url, mode, min_s, max_s, max_clips)
        return job

    def submit_uploaded(
        self,
        job_id: str,
        path: Path,
        mode: AnalysisMode,
        min_s: int,
        max_s: int,
        max_clips: int,
    ) -> JobState:
        job = self.get(job_id)
        job.source_path = path
        self._pool.submit(self._analyze, job.id, path, mode, min_s, max_s, max_clips)
        return job

    def _set(self, job: JobState, status: str, progress: int, message: str):
        with self._lock:
            job.status, job.progress, job.message = status, progress, message

    def _run_url(
        self,
        job_id: str,
        url: str,
        mode: AnalysisMode,
        min_s: int,
        max_s: int,
        max_clips: int,
    ):
        job = self.get(job_id)
        try:
            self._set(job, "running", 8, "Safely acquiring source")
            folder = safe_job_path(self.settings.jobs_dir, job.id)
            path = download_remote(url, folder / "source")
            job.source_path = path
            replay = youtube_replay_signal(url)
            self._analyze(job.id, path, mode, min_s, max_s, max_clips, replay=replay)
        except Exception as exc:
            self._fail(job, exc)

    def _analyze(
        self,
        job_id: str,
        path: Path,
        mode: AnalysisMode,
        min_s: int,
        max_s: int,
        max_clips: int,
        replay=None,
    ):
        job = self.get(job_id)
        try:
            self._set(job, "running", 20, "Validating media")
            probe_media(path, self.settings.max_video_seconds)
            self._set(job, "running", 38, "Understanding speech")
            language_hint = (
                "so"
                if mode == AnalysisMode.SOMALI
                else "ar"
                if mode in {AnalysisMode.ARABIC, AnalysisMode.QURAN}
                else None
            )
            transcript = transcribe(path, language=language_hint)
            effective_mode = mode
            if mode == AnalysisMode.AUTO:
                effective_mode = (
                    AnalysisMode.ARABIC
                    if transcript.language == "ar"
                    else AnalysisMode.SOMALI
                    if transcript.language == "so"
                    else AnalysisMode.GENERAL
                )
            self._set(job, "running", 58, "Reading audio and visual momentum")
            signals = build_media_signals(path)
            if replay:
                signals.replay = replay
            self._set(job, "running", 76, "Finding strong moments")
            job.candidates = build_candidates(
                transcript.segments,
                effective_mode,
                min_s,
                max_s,
                max_clips,
                signals=signals,
            )
            if effective_mode == AnalysisMode.QURAN:
                self._set(job, "running", 90, "Matching the local Quran reference")
                self._attach_quran_matches(job.candidates)
            self._set(job, "complete", 100, f"Found {len(job.candidates)} clip candidates")
        except Exception as exc:
            self._fail(job, exc)

    def _attach_quran_matches(self, candidates: list[ClipCandidate]) -> None:
        reference = QuranReference(self.settings.quran_reference)
        for candidate in candidates:
            decision = reference.identify(candidate.transcript)
            public = decision.public(reference.source)
            candidate.quran_match = public
            if decision.status == "verified" and decision.match:
                best = decision.match
                ayah_label = f"{best.surah}:{best.ayah}"
                if best.end_ayah:
                    ayah_label += f"–{best.end_ayah}"
                candidate.title = f"Qur'an {ayah_label}"
                reasons = [f"Verified Quran reference match: {ayah_label}"]
                if best.starts_mid_ayah or best.ends_mid_ayah:
                    reasons.append("Review timing: this candidate may cut through an ayah")
                candidate.reasons = [*reasons, *candidate.reasons][:6]
            elif decision.status in {"possible", "uncertain"}:
                candidate.title = "Qur'an passage — review required"
                candidate.reasons = [decision.message, *candidate.reasons][:6]

    def _fail(self, job: JobState, exc: Exception):
        with self._lock:
            job.status = "failed"
            job.error = str(exc)
            job.message = "Analysis failed safely"

    def get(self, job_id: str) -> JobState:
        with self._lock:
            job = self._jobs.get(job_id)
        if not job:
            raise KeyError(job_id)
        return job

    def public(self, job_id: str) -> JobPublic:
        job = self.get(job_id)
        return JobPublic(
            id=job.id,
            status=job.status,
            progress=job.progress,
            message=job.message,
            error=job.error,
            candidates=job.candidates,
        )

    def cleanup_old(self):
        cutoff = datetime.now(UTC) - timedelta(hours=self.settings.job_retention_hours)
        for path in self.settings.jobs_dir.iterdir():
            if not path.is_dir():
                continue
            modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            if modified < cutoff:
                shutil.rmtree(path, ignore_errors=True)
