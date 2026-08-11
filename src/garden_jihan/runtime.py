from __future__ import annotations

import shutil
import sys
from pathlib import Path


def bundled_root() -> Path:
    """Return the PyInstaller extraction root or the source package root."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def find_tool(name: str) -> str:
    """Resolve a bundled media binary first, then fall back to PATH."""
    executable = f"{name}.exe" if sys.platform == "win32" else name
    candidates = [
        bundled_root() / "bin" / executable,
        Path(sys.executable).resolve().parent / "bin" / executable,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    found = shutil.which(name)
    if found:
        return found
    raise RuntimeError(
        f"{name} is required but was not found. Use an official Garden of Jihan "
        "Windows release or install FFmpeg and make sure it is on PATH."
    )


def ffmpeg_path() -> str:
    return find_tool("ffmpeg")


def ffprobe_path() -> str:
    return find_tool("ffprobe")
