from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videobox_core_engine.reference_style_analysis import (
    ReferenceStyleAnalysisError,
    analyze_color,
    analyze_pacing,
)

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _generate(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_analyze_color_reports_a_bright_red_video_as_warm_and_bright(tmp_path: Path) -> None:
    video = tmp_path / "warm.mp4"
    # 순수 빨강 화면 -- 밝고 따뜻해야 한다.
    _generate([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=64x64:d=3",
        str(video),
    ])

    profile = analyze_color(video, sample_interval_sec=1.0)

    assert profile.warm_cool_bias > 20
    assert profile.average_brightness > 60
    assert profile.sample_count >= 2


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_analyze_color_reports_a_blue_video_as_cool(tmp_path: Path) -> None:
    video = tmp_path / "cool.mp4"
    _generate([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=3",
        str(video),
    ])

    profile = analyze_color(video, sample_interval_sec=1.0)

    assert profile.warm_cool_bias < -20


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_analyze_color_reports_a_dark_video_as_low_brightness(tmp_path: Path) -> None:
    video = tmp_path / "dark.mp4"
    _generate([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=3",
        str(video),
    ])

    profile = analyze_color(video, sample_interval_sec=1.0)

    assert profile.average_brightness < 20


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_analyze_pacing_counts_distinct_hard_cuts(tmp_path: Path) -> None:
    # 색이 다른 장면 셋을 이어 붙인다 -- 컷이 두 번 있는 3.6초짜리 영상.
    segment_paths = []
    for index, color in enumerate(["red", "green", "blue"]):
        segment = tmp_path / f"segment-{index}.mp4"
        _generate([
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=64x64:d=1.2:r=15",
            "-pix_fmt", "yuv420p", str(segment),
        ])
        segment_paths.append(segment)
    concat_list = tmp_path / "concat.txt"
    concat_list.write_text("".join(f"file '{path.name}'\n" for path in segment_paths), encoding="utf-8")
    joined = tmp_path / "joined.mp4"
    _generate([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c", "copy", str(joined),
    ])

    profile = analyze_pacing(joined)

    assert profile.clip_count >= 2
    assert profile.average_clip_duration_sec > 0
    assert profile.shortest_clip_sec <= profile.average_clip_duration_sec <= profile.longest_clip_sec


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_analyze_pacing_on_a_single_unbroken_shot_reports_one_clip(tmp_path: Path) -> None:
    video = tmp_path / "single-shot.mp4"
    _generate([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=gray:s=64x64:d=3",
        str(video),
    ])

    profile = analyze_pacing(video)

    assert profile.clip_count == 1
    assert profile.average_clip_duration_sec == pytest.approx(3.0, abs=0.5)


def test_analyze_color_raises_a_clear_error_for_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ReferenceStyleAnalysisError):
        analyze_color(tmp_path / "does-not-exist.mp4")


def test_analyze_pacing_raises_a_clear_error_for_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ReferenceStyleAnalysisError):
        analyze_pacing(tmp_path / "does-not-exist.mp4")
