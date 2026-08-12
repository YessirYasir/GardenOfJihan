from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _diagnostic_path() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home()
    return root / "GardenOfJihan" / "logs" / "portable-startup-error.log"


def _record_startup_failure() -> None:
    try:
        path = _diagnostic_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(traceback.format_exc(), encoding="utf-8")
    except OSError:
        pass


def _show_safe_error() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0,
            "Garden of Jihan could not start because the portable folder is incomplete or "
            "damaged.\n\nExtract the entire ZIP to a normal folder, then try again. "
            "A diagnostic log was saved in your local GardenOfJihan logs folder.",
            "Garden of Jihan could not start",
            0x10,
        )
    except Exception:
        pass


def main() -> None:
    bundle_root = Path(__file__).resolve().parents[1]
    os.chdir(bundle_root)
    os.environ.setdefault("GOJ_DISTRIBUTION", "portable-browser")
    try:
        from garden_jihan.launcher import main as launch
    except Exception:
        _record_startup_failure()
        _show_safe_error()
        return
    launch()


if __name__ == "__main__":
    main()
