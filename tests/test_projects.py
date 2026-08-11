import json

from garden_jihan.analysis.signals import MediaSignals, TimedValue
from garden_jihan.analysis.transcription import TranscriptSegment
from garden_jihan.config import Settings
from garden_jihan.jobs import JobManager
from garden_jihan.models import AnalysisMode, ClipBoundaryOverride, ClipCandidate, ProjectReview


def _completed_project(manager: JobManager):
    job = manager.create_upload_job()
    job.status = "complete"
    job.progress = 100
    job.message = "Found 1 clip candidate"
    job.ranking_method = "local_multilingual_embeddings"
    job.ranking_message = "Local multilingual meaning model active"
    job.source_path = manager.settings.jobs_dir / job.id / "upload.mp4"
    job.source_path.write_bytes(b"video")
    job.candidates = [
        ClipCandidate(
            id="clip123",
            start=4.0,
            end=18.0,
            score=91,
            title="Xilli wanaagsan",
            reasons=["Complete thought"],
            transcript="جيهان iyo Soomaali",
            mode=AnalysisMode.SOMALI,
        )
    ]
    job.transcript_segments = [TranscriptSegment(4.0, 18.0, "جيهان iyo Soomaali")]
    job.media_signals = MediaSignals(
        audio_energy=[TimedValue(4.0, 6.0, 0.8)],
        scene_times=[7.5],
    )
    return job


def test_completed_project_round_trips_local_review_and_analysis_state(tmp_path):
    settings = Settings(app_data=tmp_path)
    manager = JobManager(settings)
    job = _completed_project(manager)
    review = ProjectReview(
        name="Draft name",
        selected_ids=["clip123"],
        boundaries={"clip123": ClipBoundaryOverride(start=5.0, end=17.0)},
        aspect="9:16",
        framing="auto",
        captions=True,
        caption_style="high-contrast",
        caption_position="top",
    )
    manager.update_project(job.id, review)
    manager.update_project(job.id, review.model_copy(update={"name": "Sheeko Soomaaliyeed"}))

    restored_manager = JobManager(settings)
    restored = restored_manager.get(job.id)

    assert restored.project.name == "Sheeko Soomaaliyeed"
    assert restored.project.selected_ids == ["clip123"]
    assert restored.project.boundaries["clip123"].start == 5.0
    assert restored.candidates[0].transcript == "جيهان iyo Soomaali"
    assert restored.transcript_segments[0].text == "جيهان iyo Soomaali"
    assert restored.media_signals.audio_energy[0].value == 0.8
    assert restored.source_path == job.source_path.resolve()
    assert restored_manager.list_projects()[0]["source_available"] is True


def test_restored_project_rejects_source_path_escape(tmp_path):
    settings = Settings(app_data=tmp_path)
    manager = JobManager(settings)
    job = _completed_project(manager)
    manager.update_project(job.id, ProjectReview(name="Safe local project"))
    manifest_path = settings.jobs_dir / job.id / "project.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source"] = "../../outside.mp4"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    restored = JobManager(settings).get(job.id)

    assert restored.source_path is None
    assert JobManager(settings).list_projects()[0]["source_available"] is False


def test_project_review_rejects_unknown_candidate_before_writing(tmp_path):
    manager = JobManager(Settings(app_data=tmp_path))
    job = _completed_project(manager)

    try:
        manager.update_project(job.id, ProjectReview(name="Project", selected_ids=["unknown"]))
    except ValueError as exc:
        assert "Unknown selected clip" in str(exc)
    else:
        raise AssertionError("Unknown candidate should be rejected")

    assert not (manager.settings.jobs_dir / job.id / "project.json").exists()
