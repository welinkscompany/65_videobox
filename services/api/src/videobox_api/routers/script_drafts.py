"""대본도 찍어 둔 영상도 없는 사람이 첫 걸음을 떼는 문.

**한 번에 끝나는 요청이다.** 구조화 출력으로 물으면 2.3초에 돌아온다(2026-08-21 실측).
job으로 쪼개면 화면이 폴링을 한 겹 더 들고 다녀야 하고, 그만큼 얻는 것이 없다.

**아무것도 저장하지 않는다.** 초안은 제안이지 확정이 아니다. owner가 화면에서 고치고
확인해야 기획(`/creation-briefs`)으로 넘어간다 -- 사람 게이트 `대본 확정`이 그 자리다
(`decisions/2026-08-16-autonomous-creator-loop-scope-expansion.ko.md`).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from videobox_api.models import (
    ScriptDraftCreateRequest,
    ScriptDraftResponse,
    ScriptDraftSceneResponse,
)
from videobox_core_engine.script_draft_writer import ScriptDraftUnavailable


#: 이유마다 owner가 할 다음 행동이 다르다. 한 낱말로 뭉개면 화면이 "잠시 뒤 다시"와
#: "주제를 바꿔 적어 보세요"를 구분할 수 없다.
_STATUS_BY_DETAIL = {
    # 닿지 못했다. 다시 걸면 된다.
    "script_draft_writer_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
    # 제 시간에 못 끝냈다. 같은 길이로 다시 누르면 같은 결과다 -- 짧게 부탁해야 한다.
    "script_draft_took_too_long": status.HTTP_504_GATEWAY_TIMEOUT,
    # 답은 왔는데 owner가 쓸 수 있는 대본이 아니다.
    "script_draft_empty": status.HTTP_502_BAD_GATEWAY,
    "script_draft_not_korean": status.HTTP_502_BAD_GATEWAY,
    # 우리가 먼저 막은 것.
    "script_draft_topic_empty": status.HTTP_422_UNPROCESSABLE_ENTITY,
}


def build_script_drafts_router() -> APIRouter:
    router = APIRouter()

    @router.post("/api/projects/{project_id}/script-drafts", status_code=status.HTTP_201_CREATED)
    def create_script_draft(
        project_id: str, payload: ScriptDraftCreateRequest, request: Request
    ) -> ScriptDraftResponse:
        writer = getattr(request.app.state, "script_draft_writer", None)
        if writer is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="script_draft_writer_unavailable",
            )
        try:
            draft = writer.write(
                project_id=project_id,
                topic=payload.topic,
                duration_sec=payload.duration_sec,
                scene_count=payload.scene_count,
            )
        except ScriptDraftUnavailable as exc:
            raise HTTPException(
                status_code=_STATUS_BY_DETAIL.get(str(exc), status.HTTP_502_BAD_GATEWAY),
                detail=str(exc),
            ) from exc
        except Exception as exc:  # noqa: BLE001 - 로컬 런타임 경계
            # 여기서 500을 내보내면 화면은 이유 없는 한 문장만 띄운다.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="script_draft_writer_unavailable",
            ) from exc

        return ScriptDraftResponse(
            title=draft.title,
            script_text=draft.script_text,
            scenes=[
                ScriptDraftSceneResponse(
                    scene_number=scene.scene_number,
                    narration=scene.narration,
                    visual=scene.visual,
                )
                for scene in draft.scenes
            ],
        )

    return router


__all__ = ["build_script_drafts_router"]
