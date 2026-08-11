from __future__ import annotations

import math
import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from garden_jihan.analysis.transcription import TranscriptSegment
from garden_jihan.media.framing import FramingPoint
from garden_jihan.runtime import ffmpeg_path


@dataclass(frozen=True, slots=True)
class CaptionCue:
    start: float
    end: float
    text: str


@dataclass(frozen=True, slots=True)
class TrackedCaptionCue:
    start: float
    end: float
    words: tuple[str, ...]
    active_index: int


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


def _tracked_cues(words: list[tuple[float, float, str]], start: float, end: float):
    cues: list[TrackedCaptionCue] = []
    words = [
        word
        for word in words
        if all(math.isfinite(value) for value in word[:2]) and word[1] > word[0]
    ]
    for group_start in range(0, len(words), 7):
        group = words[group_start : group_start + 7]
        labels = tuple(word[2] for word in group)
        for index, (word_start, word_end, _text) in enumerate(group):
            cue_start = max(start, word_start)
            next_start = group[index + 1][0] if index + 1 < len(group) else word_end
            cue_end = min(end, max(word_end, next_start))
            if cue_end - cue_start < 0.05:
                continue
            cues.append(
                TrackedCaptionCue(
                    start=cue_start - start,
                    end=cue_end - start,
                    words=labels,
                    active_index=index,
                )
            )
    return cues


def word_caption_cues_for_range(
    segments: Iterable[TranscriptSegment],
    start: float,
    end: float,
) -> list[TrackedCaptionCue]:
    """Build honest word highlights only from local model acoustic timestamps."""
    if end <= start:
        raise ValueError("Clip end must be after start")
    cues: list[TrackedCaptionCue] = []
    for segment in segments:
        if segment.end <= start or segment.start >= end:
            continue
        words = [
            (word.start, word.end, word.text.strip())
            for word in segment.words
            if word.end > start and word.start < end and word.text.strip()
        ]
        cues.extend(_tracked_cues(words, start, end))
    return cues


def quran_word_caption_cues_for_range(
    match: dict,
    start: float,
    end: float,
) -> list[TrackedCaptionCue]:
    """Use sacred reference display text only after conservative acoustic alignment."""
    if end <= start:
        raise ValueError("Clip end must be after start")
    if match.get("status") != "verified" or match.get("acoustic_timing_status") != "supported":
        return []
    alignment = match.get("word_alignment")
    if not isinstance(alignment, list):
        return []
    by_ayah: dict[int, list[tuple[float, float, str]]] = {}
    for word in alignment:
        if not isinstance(word, dict):
            return []
        if not word.get("matched") or word.get("optional"):
            continue
        try:
            word_start = float(word["acoustic_start"])
            word_end = float(word["acoustic_end"])
            ayah = int(word["ayah"])
            display = str(word["reference_word"]).strip()
        except (KeyError, TypeError, ValueError):
            return []
        if (
            not display
            or not all(math.isfinite(value) for value in (word_start, word_end))
            or word_end <= word_start
        ):
            return []
        if word_end > start and word_start < end:
            by_ayah.setdefault(ayah, []).append((word_start, word_end, display))
    cues = []
    for words in by_ayah.values():
        cues.extend(_tracked_cues(words, start, end))
    return sorted(cues, key=lambda cue: (cue.start, cue.end))


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
    cues: list[CaptionCue | TrackedCaptionCue],
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
    events = []
    for cue in cues:
        if isinstance(cue, TrackedCaptionCue):
            if not cue.words or not 0 <= cue.active_index < len(cue.words):
                raise ValueError("Invalid tracked caption cue")
            words = []
            for index, word in enumerate(cue.words):
                escaped = _escape_ass_text(word)
                if index == cue.active_index:
                    escaped = rf"{{\1c&H003DCEFF&\b1}}{escaped}{{\rCaption}}"
                words.append(escaped)
            text = " ".join(words)
        else:
            text = _escape_ass_text(cue.text)
        events.append(
            f"Dialogue: 0,{_ass_time(cue.start)},{_ass_time(cue.end)},"
            f"Caption,,0,0,0,,{text}"
        )
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


def _framing_center_expression(points: list[FramingPoint] | tuple[FramingPoint, ...]) -> str:
    """Build a bounded, linearly interpolated clip-relative FFmpeg expression."""
    valid = sorted(
        (
            FramingPoint(max(0.0, point.time), min(1.0, max(0.0, point.center_x)))
            for point in points
            if point.time == point.time and point.center_x == point.center_x
        ),
        key=lambda point: point.time,
    )
    if not valid:
        return "0.5"
    unique: list[FramingPoint] = []
    for point in valid:
        if unique and abs(unique[-1].time - point.time) < 0.001:
            unique[-1] = point
        else:
            unique.append(point)
    expression = f"{unique[-1].center_x:.5f}"
    for left, right in reversed(list(zip(unique, unique[1:], strict=False))):
        duration = right.time - left.time
        if duration <= 0:
            continue
        interpolated = (
            f"{left.center_x:.5f}+"
            f"({right.center_x - left.center_x:.5f})*"
            f"(t-{left.time:.3f})/{duration:.3f}"
        )
        expression = f"if(lt(t\\,{right.time:.3f})\\,{interpolated}\\,{expression})"
    return expression


def render_clip(
    source: Path,
    output: Path,
    start: float,
    end: float,
    aspect: str = "9:16",
    framing: str = "center",
    *,
    framing_points: list[FramingPoint] | tuple[FramingPoint, ...] | None = None,
    caption_cues: list[CaptionCue | TrackedCaptionCue] | None = None,
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
            if framing_points:
                center = _framing_center_expression(framing_points)
                x = f"max(0\\,min(iw-ow\\,({center})*iw-ow/2))"
            else:
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
