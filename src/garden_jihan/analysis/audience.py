from __future__ import annotations

from garden_jihan.analysis.signals import TimedValue
from garden_jihan.security import validate_remote_url


def normalize_heatmap(segments: list[dict]) -> list[TimedValue]:
    """Convert yt-dlp heatmap bins into bounded 0..1 values."""
    parsed: list[tuple[float, float, float]] = []
    peak = 0.0
    for segment in segments:
        try:
            start = max(0.0, float(segment.get("start_time", 0.0)))
            end = max(start, float(segment.get("end_time", start)))
            value = max(0.0, float(segment.get("value", 0.0)))
        except (TypeError, ValueError):
            continue
        if end <= start:
            continue
        parsed.append((start, end, value))
        peak = max(peak, value)
    if peak <= 0:
        return []
    return [TimedValue(start, end, min(1.0, value / peak)) for start, end, value in parsed]


def youtube_replay_signal(url: str) -> list[TimedValue]:
    """Read YouTube's optional most-replayed heatmap through yt-dlp.

    The signal is advisory and failure-safe. It is only attempted for an
    already allowlisted user-supplied YouTube URL and never blocks clipping.
    """
    try:
        provider, clean = validate_remote_url(url)
        if provider != "youtube":
            return []
        import yt_dlp

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": 20,
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(clean, download=False)
        return normalize_heatmap(info.get("heatmap") or [])
    except Exception:
        return []
