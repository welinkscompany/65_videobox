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


def resolve_user_library_root() -> Path:
    configured = os.environ.get("VIDEOBOX_DATA_ROOT", "").strip()
    if configured:
        return Path(configured) / "videobox-user-library"
    return DEFAULT_PROJECTS_ROOT.parent / "videobox-user-library"


DEFAULT_MEDIA_INBOX_WATCH_PATH = Path(r"G:\내 드라이브\100_videobox")


def resolve_media_inbox_watch_path() -> Path | None:
    """Resolve the folder VideoBox watches for footage moved in from outside.

    Owner decision (2026-08-05): the watched folder is whatever a Google
    Drive desktop client happens to sync to disk. VideoBox has no Drive API
    dependency and does not know it is watching a cloud-synced folder --
    that ignorance is what keeps this off implementation-plan.ko.md's
    "no Google Sheets/Drive coupling" ban. Returns None (watching disabled)
    if explicitly cleared via VIDEOBOX_MEDIA_INBOX_WATCH_PATH="".
    """
    if "VIDEOBOX_MEDIA_INBOX_WATCH_PATH" in os.environ:
        configured = os.environ["VIDEOBOX_MEDIA_INBOX_WATCH_PATH"].strip()
        return Path(configured) if configured else None
    return DEFAULT_MEDIA_INBOX_WATCH_PATH


def resolve_media_inbox_library_root() -> Path:
    """Resolve where verified inbox footage lands. This is a plain local
    folder outside any single project -- the same B-roll should be usable
    from more than one project, matching the existing
    MediaLibraryStore/ProjectAssetMaterializer split (a project only ever
    gets a copy)."""
    configured = os.environ.get("VIDEOBOX_MEDIA_INBOX_LIBRARY_ROOT", "").strip()
    return Path(configured) if configured else resolve_user_library_root() / "media-inbox"


#: 음악과 효과음이 들어오는 폴더 이름. owner 결정 (2026-08-10): 종류는 폴더로
#: 나눈다 -- 한 폴더에 다 넣고 프로그램이 내용을 보고 판단하는 방식은 틀릴 수
#: 있어 채택하지 않았다.
OWNER_AUDIO_WATCH_FOLDER_NAMES: dict[str, str] = {
    "music": "새 음악",
    "sfx": "새 효과음",
}


def resolve_owner_audio_watch_paths(video_watch_path: Path | None) -> dict[str, Path]:
    """음악·효과음 폴더는 `새 영상`의 형제다.

    보관함(`자산화_완료`)이 이미 `감시폴더.parent`로 정해져 있어(`main.py`),
    셋을 같은 부모 아래 두면 보관함 하나를 저절로 함께 쓴다. owner가 만들
    폴더도 이름 두 개로 끝난다.
    """
    if video_watch_path is None:
        return {}
    return {
        media_type: video_watch_path.parent / folder_name
        for media_type, folder_name in OWNER_AUDIO_WATCH_FOLDER_NAMES.items()
    }


def resolve_owner_audio_library_root() -> Path:
    """owner가 직접 넣은 음악·효과음이 사는 곳.

    촬영본 라이브러리와 반드시 다른 폴더다. 한 폴더에 섞으면 촬영본 색인이
    (`_index_library_footage`) mp3를 영상으로 알고 화면 분석을 시도한다.
    """
    configured = os.environ.get("VIDEOBOX_OWNER_AUDIO_LIBRARY_ROOT", "").strip()
    return Path(configured) if configured else resolve_user_library_root() / "owner-audio"


def resolve_media_inbox_watch_enabled() -> bool:
    """Whether the app should start the background media-inbox watcher
    thread on startup. Defaults to False -- create_app() callers that don't
    opt in (including the entire test suite) must never start a thread that
    touches a real Drive-synced folder on disk."""
    return _environment_flag("VIDEOBOX_MEDIA_INBOX_WATCH_ENABLED")


def resolve_media_inbox_watch_interval_seconds() -> float:
    raw = os.environ.get("VIDEOBOX_MEDIA_INBOX_WATCH_INTERVAL_SECONDS", "").strip()
    if not raw:
        return 30.0
    try:
        value = float(raw)
    except ValueError:
        return 30.0
    return value if value > 0 else 30.0


def resolve_database_url() -> str | None:
    configured = os.environ.get("VIDEOBOX_DATABASE_URL", "").strip()
    return configured or None


def resolve_container_snapshot_root() -> Path | None:
    configured = os.environ.get("VIDEOBOX_SNAPSHOT_ROOT", "").strip()
    return Path(configured) if configured else None


def _environment_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _environment_text(name: str, fallback: str) -> str:
    return os.environ.get(name, "").strip() or fallback


def _environment_positive_int(name: str, fallback: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return fallback
    try:
        value = int(raw)
    except ValueError:
        return fallback
    return value if value > 0 else fallback


def resolve_capcut_draft_export_config() -> "CapCutDraftExportConfig":
    """Resolve CapCut draft export for callers that pass no config.

    Output size is configurable because the owner shoots 1920x1080 and also
    needs a vertical canvas for shortform, so landscape must not be assumed.
    """
    defaults = CapCutDraftExportConfig()
    return CapCutDraftExportConfig(
        enabled=_environment_flag("VIDEOBOX_CAPCUT_ENABLED"),
        video_width=_environment_positive_int("VIDEOBOX_CAPCUT_WIDTH", defaults.video_width),
        video_height=_environment_positive_int("VIDEOBOX_CAPCUT_HEIGHT", defaults.video_height),
        video_fps=_environment_positive_int("VIDEOBOX_CAPCUT_FPS", defaults.video_fps),
    )


def resolve_auto_approve_segment_review() -> bool:
    """Owner decision (2026-08-05, Task 21, Option A): place everything
    automatically and review the actual result afterward. Defaults to False
    so callers that do not opt in keep the existing blocking behavior."""
    return _environment_flag("VIDEOBOX_AUTO_APPROVE_SEGMENT_REVIEW")


def resolve_enable_local_media_analysis() -> bool:
    """Resolve whether the container/dev-server factory path should wire the
    real LM Studio vision+embedding worker instead of leaving B-roll analysis
    on `_UnavailableMediaAnalysisService`. Mirrors the STT/CapCut activation
    pattern (Task 1): the uvicorn factory receives no arguments, so this must
    be read from the environment rather than assumed at the call site.
    Defaults to False so existing tests that don't opt in keep the
    fail-visibly-blocked behavior instead of requiring a live LM Studio."""
    return _environment_flag("VIDEOBOX_MEDIA_ANALYSIS_ENABLED")


def resolve_whisper_stt_config() -> "WhisperSTTConfig":
    """Resolve speech-to-text settings for callers that pass no config.

    The container runs `uvicorn videobox_api.main:create_app --factory`, so the
    factory receives no arguments and would otherwise always get the mock
    transcriber.  Staying disabled by default keeps the existing suites, whose
    fixtures feed fake bytes as audio, away from a real model.
    """
    defaults = WhisperSTTConfig()
    return WhisperSTTConfig(
        enabled=_environment_flag("VIDEOBOX_STT_ENABLED"),
        model_size=_environment_text("VIDEOBOX_STT_MODEL_SIZE", defaults.model_size),
        device=_environment_text("VIDEOBOX_STT_DEVICE", defaults.device),
        compute_type=_environment_text("VIDEOBOX_STT_COMPUTE_TYPE", defaults.compute_type),
        language=_environment_text("VIDEOBOX_STT_LANGUAGE", defaults.language or "") or None,
    )


def resolve_local_runtime_config() -> "LocalOpenAICompatibleRuntimeConfig":
    """Resolve the local LM Studio runtime config for callers that pass none.

    The container/dev-server factory (`uvicorn ... --factory`, scripts/run_api.py)
    receives no arguments, so this must be read from the environment rather
    than assumed at the call site -- mirrors resolve_whisper_stt_config().
    model_name defaults to a hardcoded value that has drifted from whatever
    model is actually loaded in LM Studio; env override lets the two match
    without a code change.
    """
    defaults = LocalOpenAICompatibleRuntimeConfig()
    return LocalOpenAICompatibleRuntimeConfig(
        base_url=_environment_text(
            "VIDEOBOX_LOCAL_RUNTIME_BASE_URL", defaults.base_url
        ),
        model_name=_environment_text("VIDEOBOX_LOCAL_MODEL_NAME", defaults.model_name),
        timeout_seconds=_environment_positive_int(
            "VIDEOBOX_LOCAL_RUNTIME_TIMEOUT_SECONDS", defaults.timeout_seconds
        ),
    )


@dataclass(slots=True, frozen=True)
class LocalOpenAICompatibleRuntimeConfig:
    enabled: bool = True
    base_url: str = "http://127.0.0.1:1234/v1"
    model_name: str = "qwen3-35b"
    timeout_seconds: int = 30

    # The pin below exists so a "local" model call can never reach the network.
    # `host.docker.internal` is the one addition: inside the container 127.0.0.1
    # is the container itself, so loopback alone makes the owner's on-screen chat
    # impossible in container mode.  That name resolves to this same machine, so
    # the guarantee is unchanged.  Owner approved 2026-08-08
    # (`docs/development-fast-path.ko.md` §10.14 조항 2-B).
    _CONTAINER_BASE_URL = "http://host.docker.internal:1234/v1"

    def __post_init__(self) -> None:
        base_url = self.base_url
        if base_url not in ("http://127.0.0.1:1234/v1", self._CONTAINER_BASE_URL):
            raise ValueError(
                "local_runtime_config.base_url must be exactly "
                "http://127.0.0.1:1234/v1, or "
                f"{self._CONTAINER_BASE_URL} when running in the container."
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
