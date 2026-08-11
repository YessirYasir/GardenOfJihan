from __future__ import annotations

import re
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field

from garden_jihan.analysis.signals import MediaSignals
from garden_jihan.analysis.transcription import TranscriptSegment
from garden_jihan.models import AnalysisMode, ClipCandidate

HOOKS = {
    "general": {
        "listen", "truth", "secret", "never", "why", "how", "problem", "mistake", "imagine",
        "wait", "nobody", "everyone", "actually", "here's", "here", "watch", "remember",
    },
    "somali": {
        "bal", "ogow", "sabab", "maxaa", "sidee", "runta", "qalad", "dhib", "marka", "laakiin",
        "xaqiiqda", "fiiri", "maqal", "marnaba", "qofna", "dadka", "arrin", "su'aal",
    },
    "arabic": {
        "اسمع", "لماذا", "كيف", "الحقيقة", "لكن", "مشكلة", "سبب", "تخيل", "انتبه", "هل",
        "أبدا", "ابدا", "سر", "شاهد", "تذكر", "الناس", "المهم", "فعلا",
    },
}
EMOTION = {
    "general": {
        "love", "hate", "angry", "amazing", "shocked", "fear", "beautiful", "crazy", "important",
        "pain", "hope", "proud", "sad", "happy", "danger", "powerful", "unbelievable",
    },
    "somali": {
        "jacayl", "nacayb", "xanaaq", "yaab", "cabsi", "qurux", "muhiim", "farxad", "murugo",
        "xanuun", "rajo", "kibir", "khatar", "xoog", "naxdin", "qiiro",
    },
    "arabic": {
        "حب", "كره", "غضب", "عجيب", "خوف", "جميل", "مهم", "فرح", "حزن", "ألم", "الم",
        "أمل", "امل", "خطر", "قوي", "صدمة", "مؤثر",
    },
}
CONTRAST = {
    "general": {"but", "however", "instead", "until", "then", "because", "except", "although"},
    "somali": {"laakiin", "hase", "se", "markaas", "sababtoo", "haddana", "halka"},
    "arabic": {"لكن", "ولكن", "غير", "ثم", "لأن", "لان", "بينما", "مع", "إلا", "الا"},
}
PAYOFF = {
    "general": {"therefore", "so", "that's", "result", "lesson", "answer", "finally", "point"},
    "somali": {"sidaas", "sidaa", "natiijo", "jawaab", "cashar", "ugu", "dambayn", "micnaha"},
    "arabic": {"لذلك", "إذن", "اذن", "النتيجة", "الجواب", "العبرة", "أخيرا", "اخيرا", "المعنى"},
}
STOPWORDS = {
    "general": {"the", "a", "an", "and", "or", "to", "of", "in", "it", "is", "that", "this"},
    "somali": {"oo", "iyo", "waa", "in", "ay", "uu", "ka", "ku", "la", "si", "ah"},
    "arabic": {"في", "من", "على", "الى", "إلى", "و", "او", "أو", "هو", "هي", "هذا", "هذه"},
}


@dataclass(slots=True)
class ScoreBreakdown:
    hook: float = 0.0
    emotion: float = 0.0
    curiosity: float = 0.0
    payoff: float = 0.0
    completeness: float = 0.0
    density: float = 0.0
    novelty: float = 0.0
    audio: float = 0.0
    visual: float = 0.0
    replay: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {name: round(value, 1) for name, value in asdict(self).items()}


@dataclass(slots=True)
class ScoredWindow:
    start: float
    end: float
    text: str
    score: float
    reasons: list[str]
    breakdown: dict[str, float] = field(default_factory=dict)


def _language_key(mode: AnalysisMode) -> str:
    return "general" if mode in {AnalysisMode.AUTO, AnalysisMode.GENERAL, AnalysisMode.QURAN} else mode.value


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\w\u0600-\u06FF'-]+", text.lower(), flags=re.UNICODE)


def _content_tokens(tokens: list[str], key: str) -> list[str]:
    stop = STOPWORDS.get(key, set())
    return [token for token in tokens if len(token) > 1 and token not in stop]


def _lexicon_hits(tokens: list[str], lexicon: set[str]) -> int:
    return sum(1 for token in tokens if token in lexicon)


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def _jaccard(a: str, b: str, key: str) -> float:
    a_tokens = set(_content_tokens(_tokens(a), key))
    b_tokens = set(_content_tokens(_tokens(b), key))
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / len(a_tokens | b_tokens)


def score_text_detailed(
    text: str,
    mode: AnalysisMode,
    duration: float,
    *,
    audio_signal: float | None = None,
    scene_signal: float | None = None,
    replay_signal: float | None = None,
) -> tuple[float, list[str], dict[str, float]]:
    key = _language_key(mode)
    tokens = _tokens(text)
    content = _content_tokens(tokens, key)
    first = tokens[: min(30, len(tokens))]
    final = tokens[-min(24, len(tokens)) :] if tokens else []

    hooks = _lexicon_hits(first, HOOKS.get(key, set()))
    emotions = _lexicon_hits(tokens, EMOTION.get(key, set()))
    contrasts = _lexicon_hits(tokens, CONTRAST.get(key, set()))
    payoffs = _lexicon_hits(final, PAYOFF.get(key, set()))
    questions = text.count("?") + text.count("؟")
    exclamations = text.count("!")

    words_per_second = len(tokens) / max(duration, 1.0)
    density = min(1.0, words_per_second / 2.7)
    complete = 1.0 if text.rstrip().endswith((".", "!", "?", "؟", "。", ":")) else 0.5
    punctuation = min(1.0, (text.count(".") + questions + exclamations) / 4.0)

    counts = Counter(content)
    repeated = sum(max(0, count - 2) for count in counts.values())
    repetition_ratio = repeated / max(len(content), 1)
    lexical_variety = len(counts) / max(len(content), 1)

    hook_score = _clamp(30 + hooks * 19 + min(questions, 1) * 18 + min(exclamations, 1) * 8)
    emotion_score = _clamp(18 + emotions * 15 + min(exclamations, 2) * 7)
    curiosity_score = _clamp(22 + min(questions, 2) * 24 + min(contrasts, 3) * 12)
    payoff_score = _clamp(28 + min(payoffs, 3) * 18 + min(contrasts, 2) * 10 + complete * 12)
    completeness_score = _clamp(36 + complete * 40 + punctuation * 18)
    density_score = _clamp(25 + density * 65)
    novelty_score = _clamp(35 + lexical_variety * 60 - repetition_ratio * 90)

    breakdown = ScoreBreakdown(
        hook=hook_score,
        emotion=emotion_score,
        curiosity=curiosity_score,
        payoff=payoff_score,
        completeness=completeness_score,
        density=density_score,
        novelty=novelty_score,
        audio=_clamp((audio_signal or 0.0) * 100),
        visual=_clamp((scene_signal or 0.0) * 100),
        replay=_clamp((replay_signal or 0.0) * 100),
    )

    if mode == AnalysisMode.QURAN:
        score = (
            completeness_score * 0.42
            + density_score * 0.12
            + breakdown.audio * 0.18
            + breakdown.visual * 0.04
            + breakdown.replay * 0.12
            + 50 * 0.12
        )
        reasons = ["Recitation segment candidate", "Natural ending and pause quality prioritized"]
        if audio_signal is not None and audio_signal >= 0.7:
            reasons.append("Recitation intensity rises in this passage")
        if replay_signal is not None and replay_signal >= 0.65:
            reasons.append("Viewer replay activity supports this passage")
        return round(_clamp(score), 1), reasons, breakdown.as_dict()

    score = (
        hook_score * 0.20
        + emotion_score * 0.10
        + curiosity_score * 0.14
        + payoff_score * 0.16
        + completeness_score * 0.14
        + density_score * 0.08
        + novelty_score * 0.06
        + breakdown.audio * 0.05
        + breakdown.visual * 0.025
        + breakdown.replay * 0.045
    )
    score += min(6.0, hooks * 0.8 + emotions * 0.5 + questions * 0.7 + contrasts * 0.4)

    reasons: list[str] = []
    if hook_score >= 67:
        reasons.append("Strong opening hook")
    if curiosity_score >= 65:
        reasons.append("Question, contrast, or tension creates curiosity")
    if emotion_score >= 62:
        reasons.append("Emotionally expressive language")
    if payoff_score >= 65:
        reasons.append("Contains a clear payoff or conclusion")
    if replay_signal is not None and replay_signal >= 0.65:
        reasons.append("Viewer replay activity supports this moment")
    if audio_signal is not None and audio_signal >= 0.7:
        reasons.append("Audio energy rises during this moment")
    if scene_signal is not None and scene_signal >= 0.65:
        reasons.append("Visual activity supports retention")
    if completeness_score >= 75:
        reasons.append("Forms a self-contained thought")
    if density_score >= 70:
        reasons.append("High information density with little verbal dead space")
    if novelty_score >= 75:
        reasons.append("Varied wording reduces repetitive filler")

    return round(_clamp(score), 1), reasons[:6] or ["Complete, self-contained candidate"], breakdown.as_dict()


def score_text(
    text: str,
    mode: AnalysisMode,
    duration: float,
    replay_signal: float | None = None,
) -> tuple[float, list[str]]:
    score, reasons, _ = score_text_detailed(
        text,
        mode,
        duration,
        replay_signal=replay_signal,
    )
    return score, reasons


def _is_duplicate(candidate: ScoredWindow, chosen: list[ScoredWindow], key: str) -> bool:
    for existing in chosen:
        overlaps = not (candidate.end <= existing.start or candidate.start >= existing.end)
        if overlaps:
            return True
        if _jaccard(candidate.text, existing.text, key) >= 0.62:
            return True
    return False


def build_candidates(
    segments: list[TranscriptSegment],
    mode: AnalysisMode,
    min_seconds: int = 20,
    max_seconds: int = 75,
    max_clips: int = 10,
    signals: MediaSignals | None = None,
) -> list[ClipCandidate]:
    windows: list[ScoredWindow] = []
    signals = signals or MediaSignals()
    key = _language_key(mode)

    for i in range(len(segments)):
        start = segments[i].start
        text_parts: list[str] = []
        end = start
        for j in range(i, len(segments)):
            end = segments[j].end
            if end - start > max_seconds:
                break
            text_parts.append(segments[j].text)
            if end - start < min_seconds:
                continue

            text = " ".join(text_parts).strip()
            audio = signals.audio_for(start, end)
            visual = signals.scene_density_for(start, end)
            replay = signals.replay_for(start, end)
            score, reasons, breakdown = score_text_detailed(
                text,
                mode,
                end - start,
                audio_signal=audio,
                scene_signal=visual,
                replay_signal=replay,
            )
            windows.append(ScoredWindow(start, end, text, score, reasons, breakdown))

            if text.rstrip().endswith((".", "!", "?", "؟", ":")):
                break

    windows.sort(key=lambda window: window.score, reverse=True)
    chosen: list[ScoredWindow] = []
    for window in windows:
        if _is_duplicate(window, chosen, key):
            continue
        chosen.append(window)
        if len(chosen) >= max_clips:
            break

    return [
        ClipCandidate(
            id=uuid.uuid4().hex[:12],
            start=window.start,
            end=window.end,
            score=window.score,
            title=("Qur'an passage" if mode == AnalysisMode.QURAN else "Strong moment"),
            reasons=window.reasons,
            transcript=window.text,
            mode=mode,
            score_breakdown=window.breakdown,
        )
        for window in chosen
    ]
