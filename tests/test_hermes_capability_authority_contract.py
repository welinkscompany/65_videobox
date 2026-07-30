from __future__ import annotations

from dataclasses import asdict
from inspect import signature
from pathlib import Path

import pytest
import yaml

from videobox_api import hermes_capabilities
from videobox_api import hermes_capability_authority
from videobox_api.main import create_app


def test_base_and_yujin_authority_metadata_are_distinct_and_exact() -> None:
    base = getattr(
        hermes_capability_authority,
        "BASE_HERMES_CAPABILITY_AUTHORITY_CONTRACT",
        None,
    )
    deployed = (
        hermes_capability_authority.HERMES_CAPABILITY_AUTHORITY_CONTRACT
    )
    base_compose = yaml.safe_load(
        Path("compose.yaml").read_text(encoding="utf-8")
    )
    overlay = yaml.safe_load(
        Path("compose.hermes-yujin.yaml").read_text(encoding="utf-8")
    )

    assert base is not None
    assert base_compose["x-videobox-hermes-capability-authority"] == asdict(
        base
    )
    assert overlay["x-videobox-hermes-capability-authority"] == asdict(
        deployed
    )
    assert base.issuance_enabled is False
    assert base.capability_lifecycle_status == "disabled"
    assert deployed.issuance_enabled is True
    assert deployed.capability_lifecycle_status == "deployed"
    assert deployed.gateway_audit_status == "deployed_redacted"
    assert deployed.owner_authorized_revocation_writer_status == "deployed"
    assert deployed.key_replacement_mode == "coordinated_single_key_only"
    assert deployed.signing_private_key_status == "gateway_environment_only"
    assert (
        deployed.verification_public_key_status
        == "workspace_environment_only"
    )


def test_legacy_hs256_signer_router_and_create_app_injection_are_absent(
    tmp_path: Path,
) -> None:
    assert not hasattr(hermes_capabilities, "HermesCapabilitySigner")
    assert not Path(
        "services/api/src/videobox_api/routers/hermes_internal.py"
    ).exists()
    assert "hermes_capability_verifier" not in signature(
        create_app
    ).parameters
    app = create_app(projects_root=tmp_path)
    paths = {route.path for route in app.routes}
    assert "/internal/hermes/projects/{project_id}/status" not in paths


def test_authority_contract_supports_only_coordinated_single_key_replacement() -> None:
    contract = hermes_capability_authority.HERMES_CAPABILITY_AUTHORITY_CONTRACT

    assert contract.key_replacement_mode == "coordinated_single_key_only"
    rendered = repr(asdict(contract)).lower()
    for forbidden in (
        "rolling",
        "overlap",
        "multi-key",
        "automatic",
        "kms",
    ):
        assert forbidden not in rendered


def test_create_app_wires_the_environment_public_verifier_into_run_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64",
        "0EqyMnQrtKs6E2i9RhXk5tAiSrcaAWuvhSCjMsl3hzc",
    )
    monkeypatch.setenv(
        "VIDEOBOX_HERMES_CAPABILITY_KEY_ID",
        "c3-test-key-2026-07",
    )

    app = create_app(
        projects_root=tmp_path,
        agent_gateway_url="http://videobox-agent-gateway:8081",
        agent_gateway_service_token="static-service-token-at-least-32-bytes",
    )

    assert isinstance(
        app.state.hermes_run_service.capability_verifier,
        hermes_capabilities.HermesCapabilityVerifier,
    )
