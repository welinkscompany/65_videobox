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

    jobs = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]
    render_job = next(job for job in jobs if job["job_id"] == render_job_id)
    assert render_job["progress_percent"] == 100

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


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_final_render_audio_content_endpoint_extracts_a_real_audio_only_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # owner 요청(2026-08-28): "오디오만... 내보내기". 새 렌더 파이프라인이 아니라
    # 이미 만들어진 완성본 mp4에서 ffmpeg -vn으로 떠낸다(`audio_export.py`) -- 진짜
    # mp4를 진짜 ffmpeg로 만든 뒤, 그 오디오 트랙만 받아 재생 가능한 오디오인지 확인한다.
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
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=4:size=320x240:rate=15", str(broll_video)]
    )

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Audio Export Draft"}).json()["project_id"]

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

    response = client.get(f"/api/projects/{project_id}/final-renders/{render_job_id}/audio-content")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mp4"

    downloaded_audio = tmp_path / "downloaded.m4a"
    downloaded_audio.write_bytes(response.content)
    probe = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_type",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(downloaded_audio),
        ],
        capture_output=True, text=True, timeout=30,
    )
    assert probe.stdout.strip() == "audio"

    # 두 번째 요청은 다시 ffmpeg를 돌리지 않고 캐시된 파일을 그대로 준다.
    second_response = client.get(f"/api/projects/{project_id}/final-renders/{render_job_id}/audio-content")
    assert second_response.status_code == 200
    assert second_response.content == response.content


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_subtitle_content_endpoint_downloads_a_real_srt_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # owner 요청(2026-08-28): "srt... 내보내기". `.srt` 파일은 이미 디스크에 있었다 --
    # 내려받는 문(엔드포인트)만 없었다.
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
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=4:size=320x240:rate=15", str(broll_video)]
    )

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Subtitle Export Draft"}).json()["project_id"]

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
    subtitle_job_id = client.post(
        f"/api/projects/{project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]

    response = client.get(f"/api/projects/{project_id}/subtitles/{subtitle_job_id}/content")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="subtitle.srt"'
    srt_text = response.content.decode("utf-8")
    assert "-->" in srt_text
    assert "Office overview." in srt_text
