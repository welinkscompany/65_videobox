"""타임라인 클립 위에 소리 파형을 그리려면 그림이 있어야 한다.

캡컷은 소리 클립 위에 파형을 그린다. 눈으로 어디가 크고 어디가 조용한지 찾아서
자를 자리를 고르는 것이 그것이다. 우리 타임라인은 글자 이름뿐이라 화면만 보고는
알 수 없었다.

**엔진을 새로 만들지 않는다.** 라이브러리 자산이 이미 ffmpeg `showwavespic`으로
같은 그림을 만들고 있다(`routers/library_assets.py`). 여기서는 프로젝트 자산도
같은 방식으로 얻게만 한다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api import main as api_main
from videobox_domain_models.assets import AssetType


def _write_audio(path: Path, *, seconds: int = 1) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         f"sine=frequency=440:duration={seconds}", str(path)],
        check=True, capture_output=True,
    )
    return path


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    return TestClient(api_main.create_app(projects_root=tmp_path / "projects"))


def _register_audio(client: TestClient, tmp_path: Path) -> tuple[str, str]:
    project_id = client.app.state.store.bootstrap_project(name="파형").project_id
    source = _write_audio(tmp_path / "tone.wav")
    asset = client.app.state.store.register_asset(
        project_id=project_id, asset_type=AssetType.BGM, source_path=source, metadata={"title": "톤"},
    )
    return project_id, asset.asset_id


def test_a_sound_asset_can_be_seen_as_a_shape(client: TestClient, tmp_path: Path) -> None:
    project_id, asset_id = _register_audio(client, tmp_path)

    response = client.get(f"/api/projects/{project_id}/assets/{asset_id}/waveform")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("image/")
    assert len(response.content) > 0


def test_the_shape_is_drawn_once_and_reused(client: TestClient, tmp_path: Path) -> None:
    """매 클립·매 스크롤마다 ffmpeg를 부르면 타임라인이 멈춘다. 한 번 만들고 쓴다."""
    project_id, asset_id = _register_audio(client, tmp_path)

    first = client.get(f"/api/projects/{project_id}/assets/{asset_id}/waveform")
    cached = client.app.state.store.waveform_storage_path(project_id=project_id, asset_id=asset_id)
    stamped = cached.stat().st_mtime_ns

    second = client.get(f"/api/projects/{project_id}/assets/{asset_id}/waveform")

    assert first.status_code == 200 and second.status_code == 200
    assert cached.stat().st_mtime_ns == stamped, "같은 자산의 파형을 다시 그렸다"


def test_an_unknown_asset_does_not_pretend_to_have_a_shape(client: TestClient, tmp_path: Path) -> None:
    project_id = client.app.state.store.bootstrap_project(name="없음").project_id

    response = client.get(f"/api/projects/{project_id}/assets/does-not-exist/waveform")

    assert response.status_code == 404
