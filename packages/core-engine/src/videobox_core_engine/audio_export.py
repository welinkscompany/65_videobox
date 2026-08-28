"""완성본에서 오디오 트랙만 뽑아낸다 (owner 요청 2026-08-28: "오디오만... 내보내기").

새 렌더 파이프라인을 만들지 않는다 -- 이미 만들어진 완성본 mp4가 있으므로, 거기서
`-vn`으로 오디오만 다시 인코딩 없이(`-c:a copy`가 안 되면 aac로) 떠내는 게 정직한
범위다. `ffmpeg_final_renderer.py`의 `_run`과 같은 subprocess 관례(캡처·타임아웃)를
따른다.

**캐시한다.** 같은 완성본에서 여러 번 눌러도 매번 ffmpeg를 돌리지 않는다 -- 원본
mp4보다 새 캐시 파일이 있으면 그대로 돌려준다.
"""

from __future__ import annotations

import os
import subprocess
import uuid
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
    # 코드리뷰로 발견(2026-08-28): ffmpeg가 `destination_audio_path`에 바로 쓰면,
    # 같은 완성본을 동시에 두 번 누른 두 번째 요청이 **아직 다 안 써진 파일**을
    # "캐시가 있다"고 보고 그대로 스트리밍할 수 있었다(mtime은 파일을 열자마자
    # 갱신되므로). 매번 서로 다른 임시 파일에 쓰고, 다 쓴 뒤에만 원자적으로
    # `os.replace`한다 -- 이 교체 전까지는 캐시 검사에 아예 걸리지 않는다.
    staging_path = destination_audio_path.with_name(
        f".{destination_audio_path.stem}.{uuid.uuid4().hex}.staging{destination_audio_path.suffix}"
    )
    command = [
        ffmpeg_binary, "-y",
        "-i", str(source_video_path),
        "-vn", "-acodec", "aac", "-b:a", "192k",
        str(staging_path),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        staging_path.unlink(missing_ok=True)
        raise AudioExportError(f"'{ffmpeg_binary}' binary was not found. Install ffmpeg.") from exc
    except subprocess.TimeoutExpired as exc:
        staging_path.unlink(missing_ok=True)
        raise AudioExportError(f"ffmpeg timed out after {timeout_seconds}s.") from exc
    if result.returncode != 0 or not staging_path.is_file():
        staging_path.unlink(missing_ok=True)
        raise AudioExportError(f"ffmpeg failed to extract audio: {result.stderr[-2000:]}")
    os.replace(staging_path, destination_audio_path)
    return destination_audio_path
