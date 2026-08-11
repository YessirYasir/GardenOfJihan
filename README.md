# Garden of Jihan — جيهان

![Garden of Jihan design target](docs/design-preview.svg)

Garden of Jihan is a free, open-source, **local-first Windows application** that turns long-form video into ranked short-form clip candidates through a calm browser-style interface.

## Download for Windows

**Public beta:** [Download GardenOfJihan-Windows-x64.zip](https://github.com/YessirYasir/GardenOfJihan/releases/download/v0.1.0-beta.1/GardenOfJihan-Windows-x64.zip)

No Python, FFmpeg, Git, subscription, credits, or paid AI API is required.

1. Download the ZIP from the link above.
2. Extract the ZIP to a normal folder.
3. Open `GardenOfJihan.exe`.
4. Garden of Jihan opens its private local interface in your default browser.
5. Paste a supported video link or choose a local video and begin.

The first AI analysis downloads the local Whisper model once and caches it on that PC. Video analysis and rendering then run locally. Every official beta release is built from this public repository by GitHub Actions, smoke-tested on a clean Windows runner, scanned with Microsoft Defender Antivirus, published with a SHA256 checksum, and given a GitHub build-provenance attestation.

The project is also preparing free open-source trusted code signing through SignPath Foundation. Until that approval is active, a new unsigned beta can still receive a Windows SmartScreen **Unknown publisher** warning even when the release scan and automated checks are clean. See the project [`Code signing policy`](CODE_SIGNING.md).

The project is designed around four principles:

- **Private by default:** processing happens on the user's computer.
- **Useful without credits:** no token meter, subscription, or required paid AI API.
- **Multilingual by design:** English, Arabic, and Somali are first-class modes.
- **Faithful Qur'an workflows:** Qur'anic recognition must use verified reference data and fail safely when confidence is insufficient.

> **Status: public beta.** The Windows application, local security boundary, source validation, Intelligence V2 ranking, manual timing, framing controls, export pipeline, bundled media tools, CI/security scans, and clean-Windows executable smoke tests are operational. Advanced Qur'an/Qira'at reference recognition, Somali corpus validation, automatic speaker tracking, caption styling, and direct platform publishing remain active development areas and are not represented as complete yet.

## Current workflow

1. Paste a supported video URL or select a local file.
2. Choose Auto, Somali, Arabic, or Qur'an mode.
3. Analyze finished videos / finished YouTube livestreams up to two hours.
4. Rank non-overlapping moments using transcript meaning, audio energy, visual activity, and YouTube replay data when available.
5. Preview clips, adjust start/end timing, and select the strongest moments.
6. Choose 9:16, 16:9, or 1:1 output plus manual vertical framing options.
7. Render clean MP4 clips locally and save them.

Supported source validation is structured for YouTube, TikTok, Instagram, and local files. Users are responsible for having the rights and permission to process and republish source media.

Garden of Jihan does **not** include features whose purpose is to evade platform originality, provenance, copyright, or moderation systems. Creative transformation features should make edits genuinely useful and distinct, not spoof platform verification.

## UI direction

The app opens locally in the user's default browser with a light garden aesthetic: moving petals, parallax flowerbeds, soft animated landscapes, and clear six-step navigation. Motion automatically reduces when the operating system requests reduced motion.

## Development setup

End users should use the Windows release above. Contributors can run from source with Python 3.11 or 3.12:

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
- GitHub Actions CI, Bandit, dependency audit, and CodeQL checks
- Windows release smoke-tested by launching the packaged executable on a clean GitHub Windows runner
- Microsoft Defender Antivirus scan before public release
- SHA256 checksum and GitHub build-provenance attestation for the downloadable ZIP

See [`SECURITY.md`](SECURITY.md), [`PRIVACY.md`](PRIVACY.md), [`CODE_SIGNING.md`](CODE_SIGNING.md), and [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

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
