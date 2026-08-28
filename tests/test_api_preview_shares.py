from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_domain_models.jobs import JobStatus, JobType
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


def _drive_project_to_succeeded_final_render(client: TestClient, tmp_path: Path, *, name: str) -> tuple[str, str]:
    """narration/script/broll -> transcription -> segments -> broll -> timeline -> approve -> render.

    `test_api_final_render_endpoint.py`의 fixture 패턴을 그대로 따른다 -- 진짜
    ffmpeg로 완성본을 만들어야 공유 링크가 진짜 mp4를 내려주는지 확인할 수 있다.
    """
    source_audio = tmp_path / f"{name}-narration.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4", str(source_audio)])
    source_script = tmp_path / f"{name}-narration.txt"
    source_script.write_text("Office overview.\nA quick walkthrough.\n", encoding="utf-8")
    broll_video = tmp_path / f"{name}-broll.mp4"
    _generate(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=4:size=320x240:rate=15", str(broll_video)]
    )

    project_id = client.post("/api/projects", json={"name": name}).json()["project_id"]

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
    return project_id, render_job_id


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_preview_share_lifecycle_serves_real_mp4_then_revokes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _clean_high_confidence_transcribe,
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, render_job_id = _drive_project_to_succeeded_final_render(
        client, tmp_path, name="Preview Share Draft"
    )

    create_response = client.post(f"/api/projects/{project_id}/final-renders/{render_job_id}/share")
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["url"] == f"/preview/{created['token']}"
    token = created["token"]

    status_response = client.get(f"/api/preview-shares/{token}")
    assert status_response.status_code == 200
    assert status_response.json() == {"status": "active"}

    content_response = client.get(f"/api/preview-shares/{token}/content")
    assert content_response.status_code == 200
    assert content_response.headers["content-type"] == "video/mp4"
    assert len(content_response.content) > 0

    downloaded = tmp_path / "shared.mp4"
    downloaded.write_bytes(content_response.content)
    probe = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(downloaded),
        ],
        capture_output=True, text=True, timeout=30,
    )
    assert float(probe.stdout.strip()) > 0.0

    shares_response = client.get(f"/api/projects/{project_id}/final-renders/{render_job_id}/shares")
    assert shares_response.status_code == 200
    shares = shares_response.json()["shares"]
    assert len(shares) == 1
    assert shares[0]["share_id"] == created["share_id"]
    assert "token" not in shares[0]

    revoke_response = client.post(
        f"/api/projects/{project_id}/preview-shares/{created['share_id']}/revoke"
    )
    assert revoke_response.status_code == 200

    assert client.get(f"/api/preview-shares/{token}").status_code == 404
    assert client.get(f"/api/preview-shares/{token}/content").status_code == 404


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_listing_shares_for_a_render_less_job_never_leaks_another_renders_shares(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 코드리뷰로 발견(2026-08-28): `render`가 없는 job(아직 안 끝났거나 실패한
    # final-render)으로 목록을 물으면 필터 없이 그 프로젝트의 **다른 완성본**
    # 공유 링크까지 그대로 새어 나갔다. 진짜 succeeded render 하나로 공유를
    # 만든 뒤, 같은 프로젝트에 아직 output_ref가 없는 job을 하나 더 심어서
    # 그 job으로 물었을 때 빈 목록만 와야 한다는 것을 확인한다.
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _clean_high_confidence_transcribe,
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, render_job_id = _drive_project_to_succeeded_final_render(
        client, tmp_path, name="Leak Check Draft"
    )
    create_response = client.post(f"/api/projects/{project_id}/final-renders/{render_job_id}/share")
    assert create_response.status_code == 201

    pending_job = app.state.store.create_job(
        project_id=project_id, job_type=JobType.FINAL_RENDER,
        input_ref="timeline-current", status=JobStatus.RUNNING,
    )

    shares_response = client.get(f"/api/projects/{project_id}/final-renders/{pending_job['job_id']}/shares")
    assert shares_response.status_code == 200
    assert shares_response.json()["shares"] == []


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_preview_share_rejects_job_id_not_owned_by_project_and_not_yet_succeeded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _clean_high_confidence_transcribe,
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_a, render_job_a = _drive_project_to_succeeded_final_render(
        client, tmp_path, name="Project A"
    )
    project_b_id = client.post("/api/projects", json={"name": "Project B"}).json()["project_id"]

    # job_id가 다른 project 소유인 경우 -- 추측해서 가져온 job_id로는 공유를 못 만든다.
    cross_project_response = client.post(
        f"/api/projects/{project_b_id}/final-renders/{render_job_a}/share"
    )
    assert cross_project_response.status_code in (400, 404)

    # 아직 성공하지 않은(존재하지 않는) job_id.
    not_ready_response = client.post(
        f"/api/projects/{project_a}/final-renders/not-a-real-job-id/share"
    )
    assert not_ready_response.status_code in (400, 404)
