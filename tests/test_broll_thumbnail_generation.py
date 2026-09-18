from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not installed on this machine")
def test_registering_a_real_broll_video_generates_a_servable_thumbnail(tmp_path: Path) -> None:
    video_path = tmp_path / "broll.mp4"
    generate = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=1:size=64x64:rate=5",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert generate.returncode == 0, generate.stderr

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Thumbnail Project"}).json()["project_id"]

    asset_response = client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={"source_path": str(video_path), "title": "Test Clip"},
    )
    assert asset_response.status_code == 201
    asset_id = asset_response.json()["asset_id"]

    thumbnail_response = client.get(f"/api/projects/{project_id}/assets/{asset_id}/thumbnail")
    assert thumbnail_response.status_code == 200
    assert len(thumbnail_response.content) > 0

    listed = client.get(f"/api/projects/{project_id}/assets/broll-video").json()["assets"]
    registered = next(item for item in listed if item["asset_id"] == asset_id)
    assert registered["metadata"]["thumbnail_uri"].startswith(f"local://projects/{project_id}/")


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not installed on this machine")
def test_thumbnail_survives_derived_cache_cleanup_for_broll_video(tmp_path: Path) -> None:
    """INVEST-04: `derived/thumbnails/{asset_id}.jpg`는 `§10.16` 기준으로
    다시 만들 수 있는 파생물이라 정리 대상이다. 원본 등록 시점에 한 번만
    만들어지는 broll 썸네일은, 캐시 파일만 지워지면 metadata의
    `thumbnail_uri`는 남았는데 실제 파일은 없어 그냥 404가 됐다(이미지
    자산은 2026-09-17에 즉석 재생성 fallback이 생겼지만 영상은 빠졌다).
    """
    video_path = tmp_path / "broll.mp4"
    generate = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=1:size=64x64:rate=5",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert generate.returncode == 0, generate.stderr

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Thumbnail Cleanup Project"}).json()["project_id"]

    asset_response = client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={"source_path": str(video_path), "title": "Test Clip"},
    )
    assert asset_response.status_code == 201
    asset_id = asset_response.json()["asset_id"]

    first_response = client.get(f"/api/projects/{project_id}/assets/{asset_id}/thumbnail")
    assert first_response.status_code == 200

    cached_thumbnail = tmp_path / "projects" / project_id / "derived" / "thumbnails" / f"{asset_id}.jpg"
    assert cached_thumbnail.exists()
    cached_thumbnail.unlink()

    second_response = client.get(f"/api/projects/{project_id}/assets/{asset_id}/thumbnail")
    assert second_response.status_code == 200
    assert len(second_response.content) > 0
    assert cached_thumbnail.exists()


def test_registering_a_broll_asset_with_unreadable_video_data_does_not_fail_registration(
    tmp_path: Path,
) -> None:
    video_path = tmp_path / "not_a_real_video.mp4"
    video_path.write_bytes(b"not actually a video file")

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Bad Video Project"}).json()["project_id"]

    asset_response = client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={"source_path": str(video_path), "title": "Broken Clip"},
    )
    assert asset_response.status_code == 201
    asset_id = asset_response.json()["asset_id"]

    thumbnail_response = client.get(f"/api/projects/{project_id}/assets/{asset_id}/thumbnail")
    assert thumbnail_response.status_code == 404
