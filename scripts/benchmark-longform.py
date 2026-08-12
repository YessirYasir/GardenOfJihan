from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from garden_jihan.analysis.sampling import plan_listening_windows
from garden_jihan.analysis.scoring import build_candidates
from garden_jihan.analysis.semantics import LocalSemanticRanker
from garden_jihan.analysis.signals import build_media_signals
from garden_jihan.analysis.transcription import transcribe
from garden_jihan.media.probe import probe_media
from garden_jihan.models import AnalysisMode


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Benchmark the local long-form analysis path")
    parser.add_argument("video", type=Path)
    parser.add_argument("--mode", choices=[item.value for item in AnalysisMode], default="somali")
    parser.add_argument("--min-clip", type=int, default=20)
    parser.add_argument("--max-clip", type=int, default=90)
    parser.add_argument("--max-clips", type=int, default=12)
    parser.add_argument("--meaning-cache", type=Path, default=Path(".goj/benchmark-meaning"))
    parser.add_argument(
        "--require-under-seconds",
        type=float,
        help="Exit unsuccessfully when local analysis exceeds this performance gate",
    )
    args = parser.parse_args()

    video = args.video.resolve()
    mode = AnalysisMode(args.mode)
    media = probe_media(video, 2 * 60 * 60)
    language = "so" if mode == AnalysisMode.SOMALI else "ar" if mode in {
        AnalysisMode.ARABIC,
        AnalysisMode.QURAN,
    } else None

    last_reported = -1

    def report(fraction: float, _duration: float | None) -> None:
        nonlocal last_reported
        percent = int(fraction * 100)
        bucket = percent // 10 * 10
        if bucket > last_reported:
            last_reported = bucket
            print(f"Listening: {bucket}%", file=sys.stderr, flush=True)

    started = time.perf_counter()
    signal_started = time.perf_counter()
    signals = build_media_signals(video)
    signal_seconds = time.perf_counter() - signal_started
    windows = plan_listening_windows(
        float(media["duration"]),
        signals.audio_energy,
        min_clip_seconds=args.min_clip,
    )

    transcript_started = time.perf_counter()
    transcript = transcribe(video, language=language, progress=report, clips=windows)
    transcript_seconds = time.perf_counter() - transcript_started

    ranking_started = time.perf_counter()
    ranker = None if mode == AnalysisMode.QURAN else LocalSemanticRanker(args.meaning_cache)
    candidates = build_candidates(
        transcript.segments,
        mode,
        args.min_clip,
        args.max_clip,
        args.max_clips,
        signals=signals,
        semantic_ranker=ranker,
    )
    ranking_seconds = time.perf_counter() - ranking_started
    total_seconds = time.perf_counter() - started
    duration = float(media["duration"])
    print(
        json.dumps(
            {
                "video_seconds": round(duration, 3),
                "language": transcript.language,
                "segments": len(transcript.segments),
                "words": sum(len(segment.words) for segment in transcript.segments),
                "listening_windows": len(windows) if windows else 1,
                "listened_seconds": round(
                    sum(end - start for start, end in windows) if windows else duration,
                    3,
                ),
                "candidates": len(candidates),
                "transcription_seconds": round(transcript_seconds, 3),
                "signal_seconds": round(signal_seconds, 3),
                "ranking_seconds": round(ranking_seconds, 3),
                "total_seconds": round(total_seconds, 3),
                "realtime_factor": round(total_seconds / duration, 4),
                "top_moments": [
                    {
                        "start": round(candidate.start, 2),
                        "end": round(candidate.end, 2),
                        "score": candidate.score,
                        "title": candidate.title,
                        "reasons": candidate.reasons,
                    }
                    for candidate in candidates[:5]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.require_under_seconds is not None and total_seconds > args.require_under_seconds:
        raise SystemExit(
            f"Performance gate failed: {total_seconds:.3f}s exceeds "
            f"{args.require_under_seconds:.3f}s"
        )


if __name__ == "__main__":
    main()
