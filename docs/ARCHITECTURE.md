# Architecture

```text
Windows launcher
    │
    ├── creates random local session token
    ├── binds FastAPI to 127.0.0.1:<random-port>
    └── opens default browser
          │
          ▼
Light animated UI
          │
          ▼
Local API boundary
    ├── source validation
    ├── upload streaming
    ├── job isolation
    └── progress/results
          │
          ▼
Media pipeline
    ├── yt-dlp acquisition (supported remote sources)
    ├── ffprobe validation
    ├── faster-whisper transcription
    ├── language/mode routing
    ├── share-potential candidate scoring
    ├── Qur'an matcher (verified local reference required)
    └── FFmpeg render/export
```

Future modules include speaker-aware framing, scene analysis, audio-energy scoring, replay heatmap signals, word-tracked overlays, verified Qira'at diagnostics, OAuth publishing, and resumable cached projects.
