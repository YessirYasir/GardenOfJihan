from __future__ import annotations

import argparse
import shutil
from hashlib import file_digest
from pathlib import Path

from garden_jihan.analysis.semantics import (
    SEMANTIC_MODEL,
    SEMANTIC_MODEL_FILES,
    SEMANTIC_MODEL_REVISION,
)
from garden_jihan.analysis.transcription import (
    SPEECH_MODEL,
    SPEECH_MODEL_FILES,
    SPEECH_MODEL_REVISION,
)


def _verified_snapshot(
    *,
    repo_id: str,
    revision: str,
    files: dict[str, str],
    cache_dir: Path,
) -> Path:
    from huggingface_hub import snapshot_download

    snapshot = Path(
        snapshot_download(
            repo_id=repo_id,
            revision=revision,
            allow_patterns=list(files),
            cache_dir=str(cache_dir),
        )
    )
    for relative_path, expected in files.items():
        source = snapshot / relative_path
        if not source.is_file():
            raise RuntimeError(f"Pinned resource is missing: {repo_id}/{relative_path}")
        with source.open("rb") as handle:
            actual = file_digest(handle, "sha256").hexdigest()
        if actual != expected:
            raise RuntimeError(f"Pinned resource failed verification: {repo_id}/{relative_path}")
    return snapshot


def _copy_files(source: Path, destination: Path, files: dict[str, str]) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for relative_path in files:
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative_path, target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    args = parser.parse_args()
    destination = args.destination.resolve()
    cache = args.cache.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)

    speech = _verified_snapshot(
        repo_id=SPEECH_MODEL,
        revision=SPEECH_MODEL_REVISION,
        files=SPEECH_MODEL_FILES,
        cache_dir=cache / "speech",
    )
    meaning = _verified_snapshot(
        repo_id=SEMANTIC_MODEL,
        revision=SEMANTIC_MODEL_REVISION,
        files=SEMANTIC_MODEL_FILES,
        cache_dir=cache / "meaning",
    )
    _copy_files(speech, destination / "speech", SPEECH_MODEL_FILES)
    _copy_files(meaning, destination / "meaning", SEMANTIC_MODEL_FILES)
    print(f"Prepared verified offline resources in {destination}")


if __name__ == "__main__":
    main()
