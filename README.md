# Garden of Jihan — جيهان

![Garden of Jihan design target](docs/design-preview.svg)

Garden of Jihan is a free, open-source, **local-first Windows application** that turns long-form video into ranked short-form clip candidates through a calm browser-style interface.

## Windows release status

**Public Windows download is temporarily withheld while trusted code signing and Microsoft Store distribution are being completed.**

The application itself is already building and launching successfully on clean Windows runners, but Garden of Jihan will not intentionally publish an unsigned EXE as the recommended end-user download. The release pipeline now requires a valid Authenticode signature before a public release can be created.

Once the signed release is ready, this section will become the main one-click install/download entry point. End users will not need Python, FFmpeg, Git, a subscription, credits, or a paid AI API.

The first AI analysis downloads the local Whisper model and multilingual meaning model once and caches them on that PC. Video analysis and rendering then run locally. If the meaning model is unavailable, the UI reports its base-ranking fallback; it never uploads transcripts to a paid or cloud fallback.

The project is designed around four principles:

- **Private by default:** processing happens on the user's computer.
- **Useful without credits:** no token meter, subscription, or required paid AI API.
- **Multilingual by design:** English, Arabic, and Somali are first-class modes.
- **Faithful Qur'an workflows:** Qur'anic recognition must use verified reference data and fail safely when confidence is insufficient.

> **Status: internal/public-beta candidate.** The Windows application, local security boundary, source validation, Intelligence V2 ranking, manual timing, framing controls, styled segment-timed captions, export pipeline, bundled media tools, CI/security scans, clean-Windows executable smoke tests, and Microsoft Defender release scans are operational. Checksum-pinned Tanzil installation and fail-safe Surah/Ayah matching are implemented; acoustic Qira'at recognition and Qur'an word timing are not. Trusted Windows distribution, a representative Somali gold corpus, automatic speaker tracking, and direct platform publishing remain active development areas.

## Current workflow

1. Paste a supported video URL or select a local file.
2. Choose Auto, Somali, Arabic, or Qur'an mode.
3. Analyze finished videos / finished YouTube livestreams up to two hours.
4. Rank non-overlapping moments using local multilingual embeddings, transcript structure, audio energy, visual activity, and YouTube replay data when available.
5. Preview clips, adjust start/end timing, and select the strongest moments.
6. Choose 9:16, 16:9, or 1:1 output plus manual vertical framing options.
7. Optionally burn in locally timed transcript captions using Garden, high-contrast, or minimal styling.
8. Render clean MP4 clips locally and save them.

Supported source validation is structured for YouTube, TikTok, Instagram, and local files. Users are responsible for having the rights and permission to process and republish source media.

Garden of Jihan does **not** include features whose purpose is to evade platform originality, provenance, copyright, or moderation systems. Creative transformation features should make edits genuinely useful and distinct, not spoof platform verification.

## UI direction

The app opens locally in the user's default browser with a light garden aesthetic: layered flowerbeds, soft animated landscapes, and slow swaying falling flowers behind the six-step workflow. Motion automatically reduces when the operating system requests reduced motion.

## Development setup

Contributors can run from source with Python 3.11 or 3.12:

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
- Windows package smoke-tested by launching the packaged executable on a clean GitHub Windows runner
- Microsoft Defender Antivirus scan before release
- SHA256 checksum and GitHub build-provenance attestation for release artifacts
- Public release workflow requires a valid Authenticode signature

The optional local meaning pass uses the MIT-licensed `intfloat/multilingual-e5-small` model through CPU-only ONNX inference. It adjusts a bounded 10% of the candidate score for within-clip topic coherence and uses semantic similarity to reduce paraphrased repeats. The original base ranking remains available when the model cannot load. Low-resource-language performance, especially Somali varieties, must pass the licensed evaluation framework before release-quality claims are made. See [`docs/SEMANTIC_MODEL.md`](docs/SEMANTIC_MODEL.md).

See [`SECURITY.md`](SECURITY.md), [`PRIVACY.md`](PRIVACY.md), [`CODE_SIGNING.md`](CODE_SIGNING.md), and [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

## Qur'an and Qira'at

The matcher architecture separates:

1. Qur'anic passage identification
2. word-level alignment
3. a future Qira'at-sensitive acoustic evidence layer
4. future reading/transmission confidence

Current releases do not claim Qira'at identification. The UI reports that a reading was not assessed rather than inventing one.

Qur'an burn-in captions are also disabled until acoustic evidence can support verified timing. The editor may display checksum-verified reference text and textual word alignment for review, but it does not misrepresent those textual alignments as spoken-word timestamps.

The offline matcher uses a reviewed, checksum-pinned Tanzil profile. Quran Foundation / Quran.com remains the intended human-verification layer; its authenticated Content API client secret must never be embedded in this open-source desktop application. See [`data/quran/README.md`](data/quran/README.md).

## Somali language benchmark

The project keeps dialectal speech and normalized spelling as separate annotation fields so regional Somali is not silently rewritten into one standard variety. A local evaluator now reports pairwise, macro-group, worst-group, spelling-variation, and code-switching metrics; a representative licensed gold corpus is still required before release-quality claims can be made. See [`data/somali/README.md`](data/somali/README.md).

## License

MIT. Third-party datasets, models, platform APIs, and media retain their own licenses and terms.
