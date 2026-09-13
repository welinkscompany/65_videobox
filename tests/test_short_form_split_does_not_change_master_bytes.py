"""R1(계획서 `docs/superpowers/plans/2026-09-12-a-short-that-looks-like-a-short.md`)의
재확인: 숏폼을 만들 때 하는 장면 경계 나누기(`short_form_scenes.
cut_only_what_the_short_uses` -> `split_segments_at`)가 완성본(마스터) 렌더의
바이트를 바꾸는가.

**결과(2026-09-13): 바꾼다.** 아래 `xfail`이 그 실측을 고정해 둔다 -- 자세한
근거는 그 사유 문구에 있다.

**왜 다시 재는가.** 이 주장을 지키는 근거 md5(`2be2ffb42`, 2026-09-12
16:34)는 세로 기본값을 `blur`로 바꾼 렌더러 변경(`d7bd2d023`, 같은 날
17:31 -- **한 시간 뒤**)보다 먼저 잰 값이다. 구현자도 "다시 안 쟀다"고
밝혔다. 이 시험이 그 재측정이다.

**왜 컨테이너가 아니라 여기(로컬 pytest)에서 재는가.** 실제 컨테이너에서
쓰던 검증용 프로젝트(`2026-09-12-ca6dd9ed`)는 반복 프로빙으로 마스터가
너무 복잡해져(장면 하나가 14단으로 쪼개짐) 렌더 자체가 컨테이너의
`pids_limit`을 넘겨 실패한다(별도 task로 큐에 있음, 이번 시험과 무관한
자원 문제) -- 그 문제를 피해서 **깨끗한 합성 자산**으로 같은 질문에 답한다.
이 컴퓨터에는 실제 ffmpeg가 있으므로(`test_api_final_render_endpoint.py`와
같은 전제) cgroup 제약이 없는 로컬 환경에서도 "나누기가 바이트를 바꾸는가"
라는 질문 자체는 그대로 답할 수 있다 -- 이 질문은 자원 한도가 아니라
렌더러의 필터 그래프 구성 로직에 달려 있다.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_core_engine.editing_session import split_segments_at
from videobox_provider_interfaces.stt import STTResult, STTSegment

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _generate(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def _poll_until_finished(get_result, *, timeout_seconds: float = 60.0):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        body = get_result()
        if body["status"] in {"succeeded", "failed"}:
            return body
        time.sleep(0.1)
    raise TimeoutError("Job did not finish in time.")


def _clean_two_sentence_transcribe(self, request):  # noqa: ANN001
    """장면 하나를 두 문장으로 채운다 -- 나눌 자리(문장 사이)가 있어야 한다.

    `test_api_final_render_endpoint.py`의 검증된 성공 문구를 그대로 쓴다 --
    브롤 추천 신뢰도가 낮으면 `segment_review_required` 검토 표시가 붙어
    승인 자체가 막힌다(이 시험이 재려는 것과 무관한 변수라 피한다).
    """
    return STTResult(
        text="Office overview. A quick walkthrough.",
        segments=[
            STTSegment(start_sec=0.0, end_sec=1.5, text="Office overview.", confidence=0.99),
            STTSegment(start_sec=1.5, end_sec=3.0, text="A quick walkthrough.", confidence=0.98),
        ],
        provider_name="mock_stt",
    )


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
@pytest.mark.xfail(
    strict=True,
    reason=(
        "2026-09-13 실측으로 R1 주장이 깨졌다고 확인됨 -- 나누기 전후 렌더가 "
        "재생 길이·프레임 수·코덱은 완전히 같지만(90 video frames, 3.000s 둘 다) "
        "파일 크기가 다르고(249441 vs 265452 bytes), 픽셀 단위로 뽑아 비교하면 "
        "90프레임 전부가 다르다 -- 국소적 키프레임 재배치가 아니라 전역적인 "
        "차이다. 같은 편집본을 나누기 없이 두 번 렌더하면 바이트가 완전히 "
        "같다는 것은 별도로 확인했다(대조군, 논-디터미니즘이 아니다). 근본 "
        "원인 후보: 세그먼트가 둘로 나뉘면서 같은 소스를 두 번째 -i로 다시 "
        "여는 트림 경계 계산이 서브프레임 단위로 어긋나 이후 모든 프레임이 "
        "한 틱씩 밀렸을 가능성 -- 아직 확정 진단 아님, 후속 조사 필요"
        "(spawn_task로 큐에 올림). 이 시험은 xfail로 그 실측을 고정해 둔다 -- "
        "고치면 strict=True가 실패로 알려 준다."
    ),
)
def test_splitting_a_scene_boundary_does_not_change_the_master_render_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _clean_two_sentence_transcribe,
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
    project_id = client.post("/api/projects", json={"name": "R1 split re-check"}).json()["project_id"]

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
    # **편집판을 실제로 연다.** 이걸 안 하면 렌더가 세션 없이 타임라인에서
    # 바로 장면을 뽑는 대비책 경로로 빠져서(`local_pipeline.py`
    # `_editing_session_for_output_timeline`이 `None`을 돌려줌), 뒤에서 세션을
    # 고쳐도(장면 나누기) 렌더가 그 변경을 아예 안 본다 -- 처음에 이 문을
    # 안 열어서 시험이 거짓으로 통과할 뻔했다.
    create_session_response = client.post(
        f"/api/projects/{project_id}/editing-sessions", json={"timeline_job_id": timeline_job_id}
    )
    assert create_session_response.status_code == 201, create_session_response.text

    session_response = client.get(f"/api/projects/{project_id}/editing-sessions/latest")
    assert session_response.status_code == 200, session_response.text
    session = session_response.json()
    session_id = session["session_id"]
    segments_before = session["segments"]
    # 대본이 두 문장이라 세그먼트 분석이 이미 둘로 나눴을 수 있다 -- 나눌 자리가
    # 남아 있는(2초보다 긴) 장면을 하나 골라 그 한가운데를 다시 나눈다.
    target = next(seg for seg in segments_before if seg["end_sec"] - seg["start_sec"] > 1.0)
    midpoint = (target["start_sec"] + target["end_sec"]) / 2

    render_job_id_before = client.post(
        f"/api/projects/{project_id}/jobs/final-render",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]
    result_before = _poll_until_finished(
        lambda: client.get(f"/api/projects/{project_id}/final-renders/{render_job_id_before}").json()
    )
    assert result_before["status"] == "succeeded", result_before
    file_uri_before = result_before["render"]["file_uri"]
    output_before = tmp_path / "projects" / project_id / Path(
        file_uri_before.removeprefix(f"local://projects/{project_id}/")
    )
    md5_before = _md5(output_before)

    # **경계 나누기 자체만 한다** -- 화면 단추/유진 채팅과 같은 함수
    # (`short_form_scenes.cut_only_what_the_short_uses`)가 부르는 저장소
    # 원자성 그대로: split_segments_at -> update_editing_session
    # (invalidate_output_freshness=False, 이미 있는 검토 승인을 유지한다).
    store = app.state.store
    current_session = store.get_editing_session(project_id=project_id, session_id=session_id)
    split_payload = split_segments_at(
        session=dict(current_session), splits=[(target["segment_id"], midpoint)], label="숏폼에 쓸 자리 나누기",
    )
    saved = store.update_editing_session(
        project_id=project_id,
        session_id=session_id,
        session_payload=split_payload,
        expected_revision=int(current_session["session_revision"]),
        invalidate_output_freshness=False,
    )
    assert len(saved["segments"]) == len(segments_before) + 1, "나누기가 실제로 장면 하나를 늘렸는지 확인"
    # `_carry_the_owners_approval_to_the_new_board`(short_form_scenes.py)와
    # 같은 마무리 -- 승인 행을 다시 안 쓰고 **가리키는 판 버전만** 옮긴다.
    # 안 하면 렌더가 "editing session revision changed"로 거절한다.
    store.bind_timeline_to_editing_session_revision(
        project_id=project_id,
        timeline_id=str(saved["timeline_id"]),
        session_id=session_id,
        session_revision=int(saved["session_revision"]),
        keep_existing_review_approval=True,
    )

    render_job_id_after = client.post(
        f"/api/projects/{project_id}/jobs/final-render",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]
    result_after = _poll_until_finished(
        lambda: client.get(f"/api/projects/{project_id}/final-renders/{render_job_id_after}").json()
    )
    assert result_after["status"] == "succeeded", result_after
    file_uri_after = result_after["render"]["file_uri"]
    output_after = tmp_path / "projects" / project_id / Path(
        file_uri_after.removeprefix(f"local://projects/{project_id}/")
    )
    md5_after = _md5(output_after)

    assert md5_after == md5_before, (
        "장면 경계를 나눴는데 완성본 바이트가 달라졌다 -- "
        f"before={md5_before} after={md5_after}. R1 주장이 지금 렌더러에서는 깨졌다."
    )
