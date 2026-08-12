from __future__ import annotations

from garden_jihan.analysis.signals import TimedValue


def plan_listening_windows(
    duration: float,
    audio_energy: list[TimedValue],
    *,
    min_clip_seconds: int,
    max_sample_seconds: float = 450.0,
) -> list[tuple[float, float]] | None:
    """Cover a long video quickly with evenly spread and high-energy listening windows.

    Returning ``None`` asks the speech engine to listen to the complete source. Long
    sources get a bounded set of non-overlapping windows whose original timestamps are
    preserved, so every returned moment still opens and exports from the right place.
    """
    if duration <= 0:
        raise ValueError("Video duration must be positive")
    if duration <= max_sample_seconds * 1.15:
        return None

    # Batched long-form recognition accepts independent clips up to 30 seconds.
    # Thirty seconds is also enough to form every supported minimum clip length.
    window_seconds = 29.9
    window_count = max(6, int(max_sample_seconds // window_seconds))
    coverage_count = max(4, round(window_count * 0.6))
    starts: list[float] = []

    def add_center(center: float) -> bool:
        start = max(0.0, min(duration - window_seconds, center - window_seconds / 2))
        if any(abs(start - existing) < window_seconds * 1.15 for existing in starts):
            return False
        starts.append(start)
        return True

    # Even coverage makes the pass representative of the beginning, middle, and end,
    # rather than overfitting to the loudest section of a sermon or conversation.
    for index in range(coverage_count):
        add_center((index + 0.5) * duration / coverage_count)

    # Fill the remaining budget with expressive voice peaks from across the source.
    for item in sorted(audio_energy, key=lambda value: value.value, reverse=True):
        if len(starts) >= window_count:
            break
        add_center((item.start + item.end) / 2)

    # Sparse or unavailable energy data still receives deterministic whole-video coverage.
    fill_count = window_count * 3
    for index in range(fill_count):
        if len(starts) >= window_count:
            break
        add_center((index + 0.5) * duration / fill_count)

    return [
        (round(start, 3), round(min(duration, start + window_seconds), 3))
        for start in sorted(starts)
    ]
