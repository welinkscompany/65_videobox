"""Offline, tamper-evident provider-capture evidence persistence.

This module deliberately has no provider client, router, database, or activation
surface.  Its JSON files are append-only at the application contract level and
detect accidental or ordinary content tampering through canonical digests and a
hash chain.  They are not OS-immutable or adversary-proof: a signing key or an
external anchor is intentionally outside this offline foundation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from json import JSONDecodeError, dumps, loads
from math import isfinite
from pathlib import Path
import os
import re
import time
from typing import Any, Literal
from uuid import uuid4

from videobox_core_engine.agent_quality_harness import (
    CandidateResult,
    EvaluationMeasurement,
    FrozenEvaluationCase,
    FrozenKoreanEvaluationCorpus,
    QualificationReport,
    build_qualification_report,
    load_checked_in_korean_evaluation_corpus,
)
from videobox_core_engine.evaluation_fixture_versions import KOREAN_SHADOW_EVALUATION_V1_CANONICAL_SHA256


CAPTURE_VERSION = "videobox-provider-capture-v1"
LEDGER_VERSION = "videobox-provider-evidence-ledger-v1"
RECORD_VERSION = "videobox-provider-evidence-record-v1"
AUDIT_ARTIFACT_VERSION = "videobox-provider-qualification-audit-v1"
_INTAKE_SINK_MARKER_NAME = ".videobox-intake-sink-v1"


@dataclass(frozen=True, slots=True)
class _IntakeSinkWriterCapability:
    """Private in-process capability, not a boundary against hostile code."""

    root: Path


def _create_intake_sink_writer(root: Path) -> _IntakeSinkWriterCapability:
    """Create the app-contract marker and private writer for an intake-only sink."""
    root.mkdir(parents=True, exist_ok=True)
    marker = root / _INTAKE_SINK_MARKER_NAME
    if not marker.exists():
        marker.write_text("videobox-intake-sink-v1", encoding="utf-8")
    return _IntakeSinkWriterCapability(root.resolve())

_SHA256 = re.compile(r"[0-9a-f]{64}")
_AUDIT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_RAW_PATH_TEXT = re.compile(r"(?:file://|[A-Za-z]:[\\/]|\\\\|(?:^|[\s\"'])/(?:[^\s\"']+))", re.IGNORECASE)
_RELATIVE_MEDIA_PATH = re.compile(
    r"^(?:~[\\/]|\.\.?[\\/]|[^\s\\/]+[\\/][^\s]+\.(?:mp4|mov|mkv|webm|wav|mp3|m4a))",
    re.IGNORECASE,
)
# The normalizer removes separators/case before this policy is applied.  These
# are control/secret word families, not semantic response fields: any `tool*`,
# `shell*`, `sql*`, `approval*`, `authorization*`, `credential*`, `password*`,
# `secret*`, `key*`, or `apikey*` key is unsafe, as is raw media. Required
# structural names such as `token_count` remain allowed.
_FORBIDDEN_NORMALIZED_PREFIXES = (
    "tool",
    "shell",
    "sql",
    "approval",
    "authorization",
    "credential",
    "password",
    "secret",
    "key",
    "apikey",
)
_EXACT_FORBIDDEN_FIELD_NAMES = frozenset({"rawmedia"})
_SENSITIVE_FIELD_SUFFIXES = ("token", "key", "credential", "password", "secret", "path")


@dataclass(frozen=True, slots=True)
class HumanReviewAttestation:
    """Opaque human-scoring evidence bound to exactly one captured response."""

    reviewer_ref: str
    score: float
    correction_seconds: float
    attestation_id: str
    attested_at: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (self.reviewer_ref, self.attestation_id, self.attested_at)
        ):
            raise ValueError("attestation identifiers and timestamp must be non-empty strings")
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
            raise ValueError("attestation score must be a finite number from 0 through 5")
        if not isfinite(float(self.score)) or not 0 <= float(self.score) <= 5:
            raise ValueError("attestation score must be a finite number from 0 through 5")
        if isinstance(self.correction_seconds, bool) or not isinstance(self.correction_seconds, (int, float)):
            raise ValueError("attestation correction_seconds must be a positive finite number")
        if not isfinite(float(self.correction_seconds)) or float(self.correction_seconds) <= 0:
            raise ValueError("attestation correction_seconds must be a positive finite number")
        _require_utc_timestamp(self.attested_at)
        if _contains_prohibited_data(asdict(self)):
            raise ValueError("attestation contains prohibited raw data")
        # Preserve the JSON numeric spelling class (integer versus float) from
        # the signed capture payload. EvaluationMeasurement normalizes metrics
        # later; normalizing here would change the capture's canonical digest.


@dataclass(frozen=True, slots=True)
class ProviderEvidenceCapture:
    """A validated synthetic provider capture tied to one digest-pinned corpus case."""

    capture_id: str
    case: FrozenEvaluationCase
    corpus_canonical_sha256: str
    candidate: CandidateResult
    attestation: HumanReviewAttestation
    payload_sha256: str

    @property
    def corpus_id(self) -> str:
        return self.case.corpus_id

    @property
    def prompt_schema_version(self) -> str:
        return self.case.prompt_schema_version

    @property
    def renderer_version(self) -> str:
        return self.case.renderer_version

    def to_envelope(self) -> dict[str, Any]:
        payload = _capture_payload(
            capture_id=self.capture_id,
            case=self.case,
            corpus_canonical_sha256=self.corpus_canonical_sha256,
            candidate=self.candidate,
            attestation=self.attestation,
        )
        return {**payload, "payload_sha256": self.payload_sha256}


@dataclass(frozen=True, slots=True)
class PersistedProviderEvidence:
    capture: ProviderEvidenceCapture
    record_sha256: str


@dataclass(frozen=True, slots=True)
class PersistedQualificationAudit:
    path: Path
    audit_id: str
    report: QualificationReport
    record_hashes: tuple[str, ...]
    artifact_sha256: str


def import_synthetic_provider_capture(
    envelope: Mapping[str, Any],
) -> ProviderEvidenceCapture:
    """Validate an offline synthetic capture; no provider is contacted.

    The envelope is strict and versioned.  Case identity is resolved again from
    the digest-pinned checked-in corpus, so producer-provided success flags have
    no authority here.
    """
    if not isinstance(envelope, Mapping):
        raise ValueError("provider capture envelope must be an object")
    required_keys = {
        "capture_version",
        "capture_id",
        "corpus_id",
        "corpus_canonical_sha256",
        "prompt_schema_version",
        "renderer_version",
        "case_id",
        "candidate",
        "attestation",
        "payload_sha256",
    }
    if set(envelope) != required_keys:
        raise ValueError("provider capture envelope has an invalid shape")
    if envelope["capture_version"] != CAPTURE_VERSION:
        raise ValueError("provider capture has an unsupported version")
    payload_sha256 = envelope["payload_sha256"]
    if not isinstance(payload_sha256, str) or _SHA256.fullmatch(payload_sha256) is None:
        raise ValueError("provider capture has an invalid payload digest")
    payload = {key: envelope[key] for key in required_keys if key != "payload_sha256"}
    if _canonical_sha256(payload) != payload_sha256:
        raise ValueError("provider capture payload digest does not match")
    if _contains_prohibited_data(payload):
        raise ValueError("provider capture contains prohibited raw data")

    corpus = load_checked_in_korean_evaluation_corpus()
    corpus_canonical_sha256 = envelope["corpus_canonical_sha256"]
    if (
        not isinstance(corpus_canonical_sha256, str)
        or _SHA256.fullmatch(corpus_canonical_sha256) is None
        or corpus_canonical_sha256 != KOREAN_SHADOW_EVALUATION_V1_CANONICAL_SHA256
    ):
        raise ValueError("provider capture corpus digest does not match the pinned corpus")
    identity = (envelope["corpus_id"], envelope["prompt_schema_version"], envelope["renderer_version"])
    if identity != (corpus.corpus_id, corpus.prompt_schema_version, corpus.renderer_version):
        raise ValueError("provider capture corpus identity does not match the pinned corpus")
    capture_id = envelope["capture_id"]
    if not isinstance(capture_id, str) or not capture_id.strip():
        raise ValueError("provider capture_id must be a non-empty string")
    if not isinstance(envelope["case_id"], str) or not envelope["case_id"].strip():
        raise ValueError("provider capture case_id must be a non-empty string")
    cases = {case.case_id: case for case in corpus.cases}
    try:
        case = cases[envelope["case_id"]]
    except KeyError as error:
        raise ValueError("provider capture case is not in the pinned corpus") from error
    candidate = _candidate_from_payload(envelope["candidate"])
    attestation = _attestation_from_payload(envelope["attestation"])
    # Constructing this measurement repeats score/correction validation against
    # the exact frozen case. Evaluation itself happens only when a report builds.
    EvaluationMeasurement(case, candidate, attestation.score, attestation.correction_seconds)
    return ProviderEvidenceCapture(capture_id, case, corpus_canonical_sha256, candidate, attestation, payload_sha256)


class ProviderQualificationEvidenceLedger:
    """Filesystem-backed append-only evidence ledger with a verified hash chain."""

    def __init__(self, root: Path, *, _intake_writer: _IntakeSinkWriterCapability | None = None) -> None:
        if not isinstance(root, Path):
            raise ValueError("ledger root must be a Path")
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.root.is_dir():
            raise ValueError("ledger root must be a directory")
        marker = self.root / _INTAKE_SINK_MARKER_NAME
        self._intake_sink = marker.exists()
        self._intake_writer = _intake_writer
        if self._intake_sink and (
            not isinstance(_intake_writer, _IntakeSinkWriterCapability)
            or _intake_writer.root != self.root.resolve()
        ):
            self._intake_writer = None

    @property
    def records_path(self) -> Path:
        return self.root / "provider_qualification_records.v1.json"

    @property
    def reports_directory(self) -> Path:
        return self.root / "provider_qualification_reports"

    def append(self, capture: ProviderEvidenceCapture) -> PersistedProviderEvidence:
        if self._intake_sink and self._intake_writer is None:
            raise ValueError("intake sink accepts mutations only through its private gateway writer")
        if not isinstance(capture, ProviderEvidenceCapture):
            raise ValueError("ledger append requires a validated provider evidence capture")
        with self._write_lock():
            # Never trust an in-memory dataclass from a caller. Rebuild the
            # strict envelope and re-import it through today's pinned corpus.
            capture = import_synthetic_provider_capture(capture.to_envelope())
            current = self.verify_records()
            if any(record.capture.capture_id == capture.capture_id for record in current):
                raise ValueError("provider capture replay is not allowed")
            if any(record.capture.attestation.attestation_id == capture.attestation.attestation_id for record in current):
                raise ValueError("provider capture attestation replay is not allowed")
            previous_record_sha256 = current[-1].record_sha256 if current else None
            record_payload = {
                "record_version": RECORD_VERSION,
                "capture_id": capture.capture_id,
                "capture": capture.to_envelope(),
                "previous_record_sha256": previous_record_sha256,
            }
            record = {**record_payload, "record_sha256": _canonical_sha256(record_payload)}
            raw = self._read_raw_ledger()
            raw_records = list(raw["records"])
            raw_records.append(record)
            self._atomic_write_json(self.records_path, {"ledger_version": LEDGER_VERSION, "records": raw_records})
            return PersistedProviderEvidence(capture, record["record_sha256"])

    def verify_records(self) -> tuple[PersistedProviderEvidence, ...]:
        raw = self._read_raw_ledger()
        records = raw["records"]
        if not isinstance(records, list):
            raise ValueError("provider evidence ledger records must be an array")
        previous_record_sha256: str | None = None
        capture_ids: set[str] = set()
        attestation_ids: set[str] = set()
        verified: list[PersistedProviderEvidence] = []
        for raw_record in records:
            if not isinstance(raw_record, Mapping) or set(raw_record) != {
                "record_version", "capture_id", "capture", "previous_record_sha256", "record_sha256"
            }:
                raise ValueError("provider evidence ledger record has an invalid shape")
            if raw_record["record_version"] != RECORD_VERSION:
                raise ValueError("provider evidence ledger record has an unsupported version")
            if raw_record["previous_record_sha256"] != previous_record_sha256:
                raise ValueError("provider evidence ledger hash chain order does not match")
            record_sha256 = raw_record["record_sha256"]
            if not isinstance(record_sha256, str) or _SHA256.fullmatch(record_sha256) is None:
                raise ValueError("provider evidence ledger record has an invalid hash")
            record_payload = {key: raw_record[key] for key in raw_record if key != "record_sha256"}
            if _canonical_sha256(record_payload) != record_sha256:
                raise ValueError("provider evidence ledger record hash does not match")
            capture = import_synthetic_provider_capture(raw_record["capture"])
            if raw_record["capture_id"] != capture.capture_id:
                raise ValueError("provider evidence ledger capture identity does not match")
            if capture.capture_id in capture_ids:
                raise ValueError("provider evidence ledger capture replay is not allowed")
            if capture.attestation.attestation_id in attestation_ids:
                raise ValueError("provider evidence ledger attestation replay is not allowed")
            capture_ids.add(capture.capture_id)
            attestation_ids.add(capture.attestation.attestation_id)
            verified.append(PersistedProviderEvidence(capture, record_sha256))
            previous_record_sha256 = record_sha256
        return tuple(verified)

    def write_qualification_report(
        self,
        *,
        audit_id: str,
        baseline_provider: str,
        candidate_provider: str,
    ) -> PersistedQualificationAudit:
        if self._intake_sink and self._intake_writer is None:
            raise ValueError("intake sink accepts mutations only through its private gateway writer")
        if not isinstance(audit_id, str) or _AUDIT_ID.fullmatch(audit_id) is None:
            raise ValueError("audit_id must use only letters, digits, dot, underscore, or hyphen")
        with self._write_lock():
            records = self.verify_records()
            included = tuple(
                record
                for record in records
                if record.capture.candidate.provider in {baseline_provider, candidate_provider}
            )
            report = self._build_report(included, baseline_provider, candidate_provider)
            if report.route_state != "needs_human_review":
                raise ValueError("qualification audit report must remain needs_human_review")
            payload = {
                "artifact_version": AUDIT_ARTIFACT_VERSION,
                "audit_id": audit_id,
                "record_hashes": [record.record_sha256 for record in included],
                "report": _report_payload(report),
            }
            artifact_sha256 = _canonical_sha256(payload)
            self.reports_directory.mkdir(parents=True, exist_ok=True)
            path = self.reports_directory / f"{audit_id}.json"
            if path.exists():
                raise ValueError("qualification audit report is write-once and already exists")
            self._atomic_write_json(path, {**payload, "artifact_sha256": artifact_sha256})
            return PersistedQualificationAudit(path, audit_id, report, tuple(payload["record_hashes"]), artifact_sha256)

    def verify_qualification_report(self, path: Path) -> PersistedQualificationAudit:
        if not isinstance(path, Path) or path.parent.resolve() != self.reports_directory.resolve():
            raise ValueError("qualification audit report path is outside this ledger")
        try:
            raw = loads(path.read_text(encoding="utf-8"))
        except (OSError, JSONDecodeError) as error:
            raise ValueError("qualification audit report cannot be read") from error
        expected_keys = {"artifact_version", "audit_id", "record_hashes", "report", "artifact_sha256"}
        if not isinstance(raw, Mapping) or set(raw) != expected_keys:
            raise ValueError("qualification audit report has an invalid shape")
        payload = {key: raw[key] for key in raw if key != "artifact_sha256"}
        artifact_sha256 = raw["artifact_sha256"]
        if not isinstance(artifact_sha256, str) or _SHA256.fullmatch(artifact_sha256) is None:
            raise ValueError("qualification audit report has an invalid digest")
        if _canonical_sha256(payload) != artifact_sha256:
            raise ValueError("qualification audit report digest does not match")
        if raw["artifact_version"] != AUDIT_ARTIFACT_VERSION:
            raise ValueError("qualification audit report has an unsupported version")
        audit_id = raw["audit_id"]
        if not isinstance(audit_id, str) or _AUDIT_ID.fullmatch(audit_id) is None:
            raise ValueError("qualification audit report has an invalid audit_id")
        report = _report_from_payload(raw["report"])
        if report.route_state != "needs_human_review":
            raise ValueError("qualification audit report cannot activate a route")
        record_hashes = raw["record_hashes"]
        if not isinstance(record_hashes, list) or not record_hashes or any(
            not isinstance(value, str) or _SHA256.fullmatch(value) is None for value in record_hashes
        ):
            raise ValueError("qualification audit report has invalid record hashes")
        if len(set(record_hashes)) != len(record_hashes):
            raise ValueError("qualification audit report repeats a record hash")
        verified_records = self.verify_records()
        verified_by_hash = {record.record_sha256: record for record in verified_records}
        try:
            included = tuple(verified_by_hash[record_hash] for record_hash in record_hashes)
        except KeyError as error:
            raise ValueError("qualification audit report references an unknown record hash") from error
        snapshot_order = tuple(record.record_sha256 for record in verified_records if record.record_sha256 in set(record_hashes))
        if tuple(record_hashes) != snapshot_order:
            raise ValueError("qualification audit report record order or membership does not match ledger")
        expected_report = self._build_report(included, report.baseline_provider, report.candidate_provider)
        if _canonical_json(_report_payload(expected_report)) != _canonical_json(raw["report"]):
            raise ValueError("qualification audit report payload does not match its records")
        return PersistedQualificationAudit(path, audit_id, report, tuple(record_hashes), artifact_sha256)

    @contextmanager
    def _write_lock(self):
        """Hold a narrow cross-process directory lock around read-verify-write."""
        lock_path = self.root / ".provider_qualification_evidence.lock"
        deadline = time.monotonic() + 15
        while True:
            try:
                lock_path.mkdir()
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise ValueError("provider evidence ledger write lock timed out")
                time.sleep(0.01)
        try:
            yield
        finally:
            lock_path.rmdir()

    def _build_report(
        self,
        records: Sequence[PersistedProviderEvidence],
        baseline_provider: str,
        candidate_provider: str,
    ) -> QualificationReport:
        corpus = load_checked_in_korean_evaluation_corpus()
        case_by_id = {case.case_id: case for case in corpus.cases}
        measurements = tuple(
            EvaluationMeasurement(
                case_by_id[record.capture.case.case_id],
                record.capture.candidate,
                record.capture.attestation.score,
                record.capture.attestation.correction_seconds,
            )
            for record in records
        )
        return build_qualification_report(
            corpus=corpus,
            measurements=measurements,
            baseline_provider=baseline_provider,
            candidate_provider=candidate_provider,
        )

    def _read_raw_ledger(self) -> Mapping[str, Any]:
        if not self.records_path.exists():
            return {"ledger_version": LEDGER_VERSION, "records": []}
        try:
            raw = loads(self.records_path.read_text(encoding="utf-8"))
        except (OSError, JSONDecodeError) as error:
            raise ValueError("provider evidence ledger cannot be read") from error
        if not isinstance(raw, Mapping) or set(raw) != {"ledger_version", "records"}:
            raise ValueError("provider evidence ledger has an invalid shape")
        if raw["ledger_version"] != LEDGER_VERSION:
            raise ValueError("provider evidence ledger has an unsupported version")
        return raw

    @staticmethod
    def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
        temporary_path = path.parent / f".{path.name}.{uuid4().hex}.tmp"
        try:
            temporary_path.write_text(_canonical_json(value), encoding="utf-8")
            os.replace(temporary_path, path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()


def _candidate_from_payload(value: Any) -> CandidateResult:
    if not isinstance(value, Mapping) or set(value) != {"provider", "runtime", "model", "output", "latency_ms", "token_count"}:
        raise ValueError("provider capture candidate has an invalid shape")
    if not all(isinstance(value[name], str) and value[name].strip() for name in ("provider", "runtime", "model")):
        raise ValueError("provider capture candidate identifiers must be non-empty strings")
    latency_ms = value["latency_ms"]
    if isinstance(latency_ms, bool) or not isinstance(latency_ms, (int, float)) or not isfinite(float(latency_ms)) or latency_ms < 0:
        raise ValueError("provider capture latency_ms must be a non-negative finite number")
    token_count = value["token_count"]
    if not isinstance(token_count, int) or isinstance(token_count, bool) or token_count < 0:
        raise ValueError("provider capture token_count must be a non-negative integer")
    if not _is_json_value(value["output"]) or _contains_prohibited_data(value["output"]):
        raise ValueError("provider capture candidate output is not safe JSON")
    return CandidateResult(
        value["provider"], value["runtime"], value["model"], value["output"], latency_ms, token_count
    )


def _attestation_from_payload(value: Any) -> HumanReviewAttestation:
    if not isinstance(value, Mapping) or set(value) != {
        "reviewer_ref", "score", "correction_seconds", "attestation_id", "attested_at"
    }:
        raise ValueError("provider capture attestation has an invalid shape")
    return HumanReviewAttestation(
        value["reviewer_ref"], value["score"], value["correction_seconds"], value["attestation_id"], value["attested_at"]
    )


def _capture_payload(
    *,
    capture_id: str,
    case: FrozenEvaluationCase,
    corpus_canonical_sha256: str,
    candidate: CandidateResult,
    attestation: HumanReviewAttestation,
) -> dict[str, Any]:
    return {
        "capture_version": CAPTURE_VERSION,
        "capture_id": capture_id,
        "corpus_id": case.corpus_id,
        "corpus_canonical_sha256": corpus_canonical_sha256,
        "prompt_schema_version": case.prompt_schema_version,
        "renderer_version": case.renderer_version,
        "case_id": case.case_id,
        "candidate": {
            "provider": candidate.provider,
            "runtime": candidate.runtime,
            "model": candidate.model,
            "output": _thaw_json(candidate.output),
            "latency_ms": candidate.latency_ms,
            "token_count": candidate.token_count,
        },
        "attestation": asdict(attestation),
    }


def _report_payload(report: QualificationReport) -> dict[str, Any]:
    return asdict(report)


def _report_from_payload(value: Any) -> QualificationReport:
    expected_keys = {
        "corpus_id", "prompt_schema_version", "renderer_version", "baseline_provider", "candidate_provider", "sample_size",
        "schema_valid_rate", "grounded_claim_rate", "critical_policy_defect_count", "human_score_delta",
        "correction_time_delta_ratio", "schema_valid_ci_95", "grounded_claim_rate_ci_95", "human_score_delta_ci_95",
        "correction_time_delta_ratio_ci_95", "thresholds_passed", "route_state",
    }
    if not isinstance(value, Mapping) or set(value) != expected_keys:
        raise ValueError("qualification audit report payload has an invalid shape")
    try:
        string_fields = ("corpus_id", "prompt_schema_version", "renderer_version", "baseline_provider", "candidate_provider")
        if not all(isinstance(value[field], str) and value[field].strip() for field in string_fields):
            raise ValueError("qualification audit report identifiers are invalid")
        sample_size = _strict_int(value["sample_size"], minimum=1)
        policy_defect_count = _strict_int(value["critical_policy_defect_count"], minimum=0)
        schema_valid_rate = _strict_float(value["schema_valid_rate"], minimum=0, maximum=1)
        grounded_claim_rate = _strict_float(value["grounded_claim_rate"], minimum=0, maximum=1)
        human_score_delta = _strict_float(value["human_score_delta"], minimum=-5, maximum=5)
        correction_time_delta_ratio = _strict_float(value["correction_time_delta_ratio"], minimum=-1)
        if not isinstance(value["thresholds_passed"], bool):
            raise ValueError("qualification audit report thresholds_passed must be a boolean")
        if value["route_state"] != "needs_human_review":
            raise ValueError("qualification audit report route_state is invalid")
        return QualificationReport(
            corpus_id=value["corpus_id"],
            prompt_schema_version=value["prompt_schema_version"],
            renderer_version=value["renderer_version"],
            baseline_provider=value["baseline_provider"],
            candidate_provider=value["candidate_provider"],
            sample_size=sample_size,
            schema_valid_rate=schema_valid_rate,
            grounded_claim_rate=grounded_claim_rate,
            critical_policy_defect_count=policy_defect_count,
            human_score_delta=human_score_delta,
            correction_time_delta_ratio=correction_time_delta_ratio,
            schema_valid_ci_95=_pair(value["schema_valid_ci_95"]),
            grounded_claim_rate_ci_95=_pair(value["grounded_claim_rate_ci_95"]),
            human_score_delta_ci_95=_pair(value["human_score_delta_ci_95"]),
            correction_time_delta_ratio_ci_95=_pair(value["correction_time_delta_ratio_ci_95"]),
            thresholds_passed=value["thresholds_passed"],
            route_state=value["route_state"],
        )
    except (TypeError, ValueError) as error:
        raise ValueError("qualification audit report payload is invalid") from error


def _pair(value: Any) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("qualification audit report interval is invalid")
    return (_strict_float(value[0]), _strict_float(value[1]))


def _strict_int(value: Any, *, minimum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError("qualification audit report count metric is invalid")
    return value


def _strict_float(value: Any, *, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, float) or not isfinite(value):
        raise ValueError("qualification audit report scalar metric is invalid")
    if minimum is not None and value < minimum:
        raise ValueError("qualification audit report scalar metric is outside its allowed range")
    if maximum is not None and value > maximum:
        raise ValueError("qualification audit report scalar metric is outside its allowed range")
    return value


def _require_utc_timestamp(value: str) -> None:
    if not value.endswith("Z"):
        raise ValueError("attestation timestamp must be an explicit UTC Z timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("attestation timestamp must be ISO-8601 UTC") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("attestation timestamp must be UTC")


def _canonical_json(value: Any) -> str:
    try:
        return dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("provider evidence must be JSON-compatible") from error


def _canonical_sha256(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _is_json_value(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return isfinite(value)
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _is_json_value(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return all(_is_json_value(item) for item in value)
    return False


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _contains_prohibited_data(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_is_forbidden_field_name(str(key)) or _contains_prohibited_data(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_prohibited_data(item) for item in value)
    return isinstance(value, str) and (_RAW_PATH_TEXT.search(value) is not None or _RELATIVE_MEDIA_PATH.search(value) is not None)


def _is_forbidden_field_name(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", name.lower())
    return (
        normalized.startswith(_FORBIDDEN_NORMALIZED_PREFIXES)
        or normalized in _EXACT_FORBIDDEN_FIELD_NAMES
        or normalized.endswith(_SENSITIVE_FIELD_SUFFIXES)
    )
