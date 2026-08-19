from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app


def test_formats_start_empty_and_are_shared_across_projects(tmp_path: Path) -> None:
    # 포맷은 프로젝트가 아니라 사용자에게 붙는다. 새 프로젝트를 열어도 같은 목록이다.
    client = TestClient(create_app(projects_root=tmp_path))
    client.post("/api/projects", json={"name": "첫 프로젝트"})
    client.post("/api/projects", json={"name": "둘째 프로젝트"})

    response = client.get("/api/format-templates")

    assert response.status_code == 200
    assert response.json() == {"templates": []}


def test_saving_a_format_from_a_session_that_does_not_exist_is_reported(tmp_path: Path) -> None:
    # 없는 편집본에서 포맷을 뽑을 수는 없다. 조용히 빈 포맷을 만들면 나중에
    # 그걸 적용했을 때 아무 일도 안 일어난다.
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "포맷"}).json()["project_id"]

    response = client.post(
        f"/api/projects/{project_id}/format-templates",
        json={"name": "내 포맷", "session_id": "session_missing"},
    )

    assert response.status_code == 404


def test_a_format_needs_a_name(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "포맷"}).json()["project_id"]

    response = client.post(
        f"/api/projects/{project_id}/format-templates",
        json={"name": "", "session_id": "session_a"},
    )

    assert response.status_code == 422


def test_saving_and_applying_a_format_round_trips_onto_the_session(tmp_path: Path) -> None:
    """저장한 포맷을 실제로 적용하는 왕복이 한 번은 성공해야 한다.

    기존 테스트는 404·422만 확인해서 전부 초록인 채로 적용이 **항상 500**이었다 --
    라우터가 자막 스타일 갱신에 없는 scope(`all`)와 `segment_ids=None`을 넘기고
    있었고, 성공 경로를 밟는 테스트가 하나도 없어 아무도 몰랐다.
    """
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "포맷 왕복"}).json()["project_id"]
    timeline = app.state.store.save_timeline_run(
        project_id=project_id,
        output_mode="landscape",
        timeline_payload={"output": {"width": 1920, "height": 1080}, "tracks": []},
    )
    saved_session = app.state.store.save_editing_session(
        project_id=project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {"segment_id": "seg-1", "start_sec": 0.0, "end_sec": 2.0, "caption_text": "안녕"},
                {"segment_id": "seg-2", "start_sec": 2.0, "end_sec": 4.0, "caption_text": "하세요"},
            ],
            "history": [],
            # 편집본은 CaptionStyle 정본 이름(`font_size_px`)을 쓴다. 프리셋의
            # 짧은 이름(`font_size`)과 다르다 -- 그걸 넣으면 적용이 400이 된다.
            "caption_style": {"font_size_px": 42, "text_color": "#FFFFFFFF", "font_family": "Noto Sans KR"},
        },
    )
    session_id = saved_session["session_id"]

    save = client.post(
        f"/api/projects/{project_id}/format-templates",
        json={"name": "내 포맷", "session_id": session_id},
    )
    assert save.status_code == 201, save.text
    template_id = save.json()["template_id"]

    apply = client.post(
        f"/api/projects/{project_id}/format-templates/{template_id}/apply",
        json={"session_id": session_id, "expected_revision": int(saved_session["session_revision"])},
    )

    assert apply.status_code == 200, apply.text
    applied_session = apply.json()["session"]
    assert applied_session["caption_style"]["font_size_px"] == 42
    # 장면까지 같은 모양이어야 한다. 세션 값만 바꾸면 화면이 장면 스타일을 이긴다.
    assert all(segment["caption_style"]["font_size_px"] == 42 for segment in applied_session["segments"])


def test_applying_a_format_nobody_saved_is_reported(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "포맷"}).json()["project_id"]

    response = client.post(
        f"/api/projects/{project_id}/format-templates/format_template_missing/apply",
        json={"session_id": "session_a", "expected_revision": 1},
    )

    assert response.status_code == 404
