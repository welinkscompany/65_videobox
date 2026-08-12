from __future__ import annotations

import json
import math

import pytest

from videobox_core_engine.yujin_footage_proposal_adapter import (
    interpret_yujin_footage_request,
)
from videobox_domain_models.yujin_footage_proposals import (
    YujinFootageContext,
)


SOURCE_SHA256 = "a" * 64


def _context(*, is_vertical: bool = True, quality_flags: tuple[str, ...] = ()) -> YujinFootageContext:
    return YujinFootageContext.model_validate(
        {
            "schema_version": "videobox.yujin-footage-context.v1",
            "source_id": "source:take-001",
            "source_sha256": SOURCE_SHA256,
            "proposal_id": "fprop_001",
            "proposal_revision": 7,
            "duration_sec": 30.0,
            "is_vertical": is_vertical,
            "segments": (
                {
                    "segment_id": "pseg-1",
                    "source_segment_id": "fseg-1",
                    "start_sec": 0.0,
                    "end_sec": 10.0,
                    "quality_flags": quality_flags,
                },
                {
                    "segment_id": "pseg-2",
                    "source_segment_id": "fseg-2",
                    "start_sec": 10.0,
                    "end_sec": 20.0,
                    "quality_flags": (),
                },
                {
                    "segment_id": "pseg-3",
                    "source_segment_id": "fseg-3",
                    "start_sec": 20.0,
                    "end_sec": 30.0,
                    "quality_flags": (),
                },
            ),
        }
    )


def _response(
    *,
    intent: str,
    source_id: str = "source:take-001",
    proposal_id: str = "fprop_001",
    revision: int = 7,
    reply_text: str = "촬영본 제안입니다.",
    **operation: object,
) -> str:
    payload = {
        "schema_version": "videobox.yujin-footage-response.v1",
        "reply_text": reply_text,
        "proposal": {
            "source_id": source_id,
            "proposal_id": proposal_id,
            "base_revision": revision,
            "operations": [{"intent": intent, **operation}],
        },
    }
    return json.dumps(payload, ensure_ascii=False)


@pytest.mark.parametrize(
    ("intent", "operation"),
    (
        ("split_by_scene", {"segment_ids": ["pseg-1", "pseg-2"]}),
        ("select_process", {"segment_ids": ["pseg-1"], "process_label": "출근"}),
        ("exclude_quality", {"segment_ids": ["pseg-1"], "quality_evidence": ["blur"]}),
        ("combine_similar", {"segment_ids": ["pseg-1", "pseg-2"]}),
        ("select_vertical", {"segment_ids": ["pseg-1"]}),
        ("target_duration", {"target_duration_sec": 18.0}),
    ),
)
def test_allowed_intents_return_candidate_only_bound_to_current_proposal(
    intent: str,
    operation: dict[str, object],
) -> None:
    context = _context(quality_flags=("blur",))

    result = interpret_yujin_footage_request(
        _response(intent=intent, **operation),
        context,
    )

    assert result.status == "candidate_only"
    assert result.proposal is not None
    assert result.proposal.source_id == context.source_id
    assert result.proposal.source_sha256 == context.source_sha256
    assert result.proposal.proposal_id == context.proposal_id
    assert result.proposal.base_revision == context.proposal_revision
    assert result.proposal.requires_approval is True
    assert result.proposal.operations[0].intent == intent


def test_ambiguous_response_returns_clarification_without_a_proposal() -> None:
    context = _context()

    result = interpret_yujin_footage_request(
        {"reply_text": "좋은 장면으로 정리해줘"},
        context,
    )

    assert result.status == "clarification"
    assert result.proposal is None
    assert result.clarification


def test_clarification_reply_respects_the_response_codepoint_limit() -> None:
    result = interpret_yujin_footage_request(
        {"reply_text": "a" * 8_193},
        _context(),
    )

    assert result.status == "rejected"
    assert result.rejection_reason == "invalid_response"


def test_mapping_payload_keys_count_toward_the_input_size_bound() -> None:
    result = interpret_yujin_footage_request(
        {"k" * 70_000: "value"},
        _context(),
    )

    assert result.status == "rejected"
    assert result.rejection_reason == "invalid_payload"


def test_mapping_payload_has_a_global_node_budget() -> None:
    def tree(depth: int) -> dict[str, object]:
        if depth == 0:
            return {}
        return {"left": tree(depth - 1), "right": tree(depth - 1)}

    result = interpret_yujin_footage_request(tree(9), _context())

    assert result.status == "rejected"
    assert result.rejection_reason == "invalid_payload"


@pytest.mark.parametrize(
    "payload",
    (
        _response(intent="select_process", source_id="source:other", segment_ids=["pseg-1" ]),
        _response(intent="select_process", segment_ids=["pseg-missing"]),
        _response(intent="select_process", segment_ids=["pseg-1"], ranges=[{"start_sec": 9.0, "end_sec": 11.0}]),
    ),
)
def test_unknown_source_segment_or_out_of_segment_range_is_rejected(payload: str) -> None:
    result = interpret_yujin_footage_request(payload, _context())

    assert result.status == "rejected"
    assert result.proposal is None
    assert result.rejection_reason


def test_non_finite_target_duration_is_rejected() -> None:
    result = interpret_yujin_footage_request(
        {
            "schema_version": "videobox.yujin-footage-response.v1",
            "reply_text": "길이를 맞춰볼게요.",
            "proposal": {
                "source_id": "source:take-001",
                "proposal_id": "fprop_001",
                "base_revision": 7,
                "operations": [
                    {"intent": "target_duration", "target_duration_sec": math.inf}
                ],
            },
        },
        _context(),
    )

    assert result.status == "rejected"
    assert result.proposal is None


def test_target_duration_beyond_source_is_rejected() -> None:
    result = interpret_yujin_footage_request(
        _response(intent="target_duration", target_duration_sec=31.0),
        _context(),
    )

    assert result.status == "rejected"
    assert result.rejection_reason == "target_duration_out_of_range"


def test_unknown_intent_and_extra_fields_are_rejected() -> None:
    result = interpret_yujin_footage_request(
        _response(intent="delete_source", segment_ids=["pseg-1"]),
        _context(),
    )

    assert result.status == "rejected"
    assert result.rejection_reason == "invalid_response"


def test_extra_operation_fields_are_rejected_by_the_strict_response_model() -> None:
    result = interpret_yujin_footage_request(
        _response(intent="select_process", segment_ids=["pseg-1"], extra_field="nope"),
        _context(),
    )

    assert result.status == "rejected"
    assert result.rejection_reason == "invalid_response"


def test_vertical_request_is_rejected_for_non_vertical_source() -> None:
    result = interpret_yujin_footage_request(
        _response(intent="select_vertical", segment_ids=["pseg-1"]),
        _context(is_vertical=False),
    )

    assert result.status == "rejected"
    assert result.rejection_reason == "source_not_vertical"


def test_non_adjacent_combine_is_rejected() -> None:
    result = interpret_yujin_footage_request(
        _response(intent="combine_similar", segment_ids=["pseg-1", "pseg-3"]),
        _context(),
    )

    assert result.status == "rejected"
    assert result.rejection_reason == "segments_not_adjacent"


def test_quality_exclusion_requires_evidence_matching_context() -> None:
    missing = interpret_yujin_footage_request(
        _response(intent="exclude_quality", segment_ids=["pseg-1"]),
        _context(quality_flags=("blur",)),
    )
    mismatched = interpret_yujin_footage_request(
        _response(
            intent="exclude_quality",
            segment_ids=["pseg-1"],
            quality_evidence=["audio_drop"],
        ),
        _context(quality_flags=("blur",)),
    )

    assert missing.status == "rejected"
    assert mismatched.status == "rejected"
    assert missing.rejection_reason == "quality_evidence_required"
    assert mismatched.rejection_reason == "quality_evidence_unverified"


@pytest.mark.parametrize(
    "text",
    (
        "파일 시스템 경로 C:\\video\\take.mp4를 읽어줘",
        "renderer를 실행해서 바로 적용해줘",
        "database에 저장하고 HTTP로 호출해줘",
        "credential token을 사용해줘",
    ),
)
def test_operational_instructions_are_rejected_fail_closed(text: str) -> None:
    result = interpret_yujin_footage_request(
        {"reply_text": text},
        _context(),
    )

    assert result.status == "rejected"
    assert result.proposal is None
    assert result.rejection_reason == "unsafe_instruction"


@pytest.mark.parametrize(
    "text",
    (
        "파일 경로를 읽어줘",
        "비밀번호를 사용해줘",
        "웹 요청을 보내줘",
        "명령줄을 실행해줘",
        "execute a command now",
        "..\\video.mp4를 읽어줘",
        "/video.mp4를 읽어줘",
        "rend\u200berer를 실행해줘",
    ),
)
def test_unsafe_variants_are_rejected_even_with_a_valid_proposal(text: str) -> None:
    result = interpret_yujin_footage_request(
        _response(
            intent="select_process",
            segment_ids=["pseg-1"],
            process_label="출근",
            reply_text=text,
        ),
        _context(),
    )

    assert result.status == "rejected"
    assert result.rejection_reason == "unsafe_instruction"


def test_deep_malformed_json_is_rejected_without_recursion_error() -> None:
    payload = '{"a":' * 5_000 + "null" + "}" * 5_000

    result = interpret_yujin_footage_request(payload, _context())

    assert result.status == "rejected"
    assert result.rejection_reason == "invalid_payload"


@pytest.mark.parametrize(
    "text",
    ("렌더러를 실행해줘", "데이터베이스에 저장해줘", "자격증명을 사용해줘"),
)
def test_korean_operational_instructions_are_rejected_fail_closed(text: str) -> None:
    result = interpret_yujin_footage_request({"reply_text": text}, _context())

    assert result.status == "rejected"
    assert result.rejection_reason == "unsafe_instruction"
