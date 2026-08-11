# Somali evaluation corpus

Garden of Jihan needs a **gold evaluation corpus**, not an indiscriminate scrape.

Each speech item should preserve what was actually said and optionally provide a normalized orthographic form:

```json
{
  "id": "uuid",
  "start": 10.2,
  "end": 15.8,
  "verbatim": "dialect-faithful transcript",
  "normalized": "reviewed normalized form",
  "dialect_group": "Maxaa Tiri | Benaadir | Ashraaf | Maay | Digil-related",
  "subvariety": "free text",
  "region": "free text",
  "code_switching": ["Arabic"],
  "source_url": "...",
  "license": "...",
  "reviewers": ["reviewer-a", "reviewer-b"]
}
```

A stable benchmark should include multiple native reviewers, adjudication on disagreements, noisy audio, diaspora speech, code-switching, interviews, khutbahs/duruus, comedy, debate, storytelling, news, education, and ordinary phone-quality recordings.

Do not put copyrighted media in this repository without permission.
