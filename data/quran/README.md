# Qur'an reference data

Garden of Jihan does **not** use an LLM as the authority for Surah/Ayah numbering or Qira'at identification.

## Offline recognition reference

The production matcher supports a complete, verbatim Tanzil Quran text as its offline Surah/Ayah recognition reference.

Tanzil Quran Text is published by the Tanzil Project under Creative Commons Attribution 3.0. Its license permits verbatim copying and application use, requires clear attribution/source linking, and does not permit changing the Quran text itself.

Reference source and updates:

- Tanzil Project: https://tanzil.net/
- Text license: https://tanzil.net/docs/Text_License
- Updates: https://tanzil.net/updates/

Garden of Jihan preserves `text_display` verbatim. Arabic normalization is stored only as a separate `text_match` representation used for search/matching. The normalized matching copy must never replace the displayed sacred text.

The importer accepts a complete 6236-ayah Tanzil file in either `surah|ayah|text` form or the standard one-ayah-per-line order. Partial files are rejected.

Installed data is stored under the user's local Garden of Jihan application-data directory as `reference/quran_reference.json` with Tanzil source/license metadata.

## Quran.com / Quran Foundation

Quran Foundation / Quran.com remains the intended human-verification/reference layer. Its Content API uses OAuth2 client credentials, including a client secret that must stay on a backend and therefore must not be embedded in this open-source desktop client.

## Qira'at

Qira'at recognition is intentionally separate from Surah/Ayah text recognition. The application models all ten canonical readers and their two main transmitter traditions, but it must not label a reading from text matching alone. Qira'at identification requires reading-sensitive locations plus acoustic evidence, and the UI must be able to say that a passage is not distinguishable.

## Safety behavior

- High-confidence reference matches may label a candidate with Surah/Ayah.
- Borderline matches are shown as possible and require review.
- Weak matches remain uncertain.
- Missing reference data is reported explicitly.
- No reading/transmission is inferred from the offline text match.
