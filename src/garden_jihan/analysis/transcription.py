from __future__ import annotations

import math
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import file_digest
from pathlib import Path

SPEECH_MODEL = "Systran/faster-whisper-small"
SPEECH_MODEL_REVISION = "536b0662742c02347bc0e980a01041f333bce120"
SPEECH_MODEL_FILES = {
    "config.json": "b55496ac7940a7ae47d2c01eab40edfd8701feec1229d9cce3b40014383fb828",
    "model.bin": "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671",
    "tokenizer.json": "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab",
    "vocabulary.txt": "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913",
}

ProgressCallback = Callable[[float, float | None], None]
_MODEL_LOCK = threading.Lock()
_MODEL_CACHE: dict[str, object] = {}


@dataclass(frozen=True, slots=True)
class TranscriptWord:
    start: float
    end: float
    text: str
    probability: float


@dataclass(slots=True)
class TranscriptSegment:
    start: float
    end: float
    text: str
    words: list[TranscriptWord] = field(default_factory=list)


@dataclass(slots=True)
class Transcript:
    language: str
    segments: list[TranscriptSegment]


def _speech_model_source(model_name: str) -> tuple[str, bool]:
    bundled = os.getenv("GOJ_SPEECH_MODEL_PATH", "").strip()
    if bundled:
        path = Path(bundled).expanduser().resolve()
        if not path.is_dir():
            raise RuntimeError("Included speech resources are missing")
        return str(path), True
    return model_name, False


def _load_model(model_name: str):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Local speech understanding is unavailable") from exc

    source, bundled = _speech_model_source(model_name)
    device = os.getenv("GOJ_TRANSCRIPTION_DEVICE", "cpu").strip().lower() or "cpu"
    if device not in {"cpu", "cuda"}:
        device = "cpu"
    default_compute = "int8" if device == "cpu" else "float16"
    compute_type = os.getenv("GOJ_TRANSCRIPTION_COMPUTE_TYPE", default_compute).strip()
    cache_key = f"{source}|{bundled}|{device}|{compute_type}"
    with _MODEL_LOCK:
        cached = _MODEL_CACHE.get(cache_key)
        if cached is not None:
            return cached

        if bundled:
            model_path = Path(source)
            for relative_path, trusted_sha256 in SPEECH_MODEL_FILES.items():
                resource = model_path / relative_path
                if not resource.is_file():
                    raise RuntimeError(f"Included speech resource is missing: {relative_path}")
                with resource.open("rb") as handle:
                    actual_sha256 = file_digest(handle, "sha256").hexdigest()
                if actual_sha256 != trusted_sha256:
                    raise RuntimeError(
                        f"Included speech resource failed verification: {relative_path}"
                    )

        # The portable Windows runtime does not ship NVIDIA's separate CUDA
        # libraries. Defaulting to the optimized CPU path avoids a driver-only
        # CUDA detection that otherwise fails when inference begins. Advanced
        # source users can explicitly opt into CUDA after installing its runtime.
        common = {"device": device, "compute_type": compute_type}
        if bundled:
            model = WhisperModel(source, local_files_only=True, **common)
        else:
            # Prefer an existing verified cache without making a network request. This
            # avoids a completed download hanging while a second metadata request waits.
            try:
                model = WhisperModel(
                    model_name,
                    local_files_only=True,
                    revision=SPEECH_MODEL_REVISION,
                    **common,
                )
            except Exception:
                model = WhisperModel(
                    model_name,
                    revision=SPEECH_MODEL_REVISION,
                    **common,
                )
        _MODEL_CACHE[cache_key] = model
        return model


def _batch_size() -> int:
    raw = os.getenv("GOJ_TRANSCRIPTION_BATCH_SIZE", "8").strip()
    try:
        return max(1, min(16, int(raw)))
    except ValueError:
        return 8


def transcribe(
    path: Path,
    language: str | None = None,
    model_name: str = SPEECH_MODEL,
    *,
    progress: ProgressCallback | None = None,
    clips: list[tuple[float, float]] | None = None,
) -> Transcript:
    try:
        from faster_whisper import BatchedInferencePipeline
    except ImportError:
        BatchedInferencePipeline = None

    if progress:
        progress(0.0, None)
    model = _load_model(model_name)
    batch_size = _batch_size()
    runner = (
        BatchedInferencePipeline(model=model)
        if BatchedInferencePipeline is not None and batch_size > 1
        else model
    )
    options = {
        "language": language,
        "vad_filter": True,
        "vad_parameters": {"min_silence_duration_ms": 500},
        "word_timestamps": True,
        "beam_size": 1,
        "best_of": 1,
        "condition_on_previous_text": False,
        # Auto mode may follow language changes between Somali teaching and
        # Arabic quotations. A language the user explicitly selected remains
        # fixed so Somali speech is not mislabeled as Arabic.
        "multilingual": language is None,
    }
    if runner is not model:
        options["batch_size"] = batch_size
        if clips:
            options["clip_timestamps"] = [
                {"start": start, "end": end} for start, end in clips
            ]
    elif clips:
        options["clip_timestamps"] = [value for clip in clips for value in clip]
    segments, info = runner.transcribe(str(path), **options)
    source_duration = float(getattr(info, "duration", 0.0) or 0.0)
    listening_duration = (
        sum(end - start for start, end in clips)
        if clips
        else source_duration
    )

    def listened_fraction(timestamp: float) -> float:
        if not clips:
            return timestamp / listening_duration if listening_duration > 0 else 0.0
        heard = 0.0
        for start, end in clips:
            if timestamp >= end:
                heard += end - start
                continue
            if timestamp > start:
                heard += min(timestamp, end) - start
            break
        return heard / listening_duration if listening_duration > 0 else 0.0

    parsed = []
    last_fraction = 0.0
    for segment in segments:
        text = str(segment.text).strip()
        segment_start = float(segment.start)
        segment_end = float(segment.end)
        if progress and listening_duration > 0:
            fraction = min(1.0, max(last_fraction, listened_fraction(segment_end)))
            if fraction >= last_fraction + 0.005 or fraction >= 1.0:
                progress(fraction, listening_duration)
                last_fraction = fraction
        if not text:
            continue
        words = []
        for word in getattr(segment, "words", None) or ():
            word_text = str(getattr(word, "word", "")).strip()
            try:
                word_start = float(word.start)
                word_end = float(word.end)
                probability = float(word.probability)
            except (AttributeError, TypeError, ValueError):
                continue
            if (
                not word_text
                or not all(math.isfinite(value) for value in (word_start, word_end, probability))
                or word_start < max(0.0, segment_start - 0.25)
                or word_end > segment_end + 0.25
                or word_end <= word_start
                or not 0.0 <= probability <= 1.0
            ):
                continue
            words.append(TranscriptWord(word_start, word_end, word_text, probability))
        parsed.append(TranscriptSegment(segment_start, segment_end, text, words))
    if progress:
        progress(1.0, listening_duration or None)
    return Transcript(language=info.language or language or "unknown", segments=parsed)
