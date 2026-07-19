from __future__ import annotations

from dataclasses import replace

import pytest

import videobox_core_engine.agent_gateway_contract as gateway_contract
from videobox_core_engine.agent_gateway_contract import (
    BackendDerivedStatusRequest,
    GatewayRunContext,
    ToolCallProposal,
    _build_backend_attested_status_request,
    _build_backend_attested_run_context,
    load_builtin_gateway_registry,
    preflight_status_read,
    redact_status_result,
)
from videobox_core_engine.yujin_profile_contract import (
    YujinContextEnvelope,
    YujinProjectStatus,
    load_builtin_yujin_profile,
)


def _status(*, project_id: str = "project-waterplay-001") -> YujinProjectStatus:
    return YujinProjectStatus(
        project_id=project_id,
        name="아이 물놀이",
        status="editing",
        updated_at="2026-07-20T09:00:00Z",
        has_editing_session=True,
        latest_session_revision="revision-002",
    )


def _context(*, phase: str = "read_only_research") -> GatewayRunContext:
    return _build_backend_attested_run_context(
        profile=load_builtin_yujin_profile(),
        yujin_context=YujinContextEnvelope(project_id="project-waterplay-001", status=_status()),
        run_phase=phase,
    )


def test_builtin_registry_pins_the_only_read_spec_and_its_execution_limits() -> None:
    registry = load_builtin_gateway_registry()
    spec = registry.lookup(name="get_project_status", version="tool-spec-v1")

    assert spec.action_family == "read"
    assert spec.allowed_run_phases == ("read_only_research",)
    assert spec.timeout_ms == 1000
    assert spec.result_max_bytes == 1024
    assert spec.revision_precondition == "selected_project_status_revision"
    assert spec.request_schema["additionalProperties"] is False
    assert spec.request_schema["properties"] == {}
    assert spec.result_schema["additionalProperties"] is False
    assert spec.redaction_summary == "selected_project_status_only"

    with pytest.raises(ValueError, match="pinned|registry"):
        replace(spec, timeout_ms=500)
    with pytest.raises(ValueError, match="pinned|registry"):
        replace(spec, revision_precondition="none")


def test_model_proposed_tool_id_or_scope_has_no_authority_without_backend_request() -> None:
    context = _context()
    forged = ToolCallProposal(
        tool_name="get_project_status",
        tool_version="tool-spec-v1",
        project_id="project-waterplay-001",
        source_revision="revision-002",
        request_payload={},
    )

    decision = preflight_status_read(context=context, proposal=forged, backend_request=None)

    assert decision.static_contract_accepted is False
    assert decision.executor_authorized is False
    assert decision.reason == "backend_derived_request_required"
    assert decision.sanitized_request is None


def test_backend_selected_scope_and_phase_must_match_before_a_non_executable_preflight_can_pass() -> None:
    context = _context()
    proposal = ToolCallProposal(
        tool_name="get_project_status",
        tool_version="tool-spec-v1",
        project_id="project-waterplay-001",
        source_revision="revision-002",
        request_payload={},
    )
    backend_request = _build_backend_attested_status_request(context=context)

    accepted = preflight_status_read(context=context, proposal=proposal, backend_request=backend_request)
    assert accepted.static_contract_accepted is True
    assert accepted.reason == "static_contract_accepted"
    assert accepted.executor_authorized is False
    assert accepted.sanitized_request == {}

    wrong_scope = replace(backend_request, project_id="project-other-001")
    rejected_scope = preflight_status_read(context=context, proposal=proposal, backend_request=wrong_scope)
    assert rejected_scope.static_contract_accepted is False
    assert rejected_scope.reason == "backend_project_scope_mismatch"

    wrong_phase = _context(phase="proposal_or_approval_request")
    rejected_phase = preflight_status_read(context=wrong_phase, proposal=proposal, backend_request=backend_request)
    assert rejected_phase.static_contract_accepted is False
    assert rejected_phase.reason == "run_phase_not_allowed"


@pytest.mark.parametrize(
    "proposal",
    [
        ToolCallProposal("render_video", "tool-spec-v1", "project-waterplay-001", "revision-002", {}),
        ToolCallProposal("get_project_status", "unknown", "project-waterplay-001", "revision-002", {}),
        ToolCallProposal("get_project_status", "tool-spec-v1", "project-other-001", "revision-002", {}),
        ToolCallProposal("get_project_status", "tool-spec-v1", "project-waterplay-001", "revision-other", {}),
        ToolCallProposal("get_project_status", "tool-spec-v1", "project-waterplay-001", "revision-002", {"path": "C:/raw.mp4"}),
    ],
)
def test_untrusted_proposal_cannot_expand_tool_version_scope_revision_or_request_schema(proposal: ToolCallProposal) -> None:
    context = _context()
    decision = preflight_status_read(
        context=context,
        proposal=proposal,
        backend_request=_build_backend_attested_status_request(context=context),
    )

    assert decision.static_contract_accepted is False
    assert decision.executor_authorized is False


def test_result_redaction_accepts_only_the_selected_project_allowlist_and_byte_time_caps() -> None:
    context = _context()
    result = redact_status_result(context=context, backend_status=_status(), elapsed_ms=999)

    assert set(result.payload) == {
        "project_id", "name", "status", "updated_at", "has_editing_session", "latest_session_revision"
    }
    assert result.payload["project_id"] == "project-waterplay-001"
    assert result.redaction_summary == "selected_project_status_only"
    assert result.byte_size <= 1024
    assert result.executor_authorized is False

    with pytest.raises(ValueError, match="project"):
        redact_status_result(context=context, backend_status=_status(project_id="project-other-001"), elapsed_ms=1)
    with pytest.raises(ValueError, match="revision"):
        redact_status_result(
            context=context,
            backend_status=replace(_status(), latest_session_revision="revision-003"),
            elapsed_ms=1,
        )
    with pytest.raises(ValueError, match="timeout"):
        redact_status_result(context=context, backend_status=_status(), elapsed_ms=1001)


@pytest.mark.parametrize("phase", ["proposal_or_approval_request", "pending_human_approval"])
def test_result_redaction_rechecks_the_pinned_allowed_phase(phase: str) -> None:
    with pytest.raises(ValueError, match="phase"):
        redact_status_result(context=_context(phase=phase), backend_status=_status(), elapsed_ms=1)


def test_backend_request_cannot_be_constructed_from_untrusted_scope_or_custom_payload() -> None:
    context = _context()
    with pytest.raises(ValueError, match="backend-derived"):
        BackendDerivedStatusRequest(
            project_id="project-waterplay-001",
            source_revision="revision-002",
            request_payload={"project_id": "project-waterplay-001"},
            context_sha256=context.yujin_context.context_sha256,
        )


def test_directly_constructed_context_and_request_are_not_backend_attested() -> None:
    yujin_context = YujinContextEnvelope(project_id="project-waterplay-001", status=_status())
    direct_context = GatewayRunContext(
        profile=load_builtin_yujin_profile(),
        yujin_context=yujin_context,
        run_phase="read_only_research",
    )
    direct_request = BackendDerivedStatusRequest(
        project_id="project-waterplay-001",
        source_revision="revision-002",
        request_payload={},
        context_sha256=yujin_context.context_sha256,
    )
    proposal = ToolCallProposal("get_project_status", "tool-spec-v1", "project-waterplay-001", "revision-002", {})

    decision = preflight_status_read(context=direct_context, proposal=proposal, backend_request=direct_request)

    assert decision.static_contract_accepted is False
    assert decision.reason == "backend_attested_context_required"
    assert decision.executor_authorized is False
    with pytest.raises(ValueError, match="attested"):
        redact_status_result(context=direct_context, backend_status=_status(), elapsed_ms=1)


def test_backend_bound_request_must_carry_the_context_attestation() -> None:
    context = _context()
    proposal = ToolCallProposal("get_project_status", "tool-spec-v1", "project-waterplay-001", "revision-002", {})
    direct_request = BackendDerivedStatusRequest(
        project_id="project-waterplay-001",
        source_revision="revision-002",
        request_payload={},
        context_sha256=context.yujin_context.context_sha256,
    )

    decision = preflight_status_read(context=context, proposal=proposal, backend_request=direct_request)

    assert decision.static_contract_accepted is False
    assert decision.reason == "backend_attested_request_required"


def test_public_surface_has_no_attestation_issuing_factory() -> None:
    assert not hasattr(gateway_contract, "build_gateway_run_context")
    assert not hasattr(gateway_contract, "build_backend_status_request")

    context = GatewayRunContext(
        profile=load_builtin_yujin_profile(),
        yujin_context=YujinContextEnvelope(project_id="project-waterplay-001", status=_status()),
        run_phase="read_only_research",
    )
    request = BackendDerivedStatusRequest(
        project_id="project-waterplay-001",
        source_revision="revision-002",
        request_payload={},
        context_sha256=context.yujin_context.context_sha256,
    )
    proposal = ToolCallProposal("get_project_status", "tool-spec-v1", "project-waterplay-001", "revision-002", {})

    assert preflight_status_read(context=context, proposal=proposal, backend_request=request).static_contract_accepted is False


def test_str_subclass_with_hostile_equality_cannot_pass_untrusted_tool_proposal_checks() -> None:
    class HostileString(str):
        def __eq__(self, other: object) -> bool:
            return True

        def __ne__(self, other: object) -> bool:
            return False

    context = _context()
    proposal = ToolCallProposal(
        tool_name=HostileString("render_video"),
        tool_version=HostileString("unknown"),
        project_id=HostileString("project-other-001"),
        source_revision=HostileString("revision-other"),
        request_payload={},
    )

    decision = preflight_status_read(
        context=context,
        proposal=proposal,
        backend_request=_build_backend_attested_status_request(context=context),
    )

    assert decision.static_contract_accepted is False
    assert decision.reason == "untrusted_proposal_scalar_invalid"
