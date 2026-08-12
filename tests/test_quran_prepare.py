import importlib.util
from pathlib import Path


def _load_script():
    path = Path(__file__).parents[1] / "scripts" / "prepare-quran-reference.py"
    spec = importlib.util.spec_from_file_location("prepare_quran_reference", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verified_quran_download_is_cached_at_the_intended_file(monkeypatch, tmp_path):
    module = _load_script()
    payload = "reviewed text"
    requested = []

    class FakeResponse:
        status = 200

        def read(self, _limit):
            return payload.encode()

    class FakeConnection:
        def __init__(self, host, timeout):
            assert (host, timeout) == ("tanzil.net", 60)

        def request(self, method, target):
            requested.append((method, target))

        def getresponse(self):
            return FakeResponse()

        def close(self):
            pass

    monkeypatch.setattr(module.http.client, "HTTPSConnection", FakeConnection)
    monkeypatch.setattr(module, "canonical_tanzil_sha256", lambda _text: "trusted")
    monkeypatch.setattr(module, "TANZIL_TRUSTED_CANONICAL_SHA256", frozenset({"trusted"}))

    assert module._verified_text(tmp_path) == payload
    assert (tmp_path / "quran-simple-1.1.txt").read_text(encoding="utf-8") == payload
    assert requested == [
        (
            "GET",
            "/pub/download/index.php?marks=true&sajdah=true&tatweel=true&"
            "quranType=simple&outType=txt-2&agree=true",
        )
    ]
