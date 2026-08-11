from __future__ import annotations

import json
import subprocess
from pathlib import Path

from garden_jihan.runtime import ffprobe_path


def probe_media(path: Path, max_seconds: int) -> dict:
    completed = subprocess.run(  # nosec B603
        [
            ffprobe_path(),
            "-v",
            "error",
            "-show_entries",
            "format=duration,format_name",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
        shell=False,
    )
    info = json.loads(completed.stdout)
    duration = float(info.get("format", {}).get("duration") or 0)
    if duration <= 0:
        raise ValueError("Could not determine media duration")
    if duration > max_seconds:
        raise ValueError("Video exceeds the two-hour processing limit")
    video_streams = [stream for stream in info.get("streams", []) if stream.get("codec_type") == "video"]
    if not video_streams:
        raise ValueError("No video stream found")
    info["duration"] = duration
    return info
