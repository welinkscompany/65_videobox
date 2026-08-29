"""본인 유튜브 영상을 내려받아 목소리 샘플·참고 영상으로 쓴다.

owner 요청(2026-08-29): "내 유튜브 영상 있는걸로 학습은 안돼?" -- 본인이 이미
올린 본인 영상만 대상이다. 남의 영상을 받아 오는 길이 아니다 -- 이 함수를
부르는 자리(라우터)에서 유튜브 주소인지만 확인하고, 그 영상이 owner
소유인지는 확인할 방법이 없으므로 화면 문구로 그 전제를 분명히 한다
(`VoiceTtsSettings.tsx`).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_YOUTUBE_HOST_PATTERN = re.compile(
    r"^(https?://)?(www\.|m\.)?(youtube\.com/watch\?v=|youtube\.com/shorts/|youtu\.be/)",
    re.IGNORECASE,
)


class YoutubeImportError(RuntimeError):
    pass


def is_youtube_url(url: str) -> bool:
    return bool(_YOUTUBE_HOST_PATTERN.match(url.strip()))


def download_youtube_video(
    url: str,
    destination_dir: Path,
    *,
    timeout_seconds: float = 600.0,
    max_bytes: int = 512 * 1024 * 1024,
) -> Path:
    """유튜브 영상을 mp4 하나로 내려받는다.

    소리(목소리 샘플)와 그림(컷 빠르기·색감 분석)을 전부 이 파일 하나에서
    뽑는다 -- 두 번 받지 않는다.
    """

    if not is_youtube_url(url):
        raise YoutubeImportError("youtube_import_url_invalid")
    try:
        import yt_dlp
    except ImportError as exc:
        raise YoutubeImportError("youtube_import_unavailable") from exc

    destination_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(destination_dir / "youtube-import-%(id)s.%(ext)s")
    options: dict[str, Any] = {
        # 실제 유튜브로 직접 받아 보고서야 잡은 것들(2026-08-29, 코드리뷰가
        # 아니라 진짜 실행이 잡았다):
        # 1. `bestvideo+bestaudio` 조합은 이 환경에서 "Requested format is not
        #    available"로 죽었다 -- JS 실행기(deno/node)가 없어서 유튜브가
        #    분리된 영상·음성 스트림을 안 내준다(경고: "No supported
        #    JavaScript runtime could be found"). 병합 없이 한 파일로 오는
        #    구형 포맷 `18`(video+audio가 이미 한 mp4에 들어 있음)을 우선한다.
        # 2. `player_client: android`를 안 주면 그 `18`조차 못 받는다 --
        #    데스크톱 클라이언트 응답은 URL 없는 스텁만 내려온다("SABR-only
        #    streaming"). 안드로이드 클라이언트로 물으면 실제 URL이 온다.
        "format": "18/best[ext=mp4]/best",
        "outtmpl": output_template,
        "socket_timeout": timeout_seconds,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": max_bytes,
        "extractor_args": {"youtube": {"player_client": ["android"]}},
    }
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
            downloaded_path = Path(downloader.prepare_filename(info))
    except Exception as exc:  # noqa: BLE001 -- yt-dlp raises its own broad DownloadError
        raise YoutubeImportError(f"youtube_import_failed: {exc}") from exc
    # 병합 뒤 확장자가 바뀔 수 있다(원본이 webm이면 mp4로 다시 묶는다) --
    # 실제로 만들어진 파일을 찾는다.
    if downloaded_path.is_file():
        return downloaded_path
    candidates = sorted(destination_dir.glob(f"youtube-import-{info.get('id', '*')}.*"))
    if not candidates:
        raise YoutubeImportError("youtube_import_output_missing")
    return candidates[0]


__all__ = ["YoutubeImportError", "is_youtube_url", "download_youtube_video"]
