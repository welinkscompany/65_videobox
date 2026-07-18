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
