"""참고 영상(주로 본인 유튜브 영상)에서 컷 빠르기·색감을 재서 보여준다.

owner 요청(2026-08-29): "편집 스타일(컷 타이밍·색감)"을 내 영상에서 배우게.

**정직하게 밝혀 둘 것: 지금은 보여주기만 한다, 자동으로 입히지 않는다.**
- 컷 빠르기: `auto_cut.py`의 장면 전환 감지를 그대로 재사용해 평균 컷 길이를
  잰다. 이 값을 실제 자동 컷(`AutoCutConfig`)에 자동으로 먹이려면 지금 앱
  전체가 공유하는 전역 설정 하나를 프로젝트별로 바꿀 수 있게 구조를 바꿔야
  한다 -- 이번 범위 밖이라 숫자만 보여준다.
- 색감: 전문 색보정은 이 프로젝트의 제품 범위 밖으로 못박혀 있다
  (`CLAUDE.md` §2.1: "전문 색보정... 범위 밖"). 그래서 색을 실제로 입히는
  기능은 만들지 않았다 -- 밝기·채도·톤(따뜻함/차가움)을 **재서 알려주기만**
  한다. 실제로 적용하려면 별도 승인이 필요하다.

둘 다 ffmpeg의 `signalstats` 필터만 쓴다 -- 새 이미지 라이브러리가 필요 없고,
이 저장소가 이미 쓰는 "ffmpeg로 재고 정규식으로 읽는다" 방식 그대로다.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


class ReferenceStyleAnalysisError(RuntimeError):
    pass


@dataclass(slots=True, frozen=True)
class PacingProfile:
    #: 평균 컷 길이(초). 짧을수록 빠르게 전환하는 편집이다.
    average_clip_duration_sec: float
    clip_count: int
    shortest_clip_sec: float
    longest_clip_sec: float


@dataclass(slots=True, frozen=True)
class ColorProfile:
    #: 0~255. 낮을수록 어둡다.
    average_brightness: float
    #: 0 근처는 무채색에 가깝고, 클수록 색이 뚜렷하다(대략적인 지표다 --
    #: 픽셀별 채도의 정확한 평균이 아니라 프레임 평균 색의 중심에서 벗어난 정도다).
    average_colorfulness: float
    #: 양수면 따뜻한(붉은) 쪽, 음수면 차가운(푸른) 쪽으로 치우쳐 있다.
    warm_cool_bias: float
    sample_count: int


_SIGNALSTATS_PATTERN = re.compile(
    r"lavfi\.signalstats\.(YAVG|UAVG|VAVG)=([\d.-]+)"
)


def _run_signalstats(
    video_path: Path, *, sample_interval_sec: float, ffmpeg_binary: str, timeout_seconds: float
) -> list[dict[str, float]]:
    if not video_path.is_file():
        raise ReferenceStyleAnalysisError("reference_video_missing")
    command = [
        ffmpeg_binary, "-y", "-i", str(video_path),
        "-vf", f"fps=1/{sample_interval_sec},signalstats,metadata=print",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise ReferenceStyleAnalysisError(f"'{ffmpeg_binary}' binary was not found. Install ffmpeg.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ReferenceStyleAnalysisError(f"ffmpeg timed out after {timeout_seconds}s.") from exc
    samples: list[dict[str, float]] = []
    current: dict[str, float] = {}
    for match in _SIGNALSTATS_PATTERN.finditer(result.stderr):
        key, value = match.group(1), float(match.group(2))
        current[key] = value
        if len(current) == 3:
            samples.append(current)
            current = {}
    return samples


def analyze_color(
    video_path: Path,
    *,
    sample_interval_sec: float = 2.0,
    ffmpeg_binary: str = "ffmpeg",
    # owner 결정(2026-08-29): 유튜브 학습 다운로드는 10분(600s)까지 허용하는데
    # 이 값이 3분(180s)에 그쳐 있었다 -- 다운로드는 되는데 분석에서 이유를 알
    # 수 없이 실패하는 영상 구간(3~10분)이 있었다. 다운로드 한도와 맞춘다.
    timeout_seconds: float = 600.0,
) -> ColorProfile:
    samples = _run_signalstats(
        video_path, sample_interval_sec=sample_interval_sec,
        ffmpeg_binary=ffmpeg_binary, timeout_seconds=timeout_seconds,
    )
    if not samples:
        raise ReferenceStyleAnalysisError("reference_video_has_no_frames")
    avg_y = sum(sample["YAVG"] for sample in samples) / len(samples)
    avg_u = sum(sample["UAVG"] for sample in samples) / len(samples)
    avg_v = sum(sample["VAVG"] for sample in samples) / len(samples)
    colorfulness = ((avg_u - 128.0) ** 2 + (avg_v - 128.0) ** 2) ** 0.5
    warm_cool_bias = avg_v - avg_u
    return ColorProfile(
        average_brightness=avg_y,
        average_colorfulness=colorfulness,
        warm_cool_bias=warm_cool_bias,
        sample_count=len(samples),
    )


def analyze_pacing(
    video_path: Path,
    *,
    scene_threshold: float = 0.4,
    initial_scene_ignore_seconds: float = 0.5,
    ffmpeg_binary: str = "ffmpeg",
    ffprobe_binary: str = "ffprobe",
    # analyze_color와 같은 이유로 600s(다운로드 한도)로 맞춘다.
    timeout_seconds: float = 600.0,
) -> PacingProfile:
    if not video_path.is_file():
        raise ReferenceStyleAnalysisError("reference_video_missing")
    scene_command = [
        ffmpeg_binary, "-i", str(video_path),
        "-vf", f"select='gt(scene,{scene_threshold})',showinfo",
        "-f", "null", "-",
    ]
    try:
        scene_result = subprocess.run(
            scene_command, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise ReferenceStyleAnalysisError(f"'{ffmpeg_binary}' binary was not found. Install ffmpeg.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ReferenceStyleAnalysisError(f"ffmpeg timed out after {timeout_seconds}s.") from exc

    timestamps: list[float] = []
    for line in scene_result.stderr.splitlines():
        if "pts_time:" not in line:
            continue
        match = re.search(r"pts_time:([\d.]+)", line)
        if match is None:
            continue
        timestamp = float(match.group(1))
        if timestamp > initial_scene_ignore_seconds:
            timestamps.append(timestamp)
    timestamps.sort()

    duration = _probe_duration_sec(video_path, ffprobe_binary=ffprobe_binary, timeout_seconds=timeout_seconds)
    boundaries = [0.0, *timestamps, duration]
    clip_lengths = [
        boundaries[index + 1] - boundaries[index]
        for index in range(len(boundaries) - 1)
        if boundaries[index + 1] > boundaries[index]
    ]
    if not clip_lengths:
        raise ReferenceStyleAnalysisError("reference_video_has_no_detectable_cuts")
    return PacingProfile(
        average_clip_duration_sec=sum(clip_lengths) / len(clip_lengths),
        clip_count=len(clip_lengths),
        shortest_clip_sec=min(clip_lengths),
        longest_clip_sec=max(clip_lengths),
    )


def _probe_duration_sec(video_path: Path, *, ffprobe_binary: str, timeout_seconds: float) -> float:
    command = [
        ffprobe_binary, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video_path),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout_seconds,
        )
        return float(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError) as exc:
        raise ReferenceStyleAnalysisError("reference_video_duration_unavailable") from exc


__all__ = [
    "ReferenceStyleAnalysisError",
    "PacingProfile",
    "ColorProfile",
    "analyze_pacing",
    "analyze_color",
]
