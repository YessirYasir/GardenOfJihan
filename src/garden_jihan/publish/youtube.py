from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from garden_jihan.publish.credentials import ProtectedJsonStore

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105  # nosec B105
UPLOAD_ENDPOINT = "https://www.googleapis.com/upload/youtube/v3/videos"
UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
RETRIABLE_STATUS = {500, 502, 503, 504}
CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9._-]+\.apps\.googleusercontent\.com$")
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,32}$")


class YouTubePublishingError(RuntimeError):
    pass


class PublishingNotConfigured(YouTubePublishingError):
    pass


@dataclass(frozen=True, slots=True)
class YouTubeClientConfig:
    client_id: str
    client_secret: str


@dataclass(frozen=True, slots=True)
class OAuthAttempt:
    state: str
    verifier: str
    redirect_uri: str
    expires_at: float


@dataclass(frozen=True, slots=True)
class YouTubeUploadMetadata:
    title: str
    description: str = ""
    privacy: str = "private"
    made_for_kids: bool = False
    contains_synthetic_media: bool = False

    def validate(self) -> None:
        if not 1 <= len(self.title.strip()) <= 100:
            raise ValueError("YouTube title must be between 1 and 100 characters")
        if len(self.description) > 5000:
            raise ValueError("YouTube description cannot exceed 5000 characters")
        if self.privacy not in {"private", "unlisted", "public"}:
            raise ValueError("Unsupported YouTube privacy setting")


def _urlsafe_sha256(value: str) -> str:
    digest = hashlib.sha256(value.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _safe_google_error(body: bytes, status: int) -> YouTubePublishingError:
    message = ""
    try:
        payload = json.loads(body[:16_384].decode("utf-8", errors="replace"))
        error = payload.get("error", {})
        if isinstance(error, dict):
            message = str(error.get("message") or error.get("error_description") or "")
        elif isinstance(error, str):
            message = error
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        pass
    clean = " ".join(message.split())[:400]
    return YouTubePublishingError(
        f"YouTube API request failed ({status}){f': {clean}' if clean else ''}"
    )


def _video_id_from_response(body: bytes) -> str:
    try:
        video_id = str(json.loads(body.decode())["id"])
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise YouTubePublishingError(
            "YouTube completed the upload without a video identifier"
        ) from exc
    if not VIDEO_ID_RE.fullmatch(video_id):
        raise YouTubePublishingError("YouTube returned an invalid video identifier")
    return video_id


def parse_desktop_client(raw: bytes) -> YouTubeClientConfig:
    if len(raw) > 64 * 1024:
        raise ValueError("YouTube OAuth client file is unexpectedly large")
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
        installed = payload["installed"]
        client_id = str(installed["client_id"])
        client_secret = str(installed.get("client_secret") or "")
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Choose a Google OAuth Desktop app client JSON file") from exc
    if not CLIENT_ID_RE.fullmatch(client_id):
        raise ValueError("Google OAuth Desktop client ID is invalid")
    if installed.get("token_uri") not in {None, TOKEN_ENDPOINT}:
        raise ValueError("OAuth client token endpoint is not the official Google endpoint")
    auth_uri = installed.get("auth_uri")
    if auth_uri not in {None, AUTHORIZATION_ENDPOINT, "https://accounts.google.com/o/oauth2/auth"}:
        raise ValueError("OAuth client authorization endpoint is not the official Google endpoint")
    return YouTubeClientConfig(client_id=client_id, client_secret=client_secret)


class YouTubePublisher:
    """Official OAuth + resumable upload client for the local Windows application."""

    def __init__(self, store: ProtectedJsonStore):
        self.store = store
        self._oauth_attempt: OAuthAttempt | None = None

    def _data(self) -> dict[str, Any]:
        return self.store.load()

    def _client(self) -> YouTubeClientConfig:
        client = self._data().get("client")
        if not isinstance(client, dict):
            raise PublishingNotConfigured(
                "Install an approved Google OAuth Desktop app client before connecting YouTube"
            )
        try:
            return YouTubeClientConfig(
                client_id=str(client["client_id"]),
                client_secret=str(client.get("client_secret") or ""),
            )
        except KeyError as exc:
            raise PublishingNotConfigured("YouTube OAuth client configuration is incomplete") from exc

    def status(self) -> dict[str, bool | str]:
        data = self._data()
        configured = isinstance(data.get("client"), dict)
        tokens = data.get("tokens")
        connected = isinstance(tokens, dict) and bool(tokens.get("refresh_token"))
        return {
            "configured": configured,
            "connected": connected,
            "scope": UPLOAD_SCOPE if connected else "",
        }

    def install_client(self, raw: bytes) -> None:
        client = parse_desktop_client(raw)
        self.store.save(
            {
                "client": {
                    "client_id": client.client_id,
                    "client_secret": client.client_secret,
                }
            }
        )
        self._oauth_attempt = None

    @staticmethod
    def _validate_redirect_uri(redirect_uri: str) -> None:
        parsed = urlsplit(redirect_uri)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.username
            or parsed.password
            or parsed.fragment
            or not parsed.port
        ):
            raise ValueError("YouTube OAuth redirect must use this app's loopback address")

    def start_authorization(self, redirect_uri: str) -> str:
        client = self._client()
        self._validate_redirect_uri(redirect_uri)
        verifier = secrets.token_urlsafe(64)[:96]
        attempt = OAuthAttempt(
            state=secrets.token_urlsafe(32),
            verifier=verifier,
            redirect_uri=redirect_uri,
            expires_at=time.time() + 600,
        )
        self._oauth_attempt = attempt
        query = urlencode(
            {
                "client_id": client.client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": UPLOAD_SCOPE,
                "access_type": "offline",
                "prompt": "consent",
                "state": attempt.state,
                "code_challenge": _urlsafe_sha256(verifier),
                "code_challenge_method": "S256",
            }
        )
        return f"{AUTHORIZATION_ENDPOINT}?{query}"

    @staticmethod
    def _post_form(fields: dict[str, str]) -> dict[str, Any]:
        request = Request(  # noqa: S310
            TOKEN_ENDPOINT,
            data=urlencode(fields).encode(),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Garden-of-Jihan/0.1",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310  # nosec B310
                return json.loads(response.read(64 * 1024).decode())
        except HTTPError as exc:
            raise _safe_google_error(exc.read(16_384), exc.code) from exc
        except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
            raise YouTubePublishingError("Could not reach Google's OAuth token endpoint") from exc

    def complete_authorization(self, state: str, code: str) -> None:
        attempt = self._oauth_attempt
        self._oauth_attempt = None
        if (
            not attempt
            or attempt.expires_at < time.time()
            or not hmac.compare_digest(attempt.state, state)
        ):
            raise YouTubePublishingError("YouTube authorization state expired or did not match")
        if not code or len(code) > 4096:
            raise YouTubePublishingError("YouTube did not return a valid authorization code")
        client = self._client()
        fields = {
            "client_id": client.client_id,
            "code": code,
            "code_verifier": attempt.verifier,
            "grant_type": "authorization_code",
            "redirect_uri": attempt.redirect_uri,
        }
        if client.client_secret:
            fields["client_secret"] = client.client_secret
        tokens = self._post_form(fields)
        access_token = str(tokens.get("access_token") or "")
        refresh_token = str(tokens.get("refresh_token") or "")
        if not access_token or not refresh_token:
            raise YouTubePublishingError(
                "Google authorization did not return offline upload access; reconnect and consent again"
            )
        data = self._data()
        data["tokens"] = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": time.time() + max(60, int(tokens.get("expires_in") or 3600)) - 60,
            "scope": str(tokens.get("scope") or UPLOAD_SCOPE),
        }
        self.store.save(data)

    def disconnect(self) -> None:
        data = self._data()
        data.pop("tokens", None)
        self.store.save(data) if data else self.store.clear()
        self._oauth_attempt = None

    def _access_token(self) -> str:
        data = self._data()
        tokens = data.get("tokens")
        if not isinstance(tokens, dict) or not tokens.get("refresh_token"):
            raise PublishingNotConfigured("Connect a YouTube account before publishing")
        access_token = str(tokens.get("access_token") or "")
        if access_token and float(tokens.get("expires_at") or 0) > time.time() + 90:
            return access_token
        client = self._client()
        fields = {
            "client_id": client.client_id,
            "refresh_token": str(tokens["refresh_token"]),
            "grant_type": "refresh_token",
        }
        if client.client_secret:
            fields["client_secret"] = client.client_secret
        refreshed = self._post_form(fields)
        access_token = str(refreshed.get("access_token") or "")
        if not access_token:
            raise YouTubePublishingError("Google did not return a refreshed access token")
        tokens["access_token"] = access_token
        tokens["expires_at"] = (
            time.time() + max(60, int(refreshed.get("expires_in") or 3600)) - 60
        )
        data["tokens"] = tokens
        self.store.save(data)
        return access_token

    @staticmethod
    def _validated_session_url(value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.hostname != "www.googleapis.com":
            raise YouTubePublishingError("YouTube returned an invalid resumable upload address")
        return value

    @staticmethod
    def _response_body(response, limit: int = 1024 * 1024) -> bytes:
        return response.read(limit)

    def _start_session(
        self,
        path: Path,
        metadata: YouTubeUploadMetadata,
        access_token: str,
    ) -> str:
        body = json.dumps(
            {
                "snippet": {
                    "title": metadata.title.strip(),
                    "description": metadata.description,
                    "categoryId": "22",
                },
                "status": {
                    "privacyStatus": metadata.privacy,
                    "selfDeclaredMadeForKids": metadata.made_for_kids,
                    "containsSyntheticMedia": metadata.contains_synthetic_media,
                },
            },
            separators=(",", ":"),
        ).encode()
        request = Request(  # noqa: S310
            f"{UPLOAD_ENDPOINT}?uploadType=resumable&part=snippet,status&notifySubscribers=false",
            data=body,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "Content-Length": str(len(body)),
                "X-Upload-Content-Length": str(path.stat().st_size),
                "X-Upload-Content-Type": "video/mp4",
                "User-Agent": "Garden-of-Jihan/0.1",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310  # nosec B310
                location = response.headers.get("Location", "")
        except HTTPError as exc:
            raise _safe_google_error(exc.read(16_384), exc.code) from exc
        except (OSError, URLError) as exc:
            raise YouTubePublishingError("Could not start the YouTube resumable upload") from exc
        return self._validated_session_url(location)

    @staticmethod
    def _range_offset(headers, default: int) -> int:
        value = headers.get("Range", "")
        match = re.fullmatch(r"bytes=0-(\d+)", value)
        return int(match.group(1)) + 1 if match else default

    @staticmethod
    def _put(
        session_url: str,
        access_token: str,
        data: bytes,
        content_range: str,
    ) -> tuple[int, Any, bytes]:
        request = Request(  # noqa: S310
            session_url,
            data=data,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Length": str(len(data)),
                "Content-Type": "video/mp4",
                "Content-Range": content_range,
                "User-Agent": "Garden-of-Jihan/0.1",
            },
            method="PUT",
        )
        try:
            with urlopen(request, timeout=120) as response:  # noqa: S310  # nosec B310
                return response.status, response.headers, response.read(1024 * 1024)
        except HTTPError as exc:
            body = exc.read(1024 * 1024)
            if exc.code == 308 or exc.code in RETRIABLE_STATUS:
                return exc.code, exc.headers, body
            raise _safe_google_error(body, exc.code) from exc

    def _query_offset(self, session_url: str, access_token: str, total: int) -> tuple[int, str | None]:
        status, headers, body = self._put(
            session_url,
            access_token,
            b"",
            f"bytes */{total}",
        )
        if status in {200, 201}:
            return total, _video_id_from_response(body)
        if status == 308:
            return self._range_offset(headers, 0), None
        raise YouTubePublishingError(f"YouTube upload status check failed ({status})")

    def upload(
        self,
        path: Path,
        metadata: YouTubeUploadMetadata,
        progress=None,
        *,
        chunk_size: int = 8 * 1024 * 1024,
    ) -> str:
        metadata.validate()
        if path.suffix.lower() != ".mp4" or not path.is_file():
            raise ValueError("Only an existing exported MP4 can be published")
        total = path.stat().st_size
        if total <= 0:
            raise ValueError("The exported clip is empty")
        if chunk_size < 256 * 1024 or chunk_size % (256 * 1024):
            raise ValueError("YouTube upload chunk size must be a multiple of 256 KB")
        access_token = self._access_token()
        session_url = self._start_session(path, metadata, access_token)
        offset = 0
        retries = 0
        with path.open("rb") as handle:
            while offset < total:
                handle.seek(offset)
                chunk = handle.read(min(chunk_size, total - offset))
                end = offset + len(chunk) - 1
                try:
                    status, headers, body = self._put(
                        session_url,
                        access_token,
                        chunk,
                        f"bytes {offset}-{end}/{total}",
                    )
                except (OSError, URLError):
                    status, headers, body = 503, {}, b""
                if status in {200, 201}:
                    video_id = _video_id_from_response(body)
                    if progress:
                        progress(total, total)
                    return video_id
                if status == 308:
                    offset = self._range_offset(headers, end + 1)
                    retries = 0
                    if progress:
                        progress(offset, total)
                    continue
                if status in RETRIABLE_STATUS and retries < 5:
                    retries += 1
                    time.sleep(min(16, 2 ** (retries - 1)))
                    offset, completed_id = self._query_offset(
                        session_url,
                        access_token,
                        total,
                    )
                    if completed_id:
                        return completed_id
                    continue
                raise YouTubePublishingError(f"YouTube upload failed after retries ({status})")
        raise YouTubePublishingError("YouTube upload ended before completion")
