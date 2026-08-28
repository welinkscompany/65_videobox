"""만든 그림이 **자산으로 들어와서 그 장면을 실제로 채우는가**.

부품을 만드는 것과 제품을 만드는 것은 다르다(`CLAUDE.md` §4). 그림을 받아 오는
것까지는 provider가 하고, 여기서 재는 것은 그 다음이다 -- 프로젝트 자산이 되고,
그 장면에 붙고, 초안 준비가 그 장면을 더 이상 공백으로 세지 않는가.

**왜 mp4도 같이 만드는가.** 렌더 경로는 B-roll 입력을 영상으로 연다
(`ffmpeg_final_renderer.py`: broll 소스는 `is_image=False`로 들어가고
`_probe_media_duration`이 길이를 요구한다). PNG를 B-roll 자리에 그냥 꽂으면
초안까지는 통과하고 **완성본에서 터진다.** 렌더 경로는 둘이라 고치면 두 곳을
같이 고쳐야 하므로(2026-08-11 교훈), 렌더를 건드리는 대신 그림을 그 경로가
이미 아는 모양으로 바꿔 넣는다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from videobox_core_engine.scene_image_service import SceneImageGenerationError, SceneImageService
from videobox_domain_models.assets import AssetType
from videobox_provider_interfaces.visual_generation import GeneratedSceneImage, SceneImageRequest
from videobox_storage.local_project_store import LocalProjectStore


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe are required to turn a still into a scene clip",
)


def _png_bytes() -> bytes:
    """진짜 PNG여야 한다. 가짜 바이트를 쓰면 ffmpeg 단계가 시험을 안 지난다.

    단색이 아니라 한쪽에 치우친 사각형을 넣는다 -- 단색이면 줌이 실제로 움직여도
    프레임끼리 똑같아 보여서 팬·줌이 걸렸는지 시험으로 잡을 수 없다.
    """
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "seed.png"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=orange:s=320x180",
             "-vf", "drawbox=x=20:y=20:w=60:h=60:color=red:t=fill",
             "-frames:v", "1", str(target)],
            check=True, capture_output=True, timeout=60,
        )
        return target.read_bytes()


class _StubProvider:
    provider_name = "comfyui"

    def __init__(self) -> None:
        self.requests: list[SceneImageRequest] = []

    def generate_image(self, request: SceneImageRequest) -> GeneratedSceneImage:
        self.requests.append(request)
        return GeneratedSceneImage(
            provider_name=self.provider_name,
            image_bytes=_png_bytes(),
            file_name="videobox-scene_00001_.png",
            metadata={"model_name": "flux1-dev.safetensors", "seed": request.seed, "elapsed_sec": 22.3,
                      "commercial_use_is_unrestricted": False},
        )


class _RefusingProvider:
    provider_name = "comfyui"

    def generate_image(self, request: SceneImageRequest) -> GeneratedSceneImage:
        from videobox_provider_interfaces.comfyui_image_generation import ComfyUIProviderError

        raise ComfyUIProviderError("ComfyUI local resource is unavailable.", "blocked")


class _PassThroughWriter:
    """한국어를 영어 묘사로 바꾸는 자리. 여기서는 그 번역 품질이 아니라 **자산 쪽**을
    재므로, 유진이 답했다는 사실만 흉내 내고 내용은 그대로 둔다."""

    def write(self, *, project_id: str, line: str, vertical: bool) -> str:
        return f"an illustration of: {line[:40]}, cinematic"


def _service(
    tmp_path: Path, provider: object | None = None, *, writer: object | None = _PassThroughWriter(),
) -> tuple[SceneImageService, LocalProjectStore, str]:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="그림 만들기")
    service = SceneImageService(store=store, provider=provider or _StubProvider(), prompt_writer=writer)
    return service, store, project.project_id


def test_one_generated_image_becomes_two_assets_a_picture_and_a_scene_clip(tmp_path: Path) -> None:
    service, store, project_id = _service(tmp_path)

    result = service.generate_scene_image(
        project_id=project_id, prompt="해 뜨는 바다", segment_id="script-3", duration_sec=4.0,
    )

    assets = store.list_assets(project_id=project_id)
    image = next(item for item in assets if item["asset_type"] == AssetType.IMAGE.value)
    clip = next(item for item in assets if item["asset_type"] == AssetType.BROLL_VIDEO.value)
    assert result["image_asset_id"] == image["asset_id"]
    assert result["scene_asset_id"] == clip["asset_id"]

    # 그림은 겹치기·썸네일에 그대로 쓰이고, 장면 클립은 렌더가 아는 모양이다.
    clip_path = store.resolve_storage_uri(project_id=project_id, storage_uri=str(clip["storage_uri"]))
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(clip_path)],
        capture_output=True, text=True, timeout=30, check=True,
    )
    parsed = json.loads(probe.stdout)
    assert any(stream["codec_type"] == "video" for stream in parsed["streams"])
    assert float(parsed["format"]["duration"]) >= 4.0


def test_the_clip_is_not_a_frozen_still_it_pans_and_zooms(tmp_path: Path) -> None:
    """owner 요청(2026-08-28): 정지 화면이 아니라 캡컷처럼 은은하게 움직여야 한다.

    ffmpeg만으로 되는 팬·줌(Ken Burns)으로 승인됐다 -- AI 영상 생성은 범위 밖이다.
    첫 프레임과 끝 프레임을 뽑아 SSIM으로 비교한다. 완전히 같으면(1.0) 예전처럼
    멈춰 있는 것이고, 줌이 실제로 이어졌다면 확실히 갈라진다.
    """
    service, store, project_id = _service(tmp_path)

    service.generate_scene_image(
        project_id=project_id, prompt="해 뜨는 바다", segment_id="script-1", duration_sec=3.0,
    )

    clip = next(
        item for item in store.list_assets(project_id=project_id)
        if item["asset_type"] == AssetType.BROLL_VIDEO.value
    )
    clip_path = store.resolve_storage_uri(project_id=project_id, storage_uri=str(clip["storage_uri"]))

    with tempfile.TemporaryDirectory() as folder:
        first = Path(folder) / "first.png"
        last = Path(folder) / "last.png"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(clip_path), "-vf", "select=eq(n\\,0)",
             "-vframes", "1", str(first)],
            check=True, capture_output=True, timeout=30,
        )
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-sseof", "-1", "-i", str(clip_path),
             "-vframes", "1", str(last)],
            check=True, capture_output=True, timeout=30,
        )
        probe = subprocess.run(
            ["ffmpeg", "-i", str(first), "-i", str(last), "-lavfi", "ssim", "-f", "null", "-"],
            capture_output=True, text=True, timeout=30,
        )
        ssim_line = next(line for line in probe.stderr.splitlines() if "SSIM" in line)
        # "All:0.993885" 꼴에서 값만 뽑는다.
        all_value = float(ssim_line.split("All:")[1].split(" ")[0])

    assert all_value < 0.999, f"clip looks frozen (SSIM {all_value}): {ssim_line}"


def test_the_clip_says_which_scene_it_was_made_for(tmp_path: Path) -> None:
    """대본의 어느 장면인지 안 적으면, 초안 준비가 그림을 **엉뚱한 장면**에 붙인다.

    준비는 B-roll을 순서대로 짝지어 왔다(`zip(segments, playable_broll)`). 만든
    그림은 짝이 정해져 있으므로 그 사실을 자산이 들고 있어야 한다.
    """
    service, store, project_id = _service(tmp_path)

    service.generate_scene_image(project_id=project_id, prompt="해 뜨는 바다", segment_id="script-3")

    clip = next(
        item for item in store.list_assets(project_id=project_id)
        if item["asset_type"] == AssetType.BROLL_VIDEO.value
    )
    assert clip["metadata"]["scene_segment_id"] == "script-3"
    assert clip["metadata"]["generated_by"] == "comfyui"
    assert clip["metadata"]["prompt"] == "해 뜨는 바다"
    # 라이선스는 실행 중에 안 보인다. 자산이 스스로 말하게 둔다 (§10.14 2-C).
    assert clip["metadata"]["commercial_use_is_unrestricted"] is False


def test_the_picture_is_named_after_the_scene_so_the_owner_can_tell_them_apart(tmp_path: Path) -> None:
    """13개가 똑같아 보이던 추천 카드와 같은 함정이다(2026-08-20). 제목이 없으면
    라이브러리에서 열 장이 전부 `videobox-scene_00001_.png`로 보인다."""
    service, store, project_id = _service(tmp_path)

    service.generate_scene_image(project_id=project_id, prompt="해 뜨는 바다", segment_id="script-3")

    image = next(
        item for item in store.list_assets(project_id=project_id)
        if item["asset_type"] == AssetType.IMAGE.value
    )
    assert image["metadata"]["title"] == "3번째 장면 그림"


def test_a_landscape_project_does_not_get_a_vertical_picture(tmp_path: Path) -> None:
    """F-9의 재발 자리다 -- 세로가 기본이 되어 롱폼까지 전부 세로로 나갔었다."""
    provider = _StubProvider()
    service, _store, project_id = _service(tmp_path, provider)

    service.generate_scene_image(project_id=project_id, prompt="x", segment_id="script-1")
    service.generate_scene_image(project_id=project_id, prompt="x", segment_id="script-2", vertical=True)

    assert (provider.requests[0].width, provider.requests[0].height) == (1920, 1080)
    assert (provider.requests[1].width, provider.requests[1].height) == (1080, 1920)


def test_two_runs_of_the_same_prompt_are_not_the_same_picture(tmp_path: Path) -> None:
    """같은 씨앗을 쓰면 '다시 만들기'가 아무것도 안 하는 버튼이 된다."""
    provider = _StubProvider()
    service, _store, project_id = _service(tmp_path, provider)

    service.generate_scene_image(project_id=project_id, prompt="x", segment_id="script-1")
    service.generate_scene_image(project_id=project_id, prompt="x", segment_id="script-1")

    assert provider.requests[0].seed != provider.requests[1].seed


def test_a_blocked_comfyui_leaves_no_half_registered_asset_behind(tmp_path: Path) -> None:
    service, store, project_id = _service(tmp_path, _RefusingProvider())

    with pytest.raises(SceneImageGenerationError) as exc:
        service.generate_scene_image(project_id=project_id, prompt="x", segment_id="script-1")

    assert exc.value.code == "blocked"
    assert store.list_assets(project_id=project_id) == []


def test_an_empty_prompt_is_refused_before_the_gpu_is_woken_up(tmp_path: Path) -> None:
    provider = _StubProvider()
    service, _store, project_id = _service(tmp_path, provider)

    with pytest.raises(SceneImageGenerationError) as exc:
        service.generate_scene_image(project_id=project_id, prompt="   ", segment_id="script-1")

    assert exc.value.code == "invalid"
    assert provider.requests == []


class _KoreanBlindProvider(_StubProvider):
    """그림 모델은 한국어를 **거절하지 않는다.** 아무 그림이나 그럴듯하게 내놓는다."""


def test_a_korean_line_never_reaches_the_image_model_unchanged(tmp_path: Path) -> None:
    """2026-08-21 실측. 같은 씨앗(606386459)·같은 설정으로 두 번 만들었다.

    `자막은 따로, 음악도 따로 붙입니다` -> **픽셀아트 당나귀 두 마리**
    같은 뜻의 영어 묘사 -> 실제로 그 장면
    (`artifacts/scene-image-check/korean.png`, `english.png`)

    배관만 보면 다 되는 것처럼 보이는 자리다 -- 자산도 만들어지고 장면도 채워진다.
    owner만 24초 뒤에 당나귀를 본다.
    """
    class _Writer:
        def write(self, *, project_id: str, line: str, vertical: bool) -> str:
            return "a desk with two screens, one showing subtitles and one showing a waveform, cinematic, 16:9"

    provider = _KoreanBlindProvider()
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="한국어 대본")
    service = SceneImageService(store=store, provider=provider, prompt_writer=_Writer())

    result = service.generate_scene_image(
        project_id=project.project_id, prompt="자막은 따로, 음악도 따로 붙입니다", segment_id="script-2",
    )

    assert "당나귀" not in provider.requests[0].prompt
    assert provider.requests[0].prompt.startswith("a desk with two screens")
    # owner가 쓴 줄과 실제로 들어간 말을 **둘 다** 남긴다. 엉뚱한 그림이 나왔을 때
    # 어느 쪽 문제인지 알 수 있어야 한다.
    assert result["prompt"] == "자막은 따로, 음악도 따로 붙입니다"
    assert result["image_prompt"].startswith("a desk with two screens")


def test_english_the_owner_typed_is_sent_exactly_as_written(tmp_path: Path) -> None:
    """사람이 쓴 것이 모델이 다시 쓴 것보다 낫다. 무엇보다 적은 그대로 나오기를 기대한다."""
    class _Writer:
        def write(self, **_kwargs: object) -> str:
            raise AssertionError("영어는 다시 쓰지 않는다")

    provider = _StubProvider()
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="영어 프롬프트")
    service = SceneImageService(store=store, provider=provider, prompt_writer=_Writer())

    service.generate_scene_image(
        project_id=project.project_id, prompt="a quiet desk at dawn, cinematic", segment_id="script-1",
    )

    assert provider.requests[0].prompt == "a quiet desk at dawn, cinematic"


def test_when_yujin_cannot_answer_it_refuses_instead_of_making_a_donkey(tmp_path: Path) -> None:
    """조용히 틀린 그림을 만드는 것은 실패하는 것보다 나쁘다.

    24초를 기다린 뒤 엉뚱한 그림을 받으면 owner는 무엇이 잘못됐는지 알 수 없다.
    """
    from videobox_core_engine.scene_image_prompt import SceneImagePromptUnavailable

    class _Silent:
        def write(self, **_kwargs: object) -> str:
            raise SceneImagePromptUnavailable("scene_image_prompt_writer_unavailable")

    provider = _StubProvider()
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="유진 없음")
    service = SceneImageService(store=store, provider=provider, prompt_writer=_Silent())

    with pytest.raises(SceneImageGenerationError) as exc:
        service.generate_scene_image(project_id=project.project_id, prompt="해 뜨는 바다", segment_id="script-1")

    assert exc.value.code == "blocked"
    assert provider.requests == []
    assert store.list_assets(project_id=project.project_id) == []


def test_without_any_writer_a_korean_line_is_refused_before_the_gpu_wakes_up(tmp_path: Path) -> None:
    service, store, project_id = _service(tmp_path, writer=None)

    with pytest.raises(SceneImageGenerationError) as exc:
        service.generate_scene_image(project_id=project_id, prompt="해 뜨는 바다", segment_id="script-1")

    assert exc.value.code == "invalid"
    assert str(exc.value) == "scene_image_prompt_needs_english"
