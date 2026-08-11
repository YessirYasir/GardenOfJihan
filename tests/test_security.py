from pathlib import Path

import pytest

from garden_jihan.security import UnsafeSource, safe_job_path, validate_remote_url


def test_youtube_url_allowed():
    provider, clean = validate_remote_url("https://www.youtube.com/watch?v=abcdefghijk")
    assert provider == "youtube"
    assert clean.startswith("https://www.youtube.com/")


@pytest.mark.parametrize("url", [
    "http://youtube.com/watch?v=abcdefghijk",
    "https://127.0.0.1/video",
    "https://localhost/video",
    "https://evil.example/video",
    "https://user:pass@youtube.com/watch?v=abcdefghijk",
    "https://youtube.com:8443/watch?v=abcdefghijk",
])
def test_unsafe_sources_rejected(url):
    with pytest.raises(UnsafeSource):
        validate_remote_url(url)


def test_playlist_only_rejected():
    with pytest.raises(UnsafeSource):
        validate_remote_url("https://youtube.com/playlist?list=PL123")


def test_supported_social_hosts_are_exact():
    assert validate_remote_url("https://www.tiktok.com/@user/video/123")[0] == "tiktok"
    assert validate_remote_url("https://www.instagram.com/reel/example/")[0] == "instagram"
    with pytest.raises(UnsafeSource):
        validate_remote_url("https://youtube.com.attacker.example/watch?v=x")


def test_job_path_is_contained(tmp_path: Path):
    result = safe_job_path(tmp_path, "abc_123")
    assert tmp_path.resolve() in result.parents
    with pytest.raises(ValueError):
        safe_job_path(tmp_path, "../../escape")
