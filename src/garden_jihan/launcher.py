from __future__ import annotations

import os
import socket
import threading
import time
import webbrowser

import uvicorn

from garden_jihan.config import Settings
from garden_jihan.security import new_session_token
from garden_jihan.server import create_app


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


def main() -> None:
    settings = Settings()
    if settings.bind_host != "127.0.0.1":
        raise RuntimeError("Garden of Jihan must bind to 127.0.0.1 in desktop mode")
    port = _requested_port()
    token = new_session_token()
    app = create_app(port=port, settings=settings, session_token=token)

    if os.getenv("GOJ_NO_BROWSER", "0") != "1":
        def open_ui():
            time.sleep(0.8)
            webbrowser.open(f"http://127.0.0.1:{port}/")

        threading.Thread(target=open_ui, daemon=True).start()

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
