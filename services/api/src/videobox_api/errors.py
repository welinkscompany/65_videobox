from __future__ import annotations

import logging

from fastapi import HTTPException, status

from videobox_core_engine.reference_style_analysis import ReferenceStyleAnalysisError
from videobox_core_engine.youtube_import import YoutubeImportError

_LOGGER = logging.getLogger(__name__)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, YoutubeImportError):
        # 링크가 잘못됐거나(유튜브가 아님) owner가 못 받는 영상이다 -- 서버 고장이
        # 아니라 owner가 고칠 수 있는 입력이다(2026-08-29 QA에서 500으로 잘못
        # 나가던 것을 잡음).
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, ReferenceStyleAnalysisError):
        # 정지 화면뿐이라 컷을 못 찾거나 ffmpeg/ffprobe를 못 찾은 경우도 같은
        # 이유로 owner가 고칠 수 있는 입력 쪽이다.
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, ValueError) and str(exc) == "source_video_has_no_speech":
        # 말이 없는 영상은 잘못된 요청이 아니라 **쓸 수 없는 재료**다. 화면이
        # "소리가 없어요"라고 말할 수 있게 422로 구분한다.
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="source_video_has_no_speech")
    if isinstance(exc, ValueError) and str(exc) == "source_voice_has_no_speech":
        # 위와 같은 이유 -- 무음 녹음도 잘못된 요청이 아니라 쓸 수 없는 재료다.
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="source_voice_has_no_speech")
    if isinstance(exc, ValueError) and str(exc) == "asset_missing":
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="asset_missing")
    if isinstance(exc, FileNotFoundError):
        # **날 예외 문구를 밖으로 내지 않는다.** 컨테이너 절대 경로가
        # `/videobox-data/projects/...`처럼 그대로 응답에 실려 나갔다(코드리뷰
        # 2026-09-07). `library_assets.py`가 이미 쓰는 관례와 같다 -- 원문은
        # 서버 로그에만, 응답은 고정 코드만.
        _LOGGER.warning("asset_file_missing: %s", exc, exc_info=True)
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"reason": "asset_file_missing", "error_code": type(exc).__name__},
        )
    if isinstance(exc, LookupError | KeyError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    # 여기 오는 것은 분류 안 된 예외다 -- ffmpeg stderr, 파일 권한 오류 등
    # 무엇이 실려 있을지 모른다. 위와 같은 이유로 원문은 로그로만 보낸다.
    _LOGGER.warning("internal_error: %s", exc, exc_info=True)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"reason": "internal_error", "error_code": type(exc).__name__},
    )
