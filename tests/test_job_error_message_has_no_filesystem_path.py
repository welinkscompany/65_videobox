"""잡 실패 저장부(`error_message=str(exc)`)가 호스트 경로·명령 출력을 담던 것.

2026-09-07 전체 점검 §1-3이 `_http_error`(HTTP 예외 응답) 한 곳만 고치라고
했지만, 실제로 세어 보면 같은 패턴이 `local_pipeline.py`에 21곳,
`media_analysis.py`에 두 곳, `scene_videos.py`에 한 곳 더 있다(2026-09-08
인계 §2-1). 그 자리는 DB에 저장된 뒤 **정상적인 200 조회**로 나가므로
`_http_error`를 안 거친다.

여기서는 파일 경로·ffmpeg/ffprobe 명령 출력을 실제로 담을 수 있는 예외
종류(`FileNotFoundError`·`PermissionError`·`subprocess.CalledProcessError`·
그 밖의 `OSError`)만 고정 문구로 바꾸고, 나머지(코드성 `ValueError`·`RuntimeError`
등)는 그대로 둔다 -- `test_final_render_publish_fence.py`·
`test_api.py::test_segment_analysis_endpoint_marks_job_failed_on_unexpected_runtime_failure`
등 기존 시험 스무 개 가까이가 그 정확한 문구를 재기 때문이다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_core_engine.job_error_message import safe_job_error_message


def test_a_missing_source_file_error_becomes_a_fixed_code_not_the_real_path() -> None:
    host_path = Path("D:/videobox-data/projects/secret-project/assets/narration.wav")
    message = safe_job_error_message(FileNotFoundError(host_path))

    assert message == "asset_file_missing"
    assert str(host_path) not in message
    assert "/" not in message and "\\" not in message


def test_a_permission_error_becomes_a_fixed_code() -> None:
    message = safe_job_error_message(PermissionError("[Errno 13] Permission denied: 'D:\\\\videobox-data\\\\projects\\\\x\\\\y.mp4'"))

    assert message == "asset_file_permission_denied"
    assert "videobox-data" not in message


def test_a_failed_external_command_becomes_a_fixed_code_not_its_argv_or_stderr() -> None:
    exc = subprocess.CalledProcessError(
        returncode=1,
        cmd=["ffprobe", "-v", "error", "D:\\videobox-data\\projects\\x\\y.mp4"],
        output=None,
        stderr=b"D:\\videobox-data\\projects\\x\\y.mp4: No such file or directory",
    )

    message = safe_job_error_message(exc)

    assert message == "external_command_failed"
    assert "videobox-data" not in message


def test_a_status_code_valueerror_is_left_alone_because_the_screen_reads_it() -> None:
    # `OutputSourceStaleError`류 -- 사람이 읽는 실패 사유고 경로가 없다.
    message = safe_job_error_message(ValueError("stale_output_asset: content SHA-256 changed"))

    assert message == "stale_output_asset: content SHA-256 changed"


def test_a_plain_runtime_error_from_a_test_double_is_left_alone() -> None:
    # 실제 provider/테스트 더블이 던지는 흔한 모양 -- 경로가 아니라 사람이 읽을
    # 문장이라 화면이 그대로 보여준다(`test_api.py`의 "exploded" 류 시험들).
    message = safe_job_error_message(RuntimeError("segment analyzer exploded"))

    assert message == "segment analyzer exploded"


def test_segment_analysis_job_error_message_has_no_host_path_when_the_script_file_disappears(tmp_path: Path) -> None:
    """§1-3이 실제로 놓친 자리 -- `run_segment_analysis`의 실패 저장부.

    `_load_script_text`(`_pipeline_private_helpers.py:227-228`)는 등록된 대본
    자산의 저장 경로를 `Path.read_text()`로 직접 연다. 그 파일이 등록 뒤
    사라지면 `FileNotFoundError`의 문구에 **컨테이너 절대 경로**가 그대로
    담긴다(`[Errno 2] No such file or directory: '/videobox-data/...'`).
    """
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    source_audio = tmp_path / "narration.wav"
    source_script = tmp_path / "script.txt"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("한 문장짜리 대본.\n", encoding="utf-8")

    project_id = client.post("/api/projects", json={"name": "leak repro"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()
    script_asset_id = script_asset["asset_id"]
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]

    store = app.state.store
    stored_script_path = store.resolve_storage_uri(
        project_id=project_id, storage_uri=store.get_asset(project_id=project_id, asset_id=script_asset_id)["storage_uri"],
    )
    assert stored_script_path.exists()
    stored_script_path.unlink()

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={"transcription_job_id": transcription_job_id, "script_asset_id": script_asset_id},
    )

    jobs = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]
    segment_jobs = [job for job in jobs if job["job_type"] == "segment_analysis"]
    assert len(segment_jobs) == 1
    assert segment_jobs[0]["status"] == "failed"
    error_message = str(segment_jobs[0]["error_message"])

    assert error_message == "asset_file_missing"
    assert str(tmp_path) not in error_message
    assert "/" not in error_message and "\\" not in error_message
    # HTTP 응답도 §1-3의 `_http_error`가 이미 지킨다 -- 여기서는 잡 저장부만 잰다.
    assert response.status_code in (404, 500)
