from __future__ import annotations

import http.client
import logging
import os
import socket
import sys
import threading
import time
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn

from garden_jihan.config import Settings
from garden_jihan.security import new_session_token
from garden_jihan.server import create_app

LOGGER = logging.getLogger("garden_jihan")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _requested_port() -> int:
    raw = os.getenv("GOJ_PORT", "").strip()
    if not raw:
        return _free_port()
    try:
        port = int(raw)
    except ValueError as exc:
        raise RuntimeError("GOJ_PORT must be an integer") from exc
    if port < 1024 or port > 65535:
        raise RuntimeError("GOJ_PORT must be between 1024 and 65535")
    return port


def _configure_logging(settings: Settings) -> None:
    logs_dir = settings.app_data / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        logs_dir / "garden-of-jihan.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=2,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    LOGGER.setLevel(logging.INFO)
    LOGGER.handlers.clear()
    LOGGER.addHandler(handler)


def _show_startup_error(message: str) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0,
            message,
            "Garden of Jihan could not start",
            0x10,
        )
    except Exception:
        LOGGER.exception("Could not display startup error dialog")


def _open_ui_when_ready(port: int, timeout_seconds: float = 30.0) -> None:
    """Open the browser only after the loopback server answers its health check."""
    origin = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=0.5)
        try:
            connection.request("GET", "/api/health")
            if connection.getresponse().status == 200:
                webbrowser.open(f"{origin}/")
                return
        except OSError:
            time.sleep(0.15)
        finally:
            connection.close()
    LOGGER.error("Local interface did not become ready for the browser in %.1f seconds", timeout_seconds)


def run() -> None:
    if getattr(sys, "frozen", False):
        frozen_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        model_candidates = (
            frozen_root / "models",
            Path(sys.executable).resolve().parent / "models",
            Path(sys.executable).resolve().parent.parent / "Resources" / "models",
        )
        model_root = next((candidate for candidate in model_candidates if candidate.is_dir()), None)
        if model_root is not None:
            os.environ.setdefault("GOJ_SPEECH_MODEL_PATH", str(model_root / "speech"))
            os.environ.setdefault("GOJ_MEANING_MODEL_PATH", str(model_root / "meaning"))
            os.environ.setdefault(
                "GOJ_QURAN_REFERENCE_PATH", str(model_root / "quran_reference.json")
            )
    settings = Settings()
    _configure_logging(settings)
    if settings.bind_host != "127.0.0.1":
        raise RuntimeError("Garden of Jihan must bind to 127.0.0.1 in desktop mode")
    port = _requested_port()
    token = new_session_token()
    shutdown_requested = threading.Event()
    app = create_app(
        port=port,
        settings=settings,
        session_token=token,
        shutdown_callback=shutdown_requested.set,
    )
    LOGGER.info("Starting local interface on 127.0.0.1:%s", port)

    if os.getenv("GOJ_NO_BROWSER", "0") != "1":
        threading.Thread(target=_open_ui_when_ready, args=(port,), daemon=True).start()

    config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        log_config=None,
    )
    server = uvicorn.Server(config)

    def stop_when_requested():
        shutdown_requested.wait()
        server.should_exit = True

    threading.Thread(target=stop_when_requested, daemon=True).start()
    server.run()


def main() -> None:
    try:
        run()
    except Exception as exc:
        try:
            LOGGER.exception("Garden of Jihan failed to start")
        finally:
            _show_startup_error(
                f"Garden of Jihan could not start.\n\n{exc}\n\n"
                "A diagnostic log was saved under your GardenOfJihan app-data folder."
            )
        raise


if __name__ == "__main__":
    main()
