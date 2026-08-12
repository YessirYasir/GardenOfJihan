from __future__ import annotations

import argparse
import http.client
from pathlib import Path

from garden_jihan.analysis.quran import (
    TANZIL_TRUSTED_CANONICAL_SHA256,
    QuranReference,
    canonical_tanzil_sha256,
)

REFERENCE_URL = (
    "https://tanzil.net/pub/download/index.php?marks=true&sajdah=true&tatweel=true&"
    "quranType=simple&outType=txt-2&agree=true"
)


def _verified_text(cache: Path) -> str:
    cache.mkdir(parents=True, exist_ok=True)
    cache_file = cache / "quran-simple-1.1.txt"
    if cache_file.is_file():
        text = cache_file.read_text(encoding="utf-8-sig")
        if canonical_tanzil_sha256(text) in TANZIL_TRUSTED_CANONICAL_SHA256:
            return text
        cache_file.unlink()

    temporary = cache_file.with_suffix(".download")
    try:
        connection = http.client.HTTPSConnection("tanzil.net", timeout=60)
        try:
            request_target = REFERENCE_URL.removeprefix("https://tanzil.net")
            connection.request("GET", request_target)
            response = connection.getresponse()
            if response.status != 200:
                raise RuntimeError(
                    f"Reviewed Qur'an reference download failed with status {response.status}"
                )
            downloaded = response.read(8 * 1024 * 1024 + 1)
            if len(downloaded) > 8 * 1024 * 1024:
                raise RuntimeError("Reviewed Qur'an reference download was unexpectedly large")
            temporary.write_bytes(downloaded)
        finally:
            connection.close()
        text = temporary.read_text(encoding="utf-8-sig")
        checksum = canonical_tanzil_sha256(text)
        if checksum not in TANZIL_TRUSTED_CANONICAL_SHA256:
            raise RuntimeError("Downloaded Qur'an reference failed the reviewed fingerprint")
        temporary.replace(cache_file)
        return text
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare the reviewed offline Qur'an guide")
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    args = parser.parse_args()

    destination = args.destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_suffix(".staging.json")
    try:
        reference = QuranReference.install_tanzil_text(_verified_text(args.cache), staging)
        if not reference.available or len(reference.records) != 6236:
            raise RuntimeError("Prepared Qur'an reference failed integrity validation")
        staging.replace(destination)
    finally:
        staging.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
