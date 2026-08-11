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
    ├── versioned local project restore
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

Current automatic vertical framing samples faces locally with OpenCV and combines face position, mouth motion, and audio activity. A stable single face can be followed as a subject; multi-face tracking is applied only when audio-visual speech activity is separated confidently. Ambiguous evidence fails safely to the existing center crop, and manual center/left/right/split-stack framing remains available. This is not speaker identity or diarization.

Completed jobs are atomically persisted inside their random job directory. The versioned manifest stores candidates, transcript segments, media signals, review selections, boundary edits, and export preferences. Restore validates the schema and keeps any source path inside its job directory. Saved projects are retained until the user explicitly removes them; incomplete temporary jobs remain subject to retention cleanup.

Future modules include robust speaker identity/diarization, word-tracked overlays, verified Qira'at diagnostics, and OAuth publishing.
