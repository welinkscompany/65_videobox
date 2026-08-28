"""완성본에서 오디오 트랙만 뽑아낸다 (owner 요청 2026-08-28: "오디오만... 내보내기").

새 렌더 파이프라인을 만들지 않는다 -- 이미 만들어진 완성본 mp4가 있으므로, 거기서
`-vn`으로 오디오만 다시 인코딩 없이(`-c:a copy`가 안 되면 aac로) 떠내는 게 정직한
범위다. `ffmpeg_final_renderer.py`의 `_run`과 같은 subprocess 관례(캡처·타임아웃)를
따른다.

**캐시한다.** 같은 완성본에서 여러 번 눌러도 매번 ffmpeg를 돌리지 않는다 -- 원본
mp4보다 새 캐시 파일이 있으면 그대로 돌려준다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class AudioExportError(RuntimeError):
    pass


def extract_audio_only(
    *,
    source_video_path: Path,
    destination_audio_path: Path,
    ffmpeg_binary: str = "ffmpeg",
    timeout_seconds: float = 120.0,
) -> Path:
    """`source_video_path`의 오디오 트랙을 `destination_audio_path`(.m4a)로 뽑는다."""

    if not source_video_path.is_file():
        raise AudioExportError("source_video_missing")
    if (
        destination_audio_path.is_file()
        and destination_audio_path.stat().st_mtime >= source_video_path.stat().st_mtime
    ):
        return destination_audio_path

    destination_audio_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg_binary, "-y",
        "-i", str(source_video_path),
        "-vn", "-acodec", "aac", "-b:a", "192k",
        str(destination_audio_path),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise AudioExportError(f"'{ffmpeg_binary}' binary was not found. Install ffmpeg.") from exc
    except subprocess.TimeoutExpired as exc:
        raise AudioExportError(f"ffmpeg timed out after {timeout_seconds}s.") from exc
    if result.returncode != 0 or not destination_audio_path.is_file():
        destination_audio_path.unlink(missing_ok=True)
        raise AudioExportError(f"ffmpeg failed to extract audio: {result.stderr[-2000:]}")
    return destination_audio_path
