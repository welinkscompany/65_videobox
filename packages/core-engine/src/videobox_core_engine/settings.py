from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_PROJECTS_ROOT = Path(
    r"D:\AI_Workspace_louis_office_50\20_project\65_videobox-project"
)


@dataclass(slots=True, frozen=True)
class LocalOpenAICompatibleRuntimeConfig:
    enabled: bool = True
    base_url: str = "http://127.0.0.1:1234/v1"
    model_name: str = "qwen3-35b"
    timeout_seconds: int = 30

    def __post_init__(self) -> None:
        base_url = self.base_url.strip().rstrip("/")
        if not base_url:
            raise ValueError("local_runtime_config.base_url must not be blank.")
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("local_runtime_config.base_url must be a valid HTTP(S) URL.")

        model_name = self.model_name.strip()
        if not model_name:
            raise ValueError("local_runtime_config.model_name must not be blank.")
        if self.timeout_seconds <= 0:
            raise ValueError("local_runtime_config.timeout_seconds must be greater than zero.")

        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(self, "model_name", model_name)


@dataclass(slots=True, frozen=True)
class AutoCutConfig:
    min_clip_duration: float = 5.0
    max_clip_duration: float = 90.0
    auto_cut_threshold: float = 90.0
    scene_threshold: float = 0.4
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
