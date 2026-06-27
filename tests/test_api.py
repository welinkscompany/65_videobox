from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_provider_interfaces.stt import STTResult, STTSegment


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


def test_recommendation_flow_persists_broll_and_music_results(tmp_path: Path) -> None:
    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    broll_city = tmp_path / "city-office.mp4"
    broll_team = tmp_path / "team-meeting.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n\nTeam meeting restart.\n", encoding="utf-8")
    broll_city.write_bytes(b"video bytes 1")
    broll_team.write_bytes(b"video bytes 2")

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Recommendation Draft"}).json()["project_id"]

    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    city_asset = client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_city),
            "title": "Office skyline",
            "tags": ["office", "city", "overview"],
        },
    )
    team_asset = client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_team),
            "title": "Team meeting",
            "tags": ["team", "meeting", "collaboration"],
        },
    )
    assert city_asset.status_code == 201
    assert team_asset.status_code == 201

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]

    broll_job = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )
    music_job = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )
    assert broll_job.status_code == 202
    assert music_job.status_code == 202

    broll_result = client.get(
        f"/api/projects/{project_id}/jobs/broll-recommendation/{broll_job.json()['job_id']}"
    )
    music_result = client.get(
        f"/api/projects/{project_id}/jobs/music-recommendation/{music_job.json()['job_id']}"
    )
    assert broll_result.status_code == 200
    assert music_result.status_code == 200

    broll_payload = broll_result.json()
    music_payload = music_result.json()
    assert broll_payload["status"] == "succeeded"
    assert music_payload["status"] == "succeeded"
    assert len(broll_payload["recommendations"]) >= 2
    assert len(music_payload["recommendations"]) >= 2
    assert all("score" in item for item in broll_payload["recommendations"])
    assert all("reason" in item for item in broll_payload["recommendations"])
    assert all(item["auto_apply_allowed"] is True for item in broll_payload["recommendations"])
    assert all(item["review_required"] is False for item in broll_payload["recommendations"])

    project_root = tmp_path / "projects" / project_id
    recommendation_files = list((project_root / "analysis" / "recommendations").glob("*.json"))
    assert len(recommendation_files) >= 2
    payloads = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in recommendation_files
    ]
    recommendation_types = {payload["recommendation_type"] for payload in payloads}
    assert {"broll", "bgm"}.issubset(recommendation_types)


def test_timeline_and_review_snapshot_flow(tmp_path: Path) -> None:
    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    broll_city = tmp_path / "city-office.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n\nTeam meeting restart.\n", encoding="utf-8")
    broll_city.write_bytes(b"video bytes 1")

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Timeline Draft"}).json()["project_id"]

    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_city),
            "title": "Office skyline",
            "tags": ["office", "city", "overview"],
        },
    )

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]

    timeline_response = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    )
    assert timeline_response.status_code == 202
    timeline_job_id = timeline_response.json()["job_id"]

    timeline_result = client.get(
        f"/api/projects/{project_id}/timelines/{timeline_job_id}"
    )
    review_snapshot = client.get(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}"
    )
    assert timeline_result.status_code == 200
    assert review_snapshot.status_code == 200

    timeline_payload = timeline_result.json()
    review_payload = review_snapshot.json()
    assert timeline_payload["status"] == "succeeded"
    assert timeline_payload["job_id"].startswith("timeline_build_job_")
    assert timeline_payload["timeline"]["project_id"] == project_id
    assert len(timeline_payload["timeline"]["tracks"]) >= 1
    assert {"narration", "broll", "bgm"}.issubset(
        {track["track_type"] for track in timeline_payload["timeline"]["tracks"]}
    )
    assert len(review_payload["segments"]) >= 2
    assert len(review_payload["applied_recommendations"]) >= 2
    assert len(review_payload["pending_recommendations"]) == 0
    assert any(flag["code"] == "segment_review_required" for flag in review_payload["review_flags"])
    assert review_payload["timeline_id"] == timeline_payload["timeline"]["timeline_id"]

    project_root = tmp_path / "projects" / project_id
    timeline_files = list((project_root / "timelines").glob("timeline_*.json"))
    assert timeline_files
    timeline_json = json.loads(timeline_files[0].read_text(encoding="utf-8"))
    assert timeline_json["project_id"] == project_id
    assert {"narration", "broll", "bgm"}.issubset(
        {track["track_type"] for track in timeline_json["tracks"]}
    )


def test_project_listing_and_job_feed_support_dashboard(tmp_path: Path) -> None:
    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    broll_city = tmp_path / "city-office.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n\nTeam meeting restart.\n", encoding="utf-8")
    broll_city.write_bytes(b"video bytes 1")

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Dashboard Draft"}).json()["project_id"]

    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_city),
            "title": "Office skyline",
            "tags": ["office", "city", "overview"],
        },
    )

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    ).json()["job_id"]

    projects_response = client.get("/api/projects")
    project_response = client.get(f"/api/projects/{project_id}")
    jobs_response = client.get(f"/api/projects/{project_id}/jobs")

    assert projects_response.status_code == 200
    assert project_response.status_code == 200
    assert jobs_response.status_code == 200

    projects_payload = projects_response.json()
    project_payload = project_response.json()
    jobs_payload = jobs_response.json()

    assert any(project["project_id"] == project_id for project in projects_payload["projects"])
    assert project_payload["project_id"] == project_id
    assert project_payload["name"] == "Dashboard Draft"
    assert any(job["job_id"] == timeline_job_id for job in jobs_payload["jobs"])
    assert any(job["job_type"] == "timeline_build" for job in jobs_payload["jobs"])


def test_preview_and_capcut_export_flow_persist_outputs_and_statuses(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def clean_transcribe(self, request):  # noqa: ANN001
        return STTResult(
            text="Office overview. Team meeting overview.",
            segments=[
                STTSegment(start_sec=0.0, end_sec=1.0, text="Office overview.", confidence=0.99),
                STTSegment(
                    start_sec=1.0,
                    end_sec=2.2,
                    text="Team meeting overview.",
                    confidence=0.98,
                ),
            ],
            provider_name="mock_stt",
        )

    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        clean_transcribe,
    )

    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    broll_city = tmp_path / "city-office.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n\nTeam meeting overview.\n", encoding="utf-8")
    broll_city.write_bytes(b"video bytes 1")

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Output Draft"}).json()["project_id"]

    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_city),
            "title": "Office skyline",
            "tags": ["office", "city", "overview"],
        },
    )

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    ).json()["job_id"]

    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )

    assert preview_response.status_code == 202
    assert export_response.status_code == 202

    preview_job_id = preview_response.json()["job_id"]
    export_job_id = export_response.json()["job_id"]

    preview_result = client.get(f"/api/projects/{project_id}/previews/{preview_job_id}")
    export_result = client.get(f"/api/projects/{project_id}/exports/{export_job_id}")

    assert preview_result.status_code == 200
    assert export_result.status_code == 200

    preview_payload = preview_result.json()
    export_payload = export_result.json()
    assert preview_payload["status"] == "succeeded"
    assert preview_payload["preview"]["timeline_id"] == "timeline_001"
    assert preview_payload["preview"]["artifact_kind"] == "mock_preview_bundle"
    assert export_payload["status"] == "succeeded"
    assert export_payload["export"]["timeline_id"] == "timeline_001"
    assert export_payload["export"]["export_type"] == "capcut"
    assert export_payload["export"]["notes"][0].lower().startswith("mock capcut")

    project_root = tmp_path / "projects" / project_id
    assert (project_root / "previews" / "preview_001.json").exists()
    assert (
        project_root / "exports" / "capcut" / "export_001" / "capcut_payload.json"
    ).exists()


def test_preview_and_capcut_export_require_review_clearance(tmp_path: Path) -> None:
    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    broll_city = tmp_path / "city-office.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n\nTeam meeting restart.\n", encoding="utf-8")
    broll_city.write_bytes(b"video bytes 1")

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Review Gate Draft"}).json()["project_id"]

    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_city),
            "title": "Office skyline",
            "tags": ["office", "city", "overview"],
        },
    )

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    ).json()["job_id"]

    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )

    assert preview_response.status_code == 400
    assert export_response.status_code == 400
    assert "review" in preview_response.json()["detail"].lower()
    assert "review" in export_response.json()["detail"].lower()

    jobs_response = client.get(f"/api/projects/{project_id}/jobs")
    jobs_payload = jobs_response.json()["jobs"]
    preview_job = next(job for job in jobs_payload if job["job_type"] == "preview_render")
    export_job = next(job for job in jobs_payload if job["job_type"] == "capcut_export")
    assert preview_job["status"] == "failed"
    assert export_job["status"] == "failed"

    project_root = tmp_path / "projects" / project_id
    assert not list((project_root / "previews").glob("preview_*.json"))
    assert not list((project_root / "exports" / "capcut").glob("export_*"))
