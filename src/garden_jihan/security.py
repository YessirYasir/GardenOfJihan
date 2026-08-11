from __future__ import annotations

import hmac
import ipaddress
import re
import secrets
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

ALLOWED_REMOTE_HOSTS = {
    "youtube.com": "youtube",
    "www.youtube.com": "youtube",
    "m.youtube.com": "youtube",
    "music.youtube.com": "youtube",
    "youtu.be": "youtube",
    "tiktok.com": "tiktok",
    "www.tiktok.com": "tiktok",
    "vm.tiktok.com": "tiktok",
    "vt.tiktok.com": "tiktok",
    "instagram.com": "instagram",
    "www.instagram.com": "instagram",
}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class UnsafeSource(ValueError):
    pass


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def validate_remote_url(raw_url: str) -> tuple[str, str]:
    try:
        parsed = urlsplit(raw_url)
    except Exception as exc:
        raise UnsafeSource("Malformed URL") from exc

    if parsed.scheme != "https":
        raise UnsafeSource("Only HTTPS media URLs are allowed")
    if parsed.username or parsed.password:
        raise UnsafeSource("Credentials in URLs are not allowed")
    if parsed.port is not None:
        raise UnsafeSource("Custom URL ports are not allowed")

    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise UnsafeSource("Missing hostname")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise UnsafeSource("IP-literal media URLs are not allowed")

    provider = ALLOWED_REMOTE_HOSTS.get(host)
    if not provider:
        raise UnsafeSource("Unsupported media host")

    if provider == "youtube":
        query = parse_qs(parsed.query)
        if "list" in query and "v" not in query:
            raise UnsafeSource("Playlist-only URLs are not supported")

    clean = urlunsplit(("https", host, parsed.path or "/", parsed.query, ""))
    return provider, clean


def safe_job_path(root: Path, job_id: str) -> Path:
    if not SAFE_ID_RE.fullmatch(job_id):
        raise ValueError("Unsafe job identifier")
    root = root.resolve()
    candidate = (root / job_id).resolve()
    if root not in candidate.parents:
        raise ValueError("Path escaped job root")
    return candidate


class LocalSecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, session_token: str, port: int):
        super().__init__(app)
        self.session_token = session_token
        self.allowed_origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "")
        host_name = host.split(":", 1)[0].lower()
        if host_name not in {"127.0.0.1", "localhost"}:
            return JSONResponse({"detail": "Invalid local host"}, status_code=400)

        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            token = request.headers.get("x-goj-token", "")
            if origin not in self.allowed_origins:
                return JSONResponse({"detail": "Origin rejected"}, status_code=403)
            if not hmac.compare_digest(token, self.session_token):
                return JSONResponse({"detail": "Session token rejected"}, status_code=403)

        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
            "font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        response.headers["Cache-Control"] = "no-store"
        return response
