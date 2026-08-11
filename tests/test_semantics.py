import inspect

from garden_jihan.analysis.scoring import (
    ScoredWindow,
    _rerank_semantic_shortlist,
    build_candidates,
)
from garden_jihan.analysis.semantics import (
    SEMANTIC_MODEL_FILES,
    SEMANTIC_MODEL_REVISION,
    LocalSemanticRanker,
    SemanticProfile,
    semantic_profiles,
)
from garden_jihan.analysis.transcription import TranscriptSegment
from garden_jihan.models import AnalysisMode


class FakeEmbedder:
    model_name = "test/multilingual"

    def __init__(self, vectors):
        self.vectors = vectors

    def embed(self, texts):
        return [self.vectors[text] for text in texts]


def test_semantic_profiles_reward_coherent_segments_without_language_normalization():
    groups = [
        ["Somali idea", "Arabic paraphrase"],
        ["Somali idea", "Unrelated ending"],
        ["Single segment"],
    ]
    embedder = FakeEmbedder(
        {
            "Somali idea": (1.0, 0.0),
            "Arabic paraphrase": (0.98, 0.02),
            "Unrelated ending": (-1.0, 0.0),
            "Single segment": (0.0, 1.0),
        }
    )

    profiles = semantic_profiles(groups, embedder)

    assert profiles[0].coherence == 100.0
    assert profiles[1].coherence == 0.0
    assert profiles[2].coherence == 50.0


def test_semantic_mmr_prefers_a_distinct_paraphrase_cluster():
    shortlist = [
        ScoredWindow(0, 20, "first", 90, ["first"]),
        ScoredWindow(30, 50, "paraphrase", 89, ["second"]),
        ScoredWindow(60, 80, "different", 88, ["third"]),
    ]
    profiles = [
        SemanticProfile(50, (1.0, 0.0)),
        SemanticProfile(50, (0.999, 0.001)),
        SemanticProfile(50, (0.0, 1.0)),
    ]

    selected = _rerank_semantic_shortlist(shortlist, profiles, "test/model", 2)

    assert [window.text for window in selected] == ["first", "different"]
    assert all(window.semantic_model == "test/model" for window in selected)
    assert all(window.breakdown["semantic_coherence"] == 50 for window in selected)


def test_candidate_builder_uses_local_semantic_profiles_when_available():
    class FakeRanker:
        model_name = "test/multilingual"

        def profile_windows(self, groups):
            return [SemanticProfile(85, (float(index + 1), 1.0)) for index, _ in enumerate(groups)]

    segments = [
        TranscriptSegment(0, 10, "Why this matters is simple."),
        TranscriptSegment(10, 20, "Here is the answer."),
        TranscriptSegment(30, 40, "A different story begins."),
        TranscriptSegment(40, 50, "The final lesson is clear."),
    ]

    candidates = build_candidates(
        segments,
        AnalysisMode.GENERAL,
        20,
        30,
        2,
        semantic_ranker=FakeRanker(),
    )

    assert len(candidates) == 2
    assert all(candidate.semantic_model == "test/multilingual" for candidate in candidates)
    assert all(candidate.score_breakdown["semantic_coherence"] == 85 for candidate in candidates)


def test_quran_candidate_builder_never_calls_semantic_reranker():
    class ForbiddenRanker:
        model_name = "must/not/run"

        def profile_windows(self, _groups):
            raise AssertionError("Qur'an mode must not use semantic embeddings")

    segments = [
        TranscriptSegment(0, 10, "نص قرآني للمراجعة"),
        TranscriptSegment(10, 20, "نهاية المقطع"),
    ]

    candidates = build_candidates(
        segments,
        AnalysisMode.QURAN,
        20,
        30,
        1,
        semantic_ranker=ForbiddenRanker(),
    )

    assert candidates[0].semantic_model is None
    assert "semantic_coherence" not in candidates[0].score_breakdown


def test_local_semantic_ranker_fails_back_without_raising(tmp_path, monkeypatch):
    ranker = LocalSemanticRanker(tmp_path)
    monkeypatch.setattr(ranker, "_load_model", lambda: (_ for _ in ()).throw(OSError("offline")))

    assert ranker.profile_windows([["local transcript"]]) is None
    assert ranker.last_error == "OSError"


def test_local_semantic_runtime_uses_portable_quantized_onnx_artifact():
    source = inspect.getsource(LocalSemanticRanker._load_model)

    assert "onnx/model_O4.onnx" in SEMANTIC_MODEL_FILES
    assert len(SEMANTIC_MODEL_FILES["onnx/model_O4.onnx"]) == 64
    assert len(SEMANTIC_MODEL_REVISION) == 40
    assert "revision" in source
    assert "file_digest" in source
    assert "qint8_avx512" not in source
