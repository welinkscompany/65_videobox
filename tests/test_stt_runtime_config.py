"""The container starts the app factory with no arguments.

Without an environment-resolved config that path silently falls back to
MockSTTProvider, which returns two fixed lines regardless of the audio, so every
caption, segment, and b-roll text match downstream is built on a fake
transcript.  These tests pin the resolver and the factory wiring.
"""

from videobox_api.main import create_app
from videobox_api.provider_factories import _build_stt_provider
from videobox_core_engine.settings import (
    WhisperSTTConfig,
    resolve_whisper_stt_config,
)


def _clear_stt_environment(monkeypatch) -> None:
    for name in (
        "VIDEOBOX_STT_ENABLED",
        "VIDEOBOX_STT_MODEL_SIZE",
        "VIDEOBOX_STT_DEVICE",
        "VIDEOBOX_STT_COMPUTE_TYPE",
        "VIDEOBOX_STT_LANGUAGE",
    ):
        monkeypatch.delenv(name, raising=False)


def test_stt_stays_disabled_when_nothing_is_configured(monkeypatch) -> None:
    _clear_stt_environment(monkeypatch)

    assert resolve_whisper_stt_config().enabled is False


def test_stt_enables_from_the_environment(monkeypatch) -> None:
    _clear_stt_environment(monkeypatch)
    monkeypatch.setenv("VIDEOBOX_STT_ENABLED", "1")

    assert resolve_whisper_stt_config().enabled is True


def test_stt_reads_model_settings_from_the_environment(monkeypatch) -> None:
    _clear_stt_environment(monkeypatch)
    monkeypatch.setenv("VIDEOBOX_STT_ENABLED", "true")
    monkeypatch.setenv("VIDEOBOX_STT_MODEL_SIZE", "medium")
    monkeypatch.setenv("VIDEOBOX_STT_DEVICE", "cuda")
    monkeypatch.setenv("VIDEOBOX_STT_COMPUTE_TYPE", "float16")

    config = resolve_whisper_stt_config()

    assert config.model_size == "medium"
    assert config.device == "cuda"
    assert config.compute_type == "float16"


def test_blank_environment_values_fall_back_to_defaults(monkeypatch) -> None:
    _clear_stt_environment(monkeypatch)
    monkeypatch.setenv("VIDEOBOX_STT_ENABLED", "1")
    monkeypatch.setenv("VIDEOBOX_STT_MODEL_SIZE", "   ")

    assert resolve_whisper_stt_config().model_size == WhisperSTTConfig().model_size


def test_disabled_config_still_builds_the_mock_provider() -> None:
    provider = _build_stt_provider(WhisperSTTConfig(enabled=False))

    assert provider.provider_name == "mock_stt"


def test_app_factory_without_arguments_follows_the_environment(monkeypatch, tmp_path) -> None:
    """The container runs `create_app` with no arguments via uvicorn --factory."""
    _clear_stt_environment(monkeypatch)
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(tmp_path / "data"))

    app = create_app()

    assert app.state.whisper_stt_config.enabled is False
    assert app.state.stt_provider.provider_name == "mock_stt"
