"""인포그래픽 한 장을 만드는 문. 자료실 `그림`으로 들어간다.

## 왜 프로젝트가 아니라 자료실인가

그림 한 장은 한 영상에만 쓰이지 않는다. "스마트스토어 수수료 구조"는 대표님이
여러 영상에서 되풀이해 쓸 것이다. 제품 방향이 **"내 자산을 다시 쓰기 쉽게"**이므로
(`decisions/2026-09-04-capcut-shell-with-my-assets.ko.md`) 자료실이 맞는 자리다.

## 한 번에 끝나는 요청이다 — 다만 시계를 본다

`scene_images`와 같은 판단이다. 다만 여기는 훨씬 길다 -- 한 판이 63~115초다
(2026-09-07 실측). nginx는 330초에서 끊고, 거기서 잘리면 화면은 우리가 쓴 한국어
대신 프록시의 504 HTML을 받는다. 그래서 `InfographicService`가 시계를 보고
**한 판 더 돌 시간이 없으면 안 돈다**(`TOTAL_BUDGET_SECONDS`). 두 값이 어긋나지
않게 `tests/test_compose_contract.py`가 지킨다.

## 자료실 등록이 실패해도 200이다

그림은 만들어졌기 때문이다. 왜 못 넣었는지는 `library_error`로 같이 낸다 --
`SceneVideoService`가 이미 쓰는 관례다.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status

from videobox_api.errors import _http_error
from videobox_api.models import (
    InfographicCreateRequest,
    InfographicResponse,
    InfographicStyleListResponse,
    InfographicStyleResponse,
)
from videobox_core_engine.infographic_brief import INFOGRAPHIC_STYLES, InfographicFact
from videobox_core_engine.infographic_service import InfographicUnavailable

#: 자료실은 프로젝트에 매이지 않는다. 런타임은 기록용으로 이름 하나를 받으므로
#: 고정 이름을 준다 -- 없는 프로젝트 id를 지어내면 기록이 거짓말이 된다.
LIBRARY_SCOPE = "library"

_LOGGER = logging.getLogger(__name__)

#: 한 낱말로 뭉개면 화면이 "켜야 한다"와 "다시 눌러 보라"를 구분할 수 없다.
#: `scene_images`가 같은 이유로 같은 표를 들고 있다.
_STATUS_BY_REASON = {
    "infographic_topic_empty": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "infographic_bridge_not_configured": status.HTTP_503_SERVICE_UNAVAILABLE,
    "infographic_bridge_not_running": status.HTTP_503_SERVICE_UNAVAILABLE,
    "infographic_took_too_long": status.HTTP_504_GATEWAY_TIMEOUT,
    "infographic_writer_unavailable": status.HTTP_502_BAD_GATEWAY,
    "infographic_render_failed": status.HTTP_502_BAD_GATEWAY,
    "infographic_did_not_pass_checks": status.HTTP_422_UNPROCESSABLE_ENTITY,
}


def build_infographics_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/library/infographic-styles")
    def list_infographic_styles() -> InfographicStyleListResponse:
        """고를 수 있는 결. 화면이 이름을 손으로 베껴 적으면 둘이 어긋난다."""

        return InfographicStyleListResponse(
            styles=[
                InfographicStyleResponse(
                    key=style.key,
                    korean_name=style.korean_name,
                    direction=style.direction,
                )
                for style in INFOGRAPHIC_STYLES
            ]
        )

    @router.post("/api/library/infographics", status_code=status.HTTP_201_CREATED)
    def create_infographic(
        payload: InfographicCreateRequest, request: Request
    ) -> InfographicResponse:
        service = getattr(request.app.state, "infographic_service", None)
        if service is None:
            # 꺼진 것과 고장 난 것은 다르다(`scene_images`와 같은 이유).
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="infographic_generation_unavailable",
            )
        try:
            made = service.generate(
                project_id=LIBRARY_SCOPE,
                topic=payload.topic,
                facts=[
                    InfographicFact(
                        label=fact.label, value=fact.value, unit=fact.unit, note=fact.note
                    )
                    for fact in payload.facts
                ],
                style=payload.style,
                title=payload.title,
            )
        except InfographicUnavailable as exc:
            # **왜 버렸는지 남긴다.** 2026-09-07에 컨테이너에서 두 판 다 버려졌는데
            # 로그에 이유가 없어서, 모델이 `316,000원`을 지어냈다는 것을 알아내려고
            # 같은 요청을 손으로 다시 돌려야 했다. 관대한 except가 결함을 덮는
            # 그 자리와 같은 모양이다.
            _LOGGER.warning("인포그래픽을 만들지 못했습니다 (%s): %s", exc.reason, exc.detail)
            raise HTTPException(
                status_code=_STATUS_BY_REASON.get(exc.reason, status.HTTP_502_BAD_GATEWAY),
                # 검사에 걸린 것은 **무엇이 걸렸는지** 같이 낸다 -- 창작자가
                # "다시 해 보세요"만 듣고 같은 주제로 또 누르는 것을 막는다.
                detail=(
                    {"reason": exc.reason, "problems": exc.detail}
                    if exc.reason == "infographic_did_not_pass_checks" and exc.detail
                    else exc.reason
                ),
            ) from exc
        except Exception as exc:
            raise _http_error(exc) from exc
        return InfographicResponse(
            library_asset_id=made.library_asset_id,
            title=made.title,
            style=made.style_key,
            attempts=made.attempts,
            corrected=list(made.corrected),
            remaining_problems=list(made.remaining_problems),
            library_error=made.library_error,
        )

    return router
