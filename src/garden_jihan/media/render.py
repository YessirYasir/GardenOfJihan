from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from garden_jihan.analysis.transcription import TranscriptSegment
from garden_jihan.runtime import ffmpeg_path


@dataclass(frozen=True, slots=True)
class CaptionCue:
    start: float
    end: float
    text: str


CAPTION_STYLES = {
    "garden": {
        "primary": "&H00FFF8E8",
        "outline": "&H00244A35",
        "back": "&H700F251A",
        "outline_width": 4,
        "shadow": 2,
        "bold": -1,
    },
    "high-contrast": {
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "back": "&H70000000",
        "outline_width": 5,
        "shadow": 2,
        "bold": -1,
    },
    "minimal": {
        "primary": "&H00FFFFFF",
        "outline": "&H50000000",
        "back": "&H70000000",
        "outline_width": 2,
        "shadow": 1,
        "bold": 0,
    },
}
CAPTION_ALIGNMENTS = {"bottom": 2, "middle": 5, "top": 8}


def caption_cues_for_range(
    segments: Iterable[TranscriptSegment],
    start: float,
    end: float,
) -> list[CaptionCue]:
    """Return real ASR segment timings clipped and rebased to an exported clip."""
    if end <= start:
        raise ValueError("Clip end must be after start")
    cues = []
    for segment in segments:
        if segment.end <= start or segment.start >= end or not segment.text.strip():
            continue
        cue_start = max(segment.start, start) - start
        cue_end = min(segment.end, end) - start
        if cue_end - cue_start < 0.05:
            continue
        cues.append(CaptionCue(cue_start, cue_end, segment.text.strip()))
    return cues


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    whole_seconds, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{fraction:02d}"


def _escape_ass_text(text: str) -> str:
    clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return (
        clean.replace("\\", "＼")
        .replace("{", "｛")
        .replace("}", "｝")
        .replace("\r\n", r"\N")
        .replace("\r", r"\N")
        .replace("\n", r"\N")
    )


def _write_ass_captions(
    path: Path,
    cues: list[CaptionCue],
    aspect: str,
    style_name: str,
    position: str,
) -> None:
    try:
        style = CAPTION_STYLES[style_name]
        alignment = CAPTION_ALIGNMENTS[position]
    except KeyError as exc:
        raise ValueError("Unsupported caption style or position") from exc

    width, height = {
        "9:16": (1080, 1920),
        "1:1": (1080, 1080),
        "16:9": (1920, 1080),
    }.get(aspect, (0, 0))
    if not width:
        raise ValueError("Unsupported aspect ratio")
    font_size = 76 if height == 1920 else 50
    margin = 128 if height == 1920 else 72
    style_line = (
        "Style: Caption,Segoe UI,{font_size},{primary},&H000000FF,{outline},{back},"
        "{bold},0,0,0,100,100,0,0,1,{outline_width},{shadow},{alignment},"
        "70,70,{margin},1"
    ).format(font_size=font_size, alignment=alignment, margin=margin, **style)
    events = [
        f"Dialogue: 0,{_ass_time(cue.start)},{_ass_time(cue.end)},"
        f"Caption,,0,0,0,,{_escape_ass_text(cue.text)}"
        for cue in cues
    ]
    content = "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {width}",
            f"PlayResY: {height}",
            "WrapStyle: 0",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
            "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
            "MarginR, MarginV, Encoding",
            style_line,
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            *events,
            "",
        ]
    )
    path.write_text(content, encoding="utf-8")


def _subtitle_filter(path: Path) -> str:
    escaped = path.resolve().as_posix()
    for character in ("\\", ":", "'", "[", "]", ",", ";"):
        escaped = escaped.replace(character, f"\\{character}")
    return f"subtitles=filename='{escaped}'"


def render_clip(
    source: Path,
    output: Path,
    start: float,
    end: float,
    aspect: str = "9:16",
    framing: str = "center",
    *,
    caption_cues: list[CaptionCue] | None = None,
    caption_style: str = "garden",
    caption_position: str = "bottom",
) -> None:
    if end <= start:
        raise ValueError("Clip end must be after start")
    if framing not in {"center", "left", "right", "split-stack"}:
        raise ValueError("Unsupported framing mode")
    if caption_style not in CAPTION_STYLES or caption_position not in CAPTION_ALIGNMENTS:
        raise ValueError("Unsupported caption style or position")
    output.parent.mkdir(parents=True, exist_ok=True)
    caption_file = None
    caption_filter = None
    if caption_cues:
        caption_file = output.with_suffix(".captions.ass")
        _write_ass_captions(
            caption_file,
            caption_cues,
            aspect,
            caption_style,
            caption_position,
        )
        caption_filter = _subtitle_filter(caption_file)

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
            "[l][r]vstack=inputs=2"
        )
        if caption_filter:
            filter_complex += f"[stacked];[stacked]{caption_filter}[v]"
        else:
            filter_complex += "[v]"
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
        if caption_filter:
            video_filter = f"{video_filter},{caption_filter}" if video_filter else caption_filter
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
    try:
        subprocess.run(command, check=True, timeout=600, shell=False)  # nosec B603
    finally:
        if caption_file:
            caption_file.unlink(missing_ok=True)
