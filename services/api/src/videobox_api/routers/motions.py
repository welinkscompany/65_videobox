"""설명 모션 한 편을 만드는 문. 자료실 `영상`으로 들어간다.

## 왜 프로젝트가 아니라 자료실인가

막대 비교나 단계 목록 같은 모션은 한 영상에만 쓰이지 않는다. 제품 방향이
**"내 자산을 다시 쓰기 쉽게"**이므로(`decisions/2026-09-04-capcut-shell-with-my-assets.ko.md`)
자료실이 맞는 자리다.

## 한 요청에 끝난다 — 시계는 다리가 본다

한 편은 십수 초이고, 다리의 렌더 상한은 180초, 이 쪽이 다리를 기다리는 시간은 240초다.
nginx는 600초에서 끊으므로 화면은 늘 우리가 쓴 한국어 답을 받는다. 세 값이 어긋나지
않게 `tests/test_compose_contract.py`가 지킨다.

## 자료실 등록이 실패해도 201이다

모션은 만들어졌기 때문이다. 왜 못 넣었는지는 `library_error`로 같이 낸다.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status

from videobox_api.errors import _http_error
from videobox_api.models import (
    MotionCreateRequest,
    MotionResponse,
    MotionTemplateListResponse,
    MotionTemplateResponse,
)
from videobox_core_engine.motion_service import MotionUnavailable
from videobox_core_engine.motion_templates import (
    MAX_MOTION_DURATION_SEC,
    MIN_MOTION_DURATION_SEC,
    MOTION_TEMPLATES,
)

_LOGGER = logging.getLogger(__name__)

#: 한 낱말로 뭉개면 화면이 "켜야 한다"와 "잠시 뒤 다시"와 "글을 고쳐라"를 구분할 수 없다.
_STATUS_BY_REASON = {
    "motion_template_unknown": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "motion_variables_invalid": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "motion_bridge_not_configured": status.HTTP_503_SERVICE_UNAVAILABLE,
    "motion_bridge_not_running": status.HTTP_503_SERVICE_UNAVAILABLE,
    "motion_engine_not_prepared": status.HTTP_503_SERVICE_UNAVAILABLE,
    "motion_busy": status.HTTP_409_CONFLICT,
    "motion_took_too_long": status.HTTP_504_GATEWAY_TIMEOUT,
    "motion_render_failed": status.HTTP_502_BAD_GATEWAY,
}


def build_motions_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/library/motion-templates")
    def list_motion_templates() -> MotionTemplateListResponse:
        """고를 수 있는 모션. 화면이 이름·글자 수 한도를 손으로 베껴 적으면 둘이 어긋난다."""

        return MotionTemplateListResponse(
            templates=[
                MotionTemplateResponse(
                    key=t.key,
                    korean_name=t.korean_name,
                    description=t.description,
                    default_duration_sec=t.default_duration_sec,
                    min_duration_sec=MIN_MOTION_DURATION_SEC,
                    max_duration_sec=MAX_MOTION_DURATION_SEC,
                    limits=dict(t.limits),
                )
                for t in MOTION_TEMPLATES
            ]
        )

    @router.post("/api/library/motions", status_code=status.HTTP_201_CREATED)
    def create_motion(payload: MotionCreateRequest, request: Request) -> MotionResponse:
        service = getattr(request.app.state, "motion_service", None)
        if service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="motion_generation_unavailable",
            )
        try:
            made = service.make(
                template_key=payload.template,
                variables=payload.variables,
                duration_sec=payload.duration_sec,
                layout=payload.layout,
                title=payload.title,
            )
        except MotionUnavailable as exc:
            # 왜 못 만들었는지 남긴다 -- 화면 문구는 reason만 받으므로 로그가 유일한 상세다.
            _LOGGER.warning("모션을 만들지 못했습니다 (%s): %s", exc.reason, exc.detail)
            raise HTTPException(
                status_code=_STATUS_BY_REASON.get(exc.reason, status.HTTP_502_BAD_GATEWAY),
                detail=(
                    {"reason": exc.reason, "problems": list(exc.problems)}
                    if exc.problems
                    else exc.reason
                ),
            ) from exc
        except Exception as exc:
            raise _http_error(exc) from exc
        return MotionResponse(
            library_asset_id=made.library_asset_id,
            template=made.template_key,
            title=made.title,
            duration_sec=made.duration_sec,
            layout=made.layout,
            format=made.format,
            byte_size=len(made.video_bytes),
            elapsed_sec=made.elapsed_sec,
            library_error=made.library_error,
        )

    return router
