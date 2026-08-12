import sys
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from garden_jihan.analysis import transcription
from garden_jihan.analysis.transcription import transcribe


def test_bundled_speech_resources_are_verified_before_loading(monkeypatch, tmp_path):
    transcription._MODEL_CACHE.clear()
    payload = b"verified speech resource"
    (tmp_path / "model.bin").write_bytes(payload)
    monkeypatch.setenv("GOJ_SPEECH_MODEL_PATH", str(tmp_path))
    monkeypatch.setattr(
        transcription,
        "SPEECH_MODEL_FILES",
        {"model.bin": sha256(payload).hexdigest()},
    )

    class FakeModel:
        def __init__(self, source, **kwargs):
            assert source == str(tmp_path.resolve())
            assert kwargs["local_files_only"] is True

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeModel))

    assert isinstance(transcription._load_model(transcription.SPEECH_MODEL), FakeModel)


def test_corrupt_bundled_speech_resource_fails_closed(monkeypatch, tmp_path):
    transcription._MODEL_CACHE.clear()
    (tmp_path / "model.bin").write_bytes(b"changed")
    monkeypatch.setenv("GOJ_SPEECH_MODEL_PATH", str(tmp_path))
    monkeypatch.setattr(
        transcription,
        "SPEECH_MODEL_FILES",
        {"model.bin": sha256(b"expected").hexdigest()},
    )
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=object))

    with pytest.raises(RuntimeError, match="failed verification"):
        transcription._load_model(transcription.SPEECH_MODEL)


def test_transcribe_requests_and_preserves_valid_acoustic_word_timestamps(monkeypatch):
    transcription._MODEL_CACHE.clear()
    captured = {}

    class FakeModel:
        def __init__(self, *args, **kwargs):
            captured["init"] = (args, kwargs)

        def transcribe(self, path, **kwargs):
            captured["transcribe"] = (path, kwargs)
            segment = SimpleNamespace(
                start=2.0,
                end=5.0,
                text="  السلام عليكم  ",
                words=[
                    SimpleNamespace(start=2.1, end=3.0, word=" السلام", probability=0.91),
                    SimpleNamespace(start=3.1, end=4.8, word="عليكم", probability=0.88),
                    SimpleNamespace(start=float("nan"), end=4.9, word="bad", probability=0.9),
                ],
            )
            return iter([segment]), SimpleNamespace(language="ar")

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeModel))
    transcript = transcribe(Path("source.mp4"), language="ar")

    assert captured["transcribe"][1]["word_timestamps"] is True
    assert captured["transcribe"][1]["beam_size"] == 1
    assert captured["transcribe"][1]["best_of"] == 1
    assert captured["transcribe"][1]["condition_on_previous_text"] is False
    assert captured["transcribe"][1]["multilingual"] is False
    assert transcript.language == "ar"
    assert transcript.segments[0].text == "السلام عليكم"
    assert [(word.start, word.end, word.text, word.probability) for word in transcript.segments[0].words] == [
        (2.1, 3.0, "السلام", 0.91),
        (3.1, 4.8, "عليكم", 0.88),
    ]


def test_transcribe_uses_batched_long_form_path_and_reports_real_progress(monkeypatch):
    transcription._MODEL_CACHE.clear()
    captured = {}

    class FakeModel:
        def __init__(self, *args, **kwargs):
            captured["init"] = (args, kwargs)

    class FakeBatch:
        def __init__(self, model):
            captured["model"] = model

        def transcribe(self, path, **kwargs):
            captured["transcribe"] = (path, kwargs)
            segments = [
                SimpleNamespace(start=0.0, end=25.0, text="first phrase", words=[]),
                SimpleNamespace(start=25.0, end=50.0, text="second phrase", words=[]),
            ]
            return iter(segments), SimpleNamespace(language="so", duration=50.0)

    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        SimpleNamespace(WhisperModel=FakeModel, BatchedInferencePipeline=FakeBatch),
    )
    seen = []
    transcript = transcribe(Path("source.mp4"), language="so", progress=lambda value, _: seen.append(value))

    assert transcript.language == "so"
    assert captured["transcribe"][1]["batch_size"] == 8
    assert captured["transcribe"][1]["beam_size"] == 1
    assert seen[0] == 0.0
    assert 0.5 in seen
    assert seen[-1] == 1.0


def test_sampled_transcription_preserves_source_times_and_reports_sample_progress(monkeypatch):
    transcription._MODEL_CACHE.clear()
    captured = {}

    class FakeModel:
        def __init__(self, *args, **kwargs):
            pass

    class FakeBatch:
        def __init__(self, model):
            pass

        def transcribe(self, path, **kwargs):
            captured.update(kwargs)
            segments = [
                SimpleNamespace(start=100.0, end=120.0, text="first", words=[]),
                SimpleNamespace(start=900.0, end=920.0, text="second", words=[]),
            ]
            return iter(segments), SimpleNamespace(language="so", duration=1000.0)

    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        SimpleNamespace(WhisperModel=FakeModel, BatchedInferencePipeline=FakeBatch),
    )
    seen = []
    result = transcribe(
        Path("long.mp4"),
        language="so",
        clips=[(100.0, 120.0), (900.0, 920.0)],
        progress=lambda value, _: seen.append(value),
    )

    assert captured["clip_timestamps"] == [
        {"start": 100.0, "end": 120.0},
        {"start": 900.0, "end": 920.0},
    ]
    assert [(segment.start, segment.end) for segment in result.segments] == [
        (100.0, 120.0),
        (900.0, 920.0),
    ]
    assert 0.5 in seen
    assert seen[-1] == 1.0
