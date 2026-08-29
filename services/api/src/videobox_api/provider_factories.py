from __future__ import annotations

from typing import Any

from videobox_core_engine.settings import CapCutDraftExportConfig, ImageGenerationConfig, TTSEngineConfig, VideoGenerationConfig, WhisperSTTConfig
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
    if config.engine == "local_xtts":
        from videobox_provider_interfaces.local_xtts_provider import LocalXTTSProvider

        return LocalXTTSProvider(
            model_name=config.local_xtts_model_name,
            language=config.language,
            use_gpu=config.local_xtts_use_gpu,
        )
    from videobox_provider_interfaces.chatterbox_tts_provider import ChatterboxTTSProvider

    return ChatterboxTTSProvider(
        language=config.language,
        device="cuda" if config.chatterbox_use_gpu else "cpu",
    )


def _build_scene_image_provider(config: ImageGenerationConfig) -> Any | None:
    """켜지 않았으면 아무것도 만들지 않는다.

    켜지 않았는데 provider를 붙여 두면 화면은 "만들 수 있다"고 보이고 누르는 순간
    실패한다. 켜진 것과 꺼진 것을 화면이 구분할 수 있어야 한다 (§10.14 2-C).
    """
    if not config.enabled:
        return None
    from videobox_provider_interfaces.comfyui_image_generation import (
        ComfyUIHTTPTransport,
        ComfyUIImageGenerationProvider,
    )

    return ComfyUIImageGenerationProvider(
        transport=ComfyUIHTTPTransport(base_url=config.base_url),
        config=config,
    )


def _build_scene_video_provider(config: VideoGenerationConfig) -> Any | None:
    """`_build_scene_image_provider`와 같은 이유 -- 켜지 않았으면 아무것도
    안 만든다. owner 결정 2026-08-29(2회차, "원래 만든거외에 별도로 만들자") --
    이 provider는 `SceneVideoService`(정지 이미지+zoompan과는 별개 경로)에만 쓰인다."""
    if not config.enabled:
        return None
    from videobox_provider_interfaces.comfyui_image_generation import ComfyUIHTTPTransport
    from videobox_provider_interfaces.comfyui_video_generation import ComfyUIVideoGenerationProvider

    return ComfyUIVideoGenerationProvider(
        transport=ComfyUIHTTPTransport(base_url=config.base_url),
        config=config,
    )
