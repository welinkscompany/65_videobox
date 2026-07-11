from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import videobox_api.main as api_main
from videobox_api.main import create_app


def test_default_create_app_uses_no_live_llm_transport(tmp_path: Path, monkeypatch) -> None:
    def forbidden_urlopen(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Test create_app must not call a live LLM transport.")

    monkeypatch.setattr(api_main, "urlopen", forbidden_urlopen)
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "Deterministic API Test"}).json()[
        "project_id"
    ]
    narration_path = tmp_path / "narration.wav"
    narration_path.write_bytes(b"deterministic test narration")
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(narration_path)},
    ).json()["asset_id"]
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={"transcription_job_id": transcription_job_id, "script_asset_id": None},
    )

    assert response.status_code == 202
