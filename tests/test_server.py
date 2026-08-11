import threading
import time

from fastapi.testclient import TestClient

from garden_jihan.analysis import quran as quran_module
from garden_jihan.analysis.quran import AYAH_COUNTS, canonical_tanzil_sha256
from garden_jihan.analysis.transcription import TranscriptSegment
from garden_jihan.config import Settings
from garden_jihan.media.framing import FramingDecision, FramingPoint
from garden_jihan.models import AnalysisMode, ClipCandidate
from garden_jihan.server import create_app


def test_health_and_security_headers(tmp_path):
    settings = Settings(app_data=tmp_path)
    app = create_app(port=8765, settings=settings, session_token="test-token")
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert isinstance(response.json()["auto_framing_available"], bool)
        assert isinstance(response.json()["credential_protection_available"], bool)
        assert response.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_mutation_requires_origin_and_token(tmp_path):
    settings = Settings(app_data=tmp_path)
    app = create_app(port=8765, settings=settings, session_token="test-token")
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        payload = {"url": "https://youtube.com/watch?v=abcdefghijk"}
        response = client.post("/api/source/inspect", json=payload)
        assert response.status_code == 403


def test_quran_reference_status_starts_unavailable(tmp_path):
    settings = Settings(app_data=tmp_path)
    app = create_app(port=8765, settings=settings, session_token="test-token")
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        response = client.get("/api/quran/reference")
        assert response.status_code == 200
        assert response.json()["installed"] is False
        assert response.json()["available"] is False
        assert response.json()["verified"] is False
        assert response.json()["verses"] == 0


def test_quran_reference_install_requires_complete_reference(tmp_path):
    settings = Settings(app_data=tmp_path)
    app = create_app(port=8765, settings=settings, session_token="test-token")
    headers = {"origin": "http://127.0.0.1:8765", "x-goj-token": "test-token"}
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        response = client.post(
            "/api/quran/reference",
            headers=headers,
            files={"file": ("quran.txt", "1|1|بسم الله الرحمن الرحيم", "text/plain")},
        )
        assert response.status_code == 400
        assert "6236" in response.json()["detail"]


def test_quran_reference_install_rejects_complete_unreviewed_content(tmp_path):
    settings = Settings(app_data=tmp_path)
    app = create_app(port=8765, settings=settings, session_token="test-token")
    headers = {"origin": "http://127.0.0.1:8765", "x-goj-token": "test-token"}
    lines = []
    for surah, count in enumerate(AYAH_COUNTS, start=1):
        for ayah in range(1, count + 1):
            lines.append(f"{surah}|{ayah}|نص السورة {surah} الاية {ayah}")
    raw = "\n".join(lines)
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        response = client.post(
            "/api/quran/reference",
            headers=headers,
            files={"file": ("quran.txt", raw, "text/plain")},
        )
        assert response.status_code == 400
        assert "does not match the reviewed Tanzil" in response.json()["detail"]


def test_quran_reference_install_accepts_reviewed_hash(tmp_path, monkeypatch):
    settings = Settings(app_data=tmp_path)
    app = create_app(port=8765, settings=settings, session_token="test-token")
    headers = {"origin": "http://127.0.0.1:8765", "x-goj-token": "test-token"}
    lines = []
    for surah, count in enumerate(AYAH_COUNTS, start=1):
        for ayah in range(1, count + 1):
            lines.append(f"{surah}|{ayah}|نص السورة {surah} الاية {ayah}")
    raw = "\n".join(lines)
    monkeypatch.setattr(
        quran_module,
        "TANZIL_TRUSTED_CANONICAL_SHA256",
        frozenset({canonical_tanzil_sha256(raw)}),
    )
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        response = client.post(
            "/api/quran/reference",
            headers=headers,
            files={"file": ("quran.txt", raw, "text/plain")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["installed"] is True
        assert data["available"] is True
        assert data["verified"] is True
        assert data["verses"] == 6236
        assert data["source"]["name"] == "Tanzil Project"
        assert data["integrity"]["canonical_sha256"] == canonical_tanzil_sha256(raw)
        status = client.get("/api/quran/reference").json()
        assert status["available"] is True
        assert status["verified"] is True
        assert status["verses"] == 6236


def test_export_boundary_model_rejects_backwards_range():
    from pydantic import ValidationError

    from garden_jihan.models import ClipBoundaryOverride

    try:
        ClipBoundaryOverride(start=10, end=9)
    except ValidationError:
        return
    raise AssertionError("Backwards clip boundary should be rejected")


def _complete_export_job(app, tmp_path, mode=AnalysisMode.GENERAL):
    job = app.state.jobs.create_upload_job()
    job.status = "complete"
    job.source_path = tmp_path / "source.mp4"
    job.source_path.write_bytes(b"video")
    job.transcript_segments = [TranscriptSegment(8.0, 14.0, "A timed transcript segment.")]
    job.candidates = [
        ClipCandidate(
            id="candidate123",
            start=8.0,
            end=14.0,
            score=90,
            title="Strong moment",
            reasons=["Test"],
            transcript="A timed transcript segment.",
            mode=mode,
        )
    ]
    return job


def _await_export(client, response):
    assert response.status_code == 202
    export_id = response.json()["id"]
    for _attempt in range(200):
        status = client.get(f"/api/exports/{export_id}")
        assert status.status_code == 200
        data = status.json()
        if data["status"] in {"complete", "failed"}:
            return data
        time.sleep(0.01)
    raise AssertionError("Background export did not finish")


def test_export_passes_clipped_caption_cues_and_style(tmp_path, monkeypatch):
    settings = Settings(app_data=tmp_path)
    app = create_app(port=8765, settings=settings, session_token="test-token")
    job = _complete_export_job(app, tmp_path)
    captured = {}
    monkeypatch.setattr("garden_jihan.server.probe_media", lambda *_args: {"duration": 30.0})

    def fake_render(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        args[1].write_bytes(b"rendered")

    monkeypatch.setattr("garden_jihan.media.exporting.render_clip", fake_render)
    headers = {"origin": "http://127.0.0.1:8765", "x-goj-token": "test-token"}
    payload = {
        "candidate_ids": ["candidate123"],
        "captions": True,
        "caption_style": "high-contrast",
        "caption_position": "top",
        "boundaries": {"candidate123": {"start": 10.0, "end": 13.0}},
    }
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        response = client.post(f"/api/jobs/{job.id}/export", headers=headers, json=payload)
        export = _await_export(client, response)

    assert export["status"] == "complete"
    cue = captured["kwargs"]["caption_cues"][0]
    assert (cue.start, cue.end, cue.text) == (0.0, 3.0, "A timed transcript segment.")
    assert captured["kwargs"]["caption_style"] == "high-contrast"
    assert captured["kwargs"]["caption_position"] == "top"


def test_quran_export_captions_fail_closed_without_acoustic_timing(tmp_path, monkeypatch):
    settings = Settings(app_data=tmp_path)
    app = create_app(port=8765, settings=settings, session_token="test-token")
    job = _complete_export_job(app, tmp_path, AnalysisMode.QURAN)
    headers = {"origin": "http://127.0.0.1:8765", "x-goj-token": "test-token"}
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        response = client.post(
            f"/api/jobs/{job.id}/export",
            headers=headers,
            json={"candidate_ids": ["candidate123"], "captions": True},
        )

    assert response.status_code == 409
    assert "segment captions are disabled" in response.json()["detail"]


def test_quran_word_caption_export_requires_and_uses_supported_acoustic_alignment(
    tmp_path, monkeypatch
):
    settings = Settings(app_data=tmp_path)
    app = create_app(port=8765, settings=settings, session_token="test-token")
    job = _complete_export_job(app, tmp_path, AnalysisMode.QURAN)
    job.candidates[0].quran_match = {
        "status": "verified",
        "acoustic_timing_status": "supported",
        "word_alignment": [
            {
                "reference_word": "إِنَّا",
                "ayah": 1,
                "matched": True,
                "optional": False,
                "acoustic_start": 8.1,
                "acoustic_end": 9.0,
            },
            {
                "reference_word": "أَعْطَيْنَاكَ",
                "ayah": 1,
                "matched": True,
                "optional": False,
                "acoustic_start": 9.1,
                "acoustic_end": 10.2,
            },
        ],
    }
    captured = {}
    monkeypatch.setattr("garden_jihan.server.probe_media", lambda *_args: {"duration": 30.0})

    def fake_render(*args, **kwargs):
        captured.update(args=args, kwargs=kwargs)
        args[1].write_bytes(b"rendered")

    monkeypatch.setattr("garden_jihan.media.exporting.render_clip", fake_render)
    headers = {"origin": "http://127.0.0.1:8765", "x-goj-token": "test-token"}
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        unavailable = client.post(
            f"/api/jobs/{job.id}/export",
            headers=headers,
            json={"candidate_ids": ["candidate123"], "captions": True, "word_tracking": True},
        )
        assert unavailable.status_code == 202
        export = _await_export(client, unavailable)

    assert export["status"] == "complete"
    cue = captured["kwargs"]["caption_cues"][0]
    assert cue.words == ("إِنَّا", "أَعْطَيْنَاكَ")
    assert round(cue.start, 3) == 0.1


def test_quran_word_caption_export_fails_closed_when_acoustic_alignment_is_missing(
    tmp_path, monkeypatch
):
    settings = Settings(app_data=tmp_path)
    app = create_app(port=8765, settings=settings, session_token="test-token")
    job = _complete_export_job(app, tmp_path, AnalysisMode.QURAN)
    job.candidates[0].quran_match = {
        "status": "verified",
        "acoustic_timing_status": "uncertain",
        "word_alignment": [],
    }
    monkeypatch.setattr("garden_jihan.server.probe_media", lambda *_args: {"duration": 30.0})
    headers = {"origin": "http://127.0.0.1:8765", "x-goj-token": "test-token"}
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        response = client.post(
            f"/api/jobs/{job.id}/export",
            headers=headers,
            json={"candidate_ids": ["candidate123"], "captions": True, "word_tracking": True},
        )

    assert response.status_code == 409
    assert "remain disabled" in response.json()["detail"]


def test_export_runs_off_request_thread_and_rejects_duplicate_project_export(
    tmp_path, monkeypatch
):
    settings = Settings(app_data=tmp_path)
    app = create_app(port=8765, settings=settings, session_token="test-token")
    job = _complete_export_job(app, tmp_path)
    started = threading.Event()
    release = threading.Event()
    monkeypatch.setattr("garden_jihan.server.probe_media", lambda *_args: {"duration": 30.0})

    def blocking_render(*args, **_kwargs):
        args[1].write_bytes(b"rendered")
        started.set()
        assert release.wait(timeout=5)

    monkeypatch.setattr("garden_jihan.media.exporting.render_clip", blocking_render)
    headers = {"origin": "http://127.0.0.1:8765", "x-goj-token": "test-token"}
    payload = {"candidate_ids": ["candidate123"], "framing": "center"}

    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        response = client.post(f"/api/jobs/{job.id}/export", headers=headers, json=payload)
        assert response.status_code == 202
        assert started.wait(timeout=2)
        assert client.get("/api/health").status_code == 200
        duplicate = client.post(f"/api/jobs/{job.id}/export", headers=headers, json=payload)
        assert duplicate.status_code == 409
        assert "already running" in duplicate.json()["detail"]
        release.set()
        export = _await_export(client, response)

    assert export["status"] == "complete"


def test_auto_framing_passes_confident_points_and_reports_evidence(tmp_path, monkeypatch):
    settings = Settings(app_data=tmp_path)
    app = create_app(port=8765, settings=settings, session_token="test-token")
    job = _complete_export_job(app, tmp_path)
    captured = {}
    monkeypatch.setattr("garden_jihan.server.probe_media", lambda *_args: {"duration": 30.0})
    monkeypatch.setattr(
        "garden_jihan.media.exporting.analyze_auto_framing",
        lambda *_args: FramingDecision(
            applied="auto-speaking-face",
            confidence=0.86,
            message="Confident local audio-visual evidence.",
            points=(FramingPoint(0.0, 0.25), FramingPoint(6.0, 0.75)),
        ),
    )
    def fake_render(*args, **kwargs):
        captured.update(args=args, kwargs=kwargs)
        args[1].write_bytes(b"rendered")

    monkeypatch.setattr("garden_jihan.media.exporting.render_clip", fake_render)
    headers = {"origin": "http://127.0.0.1:8765", "x-goj-token": "test-token"}

    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        response = client.post(
            f"/api/jobs/{job.id}/export",
            headers=headers,
            json={"candidate_ids": ["candidate123"], "framing": "auto"},
        )
        export = _await_export(client, response)

    assert export["status"] == "complete"
    assert captured["args"][5] == "center"
    assert captured["kwargs"]["framing_points"] == (
        FramingPoint(0.0, 0.25),
        FramingPoint(6.0, 0.75),
    )
    assert export["files"][0]["framing"] == {
        "requested": "auto",
        "applied": "auto-speaking-face",
        "confidence": 0.86,
        "message": "Confident local audio-visual evidence.",
    }


def test_auto_framing_non_vertical_export_reports_center_fallback(tmp_path, monkeypatch):
    settings = Settings(app_data=tmp_path)
    app = create_app(port=8765, settings=settings, session_token="test-token")
    job = _complete_export_job(app, tmp_path)
    monkeypatch.setattr("garden_jihan.server.probe_media", lambda *_args: {"duration": 30.0})
    def fake_render(*args, **_kwargs):
        args[1].write_bytes(b"rendered")

    monkeypatch.setattr("garden_jihan.media.exporting.render_clip", fake_render)
    headers = {"origin": "http://127.0.0.1:8765", "x-goj-token": "test-token"}

    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        response = client.post(
            f"/api/jobs/{job.id}/export",
            headers=headers,
            json={
                "candidate_ids": ["candidate123"],
                "framing": "auto",
                "aspect": "1:1",
            },
        )
        export = _await_export(client, response)

    framing = export["files"][0]["framing"]
    assert framing["applied"] == "center"
    assert framing["confidence"] == 0.0
    assert "only to vertical 9:16" in framing["message"]


def test_project_review_list_resume_and_remove_are_local_and_validated(tmp_path):
    settings = Settings(app_data=tmp_path)
    app = create_app(port=8765, settings=settings, session_token="test-token")
    job = _complete_export_job(app, tmp_path)
    job_folder = settings.jobs_dir / job.id
    job.source_path = job_folder / "upload.mp4"
    job.source_path.write_bytes(b"video")
    headers = {"origin": "http://127.0.0.1:8765", "x-goj-token": "test-token"}
    payload = {
        "name": "My local project",
        "selected_ids": ["candidate123"],
        "boundaries": {"candidate123": {"start": 9.0, "end": 13.5}},
        "aspect": "1:1",
        "framing": "center",
        "captions": True,
        "caption_style": "minimal",
        "caption_position": "middle",
    }

    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        saved = client.put(f"/api/jobs/{job.id}/project", headers=headers, json=payload)
        projects = client.get("/api/projects")
        resumed = client.get(f"/api/jobs/{job.id}")
        removed = client.delete(f"/api/projects/{job.id}", headers=headers)

    assert saved.status_code == 200
    assert saved.json()["project"]["name"] == "My local project"
    assert projects.json()["projects"][0]["selected_count"] == 1
    assert resumed.json()["project"]["boundaries"]["candidate123"] == {
        "start": 9.0,
        "end": 13.5,
    }
    assert removed.json() == {"removed": True}
    assert not job_folder.exists()


def test_publishing_status_is_honest_about_youtube_and_tiktok_gates(tmp_path):
    settings = Settings(app_data=tmp_path)
    app = create_app(port=8765, settings=settings, session_token="test-token")

    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        response = client.get("/api/publish/status")

    assert response.status_code == 200
    assert response.json()["youtube"] == {"configured": False, "connected": False, "scope": ""}
    assert response.json()["tiktok"]["available"] is False
    assert "audited Content Posting API" in response.json()["tiktok"]["message"]


def test_youtube_connect_uses_loopback_and_callback_state_handler(tmp_path, monkeypatch):
    settings = Settings(app_data=tmp_path)
    app = create_app(port=8765, settings=settings, session_token="test-token")
    captured = {}

    def fake_start_authorization(redirect):
        captured["redirect"] = redirect
        return "https://accounts.google.com/o/oauth2/v2/auth?safe=1"

    monkeypatch.setattr(
        app.state.youtube_publisher,
        "start_authorization",
        fake_start_authorization,
    )
    monkeypatch.setattr(
        app.state.youtube_publisher,
        "complete_authorization",
        lambda state, code: captured.update(state=state, code=code),
    )
    headers = {"origin": "http://127.0.0.1:8765", "x-goj-token": "test-token"}

    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        connect = client.post("/api/publish/youtube/connect", headers=headers)
        callback = client.get("/?state=safe-state&code=safe-code")

    assert connect.status_code == 200
    assert captured["redirect"] == "http://127.0.0.1:8765"
    assert captured["state"] == "safe-state"
    assert captured["code"] == "safe-code"
    assert "upload-only permission" in callback.text


def test_youtube_publish_accepts_only_a_real_project_export_and_reports_completion(
    tmp_path,
    monkeypatch,
):
    settings = Settings(app_data=tmp_path)
    app = create_app(port=8765, settings=settings, session_token="test-token")
    job = _complete_export_job(app, tmp_path)
    output = settings.jobs_dir / job.id / "output"
    output.mkdir()
    (output / "clip_01_candidate123.mp4").write_bytes(b"rendered-video")
    monkeypatch.setattr(
        app.state.youtube_publisher,
        "status",
        lambda: {"configured": True, "connected": True, "scope": "upload"},
    )
    monkeypatch.setattr(app.state.youtube_publisher, "upload", lambda *_args: "youtube-video-id")
    headers = {"origin": "http://127.0.0.1:8765", "x-goj-token": "test-token"}
    payload = {
        "filename": "clip_01_candidate123.mp4",
        "title": "Garden clip",
        "privacy": "private",
        "made_for_kids": False,
        "contains_synthetic_media": False,
    }

    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        missing_disclosure = client.post(
            f"/api/jobs/{job.id}/publish/youtube",
            headers=headers,
            json={key: value for key, value in payload.items() if key != "made_for_kids"},
        )
        started = client.post(
            f"/api/jobs/{job.id}/publish/youtube",
            headers=headers,
            json=payload,
        )
        assert started.status_code == 200
        for _attempt in range(50):
            status = client.get(
                f"/api/publish/youtube/uploads/{started.json()['id']}"
            ).json()
            if status["status"] == "complete":
                break
            time.sleep(0.01)

    assert missing_disclosure.status_code == 422
    assert status["progress"] == 100
    assert status["video_id"] == "youtube-video-id"
    assert status["url"] == "https://www.youtube.com/watch?v=youtube-video-id"
