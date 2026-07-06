from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app


def test_auto_cut_detect_endpoint_runs_real_ffmpeg_and_returns_plan_shape(tmp_path: Path) -> None:
    raw_video = tmp_path / "raw-footage.mp4"
    raw_video.write_bytes(b"not a real video, just bytes")

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "AutoCut Detect Draft"}).json()["project_id"]

    raw_asset_response = client.post(
        f"/api/projects/{project_id}/assets/raw-video",
        json={"source_path": str(raw_video)},
    )
    assert raw_asset_response.status_code == 201
    raw_asset_id = raw_asset_response.json()["asset_id"]

    detect_response = client.post(
        f"/api/projects/{project_id}/jobs/auto-cut-detect",
        json={"raw_video_asset_id": raw_asset_id},
    )

    assert detect_response.status_code == 200
    body = detect_response.json()
    assert body["asset_id"] == raw_asset_id
    assert body["scene_detection_filter"] == "select='gt(scene,0.4)',showinfo"
    assert isinstance(body["planned_segments"], list)
    assert isinstance(body["kept_segments"], list)
