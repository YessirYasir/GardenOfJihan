from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    package = args.package_root.resolve()
    archive = args.archive.resolve()
    if not package.is_dir() or package.parent.name != "dist":
        raise SystemExit("Refusing to package anything outside the repository dist directory")

    manifest_path = package / ".package-files.sha256"
    files = sorted(
        path for path in package.rglob("*") if path.is_file() and path != manifest_path
    )
    manifest_path.write_text(
        "".join(f"{file_hash(path)}  {path.relative_to(package).as_posix()}\n" for path in files),
        encoding="ascii",
    )
    archive.unlink(missing_ok=True)
    subprocess.run(  # nosec B603
        [
            "/usr/bin/ditto",
            "-c",
            "-k",
            "--sequesterRsrc",
            "--keepParent",
            str(package),
            str(archive),
        ],
        check=True,
        shell=False,
    )
    checksum = file_hash(archive)
    archive.with_suffix(".sha256").write_text(
        f"{checksum}  {archive.name}\n", encoding="ascii"
    )
    print(f"Created {archive}")
    print(f"SHA256: {checksum}")


if __name__ == "__main__":
    main()
