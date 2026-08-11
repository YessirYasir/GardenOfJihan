# Somali evaluation corpus

Garden of Jihan needs a licensed, human-reviewed **gold evaluation corpus**, not an indiscriminate scrape. No media or gold annotations are bundled in this repository yet, so the project does not claim that Somali quality has passed a representative benchmark.

The executable evaluation framework accepts UTF-8 JSONL that follows [`evaluation.schema.json`](evaluation.schema.json). Every line is one candidate inside a comparison pair:

```json
{
  "id": "opaque-item-id",
  "pair_id": "opaque-comparison-id",
  "preferred": true,
  "duration": 31.4,
  "verbatim": "dialect-faithful reviewer transcript",
  "normalized": "optional reviewed orthographic alternative",
  "dialect_group": "reviewer-supplied variety label",
  "subvariety": "optional reviewer-supplied label",
  "region": "optional broad region",
  "speaker_id": "pseudonymous-speaker-id",
  "genre": "interview",
  "audio_quality": "phone-noisy",
  "code_switching": ["Arabic"],
  "source_id": "licensed-source-reference",
  "license": "corpus license or internal permission record",
  "reviewers": ["reviewer-a", "reviewer-b"],
  "adjudicated": true
}
```

`verbatim` always remains the display/audit transcript. `normalized` is a separate reviewed alternative used only to measure sensitivity to spelling choices. The application must never silently replace dialect-faithful speech with a normalized form.

## Pair construction

- Put two or more candidates with comparable duration and context in each `pair_id`.
- Mark exactly one human-preferred clip with `preferred: true` after adjudication.
- Keep a pair within one reviewer-supplied `dialect_group`; comparing one variety against another would confound the ranking result.
- Use pseudonymous speaker IDs and keep speakers disjoint across development and final test splits.
- Include noisy audio, diaspora speech, code-switching, interviews, khutbahs/duruus, comedy, debate, storytelling, news, education, and ordinary phone recordings.
- Require at least two qualified reviewers plus an adjudication result before treating an item as gold.
- Record a license or permission reference. Do not put copyrighted media in this repository without permission.

The schema deliberately does not impose a fixed dialect taxonomy. Variety names and boundaries require community and linguistic judgment; the evaluator treats reviewer-supplied labels as opaque groups and reports them separately.

## Running the benchmark

From an activated development environment:

```powershell
garden-of-jihan-somali-eval .\path\to\licensed-gold.jsonl `
  --min-pair-accuracy 0.75 `
  --min-macro-dialect-accuracy 0.70 `
  --min-worst-dialect-accuracy 0.60 `
  --max-dialect-gap 0.20 `
  --max-spelling-delta 5
```

The command emits no transcripts or source paths. It reports:

- pairwise ranking accuracy;
- macro and worst-group dialect accuracy;
- the accuracy gap between best and worst represented groups;
- mean score change between verbatim and reviewed normalized spelling;
- code-switched pair accuracy;
- per-group pair counts and accuracy.

Thresholds are explicit CLI arguments so a small exploratory corpus cannot silently become a launch gate. `--allow-unadjudicated` is only for corpus development and must not be used for release claims.
