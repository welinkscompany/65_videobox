"""대표님 결재 결과를 받아 한 번만 반영하는 문 (AK W1215-2, 2026-09-28).

VideoBox는 제목 후보·대본 확정·업로드 요청을 AK-System 결재함에 올리기만 하고
결과를 다시 읽지 않았다. 결과는 AK 레지스트리 파일에 남으므로, 호스트에서 도는
`videobox_mcp.ak_decision_sync`가 그 파일을 **읽기만** 해서 결정이 난 항목을
이 문으로 보낸다. 이 문은 아무것도 밖으로 보내지 않는다 -- 업로드 승인이 와도
유튜브에 올리지 않는다(업로드 실행기는 아직 없고, 만들 때도 따로 승인이 필요하다).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from videobox_api.errors import _http_error
from videobox_api.models import FounderApprovalDecisionRequest


def build_founder_approvals_router(store) -> APIRouter:
    router = APIRouter()

    @router.post("/api/projects/{project_id}/founder-approval-decisions")
    def apply_decision(project_id: str, payload: FounderApprovalDecisionRequest) -> dict[str, object]:
        try:
            return store.apply_founder_approval_decision(project_id=project_id, **payload.model_dump())
        except ValueError as exc:
            if str(exc).startswith("founder_decision_conflict"):
                # 같은 결정 번호에 다른 결과 -- 입력이 틀린 게 아니라 두 기록이 부딪친 것이다.
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"reason": "founder_decision_conflict", "decision_id": payload.decision_id},
                ) from exc
            raise _http_error(exc) from exc
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.get("/api/projects/{project_id}/founder-approval-decisions")
    def list_decisions(project_id: str) -> dict[str, object]:
        try:
            return {"decisions": store.list_founder_approval_decisions(project_id=project_id)}
        except Exception as exc:
            raise _http_error(exc) from exc

    return router
