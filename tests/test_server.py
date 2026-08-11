from fastapi.testclient import TestClient

from garden_jihan.analysis.quran import AYAH_COUNTS
from garden_jihan.config import Settings
from garden_jihan.server import create_app


def test_health_and_security_headers(tmp_path):
    settings = Settings(app_data=tmp_path)
    app = create_app(port=8765, settings=settings, session_token="test-token")
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        response = client.get("/api/health")
        assert response.status_code == 200
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
        assert response.json()["available"] is False
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


def test_quran_reference_install_accepts_complete_tanzil_shape(tmp_path):
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
        assert response.status_code == 200
        data = response.json()
        assert data["available"] is True
        assert data["verses"] == 6236
        assert data["source"]["name"] == "Tanzil Project"
        status = client.get("/api/quran/reference").json()
        assert status["available"] is True
        assert status["verses"] == 6236


def test_export_boundary_model_rejects_backwards_range():
    from pydantic import ValidationError

    from garden_jihan.models import ClipBoundaryOverride

    try:
        ClipBoundaryOverride(start=10, end=9)
    except ValidationError:
        return
    raise AssertionError("Backwards clip boundary should be rejected")
