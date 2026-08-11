from __future__ import annotations

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


def main() -> None:
    settings = Settings()
    if settings.bind_host != "127.0.0.1":
        raise RuntimeError("Garden of Jihan must bind to 127.0.0.1 in desktop mode")
    port = _free_port()
    token = new_session_token()
    app = create_app(port=port, settings=settings, session_token=token)

    def open_ui():
        time.sleep(0.8)
        webbrowser.open(f"http://127.0.0.1:{port}/")

    threading.Thread(target=open_ui, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
