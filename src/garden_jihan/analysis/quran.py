from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
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

# Standard 6236-ayah numbering used by the Tanzil text release.
AYAH_COUNTS = [
    7, 286, 200, 176, 120, 165, 206, 75, 129, 109, 123, 111, 43, 52, 99,
    128, 111, 110, 98, 135, 112, 78, 118, 64, 77, 227, 93, 88, 69, 60, 34,
    30, 73, 54, 45, 83, 182, 88, 75, 85, 54, 53, 89, 59, 37, 35, 38, 29, 18,
    45, 60, 49, 62, 55, 78, 96, 29, 22, 24, 13, 14, 11, 11, 18, 12, 12, 30,
    52, 52, 44, 28, 28, 20, 56, 40, 31, 50, 40, 46, 42, 29, 19, 36, 25, 22,
    17, 19, 26, 30, 20, 15, 21, 11, 8, 8, 19, 5, 8, 8, 11, 11, 8, 3, 9, 5,
    4, 7, 3, 6, 3, 5, 4, 5, 6,
]

TANZIL_SOURCE = {
    "name": "Tanzil Project",
    "version": "1.1",
    "license": "Creative Commons Attribution 3.0",
    "url": "https://tanzil.net/",
    "updates": "https://tanzil.net/updates/",
    "notice": (
        "Tanzil Quran Text Copyright (C) 2007-2021 Tanzil Project. "
        "Verbatim Quran text must not be changed."
    ),
}

_ARABIC_MARKS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")


def normalize_arabic(text: str) -> str:
    """Normalize only a temporary matching copy; never use this for sacred display text."""
    text = unicodedata.normalize("NFKC", text)
    text = _ARABIC_MARKS.sub("", text)
    text = text.replace("ـ", "")
    text = re.sub(r"[إأآٱ]", "ا", text)
    text = text.replace("ى", "ي")
    text = re.sub(r"[^\u0621-\u063A\u0641-\u064A ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _similarity(query: str, target: str) -> float:
    if not query or not target:
        return 0.0
    if query == target:
        return 1.0
    ratio = SequenceMatcher(None, query, target).ratio()
    if query in target:
        ratio = max(ratio, 0.88 + 0.12 * (len(query) / max(len(target), 1)))
    elif target in query:
        ratio = max(ratio, 0.90 + 0.10 * (len(target) / max(len(query), 1)))

    query_tokens = set(query.split())
    target_tokens = set(target.split())
    if query_tokens and target_tokens:
        recall = len(query_tokens & target_tokens) / len(query_tokens)
        precision = len(query_tokens & target_tokens) / len(target_tokens)
        token_score = (recall * 0.6) + (precision * 0.4)
        ratio = max(ratio, token_score * 0.96)
    return min(1.0, ratio)


@dataclass(slots=True)
class QuranMatch:
    surah: int
    ayah: int
    confidence: float
    end_ayah: int | None = None
    text_display: str | None = None
    reading: str | None = None
    transmission: str | None = None

    def public(self) -> dict:
        data = asdict(self)
        data["status"] = (
            "high_confidence" if self.confidence >= 92 else "possible" if self.confidence >= 82 else "uncertain"
        )
        return data


class QuranReference:
    def __init__(self, path: Path):
        self.path = path
        self.records: list[dict] = []
        self.source: dict = {}
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                self.records = loaded
            else:
                self.records = loaded.get("verses", [])
                self.source = loaded.get("source", {})
        self._prepare_records()

    def _prepare_records(self) -> None:
        for record in self.records:
            if "text_match" not in record:
                record["text_match"] = normalize_arabic(str(record.get("text_display", "")))

    @property
    def available(self) -> bool:
        return bool(self.records)

    def match(
        self,
        transcript: str,
        threshold: float = 0.72,
        max_span_ayahs: int = 5,
    ) -> list[QuranMatch]:
        """Match ASR text against one or more adjacent ayahs without inferring Qira'at."""
        if not self.records:
            return []
        query = normalize_arabic(transcript)
        if not query:
            return []

        matches: list[QuranMatch] = []
        total = len(self.records)
        for index, record in enumerate(self.records):
            surah = int(record["surah"])
            span_texts: list[str] = []
            display_texts: list[str] = []
            last_ayah = int(record["ayah"])
            for offset in range(max(1, max_span_ayahs)):
                pos = index + offset
                if pos >= total:
                    break
                item = self.records[pos]
                if int(item["surah"]) != surah:
                    break
                span_texts.append(str(item.get("text_match", "")))
                display_texts.append(str(item.get("text_display", "")))
                last_ayah = int(item["ayah"])
                target = " ".join(part for part in span_texts if part).strip()
                confidence = _similarity(query, target)
                if confidence >= threshold:
                    matches.append(
                        QuranMatch(
                            surah=surah,
                            ayah=int(record["ayah"]),
                            end_ayah=last_ayah if last_ayah != int(record["ayah"]) else None,
                            confidence=round(confidence * 100, 2),
                            text_display=" ﴿ ".join(display_texts),
                        )
                    )

        matches.sort(key=lambda match: (match.confidence, -(match.end_ayah or match.ayah)), reverse=True)
        unique: list[QuranMatch] = []
        seen: set[tuple[int, int, int | None]] = set()
        for match in matches:
            key = (match.surah, match.ayah, match.end_ayah)
            if key in seen:
                continue
            seen.add(key)
            unique.append(match)
            if len(unique) >= 5:
                break
        return unique

    @classmethod
    def install_tanzil_text(cls, raw_text: str, destination: Path) -> QuranReference:
        """Install a user-supplied verbatim Tanzil Quran text file as an offline reference."""
        lines = [line.lstrip("\ufeff").strip() for line in raw_text.splitlines()]
        lines = [line for line in lines if line and not line.startswith("#")]
        records: list[dict] = []

        delimited = all(line.count("|") >= 2 for line in lines[: min(10, len(lines))]) if lines else False
        if delimited:
            for line in lines:
                surah_text, ayah_text, verse = line.split("|", 2)
                records.append(
                    {
                        "surah": int(surah_text),
                        "ayah": int(ayah_text),
                        "text_display": verse,
                        "text_match": normalize_arabic(verse),
                    }
                )
        else:
            if len(lines) != sum(AYAH_COUNTS):
                raise ValueError("Expected a complete 6236-ayah Tanzil text file")
            cursor = 0
            for surah, count in enumerate(AYAH_COUNTS, start=1):
                for ayah in range(1, count + 1):
                    verse = lines[cursor]
                    cursor += 1
                    records.append(
                        {
                            "surah": surah,
                            "ayah": ayah,
                            "text_display": verse,
                            "text_match": normalize_arabic(verse),
                        }
                    )

        if len(records) != sum(AYAH_COUNTS):
            raise ValueError("Quran reference must contain exactly 6236 ayahs")

        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {"source": TANZIL_SOURCE, "verses": records}
        destination.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return cls(destination)
