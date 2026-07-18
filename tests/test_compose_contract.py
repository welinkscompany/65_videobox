from pathlib import Path

import yaml


def test_compose_uses_exact_project_name_and_only_web_loopback_port() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))

    assert compose["name"] == "65_videobox"
    assert "ports" not in compose["services"]["videobox-api"]
    assert "ports" not in compose["services"]["videobox-postgres"]
    assert compose["services"]["videobox-web"]["ports"] == [
        "127.0.0.1:${VIDEOBOX_WEB_PORT:-5173}:8080"
    ]


def test_api_mounts_only_writable_runtime_and_read_only_verified_snapshot() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    api = compose["services"]["videobox-api"]

    assert api["environment"]["VIDEOBOX_DATA_ROOT"] == "/videobox-data"
    assert api["environment"]["VIDEOBOX_SNAPSHOT_ROOT"] == "/videobox-snapshot"
    assert api["volumes"] == [
        "${VIDEOBOX_CONTAINER_DATA_ROOT:?set VIDEOBOX_CONTAINER_DATA_ROOT in .env.container}/runtime:/videobox-data",
        "${VIDEOBOX_CONTAINER_DATA_ROOT:?set VIDEOBOX_CONTAINER_DATA_ROOT in .env.container}/snapshot:/videobox-snapshot:ro",
    ]
