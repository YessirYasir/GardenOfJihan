
import pytest

from garden_jihan.config import default_app_data
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


def test_default_app_data_uses_macos_application_support(monkeypatch, tmp_path):
    monkeypatch.delenv("GOJ_APP_DATA", raising=False)
    monkeypatch.setattr("garden_jihan.config.sys.platform", "darwin")
    monkeypatch.setattr("garden_jihan.config.Path.home", lambda: tmp_path)

    assert default_app_data() == tmp_path / "Library" / "Application Support" / "GardenOfJihan"


def test_default_app_data_honors_explicit_override(monkeypatch, tmp_path):
    target = tmp_path / "private-garden"
    monkeypatch.setenv("GOJ_APP_DATA", str(target))

    assert default_app_data() == target
