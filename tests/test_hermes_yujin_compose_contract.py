from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient
import yaml


ROOT = Path(__file__).parents[1]
COMPOSE_PATH = ROOT / "compose.yaml"
PINNED_HERMES_IMAGE = (
    "nousresearch/hermes-agent@"
    "sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787"
)
HERMES_NETWORK = "videobox-agent-gateway-network"
GATEWAY_API_NETWORK = "videobox-agent-gateway-api-network"
PROVIDER_EGRESS_NETWORK = "videobox-hermes-provider-egress"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def test_hermes_yujin_uses_the_pinned_serve_contract_and_isolated_oauth_state() -> None:
    compose = _compose()
    hermes = compose["services"]["videobox-hermes-yujin"]

    assert hermes["image"] == PINNED_HERMES_IMAGE
    assert hermes["command"] == ["serve", "--host", "0.0.0.0", "--port", "9120"]
    assert hermes["networks"] == [HERMES_NETWORK, PROVIDER_EGRESS_NETWORK]
    assert hermes["volumes"] == ["videobox_hermes_oauth_state:/opt/data"]
    assert "ports" not in hermes
    assert "expose" not in hermes
    assert "depends_on" not in hermes
    assert "network_mode" not in hermes

    rendered = str(hermes)
    for forbidden in (
        GATEWAY_API_NETWORK,
        "videobox-edge",
        "videobox-internal",
        "videobox-postgres",
        "videobox-workspace",
        "videobox-api",
        "renderer",
        "/videobox-data",
        "/videobox-snapshot",
        "docker.sock",
    ):
        assert forbidden not in rendered


def test_hermes_yujin_receives_only_hashed_auth_and_has_honest_http_health() -> None:
    hermes = _compose()["services"]["videobox-hermes-yujin"]

    assert hermes["environment"] == {
        "HERMES_DASHBOARD_BASIC_AUTH_USERNAME": (
            "${HERMES_YUJIN_GATEWAY_USERNAME:?set in .env.container}"
        ),
        "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH": (
            "${HERMES_YUJIN_GATEWAY_PASSWORD_HASH:?set in .env.container}"
        ),
    }
    assert "HERMES_YUJIN_GATEWAY_PASSWORD" not in hermes["environment"]
    health_command = " ".join(hermes["healthcheck"]["test"])
    assert "http://127.0.0.1:9120/api/status" in health_command
    assert "provider" not in health_command.lower()
    assert "chat" not in health_command.lower()
    assert "PASSWORD" not in health_command
    assert hermes["read_only"] is True
    assert hermes["cap_drop"] == ["ALL"]
    assert hermes["security_opt"] == ["no-new-privileges:true"]
    assert hermes["pids_limit"] == 128
    assert hermes["mem_limit"] == "2g"
    assert hermes["cpus"] == 2.0
    assert hermes["logging"]["driver"] == "local"


def test_gateway_is_the_only_two_network_application_bridge() -> None:
    compose = _compose()
    gateway = compose["services"]["videobox-agent-gateway"]
    workspace = compose["services"]["videobox-workspace"]

    assert gateway["build"] == {
        "context": ".",
        "dockerfile": "docker/agent-gateway.Dockerfile",
    }
    assert gateway["networks"] == [GATEWAY_API_NETWORK, HERMES_NETWORK]
    assert workspace["networks"] == [
        "videobox-edge",
        "videobox-internal",
        GATEWAY_API_NETWORK,
    ]
    assert compose["networks"][GATEWAY_API_NETWORK] == {"internal": True}
    assert compose["networks"][HERMES_NETWORK] == {"internal": True}

    assert PROVIDER_EGRESS_NETWORK not in gateway["networks"]
    assert "videobox-edge" not in gateway["networks"]
    assert "videobox-internal" not in gateway["networks"]
    assert HERMES_NETWORK not in workspace["networks"]
    assert PROVIDER_EGRESS_NETWORK not in workspace["networks"]
    assert "ports" not in gateway
    assert "volumes" not in gateway

    rendered_gateway = str(gateway)
    for forbidden in (
        "videobox-postgres",
        "/videobox-data",
        "/videobox-snapshot",
        "/opt/data",
        "docker.sock",
    ):
        assert forbidden not in rendered_gateway


def test_gateway_gets_plaintext_auth_but_workspace_never_gets_hermes_secrets() -> None:
    compose = _compose()
    gateway = compose["services"]["videobox-agent-gateway"]
    workspace = compose["services"]["videobox-workspace"]

    assert gateway["environment"] == {
        "HERMES_YUJIN_GATEWAY_USERNAME": (
            "${HERMES_YUJIN_GATEWAY_USERNAME:?set in .env.container}"
        ),
        "HERMES_YUJIN_GATEWAY_PASSWORD": (
            "${HERMES_YUJIN_GATEWAY_PASSWORD:?set in .env.container}"
        ),
        "HERMES_YUJIN_URL": "http://videobox-hermes-yujin:9120",
    }
    assert "HERMES_YUJIN_GATEWAY_PASSWORD_HASH" not in gateway["environment"]
    assert all("HERMES" not in name for name in workspace["environment"])
    assert "HERMES_YUJIN_GATEWAY_PASSWORD" not in str(workspace)
    assert "HERMES_YUJIN_GATEWAY_PASSWORD_HASH" not in str(workspace)
    assert gateway["read_only"] is True
    assert gateway["tmpfs"] == ["/tmp"]
    assert gateway["cap_drop"] == ["ALL"]
    assert gateway["security_opt"] == ["no-new-privileges:true"]
    assert gateway["user"] == "10001:10001"
    assert gateway["pids_limit"] == 64
    assert gateway["mem_limit"] == "256m"
    assert gateway["cpus"] == 0.5
    assert gateway["logging"]["driver"] == "local"


def test_agent_gateway_dockerfile_is_minimal_non_root_and_read_only_compatible() -> None:
    dockerfile = (ROOT / "docker" / "agent-gateway.Dockerfile").read_text(
        encoding="utf-8"
    )
    requirements = (ROOT / "requirements-agent-gateway.txt").read_text(
        encoding="utf-8"
    )

    assert dockerfile.startswith("FROM python:3.12-slim\n")
    assert "COPY requirements-agent-gateway.txt" in dockerfile
    assert "COPY services/agent-gateway/src" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert "uvicorn" in dockerfile
    assert "--host\", \"0.0.0.0\"" in dockerfile
    assert "--port\", \"8081\"" in dockerfile
    assert "COPY . ." not in dockerfile
    for forbidden in (
        "services/api",
        "apps/web",
        "packages/",
        "postgres",
        "videobox-data",
        "videobox-snapshot",
        "/opt/data",
    ):
        assert forbidden not in dockerfile.lower()
    assert requirements.splitlines() == ["fastapi==0.115.0", "uvicorn==0.30.6"]


def test_gateway_health_is_http_process_readiness_only_and_reads_no_auth_env(
    monkeypatch,
) -> None:
    main_path = (
        ROOT
        / "services"
        / "agent-gateway"
        / "src"
        / "videobox_agent_gateway"
        / "main.py"
    )
    source = main_path.read_text(encoding="utf-8")
    assert "os.environ" not in source
    assert "os.getenv" not in source
    assert "HERMES_YUJIN_GATEWAY_USERNAME" not in source
    assert "HERMES_YUJIN_GATEWAY_PASSWORD" not in source

    monkeypatch.setenv("HERMES_YUJIN_GATEWAY_USERNAME", "must-not-be-returned-user")
    monkeypatch.setenv("HERMES_YUJIN_GATEWAY_PASSWORD", "must-not-be-returned-password")
    spec = importlib.util.spec_from_file_location("a1_gateway_main", main_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    response = TestClient(module.app).get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "scope": "gateway_http_process",
        "hermes_http_ready": False,
        "provider_ready": False,
        "chat_ready": False,
    }
    assert "must-not-be-returned" not in response.text


def test_start_script_validates_a_real_env_file_and_is_nondestructive() -> None:
    script = (ROOT / "scripts" / "start-hermes-yujin.ps1").read_text(
        encoding="utf-8"
    )
    required_names = (
        "POSTGRES_PASSWORD",
        "VIDEOBOX_CONTAINER_DATA_ROOT",
        "HERMES_YUJIN_GATEWAY_USERNAME",
        "HERMES_YUJIN_GATEWAY_PASSWORD",
        "HERMES_YUJIN_GATEWAY_PASSWORD_HASH",
    )
    assert "Test-Path -LiteralPath $EnvFile -PathType Leaf" in script
    assert "replace-before-starting" in script
    for name in required_names:
        assert name in script
    assert re.search(
        r"docker compose .*--env-file .* up -d --build "
        r"videobox-hermes-yujin videobox-agent-gateway",
        script,
    )
    assert "Write-Output $value" not in script
    assert "Write-Host $value" not in script
    assert "install-hermes-yujin-profile" not in script
    assert not re.search(
        r"docker compose[^\r\n]*(?:\bdown\b|\brm\b|--remove-orphans|-v\b)",
        script,
        flags=re.IGNORECASE,
    )


def test_static_verifier_uses_child_dummy_env_and_checks_the_source_topology() -> None:
    script = (ROOT / "scripts" / "verify-hermes-yujin-runtime.ps1").read_text(
        encoding="utf-8"
    )

    assert "param(" in script
    assert "[switch]$StaticOnly" in script
    assert "ProcessStartInfo" in script
    assert "config --format json" in script
    assert "ConvertFrom-Json" in script
    assert ".env.container" not in re.sub(
        r"set in \.env\.container", "", script, flags=re.IGNORECASE
    )
    for name in (
        "POSTGRES_PASSWORD",
        "VIDEOBOX_CONTAINER_DATA_ROOT",
        "HERMES_YUJIN_GATEWAY_USERNAME",
        "HERMES_YUJIN_GATEWAY_PASSWORD",
        "HERMES_YUJIN_GATEWAY_PASSWORD_HASH",
        GATEWAY_API_NETWORK,
        HERMES_NETWORK,
        PROVIDER_EGRESS_NETWORK,
        PINNED_HERMES_IMAGE,
        "/api/status",
    ):
        assert name in script
    assert not re.search(
        r"docker compose[^\r\n]*(?:\bup\b|\bdown\b|\brm\b|--remove-orphans|-v\b)",
        script,
        flags=re.IGNORECASE,
    )


def test_env_example_distinguishes_plaintext_and_hash_without_usable_credentials() -> None:
    example = (ROOT / ".env.container.example").read_text(encoding="utf-8")

    assert "HERMES_YUJIN_GATEWAY_USERNAME=replace-before-starting" in example
    assert "HERMES_YUJIN_GATEWAY_PASSWORD=replace-before-starting" in example
    assert "HERMES_YUJIN_GATEWAY_PASSWORD_HASH=replace-before-starting" in example
    assert "plaintext" in example.lower()
    assert "hash" in example.lower()
    assert "must match" in example.lower()
    assert "scrypt$" not in example
