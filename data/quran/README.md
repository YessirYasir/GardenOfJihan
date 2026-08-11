# Qur'an reference data

This directory intentionally does **not** ship an unverified scrape.

Garden of Jihan should use Quran Foundation / Quran.com as the human-verification authority while respecting its developer terms and authentication model. The Quran Foundation Content API requires a client secret that must not be embedded in an open-source desktop client.

The production matcher expects a verified local reference package containing, at minimum:

```json
{
  "surah": 1,
  "ayah": 1,
  "text_display": "verified Arabic text",
  "text_match": "normalized matching representation",
  "reading": "Hafs",
  "transmission": "Hafs an Asim",
  "source": "documented authority",
  "license": "documented license",
  "sha256": "reference-record hash"
}
```

Stable releases must verify the provenance, license, integrity, and update process for any bundled sacred text. The language model must never be the final authority for Surah/Ayah numbering or Qira'at identification.
