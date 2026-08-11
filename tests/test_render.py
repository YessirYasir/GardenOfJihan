from pathlib import Path

import pytest

from garden_jihan.analysis.transcription import TranscriptSegment
from garden_jihan.media import render
from garden_jihan.media.render import CaptionCue, caption_cues_for_range, render_clip


def test_caption_cues_use_real_segment_timing_and_clip_to_manual_boundaries():
    segments = [
        TranscriptSegment(8.0, 12.0, "Before and inside"),
        TranscriptSegment(12.0, 16.5, "  Somali – العربية  "),
        TranscriptSegment(18.0, 22.0, "Inside and after"),
        TranscriptSegment(24.0, 25.0, "Outside"),
    ]

    assert caption_cues_for_range(segments, 10.0, 20.0) == [
        CaptionCue(0.0, 2.0, "Before and inside"),
        CaptionCue(2.0, 6.5, "Somali – العربية"),
        CaptionCue(8.0, 10.0, "Inside and after"),
    ]


def test_render_burns_escaped_unicode_ass_and_removes_temporary_file(tmp_path, monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        caption_path = next(tmp_path.glob("*.captions.ass"))
        captured["command"] = command
        captured["captions"] = caption_path.read_text(encoding="utf-8")
        captured["kwargs"] = kwargs

    monkeypatch.setattr(render, "ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(render.subprocess, "run", fake_run)
    output = tmp_path / "clip.mp4"

    render_clip(
        Path("source.mp4"),
        output,
        5.0,
        9.0,
        caption_cues=[CaptionCue(0.0, 2.25, "جيهان {\\bord99}\nline two")],
        caption_style="high-contrast",
        caption_position="top",
    )

    command = captured["command"]
    video_filter = command[command.index("-vf") + 1]
    assert "subtitles=filename=" in video_filter
    assert "Alignment" in captured["captions"]
    assert "｛＼bord99｝" in captured["captions"]
    assert r"{\bord99}" not in captured["captions"]
    assert r"\Nline two" in captured["captions"]
    assert "جيهان" in captured["captions"]
    assert captured["kwargs"] == {"check": True, "timeout": 600, "shell": False}
    assert not list(tmp_path.glob("*.captions.ass"))


def test_split_stack_applies_captions_after_compositing(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(render, "ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(
        render.subprocess,
        "run",
        lambda command, **_kwargs: captured.setdefault("command", command),
    )

    render_clip(
        Path("source.mp4"),
        tmp_path / "clip.mp4",
        0.0,
        3.0,
        framing="split-stack",
        caption_cues=[CaptionCue(0.0, 3.0, "Timed segment")],
    )

    command = captured["command"]
    complex_filter = command[command.index("-filter_complex") + 1]
    assert "vstack=inputs=2[stacked]" in complex_filter
    assert "[stacked]subtitles=filename=" in complex_filter
    assert complex_filter.endswith("[v]")


def test_render_rejects_unknown_caption_style(tmp_path):
    with pytest.raises(ValueError, match="Unsupported caption"):
        render_clip(
            Path("source.mp4"),
            tmp_path / "clip.mp4",
            0.0,
            2.0,
            caption_style="untrusted",
        )
