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
