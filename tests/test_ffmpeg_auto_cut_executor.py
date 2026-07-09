from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videobox_core_engine.auto_cut import AutoCutPlanner
from videobox_core_engine.ffmpeg_auto_cut_executor import (
    FfmpegAutoCutExecutor,
    FfmpegExecutionError,
)
from videobox_core_engine.settings import AutoCutConfig

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _fake_result(*, returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _patch_subprocess_run(monkeypatch: pytest.MonkeyPatch, fn) -> None:
    monkeypatch.setattr("videobox_core_engine.ffmpeg_auto_cut_executor.subprocess.run", fn)


def test_get_duration_parses_ffprobe_stdout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    executor = FfmpegAutoCutExecutor(planner=AutoCutPlanner())
    _patch_subprocess_run(monkeypatch, lambda command, **kwargs: _fake_result(stdout="123.45\n"))

    assert executor.get_duration(tmp_path / "clip.mp4") == pytest.approx(123.45)


def test_detect_scene_timestamps_delegates_to_planner_parser(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    executor = FfmpegAutoCutExecutor(planner=AutoCutPlanner())
    stderr = "[Parsed_showinfo_1 @ 0x0] n:0 pts_time:12.3\n[Parsed_showinfo_1 @ 0x0] n:1 pts_time:45.6\n"
    _patch_subprocess_run(monkeypatch, lambda command, **kwargs: _fake_result(stderr=stderr))

    assert executor.detect_scene_timestamps(tmp_path / "clip.mp4") == [12.3, 45.6]


def test_detect_black_regions_delegates_to_planner_parser(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    executor = FfmpegAutoCutExecutor(planner=AutoCutPlanner())
    stderr = "[blackdetect @ 0x0] black_start:5.0 black_end:6.5 black_duration:1.5\n"
    _patch_subprocess_run(monkeypatch, lambda command, **kwargs: _fake_result(stderr=stderr))

    assert executor.detect_black_regions(tmp_path / "clip.mp4") == [{"start": 5.0, "end": 6.5}]


def test_measure_clip_brightness_parses_yavg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    executor = FfmpegAutoCutExecutor(planner=AutoCutPlanner())
    captured_commands: list[list[str]] = []

    def _capture(command: list[str], **kwargs: object):
        captured_commands.append(command)
        # Real ffmpeg (verified against an actual signalstats+metadata=print run)
        # logs one line like this per frame, not a single summary line.
        return _fake_result(stderr="[Parsed_metadata_2 @ 0x0] lavfi.signalstats.YAVG=42.7\n")

    _patch_subprocess_run(monkeypatch, _capture)

    brightness = executor.measure_clip_brightness(tmp_path / "clip.mp4", start_sec=0.0, duration_sec=5.0)

    assert brightness == pytest.approx(42.7)
    assert any("metadata=print" in part for part in captured_commands[0])


def test_measure_clip_brightness_falls_back_when_unparseable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executor = FfmpegAutoCutExecutor(planner=AutoCutPlanner())
    _patch_subprocess_run(monkeypatch, lambda command, **kwargs: _fake_result(stderr="no stats here"))

    assert executor.measure_clip_brightness(tmp_path / "clip.mp4", start_sec=0.0, duration_sec=5.0) == 128.0


def test_count_scene_changes_uses_static_check_filter_not_cut_filter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    planner = AutoCutPlanner(config=AutoCutConfig(scene_threshold=0.4, static_check_scene_threshold=0.02))
    executor = FfmpegAutoCutExecutor(planner=planner)
    captured_commands: list[list[str]] = []

    def _capture(command: list[str], **kwargs: object):
        captured_commands.append(command)
        return _fake_result(stderr="pts_time:1.0\npts_time:2.0\npts_time:3.0\n")

    _patch_subprocess_run(monkeypatch, _capture)

    count = executor.count_scene_changes(tmp_path / "clip.mp4", start_sec=0.0, duration_sec=10.0)

    assert count == 3
    assert any("0.02" in part for part in captured_commands[0])
    assert not any("gt(scene,0.4)" in part for part in captured_commands[0])


def test_detect_scene_and_black_regions_combines_both_parsers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executor = FfmpegAutoCutExecutor(planner=AutoCutPlanner())
    stderr = (
        "[Parsed_showinfo_2 @ 0x0] n:0 pts_time:10\n"
        "[Parsed_blackdetect_3 @ 0x0] black_start:8 black_end:9.8 black_duration:1.8\n"
    )
    captured_commands: list[list[str]] = []

    def _capture(command: list[str], **kwargs: object):
        captured_commands.append(command)
        return _fake_result(stderr=stderr)

    _patch_subprocess_run(monkeypatch, _capture)

    scene_timestamps, black_regions = executor.detect_scene_and_black_regions(tmp_path / "clip.mp4")

    assert scene_timestamps == [10.0]
    assert black_regions == [{"start": 8.0, "end": 9.8}]
    assert any("split=2" in part for part in captured_commands[0])


def test_scaled_detection_timeout_grows_with_duration(tmp_path: Path) -> None:
    executor = FfmpegAutoCutExecutor(planner=AutoCutPlanner(), detection_timeout_seconds=300)

    assert executor._scaled_detection_timeout(60.0) == 300
    assert executor._scaled_detection_timeout(3600.0) == 5400


def test_run_full_detection_raises_helpful_error_when_ffmpeg_missing(tmp_path: Path) -> None:
    executor = FfmpegAutoCutExecutor(planner=AutoCutPlanner(), ffmpeg_binary="videobox-nonexistent-ffmpeg")

    with pytest.raises(FfmpegExecutionError, match="was not found"):
        executor.detect_scene_timestamps(tmp_path / "clip.mp4")


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_run_full_detection_against_a_real_synthetic_video(tmp_path: Path) -> None:
    video_path = tmp_path / "synthetic.mp4"
    generate = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=3:size=64x64:rate=10",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert generate.returncode == 0, generate.stderr

    config = AutoCutConfig(min_clip_duration=0.1)
    executor = FfmpegAutoCutExecutor(planner=AutoCutPlanner(config=config))

    detection = executor.run_full_detection(video_path)

    assert detection["total_duration"] == pytest.approx(3.0, abs=0.5)
    assert isinstance(detection["segment_samples"], list)
    assert len(detection["segment_samples"]) >= 1
    for sample in detection["segment_samples"]:
        assert sample["avg_brightness"] is not None
        assert sample["scene_change_count"] is not None
