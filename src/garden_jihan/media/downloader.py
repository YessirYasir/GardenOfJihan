from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from garden_jihan.runtime import ffmpeg_path
from garden_jihan.security import validate_remote_url

DownloadProgress = Callable[[float, int | None], None]


def download_remote(
    url: str,
    destination: Path,
    *,
    progress: DownloadProgress | None = None,
) -> Path:
    import yt_dlp

    _provider, clean_url = validate_remote_url(url)
    destination.mkdir(parents=True, exist_ok=True)
    outtmpl = str(destination / "source.%(ext)s")

    def progress_hook(data: dict) -> None:
        if progress is None:
            return
        status = data.get("status")
        if status == "finished":
            progress(1.0, 0)
            return
        if status != "downloading":
            return
        downloaded = float(data.get("downloaded_bytes") or 0)
        total = float(data.get("total_bytes") or data.get("total_bytes_estimate") or 0)
        fraction = downloaded / total if total > 0 else 0.0
        raw_eta = data.get("eta")
        eta = max(0, round(float(raw_eta))) if raw_eta is not None else None
        progress(max(0.0, min(1.0, fraction)), eta)

    options = {
        # A 720p analysis master is ample for vertical and square short-form exports,
        # while avoiding multi-gigabyte long-form downloads that delay the first result.
        "format": (
            "bv*[height<=720][fps<=30]+ba/"
            "b[height<=720][fps<=30]/"
            "bv*[height<=720]+ba/b[height<=720]/bv*+ba/b"
        ),
        "merge_output_format": "mp4",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "overwrites": True,
        "socket_timeout": 30,
        "concurrent_fragment_downloads": 4,
        "ffmpeg_location": str(Path(ffmpeg_path()).parent),
        "progress_hooks": [progress_hook],
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(clean_url, download=True)
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
