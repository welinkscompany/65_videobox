from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app


def test_health_endpoint_reports_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_project_creation_endpoint_returns_local_storage_metadata(tmp_path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post("/api/projects", json={"name": "Narration Draft"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "Narration Draft"
    assert payload["root_storage_uri"].startswith("local://projects/")


def test_ingest_and_analysis_flow_persists_files_and_records(tmp_path: Path) -> None:
    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Line one.\n\nLine two with restart.\n", encoding="utf-8")

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_response = client.post("/api/projects", json={"name": "Narration Draft"})
    project_id = project_response.json()["project_id"]

    narration_response = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    )
    script_response = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    )

    assert narration_response.status_code == 201
    assert script_response.status_code == 201
    narration_asset_id = narration_response.json()["asset_id"]
    script_asset_id = script_response.json()["asset_id"]

    transcription_response = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    )
    assert transcription_response.status_code == 202
    transcription_job_id = transcription_response.json()["job_id"]

    transcription_result_response = client.get(
        f"/api/projects/{project_id}/jobs/transcription/{transcription_job_id}"
    )
    assert transcription_result_response.status_code == 200
    transcription_payload = transcription_result_response.json()
    assert transcription_payload["status"] == "succeeded"
    assert transcription_payload["transcript_uri"].startswith(
        f"local://projects/{project_id}/analysis/transcripts/"
    )

    segment_response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )
    assert segment_response.status_code == 202
    segment_job_id = segment_response.json()["job_id"]

    segment_result_response = client.get(
        f"/api/projects/{project_id}/jobs/segment-analysis/{segment_job_id}"
    )
    assert segment_result_response.status_code == 200
    segment_payload = segment_result_response.json()
    assert segment_payload["status"] == "succeeded"
    assert len(segment_payload["segments"]) >= 2
    assert any(segment["review_required"] for segment in segment_payload["segments"])

    project_root = tmp_path / "projects" / project_id
    assert (project_root / "inputs" / "narration" / source_audio.name).read_bytes() == b"fake wav data"
    assert (
        project_root / "inputs" / "scripts" / source_script.name
    ).read_text(encoding="utf-8") == "Line one.\n\nLine two with restart.\n"

    transcript_files = list((project_root / "analysis" / "transcripts").glob("*.json"))
    assert transcript_files
    transcript_payload = json.loads(transcript_files[0].read_text(encoding="utf-8"))
    assert transcript_payload["source_asset_id"] == narration_asset_id

    segment_files = list((project_root / "analysis" / "segments").glob("*.json"))
    assert segment_files
    persisted_segments = json.loads(segment_files[0].read_text(encoding="utf-8"))
    assert persisted_segments["script_asset_id"] == script_asset_id
