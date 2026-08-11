from __future__ import annotations

import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from garden_jihan.analysis.signals import MediaSignals
from garden_jihan.media.framing import FramingDecision, analyze_auto_framing
from garden_jihan.media.render import CaptionCue, TrackedCaptionCue, render_clip


@dataclass(frozen=True, slots=True)
class PreparedExportClip:
    candidate_id: str
    filename: str
    start: float
    end: float
    caption_cues: tuple[CaptionCue | TrackedCaptionCue, ...] = ()


@dataclass(frozen=True, slots=True)
class ExportPlan:
    project_id: str
    source: Path
    output_dir: Path
    media_signals: MediaSignals
    aspect: str
    framing: str
    caption_style: str
    caption_position: str
    clips: tuple[PreparedExportClip, ...]


@dataclass(slots=True)
class ExportJob:
    id: str
    project_id: str
    status: str = "queued"
    progress: int = 0
    message: str = "Queued for local rendering"
    error: str | None = None
    files: list[dict[str, object]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def public(self) -> dict[str, object]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "error": self.error,
            "files": list(self.files),
        }


class ExportManager:
    """Run validated local exports without blocking the loopback API."""

    def __init__(self, *, max_workers: int = 1, max_pending: int | None = None):
        workers = max(1, max_workers)
        self._max_pending = max_pending if max_pending is not None else max(2, workers * 2)
        self._jobs: dict[str, ExportJob] = {}
        self._active_projects: set[str] = set()
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="goj-export")

    def submit(self, plan: ExportPlan) -> ExportJob:
        if not plan.clips:
            raise ValueError("Choose at least one clip to export")
        if any(
            Path(clip.filename).name != clip.filename
            or not re.fullmatch(r"clip_[A-Za-z0-9_.-]+\.mp4", clip.filename)
            for clip in plan.clips
        ):
            raise ValueError("Export plan contains an invalid output filename")
        with self._lock:
            pending = sum(
                job.status in {"queued", "rendering"} for job in self._jobs.values()
            )
            if pending >= self._max_pending:
                raise ValueError("The local export queue is full; wait for a render to finish")
            if plan.project_id in self._active_projects:
                raise ValueError("An export is already running for this project")
            job = ExportJob(id=uuid.uuid4().hex, project_id=plan.project_id)
            self._jobs[job.id] = job
            self._active_projects.add(plan.project_id)
        self._pool.submit(self._run, job.id, plan)
        return job

    def _run(self, export_id: str, plan: ExportPlan) -> None:
        staging_dir = plan.output_dir / ".exports" / export_id
        staged: list[tuple[Path, Path, dict[str, object]]] = []
        attempted_paths: list[Path] = []
        job = self._get(export_id)
        with self._lock:
            job.status = "rendering"
            job.progress = 1
            job.message = f"Preparing {len(plan.clips)} local clip(s)"
        try:
            staging_dir.mkdir(parents=True, exist_ok=False)
            for index, clip in enumerate(plan.clips, start=1):
                with self._lock:
                    job.message = f"Rendering clip {index} of {len(plan.clips)} locally"
                    job.progress = max(1, round((index - 1) / len(plan.clips) * 95))

                render_framing = plan.framing
                framing_points = None
                if plan.framing == "auto":
                    render_framing = "center"
                    if plan.aspect != "9:16":
                        framing_decision = FramingDecision(
                            applied="center",
                            confidence=0.0,
                            message="Auto framing applies only to vertical 9:16 exports.",
                        )
                    else:
                        framing_decision = analyze_auto_framing(
                            plan.source,
                            clip.start,
                            clip.end,
                            plan.media_signals,
                        )
                        framing_points = framing_decision.points
                elif plan.aspect != "9:16" and plan.framing != "center":
                    render_framing = "center"
                    framing_decision = FramingDecision(
                        applied="center",
                        confidence=0.0,
                        message=(
                            "Left, right, and split framing apply only to vertical 9:16 "
                            "exports; center framing was used."
                        ),
                    )
                else:
                    framing_decision = FramingDecision(
                        applied=plan.framing,
                        confidence=1.0,
                        message=f"Manual {plan.framing} framing applied.",
                    )

                staged_path = staging_dir / clip.filename
                attempted_paths.append(staged_path)
                render_clip(
                    plan.source,
                    staged_path,
                    clip.start,
                    clip.end,
                    plan.aspect,
                    render_framing,
                    framing_points=framing_points,
                    caption_cues=list(clip.caption_cues) or None,
                    caption_style=plan.caption_style,
                    caption_position=plan.caption_position,
                )
                staged.append(
                    (
                        staged_path,
                        plan.output_dir / clip.filename,
                        {
                            "name": clip.filename,
                            "url": f"/api/jobs/{plan.project_id}/output/{clip.filename}",
                            "framing": framing_decision.public(plan.framing),
                        },
                    )
                )
                with self._lock:
                    job.progress = min(95, round(index / len(plan.clips) * 95))
                    job.message = f"Rendered clip {index} of {len(plan.clips)} locally"

            plan.output_dir.mkdir(parents=True, exist_ok=True)
            for staged_path, destination, _file in staged:
                staged_path.replace(destination)
            with self._lock:
                job.files = [file for _staged, _destination, file in staged]
                job.status = "complete"
                job.progress = 100
                job.message = f"Rendered {len(staged)} clip(s) locally"
        except Exception:
            with self._lock:
                job.status = "failed"
                job.error = (
                    "Local rendering failed. Check FFmpeg, the source media, and available disk space."
                )
                job.message = "Export failed safely; partial clips were not published"
        finally:
            for attempted_path in attempted_paths:
                attempted_path.unlink(missing_ok=True)
            try:
                staging_dir.rmdir()
                staging_dir.parent.rmdir()
            except OSError:
                pass
            with self._lock:
                self._active_projects.discard(plan.project_id)

    def _get(self, export_id: str) -> ExportJob:
        with self._lock:
            job = self._jobs.get(export_id)
        if not job:
            raise KeyError(export_id)
        return job

    def public(self, export_id: str) -> dict[str, object]:
        with self._lock:
            job = self._jobs.get(export_id)
            if not job:
                raise KeyError(export_id)
            return job.public()
