from __future__ import annotations

from hashlib import sha256
from json import loads
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
ASSET_ROOT = ROOT / "docker" / "hermes" / "yujin"


def test_yujin_hermes_assets_are_canonical_and_hash_verified() -> None:
    manifest = loads((ASSET_ROOT / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["schema_version"] == "videobox-yujin-hermes-assets-v1"
    assert manifest["identity"] == "videobox-yujin"
    assert set(manifest["assets"]) == {"SOUL.md", "AGENTS.md", "USER.md.seed", "mem0.json"}
    for filename, expected_digest in manifest["assets"].items():
        payload = (ASSET_ROOT / filename).read_bytes()
        assert sha256(payload).hexdigest() == expected_digest

    mem0 = loads((ASSET_ROOT / "mem0.json").read_text(encoding="utf-8"))
    assert mem0["mode"] == "oss"
    assert mem0["user_id"] == "videobox-owner"
    assert mem0["agent_id"] == "videobox-yujin"
    assert "write_approval" not in mem0
    assert mem0["oss"]["llm"] == {
        "provider": "ollama",
        "config": {
            "model": "qwen3:4b",
            "ollama_base_url": "http://videobox-hermes-local-ollama:11434",
        },
    }


def test_yujin_assets_limit_the_agent_to_videobox_editing_and_asset_operations() -> None:
    soul = (ASSET_ROOT / "SOUL.md").read_text(encoding="utf-8")
    rules = (ASSET_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    user_seed = (ASSET_ROOT / "USER.md.seed").read_text(encoding="utf-8")

    assert "VideoBox" in soul
    assert "영상 편집" in soul
    assert "B-roll Inbox" in rules
    assert "프로젝트 밖의 파일" in rules
    assert "대본" in rules and "썸네일" in rules
    assert "videobox-owner" in user_seed
    assert "GPT" not in user_seed


def test_runtime_dockerfile_pins_hermes_and_local_mem0_oss_dependencies() -> None:
    dockerfile = (ROOT / "docker" / "hermes" / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787" in dockerfile
    assert "mem0ai==2.0.12" in dockerfile
    assert "qdrant-client==1.18.0" in dockerfile
    assert "ollama==0.6.2" in dockerfile
    assert "COPY docker/hermes/yujin /opt/videobox-yujin" in dockerfile
    assert dockerfile.rstrip().endswith("USER root")


def test_runtime_bootstrap_seeds_user_memory_once_and_enables_local_mem0_oss() -> None:
    script = (ROOT / "scripts" / "bootstrap-videobox-hermes-runtime.ps1").read_text(encoding="utf-8")

    assert "if [ ! -e /opt/data/memories/USER.md ]; then" in script
    assert "cp /opt/videobox-yujin/USER.md.seed /opt/data/memories/USER.md" in script
    assert "install -m 0644 /opt/videobox-yujin/SOUL.md /opt/data/SOUL.md" in script
    assert "install -m 0644 /opt/videobox-yujin/AGENTS.md /opt/data/AGENTS.md" in script
    assert "python /opt/videobox-yujin/verify_assets.py --target /opt/data" in script
    assert "chown -R 10000:10000 /opt/data" in script
    assert "s6-setuidgid hermes sh -c" in script
    assert "hermes config set memory.provider mem0" in script
    # mem0.json has no secret; Hermes runs as its unprivileged user and must
    # therefore be able to read the local OSS configuration after bootstrap.
    assert "install -m 0644 /opt/videobox-yujin/mem0.json /opt/data/mem0.json" in script
    assert "MEM0_API_KEY" not in script
    assert "OpenAI" not in script
    assert "$PSScriptRoot" in script
    assert "Push-Location $repoRoot" in script
    assert "docker compose" not in script
    assert "$ollamaReady" in script
    assert script.index("$ollamaReady") < script.index("videobox-hermes-model-seed")


def test_runtime_compose_is_isolated_and_only_model_seed_has_egress() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    runtime = compose["services"]["videobox-hermes-runtime"]
    ollama = compose["services"]["videobox-hermes-local-ollama"]
    model_seed = compose["services"]["videobox-hermes-model-seed"]

    assert runtime["profiles"] == ["hermes-runtime"]
    assert runtime["build"] == {"context": ".", "dockerfile": "docker/hermes/Dockerfile"}
    assert "user" not in runtime
    assert runtime["entrypoint"] == ["/opt/hermes/docker/main-wrapper.sh"]
    assert runtime["volumes"] == ["videobox_hermes_oauth_state:/opt/data"]
    assert runtime["networks"] == ["videobox-hermes-memory", "videobox-hermes-provider-egress"]
    assert "ports" not in runtime
    assert "videobox-internal" not in str(runtime)
    assert "videobox-edge" not in str(runtime)
    assert "videobox-data" not in str(runtime)
    assert runtime["depends_on"] == {
        "videobox-hermes-local-ollama": {"condition": "service_healthy"}
    }

    assert ollama["profiles"] == ["hermes-runtime", "hermes-dashboard"]
    assert ollama["image"] == (
        "ollama/ollama@"
        "sha256:1514372d3cef7387b6202b253e761d820e00e44b28f268aad5029389d0479e99"
    )
    assert "ports" not in ollama
    assert ollama["networks"] == ["videobox-hermes-memory"]
    assert ollama["healthcheck"]["test"] == ["CMD-SHELL", "ollama list >/dev/null 2>&1"]
    assert compose["networks"]["videobox-hermes-memory"]["internal"] is True

    assert model_seed["profiles"] == ["hermes-model-seed"]
    assert model_seed["image"] == ollama["image"]
    assert model_seed["networks"] == ["videobox-hermes-memory", "videobox-hermes-model-egress"]
    assert "qwen3:4b" in str(model_seed["command"])
    assert "nomic-embed-text" in str(model_seed["command"])
    assert compose["networks"]["videobox-hermes-model-egress"] == {}
    assert "videobox-hermes-model-egress" not in runtime["networks"]

    dashboard = compose["services"]["videobox-hermes-dashboard"]
    assert "user" not in dashboard
    assert dashboard["image"] == (
        "nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787"
    )
    assert "build" not in dashboard
    assert "entrypoint" not in dashboard
    assert "depends_on" not in dashboard
    assert dashboard["networks"] == ["videobox-hermes-provider-egress"]
    assert "videobox-internal" not in str(dashboard)
    assert "videobox-edge" not in str(dashboard)


def test_oauth_bootstrap_and_verify_scripts_keep_credentials_out_of_output() -> None:
    start = (ROOT / "scripts" / "start-hermes-oauth-bootstrap.ps1").read_text(encoding="utf-8")
    verify = (ROOT / "scripts" / "verify-hermes-oauth-bootstrap.ps1").read_text(encoding="utf-8")

    assert "hermes-oauth-bootstrap" in start
    assert "videobox-hermes-oauth-bootstrap" in start
    assert "hermes auth add openai-codex --type oauth" in start
    assert "hermes model" in start
    assert "& docker @composeBase exec" not in start
    assert "auth.json" not in start
    assert ".env" not in start
    assert "$PSScriptRoot" in start
    assert "Push-Location $repoRoot" in start

    assert "videobox-hermes-oauth-bootstrap" in verify
    assert "docker inspect --format" in verify
    assert "auth.json" not in verify
    assert ".env" not in verify
    assert "hermes auth" not in verify
    assert "hermes model" not in verify


def test_runtime_verifier_requires_built_image_and_checks_effective_user_and_dependencies() -> None:
    verify = (ROOT / "scripts" / "verify-videobox-hermes-runtime-contract.ps1").read_text(encoding="utf-8")

    assert "docker image inspect --format" in verify
    assert "Config.User" in verify
    assert "hermes" in verify
    assert "mem0" in verify
    assert "qdrant_client" in verify
    assert "ollama" in verify
    assert "--network none" in verify
    assert "--read-only" in verify


def test_authoritative_fast_path_records_the_direct_egress_local_mvp_limit() -> None:
    fast_path = (ROOT / "docs" / "development-fast-path.ko.md").read_text(encoding="utf-8")

    assert "videobox-hermes-provider-egress" in fast_path
    assert "직접 egress" in fast_path
    assert "VideoBox data" in fast_path
    assert "gateway allowlist" in fast_path
