from __future__ import annotations

import pytest

from videobox_core_engine.agent_quality_harness import (
    CandidateResult,
    FrozenEvaluationCase,
    evaluate_candidate,
)


def test_evaluate_candidate_accepts_schema_valid_grounded_shadow_result() -> None:
    case = FrozenEvaluationCase(
        case_id="title-001",
        task="title_generation",
        sanitized_input={"scene_summary": "아이 물놀이와 놀이터", "audio_policy": "preserve_original"},
        response_schema={
            "required": ["titles"],
            "properties": {"titles": {}, "audio_policy": {}},
            "additionalProperties": False,
        },
        required_claims=frozenset({"preserve_original"}),
        corpus_id="videobox-korean-v1",
        prompt_schema_version="v1",
        renderer_version="ffmpeg-fixture-v1",
    )

    result = evaluate_candidate(
        case=case,
        candidate=CandidateResult(
            provider="local_qwen",
            runtime="lm_studio",
            model="qwen3.6-35b-a3b",
            output={"titles": ["원본 소리를 살린 물놀이 하루"], "audio_policy": "preserve_original"},
            latency_ms=120,
            token_count=97,
        ),
    )

    assert result.schema_valid is True
    assert result.grounded is True
    assert result.policy_defect is False
    assert result.route_state == "shadow_only"


def test_evaluate_candidate_rejects_raw_or_unauthorized_fields() -> None:
    case = FrozenEvaluationCase(
        case_id="title-002",
        task="title_generation",
        sanitized_input={"scene_summary": "아이 물놀이"},
        response_schema={"required": ["titles"], "properties": {"titles": {}}, "additionalProperties": False},
        required_claims=frozenset(),
        corpus_id="videobox-korean-v1",
        prompt_schema_version="v1",
        renderer_version="ffmpeg-fixture-v1",
    )

    result = evaluate_candidate(
        case=case,
        candidate=CandidateResult(
            provider="fake_gpt",
            runtime="fake",
            model="gpt-5.4-mini",
            output={"titles": ["제목"], "source_path": "C:/private/video.mp4"},
            latency_ms=1,
            token_count=1,
        ),
    )

    assert result.schema_valid is False
    assert result.grounded is True
    assert result.policy_defect is True
    assert result.route_state == "needs_human_review"


def test_evaluate_candidate_fails_closed_for_ungrounded_or_malformed_contract() -> None:
    case = FrozenEvaluationCase(
        case_id="summary-003",
        task="conversation_compression",
        sanitized_input={"audio_policy": "preserve_original"},
        response_schema={"required": "summary", "properties": {"summary": {}}, "additionalProperties": False},
        required_claims=frozenset({"preserve_original"}),
        corpus_id="videobox-korean-v1",
        prompt_schema_version="v1",
        renderer_version="ffmpeg-fixture-v1",
    )

    result = evaluate_candidate(
        case=case,
        candidate=CandidateResult(
            provider="local_qwen",
            runtime="lm_studio",
            model="qwen3.6-35b-a3b",
            output={"summary": "장면 요약"},
            latency_ms=2,
            token_count=4,
        ),
    )

    assert result.schema_valid is False
    assert result.grounded is False
    assert result.route_state == "needs_human_review"


def test_evaluate_candidate_detects_nested_approval_or_tool_smuggling() -> None:
    case = FrozenEvaluationCase(
        case_id="title-004",
        task="title_generation",
        sanitized_input={"scene_summary": "아이 놀이터"},
        response_schema={"required": ["titles"], "properties": {"titles": {}, "metadata": {}}, "additionalProperties": False},
        required_claims=frozenset(),
        corpus_id="videobox-korean-v1",
        prompt_schema_version="v1",
        renderer_version="ffmpeg-fixture-v1",
    )

    result = evaluate_candidate(
        case=case,
        candidate=CandidateResult(
            provider="fake_gpt",
            runtime="fake",
            model="gpt-5.4-mini",
            output={"titles": ["놀이터의 오후"], "metadata": {"tool_call": "render"}},
            latency_ms=1,
            token_count=1,
        ),
    )

    assert result.policy_defect is True
    assert result.route_state == "needs_human_review"


def test_evaluate_candidate_fails_closed_for_non_object_extra_field_and_path_or_credential() -> None:
    case = FrozenEvaluationCase(
        case_id="title-005",
        task="title_generation",
        sanitized_input={"scene_summary": "아이 놀이터"},
        response_schema={"required": ["titles"], "properties": {"titles": {}}, "additionalProperties": False},
        required_claims=frozenset(),
        corpus_id="videobox-korean-v1",
        prompt_schema_version="v1",
        renderer_version="ffmpeg-fixture-v1",
    )

    raw_result = evaluate_candidate(
        case=case,
        candidate=CandidateResult("fake_gpt", "fake", "gpt-5.4-mini", "titles", 1, 1),
    )
    credential_result = evaluate_candidate(
        case=case,
        candidate=CandidateResult(
            "fake_gpt", "fake", "gpt-5.4-mini", {"titles": ["제목"], "access_token": "secret"}, 1, 1
        ),
    )
    path_result = evaluate_candidate(
        case=case,
        candidate=CandidateResult("fake_gpt", "fake", "gpt-5.4-mini", {"titles": ["C:/private/video.mp4"]}, 1, 1),
    )

    assert raw_result.route_state == "needs_human_review"
    assert credential_result.schema_valid is False
    assert credential_result.policy_defect is True
    assert path_result.policy_defect is True


def test_frozen_case_copies_nested_fixture_and_records_identity() -> None:
    source_input = {"scene_summary": "아이 물놀이"}
    source_schema = {"required": ["titles"], "properties": {"titles": {}}, "additionalProperties": False}
    case = FrozenEvaluationCase(
        case_id="title-006",
        task="title_generation",
        sanitized_input=source_input,
        response_schema=source_schema,
        required_claims=frozenset(),
        corpus_id="videobox-korean-v1",
        prompt_schema_version="v1",
        renderer_version="ffmpeg-fixture-v1",
    )
    source_input["scene_summary"] = "변조"
    source_schema["required"].clear()

    result = evaluate_candidate(
        case=case,
        candidate=CandidateResult("local_qwen", "lm_studio", "qwen3.6-35b-a3b", {"titles": ["물놀이" ]}, 1, 1),
    )

    assert case.sanitized_input["scene_summary"] == "아이 물놀이"
    assert result.schema_valid is True
    assert result.corpus_id == "videobox-korean-v1"
    assert result.prompt_schema_version == "v1"
    assert result.renderer_version == "ffmpeg-fixture-v1"


def test_frozen_case_rejects_non_json_mutable_values_and_relative_media_paths() -> None:
    with pytest.raises(ValueError, match="JSON-compatible"):
        FrozenEvaluationCase(
            case_id="bad-007",
            task="title_generation",
            sanitized_input={"tags": {"mutable"}},
            response_schema={"required": ["titles"], "properties": {"titles": {}}, "additionalProperties": False},
            required_claims=frozenset(),
            corpus_id="videobox-korean-v1",
            prompt_schema_version="v1",
            renderer_version="ffmpeg-fixture-v1",
        )

    case = FrozenEvaluationCase(
        case_id="title-008",
        task="title_generation",
        sanitized_input={"scene_summary": "아이 놀이터"},
        response_schema={"required": ["titles"], "properties": {"titles": {}}, "additionalProperties": False},
        required_claims=frozenset(),
        corpus_id="videobox-korean-v1",
        prompt_schema_version="v1",
        renderer_version="ffmpeg-fixture-v1",
    )
    result = evaluate_candidate(
        case=case,
        candidate=CandidateResult("local_qwen", "lm_studio", "qwen3.6-35b-a3b", {"titles": ["clips/kids.mp4"]}, 1, 1),
    )

    assert result.policy_defect is True
    assert result.route_state == "needs_human_review"
