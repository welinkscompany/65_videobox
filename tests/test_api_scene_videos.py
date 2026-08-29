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

    def generate_video(self, request: SceneVideoRequest) -> GeneratedSceneVideo:
        self.prompts.append(request.prompt)
        return GeneratedSceneVideo(
            provider_name=self.provider_name, video_bytes=_webm_bytes(self.tmp_path),
            file_name="videobox-scene-video_00001_.webm",
            metadata={"model_name": "wan2.1_t2v_1.3B_fp16.safetensors", "seed": request.seed, "elapsed_sec": 96.4},
        )


class _BlockedProvider:
    provider_name = "comfyui"

    def generate_video(self, request: SceneVideoRequest) -> GeneratedSceneVideo:
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
    assert result["prompt"] == "해 뜨는 바다"
    assert result["video_prompt"].startswith("a short clip of")
    assert provider.prompts == [result["video_prompt"]]

    listed = client.get(f"/api/projects/{project_id}/scene-videos")
    assert listed.status_code == 200
    assert [item["segment_id"] for item in listed.json()["videos"]] == ["script-3"]


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
