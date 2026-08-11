import sys
from pathlib import Path
from types import SimpleNamespace

from garden_jihan.analysis.transcription import transcribe


def test_transcribe_requests_and_preserves_valid_acoustic_word_timestamps(monkeypatch):
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
    assert transcript.language == "ar"
    assert transcript.segments[0].text == "السلام عليكم"
    assert [(word.start, word.end, word.text, word.probability) for word in transcript.segments[0].words] == [
        (2.1, 3.0, "السلام", 0.91),
        (3.1, 4.8, "عليكم", 0.88),
    ]
