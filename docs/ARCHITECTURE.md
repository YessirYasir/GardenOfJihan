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
    ├── faster-whisper transcription + acoustic word timestamps
    ├── language/mode routing
    ├── share-potential candidate scoring
    ├── Qur'an matcher (verified local reference required)
    └── bounded background FFmpeg render/export
```

Current automatic vertical framing samples faces locally with OpenCV and combines face position, mouth motion, and audio activity. A stable single face can be followed as a subject; multi-face tracking is applied only when audio-visual speech activity is separated confidently. Ambiguous evidence fails safely to the existing center crop, and manual center/left/right/split-stack framing remains available. This is not speaker identity or diarization.

The private portable-browser distribution is a separate handoff boundary for pre-signing tests. A plain one-click script launches a checksum-pinned, Python Software Foundation-signed embedded runtime with an isolated path file, hash-locked local dependencies, and bundled FFmpeg. It starts the same loopback-only server and production UI, stores mutable data under the current Windows user profile, and contains no custom unsigned Garden executable. It is validated from the exact ZIP contents and is never published through the public release workflow.

Completed jobs are atomically persisted inside their random job directory. The versioned manifest stores candidates, transcript segments, media signals, review selections, boundary edits, and export preferences. Restore validates the schema and keeps any source path inside its job directory. Saved projects are retained until the user explicitly removes them; incomplete temporary jobs remain subject to retention cleanup.

For Qur'an candidates, restored manifests are never trusted as the Surah/Ayah source of truth. Garden of Jihan reruns the matcher against the currently installed checksum-verified reference. Word-caption timing is exposed only when the verified text alignment is complete and every locating word maps to a monotonic, confidence-gated local acoustic timestamp. The timing is model-estimated and is not Qira'at evidence.

YouTube publishing is a separate opt-in boundary: Google Desktop OAuth uses loopback PKCE and upload-only scope, refresh material is DPAPI-encrypted for the current Windows user, and only validated MP4 exports inside the selected project can enter an official resumable upload. TikTok remains gated rather than falling back to an unofficial flow.

Future modules include robust speaker identity/diarization, independently evaluated acoustic alignment, verified Qira'at research, and audited TikTok publishing.
