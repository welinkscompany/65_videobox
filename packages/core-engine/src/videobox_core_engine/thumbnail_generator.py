from __future__ import annotations

import subprocess
from pathlib import Path


class ThumbnailGenerationError(RuntimeError):
    pass


def generate_video_thumbnail(
    video_path: Path,
    output_path: Path,
    *,
    ffmpeg_binary: str = "ffmpeg",
    timestamp_sec: float = 0.5,
    timeout_seconds: int = 30,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg_binary,
        "-y",
        "-ss",
        str(timestamp_sec),
        "-i",
        str(video_path),
        "-vframes",
        "1",
        "-vf",
        "scale=320:-1",
        str(output_path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds)
    except FileNotFoundError as exc:
        raise ThumbnailGenerationError(f"'{ffmpeg_binary}' binary was not found.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ThumbnailGenerationError(f"'{ffmpeg_binary}' timed out after {timeout_seconds}s.") from exc
    if result.returncode != 0 or not output_path.exists():
        raise ThumbnailGenerationError(f"ffmpeg failed to generate thumbnail: {result.stderr}")


__all__ = ["ThumbnailGenerationError", "generate_video_thumbnail"]
