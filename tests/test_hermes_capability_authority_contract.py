from __future__ import annotations

from dataclasses import asdict
from inspect import getsource
from pathlib import Path

import pytest
import yaml

from videobox_api.hermes_capability_authority import (
    HERMES_CAPABILITY_AUTHORITY_CONTRACT,
    HermesCapabilityAuthorityConfigurationError,
    validate_static_hermes_capability_authority_request,
)
from videobox_api.hermes_capabilities import HermesCapabilityVerifier
from videobox_api import main as api_main
from videobox_api.main import create_app
from videobox_api.routers.hermes_internal import build_hermes_internal_router
from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.postgres_project_store import PostgresProjectStore


def test_static_capability_authority_names_the_future_owner_and_existing_durable_boundary() -> None:
    contract = HERMES_CAPABILITY_AUTHORITY_CONTRACT

    assert contract.schema_version == "v1"
    assert contract.issuer == "videobox-agent-gateway"
    assert contract.issuer_owner == "gateway-only"
    assert contract.issuance_enabled is False
    assert contract.signing_secret_delivery == "forbidden"
    assert contract.durable_revocation_storage_primitive == "LocalProjectStore.revoke_hermes_capability"
    assert contract.owner_authorized_revocation_writer_status == "not_deployed"
    assert contract.durable_consume_replay_boundary == "ProjectStore.consume_hermes_capability"
    assert contract.gateway_route_status == "not_deployed"
    assert contract.hermes_network_status == "preauth-network-none"
    assert contract.ordinary_api_paths == "forbidden"
    assert contract.gateway_service == "videobox-agent-gateway"
    assert contract.gateway_network == "videobox-agent-gateway-network"
    assert contract.gateway_route_mode == "gateway-only"


def test_static_capability_authority_rejects_any_activation_or_non_gateway_input() -> None:
    validate_static_hermes_capability_authority_request(issuer="videobox-agent-gateway")

    invalid_requests = (
        {"issuer": "unknown-issuer"},
        {"issuer": "videobox-agent-gateway", "signing_secret_delivery": "attempted"},
        {"issuer": "videobox-agent-gateway", "route_path": "/api/projects"},
        {"issuer": "videobox-agent-gateway", "network": "videobox-internal"},
        {
            "issuer": "videobox-agent-gateway",
            "route_path": "/internal/hermes/projects/{project_id}/status",
        },
        {"issuer": "videobox-agent-gateway", "activation_requested": True},
    )

    for request in invalid_requests:
        with pytest.raises(HermesCapabilityAuthorityConfigurationError):
            validate_static_hermes_capability_authority_request(**request)


def test_compose_fields_match_the_canonical_static_authority_contract() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))

    assert compose["x-videobox-hermes-capability-authority"] == asdict(
        HERMES_CAPABILITY_AUTHORITY_CONTRACT
    )


def test_gateway_boundary_is_not_an_active_hermes_attachment(tmp_path: Path) -> None:
    contract = HERMES_CAPABILITY_AUTHORITY_CONTRACT
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    default_app = create_app(projects_root=tmp_path)
    default_paths = {route.path for route in default_app.routes}
    conditional_router = build_hermes_internal_router(
        default_app.state.store,
        HermesCapabilityVerifier(keys={"test-key": b"test-key-must-be-at-least-thirty-two-bytes"}),
    )
    conditional_paths = {route.path for route in conditional_router.routes}

    assert contract.gateway_service not in compose["services"]
    assert contract.gateway_network not in compose["networks"]
    assert compose["services"]["videobox-hermes-agent"]["network_mode"] == "none"
    assert "/internal/hermes/projects/{project_id}/status" not in default_paths
    assert conditional_paths == {"/internal/hermes/projects/{project_id}/status"}
    assert contract.gateway_route_mode == "gateway-only"


def test_durable_revocation_is_a_storage_primitive_not_an_authorized_writer_route(tmp_path: Path) -> None:
    default_app = create_app(projects_root=tmp_path)
    default_paths = {route.path for route in default_app.routes}
    conditional_source = getsource(build_hermes_internal_router)
    main_source = getsource(api_main)

    assert LocalProjectStore.revoke_hermes_capability is PostgresProjectStore.revoke_hermes_capability
    assert "def revoke_hermes_capability" in getsource(LocalProjectStore)
    assert "store.consume_hermes_capability" in main_source
    assert "revoke_hermes_capability" not in conditional_source
    assert not any("capability" in path or "revoke" in path or "issue" in path for path in default_paths)
    assert HERMES_CAPABILITY_AUTHORITY_CONTRACT.issuance_enabled is False
    assert HERMES_CAPABILITY_AUTHORITY_CONTRACT.owner_authorized_revocation_writer_status == "not_deployed"
