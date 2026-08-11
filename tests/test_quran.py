import json

from garden_jihan.analysis.quran import (
    AYAH_COUNTS,
    CANONICAL_READINGS,
    QuranReference,
    normalize_arabic,
)


def test_all_ten_readers_are_modeled():
    assert len(CANONICAL_READINGS) == 10
    assert "Hafs" in CANONICAL_READINGS["Asim"]
    assert "Warsh" in CANONICAL_READINGS["Nafi"]


def test_arabic_normalization_removes_marks():
    assert normalize_arabic("الْحَمْدُ لِلَّهِ") == "الحمد لله"


def test_reference_match_uses_data_not_llm_memory(tmp_path):
    data = [
        {
            "surah": 1,
            "ayah": 2,
            "text_display": "الحمد لله رب العالمين",
        }
    ]
    path = tmp_path / "quran.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    ref = QuranReference(path)
    matches = ref.match("الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ")
    assert matches
    assert matches[0].surah == 1
    assert matches[0].ayah == 2
    assert matches[0].confidence > 90
    assert matches[0].reading is None
    assert matches[0].transmission is None


def test_reference_can_match_adjacent_ayah_span(tmp_path):
    data = [
        {"surah": 1, "ayah": 1, "text_display": "بسم الله الرحمن الرحيم"},
        {"surah": 1, "ayah": 2, "text_display": "الحمد لله رب العالمين"},
        {"surah": 1, "ayah": 3, "text_display": "الرحمن الرحيم"},
    ]
    path = tmp_path / "quran.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    ref = QuranReference(path)
    matches = ref.match("الحمد لله رب العالمين الرحمن الرحيم", threshold=0.8)
    assert matches
    assert matches[0].surah == 1
    assert matches[0].ayah == 2
    assert matches[0].end_ayah == 3
    assert matches[0].public()["status"] == "high_confidence"


def test_tanzil_delimited_import_builds_complete_offline_reference(tmp_path):
    lines = []
    for surah, count in enumerate(AYAH_COUNTS, start=1):
        for ayah in range(1, count + 1):
            lines.append(f"{surah}|{ayah}|نص السورة {surah} الاية {ayah}")
    destination = tmp_path / "reference" / "quran_reference.json"
    ref = QuranReference.install_tanzil_text("\n".join(lines), destination)
    assert ref.available
    assert len(ref.records) == 6236
    assert ref.source["name"] == "Tanzil Project"
    assert ref.records[0]["surah"] == 1
    assert ref.records[-1]["surah"] == 114
    assert ref.records[-1]["ayah"] == 6


def test_tanzil_import_rejects_partial_reference(tmp_path):
    destination = tmp_path / "quran_reference.json"
    try:
        QuranReference.install_tanzil_text("1|1|بسم الله الرحمن الرحيم", destination)
    except ValueError as exc:
        assert "6236" in str(exc)
    else:
        raise AssertionError("partial Quran reference should not be accepted")


def test_missing_reference_fails_safe(tmp_path):
    ref = QuranReference(tmp_path / "missing.json")
    assert not ref.available
    assert ref.match("الحمد لله") == []
