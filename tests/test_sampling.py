from garden_jihan.analysis.sampling import plan_listening_windows
from garden_jihan.analysis.signals import TimedValue


def test_short_video_is_listened_to_in_full():
    assert plan_listening_windows(300, [], min_clip_seconds=20) is None


def test_long_video_plan_is_bounded_spread_and_includes_voice_peaks():
    energy = [
        TimedValue(start=float(second), end=float(second + 2), value=second / 7200)
        for second in range(0, 7200, 120)
    ]
    windows = plan_listening_windows(7200, energy, min_clip_seconds=20)

    assert windows is not None
    assert 9 <= len(windows) <= 15
    assert sum(end - start for start, end in windows) <= 450
    assert windows[0][0] < 720
    assert windows[-1][1] > 6480
    assert all(left[1] <= right[0] for left, right in zip(windows, windows[1:], strict=False))
    assert any(start <= 7080 <= end for start, end in windows)
