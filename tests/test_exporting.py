import threading
import time

import pytest

from garden_jihan.analysis.signals import MediaSignals
from garden_jihan.media.exporting import (
    ExportManager,
    ExportPlan,
    PreparedExportClip,
)


def _plan(tmp_path, *, project_id="project1", filenames=("clip_01_one.mp4",)):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    return ExportPlan(
        project_id=project_id,
        source=source,
        output_dir=tmp_path / project_id / "output",
        media_signals=MediaSignals(),
        aspect="9:16",
        framing="center",
        caption_style="garden",
        caption_position="bottom",
        clips=tuple(
            PreparedExportClip(
                candidate_id=f"candidate{index}",
                filename=filename,
                start=float(index),
                end=float(index + 1),
            )
            for index, filename in enumerate(filenames, start=1)
        ),
    )


def _wait(manager, export_id):
    for _attempt in range(200):
        data = manager.public(export_id)
        if data["status"] in {"complete", "failed"}:
            return data
        time.sleep(0.01)
    raise AssertionError("Export did not finish")


def test_background_export_reports_progress_before_publishing_files(tmp_path, monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def fake_render(_source, output, *_args, **_kwargs):
        output.write_bytes(b"complete mp4")
        started.set()
        assert release.wait(timeout=2)

    monkeypatch.setattr("garden_jihan.media.exporting.render_clip", fake_render)
    manager = ExportManager(max_workers=1)
    export = manager.submit(_plan(tmp_path))

    assert started.wait(timeout=2)
    in_progress = manager.public(export.id)
    assert in_progress["status"] == "rendering"
    assert in_progress["files"] == []
    assert not (tmp_path / "project1" / "output" / "clip_01_one.mp4").exists()

    release.set()
    complete = _wait(manager, export.id)
    assert complete["status"] == "complete"
    assert complete["progress"] == 100
    assert complete["files"][0]["name"] == "clip_01_one.mp4"
    assert (tmp_path / "project1" / "output" / "clip_01_one.mp4").read_bytes() == b"complete mp4"


def test_failed_multi_clip_export_preserves_old_outputs_and_removes_partial_files(
    tmp_path, monkeypatch
):
    plan = _plan(tmp_path, filenames=("clip_01_one.mp4", "clip_02_two.mp4"))
    plan.output_dir.mkdir(parents=True)
    previous = plan.output_dir / "clip_01_one.mp4"
    previous.write_bytes(b"previous valid export")
    calls = 0

    def fake_render(_source, output, *_args, **_kwargs):
        nonlocal calls
        calls += 1
        output.write_bytes(b"partial")
        if calls == 2:
            raise RuntimeError(f"private source path: {plan.source}")

    monkeypatch.setattr("garden_jihan.media.exporting.render_clip", fake_render)
    manager = ExportManager(max_workers=1)
    export = manager.submit(plan)
    failed = _wait(manager, export.id)

    assert failed["status"] == "failed"
    assert failed["files"] == []
    assert str(plan.source) not in failed["error"]
    assert previous.read_bytes() == b"previous valid export"
    assert not (plan.output_dir / "clip_02_two.mp4").exists()
    assert not (plan.output_dir / ".exports" / export.id).exists()


def test_export_manager_bounds_queue_and_rejects_unsafe_names(tmp_path, monkeypatch):
    release = threading.Event()

    def blocking_render(_source, output, *_args, **_kwargs):
        output.write_bytes(b"rendered")
        assert release.wait(timeout=2)

    monkeypatch.setattr("garden_jihan.media.exporting.render_clip", blocking_render)
    manager = ExportManager(max_workers=1, max_pending=2)
    first = manager.submit(_plan(tmp_path, project_id="first"))
    manager.submit(_plan(tmp_path, project_id="second"))

    with pytest.raises(ValueError, match="queue is full"):
        manager.submit(_plan(tmp_path, project_id="third"))
    with pytest.raises(ValueError, match="invalid output filename"):
        manager.submit(_plan(tmp_path, project_id="unsafe", filenames=("../escape.mp4",)))

    release.set()
    assert _wait(manager, first.id)["status"] == "complete"


def test_non_vertical_manual_edge_framing_reports_center_fallback(tmp_path, monkeypatch):
    plan = _plan(tmp_path)
    plan = ExportPlan(
        project_id=plan.project_id,
        source=plan.source,
        output_dir=plan.output_dir,
        media_signals=plan.media_signals,
        aspect="1:1",
        framing="right",
        caption_style=plan.caption_style,
        caption_position=plan.caption_position,
        clips=plan.clips,
    )
    captured = {}

    def fake_render(*args, **_kwargs):
        captured["framing"] = args[5]
        args[1].write_bytes(b"rendered")

    monkeypatch.setattr("garden_jihan.media.exporting.render_clip", fake_render)
    manager = ExportManager(max_workers=1)
    export = _wait(manager, manager.submit(plan).id)

    assert captured["framing"] == "center"
    framing = export["files"][0]["framing"]
    assert framing["requested"] == "right"
    assert framing["applied"] == "center"
    assert "only to vertical 9:16" in framing["message"]
