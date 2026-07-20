from __future__ import annotations

from dataclasses import replace

import pytest

from videobox_core_engine.agent_gateway_contract import TOOL_SPEC_MANIFEST_SHA256
from videobox_core_engine.approval_workflow_contract import NO_SKILL_MANIFEST_SHA256
from videobox_core_engine.yujin_agent_package_contract import (
    BUILTIN_APPROVAL_WORKFLOW_MANIFEST_SHA256,
    BUILTIN_YUJIN_AGENT_PACKAGE_MANIFEST_SHA256,
    MCP_DEFAULT_DECISION,
    McpDeclarationDecision,
    McpPolicy,
    UserPreferenceConsent,
    YujinSkillSpec,
    YujinSoul,
    YujinSkillsManifest,
    evaluate_declared_mcp,
    load_builtin_yujin_agent_package,
)
from videobox_core_engine.yujin_profile_contract import BUILTIN_PROMPT_MANIFEST_SHA256


def test_builtin_yujin_agent_package_binds_the_pinned_profile_tool_and_workflow_contracts() -> None:
    package = load_builtin_yujin_agent_package()

    assert package.package_id == "yujin-agent-package"
    assert package.package_version == "yujin-agent-package-v3"
    assert package.soul.profile_id == "yujin-video-director"
    assert package.soul.prompt_manifest_sha256 == BUILTIN_PROMPT_MANIFEST_SHA256
    assert package.prompt_manifest_sha256 == BUILTIN_PROMPT_MANIFEST_SHA256
    assert package.tool_spec_manifest_sha256 == TOOL_SPEC_MANIFEST_SHA256
    assert package.workflow_manifest_sha256 == BUILTIN_APPROVAL_WORKFLOW_MANIFEST_SHA256
    assert package.skill_manifest_sha256 != NO_SKILL_MANIFEST_SHA256
    assert package.package_manifest_sha256 == BUILTIN_YUJIN_AGENT_PACKAGE_MANIFEST_SHA256
    assert tuple(skill.skill_id for skill in package.skills_manifest.skills) == (
        "describe_project_status",
        "clarify_editing_goal",
        "propose_broll_inbox_organization",
        "propose_asset_metadata_classification",
        "propose_project_organization",
        "propose_edit_guidance",
    )
    assert all(skill.executor_authorized is False for skill in package.skills_manifest.skills)


def test_static_profile_explicitly_has_no_authority_over_hermes_runtime_memory() -> None:
    package = load_builtin_yujin_agent_package()
    preferences = package.user_preferences_schema

    assert package.soul.role == "video_editing_operations_assistant"
    assert preferences.project_data_ssot == "videobox_project_editor_asset_db"
    assert preferences.memory_runtime_authority == "hermes_runtime_owned"
    assert preferences.runtime_io == "static_profile_no_runtime_memory_authority"
    assert not hasattr(preferences, "memory_opt_in")
    assert not hasattr(preferences, "memory_retention_days")


def test_static_profile_preferences_are_immutable_without_a_memory_consent_or_retention_gate() -> None:
    preferences = UserPreferenceConsent(
        language="ko",
        copy_style="short_action_oriented",
        project_data_ssot="videobox_project_editor_asset_db",
        memory_runtime_authority="hermes_runtime_owned",
        runtime_io="static_profile_no_runtime_memory_authority",
    )

    assert preferences.memory_runtime_authority == "hermes_runtime_owned"
    assert preferences.runtime_io == "static_profile_no_runtime_memory_authority"
    with pytest.raises(ValueError, match="runtime|authority"):
        replace(preferences, memory_runtime_authority="static_contract")
    with pytest.raises((AttributeError, TypeError)):
        preferences.language = "en"  # type: ignore[misc]


@pytest.mark.parametrize(
    "mcp_name",
    [
        "filesystem.read",
        "shell.run",
        "database.query",
        "renderer.render",
        "capcut.import",
        "http.request",
        "project.mutate",
        "mem0.store",
    ],
)
def test_mcp_policy_is_default_deny_for_every_forbidden_or_unknown_mcp(mcp_name: str) -> None:
    package = load_builtin_yujin_agent_package()

    decision = evaluate_declared_mcp(package=package, mcp_name=mcp_name)

    assert package.mcp_policy.default_decision == MCP_DEFAULT_DECISION == "deny"
    assert decision.decision == "denied"
    assert decision.executor_authorized is False
    assert decision.side_effect_count == 0


def test_only_status_mcp_is_declared_and_it_is_never_an_invocation() -> None:
    package = load_builtin_yujin_agent_package()

    decision = evaluate_declared_mcp(package=package, mcp_name="get_project_status")

    assert decision.decision == "declared_read_only"
    assert decision.tool_spec_manifest_sha256 == TOOL_SPEC_MANIFEST_SHA256
    assert decision.invocation is None
    assert decision.executor_authorized is False
    assert decision.side_effect_count == 0


def test_package_rejects_tampered_skill_mcp_or_workflow_binding() -> None:
    package = load_builtin_yujin_agent_package()

    with pytest.raises(ValueError, match="package|manifest|built-in"):
        replace(package, tool_spec_manifest_sha256="0" * 64)
    with pytest.raises(ValueError, match="workflow|manifest|built-in"):
        replace(package, workflow_manifest_sha256="1" * 64)
    with pytest.raises(ValueError, match="skills|manifest|built-in"):
        replace(package.skills_manifest, manifest_sha256="2" * 64)


def test_hostile_string_subclasses_cannot_smuggle_a_skill_or_preference_value() -> None:
    class HostileString(str):
        def __eq__(self, other: object) -> bool:
            return True

        def __ne__(self, other: object) -> bool:
            return False

    with pytest.raises(ValueError, match="skill|built-in"):
        YujinSkillSpec(HostileString("render_video"), "status_summary", "get_project_status")
    with pytest.raises(ValueError, match="runtime|authority"):
        UserPreferenceConsent(
            HostileString("ko"), "short_action_oriented", "videobox_project_editor_asset_db",
            "hermes_runtime_owned", "static_profile_no_runtime_memory_authority",
        )


def test_nested_skills_manifest_and_package_reject_hostile_string_hash_bypass() -> None:
    class HostileString(str):
        def __eq__(self, other: object) -> bool:
            return True

        def __ne__(self, other: object) -> bool:
            return False

    package = load_builtin_yujin_agent_package()
    with pytest.raises(ValueError, match="skills|manifest|built-in"):
        YujinSkillsManifest(
            HostileString("yujin-skills-v1"),
            package.skills_manifest.skills,
            HostileString("0" * 64),
        )

    forged = object.__new__(YujinSkillsManifest)
    object.__setattr__(forged, "manifest_version", HostileString("yujin-skills-v1"))
    object.__setattr__(forged, "skills", package.skills_manifest.skills)
    object.__setattr__(forged, "manifest_sha256", HostileString("0" * 64))
    with pytest.raises(ValueError, match="skills|manifest|built-in"):
        replace(package, skills_manifest=forged)


def test_skills_manifest_rejects_tuple_subclasses_and_non_skill_nested_values() -> None:
    package = load_builtin_yujin_agent_package()

    class HostileTuple(tuple):
        pass

    with pytest.raises(ValueError, match="skills|manifest|built-in"):
        YujinSkillsManifest(
            "yujin-skills-v1",
            HostileTuple(package.skills_manifest.skills),
            package.skills_manifest.manifest_sha256,
        )

    class HostileSkill:
        def __eq__(self, other: object) -> bool:
            return True

        def __ne__(self, other: object) -> bool:
            return False

    forged_skill = HostileSkill()
    with pytest.raises(ValueError, match="skills|manifest|built-in"):
        YujinSkillsManifest(
            "yujin-skills-v1",
            (forged_skill, *package.skills_manifest.skills[1:]),
            package.skills_manifest.manifest_sha256,
        )


def test_package_rejects_hostile_nested_preference_schema_version() -> None:
    class HostileString(str):
        def __eq__(self, other: object) -> bool:
            return True

        def __ne__(self, other: object) -> bool:
            return False

    package = load_builtin_yujin_agent_package()
    forged_preferences = object.__new__(UserPreferenceConsent)
    object.__setattr__(forged_preferences, "language", "ko")
    object.__setattr__(forged_preferences, "copy_style", "short_action_oriented")
    object.__setattr__(forged_preferences, "project_data_ssot", "videobox_project_editor_asset_db")
    object.__setattr__(forged_preferences, "memory_runtime_authority", "hermes_runtime_owned")
    object.__setattr__(forged_preferences, "runtime_io", "static_profile_no_runtime_memory_authority")
    object.__setattr__(forged_preferences, "schema_version", HostileString("yujin-static-profile-preferences-v3"))

    with pytest.raises(ValueError, match="soul|user preference|schema"):
        replace(package, user_preferences_schema=forged_preferences)


def test_package_rejects_forged_nested_preferences_even_when_schema_version_is_valid() -> None:
    package = load_builtin_yujin_agent_package()
    forged_preferences = object.__new__(UserPreferenceConsent)
    object.__setattr__(forged_preferences, "language", "ko")
    object.__setattr__(forged_preferences, "copy_style", "short_action_oriented")
    object.__setattr__(forged_preferences, "project_data_ssot", "videobox_project_editor_asset_db")
    object.__setattr__(forged_preferences, "memory_runtime_authority", "static_contract")
    object.__setattr__(forged_preferences, "runtime_io", "static_profile_no_runtime_memory_authority")
    object.__setattr__(forged_preferences, "schema_version", "yujin-static-profile-preferences-v3")

    with pytest.raises(ValueError, match="user preference|memory|schema"):
        replace(package, user_preferences_schema=forged_preferences)


def test_package_rejects_constructor_bypassed_soul_or_mcp_policy() -> None:
    package = load_builtin_yujin_agent_package()
    forged_soul = object.__new__(YujinSoul)
    object.__setattr__(forged_soul, "soul_version", "yujin-soul-v2")
    object.__setattr__(forged_soul, "profile_id", "yujin-video-director")
    object.__setattr__(forged_soul, "prompt_manifest_sha256", BUILTIN_PROMPT_MANIFEST_SHA256)
    object.__setattr__(forged_soul, "role", "video_editing_operations_assistant")
    object.__setattr__(forged_soul, "copy_style", "short_action_oriented_korean")
    object.__setattr__(forged_soul, "authority", "authorizing")
    with pytest.raises(ValueError, match="soul|built-in|profile"):
        replace(package, soul=forged_soul)

    forged_policy = object.__new__(McpPolicy)
    object.__setattr__(forged_policy, "policy_version", "yujin-mcp-policy-v1")
    object.__setattr__(forged_policy, "default_decision", "allow")
    object.__setattr__(forged_policy, "declared_mcp", ("get_project_status",))
    object.__setattr__(forged_policy, "tool_spec_manifest_sha256", TOOL_SPEC_MANIFEST_SHA256)
    object.__setattr__(forged_policy, "invocation", None)
    with pytest.raises(ValueError, match="MCP|policy|built-in"):
        replace(package, mcp_policy=forged_policy)


def test_package_rejects_constructor_bypassed_skills_manifest_with_pinned_hash() -> None:
    package = load_builtin_yujin_agent_package()
    forged_manifest = object.__new__(YujinSkillsManifest)
    object.__setattr__(forged_manifest, "manifest_version", "yujin-skills-v1")
    object.__setattr__(forged_manifest, "skills", ())
    object.__setattr__(forged_manifest, "manifest_sha256", package.skills_manifest.manifest_sha256)

    with pytest.raises(ValueError, match="skills|manifest|built-in"):
        replace(package, skills_manifest=forged_manifest)


def test_mcp_decision_rejects_boolean_side_effect_count() -> None:
    with pytest.raises(ValueError, match="side effect"):
        McpDeclarationDecision("denied", None, side_effect_count=False)  # type: ignore[arg-type]
