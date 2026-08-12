import pytest

from garden_jihan import launcher


def test_requested_port_uses_valid_environment_port(monkeypatch):
    monkeypatch.setenv("GOJ_PORT", "8765")
    assert launcher._requested_port() == 8765


def test_requested_port_rejects_invalid_value(monkeypatch):
    monkeypatch.setenv("GOJ_PORT", "not-a-port")
    with pytest.raises(RuntimeError):
        launcher._requested_port()


def test_requested_port_rejects_privileged_port(monkeypatch):
    monkeypatch.setenv("GOJ_PORT", "80")
    with pytest.raises(RuntimeError):
        launcher._requested_port()


def test_browser_waits_for_healthy_local_interface(monkeypatch):
    opened = []

    class HealthyConnection:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("127.0.0.1", 8765, 0.5)

        def request(self, method, path):
            assert (method, path) == ("GET", "/api/health")

        def getresponse(self):
            return type("Response", (), {"status": 200})()

        def close(self):
            pass

    monkeypatch.setattr(launcher.http.client, "HTTPConnection", HealthyConnection)
    monkeypatch.setattr(launcher.webbrowser, "open", opened.append)

    launcher._open_ui_when_ready(8765, timeout_seconds=0.1)

    assert opened == ["http://127.0.0.1:8765/"]
