import json

import pytest

from garden_jihan.analysis.scoring import score_text_detailed
from garden_jihan.analysis.somali import (
    SomaliAnnotation,
    evaluate_somali_ranking,
    load_somali_evaluation_jsonl,
    main,
    preserve_dialect,
    somali_matching_tokens,
)
from garden_jihan.models import AnalysisMode


def _item(
    item_id: str,
    pair_id: str,
    preferred: bool,
    verbatim: str,
    dialect_group: str,
    *,
    normalized: str | None = None,
    code_switching: list[str] | None = None,
) -> dict:
    return {
        "id": item_id,
        "pair_id": pair_id,
        "preferred": preferred,
        "duration": 24,
        "verbatim": verbatim,
        "normalized": normalized,
        "dialect_group": dialect_group,
        "subvariety": None,
        "region": None,
        "speaker_id": f"speaker-{pair_id}",
        "genre": "synthetic-test-only",
        "audio_quality": "clean",
        "code_switching": code_switching or [],
        "source_id": "synthetic-unit-test",
        "license": "synthetic-test-data",
        "reviewers": ["reviewer-a", "reviewer-b"],
        "adjudicated": True,
    }


def _write_jsonl(path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records),
        encoding="utf-8",
    )


def test_preserve_dialect_keeps_verbatim_and_review_metadata():
    annotation = SomaliAnnotation(
        verbatim="hadal sidii loo yiri",
        normalized="hadal dib loo eegay",
        dialect_group="reviewer-group",
        subvariety="reviewer-subvariety",
        region="broad-region",
        code_switching=("Arabic",),
    )

    public = preserve_dialect(annotation)

    assert public["display"] == "hadal sidii loo yiri"
    assert public["normalized"] == "hadal dib loo eegay"
    assert public["dialect_group"] == "reviewer-group"
    assert public["subvariety"] == "reviewer-subvariety"
    assert public["code_switching"] == ["Arabic"]


def test_somali_matching_handles_apostrophe_and_hyphen_spelling_variants():
    assert somali_matching_tokens("Su’aal af-Carabi") == ["suaal", "afcarabi"]
    assert somali_matching_tokens("su'aal afcarabi") == ["suaal", "afcarabi"]

    curly, _, _ = score_text_detailed(
        "Bal ogow su’aal muhiim ah?",
        AnalysisMode.SOMALI,
        20,
    )
    plain, _, _ = score_text_detailed(
        "Bal ogow suaal muhiim ah?",
        AnalysisMode.SOMALI,
        20,
    )
    assert curly == plain


def test_gold_loader_preserves_text_and_requires_review(tmp_path):
    path = tmp_path / "somali.jsonl"
    records = [
        _item("a-best", "a", True, "preferred-a", "group-a"),
        _item("a-other", "a", False, "other-a", "group-a"),
    ]
    _write_jsonl(path, records)

    items = load_somali_evaluation_jsonl(path)

    assert items[0].verbatim == "preferred-a"
    assert items[0].dialect_group == "group-a"
    assert items[0].reviewers == ("reviewer-a", "reviewer-b")

    records[0]["reviewers"] = ["only-reviewer"]
    _write_jsonl(path, records)
    with pytest.raises(ValueError, match="at least two reviewers"):
        load_somali_evaluation_jsonl(path)
    assert load_somali_evaluation_jsonl(path, require_gold=False)

    records[0]["misspelled_field"] = "must not be ignored"
    _write_jsonl(path, records)
    with pytest.raises(ValueError, match="unknown annotation fields"):
        load_somali_evaluation_jsonl(path, require_gold=False)


def test_evaluator_reports_macro_worst_group_spelling_and_code_switching(tmp_path):
    path = tmp_path / "somali.jsonl"
    records = [
        _item(
            "a-best",
            "a",
            True,
            "a-best-raw",
            "group-a",
            normalized="a-best-normalized",
            code_switching=["Arabic"],
        ),
        _item("a-other", "a", False, "a-other", "group-a"),
        _item("b-best", "b", True, "b-best", "group-b"),
        _item("b-other", "b", False, "b-other", "group-b"),
    ]
    _write_jsonl(path, records)
    items = load_somali_evaluation_jsonl(path)
    scores = {
        "a-best-raw": 90,
        "a-best-normalized": 86,
        "a-other": 20,
        "b-best": 40,
        "b-other": 50,
    }

    report = evaluate_somali_ranking(items, scorer=lambda text, _duration: scores[text])

    assert report.item_count == 4
    assert report.pair_count == 2
    assert report.pairwise_accuracy == pytest.approx(0.5)
    assert report.macro_dialect_accuracy == pytest.approx(0.5)
    assert report.worst_dialect_accuracy == 0
    assert report.dialect_accuracy_gap == 1
    assert report.spelling_variant_count == 1
    assert report.spelling_score_delta_mae == 4
    assert report.code_switched_pair_count == 1
    assert report.code_switched_pair_accuracy == 1
    assert report.per_dialect["group-a"].accuracy == 1
    assert report.per_dialect["group-b"].accuracy == 0


def test_evaluator_rejects_cross_dialect_pairs(tmp_path):
    path = tmp_path / "somali.jsonl"
    _write_jsonl(
        path,
        [
            _item("best", "mixed", True, "best", "group-a"),
            _item("other", "mixed", False, "other", "group-b"),
        ],
    )

    with pytest.raises(ValueError, match="must not compare different dialect groups"):
        evaluate_somali_ranking(
            load_somali_evaluation_jsonl(path),
            scorer=lambda text, _duration: {"best": 10, "other": 5}[text],
        )


def test_evaluator_rejects_unfair_duration_pairs(tmp_path):
    path = tmp_path / "somali.jsonl"
    records = [
        _item("best", "duration", True, "best", "group"),
        _item("other", "duration", False, "other", "group"),
    ]
    records[1]["duration"] = 60
    _write_jsonl(path, records)

    with pytest.raises(ValueError, match="incomparable candidate durations"):
        evaluate_somali_ranking(
            load_somali_evaluation_jsonl(path),
            scorer=lambda text, _duration: {"best": 10, "other": 5}[text],
        )


def test_cli_thresholds_fail_closed(tmp_path, capsys):
    path = tmp_path / "somali.jsonl"
    _write_jsonl(
        path,
        [
            _item("preferred", "pair", True, "ordinary words", "group"),
            _item("other", "pair", False, "Bal ogow maxaa sabab muhiim ah?", "group"),
        ],
    )

    exit_code = main([str(path), "--min-pair-accuracy", "1"])
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert report["gate_failures"] == ["pairwise_accuracy"]
    assert "verbatim" not in report
