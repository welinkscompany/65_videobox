from __future__ import annotations

from dataclasses import dataclass


class HermesCapabilityAuthorityConfigurationError(ValueError):
    """A proposed issuer deployment exceeds the static, fail-closed contract."""


@dataclass(frozen=True)
class HermesCapabilityAuthorityContract:
    """Declaration only; this neither issues capabilities nor opens a route."""

    schema_version: str
    issuer: str
    issuer_owner: str
    issuance_enabled: bool
    signing_secret_delivery: str
    durable_revocation_storage_primitive: str
    owner_authorized_revocation_writer_status: str
    durable_consume_replay_boundary: str
    gateway_route_status: str
    ordinary_api_paths: str
    hermes_network_status: str
    gateway_service: str
    gateway_network: str
    gateway_route_mode: str


HERMES_CAPABILITY_AUTHORITY_CONTRACT = HermesCapabilityAuthorityContract(
    schema_version="v1",
    issuer="videobox-agent-gateway",
    issuer_owner="gateway-only",
    issuance_enabled=False,
    signing_secret_delivery="forbidden",
    durable_revocation_storage_primitive="LocalProjectStore.revoke_hermes_capability",
    owner_authorized_revocation_writer_status="not_deployed",
    durable_consume_replay_boundary="ProjectStore.consume_hermes_capability",
    gateway_route_status="not_deployed",
    ordinary_api_paths="forbidden",
    hermes_network_status="preauth-network-none",
    gateway_service="videobox-agent-gateway",
    gateway_network="videobox-agent-gateway-network",
    gateway_route_mode="gateway-only",
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

    if issuer != HERMES_CAPABILITY_AUTHORITY_CONTRACT.issuer:
        raise HermesCapabilityAuthorityConfigurationError("hermes_capability_issuer_forbidden")
    if signing_secret_delivery is not None:
        raise HermesCapabilityAuthorityConfigurationError("hermes_capability_secret_delivery_forbidden")
    if route_path is not None:
        raise HermesCapabilityAuthorityConfigurationError("hermes_capability_route_activation_forbidden")
    if network is not None:
        raise HermesCapabilityAuthorityConfigurationError("hermes_capability_network_activation_forbidden")
    if activation_requested:
        raise HermesCapabilityAuthorityConfigurationError("hermes_capability_activation_forbidden")
