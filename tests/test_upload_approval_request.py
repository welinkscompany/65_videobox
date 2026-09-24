from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_provider_interfaces.stt import STTResult, STTSegment

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


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


def _clean_high_confidence_transcribe(self, request):  # noqa: ANN001
    return STTResult(
        text="Office overview. A quick walkthrough.",
        segments=[
            STTSegment(start_sec=0.0, end_sec=1.5, text="Office overview.", confidence=0.99),
            STTSegment(start_sec=1.5, end_sec=3.0, text="A quick walkthrough.", confidence=0.98),
        ],
        provider_name="mock_stt",
    )


def _build_real_completed_render(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A genuinely completed final render, not a hand-crafted job row --
    `request_upload_approval` reads the same `get_final_render_result` that
    the outputs screen does, and that call resolves the export from the job's
    `output_ref`, not from job status alone."""
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

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Upload Approval Draft"}).json()["project_id"]

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
        json={"source_path": str(broll_video), "title": "Office skyline", "tags": ["office", "overview", "walkthrough"]},
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
    render_job_id = client.post(
        f"/api/projects/{project_id}/jobs/final-render",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]
    body = _poll_until_finished(
        lambda: client.get(f"/api/projects/{project_id}/final-renders/{render_job_id}").json()
    )
    assert body["status"] == "succeeded"
    return app, client, project_id, render_job_id


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_upload_approval_reports_not_queued_when_no_hermes_bridge_is_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # create_app()가 기본 환경(테스트 환경)에는 agent_gateway_client가 없다 --
    # 결재함 큐가 안 켜진 것뿐이지 완성본이나 승인 요청 자체가 잘못된 게 아니다.
    _app, client, project_id, render_job_id = _build_real_completed_render(tmp_path, monkeypatch)

    response = client.post(
        f"/api/projects/{project_id}/final-renders/{render_job_id}/request-upload-approval",
        json={"upload_scheduled_summary_ko": "이번 주 목요일에 유튜브로 올릴 예정입니다."},
    )

    assert response.status_code == 200
    assert response.json() == {"queued": False}


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_upload_approval_calls_the_hermes_bridge_when_it_is_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, client, project_id, render_job_id = _build_real_completed_render(tmp_path, monkeypatch)

    calls: list[dict[str, object]] = []

    class _FakeApprovalClient:
        async def submit_upload_request(self, **kwargs: object) -> dict[str, object]:
            calls.append(kwargs)
            return {"queued": True}

    app.state.agent_gateway_client = _FakeApprovalClient()

    response = client.post(
        f"/api/projects/{project_id}/final-renders/{render_job_id}/request-upload-approval",
        json={"upload_target": "youtube", "upload_scheduled_summary_ko": "이번 주 목요일에 올릴 예정입니다."},
    )

    assert response.status_code == 200
    assert response.json() == {"queued": True}
    assert len(calls) == 1
    assert calls[0]["project_id"] == project_id
    assert calls[0]["cycle_id"] == render_job_id
    assert calls[0]["upload_target"] == "youtube"
    assert calls[0]["upload_scheduled_summary_ko"] == "이번 주 목요일에 올릴 예정입니다."
    assert calls[0]["target"] == "루이스 대표님"


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_upload_approval_surfaces_a_failure_when_the_hermes_bridge_is_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 대본 확정 알림과 다르게, 여기서는 owner가 지금 막 누른 요청이다 -- 실패를
    # 삼키면 결재함에 아무것도 안 올라간 채 owner가 계속 기다리게 된다.
    app, client, project_id, render_job_id = _build_real_completed_render(tmp_path, monkeypatch)

    class _BrokenApprovalClient:
        async def submit_upload_request(self, **kwargs: object) -> dict[str, object]:
            raise RuntimeError("hermes_approval_mcp_unreachable")

    app.state.agent_gateway_client = _BrokenApprovalClient()

    response = client.post(
        f"/api/projects/{project_id}/final-renders/{render_job_id}/request-upload-approval",
        json={"upload_scheduled_summary_ko": "이번 주 목요일에 올릴 예정입니다."},
    )

    # 코드리뷰(2026-09-24): owner 입력이 아니라 상류(Hermes 결재함 다리)가
    # 안 닿은 것이므로 400이 아니라 502여야 한다.
    assert response.status_code == 502
    assert "upload_approval_queue_unavailable" in response.text


def test_upload_approval_refuses_a_render_that_does_not_exist_yet(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "No Render Yet"}).json()["project_id"]

    response = client.post(
        f"/api/projects/{project_id}/final-renders/final_render_job_001/request-upload-approval",
        json={"upload_scheduled_summary_ko": "아직 완성본이 없습니다."},
    )

    assert response.status_code >= 400
