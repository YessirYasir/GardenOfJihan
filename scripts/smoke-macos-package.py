from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def request_json(url: str, *, token: str = "", method: str = "GET") -> dict:
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
        raise ValueError("Mac smoke requests must stay on the fixed loopback origin")
    headers = {"Origin": url.split("/api/", 1)[0]}
    if token:
        headers["X-GOJ-Token"] = token
    request = Request(url, headers=headers, method=method)  # noqa: S310
    with urlopen(request, timeout=5) as response:  # noqa: S310  # nosec B310
        return json.loads(response.read())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8878)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        raise SystemExit("Smoke-test port must be between 1024 and 65535")
    executable = (
        args.package_root.resolve()
        / "Garden of Jihan.app"
        / "Contents"
        / "MacOS"
        / "Garden of Jihan"
    )
    if not executable.is_file():
        raise SystemExit("Packaged Mac application executable is missing")

    with tempfile.TemporaryDirectory(prefix="goj-macos-app-data-") as app_data:
        environment = os.environ.copy()
        environment.update(
            {
                "GOJ_APP_DATA": app_data,
                "GOJ_PORT": str(args.port),
                "GOJ_NO_BROWSER": "1",
                "GOJ_DISTRIBUTION": "macos-browser",
            }
        )
        process = subprocess.Popen(  # nosec B603
            [str(executable)], env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        origin = f"http://127.0.0.1:{args.port}"
        try:
            health = None
            for _attempt in range(120):
                if process.poll() is not None:
                    stdout, stderr = process.communicate(timeout=5)
                    raise SystemExit(
                        f"Mac app exited before startup.\n{stdout.decode()}\n{stderr.decode()}"
                    )
                try:
                    health = request_json(f"{origin}/api/health")
                    if health.get("ok") is True:
                        break
                except (OSError, URLError):
                    time.sleep(0.5)
            if not health or any(
                health.get(key) != expected
                for key, expected in {
                    "ok": True,
                    "local": True,
                    "distribution": "macos-browser",
                    "first_run": True,
                    "auto_framing_available": True,
                    "credential_protection_available": True,
                }.items()
            ):
                raise SystemExit(f"Mac app health check failed: {health}")

            with urlopen(f"{origin}/", timeout=5) as response:  # noqa: S310  # nosec B310
                markup = response.read().decode()
            if (
                "Garden of Jihan" not in markup
                or 'id="progressClock"' not in markup
                or "complete reviewed guide is included" not in markup
            ):
                raise SystemExit("Mac app did not serve the complete production interface")
            quran = request_json(f"{origin}/api/quran/reference")
            if not quran.get("verified") or quran.get("verses") != 6236:
                raise SystemExit("Mac app did not load the complete reviewed Qur'an guide")
            token_match = re.search(r'<meta name="goj-token" content="([^"]+)">', markup)
            if not token_match:
                raise SystemExit("Mac app did not provide its local request token")
            token = token_match.group(1)
            welcome = request_json(
                f"{origin}/api/onboarding/complete", token=token, method="POST"
            )
            if welcome.get("complete") is not True:
                raise SystemExit("Mac first-run welcome could not be completed")
            closing = request_json(f"{origin}/api/app/quit", token=token, method="POST")
            if closing.get("closing") is not True:
                raise SystemExit("Mac app did not accept a clean shutdown")
            process.wait(timeout=20)
            if process.returncode != 0:
                raise SystemExit(f"Mac app exited with code {process.returncode}")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
    print("Mac one-click app, Keychain, UI, Qur'an guide, and shutdown passed")


if __name__ == "__main__":
    main()
