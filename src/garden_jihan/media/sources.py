from __future__ import annotations

from dataclasses import dataclass

from garden_jihan.security import validate_remote_url


@dataclass(slots=True)
class SourceInfo:
    provider: str
    url: str
    title: str = ""
    duration: int | None = None
    live_status: str | None = None


def inspect_source(url: str, max_seconds: int) -> SourceInfo:
    provider, clean = validate_remote_url(url)
    try:
        import yt_dlp
    except ImportError:
        return SourceInfo(provider=provider, url=clean)

    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "extract_flat": False,
        "socket_timeout": 20,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(clean, download=False)

    duration = info.get("duration")
    live_status = info.get("live_status")
    if live_status in {"is_live", "is_upcoming"}:
        raise ValueError("Only finished livestreams are supported")
    if duration and int(duration) > max_seconds:
        raise ValueError("Video exceeds the two-hour processing limit")

    return SourceInfo(
        provider=provider,
        url=clean,
        title=str(info.get("title") or "Untitled"),
        duration=int(duration) if duration else None,
        live_status=live_status,
    )
