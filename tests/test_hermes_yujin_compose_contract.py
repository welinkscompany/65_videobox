from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
import yaml


ROOT = Path(__file__).parents[1]
COMPOSE_PATH = ROOT / "compose.yaml"
OVERLAY_PATH = ROOT / "compose.hermes-yujin.yaml"
PINNED_HERMES_IMAGE = (
    "nousresearch/hermes-agent@"
    "sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787"
)
HERMES_NETWORK = "videobox-agent-gateway-network"
GATEWAY_API_NETWORK = "videobox-agent-gateway-api-network"
PROVIDER_EGRESS_NETWORK = "videobox-hermes-provider-egress"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def _overlay() -> dict:
    return yaml.safe_load(OVERLAY_PATH.read_text(encoding="utf-8"))


def _render_compose(*, include_yujin: bool) -> dict:
    command = ["docker", "compose", "-f", str(COMPOSE_PATH)]
    environment = {
        **os.environ,
        "POSTGRES_PASSWORD": "static-base-password",
        "VIDEOBOX_CONTAINER_DATA_ROOT": "D:/videobox-static-data",
    }
    if include_yujin:
        command.extend(["-f", str(OVERLAY_PATH), "--profile", "hermes-yujin"])
        environment.update(
            {
                "HERMES_YUJIN_GATEWAY_USERNAME": "static-gateway-user",
                "HERMES_YUJIN_GATEWAY_PASSWORD": "static-gateway-password",
                "HERMES_YUJIN_GATEWAY_PASSWORD_HASH": "static-gateway-password-hash",
            }
        )
    command.extend(["config", "--format", "json"])
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, "Compose config failed without safe diagnostics"
    return json.loads(result.stdout)


def test_base_compose_remains_yujin_free_and_overlay_is_explicitly_opt_in() -> None:
    base_source = COMPOSE_PATH.read_text(encoding="utf-8")
    base = _render_compose(include_yujin=False)
    merged = _render_compose(include_yujin=True)

    assert "HERMES_YUJIN" not in base_source
    assert "videobox-agent-gateway" not in base["services"]
    assert "videobox-hermes-yujin" not in base["services"]
    assert set(base["services"]["videobox-workspace"]["networks"]) == {
        "videobox-edge",
        "videobox-internal",
    }
    assert set(merged["services"]) >= {
        "videobox-agent-gateway",
        "videobox-hermes-yujin",
    }
    assert merged["services"]["videobox-agent-gateway"]["profiles"] == [
        "hermes-yujin"
    ]
    assert merged["services"]["videobox-hermes-yujin"]["profiles"] == [
        "hermes-yujin"
    ]
    assert set(merged["services"]["videobox-workspace"]["networks"]) == {
        "videobox-edge",
        "videobox-internal",
        GATEWAY_API_NETWORK,
    }


def test_capability_authority_comment_matches_the_deployed_a1_state() -> None:
    base_source = COMPOSE_PATH.read_text(encoding="utf-8")
    top_comment = "\n".join(base_source.splitlines()[:8])

    assert "future gateway" not in top_comment
    assert "capability issuance, private key, and route remain not deployed" in (
        top_comment
    )
    assert "health-only gateway and internal networks are deployed separately" in (
        top_comment
    )


def test_hermes_yujin_uses_the_pinned_serve_contract_and_isolated_oauth_state() -> None:
    compose = _overlay()
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
    hermes = _overlay()["services"]["videobox-hermes-yujin"]

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
    compose = _overlay()
    gateway = compose["services"]["videobox-agent-gateway"]
    workspace = compose["services"]["videobox-workspace"]

    assert gateway["build"] == {
        "context": ".",
        "dockerfile": "docker/agent-gateway.Dockerfile",
    }
    assert gateway["networks"] == [GATEWAY_API_NETWORK, HERMES_NETWORK]
    assert workspace["networks"] == [GATEWAY_API_NETWORK]
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
    compose = _overlay()
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
    assert all("HERMES" not in name for name in workspace.get("environment", {}))
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


def test_agent_gateway_build_context_uses_a_deny_all_dockerfile_allowlist() -> None:
    ignore_path = ROOT / "docker" / "agent-gateway.Dockerfile.dockerignore"
    patterns = ignore_path.read_text(encoding="utf-8").splitlines()
    assert patterns == [
        "**",
        "!docker/",
        "!docker/agent-gateway.Dockerfile",
        "!requirements-agent-gateway.txt",
        "!services/",
        "!services/agent-gateway/",
        "!services/agent-gateway/src/",
        "!services/agent-gateway/src/**",
    ]

    def is_included(relative_path: str) -> bool:
        normalized = relative_path.replace("\\", "/").strip("/")
        included = True
        for raw_pattern in patterns:
            negated = raw_pattern.startswith("!")
            pattern = raw_pattern.removeprefix("!")
            directory_only = pattern.endswith("/")
            pattern = pattern.strip("/")
            if pattern == "**":
                matches = True
            elif pattern.endswith("/**"):
                prefix = pattern.removesuffix("/**")
                matches = normalized == prefix or normalized.startswith(f"{prefix}/")
            elif directory_only:
                matches = normalized == pattern
            else:
                matches = normalized == pattern
            if matches:
                included = negated
        return included

    allowed = (
        "docker/agent-gateway.Dockerfile",
        "requirements-agent-gateway.txt",
        "services/agent-gateway/src/videobox_agent_gateway/__init__.py",
        "services/agent-gateway/src/videobox_agent_gateway/main.py",
        "services/agent-gateway/src/videobox_agent_gateway/nested/module.py",
    )
    rejected = (
        ".env",
        ".env.container",
        ".env.container.example",
        ".tmp-final-fence-debug/private.txt",
        ".tmp-real-video-dogfood/sample.json",
        "apps/web/.tmp-real-video-dogfood/sample.mp4",
        "apps/web/src/main.tsx",
        "services/api/src/videobox_api/main.py",
        "services/agent-gateway/README.md",
        "packages/core-engine/src/videobox_core_engine/__init__.py",
        "docs/implementation-plan.ko.md",
        "runtime.sqlite",
        "sample.mp4",
        "sample.wav",
        "sample.mp3",
        "sample.mov",
        "docker/workspace.Dockerfile",
    )
    assert all(is_included(path) for path in allowed)
    assert not any(is_included(path) for path in rejected)


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
    route_paths = {route.path for route in module.app.routes}
    assert route_paths == {"/health"}
    assert module.app.openapi_url is None


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
    for argument in (
        '"compose"',
        '"-f", $composeFile',
        '"-f", $overlayFile',
        '"--profile", "hermes-yujin"',
        '"--env-file", $resolvedEnvFile',
        '"up"',
        '"-d"',
        '"--build"',
        '"videobox-hermes-yujin"',
        '"videobox-agent-gateway"',
    ):
        assert argument in script
    assert "Write-Output $value" not in script
    assert "Write-Host $value" not in script
    assert "install-hermes-yujin-profile" not in script
    for destructive_argument in ('"down"', '"rm"', '"--remove-orphans"', '"-v"'):
        assert destructive_argument not in script


def test_static_verifier_uses_child_dummy_env_and_checks_the_source_topology() -> None:
    script = (ROOT / "scripts" / "verify-hermes-yujin-runtime.ps1").read_text(
        encoding="utf-8"
    )

    assert "param(" in script
    assert "[switch]$StaticOnly" in script
    assert "ProcessStartInfo" in script
    assert "compose.hermes-yujin.yaml" in script
    assert "--profile hermes-yujin" in script
    assert "Base Compose must not contain Yujin services." in script
    assert "profiles" in script
    assert "privileged" in script
    assert "extra_hosts" in script
    assert "dns" in script
    assert "cap_add" in script
    assert "Gateway environment contract is invalid." in script
    assert "Workspace received a forbidden Hermes environment value." in script
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


def test_static_verifier_rejects_workspace_alias_of_a_dummy_secret(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "compose.yaml").write_text(
        COMPOSE_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    overlay_source = OVERLAY_PATH.read_text(encoding="utf-8").replace(
        "  videobox-workspace:\n"
        "    networks: [videobox-agent-gateway-api-network]\n",
        "  videobox-workspace:\n"
        "    environment:\n"
        "      SAFE_ALIAS: ${HERMES_YUJIN_GATEWAY_PASSWORD}\n"
        "    networks: [videobox-agent-gateway-api-network]\n",
        1,
    )
    (repository / "compose.hermes-yujin.yaml").write_text(
        overlay_source,
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "verify-hermes-yujin-runtime.ps1"),
            "-StaticOnly",
            "-RepositoryRoot",
            str(repository),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert result.returncode != 0
    output = f"{result.stdout}\n{result.stderr}"
    for forbidden in (
        "static-gateway-user",
        "static-gateway-password",
        "static-gateway-password-hash",
    ):
        assert forbidden not in output


def test_env_example_distinguishes_plaintext_and_hash_without_usable_credentials() -> None:
    example = (ROOT / ".env.container.example").read_text(encoding="utf-8")

    assert "HERMES_YUJIN_GATEWAY_USERNAME=replace-before-starting" in example
    assert "HERMES_YUJIN_GATEWAY_PASSWORD=replace-before-starting" in example
    assert "HERMES_YUJIN_GATEWAY_PASSWORD_HASH=replace-before-starting" in example
    assert "plaintext" in example.lower()
    assert "hash" in example.lower()
    assert "must match" in example.lower()
    assert "scrypt$" not in example
