from __future__ import annotations

from typing import Any

from videobox_core_engine.settings import CapCutDraftExportConfig, TTSEngineConfig, WhisperSTTConfig
from videobox_provider_interfaces.faster_whisper_stt import FasterWhisperSTTProvider
from videobox_provider_interfaces.stt import MockSTTProvider, STTProvider
from videobox_storage.local_project_store import LocalProjectStore


def _build_stt_provider(config: WhisperSTTConfig) -> STTProvider:
    if not config.enabled:
        return MockSTTProvider()
    return FasterWhisperSTTProvider(
        model_size=config.model_size,
        device=config.device,
        compute_type=config.compute_type,
        language=config.language,
        ffmpeg_binary=config.ffmpeg_binary,
    )


def _build_pycapcut_exporter(config: CapCutDraftExportConfig, *, store: LocalProjectStore) -> Any | None:
    if not config.enabled:
        return None
    from videobox_capcut_export.pycapcut_adapter import PyCapCutRealExportAdapter

    return PyCapCutRealExportAdapter(
        store=store,
        video_width=config.video_width,
        video_height=config.video_height,
        video_fps=config.video_fps,
    )


def _build_tts_provider(config: TTSEngineConfig) -> Any | None:
    if not config.enabled:
        return None
    if config.engine == "gtts":
        from videobox_provider_interfaces.gtts_provider import GTTSProvider

        return GTTSProvider(language=config.language)
    if config.engine == "elevenlabs":
        from videobox_provider_interfaces.elevenlabs_tts_provider import ElevenLabsTTSProvider

        return ElevenLabsTTSProvider(
            api_key=config.elevenlabs_api_key,
            voice_id=config.elevenlabs_voice_id,
        )
    from videobox_provider_interfaces.local_xtts_provider import LocalXTTSProvider

    return LocalXTTSProvider(
        model_name=config.local_xtts_model_name,
        language=config.language,
        use_gpu=config.local_xtts_use_gpu,
    )
