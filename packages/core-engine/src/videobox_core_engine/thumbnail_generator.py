from __future__ import annotations

import subprocess
from pathlib import Path


class ThumbnailGenerationError(RuntimeError):
    pass


def render_thumbnail_bytes(*, source: Path, media_type: str, kind: str) -> bytes | None:
    """한 소스 파일을 png 썸네일(또는 파형)로 그린다. `stdout`으로 받아 파일
    쓰기는 호출자에게 맡긴다 -- 저장 경로·캐시 규칙이 자산 체계마다 다르다
    (자료실은 content-hash 파생물, 프로젝트 자산은 `asset_id` 기준 캐시).

    본디 `routers/library_assets.py`의 `_render_derivative`였다. 이미지
    렌더는 이미 검증돼 있었는데(자료실 썸네일), 프로젝트 안의 이미지 자산은
    이 로직이 없어서 썸네일을 아예 안 만들었다(2026-09-17 화면 점검 실측 --
    `assets.py`의 `get_asset_thumbnail`이 파일 없으면 그냥 404였다). 같은
    렌더를 두 번 짜는 대신 여기로 옮겨 둘 다 쓴다.
    """
    if media_type == "image":
        # 파형 필터(`showwavespic`)를 그림에 태우면 ffmpeg가 실패한다.
        command = [
            "ffmpeg", "-y", "-v", "error", "-i", str(source),
            "-frames:v", "1", "-vf", "scale=640:360:force_original_aspect_ratio=decrease",
            "-f", "image2pipe", "-vcodec", "png", "pipe:1",
        ]
    elif media_type == "broll":
        command = [
            "ffmpeg", "-y", "-v", "error", "-ss", "0", "-i", str(source),
            "-frames:v", "1", "-vf", "scale=640:360:force_original_aspect_ratio=decrease",
            "-f", "image2pipe", "-vcodec", "png", "pipe:1",
        ]
    else:
        height = "220" if kind == "waveform" else "360"
        command = [
            "ffmpeg", "-y", "-v", "error", "-i", str(source),
            "-filter_complex", f"aformat=channel_layouts=mono,showwavespic=s=640x{height}:colors=orangered",
            "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1",
        ]
    result = subprocess.run(command, capture_output=True, timeout=30, check=False)
    if result.returncode != 0 or not result.stdout:
        return None
    return bytes(result.stdout)


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
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise ThumbnailGenerationError(f"'{ffmpeg_binary}' binary was not found.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ThumbnailGenerationError(f"'{ffmpeg_binary}' timed out after {timeout_seconds}s.") from exc
    if result.returncode != 0 or not output_path.exists():
        raise ThumbnailGenerationError(f"ffmpeg failed to generate thumbnail: {result.stderr}")


__all__ = ["ThumbnailGenerationError", "generate_video_thumbnail", "render_thumbnail_bytes"]
