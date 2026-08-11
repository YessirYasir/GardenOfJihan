from __future__ import annotations

import subprocess
from pathlib import Path

from garden_jihan.runtime import ffmpeg_path


def render_clip(
    source: Path,
    output: Path,
    start: float,
    end: float,
    aspect: str = "9:16",
) -> None:
    if end <= start:
        raise ValueError("Clip end must be after start")
    output.parent.mkdir(parents=True, exist_ok=True)

    video_filter = None
    if aspect == "9:16":
        video_filter = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    elif aspect == "1:1":
        video_filter = "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080"
    elif aspect != "16:9":
        raise ValueError("Unsupported aspect ratio")

    command = [
        ffmpeg_path(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-to",
        f"{end:.3f}",
        "-i",
        str(source),
    ]
    if video_filter:
        command += ["-vf", video_filter]
    command += [
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        str(output),
    ]
    subprocess.run(command, check=True, timeout=600, shell=False)  # nosec B603
