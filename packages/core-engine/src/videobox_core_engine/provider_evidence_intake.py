"""Offline-only synthetic evidence intake with recoverable dual-file persistence.

This is a contract-test foundation, never real identity/authentication, OAuth,
provider routing, or consent issuance.  It accepts already-sanitized synthetic
fixtures only and records non-authorizing evidence.  The prepared transaction
journal lets a retry reconcile an interrupted ledger/audit pair; its hashes are
tamper-evident at the application level, not OS-immutable or adversary-proof.
Owner/grant reference hashes are redacted correlation values, not keyed or
confidentiality-preserving identifiers; the offline fixture contract must not
be used to store sensitive source references.

The gateway keeps accepted intake evidence in a private sink directory beneath
its root.  A generic ``ProviderQualificationEvidenceLedger(root)`` remains
pre-gate/offline test evidence only; it is deliberately not an intake sink and
cannot constitute owner-granted acceptance.  In the normal writable path both
accepted and denied accepts are audited.  If the audit or its lock is
unavailable, the gateway returns a non-authorizing fail-closed decision and no
audit record can truthfully be claimed.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from json import JSONDecodeError, dumps, loads
from math import isfinite
from pathlib import Path
import os
import re
import time
from typing import Any, Literal, Mapping
from uuid import uuid4

try:  # Windows desktop runtime; advisory lock is released automatically on crash.
    import msvcrt
except ImportError:  # Linux verification containers.
    import fcntl

from videobox_core_engine.evaluation_fixture_versions import KOREAN_SHADOW_EVALUATION_V1_CANONICAL_SHA256
from videobox_core_engine.provider_qualification_evidence import (
    PersistedProviderEvidence,
    ProviderEvidenceCapture,
    ProviderQualificationEvidenceLedger,
    _create_intake_sink_writer,
    import_synthetic_provider_capture,
)


INTAKE_AUDIT_VERSION = "videobox-provider-evidence-intake-audit-v1"
INTAKE_EVENT_VERSION = "videobox-provider-evidence-intake-event-v1"
INTAKE_TRANSACTION_VERSION = "videobox-provider-evidence-intake-transaction-v1"
OFFLINE_SYNTHETIC_SCOPE = "offline_synthetic_evidence_import"
OFFLINE_ONLY_STATE = "offline_evidence_only"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class _IntakeLockUnavailable(Exception):
    pass


@dataclass(frozen=True, slots=True)
class OwnerEvidenceImportGrant:
    """Offline test grant form, not an identity or consent credential."""

    owner_ref: str
    grant_id: str
    corpus_canonical_sha256: str
    provider: str
    runtime: str
    scope: str
    expires_at: str
    max_capture_count: int
    max_token_total: int
    max_latency_total_ms: int | float

    def __post_init__(self) -> None:
        if not all(isinstance(value, str) and _OPAQUE_ID.fullmatch(value) for value in (
            self.owner_ref, self.grant_id, self.provider, self.runtime
        )):
            raise ValueError("grant opaque identifiers must be non-empty safe identifiers")
        if not isinstance(self.corpus_canonical_sha256, str) or _SHA256.fullmatch(self.corpus_canonical_sha256) is None:
            raise ValueError("grant corpus digest must be a SHA-256 hex digest")
        if self.scope != OFFLINE_SYNTHETIC_SCOPE:
            raise ValueError("grant scope must be offline synthetic evidence import")
        _parse_utc_timestamp(self.expires_at)
        if not isinstance(self.max_capture_count, int) or isinstance(self.max_capture_count, bool) or self.max_capture_count < 0:
            raise ValueError("grant capture budget must be a non-negative integer")
        if not isinstance(self.max_token_total, int) or isinstance(self.max_token_total, bool) or self.max_token_total < 0:
            raise ValueError("grant token budget must be a non-negative integer")
        if isinstance(self.max_latency_total_ms, bool) or not isinstance(self.max_latency_total_ms, (int, float)):
            raise ValueError("grant latency budget must be a non-negative finite number")
        if not isfinite(float(self.max_latency_total_ms)) or self.max_latency_total_ms < 0:
            raise ValueError("grant latency budget must be a non-negative finite number")

    @property
    def grant_sha256(self) -> str:
        return _canonical_sha256({
            "owner_ref": self.owner_ref, "grant_id": self.grant_id,
            "corpus_canonical_sha256": self.corpus_canonical_sha256,
            "provider": self.provider, "runtime": self.runtime, "scope": self.scope,
            "expires_at": self.expires_at, "max_capture_count": self.max_capture_count,
            "max_token_total": self.max_token_total, "max_latency_total_ms": self.max_latency_total_ms,
        })


@dataclass(frozen=True, slots=True)
class EvidenceIntakeDecision:
    """A local persistence decision; never authorization to call a provider."""

    allowed: bool
    reason_code: str
    non_authorizing_state: Literal["offline_evidence_only"] = OFFLINE_ONLY_STATE
    evidence_record_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class IntakeAuditEvent:
    """Redacted accepted event; refs are unkeyed correlation hashes, not source text."""

    event_id: str
    occurred_at: str
    outcome: Literal["accepted", "denied"]
    reason_code: str
    non_authorizing_state: Literal["offline_evidence_only"]
    owner_ref_sha256: str | None
    grant_id_sha256: str | None
    grant_sha256: str | None
    capture_id: str | None
    capture_payload_sha256: str | None
    evidence_record_sha256: str | None
    token_total: int | None
    latency_total_ms: float | None
    event_sha256: str


class EvidenceIntakeGateway:
    """Offline synthetic-only intake gate with one recoverable pending transaction."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise ValueError("evidence intake root must be a Path")
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.root.is_dir():
            raise ValueError("evidence intake root must be a directory")
        self._accepted_evidence_path = root / "accepted_intake_evidence"
        self._accepted_ledger = ProviderQualificationEvidenceLedger(
            self._accepted_evidence_path,
            _intake_writer=_create_intake_sink_writer(self._accepted_evidence_path),
        )

    @property
    def accepted_evidence_path(self) -> Path:
        """Read-only location hint; its writer remains private to this gateway."""
        return self._accepted_evidence_path

    def verify_accepted_evidence(self) -> tuple[PersistedProviderEvidence, ...]:
        """Read verified accepted evidence without exposing its mutation capability."""
        return self._accepted_ledger.verify_records()

    @property
    def audit_path(self) -> Path:
        return self.root / "provider_evidence_intake_audit.v1.json"

    @property
    def transaction_path(self) -> Path:
        return self.root / "provider_evidence_intake_pending.v1.json"

    @property
    def lock_path(self) -> Path:
        return self.root / ".provider_evidence_intake.lock"

    def preflight(self, envelope: Mapping[str, Any], grant: object, *, now: str) -> EvidenceIntakeDecision:
        """Return an allow/deny decision without writing or consuming anything."""
        try:
            current_time = _parse_utc_timestamp(now)
        except ValueError:
            return _deny("time_invalid")
        try:
            capture = import_synthetic_provider_capture(envelope)
        except (TypeError, ValueError):
            return _deny("capture_invalid")
        if not _audit_safe_capture(capture):
            return _deny("capture_identity_invalid")
        try:
            if self._read_transaction() is not None:
                return _deny("intake_recovery_required")
        except ValueError:
            return _deny("intake_state_invalid")
        return self._preflight_capture(capture, grant, current_time)

    def accept(self, envelope: Mapping[str, Any], grant: object, *, now: str) -> EvidenceIntakeDecision:
        """Re-preflight under lock; interrupted writes leave a recoverable journal for retry reconciliation."""
        try:
            current_time = _parse_utc_timestamp(now)
        except ValueError:
            return self._deny_with_audit("time_invalid", now=now, grant=grant, capture=None)
        try:
            capture = import_synthetic_provider_capture(envelope)
        except (TypeError, ValueError):
            return self._deny_with_audit("capture_invalid", now=now, grant=grant, capture=None)
        if not _audit_safe_capture(capture):
            return self._deny_with_audit("capture_identity_invalid", now=now, grant=grant, capture=capture)
        try:
            with self._write_lock():
                try:
                    transaction = self._read_transaction()
                except ValueError:
                    return self._deny_with_audit("intake_state_invalid", now=now, grant=grant, capture=capture, locked=True)
                if transaction is not None:
                    decision = self._resume_transaction(transaction, capture, grant)
                    return self._audit_denial_if_needed(decision, now=now, grant=grant, capture=capture, locked=True)
                decision = self._preflight_capture(capture, grant, current_time)
                if not decision.allowed:
                    return self._audit_denial_if_needed(decision, now=now, grant=grant, capture=capture, locked=True)
                assert isinstance(grant, OwnerEvidenceImportGrant)
                try:
                    self._write_transaction(_prepared_transaction(capture, grant, now))
                except OSError:
                    return self._deny_with_audit("intake_recovery_required", now=now, grant=grant, capture=capture, locked=True)
                decision = self._resume_transaction(self._read_transaction(), capture, grant)
                return self._audit_denial_if_needed(decision, now=now, grant=grant, capture=capture, locked=True)
        except (_IntakeLockUnavailable, OSError):
            return _deny("intake_lock_unavailable")

    def verify_audit_events(self, *, allow_pending: bool = False) -> tuple[IntakeAuditEvent, ...]:
        """Verify audit hashes plus strict one-to-one binding to ledger records."""
        transaction = self._read_transaction()
        if transaction is not None and not allow_pending:
            raise ValueError("evidence intake audit verification requires pending transaction recovery")
        raw = self._read_raw_audit()
        events = raw["events"]
        if not isinstance(events, list):
            raise ValueError("evidence intake audit events must be an array")
        records = self._accepted_ledger.verify_records()
        evidence_by_hash = {record.record_sha256: record for record in records}
        previous_event_sha256: str | None = None
        verified: list[IntakeAuditEvent] = []
        seen_event_ids: set[str] = set()
        seen_capture_ids: set[str] = set()
        seen_record_hashes: set[str] = set()
        for value in events:
            event = _verify_event(value, previous_event_sha256)
            if event.event_id in seen_event_ids:
                raise ValueError("evidence intake audit has a duplicate event or evidence binding")
            if event.outcome == "accepted":
                assert event.capture_id is not None and event.evidence_record_sha256 is not None
                if event.capture_id in seen_capture_ids or event.evidence_record_sha256 in seen_record_hashes:
                    raise ValueError("evidence intake audit has a duplicate event or evidence binding")
                try:
                    persisted = evidence_by_hash[event.evidence_record_sha256]
                except KeyError as error:
                    raise ValueError("evidence intake audit references an unknown evidence record") from error
                if persisted.capture.capture_id != event.capture_id or persisted.capture.payload_sha256 != event.capture_payload_sha256:
                    raise ValueError("evidence intake audit capture binding does not match")
                if event.token_total != persisted.capture.candidate.token_count or event.latency_total_ms != float(persisted.capture.candidate.latency_ms):
                    raise ValueError("evidence intake audit usage aggregate does not match evidence")
                seen_capture_ids.add(event.capture_id)
                seen_record_hashes.add(event.evidence_record_sha256)
            seen_event_ids.add(event.event_id)
            previous_event_sha256 = event.event_sha256
            verified.append(event)
        expected_hashes = set(evidence_by_hash)
        if allow_pending:
            if transaction is not None:
                pending_hash = _pending_record_hash(transaction, records)
                if pending_hash is not None and pending_hash not in seen_record_hashes:
                    expected_hashes.discard(pending_hash)
        if seen_record_hashes != expected_hashes:
            raise ValueError("evidence intake ledger and audit must have one-to-one bindings")
        return tuple(verified)

    def _resume_transaction(
        self, transaction: Mapping[str, Any] | None, capture: ProviderEvidenceCapture, grant: object
    ) -> EvidenceIntakeDecision:
        if transaction is None or not isinstance(grant, OwnerEvidenceImportGrant):
            return _deny("intake_recovery_required")
        if not self._grant_is_current_synthetic_only(grant) or not _transaction_matches(transaction, capture, grant):
            return _deny("intake_recovery_required")
        # A retry is reconciliation of the original offline acceptance, never a
        # silent new acceptance after expiry. Its grant must have been valid at
        # the prepared UTC time, and its audit retains that original time.
        if _parse_utc_timestamp(grant.expires_at) <= _parse_utc_timestamp(transaction["occurred_at"]):
            return _deny("intake_state_invalid")
        try:
            records = self._accepted_ledger.verify_records()
            existing = [record for record in records if record.capture.capture_id == capture.capture_id]
        except ValueError:
            return _deny("intake_state_invalid")
        if len(existing) > 1:
            return _deny("intake_state_invalid")
        persisted: PersistedProviderEvidence
        if existing:
            persisted = existing[0]
            if persisted.capture.payload_sha256 != capture.payload_sha256:
                return _deny("intake_state_invalid")
        else:
            try:
                persisted = self._accepted_ledger.append(capture)
            except (OSError, ValueError):
                return _deny("intake_recovery_required")
        transaction = _evidence_appended_transaction(transaction, persisted.record_sha256)
        try:
            self._write_transaction(transaction)
            events = self.verify_audit_events(allow_pending=True)
        except (OSError, ValueError):
            return _deny("intake_recovery_required")
        matching = [event for event in events if event.evidence_record_sha256 == persisted.record_sha256]
        if matching:
            if len(matching) != 1:
                return _deny("intake_state_invalid")
        else:
            try:
                self._append_accepted_event(capture, grant, persisted, transaction["occurred_at"])
            except (OSError, ValueError):
                return _deny("intake_recovery_required")
        try:
            # Final verification makes success mean both files are durable and bound.
            self.verify_audit_events(allow_pending=True)
            self.transaction_path.unlink()
            self.verify_audit_events()
        except (OSError, ValueError):
            return _deny("intake_recovery_required")
        return EvidenceIntakeDecision(True, "allowed_offline_synthetic_evidence_only", evidence_record_sha256=persisted.record_sha256)

    def _preflight_capture(self, capture: ProviderEvidenceCapture, grant: object, current_time: datetime) -> EvidenceIntakeDecision:
        if not _audit_safe_capture(capture):
            return _deny("capture_identity_invalid")
        if not isinstance(grant, OwnerEvidenceImportGrant) or not self._grant_is_current_synthetic_only(grant):
            return _deny("grant_invalid")
        if _parse_utc_timestamp(grant.expires_at) <= current_time:
            return _deny("grant_expired")
        if capture.candidate.runtime != "synthetic_fixture" or not capture.candidate.provider.startswith("synthetic_"):
            return _deny("synthetic_only")
        if (capture.corpus_canonical_sha256 != grant.corpus_canonical_sha256 or capture.candidate.provider != grant.provider or capture.candidate.runtime != grant.runtime):
            return _deny("grant_binding_mismatch")
        try:
            records = self._accepted_ledger.verify_records()
            events = self.verify_audit_events()
        except ValueError:
            return _deny("intake_state_invalid")
        if any(record.capture.capture_id == capture.capture_id for record in records):
            return _deny("capture_replay")
        owner_hash = _ref_sha256(grant.owner_ref)
        grant_id_hash = _ref_sha256(grant.grant_id)
        same_grant = [event for event in events if event.outcome == "accepted" and event.grant_id_sha256 == grant_id_hash]
        if any(event.grant_sha256 != grant.grant_sha256 or event.owner_ref_sha256 != owner_hash for event in same_grant):
            return _deny("grant_replay")
        if len(same_grant) + 1 > grant.max_capture_count:
            return _deny("budget_capture_limit")
        if sum(event.token_total for event in same_grant) + capture.candidate.token_count > grant.max_token_total:
            return _deny("budget_token_limit")
        if sum(event.latency_total_ms for event in same_grant) + float(capture.candidate.latency_ms) > float(grant.max_latency_total_ms):
            return _deny("budget_latency_limit")
        return EvidenceIntakeDecision(True, "allowed_offline_synthetic_evidence_only")

    @staticmethod
    def _grant_is_current_synthetic_only(grant: OwnerEvidenceImportGrant) -> bool:
        return (
            grant.scope == OFFLINE_SYNTHETIC_SCOPE
            and grant.corpus_canonical_sha256 == KOREAN_SHADOW_EVALUATION_V1_CANONICAL_SHA256
            and grant.runtime == "synthetic_fixture" and grant.provider.startswith("synthetic_")
        )

    def _append_accepted_event(self, capture: ProviderEvidenceCapture, grant: OwnerEvidenceImportGrant,
                               persisted: PersistedProviderEvidence, occurred_at: str) -> None:
        raw = self._read_raw_audit()
        events = list(raw["events"])
        previous_event_sha256 = events[-1]["event_sha256"] if events else None
        payload = {
            "event_version": INTAKE_EVENT_VERSION, "event_id": f"intake-{uuid4().hex}", "occurred_at": occurred_at,
            "outcome": "accepted", "reason_code": "allowed_offline_synthetic_evidence_only",
            "non_authorizing_state": OFFLINE_ONLY_STATE, "owner_ref_sha256": _ref_sha256(grant.owner_ref),
            "grant_id_sha256": _ref_sha256(grant.grant_id), "grant_sha256": grant.grant_sha256,
            "capture_id": capture.capture_id, "capture_payload_sha256": capture.payload_sha256,
            "evidence_record_sha256": persisted.record_sha256,
            "usage_delta": {"capture_count": 1, "token_total": capture.candidate.token_count, "latency_total_ms": capture.candidate.latency_ms},
            "previous_event_sha256": previous_event_sha256,
        }
        events.append({**payload, "event_sha256": _canonical_sha256(payload)})
        _atomic_write_json(self.audit_path, {"audit_version": INTAKE_AUDIT_VERSION, "events": events})

    def _audit_denial_if_needed(self, decision: EvidenceIntakeDecision, *, now: str, grant: object,
                                capture: ProviderEvidenceCapture | None, locked: bool = False) -> EvidenceIntakeDecision:
        if decision.allowed:
            return decision
        return self._deny_with_audit(decision.reason_code, now=now, grant=grant, capture=capture, locked=locked)

    def _deny_with_audit(self, reason_code: str, *, now: str, grant: object,
                         capture: ProviderEvidenceCapture | None, locked: bool = False) -> EvidenceIntakeDecision:
        """Persist a redacted accept-denial event; failure remains a fail-closed denial."""
        if not locked:
            try:
                with self._write_lock():
                    return self._deny_with_audit(reason_code, now=now, grant=grant, capture=capture, locked=True)
            except (_IntakeLockUnavailable, OSError):
                # The audit lock itself is unavailable, so fail closed without an unaudited write.
                return _deny("intake_lock_unavailable")
        occurred_at = now if _is_utc_timestamp(now) else datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        try:
            raw = self._read_raw_audit()
            events = list(raw["events"])
            previous_event_sha256 = events[-1]["event_sha256"] if events else None
            payload = {
                "event_version": INTAKE_EVENT_VERSION, "event_id": f"intake-{uuid4().hex}", "occurred_at": occurred_at,
                "outcome": "denied", "reason_code": reason_code, "non_authorizing_state": OFFLINE_ONLY_STATE,
                "owner_ref_sha256": _ref_sha256(grant.owner_ref) if isinstance(grant, OwnerEvidenceImportGrant) else None,
                "grant_id_sha256": _ref_sha256(grant.grant_id) if isinstance(grant, OwnerEvidenceImportGrant) else None,
                "grant_sha256": grant.grant_sha256 if isinstance(grant, OwnerEvidenceImportGrant) else None,
                "capture_id": capture.capture_id if capture is not None and _audit_safe_capture(capture) else None,
                "capture_payload_sha256": capture.payload_sha256 if capture is not None and _audit_safe_capture(capture) else None,
                "evidence_record_sha256": None, "usage_delta": None, "previous_event_sha256": previous_event_sha256,
            }
            events.append({**payload, "event_sha256": _canonical_sha256(payload)})
            _atomic_write_json(self.audit_path, {"audit_version": INTAKE_AUDIT_VERSION, "events": events})
        except (OSError, ValueError):
            return _deny("intake_audit_unavailable")
        return _deny(reason_code)

    def _read_raw_audit(self) -> Mapping[str, Any]:
        if not self.audit_path.exists():
            return {"audit_version": INTAKE_AUDIT_VERSION, "events": []}
        try:
            raw = loads(self.audit_path.read_text(encoding="utf-8"))
        except (OSError, JSONDecodeError) as error:
            raise ValueError("evidence intake audit cannot be read") from error
        if not isinstance(raw, Mapping) or set(raw) != {"audit_version", "events"} or raw["audit_version"] != INTAKE_AUDIT_VERSION:
            raise ValueError("evidence intake audit has an invalid shape or version")
        return raw

    def _read_transaction(self) -> Mapping[str, Any] | None:
        if not self.transaction_path.exists():
            return None
        try:
            raw = loads(self.transaction_path.read_text(encoding="utf-8"))
        except (OSError, JSONDecodeError) as error:
            raise ValueError("evidence intake transaction cannot be read") from error
        return _verify_transaction(raw)

    def _write_transaction(self, transaction: Mapping[str, Any]) -> None:
        _atomic_write_json(self.transaction_path, transaction)

    @contextmanager
    def _write_lock(self):
        """Use an OS-held advisory lock; a leftover artifact is never a stale wedge."""
        deadline = time.monotonic() + 15
        fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        acquired = False
        while True:
            try:
                _try_lock_file(fd)
                acquired = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise _IntakeLockUnavailable("evidence intake write lock timed out")
                time.sleep(0.01)
        try:
            os.ftruncate(fd, 0)
            os.write(fd, _canonical_json({"owner_nonce": uuid4().hex, "lease_expires_at": time.time() + 30}).encode("utf-8"))
            yield
        finally:
            if acquired:
                _unlock_file(fd)
            os.close(fd)


def _deny(reason_code: str) -> EvidenceIntakeDecision:
    return EvidenceIntakeDecision(False, reason_code)


def _ref_sha256(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _audit_safe_capture(capture: ProviderEvidenceCapture) -> bool:
    """The importer permits broader fixture IDs; durable audit identity does not."""
    return _OPAQUE_ID.fullmatch(capture.capture_id) is not None


def _prepared_transaction(capture: ProviderEvidenceCapture, grant: OwnerEvidenceImportGrant, occurred_at: str) -> Mapping[str, Any]:
    payload = {
        "transaction_version": INTAKE_TRANSACTION_VERSION, "phase": "prepared", "occurred_at": occurred_at,
        "capture_id": capture.capture_id, "capture_payload_sha256": capture.payload_sha256,
        "owner_ref_sha256": _ref_sha256(grant.owner_ref), "grant_id_sha256": _ref_sha256(grant.grant_id),
        "grant_sha256": grant.grant_sha256, "evidence_record_sha256": None,
    }
    return {**payload, "transaction_sha256": _canonical_sha256(payload)}


def _evidence_appended_transaction(transaction: Mapping[str, Any], record_sha256: str) -> Mapping[str, Any]:
    payload = {key: transaction[key] for key in (
        "transaction_version", "occurred_at", "capture_id", "capture_payload_sha256", "owner_ref_sha256", "grant_id_sha256", "grant_sha256"
    )}
    payload.update({"phase": "evidence_appended", "evidence_record_sha256": record_sha256})
    return {**payload, "transaction_sha256": _canonical_sha256(payload)}


def _verify_transaction(value: Any) -> Mapping[str, Any]:
    expected = {
        "transaction_version", "phase", "occurred_at", "capture_id", "capture_payload_sha256", "owner_ref_sha256",
        "grant_id_sha256", "grant_sha256", "evidence_record_sha256", "transaction_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != expected or value["transaction_version"] != INTAKE_TRANSACTION_VERSION:
        raise ValueError("evidence intake transaction has an invalid shape or version")
    if value["phase"] not in {"prepared", "evidence_appended"}:
        raise ValueError("evidence intake transaction phase is invalid")
    if value["phase"] == "prepared" and value["evidence_record_sha256"] is not None:
        raise ValueError("prepared intake transaction cannot bind evidence")
    if value["phase"] == "evidence_appended" and (not isinstance(value["evidence_record_sha256"], str) or _SHA256.fullmatch(value["evidence_record_sha256"]) is None):
        raise ValueError("evidence-appended transaction requires an evidence digest")
    for name in ("capture_id",):
        if not isinstance(value[name], str) or _OPAQUE_ID.fullmatch(value[name]) is None:
            raise ValueError("evidence intake transaction identifier is invalid")
    for name in ("capture_payload_sha256", "owner_ref_sha256", "grant_id_sha256", "grant_sha256", "transaction_sha256"):
        if not isinstance(value[name], str) or _SHA256.fullmatch(value[name]) is None:
            raise ValueError("evidence intake transaction digest is invalid")
    _parse_utc_timestamp(value["occurred_at"])
    payload = {key: value[key] for key in value if key != "transaction_sha256"}
    if _canonical_sha256(payload) != value["transaction_sha256"]:
        raise ValueError("evidence intake transaction hash does not match")
    return value


def _transaction_matches(transaction: Mapping[str, Any], capture: ProviderEvidenceCapture, grant: OwnerEvidenceImportGrant) -> bool:
    return (
        transaction["capture_id"] == capture.capture_id and transaction["capture_payload_sha256"] == capture.payload_sha256
        and transaction["owner_ref_sha256"] == _ref_sha256(grant.owner_ref)
        and transaction["grant_id_sha256"] == _ref_sha256(grant.grant_id) and transaction["grant_sha256"] == grant.grant_sha256
    )


def _pending_record_hash(transaction: Mapping[str, Any], records: tuple[PersistedProviderEvidence, ...]) -> str | None:
    if transaction["phase"] == "evidence_appended":
        return transaction["evidence_record_sha256"]
    matching = [record.record_sha256 for record in records if record.capture.capture_id == transaction["capture_id"] and record.capture.payload_sha256 == transaction["capture_payload_sha256"]]
    return matching[0] if len(matching) == 1 else None


def _verify_event(value: Any, previous_event_sha256: str | None) -> IntakeAuditEvent:
    expected = {
        "event_version", "event_id", "occurred_at", "outcome", "reason_code", "non_authorizing_state", "owner_ref_sha256",
        "grant_id_sha256", "grant_sha256", "capture_id", "capture_payload_sha256", "evidence_record_sha256", "usage_delta",
        "previous_event_sha256", "event_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != expected or value["event_version"] != INTAKE_EVENT_VERSION:
        raise ValueError("evidence intake audit event has an invalid shape or version")
    if value["previous_event_sha256"] != previous_event_sha256:
        raise ValueError("evidence intake audit event hash chain order does not match")
    event_sha256 = value["event_sha256"]
    if not isinstance(event_sha256, str) or _SHA256.fullmatch(event_sha256) is None:
        raise ValueError("evidence intake audit event has an invalid hash")
    payload = {key: value[key] for key in value if key != "event_sha256"}
    if _canonical_sha256(payload) != event_sha256:
        raise ValueError("evidence intake audit event hash does not match")
    if value["outcome"] not in {"accepted", "denied"} or not isinstance(value["reason_code"], str) or not value["reason_code"] or value["non_authorizing_state"] != OFFLINE_ONLY_STATE:
        raise ValueError("evidence intake audit event is not non-authorizing")
    if not isinstance(value["event_id"], str) or _OPAQUE_ID.fullmatch(value["event_id"]) is None:
        raise ValueError("evidence intake audit event identifier is invalid")
    if value["outcome"] == "denied":
        if value["evidence_record_sha256"] is not None or value["usage_delta"] is not None:
            raise ValueError("denied intake audit event cannot bind evidence or consume budget")
        for name in ("owner_ref_sha256", "grant_id_sha256", "grant_sha256", "capture_id", "capture_payload_sha256"):
            if value[name] is not None and (not isinstance(value[name], str) or (_SHA256.fullmatch(value[name]) is None if name != "capture_id" else _OPAQUE_ID.fullmatch(value[name]) is None)):
                raise ValueError("denied intake audit event has an invalid redacted reference")
        _parse_utc_timestamp(value["occurred_at"])
        return IntakeAuditEvent(
            event_id=value["event_id"], occurred_at=value["occurred_at"], outcome="denied", reason_code=value["reason_code"],
            non_authorizing_state=value["non_authorizing_state"], owner_ref_sha256=value["owner_ref_sha256"],
            grant_id_sha256=value["grant_id_sha256"], grant_sha256=value["grant_sha256"], capture_id=value["capture_id"],
            capture_payload_sha256=value["capture_payload_sha256"], evidence_record_sha256=None,
            token_total=None, latency_total_ms=None, event_sha256=event_sha256,
        )
    if value["reason_code"] != "allowed_offline_synthetic_evidence_only":
        raise ValueError("accepted intake audit event reason is invalid")
    for name in ("event_id", "capture_id"):
        if not isinstance(value[name], str) or _OPAQUE_ID.fullmatch(value[name]) is None:
            raise ValueError("evidence intake audit event identifier is invalid")
    for name in ("owner_ref_sha256", "grant_id_sha256", "grant_sha256", "capture_payload_sha256", "evidence_record_sha256"):
        if not isinstance(value[name], str) or _SHA256.fullmatch(value[name]) is None:
            raise ValueError("evidence intake audit event digest is invalid")
    _parse_utc_timestamp(value["occurred_at"])
    usage = _usage_delta(value)
    return IntakeAuditEvent(
        event_id=value["event_id"], occurred_at=value["occurred_at"], outcome=value["outcome"], reason_code=value["reason_code"],
        non_authorizing_state=value["non_authorizing_state"], owner_ref_sha256=value["owner_ref_sha256"],
        grant_id_sha256=value["grant_id_sha256"], grant_sha256=value["grant_sha256"], capture_id=value["capture_id"],
        capture_payload_sha256=value["capture_payload_sha256"], evidence_record_sha256=value["evidence_record_sha256"],
        token_total=usage["token_total"], latency_total_ms=usage["latency_total_ms"], event_sha256=event_sha256,
    )


def _usage_delta(value: Mapping[str, Any]) -> Mapping[str, int | float]:
    usage = value.get("usage_delta")
    if not isinstance(usage, Mapping) or set(usage) != {"capture_count", "token_total", "latency_total_ms"}:
        raise ValueError("evidence intake audit usage aggregate is invalid")
    if not isinstance(usage["capture_count"], int) or isinstance(usage["capture_count"], bool) or usage["capture_count"] != 1:
        raise ValueError("evidence intake audit capture aggregate is invalid")
    if not isinstance(usage["token_total"], int) or isinstance(usage["token_total"], bool) or usage["token_total"] < 0:
        raise ValueError("evidence intake audit token aggregate is invalid")
    latency = usage["latency_total_ms"]
    if isinstance(latency, bool) or not isinstance(latency, (int, float)) or not isfinite(float(latency)) or latency < 0:
        raise ValueError("evidence intake audit latency aggregate is invalid")
    return {"token_total": usage["token_total"], "latency_total_ms": float(latency)}


def _parse_utc_timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must be an explicit UTC Z timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("timestamp must be ISO-8601 UTC") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("timestamp must be UTC")
    return parsed


def _is_utc_timestamp(value: str) -> bool:
    try:
        _parse_utc_timestamp(value)
    except ValueError:
        return False
    return True


def _canonical_json(value: Any) -> str:
    try:
        return dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("evidence intake value must be JSON-compatible") from error


def _canonical_sha256(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary_path = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        temporary_path.write_text(_canonical_json(value), encoding="utf-8")
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _try_lock_file(fd: int) -> None:
    os.lseek(fd, 0, os.SEEK_SET)
    if "msvcrt" in globals():
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise BlockingIOError from error
    else:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise


def _unlock_file(fd: int) -> None:
    os.lseek(fd, 0, os.SEEK_SET)
    if "msvcrt" in globals():
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
