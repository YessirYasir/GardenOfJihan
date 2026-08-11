from __future__ import annotations

import subprocess
from pathlib import Path


def render_clip(source: Path, output: Path, start: float, end: float, aspect: str = "9:16") -> None:
    if end <= start:
        raise ValueError("Clip end must be after start")
    output.parent.mkdir(parents=True, exist_ok=True)
    vf = None
    if aspect == "9:16":
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    elif aspect == "1:1":
        vf = "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080"
    elif aspect != "16:9":
        raise ValueError("Unsupported aspect ratio")

    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(source),
    ]
    if vf:
        command += ["-vf", vf]
    command += ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "160k", str(output)]
    subprocess.run(command, check=True, timeout=600, shell=False)
