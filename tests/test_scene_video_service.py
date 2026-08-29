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

from videobox_core_engine.scene_video_service import SceneVideoGenerationError, SceneVideoService
from videobox_domain_models.assets import AssetType
from videobox_provider_interfaces.visual_generation import GeneratedSceneVideo, SceneVideoRequest
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

    def generate_video(self, request: SceneVideoRequest) -> GeneratedSceneVideo:
        self.requests.append(request)
        return GeneratedSceneVideo(
            provider_name=self.provider_name,
            video_bytes=_webm_bytes(),
            file_name="videobox-scene-video_00001_.webm",
            metadata={"model_name": "wan2.1_t2v_1.3B_fp16.safetensors", "seed": request.seed, "elapsed_sec": 96.4},
        )


class _RefusingProvider:
    provider_name = "comfyui"

    def generate_video(self, request: SceneVideoRequest) -> GeneratedSceneVideo:
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


def test_an_unknown_quality_is_refused_before_the_gpu_is_woken_up(tmp_path: Path) -> None:
    provider = _StubProvider()
    service, _store, project_id = _service(tmp_path, provider)

    with pytest.raises(SceneVideoGenerationError) as exc:
        service.generate_scene_video(project_id=project_id, prompt="x", segment_id="script-1", quality="ultra")

    assert exc.value.code == "invalid"
    assert provider.requests == []


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
