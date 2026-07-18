from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


DEFAULT_PROJECTS_ROOT = Path(
    r"D:\AI_Workspace_louis_office_50\20_project\65_videobox-project"
)


def resolve_projects_root() -> Path:
    configured = os.environ.get("VIDEOBOX_DATA_ROOT", "").strip()
    return Path(configured) if configured else DEFAULT_PROJECTS_ROOT


@dataclass(slots=True, frozen=True)
class LocalOpenAICompatibleRuntimeConfig:
    enabled: bool = True
    base_url: str = "http://127.0.0.1:1234/v1"
    model_name: str = "qwen3-35b"
    timeout_seconds: int = 30

    def __post_init__(self) -> None:
        base_url = self.base_url
        if base_url != "http://127.0.0.1:1234/v1":
            raise ValueError(
                "local_runtime_config.base_url must be exactly http://127.0.0.1:1234/v1."
            )

        model_name = self.model_name.strip()
        if not model_name:
            raise ValueError("local_runtime_config.model_name must not be blank.")
        if self.timeout_seconds <= 0:
            raise ValueError("local_runtime_config.timeout_seconds must be greater than zero.")

        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(self, "model_name", model_name)


@dataclass(slots=True, frozen=True)
class WhisperSTTConfig:
    # Defaults to disabled so create_app() callers that don't opt in (including the
    # existing test suite, which feeds fake byte content as "audio") keep the
    # deterministic MockSTTProvider instead of silently invoking a real model.
    enabled: bool = False
    model_size: str = "small"
    device: str = "cpu"
    compute_type: str = "int8"
    language: str | None = "ko"
    ffmpeg_binary: str = "ffmpeg"

    def __post_init__(self) -> None:
        if not self.model_size.strip():
            raise ValueError("whisper_stt_config.model_size must not be blank.")
        if not self.device.strip():
            raise ValueError("whisper_stt_config.device must not be blank.")
        if not self.compute_type.strip():
            raise ValueError("whisper_stt_config.compute_type must not be blank.")
        if not self.ffmpeg_binary.strip():
            raise ValueError("whisper_stt_config.ffmpeg_binary must not be blank.")


@dataclass(slots=True, frozen=True)
class CapCutDraftExportConfig:
    # Defaults to disabled: the `pycapcut` package pulls in Windows-only
    # dependencies (uiautomation/comtypes) that are not installed by default
    # and would break create_app() callers (including tests) that don't need
    # a real CapCut draft.
    enabled: bool = False
    video_width: int = 1280
    video_height: int = 720
    video_fps: int = 30

    def __post_init__(self) -> None:
        if self.video_width <= 0:
            raise ValueError("capcut_draft_export_config.video_width must be greater than zero.")
        if self.video_height <= 0:
            raise ValueError("capcut_draft_export_config.video_height must be greater than zero.")
        if self.video_fps <= 0:
            raise ValueError("capcut_draft_export_config.video_fps must be greater than zero.")


@dataclass(slots=True, frozen=True)
class TTSEngineConfig:
    # Defaults to disabled: gtts needs live network access, elevenlabs needs a
    # paid API key, and local_xtts needs a heavy optional install — none of
    # these should run implicitly for create_app() callers that don't opt in.
    enabled: bool = False
    engine: str = "gtts"
    language: str = "ko"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    local_xtts_model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    local_xtts_use_gpu: bool = False

    def __post_init__(self) -> None:
        valid_engines = {"gtts", "elevenlabs", "local_xtts"}
        if self.engine not in valid_engines:
            raise ValueError(f"tts_engine_config.engine must be one of {sorted(valid_engines)}.")
        if not self.language.strip():
            raise ValueError("tts_engine_config.language must not be blank.")
        if self.engine == "elevenlabs":
            if not self.elevenlabs_api_key.strip():
                raise ValueError("tts_engine_config.elevenlabs_api_key is required for the elevenlabs engine.")
            if not self.elevenlabs_voice_id.strip():
                raise ValueError("tts_engine_config.elevenlabs_voice_id is required for the elevenlabs engine.")


@dataclass(slots=True, frozen=True)
class AutoCutConfig:
    min_clip_duration: float = 5.0
    max_clip_duration: float = 90.0
    auto_cut_threshold: float = 90.0
    scene_threshold: float = 0.4
    # Much more sensitive than scene_threshold: used only to check whether a
    # candidate clip has *any* motion at all (frozen/static-shot detection),
    # not to find cut points. Reusing scene_threshold here would make almost
    # every clip longer than static_duration look "static" and get discarded,
    # since interior frames rarely exceed the higher cut-point threshold.
    static_check_scene_threshold: float = 0.02
    initial_scene_ignore_seconds: float = 0.5
    cut_point_min_spacing: float = 2.0
    blackdetect_min_duration: float = 0.5
    blackdetect_picture_threshold: float = 0.95
    dark_brightness: float = 15.0
    static_duration: float = 30.0
    merge_threshold: float = 10.0

    def __post_init__(self) -> None:
        if self.min_clip_duration <= 0:
            raise ValueError("auto_cut.min_clip_duration must be greater than zero.")
        if self.max_clip_duration <= self.min_clip_duration:
            raise ValueError("auto_cut.max_clip_duration must be greater than min_clip_duration.")
        if self.auto_cut_threshold <= 0:
            raise ValueError("auto_cut.auto_cut_threshold must be greater than zero.")
        if not 0.0 <= self.scene_threshold <= 1.0:
            raise ValueError("auto_cut.scene_threshold must be between 0 and 1.")
        if not 0.0 <= self.static_check_scene_threshold <= 1.0:
            raise ValueError("auto_cut.static_check_scene_threshold must be between 0 and 1.")
        if self.initial_scene_ignore_seconds < 0:
            raise ValueError("auto_cut.initial_scene_ignore_seconds must not be negative.")
        if self.cut_point_min_spacing < 0:
            raise ValueError("auto_cut.cut_point_min_spacing must not be negative.")
        if self.blackdetect_min_duration <= 0:
            raise ValueError("auto_cut.blackdetect_min_duration must be greater than zero.")
        if not 0.0 <= self.blackdetect_picture_threshold <= 1.0:
            raise ValueError("auto_cut.blackdetect_picture_threshold must be between 0 and 1.")
        if self.dark_brightness < 0:
            raise ValueError("auto_cut.dark_brightness must not be negative.")
        if self.static_duration <= 0:
            raise ValueError("auto_cut.static_duration must be greater than zero.")
        if self.merge_threshold < 0:
            raise ValueError("auto_cut.merge_threshold must not be negative.")
