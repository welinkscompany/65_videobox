from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from videobox_core_engine.auto_cut import AutoCutPlanner

_YAVG_PATTERN = re.compile(r"YAVG[=:]([\d.]+)")


class FfmpegExecutionError(RuntimeError):
    pass


@dataclass(slots=True)
class FfmpegAutoCutExecutor:
    planner: AutoCutPlanner
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    detection_timeout_seconds: int = 300
    probe_timeout_seconds: int = 30
    brightness_sample_seconds: float = 5.0

    def _run(self, command: list[str], *, timeout: int, binary: str) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError as exc:
            raise FfmpegExecutionError(f"'{binary}' binary was not found. Install ffmpeg to enable auto-cut.") from exc
        except subprocess.TimeoutExpired as exc:
            raise FfmpegExecutionError(f"'{binary}' timed out after {timeout}s.") from exc

    def get_duration(self, video_path: Path) -> float:
        command = [
            self.ffprobe_binary,
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        result = self._run(command, timeout=self.probe_timeout_seconds, binary=self.ffprobe_binary)
        try:
            return float(result.stdout.strip())
        except ValueError:
            return 0.0

    def detect_scene_timestamps(self, video_path: Path) -> list[float]:
        command = [
            self.ffmpeg_binary,
            "-i",
            str(video_path),
            "-vf",
            self.planner.build_scene_detection_filter(),
            "-vsync",
            "vfr",
            "-f",
            "null",
            "-",
        ]
        result = self._run(command, timeout=self.detection_timeout_seconds, binary=self.ffmpeg_binary)
        return self.planner.parse_scene_timestamps(result.stderr)

    def detect_black_regions(self, video_path: Path) -> list[dict[str, float]]:
        command = [
            self.ffmpeg_binary,
            "-i",
            str(video_path),
            "-vf",
            self.planner.build_blackdetect_filter(),
            "-f",
            "null",
            "-",
        ]
        result = self._run(command, timeout=self.detection_timeout_seconds, binary=self.ffmpeg_binary)
        return self.planner.parse_black_regions(result.stderr)

    def measure_clip_brightness(self, video_path: Path, *, start_sec: float, duration_sec: float) -> float:
        sample_duration = max(0.1, min(duration_sec, self.brightness_sample_seconds))
        command = [
            self.ffmpeg_binary,
            "-ss",
            str(start_sec),
            "-t",
            str(sample_duration),
            "-i",
            str(video_path),
            "-vf",
            "scale=64:64,signalstats",
            "-f",
            "null",
            "-",
        ]
        result = self._run(command, timeout=self.probe_timeout_seconds, binary=self.ffmpeg_binary)
        match = _YAVG_PATTERN.search(result.stderr)
        return float(match.group(1)) if match else 128.0

    def count_scene_changes(self, video_path: Path, *, start_sec: float, duration_sec: float) -> int:
        command = [
            self.ffmpeg_binary,
            "-ss",
            str(start_sec),
            "-t",
            str(duration_sec),
            "-i",
            str(video_path),
            "-vf",
            self.planner.build_static_check_filter(),
            "-vsync",
            "vfr",
            "-f",
            "null",
            "-",
        ]
        result = self._run(command, timeout=self.detection_timeout_seconds, binary=self.ffmpeg_binary)
        return result.stderr.count("pts_time")

    def run_full_detection(self, video_path: Path) -> dict[str, Any]:
        total_duration = self.get_duration(video_path)
        scene_timestamps = self.detect_scene_timestamps(video_path)
        black_regions = self.detect_black_regions(video_path)
        planned_segments = self.planner.plan_segments(
            total_duration=total_duration,
            scene_timestamps=scene_timestamps,
            black_regions=black_regions,
        )
        segment_samples = [
            {
                "start_sec": segment.start_sec,
                "end_sec": segment.end_sec,
                "avg_brightness": self.measure_clip_brightness(
                    video_path,
                    start_sec=segment.start_sec,
                    duration_sec=segment.duration_sec,
                ),
                "scene_change_count": self.count_scene_changes(
                    video_path,
                    start_sec=segment.start_sec,
                    duration_sec=segment.duration_sec,
                ),
            }
            for segment in planned_segments
        ]
        return {
            "total_duration": total_duration,
            "scene_timestamps": scene_timestamps,
            "black_regions": black_regions,
            "segment_samples": segment_samples,
        }


__all__ = ["FfmpegAutoCutExecutor", "FfmpegExecutionError"]
