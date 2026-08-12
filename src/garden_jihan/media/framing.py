from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from garden_jihan.analysis.signals import MediaSignals


@dataclass(frozen=True, slots=True)
class FaceObservation:
    """One locally measured face position and its visual speech activity."""

    time: float
    track_id: int
    center_x: float
    area: float
    mouth_motion: float
    audio_energy: float | None


@dataclass(frozen=True, slots=True)
class FramingPoint:
    """A clip-relative horizontal center used by the FFmpeg crop expression."""

    time: float
    center_x: float


@dataclass(frozen=True, slots=True)
class FramingDecision:
    applied: str
    confidence: float
    message: str
    points: tuple[FramingPoint, ...] = ()

    def public(self, requested: str = "auto") -> dict[str, str | float]:
        return {
            "requested": requested,
            "applied": self.applied,
            "confidence": round(self.confidence, 3),
            "message": self.message,
        }


def _center_fallback(message: str) -> FramingDecision:
    return FramingDecision(applied="center", confidence=0.0, message=message)


@lru_cache(maxsize=1)
def auto_framing_runtime_status() -> tuple[bool, str]:
    """Check that both OpenCV and its packaged detector data are loadable."""
    try:
        import cv2  # type: ignore[import-not-found]

        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        detector = cv2.CascadeClassifier(str(cascade_path))
        if detector.empty():
            return False, "Local face detector data is unavailable"
    except (AttributeError, ImportError, OSError):
        return False, "Local OpenCV face tracking is unavailable"
    return True, "Local face tracking is available"


def _smooth_points(points: list[FramingPoint]) -> tuple[FramingPoint, ...]:
    """Limit crop jumps and reduce the FFmpeg expression to one point per second."""
    if not points:
        return ()
    buckets: dict[int, list[float]] = defaultdict(list)
    for point in points:
        buckets[max(0, round(point.time))].append(min(1.0, max(0.0, point.center_x)))
    reduced = [
        FramingPoint(float(second), sum(values) / len(values))
        for second, values in sorted(buckets.items())
    ]
    smoothed = [reduced[0]]
    for point in reduced[1:]:
        previous = smoothed[-1].center_x
        # A bounded exponential step avoids abrupt pans between nearby samples.
        target = previous * 0.58 + point.center_x * 0.42
        target = min(previous + 0.14, max(previous - 0.14, target))
        smoothed.append(FramingPoint(point.time, target))
    return tuple(smoothed)


def choose_auto_framing(
    observations: list[FaceObservation],
    *,
    clip_start: float,
    expected_samples: int,
) -> FramingDecision:
    """Choose a face only from sufficiently strong local visual evidence.

    A single stable face is tracked as a subject, without claiming that the person is
    speaking. With multiple faces, a frame is selected only when mouth motion is present,
    source audio is active, and the best face is clearly separated from the alternatives.
    """
    if expected_samples < 1 or not observations:
        return _center_fallback("Auto framing found no usable face evidence; center crop used.")

    by_time: dict[float, list[FaceObservation]] = defaultdict(list)
    by_track: dict[int, list[FaceObservation]] = defaultdict(list)
    for observation in observations:
        if not all(
            math.isfinite(value)
            for value in (observation.time, observation.center_x, observation.area)
        ):
            continue
        by_time[observation.time].append(observation)
        by_track[observation.track_id].append(observation)
    coverage = len(by_time) / expected_samples
    if coverage < 0.45 or not by_track:
        return _center_fallback(
            "Auto framing could not track a face consistently; center crop used."
        )

    dominant_id, dominant = max(by_track.items(), key=lambda item: len(item[1]))
    dominant_coverage = len(dominant) / expected_samples
    multi_face_frames = sum(len(frame) > 1 for frame in by_time.values())
    if dominant_coverage >= 0.58 and multi_face_frames / len(by_time) < 0.28:
        points = _smooth_points(
            [
                FramingPoint(item.time - clip_start, item.center_x)
                for item in dominant
                if item.track_id == dominant_id
            ]
        )
        confidence = min(0.95, 0.48 + dominant_coverage * 0.45)
        return FramingDecision(
            applied="auto-subject",
            confidence=confidence,
            message=(
                "Tracked one stable face locally. This is subject tracking, not speaker "
                "identity recognition."
            ),
            points=points,
        )

    selected: list[FramingPoint] = []
    eligible_frames = 0
    confident_frames = 0
    for timestamp, faces in sorted(by_time.items()):
        if len(faces) < 2:
            continue
        with_audio = [
            face
            for face in faces
            if face.audio_energy is not None and face.audio_energy >= 0.25
        ]
        if len(with_audio) < 2:
            continue
        eligible_frames += 1
        ranked = sorted(
            with_audio,
            key=lambda face: face.mouth_motion * (0.45 + 0.55 * face.audio_energy),
            reverse=True,
        )
        best, runner_up = ranked[:2]
        best_score = best.mouth_motion * (0.45 + 0.55 * best.audio_energy)
        runner_score = runner_up.mouth_motion * (0.45 + 0.55 * runner_up.audio_energy)
        separated = best_score >= max(0.012, runner_score * 1.4) and (
            best_score - runner_score >= 0.003
        )
        if separated:
            confident_frames += 1
            center = best.center_x
        else:
            # Ambiguous frames deliberately return toward neutral rather than guessing.
            center = 0.5
        selected.append(FramingPoint(timestamp - clip_start, center))

    confident_ratio = confident_frames / eligible_frames if eligible_frames else 0.0
    evidence_ratio = confident_frames / expected_samples
    if eligible_frames < 3 or confident_frames < 3 or confident_ratio < 0.4 or evidence_ratio < 0.12:
        return _center_fallback(
            "Multiple faces were ambiguous or lacked audio-visual speech evidence; "
            "center crop used."
        )

    confidence = min(0.92, 0.4 + confident_ratio * 0.35 + coverage * 0.17)
    return FramingDecision(
        applied="auto-speaking-face",
        confidence=confidence,
        message=(
            "Followed locally measured audio-visual speech activity. This does not identify "
            "the speaker and uncertain frames return toward center."
        ),
        points=_smooth_points(selected),
    )


def analyze_auto_framing(
    path: Path,
    start: float,
    end: float,
    signals: MediaSignals | None,
    *,
    sample_interval: float = 0.5,
) -> FramingDecision:
    """Measure face position and mouth motion locally, failing safely to center crop."""
    if end <= start:
        return _center_fallback("Auto framing received an invalid clip range; center crop used.")
    try:
        import cv2  # type: ignore[import-not-found]
    except (ImportError, OSError):
        return _center_fallback(
            "Local face tracking is unavailable in this installation; center crop used."
        )

    capture = None
    try:
        runtime_ready, runtime_message = auto_framing_runtime_status()
        if not runtime_ready:
            return _center_fallback(f"{runtime_message}; center crop used.")
        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        detector = cv2.CascadeClassifier(str(cascade_path))
        if detector.empty():
            return _center_fallback(
                "Local face detector data is unavailable; center crop used."
            )
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            return _center_fallback("Auto framing could not read the video; center crop used.")

        sample_times = []
        current = start
        while current < end and len(sample_times) < 360:
            sample_times.append(current)
            current += sample_interval

        observations: list[FaceObservation] = []
        previous_tracks: dict[int, tuple[float, float, object, float]] = {}
        next_track_id = 1
        for timestamp in sample_times:
            capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            height, width = frame.shape[:2]
            if width <= 0 or height <= 0:
                continue
            if width > 720:
                scale = 720 / width
                frame = cv2.resize(frame, (720, max(1, round(height * scale))))
                height, width = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)
            detected = detector.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(40, 40),
            )
            assigned: set[int] = set()
            for x, y, face_width, face_height in sorted(
                detected,
                key=lambda box: int(box[2]) * int(box[3]),
                reverse=True,
            )[:5]:
                center_x = (float(x) + float(face_width) / 2) / width
                area = float(face_width * face_height) / float(width * height)
                mouth_top = int(y + face_height * 0.55)
                mouth = gray[mouth_top : y + face_height, x : x + face_width]
                if mouth.size == 0:
                    continue
                mouth_patch = cv2.resize(mouth, (32, 16))

                candidates = []
                for track_id, (old_center, old_area, _patch, old_time) in previous_tracks.items():
                    if track_id in assigned or timestamp - old_time > sample_interval * 2.5:
                        continue
                    area_ratio = area / max(old_area, 1e-6)
                    distance = abs(center_x - old_center)
                    if 0.45 <= area_ratio <= 2.2 and distance <= 0.2:
                        candidates.append((distance + abs(math.log(area_ratio)) * 0.06, track_id))
                if candidates:
                    track_id = min(candidates)[1]
                    old_patch = previous_tracks[track_id][2]
                    motion = float(cv2.absdiff(mouth_patch, old_patch).mean()) / 255.0
                else:
                    track_id = next_track_id
                    next_track_id += 1
                    motion = 0.0
                assigned.add(track_id)
                previous_tracks[track_id] = (center_x, area, mouth_patch, timestamp)
                audio = signals.audio_for(
                    max(start, timestamp - sample_interval / 2),
                    min(end, timestamp + sample_interval / 2),
                ) if signals else None
                observations.append(
                    FaceObservation(
                        time=timestamp,
                        track_id=track_id,
                        center_x=center_x,
                        area=area,
                        mouth_motion=motion,
                        audio_energy=audio,
                    )
                )
        return choose_auto_framing(
            observations,
            clip_start=start,
            expected_samples=len(sample_times),
        )
    except Exception:
        return _center_fallback(
            "Auto framing could not establish reliable local evidence; center crop used."
        )
    finally:
        if capture is not None:
            capture.release()
