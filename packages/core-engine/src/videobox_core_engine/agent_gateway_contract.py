"""Static, fail-closed ToolSpec contract for the first Yujin gateway slice.

There is intentionally no provider client, API route, tool executor, storage
access, or network operation here.  A model proposal is only untrusted data.
The eventual backend must independently bind the selected project and status
revision before a later execution slice can use this contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from json import dumps
import re
from types import MappingProxyType
from typing import Any, Literal, Mapping

from videobox_core_engine.yujin_profile_contract import (
    YujinContextEnvelope,
    YujinProjectStatus,
    YujinPromptProfile,
    load_builtin_yujin_profile,
)

__all__ = (
    "BackendDerivedStatusRequest",
    "GatewayDecisionAttempt",
    "GatewayDecisionAuditEvent",
    "GatewayDecisionState",
    "GatewayDecisionTransition",
    "GatewayPreflightDecision",
    "GatewayRegistry",
    "GatewayRunContext",
    "RedactedToolResult",
    "ToolCallProposal",
    "ToolSpec",
    "load_builtin_gateway_registry",
    "load_builtin_status_tool_spec",
    "preflight_status_read",
    "record_status_read_decision",
    "redact_status_result",
)


TOOL_NAME = "get_project_status"
TOOL_VERSION = "tool-spec-v1"
REGISTRY_VERSION = "gateway-registry-v1"
TOOL_SPEC_MANIFEST_SHA256 = "def18d0d02fa1a30b3fb5b9f40347f76333454422506a959c8b9efa93b758333"
RESULT_REDACTION_SUMMARY = "selected_project_status_only"
DECISION_AUDIT_VERSION = "gateway-decision-audit-v1"
DECISION_AUDIT_REDACTION = "hashes_and_fixed_reason_only"
_PREFLIGHT_AUDIT_REASON_CODES = frozenset(
    {
        "invalid_gateway_context_or_proposal",
        "backend_attested_context_required",
        "backend_context_scalar_invalid",
        "untrusted_proposal_scalar_invalid",
        "tool_or_version_not_registered",
        "run_phase_not_allowed",
        "backend_derived_request_required",
        "invalid_backend_request",
        "backend_attested_request_required",
        "backend_project_scope_mismatch",
        "untrusted_project_or_revision_mismatch",
        "strict_request_schema_rejected",
        "static_contract_accepted",
    }
)
_AUDIT_REASON_CODES = _PREFLIGHT_AUDIT_REASON_CODES | {"idempotency_key_conflict"}
_ALLOWED_PHASES = ("read_only_research",)
_REVISION_PRECONDITION = "selected_project_status_revision"
_BACKEND_BINDING_ISSUER = object()
_BACKEND_DECISION_ATTEMPT_ISSUER = object()
_KNOWN_RUN_PHASES = frozenset(
    {
        "intake",
        "clarification_needed",
        "brief_candidate",
        "brief_confirmed",
        "read_only_research",
        "proposal_or_approval_request",
        "deterministic_preflight",
        "pending_human_approval",
        "applied",
        "rejected",
        "cancelled",
        "blocked",
        "failed",
    }
)
_REQUEST_SCHEMA: Mapping[str, Any] = MappingProxyType(
    {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
)
_RESULT_SCHEMA: Mapping[str, Any] = MappingProxyType(
    {
        "type": "object",
        "required": [
            "project_id",
            "name",
            "status",
            "updated_at",
            "has_editing_session",
            "latest_session_revision",
        ],
        "properties": {
            "project_id": {"type": "string"},
            "name": {"type": "string"},
            "status": {"type": "string"},
            "updated_at": {"type": "string"},
            "has_editing_session": {"type": "boolean"},
            "latest_session_revision": {"type": ["string", "null"]},
        },
        "additionalProperties": False,
    }
)


def _canonical_json(value: Any) -> str:
    return dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    frozen: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            frozen[key] = _freeze_mapping(item)
        elif isinstance(item, list):
            frozen[key] = tuple(_freeze_mapping(part) if isinstance(part, Mapping) else part for part in item)
        else:
            frozen[key] = item
    return MappingProxyType(frozen)


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _builtin_spec_payload() -> Mapping[str, Any]:
    return {
        "name": TOOL_NAME,
        "version": TOOL_VERSION,
        "action_family": "read",
        "request_schema": _thaw(_REQUEST_SCHEMA),
        "result_schema": _thaw(_RESULT_SCHEMA),
        "backend_scope": "selected_project_status_only",
        "revision_precondition": _REVISION_PRECONDITION,
        "redaction_summary": RESULT_REDACTION_SUMMARY,
        "result_max_bytes": 1024,
        "timeout_ms": 1000,
        "idempotency": "not_applicable_read_only_static_contract",
        "audit_event": "agent_gateway_status_read_preflight",
        "allowed_run_phases": list(_ALLOWED_PHASES),
    }


def _is_exact_empty_object(value: object) -> bool:
    return type(value) is dict and value == {}


def _is_canonical_empty_backend_request(value: object) -> bool:
    return type(value) is type(MappingProxyType({})) and dict(value) == {}


def _has_exact_context_scalars(context: "GatewayRunContext") -> bool:
    status = context.yujin_context.status
    return (
        type(context.yujin_context.project_id) is str
        and type(context.yujin_context.context_sha256) is str
        and type(status) is YujinProjectStatus
        and type(status.project_id) is str
        and type(status.name) is str
        and type(status.status) is str
        and type(status.updated_at) is str
        and type(status.has_editing_session) is bool
        and (status.latest_session_revision is None or type(status.latest_session_revision) is str)
    )


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Pinned metadata; it describes a possible read, never an invocation."""

    name: str
    version: str
    action_family: Literal["read"]
    request_schema: Mapping[str, Any]
    result_schema: Mapping[str, Any]
    backend_scope: Literal["selected_project_status_only"]
    revision_precondition: Literal["selected_project_status_revision"]
    redaction_summary: Literal["selected_project_status_only"]
    result_max_bytes: int
    timeout_ms: int
    idempotency: Literal["not_applicable_read_only_static_contract"]
    audit_event: Literal["agent_gateway_status_read_preflight"]
    allowed_run_phases: tuple[str, ...]
    manifest_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.allowed_run_phases, tuple):
            raise ValueError("ToolSpec allowed phases must be immutable")
        request_schema = _freeze_mapping(self.request_schema)
        result_schema = _freeze_mapping(self.result_schema)
        payload = {
            "name": self.name,
            "version": self.version,
            "action_family": self.action_family,
            "request_schema": _thaw(request_schema),
            "result_schema": _thaw(result_schema),
            "backend_scope": self.backend_scope,
            "revision_precondition": self.revision_precondition,
            "redaction_summary": self.redaction_summary,
            "result_max_bytes": self.result_max_bytes,
            "timeout_ms": self.timeout_ms,
            "idempotency": self.idempotency,
            "audit_event": self.audit_event,
            "allowed_run_phases": list(self.allowed_run_phases),
        }
        if payload != _builtin_spec_payload() or self.manifest_sha256 != TOOL_SPEC_MANIFEST_SHA256:
            raise ValueError("ToolSpec must use the pinned built-in registry artifacts")
        if _digest(payload) != self.manifest_sha256:
            raise ValueError("ToolSpec manifest does not match the pinned artifacts")
        object.__setattr__(self, "request_schema", request_schema)
        object.__setattr__(self, "result_schema", result_schema)


def load_builtin_status_tool_spec() -> ToolSpec:
    artifacts = dict(_builtin_spec_payload())
    artifacts["allowed_run_phases"] = tuple(artifacts["allowed_run_phases"])
    return ToolSpec(**artifacts, manifest_sha256=TOOL_SPEC_MANIFEST_SHA256)


@dataclass(frozen=True, slots=True)
class GatewayRegistry:
    registry_version: Literal["gateway-registry-v1"]
    tools: Mapping[str, ToolSpec]

    def __post_init__(self) -> None:
        expected = load_builtin_status_tool_spec()
        if self.registry_version != REGISTRY_VERSION or set(self.tools) != {TOOL_NAME} or self.tools[TOOL_NAME] != expected:
            raise ValueError("Gateway registry must contain the sole pinned ToolSpec")
        object.__setattr__(self, "tools", MappingProxyType({TOOL_NAME: expected}))

    def lookup(self, *, name: str, version: str) -> ToolSpec:
        spec = self.tools.get(name)
        if spec is None or version != spec.version:
            raise ValueError("ToolSpec is not registered at the requested pinned version")
        return spec


def load_builtin_gateway_registry() -> GatewayRegistry:
    spec = load_builtin_status_tool_spec()
    return GatewayRegistry(registry_version=REGISTRY_VERSION, tools={TOOL_NAME: spec})


@dataclass(frozen=True, slots=True)
class GatewayRunContext:
    """Backend-selected context with an in-process binding marker.

    The private marker distinguishes ordinary app construction from the local
    backend factory. It is an application-contract guard, not a defense
    against hostile in-process code that can import private module state.
    """

    profile: YujinPromptProfile
    yujin_context: YujinContextEnvelope
    run_phase: str
    _backend_binding: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.profile) is not YujinPromptProfile or type(self.yujin_context) is not YujinContextEnvelope:
            raise ValueError("Gateway context requires the pinned Yujin profile and selected project context")
        if self.profile != load_builtin_yujin_profile() or type(self.run_phase) is not str or self.run_phase not in _KNOWN_RUN_PHASES:
            raise ValueError("Gateway run phase is unknown")
        if self._backend_binding not in (None, _BACKEND_BINDING_ISSUER):
            raise ValueError("Gateway context has an invalid backend attestation marker")

    @property
    def is_backend_attested(self) -> bool:
        return self._backend_binding is _BACKEND_BINDING_ISSUER


def _build_backend_attested_run_context(
    *, profile: YujinPromptProfile, yujin_context: YujinContextEnvelope, run_phase: str
) -> GatewayRunContext:
    """Backend-adapter-only factory. Not part of the public consumer surface."""
    return GatewayRunContext(
        profile=profile,
        yujin_context=yujin_context,
        run_phase=run_phase,
        _backend_binding=_BACKEND_BINDING_ISSUER,
    )


@dataclass(frozen=True, slots=True)
class ToolCallProposal:
    """Untrusted model data.  Its tool, project, and revision fields grant no authority."""

    tool_name: object
    tool_version: object
    project_id: object
    source_revision: object
    request_payload: object


@dataclass(frozen=True, slots=True)
class BackendDerivedStatusRequest:
    """A local backend binding, not a model supplied request or an executor call.

    The marker is only an ordinary in-process app-contract boundary; hostile
    in-process code is explicitly outside this static contract's threat model.
    """

    project_id: str
    source_revision: str | None
    request_payload: Mapping[str, Any]
    context_sha256: str
    _backend_binding: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            type(self.project_id) is not str
            or type(self.context_sha256) is not str
            or not (_is_exact_empty_object(self.request_payload) or _is_canonical_empty_backend_request(self.request_payload))
        ):
            raise ValueError("status request must be backend-derived with the empty strict request schema")
        if self.source_revision is not None and type(self.source_revision) is not str:
            raise ValueError("status request revision must be backend-derived")
        if self._backend_binding not in (None, _BACKEND_BINDING_ISSUER):
            raise ValueError("status request has an invalid backend attestation marker")
        object.__setattr__(self, "request_payload", MappingProxyType({}))

    @property
    def is_backend_attested(self) -> bool:
        return self._backend_binding is _BACKEND_BINDING_ISSUER


def _build_backend_attested_status_request(*, context: GatewayRunContext) -> BackendDerivedStatusRequest:
    """Backend-adapter-only request binding. Not a public authority issuer."""
    if not isinstance(context, GatewayRunContext) or not context.is_backend_attested:
        raise ValueError("status request requires the backend-selected gateway context")
    return BackendDerivedStatusRequest(
        project_id=context.yujin_context.project_id,
        source_revision=context.yujin_context.status.latest_session_revision,
        request_payload={},
        context_sha256=context.yujin_context.context_sha256,
        _backend_binding=_BACKEND_BINDING_ISSUER,
    )


@dataclass(frozen=True, slots=True)
class GatewayPreflightDecision:
    static_contract_accepted: bool
    reason: str
    spec_manifest_sha256: str | None
    sanitized_request: Mapping[str, Any] | None
    executor_authorized: Literal[False] = False


_BACKEND_OPAQUE_IDENTIFIER = re.compile(
    r"(?:corr|idem|principal)_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z"
)
_UTC_AUDIT_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")


def _is_backend_opaque_identifier(value: object, *, prefix: str) -> bool:
    return type(value) is str and value.startswith(prefix) and _BACKEND_OPAQUE_IDENTIFIER.fullmatch(value) is not None


def _is_utc_audit_timestamp(value: object) -> bool:
    if type(value) is not str or _UTC_AUDIT_TIMESTAMP.fullmatch(value) is None:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _text_sha256(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _redacted_context_reference(context: object, *, field: Literal["project_id", "source_revision"]) -> str | None:
    if not isinstance(context, GatewayRunContext):
        return None
    value: object
    if field == "project_id":
        value = context.yujin_context.project_id
    else:
        value = context.yujin_context.status.latest_session_revision
    return _text_sha256(value) if type(value) is str else None


@dataclass(frozen=True, slots=True)
class GatewayDecisionAttempt:
    """Untrusted run metadata used only for correlation and replay bookkeeping.

    ``untrusted_model_claim`` is intentionally neither validated as authority nor
    retained in state/audit. It exists to make that boundary explicit in tests
    and future adapters.
    """

    correlation_id: str
    idempotency_key: str
    backend_principal_ref: str
    occurred_at: str
    retry_attempt: int
    untrusted_model_claim: object = field(default=None, repr=False, compare=False)
    _backend_binding: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not _is_backend_opaque_identifier(self.correlation_id, prefix="corr_"):
            raise ValueError("decision correlation identifier must use the fixed high-entropy backend format")
        if not _is_backend_opaque_identifier(self.idempotency_key, prefix="idem_"):
            raise ValueError("decision idempotency key must use the fixed high-entropy backend format")
        if not _is_backend_opaque_identifier(self.backend_principal_ref, prefix="principal_"):
            raise ValueError("decision backend principal must use the fixed high-entropy backend format")
        if not _is_utc_audit_timestamp(self.occurred_at):
            raise ValueError("decision audit timestamp must be strict UTC seconds")
        if type(self.retry_attempt) is not int or self.retry_attempt < 0:
            raise ValueError("decision retry attempt must be a nonnegative integer")
        if self._backend_binding not in (None, _BACKEND_DECISION_ATTEMPT_ISSUER):
            raise ValueError("decision attempt has an invalid backend attestation marker")

    @property
    def is_backend_attested(self) -> bool:
        return self._backend_binding is _BACKEND_DECISION_ATTEMPT_ISSUER


def _build_backend_attested_decision_attempt(
    *, correlation_id: str, idempotency_key: str, backend_principal_ref: str, occurred_at: str,
    retry_attempt: int, untrusted_model_claim: object = None,
) -> GatewayDecisionAttempt:
    """Backend-adapter-only metadata binding; model-supplied identifiers have no authority."""
    return GatewayDecisionAttempt(
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        backend_principal_ref=backend_principal_ref,
        occurred_at=occurred_at,
        retry_attempt=retry_attempt,
        untrusted_model_claim=untrusted_model_claim,
        _backend_binding=_BACKEND_DECISION_ATTEMPT_ISSUER,
    )


@dataclass(frozen=True, slots=True)
class _StoredGatewayDecision:
    fingerprint_sha256: str
    decision_sha256: str
    static_contract_accepted: bool
    reason: str
    spec_manifest_sha256: str | None

    def __post_init__(self) -> None:
        if (
            _SHA256_HEX.fullmatch(self.fingerprint_sha256) is None
            or _SHA256_HEX.fullmatch(self.decision_sha256) is None
            or type(self.static_contract_accepted) is not bool
            or type(self.reason) is not str
            or self.reason not in _PREFLIGHT_AUDIT_REASON_CODES
            or (self.spec_manifest_sha256 is not None and _SHA256_HEX.fullmatch(self.spec_manifest_sha256) is None)
        ):
            raise ValueError("stored gateway decision has an invalid static shape")


@dataclass(frozen=True, slots=True)
class GatewayDecisionState:
    """Immutable local replay state contract; it is not persistent storage."""

    records: Mapping[str, _StoredGatewayDecision]
    storage_scope: Literal["in_memory_nonpersistent"] = "in_memory_nonpersistent"

    def __post_init__(self) -> None:
        if not isinstance(self.records, Mapping) or self.storage_scope != "in_memory_nonpersistent":
            raise ValueError("gateway decision state requires an immutable mapping")
        records: dict[str, _StoredGatewayDecision] = {}
        for key, value in self.records.items():
            if type(key) is not str or _SHA256_HEX.fullmatch(key) is None or type(value) is not _StoredGatewayDecision:
                raise ValueError("gateway decision state contains an invalid record")
            records[key] = value
        object.__setattr__(self, "records", MappingProxyType(records))

    @classmethod
    def empty(cls) -> "GatewayDecisionState":
        return cls(records={})


@dataclass(frozen=True, slots=True)
class GatewayDecisionAuditEvent:
    """Redacted deterministic audit record. It never contains a model claim or raw content."""

    event_id: str
    correlation_id_sha256: str
    idempotency_key_sha256: str
    retry_attempt: int
    retry_disposition: Literal["initial_nonexecuting", "replayed_nonexecuting", "idempotency_conflict_nonexecuting"]
    decision_sha256: str
    outcome: Literal["accepted", "denied"]
    reason: str
    static_contract_accepted: bool
    executor_authorized: Literal[False]
    spec_manifest_sha256: str | None
    profile_manifest_sha256: str
    tool_name: Literal["get_project_status"]
    tool_version: Literal["tool-spec-v1"]
    sanitized_request_sha256: str
    static_result_sha256: None
    principal_sha256: str
    occurred_at: str
    state_scope: Literal["in_memory_nonpersistent"]
    project_id_sha256: str | None
    source_revision_sha256: str | None
    redaction_summary: Literal["hashes_and_fixed_reason_only"]
    event_sha256: str

    def __post_init__(self) -> None:
        hashes = (
            self.correlation_id_sha256, self.idempotency_key_sha256, self.decision_sha256, self.event_sha256,
            self.profile_manifest_sha256, self.sanitized_request_sha256, self.principal_sha256,
        )
        optional_hashes = (self.spec_manifest_sha256, self.project_id_sha256, self.source_revision_sha256)
        if (
            type(self.event_id) is not str
            or _SHA256_HEX.fullmatch(self.event_id) is None
            or any(_SHA256_HEX.fullmatch(value) is None for value in hashes)
            or any(value is not None and _SHA256_HEX.fullmatch(value) is None for value in optional_hashes)
            or type(self.retry_attempt) is not int
            or self.retry_attempt < 0
            or self.retry_disposition not in {"initial_nonexecuting", "replayed_nonexecuting", "idempotency_conflict_nonexecuting"}
            or self.outcome not in {"accepted", "denied"}
            or type(self.reason) is not str
            or self.reason not in _AUDIT_REASON_CODES
            or type(self.static_contract_accepted) is not bool
            or self.executor_authorized is not False
            or self.redaction_summary != DECISION_AUDIT_REDACTION
            or self.tool_name != TOOL_NAME
            or self.tool_version != TOOL_VERSION
            or self.sanitized_request_sha256 != _digest({})
            or self.static_result_sha256 is not None
            or not _is_utc_audit_timestamp(self.occurred_at)
            or self.state_scope != "in_memory_nonpersistent"
        ):
            raise ValueError("gateway decision audit event has an invalid redacted shape")
        if self.retry_disposition == "idempotency_conflict_nonexecuting":
            if self.reason != "idempotency_key_conflict" or self.static_contract_accepted or self.outcome != "denied":
                raise ValueError("gateway decision audit conflict must remain non-authorizing")
        elif (
            self.reason == "idempotency_key_conflict"
            or self.static_contract_accepted != (self.reason == "static_contract_accepted")
            or self.outcome != ("accepted" if self.static_contract_accepted else "denied")
        ):
            raise ValueError("gateway decision audit reason must match the fixed static outcome")
        payload = self._payload_without_hash()
        if _digest(payload) != self.event_sha256 or self.event_id != self.event_sha256:
            raise ValueError("gateway decision audit event hash does not match")

    def _payload_without_hash(self) -> Mapping[str, Any]:
        return {
            "audit_version": DECISION_AUDIT_VERSION,
            "correlation_id_sha256": self.correlation_id_sha256,
            "idempotency_key_sha256": self.idempotency_key_sha256,
            "retry_attempt": self.retry_attempt,
            "retry_disposition": self.retry_disposition,
            "decision_sha256": self.decision_sha256,
            "outcome": self.outcome,
            "reason": self.reason,
            "static_contract_accepted": self.static_contract_accepted,
            "executor_authorized": False,
            "spec_manifest_sha256": self.spec_manifest_sha256,
            "profile_manifest_sha256": self.profile_manifest_sha256,
            "tool_name": TOOL_NAME,
            "tool_version": TOOL_VERSION,
            "sanitized_request_sha256": _digest({}),
            "static_result_sha256": None,
            "principal_sha256": self.principal_sha256,
            "occurred_at": self.occurred_at,
            "state_scope": "in_memory_nonpersistent",
            "project_id_sha256": self.project_id_sha256,
            "source_revision_sha256": self.source_revision_sha256,
            "redaction_summary": DECISION_AUDIT_REDACTION,
        }

    def as_dict(self) -> Mapping[str, Any]:
        return MappingProxyType({**self._payload_without_hash(), "event_id": self.event_id, "event_sha256": self.event_sha256})


@dataclass(frozen=True, slots=True)
class GatewayDecisionTransition:
    audit_event: GatewayDecisionAuditEvent
    state: GatewayDecisionState


def _proposal_audit_shape(context: object, proposal: object, backend_request: object) -> Mapping[str, Any]:
    """Describe comparison outcomes, never proposal values or request payload content."""
    selected_project = context.yujin_context.project_id if isinstance(context, GatewayRunContext) else None
    selected_revision = context.yujin_context.status.latest_session_revision if isinstance(context, GatewayRunContext) else None
    if not isinstance(proposal, ToolCallProposal):
        proposal_shape: Mapping[str, str] = MappingProxyType({"kind": "invalid"})
    else:
        proposal_shape = MappingProxyType(
            {
                "kind": "tool_proposal",
                "tool": "registered" if type(proposal.tool_name) is str and proposal.tool_name == TOOL_NAME else "unregistered_or_invalid",
                "version": "pinned" if type(proposal.tool_version) is str and proposal.tool_version == TOOL_VERSION else "unknown_or_invalid",
                "project": "selected" if type(proposal.project_id) is str and proposal.project_id == selected_project else "other_or_invalid",
                "revision": "selected" if proposal.source_revision == selected_revision else "other_or_invalid",
                "request": "empty" if _is_exact_empty_object(proposal.request_payload) else "nonempty_or_invalid",
            }
        )
    if backend_request is None:
        backend_shape: Mapping[str, str] = MappingProxyType({"kind": "missing"})
    elif not isinstance(backend_request, BackendDerivedStatusRequest):
        backend_shape = MappingProxyType({"kind": "invalid"})
    else:
        backend_shape = MappingProxyType(
            {
                "kind": "attested" if backend_request.is_backend_attested else "unattested",
                "project": "selected" if backend_request.project_id == selected_project else "other",
                "revision": "selected" if backend_request.source_revision == selected_revision else "other",
                "request": "empty" if _is_canonical_empty_backend_request(backend_request.request_payload) else "nonempty_or_invalid",
            }
        )
    return MappingProxyType({"proposal": proposal_shape, "backend": backend_shape})


def _decision_fingerprint(
    *, context: object, proposal: object, backend_request: object, attempt: GatewayDecisionAttempt,
    decision: GatewayPreflightDecision,
) -> str:
    context_sha256 = (
        context.yujin_context.context_sha256
        if isinstance(context, GatewayRunContext) and type(context.yujin_context.context_sha256) is str
        else None
    )
    run_phase = context.run_phase if isinstance(context, GatewayRunContext) and type(context.run_phase) is str else "invalid"
    return _digest(
        {
            "audit_version": DECISION_AUDIT_VERSION,
            "correlation_id_sha256": _text_sha256(attempt.correlation_id),
            "principal_sha256": _text_sha256(attempt.backend_principal_ref),
            "context_sha256": context_sha256,
            "run_phase": run_phase,
            "input_shape": _thaw(_proposal_audit_shape(context, proposal, backend_request)),
            "static_contract_accepted": decision.static_contract_accepted,
            "reason": decision.reason,
            "spec_manifest_sha256": decision.spec_manifest_sha256,
            "executor_authorized": False,
        }
    )


def _make_decision_audit_event(
    *, context: object, attempt: GatewayDecisionAttempt, stored: _StoredGatewayDecision,
    retry_disposition: Literal["initial_nonexecuting", "replayed_nonexecuting", "idempotency_conflict_nonexecuting"],
) -> GatewayDecisionAuditEvent:
    static_contract_accepted = stored.static_contract_accepted and retry_disposition != "idempotency_conflict_nonexecuting"
    reason = stored.reason if retry_disposition != "idempotency_conflict_nonexecuting" else "idempotency_key_conflict"
    payload = {
        "audit_version": DECISION_AUDIT_VERSION,
        "correlation_id_sha256": _text_sha256(attempt.correlation_id),
        "idempotency_key_sha256": _text_sha256(attempt.idempotency_key),
        "retry_attempt": attempt.retry_attempt,
        "retry_disposition": retry_disposition,
        "decision_sha256": stored.decision_sha256,
        "outcome": "accepted" if static_contract_accepted else "denied",
        "reason": reason,
        "static_contract_accepted": static_contract_accepted,
        "executor_authorized": False,
        "spec_manifest_sha256": stored.spec_manifest_sha256,
        "profile_manifest_sha256": context.profile.prompt_manifest_sha256,
        "tool_name": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "sanitized_request_sha256": _digest({}),
        "static_result_sha256": None,
        "principal_sha256": _text_sha256(attempt.backend_principal_ref),
        "occurred_at": attempt.occurred_at,
        "state_scope": "in_memory_nonpersistent",
        "project_id_sha256": _redacted_context_reference(context, field="project_id"),
        "source_revision_sha256": _redacted_context_reference(context, field="source_revision"),
        "redaction_summary": DECISION_AUDIT_REDACTION,
    }
    event_sha256 = _digest(payload)
    event_fields = {key: value for key, value in payload.items() if key != "audit_version"}
    return GatewayDecisionAuditEvent(**event_fields, event_id=event_sha256, event_sha256=event_sha256)


def record_status_read_decision(
    *, state: GatewayDecisionState, context: GatewayRunContext, proposal: ToolCallProposal,
    backend_request: BackendDerivedStatusRequest | None, attempt: GatewayDecisionAttempt,
) -> GatewayDecisionTransition:
    """Audit a static preflight and maintain only redacted, non-executing replay state."""
    if not isinstance(state, GatewayDecisionState) or not isinstance(attempt, GatewayDecisionAttempt):
        raise ValueError("gateway decision recording requires static state and a bounded attempt")
    if not attempt.is_backend_attested:
        raise ValueError("gateway decision recording requires a backend-attested decision attempt")
    decision = preflight_status_read(context=context, proposal=proposal, backend_request=backend_request)
    fingerprint_sha256 = _decision_fingerprint(
        context=context, proposal=proposal, backend_request=backend_request, attempt=attempt, decision=decision
    )
    idempotency_key_sha256 = _text_sha256(attempt.idempotency_key)
    stored = state.records.get(idempotency_key_sha256)
    if stored is None:
        stored = _StoredGatewayDecision(
            fingerprint_sha256=fingerprint_sha256,
            decision_sha256=_digest(
                {
                    "fingerprint_sha256": fingerprint_sha256,
                    "static_contract_accepted": decision.static_contract_accepted,
                    "reason": decision.reason,
                    "spec_manifest_sha256": decision.spec_manifest_sha256,
                    "executor_authorized": False,
                }
            ),
            static_contract_accepted=decision.static_contract_accepted,
            reason=decision.reason,
            spec_manifest_sha256=decision.spec_manifest_sha256,
        )
        records = dict(state.records)
        records[idempotency_key_sha256] = stored
        next_state = GatewayDecisionState(records=records)
        disposition: Literal["initial_nonexecuting", "replayed_nonexecuting", "idempotency_conflict_nonexecuting"] = "initial_nonexecuting"
    elif stored.fingerprint_sha256 == fingerprint_sha256:
        next_state = state
        disposition = "replayed_nonexecuting"
    else:
        next_state = state
        disposition = "idempotency_conflict_nonexecuting"
    return GatewayDecisionTransition(
        audit_event=_make_decision_audit_event(
            context=context, attempt=attempt, stored=stored, retry_disposition=disposition
        ),
        state=next_state,
    )


def _denied(reason: str, spec: ToolSpec | None = None) -> GatewayPreflightDecision:
    return GatewayPreflightDecision(
        static_contract_accepted=False,
        reason=reason,
        spec_manifest_sha256=None if spec is None else spec.manifest_sha256,
        sanitized_request=None,
    )


def _matches_revision_precondition(
    spec: ToolSpec, *, expected: str | None, candidate: object
) -> bool:
    """Use the pinned spec rather than an implicit revision comparison rule."""
    if spec.revision_precondition != _REVISION_PRECONDITION:
        return False
    return candidate == expected


def _has_exact_proposal_scalars(proposal: ToolCallProposal) -> bool:
    return (
        type(proposal.tool_name) is str
        and type(proposal.tool_version) is str
        and type(proposal.project_id) is str
        and (proposal.source_revision is None or type(proposal.source_revision) is str)
        and _is_exact_empty_object(proposal.request_payload)
    )


def preflight_status_read(
    *, context: GatewayRunContext, proposal: ToolCallProposal, backend_request: BackendDerivedStatusRequest | None
) -> GatewayPreflightDecision:
    """Validate only; even an accepted preflight never authorizes or runs a tool."""
    if not isinstance(context, GatewayRunContext) or not isinstance(proposal, ToolCallProposal):
        return _denied("invalid_gateway_context_or_proposal")
    if not context.is_backend_attested:
        return _denied("backend_attested_context_required")
    if not _has_exact_context_scalars(context):
        return _denied("backend_context_scalar_invalid")
    if not _has_exact_proposal_scalars(proposal):
        return _denied("untrusted_proposal_scalar_invalid")
    try:
        spec = load_builtin_gateway_registry().lookup(name=proposal.tool_name, version=proposal.tool_version)
    except (TypeError, ValueError):
        return _denied("tool_or_version_not_registered")
    if context.run_phase not in spec.allowed_run_phases:
        return _denied("run_phase_not_allowed", spec)
    if backend_request is None:
        return _denied("backend_derived_request_required", spec)
    if not isinstance(backend_request, BackendDerivedStatusRequest):
        return _denied("invalid_backend_request", spec)
    if not backend_request.is_backend_attested:
        return _denied("backend_attested_request_required", spec)
    if (
        backend_request.project_id != context.yujin_context.project_id
        or backend_request.context_sha256 != context.yujin_context.context_sha256
        or not _matches_revision_precondition(
            spec,
            expected=context.yujin_context.status.latest_session_revision,
            candidate=backend_request.source_revision,
        )
    ):
        return _denied("backend_project_scope_mismatch", spec)
    if proposal.project_id != backend_request.project_id or proposal.source_revision != backend_request.source_revision:
        return _denied("untrusted_project_or_revision_mismatch", spec)
    if not _is_exact_empty_object(proposal.request_payload) or not _is_canonical_empty_backend_request(backend_request.request_payload):
        return _denied("strict_request_schema_rejected", spec)
    return GatewayPreflightDecision(
        static_contract_accepted=True,
        reason="static_contract_accepted",
        spec_manifest_sha256=spec.manifest_sha256,
        sanitized_request=MappingProxyType({}),
    )


@dataclass(frozen=True, slots=True)
class RedactedToolResult:
    payload: Mapping[str, Any]
    byte_size: int
    elapsed_ms: int
    redaction_summary: Literal["selected_project_status_only"]
    executor_authorized: Literal[False] = False


def redact_status_result(
    *, context: GatewayRunContext, backend_status: YujinProjectStatus, elapsed_ms: int
) -> RedactedToolResult:
    """Shape a pre-supplied backend status result without fetching or executing anything."""
    spec = load_builtin_status_tool_spec()
    if not isinstance(context, GatewayRunContext) or not isinstance(backend_status, YujinProjectStatus):
        raise ValueError("status result requires selected backend context and allowlisted status")
    if not context.is_backend_attested:
        raise ValueError("status result requires backend-attested context")
    if not _has_exact_context_scalars(context):
        raise ValueError("status result requires exact backend context scalars")
    if context.run_phase not in spec.allowed_run_phases:
        raise ValueError("status result run phase is not allowed by the pinned ToolSpec")
    if backend_status.project_id != context.yujin_context.project_id:
        raise ValueError("status result project must match backend-selected project")
    if not _matches_revision_precondition(
        spec,
        expected=context.yujin_context.status.latest_session_revision,
        candidate=backend_status.latest_session_revision,
    ):
        raise ValueError("status result revision must match the backend-selected precondition")
    if not isinstance(elapsed_ms, int) or isinstance(elapsed_ms, bool) or elapsed_ms < 0 or elapsed_ms > spec.timeout_ms:
        raise ValueError("status result exceeded the static timeout")
    payload = MappingProxyType(dict(backend_status.as_allowlisted_dict()))
    if set(payload) != set(spec.result_schema["required"]):
        raise ValueError("status result violates the strict result schema")
    byte_size = len(_canonical_json(_thaw(payload)).encode("utf-8"))
    if byte_size > spec.result_max_bytes:
        raise ValueError("status result exceeded the static byte cap")
    return RedactedToolResult(
        payload=payload,
        byte_size=byte_size,
        elapsed_ms=elapsed_ms,
        redaction_summary=RESULT_REDACTION_SUMMARY,
    )
