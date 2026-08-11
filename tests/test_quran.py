import json

import pytest

from garden_jihan.analysis import quran as quran_module
from garden_jihan.analysis.quran import (
    AYAH_COUNTS,
    CANONICAL_READINGS,
    TANZIL_NOTICE,
    TANZIL_TRUSTED_CANONICAL_SHA256,
    QuranReference,
    canonical_tanzil_sha256,
    normalize_arabic,
)
from garden_jihan.config import Settings
from garden_jihan.jobs import JobManager
from garden_jihan.models import AnalysisMode, ClipCandidate

ARABIC_ID_ALPHABET = "ابتثجحخدذرزسشصضطظعغفقكلمنهوي"


def _arabic_id(value: int) -> str:
    result = ""
    while value:
        value, remainder = divmod(value - 1, len(ARABIC_ID_ALPHABET))
        result = ARABIC_ID_ALPHABET[remainder] + result
    return result or ARABIC_ID_ALPHABET[0]


def _complete_numbered_text(overrides: dict[tuple[int, int], str] | None = None) -> str:
    overrides = overrides or {}
    lines = []
    index = 0
    for surah, count in enumerate(AYAH_COUNTS, start=1):
        for ayah in range(1, count + 1):
            index += 1
            verse = overrides.get((surah, ayah), f"نص مرجعي فريد {_arabic_id(index)}")
            lines.append(f"{surah}|{ayah}|{verse}")
    lines.extend(["", "# Tanzil test fixture", "# License footer is ignored by the canonical hash"])
    return "\n".join(lines)


@pytest.fixture
def trusted_reference(tmp_path, monkeypatch):
    raw = _complete_numbered_text(
        {
            (1, 1): "بسم الله الرحمن الرحيم",
            (1, 2): "الحمد لله رب العالمين",
            (1, 3): "الرحمن الرحيم",
            # A repeated short passage is deliberately present so ambiguity is testable.
            (2, 1): "بسم الله الرحمن الرحيم",
            (108, 1): "بسم الله الرحمن الرحيم إنا أعطيناك الكوثر",
        }
    )
    checksum = canonical_tanzil_sha256(raw)
    monkeypatch.setattr(
        quran_module,
        "TANZIL_TRUSTED_CANONICAL_SHA256",
        frozenset({checksum}),
    )
    path = tmp_path / "reference" / "quran_reference.json"
    reference = QuranReference.install_tanzil_text(raw, path)
    return reference, path, raw


def test_all_ten_readers_are_registry_only():
    assert len(CANONICAL_READINGS) == 10
    assert "Hafs" in CANONICAL_READINGS["Asim"]
    assert "Warsh" in CANONICAL_READINGS["Nafi"]


def test_arabic_normalization_removes_marks():
    assert normalize_arabic("الْحَمْدُ لِلَّهِ") == "الحمد لله"


def test_reviewed_tanzil_profile_has_pinned_hash():
    assert TANZIL_TRUSTED_CANONICAL_SHA256 == {
        "d25401b9235ea0c77a2511b1edc5b5d28df1b3bcd0259d6657ec6e303dd8eee9"
    }


def test_complete_but_unreviewed_text_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="does not match the reviewed Tanzil"):
        QuranReference.install_tanzil_text(
            _complete_numbered_text(),
            tmp_path / "quran_reference.json",
        )


def test_numbered_import_rejects_wrong_coordinate_before_trust_check(tmp_path):
    lines = _complete_numbered_text().splitlines()
    lines[1] = lines[1].replace("1|2|", "1|3|", 1)
    with pytest.raises(ValueError, match=r"expected 1\|2"):
        QuranReference.install_tanzil_text(
            "\n".join(lines),
            tmp_path / "quran_reference.json",
        )


def test_reference_match_uses_verified_data_and_never_sets_qiraat(trusted_reference):
    reference, _, _ = trusted_reference
    decision = reference.identify("الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ")
    assert decision.status == "verified"
    assert decision.match is not None
    assert decision.match.surah == 1
    assert decision.match.ayah == 2
    assert decision.match.confidence > 95
    public = decision.public(reference.source)
    assert public["reading"] is None
    assert public["transmission"] is None
    assert public["qiraat_status"] == "not_assessed"


def test_reference_aligns_words_across_adjacent_ayahs(trusted_reference):
    reference, _, _ = trusted_reference
    decision = reference.identify("الحمد لله رب العالمين الرحمن الرحيم")
    assert decision.status == "verified"
    assert decision.match is not None
    assert decision.match.surah == 1
    assert decision.match.ayah == 2
    assert decision.match.end_ayah == 3
    assert decision.match.word_coverage == pytest.approx(1.0)
    assert decision.match.query_coverage == pytest.approx(1.0)
    assert decision.match.matched_words == decision.match.total_words
    assert [verse["text_display"] for verse in decision.match.verses] == [
        "الحمد لله رب العالمين",
        "الرحمن الرحيم",
    ]


def test_tanzil_opening_basmala_is_optional_for_locating_words(trusted_reference):
    reference, _, _ = trusted_reference
    decision = reference.identify("إنا أعطيناك الكوثر")
    assert decision.status == "verified"
    assert decision.match is not None
    assert (decision.match.surah, decision.match.ayah) == (108, 1)
    assert decision.match.word_coverage == pytest.approx(1.0)
    assert decision.match.query_coverage == pytest.approx(1.0)
    assert decision.match.matched_words == decision.match.total_words == 3
    assert [word.optional for word in decision.match.word_alignment[:4]] == [True] * 4
    assert decision.match.verses[0]["text_display"].startswith("بسم الله الرحمن الرحيم")


def test_repeated_short_passage_never_guesses_location(trusted_reference):
    reference, _, _ = trusted_reference
    decision = reference.identify("بسم الله الرحمن الرحيم")
    public = decision.public(reference.source)
    assert decision.status == "uncertain"
    assert decision.alternatives > 1
    assert "surah" not in public
    assert "ayah" not in public
    assert "not enough to identify a Surah/Ayah" in decision.message


def test_partial_ayah_does_not_expose_location(trusted_reference):
    reference, _, _ = trusted_reference
    decision = reference.identify("الحمد لله")
    public = decision.public(reference.source)
    assert decision.status in {"possible", "uncertain"}
    assert "surah" not in public
    assert "ayah" not in public


def test_job_candidates_only_receive_verified_locations(trusted_reference):
    reference, _, _ = trusted_reference
    manager = JobManager(Settings(app_data=reference.path.parents[1]))
    candidates = [
        ClipCandidate(
            id="verified",
            start=0,
            end=12,
            score=90,
            title="Candidate",
            reasons=["Strong moment"],
            transcript="إنا أعطيناك الكوثر",
            mode=AnalysisMode.QURAN,
        ),
        ClipCandidate(
            id="ambiguous",
            start=20,
            end=30,
            score=88,
            title="Candidate",
            reasons=["Strong moment"],
            transcript="بسم الله الرحمن الرحيم",
            mode=AnalysisMode.QURAN,
        ),
    ]
    try:
        manager._attach_quran_matches(candidates)
    finally:
        manager._pool.shutdown(wait=True)

    assert candidates[0].title == "Qur'an 108:1"
    assert candidates[0].quran_match["status"] == "verified"
    assert candidates[0].quran_match["surah"] == 108
    assert candidates[0].quran_match["reading"] is None
    assert candidates[1].title == "Qur'an passage — review required"
    assert candidates[1].quran_match["status"] == "uncertain"
    assert "surah" not in candidates[1].quran_match
    assert "ayah" not in candidates[1].quran_match


def test_installed_package_preserves_notice_and_integrity(trusted_reference):
    reference, path, _ = trusted_reference
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert reference.available
    assert len(reference.records) == 6236
    assert payload["source"]["notice"] == TANZIL_NOTICE
    assert payload["integrity"]["verified"] is True
    assert payload["integrity"]["canonical_sha256"] == canonical_tanzil_sha256(
        "\n".join(
            f"{item['surah']}|{item['ayah']}|{item['text_display']}"
            for item in payload["verses"]
        )
    )


def test_modified_sacred_text_is_blocked_on_next_load(trusted_reference):
    _, path, _ = trusted_reference
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["verses"][1]["text_display"] += " ا"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    corrupted = QuranReference(path)
    assert corrupted.installed
    assert not corrupted.available
    assert corrupted.match("الحمد لله رب العالمين") == []
    assert corrupted.identify("الحمد لله رب العالمين").status == "reference_invalid"


def test_stored_normalized_copy_is_rebuilt_not_trusted(trusted_reference):
    _, path, _ = trusted_reference
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["verses"][1]["text_match"] = "نص محرف"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    reloaded = QuranReference(path)
    assert reloaded.available
    assert reloaded.records[1]["text_match"] == "الحمد لله رب العالمين"


def test_missing_reference_fails_safe(tmp_path):
    reference = QuranReference(tmp_path / "missing.json")
    assert not reference.installed
    assert not reference.available
    assert reference.match("الحمد لله") == []
    assert reference.identify("الحمد لله").status == "reference_unavailable"
