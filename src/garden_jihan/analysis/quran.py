from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

CANONICAL_READINGS = {
    "Nafi": ["Warsh", "Qalun"],
    "Ibn Kathir": ["Al-Bazzi", "Qunbul"],
    "Abu Amr": ["Ad-Duri", "As-Susi"],
    "Ibn Amir": ["Hisham", "Ibn Dhakwan"],
    "Asim": ["Hafs", "Shubah"],
    "Hamzah": ["Khalaf", "Khallad"],
    "Al-Kisai": ["Abu al-Harith", "Ad-Duri"],
    "Abu Jafar": ["Ibn Wardan", "Ibn Jammaz"],
    "Yaqub": ["Ruways", "Rawh"],
    "Khalaf": ["Ishaq", "Idris"],
}

_ARABIC_MARKS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")


def normalize_arabic(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _ARABIC_MARKS.sub("", text)
    text = text.replace("ـ", "")
    text = re.sub(r"[إأآٱ]", "ا", text)
    text = text.replace("ى", "ي")
    text = re.sub(r"[^\u0621-\u063A\u0641-\u064A ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass(slots=True)
class QuranMatch:
    surah: int
    ayah: int
    confidence: float
    reading: str | None = None
    transmission: str | None = None


class QuranReference:
    def __init__(self, path: Path):
        self.path = path
        self.records: list[dict] = []
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.records = loaded if isinstance(loaded, list) else loaded.get("verses", [])

    @property
    def available(self) -> bool:
        return bool(self.records)

    def match(self, transcript: str, threshold: float = 0.72) -> list[QuranMatch]:
        if not self.records:
            return []
        query = normalize_arabic(transcript)
        if not query:
            return []
        matches: list[QuranMatch] = []
        for record in self.records:
            target = record.get("text_match") or normalize_arabic(str(record.get("text_display", "")))
            confidence = SequenceMatcher(None, query, target).ratio()
            if confidence >= threshold:
                matches.append(
                    QuranMatch(
                        surah=int(record["surah"]),
                        ayah=int(record["ayah"]),
                        confidence=round(confidence * 100, 2),
                        reading=record.get("reading"),
                        transmission=record.get("transmission"),
                    )
                )
        return sorted(matches, key=lambda m: m.confidence, reverse=True)[:5]
