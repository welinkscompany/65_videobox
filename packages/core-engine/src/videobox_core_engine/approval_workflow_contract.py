"""Static approval-card contract for the first read-only Yujin workflow slice.

This module has no provider client, database, API route, action executor, or
durable store.  It freezes the data a later, separately authorized approval
system must bind before it can even consider an editing action.  In this slice
an accepted explicit signal is recorded only as a non-executing static result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from json import dumps
import re
from typing import Literal

from videobox_core_engine.yujin_profile_contract import BUILTIN_PROMPT_MANIFEST_SHA256, YujinPromptProfile

__all__ = (
    "ApprovalCard",
    "ApprovalPreflightResult",
    "ExplicitApprovalSignal",
    "NO_SKILL_MANIFEST_SHA256",
    "StaticProposalArtifact",
    "StaticWorkflowTransition",
    "advance_static_workflow",
    "build_static_approval_card",
    "build_static_proposal_artifact",
    "evaluate_approval_preflight",
)


_BACKEND_APPROVAL_ISSUER = object()
NO_SKILL_MANIFEST_SHA256 = "e75fd2c43ff2770839405a3c5f4049cf62f200ba6aef8a3d6e824836a8d2a905"
_OPAQUE_ID = re.compile(r"[a-z][a-z0-9-]{2,127}\Z")
_REVISION_ID = re.compile(r"revision-[a-z0-9-]{1,120}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_UTC_SECONDS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_UNSAFE_SUMMARY_TEXT = re.compile(
    r"(?:https?://|[a-z]:[\\/]|\\\\|\.\.?[\\/]|credential|token|secret|password|api key|oauth|"
    r"shell|sql|filesystem|database|raw.media|캡컷|capcut|렌더|내보내|자막|대본|미디어|경로|토큰|비밀번호|암호|실행)",
    re.IGNORECASE,
)
_STATIC_TRANSITIONS = frozenset(
    {
        ("intake", "clarification_needed"),
        ("intake", "brief_candidate"),
        ("clarification_needed", "brief_candidate"),
        ("brief_candidate", "brief_confirmed"),
        ("brief_confirmed", "read_only_research"),
        ("read_only_research", "proposal_or_approval_request"),
        ("proposal_or_approval_request", "deterministic_preflight"),
        ("deterministic_preflight", "pending_human_approval"),
        ("deterministic_preflight", "blocked"),
        ("pending_human_approval", "rejected"),
        ("pending_human_approval", "cancelled"),
        ("pending_human_approval", "blocked"),
    }
)


def _canonical_json(value: object) -> str:
    return dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


def _digest(value: object) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_id(value: str, *, field_name: str) -> None:
    if type(value) is not str or _OPAQUE_ID.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be an opaque identifier")


def _require_revision(value: str) -> None:
    if type(value) is not str or _REVISION_ID.fullmatch(value) is None:
        raise ValueError("base_revision must be a revision identifier")


def _parse_utc(value: str, *, field_name: str) -> datetime:
    if type(value) is not str or _UTC_SECONDS.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a UTC seconds timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} must be a valid UTC timestamp") from error
    if parsed.tzinfo != timezone.utc:
        raise ValueError(f"{field_name} must be UTC")
    return parsed


def _require_safe_summary(value: str, *, field_name: str) -> None:
    if type(value) is not str or not value.strip() or len(value) > 280 or _UNSAFE_SUMMARY_TEXT.search(value):
        raise ValueError(f"{field_name} must be short, sanitised proposal text")


def _proposal_payload(
    *, project_id: str, conversation_id: str, run_id: str, base_revision: str,
    change_summary: str, rights_blocker: str, prompt_manifest_sha256: str,
    skill_manifest_sha256: str, proposal_scope_sha256: str,
) -> dict[str, str]:
    return {
        "project_id": project_id,
        "conversation_id": conversation_id,
        "run_id": run_id,
        "base_revision": base_revision,
        "change_summary": change_summary,
        "rights_blocker": rights_blocker,
        "prompt_manifest_sha256": prompt_manifest_sha256,
        "skill_manifest_sha256": skill_manifest_sha256,
        "proposal_scope_sha256": proposal_scope_sha256,
    }


@dataclass(frozen=True, slots=True)
class StaticProposalArtifact:
    """A reviewable static record; ``action`` deliberately cannot be invoked."""

    project_id: str
    conversation_id: str
    run_id: str
    base_revision: str
    change_summary: str
    rights_blocker: str
    prompt_manifest_sha256: str
    skill_manifest_sha256: str
    proposal_scope_sha256: str
    proposal_sha256: str
    persistence: Literal["static_artifact_only"] = "static_artifact_only"
    executor_authorized: Literal[False] = False

    def __post_init__(self) -> None:
        _require_id(self.project_id, field_name="project_id")
        _require_id(self.conversation_id, field_name="conversation_id")
        _require_id(self.run_id, field_name="run_id")
        _require_revision(self.base_revision)
        _require_safe_summary(self.change_summary, field_name="change_summary")
        _require_safe_summary(self.rights_blocker, field_name="rights_blocker")
        if (
            _SHA256.fullmatch(self.prompt_manifest_sha256) is None
            or _SHA256.fullmatch(self.skill_manifest_sha256) is None
            or _SHA256.fullmatch(self.proposal_scope_sha256) is None
            or _SHA256.fullmatch(self.proposal_sha256) is None
        ):
            raise ValueError("proposal must bind SHA-256 manifests and digests")
        if self.prompt_manifest_sha256 != BUILTIN_PROMPT_MANIFEST_SHA256:
            raise ValueError("static slice permits only the pinned built-in prompt manifest")
        if self.skill_manifest_sha256 != NO_SKILL_MANIFEST_SHA256:
            raise ValueError("static slice permits only the pinned no-skill manifest")
        if self.persistence != "static_artifact_only" or self.executor_authorized is not False:
            raise ValueError("proposal remains a non-executing static artifact")
        expected_scope = _digest(
            {
                "project_id": self.project_id,
                "base_revision": self.base_revision,
                "change_summary": self.change_summary,
                "rights_blocker": self.rights_blocker,
            }
        )
        if self.proposal_scope_sha256 != expected_scope:
            raise ValueError("proposal scope digest does not match its non-executable static scope")
        expected_proposal = _digest(
            _proposal_payload(
                project_id=self.project_id,
                conversation_id=self.conversation_id,
                run_id=self.run_id,
                base_revision=self.base_revision,
                change_summary=self.change_summary,
                rights_blocker=self.rights_blocker,
                prompt_manifest_sha256=self.prompt_manifest_sha256,
                skill_manifest_sha256=self.skill_manifest_sha256,
                proposal_scope_sha256=self.proposal_scope_sha256,
            )
        )
        if self.proposal_sha256 != expected_proposal:
            raise ValueError("proposal digest does not match its immutable fields")


def build_static_proposal_artifact(
    *, project_id: str, conversation_id: str, run_id: str, base_revision: str,
    change_summary: str, rights_blocker: str, profile: YujinPromptProfile,
) -> StaticProposalArtifact:
    """Create a static review artifact from a pinned profile, without any I/O."""
    if type(profile) is not YujinPromptProfile:
        raise ValueError("proposal requires the pinned Yujin profile")
    proposal_scope_sha256 = _digest(
        {
            "project_id": project_id,
            "base_revision": base_revision,
            "change_summary": change_summary,
            "rights_blocker": rights_blocker,
        }
    )
    payload = _proposal_payload(
        project_id=project_id,
        conversation_id=conversation_id,
        run_id=run_id,
        base_revision=base_revision,
        change_summary=change_summary,
        rights_blocker=rights_blocker,
        prompt_manifest_sha256=profile.prompt_manifest_sha256,
        skill_manifest_sha256=NO_SKILL_MANIFEST_SHA256,
        proposal_scope_sha256=proposal_scope_sha256,
    )
    return StaticProposalArtifact(
        **payload,
        proposal_sha256=_digest(payload),
    )


@dataclass(frozen=True, slots=True)
class ApprovalCard:
    """Immutable human-review card. Its scope digest is not an executable action."""

    card_id: str
    project_id: str
    conversation_id: str
    run_id: str
    proposal_sha256: str
    proposal_scope_sha256: str
    base_revision: str
    change_summary: str
    rights_blocker: str
    prompt_manifest_sha256: str
    skill_manifest_sha256: str
    expires_at: str

    def __post_init__(self) -> None:
        _require_id(self.project_id, field_name="project_id")
        _require_id(self.conversation_id, field_name="conversation_id")
        _require_id(self.run_id, field_name="run_id")
        _require_revision(self.base_revision)
        _require_safe_summary(self.change_summary, field_name="change_summary")
        _require_safe_summary(self.rights_blocker, field_name="rights_blocker")
        _parse_utc(self.expires_at, field_name="expires_at")
        digest_fields = {
            "project_id": self.project_id,
            "conversation_id": self.conversation_id,
            "run_id": self.run_id,
            "proposal_sha256": self.proposal_sha256,
            "proposal_scope_sha256": self.proposal_scope_sha256,
            "base_revision": self.base_revision,
            "change_summary": self.change_summary,
            "rights_blocker": self.rights_blocker,
            "prompt_manifest_sha256": self.prompt_manifest_sha256,
            "skill_manifest_sha256": self.skill_manifest_sha256,
            "expires_at": self.expires_at,
        }
        if any(_SHA256.fullmatch(value) is None for value in (
            self.proposal_sha256, self.proposal_scope_sha256, self.prompt_manifest_sha256, self.skill_manifest_sha256
        )) or self.card_id != _digest(digest_fields):
            raise ValueError("approval card digest does not match its immutable binding")
        if self.prompt_manifest_sha256 != BUILTIN_PROMPT_MANIFEST_SHA256:
            raise ValueError("static slice permits only the pinned built-in prompt manifest")
        if self.skill_manifest_sha256 != NO_SKILL_MANIFEST_SHA256:
            raise ValueError("static slice permits only the pinned no-skill manifest")


def build_static_approval_card(*, proposal: StaticProposalArtifact, expires_at: str) -> ApprovalCard:
    """Bind the complete static proposal to an expiring card; this does no storage."""
    if type(proposal) is not StaticProposalArtifact:
        raise ValueError("approval card requires a static proposal artifact")
    fields = {
        "project_id": proposal.project_id,
        "conversation_id": proposal.conversation_id,
        "run_id": proposal.run_id,
        "proposal_sha256": proposal.proposal_sha256,
        "proposal_scope_sha256": proposal.proposal_scope_sha256,
        "base_revision": proposal.base_revision,
        "change_summary": proposal.change_summary,
        "rights_blocker": proposal.rights_blocker,
        "prompt_manifest_sha256": proposal.prompt_manifest_sha256,
        "skill_manifest_sha256": proposal.skill_manifest_sha256,
        "expires_at": expires_at,
    }
    return ApprovalCard(card_id=_digest(fields), **fields)


@dataclass(frozen=True, slots=True)
class ExplicitApprovalSignal:
    """Structured card response, untrusted unless a later backend attests it."""

    card_id: str
    decision: Literal["approved", "rejected"]
    _backend_attestation: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.card_id) is not str or type(self.decision) is not str or self.decision not in {"approved", "rejected"}:
            raise ValueError("approval signal must be a structured card decision")
        if self._backend_attestation not in (None, _BACKEND_APPROVAL_ISSUER):
            raise ValueError("approval signal has an invalid backend attestation")

    @property
    def is_backend_attested(self) -> bool:
        return self._backend_attestation is _BACKEND_APPROVAL_ISSUER


def _build_backend_attested_approval_signal(
    *, card_id: str, decision: Literal["approved", "rejected"]
) -> ExplicitApprovalSignal:
    """Adapter-only test seam; it grants no executor capability."""
    return ExplicitApprovalSignal(card_id, decision, _BACKEND_APPROVAL_ISSUER)


@dataclass(frozen=True, slots=True)
class ApprovalPreflightResult:
    workflow_state: Literal["pending_human_approval", "rejected", "blocked"]
    decision: Literal[
        "chat_text_is_not_approval", "authority_insufficient", "approval_card_expired",
        "base_revision_stale", "approval_card_mismatch", "rejected_by_human",
        "approval_recorded_static_nonexecuting",
    ]
    executor_authorized: Literal[False] = False
    side_effect_count: Literal[0] = 0

    def __post_init__(self) -> None:
        allowed_pairs = {
            ("pending_human_approval", "chat_text_is_not_approval"),
            ("pending_human_approval", "approval_recorded_static_nonexecuting"),
            ("rejected", "rejected_by_human"),
            ("blocked", "authority_insufficient"),
            ("blocked", "approval_card_expired"),
            ("blocked", "base_revision_stale"),
            ("blocked", "approval_card_mismatch"),
        }
        if (self.workflow_state, self.decision) not in allowed_pairs:
            raise ValueError("approval preflight state and decision must be a fixed fail-closed pair")
        if self.executor_authorized is not False:
            raise ValueError("approval preflight cannot authorize execution")
        if type(self.side_effect_count) is not int or self.side_effect_count != 0:
            raise ValueError("approval preflight side effect count must be exactly zero")


@dataclass(frozen=True, slots=True)
class StaticWorkflowTransition:
    """An allowed state-edge declaration, never a mutation of persisted state."""

    from_state: str
    to_state: str
    executor_authorized: Literal[False] = False
    side_effect_count: Literal[0] = 0

    def __post_init__(self) -> None:
        if (self.from_state, self.to_state) not in _STATIC_TRANSITIONS:
            raise ValueError("workflow transition is not available in the static non-executing slice")
        if self.executor_authorized is not False or self.side_effect_count != 0:
            raise ValueError("static workflow transition cannot authorize or execute an action")


def advance_static_workflow(*, from_state: str, to_state: str) -> StaticWorkflowTransition:
    """Validate one declarative pre-approval edge without retaining or applying state."""
    return StaticWorkflowTransition(from_state=from_state, to_state=to_state)


def evaluate_approval_preflight(
    *, card: ApprovalCard, response: object, now: str, current_revision: str
) -> ApprovalPreflightResult:
    """Fail closed before every side effect; an approval never applies an action here."""
    if type(card) is not ApprovalCard:
        raise ValueError("approval preflight requires an immutable approval card")
    now_value = _parse_utc(now, field_name="now")
    _require_revision(current_revision)
    if current_revision != card.base_revision:
        return ApprovalPreflightResult("blocked", "base_revision_stale")
    if now_value >= _parse_utc(card.expires_at, field_name="expires_at"):
        return ApprovalPreflightResult("blocked", "approval_card_expired")
    if isinstance(response, str):
        return ApprovalPreflightResult("pending_human_approval", "chat_text_is_not_approval")
    if type(response) is not ExplicitApprovalSignal or not response.is_backend_attested:
        return ApprovalPreflightResult("blocked", "authority_insufficient")
    if response.card_id != card.card_id:
        return ApprovalPreflightResult("blocked", "approval_card_mismatch")
    if response.decision == "rejected":
        return ApprovalPreflightResult("rejected", "rejected_by_human")
    return ApprovalPreflightResult("pending_human_approval", "approval_recorded_static_nonexecuting")
