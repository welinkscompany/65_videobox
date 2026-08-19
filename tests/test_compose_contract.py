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


def test_every_service_caps_its_logs_including_postgres() -> None:
    """postgres was the one service with no cap, so its logs grew without bound
    while the other four rotated at 10MB. An unbounded log on the database is
    the worst place for one: it fills the disk quietly, and it does so fastest
    exactly when the database is already unhealthy and printing errors."""
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))

    uncapped = [
        name
        for name, service in compose["services"].items()
        if service.get("logging")
        != {"driver": "local", "options": {"max-size": "10m", "max-file": "3"}}
    ]

    assert uncapped == []


def test_workspace_owns_api_and_web_mounts_without_host_or_docker_access() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    workspace = compose["services"]["videobox-workspace"]

    assert workspace["build"] == {"context": ".", "dockerfile": "docker/workspace.Dockerfile"}
    assert workspace["environment"]["VIDEOBOX_DATA_ROOT"] == "/videobox-data"
    assert workspace["environment"]["VIDEOBOX_SNAPSHOT_ROOT"] == "/videobox-snapshot"
    # Exactly three host bind mounts, all under the configured data root, plus a
    # named volume for speech-to-text weights.  The named volume grants no host
    # access; it exists because the root filesystem is read-only and model
    # downloads must not land in the owner's project data.  Keep this list exact
    # so any further mount has to be justified here.
    #
    # drive-sync is the drop folder the owner (or a Drive mirror) puts footage
    # in. It stays under the same data root as everything else -- this is not a
    # widening to arbitrary host paths -- and it is writable because the watcher
    # files each original into a sibling folder once it has been imported, which
    # is how the owner can see what was already taken.
    assert workspace["volumes"] == [
        "${VIDEOBOX_CONTAINER_DATA_ROOT:?set VIDEOBOX_CONTAINER_DATA_ROOT in .env.container}/runtime:/videobox-data",
        "${VIDEOBOX_CONTAINER_DATA_ROOT:?set VIDEOBOX_CONTAINER_DATA_ROOT in .env.container}/snapshot:/videobox-snapshot:ro",
        "${VIDEOBOX_CONTAINER_DATA_ROOT:?set VIDEOBOX_CONTAINER_DATA_ROOT in .env.container}/drive-sync:/videobox-drive-sync",
        "videobox_model_cache:/opt/models",
    ]
    assert workspace["environment"]["HF_HOME"] == "/opt/models"
    assert workspace["networks"] == ["videobox-edge", "videobox-internal"]
    assert "videobox-agent-gateway-network" not in workspace["networks"]
    assert "videobox-hermes-provider-egress" not in workspace["networks"]
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


def _workspace_environment() -> dict[str, str]:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    return {
        str(key): str(value)
        for key, value in compose["services"]["videobox-workspace"]["environment"].items()
    }


def test_speech_to_text_defaults_to_on_so_a_container_never_ships_fake_transcripts() -> None:
    """이 저장소가 **가장 비싸게 배운 사고**를 한 글자로 되돌릴 수 있었다.

    `VIDEOBOX_STT_ENABLED`가 `0`으로 바뀌면 `create_app`은 `MockSTTProvider`로
    내려간다. 그 provider는 오디오를 **무시하고** `"Line one."` 같은 영어 문장을
    돌려준다 -- owner에게는 가짜 전사가 완성본에 박힌다.

    그런데 2026-08-19까지 이 기본값을 지키는 테스트가 하나도 없었다. 백엔드
    3,650개도 웹 1,088개도 e2e 48개도 전부 초록인 채로 그 사고가 재현된다.
    테스트가 오히려 **컨테이너 기본이 mock임을 정답으로 고정**하고 있었다
    (`tests/test_stt_runtime_config.py`는 인자 없는 `create_app()`을 재는데,
    컨테이너는 그 경로에 이 환경변수를 넣어 준다).
    """
    environment = _workspace_environment()

    assert environment["VIDEOBOX_STT_ENABLED"] == "${VIDEOBOX_STT_ENABLED:-1}"
    assert environment["VIDEOBOX_STT_LANGUAGE"] == "${VIDEOBOX_STT_LANGUAGE:-ko}"


def test_the_stack_verifier_names_only_services_that_still_exist() -> None:
    """`verify_container_stack.ps1`이 `videobox-api`·`videobox-web`을 요구하고
    있었다 -- 두 서비스는 `videobox-workspace`로 합쳐져 사라진 지 오래라,
    스택이 멀쩡해도 이 검증은 항상 실패한다. 항상 실패하는 검증은 아무도
    안 돌리게 되고, 그 순간부터 지키는 것이 없다."""
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    verifier = (ROOT / "scripts" / "verify_container_stack.ps1").read_text(encoding="utf-8")

    referenced = set(re.findall(r"videobox-[a-z0-9-]+", verifier))
    missing = sorted(referenced - set(compose["services"]))

    assert referenced, "검증 스크립트가 아무 서비스도 확인하지 않는다"
    assert missing == []


def test_the_local_model_address_stays_on_the_host_loopback_bridge() -> None:
    """로컬 모델 주소가 바뀌면 분석·의미검색·유진 대화가 한꺼번에 조용히 죽는다.

    실패해도 `/health`는 `ok`이고 `owner-ready`도 PASS라, 화면에서만 "추천이
    안 나온다"로 나타난다. 기본값을 여기서 못 박아 둔다.
    """
    environment = _workspace_environment()

    assert environment["VIDEOBOX_LOCAL_RUNTIME_BASE_URL"] == (
        "${VIDEOBOX_LOCAL_RUNTIME_BASE_URL:-http://host.docker.internal:1234/v1}"
    )
