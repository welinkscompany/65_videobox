from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from videobox_core_engine.settings import AutoCutConfig


@dataclass(slots=True, frozen=True)
class AutoCutSegment:
    start_sec: float
    end_sec: float
    reasons: tuple[str, ...] = field(default_factory=tuple)
    avg_brightness: float | None = None
    scene_change_count: int | None = None

    @property
    def duration_sec(self) -> float:
        return max(0.0, self.end_sec - self.start_sec)


class AutoCutPlanner:
    def __init__(self, *, config: AutoCutConfig | None = None) -> None:
        self.config = config or AutoCutConfig()

    def should_auto_cut(self, *, total_duration: float) -> bool:
        return total_duration > self.config.auto_cut_threshold

    def build_scene_detection_filter(self) -> str:
        return f"select='gt(scene,{self.config.scene_threshold})',showinfo"

    def build_blackdetect_filter(self) -> str:
        return (
            f"blackdetect=d={self.config.blackdetect_min_duration}:"
            f"pic_th={self.config.blackdetect_picture_threshold}"
        )

    def parse_scene_timestamps(self, stderr_output: str) -> list[float]:
        timestamps: list[float] = []
        for line in stderr_output.splitlines():
            if "pts_time:" not in line:
                continue
            match = re.search(r"pts_time:([\d.]+)", line)
            if match is None:
                continue
            timestamp = float(match.group(1))
            if timestamp > self.config.initial_scene_ignore_seconds:
                timestamps.append(timestamp)
        return sorted(timestamps)

    def parse_black_regions(self, stderr_output: str) -> list[dict[str, float]]:
        regions: list[dict[str, float]] = []
        for line in stderr_output.splitlines():
            if "black_start" not in line:
                continue
            start_match = re.search(r"black_start:([\d.]+)", line)
            end_match = re.search(r"black_end:([\d.]+)", line)
            if start_match is None or end_match is None:
                continue
            regions.append(
                {
                    "start": float(start_match.group(1)),
                    "end": float(end_match.group(1)),
                }
            )
        return regions

    def plan_segments(
        self,
        *,
        total_duration: float,
        scene_timestamps: list[float],
        black_regions: list[dict[str, float]],
    ) -> list[AutoCutSegment]:
        cut_points = self._build_cut_points(
            total_duration=total_duration,
            scene_timestamps=scene_timestamps,
            black_regions=black_regions,
        )
        boundaries = [0.0, *cut_points, total_duration]
        segments: list[AutoCutSegment] = []
        for index in range(len(boundaries) - 1):
            start_sec = boundaries[index]
            end_sec = boundaries[index + 1]
            if end_sec <= start_sec:
                continue
            segments.append(AutoCutSegment(start_sec=start_sec, end_sec=end_sec))
        return segments

    def filter_segments(self, segment_samples: list[dict[str, Any]]) -> list[AutoCutSegment]:
        kept: list[AutoCutSegment] = []
        for sample in segment_samples:
            segment = AutoCutSegment(
                start_sec=float(sample["start_sec"]),
                end_sec=float(sample["end_sec"]),
                avg_brightness=float(sample["avg_brightness"]) if sample.get("avg_brightness") is not None else None,
                scene_change_count=int(sample["scene_change_count"])
                if sample.get("scene_change_count") is not None
                else None,
            )
            if segment.duration_sec < self.config.min_clip_duration:
                continue
            if segment.avg_brightness is not None and segment.avg_brightness < self.config.dark_brightness:
                continue
            if (
                segment.scene_change_count is not None
                and segment.scene_change_count == 0
                and segment.duration_sec > self.config.static_duration
            ):
                continue
            kept.append(segment)
        return kept

    def _build_cut_points(
        self,
        *,
        total_duration: float,
        scene_timestamps: list[float],
        black_regions: list[dict[str, float]],
    ) -> list[float]:
        cut_points: set[float] = set()
        for timestamp in scene_timestamps:
            if 0.0 < timestamp < total_duration:
                cut_points.add(round(float(timestamp), 2))
        for region in black_regions:
            end_sec = float(region.get("end", 0.0))
            if 0.0 < end_sec < total_duration:
                cut_points.add(round(end_sec, 2))

        cut_points = self._enforce_max_clip_duration(
            cut_points=sorted(cut_points),
            total_duration=total_duration,
        )

        proximity_merged: list[float] = []
        for timestamp in cut_points:
            if (
                not proximity_merged
                or timestamp - proximity_merged[-1] >= self.config.cut_point_min_spacing
            ):
                proximity_merged.append(timestamp)
        merged_points = self._merge_short_adjacent_segments(
            cut_points=proximity_merged,
            total_duration=total_duration,
        )
        return self._enforce_max_clip_duration(
            cut_points=merged_points,
            total_duration=total_duration,
        )

    def _merge_short_adjacent_segments(
        self,
        *,
        cut_points: list[float],
        total_duration: float,
    ) -> list[float]:
        final_points = list(cut_points)
        while final_points:
            boundaries = [0.0, *final_points, total_duration]
            cut_index_to_remove: int | None = None
            for index in range(1, len(boundaries) - 1):
                left_duration = boundaries[index] - boundaries[index - 1]
                right_duration = boundaries[index + 1] - boundaries[index]
                is_first_cut = index == 1
                is_last_cut = index == len(boundaries) - 2
                if left_duration <= self.config.merge_threshold and right_duration <= self.config.merge_threshold:
                    cut_index_to_remove = index - 1
                    break
                if (
                    is_first_cut
                    and left_duration < self.config.min_clip_duration
                ):
                    cut_index_to_remove = index - 1
                    break
                if not is_last_cut and right_duration < self.config.min_clip_duration:
                    cut_index_to_remove = index - 1
                    break
                if is_last_cut and right_duration < self.config.min_clip_duration:
                    cut_index_to_remove = index - 1
                    break

            if cut_index_to_remove is None:
                break

            final_points.pop(cut_index_to_remove)

        return final_points

    def _enforce_max_clip_duration(
        self,
        *,
        cut_points: list[float],
        total_duration: float,
    ) -> list[float]:
        boundaries = [0.0, *cut_points, total_duration]
        final_points = list(cut_points)
        for index in range(len(boundaries) - 1):
            segment_start = boundaries[index]
            segment_end = boundaries[index + 1]
            segment_length = segment_end - segment_start
            if segment_length > self.config.max_clip_duration:
                part_count = int(segment_length // self.config.max_clip_duration) + 1
                for part_index in range(1, part_count):
                    final_points.append(round(segment_start + segment_length * part_index / part_count, 2))
        return sorted(set(final_points))


__all__ = ["AutoCutConfig", "AutoCutPlanner", "AutoCutSegment"]
