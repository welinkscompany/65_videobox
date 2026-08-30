"""만든 영상이 **자산으로 들어와서 그 장면을 실제로 채우는가**. owner 결정
2026-08-29(2회차, "원래 만든거외에 별도로 만들자").

`test_scene_image_service.py`와 같은 자리다 -- provider가 바이트를 돌려주는
것까지가 아니라, 그 다음(프로젝트 자산이 되고 렌더가 아는 mp4 모양이 되는가,
GIF를 같이 요청하면 애니메이션 GIF가 `AssetType.IMAGE`로 등록되는가)을 잰다.

`SceneImageService`는 이 파일에서 손대지 않는다 -- 정지 이미지+zoompan
경로는 그대로다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from videobox_core_engine.library_ingest import LibraryIngestService
from videobox_core_engine.scene_video_service import SceneVideoGenerationError, SceneVideoService
from videobox_domain_models.assets import AssetType
from videobox_provider_interfaces.visual_generation import GeneratedSceneVideo, SceneVideoRequest
from videobox_storage.library_user_asset_store import LibraryUserAssetStore
from videobox_storage.local_project_store import LocalProjectStore


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe are required to transcode a generated clip",
)


def _webm_bytes() -> bytes:
    """진짜 webm이어야 한다 -- 가짜 바이트는 ffmpeg 변환 단계를 못 지난다."""
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "seed.webm"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=orange:s=64x64:d=1:r=10",
             "-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", str(target)],
            check=True, capture_output=True, timeout=60,
        )
        return target.read_bytes()


class _StubProvider:
    provider_name = "comfyui"

    def __init__(self) -> None:
        self.requests: list[SceneVideoRequest] = []
        self.on_submitted_calls: list[object] = []
        self.cancel_events: list[object] = []

    def generate_video(self, request: SceneVideoRequest, *, on_submitted=None, cancel_event=None) -> GeneratedSceneVideo:
        self.requests.append(request)
        self.on_submitted_calls.append(on_submitted)
        self.cancel_events.append(cancel_event)
        if on_submitted is not None:
            on_submitted("job-1")
        return GeneratedSceneVideo(
            provider_name=self.provider_name,
            video_bytes=_webm_bytes(),
            file_name="videobox-scene-video_00001_.webm",
            metadata={"model_name": "wan2.1_t2v_1.3B_fp16.safetensors", "seed": request.seed, "elapsed_sec": 96.4},
        )


class _RefusingProvider:
    provider_name = "comfyui"

    def generate_video(self, request: SceneVideoRequest, *, on_submitted=None, cancel_event=None) -> GeneratedSceneVideo:
        from videobox_provider_interfaces.comfyui_image_generation import ComfyUIProviderError

        raise ComfyUIProviderError("ComfyUI local resource is unavailable.", "blocked")


class _PassThroughWriter:
    def write(self, *, project_id: str, line: str, vertical: bool) -> str:
        return f"a short clip of: {line[:40]}, cinematic"


def _service(
    tmp_path: Path, provider: object | None = None, *, writer: object | None = _PassThroughWriter(),
) -> tuple[SceneVideoService, LocalProjectStore, str]:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="영상 만들기")
    service = SceneVideoService(store=store, provider=provider or _StubProvider(), prompt_writer=writer)
    return service, store, project.project_id


def test_a_generated_clip_becomes_a_render_ready_mp4_asset(tmp_path: Path) -> None:
    service, store, project_id = _service(tmp_path)

    result = service.generate_scene_video(project_id=project_id, prompt="해 뜨는 바다", segment_id="script-3")

    assets = store.list_assets(project_id=project_id)
    clip = next(item for item in assets if item["asset_type"] == AssetType.BROLL_VIDEO.value)
    assert result["scene_asset_id"] == clip["asset_id"]
    assert result["gif_asset_id"] is None

    clip_path = store.resolve_storage_uri(project_id=project_id, storage_uri=str(clip["storage_uri"]))
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name", "-of", "json", str(clip_path)],
        capture_output=True, text=True, timeout=30, check=True,
    )
    parsed = json.loads(probe.stdout)
    video_stream = next(stream for stream in parsed["streams"] if stream["codec_type"] == "video")
    assert video_stream["codec_name"] == "h264"


def test_asking_for_a_gif_registers_it_as_a_plain_image_asset(tmp_path: Path) -> None:
    """새 자산 종류를 만들지 않는다 -- `LibraryPreviewPane.tsx`가 이미
    `AssetType.IMAGE`를 `<img src=...>`로 그리고 있어서, 애니메이션 GIF도 그
    자리에 그냥 놓으면 브라우저가 알아서 재생한다."""
    service, store, project_id = _service(tmp_path)

    result = service.generate_scene_video(
        project_id=project_id, prompt="해 뜨는 바다", segment_id="script-1", make_gif=True,
    )

    assert result["gif_asset_id"] is not None
    gif = next(
        item for item in store.list_assets(project_id=project_id)
        if item["asset_id"] == result["gif_asset_id"]
    )
    assert gif["asset_type"] == AssetType.IMAGE.value
    gif_path = store.resolve_storage_uri(project_id=project_id, storage_uri=str(gif["storage_uri"]))
    assert gif_path.suffix == ".gif"
    # 진짜 GIF 헤더인지("GIF87a"/"GIF89a") 확인한다 -- 확장자만 바꾼 다른 파일이면 안 된다.
    assert gif_path.read_bytes()[:6] in (b"GIF87a", b"GIF89a")
    assert gif["metadata"]["source_video_asset_id"] == result["scene_asset_id"]


def test_a_generated_clip_also_lands_in_the_shared_library(tmp_path: Path) -> None:
    """owner 요청(2026-08-29, 3회차): "이렇게 생성된것도 우리 자산으로
    들어가도록". 프로젝트 자산과 별개로 자료실(여러 프로젝트가 나눠 쓰는
    검색 가능한 라이브러리)에도 실제로 등록되는지 잰다 -- 가짜가 아니라 진짜
    `LibraryIngestService`로."""
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project(name="영상 만들기")
    library_store = LibraryUserAssetStore(tmp_path / "library-db")
    library_ingest = LibraryIngestService(store=library_store, managed_root=tmp_path / "library-managed")
    service = SceneVideoService(
        store=store, provider=_StubProvider(), prompt_writer=_PassThroughWriter(), library_ingest=library_ingest,
    )

    result = service.generate_scene_video(
        project_id=project.project_id, prompt="해 뜨는 바다", segment_id="script-1", make_gif=True,
    )

    assert result["library_asset_id"] is not None
    library_asset = library_store.get_asset(result["library_asset_id"])
    assert library_asset is not None
    assert library_asset.media_type.value == "broll"

    assert result["gif_library_asset_id"] is not None
    gif_library_asset = library_store.get_asset(result["gif_library_asset_id"])
    assert gif_library_asset is not None
    assert gif_library_asset.media_type.value == "image"


def test_a_broken_library_does_not_lose_the_project_asset_that_took_18_minutes(tmp_path: Path) -> None:
    """자료실 등록은 곁가지다 -- 실패해도 방금 만든 프로젝트 자산(렌더에 실제로
    쓰이는 것)까지 지우면 안 된다."""
    class _BrokenLibraryIngest:
        def ingest(self, **_kwargs: object) -> dict[str, object]:
            raise RuntimeError("library disk is full")

    service, store, project_id = _service(tmp_path)
    service.library_ingest = _BrokenLibraryIngest()

    result = service.generate_scene_video(project_id=project_id, prompt="해 뜨는 바다", segment_id="script-1")

    assert result["library_asset_id"] is None
    # 코드리뷰(2026-08-30)로 잡힌 결함 -- 실패가 어디에도 안 남아서 왜 안 됐는지
    # 알 방법이 없었다. 이제 error_code가 남아야 한다.
    assert result["library_ingest_error"] == "RuntimeError"
    clip = next(
        item for item in store.list_assets(project_id=project_id)
        if item["asset_id"] == result["scene_asset_id"]
    )
    assert clip is not None
    assert clip["metadata"]["library_ingest_error"] == "RuntimeError"


def test_a_broken_metadata_patch_does_not_lose_the_project_asset_either(tmp_path: Path) -> None:
    """코드리뷰(2026-08-30)로 잡힌 결함 -- `library_asset_id`를 목록에서도
    보이게 하려고 생성 직후 `update_asset_metadata`로 다시 적어 두는데, 이
    호출 자체가 실패하면(예: 일시적 DB 쓰기 오류) `_ingest_into_library`와
    달리 자기 실패를 삼키지 않아서 방금 만든 20분짜리 자산까지 보상
    삭제(compensate)됐었다. `_ingest_into_library`와 같은 보호를 받아야 한다."""
    class _BrokenMetadataPatchStore:
        def __init__(self, real_store: LocalProjectStore) -> None:
            self._real = real_store

        def update_asset_metadata(self, **_kwargs: object) -> None:
            raise RuntimeError("asset index is locked")

        def __getattr__(self, name: str) -> object:
            return getattr(self._real, name)

    real_store = LocalProjectStore(tmp_path)
    project = real_store.bootstrap_project(name="영상 만들기")
    service = SceneVideoService(
        store=_BrokenMetadataPatchStore(real_store), provider=_StubProvider(), prompt_writer=_PassThroughWriter(),
    )

    result = service.generate_scene_video(project_id=project.project_id, prompt="해 뜨는 바다", segment_id="script-1")

    assert result["scene_asset_id"]
    clip = next(
        item for item in real_store.list_assets(project_id=project.project_id)
        if item["asset_id"] == result["scene_asset_id"]
    )
    assert clip is not None


def test_the_clip_says_which_scene_it_was_made_for(tmp_path: Path) -> None:
    service, store, project_id = _service(tmp_path)

    service.generate_scene_video(project_id=project_id, prompt="해 뜨는 바다", segment_id="script-3")

    clip = next(
        item for item in store.list_assets(project_id=project_id)
        if item["asset_type"] == AssetType.BROLL_VIDEO.value
    )
    assert clip["metadata"]["scene_segment_id"] == "script-3"
    assert clip["metadata"]["generated_by"] == "comfyui"
    assert clip["metadata"]["prompt"] == "해 뜨는 바다"


def test_a_landscape_project_does_not_get_a_vertical_request(tmp_path: Path) -> None:
    provider = _StubProvider()
    service, _store, project_id = _service(tmp_path, provider)

    service.generate_scene_video(project_id=project_id, prompt="x", segment_id="script-1")
    service.generate_scene_video(project_id=project_id, prompt="x", segment_id="script-2", vertical=True)

    assert (provider.requests[0].width, provider.requests[0].height) == (1920, 1080)
    assert (provider.requests[1].width, provider.requests[1].height) == (1080, 1920)


def test_quality_defaults_to_full_and_preview_asks_for_less(tmp_path: Path) -> None:
    """빠른 미리보기(owner 요청 2026-08-29, 3회차) -- 실측: full은 1920x1080·81프레임·
    20스텝(약 18~23분), preview는 512x288·17프레임·8스텝(약 12초)."""
    provider = _StubProvider()
    service, _store, project_id = _service(tmp_path, provider)

    result_full = service.generate_scene_video(project_id=project_id, prompt="x", segment_id="script-1")
    result_preview = service.generate_scene_video(
        project_id=project_id, prompt="x", segment_id="script-2", quality="preview",
    )

    assert result_full["quality"] == "full"
    assert (provider.requests[0].width, provider.requests[0].height) == (1920, 1080)
    assert (provider.requests[0].length_frames, provider.requests[0].steps) == (81, 20)

    assert result_preview["quality"] == "preview"
    assert (provider.requests[1].width, provider.requests[1].height) == (512, 288)
    assert (provider.requests[1].length_frames, provider.requests[1].steps) == (17, 8)


def test_standard_quality_sits_between_preview_and_full(tmp_path: Path) -> None:
    """중간 화질(owner 요청 2026-08-30) -- 실측(RTX 5090, 2026-08-30):
    1280x720·65프레임·16스텝이 약 2분 19초. 미리보기(12초)와 고화질(18~20분)
    사이에 아무것도 없어서 완성에 가까운 화질이 필요한데 18분을 못 기다리는
    경우 고를 자리가 없었다."""
    provider = _StubProvider()
    service, _store, project_id = _service(tmp_path, provider)

    result = service.generate_scene_video(
        project_id=project_id, prompt="x", segment_id="script-1", quality="standard",
    )

    assert result["quality"] == "standard"
    assert (provider.requests[0].width, provider.requests[0].height) == (1280, 720)
    assert (provider.requests[0].length_frames, provider.requests[0].steps) == (65, 16)


def test_standard_quality_is_vertical_when_asked(tmp_path: Path) -> None:
    provider = _StubProvider()
    service, _store, project_id = _service(tmp_path, provider)

    service.generate_scene_video(
        project_id=project_id, prompt="x", segment_id="script-1", quality="standard", vertical=True,
    )

    assert (provider.requests[0].width, provider.requests[0].height) == (720, 1280)


def test_an_unknown_quality_is_refused_before_the_gpu_is_woken_up(tmp_path: Path) -> None:
    provider = _StubProvider()
    service, _store, project_id = _service(tmp_path, provider)

    with pytest.raises(SceneVideoGenerationError) as exc:
        service.generate_scene_video(project_id=project_id, prompt="x", segment_id="script-1", quality="ultra")

    assert exc.value.code == "invalid"
    assert provider.requests == []


def test_the_cancel_wiring_reaches_the_provider_unchanged(tmp_path: Path) -> None:
    """취소 버튼(owner 요청 2026-08-29 3회차) -- 실제로 멈추는 로직은
    provider가 갖고 있다(`test_comfyui_video_generation_provider.py`가 잰다).
    여기서는 서비스가 그 둘(콜백·이벤트)을 provider까지 그대로 전달하는지만
    잰다."""
    import threading

    provider = _StubProvider()
    service, _store, project_id = _service(tmp_path, provider)
    cancel_event = threading.Event()
    seen_prompt_ids: list[str] = []

    service.generate_scene_video(
        project_id=project_id, prompt="x", segment_id="script-1",
        on_prompt_submitted=seen_prompt_ids.append, cancel_event=cancel_event,
    )

    assert seen_prompt_ids == ["job-1"]
    assert provider.cancel_events == [cancel_event]


def test_two_runs_of_the_same_prompt_are_not_the_same_video(tmp_path: Path) -> None:
    provider = _StubProvider()
    service, _store, project_id = _service(tmp_path, provider)

    service.generate_scene_video(project_id=project_id, prompt="x", segment_id="script-1")
    service.generate_scene_video(project_id=project_id, prompt="x", segment_id="script-1")

    assert provider.requests[0].seed != provider.requests[1].seed


def test_a_blocked_comfyui_leaves_no_half_registered_asset_behind(tmp_path: Path) -> None:
    service, store, project_id = _service(tmp_path, _RefusingProvider())

    with pytest.raises(SceneVideoGenerationError) as exc:
        service.generate_scene_video(project_id=project_id, prompt="x", segment_id="script-1")

    assert exc.value.code == "blocked"
    assert store.list_assets(project_id=project_id) == []


def test_an_empty_prompt_is_refused_before_the_gpu_is_woken_up(tmp_path: Path) -> None:
    provider = _StubProvider()
    service, _store, project_id = _service(tmp_path, provider)

    with pytest.raises(SceneVideoGenerationError) as exc:
        service.generate_scene_video(project_id=project_id, prompt="   ", segment_id="script-1")

    assert exc.value.code == "invalid"
    assert provider.requests == []


def test_without_any_writer_a_korean_line_is_refused_before_the_gpu_wakes_up(tmp_path: Path) -> None:
    service, store, project_id = _service(tmp_path, writer=None)

    with pytest.raises(SceneVideoGenerationError) as exc:
        service.generate_scene_video(project_id=project_id, prompt="해 뜨는 바다", segment_id="script-1")

    assert exc.value.code == "invalid"
    assert str(exc.value) == "scene_video_prompt_needs_english"
