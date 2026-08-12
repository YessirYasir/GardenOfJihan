from __future__ import annotations

import logging
import math
import os
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import file_digest
from pathlib import Path
from typing import Protocol

SEMANTIC_MODEL = "intfloat/multilingual-e5-small"
SEMANTIC_DIMENSIONS = 384
SEMANTIC_MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
SEMANTIC_MODEL_FILES = {
    "config.json": "69137736cab8b8903a07fe8afaafdda25aac55415a12a55d1bffa9f581abf959",
    "special_tokens_map.json": "d05497f1da52c5e09554c0cd874037a083e1dc1b9cfd48034d1c717f1afc07a7",
    "tokenizer.json": "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39",
    "tokenizer_config.json": "a1d6bc8734a6f635dc158508bef000f8e2e5a759c7d92f984b2c86e5ff53425b",
    "onnx/model_O4.onnx": "4654c156f3e4171abc9c716cdb771bf9116455d15ac1aab364aeeede0e3205b0",
}
LOGGER = logging.getLogger("garden_jihan.semantic")
_MODEL_REGISTRATION_LOCK = threading.Lock()


class TextEmbedder(Protocol):
    model_name: str

    def embed(self, texts: Sequence[str]) -> list[Sequence[float]]: ...


@dataclass(frozen=True, slots=True)
class SemanticProfile:
    coherence: float
    vector: tuple[float, ...]


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Semantic vectors must have the same non-zero dimensions")
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return max(-1.0, min(1.0, numerator / (left_norm * right_norm)))


def _normalized_centroid(vectors: Sequence[Sequence[float]]) -> tuple[float, ...]:
    dimensions = len(vectors[0])
    if any(len(vector) != dimensions for vector in vectors):
        raise ValueError("Semantic vectors have inconsistent dimensions")
    centroid = tuple(sum(vector[index] for vector in vectors) / len(vectors) for index in range(dimensions))
    norm = math.sqrt(sum(value * value for value in centroid))
    if not norm:
        return tuple(0.0 for _ in centroid)
    return tuple(value / norm for value in centroid)


def _relative_percentiles(values: Sequence[float]) -> list[float]:
    if len(values) <= 1:
        return [50.0 for _ in values]
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    result = [0.0] * len(values)
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and math.isclose(
            ordered[end][1], ordered[cursor][1], rel_tol=1e-9, abs_tol=1e-9
        ):
            end += 1
        average_rank = (cursor + end - 1) / 2
        percentile = average_rank / (len(values) - 1) * 100
        for rank in range(cursor, end):
            result[ordered[rank][0]] = percentile
        cursor = end
    return result


def semantic_profiles(
    segment_groups: Sequence[Sequence[str]],
    embedder: TextEmbedder,
) -> list[SemanticProfile]:
    """Profile topical cohesion without rewriting or exposing transcript text."""
    unique_texts = list(
        dict.fromkeys(text.strip() for group in segment_groups for text in group if text.strip())
    )
    if not unique_texts:
        return []
    embedded = embedder.embed(unique_texts)
    if len(embedded) != len(unique_texts):
        raise ValueError("Meaning model returned the wrong number of vectors")
    vectors: dict[str, tuple[float, ...]] = {}
    for text, values in zip(unique_texts, embedded, strict=True):
        vector = tuple(float(value) for value in values)
        if not vector or any(not math.isfinite(value) for value in vector):
            raise ValueError("Meaning model returned an invalid vector")
        vectors[text] = vector

    centroids: list[tuple[float, ...]] = []
    raw_coherence: list[float] = []
    for group in segment_groups:
        group_vectors = [vectors[text.strip()] for text in group if text.strip()]
        if not group_vectors:
            raise ValueError("Semantic window contains no transcript segments")
        centroid = _normalized_centroid(group_vectors)
        centroids.append(centroid)
        if len(group_vectors) == 1:
            raw_coherence.append(0.0)
            continue
        adjacent = [
            cosine_similarity(left, right)
            for left, right in zip(group_vectors, group_vectors[1:], strict=False)
        ]
        centrality = [cosine_similarity(vector, centroid) for vector in group_vectors]
        raw_coherence.append(
            sum(adjacent) / len(adjacent) * 0.55
            + sum(centrality) / len(centrality) * 0.45
        )

    relative_coherence = _relative_percentiles(raw_coherence)
    return [
        SemanticProfile(round(coherence, 1), centroid)
        for coherence, centroid in zip(relative_coherence, centroids, strict=True)
    ]


class LocalSemanticRanker:
    """Lazily load a free local ONNX embedding model and fail back to base ranking."""

    model_name = SEMANTIC_MODEL

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self._model = None
        self._lock = threading.Lock()
        self.last_error: str | None = None

    def _load_model(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            from fastembed import TextEmbedding
            from fastembed.common.model_description import ModelSource, PoolingType
            from huggingface_hub import snapshot_download

            with _MODEL_REGISTRATION_LOCK:
                supported = {item["model"] for item in TextEmbedding.list_supported_models()}
                if self.model_name not in supported:
                    TextEmbedding.add_custom_model(
                        model=self.model_name,
                        pooling=PoolingType.MEAN,
                        normalization=True,
                        sources=ModelSource(hf=self.model_name),
                        dim=SEMANTIC_DIMENSIONS,
                        model_file="onnx/model_O4.onnx",
                    )
            bundled = os.getenv("GOJ_MEANING_MODEL_PATH", "").strip()
            if bundled:
                model_dir = Path(bundled).expanduser().resolve()
                if not model_dir.is_dir():
                    raise ValueError("Included meaning resources are missing")
            else:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                try:
                    model_dir = Path(
                        snapshot_download(
                            repo_id=self.model_name,
                            revision=SEMANTIC_MODEL_REVISION,
                            allow_patterns=list(SEMANTIC_MODEL_FILES),
                            cache_dir=str(self.cache_dir),
                            local_files_only=True,
                        )
                    )
                except Exception:
                    model_dir = Path(
                        snapshot_download(
                            repo_id=self.model_name,
                            revision=SEMANTIC_MODEL_REVISION,
                            allow_patterns=list(SEMANTIC_MODEL_FILES),
                            cache_dir=str(self.cache_dir),
                        )
                    )
            for relative_path, trusted_sha256 in SEMANTIC_MODEL_FILES.items():
                model_path = model_dir / relative_path
                if not model_path.is_file():
                    raise ValueError(f"Meaning model file is missing: {relative_path}")
                with model_path.open("rb") as handle:
                    actual_sha256 = file_digest(handle, "sha256").hexdigest()
                if actual_sha256 != trusted_sha256:
                    raise ValueError(f"Meaning model integrity check failed: {relative_path}")
            self._model = TextEmbedding(
                model_name=self.model_name,
                cache_dir=str(self.cache_dir),
                specific_model_path=str(model_dir),
            )
            return self._model

    def embed(self, texts: Sequence[str]) -> list[Sequence[float]]:
        model = self._load_model()
        prepared = [f"query: {text}" for text in texts]
        return list(model.embed(prepared, batch_size=32, parallel=None))

    def profile_windows(
        self,
        segment_groups: Sequence[Sequence[str]],
    ) -> list[SemanticProfile] | None:
        try:
            profiles = semantic_profiles(segment_groups, self)
            self.last_error = None
            return profiles
        except Exception as exc:
            self.last_error = type(exc).__name__
            LOGGER.warning("Local meaning model unavailable; using base ranking (%s)", self.last_error)
            return None
