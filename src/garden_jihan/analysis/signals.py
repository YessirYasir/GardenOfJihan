from __future__ import annotations

import math
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from garden_jihan.runtime import ffmpeg_path


@dataclass(slots=True)
class TimedValue:
    start: float
    end: float
    value: float


@dataclass(slots=True)
class MediaSignals:
    audio_energy: list[TimedValue] = field(default_factory=list)
    scene_times: list[float] = field(default_factory=list)
    replay: list[TimedValue] = field(default_factory=list)

    @staticmethod
    def _mean(values: list[TimedValue], start: float, end: float) -> float | None:
        weighted = 0.0
        covered = 0.0
        for item in values:
            overlap = max(0.0, min(end, item.end) - max(start, item.start))
            if overlap:
                weighted += item.value * overlap
                covered += overlap
        return weighted / covered if covered else None

    def audio_for(self, start: float, end: float) -> float | None:
        return self._mean(self.audio_energy, start, end)

    def replay_for(self, start: float, end: float) -> float | None:
        return self._mean(self.replay, start, end)

    def scene_density_for(self, start: float, end: float) -> float | None:
        duration = max(end - start, 1.0)
        count = sum(1 for value in self.scene_times if start <= value <= end)
        if not self.scene_times:
            return None
        return min(1.0, count / max(duration / 15.0, 1.0))


def _percentile_rank(values: list[float]) -> list[float]:
    if not values:
        return []
    if len(values) == 1:
        return [0.5]
    ordered = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    for rank, index in enumerate(ordered):
        ranks[index] = rank / (len(values) - 1)
    return ranks


def extract_audio_energy(path: Path, bucket_seconds: float = 2.0) -> list[TimedValue]:
    command = [
        ffmpeg_path(),
        "-hide_banner",
        "-nostdin",
        "-i",
        str(path),
        "-vn",
        "-af",
        "asetnsamples=n=32000:p=0,astats=metadata=1:reset=1,"
        "ametadata=print:key=lavfi.astats.Overall.RMS_level",
        "-f",
        "null",
        "-",
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=240,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    times: list[float] = []
    db_values: list[float] = []
    current_time: float | None = None
    for line in completed.stderr.splitlines():
        match = re.search(r"pts_time:([0-9.]+)", line)
        if match:
            current_time = float(match.group(1))
            continue
        if "lavfi.astats.Overall.RMS_level=" in line and current_time is not None:
            raw = line.rsplit("=", 1)[-1].strip()
            try:
                db = float(raw)
            except ValueError:
                continue
            if math.isfinite(db):
                times.append(current_time)
                db_values.append(db)

    ranked = _percentile_rank(db_values)
    return [
        TimedValue(start=t, end=t + bucket_seconds, value=value)
        for t, value in zip(times, ranked, strict=False)
    ]


def extract_scene_times(path: Path, threshold: float = 0.32) -> list[float]:
    command = [
        ffmpeg_path(),
        "-hide_banner",
        "-nostdin",
        "-i",
        str(path),
        "-an",
        "-vf",
        f"select='gt(scene,{threshold})',showinfo",
        "-vsync",
        "vfr",
        "-f",
        "null",
        "-",
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    values: list[float] = []
    for line in completed.stderr.splitlines():
        match = re.search(r"pts_time:([0-9.]+)", line)
        if match:
            values.append(float(match.group(1)))
    return values


def build_media_signals(path: Path) -> MediaSignals:
    return MediaSignals(
        audio_energy=extract_audio_energy(path),
        scene_times=extract_scene_times(path),
    )
