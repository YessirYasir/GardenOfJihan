from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

MAX_EVALUATION_BYTES = 10 * 1024 * 1024
MAX_JSONL_LINE_BYTES = 128 * 1024
MAX_PAIR_DURATION_RATIO = 1.5
_TOKEN_PATTERN = re.compile(r"[\w\u0600-\u06FF'’‘-]+", flags=re.UNICODE)
_APOSTROPHE_TRANSLATION = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "`": "'"})
_EVALUATION_FIELDS = {
    "id",
    "pair_id",
    "preferred",
    "duration",
    "verbatim",
    "normalized",
    "dialect_group",
    "source_id",
    "license",
    "reviewers",
    "adjudicated",
    "subvariety",
    "region",
    "speaker_id",
    "genre",
    "audio_quality",
    "code_switching",
}


@dataclass(slots=True)
class SomaliAnnotation:
    verbatim: str
    normalized: str | None
    dialect_group: str
    subvariety: str | None = None
    region: str | None = None
    code_switching: tuple[str, ...] = ()


def preserve_dialect(annotation: SomaliAnnotation) -> dict[str, object]:
    """Expose reviewed alternatives without silently replacing dialect-faithful text."""
    return {
        "display": annotation.verbatim,
        "normalized": annotation.normalized,
        "dialect_group": annotation.dialect_group,
        "subvariety": annotation.subvariety,
        "region": annotation.region,
        "code_switching": list(annotation.code_switching),
    }


def normalize_somali_matching_token(token: str) -> str:
    """Normalize punctuation-only spelling variation for scoring, never for display."""
    normalized = unicodedata.normalize("NFKC", token).casefold().translate(
        _APOSTROPHE_TRANSLATION
    )
    return re.sub(r"['_-]+", "", normalized).strip("_")


def somali_matching_tokens(text: str) -> list[str]:
    """Tokenize a temporary Somali matching copy while preserving the source text elsewhere."""
    tokens = [normalize_somali_matching_token(token) for token in _TOKEN_PATTERN.findall(text)]
    return [token for token in tokens if token]


def _required_text(data: Mapping[str, object], key: str, line_number: int) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Line {line_number}: {key} must be a non-empty string")
    return value.strip()


def _optional_text(data: Mapping[str, object], key: str, line_number: int) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Line {line_number}: {key} must be null or a non-empty string")
    return value.strip()


def _string_tuple(
    data: Mapping[str, object],
    key: str,
    line_number: int,
    *,
    required: bool = False,
) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"Line {line_number}: {key} must be a list of non-empty strings")
    result = tuple(dict.fromkeys(item.strip() for item in value))
    if required and not result:
        raise ValueError(f"Line {line_number}: {key} must not be empty")
    return result


@dataclass(frozen=True, slots=True)
class SomaliEvaluationItem:
    id: str
    pair_id: str
    preferred: bool
    duration: float
    verbatim: str
    normalized: str | None
    dialect_group: str
    source_id: str
    license: str
    reviewers: tuple[str, ...]
    adjudicated: bool
    subvariety: str | None = None
    region: str | None = None
    speaker_id: str | None = None
    genre: str | None = None
    audio_quality: str | None = None
    code_switching: tuple[str, ...] = ()

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, object],
        line_number: int,
        *,
        require_gold: bool = True,
    ) -> SomaliEvaluationItem:
        unknown_fields = sorted(set(data) - _EVALUATION_FIELDS)
        if unknown_fields:
            raise ValueError(
                f"Line {line_number}: unknown annotation fields: {', '.join(unknown_fields)}"
            )
        preferred = data.get("preferred")
        adjudicated = data.get("adjudicated")
        if not isinstance(preferred, bool):
            raise ValueError(f"Line {line_number}: preferred must be true or false")
        if not isinstance(adjudicated, bool):
            raise ValueError(f"Line {line_number}: adjudicated must be true or false")

        duration_value = data.get("duration")
        if isinstance(duration_value, bool) or not isinstance(duration_value, int | float):
            raise ValueError(f"Line {line_number}: duration must be a number")
        duration = float(duration_value)
        if not 0 < duration <= 180:
            raise ValueError(f"Line {line_number}: duration must be greater than 0 and at most 180")

        reviewers = _string_tuple(data, "reviewers", line_number, required=True)
        if require_gold and len(reviewers) < 2:
            raise ValueError(f"Line {line_number}: gold items require at least two reviewers")
        if require_gold and not adjudicated:
            raise ValueError(f"Line {line_number}: gold items must be adjudicated")

        return cls(
            id=_required_text(data, "id", line_number),
            pair_id=_required_text(data, "pair_id", line_number),
            preferred=preferred,
            duration=duration,
            verbatim=_required_text(data, "verbatim", line_number),
            normalized=_optional_text(data, "normalized", line_number),
            dialect_group=_required_text(data, "dialect_group", line_number),
            source_id=_required_text(data, "source_id", line_number),
            license=_required_text(data, "license", line_number),
            reviewers=reviewers,
            adjudicated=adjudicated,
            subvariety=_optional_text(data, "subvariety", line_number),
            region=_optional_text(data, "region", line_number),
            speaker_id=_optional_text(data, "speaker_id", line_number),
            genre=_optional_text(data, "genre", line_number),
            audio_quality=_optional_text(data, "audio_quality", line_number),
            code_switching=_string_tuple(data, "code_switching", line_number),
        )


def load_somali_evaluation_jsonl(
    path: Path,
    *,
    require_gold: bool = True,
) -> list[SomaliEvaluationItem]:
    """Load bounded, licensed JSONL annotations without exposing their text in errors."""
    if path.stat().st_size > MAX_EVALUATION_BYTES:
        raise ValueError("Somali evaluation file exceeds the 10 MB safety limit")

    items: list[SomaliEvaluationItem] = []
    seen_ids: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not raw_line.strip():
            continue
        if len(raw_line.encode("utf-8")) > MAX_JSONL_LINE_BYTES:
            raise ValueError(f"Line {line_number}: annotation exceeds the line-size limit")
        try:
            data = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Line {line_number}: invalid JSON") from exc
        if not isinstance(data, dict):
            raise ValueError(f"Line {line_number}: each annotation must be a JSON object")
        item = SomaliEvaluationItem.from_mapping(
            data,
            line_number,
            require_gold=require_gold,
        )
        if item.id in seen_ids:
            raise ValueError(f"Line {line_number}: duplicate item id")
        seen_ids.add(item.id)
        items.append(item)

    if not items:
        raise ValueError("Somali evaluation file contains no annotations")
    return items


@dataclass(frozen=True, slots=True)
class SomaliDialectMetrics:
    pair_count: int
    correct_pairs: int
    accuracy: float

    def public(self) -> dict[str, int | float]:
        return {
            "pair_count": self.pair_count,
            "correct_pairs": self.correct_pairs,
            "accuracy": round(self.accuracy, 4),
        }


@dataclass(frozen=True, slots=True)
class SomaliEvaluationReport:
    item_count: int
    pair_count: int
    correct_pairs: int
    pairwise_accuracy: float
    macro_dialect_accuracy: float
    worst_dialect_accuracy: float
    dialect_accuracy_gap: float
    spelling_variant_count: int
    spelling_score_delta_mae: float | None
    code_switched_pair_count: int
    code_switched_pair_accuracy: float | None
    per_dialect: dict[str, SomaliDialectMetrics]

    def public(self) -> dict[str, object]:
        data = asdict(self)
        data["pairwise_accuracy"] = round(self.pairwise_accuracy, 4)
        data["macro_dialect_accuracy"] = round(self.macro_dialect_accuracy, 4)
        data["worst_dialect_accuracy"] = round(self.worst_dialect_accuracy, 4)
        data["dialect_accuracy_gap"] = round(self.dialect_accuracy_gap, 4)
        if self.spelling_score_delta_mae is not None:
            data["spelling_score_delta_mae"] = round(self.spelling_score_delta_mae, 4)
        if self.code_switched_pair_accuracy is not None:
            data["code_switched_pair_accuracy"] = round(
                self.code_switched_pair_accuracy,
                4,
            )
        data["per_dialect"] = {
            group: metrics.public() for group, metrics in sorted(self.per_dialect.items())
        }
        return data


SomaliScoreFunction = Callable[[str, float], float]


def _production_somali_score(text: str, duration: float) -> float:
    from garden_jihan.analysis.scoring import score_text_detailed
    from garden_jihan.models import AnalysisMode

    score, _, _ = score_text_detailed(text, AnalysisMode.SOMALI, duration)
    return score


def evaluate_somali_ranking(
    items: list[SomaliEvaluationItem],
    *,
    scorer: SomaliScoreFunction | None = None,
) -> SomaliEvaluationReport:
    """Evaluate pair ranking and variation stability without averaging away dialect groups."""
    if not items:
        raise ValueError("Somali evaluation requires at least one item")
    scorer = scorer or _production_somali_score
    raw_scores = {item.id: float(scorer(item.verbatim, item.duration)) for item in items}

    spelling_deltas = [
        abs(raw_scores[item.id] - float(scorer(item.normalized, item.duration)))
        for item in items
        if item.normalized is not None
    ]

    pairs: dict[str, list[SomaliEvaluationItem]] = defaultdict(list)
    for item in items:
        pairs[item.pair_id].append(item)

    by_dialect: dict[str, list[bool]] = defaultdict(list)
    pair_results: list[bool] = []
    code_switched_results: list[bool] = []
    for pair_id, pair_items in pairs.items():
        if len(pair_items) < 2:
            raise ValueError(f"Pair {pair_id!r} must contain at least two candidates")
        preferred = [item for item in pair_items if item.preferred]
        if len(preferred) != 1:
            raise ValueError(f"Pair {pair_id!r} must contain exactly one preferred candidate")
        dialect_groups = {item.dialect_group for item in pair_items}
        if len(dialect_groups) != 1:
            raise ValueError(f"Pair {pair_id!r} must not compare different dialect groups")
        source_ids = {item.source_id for item in pair_items}
        if len(source_ids) != 1:
            raise ValueError(f"Pair {pair_id!r} must come from one licensed source")
        durations = [item.duration for item in pair_items]
        if max(durations) / min(durations) > MAX_PAIR_DURATION_RATIO:
            raise ValueError(f"Pair {pair_id!r} has incomparable candidate durations")

        winner = preferred[0]
        correct = raw_scores[winner.id] > max(
            raw_scores[item.id] for item in pair_items if item.id != winner.id
        )
        dialect_group = next(iter(dialect_groups))
        pair_results.append(correct)
        by_dialect[dialect_group].append(correct)
        if any(item.code_switching for item in pair_items):
            code_switched_results.append(correct)

    per_dialect = {
        group: SomaliDialectMetrics(
            pair_count=len(results),
            correct_pairs=sum(results),
            accuracy=sum(results) / len(results),
        )
        for group, results in by_dialect.items()
    }
    dialect_accuracies = [metrics.accuracy for metrics in per_dialect.values()]
    pairwise_accuracy = sum(pair_results) / len(pair_results)
    return SomaliEvaluationReport(
        item_count=len(items),
        pair_count=len(pair_results),
        correct_pairs=sum(pair_results),
        pairwise_accuracy=pairwise_accuracy,
        macro_dialect_accuracy=sum(dialect_accuracies) / len(dialect_accuracies),
        worst_dialect_accuracy=min(dialect_accuracies),
        dialect_accuracy_gap=max(dialect_accuracies) - min(dialect_accuracies),
        spelling_variant_count=len(spelling_deltas),
        spelling_score_delta_mae=(
            sum(spelling_deltas) / len(spelling_deltas) if spelling_deltas else None
        ),
        code_switched_pair_count=len(code_switched_results),
        code_switched_pair_accuracy=(
            sum(code_switched_results) / len(code_switched_results)
            if code_switched_results
            else None
        ),
        per_dialect=per_dialect,
    )


def _bounded_rate(value: str) -> float:
    parsed = float(value)
    if not 0 <= parsed <= 1:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return parsed


def _nonnegative(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate Somali clip ranking by reviewed group")
    parser.add_argument("corpus", type=Path, help="Licensed Somali evaluation JSONL")
    parser.add_argument("--allow-unadjudicated", action="store_true")
    parser.add_argument("--min-pair-accuracy", type=_bounded_rate)
    parser.add_argument("--min-macro-dialect-accuracy", type=_bounded_rate)
    parser.add_argument("--min-worst-dialect-accuracy", type=_bounded_rate)
    parser.add_argument("--max-dialect-gap", type=_bounded_rate)
    parser.add_argument("--max-spelling-delta", type=_nonnegative)
    args = parser.parse_args(argv)

    try:
        items = load_somali_evaluation_jsonl(
            args.corpus,
            require_gold=not args.allow_unadjudicated,
        )
        report = evaluate_somali_ranking(items)
    except (OSError, UnicodeError, ValueError) as exc:
        print(
            json.dumps(
                {"error": str(exc), "gate_failures": ["invalid_corpus"]},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 2
    failures: list[str] = []
    if args.min_pair_accuracy is not None and report.pairwise_accuracy < args.min_pair_accuracy:
        failures.append("pairwise_accuracy")
    if (
        args.min_macro_dialect_accuracy is not None
        and report.macro_dialect_accuracy < args.min_macro_dialect_accuracy
    ):
        failures.append("macro_dialect_accuracy")
    if (
        args.min_worst_dialect_accuracy is not None
        and report.worst_dialect_accuracy < args.min_worst_dialect_accuracy
    ):
        failures.append("worst_dialect_accuracy")
    if args.max_dialect_gap is not None and report.dialect_accuracy_gap > args.max_dialect_gap:
        failures.append("dialect_accuracy_gap")
    if (
        args.max_spelling_delta is not None
        and report.spelling_score_delta_mae is not None
        and report.spelling_score_delta_mae > args.max_spelling_delta
    ):
        failures.append("spelling_score_delta_mae")

    payload = report.public()
    payload["gate_failures"] = failures
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
