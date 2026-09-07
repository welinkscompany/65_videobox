"""화면이 부를 수 있는 문인가 -- `SceneImageService`와 별개인 진짜 동영상 경로.
owner 결정 2026-08-29(2회차, "원래 만든거외에 별도로 만들자").

**비동기다.** 실측(2026-08-29, RTX 5090)으로 1920x1080·81프레임이 5분을
넘긴다 -- nginx 330초보다 오래 걸릴 수 있어 `test_api_reference_style_import.py`가
쓴 것과 같은 패턴(202로 바로 응답, `job_id`로 상태 확인)을 그대로 쓴다.
`TestClient`는 `BackgroundTasks`를 응답 준비 과정에서 같이 끝내므로 이어서
바로 확인해도 이미 끝나 있다.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_provider_interfaces.visual_generation import GeneratedSceneVideo, SceneVideoRequest


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe are required to transcode a generated clip",
)


def _webm_bytes(tmp_path: Path) -> bytes:
    target = tmp_path / "seed.webm"
    if not target.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=teal:s=64x64:d=1:r=10",
             "-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", str(target)],
            check=True, capture_output=True, timeout=60,
        )
    return target.read_bytes()


class _StubProvider:
    provider_name = "comfyui"

    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.prompts: list[str] = []
        self.requests: list[SceneVideoRequest] = []

    def generate_video(self, request: SceneVideoRequest, *, on_submitted=None, cancel_event=None) -> GeneratedSceneVideo:
        self.prompts.append(request.prompt)
        self.requests.append(request)
        return GeneratedSceneVideo(
            provider_name=self.provider_name, video_bytes=_webm_bytes(self.tmp_path),
            file_name="videobox-scene-video_00001_.webm",
            metadata={"model_name": "wan2.1_t2v_1.3B_fp16.safetensors", "seed": request.seed, "elapsed_sec": 96.4},
        )


class _BlockedProvider:
    provider_name = "comfyui"

    def generate_video(self, request: SceneVideoRequest, *, on_submitted=None, cancel_event=None) -> GeneratedSceneVideo:
        from videobox_provider_interfaces.comfyui_image_generation import ComfyUIProviderError

        raise ComfyUIProviderError("ComfyUI local resource is unavailable.", "blocked")


class _Writer:
    def write(self, *, project_id: str, line: str, vertical: bool) -> str:
        return f"a short clip of: {line[:40]}, cinematic"


def _client(tmp_path: Path, provider: object | None = None) -> tuple[TestClient, str]:
    client = TestClient(create_app(
        projects_root=tmp_path / "data", scene_video_provider=provider,
        scene_image_prompt_writer=_Writer(),
    ))
    project_id = client.post("/api/projects", json={"name": "영상"}).json()["project_id"]
    return client, project_id


def test_it_makes_a_video_for_one_scene_and_says_what_it_made(tmp_path: Path) -> None:
    provider = _StubProvider(tmp_path)
    client, project_id = _client(tmp_path, provider)

    started = client.post(
        f"/api/projects/{project_id}/scene-videos",
        json={"prompt": "해 뜨는 바다", "segment_id": "script-3"},
    )
    assert started.status_code == 202, started.text
    job_id = started.json()["job_id"]
    assert started.json()["status"] == "processing"

    status_response = client.get(f"/api/projects/{project_id}/scene-videos/{job_id}")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["status"] == "succeeded", body
    result = body["result"]
    assert result["segment_id"] == "script-3"
    assert result["title"] == "3번째 장면 영상"
    assert result["scene_asset_id"]
    assert result["gif_asset_id"] is None
    # owner 요청(2026-08-29 3회차): "이렇게 생성된것도 우리 자산으로 들어가도록".
    # `create_app`이 항상 진짜 `library_ingest_service`를 만들어 준다 --
    # 이 경로도 실제 앱 배선을 그대로 거친다.
    assert result["library_asset_id"] is not None
    assert result["prompt"] == "해 뜨는 바다"
    assert result["video_prompt"].startswith("a short clip of")
    assert provider.prompts == [result["video_prompt"]]

    listed = client.get(f"/api/projects/{project_id}/scene-videos")
    assert listed.status_code == 200
    assert [item["segment_id"] for item in listed.json()["videos"]] == ["script-3"]


def test_asking_for_a_preview_passes_the_quality_through(tmp_path: Path) -> None:
    """빠른 미리보기(owner 요청 2026-08-29, 3회차) -- API 요청의 `quality`가
    서비스까지 그대로 전달되는지 확인한다."""
    provider = _StubProvider(tmp_path)
    client, project_id = _client(tmp_path, provider)

    started = client.post(
        f"/api/projects/{project_id}/scene-videos",
        json={"prompt": "해 뜨는 바다", "segment_id": "script-1", "quality": "preview"},
    )
    job_id = started.json()["job_id"]

    body = client.get(f"/api/projects/{project_id}/scene-videos/{job_id}").json()
    assert body["status"] == "succeeded", body
    assert body["result"]["quality"] == "preview"
    assert (provider.requests[0].width, provider.requests[0].height) == (512, 288)
    assert (provider.requests[0].length_frames, provider.requests[0].steps) == (17, 8)


def test_the_list_view_still_shows_the_library_id_after_a_refresh(tmp_path: Path) -> None:
    """알려진 격차(2026-08-29 3회차 turn) -- 목록 조회가 항상 `library_asset_id`를
    `None`으로 돌려줬다. 만드는 순간의 응답에만 있으면 화면을 새로고침한 뒤에는
    "자료실에도 저장했어요"가 사라져 보인다."""
    client, project_id = _client(tmp_path, _StubProvider(tmp_path))

    started = client.post(
        f"/api/projects/{project_id}/scene-videos",
        json={"prompt": "해 뜨는 바다", "segment_id": "script-1", "make_gif": True},
    )
    job_id = started.json()["job_id"]
    created = client.get(f"/api/projects/{project_id}/scene-videos/{job_id}").json()["result"]

    listed = client.get(f"/api/projects/{project_id}/scene-videos").json()["videos"]
    assert len(listed) == 1
    assert listed[0]["library_asset_id"] == created["library_asset_id"]
    assert listed[0]["gif_asset_id"] == created["gif_asset_id"]
    assert listed[0]["gif_library_asset_id"] == created["gif_library_asset_id"]


def test_asking_for_standard_quality_passes_the_middle_tier_through(tmp_path: Path) -> None:
    """중간 화질(owner 요청 2026-08-30) -- 실측(RTX 5090): 1280x720·65프레임·
    16스텝이 약 2분 19초. API 요청의 `quality=standard`가 서비스까지 그대로
    전달되는지 확인한다."""
    provider = _StubProvider(tmp_path)
    client, project_id = _client(tmp_path, provider)

    started = client.post(
        f"/api/projects/{project_id}/scene-videos",
        json={"prompt": "해 뜨는 바다", "segment_id": "script-1", "quality": "standard"},
    )
    job_id = started.json()["job_id"]

    body = client.get(f"/api/projects/{project_id}/scene-videos/{job_id}").json()
    assert body["status"] == "succeeded", body
    assert body["result"]["quality"] == "standard"
    assert (provider.requests[0].width, provider.requests[0].height) == (1280, 720)
    assert (provider.requests[0].length_frames, provider.requests[0].steps) == (65, 16)


def test_asking_for_a_gif_reports_the_gif_asset_id_too(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path, _StubProvider(tmp_path))

    started = client.post(
        f"/api/projects/{project_id}/scene-videos",
        json={"prompt": "해 뜨는 바다", "segment_id": "script-1", "make_gif": True},
    )
    job_id = started.json()["job_id"]

    body = client.get(f"/api/projects/{project_id}/scene-videos/{job_id}").json()
    assert body["status"] == "succeeded", body
    assert body["result"]["gif_asset_id"] is not None


def test_the_video_can_be_fetched_back_so_the_screen_can_show_it(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path, _StubProvider(tmp_path))

    started = client.post(
        f"/api/projects/{project_id}/scene-videos",
        json={"prompt": "해 뜨는 바다", "segment_id": "script-1"},
    )
    job_id = started.json()["job_id"]
    result = client.get(f"/api/projects/{project_id}/scene-videos/{job_id}").json()["result"]

    content = client.get(f"/api/projects/{project_id}/assets/{result['scene_asset_id']}/content")
    assert content.status_code == 200


def test_a_missing_comfyui_says_so_instead_of_pretending_it_worked(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path, _BlockedProvider())

    started = client.post(
        f"/api/projects/{project_id}/scene-videos",
        json={"prompt": "해 뜨는 바다", "segment_id": "script-1"},
    )
    job_id = started.json()["job_id"]

    body = client.get(f"/api/projects/{project_id}/scene-videos/{job_id}").json()
    assert body["status"] == "failed"
    assert body["error_detail"] == "scene_video_generation_blocked"


def test_without_the_feature_turned_on_the_door_says_it_is_off_not_broken(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path, None)

    response = client.post(
        f"/api/projects/{project_id}/scene-videos",
        json={"prompt": "해 뜨는 바다", "segment_id": "script-1"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "scene_video_generation_unavailable"


def test_an_unknown_job_id_is_a_404_not_an_empty_success(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path, _StubProvider(tmp_path))

    response = client.get(f"/api/projects/{project_id}/scene-videos/does-not-exist")

    assert response.status_code == 404


def test_cancelling_an_unknown_job_is_also_a_404(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path, _StubProvider(tmp_path))

    response = client.post(f"/api/projects/{project_id}/scene-videos/does-not-exist/cancel")

    assert response.status_code == 404


def test_a_stranded_running_job_recovers_to_a_clear_failure_after_a_restart(tmp_path: Path) -> None:
    """job 상태 영속화(2026-08-30) -- 다른 job 종류가 이미 쓰던
    `recover_orphaned_in_process_jobs`(재시작 시 멈춰 있던 job을 실패로
    정리하는 기존 장치)가 `JobType.SCENE_VIDEO_GENERATION`도 그대로 덮는지
    확인한다. 이 job 자체는 그 장치를 전혀 몰라도 자동으로 덮인다 -- 새
    스키마 없이 `JobType`에 한 줄만 더해 기존 재사용 게이트를 탄 결과다."""
    from videobox_domain_models.jobs import JobStatus, JobType

    client, project_id = _client(tmp_path, _StubProvider(tmp_path))
    store = client.app.state.store
    stranded = store.create_job(
        project_id=project_id, job_type=JobType.SCENE_VIDEO_GENERATION,
        input_ref="script-9", status=JobStatus.RUNNING,
    )
    job_id = str(stranded["job_id"])

    store.recover_orphaned_in_process_jobs(project_id=project_id)

    body = client.get(f"/api/projects/{project_id}/scene-videos/{job_id}").json()
    assert body["status"] == "failed"
    assert body["error_detail"] == "WORKER_RESTARTED"


def test_a_finished_job_still_answers_after_this_process_forgets_it(tmp_path: Path) -> None:
    """job 상태 영속화(2026-08-30) -- 이 프로세스의 메모리(`_jobs`)가
    재시작으로 사라져도, DB의 job 행 + scene 자산 메타데이터만으로 같은
    결과를 다시 돌려줄 수 있어야 한다. 결과 자체는 두 번 저장하지 않는다 --
    `output_ref`가 가리키는 자산에서 되짚는다."""
    from videobox_api.routers import scene_videos as scene_videos_module

    client, project_id = _client(tmp_path, _StubProvider(tmp_path))
    started = client.post(
        f"/api/projects/{project_id}/scene-videos",
        json={"prompt": "해 뜨는 바다", "segment_id": "script-1"},
    )
    job_id = started.json()["job_id"]
    before = client.get(f"/api/projects/{project_id}/scene-videos/{job_id}").json()
    assert before["status"] == "succeeded", before

    # 실제 재시작을 흉내낸다 -- 이 프로세스가 이 job을 다루며 만든 메모리
    # 기록을 지운다.
    scene_videos_module._jobs.pop(job_id, None)

    after = client.get(f"/api/projects/{project_id}/scene-videos/{job_id}").json()
    assert after["status"] == "succeeded"
    assert after["result"] == before["result"]


def test_cancelling_a_job_this_process_no_longer_remembers_is_refused_not_lost(tmp_path: Path) -> None:
    """job 상태 영속화(2026-08-30) -- 메모리를 잃은 job은 취소할 실제 스레드가
    없다. 404(없음)로 답하면 "있던 job이 사라졌다"는 착각을 준다 -- 409(취소
    불가)가 맞다. 진짜 없는 job(테스트 파일 위쪽의 `does-not-exist`)은 여전히
    404다."""
    from videobox_api.routers import scene_videos as scene_videos_module

    client, project_id = _client(tmp_path, _StubProvider(tmp_path))
    started = client.post(
        f"/api/projects/{project_id}/scene-videos",
        json={"prompt": "해 뜨는 바다", "segment_id": "script-1"},
    )
    job_id = started.json()["job_id"]
    scene_videos_module._jobs.pop(job_id, None)

    response = client.post(f"/api/projects/{project_id}/scene-videos/{job_id}/cancel")

    assert response.status_code == 409
    assert response.json()["detail"] == "scene_video_job_not_cancellable"


def test_cancelling_a_job_that_already_finished_is_refused(tmp_path: Path) -> None:
    """취소 버튼(owner 요청 2026-08-29 3회차) -- 이미 끝난 작업을 다시
    취소하면 안 된다. `TestClient`는 백그라운드 작업을 응답 준비 과정에서
    같이 끝내므로, 이 시점에는 이미 `succeeded`다."""
    client, project_id = _client(tmp_path, _StubProvider(tmp_path))
    started = client.post(
        f"/api/projects/{project_id}/scene-videos",
        json={"prompt": "해 뜨는 바다", "segment_id": "script-1"},
    )
    job_id = started.json()["job_id"]

    response = client.post(f"/api/projects/{project_id}/scene-videos/{job_id}/cancel")

    assert response.status_code == 409
    assert response.json()["detail"] == "scene_video_job_not_cancellable"
