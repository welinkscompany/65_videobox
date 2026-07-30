from __future__ import annotations

from dataclasses import dataclass


class HermesCapabilityAuthorityConfigurationError(ValueError):
    """A proposed issuer deployment exceeds the static, fail-closed contract."""


@dataclass(frozen=True)
class HermesCapabilityAuthorityContract:
    """Deployment metadata; it never grants capability authority by itself."""

    schema_version: str
    issuer: str
    issuer_owner: str
    issuance_enabled: bool
    signing_secret_delivery: str
    durable_revocation_storage_primitive: str
    owner_authorized_revocation_writer_status: str
    durable_consume_replay_boundary: str
    capability_gateway_route_status: str
    signing_private_key_status: str
    verification_public_key_status: str
    capability_lifecycle_status: str
    gateway_audit_status: str
    key_replacement_mode: str
    ordinary_api_paths: str
    preauth_hermes_network_status: str
    yujin_topology_status: str
    gateway_service_status: str
    gateway_service: str
    gateway_api_network: str
    gateway_network: str
    gateway_route_mode: str


BASE_HERMES_CAPABILITY_AUTHORITY_CONTRACT = HermesCapabilityAuthorityContract(
    schema_version="v1",
    issuer="videobox-agent-gateway",
    issuer_owner="gateway-only",
    issuance_enabled=False,
    signing_secret_delivery="forbidden",
    durable_revocation_storage_primitive="LocalProjectStore.revoke_hermes_capability",
    owner_authorized_revocation_writer_status="not_deployed",
    durable_consume_replay_boundary="ProjectStore.consume_hermes_capability",
    capability_gateway_route_status="not_deployed",
    signing_private_key_status="not_deployed",
    verification_public_key_status="not_deployed",
    capability_lifecycle_status="disabled",
    gateway_audit_status="disabled",
    key_replacement_mode="not_deployed",
    ordinary_api_paths="forbidden",
    preauth_hermes_network_status="network_mode_none",
    yujin_topology_status="deployed",
    gateway_service_status="health_only",
    gateway_service="videobox-agent-gateway",
    gateway_api_network="videobox-agent-gateway-api-network",
    gateway_network="videobox-agent-gateway-network",
    gateway_route_mode="gateway-only",
)

HERMES_CAPABILITY_AUTHORITY_CONTRACT = HermesCapabilityAuthorityContract(
    schema_version="v1",
    issuer="videobox-agent-gateway",
    issuer_owner="gateway-only",
    issuance_enabled=True,
    signing_secret_delivery="gateway_private_environment_only",
    durable_revocation_storage_primitive=(
        "ProjectStore.revoke_issued_hermes_capabilities"
    ),
    owner_authorized_revocation_writer_status="deployed",
    durable_consume_replay_boundary=(
        "ProjectStore.consume_registered_hermes_capability"
    ),
    capability_gateway_route_status="existing_reserve_attach_stream_only",
    signing_private_key_status="gateway_environment_only",
    verification_public_key_status="workspace_environment_only",
    capability_lifecycle_status="deployed",
    gateway_audit_status="deployed_redacted",
    key_replacement_mode="coordinated_single_key_only",
    ordinary_api_paths="forbidden",
    preauth_hermes_network_status="network_mode_none",
    yujin_topology_status="deployed",
    gateway_service_status="capability_lifecycle_deployed",
    gateway_service="videobox-agent-gateway",
    gateway_api_network="videobox-agent-gateway-api-network",
    gateway_network="videobox-agent-gateway-network",
    gateway_route_mode="existing_reserve_attach_stream_only",
)


def validate_static_hermes_capability_authority_request(
    *,
    issuer: str,
    signing_secret_delivery: str | None = None,
    route_path: str | None = None,
    network: str | None = None,
    activation_requested: bool = False,
) -> None:
    """Allow only an inert declaration for the one future gateway-owned issuer."""

    if issuer != BASE_HERMES_CAPABILITY_AUTHORITY_CONTRACT.issuer:
        raise HermesCapabilityAuthorityConfigurationError("hermes_capability_issuer_forbidden")
    if signing_secret_delivery is not None:
        raise HermesCapabilityAuthorityConfigurationError("hermes_capability_secret_delivery_forbidden")
    if route_path is not None:
        raise HermesCapabilityAuthorityConfigurationError("hermes_capability_route_activation_forbidden")
    if network is not None:
        raise HermesCapabilityAuthorityConfigurationError("hermes_capability_network_activation_forbidden")
    if activation_requested:
        raise HermesCapabilityAuthorityConfigurationError("hermes_capability_activation_forbidden")
