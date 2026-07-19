from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from threading import Event

import pytest

from videobox_core_engine.agent_quality_harness import load_checked_in_korean_evaluation_corpus
from videobox_core_engine.evaluation_fixture_versions import KOREAN_SHADOW_EVALUATION_V1_CANONICAL_SHA256
from videobox_core_engine.provider_qualification_evidence import (
    ProviderEvidenceCapture,
    ProviderQualificationEvidenceLedger,
    import_synthetic_provider_capture,
)


def _capture_envelope(*, case_id: str, provider: str, output: dict[str, object]) -> dict[str, object]:
    corpus = load_checked_in_korean_evaluation_corpus()
    payload = {
        "capture_version": "videobox-provider-capture-v1",
        "capture_id": f"capture-{provider}-{case_id}",
        "corpus_id": corpus.corpus_id,
        "corpus_canonical_sha256": KOREAN_SHADOW_EVALUATION_V1_CANONICAL_SHA256,
        "prompt_schema_version": corpus.prompt_schema_version,
        "renderer_version": corpus.renderer_version,
        "case_id": case_id,
        "candidate": {
            "provider": provider,
            "runtime": "synthetic_fixture",
            "model": f"{provider}-model-v1",
            "output": output,
            "latency_ms": 12,
            "token_count": 34,
        },
        "attestation": {
            "reviewer_ref": "synthetic-reviewer",
            "score": 4.5,
            "correction_seconds": 30,
            "attestation_id": f"attestation-{provider}-{case_id}",
            "attested_at": "2026-07-19T10:00:00Z",
        },
    }
    return {
        **payload,
        "payload_sha256": sha256(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest(),
    }


def _output_for_case(case_id: str) -> dict[str, object]:
    if case_id == "summary-playground-002":
        return {"summary": "아이들이 놀이터에서 즐겁게 놉니다."}
    return {"titles": ["원본 소리를 살린 놀이 장면"], "audio_policy": "preserve_original"}


def test_import_append_and_verify_report_is_always_non_authorizing(tmp_path) -> None:
    corpus = load_checked_in_korean_evaluation_corpus()
    ledger = ProviderQualificationEvidenceLedger(tmp_path)
    for provider in ("synthetic_gpt", "synthetic_qwen"):
        for case in corpus.cases:
            ledger.append(import_synthetic_provider_capture(_capture_envelope(
                case_id=case.case_id, provider=provider, output=_output_for_case(case.case_id)
            )))

    persisted = ledger.write_qualification_report(
        audit_id="synthetic-audit-v1",
        baseline_provider="synthetic_gpt",
        candidate_provider="synthetic_qwen",
    )

    verified = ledger.verify_qualification_report(persisted.path)
    assert len(ledger.verify_records()) == 6
    assert verified.report.sample_size == 3
    assert verified.report.route_state == "needs_human_review"
    assert verified.report.thresholds_passed is False


def test_import_rejects_capture_payload_digest_and_attestation_identity_tampering() -> None:
    envelope = _capture_envelope(
        case_id="title-waterplay-001",
        provider="synthetic_gpt",
        output=_output_for_case("title-waterplay-001"),
    )
    tampered_digest = deepcopy(envelope)
    tampered_digest["candidate"]["output"]["titles"] = ["변조된 제목"]  # type: ignore[index]
    with pytest.raises(ValueError, match="digest"):
        import_synthetic_provider_capture(tampered_digest)

    wrong_identity = deepcopy(envelope)
    wrong_identity["case_id"] = "unknown-case"
    wrong_payload = {key: value for key, value in wrong_identity.items() if key != "payload_sha256"}
    wrong_identity["payload_sha256"] = sha256(
        json.dumps(wrong_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    with pytest.raises(ValueError, match="case"):
        import_synthetic_provider_capture(wrong_identity)


def test_import_rejects_recomputed_capture_with_wrong_pinned_corpus_digest() -> None:
    envelope = _capture_envelope(
        case_id="title-waterplay-001",
        provider="synthetic_gpt",
        output=_output_for_case("title-waterplay-001"),
    )
    envelope["corpus_canonical_sha256"] = "0" * 64
    payload = {key: value for key, value in envelope.items() if key != "payload_sha256"}
    envelope["payload_sha256"] = sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()

    with pytest.raises(ValueError, match="corpus digest"):
        import_synthetic_provider_capture(envelope)


def test_ledger_detects_record_content_tampering_and_capture_replay(tmp_path) -> None:
    capture = import_synthetic_provider_capture(_capture_envelope(
        case_id="title-waterplay-001",
        provider="synthetic_gpt",
        output=_output_for_case("title-waterplay-001"),
    ))
    ledger = ProviderQualificationEvidenceLedger(tmp_path)
    ledger.append(capture)
    with pytest.raises(ValueError, match="replay"):
        ledger.append(capture)

    raw = json.loads(ledger.records_path.read_text(encoding="utf-8"))
    raw["records"][0]["capture"]["attestation"]["score"] = 5
    ledger.records_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        ledger.verify_records()


def test_ledger_rejects_rebinding_one_human_attestation_to_a_second_capture(tmp_path) -> None:
    envelope = _capture_envelope(
        case_id="title-waterplay-001",
        provider="synthetic_gpt",
        output=_output_for_case("title-waterplay-001"),
    )
    rebinding = deepcopy(envelope)
    rebinding["capture_id"] = "capture-synthetic_gpt-title-waterplay-001-retry"
    rebinding_payload = {key: value for key, value in rebinding.items() if key != "payload_sha256"}
    rebinding["payload_sha256"] = sha256(
        json.dumps(rebinding_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()

    ledger = ProviderQualificationEvidenceLedger(tmp_path)
    ledger.append(import_synthetic_provider_capture(envelope))
    with pytest.raises(ValueError, match="attestation replay"):
        ledger.append(import_synthetic_provider_capture(rebinding))


def test_ledger_detects_persisted_report_alteration(tmp_path) -> None:
    corpus = load_checked_in_korean_evaluation_corpus()
    ledger = ProviderQualificationEvidenceLedger(tmp_path)
    for provider in ("synthetic_gpt", "synthetic_qwen"):
        for case in corpus.cases:
            ledger.append(import_synthetic_provider_capture(_capture_envelope(
                case_id=case.case_id, provider=provider, output=_output_for_case(case.case_id)
            )))
    persisted = ledger.write_qualification_report(
        audit_id="synthetic-audit-v1",
        baseline_provider="synthetic_gpt",
        candidate_provider="synthetic_qwen",
    )

    raw = json.loads(persisted.path.read_text(encoding="utf-8"))
    raw["report"]["route_state"] = "qualified"
    persisted.path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="digest|route"):
        ledger.verify_qualification_report(persisted.path)


def test_ledger_rejects_rehashed_audit_with_type_spoofed_metric_scalar(tmp_path) -> None:
    corpus = load_checked_in_korean_evaluation_corpus()
    ledger = ProviderQualificationEvidenceLedger(tmp_path)
    for provider in ("synthetic_gpt", "synthetic_qwen"):
        for case in corpus.cases:
            ledger.append(import_synthetic_provider_capture(_capture_envelope(
                case_id=case.case_id, provider=provider, output=_output_for_case(case.case_id)
            )))
    persisted = ledger.write_qualification_report(
        audit_id="type-spoof-audit-v1",
        baseline_provider="synthetic_gpt",
        candidate_provider="synthetic_qwen",
    )

    raw = json.loads(persisted.path.read_text(encoding="utf-8"))
    raw["report"]["schema_valid_rate"] = 1
    payload = {key: value for key, value in raw.items() if key != "artifact_sha256"}
    raw["artifact_sha256"] = sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    persisted.path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="payload|metric"):
        ledger.verify_qualification_report(persisted.path)


def test_public_capture_import_and_ledger_cannot_accept_a_custom_corpus(tmp_path) -> None:
    corpus = load_checked_in_korean_evaluation_corpus()
    envelope = _capture_envelope(
        case_id="title-waterplay-001",
        provider="synthetic_gpt",
        output=_output_for_case("title-waterplay-001"),
    )

    with pytest.raises(TypeError):
        import_synthetic_provider_capture(envelope, corpus=corpus)
    with pytest.raises(TypeError):
        ProviderQualificationEvidenceLedger(tmp_path, corpus=corpus)


def test_ledger_revalidates_manually_constructed_capture_before_writing(tmp_path) -> None:
    valid = import_synthetic_provider_capture(_capture_envelope(
        case_id="title-waterplay-001",
        provider="synthetic_gpt",
        output=_output_for_case("title-waterplay-001"),
    ))
    forged = ProviderEvidenceCapture(
        capture_id=valid.capture_id,
        case=valid.case,
        corpus_canonical_sha256=valid.corpus_canonical_sha256,
        candidate=type(valid.candidate)(
            valid.candidate.provider,
            valid.candidate.runtime,
            valid.candidate.model,
            {"titles": ["제목"], "source_path": "C:/private/video.mp4"},
            valid.candidate.latency_ms,
            valid.candidate.token_count,
        ),
        attestation=valid.attestation,
        payload_sha256=valid.payload_sha256,
    )

    with pytest.raises(ValueError, match="digest|safe"):
        ProviderQualificationEvidenceLedger(tmp_path).append(forged)


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "tool_calls",
        "tool_result",
        "tool_output",
        "shell_command",
        "approval_status",
        "approval_decision",
        "approval_required",
        "authorization",
        "authorization_header",
        "key_value",
        "credential_value",
        "password_hint",
        "api_key_value",
    ],
)
def test_import_rejects_normalized_forbidden_key_variants(forbidden_key: str) -> None:
    envelope = _capture_envelope(
        case_id="title-waterplay-001",
        provider="synthetic_gpt",
        output={"titles": ["제목"], "audio_policy": "preserve_original", forbidden_key: "blocked"},
    )

    with pytest.raises(ValueError, match="prohibited|safe"):
        import_synthetic_provider_capture(envelope)


@pytest.mark.parametrize(
    "raw_path",
    ["/mnt/private/video.mp4", "file:///mnt/private/video.mp4", "근거 C:/private/video.mp4 는 사용하지 마세요"],
)
def test_import_rejects_recomputed_digest_with_raw_path_text(raw_path: str) -> None:
    envelope = _capture_envelope(
        case_id="title-waterplay-001",
        provider="synthetic_gpt",
        output={"titles": [raw_path], "audio_policy": "preserve_original"},
    )

    with pytest.raises(ValueError, match="prohibited|safe"):
        import_synthetic_provider_capture(envelope)


def test_historic_audit_remains_verifiable_after_later_capture_append(tmp_path) -> None:
    corpus = load_checked_in_korean_evaluation_corpus()
    ledger = ProviderQualificationEvidenceLedger(tmp_path)
    for provider in ("synthetic_gpt", "synthetic_qwen"):
        for case in corpus.cases:
            ledger.append(import_synthetic_provider_capture(_capture_envelope(
                case_id=case.case_id, provider=provider, output=_output_for_case(case.case_id)
            )))
    persisted = ledger.write_qualification_report(
        audit_id="historic-audit-v1",
        baseline_provider="synthetic_gpt",
        candidate_provider="synthetic_qwen",
    )

    later = _capture_envelope(
        case_id="title-waterplay-001",
        provider="synthetic_qwen",
        output=_output_for_case("title-waterplay-001"),
    )
    later["capture_id"] = "capture-synthetic-qwen-later"
    later["attestation"]["attestation_id"] = "attestation-synthetic-qwen-later"  # type: ignore[index]
    later_payload = {key: value for key, value in later.items() if key != "payload_sha256"}
    later["payload_sha256"] = sha256(
        json.dumps(later_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    ledger.append(import_synthetic_provider_capture(later))

    assert ledger.verify_qualification_report(persisted.path).audit_id == "historic-audit-v1"


def test_concurrent_ledger_appends_do_not_lose_distinct_records(tmp_path) -> None:
    captures = (
        import_synthetic_provider_capture(_capture_envelope(
            case_id="title-waterplay-001", provider="synthetic_gpt", output=_output_for_case("title-waterplay-001")
        )),
        import_synthetic_provider_capture(_capture_envelope(
            case_id="summary-playground-002", provider="synthetic_qwen", output=_output_for_case("summary-playground-002")
        )),
    )
    start = Event()

    def append(capture):
        start.wait()
        return ProviderQualificationEvidenceLedger(tmp_path).append(capture)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(append, capture) for capture in captures]
        start.set()
        results = [future.result() for future in futures]

    assert len({result.record_sha256 for result in results}) == 2
    assert len(ProviderQualificationEvidenceLedger(tmp_path).verify_records()) == 2


def test_concurrent_write_once_audit_has_exactly_one_winner(tmp_path) -> None:
    corpus = load_checked_in_korean_evaluation_corpus()
    ledger = ProviderQualificationEvidenceLedger(tmp_path)
    for provider in ("synthetic_gpt", "synthetic_qwen"):
        for case in corpus.cases:
            ledger.append(import_synthetic_provider_capture(_capture_envelope(
                case_id=case.case_id, provider=provider, output=_output_for_case(case.case_id)
            )))
    start = Event()

    def write() -> str:
        start.wait()
        try:
            ProviderQualificationEvidenceLedger(tmp_path).write_qualification_report(
                audit_id="contended-audit-v1", baseline_provider="synthetic_gpt", candidate_provider="synthetic_qwen"
            )
        except ValueError as error:
            return str(error)
        return "winner"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(write), executor.submit(write)]
        start.set()
        outcomes = [future.result() for future in futures]

    assert outcomes.count("winner") == 1
    assert any("write-once" in outcome for outcome in outcomes)
    path = ledger.reports_directory / "contended-audit-v1.json"
    assert ledger.verify_qualification_report(path).audit_id == "contended-audit-v1"
