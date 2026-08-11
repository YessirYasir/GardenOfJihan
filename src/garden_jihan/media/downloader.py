from __future__ import annotations

from pathlib import Path

from garden_jihan.security import validate_remote_url


def download_remote(url: str, destination: Path) -> Path:
    import yt_dlp

    _provider, clean = validate_remote_url(url)
    destination.mkdir(parents=True, exist_ok=True)
    outtmpl = str(destination / "source.%(ext)s")
    options = {
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "overwrites": True,
        "socket_timeout": 30,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(clean, download=True)
        candidate = Path(ydl.prepare_filename(info))

    if candidate.exists():
        return candidate
    mp4 = destination / "source.mp4"
    if mp4.exists():
        return mp4
    matches = list(destination.glob("source.*"))
    if not matches:
        raise FileNotFoundError("Downloaded media could not be located")
    return matches[0]
