from __future__ import annotations

from fastapi import HTTPException, status

from videobox_core_engine.reference_style_analysis import ReferenceStyleAnalysisError
from videobox_core_engine.youtube_import import YoutubeImportError


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
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, LookupError | KeyError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
