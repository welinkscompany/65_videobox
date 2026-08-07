from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


MAX_FRAMES = 6
MAX_LONG_EDGE_PX = 768
MAX_FRAME_BYTES = 1_500_000
SUBPROCESS_TIMEOUT_SECONDS = 60
# Task 27. ffmpeg's own scene score: how different a frame is from the one
# before it. 0.3 is the usual working value -- low enough to catch a real cut,
# high enough to ignore a pan or a lighting shift. Measured on the owner's
# footage: an eight-minute edited video yields 11 cuts, and continuous phone
# takes correctly yield none.
SCENE_CHANGE_THRESHOLD = 0.3
# Scene detection decodes the whole file. Measured at ~7s for a 521MB
# eight-minute clip, so it is affordable on the analysis path -- but a stuck
# decode must not hang analysis, hence its own wider ceiling.
SCENE_DETECT_TIMEOUT_SECONDS = 300


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
        """Full probe including representative frames, for vision analysis."""
        return self._probe(path, with_frames=True)

    def probe_metadata(self, path: Path) -> MediaProbeResult:
        """Metadata only -- one ffprobe call, no frame extraction.

        Asset intake needs size, length, and audio presence but not the six
        stills the vision path uses, so it must not pay for them.
        """
        return self._probe(path, with_frames=False)

    def _probe(self, path: Path, *, with_frames: bool) -> MediaProbeResult:
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
        if duration <= 0:
            boundaries: tuple[float, ...] = (0.0,)
        elif with_frames:
            # Only the analysis path pays for a full decode. `probe_metadata`
            # runs on every asset registration and must stay one ffprobe call.
            boundaries = self._detect_scene_boundaries(path, duration)
        else:
            boundaries = (0.0, duration)
        frames = (
            self._extract_representative_frames(path, duration, max(width or 0, height or 0, 1))
            if with_frames
            else ()
        )
        return MediaProbeResult(duration, str(stream.get("codec_name") or "") or None, width, height, aspect, fps, str(audio_stream.get("codec_name") or "") or None, boundaries, frames)

    def _detect_scene_boundaries(self, path: Path, duration: float) -> tuple[float, ...]:
        """Cut points inside the clip, as `(0.0, ...cuts..., duration)`.

        Best-effort: footage that cannot be decoded still analyzes, it just
        reports one whole-clip window the way it did before detection existed.
        A continuous take genuinely has no cuts, so one window is the correct
        answer for it -- not a failure.
        """
        try:
            completed = subprocess.run(
                [self.ffmpeg_binary, "-i", str(path), "-filter:v",
                 f"select='gt(scene,{SCENE_CHANGE_THRESHOLD})',showinfo", "-f", "null", "-"],
                capture_output=True, text=True, errors="replace",
                timeout=SCENE_DETECT_TIMEOUT_SECONDS, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return (0.0, duration)
        cuts = sorted(
            {
                rounded
                for value in re.findall(r"pts_time:([0-9]+\.?[0-9]*)", completed.stderr or "")
                if 0.0 < (rounded := round(float(value), 3)) < duration
            }
        )
        return (0.0, *cuts, duration)

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
