from __future__ import annotations

import importlib.util
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_core_engine.capcut_handoff import CapCutHandoffService
from videobox_core_engine.settings import CapCutDraftExportConfig
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_provider_interfaces.stt import STTResult, STTSegment
from videobox_storage.local_project_store import LocalProjectStore

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
PYCAPCUT_AVAILABLE = importlib.util.find_spec("pycapcut") is not None


def _generate(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def _poll_until_finished(get_result, *, timeout_seconds: float = 30.0):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        body = get_result()
        if body["status"] in {"succeeded", "failed"}:
            return body
        time.sleep(0.1)
    raise TimeoutError("Job did not finish in time.")


def _save_current_capcut_draft_export_job(store: LocalProjectStore, *, project_id: str) -> tuple[dict, dict]:
    timeline = store.save_timeline_run(
        project_id=project_id,
        output_mode="review",
        timeline_payload={"tracks": [], "review_flags": [], "pending_recommendations": []},
    )
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={"segments": [], "history": []},
    )
    store.save_review_state(
        project_id=project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
        source_session_revision=session["session_revision"],
    )
    source_draft = store.project_root(project_id) / "source_draft"
    source_draft.mkdir()
    (source_draft / "draft_content.json").write_text("{}", encoding="utf-8")
    export = store.save_capcut_draft_export(
        project_id=project_id,
        timeline_id=timeline["timeline_id"],
        source_draft_path=source_draft,
    )
    job = store.create_job(
        project_id=project_id,
        job_type=JobType.CAPCUT_DRAFT_EXPORT,
        input_ref="timeline_build_job_001",
    )
    return store.update_job(
        project_id=project_id,
        job_id=job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=export["export_id"],
    ), session


def test_capcut_draft_export_result_api_preserves_null_artifact_and_failure_reason(tmp_path: Path) -> None:
    app = create_app(
        projects_root=tmp_path,
        capcut_handoff_service=CapCutHandoffService(local_app_data=tmp_path / "NoCapCut"),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "CapCut failure API contract"}).json()["project_id"]
    store = LocalProjectStore(tmp_path)
    job = store.create_job(
        project_id=project_id,
        job_type=JobType.CAPCUT_DRAFT_EXPORT,
        input_ref="timeline_build_job_001",
    )
    store.update_job(
        project_id=project_id,
        job_id=job["job_id"],
        status=JobStatus.FAILED,
        error_message="CapCut draft package could not be written.",
    )

    response = client.get(f"/api/projects/{project_id}/capcut-draft-exports/{job['job_id']}")

    assert response.status_code == 200
    assert response.json() == {
        "job_id": job["job_id"],
        "status": "failed",
        "export": None,
        "error_message": "CapCut draft package could not be written.",
    }


def test_capcut_draft_handoff_api_refuses_a_direct_post_without_an_authoritative_current_export(tmp_path: Path) -> None:
    app = create_app(
        projects_root=tmp_path,
        capcut_handoff_service=CapCutHandoffService(local_app_data=tmp_path / "NoCapCut"),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "CapCut handoff API contract"}).json()["project_id"]
    store = LocalProjectStore(tmp_path)
    job, _ = _save_current_capcut_draft_export_job(store, project_id=project_id)
    store.update_editing_session(
        project_id=project_id,
        session_id=store.get_latest_editing_session(project_id=project_id)["session_id"],
        session_payload={"segments": [], "history": []},
        expected_revision=store.get_latest_editing_session(project_id=project_id)["session_revision"],
    )

    response = client.post(f"/api/projects/{project_id}/capcut-draft-exports/{job['job_id']}/handoff")

    assert response.status_code == 400
    assert response.json()["detail"] == "stale_output_asset: CapCut draft export freshness changed"


def test_capcut_draft_handoff_api_refuses_a_failed_export_job_even_when_it_has_an_export(tmp_path: Path) -> None:
    app = create_app(
        projects_root=tmp_path,
        capcut_handoff_service=CapCutHandoffService(local_app_data=tmp_path / "NoCapCut"),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "CapCut failed handoff API contract"}).json()["project_id"]
    store = LocalProjectStore(tmp_path)
    job, _ = _save_current_capcut_draft_export_job(store, project_id=project_id)
    store.update_job(
        project_id=project_id,
        job_id=job["job_id"],
        status=JobStatus.FAILED,
        output_ref=job["output_ref"],
        error_message="draft export failed after artifact write",
    )

    response = client.post(f"/api/projects/{project_id}/capcut-draft-exports/{job['job_id']}/handoff")

    assert response.status_code == 400
    assert response.json()["detail"] == "capcut_draft_handoff_requires_succeeded_export_job"


def test_capcut_draft_handoff_api_persists_failed_registration_with_recovery_reason(tmp_path: Path) -> None:
    app = create_app(
        projects_root=tmp_path,
        capcut_handoff_service=CapCutHandoffService(local_app_data=tmp_path / "NoCapCut"),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "CapCut unavailable handoff API contract"}).json()["project_id"]
    job, _ = _save_current_capcut_draft_export_job(LocalProjectStore(tmp_path), project_id=project_id)

    response = client.post(f"/api/projects/{project_id}/capcut-draft-exports/{job['job_id']}/handoff")

    assert response.status_code == 200
    body = response.json()
    assert body["handoff"]["status"] == "failed"
    assert "CapCut 설치를 확인" in body["handoff"]["error_message"]


def test_capcut_draft_handoff_api_reuses_a_current_successful_export(tmp_path: Path) -> None:
    local_app_data = tmp_path / "LocalAppData"
    executable = local_app_data / "CapCut" / "Apps" / "8.7.0" / "CapCut.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"capcut")
    (local_app_data / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft").mkdir(parents=True)
    app = create_app(
        projects_root=tmp_path,
        capcut_handoff_service=CapCutHandoffService(local_app_data=local_app_data),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "CapCut current handoff API contract"}).json()["project_id"]
    job, _ = _save_current_capcut_draft_export_job(LocalProjectStore(tmp_path), project_id=project_id)

    first = client.post(f"/api/projects/{project_id}/capcut-draft-exports/{job['job_id']}/handoff")
    reused = client.post(f"/api/projects/{project_id}/capcut-draft-exports/{job['job_id']}/handoff")

    assert first.status_code == 200
    assert first.json()["handoff"]["status"] == "ready"
    assert first.json()["handoff"]["reused"] is False
    assert reused.status_code == 200
    assert reused.json()["handoff"]["status"] == "ready"
    assert reused.json()["handoff"]["reused"] is True


def test_capcut_handoff_diagnostics_api_reports_injected_windows_readiness_without_llm_call(tmp_path: Path) -> None:
    local_app_data = tmp_path / "LocalAppData"
    executable = local_app_data / "CapCut" / "Apps" / "8.9.1.3802" / "CapCut.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"capcut")
    project_root = local_app_data / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
    project_root.mkdir(parents=True)
    app = create_app(
        projects_root=tmp_path / "projects",
        capcut_handoff_service=CapCutHandoffService(local_app_data=local_app_data),
    )

    response = TestClient(app).get("/api/capcut/handoff-diagnostics")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["installation_path"] == str(executable)
    assert body["detected_version"] == "8.9.1.3802"
    assert body["is_supported"] is True
    assert body["project_root_path"] == str(project_root)
    assert body["project_root_exists"] is True
    assert body["write_access"] is True
    assert body["recovery_message"] is None
    assert body["checked_at"]


def _clean_high_confidence_transcribe(self, request):  # noqa: ANN001
    return STTResult(
        text="Office overview. A quick walkthrough.",
        segments=[
            STTSegment(start_sec=0.0, end_sec=1.5, text="Office overview.", confidence=0.99),
            STTSegment(start_sec=1.5, end_sec=3.0, text="A quick walkthrough.", confidence=0.98),
        ],
        provider_name="mock_stt",
    )


@pytest.mark.skipif(
    not (FFMPEG_AVAILABLE and PYCAPCUT_AVAILABLE),
    reason="ffmpeg/ffprobe/pycapcut not installed on this machine",
)
def test_capcut_draft_export_endpoint_produces_a_real_openable_draft_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _clean_high_confidence_transcribe,
    )
    source_audio = tmp_path / "narration.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4", str(source_audio)])
    source_script = tmp_path / "narration.txt"
    source_script.write_text("Office overview.\nA quick walkthrough.\n", encoding="utf-8")
    broll_video = tmp_path / "broll.mp4"
    _generate(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=4:size=320x240:rate=15", str(broll_video)]
    )

    app = create_app(
        projects_root=tmp_path,
        capcut_draft_export_config=CapCutDraftExportConfig(enabled=True),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "CapCut Draft Export Draft"}).json()["project_id"]

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
            "source_path": str(broll_video),
            "title": "Office skyline",
            "tags": ["office", "overview", "walkthrough"],
        },
    )

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={"transcription_job_id": transcription_job_id, "script_asset_id": script_asset_id},
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={"segment_analysis_job_id": segment_job_id, "recommendation_job_ids": [broll_job_id]},
    ).json()["job_id"]

    assert (
        client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve").status_code
        == 202
    )

    export_job_id = client.post(
        f"/api/projects/{project_id}/jobs/capcut-draft-export",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]

    body = _poll_until_finished(
        lambda: client.get(f"/api/projects/{project_id}/capcut-draft-exports/{export_job_id}").json()
    )

    assert body["status"] == "succeeded"
    assert body["export"]["export_type"] == "capcut_draft_export"

    file_uri = body["export"]["file_uri"]
    relative_output_path = Path(file_uri.removeprefix(f"local://projects/{project_id}/"))
    draft_directory = tmp_path / "projects" / project_id / relative_output_path
    assert (draft_directory / "draft_content.json").exists()
