
import pytest

from garden_jihan.runtime import find_tool


def test_find_tool_honors_explicit_local_program(monkeypatch, tmp_path):
    program = tmp_path / "ffprobe.exe"
    program.write_bytes(b"program")
    monkeypatch.setenv("GOJ_FFPROBE_PATH", str(program))

    assert find_tool("ffprobe") == str(program.resolve())


def test_find_tool_fails_closed_for_missing_configured_program(monkeypatch, tmp_path):
    monkeypatch.setenv("GOJ_FFMPEG_PATH", str(tmp_path / "missing.exe"))

    with pytest.raises(RuntimeError, match="Configured ffmpeg program was not found"):
        find_tool("ffmpeg")
