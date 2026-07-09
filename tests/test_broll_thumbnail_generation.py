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
