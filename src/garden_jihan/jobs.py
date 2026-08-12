from __future__ import annotations

import json
import math
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from garden_jihan.analysis.audience import youtube_replay_signal
from garden_jihan.analysis.quran import QuranReference, normalize_arabic
from garden_jihan.analysis.sampling import plan_listening_windows
from garden_jihan.analysis.scoring import build_candidates
from garden_jihan.analysis.semantics import LocalSemanticRanker
from garden_jihan.analysis.signals import MediaSignals, TimedValue, build_media_signals
from garden_jihan.analysis.transcription import TranscriptSegment, TranscriptWord, transcribe
from garden_jihan.config import Settings
from garden_jihan.media.downloader import download_remote
from garden_jihan.media.probe import probe_media
from garden_jihan.models import AnalysisMode, ClipCandidate, JobPublic, ProjectReview
from garden_jihan.security import safe_job_path


@dataclass
class JobState:
    id: str
    status: str = "queued"
    progress: int = 0
    eta_seconds: int | None = None
    message: str = "Queued"
    error: str | None = None
    ranking_method: str = "base"
    ranking_message: str = "Base ranking"
    candidates: list[ClipCandidate] = field(default_factory=list)
    transcript_segments: list[TranscriptSegment] = field(default_factory=list)
    media_signals: MediaSignals | None = None
    source_path: Path | None = None
    project: ProjectReview = field(default_factory=ProjectReview)
    analysis_started_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class JobManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()
        self.cleanup_old()
        self._load_projects()
        self._semantic_ranker = LocalSemanticRanker(settings.app_data / "models" / "semantic")
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
        job.analysis_started_at = datetime.now(UTC)
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
        job.analysis_started_at = datetime.now(UTC)
        self._set(job, "queued", 0, "Queued for local analysis")
        self._pool.submit(self._analyze, job.id, path, mode, min_s, max_s, max_clips)
        return job

    def mark_upload_ready(self, job: JobState, path: Path, project_name: str) -> None:
        with self._lock:
            job.source_path = path
            job.status = "uploaded"
            job.progress = 0
            job.message = "Local upload ready for analysis"
            job.project.name = project_name
            job.updated_at = datetime.now(UTC)

    def mark_upload_failed(self, job: JobState) -> None:
        self._set(job, "failed", 0, "Local upload failed safely")

    def _set(
        self,
        job: JobState,
        status: str,
        progress: int,
        message: str,
        *,
        eta_seconds: int | None = None,
    ):
        with self._lock:
            job.status, job.progress, job.message = status, progress, message
            job.eta_seconds = eta_seconds
            job.updated_at = datetime.now(UTC)

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
            self._set(job, "running", 4, "Safely acquiring source", eta_seconds=60)
            folder = safe_job_path(self.settings.jobs_dir, job.id)

            def acquiring_progress(fraction: float, eta: int | None) -> None:
                mapped = 4 + round(max(0.0, min(1.0, fraction)) * 7)
                total_eta = (eta + 44) if eta is not None else None
                self._set(
                    job,
                    "running",
                    mapped,
                    "Bringing the video into your garden",
                    eta_seconds=total_eta,
                )

            path = download_remote(url, folder / "source", progress=acquiring_progress)
            job.source_path = path
            if job.project.name == "Untitled project":
                job.project.name = path.stem[:80] or "Imported video"
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
            self._set(job, "running", 12, "Validating media", eta_seconds=48)
            media = probe_media(path, self.settings.max_video_seconds)
            self._set(job, "running", 16, "Surveying the whole video", eta_seconds=45)
            signals = build_media_signals(path)
            if replay:
                signals.replay = replay
            with self._lock:
                job.media_signals = signals
            listening_windows = plan_listening_windows(
                float(media["duration"]),
                signals.audio_energy,
                min_clip_seconds=min_s,
            )
            self._set(job, "running", 20, "Understanding speech")
            language_hint = (
                "so"
                if mode == AnalysisMode.SOMALI
                else "ar"
                if mode in {AnalysisMode.ARABIC, AnalysisMode.QURAN}
                else None
            )
            listening_started = time.monotonic()
            last_listening_progress = 19

            def listening_progress(fraction: float, _duration: float | None) -> None:
                nonlocal last_listening_progress
                fraction = max(0.0, min(1.0, fraction))
                mapped = 20 + round(fraction * 27)
                if mapped <= last_listening_progress:
                    return
                last_listening_progress = mapped
                elapsed = time.monotonic() - listening_started
                eta_seconds = None
                if fraction >= 0.02 and elapsed >= 2:
                    eta_seconds = 12 + min(
                        6 * 60 * 60,
                        round(elapsed * (1 - fraction) / fraction),
                    )
                self._set(
                    job,
                    "running",
                    mapped,
                    "Understanding speech",
                    eta_seconds=eta_seconds,
                )

            transcript = transcribe(
                path,
                language=language_hint,
                progress=listening_progress,
                clips=listening_windows,
            )
            with self._lock:
                job.transcript_segments = list(transcript.segments)
            effective_mode = mode
            if mode == AnalysisMode.AUTO:
                effective_mode = (
                    AnalysisMode.ARABIC
                    if transcript.language == "ar"
                    else AnalysisMode.SOMALI
                    if transcript.language == "so"
                    else AnalysisMode.GENERAL
                )
            self._set(
                job,
                "running",
                58,
                "Reading audio and visual momentum",
                eta_seconds=10,
            )
            ranking_message = (
                "Ranking complete recitation segments"
                if effective_mode == AnalysisMode.QURAN
                else "Loading the local multilingual meaning model"
            )
            self._set(job, "running", 76, ranking_message, eta_seconds=5)
            job.candidates = build_candidates(
                transcript.segments,
                effective_mode,
                min_s if listening_windows is None else min(min_s, 20),
                max_s,
                max_clips,
                signals=signals,
                semantic_ranker=(
                    None if effective_mode == AnalysisMode.QURAN else self._semantic_ranker
                ),
            )
            if listening_windows is not None and effective_mode != AnalysisMode.QURAN:
                source_duration = float(media["duration"])
                for candidate in job.candidates:
                    if candidate.end - candidate.start >= min_s:
                        continue
                    center = (candidate.start + candidate.end) / 2
                    candidate.start = max(
                        0.0,
                        min(source_duration - min_s, center - min_s / 2),
                    )
                    candidate.end = min(source_duration, candidate.start + min_s)
            if effective_mode == AnalysisMode.QURAN:
                job.ranking_method = "quran_safe"
                job.ranking_message = "Qur'an pause-and-completeness ranking; no semantic model"
            elif any(candidate.semantic_model for candidate in job.candidates):
                job.ranking_method = "local_multilingual_embeddings"
                job.ranking_message = "Local multilingual meaning model active"
            else:
                job.ranking_method = "base_fallback"
                job.ranking_message = "Base ranking used; local meaning model unavailable"
            if effective_mode == AnalysisMode.QURAN:
                self._set(
                    job,
                    "running",
                    90,
                    "Matching the local Quran reference",
                    eta_seconds=3,
                )
                self._attach_quran_matches(job.candidates, job.transcript_segments)
            strong_ids = [candidate.id for candidate in job.candidates if candidate.score >= 85]
            job.project.selected_ids = strong_ids or [
                candidate.id for candidate in job.candidates[: min(3, len(job.candidates))]
            ]
            self._set(job, "complete", 100, f"Found {len(job.candidates)} clip candidates")
            job.updated_at = datetime.now(UTC)
            try:
                self._persist_project(job)
            except OSError:
                job.message += "; local project could not be saved"
        except Exception as exc:
            self._fail(job, exc)

    @staticmethod
    def _attach_quran_acoustic_timing(
        candidate: ClipCandidate,
        public: dict,
        transcript_segments: list[TranscriptSegment],
    ) -> None:
        public["acoustic_timing_status"] = "unavailable"
        public["acoustic_timing_message"] = (
            "Acoustic word timestamps are unavailable; Qur'an word captions remain disabled."
        )
        if public.get("status") != "verified":
            return
        alignment = public.get("word_alignment")
        if not isinstance(alignment, list) or not alignment:
            return
        locating = [word for word in alignment if word.get("matched") and not word.get("optional")]
        if (
            len(locating) < 3
            or len(locating) != int(public.get("total_words") or 0)
            or int(public.get("matched_words") or 0) != int(public.get("total_words") or 0)
        ):
            public["acoustic_timing_status"] = "uncertain"
            public["acoustic_timing_message"] = (
                "The reference word alignment is incomplete; Qur'an word captions remain disabled."
            )
            return

        timed_words = [
            word
            for segment in transcript_segments
            if segment.end > candidate.start and segment.start < candidate.end
            for word in segment.words
            if word.end > candidate.start and word.start < candidate.end
        ]
        if not timed_words:
            return
        query_tokens = [
            normalized
            for raw in candidate.transcript.split()
            if (normalized := normalize_arabic(raw))
        ]
        timed_tokens = [normalize_arabic(word.text) for word in timed_words]
        if not query_tokens or timed_tokens != query_tokens:
            public["acoustic_timing_status"] = "uncertain"
            public["acoustic_timing_message"] = (
                "Acoustic words did not map exactly to the matched transcript; Qur'an word "
                "captions remain disabled."
            )
            return

        resolved: list[tuple[dict, TranscriptWord]] = []
        for word in locating:
            query_index = word.get("query_index")
            if not isinstance(query_index, int) or not 0 <= query_index < len(timed_words):
                return
            acoustic = timed_words[query_index]
            if acoustic.probability < 0.55:
                public["acoustic_timing_status"] = "uncertain"
                public["acoustic_timing_message"] = (
                    "At least one acoustic word confidence is below the safety threshold; "
                    "Qur'an word captions remain disabled."
                )
                return
            resolved.append((word, acoustic))
        if any(
            current.start < previous.start or current.end <= current.start
            for (_word, previous), (_next_word, current) in zip(
                resolved,
                resolved[1:],
                strict=False,
            )
        ):
            public["acoustic_timing_status"] = "uncertain"
            public["acoustic_timing_message"] = (
                "Acoustic word timestamps were not monotonic; Qur'an word captions remain disabled."
            )
            return
        for word, acoustic in resolved:
            word["acoustic_start"] = round(acoustic.start, 3)
            word["acoustic_end"] = round(acoustic.end, 3)
            word["acoustic_probability"] = round(acoustic.probability, 3)
        minimum_probability = min(acoustic.probability for _word, acoustic in resolved)
        public["acoustic_timing_status"] = "supported"
        public["acoustic_timing_confidence"] = round(minimum_probability * 100, 1)
        public["acoustic_timing_message"] = (
            "Reference words map one-to-one to confidence-gated local acoustic timestamps. "
            "Timing is model-estimated, not human-verified; Qira'at is not assessed."
        )

    def _attach_quran_matches(
        self,
        candidates: list[ClipCandidate],
        transcript_segments: list[TranscriptSegment] | None = None,
        reference: QuranReference | None = None,
    ) -> None:
        reference = reference or QuranReference(self.settings.active_quran_reference)
        for candidate in candidates:
            decision = reference.identify(candidate.transcript)
            public = decision.public(reference.source)
            self._attach_quran_acoustic_timing(
                candidate,
                public,
                transcript_segments or [],
            )
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
                existing = [
                    reason
                    for reason in candidate.reasons
                    if not reason.startswith("Verified Quran reference match:")
                    and reason != "Review timing: this candidate may cut through an ayah"
                ]
                candidate.reasons = [*reasons, *existing][:6]
            elif decision.status in {"possible", "uncertain"}:
                candidate.title = "Qur'an passage — review required"
                candidate.reasons = [
                    decision.message,
                    *(
                        reason
                        for reason in candidate.reasons
                        if reason != decision.message
                        and not reason.startswith("Verified Quran reference match:")
                        and reason != "Review timing: this candidate may cut through an ayah"
                    ),
                ][:6]
            else:
                candidate.title = "Qur'an passage — reference required"
                candidate.reasons = [
                    decision.message,
                    *(
                        reason
                        for reason in candidate.reasons
                        if reason != decision.message
                        and not reason.startswith("Verified Quran reference match:")
                        and reason != "Review timing: this candidate may cut through an ayah"
                    ),
                ][:6]

    def _fail(self, job: JobState, exc: Exception):
        with self._lock:
            job.status = "failed"
            job.eta_seconds = None
            job.error = str(exc)
            job.message = "Analysis failed safely"
            job.updated_at = datetime.now(UTC)

    def get(self, job_id: str) -> JobState:
        with self._lock:
            job = self._jobs.get(job_id)
        if not job:
            raise KeyError(job_id)
        return job

    def has_active_work(self) -> bool:
        with self._lock:
            return any(job.status in {"queued", "running"} for job in self._jobs.values())

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True, cancel_futures=True)

    def public(self, job_id: str) -> JobPublic:
        job = self.get(job_id)
        clock_start = job.analysis_started_at or job.created_at
        clock_end = job.updated_at if job.status in {"complete", "failed"} else datetime.now(UTC)
        return JobPublic(
            id=job.id,
            status=job.status,
            progress=job.progress,
            eta_seconds=job.eta_seconds,
            elapsed_seconds=max(0, round((clock_end - clock_start).total_seconds())),
            message=job.message,
            error=job.error,
            ranking_method=job.ranking_method,
            ranking_message=job.ranking_message,
            candidates=job.candidates,
            project=job.project,
            source_available=bool(job.source_path and job.source_path.exists()),
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    @staticmethod
    def _timed_values(values: list) -> list[dict[str, float]]:
        return [
            {"start": float(item.start), "end": float(item.end), "value": float(item.value)}
            for item in values
        ]

    def _persist_project(self, job: JobState) -> None:
        if job.status != "complete":
            return
        folder = safe_job_path(self.settings.jobs_dir, job.id)
        source_relative = None
        if job.source_path:
            try:
                source_relative = job.source_path.resolve().relative_to(folder.resolve()).as_posix()
            except ValueError:
                source_relative = None
        signals = job.media_signals or MediaSignals()
        manifest = {
            "schema": 1,
            "id": job.id,
            "status": job.status,
            "message": job.message,
            "ranking_method": job.ranking_method,
            "ranking_message": job.ranking_message,
            "source": source_relative,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
            "project": job.project.model_dump(mode="json"),
            "candidates": [candidate.model_dump(mode="json") for candidate in job.candidates],
            "transcript_segments": [
                {
                    "start": item.start,
                    "end": item.end,
                    "text": item.text,
                    "words": [
                        {
                            "start": word.start,
                            "end": word.end,
                            "text": word.text,
                            "probability": word.probability,
                        }
                        for word in item.words
                    ],
                }
                for item in job.transcript_segments
            ],
            "media_signals": {
                "audio_energy": self._timed_values(signals.audio_energy),
                "scene_times": [float(value) for value in signals.scene_times],
                "replay": self._timed_values(signals.replay),
            },
        }
        temporary = folder / "project.json.tmp"
        destination = folder / "project.json"
        temporary.write_text(
            json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(destination)

    @staticmethod
    def _parse_time(raw: object) -> datetime:
        try:
            value = datetime.fromisoformat(str(raw))
        except (TypeError, ValueError):
            return datetime.now(UTC)
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @staticmethod
    def _load_timed_values(raw: object) -> list:
        if not isinstance(raw, list):
            return []
        values = []
        for item in raw[:20_000]:
            if not isinstance(item, dict):
                continue
            try:
                values.append(
                    TimedValue(
                        start=float(item["start"]),
                        end=float(item["end"]),
                        value=float(item["value"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return values

    def _load_projects(self) -> None:
        restored_quran_reference = None
        for manifest_path in self.settings.jobs_dir.glob("*/project.json"):
            try:
                if manifest_path.stat().st_size > 64 * 1024 * 1024:
                    continue
                folder = safe_job_path(self.settings.jobs_dir, manifest_path.parent.name)
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
                if raw.get("schema") != 1 or raw.get("id") != folder.name:
                    continue
                source_path = None
                source_relative = raw.get("source")
                if isinstance(source_relative, str) and source_relative:
                    candidate_source = (folder / source_relative).resolve()
                    if folder.resolve() in candidate_source.parents and candidate_source.is_file():
                        source_path = candidate_source
                transcript = []
                for item in raw.get("transcript_segments", [])[:100_000]:
                    segment_start = float(item["start"])
                    segment_end = float(item["end"])
                    words = []
                    for word in item.get("words", [])[:2_000]:
                        word_start = float(word["start"])
                        word_end = float(word["end"])
                        probability = float(word["probability"])
                        text = str(word["text"]).strip()
                        if (
                            text
                            and all(
                                math.isfinite(value)
                                for value in (word_start, word_end, probability)
                            )
                            and max(0.0, segment_start - 0.25) <= word_start < word_end
                            and word_end <= segment_end + 0.25
                            and 0.0 <= probability <= 1.0
                        ):
                            words.append(
                                TranscriptWord(word_start, word_end, text, probability)
                            )
                    transcript.append(
                        TranscriptSegment(
                            start=segment_start,
                            end=segment_end,
                            text=str(item["text"]),
                            words=words,
                        )
                    )
                signal_data = raw.get("media_signals", {})
                signals = MediaSignals(
                    audio_energy=self._load_timed_values(signal_data.get("audio_energy")),
                    scene_times=[
                        float(value) for value in signal_data.get("scene_times", [])[:20_000]
                    ],
                    replay=self._load_timed_values(signal_data.get("replay")),
                )
                job = JobState(
                    id=folder.name,
                    status="complete",
                    progress=100,
                    message=str(raw.get("message") or "Project restored"),
                    ranking_method=str(raw.get("ranking_method") or "base_fallback"),
                    ranking_message=str(raw.get("ranking_message") or "Restored local project"),
                    candidates=[
                        ClipCandidate.model_validate(item)
                        for item in raw.get("candidates", [])[:30]
                    ],
                    transcript_segments=transcript,
                    media_signals=signals,
                    source_path=source_path,
                    project=ProjectReview.model_validate(raw.get("project", {})),
                    created_at=self._parse_time(raw.get("created_at")),
                    updated_at=self._parse_time(raw.get("updated_at")),
                )
                if any(candidate.mode == AnalysisMode.QURAN for candidate in job.candidates):
                    if restored_quran_reference is None:
                        restored_quran_reference = QuranReference(
                            self.settings.active_quran_reference
                        )
                    self._attach_quran_matches(
                        job.candidates,
                        job.transcript_segments,
                        restored_quran_reference,
                    )
            except (AttributeError, OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
                continue
            self._jobs[job.id] = job

    def list_projects(self) -> list[dict]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda job: job.updated_at, reverse=True)
        return [
            {
                "id": job.id,
                "name": job.project.name,
                "updated_at": job.updated_at.isoformat(),
                "candidate_count": len(job.candidates),
                "selected_count": len(job.project.selected_ids),
                "source_available": bool(job.source_path and job.source_path.exists()),
            }
            for job in jobs
            if job.status == "complete"
        ]

    def list_top_moments(self, limit: int = 12) -> list[dict]:
        """Return the strongest saved moments across completed projects.

        The dashboard shelf is reconstructed from project manifests, so it grows
        naturally as work is completed and never relies on placeholder content.
        """
        bounded_limit = max(1, min(limit, 30))
        with self._lock:
            moments: list[dict] = []
            for job in self._jobs.values():
                if job.status != "complete":
                    continue
                selected_ids = set(job.project.selected_ids)
                source_available = bool(job.source_path and job.source_path.exists())
                for candidate in job.candidates:
                    boundary = job.project.boundaries.get(candidate.id)
                    moments.append(
                        {
                            "id": candidate.id,
                            "project_id": job.id,
                            "project_name": job.project.name,
                            "updated_at": job.updated_at.isoformat(),
                            "source_available": source_available,
                            "selected": candidate.id in selected_ids,
                            "title": candidate.title,
                            "start": boundary.start if boundary else candidate.start,
                            "end": boundary.end if boundary else candidate.end,
                            "score": candidate.score,
                            "mode": candidate.mode.value,
                        }
                    )
        moments.sort(key=lambda moment: (moment["score"], moment["updated_at"]), reverse=True)
        return moments[:bounded_limit]

    def update_project(self, job_id: str, project: ProjectReview) -> JobState:
        job = self.get(job_id)
        if job.status != "complete":
            raise ValueError("Analysis is not complete")
        candidate_ids = {candidate.id for candidate in job.candidates}
        if unknown := set(project.selected_ids) - candidate_ids:
            raise ValueError(f"Unknown selected clip: {sorted(unknown)[0]}")
        if unknown := set(project.boundaries) - candidate_ids:
            raise ValueError(f"Unknown adjusted clip: {sorted(unknown)[0]}")
        with self._lock:
            previous_project = job.project
            previous_updated_at = job.updated_at
            job.project = project
            job.updated_at = datetime.now(UTC)
        try:
            self._persist_project(job)
        except (OSError, ValueError):
            with self._lock:
                job.project = previous_project
                job.updated_at = previous_updated_at
            raise
        return job

    def delete_project(self, job_id: str) -> None:
        job = self.get(job_id)
        if job.status == "running":
            raise ValueError("A running project cannot be removed")
        folder = safe_job_path(self.settings.jobs_dir, job_id)
        shutil.rmtree(folder)
        with self._lock:
            self._jobs.pop(job_id, None)

    def cleanup_old(self):
        cutoff = datetime.now(UTC) - timedelta(hours=self.settings.job_retention_hours)
        for path in self.settings.jobs_dir.iterdir():
            if not path.is_dir():
                continue
            if (path / "project.json").is_file():
                continue
            modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            if modified < cutoff:
                target = safe_job_path(self.settings.jobs_dir, path.name)
                shutil.rmtree(target, ignore_errors=True)
