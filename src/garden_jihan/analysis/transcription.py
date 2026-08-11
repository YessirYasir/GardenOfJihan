from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path


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


def transcribe(path: Path, language: str | None = None, model_name: str = "small") -> Transcript:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Install the 'ai' extra to enable local transcription") from exc

    model = WhisperModel(model_name, device="auto", compute_type="auto")
    segments, info = model.transcribe(
        str(path), language=language, vad_filter=True, word_timestamps=True, beam_size=5
    )
    parsed = []
    for segment in segments:
        text = str(segment.text).strip()
        if not text:
            continue
        segment_start = float(segment.start)
        segment_end = float(segment.end)
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
    return Transcript(language=info.language or language or "unknown", segments=parsed)
