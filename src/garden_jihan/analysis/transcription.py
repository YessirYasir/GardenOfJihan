from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(slots=True)
class Transcript:
    language: str
    segments: list[TranscriptSegment]


def transcribe(path: Path, language: str | None = None, model_name: str = "small") -> Transcript:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Install the 'ai' extra to enable local transcription") from exc

    model = WhisperModel(model_name, device="auto", compute_type="auto")
    segments, info = model.transcribe(
        str(path), language=language, vad_filter=True, word_timestamps=False, beam_size=5
    )
    parsed = [TranscriptSegment(float(s.start), float(s.end), s.text.strip()) for s in segments if s.text.strip()]
    return Transcript(language=info.language or language or "unknown", segments=parsed)
