"""Deterministic contract cases for local conversational editing proposals.

These fixtures intentionally stand in for the local model response: the test
checks what reaches the product boundary (intent, target and fail-closed
status), rather than merely proving that a model method was invoked.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from videobox_core_engine.yujin_editing_proposal_adapter import YujinEditingContext
from videobox_core_engine.yujin_editing_proposal_service import YujinEditingProposalService


@dataclass(frozen=True)
class _StructuredResponse:
    output_data: dict[str, object]


@dataclass
class _FixtureRuntime:
    output_data: dict[str, object]

    def generate_structured(self, **_kwargs: object) -> _StructuredResponse:
        return _StructuredResponse(self.output_data)


def _response(*, operation: dict[str, object] | None) -> dict[str, object]:
    return {
        "schema_version": "videobox.yujin-editing-response.v1",
        "reply_text": "검토용 편집안을 만들었어요." if operation else "어느 장면을 다듬을까요?",
        "proposal": None if operation is None else {
            "proposal_id": "evaluation-proposal",
            "base_session_revision": 3,
            "operations": [operation],
        },
    }


CASES = (
    ("두 번째 장면을 두 배로 빠르게 하고 자막도 맞춰줘", {"intent": "set_scene_speed", "segment_id": "scene-2", "rate": 2}, "candidate_only", "set_scene_speed", "scene-2"),
    ("여기 말이 길어. 앞을 조금 잘라줘", {"intent": "set_segment_bounds", "segment_id": "scene-2", "start_sec": 4.5, "end_sec": 8.0}, "candidate_only", "set_segment_bounds", "scene-2"),
    ("이 분위기에 맞는 음악으로 바꿔줘", {"intent": "apply_media", "segment_id": "scene-2", "media_type": "bgm", "asset_id": "approved-bgm"}, "candidate_only", "apply_media", "scene-2"),
    ("짧게 해줘", None, "clarification", None, None),
)


@pytest.mark.parametrize(("instruction", "operation", "expected_status", "expected_intent", "expected_target"), CASES)
def test_local_command_evaluation_checks_interpreted_status_intent_and_target(
    instruction: str,
    operation: dict[str, object] | None,
    expected_status: str,
    expected_intent: str | None,
    expected_target: str | None,
) -> None:
    service = YujinEditingProposalService(runtime=_FixtureRuntime(_response(operation=operation)))
    result = service.create(
        project_id="evaluation-project",
        instruction=instruction,
        context=YujinEditingContext(
            session_id="session-1",
            session_revision=3,
            segment_ids=("scene-1", "scene-2"),
            approved_asset_ids=("approved-bgm",),
            approved_asset_types=(("approved-bgm", "bgm"),),
        ),
    )

    assert result.status == expected_status
    if expected_intent is None:
        assert result.proposal is None
        return
    assert result.proposal is not None
    operation_result = result.proposal.operations[0]
    assert operation_result.intent == expected_intent
    assert operation_result.segment_id == expected_target


def test_local_command_evaluation_rejects_an_unapproved_media_candidate() -> None:
    service = YujinEditingProposalService(runtime=_FixtureRuntime(_response(operation={
        "intent": "apply_media", "segment_id": "scene-2", "media_type": "bgm", "asset_id": "unapproved-bgm",
    })))

    result = service.create(
        project_id="evaluation-project",
        instruction="음악으로 바꿔줘",
        context=YujinEditingContext(session_id="session-1", session_revision=3, segment_ids=("scene-1", "scene-2")),
    )

    assert (result.status, result.reason, result.proposal) == ("rejected", "media_asset_not_approved", None)
