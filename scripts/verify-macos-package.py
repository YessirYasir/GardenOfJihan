from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import subprocess
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def one(root: Path, name: str) -> Path:
    matches = [path for path in root.rglob(name) if path.is_file()]
    concrete = [path for path in matches if not path.is_symlink()]
    if len(concrete) == 1:
        return concrete[0]
    if len(matches) == 1:
        return matches[0]
    raise SystemExit(f"Expected one concrete {name} in the Mac package; found {len(concrete)}")


def run(*command: str) -> str:
    completed = subprocess.run(  # nosec B603
        list(command), check=True, capture_output=True, text=True, shell=False
    )
    return f"{completed.stdout}\n{completed.stderr}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--architecture", choices=("arm64", "x86_64"), required=True)
    parser.add_argument("--require-notarized", action="store_true")
    args = parser.parse_args()

    package = args.package_root.resolve()
    app = package / "Garden of Jihan.app"
    executable = app / "Contents" / "MacOS" / "Garden of Jihan"
    info_path = app / "Contents" / "Info.plist"
    manifest = package / ".package-files.sha256"
    required = (
        app,
        executable,
        info_path,
        package / "START-HERE.txt",
        package / "FFMPEG-LICENSE.txt",
        package / "PACKAGE-INFO.json",
        manifest,
    )
    if any(not path.exists() for path in required):
        raise SystemExit("The Mac package is incomplete")

    info = plistlib.loads(info_path.read_bytes())
    if info.get("CFBundleIdentifier") != "com.gardenofjihan.desktop":
        raise SystemExit("The Mac app bundle identifier is invalid")
    if info.get("CFBundleDisplayName", info.get("CFBundleName")) != "Garden of Jihan":
        raise SystemExit("The Mac app product name is invalid")
    if info.get("LSMinimumSystemVersion") != "14.0":
        raise SystemExit("The Mac app must declare its tested macOS 14 minimum")

    metadata = json.loads((package / "PACKAGE-INFO.json").read_text(encoding="utf-8"))
    if (
        metadata.get("product") != "Garden of Jihan"
        or metadata.get("arabic_brand") != "جيهان"
        or metadata.get("architecture") != args.architecture
        or metadata.get("public_release") is not args.require_notarized
    ):
        raise SystemExit("The Mac package identity or private distribution boundary is invalid")

    ffmpeg = one(app, "ffmpeg")
    ffprobe = one(app, "ffprobe")
    one(app, "model.bin")
    one(app, "model_O4.onnx")
    quran = one(app, "quran_reference.json")
    quran_payload = json.loads(quran.read_text(encoding="utf-8"))
    if len(quran_payload.get("verses", [])) != 6236:
        raise SystemExit("The complete reviewed Qur'an guide is missing from the Mac app")

    for binary in (executable, ffmpeg, ffprobe):
        architectures = run("/usr/bin/lipo", "-archs", str(binary)).split()
        if args.architecture not in architectures:
            raise SystemExit(f"{binary.name} does not support {args.architecture}")

    expected_files = set()
    for line in manifest.read_text(encoding="ascii").splitlines():
        expected, separator, relative = line.partition("  ")
        if not separator or len(expected) != 64:
            raise SystemExit("The Mac package integrity manifest contains an invalid entry")
        target = package / relative
        if not target.is_file() or digest(target) != expected:
            raise SystemExit(f"Mac package integrity verification failed: {relative}")
        expected_files.add(relative)
    actual_files = {
        path.relative_to(package).as_posix()
        for path in package.rglob("*")
        if path.is_file() and path != manifest
    }
    if actual_files != expected_files:
        raise SystemExit("The Mac package contains an unverified or missing file")

    run("/usr/bin/codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app))
    if args.require_notarized:
        details = run("/usr/bin/codesign", "--display", "--verbose=4", str(app))
        if "Authority=Developer ID Application:" not in details:
            raise SystemExit("Public Mac package is not signed by an Apple Developer ID")
        run("/usr/bin/xcrun", "stapler", "validate", str(app))
        run("/usr/sbin/spctl", "--assess", "--type", "execute", "--verbose=2", str(app))

    print(f"Verified Garden of Jihan for {args.architecture}")


if __name__ == "__main__":
    main()
