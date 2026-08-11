import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from garden_jihan.publish import youtube as youtube_module
from garden_jihan.publish.credentials import ProtectedJsonStore
from garden_jihan.publish.youtube import (
    PublishingNotConfigured,
    YouTubePublisher,
    YouTubePublishingError,
    YouTubeUploadMetadata,
    parse_desktop_client,
)

CLIENT_JSON = b"""{
  "installed": {
    "client_id": "garden-test.apps.googleusercontent.com",
    "client_secret": "desktop-client-value",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token"
  }
}"""


class TestProtector:
    def protect(self, value: bytes) -> bytes:
        return b"protected:" + bytes(byte ^ 0xA5 for byte in value)

    def unprotect(self, value: bytes) -> bytes:
        if not value.startswith(b"protected:"):
            raise ValueError("not protected")
        return bytes(byte ^ 0xA5 for byte in value.removeprefix(b"protected:"))


def _publisher(tmp_path: Path) -> YouTubePublisher:
    publisher = YouTubePublisher(
        ProtectedJsonStore(tmp_path / "youtube.bin", protector=TestProtector())
    )
    publisher.install_client(CLIENT_JSON)
    return publisher


def test_desktop_client_requires_official_google_endpoints():
    assert parse_desktop_client(CLIENT_JSON).client_id.endswith(".apps.googleusercontent.com")
    hostile = CLIENT_JSON.replace(
        b"https://oauth2.googleapis.com/token",
        b"https://example.com/token",
    )

    with pytest.raises(ValueError, match="official Google endpoint"):
        parse_desktop_client(hostile)
    with pytest.raises(ValueError, match="Desktop app"):
        parse_desktop_client(b'{"web":{"client_id":"x"}}')


def test_oauth_uses_loopback_state_pkce_and_protected_offline_tokens(tmp_path, monkeypatch):
    publisher = _publisher(tmp_path)
    captured = {}

    def fake_post(fields):
        captured.update(fields)
        return {
            "access_token": "access-value",
            "refresh_token": "refresh-value",
            "expires_in": 3600,
        }

    monkeypatch.setattr(publisher, "_post_form", fake_post)
    authorization_url = publisher.start_authorization(
        "http://127.0.0.1:8765"
    )
    query = parse_qs(urlsplit(authorization_url).query)

    assert query["scope"] == ["https://www.googleapis.com/auth/youtube.upload"]
    assert query["access_type"] == ["offline"]
    assert query["code_challenge_method"] == ["S256"]
    assert len(query["code_challenge"][0]) >= 43

    publisher.complete_authorization(query["state"][0], "authorization-code")

    assert captured["code_verifier"]
    assert captured["redirect_uri"].startswith("http://127.0.0.1:")
    assert publisher.status()["connected"] is True
    on_disk = (tmp_path / "youtube.bin").read_bytes()
    assert b"refresh-value" not in on_disk
    assert b"desktop-client-value" not in on_disk


def test_oauth_rejects_mismatched_state_before_token_exchange(tmp_path, monkeypatch):
    publisher = _publisher(tmp_path)
    publisher.start_authorization("http://127.0.0.1:8765")
    called = False

    def fake_post(_fields):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(publisher, "_post_form", fake_post)

    with pytest.raises(YouTubePublishingError, match="did not match"):
        publisher.complete_authorization("wrong-state", "code")
    assert called is False


def test_upload_uses_contiguous_resumable_chunks_and_returns_video_id(tmp_path, monkeypatch):
    publisher = _publisher(tmp_path)
    stored = publisher.store.load()
    stored["tokens"] = {
        "access_token": "access-value",
        "refresh_token": "refresh-value",
        "expires_at": 9_999_999_999,
    }
    publisher.store.save(stored)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x" * 600_000)
    calls = []
    progress = []

    monkeypatch.setattr(
        publisher,
        "_start_session",
        lambda *_args: "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=safe",
    )

    def fake_put(_url, _token, data, content_range):
        calls.append((len(data), content_range))
        if len(calls) == 1:
            return 308, {"Range": "bytes=0-262143"}, b""
        if len(calls) == 2:
            return 308, {"Range": "bytes=0-524287"}, b""
        return 201, {}, b'{"id":"official-video-id"}'

    monkeypatch.setattr(publisher, "_put", fake_put)

    video_id = publisher.upload(
        video,
        YouTubeUploadMetadata(title="Garden clip", privacy="private"),
        lambda sent, total: progress.append((sent, total)),
        chunk_size=256 * 1024,
    )

    assert video_id == "official-video-id"
    assert calls == [
        (262_144, "bytes 0-262143/600000"),
        (262_144, "bytes 262144-524287/600000"),
        (75_712, "bytes 524288-599999/600000"),
    ]
    assert progress[-1] == (600_000, 600_000)


def test_resumable_session_sends_required_metadata_and_disclosures(tmp_path, monkeypatch):
    publisher = _publisher(tmp_path)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"rendered")
    captured = {}

    class Response:
        status = 200
        headers = {
            "Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=safe"
        }

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_open(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(youtube_module, "urlopen", fake_open)

    session = publisher._start_session(
        video,
        YouTubeUploadMetadata(
            title="Garden clip",
            description="Local export",
            privacy="unlisted",
            made_for_kids=False,
            contains_synthetic_media=True,
        ),
        "access-value",
    )

    body = json.loads(captured["request"].data)
    assert session.startswith("https://www.googleapis.com/upload/")
    assert captured["request"].get_header("Authorization") == "Bearer access-value"
    assert captured["request"].get_header("X-upload-content-length") == "8"
    assert body["status"] == {
        "privacyStatus": "unlisted",
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": True,
    }


def test_unconfigured_publisher_and_untrusted_session_fail_closed(tmp_path):
    publisher = YouTubePublisher(
        ProtectedJsonStore(tmp_path / "youtube.bin", protector=TestProtector())
    )

    with pytest.raises(PublishingNotConfigured):
        publisher.start_authorization("http://127.0.0.1:8765/callback")
    with pytest.raises(YouTubePublishingError, match="invalid resumable"):
        publisher._validated_session_url("https://evil.example/upload")


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI is the production credential store")
def test_windows_dpapi_store_round_trip_does_not_write_plaintext(tmp_path):
    store = ProtectedJsonStore(tmp_path / "youtube.bin")
    expected = "highly-sensitive-token"
    store.save({"tokens": {"refresh_token": expected}})

    assert store.load()["tokens"]["refresh_token"] == expected
    assert expected.encode() not in (tmp_path / "youtube.bin").read_bytes()
