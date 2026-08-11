from fastapi.testclient import TestClient

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
