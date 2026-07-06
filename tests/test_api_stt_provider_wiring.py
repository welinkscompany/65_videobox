from __future__ import annotations

from pathlib import Path

from videobox_api.main import create_app
from videobox_core_engine.settings import WhisperSTTConfig
from videobox_provider_interfaces.faster_whisper_stt import FasterWhisperSTTProvider
from videobox_provider_interfaces.stt import MockSTTProvider


def test_create_app_defaults_to_mock_stt_provider(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)

    assert isinstance(app.state.whisper_stt_config, WhisperSTTConfig)
    assert app.state.whisper_stt_config.enabled is False


def test_create_app_with_whisper_enabled_wires_real_provider(tmp_path: Path) -> None:
    app = create_app(
        projects_root=tmp_path,
        whisper_stt_config=WhisperSTTConfig(enabled=True, model_size="tiny", device="cpu", compute_type="int8"),
    )

    assert app.state.whisper_stt_config.enabled is True


def test_build_stt_provider_respects_enabled_flag() -> None:
    from videobox_api.main import _build_stt_provider

    disabled_provider = _build_stt_provider(WhisperSTTConfig(enabled=False))
    assert isinstance(disabled_provider, MockSTTProvider)

    enabled_provider = _build_stt_provider(
        WhisperSTTConfig(enabled=True, model_size="tiny", device="cpu", compute_type="int8", language="en")
    )
    assert isinstance(enabled_provider, FasterWhisperSTTProvider)
    assert enabled_provider.model_size == "tiny"
    assert enabled_provider.language == "en"
