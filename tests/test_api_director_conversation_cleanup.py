"""쌓인 유진 대화를 화면에서 정리할 수 있어야 한다."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app


def _client_with_conversation(tmp_path: Path):
    app = create_app(projects_root=tmp_path / "projects", media_analysis_poll_interval_seconds=3600)
    client = TestClient(app)
    store = app.state.store
    project = store.bootstrap_project("대화 정리")
    session = store.save_editing_session(
        project_id=project.project_id, timeline_id="timeline",
        session_payload={"segments": [{"segment_id": "seg"}], "history": []},
    )
    created = client.post(
        f"/api/projects/{project.project_id}/director/conversations",
        json={"session_id": session["session_id"]},
    )
    return client, project.project_id, created.json()["conversation_id"]


def test_the_owner_can_see_what_conversations_exist(tmp_path: Path) -> None:
    client, project_id, conversation_id = _client_with_conversation(tmp_path)

    response = client.get(f"/api/projects/{project_id}/director/conversations")

    assert response.status_code == 200
    listed = response.json()["conversations"]
    assert [item["conversation_id"] for item in listed] == [conversation_id]
    assert listed[0]["message_count"] == 0


def test_deleting_a_conversation_removes_it_from_the_list(tmp_path: Path) -> None:
    client, project_id, conversation_id = _client_with_conversation(tmp_path)

    removed = client.delete(f"/api/projects/{project_id}/director/conversations/{conversation_id}")

    assert removed.status_code == 204
    assert client.get(f"/api/projects/{project_id}/director/conversations").json()["conversations"] == []


def test_deleting_one_that_is_gone_says_so_instead_of_pretending(tmp_path: Path) -> None:
    client, project_id, _ = _client_with_conversation(tmp_path)

    response = client.delete(f"/api/projects/{project_id}/director/conversations/conv-missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "director_conversation_missing"
