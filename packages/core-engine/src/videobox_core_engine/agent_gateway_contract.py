"""Static, fail-closed ToolSpec contract for the first Yujin gateway slice.

There is intentionally no provider client, API route, tool executor, storage
access, or network operation here.  A model proposal is only untrusted data.
The eventual backend must independently bind the selected project and status
revision before a later execution slice can use this contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from json import dumps
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
    "GatewayPreflightDecision",
    "GatewayRegistry",
    "GatewayRunContext",
    "RedactedToolResult",
    "ToolCallProposal",
    "ToolSpec",
    "load_builtin_gateway_registry",
    "load_builtin_status_tool_spec",
    "preflight_status_read",
    "redact_status_result",
)


TOOL_NAME = "get_project_status"
TOOL_VERSION = "tool-spec-v1"
REGISTRY_VERSION = "gateway-registry-v1"
TOOL_SPEC_MANIFEST_SHA256 = "def18d0d02fa1a30b3fb5b9f40347f76333454422506a959c8b9efa93b758333"
RESULT_REDACTION_SUMMARY = "selected_project_status_only"
_ALLOWED_PHASES = ("read_only_research",)
_REVISION_PRECONDITION = "selected_project_status_revision"
_BACKEND_BINDING_ISSUER = object()
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
