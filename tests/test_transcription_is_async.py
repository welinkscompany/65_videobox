"""받아쓰기(전사)를 잡(비동기)으로 바꿈 -- 2026-09-08, §1-6 나머지.

2026-09-07 전체 점검 §1-6: Whisper 호출에 시간 제한이 없어 긴 내레이션은
nginx 330초 벽을 넘길 수 있다. 자막 번역·더빙과 같은 이유이고 같은 방식
(202 + `job_id`, `GET .../jobs/transcription/{job_id}`로 폴링)으로 바꿨다.

owner 승인(2026-09-08 대화, "받아쓰기... 전체 비동기 전환").
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_provider_interfaces.stt import STTRequest, STTResult, STTSegment


class _FailingSTTProvider:
    provider_name = "failing_stt"

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def transcribe(self, request: STTRequest) -> STTResult:
        raise self._exc


def _register_narration(client: TestClient, project_id: str, tmp_path: Path) -> str:
    # 경로 등록 문은 `projects_root` 밖의 경로를 거절한다(§1-1 봉쇄, 2026-09-07
    # 코드리뷰) -- 이 파일의 모든 시험이 `create_app(projects_root=tmp_path /
    # "projects")`를 쓰므로 여기서도 그 안에 둔다.
    narration = tmp_path / "projects" / "narration.wav"
    narration.parent.mkdir(parents=True, exist_ok=True)
    narration.write_bytes(b"fake wav data")
    response = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(narration)},
    )
    assert response.status_code == 201, response.text
    return response.json()["asset_id"]


def _transcribe(client: TestClient, project_id: str, narration_asset_id: str) -> dict:
    """받아쓰기를 걸고 끝날 때까지 기다린다.

    받아쓰기는 **비동기다**(2026-09-08, §1-6). `TestClient`는 background task를
    응답 뒤에 바로 돌리므로, 한 번 물어보면 이미 끝나 있다(더빙·자막 번역
    시험과 같은 패턴).
    """
    started = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    )
    assert started.status_code == 202, started.text
    assert started.json()["status"] != "succeeded", "시작 응답은 아직 처리 중이어야 한다"
    job_id = started.json()["job_id"]
    status_response = client.get(f"/api/projects/{project_id}/jobs/transcription/{job_id}")
    assert status_response.status_code == 200, status_response.text
    return status_response.json()


def test_transcription_starts_processing_and_finishes_on_poll(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "async transcription"}).json()["project_id"]
    narration_asset_id = _register_narration(client, project_id, tmp_path)

    job = _transcribe(client, project_id, narration_asset_id)

    assert job["status"] == "succeeded"
    assert job["transcript_uri"]


def test_a_failing_stt_provider_marks_the_job_failed_with_a_safe_message(tmp_path: Path) -> None:
    """예전엔 STT가 실패하면 잡이 영원히 RUNNING으로 멈춰 있었다 -- 되짚어 보니

    동기 코드에는 실패를 잡아 FAILED로 적는 처리 자체가 없었다. 비동기로
    바꾸면서 같이 넣었다.
    """
    app = create_app(
        projects_root=tmp_path / "projects",
        stt_provider=_FailingSTTProvider(RuntimeError("engine offline")),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "async transcription failure"}).json()["project_id"]
    narration_asset_id = _register_narration(client, project_id, tmp_path)

    job = _transcribe(client, project_id, narration_asset_id)

    assert job["status"] == "failed"
    jobs = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]
    transcription_jobs = [item for item in jobs if item["job_type"] == "transcription"]
    assert len(transcription_jobs) == 1
    assert transcription_jobs[0]["error_message"] == "engine offline"


def test_retrying_a_failed_transcription_job_actually_runs_the_stt_again(tmp_path: Path) -> None:
    """재시도는 잡 자리만 새로 만드는 게 아니라 **실제로 다시 돌아야 한다.**

    `start_transcription`이 더는 Whisper를 직접 부르지 않으므로, retry 라우트가
    새 배경 실행기를 걸지 않으면 재시도 잡이 영원히 처리 중으로 남는다.
    """
    calls = {"count": 0}
    real = STTResult(
        text="ok", segments=[STTSegment(start_sec=0.0, end_sec=1.0, text="ok", confidence=0.9)], provider_name="mock",
    )

    class _FlakyOnceProvider:
        provider_name = "flaky_once"

        def transcribe(self, request: STTRequest) -> STTResult:
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("first attempt fails")
            return real

    app = create_app(projects_root=tmp_path / "projects", stt_provider=_FlakyOnceProvider())
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "retry transcription"}).json()["project_id"]
    narration_asset_id = _register_narration(client, project_id, tmp_path)

    failed = _transcribe(client, project_id, narration_asset_id)
    assert failed["status"] == "failed"

    retried = client.post(f"/api/projects/{project_id}/jobs/{failed['job_id']}/retry")
    assert retried.status_code == 202, retried.text

    # retry는 백그라운드 스레드(threading.Thread)를 쓴다 -- TestClient가 자동으로
    # 기다려 주지 않으므로 직접 짧게 기다린 뒤 확인한다.
    import time

    for _ in range(50):
        polled = client.get(f"/api/projects/{project_id}/jobs/transcription/{retried.json()['job_id']}").json()
        if polled["status"] != "processing" and polled["status"] != "running":
            break
        time.sleep(0.1)

    assert polled["status"] == "succeeded", polled
    assert calls["count"] == 2
