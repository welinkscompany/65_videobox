from __future__ import annotations

import json
from hashlib import sha256

import pytest

from videobox_core_engine.agent_quality_harness import (
    CHECKED_IN_KOREAN_EVALUATION_FIXTURE_PATH,
    CandidateResult,
    EvaluationMeasurement,
    FrozenKoreanEvaluationCorpus,
    FrozenEvaluationCase,
    QualificationThresholds,
    build_qualification_report,
    evaluate_candidate,
    load_checked_in_korean_evaluation_corpus,
)
from videobox_core_engine.evaluation_fixture_versions import KOREAN_SHADOW_EVALUATION_V1_CANONICAL_SHA256


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


def test_evaluate_candidate_rejects_wrong_declared_property_value_type() -> None:
    case = FrozenEvaluationCase(
        case_id="typed-title-001",
        task="title_generation",
        sanitized_input={"scene_summary": "아이 물놀이"},
        response_schema={
            "type": "object",
            "required": ["titles"],
            "properties": {"titles": {"type": "array", "items": {"type": "string"}}},
            "additionalProperties": False,
        },
        required_claims=frozenset(),
        corpus_id="typed-v1",
        prompt_schema_version="v1",
        renderer_version="fixture-v1",
    )

    result = evaluate_candidate(
        case=case,
        candidate=CandidateResult("local_qwen", "fixture", "qwen", {"titles": [123]}, 1, 1),
    )

    assert result.schema_valid is False
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


def test_offline_qualification_report_records_metrics_ci_and_human_gate() -> None:
    cases = tuple(
        FrozenEvaluationCase(
            case_id=f"title-{index:03d}",
            task="title_generation",
            sanitized_input={"scene_summary": f"아이 물놀이 장면 {index}"},
            response_schema={"required": ["titles"], "properties": {"titles": {}}, "additionalProperties": False},
            required_claims=frozenset(),
            corpus_id="videobox-korean-v1",
            prompt_schema_version="v1",
            renderer_version="ffmpeg-fixture-v1",
        )
        for index in range(1, 4)
    )
    corpus = FrozenKoreanEvaluationCorpus(
        corpus_id="videobox-korean-v1",
        prompt_schema_version="v1",
        renderer_version="ffmpeg-fixture-v1",
        cases=cases,
    )

    measurements = tuple(
        measurement
        for index, case in enumerate(cases)
        for measurement in (
            EvaluationMeasurement(
                case=case,
                candidate=CandidateResult(
                    provider="hermes_fixture",
                    runtime="fixture",
                    model="gpt-5.4-mini",
                    output={"titles": ["물놀이 제목"]},
                    latency_ms=10,
                    token_count=10,
                ),
                human_score=4.5,
                correction_seconds=100,
            ),
            EvaluationMeasurement(
                case=case,
                candidate=CandidateResult(
                    provider="local_qwen",
                    runtime="fixture",
                    model="qwen3.6-35b-a3b",
                    output={"titles": ["물놀이 제목"]},
                    latency_ms=12,
                    token_count=12,
                ),
                human_score=4.3,
                correction_seconds=105,
            ),
        )
    )

    report = build_qualification_report(
        corpus=corpus,
        measurements=measurements,
        baseline_provider="hermes_fixture",
        candidate_provider="local_qwen",
    )

    assert report.schema_valid_rate == 1.0
    assert report.grounded_claim_rate == 1.0
    assert report.critical_policy_defect_count == 0
    assert report.human_score_delta == pytest.approx(-0.2)
    assert report.correction_time_delta_ratio == pytest.approx(0.05)
    assert report.schema_valid_ci_95 is not None
    assert report.human_score_delta_ci_95 is not None
    assert report.route_state == "needs_human_review"


def test_qualification_report_policy_defect_cannot_qualify() -> None:
    case = FrozenEvaluationCase(
        case_id="title-policy-001",
        task="title_generation",
        sanitized_input={"scene_summary": "아이 물놀이"},
        response_schema={"required": ["titles"], "properties": {"titles": {}}, "additionalProperties": False},
        required_claims=frozenset(),
        corpus_id="videobox-korean-v1",
        prompt_schema_version="v1",
        renderer_version="ffmpeg-fixture-v1",
    )
    corpus = FrozenKoreanEvaluationCorpus("videobox-korean-v1", "v1", "ffmpeg-fixture-v1", (case,))
    baseline = CandidateResult("baseline", "fixture", "baseline-v1", {"titles": ["제목"]}, 1, 1)
    candidate = CandidateResult("candidate", "fixture", "candidate-v1", {"titles": ["제목"], "source_path": "C:/private/video.mp4"}, 1, 1)

    report = build_qualification_report(
        corpus=corpus,
        measurements=(EvaluationMeasurement(case, baseline, 5, 10), EvaluationMeasurement(case, candidate, 5, 10)),
        baseline_provider="baseline",
        candidate_provider="candidate",
    )

    assert report.critical_policy_defect_count == 1
    assert report.thresholds_passed is False
    assert report.route_state == "needs_human_review"


def test_qualification_report_rejects_mismatched_case_identity() -> None:
    case = FrozenEvaluationCase(
        case_id="title-identity-001",
        task="title_generation",
        sanitized_input={"scene_summary": "아이 놀이터"},
        response_schema={"required": ["titles"], "properties": {"titles": {}}, "additionalProperties": False},
        required_claims=frozenset(),
        corpus_id="videobox-korean-v1",
        prompt_schema_version="v1",
        renderer_version="ffmpeg-fixture-v1",
    )
    corpus = FrozenKoreanEvaluationCorpus("videobox-korean-v1", "v1", "ffmpeg-fixture-v1", (case,))
    baseline = CandidateResult("baseline", "fixture", "baseline-v1", {"titles": ["제목"]}, 1, 1)
    mismatched_case = FrozenEvaluationCase(
        case_id=case.case_id,
        task=case.task,
        sanitized_input={"scene_summary": "아이 놀이터"},
        response_schema={"required": ["titles"], "properties": {"titles": {}}, "additionalProperties": False},
        required_claims=frozenset(), corpus_id=case.corpus_id, prompt_schema_version=case.prompt_schema_version,
        renderer_version="other-renderer-v1",
    )
    candidate = CandidateResult("candidate", "fixture", "candidate-v1", {"titles": ["제목"]}, 1, 1)

    with pytest.raises(ValueError, match="identity"):
        build_qualification_report(
            corpus=corpus,
            measurements=(
                EvaluationMeasurement(case, baseline, 5, 10),
                EvaluationMeasurement(mismatched_case, candidate, 5, 10),
            ),
            baseline_provider="baseline",
            candidate_provider="candidate",
        )


def test_perfect_static_measurements_remain_non_authorizing() -> None:
    cases = tuple(
        FrozenEvaluationCase(
            case_id=f"static-{index}",
            task="title_generation",
            sanitized_input={"scene_summary": f"아이 물놀이 {index}"},
            response_schema={"required": ["titles"], "properties": {"titles": {}}, "additionalProperties": False},
            required_claims=frozenset(),
            corpus_id="static-v1",
            prompt_schema_version="v1",
            renderer_version="fixture-v1",
        )
        for index in range(20)
    )
    corpus = FrozenKoreanEvaluationCorpus("static-v1", "v1", "fixture-v1", cases)
    measurements = tuple(
        EvaluationMeasurement(case, CandidateResult(provider, "fixture", f"{provider}-v1", {"titles": ["제목"]}, 1, 1), 5, 10)
        for case in cases
        for provider in ("baseline", "candidate")
    )

    report = build_qualification_report(
        corpus=corpus,
        measurements=measurements,
        baseline_provider="baseline",
        candidate_provider="candidate",
    )

    assert report.thresholds_passed is True
    assert report.route_state == "needs_human_review"


def test_frozen_case_and_corpus_reject_prohibited_sanitized_input() -> None:
    with pytest.raises(ValueError, match="prohibited"):
        FrozenEvaluationCase(
            case_id="unsafe-case",
            task="title_generation",
            sanitized_input={"source_path": "C:/private/video.mp4"},
            response_schema={"required": ["titles"], "properties": {"titles": {}}, "additionalProperties": False},
            required_claims=frozenset(),
            corpus_id="unsafe-v1",
            prompt_schema_version="v1",
            renderer_version="fixture-v1",
        )
    with pytest.raises(ValueError, match="prohibited"):
        FrozenEvaluationCase(
            case_id="unsafe-schema-case",
            task="title_generation",
            sanitized_input={"scene_summary": "아이 놀이터"},
            response_schema={
                "type": "object",
                "required": ["titles"],
                "properties": {"titles": {"type": "string", "example": "C:/private/video.mp4"}},
                "additionalProperties": False,
            },
            required_claims=frozenset(),
            corpus_id="unsafe-v1",
            prompt_schema_version="v1",
            renderer_version="fixture-v1",
        )
    with pytest.raises(ValueError, match="prohibited"):
        FrozenEvaluationCase(
            case_id="unsafe-approval-case",
            task="title_generation",
            sanitized_input={"approval_state": "approved"},
            response_schema={"required": ["titles"], "properties": {"titles": {}}, "additionalProperties": False},
            required_claims=frozenset(),
            corpus_id="unsafe-v1",
            prompt_schema_version="v1",
            renderer_version="fixture-v1",
        )

    safe_case = FrozenEvaluationCase(
        case_id="safe-case",
        task="title_generation",
        sanitized_input={"scene_summary": "아이 놀이터"},
        response_schema={"required": ["titles"], "properties": {"titles": {}}, "additionalProperties": False},
        required_claims=frozenset(),
        corpus_id="unsafe-v1",
        prompt_schema_version="v1",
        renderer_version="fixture-v1",
    )
    object.__setattr__(safe_case, "sanitized_input", {"access_token": "secret"})
    with pytest.raises(ValueError, match="prohibited"):
        FrozenKoreanEvaluationCorpus("unsafe-v1", "v1", "fixture-v1", (safe_case,))


def test_qualification_threshold_counts_require_real_integers() -> None:
    with pytest.raises(ValueError, match="integer"):
        QualificationThresholds(minimum_sample_size=20.0)
    with pytest.raises(ValueError, match="integer"):
        QualificationThresholds(maximum_critical_policy_defect_count=False)


def test_qualification_report_recomputes_policy_defect_from_captured_candidate() -> None:
    case = FrozenEvaluationCase(
        case_id="forged-policy-001",
        task="title_generation",
        sanitized_input={"scene_summary": "아이 놀이터"},
        response_schema={"required": ["titles"], "properties": {"titles": {}}, "additionalProperties": False},
        required_claims=frozenset(),
        corpus_id="forged-v1",
        prompt_schema_version="v1",
        renderer_version="fixture-v1",
    )
    corpus = FrozenKoreanEvaluationCorpus("forged-v1", "v1", "fixture-v1", (case,))
    baseline = CandidateResult("baseline", "fixture", "baseline-v1", {"titles": ["제목"]}, 1, 1)
    prohibited_candidate = CandidateResult(
        "candidate", "fixture", "candidate-v1", {"titles": ["제목"], "access_token": "secret"}, 1, 1
    )

    report = build_qualification_report(
        corpus=corpus,
        measurements=(
            EvaluationMeasurement(case, baseline, 5, 10),
            EvaluationMeasurement(case, prohibited_candidate, 5, 10),
        ),
        baseline_provider="baseline",
        candidate_provider="candidate",
    )

    assert report.critical_policy_defect_count == 1
    assert report.route_state == "needs_human_review"


def test_checked_in_korean_fixture_loader_verifies_canonical_digest(tmp_path) -> None:
    corpus = load_checked_in_korean_evaluation_corpus()
    assert corpus.corpus_id == "videobox-korean-shadow-v1"
    assert len(corpus.cases) == 3

    fixture_path = tmp_path / "tampered-korean-corpus.json"
    fixture_path.write_text(CHECKED_IN_KOREAN_EVALUATION_FIXTURE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload["corpus"]["cases"][0]["sanitized_input"]["scene_summary"] = "변조"
    payload["canonical_sha256"] = sha256(
        json.dumps(payload["corpus"], ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    fixture_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="digest"):
        load_checked_in_korean_evaluation_corpus(fixture_path)
    assert payload["canonical_sha256"] != KOREAN_SHADOW_EVALUATION_V1_CANONICAL_SHA256
