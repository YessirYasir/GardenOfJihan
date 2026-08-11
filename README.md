# Garden of Jihan — جيهان

![Garden of Jihan design target](docs/design-preview.svg)

Garden of Jihan is a free, open-source, **local-first Windows application** that turns long-form video into ranked short-form clip candidates through a calm browser-style interface.

The project is designed around four principles:

- **Private by default:** processing happens on the user's computer.
- **Useful without credits:** no token meter, subscription, or required paid AI API.
- **Multilingual by design:** English, Arabic, and Somali are first-class modes.
- **Faithful Qur'an workflows:** Qur'anic recognition must use verified reference data and fail safely when confidence is insufficient.

> **Status: early build.** The application shell, security boundary, source validation, local job architecture, scoring engine, UI, and Qur'an matcher interfaces are included. Qur'an/Qira'at reference data and Somali evaluation corpora are intentionally not claimed complete until they are verified and licensed for distribution.

## What it will do

1. Paste a supported video URL or select a local file.
2. Choose Auto, Somali, Arabic, or Qur'an mode.
3. Analyze finished videos / finished YouTube livestreams up to two hours.
4. Rank non-overlapping moments by share potential.
5. Review and adjust boundaries.
6. Render clean clips in 9:16, 16:9, or 1:1.
7. Save locally and, after official OAuth integrations are configured, publish through supported platform APIs.

Supported source validation is structured for YouTube, TikTok, Instagram, and local files. Users are responsible for having the rights and permission to process and republish source media.

Garden of Jihan does **not** include features whose purpose is to evade platform originality, provenance, copyright, or moderation systems. Creative transformation features should make edits genuinely useful and distinct, not spoof platform verification.

## UI direction

The app opens locally in the user's default browser with a light garden aesthetic: moving petals, parallax flowerbeds, soft animated landscapes, and clear six-step navigation. Motion automatically reduces when the operating system requests reduced motion.

## Quick start (development)

Requirements:

- Windows 11 recommended
- Python 3.11 or 3.12
- FFmpeg and ffprobe available on PATH
- Git

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,ai]"
garden-of-jihan
```

The launcher binds only to `127.0.0.1`, chooses a local port, opens the UI, and generates a per-launch anti-CSRF token.

## Security model

Garden of Jihan is designed as local software, not an internet-facing web service.

- Loopback-only binding (`127.0.0.1`)
- Strict source-host allowlist
- No arbitrary URL fetch endpoint
- Mutation requests require a per-launch token and same-origin request
- No `shell=True` subprocess execution
- Random isolated job directories
- Bounded input duration and upload size
- Content Security Policy and anti-framing headers
- No telemetry by default
- Temporary-job cleanup
- GitHub Actions security checks

See [`SECURITY.md`](SECURITY.md) and [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

## Qur'an and Qira'at

The matcher architecture separates:

1. Qur'anic passage identification
2. word-level alignment
3. Qira'at-sensitive diagnostic locations
4. reading/transmission confidence

The UI must be able to say **“not distinguishable from this passage”** rather than invent a reading.

The intended reference authority is Quran Foundation / Quran.com. Their authenticated Content API client secret must never be embedded in this open-source desktop application. See [`data/quran/README.md`](data/quran/README.md).

## Somali language benchmark

The project keeps dialectal speech and normalized spelling as separate annotation fields so regional Somali is not silently rewritten into one standard variety. See [`data/somali/README.md`](data/somali/README.md).

## License

MIT. Third-party datasets, models, platform APIs, and media retain their own licenses and terms.
