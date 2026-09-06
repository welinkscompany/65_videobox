"""빈 편집판을 여는 엔드포인트.

편집 세션을 만드는 길이 둘뿐이었고 둘 다 기획을 먼저 통과해야 했다. 그래서 owner가
편집기를 열면 `먼저 영상 초안을 만들어 주세요`라는 잠긴 문을 만났다. 캡컷은 열면
바로 빈 편집판이다(2026-08-17 owner 지시).
"""

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app


def _client(tmp_path: Path) -> tuple[TestClient, str]:
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "blank board"}).json()["project_id"]
    return client, project_id


def test_the_editor_opens_without_going_through_planning(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path)

    response = client.post(f"/api/projects/{project_id}/editing-sessions/blank")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["session_id"]
    # 편집기가 바로 읽을 수 있어야 한다 -- 만들고 나서 화면이 못 여는 것은 완료가 아니다.
    latest = client.get(f"/api/projects/{project_id}/editing-sessions/latest")
    assert latest.status_code == 200, latest.text
    assert latest.json()["session_id"] == body["session_id"]


def test_the_editor_can_actually_draw_the_blank_board(tmp_path: Path) -> None:
    """세션만 만들면 화면이 안 열린다.

    2026-08-17에 세션만 만들었더니 편집기가 `재생 내용을 불러오지 못했어요`만
    띄웠다 -- 재생 목록을 만들려면 **짝이 되는 타임라인**이 있어야 하는데 없었다.
    만드는 것과 열리는 것은 다르다(§4 완료의 정의).
    """
    client, project_id = _client(tmp_path)

    session_id = client.post(f"/api/projects/{project_id}/editing-sessions/blank").json()["session_id"]

    manifest = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}/playback-manifest")
    assert manifest.status_code == 200, manifest.text
    assert manifest.json()["output"]["duration_sec"] > 0


def test_a_blank_board_has_one_scene_marked_as_needing_the_owner(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path)

    session_id = client.post(f"/api/projects/{project_id}/editing-sessions/blank").json()["session_id"]

    segments = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}").json()["segments"]
    assert len(segments) == 1
    # 아직 아무것도 안 들어 있다. 조용히 완성본으로 나가면 안 된다.
    assert segments[0]["review_required"] is True


def test_opening_a_second_blank_board_does_not_erase_the_first(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path)

    first = client.post(f"/api/projects/{project_id}/editing-sessions/blank").json()["session_id"]
    second = client.post(f"/api/projects/{project_id}/editing-sessions/blank").json()["session_id"]

    assert first != second
    assert client.get(f"/api/projects/{project_id}/editing-sessions/{first}").status_code == 200


def test_a_blank_board_needs_a_real_project(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    response = client.post("/api/projects/does-not-exist/editing-sessions/blank")

    assert response.status_code in {404, 422}, response.text


def test_a_blank_board_can_reach_the_finished_video(tmp_path: Path) -> None:
    """빈 편집판으로 들어온 창작자가 완성본까지 갈 길이 있어야 한다.

    2026-09-06 실측: `+ 새로 만들기`로 들어가면 편집판은 열리는데 내보내기가
    막다른 길이었다. 빈 편집판은 타임라인을 실제로 만들면서 **그 타임라인을
    만들었다는 작업 기록만 안 남기고** 있었고, 출력 화면은 그 기록으로
    "편집본 준비됨"을 판단한다. 부분 재생성은 2026-09-03에 같은 함정을
    고쳤는데(`editing_session_and_regeneration._record_timeline_build`)
    빈 편집판 경로가 빠져 있었다.
    """
    client, project_id = _client(tmp_path)

    session = client.post(f"/api/projects/{project_id}/editing-sessions/blank").json()
    timeline_id = session["timeline_id"]

    jobs = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]
    builds = [
        job
        for job in jobs
        if job["job_type"] == "timeline_build"
        and job["output_ref"] == timeline_id
        and job["status"] == "succeeded"
    ]
    assert builds, jobs

    # 사람 게이트는 그대로다 -- 승인 없이는 완성본을 만들지 못한다.
    approval = client.get(
        f"/api/projects/{project_id}/review-approvals/timelines/{timeline_id}"
    ).json()
    assert approval["review_status"] != "approved"
    assert approval["source_session_id"] == session["session_id"]
    assert approval["is_current"] is True

    # 승인하고 나면 완성본 요청이 "그런 작업 없음"으로 튕기지 않는다.
    assert client.post(
        f"/api/projects/{project_id}/review-approvals/{builds[0]['job_id']}/approve"
    ).status_code == 202
    started = client.post(
        f"/api/projects/{project_id}/jobs/final-render",
        json={"timeline_job_id": builds[0]["job_id"]},
    )
    assert started.status_code != 404, started.text
