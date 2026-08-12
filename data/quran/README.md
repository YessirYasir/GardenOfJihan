# Qur'an reference data

Garden of Jihan does **not** use an LLM as the authority for Surah/Ayah numbering or Qira'at identification.

## Offline recognition reference

The production matcher currently supports one reviewed Tanzil 1.1 profile as its offline Surah/Ayah recognition reference:

- text type: **Simple**
- Tanzil's default pause marks, sajdah signs, and tatweel options
- download format: **Text (with aya numbers)**
- canonical SHA256: `d25401b9235ea0c77a2511b1edc5b5d28df1b3bcd0259d6657ec6e303dd8eee9`

Tanzil Quran Text is published by the Tanzil Project under Creative Commons Attribution 3.0. Its license permits verbatim copying and application use, requires clear attribution/source linking, and does not permit changing the Quran text itself.

Reference source and updates:

- Tanzil Project: https://tanzil.net/
- Text license: https://tanzil.net/docs/Text_License
- Download documentation: https://tanzil.net/docs/download
- Updates: https://tanzil.net/docs/text_updates

Garden of Jihan preserves `text_display` verbatim. Arabic normalization is stored only as a separate `text_match` representation used for search/matching. The normalized matching copy must never replace the displayed sacred text.

The importer accepts only a complete `surah|ayah|text` file whose 6236 coordinates are in exact canonical order and whose canonical checksum matches the reviewed profile above. The canonical checksum is calculated over the non-comment content lines, joined with LF line endings and no final newline. Partial, reordered, modified, differently configured, or newer files fail closed until their exact profile is reviewed and added in code.

Installed data is written atomically under the user's local Garden of Jihan application-data directory as `reference/quran_reference.json` with Tanzil source/license metadata and integrity fields. The coordinate sequence, display text, profile, notice, and checksums are revalidated every time the reference is loaded. A corrupt or edited installed file is disabled rather than used.

## Quran.com / Quran Foundation

Quran Foundation / Quran.com remains the intended human-verification/reference layer. Its Content API uses OAuth2 client credentials, including a client secret that must stay on a backend and therefore must not be embedded in this open-source desktop client.

## Qira'at

Qira'at recognition is intentionally separate from Surah/Ayah text recognition. A planning registry records the ten canonical readers and their two main transmission traditions, but the application does **not** currently identify Qira'at. It must not label a reading from text matching alone. Future Qira'at support requires independently validated reading-sensitive reference data and acoustic evidence, and the UI must be able to say that a reading was not assessed or is not distinguishable.

## Safety behavior

- A Surah/Ayah label appears only when the reference is valid, textual confidence and coverage clear strict thresholds, and competing locations are not too close.
- Borderline, partial, or ambiguous matches require review and do not reveal a guessed location.
- Repeated passages fail safely when textual evidence cannot distinguish their locations.
- Reference word alignment remains textual. Separately, optional caption timing is attached only when every locating reference word maps one-to-one to monotonic local speech-model timestamps and all per-word probabilities clear the conservative threshold. The timing is labeled model-estimated, not human-verified.
- Acoustic word timing is not evidence of Qira'at, reader identity, or transmission.
- Missing or invalid reference data is reported explicitly.
- No reading or transmission is inferred from the offline text match.
