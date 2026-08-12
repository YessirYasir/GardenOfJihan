import sys
from pathlib import Path
from types import SimpleNamespace

from garden_jihan.media.downloader import download_remote


def test_remote_download_reports_real_fraction_and_eta(monkeypatch, tmp_path):
    captured = {}

    class FakeDownloader:
        def __init__(self, options):
            captured.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, download):
            assert download is True
            hook = captured["progress_hooks"][0]
            hook(
                {
                    "status": "downloading",
                    "downloaded_bytes": 25,
                    "total_bytes": 100,
                    "eta": 9.4,
                }
            )
            hook({"status": "finished"})
            (tmp_path / "source.mp4").write_bytes(b"video")
            return {"ext": "mp4"}

        def prepare_filename(self, _info):
            return str(tmp_path / "source.mp4")

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeDownloader))
    monkeypatch.setattr(
        "garden_jihan.media.downloader.ffmpeg_path",
        lambda: str(tmp_path / "ffmpeg.exe"),
    )
    seen = []

    result = download_remote(
        "https://www.youtube.com/watch?v=abcdefghijk",
        tmp_path,
        progress=lambda fraction, eta: seen.append((fraction, eta)),
    )

    assert result == Path(tmp_path / "source.mp4")
    assert seen == [(0.25, 9), (1.0, 0)]
    assert captured["concurrent_fragment_downloads"] == 4
