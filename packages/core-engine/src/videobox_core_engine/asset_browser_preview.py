from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class BrowserPreviewError(RuntimeError):
    """A bounded browser-preview failure safe to expose as an error code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class BrowserPreviewMediaInfo:
    container_names: tuple[str, ...]
    video_codec: str
    pixel_format: str
    audio_codec: str | None
    width: int
    height: int

    @property
    def browser_compatible(self) -> bool:
        return (
            bool({"mov", "mp4"}.intersection(self.container_names))
            and self.video_codec == "h264"
            and self.pixel_format == "yuv420p"
            and self.audio_codec in {None, "aac"}
        )


class FFprobeBrowserPreviewProbe:
    def __init__(self, ffprobe_binary: str = "ffprobe", timeout_seconds: int = 30) -> None:
        self.ffprobe_binary = ffprobe_binary
        self.timeout_seconds = timeout_seconds

    def probe(self, source: Path) -> BrowserPreviewMediaInfo:
        command = [
            self.ffprobe_binary,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(source),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BrowserPreviewError("PREVIEW_PROBE_UNAVAILABLE") from exc
        if completed.returncode != 0:
            raise BrowserPreviewError("PREVIEW_PROBE_FAILED")
        try:
            payload: dict[str, Any] = json.loads(completed.stdout)
            streams = payload["streams"]
            format_names = str(payload["format"]["format_name"]).split(",")
            video = next(stream for stream in streams if stream.get("codec_type") == "video")
            audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
            return BrowserPreviewMediaInfo(
                container_names=tuple(name.strip().lower() for name in format_names if name.strip()),
                video_codec=str(video["codec_name"]).lower(),
                pixel_format=str(video["pix_fmt"]).lower(),
                audio_codec=str(audio["codec_name"]).lower() if audio is not None else None,
                width=int(video["width"]),
                height=int(video["height"]),
            )
        except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise BrowserPreviewError("PREVIEW_PROBE_INVALID") from exc


class FFmpegBrowserPreviewRenderer:
    def __init__(self, ffmpeg_binary: str = "ffmpeg", timeout_seconds: int = 3600) -> None:
        self.ffmpeg_binary = ffmpeg_binary
        self.timeout_seconds = timeout_seconds

    def render(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        scale = "scale='if(gte(iw,ih),min(iw,1280),-2)':'if(gte(iw,ih),-2,min(ih,1280))'"
        command = [
            self.ffmpeg_binary,
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-vf",
            scale,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-tag:v",
            "avc1",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
            str(destination),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BrowserPreviewError("PREVIEW_RENDER_UNAVAILABLE") from exc
        if completed.returncode != 0:
            raise BrowserPreviewError("PREVIEW_RENDER_FAILED")
        if not destination.is_file() or destination.stat().st_size <= 0:
            raise BrowserPreviewError("PREVIEW_RENDER_EMPTY")
