from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass

from garden_jihan.analysis.transcription import TranscriptSegment
from garden_jihan.models import AnalysisMode, ClipCandidate

HOOKS = {
    "general": {"listen", "truth", "secret", "never", "why", "how", "problem", "mistake", "imagine", "wait"},
    "somali": {"bal", "ogow", "sabab", "maxaa", "sidee", "runta", "qalad", "dhib", "marka", "laakiin"},
    "arabic": {"اسمع", "لماذا", "كيف", "الحقيقة", "لكن", "مشكلة", "سبب", "تخيل", "انتبه", "هل"},
}
EMOTION = {
    "general": {"love", "hate", "angry", "amazing", "shocked", "fear", "beautiful", "crazy", "important"},
    "somali": {"jacayl", "nacayb", "xanaaq", "yaab", "cabsi", "qurux", "muhiim", "farxad", "murugo"},
    "arabic": {"حب", "كره", "غضب", "عجيب", "خوف", "جميل", "مهم", "فرح", "حزن"},
}


@dataclass(slots=True)
class ScoredWindow:
    start: float
    end: float
    text: str
    score: float
    reasons: list[str]


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\w\u0600-\u06FF'-]+", text.lower(), flags=re.UNICODE)


def _lexicon_hits(tokens: list[str], lexicon: set[str]) -> int:
    return sum(1 for t in tokens if t in lexicon)


def score_text(text: str, mode: AnalysisMode, duration: float, replay_signal: float | None = None) -> tuple[float, list[str]]:
    key = "general" if mode in {AnalysisMode.AUTO, AnalysisMode.GENERAL, AnalysisMode.QURAN} else mode.value
    tokens = _tokens(text)
    hooks = _lexicon_hits(tokens[:30], HOOKS.get(key, set()))
    emotions = _lexicon_hits(tokens, EMOTION.get(key, set()))
    questions = text.count("?") + text.count("؟")
    density = min(len(tokens) / max(duration, 1.0), 3.0) / 3.0
    completeness = 1.0 if text.rstrip().endswith((".", "!", "?", "؟", "。")) else 0.55

    raw = 42 + min(hooks, 4) * 7 + min(emotions, 4) * 4 + min(questions, 2) * 5
    raw += density * 12 + completeness * 8
    reasons: list[str] = []
    if hooks:
        reasons.append("Strong opening language")
    if emotions:
        reasons.append("Emotionally expressive wording")
    if questions:
        reasons.append("Question or tension creates curiosity")
    if density > 0.55:
        reasons.append("Dense spoken content with little dead space")
    if completeness > 0.9:
        reasons.append("Ends on a complete thought")
    if replay_signal is not None:
        replay = max(0.0, min(1.0, replay_signal))
        raw = raw * 0.88 + replay * 100 * 0.12
        if replay > 0.65:
            reasons.append("Viewer replay signal supports this moment")

    if mode == AnalysisMode.QURAN:
        raw = 50 + density * 10 + completeness * 20
        reasons = ["Recitation segment candidate", "Natural boundary scoring required before export"]

    return round(max(0.0, min(100.0, raw)), 1), reasons or ["Complete self-contained candidate"]


def build_candidates(
    segments: list[TranscriptSegment],
    mode: AnalysisMode,
    min_seconds: int = 20,
    max_seconds: int = 75,
    max_clips: int = 10,
) -> list[ClipCandidate]:
    windows: list[ScoredWindow] = []
    for i in range(len(segments)):
        start = segments[i].start
        text_parts: list[str] = []
        end = start
        for j in range(i, len(segments)):
            end = segments[j].end
            if end - start > max_seconds:
                break
            text_parts.append(segments[j].text)
            if end - start >= min_seconds:
                text = " ".join(text_parts).strip()
                score, reasons = score_text(text, mode, end - start)
                windows.append(ScoredWindow(start, end, text, score, reasons))
                if text.endswith((".", "!", "?", "؟")):
                    break

    windows.sort(key=lambda w: w.score, reverse=True)
    chosen: list[ScoredWindow] = []
    for window in windows:
        if any(not (window.end <= c.start or window.start >= c.end) for c in chosen):
            continue
        chosen.append(window)
        if len(chosen) >= max_clips:
            break

    chosen.sort(key=lambda w: w.score, reverse=True)
    return [
        ClipCandidate(
            id=uuid.uuid4().hex[:12],
            start=w.start,
            end=w.end,
            score=w.score,
            title=("Qur'an passage" if mode == AnalysisMode.QURAN else "Strong moment"),
            reasons=w.reasons,
            transcript=w.text,
            mode=mode,
        )
        for w in chosen
    ]
