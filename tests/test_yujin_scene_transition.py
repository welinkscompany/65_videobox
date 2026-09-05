"""유진이 장면 전환을 못 넣었다 — 실측 2026-09-06.

owner: "더 다양한 사례로 유진이가 명령하면 영상 편집 작동 하는지 테스트 해봐."

> "장면 전환 부드럽게 넣어줘"
> → "현재 허용된 intent 목록에는 '...'이 없습니다"

**부품은 다 있었고 유진 경로에만 없었다** -- 이 저장소가 반복해서 겪은 패턴이다.
엔진에 `update_segment_transition`이 있고 화면은 `setSceneTransition`으로 그것을
부른다. 유진의 허용 항목 열둘에 전환만 빠져 있었다.

**전환은 그 장면으로 넘어올 때 걸린다**(`update_segment_transition` 머리말).
그래서 뒤쪽 장면에 싣는다 -- 앞 장면에 실으면 장면을 지우거나 순서를 바꿀 때
어느 경계 것이었는지 알 수 없어진다.

**지어낸 이름은 검증기가 막는다.** 색감과 같은 이유다: 표에 없는 이름은 렌더러가
조용히 넘기고, 창작자는 "골랐는데 아무 일도 안 일어났다"를 본다.
"""

from __future__ import annotations

from videobox_core_engine.editing_session import _apply_yujin_editing_operations, build_editing_session
from videobox_core_engine.transitions import TRANSITION_CATALOG
from videobox_core_engine.yujin_editing_proposal_service import (
    YujinEditingContext,
    interpret_yujin_editing_request,
)


def _context() -> YujinEditingContext:
    return YujinEditingContext(
        session_id="session-1",
        session_revision=3,
        segment_ids=("seg-1", "seg-2"),
        segment_ids_with_broll=("seg-1", "seg-2"),
    )


def _response(*, transition_type: str | None, segment_id: str = "seg-2") -> dict[str, object]:
    operation: dict[str, object] = {
        "intent": "set_scene_transition",
        "segment_id": segment_id,
        "transition_type": transition_type,
    }
    return {
        "schema_version": "videobox.yujin-editing-response.v1",
        "reply_text": "장면이 넘어올 때 부드럽게 겹치도록 만들었어요.",
        "proposal": {
            "proposal_id": "candidate",
            "base_session_revision": 3,
            "operations": [operation],
        },
    }


def test_yujin_can_choose_a_transition_from_the_catalogue() -> None:
    accepted = interpret_yujin_editing_request(_response(transition_type="fade"), _context())

    assert accepted.status == "candidate_only"
    assert accepted.proposal is not None
    assert accepted.proposal.operations[0].transition_type == "fade"


def test_a_transition_nobody_can_render_is_refused() -> None:
    """표에 없는 이름은 렌더러가 조용히 넘긴다. 여기서 막는다."""
    refused = interpret_yujin_editing_request(_response(transition_type="star-wipe-nope"), _context())

    assert refused.reason == "scene_transition_not_available"


def test_applying_the_transition_lands_on_the_scene_being_entered() -> None:
    session = build_editing_session(
        project_id="project-1",
        timeline={"timeline_id": "timeline-1", "tracks": []},
        segments=[
            {"segment_id": "seg-1", "start_sec": 0.0, "end_sec": 5.0, "text": "첫 장면"},
            {"segment_id": "seg-2", "start_sec": 5.0, "end_sec": 9.0, "text": "둘째 장면"},
        ],
    )
    proposal = interpret_yujin_editing_request(_response(transition_type="fade"), _context()).proposal
    assert proposal is not None

    applied = _apply_yujin_editing_operations(session=session, operations=tuple(proposal.operations))

    segments = {str(item["segment_id"]): item for item in applied["segments"]}
    # **넘어오는 쪽**에 실린다.
    assert segments["seg-2"]["transition_in"]["type"] == "fade"
    assert "transition_in" not in segments["seg-1"]
    # 유진이 골랐다는 것이 남는다 -- owner가 고른 것과 구분할 수 있어야 한다.
    assert segments["seg-2"]["transition_in"].get("chosen_by") == "yujin"


def test_a_null_transition_takes_it_off() -> None:
    session = build_editing_session(
        project_id="project-1",
        timeline={"timeline_id": "timeline-1", "tracks": []},
        segments=[
            {"segment_id": "seg-1", "start_sec": 0.0, "end_sec": 5.0, "text": "첫 장면"},
            {"segment_id": "seg-2", "start_sec": 5.0, "end_sec": 9.0, "text": "둘째 장면"},
        ],
    )
    with_fade = _apply_yujin_editing_operations(
        session=session,
        operations=tuple(interpret_yujin_editing_request(_response(transition_type="fade"), _context()).proposal.operations),
    )
    proposal = interpret_yujin_editing_request(_response(transition_type=None), _context()).proposal
    assert proposal is not None

    removed = _apply_yujin_editing_operations(session=with_fade, operations=tuple(proposal.operations))

    segments = {str(item["segment_id"]): item for item in removed["segments"]}
    assert "transition_in" not in segments["seg-2"]


def test_the_prompt_lists_the_transitions_it_may_choose() -> None:
    """이름을 지어내지 못하게 표를 그대로 준다 -- 색감에서 세운 규칙이다."""
    from videobox_core_engine.yujin_editing_proposal_service import _scene_transition_catalogue

    listed = _scene_transition_catalogue()

    for key in TRANSITION_CATALOG:
        assert key in listed
    assert "넘어올 때" in listed
