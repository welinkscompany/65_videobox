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
    for name in ("VIDEOBOX_LOCAL_MODEL_NAME", "VIDEOBOX_LOCAL_RUNTIME_TIMEOUT_SECONDS"):
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
