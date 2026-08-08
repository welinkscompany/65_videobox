"""The container/dev-server factory starts `create_app` with no arguments.

Without an environment-resolved config, `local_runtime_config` silently falls
back to the hardcoded default model_name ("qwen3-35b"), which does not match
whatever model is actually loaded in LM Studio (e.g. "qwen/qwen3.6-35b-a3b").
Mirrors the STT config resolver pattern (tests/test_stt_runtime_config.py).
"""

from pathlib import Path

from videobox_api.main import create_app
from videobox_core_engine.settings import (
    LocalOpenAICompatibleRuntimeConfig,
    resolve_local_runtime_config,
)


def _clear_local_runtime_environment(monkeypatch) -> None:
    for name in (
        "VIDEOBOX_LOCAL_MODEL_NAME",
        "VIDEOBOX_LOCAL_RUNTIME_TIMEOUT_SECONDS",
        "VIDEOBOX_LOCAL_RUNTIME_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_local_runtime_model_name_defaults_when_nothing_is_configured(monkeypatch) -> None:
    _clear_local_runtime_environment(monkeypatch)

    assert resolve_local_runtime_config().model_name == LocalOpenAICompatibleRuntimeConfig().model_name


def test_local_runtime_reads_model_name_from_the_environment(monkeypatch) -> None:
    _clear_local_runtime_environment(monkeypatch)
    monkeypatch.setenv("VIDEOBOX_LOCAL_MODEL_NAME", "qwen/qwen3.6-35b-a3b")

    assert resolve_local_runtime_config().model_name == "qwen/qwen3.6-35b-a3b"


def test_local_runtime_reads_timeout_from_the_environment(monkeypatch) -> None:
    _clear_local_runtime_environment(monkeypatch)
    monkeypatch.setenv("VIDEOBOX_LOCAL_RUNTIME_TIMEOUT_SECONDS", "45")

    assert resolve_local_runtime_config().timeout_seconds == 45


def test_blank_environment_values_fall_back_to_defaults(monkeypatch) -> None:
    _clear_local_runtime_environment(monkeypatch)
    monkeypatch.setenv("VIDEOBOX_LOCAL_MODEL_NAME", "   ")

    assert resolve_local_runtime_config().model_name == LocalOpenAICompatibleRuntimeConfig().model_name


def test_factory_with_no_arguments_wires_the_environment_resolved_model_name(
    tmp_path: Path, monkeypatch,
) -> None:
    """Pins the create_app() wiring, not just the resolver in isolation --
    this is the exact gap the STT config had before its factory wiring was
    fixed (Task 1)."""
    _clear_local_runtime_environment(monkeypatch)
    monkeypatch.setenv("VIDEOBOX_LOCAL_MODEL_NAME", "qwen/qwen3.6-35b-a3b")
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(tmp_path / "projects"))

    app = create_app()

    assert app.state.local_runtime_config.model_name == "qwen/qwen3.6-35b-a3b"


def test_factory_with_explicit_config_is_not_overridden_by_the_environment(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("VIDEOBOX_LOCAL_MODEL_NAME", "qwen/qwen3.6-35b-a3b")
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(tmp_path / "projects"))
    explicit = LocalOpenAICompatibleRuntimeConfig(model_name="explicit-override")

    app = create_app(local_runtime_config=explicit)

    assert app.state.local_runtime_config.model_name == "explicit-override"


def test_local_runtime_reaches_lm_studio_from_inside_a_container(monkeypatch) -> None:
    """Inside the container `127.0.0.1` is the container, not the machine.

    LM Studio runs on the host, so a pin to loopback makes the owner's on-screen
    chat structurally impossible in container mode.  Owner approved opening this
    one host path on 2026-08-08 (`docs/development-fast-path.ko.md` §10.14 조항 2-B).
    """
    _clear_local_runtime_environment(monkeypatch)
    monkeypatch.setenv(
        "VIDEOBOX_LOCAL_RUNTIME_BASE_URL",
        "http://host.docker.internal:1234/v1",
    )

    assert resolve_local_runtime_config().base_url == (
        "http://host.docker.internal:1234/v1"
    )


def test_local_runtime_still_refuses_to_leave_this_machine() -> None:
    """The pin exists so a local call never reaches the network.  Widening it to
    the Docker host must not widen it to anything else."""
    for rejected in (
        "http://example.com:1234/v1",
        "https://host.docker.internal:1234/v1",
        "http://host.docker.internal:8080/v1",
        "http://host.docker.internal:1234/v2",
        "http://user:pw@host.docker.internal:1234/v1",
    ):
        try:
            LocalOpenAICompatibleRuntimeConfig(base_url=rejected)
        except ValueError:
            continue
        raise AssertionError(f"accepted a non-local base_url: {rejected}")
