from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

# This registry is documentation for the future acoustic research layer. Garden of Jihan does
# not currently classify any Qira'ah, reader, or transmission.
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
    7,
    286,
    200,
    176,
    120,
    165,
    206,
    75,
    129,
    109,
    123,
    111,
    43,
    52,
    99,
    128,
    111,
    110,
    98,
    135,
    112,
    78,
    118,
    64,
    77,
    227,
    93,
    88,
    69,
    60,
    34,
    30,
    73,
    54,
    45,
    83,
    182,
    88,
    75,
    85,
    54,
    53,
    89,
    59,
    37,
    35,
    38,
    29,
    18,
    45,
    60,
    49,
    62,
    55,
    78,
    96,
    29,
    22,
    24,
    13,
    14,
    11,
    11,
    18,
    12,
    12,
    30,
    52,
    52,
    44,
    28,
    28,
    20,
    56,
    40,
    31,
    50,
    40,
    46,
    42,
    29,
    19,
    36,
    25,
    22,
    17,
    19,
    26,
    30,
    20,
    15,
    21,
    11,
    8,
    8,
    19,
    5,
    8,
    8,
    11,
    11,
    8,
    3,
    9,
    5,
    4,
    7,
    3,
    6,
    3,
    5,
    4,
    5,
    6,
]
TOTAL_AYAHS = sum(AYAH_COUNTS)

TANZIL_PROFILE = "simple-1.1-default-with-ayah-numbers"
TANZIL_TRUSTED_CANONICAL_SHA256 = frozenset(
    {
        # Official Tanzil 1.1 Simple text, default marks, Text (with aya numbers).
        # Canonical form is the 6236 non-comment lines joined with LF and no final LF.
        "d25401b9235ea0c77a2511b1edc5b5d28df1b3bcd0259d6657ec6e303dd8eee9",
    }
)
TANZIL_NOTICE = """PLEASE DO NOT REMOVE OR CHANGE THIS COPYRIGHT BLOCK

Tanzil Quran Text (Simple, Version 1.1)
Copyright (C) 2007-2026 Tanzil Project
License: Creative Commons Attribution 3.0

This copy of the Quran text is carefully produced, highly
verified and continuously monitored by a group of specialists
at Tanzil Project.

TERMS OF USE:

- Permission is granted to copy and distribute verbatim copies
  of this text, but CHANGING IT IS NOT ALLOWED.

- This Quran text can be used in any website or application,
  provided that its source (Tanzil Project) is clearly indicated,
  and a link is made to tanzil.net to enable users to keep
  track of changes.

- This copyright notice shall be included in all verbatim copies
  of the text, and shall be reproduced appropriately in all files
  derived from or containing substantial portion of this text.

Please check updates at: http://tanzil.net/updates/"""
TANZIL_SOURCE = {
    "name": "Tanzil Project",
    "version": "1.1",
    "profile": TANZIL_PROFILE,
    "license": "Creative Commons Attribution 3.0",
    "license_url": "https://tanzil.net/docs/Text_License",
    "url": "https://tanzil.net/",
    "download": "https://tanzil.net/download/",
    "updates": "https://tanzil.net/updates/",
    "notice": TANZIL_NOTICE,
}

VERIFIED_CONFIDENCE = 92.0
POSSIBLE_CONFIDENCE = 82.0
MIN_VERIFIED_MARGIN = 5.0
MIN_VERIFIED_COVERAGE = 0.78

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


_BASMALA_MATCH_TEXT = normalize_arabic("\u0628\u0633\u0645 \u0627\u0644\u0644\u0647 \u0627\u0644\u0631\u062d\u0645\u0646 \u0627\u0644\u0631\u062d\u064a\u0645")


def _is_non_locating_opening_formula(text: str) -> bool:
    """Treat a basmala-only transcript as non-locating recitation context."""
    normalized = normalize_arabic(text)
    return bool(normalized) and normalized in _BASMALA_MATCH_TEXT


def _content_lines(raw_text: str) -> list[str]:
    lines = raw_text.splitlines()
    if lines:
        lines[0] = lines[0].lstrip("\ufeff")
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def canonical_tanzil_sha256(raw_text: str) -> str:
    """Hash the exact Quran content while ignoring footer and platform line endings."""
    canonical = "\n".join(_content_lines(raw_text))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _expected_coordinates():
    for surah, count in enumerate(AYAH_COUNTS, start=1):
        for ayah in range(1, count + 1):
            yield surah, ayah


def _parse_numbered_tanzil(raw_text: str) -> list[dict]:
    lines = _content_lines(raw_text)
    if len(lines) != TOTAL_AYAHS:
        raise ValueError(f"Expected the complete {TOTAL_AYAHS}-ayah Tanzil text file")

    records: list[dict] = []
    for line_number, (line, expected) in enumerate(
        zip(lines, _expected_coordinates(), strict=True),
        start=1,
    ):
        if line.count("|") < 2:
            raise ValueError(
                "Choose Tanzil's Text (with aya numbers) format; every line must be surah|ayah|text"
            )
        surah_text, ayah_text, verse = line.split("|", 2)
        try:
            coordinates = (int(surah_text), int(ayah_text))
        except ValueError as exc:
            raise ValueError(f"Invalid Surah/Ayah coordinate on line {line_number}") from exc
        if coordinates != expected:
            raise ValueError(
                f"Unexpected coordinate on line {line_number}; expected {expected[0]}|{expected[1]}"
            )
        if not verse or not normalize_arabic(verse):
            raise ValueError(f"Missing Arabic ayah text on line {line_number}")
        records.append(
            {
                "surah": coordinates[0],
                "ayah": coordinates[1],
                "text_display": verse,
                "text_match": normalize_arabic(verse),
            }
        )
    return records


def _records_canonical_sha256(records: list[dict]) -> str:
    lines = [
        f"{record['surah']}|{record['ayah']}|{record['text_display']}" for record in records
    ]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


@dataclass(slots=True)
class QuranWordAlignment:
    reference_word: str
    ayah: int
    matched: bool
    optional: bool = False
    similarity: float = 0.0
    query_word: str | None = None

    def public(self) -> dict:
        data = asdict(self)
        data["similarity"] = round(self.similarity * 100, 1)
        return data


@dataclass(slots=True)
class QuranMatch:
    surah: int
    ayah: int
    confidence: float
    end_ayah: int | None = None
    verses: list[dict] = field(default_factory=list)
    word_alignment: list[QuranWordAlignment] = field(default_factory=list)
    matched_words: int = 0
    total_words: int = 0
    word_coverage: float = 0.0
    query_coverage: float = 0.0
    starts_mid_ayah: bool = False
    ends_mid_ayah: bool = False
    reading: str | None = None
    transmission: str | None = None

    def public(self, *, include_location: bool = True) -> dict:
        data = {
            "confidence": self.confidence,
            "matched_words": self.matched_words,
            "total_words": self.total_words,
            "word_coverage": round(self.word_coverage * 100, 1),
            "query_coverage": round(self.query_coverage * 100, 1),
            "starts_mid_ayah": self.starts_mid_ayah,
            "ends_mid_ayah": self.ends_mid_ayah,
            "reading": None,
            "transmission": None,
        }
        if include_location:
            data.update(
                {
                    "surah": self.surah,
                    "ayah": self.ayah,
                    "end_ayah": self.end_ayah,
                    "verses": self.verses,
                    "word_alignment": [word.public() for word in self.word_alignment],
                }
            )
        return data


@dataclass(slots=True)
class QuranDecision:
    status: str
    message: str
    match: QuranMatch | None = None
    margin: float | None = None
    alternatives: int = 0

    def public(self, source: dict) -> dict:
        data = {
            "status": self.status,
            "message": self.message,
            "source": source.get("name") if source else None,
            "source_version": source.get("version") if source else None,
            "qiraat_status": "not_assessed",
            "qiraat_message": (
                "Qira’at is not assessed. Text matching cannot identify a reader or transmission."
            ),
        }
        if self.match:
            data.update(self.match.public(include_location=self.status == "verified"))
        if self.margin is not None:
            data["confidence_margin"] = round(self.margin, 2)
        if self.alternatives:
            data["plausible_locations"] = self.alternatives
        return data


@dataclass(slots=True)
class _ReferenceWord:
    display: str
    normalized: str
    ayah: int


def _word_similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    ratio = SequenceMatcher(None, left, right).ratio()
    return ratio if ratio >= 0.72 else 0.0


def _align_words(
    query_text: str,
    reference_words: list[_ReferenceWord],
) -> tuple[list[QuranWordAlignment], float, float, bool, bool]:
    query_display = query_text.split()
    query_words = [normalize_arabic(word) for word in query_display]
    query_pairs = [pair for pair in zip(query_display, query_words, strict=True) if pair[1]]
    query_display = [pair[0] for pair in query_pairs]
    query_words = [pair[1] for pair in query_pairs]
    target_words = [word.normalized for word in reference_words]
    query_count, target_count = len(query_words), len(target_words)
    if not query_count or not target_count:
        empty = [
            QuranWordAlignment(reference_word=word.display, ayah=word.ayah, matched=False)
            for word in reference_words
        ]
        return empty, 0.0, 0.0, False, False

    costs = [[0.0] * (target_count + 1) for _ in range(query_count + 1)]
    parents = [[""] * (target_count + 1) for _ in range(query_count + 1)]
    for i in range(1, query_count + 1):
        costs[i][0] = float(i)
        parents[i][0] = "up"
    for j in range(1, target_count + 1):
        costs[0][j] = float(j)
        parents[0][j] = "left"

    for i in range(1, query_count + 1):
        for j in range(1, target_count + 1):
            similarity = _word_similarity(query_words[i - 1], target_words[j - 1])
            diagonal = costs[i - 1][j - 1] + (1.0 - similarity if similarity else 1.1)
            choices = ((diagonal, "diag"), (costs[i - 1][j] + 1.0, "up"), (costs[i][j - 1] + 1.0, "left"))
            costs[i][j], parents[i][j] = min(choices, key=lambda item: item[0])

    aligned: dict[int, tuple[int, float]] = {}
    i, j = query_count, target_count
    while i or j:
        direction = parents[i][j]
        if direction == "diag":
            similarity = _word_similarity(query_words[i - 1], target_words[j - 1])
            if similarity:
                aligned[j - 1] = (i - 1, similarity)
            i -= 1
            j -= 1
        elif direction == "up":
            i -= 1
        else:
            j -= 1

    public_alignment: list[QuranWordAlignment] = []
    strength = 0.0
    for index, word in enumerate(reference_words):
        query_match = aligned.get(index)
        if query_match:
            query_index, similarity = query_match
            strength += similarity
            public_alignment.append(
                QuranWordAlignment(
                    reference_word=word.display,
                    ayah=word.ayah,
                    matched=True,
                    similarity=similarity,
                    query_word=query_display[query_index],
                )
            )
        else:
            public_alignment.append(
                QuranWordAlignment(reference_word=word.display, ayah=word.ayah, matched=False)
            )

    reference_coverage = strength / target_count
    query_coverage = strength / query_count
    matched_indices = sorted(aligned)
    starts_mid_ayah = bool(matched_indices) and matched_indices[0] >= 2
    ends_mid_ayah = bool(matched_indices) and target_count - matched_indices[-1] - 1 >= 2
    return (
        public_alignment,
        reference_coverage,
        query_coverage,
        starts_mid_ayah,
        ends_mid_ayah,
    )


def _reference_words(records: list[dict]) -> list[_ReferenceWord]:
    words: list[_ReferenceWord] = []
    for record in records:
        for display in str(record["text_display"]).split():
            normalized = normalize_arabic(display)
            if normalized:
                words.append(
                    _ReferenceWord(
                        display=display,
                        normalized=normalized,
                        ayah=int(record["ayah"]),
                    )
                )
    return words


def _optional_opening_prefix_count(records: list[dict], query: str) -> int:
    """Return the known Tanzil basmala prefix length when it is absent from the query."""
    if not records:
        return 0
    first = records[0]
    if int(first["ayah"]) != 1 or int(first["surah"]) in {1, 9}:
        return 0
    if normalize_arabic(query).startswith(_BASMALA_MATCH_TEXT):
        return 0
    first_words = str(first["text_match"]).split()
    basmala_words = _BASMALA_MATCH_TEXT.split()
    return len(basmala_words) if first_words[: len(basmala_words)] == basmala_words else 0


def _score_span(query: str, records: list[dict]) -> QuranMatch:
    reference_words = _reference_words(records)
    optional_prefix_count = _optional_opening_prefix_count(records, query)
    scored_words = reference_words[optional_prefix_count:]
    target = " ".join(word.normalized for word in scored_words)
    alignment, word_coverage, query_coverage, starts_mid, ends_mid = _align_words(
        query,
        scored_words,
    )
    if optional_prefix_count:
        alignment = [
            QuranWordAlignment(
                reference_word=word.display,
                ayah=word.ayah,
                matched=False,
                optional=True,
            )
            for word in reference_words[:optional_prefix_count]
        ] + alignment
    char_ratio = SequenceMatcher(None, normalize_arabic(query), target).ratio()
    query_count = len(normalize_arabic(query).split())
    target_count = len(scored_words)
    length_balance = min(query_count, target_count) / max(query_count, target_count, 1)
    confidence = (
        char_ratio * 0.32
        + word_coverage * 0.28
        + query_coverage * 0.28
        + length_balance * 0.12
    )
    matched_words = sum(1 for word in alignment if word.matched and not word.optional)
    return QuranMatch(
        surah=int(records[0]["surah"]),
        ayah=int(records[0]["ayah"]),
        end_ayah=int(records[-1]["ayah"]) if len(records) > 1 else None,
        confidence=round(confidence * 100, 2),
        verses=[
            {
                "surah": int(record["surah"]),
                "ayah": int(record["ayah"]),
                "text_display": str(record["text_display"]),
            }
            for record in records
        ],
        word_alignment=alignment,
        matched_words=matched_words,
        total_words=len(scored_words),
        word_coverage=word_coverage,
        query_coverage=query_coverage,
        starts_mid_ayah=starts_mid,
        ends_mid_ayah=ends_mid,
    )


class QuranReference:
    def __init__(self, path: Path):
        self.path = path
        self.records: list[dict] = []
        self.source: dict = {}
        self.integrity: dict = {}
        self.validation_error: str | None = None
        self.installed = path.exists()
        self._token_index: dict[str, set[int]] = {}
        if not self.installed:
            return
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self._load_verified_package(loaded)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
            self.validation_error = f"Installed reference failed integrity validation: {exc}"
            self.records = []
            self.source = {}
            self.integrity = {}

    def _load_verified_package(self, loaded) -> None:
        if not isinstance(loaded, dict) or loaded.get("schema_version") != 1:
            raise ValueError("unsupported or unverified package format")
        records = loaded.get("verses")
        if not isinstance(records, list) or len(records) != TOTAL_AYAHS:
            raise ValueError(f"expected exactly {TOTAL_AYAHS:,} ayahs")

        prepared: list[dict] = []
        for line_number, (record, expected) in enumerate(
            zip(records, _expected_coordinates(), strict=True),
            start=1,
        ):
            if not isinstance(record, dict):
                raise ValueError(f"invalid record on line {line_number}")
            coordinates = (int(record["surah"]), int(record["ayah"]))
            if coordinates != expected:
                raise ValueError(f"unexpected coordinate at record {line_number}")
            display = record.get("text_display")
            if not isinstance(display, str) or not display or not normalize_arabic(display):
                raise ValueError(f"invalid Arabic display text at record {line_number}")
            prepared.append(
                {
                    "surah": coordinates[0],
                    "ayah": coordinates[1],
                    "text_display": display,
                    # Never trust a stored derived matching representation.
                    "text_match": normalize_arabic(display),
                }
            )

        checksum = _records_canonical_sha256(prepared)
        integrity = loaded.get("integrity")
        source = loaded.get("source")
        if checksum not in TANZIL_TRUSTED_CANONICAL_SHA256:
            raise ValueError("Quran text checksum is not on the reviewed trust list")
        if not isinstance(integrity, dict) or integrity.get("canonical_sha256") != checksum:
            raise ValueError("stored checksum does not match the Quran text")
        if not isinstance(source, dict):
            raise ValueError("source attribution is missing")
        if source.get("name") != TANZIL_SOURCE["name"] or source.get("version") != "1.1":
            raise ValueError("source attribution is not the reviewed Tanzil 1.1 release")
        if source.get("profile") != TANZIL_PROFILE or source.get("notice") != TANZIL_NOTICE:
            raise ValueError("source profile or required license notice is missing")

        self.records = prepared
        self.source = source
        self.integrity = {
            "verified": True,
            "canonical_sha256": checksum,
            "profile": TANZIL_PROFILE,
            "verse_count": TOTAL_AYAHS,
        }
        self._prepare_index()

    def _prepare_index(self) -> None:
        for index, record in enumerate(self.records):
            for token in set(str(record["text_match"]).split()):
                self._token_index.setdefault(token, set()).add(index)

    @property
    def available(self) -> bool:
        return bool(self.records) and self.integrity.get("verified") is True

    def match(
        self,
        transcript: str,
        threshold: float = 0.60,
        max_span_ayahs: int = 12,
    ) -> list[QuranMatch]:
        """Align ASR text to adjacent ayahs without inferring Qira'at."""
        if not self.available:
            return []
        query = normalize_arabic(transcript)
        query_tokens = query.split()
        if not query_tokens:
            return []

        hit_indices: set[int] = set()
        for token in set(query_tokens):
            hit_indices.update(self._token_index.get(token, ()))
        if not hit_indices:
            return []

        starts: set[int] = set()
        max_span = max(1, min(max_span_ayahs, 20))
        for hit in hit_indices:
            hit_surah = int(self.records[hit]["surah"])
            for distance in range(max_span):
                start = hit - distance
                if start < 0 or int(self.records[start]["surah"]) != hit_surah:
                    break
                starts.add(start)

        rough: list[tuple[float, list[dict]]] = []
        for start in starts:
            span: list[dict] = []
            surah = int(self.records[start]["surah"])
            for offset in range(max_span):
                pos = start + offset
                if pos >= len(self.records) or int(self.records[pos]["surah"]) != surah:
                    break
                span.append(self.records[pos])
                target = " ".join(str(record["text_match"]) for record in span)
                target_tokens = target.split()
                char_ratio = SequenceMatcher(None, query, target).ratio()
                token_ratio = SequenceMatcher(None, query_tokens, target_tokens).ratio()
                length_balance = min(len(query_tokens), len(target_tokens)) / max(
                    len(query_tokens),
                    len(target_tokens),
                    1,
                )
                rough_score = char_ratio * 0.55 + token_ratio * 0.35 + length_balance * 0.10
                rough.append((rough_score, list(span)))

        rough.sort(key=lambda item: item[0], reverse=True)
        matches = [_score_span(transcript, records) for _, records in rough[:30]]
        matches = [match for match in matches if match.confidence >= threshold * 100]
        matches.sort(
            key=lambda match: (match.confidence, match.word_coverage, match.query_coverage),
            reverse=True,
        )

        unique: list[QuranMatch] = []
        seen: set[tuple[int, int, int | None]] = set()
        for match in matches:
            key = (match.surah, match.ayah, match.end_ayah)
            if key in seen:
                continue
            seen.add(key)
            unique.append(match)
            if len(unique) >= 8:
                break
        return unique

    def identify(self, transcript: str) -> QuranDecision:
        if not self.installed:
            return QuranDecision(
                status="reference_unavailable",
                message=(
                    "Install the reviewed Tanzil reference before Garden of Jihan can identify "
                    "Surah or Ayah."
                ),
            )
        if not self.available:
            return QuranDecision(
                status="reference_invalid",
                message=(
                    "The installed Quran reference did not pass integrity checks. Reinstall the "
                    "reviewed Tanzil profile; no Surah/Ayah will be shown."
                ),
            )

        if _is_non_locating_opening_formula(transcript):
            return QuranDecision(
                status="uncertain",
                alternatives=2,
                message=(
                    "The basmala can introduce multiple recitation locations and is not enough "
                    "to identify a Surah/Ayah. No location is shown."
                ),
            )

        matches = self.match(transcript)
        if not matches:
            return QuranDecision(
                status="uncertain",
                message="No sufficiently supported Quran reference match. Review manually.",
            )

        best = matches[0]
        runner_up = matches[1] if len(matches) > 1 else None
        margin = best.confidence - runner_up.confidence if runner_up else best.confidence
        plausible = sum(1 for match in matches if best.confidence - match.confidence < 3.0)
        coverage_ok = (
            best.word_coverage >= MIN_VERIFIED_COVERAGE
            and best.query_coverage >= MIN_VERIFIED_COVERAGE
        )

        if (
            best.confidence >= VERIFIED_CONFIDENCE
            and coverage_ok
            and margin >= MIN_VERIFIED_MARGIN
        ):
            warning = ""
            if best.starts_mid_ayah or best.ends_mid_ayah:
                warning = " The candidate may begin or end inside an ayah; review its boundaries."
            return QuranDecision(
                status="verified",
                match=best,
                margin=margin,
                alternatives=plausible,
                message=f"Verified against the reviewed local Tanzil reference.{warning}",
            )

        if plausible > 1 and margin < MIN_VERIFIED_MARGIN:
            return QuranDecision(
                status="uncertain",
                match=best,
                margin=margin,
                alternatives=plausible,
                message=(
                    "Several Quran locations fit this transcript too closely to distinguish. "
                    "No Surah/Ayah is shown."
                ),
            )

        if (
            best.confidence >= POSSIBLE_CONFIDENCE
            and best.word_coverage >= 0.65
            and best.query_coverage >= 0.65
        ):
            return QuranDecision(
                status="possible",
                match=best,
                margin=margin,
                alternatives=plausible,
                message=(
                    "Possible Quran text match, but the evidence is below the verified threshold. "
                    "No Surah/Ayah is shown."
                ),
            )

        return QuranDecision(
            status="uncertain",
            match=best,
            margin=margin,
            alternatives=plausible,
            message="Quran text may be present, but confidence is insufficient. Review manually.",
        )

    @classmethod
    def install_tanzil_text(
        cls,
        raw_text: str,
        destination: Path,
    ) -> QuranReference:
        """Install only a reviewed, byte-faithful Tanzil profile as an offline reference."""
        records = _parse_numbered_tanzil(raw_text)
        checksum = canonical_tanzil_sha256(raw_text)
        if checksum not in TANZIL_TRUSTED_CANONICAL_SHA256:
            raise ValueError(
                "The file is complete but does not match the reviewed Tanzil 1.1 Simple profile. "
                "Download it with the default marks and Text (with aya numbers), or update Garden "
                "of Jihan after a newer Tanzil release has been reviewed."
            )

        destination.parent.mkdir(parents=True, exist_ok=True)
        source = {**TANZIL_SOURCE, "canonical_sha256": checksum}
        payload = {
            "schema_version": 1,
            "source": source,
            "integrity": {
                "verified": True,
                "canonical_sha256": checksum,
                "profile": TANZIL_PROFILE,
                "verse_count": TOTAL_AYAHS,
            },
            "verses": records,
        }
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return cls(destination)
