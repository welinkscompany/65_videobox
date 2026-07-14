from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


MAX_FRAMES = 6
MAX_LONG_EDGE_PX = 768
MAX_FRAME_BYTES = 1_500_000
SUBPROCESS_TIMEOUT_SECONDS = 60


@dataclass(frozen=True, slots=True)
class RepresentativeFrame:
    data: bytes
    long_edge_px: int
    encoded_size_bytes: int
    timestamp_sec: float = 0.0


@dataclass(frozen=True, slots=True)
class MediaProbeResult:
    duration_sec: float
    codec: str | None
    width: int | None
    height: int | None
    aspect_ratio: float | None
    fps: float | None
    audio_codec: str | None
    scene_boundaries: tuple[float, ...]
    frames: tuple[RepresentativeFrame, ...]


class FFmpegMediaProbe:
    def __init__(self, ffmpeg_binary: str = "ffmpeg", ffprobe_binary: str = "ffprobe") -> None:
        self.ffmpeg_binary = ffmpeg_binary
        self.ffprobe_binary = ffprobe_binary
        self.ffmpeg_version = self._version(ffmpeg_binary)

    def _version(self, binary: str) -> str:
        try:
            output = subprocess.run([binary, "-version"], capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_SECONDS, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return "unknown"
        return (output.stdout or output.stderr).splitlines()[0].strip() or "unknown"

    def probe(self, path: Path) -> MediaProbeResult:
        completed = subprocess.run(
            [self.ffprobe_binary, "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_SECONDS, check=True,
        )
        try:
            payload = json.loads(completed.stdout)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("ffprobe returned corrupt metadata") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("format"), dict):
            raise ValueError("ffprobe returned corrupt metadata")
        streams = payload.get("streams") if isinstance(payload, dict) else []
        if not isinstance(streams, list):
            raise ValueError("ffprobe returned corrupt metadata")
        stream = next((item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video" and item.get("width") and item.get("height")), {})
        audio_stream = next((item for item in streams if isinstance(item, dict) and item.get("codec_type") == "audio"), {})
        width = self._int(stream.get("width"))
        height = self._int(stream.get("height"))
        try:
            duration = float((payload.get("format") or {}).get("duration") or 0.0)
        except (TypeError, ValueError) as exc:
            raise ValueError("ffprobe returned corrupt duration") from exc
        if duration < 0 or not width or not height:
            raise ValueError("ffprobe returned unusable media metadata")
        aspect = (width / height) if width and height else None
        fps = self._fps(stream.get("avg_frame_rate"))
        boundaries = (0.0, duration) if duration > 0 else (0.0,)
        frames = self._extract_representative_frames(path, duration, max(width or 0, height or 0, 1))
        return MediaProbeResult(duration, str(stream.get("codec_name") or "") or None, width, height, aspect, fps, str(audio_stream.get("codec_name") or "") or None, boundaries, frames)

    def _extract_representative_frames(self, path: Path, duration: float, long_edge_px: int) -> tuple[RepresentativeFrame, ...]:
        if duration <= 0:
            return ()
        # Evenly distributed stills are deterministic and deliberately bounded.  Scene-aware
        # providers can later refine `scene_boundaries` without expanding this extraction budget.
        timestamps = [duration * (index + 0.5) / MAX_FRAMES for index in range(MAX_FRAMES)]
        raw_frames: list[bytes] = []
        for timestamp in timestamps:
            try:
                completed = subprocess.run(
                    [self.ffmpeg_binary, "-v", "error", "-ss", f"{timestamp:.3f}", "-i", str(path), "-frames:v", "1", "-vf", f"scale='if(gte(iw,ih),{MAX_LONG_EDGE_PX},-2)':'if(gte(iw,ih),-2,{MAX_LONG_EDGE_PX})'", "-q:v", "4", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"],
                    capture_output=True, timeout=SUBPROCESS_TIMEOUT_SECONDS, check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if completed.returncode == 0 and isinstance(completed.stdout, bytes) and completed.stdout:
                raw_frames.append(completed.stdout)
        return self._bounded_frames(raw_frames, long_edge_px=long_edge_px)

    @staticmethod
    def _int(value: object) -> int | None:
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _fps(value: object) -> float | None:
        try:
            numerator, denominator = str(value).split("/", 1)
            parsed = float(numerator) / float(denominator)
            return parsed if parsed > 0 else None
        except (TypeError, ValueError, ZeroDivisionError):
            return None

    @staticmethod
    def _bounded_frames(frames: Iterable[bytes], *, long_edge_px: int) -> tuple[RepresentativeFrame, ...]:
        bounded: list[RepresentativeFrame] = []
        for raw in frames:
            if len(bounded) >= MAX_FRAMES:
                break
            # Cutting a JPEG byte stream produces a corrupt image. The extraction command
            # already requests a bounded scale/quality; reject an oversized result instead.
            if len(raw) > MAX_FRAME_BYTES:
                continue
            data = bytes(raw)
            bounded.append(RepresentativeFrame(data=data, long_edge_px=min(MAX_LONG_EDGE_PX, max(1, long_edge_px)), encoded_size_bytes=len(data)))
        return tuple(bounded)
