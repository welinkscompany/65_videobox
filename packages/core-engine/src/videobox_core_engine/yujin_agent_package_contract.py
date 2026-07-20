"""Pinned, non-executing Yujin Agent Package v1.

This is configuration-as-contract, not a Hermes profile, MCP client, memory
store, provider adapter, or executor.  It tells a later separately authorised
runtime which fixed policy artifacts it must bind before it can even consider
opening a narrow route.  Every declaration in this module has zero side
effects and fails closed by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from re import fullmatch
from typing import Literal

from videobox_core_engine.agent_gateway_contract import TOOL_SPEC_MANIFEST_SHA256
from videobox_core_engine.approval_workflow_contract import (
    APPROVAL_WORKFLOW_CONTRACT_VERSION,
    BUILTIN_APPROVAL_WORKFLOW_MANIFEST_SHA256,
)
from videobox_core_engine.yujin_profile_contract import BUILTIN_PROMPT_MANIFEST_SHA256, PROFILE_ID

__all__ = (
    "BUILTIN_APPROVAL_WORKFLOW_MANIFEST_SHA256",
    "BUILTIN_YUJIN_AGENT_PACKAGE_MANIFEST_SHA256",
    "MCP_DEFAULT_DECISION",
    "McpDeclarationDecision",
    "McpPolicy",
    "UserPreferenceConsent",
    "YujinAgentPackage",
    "YujinSkillSpec",
    "YujinSoul",
    "YujinSkillsManifest",
    "evaluate_declared_mcp",
    "load_builtin_yujin_agent_package",
)


PACKAGE_ID = "yujin-agent-package"
PACKAGE_VERSION = "yujin-agent-package-v1"
SOUL_VERSION = "yujin-soul-v1"
USER_PREFERENCES_VERSION = "yujin-user-preferences-v1"
SKILLS_MANIFEST_VERSION = "yujin-skills-v1"
MCP_POLICY_VERSION = "yujin-mcp-policy-v1"
MCP_DEFAULT_DECISION = "deny"
_SHA256 = r"[0-9a-f]{64}"
_ALLOWED_SKILLS = (
    ("describe_project_status", "status_summary", "get_project_status"),
    ("interview_video_goal", "clarification_question", None),
    ("propose_without_action", "actionless_proposal", None),
)
def _canonical_json(value: object) -> str:
    return dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


def _digest(value: object) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_sha(value: str, *, field_name: str) -> None:
    if type(value) is not str or fullmatch(_SHA256, value) is None:
        raise ValueError(f"{field_name} must be a SHA-256 literal")


@dataclass(frozen=True, slots=True)
class YujinSoul:
    """The fixed role and tone; no tool or model instruction is executable."""

    soul_version: Literal["yujin-soul-v1"]
    profile_id: Literal["yujin-video-director"]
    prompt_manifest_sha256: str
    role: Literal["video_director_read_only"]
    copy_style: Literal["short_action_oriented_korean"]
    authority: Literal["non_authorizing"]

    def __post_init__(self) -> None:
        if (
            any(type(value) is not str for value in (
                self.soul_version, self.profile_id, self.prompt_manifest_sha256, self.role, self.copy_style, self.authority,
            ))
            or
            self.soul_version != SOUL_VERSION or self.profile_id != PROFILE_ID
            or self.prompt_manifest_sha256 != BUILTIN_PROMPT_MANIFEST_SHA256
            or self.role != "video_director_read_only" or self.copy_style != "short_action_oriented_korean"
            or self.authority != "non_authorizing"
        ):
            raise ValueError("Yujin soul must use the fixed built-in profile policy")


@dataclass(frozen=True, slots=True)
class UserPreferenceConsent:
    """Schema only: v1 retains no user file and never opts into long-term memory."""

    language: Literal["ko"]
    copy_style: Literal["short_action_oriented"]
    memory_opt_in: Literal[False]
    memory_scope: Literal["none"]
    memory_retention_days: Literal[0]
    schema_version: Literal["yujin-user-preferences-v1"] = USER_PREFERENCES_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.language) is not str or type(self.copy_style) is not str
            or type(self.memory_opt_in) is not bool or type(self.memory_scope) is not str or type(self.schema_version) is not str
            or
            self.language != "ko" or self.copy_style != "short_action_oriented"
            or self.memory_opt_in is not False or self.memory_scope != "none"
            or type(self.memory_retention_days) is not int or self.memory_retention_days != 0
            or self.schema_version != USER_PREFERENCES_VERSION
        ):
            raise ValueError("memory requires a separate opt-in scope and retention gate")


def _is_builtin_user_preferences(value: object) -> bool:
    """Defend the package boundary even if hostile code bypassed the dataclass constructor."""
    return (
        type(value) is UserPreferenceConsent
        and type(value.language) is str
        and type(value.copy_style) is str
        and type(value.memory_opt_in) is bool
        and type(value.memory_scope) is str
        and type(value.memory_retention_days) is int
        and type(value.schema_version) is str
        and value.language == "ko"
        and value.copy_style == "short_action_oriented"
        and value.memory_opt_in is False
        and value.memory_scope == "none"
        and value.memory_retention_days == 0
        and value.schema_version == USER_PREFERENCES_VERSION
    )


@dataclass(frozen=True, slots=True)
class YujinSkillSpec:
    """A response-shaped declaration, never a callable implementation."""

    skill_id: str
    response_type: Literal["status_summary", "clarification_question", "actionless_proposal"]
    declared_mcp: Literal["get_project_status"] | None
    executor_authorized: Literal[False] = False

    def __post_init__(self) -> None:
        if (
            type(self.skill_id) is not str or type(self.response_type) is not str
            or (self.declared_mcp is not None and type(self.declared_mcp) is not str)
            or (self.skill_id, self.response_type, self.declared_mcp) not in _ALLOWED_SKILLS
        ):
            raise ValueError("Yujin skills must use the fixed read-only built-in declarations")
        if self.executor_authorized is not False:
            raise ValueError("Yujin skill declarations cannot authorize execution")


_BUILTIN_SKILLS = (
    YujinSkillSpec("describe_project_status", "status_summary", "get_project_status"),
    YujinSkillSpec("interview_video_goal", "clarification_question", None),
    YujinSkillSpec("propose_without_action", "actionless_proposal", None),
)
_SKILLS_PAYLOAD = {
    "version": SKILLS_MANIFEST_VERSION,
    "skills": [
        {"skill_id": skill.skill_id, "response_type": skill.response_type, "declared_mcp": skill.declared_mcp,
         "executor_authorized": skill.executor_authorized}
        for skill in _BUILTIN_SKILLS
    ],
}
BUILTIN_YUJIN_SKILLS_MANIFEST_SHA256 = "d757dd5a7e4dcfd44379bc272b3a898ee9bc2d0c01d4ef3c22a14268b5eb343e"


@dataclass(frozen=True, slots=True)
class YujinSkillsManifest:
    manifest_version: Literal["yujin-skills-v1"]
    skills: tuple[YujinSkillSpec, ...]
    manifest_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.manifest_version) is not str or type(self.manifest_sha256) is not str
            or type(self.skills) is not tuple
            or any(type(skill) is not YujinSkillSpec for skill in self.skills)
            or self.manifest_version != SKILLS_MANIFEST_VERSION or self.skills != _BUILTIN_SKILLS
        ):
            raise ValueError("Yujin skills manifest must contain the fixed built-in skills")
        if self.manifest_sha256 != BUILTIN_YUJIN_SKILLS_MANIFEST_SHA256 or self.manifest_sha256 != _digest(_SKILLS_PAYLOAD):
            raise ValueError("Yujin skills manifest must use the pinned built-in manifest")


def _is_builtin_skills_manifest(value: object) -> bool:
    """Revalidate every response-only skill after a hostile constructor bypass."""
    if (
        type(value) is not YujinSkillsManifest
        or type(value.manifest_version) is not str
        or type(value.manifest_sha256) is not str
        or type(value.skills) is not tuple
        or value.manifest_version != SKILLS_MANIFEST_VERSION
        or value.manifest_sha256 != BUILTIN_YUJIN_SKILLS_MANIFEST_SHA256
        or len(value.skills) != len(_ALLOWED_SKILLS)
        or any(type(skill) is not YujinSkillSpec for skill in value.skills)
    ):
        return False
    actual = tuple(
        (skill.skill_id, skill.response_type, skill.declared_mcp, skill.executor_authorized)
        for skill in value.skills
    )
    expected = tuple((*definition, False) for definition in _ALLOWED_SKILLS)
    return (
        all(
            type(skill.skill_id) is str
            and type(skill.response_type) is str
            and (skill.declared_mcp is None or type(skill.declared_mcp) is str)
            and type(skill.executor_authorized) is bool
            for skill in value.skills
        )
        and actual == expected
    )


@dataclass(frozen=True, slots=True)
class McpPolicy:
    """No server endpoint or transport exists here; this is a deny-by-default registry."""

    policy_version: Literal["yujin-mcp-policy-v1"]
    default_decision: Literal["deny"]
    declared_mcp: tuple[Literal["get_project_status"], ...]
    tool_spec_manifest_sha256: str
    invocation: None = None

    def __post_init__(self) -> None:
        if (
            type(self.policy_version) is not str or type(self.default_decision) is not str
            or type(self.declared_mcp) is not tuple
            or any(type(name) is not str for name in self.declared_mcp)
            or type(self.tool_spec_manifest_sha256) is not str
            or
            self.policy_version != MCP_POLICY_VERSION or self.default_decision != MCP_DEFAULT_DECISION
            or self.declared_mcp != ("get_project_status",)
            or self.tool_spec_manifest_sha256 != TOOL_SPEC_MANIFEST_SHA256 or self.invocation is not None
        ):
            raise ValueError("Yujin MCP policy is fixed default-deny declaration-only status access")


def _is_builtin_soul(value: object) -> bool:
    """Recheck immutable role fields at the package boundary after constructor bypass."""
    return (
        type(value) is YujinSoul
        and all(type(field) is str for field in (
            value.soul_version, value.profile_id, value.prompt_manifest_sha256, value.role, value.copy_style, value.authority,
        ))
        and value.soul_version == SOUL_VERSION
        and value.profile_id == PROFILE_ID
        and value.prompt_manifest_sha256 == BUILTIN_PROMPT_MANIFEST_SHA256
        and value.role == "video_director_read_only"
        and value.copy_style == "short_action_oriented_korean"
        and value.authority == "non_authorizing"
    )


def _is_builtin_mcp_policy(value: object) -> bool:
    """MCP must remain a declaration-only default-deny registry at this boundary."""
    return (
        type(value) is McpPolicy
        and type(value.policy_version) is str
        and type(value.default_decision) is str
        and type(value.declared_mcp) is tuple
        and all(type(name) is str for name in value.declared_mcp)
        and type(value.tool_spec_manifest_sha256) is str
        and value.policy_version == MCP_POLICY_VERSION
        and value.default_decision == MCP_DEFAULT_DECISION
        and value.declared_mcp == ("get_project_status",)
        and value.tool_spec_manifest_sha256 == TOOL_SPEC_MANIFEST_SHA256
        and value.invocation is None
    )


@dataclass(frozen=True, slots=True)
class McpDeclarationDecision:
    decision: Literal["declared_read_only", "denied"]
    tool_spec_manifest_sha256: str | None
    invocation: None = None
    executor_authorized: Literal[False] = False
    side_effect_count: Literal[0] = 0

    def __post_init__(self) -> None:
        valid = {
            ("declared_read_only", TOOL_SPEC_MANIFEST_SHA256),
            ("denied", None),
        }
        if (
            type(self.decision) is not str
            or (self.tool_spec_manifest_sha256 is not None and type(self.tool_spec_manifest_sha256) is not str)
            or (self.decision, self.tool_spec_manifest_sha256) not in valid
        ):
            raise ValueError("MCP decision must be an exact static declaration or denial")
        if (
            self.invocation is not None or type(self.executor_authorized) is not bool or self.executor_authorized is not False
            or type(self.side_effect_count) is not int or self.side_effect_count != 0
        ):
            raise ValueError("MCP declaration decision cannot invoke, authorize execution, or report side effects")


@dataclass(frozen=True, slots=True)
class YujinAgentPackage:
    package_id: Literal["yujin-agent-package"]
    package_version: Literal["yujin-agent-package-v1"]
    soul: YujinSoul
    user_preferences_schema: UserPreferenceConsent
    skills_manifest: YujinSkillsManifest
    mcp_policy: McpPolicy
    prompt_manifest_sha256: str
    tool_spec_manifest_sha256: str
    workflow_manifest_sha256: str
    skill_manifest_sha256: str
    package_manifest_sha256: str

    def __post_init__(self) -> None:
        if (
            any(type(value) is not str for value in (
                self.package_id, self.package_version, self.prompt_manifest_sha256, self.tool_spec_manifest_sha256,
                self.workflow_manifest_sha256, self.skill_manifest_sha256, self.package_manifest_sha256,
            ))
            or self.package_id != PACKAGE_ID or self.package_version != PACKAGE_VERSION
        ):
            raise ValueError("Yujin package must use the built-in package identifier and version")
        if (
            not _is_builtin_soul(self.soul) or not _is_builtin_user_preferences(self.user_preferences_schema)
        ):
            raise ValueError("Yujin package requires fixed soul and user preference schema")
        if not _is_builtin_skills_manifest(self.skills_manifest) or not _is_builtin_mcp_policy(self.mcp_policy):
            raise ValueError("Yujin package requires fixed skills and MCP policy")
        if (
            type(self.skills_manifest.manifest_version) is not str
            or type(self.skills_manifest.manifest_sha256) is not str
            or
            self.prompt_manifest_sha256 != BUILTIN_PROMPT_MANIFEST_SHA256
            or self.soul.prompt_manifest_sha256 != self.prompt_manifest_sha256
            or self.tool_spec_manifest_sha256 != TOOL_SPEC_MANIFEST_SHA256
            or self.mcp_policy.tool_spec_manifest_sha256 != self.tool_spec_manifest_sha256
            or self.workflow_manifest_sha256 != BUILTIN_APPROVAL_WORKFLOW_MANIFEST_SHA256
            or self.skill_manifest_sha256 != BUILTIN_YUJIN_SKILLS_MANIFEST_SHA256
            or self.skills_manifest.manifest_sha256 != self.skill_manifest_sha256
        ):
            raise ValueError("Yujin package manifest bindings must use the pinned built-in contracts")
        expected = _digest(_package_payload(self))
        if self.package_manifest_sha256 != BUILTIN_YUJIN_AGENT_PACKAGE_MANIFEST_SHA256 or self.package_manifest_sha256 != expected:
            raise ValueError("Yujin package manifest does not match its fixed static artifacts")


def _package_payload(package: YujinAgentPackage) -> dict[str, object]:
    return {
        "package_id": package.package_id,
        "package_version": package.package_version,
        "soul_version": package.soul.soul_version,
        "prompt_manifest_sha256": package.prompt_manifest_sha256,
        "user_preferences_schema_version": package.user_preferences_schema.schema_version,
        "skills_manifest_sha256": package.skill_manifest_sha256,
        "mcp_policy_version": package.mcp_policy.policy_version,
        "tool_spec_manifest_sha256": package.tool_spec_manifest_sha256,
        "workflow_contract_version": APPROVAL_WORKFLOW_CONTRACT_VERSION,
        "workflow_manifest_sha256": package.workflow_manifest_sha256,
    }


BUILTIN_YUJIN_AGENT_PACKAGE_MANIFEST_SHA256 = "d9c9d2cfb83a0340d58a955d65f7560157105d9b1b592961881e554cce02074a"


def load_builtin_yujin_agent_package() -> YujinAgentPackage:
    """Load the only static package. No provider, runtime, memory, or MCP is opened."""
    return YujinAgentPackage(
        package_id=PACKAGE_ID,
        package_version=PACKAGE_VERSION,
        soul=YujinSoul(
            soul_version=SOUL_VERSION,
            profile_id=PROFILE_ID,
            prompt_manifest_sha256=BUILTIN_PROMPT_MANIFEST_SHA256,
            role="video_director_read_only",
            copy_style="short_action_oriented_korean",
            authority="non_authorizing",
        ),
        user_preferences_schema=UserPreferenceConsent(
            language="ko", copy_style="short_action_oriented", memory_opt_in=False, memory_scope="none", memory_retention_days=0,
        ),
        skills_manifest=YujinSkillsManifest(
            manifest_version=SKILLS_MANIFEST_VERSION,
            skills=_BUILTIN_SKILLS,
            manifest_sha256=BUILTIN_YUJIN_SKILLS_MANIFEST_SHA256,
        ),
        mcp_policy=McpPolicy(
            policy_version=MCP_POLICY_VERSION,
            default_decision=MCP_DEFAULT_DECISION,
            declared_mcp=("get_project_status",),
            tool_spec_manifest_sha256=TOOL_SPEC_MANIFEST_SHA256,
        ),
        prompt_manifest_sha256=BUILTIN_PROMPT_MANIFEST_SHA256,
        tool_spec_manifest_sha256=TOOL_SPEC_MANIFEST_SHA256,
        workflow_manifest_sha256=BUILTIN_APPROVAL_WORKFLOW_MANIFEST_SHA256,
        skill_manifest_sha256=BUILTIN_YUJIN_SKILLS_MANIFEST_SHA256,
        package_manifest_sha256=BUILTIN_YUJIN_AGENT_PACKAGE_MANIFEST_SHA256,
    )


def evaluate_declared_mcp(*, package: YujinAgentPackage, mcp_name: object) -> McpDeclarationDecision:
    """Classify only a declaration. It cannot return a callable or perform I/O."""
    if type(package) is not YujinAgentPackage:
        raise ValueError("MCP declaration requires the pinned Yujin agent package")
    if type(mcp_name) is str and mcp_name == "get_project_status":
        return McpDeclarationDecision("declared_read_only", TOOL_SPEC_MANIFEST_SHA256)
    # Unknown names, including every unsafe category, receive the same no-detail
    # denial so an untrusted model cannot discover a larger tool surface.
    return McpDeclarationDecision("denied", None)
