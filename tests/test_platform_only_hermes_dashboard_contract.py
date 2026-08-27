from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]


def test_platform_only_dashboard_has_no_custom_runtime_bootstrap_sources() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))

    retired_services = {
        "videobox-hermes-runtime",
        "videobox-hermes-local-ollama",
        "videobox-hermes-model-seed",
    }
    retired_networks = {
        "videobox-hermes-memory",
        "videobox-hermes-model-egress",
    }
    retired_model_volume = "videobox_hermes_ollama_models"

    assert retired_services.isdisjoint(compose["services"])
    assert retired_networks.isdisjoint(compose["networks"])
    assert retired_model_volume not in compose["volumes"]
    assert not (ROOT / "docker" / "hermes").exists()
    assert not (ROOT / "scripts" / "bootstrap-videobox-hermes-runtime.ps1").exists()
    assert not (ROOT / "scripts" / "verify-videobox-hermes-runtime-contract.ps1").exists()

    dashboard = compose["services"]["videobox-hermes-dashboard"]
    assert dashboard["image"] == (
        "nousresearch/hermes-agent@sha256:3811ed13da874fba2ac99b6d492db9a203d34cb6dccf90d886948c00d0ccec09"
    )
    assert dashboard["networks"] == ["videobox-hermes-provider-egress"]
    assert "depends_on" not in dashboard
