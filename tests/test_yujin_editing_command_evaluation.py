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


@dataclass
class _CapturingRuntime:
    output_data: dict[str, object]
    request: dict[str, object] | None = None

    def generate_structured(self, **kwargs: object) -> _StructuredResponse:
        self.request = kwargs
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


def test_local_command_evaluation_tells_the_model_which_assets_it_may_actually_use() -> None:
    """Task 4 (2026-08-26 계획서)로 잡힌 결함 -- `apply_media`는 `asset_id`를
    요구하는데, 프롬프트가 실제 승인된 자산 목록을 한 번도 알려주지 않았다.
    모델은 있지도 않은 ID를 지어낼 수밖에 없었고, 그 ID는 검증에서 항상
    `media_asset_not_approved`로 막혔다 -- B-roll·음악·효과음 교체 요청이
    설계상 지원 동작인데도 실제로는 한 번도 성공할 수 없었다."""
    runtime = _CapturingRuntime(_response(operation={
        "intent": "apply_media", "segment_id": "scene-2", "media_type": "bgm", "asset_id": "approved-bgm-1",
    }))

    YujinEditingProposalService(runtime=runtime).create(
        project_id="evaluation-project",
        instruction="분위기에 맞는 음악으로 바꿔줘",
        context=YujinEditingContext(
            session_id="session-1",
            session_revision=3,
            segment_ids=("scene-1", "scene-2"),
            approved_asset_ids=("approved-bgm-1", "approved-broll-1"),
            approved_asset_types=(("approved-bgm-1", "bgm"), ("approved-broll-1", "broll_video")),
        ),
    )

    assert runtime.request is not None
    prompt = str(runtime.request["prompt"])
    assert "approved-bgm-1" in prompt
    assert "approved-broll-1" in prompt


def test_local_command_evaluation_says_nothing_is_approved_when_nothing_is() -> None:
    # 승인된 자산이 하나도 없으면 목록을 지어내지 않고, 그 사실 자체를
    # 프롬프트에 명시해 모델이 apply_media를 시도하지 않게 한다.
    runtime = _CapturingRuntime(_response(operation={
        "intent": "set_scene_speed", "segment_id": "scene-2", "rate": 2,
    }))

    YujinEditingProposalService(runtime=runtime).create(
        project_id="evaluation-project",
        instruction="두 번째 장면을 두 배로 빠르게 해줘",
        context=YujinEditingContext(session_id="session-1", session_revision=3, segment_ids=("scene-1", "scene-2")),
    )

    assert runtime.request is not None
    prompt = str(runtime.request["prompt"])
    assert "승인된 자산이 없" in prompt


def test_local_command_evaluation_tells_the_runtime_the_exact_candidate_contract() -> None:
    runtime = _CapturingRuntime(_response(operation={
        "intent": "set_scene_speed", "segment_id": "scene-2", "rate": 2,
    }))

    result = YujinEditingProposalService(runtime=runtime).create(
        project_id="evaluation-project",
        instruction="두 번째 장면을 두 배로 빠르게 해줘",
        context=YujinEditingContext(
            session_id="session-1",
            session_revision=3,
            segment_ids=("scene-1", "scene-2"),
        ),
    )

    assert result.status == "candidate_only"
    assert runtime.request is not None
    prompt = str(runtime.request["prompt"])
    schema = runtime.request["response_schema"]
    assert '"schema_version": "videobox.yujin-editing-response.v1"' in prompt
    assert '"base_session_revision": 3' in prompt
    assert '"intent": "set_scene_speed"' in prompt
    assert '"segment_id": "scene-2"' in prompt
    assert isinstance(schema, dict)
    proposal_schema = schema["properties"]["proposal"]
    assert proposal_schema["properties"]["base_session_revision"]["const"] == 3
    assert proposal_schema["properties"]["operations"]["items"]["oneOf"]
