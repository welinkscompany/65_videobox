from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from videobox_agent_gateway.context_capabilities import YujinCapabilityIssuer
from videobox_api.agent_gateway_client import (
    AgentGatewayClient,
    AgentGatewayHealth,
    AgentGatewayUnavailable,
)
from videobox_api.hermes_operational_status import HermesOperationalStatusService
from videobox_api.main import create_app
from videobox_api.models import HermesYujinStatusResponse


SERVICE_TOKEN = "workspace-service-token-that-is-at-least-32"


def gateway_health(
    now: datetime,
    **patch,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "ready",
        "scope": "gateway_http_process",
        "gateway_configured": True,
        "capability_routes_ready": True,
        "hermes_http_ready": True,
        "provider_ready": False,
        "chat_ready": False,
        "degraded": False,
        "observation_epoch": "epoch-a",
        "process_started_at": now - timedelta(minutes=1),
        "provider_observed_at": None,
        "last_chat_verified_at": None,
        "evidence_valid_until": None,
        "status_basis": "gateway_observation",
    }
    payload.update(patch)
    return payload


class _HealthResponse:
    status_code = 200
    is_redirect = False

    def __init__(self, payload: object) -> None:
        self._payload = payload

    def json(self):
        return self._payload


class _HealthHttp:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.calls: list[tuple[str, str]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def get(self, path: str):
        self.calls.append(("GET", path))
        return _HealthResponse(self.payload)


class _GatewaySequence:
    def __init__(self, *results: object) -> None:
        self.results = list(results)
        self.calls = 0

    async def get_health(self) -> AgentGatewayHealth:
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return AgentGatewayHealth.model_validate(result)


def test_unconfigured_global_status_is_explicit_and_strict(
    tmp_path: Path,
) -> None:
    response = TestClient(create_app(projects_root=tmp_path)).get(
        "/api/hermes-yujin/status"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "state": "not_configured",
        "http_ready": False,
        "provider_ready": False,
        "chat_verified": False,
        "checked_at": payload["checked_at"],
        "last_chat_verified_at": None,
        "restart_available": False,
        "status_basis": "application_path",
    }
    assert datetime.fromisoformat(payload["checked_at"]).tzinfo is not None


def test_gateway_health_uses_a_short_independent_timeout_and_strict_dto() -> None:
    now = datetime(2026, 7, 30, 1, tzinfo=UTC)
    http = _HealthHttp(gateway_health(now))
    factory_calls: list[dict[str, object]] = []

    def factory(**kwargs):
        factory_calls.append(kwargs)
        return http

    client = AgentGatewayClient(
        base_url="http://videobox-agent-gateway:8081",
        service_token=SERVICE_TOKEN,
        http_client_factory=factory,
    )

    health = asyncio.run(client.get_health())

    assert health.observation_epoch == "epoch-a"
    assert http.calls == [("GET", "/health")]
    assert factory_calls == [{
        "base_url": "http://videobox-agent-gateway:8081",
        "timeout": 3.0,
    }]

    invalid_http = _HealthHttp(gateway_health(now, leaked_secret="PRIVATE"))
    invalid_client = AgentGatewayClient(
        base_url="http://videobox-agent-gateway:8081",
        service_token=SERVICE_TOKEN,
        http_client_factory=lambda **_: invalid_http,
    )
    with pytest.raises(
        AgentGatewayUnavailable,
        match="^agent_gateway_status_unavailable$",
    ) as caught:
        asyncio.run(invalid_client.get_health())
    assert "PRIVATE" not in str(caught.value)


def test_actual_gateway_iso_json_round_trips_to_exact_http_ready_state() -> None:
    now = datetime(2026, 7, 30, 1, 15, tzinfo=UTC)

    async def probe() -> bool:
        return True

    from videobox_agent_gateway.main import create_app as create_gateway_app

    gateway_response = TestClient(create_gateway_app(
        hermes_client=object(),
        service_token="service-secret-that-is-at-least-32-bytes",
        capability_issuer=YujinCapabilityIssuer(
            key_id="round-trip-test-key",
            private_key=b"\x22" * 32,
            now=lambda: now,
            capability_id_factory=lambda: "round-trip-capability",
        ),
        hermes_http_probe=probe,
        operational_clock=lambda: now,
        observation_epoch="epoch-json-round-trip",
    )).get("/health")
    assert gateway_response.status_code == 200
    assert gateway_response.json()["process_started_at"] == (
        "2026-07-30T01:15:00Z"
    )
    http = _HealthHttp(gateway_response.json())
    client = AgentGatewayClient(
        base_url="http://videobox-agent-gateway:8081",
        service_token=SERVICE_TOKEN,
        http_client_factory=lambda **_: http,
    )
    service = HermesOperationalStatusService(client, now=lambda: now)

    status = asyncio.run(service.get_status())

    assert status.state == "http_ready"
    assert status.http_ready is True
    assert status.provider_ready is False
    assert status.chat_verified is False


def test_gateway_health_rejects_non_utc_and_contradictory_evidence() -> None:
    now = datetime(2026, 7, 30, 1, tzinfo=UTC)
    valid = gateway_health(
        now,
        provider_ready=True,
        chat_ready=True,
        provider_observed_at=now - timedelta(seconds=30),
        last_chat_verified_at=now - timedelta(seconds=20),
        evidence_valid_until=now + timedelta(minutes=9),
    )
    invalid_payloads = [
        {
            **valid,
            "process_started_at": datetime(
                2026,
                7,
                30,
                9,
                59,
                tzinfo=timezone(timedelta(hours=9)),
            ),
        },
        {**valid, "provider_ready": False},
        {**valid, "hermes_http_ready": False},
        {**valid, "capability_routes_ready": False},
        {**valid, "gateway_configured": False},
        {**valid, "degraded": True},
        {
            **valid,
            "provider_observed_at": valid["process_started_at"]
            - timedelta(seconds=1),
        },
        {
            **valid,
            "evidence_valid_until": valid["last_chat_verified_at"]
            - timedelta(seconds=1),
        },
    ]

    for payload in invalid_payloads:
        with pytest.raises(ValidationError):
            AgentGatewayHealth.model_validate(payload)


def test_gateway_health_rejects_degraded_without_configured_capability_path(
) -> None:
    now = datetime(2026, 7, 30, 1, tzinfo=UTC)
    degraded = gateway_health(
        now,
        gateway_configured=False,
        capability_routes_ready=False,
        hermes_http_ready=False,
        degraded=True,
        provider_observed_at=now - timedelta(seconds=30),
        last_chat_verified_at=now - timedelta(seconds=20),
        evidence_valid_until=now + timedelta(minutes=9),
    )

    with pytest.raises(ValidationError):
        AgentGatewayHealth.model_validate(degraded)


@pytest.mark.parametrize(
    ("health_patch", "expected_state"),
    [
        ({"hermes_http_ready": False}, "starting"),
        ({}, "http_ready"),
        (
            {
                "provider_ready": True,
                "provider_observed_at": datetime(
                    2026, 7, 30, 0, 59, tzinfo=UTC
                ),
                "evidence_valid_until": datetime(
                    2026, 7, 30, 1, 9, tzinfo=UTC
                ),
            },
            "provider_ready",
        ),
        (
            {
                "provider_ready": True,
                "chat_ready": True,
                "provider_observed_at": datetime(
                    2026, 7, 30, 0, 59, tzinfo=UTC
                ),
                "last_chat_verified_at": datetime(
                    2026, 7, 30, 0, 59, 30, tzinfo=UTC
                ),
                "evidence_valid_until": datetime(
                    2026, 7, 30, 1, 9, 30, tzinfo=UTC
                ),
            },
            "chat_verified",
        ),
        (
            {
                "degraded": True,
                "last_chat_verified_at": datetime(
                    2026, 7, 30, 0, 59, 30, tzinfo=UTC
                ),
                "evidence_valid_until": datetime(
                    2026, 7, 30, 1, 9, 30, tzinfo=UTC
                ),
            },
            "degraded",
        ),
    ],
)
def test_status_mapping_keeps_http_provider_chat_and_degraded_distinct(
    health_patch: dict[str, object],
    expected_state: str,
) -> None:
    now = datetime(2026, 7, 30, 1, tzinfo=UTC)
    service = HermesOperationalStatusService(
        _GatewaySequence(gateway_health(now, **health_patch)),
        now=lambda: now,
    )

    status = asyncio.run(service.get_status())

    assert status.state == expected_state
    assert status.status_basis == "application_path"
    assert status.restart_available is False


def test_gateway_unreachable_is_app_path_stopped_then_process_local_degraded(
) -> None:
    now = [datetime(2026, 7, 30, 1, tzinfo=UTC)]
    verified = gateway_health(
        now[0],
        provider_ready=True,
        chat_ready=True,
        provider_observed_at=now[0] - timedelta(seconds=30),
        last_chat_verified_at=now[0] - timedelta(seconds=20),
        evidence_valid_until=now[0] + timedelta(minutes=9),
    )
    service = HermesOperationalStatusService(
        _GatewaySequence(
            AgentGatewayUnavailable("PRIVATE first"),
            verified,
            AgentGatewayUnavailable("PRIVATE second"),
            AgentGatewayUnavailable("PRIVATE expired"),
        ),
        now=lambda: now[0],
    )

    stopped = asyncio.run(service.get_status())
    verified_status = asyncio.run(service.get_status())
    degraded = asyncio.run(service.get_status())
    now[0] += timedelta(minutes=10)
    expired = asyncio.run(service.get_status())

    assert stopped.state == "stopped"
    assert verified_status.state == "chat_verified"
    assert degraded.state == "degraded"
    assert degraded.last_chat_verified_at == verified_status.last_chat_verified_at
    assert expired.state == "stopped"
    assert expired.last_chat_verified_at == verified_status.last_chat_verified_at


def test_degraded_gateway_then_unavailable_stays_degraded_for_failure_ttl(
) -> None:
    now = [datetime(2026, 7, 30, 2, tzinfo=UTC)]
    last_chat = now[0]
    now[0] += timedelta(seconds=9)
    degraded_health = gateway_health(
        now[0],
        hermes_http_ready=False,
        degraded=True,
        provider_observed_at=last_chat,
        last_chat_verified_at=last_chat,
        evidence_valid_until=now[0] + timedelta(minutes=10),
    )
    service = HermesOperationalStatusService(
        _GatewaySequence(
            degraded_health,
            AgentGatewayUnavailable("PRIVATE unavailable"),
        ),
        now=lambda: now[0],
    )

    degraded = asyncio.run(service.get_status())
    now[0] += timedelta(minutes=9)
    unavailable = asyncio.run(service.get_status())

    assert degraded.state == "degraded"
    assert degraded.http_ready is False
    assert degraded.provider_ready is False
    assert degraded.chat_verified is False
    assert degraded.last_chat_verified_at == last_chat
    assert unavailable.state == "degraded"
    assert unavailable.last_chat_verified_at == last_chat


def test_fresh_degraded_failure_extends_ttl_beyond_old_chat_age() -> None:
    started_at = datetime(2026, 7, 30, 2, tzinfo=UTC)
    now = [started_at]
    verified = gateway_health(
        started_at,
        process_started_at=started_at - timedelta(minutes=1),
        provider_ready=True,
        chat_ready=True,
        provider_observed_at=started_at,
        last_chat_verified_at=started_at,
        evidence_valid_until=started_at + timedelta(minutes=10),
    )
    failure_at = started_at + timedelta(minutes=10, seconds=1)
    degraded = gateway_health(
        failure_at,
        process_started_at=started_at - timedelta(minutes=1),
        hermes_http_ready=False,
        degraded=True,
        provider_observed_at=started_at,
        last_chat_verified_at=started_at,
        evidence_valid_until=failure_at + timedelta(minutes=10),
    )
    service = HermesOperationalStatusService(
        _GatewaySequence(
            verified,
            degraded,
            AgentGatewayUnavailable("PRIVATE unavailable"),
        ),
        now=lambda: now[0],
    )

    assert asyncio.run(service.get_status()).state == "chat_verified"
    now[0] = failure_at
    degraded_status = asyncio.run(service.get_status())
    unavailable_status = asyncio.run(service.get_status())

    assert degraded_status.state == "degraded"
    assert degraded_status.last_chat_verified_at == started_at
    assert unavailable_status.state == "degraded"
    assert unavailable_status.last_chat_verified_at == started_at


def test_epoch_change_and_expired_or_future_evidence_cannot_elevate_status(
) -> None:
    now = [datetime(2026, 7, 30, 1, tzinfo=UTC)]
    verified = gateway_health(
        now[0],
        provider_ready=True,
        chat_ready=True,
        provider_observed_at=now[0] - timedelta(seconds=30),
        last_chat_verified_at=now[0] - timedelta(seconds=20),
        evidence_valid_until=now[0] + timedelta(minutes=9),
    )
    new_epoch = gateway_health(
        now[0],
        observation_epoch="epoch-b",
        hermes_http_ready=False,
    )
    expired = gateway_health(
        now[0],
        observation_epoch="epoch-b",
        process_started_at=now[0] - timedelta(minutes=12),
        provider_ready=True,
        chat_ready=True,
        provider_observed_at=now[0] - timedelta(minutes=11),
        last_chat_verified_at=now[0] - timedelta(minutes=11),
        evidence_valid_until=now[0] + timedelta(minutes=1),
    )
    future = gateway_health(
        now[0],
        observation_epoch="epoch-b",
        provider_ready=True,
        chat_ready=True,
        provider_observed_at=now[0] + timedelta(seconds=1),
        last_chat_verified_at=now[0] + timedelta(seconds=1),
        evidence_valid_until=now[0] + timedelta(minutes=10),
    )
    service = HermesOperationalStatusService(
        _GatewaySequence(verified, new_epoch, expired, future),
        now=lambda: now[0],
    )

    assert asyncio.run(service.get_status()).state == "chat_verified"
    assert asyncio.run(service.get_status()).state == "starting"
    assert asyncio.run(service.get_status()).state == "http_ready"
    future_status = asyncio.run(service.get_status())
    assert future_status.state == "http_ready"
    assert future_status.last_chat_verified_at == (
        now[0] - timedelta(minutes=11)
    )


def test_public_status_dto_rejects_private_fields_and_naive_timestamps(
) -> None:
    valid = {
        "state": "http_ready",
        "http_ready": True,
        "provider_ready": False,
        "chat_verified": False,
        "checked_at": datetime(2026, 7, 30, 1, tzinfo=UTC),
        "last_chat_verified_at": None,
        "restart_available": False,
        "status_basis": "application_path",
    }

    with pytest.raises(ValidationError):
        HermesYujinStatusResponse.model_validate({
            **valid,
            "checked_at": datetime(2026, 7, 30, 1),
        })
    with pytest.raises(ValidationError):
        HermesYujinStatusResponse.model_validate({
            **valid,
            "checked_at": datetime(
                2026,
                7,
                30,
                10,
                tzinfo=timezone(timedelta(hours=9)),
            ),
        })
    with pytest.raises(ValidationError):
        HermesYujinStatusResponse.model_validate({
            **valid,
            "private_failure": "SECRET",
        })


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("not_configured", (False, False, False)),
        ("stopped", (False, False, False)),
        ("starting", (False, False, False)),
        ("http_ready", (True, False, False)),
        ("provider_ready", (True, True, False)),
        ("chat_verified", (True, True, True)),
    ],
)
def test_public_status_dto_enforces_exact_state_boolean_invariants(
    state: str,
    expected: tuple[bool, bool, bool],
) -> None:
    fields = ("http_ready", "provider_ready", "chat_verified")
    valid = {
        "state": state,
        **dict(zip(fields, expected, strict=True)),
        "checked_at": datetime(2026, 7, 30, 1, tzinfo=UTC),
        "last_chat_verified_at": None,
        "restart_available": False,
        "status_basis": "application_path",
    }

    assert HermesYujinStatusResponse.model_validate(valid).state == state
    for field, value in zip(fields, expected, strict=True):
        with pytest.raises(ValidationError):
            HermesYujinStatusResponse.model_validate({
                **valid,
                field: not value,
            })


@pytest.mark.parametrize("http_ready", [False, True])
def test_public_degraded_status_allows_http_but_rejects_provider_or_chat(
    http_ready: bool,
) -> None:
    valid = {
        "state": "degraded",
        "http_ready": http_ready,
        "provider_ready": False,
        "chat_verified": False,
        "checked_at": datetime(2026, 7, 30, 1, tzinfo=UTC),
        "last_chat_verified_at": datetime(
            2026,
            7,
            30,
            0,
            59,
            tzinfo=UTC,
        ),
        "restart_available": False,
        "status_basis": "application_path",
    }

    assert HermesYujinStatusResponse.model_validate(valid).state == "degraded"
    for field in ("provider_ready", "chat_verified"):
        with pytest.raises(ValidationError):
            HermesYujinStatusResponse.model_validate({
                **valid,
                field: True,
            })


def test_configured_gateway_without_capability_verifier_is_not_ready(
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    http = _HealthHttp(gateway_health(now))

    response = TestClient(create_app(
        projects_root=tmp_path,
        agent_gateway_url="http://videobox-agent-gateway:8081",
        agent_gateway_service_token=SERVICE_TOKEN,
        agent_gateway_http_client_factory=lambda **_: http,
    )).get("/api/hermes-yujin/status")

    assert response.status_code == 200
    assert response.json()["state"] == "not_configured"
    assert response.json()["status_basis"] == "application_path"
    assert http.calls == []


def test_status_service_rejects_non_utc_gateway_evidence() -> None:
    now = datetime(2026, 7, 30, 1, tzinfo=UTC)
    kst = timezone(timedelta(hours=9))
    payload = gateway_health(
        now,
        process_started_at=datetime(
            2026,
            7,
            30,
            9,
            59,
            tzinfo=kst,
        ),
    )

    with pytest.raises(ValidationError):
        AgentGatewayHealth.model_validate(payload)


def test_real_environment_verifier_enables_gateway_health_wiring(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    public_key = base64.urlsafe_b64encode(b"k" * 32).rstrip(b"=").decode()
    monkeypatch.setenv(
        "VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64",
        public_key,
    )
    monkeypatch.setenv(
        "VIDEOBOX_HERMES_CAPABILITY_KEY_ID",
        "operations-test-key",
    )
    http = _HealthHttp(gateway_health(now))

    response = TestClient(create_app(
        projects_root=tmp_path,
        agent_gateway_url="http://videobox-agent-gateway:8081",
        agent_gateway_service_token=SERVICE_TOKEN,
        agent_gateway_http_client_factory=lambda **_: http,
    )).get("/api/hermes-yujin/status")

    assert response.status_code == 200
    assert response.json()["state"] == "http_ready"
    assert http.calls == [("GET", "/health")]


def test_local_clock_rollback_cannot_reuse_or_expose_future_memory() -> None:
    now = [datetime(2026, 7, 30, 1, tzinfo=UTC)]
    service = HermesOperationalStatusService(
        _GatewaySequence(
            gateway_health(
                now[0],
                provider_ready=True,
                chat_ready=True,
                provider_observed_at=now[0] - timedelta(seconds=30),
                last_chat_verified_at=now[0] - timedelta(seconds=20),
                evidence_valid_until=now[0] + timedelta(minutes=9),
            ),
            AgentGatewayUnavailable("PRIVATE clock rollback"),
        ),
        now=lambda: now[0],
    )

    assert asyncio.run(service.get_status()).state == "chat_verified"
    now[0] -= timedelta(minutes=2)
    rolled_back = asyncio.run(service.get_status())

    assert rolled_back.state == "stopped"
    assert rolled_back.last_chat_verified_at is None
