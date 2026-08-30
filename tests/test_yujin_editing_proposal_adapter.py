from __future__ import annotations

from videobox_core_engine.yujin_editing_proposal_adapter import (
    YujinEditingContext,
    interpret_yujin_editing_request,
)


def _context(*, segment_ids: tuple[str, ...] = ("scene-1",)) -> YujinEditingContext:
    return YujinEditingContext(
        session_id="session-1",
        session_revision=7,
        segment_ids=segment_ids,
    )


def _response(*, intent: str, segment_id: str, rate: int) -> dict[str, object]:
    return {
        "schema_version": "videobox.yujin-editing-response.v1",
        "reply_text": "두 번째 장면을 두 배로 빠르게 할게요.",
        "proposal": {
            "proposal_id": "proposal-1",
            "base_session_revision": 7,
            "operations": [
                {
                    "intent": intent,
                    "segment_id": segment_id,
                    "rate": rate,
                }
            ],
        },
    }


def test_speed_proposal_binds_one_current_segment_and_rate() -> None:
    result = interpret_yujin_editing_request(
        _response(intent="set_scene_speed", segment_id="scene-2", rate=2),
        _context(segment_ids=("scene-1", "scene-2")),
    )

    assert result.status == "candidate_only"
    assert result.proposal is not None
    assert result.proposal.operations[0].intent == "set_scene_speed"
    assert result.proposal.operations[0].segment_id == "scene-2"
    assert result.proposal.operations[0].rate == 2


def test_ambiguous_request_returns_clarification_without_candidate() -> None:
    result = interpret_yujin_editing_request(
        {"reply_text": "이 장면을 더 짧게 해줘"},
        _context(),
    )

    assert result.status == "clarification"
    assert result.proposal is None


def test_clarification_carries_the_models_own_reply_not_the_users_instruction() -> None:
    # Task 4 gap (2026-08-26 계획서) -- 라우터가 이 값을 대신 사용자 원문으로
    # 덮어써서, 유진이 실제로 물은 질문이 화면에 한 번도 안 보였다.
    result = interpret_yujin_editing_request(
        {
            "schema_version": "videobox.yujin-editing-response.v1",
            "reply_text": "어느 장면을 말씀하시는지 조금 더 알려 주시겠어요?",
            "proposal": None,
        },
        _context(),
    )

    assert result.status == "clarification"
    assert result.reply_text == "어느 장면을 말씀하시는지 조금 더 알려 주시겠어요?"


def test_stale_or_missing_targets_never_create_a_candidate() -> None:
    stale = _response(intent="set_scene_speed", segment_id="scene-1", rate=2)
    stale["proposal"] = {**stale["proposal"], "base_session_revision": 6}  # type: ignore[dict-item]
    missing = _response(intent="set_scene_speed", segment_id="scene-2", rate=2)

    assert interpret_yujin_editing_request(stale, _context()).reason == "stale_session_revision"
    assert interpret_yujin_editing_request(missing, _context()).reason == "segment_not_current"


def test_unapproved_media_duplicate_operations_and_unsafe_text_are_rejected() -> None:
    media = {
        "schema_version": "videobox.yujin-editing-response.v1",
        "reply_text": "음악을 바꿀게요.",
        "proposal": {
            "proposal_id": "proposal-media",
            "base_session_revision": 7,
            "operations": [
                {
                    "intent": "apply_media",
                    "segment_id": "scene-1",
                    "media_type": "bgm",
                    "asset_id": "asset-unapproved",
                }
            ],
        },
    }
    duplicate = _response(intent="set_scene_speed", segment_id="scene-1", rate=2)
    duplicate["proposal"] = {
        **duplicate["proposal"],  # type: ignore[dict-item]
        "operations": [
            {"intent": "set_scene_speed", "segment_id": "scene-1", "rate": 2},
            {"intent": "set_scene_speed", "segment_id": "scene-1", "rate": 1.5},
        ],
    }
    unsafe = _response(intent="set_scene_speed", segment_id="scene-1", rate=2)
    unsafe["reply_text"] = "Use a network request before changing the scene."

    assert interpret_yujin_editing_request(media, _context()).reason == "media_asset_not_approved"
    assert interpret_yujin_editing_request(duplicate, _context()).reason == "duplicate_conflicting_operation"
    assert interpret_yujin_editing_request(unsafe, _context()).reason == "invalid_payload_or_unsafe_instruction"


def test_unknown_operation_and_unsupported_speed_are_rejected() -> None:
    unknown = _response(intent="render_video", segment_id="scene-1", rate=2)
    unsupported_rate = _response(intent="set_scene_speed", segment_id="scene-1", rate=3)

    assert interpret_yujin_editing_request(unknown, _context()).reason == "invalid_editing_response"
    assert interpret_yujin_editing_request(unsupported_rate, _context()).reason == "invalid_editing_response"
