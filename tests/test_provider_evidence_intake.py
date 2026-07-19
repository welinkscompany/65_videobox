from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from hashlib import sha256
import json

import pytest
from threading import Event

from videobox_core_engine.agent_quality_harness import load_checked_in_korean_evaluation_corpus
from videobox_core_engine.evaluation_fixture_versions import KOREAN_SHADOW_EVALUATION_V1_CANONICAL_SHA256
from videobox_core_engine.provider_evidence_intake import (
    EvidenceIntakeGateway,
    OwnerEvidenceImportGrant,
)
from videobox_core_engine.provider_qualification_evidence import (
    ProviderQualificationEvidenceLedger,
    import_synthetic_provider_capture,
)


NOW = "2026-07-19T12:00:00Z"


def _capture_envelope(*, capture_id: str = "capture-synthetic-gpt-001", provider: str = "synthetic_gpt",
                      runtime: str = "synthetic_fixture", token_count: int = 34, latency_ms: int = 12) -> dict[str, object]:
    corpus = load_checked_in_korean_evaluation_corpus()
    payload = {
        "capture_version": "videobox-provider-capture-v1",
        "capture_id": capture_id,
        "corpus_id": corpus.corpus_id,
        "corpus_canonical_sha256": KOREAN_SHADOW_EVALUATION_V1_CANONICAL_SHA256,
        "prompt_schema_version": corpus.prompt_schema_version,
        "renderer_version": corpus.renderer_version,
        "case_id": "title-waterplay-001",
        "candidate": {
            "provider": provider,
            "runtime": runtime,
            "model": f"{provider}-fixture-v1",
            "output": {"titles": ["아이 물놀이 장면"], "audio_policy": "preserve_original"},
            "latency_ms": latency_ms,
            "token_count": token_count,
        },
        "attestation": {
            "reviewer_ref": "synthetic-reviewer",
            "score": 4.5,
            "correction_seconds": 30,
            "attestation_id": f"attestation-{capture_id}",
            "attested_at": "2026-07-19T10:00:00Z",
        },
    }
    return {**payload, "payload_sha256": sha256(json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")).hexdigest()}


def _grant(**overrides: object) -> OwnerEvidenceImportGrant:
    values: dict[str, object] = {
        "owner_ref": "owner-local-opaque",
        "grant_id": "grant-synthetic-gpt-001",
        "corpus_canonical_sha256": KOREAN_SHADOW_EVALUATION_V1_CANONICAL_SHA256,
        "provider": "synthetic_gpt",
        "runtime": "synthetic_fixture",
        "scope": "offline_synthetic_evidence_import",
        "expires_at": "2026-07-20T12:00:00Z",
        "max_capture_count": 1,
        "max_token_total": 100,
        "max_latency_total_ms": 100,
    }
    values.update(overrides)
    return OwnerEvidenceImportGrant(**values)  # type: ignore[arg-type]


def test_preflight_is_side_effect_free_and_accepts_only_a_bound_synthetic_capture(tmp_path) -> None:
    gateway = EvidenceIntakeGateway(tmp_path)
    envelope = _capture_envelope()
    grant = _grant()

    preflight = gateway.preflight(envelope, grant, now=NOW)

    assert preflight.allowed is True
    assert preflight.reason_code == "allowed_offline_synthetic_evidence_only"
    assert gateway.verify_accepted_evidence() == ()
    assert gateway.verify_audit_events() == ()

    accepted = gateway.accept(envelope, grant, now=NOW)

    assert accepted.allowed is True
    assert accepted.non_authorizing_state == "offline_evidence_only"
    assert len(gateway.verify_accepted_evidence()) == 1
    events = gateway.verify_audit_events()
    assert len(events) == 1
    assert events[0].outcome == "accepted"
    assert events[0].non_authorizing_state == "offline_evidence_only"


def test_denials_do_not_append_capture_or_consume_budget(tmp_path) -> None:
    gateway = EvidenceIntakeGateway(tmp_path)
    valid = _capture_envelope()
    expired = _grant(expires_at="2026-07-19T11:59:59Z")
    wrong_provider = _grant(provider="synthetic_qwen")
    wrong_runtime = _grant(runtime="other_fixture")
    wrong_corpus = _grant(corpus_canonical_sha256="0" * 64)
    malformed = {"approval": "yes"}
    real = _capture_envelope(provider="gpt-5.4-mini", runtime="oauth")

    decisions = [
        gateway.accept(valid, expired, now=NOW),
        gateway.accept(valid, wrong_provider, now=NOW),
        gateway.accept(valid, wrong_runtime, now=NOW),
        gateway.accept(valid, wrong_corpus, now=NOW),
        gateway.accept(valid, malformed, now=NOW),
        gateway.accept(real, _grant(), now=NOW),
    ]

    assert [decision.reason_code for decision in decisions] == [
        "grant_expired", "grant_binding_mismatch", "grant_invalid", "grant_invalid", "grant_invalid", "synthetic_only",
    ]
    assert gateway.verify_accepted_evidence() == ()
    assert [event.outcome for event in gateway.verify_audit_events()] == ["denied"] * 6


def test_budget_and_replay_rejections_do_not_mutate_evidence_ledger(tmp_path) -> None:
    gateway = EvidenceIntakeGateway(tmp_path)
    envelope = _capture_envelope()
    count_limited = _grant(max_capture_count=0)
    token_limited = _grant(max_token_total=33)
    latency_limited = _grant(max_latency_total_ms=11)

    assert gateway.accept(envelope, count_limited, now=NOW).reason_code == "budget_capture_limit"
    assert gateway.accept(envelope, token_limited, now=NOW).reason_code == "budget_token_limit"
    assert gateway.accept(envelope, latency_limited, now=NOW).reason_code == "budget_latency_limit"
    assert gateway.verify_accepted_evidence() == ()
    assert [event.outcome for event in gateway.verify_audit_events()] == ["denied"] * 3

    accepted = gateway.accept(envelope, _grant(), now=NOW)
    replay = gateway.accept(envelope, _grant(), now=NOW)

    assert accepted.allowed is True
    assert replay.allowed is False
    assert replay.reason_code == "capture_replay"
    assert len(gateway.verify_accepted_evidence()) == 1
    assert [event.outcome for event in gateway.verify_audit_events()] == ["denied"] * 3 + ["accepted", "denied"]


def test_grant_id_cannot_be_rebound_to_expand_its_budget(tmp_path) -> None:
    gateway = EvidenceIntakeGateway(tmp_path)
    first = _capture_envelope(capture_id="capture-synthetic-gpt-first")
    rebound_capture = _capture_envelope(capture_id="capture-synthetic-gpt-rebound")
    original = _grant(max_capture_count=1)
    rebound = _grant(max_capture_count=2)

    assert gateway.accept(first, original, now=NOW).allowed is True
    decision = gateway.accept(rebound_capture, rebound, now=NOW)

    assert decision.allowed is False
    assert decision.reason_code == "grant_replay"
    assert len(gateway.verify_accepted_evidence()) == 1
    assert [event.outcome for event in gateway.verify_audit_events()] == ["accepted", "denied"]


def test_audit_is_tamper_evident_and_redacts_capture_content(tmp_path) -> None:
    gateway = EvidenceIntakeGateway(tmp_path)
    accepted = gateway.accept(_capture_envelope(), _grant(), now=NOW)
    assert accepted.allowed is True

    raw = json.loads(gateway.audit_path.read_text(encoding="utf-8"))
    event = raw["events"][0]
    serialized = json.dumps(event, ensure_ascii=False)
    assert "아이 물놀이" not in serialized
    assert "token_count" not in serialized
    assert "credential" not in serialized
    assert "path" not in serialized
    assert event["non_authorizing_state"] == "offline_evidence_only"

    tampered = deepcopy(raw)
    tampered["events"][0]["outcome"] = "authorized"
    gateway.audit_path.write_text(json.dumps(tampered, ensure_ascii=False), encoding="utf-8")

    try:
        gateway.verify_audit_events()
    except ValueError as error:
        assert "hash" in str(error)
    else:
        raise AssertionError("tampered intake audit must be rejected")


def test_audit_rejects_a_rehashed_usage_aggregate_that_disagrees_with_evidence(tmp_path) -> None:
    gateway = EvidenceIntakeGateway(tmp_path)
    assert gateway.accept(_capture_envelope(), _grant(), now=NOW).allowed is True

    raw = json.loads(gateway.audit_path.read_text(encoding="utf-8"))
    raw["events"][0]["usage_delta"]["token_total"] = 0
    payload = {key: value for key, value in raw["events"][0].items() if key != "event_sha256"}
    raw["events"][0]["event_sha256"] = sha256(json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")).hexdigest()
    gateway.audit_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    try:
        gateway.verify_audit_events()
    except ValueError as error:
        assert "usage" in str(error)
    else:
        raise AssertionError("usage aggregate must bind to the accepted evidence")


def test_preflight_fails_closed_with_a_stable_reason_when_durable_state_is_tampered(tmp_path) -> None:
    gateway = EvidenceIntakeGateway(tmp_path)
    assert gateway.accept(_capture_envelope(), _grant(), now=NOW).allowed is True
    raw = json.loads(gateway.audit_path.read_text(encoding="utf-8"))
    raw["events"][0]["outcome"] = "authorized"
    gateway.audit_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    decision = gateway.preflight(
        _capture_envelope(capture_id="capture-synthetic-gpt-after-tamper"), _grant(max_capture_count=2), now=NOW
    )

    assert decision.allowed is False
    assert decision.reason_code == "intake_state_invalid"


def test_audit_failure_after_evidence_append_is_reconciled_by_a_fresh_gateway_retry(tmp_path, monkeypatch) -> None:
    gateway = EvidenceIntakeGateway(tmp_path)
    envelope = _capture_envelope()
    grant = _grant()

    def fail_audit(*_args, **_kwargs) -> None:
        raise OSError("simulated audit write failure")

    monkeypatch.setattr(gateway, "_append_accepted_event", fail_audit)
    interrupted = gateway.accept(envelope, grant, now=NOW)

    assert interrupted.allowed is False
    assert interrupted.reason_code == "intake_recovery_required"
    assert len(gateway.verify_accepted_evidence()) == 1
    assert gateway.transaction_path.exists()

    recovered = EvidenceIntakeGateway(tmp_path).accept(envelope, grant, now=NOW)

    assert recovered.allowed is True
    assert len(EvidenceIntakeGateway(tmp_path).verify_accepted_evidence()) == 1
    assert [event.outcome for event in EvidenceIntakeGateway(tmp_path).verify_audit_events()] == ["denied", "accepted"]
    assert not EvidenceIntakeGateway(tmp_path).transaction_path.exists()


def test_ledger_failure_after_prepared_journal_cannot_create_phantom_audit_and_retry_completes(tmp_path, monkeypatch) -> None:
    gateway = EvidenceIntakeGateway(tmp_path)
    envelope = _capture_envelope()
    grant = _grant()
    original_append = gateway._accepted_ledger.append

    def fail_ledger(*_args, **_kwargs):
        raise OSError("simulated ledger write failure")

    monkeypatch.setattr(gateway._accepted_ledger, "append", fail_ledger)
    interrupted = gateway.accept(envelope, grant, now=NOW)

    assert interrupted.allowed is False
    assert interrupted.reason_code == "intake_recovery_required"
    assert gateway.verify_accepted_evidence() == ()
    assert [event.outcome for event in gateway.verify_audit_events(allow_pending=True)] == ["denied"]
    assert gateway.transaction_path.exists()

    monkeypatch.setattr(gateway._accepted_ledger, "append", original_append)
    recovered = EvidenceIntakeGateway(tmp_path).accept(envelope, grant, now=NOW)

    assert recovered.allowed is True
    assert len(EvidenceIntakeGateway(tmp_path).verify_accepted_evidence()) == 1
    assert [event.outcome for event in EvidenceIntakeGateway(tmp_path).verify_audit_events()] == ["denied", "accepted"]


def test_crash_between_ledger_append_and_transaction_phase_is_reconciled_from_prepared_journal(tmp_path, monkeypatch) -> None:
    gateway = EvidenceIntakeGateway(tmp_path)
    envelope = _capture_envelope()
    grant = _grant()
    original_write = gateway._write_transaction

    def fail_evidence_phase(transaction) -> None:
        if transaction["phase"] == "evidence_appended":
            raise OSError("simulated crash before evidence phase is durable")
        original_write(transaction)

    monkeypatch.setattr(gateway, "_write_transaction", fail_evidence_phase)
    interrupted = gateway.accept(envelope, grant, now=NOW)

    assert interrupted.reason_code == "intake_recovery_required"
    assert len(gateway.verify_accepted_evidence()) == 1
    assert gateway.transaction_path.exists()

    recovered = EvidenceIntakeGateway(tmp_path).accept(envelope, grant, now=NOW)

    assert recovered.allowed is True
    assert [event.outcome for event in EvidenceIntakeGateway(tmp_path).verify_audit_events()] == ["denied", "accepted"]


def test_preflight_and_accept_return_the_same_stable_invalid_time_decision(tmp_path) -> None:
    gateway = EvidenceIntakeGateway(tmp_path)
    envelope = _capture_envelope()
    grant = _grant()

    preflight = gateway.preflight(envelope, grant, now="not-a-time")
    accepted = gateway.accept(envelope, grant, now="not-a-time")

    assert preflight.reason_code == accepted.reason_code == "time_invalid"
    assert gateway.verify_accepted_evidence() == ()


def test_audit_hashes_owner_and_grant_refs_and_rejects_duplicate_evidence_binding(tmp_path) -> None:
    owner_ref = "owner-secret-token-should-not-persist"
    grant_id = "grant-secret-token-should-not-persist"
    gateway = EvidenceIntakeGateway(tmp_path)
    assert gateway.accept(_capture_envelope(), _grant(owner_ref=owner_ref, grant_id=grant_id), now=NOW).allowed is True

    raw = json.loads(gateway.audit_path.read_text(encoding="utf-8"))
    serialized = json.dumps(raw, ensure_ascii=False)
    assert owner_ref not in serialized
    assert grant_id not in serialized
    assert "owner_ref_sha256" in raw["events"][0]
    assert "grant_id_sha256" in raw["events"][0]

    duplicate = deepcopy(raw["events"][0])
    duplicate["event_id"] = "intake-duplicate-binding"
    duplicate["previous_event_sha256"] = raw["events"][0]["event_sha256"]
    payload = {key: value for key, value in duplicate.items() if key != "event_sha256"}
    duplicate["event_sha256"] = sha256(json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")).hexdigest()
    raw["events"].append(duplicate)
    gateway.audit_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    try:
        gateway.verify_audit_events()
    except ValueError as error:
        assert "duplicate" in str(error) or "one-to-one" in str(error)
    else:
        raise AssertionError("duplicate audit binding must be rejected")


def test_two_gateway_instances_contend_for_one_capture_budget_without_double_accept(tmp_path) -> None:
    grant = _grant(max_capture_count=1)
    start = Event()

    def accept(capture_id: str):
        start.wait()
        return EvidenceIntakeGateway(tmp_path).accept(_capture_envelope(capture_id=capture_id), grant, now=NOW)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(accept, "capture-synthetic-gpt-left"), executor.submit(accept, "capture-synthetic-gpt-right")]
        start.set()
        decisions = [future.result() for future in futures]

    assert sum(decision.allowed for decision in decisions) == 1
    assert {decision.reason_code for decision in decisions} <= {
        "allowed_offline_synthetic_evidence_only", "budget_capture_limit",
    }
    gateway = EvidenceIntakeGateway(tmp_path)
    assert len(gateway.verify_accepted_evidence()) == 1
    assert [event.outcome for event in gateway.verify_audit_events()] == ["accepted", "denied"]


def test_non_audit_safe_capture_id_is_rejected_before_prepared_journal_creation(tmp_path) -> None:
    gateway = EvidenceIntakeGateway(tmp_path)
    envelope = _capture_envelope(capture_id="capture synthetic with spaces")
    grant = _grant()

    preflight = gateway.preflight(envelope, grant, now=NOW)
    accepted = gateway.accept(envelope, grant, now=NOW)

    assert preflight.reason_code == accepted.reason_code == "capture_identity_invalid"
    assert gateway.verify_accepted_evidence() == ()
    assert [event.outcome for event in gateway.verify_audit_events()] == ["denied"]
    assert not gateway.transaction_path.exists()


def test_recovery_uses_original_prepared_time_only_when_grant_was_valid_then(tmp_path, monkeypatch) -> None:
    gateway = EvidenceIntakeGateway(tmp_path)
    envelope = _capture_envelope()
    grant = _grant(expires_at="2026-07-19T12:01:00Z")

    def fail_audit(*_args, **_kwargs) -> None:
        raise OSError("simulated interruption")

    monkeypatch.setattr(gateway, "_append_accepted_event", fail_audit)
    assert gateway.accept(envelope, grant, now=NOW).reason_code == "intake_recovery_required"

    recovered = EvidenceIntakeGateway(tmp_path).accept(envelope, grant, now="2026-07-19T12:02:00Z")

    assert recovered.allowed is True
    event = EvidenceIntakeGateway(tmp_path).verify_audit_events()[0]
    assert event.occurred_at == NOW
    assert EvidenceIntakeGateway(tmp_path).preflight(
        _capture_envelope(capture_id="capture-after-expiry"), grant, now="2026-07-19T12:02:00Z"
    ).reason_code == "grant_expired"


def test_default_audit_verification_rejects_a_prepared_transaction_until_recovery(tmp_path, monkeypatch) -> None:
    gateway = EvidenceIntakeGateway(tmp_path)

    def fail_ledger(*_args, **_kwargs):
        raise OSError("simulated interrupted append")

    monkeypatch.setattr(gateway._accepted_ledger, "append", fail_ledger)
    assert gateway.accept(_capture_envelope(), _grant(), now=NOW).reason_code == "intake_recovery_required"

    try:
        gateway.verify_audit_events()
    except ValueError as error:
        assert "transaction" in str(error)
    else:
        raise AssertionError("ordinary audit verification must require pending-transaction recovery")


def test_accept_denials_are_redacted_audit_events_without_evidence_or_budget_consumption(tmp_path) -> None:
    gateway = EvidenceIntakeGateway(tmp_path)
    raw_invalid = _capture_envelope()
    raw_invalid["candidate"]["output"]["titles"] = ["C:/private/video.mp4"]  # type: ignore[index]
    decisions = [
        gateway.accept(_capture_envelope(), _grant(expires_at="2026-07-19T11:59:59Z"), now=NOW),
        gateway.accept(_capture_envelope(), _grant(max_token_total=33), now=NOW),
        gateway.accept(raw_invalid, {"approval": "yes"}, now=NOW),
    ]

    assert [decision.reason_code for decision in decisions] == ["grant_expired", "budget_token_limit", "capture_invalid"]
    assert gateway.verify_accepted_evidence() == ()
    events = gateway.verify_audit_events()
    assert [event.outcome for event in events] == ["denied", "denied", "denied"]
    assert all(event.non_authorizing_state == "offline_evidence_only" for event in events)
    raw_audit = gateway.audit_path.read_text(encoding="utf-8")
    assert "C:/private/video.mp4" not in raw_audit
    assert "approval" not in raw_audit

    tampered = json.loads(raw_audit)
    tampered["events"][0]["reason_code"] = "forged"
    gateway.audit_path.write_text(json.dumps(tampered, ensure_ascii=False), encoding="utf-8")
    try:
        gateway.verify_audit_events()
    except ValueError as error:
        assert "hash" in str(error)
    else:
        raise AssertionError("denied audit event tampering must be rejected")


def test_stale_lock_artifact_does_not_wedge_prepared_transaction_recovery(tmp_path, monkeypatch) -> None:
    gateway = EvidenceIntakeGateway(tmp_path)

    def fail_ledger(*_args, **_kwargs):
        raise OSError("interrupted")

    monkeypatch.setattr(gateway._accepted_ledger, "append", fail_ledger)
    assert gateway.accept(_capture_envelope(), _grant(), now=NOW).reason_code == "intake_recovery_required"
    gateway.lock_path.write_text('{"stale":"artifact"}', encoding="utf-8")

    recovered = EvidenceIntakeGateway(tmp_path).accept(_capture_envelope(), _grant(), now=NOW)

    assert recovered.allowed is True
    assert [event.outcome for event in EvidenceIntakeGateway(tmp_path).verify_audit_events()] == ["denied", "accepted"]


def test_concurrent_invalid_accepts_serialize_every_denied_audit_event(tmp_path) -> None:
    start = Event()

    def deny_once() -> str:
        start.wait()
        decision = EvidenceIntakeGateway(tmp_path).accept({"not": "a capture"}, {"approval": "yes"}, now=NOW)
        return decision.reason_code

    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [executor.submit(deny_once) for _ in range(32)]
        start.set()
        reasons = [future.result() for future in futures]

    assert reasons == ["capture_invalid"] * 32
    gateway = EvidenceIntakeGateway(tmp_path)
    assert gateway.verify_accepted_evidence() == ()
    assert [event.outcome for event in gateway.verify_audit_events()] == ["denied"] * 32


def test_lock_unavailable_fails_closed_without_an_unaudited_write(tmp_path, monkeypatch) -> None:
    gateway = EvidenceIntakeGateway(tmp_path)

    @contextmanager
    def unavailable_lock():
        raise OSError("simulated lock I/O failure")
        yield

    monkeypatch.setattr(gateway, "_write_lock", unavailable_lock)
    decision = gateway.accept({"not": "a capture"}, {"approval": "yes"}, now=NOW)

    assert decision.reason_code == "intake_lock_unavailable"
    assert gateway.verify_accepted_evidence() == ()
    assert gateway.verify_audit_events() == ()


def test_parent_generic_ledger_cannot_bypass_or_poison_isolated_intake_sink(tmp_path) -> None:
    envelope = _capture_envelope()
    generic_parent_ledger = ProviderQualificationEvidenceLedger(tmp_path)
    generic_parent_ledger.append(import_synthetic_provider_capture(envelope))
    gateway = EvidenceIntakeGateway(tmp_path)

    assert gateway.preflight(envelope, _grant(), now=NOW).allowed is True
    accepted = gateway.accept(envelope, _grant(), now=NOW)

    assert accepted.allowed is True
    assert len(generic_parent_ledger.verify_records()) == 1
    assert len(gateway.verify_accepted_evidence()) == 1
    assert [event.outcome for event in gateway.verify_audit_events()] == ["accepted"]


def test_ordinary_caller_cannot_mutate_gateway_accepted_sink_under_app_contract(tmp_path) -> None:
    gateway = EvidenceIntakeGateway(tmp_path)
    capture = import_synthetic_provider_capture(_capture_envelope())

    assert not hasattr(gateway, "ledger")
    with pytest.raises(ValueError, match="intake sink"):
        ProviderQualificationEvidenceLedger(gateway.accepted_evidence_path).append(capture)

    assert gateway.accept(_capture_envelope(), _grant(), now=NOW).allowed is True
    assert len(EvidenceIntakeGateway(tmp_path).verify_accepted_evidence()) == 1
