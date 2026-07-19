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


def test_hermes_preauth_service_is_pinned_isolated_and_has_no_videobox_data_mount() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    hermes = compose["services"]["videobox-hermes-agent"]

    assert hermes["profiles"] == ["hermes-preauth"]
    assert hermes["image"] == (
        "nousresearch/hermes-agent@"
        "sha256:3db34ce19adfa080736a2a3feb0316dbcccc588faa9afe7fd8ae1c03b4f1a53a"
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
    assert "videobox_hermes_oauth_state" not in compose["volumes"]
