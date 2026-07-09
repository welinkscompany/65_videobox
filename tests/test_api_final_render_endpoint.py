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


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_final_render_endpoint_produces_a_real_playable_mp4_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _clean_high_confidence_transcribe,
    )
    source_audio = tmp_path / "narration.wav"
    _generate(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4", str(source_audio)]
    )
    source_script = tmp_path / "narration.txt"
    source_script.write_text("Office overview.\nA quick walkthrough.\n", encoding="utf-8")
    broll_video = tmp_path / "broll.mp4"
    _generate(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=4:size=320x240:rate=15",
            str(broll_video),
        ]
    )

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Final Render Draft"}).json()["project_id"]

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
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id],
        },
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
    assert body["render"]["export_type"] == "final_render"

    file_uri = body["render"]["file_uri"]
    relative_output_path = Path(file_uri.removeprefix(f"local://projects/{project_id}/"))
    resolved_output_path = tmp_path / "projects" / project_id / relative_output_path
    assert resolved_output_path.exists()

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(resolved_output_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert float(probe.stdout.strip()) > 0.0
