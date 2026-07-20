from pathlib import Path
import re

import yaml


ROOT = Path(__file__).parents[1]


def test_compose_uses_exact_project_name_and_workspace_only_web_loopback_port() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))

    assert compose["name"] == "65_videobox"
    assert "videobox-api" not in compose["services"]
    assert "videobox-web" not in compose["services"]
    assert "ports" not in compose["services"]["videobox-postgres"]
    assert compose["services"]["videobox-workspace"]["ports"] == [
        "127.0.0.1:${VIDEOBOX_WEB_PORT:-5173}:8080"
    ]


def test_workspace_owns_api_and_web_mounts_without_host_or_docker_access() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    workspace = compose["services"]["videobox-workspace"]

    assert workspace["build"] == {"context": ".", "dockerfile": "docker/workspace.Dockerfile"}
    assert workspace["environment"]["VIDEOBOX_DATA_ROOT"] == "/videobox-data"
    assert workspace["environment"]["VIDEOBOX_SNAPSHOT_ROOT"] == "/videobox-snapshot"
    assert workspace["volumes"] == [
        "${VIDEOBOX_CONTAINER_DATA_ROOT:?set VIDEOBOX_CONTAINER_DATA_ROOT in .env.container}/runtime:/videobox-data",
        "${VIDEOBOX_CONTAINER_DATA_ROOT:?set VIDEOBOX_CONTAINER_DATA_ROOT in .env.container}/snapshot:/videobox-snapshot:ro",
    ]
    assert workspace["networks"] == ["videobox-edge", "videobox-internal"]
    assert workspace["read_only"] is True
    assert workspace["cap_drop"] == ["ALL"]
    assert workspace["cap_add"] == ["SETGID", "SETUID"]
    assert workspace["security_opt"] == ["no-new-privileges:true"]
    assert workspace["pids_limit"] == 128
    assert workspace["mem_limit"] == "2g"
    assert workspace["cpus"] == 2.0
    assert workspace["logging"] == {
        "driver": "local",
        "options": {"max-size": "10m", "max-file": "3"},
    }
    assert workspace["healthcheck"]["test"] == [
        "CMD",
        "python",
        "-c",
        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).read()",
    ]
    assert all("docker.sock" not in mount for mount in workspace["volumes"])
    assert compose["networks"]["videobox-internal"]["internal"] is True
    assert "videobox-edge" in compose["networks"]


def test_hermes_preauth_service_is_pinned_isolated_and_has_no_videobox_data_mount() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    hermes = compose["services"]["videobox-hermes-agent"]

    assert hermes["profiles"] == ["hermes-preauth"]
    assert hermes["image"] == (
        "nousresearch/hermes-agent@"
        "sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787"
    )
    assert "ports" not in hermes
    assert hermes["network_mode"] == "none"
    assert hermes["volumes"] == ["videobox_hermes_preauth_state:/opt/data"]
    assert hermes["read_only"] is True
    assert hermes["cap_drop"] == ["ALL"]
    assert hermes["cap_add"] == ["CHOWN", "DAC_OVERRIDE", "SETGID", "SETUID"]
    assert hermes["security_opt"] == ["no-new-privileges:true"]
    assert hermes["logging"] == {
        "driver": "local",
        "options": {"max-size": "10m", "max-file": "3"},
    }
    assert "videobox_hermes_preauth_state" in compose["volumes"]
    assert "videobox_hermes_oauth_state" not in hermes["volumes"]


def test_hermes_oauth_bootstrap_is_isolated_from_preauth_and_videobox_data() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    bootstrap = compose["services"]["videobox-hermes-oauth-bootstrap"]

    assert bootstrap["profiles"] == ["hermes-oauth-bootstrap"]
    assert bootstrap["image"] == (
        "nousresearch/hermes-agent@"
        "sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787"
    )
    assert bootstrap["command"] == ["sleep", "infinity"]
    assert bootstrap["volumes"] == ["videobox_hermes_oauth_state:/opt/data"]
    assert bootstrap["networks"] == ["videobox-hermes-egress"]
    assert "ports" not in bootstrap
    assert "network_mode" not in bootstrap
    assert "videobox_hermes_preauth_state" not in str(bootstrap)
    assert "videobox-data" not in str(bootstrap)
    assert bootstrap["read_only"] is True
    assert bootstrap["tmpfs"] == [
        "/tmp:uid=10000,gid=10000,mode=1777",
        "/run:rw,exec,nosuid,nodev,mode=0755",
    ]
    assert bootstrap["cap_drop"] == ["ALL"]
    assert bootstrap["cap_add"] == ["CHOWN", "DAC_OVERRIDE", "SETGID", "SETUID"]
    assert bootstrap["security_opt"] == ["no-new-privileges:true"]
    assert bootstrap["pids_limit"] == 128
    assert bootstrap["mem_limit"] == "2g"
    assert bootstrap["cpus"] == 2.0
    assert bootstrap["logging"] == {
        "driver": "local",
        "options": {"max-size": "10m", "max-file": "3"},
    }
    assert compose["networks"]["videobox-hermes-egress"] == {}
    assert "videobox_hermes_oauth_state" in compose["volumes"]


def test_hermes_oauth_bootstrap_verifier_requires_the_compose_pinned_image() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    verifier = (ROOT / "scripts" / "verify-hermes-oauth-bootstrap.ps1").read_text(encoding="utf-8")
    expected_image = re.search(r"\$image\s+-ne\s+'([^']+)'", verifier)

    assert expected_image is not None
    assert expected_image.group(1) == compose["services"]["videobox-hermes-oauth-bootstrap"]["image"]


def test_hermes_dashboard_is_loopback_only_and_uses_only_the_isolated_oauth_state() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    dashboard = compose["services"]["videobox-hermes-dashboard"]

    assert dashboard["profiles"] == ["hermes-dashboard"]
    assert dashboard["image"] == (
        "nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787"
    )
    assert "build" not in dashboard
    assert dashboard["command"] == [
        "dashboard", "--host", "0.0.0.0", "--port", "9119", "--insecure", "--no-open",
    ]
    assert dashboard["ports"] == ["127.0.0.1:9119:9119"]
    assert dashboard["volumes"] == ["videobox_hermes_oauth_state:/opt/data"]
    # Platform-only configuration keeps the dashboard on provider egress only.
    assert dashboard["networks"] == ["videobox-hermes-provider-egress"]
    assert "depends_on" not in dashboard
    assert "network_mode" not in dashboard
    assert "videobox_hermes_preauth_state" not in str(dashboard)
    assert "videobox-data" not in str(dashboard)
    assert "videobox-internal" not in str(dashboard)
    assert "videobox-postgres" not in str(dashboard)
    assert dashboard["read_only"] is True
    assert dashboard["tmpfs"] == [
        "/tmp:uid=10000,gid=10000,mode=1777",
        "/run:rw,exec,nosuid,nodev,mode=0755",
    ]
    assert dashboard["cap_drop"] == ["ALL"]
    assert dashboard["cap_add"] == ["CHOWN", "DAC_OVERRIDE", "SETGID", "SETUID"]
    assert dashboard["security_opt"] == ["no-new-privileges:true"]
    assert dashboard["pids_limit"] == 128
    assert dashboard["mem_limit"] == "2g"
    assert dashboard["cpus"] == 2.0
    assert dashboard["logging"] == {
        "driver": "local",
        "options": {"max-size": "10m", "max-file": "3"},
    }


def test_workspace_image_runs_api_and_web_proxy_together() -> None:
    dockerfile = Path("docker/workspace.Dockerfile").read_text(encoding="utf-8")
    entrypoint = Path("docker/workspace-entrypoint.sh").read_text(encoding="utf-8")
    supervisor = Path("docker/workspace-supervisor.py").read_text(encoding="utf-8")
    nginx = Path("docker/workspace-nginx.conf").read_text(encoding="utf-8")

    assert "FROM node:20-bookworm-slim AS web-build" in dockerfile
    assert "FROM python:3.12-slim" in dockerfile
    assert "ffmpeg nginx" in dockerfile
    assert "exec python /app/docker/workspace-supervisor.py" in entrypoint
    assert '"--host", "127.0.0.1", "--port", "8000"' in supervisor
    assert '"setpriv", "--reuid=10001", "--regid=10001", "--init-groups"' in supervisor
    assert '"setpriv", "--reuid=10002", "--regid=10002", "--init-groups"' in supervisor
    assert 'web_env.pop("VIDEOBOX_DATABASE_URL", None)' in supervisor
    assert "_drop_pid_one_capabilities()" in supervisor
    assert "ctypes.CDLL(None, use_errno=True).capset" in supervisor
    assert "os.wait()" in supervisor
    assert "proxy_pass http://127.0.0.1:8000;" in nginx
    assert "location = /health" in nginx
    assert "fastcgi_temp_path /tmp/nginx-fastcgi;" in nginx
    assert "/var/lib/nginx" not in nginx
    assert "error_log /tmp/nginx-error.log notice;" in nginx
    assert "access_log /tmp/nginx-access.log;" in nginx
