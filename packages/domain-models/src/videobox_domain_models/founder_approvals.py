"""대표님 결재 결과의 어휘 (AK W1215-2, 2026-09-28).

VideoBox는 사람 게이트 셋(제목 선택·대본 확정·업로드)을 AK-System 결재함에
올린다. 대표님이 결재함에서 내린 결과는 AK 레지스트리 파일의 `status` 에
남는다 -- 이 모듈이 그 상태 이름을 VideoBox 쪽 뜻(승인/반려)으로 옮기는 **한
곳**이다. API(반영)와 호스트 동기화(읽기)가 둘 다 여기서 읽는다.

상태 이름의 원본은 AK 쪽 `videobox-*-approval-registry.json` 의
`allowed_statuses` 다. 동기화가 그 목록과 이 표를 대조해, 한쪽만 바뀌면
조용히 건너뛰지 않고 멈춘다(`videobox_mcp.ak_decision_sync`).
"""

from __future__ import annotations

from typing import Literal

FounderGateKind = Literal["title", "script", "upload"]
FounderOutcome = Literal["approved", "rejected"]

#: 결재함에 올라가 아직 답을 기다리는 상태. 반영 대상이 아니다.
PENDING_STATUS_BY_KIND: dict[str, str] = {
    "title": "pending_title_selection",
    "script": "pending_script_confirmation",
    "upload": "pending_upload_approval",
}

#: 결정이 난 상태 -> VideoBox 쪽 뜻.
OUTCOME_BY_KIND_AND_STATUS: dict[str, dict[str, FounderOutcome]] = {
    "title": {"title_selected": "approved", "title_rejected": "rejected"},
    "script": {"script_confirmed": "approved", "script_rejected": "rejected"},
    "upload": {"upload_approved": "approved", "upload_rejected": "rejected"},
}

#: 고른 후보가 있어야 하는 결정(제목·대본을 고른 경우). AK 레지스트리의 필드 이름도 같이 둔다.
SELECTION_FIELD_BY_KIND: dict[str, str] = {"title": "selected_title", "script": "selected_script"}


def founder_decision_id(*, kind: str, project_id: str, cycle_id: str) -> str:
    """AK `append-videobox-approval-entry.ps1` 가 만드는 결정 번호와 같은 모양."""
    return f"vb-{kind}-{project_id}-{cycle_id}"


def founder_outcome(*, kind: str, status: str) -> FounderOutcome:
    try:
        return OUTCOME_BY_KIND_AND_STATUS[kind][status]
    except KeyError as exc:
        raise ValueError(f"founder_decision_status_invalid: {kind}/{status}") from exc
