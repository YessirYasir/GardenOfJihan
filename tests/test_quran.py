import json

from garden_jihan.analysis.quran import CANONICAL_READINGS, QuranReference, normalize_arabic


def test_all_ten_readers_are_modeled():
    assert len(CANONICAL_READINGS) == 10
    assert "Hafs" in CANONICAL_READINGS["Asim"]
    assert "Warsh" in CANONICAL_READINGS["Nafi"]


def test_arabic_normalization_removes_marks():
    assert normalize_arabic("الْحَمْدُ لِلَّهِ") == "الحمد لله"


def test_reference_match_uses_data_not_llm_memory(tmp_path):
    data = [{"surah": 1, "ayah": 2, "text_display": "الحمد لله رب العالمين", "reading": "Hafs", "transmission": "Hafs an Asim"}]
    path = tmp_path / "quran.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    ref = QuranReference(path)
    matches = ref.match("الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ")
    assert matches
    assert matches[0].surah == 1
    assert matches[0].ayah == 2
    assert matches[0].confidence > 90


def test_missing_reference_fails_safe(tmp_path):
    ref = QuranReference(tmp_path / "missing.json")
    assert not ref.available
    assert ref.match("الحمد لله") == []
