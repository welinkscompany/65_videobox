"""화면이 부를 수 있는 문인가. §10.14 조항 2-C.

`api.ts` 메서드 147개 중 31개가 화면 어디에서도 이름조차 불리지 않았다(2026-08-09).
새 백엔드를 만들 때마다 부르는 자리를 같이 만들지 않으면 그 목록이 는다. 여기서는
문이 제대로 열리는지를 재고, 화면이 실제로 부르는지는 `SceneImageStudio.test.tsx`가
잰다.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_provider_interfaces.visual_generation import GeneratedSceneImage, SceneImageRequest


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe are required to turn a still into a scene clip",
)


def _png_bytes(tmp_path: Path) -> bytes:
    target = tmp_path / "seed.png"
    if not target.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=teal:s=320x180",
             "-frames:v", "1", str(target)],
            check=True, capture_output=True, timeout=60,
        )
    return target.read_bytes()


class _StubProvider:
    provider_name = "comfyui"

    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.prompts: list[str] = []

    def generate_image(self, request: SceneImageRequest) -> GeneratedSceneImage:
        self.prompts.append(request.prompt)
        return GeneratedSceneImage(
            provider_name=self.provider_name, image_bytes=_png_bytes(self.tmp_path),
            file_name="videobox-scene_00001_.png",
            metadata={"model_name": "flux1-dev.safetensors", "seed": request.seed,
                      "elapsed_sec": 22.3, "commercial_use_is_unrestricted": False},
        )


class _BlockedProvider:
    provider_name = "comfyui"

    def generate_image(self, request: SceneImageRequest) -> GeneratedSceneImage:
        from videobox_provider_interfaces.comfyui_image_generation import ComfyUIProviderError

        raise ComfyUIProviderError("ComfyUI local resource is unavailable.", "blocked")


def _client(tmp_path: Path, provider: object | None = None) -> tuple[TestClient, str]:
    client = TestClient(create_app(projects_root=tmp_path / "data", scene_image_provider=provider))
    project_id = client.post("/api/projects", json={"name": "그림"}).json()["project_id"]
    return client, project_id


def test_it_makes_a_picture_for_one_scene_and_says_what_it_made(tmp_path: Path) -> None:
    provider = _StubProvider(tmp_path)
    client, project_id = _client(tmp_path, provider)

    response = client.post(
        f"/api/projects/{project_id}/scene-images",
        json={"prompt": "해 뜨는 바다", "segment_id": "script-3", "duration_sec": 4.0},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["segment_id"] == "script-3"
    assert body["title"] == "3번째 장면 그림"
    assert body["image_asset_id"] and body["scene_asset_id"]
    assert provider.prompts == ["해 뜨는 바다"]

    listed = client.get(f"/api/projects/{project_id}/scene-images")
    assert listed.status_code == 200
    assert [item["segment_id"] for item in listed.json()["images"]] == ["script-3"]
    assert listed.json()["images"][0]["image_asset_id"] == body["image_asset_id"]


def test_the_picture_can_be_fetched_back_so_the_screen_can_show_it(tmp_path: Path) -> None:
    """만들어 놓고 볼 수 없으면 owner는 마음에 드는지 판단할 수 없다."""
    client, project_id = _client(tmp_path, _StubProvider(tmp_path))

    created = client.post(
        f"/api/projects/{project_id}/scene-images",
        json={"prompt": "해 뜨는 바다", "segment_id": "script-1"},
    ).json()

    content = client.get(
        f"/api/projects/{project_id}/assets/{created['image_asset_id']}/content"
    )
    assert content.status_code == 200
    assert content.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_missing_comfyui_says_so_instead_of_pretending_it_worked(tmp_path: Path) -> None:
    """꺼진 기능을 고장이라고 말하지 않는다 -- 2026-08-20에 503 둘을 구분 못 해
    "저장하지 못했어요"가 떴다. 화면이 어느 쪽인지 알 수 있어야 한다."""
    client, project_id = _client(tmp_path, _BlockedProvider())

    response = client.post(
        f"/api/projects/{project_id}/scene-images",
        json={"prompt": "해 뜨는 바다", "segment_id": "script-1"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "scene_image_generation_blocked"


def test_without_the_feature_turned_on_the_door_says_it_is_off_not_broken(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path, None)

    response = client.post(
        f"/api/projects/{project_id}/scene-images",
        json={"prompt": "해 뜨는 바다", "segment_id": "script-1"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "scene_image_generation_unavailable"


def test_an_empty_prompt_is_refused_with_a_reason_the_screen_can_translate(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path, _StubProvider(tmp_path))

    response = client.post(
        f"/api/projects/{project_id}/scene-images",
        json={"prompt": "   ", "segment_id": "script-1"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "scene_image_prompt_empty"
