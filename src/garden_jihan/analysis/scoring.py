from __future__ import annotations

import re
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field

from garden_jihan.analysis.semantics import (
    LocalSemanticRanker,
    SemanticProfile,
    cosine_similarity,
)
from garden_jihan.analysis.signals import MediaSignals
from garden_jihan.analysis.somali import somali_matching_tokens
from garden_jihan.analysis.transcription import TranscriptSegment
from garden_jihan.models import AnalysisMode, ClipCandidate

HOOKS = {
    "general": {
        "listen", "truth", "secret", "never", "why", "how", "problem", "mistake", "imagine",
        "wait", "nobody", "everyone", "actually", "here's", "here", "watch", "remember",
    },
    "somali": {
        "bal", "ogow", "sabab", "maxaa", "sidee", "runta", "qalad", "dhib", "marka", "laakiin",
        "xaqiiqda", "fiiri", "maqal", "marnaba", "qofna", "dadka", "arrin", "suaal",
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
STORY = {
    "general": {
        "story", "once", "when", "then", "after", "before", "remember", "example",
        "imagine", "person", "man", "woman", "family", "learned", "happened",
    },
    "somali": {
        "sheeko", "mar", "maalin", "markii", "markaas", "dabadeed", "kadib", "kahor",
        "tusaale", "qof", "nin", "naag", "qoys", "wuxuu", "waxay", "dhacay", "bartay",
        "xusuus", "bal", "ogaaday",
    },
    "arabic": {
        "قصة", "مرة", "يوم", "عندما", "ثم", "بعد", "قبل", "مثال", "رجل", "امرأة",
        "شخص", "أسرة", "حدث", "تعلم", "تذكر", "تخيل",
    },
}
KEY_PHRASES = {
    "general": (
        "the important thing", "here is why", "for example", "what happened next",
        "the lesson is", "this means", "the real reason", "in the end",
    ),
    "somali": (
        "waxaa muhiim ah", "arrinta muhiimka", "sababta oo ah", "tusaale ahaan",
        "taas macnaheedu", "waxa dhacay", "markii uu", "markii ay", "ugu dambayn",
        "casharka waa", "bal ka warran", "xaqiiqdu waa",
    ),
    "arabic": (
        "المهم هو", "والسبب هو", "على سبيل المثال", "ماذا حدث", "هذا يعني",
        "العبرة هي", "في النهاية", "الحقيقة هي",
    ),
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
    story: float = 0.0
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
    segment_texts: list[str] = field(default_factory=list)
    semantic_model: str | None = None


def _language_key(mode: AnalysisMode) -> str:
    return "general" if mode in {AnalysisMode.AUTO, AnalysisMode.GENERAL, AnalysisMode.QURAN} else mode.value


def _tokens(text: str, key: str = "general") -> list[str]:
    if key == "somali":
        return somali_matching_tokens(text)
    return re.findall(r"[\w\u0600-\u06FF'-]+", text.lower(), flags=re.UNICODE)


def _content_tokens(tokens: list[str], key: str) -> list[str]:
    stop = STOPWORDS.get(key, set())
    return [token for token in tokens if len(token) > 1 and token not in stop]


def _lexicon_hits(tokens: list[str], lexicon: set[str]) -> int:
    return sum(1 for token in tokens if token in lexicon)


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def _jaccard(a: str, b: str, key: str) -> float:
    a_tokens = set(_content_tokens(_tokens(a, key), key))
    b_tokens = set(_content_tokens(_tokens(b, key), key))
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
    tokens = _tokens(text, key)
    content = _content_tokens(tokens, key)
    first = tokens[: min(30, len(tokens))]
    final = tokens[-min(24, len(tokens)) :] if tokens else []

    hooks = _lexicon_hits(first, HOOKS.get(key, set()))
    emotions = _lexicon_hits(tokens, EMOTION.get(key, set()))
    contrasts = _lexicon_hits(tokens, CONTRAST.get(key, set()))
    payoffs = _lexicon_hits(final, PAYOFF.get(key, set()))
    story_hits = _lexicon_hits(tokens, STORY.get(key, set()))
    normalized_text = " ".join(tokens)
    phrase_hits = sum(
        1 for phrase in KEY_PHRASES.get(key, ()) if phrase in normalized_text
    )
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
    story_score = _clamp(
        16
        + min(story_hits, 7) * 8
        + min(phrase_hits, 3) * 13
        + min(contrasts, 2) * 7
        + min(payoffs, 2) * 8
    )

    breakdown = ScoreBreakdown(
        hook=hook_score,
        emotion=emotion_score,
        curiosity=curiosity_score,
        payoff=payoff_score,
        completeness=completeness_score,
        density=density_score,
        novelty=novelty_score,
        story=story_score,
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
        + emotion_score * 0.08
        + curiosity_score * 0.12
        + payoff_score * 0.13
        + completeness_score * 0.13
        + density_score * 0.08
        + novelty_score * 0.05
        + story_score * 0.08
        + breakdown.audio * 0.05
        + breakdown.visual * 0.03
        + breakdown.replay * 0.05
    )
    score += min(6.0, hooks * 0.8 + emotions * 0.5 + questions * 0.7 + contrasts * 0.4)
    score += min(5.0, story_hits * 0.6 + phrase_hits * 1.5)

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
    if story_score >= 62:
        reasons.append("Tells a story or example with a clear turn")
    elif phrase_hits:
        reasons.append("A key phrase brings the main idea into focus")

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


def _rerank_semantic_shortlist(
    shortlist: list[ScoredWindow],
    profiles: list[SemanticProfile],
    model_name: str,
    max_clips: int,
) -> list[ScoredWindow]:
    if len(shortlist) != len(profiles):
        raise ValueError("Semantic profiles do not match the ranking shortlist")
    for window, profile in zip(shortlist, profiles, strict=True):
        window.score = round(_clamp(window.score * 0.90 + profile.coherence * 0.10), 1)
        window.breakdown["semantic_coherence"] = profile.coherence
        window.semantic_model = model_name
        if profile.coherence >= 70:
            window.reasons = [
                *window.reasons,
                "Ideas stay focused from beginning to end",
            ][:6]

    selected: list[int] = []
    remaining = set(range(len(shortlist)))
    while remaining and len(selected) < max_clips:
        def selection_score(index: int) -> float:
            if not selected:
                return shortlist[index].score
            similarity = max(
                cosine_similarity(profiles[index].vector, profiles[chosen].vector)
                for chosen in selected
            )
            duplicate_penalty = max(0.0, (similarity - 0.78) / 0.22) * 7.0
            return shortlist[index].score - duplicate_penalty

        best = max(remaining, key=lambda index: (selection_score(index), shortlist[index].score))
        selected.append(best)
        remaining.remove(best)
    return [shortlist[index] for index in selected]


def _moment_title(
    segment_texts: list[str],
    mode: AnalysisMode,
    start: float,
) -> str:
    key = _language_key(mode)

    def phrase_strength(text: str) -> tuple[int, int]:
        tokens = _tokens(text, key)
        content = _content_tokens(tokens, key)
        signal = (
            _lexicon_hits(tokens, HOOKS.get(key, set())) * 3
            + _lexicon_hits(tokens, STORY.get(key, set())) * 2
            + _lexicon_hits(tokens, PAYOFF.get(key, set())) * 2
            + sum(3 for phrase in KEY_PHRASES.get(key, ()) if phrase in " ".join(tokens))
        )
        return signal, min(len(content), 12)

    meaningful = [text.strip() for text in segment_texts if len(_tokens(text, key)) >= 3]
    if not meaningful:
        return "Strong moment"
    phrase = max(meaningful, key=phrase_strength)
    words = phrase.split()
    title = " ".join(words[:9]).strip(" .,:;!?؟")
    if len(words) > 9:
        title += "…"
    if mode == AnalysisMode.SOMALI:
        arabic_letters = len(re.findall(r"[\u0600-\u06ff]", title))
        latin_letters = len(re.findall(r"[A-Za-z]", title))
        if arabic_letters > max(4, latin_letters):
            minutes, seconds = divmod(max(0, round(start)), 60)
            return f"Moment at {minutes}:{seconds:02d}"
    return title[:72] or "Strong moment"


def _apply_relative_strength(windows: list[ScoredWindow]) -> None:
    if not windows:
        return
    values = sorted(window.score for window in windows)
    for window in windows:
        if len(values) == 1:
            percentile = 50.0
        else:
            below = sum(value < window.score for value in values)
            equal = sum(value == window.score for value in values)
            percentile = (below + (equal - 1) / 2) / (len(values) - 1) * 100
        relative_strength = round(50 + percentile * 0.5, 1)
        window.breakdown["relative_strength"] = relative_strength
        window.score = round(_clamp(window.score + relative_strength * 0.5), 1)


def build_candidates(
    segments: list[TranscriptSegment],
    mode: AnalysisMode,
    min_seconds: int = 20,
    max_seconds: int = 75,
    max_clips: int = 10,
    signals: MediaSignals | None = None,
    semantic_ranker: LocalSemanticRanker | None = None,
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
            windows.append(
                ScoredWindow(
                    start,
                    end,
                    text,
                    score,
                    reasons,
                    breakdown,
                    [segment.text for segment in segments[i : j + 1]],
                )
            )

            if text.rstrip().endswith((".", "!", "?", "؟", ":")):
                break

    windows.sort(key=lambda window: window.score, reverse=True)
    shortlist: list[ScoredWindow] = []
    for window in windows:
        if _is_duplicate(window, shortlist, key):
            continue
        shortlist.append(window)
        if len(shortlist) >= max(max_clips * 6, max_clips):
            break

    chosen = shortlist[:max_clips]
    if semantic_ranker is not None and mode != AnalysisMode.QURAN and shortlist:
        profiles = semantic_ranker.profile_windows([window.segment_texts for window in shortlist])
        if profiles:
            chosen = _rerank_semantic_shortlist(
                shortlist,
                profiles,
                semantic_ranker.model_name,
                max_clips,
            )

    _apply_relative_strength(chosen)
    return [
        ClipCandidate(
            id=uuid.uuid4().hex[:12],
            start=window.start,
            end=window.end,
            score=window.score,
            title=(
                "Qur'an passage"
                if mode == AnalysisMode.QURAN
                else _moment_title(window.segment_texts, mode, window.start)
            ),
            reasons=window.reasons,
            transcript=window.text,
            mode=mode,
            score_breakdown=window.breakdown,
            semantic_model=window.semantic_model,
        )
        for window in chosen
    ]
