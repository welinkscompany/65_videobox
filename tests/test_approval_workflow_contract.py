from __future__ import annotations

from dataclasses import replace

import pytest

from videobox_core_engine.approval_workflow_contract import (
    ApprovalCard,
    ApprovalPreflightResult,
    ExplicitApprovalSignal,
    NO_SKILL_MANIFEST_SHA256,
    StaticProposalArtifact,
    _digest,
    advance_static_workflow,
    _build_backend_attested_approval_signal,
    build_static_approval_card,
    build_static_proposal_artifact,
    evaluate_approval_preflight,
)
from videobox_core_engine.yujin_profile_contract import load_builtin_yujin_profile


def _proposal(*, revision: str = "revision-002") -> StaticProposalArtifact:
    return build_static_proposal_artifact(
        project_id="project-waterplay-001",
        conversation_id="conversation-waterplay-001",
        run_id="run-waterplay-001",
        base_revision=revision,
        change_summary="물놀이 장면 다음에 놀이터 장면을 제안합니다.",
        rights_blocker="권리 확인이 필요합니다.",
        profile=load_builtin_yujin_profile(),
    )


def _card(*, revision: str = "revision-002", expires_at: str = "2026-07-20T12:00:00Z") -> ApprovalCard:
    return build_static_approval_card(proposal=_proposal(revision=revision), expires_at=expires_at)


def test_chat_yes_is_not_an_approval_and_has_zero_execution_side_effect() -> None:
    result = evaluate_approval_preflight(
        card=_card(),
        response="네, 승인합니다.",
        now="2026-07-20T11:00:00Z",
        current_revision="revision-002",
    )

    assert result.workflow_state == "pending_human_approval"
    assert result.decision == "chat_text_is_not_approval"
    assert result.executor_authorized is False
    assert result.side_effect_count == 0


def test_immutable_card_binds_project_revision_summary_rights_and_prompt_skill_hashes() -> None:
    proposal = _proposal()
    card = _card()

    assert card.project_id == proposal.project_id
    assert card.base_revision == "revision-002"
    assert card.change_summary == proposal.change_summary
    assert card.rights_blocker == proposal.rights_blocker
    assert card.prompt_manifest_sha256 == proposal.prompt_manifest_sha256
    assert card.skill_manifest_sha256 == NO_SKILL_MANIFEST_SHA256
    assert card.proposal_sha256 == proposal.proposal_sha256
    assert card.proposal_scope_sha256 == proposal.proposal_scope_sha256
    with pytest.raises((AttributeError, TypeError)):
        card.change_summary = "다른 변경"  # type: ignore[misc]
    with pytest.raises(ValueError, match="card|digest"):
        replace(card, base_revision="revision-999")


@pytest.mark.parametrize(
    ("response", "now", "current_revision", "decision", "state"),
    [
        (ExplicitApprovalSignal("card", "approved"), "2026-07-20T11:00:00Z", "revision-002", "authority_insufficient", "blocked"),
        ("reject", "2026-07-20T11:00:00Z", "revision-002", "chat_text_is_not_approval", "pending_human_approval"),
        (None, "2026-07-20T12:00:00Z", "revision-002", "approval_card_expired", "blocked"),
        (None, "2026-07-20T11:00:00Z", "revision-003", "base_revision_stale", "blocked"),
    ],
)
def test_reject_expire_stale_and_insufficient_authority_fail_closed_with_zero_side_effects(
    response: object, now: str, current_revision: str, decision: str, state: str
) -> None:
    result = evaluate_approval_preflight(
        card=_card(), response=response, now=now, current_revision=current_revision
    )

    assert result.decision == decision
    assert result.workflow_state == state
    assert result.executor_authorized is False
    assert result.side_effect_count == 0


def test_explicit_attested_rejection_is_terminal_but_never_executes() -> None:
    card = _card()
    response = _build_backend_attested_approval_signal(card_id=card.card_id, decision="rejected")

    result = evaluate_approval_preflight(
        card=card, response=response, now="2026-07-20T11:00:00Z", current_revision="revision-002"
    )

    assert result.workflow_state == "rejected"
    assert result.decision == "rejected_by_human"
    assert result.executor_authorized is False
    assert result.side_effect_count == 0


def test_attested_approval_only_records_static_nonexecuting_approval() -> None:
    card = _card()
    response = _build_backend_attested_approval_signal(card_id=card.card_id, decision="approved")

    result = evaluate_approval_preflight(
        card=card, response=response, now="2026-07-20T11:00:00Z", current_revision="revision-002"
    )

    assert result.workflow_state == "pending_human_approval"
    assert result.decision == "approval_recorded_static_nonexecuting"
    assert result.executor_authorized is False
    assert result.side_effect_count == 0


def test_read_only_proposal_is_only_a_static_artifact_without_an_action_or_execution_surface() -> None:
    proposal = _proposal()

    assert proposal.persistence == "static_artifact_only"
    assert proposal.executor_authorized is False
    assert proposal.proposal_scope_sha256
    assert "action" not in proposal.__class__.__dict__
    assert "execute" not in proposal.__class__.__dict__


def test_static_slice_rejects_arbitrary_skill_manifest_and_labels_scope_digest_non_executable() -> None:
    proposal = _proposal()

    assert proposal.skill_manifest_sha256 == NO_SKILL_MANIFEST_SHA256
    assert "action_sha256" not in proposal.__class__.__dict__
    with pytest.raises(ValueError, match="no-skill"):
        replace(proposal, skill_manifest_sha256="a" * 64)
    with pytest.raises(TypeError):
        build_static_proposal_artifact(
            project_id="project-waterplay-001",
            conversation_id="conversation-waterplay-001",
            run_id="run-waterplay-001",
            base_revision="revision-002",
            change_summary="물놀이 장면 다음에 놀이터 장면을 제안합니다.",
            rights_blocker="권리 확인이 필요합니다.",
            profile=load_builtin_yujin_profile(),
            skill_manifest_sha256="a" * 64,
        )


def test_direct_proposal_and_card_construction_cannot_rebind_pinned_prompt_manifest() -> None:
    proposal = _proposal()
    card = _card()
    base_proposal_fields = {
        field: getattr(proposal, field)
        for field in proposal.__dataclass_fields__
        if field != "proposal_sha256"
    }
    base_card_fields = {
        field: getattr(card, field)
        for field in card.__dataclass_fields__
        if field != "card_id"
    }

    for field_name, forged_value, expected_error in (
        ("prompt_manifest_sha256", "b" * 64, "built-in prompt"),
        ("skill_manifest_sha256", "c" * 64, "no-skill"),
    ):
        forged_proposal_fields = {**base_proposal_fields, field_name: forged_value}
        forged_proposal_fields["proposal_sha256"] = _digest(
            {
                key: forged_proposal_fields[key]
                for key in (
                    "project_id", "conversation_id", "run_id", "base_revision", "change_summary",
                    "rights_blocker", "prompt_manifest_sha256", "skill_manifest_sha256", "proposal_scope_sha256",
                )
            }
        )
        forged_card_fields = {**base_card_fields, field_name: forged_value}

        with pytest.raises(ValueError, match=expected_error):
            StaticProposalArtifact(**forged_proposal_fields)
        with pytest.raises(ValueError, match=expected_error):
            ApprovalCard(card_id=_digest(forged_card_fields), **forged_card_fields)


def test_static_workflow_permits_review_path_but_has_no_applied_transition() -> None:
    transition = advance_static_workflow(
        from_state="proposal_or_approval_request", to_state="deterministic_preflight"
    )

    assert transition.from_state == "proposal_or_approval_request"
    assert transition.to_state == "deterministic_preflight"
    assert transition.executor_authorized is False
    assert transition.side_effect_count == 0
    with pytest.raises(ValueError, match="not available|static"):
        advance_static_workflow(from_state="pending_human_approval", to_state="applied")


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"workflow_state": "blocked", "decision": "approval_card_expired", "executor_authorized": True}, "authorize"),
        ({"workflow_state": "blocked", "decision": "approval_card_expired", "side_effect_count": 1}, "side effect"),
        ({"workflow_state": "rejected", "decision": "approval_card_expired"}, "state|decision"),
        ({"workflow_state": "applied", "decision": "approval_recorded_static_nonexecuting"}, "state|decision"),
    ],
)
def test_public_preflight_result_rejects_forged_authority_side_effects_and_invalid_state_decision_pairs(
    fields: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ApprovalPreflightResult(**fields)  # type: ignore[arg-type]
