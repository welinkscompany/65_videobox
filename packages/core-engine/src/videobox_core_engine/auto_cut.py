from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Any, Iterable, Mapping

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

    def build_static_check_filter(self) -> str:
        return f"select='gt(scene,{self.config.static_check_scene_threshold})',showinfo"

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

    def build_footage_suggestions(
        self,
        *,
        total_duration: float,
        scene_timestamps: Iterable[float] = (),
        black_regions: Iterable[Mapping[str, Any]] = (),
        static_windows: Iterable[Mapping[str, Any]] = (),
        audio_windows: Iterable[Mapping[str, Any]] = (),
        analysis_windows: Iterable[Mapping[str, Any]] = (),
    ) -> list[dict[str, Any]]:
        """Turn independent measurements into bounded, reviewable windows.

        This is deliberately a pure operation.  It only creates references to
        the source timeline; it never edits an editing session or source file.
        Invalid/non-finite measurements are ignored and all resulting bounds
        are clamped to the measured duration.
        """
        try:
            duration = float(total_duration)
        except (TypeError, ValueError):
            return []
        if not math.isfinite(duration) or duration <= 0:
            return []

        scenes = sorted({point for point in self._finite_points(scene_timestamps) if 0 < point < duration})
        black = self._normalize_windows(black_regions, duration)
        static = self._normalize_windows(static_windows, duration)
        audio = self._normalize_windows(audio_windows, duration)
        analysis = self._normalize_windows(analysis_windows, duration)

        boundaries = {0.0, duration, *scenes}
        for windows in (black, static, audio, analysis):
            for start, end in windows:
                boundaries.update((start, end))
        ordered = sorted(boundaries)
        suggestions: list[dict[str, Any]] = []
        labels = {
            "scene_change": "장면이 바뀐 지점이에요",
            "black_screen": "검은 화면이 감지됐어요",
            "static_scene": "화면 변화가 거의 없어요",
            "audio_activity": "소리가 있는 구간이에요",
            "analysis_window": "분석된 구간이에요",
        }
        for start, end in zip(ordered, ordered[1:]):
            if end <= start:
                continue
            reasons: list[str] = []
            if any(math.isclose(start, point, abs_tol=1e-6) for point in scenes):
                reasons.append("scene_change")
            if self._overlaps((start, end), black):
                reasons.append("black_screen")
            if self._overlaps((start, end), static):
                reasons.append("static_scene")
            if self._overlaps((start, end), audio):
                reasons.append("audio_activity")
            if self._overlaps((start, end), analysis):
                reasons.append("analysis_window")
            suggestions.append(
                {
                    "start_sec": round(start, 6),
                    "end_sec": round(end, 6),
                    "reason_codes": reasons,
                    "reason_labels": [labels[reason] for reason in reasons],
                }
            )
        return suggestions

    # A descriptive alias keeps callers independent from the auto-cut name.
    suggest_footage_segments = build_footage_suggestions

    @staticmethod
    def _finite_points(values: Iterable[float]) -> list[float]:
        result: list[float] = []
        for value in values:
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(number):
                result.append(number)
        return result

    @classmethod
    def _normalize_windows(
        cls, values: Iterable[Any], duration: float
    ) -> list[tuple[float, float]]:
        result: list[tuple[float, float]] = []
        for raw in values:
            if isinstance(raw, Mapping):
                start_value = raw.get("start_sec", raw.get("start", 0.0))
                end_value = raw.get("end_sec", raw.get("end", 0.0))
            elif isinstance(raw, (tuple, list)) and len(raw) >= 2:
                start_value, end_value = raw[0], raw[1]
            else:
                continue
            try:
                start = float(start_value)
                end = float(end_value)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(start) or not math.isfinite(end):
                continue
            start, end = max(0.0, start), min(duration, end)
            if end > start:
                result.append((round(start, 6), round(end, 6)))
        return result

    @staticmethod
    def _overlaps(window: tuple[float, float], candidates: Iterable[tuple[float, float]]) -> bool:
        start, end = window
        return any(start < candidate_end and end > candidate_start for candidate_start, candidate_end in candidates)

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
