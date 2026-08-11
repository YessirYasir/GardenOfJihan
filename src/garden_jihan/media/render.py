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
    framing: str = "center",
) -> None:
    if end <= start:
        raise ValueError("Clip end must be after start")
    if framing not in {"center", "left", "right", "split-stack"}:
        raise ValueError("Unsupported framing mode")
    output.parent.mkdir(parents=True, exist_ok=True)

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

    if aspect == "9:16" and framing == "split-stack":
        filter_complex = (
            "[0:v]split=2[left][right];"
            "[left]crop=iw/2:ih:0:0,"
            "scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[l];"
            "[right]crop=iw/2:ih:iw/2:0,"
            "scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[r];"
            "[l][r]vstack=inputs=2[v]"
        )
        command += ["-filter_complex", filter_complex, "-map", "[v]", "-map", "0:a?"]
    else:
        video_filter = None
        if aspect == "9:16":
            x = {"left": "0", "center": "(iw-ow)/2", "right": "iw-ow"}.get(
                framing,
                "(iw-ow)/2",
            )
            video_filter = (
                "scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920:{x}:0"
            )
        elif aspect == "1:1":
            video_filter = "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080"
        elif aspect != "16:9":
            raise ValueError("Unsupported aspect ratio")
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
        "-movflags",
        "+faststart",
        str(output),
    ]
    subprocess.run(command, check=True, timeout=600, shell=False)  # nosec B603
