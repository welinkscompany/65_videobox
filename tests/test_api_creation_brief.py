from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_core_engine.creation_interview import CreationInterviewQuestion
from videobox_storage.local_project_store import LocalProjectStore


def test_creation_brief_api_is_durable_idempotent_and_deletable(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "Interview"}).json()["project_id"]
    path = f"/api/projects/{project_id}/creation-briefs"
    payload = {
        "script_filename": "script.srt",
        "script_text": "1\n00:00:00,000 --> 00:00:01,000\n제품을 소개합니다",
        "idempotency_key": "interview-001",
        "capability_profile": {"ai_execution": "disabled"},
    }

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: TestClient(client.app).post(path, json=payload), range(2)))
    assert {response.status_code for response in responses} == {201}
    assert len({response.json()["brief_id"] for response in responses}) == 1
    assert len(LocalProjectStore(tmp_path).list_assets(project_id=project_id)) == 1
    brief = responses[0].json()
    resumed = client.get(f"{path}/{brief['brief_id']}")
    assert resumed.status_code == 200
    assert resumed.json()["idempotency_key"] == "interview-001"
    assert client.delete(f"{path}/{brief['brief_id']}").status_code == 204
    assert client.get(f"{path}/{brief['brief_id']}").status_code == 404


def test_creation_brief_api_supports_answer_bypass_edit_and_approval(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "Approval"}).json()["project_id"]
    path = f"/api/projects/{project_id}/creation-briefs"
    brief = client.post(path, json={
        "script_filename": "script.txt", "script_text": "소개 영상", "idempotency_key": "approval",
        "capability_profile": {"ai_execution": "disabled"},
    }).json()
    answered = client.post(f"{path}/{brief['brief_id']}/answers", json={
        "question_id": brief["questions"][0]["question_id"], "answer": "추천해줘", "expected_revision": brief["revision"]
    })
    assert answered.status_code == 200
    bypassed = client.post(f"{path}/{brief['brief_id']}/bypass", json={"expected_revision": answered.json()["revision"]})
    assert bypassed.status_code == 200
    edited = client.patch(f"{path}/{brief['brief_id']}", json={
        "summary": "사용자가 고친 요약", "expected_revision": bypassed.json()["revision"]
    })
    approved = client.post(f"{path}/{brief['brief_id']}/approve", json={"expected_revision": edited.json()["revision"]})
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


def test_creation_brief_api_accepts_utf8_script_upload_only(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "Upload"}).json()["project_id"]
    path = f"/api/projects/{project_id}/creation-briefs/upload"
    accepted = client.post(
        path,
        data={"idempotency_key": "upload-001", "capability_profile_json": '{"ai_execution":"disabled"}'},
        files={"script_file": ("script.md", "# 제품 소개".encode("utf-8"), "text/markdown")},
    )
    rejected = client.post(
        path,
        data={"idempotency_key": "upload-002", "capability_profile_json": "{}"},
        files={"script_file": ("script.pdf", b"not-a-script", "application/pdf")},
    )
    assert accepted.status_code == 201
    assert accepted.json()["script_filename"] == "script.md"
    assert rejected.status_code == 400


def test_creation_brief_api_streaming_upload_rejects_over_one_mebibyte(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "Too large"}).json()["project_id"]
    response = client.post(
        f"/api/projects/{project_id}/creation-briefs/upload",
        data={"idempotency_key": "large", "capability_profile_json": "{}"},
        files={"script_file": ("large.txt", b"x" * (1024 * 1024 + 1), "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "creation_brief_script_too_large"


def test_creation_brief_api_uses_injected_local_runtime_and_never_requires_provider_calls(tmp_path: Path) -> None:
    class LocalRuntime:
        calls = 0
        def plan_questions(self, *, script_text: str) -> list[CreationInterviewQuestion]:
            self.calls += 1
            return [CreationInterviewQuestion("goal", "목표는 무엇인가요?")]

    runtime = LocalRuntime()
    client = TestClient(create_app(projects_root=tmp_path, creation_interview_runtime=runtime))
    project_id = client.post("/api/projects", json={"name": "Injected runtime"}).json()["project_id"]
    response = client.post(f"/api/projects/{project_id}/creation-briefs", json={
        "script_filename": "script.txt", "script_text": "로컬", "idempotency_key": "injected", "capability_profile": {},
    })
    assert response.status_code == 201
    assert runtime.calls == 1
    assert response.json()["questions"][0]["field"] == "goal"


def test_creation_brief_upload_uses_the_same_injected_local_runtime(tmp_path: Path) -> None:
    class LocalRuntime:
        calls = 0
        def plan_questions(self, *, script_text: str) -> list[CreationInterviewQuestion]:
            self.calls += 1
            return [CreationInterviewQuestion("goal", "무엇을 만들까요?")]

    runtime = LocalRuntime()
    client = TestClient(create_app(projects_root=tmp_path, creation_interview_runtime=runtime))
    project_id = client.post("/api/projects", json={"name": "Uploaded runtime"}).json()["project_id"]
    response = client.post(
        f"/api/projects/{project_id}/creation-briefs/upload",
        data={"idempotency_key": "upload-runtime", "capability_profile_json": "{}"},
        files={"script_file": ("script.txt", "대본".encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 201
    assert runtime.calls == 1
    assert response.json()["questions"][0]["field"] == "goal"


def test_creation_brief_api_rejects_blank_upload_and_other_project_script_asset(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    first = client.post("/api/projects", json={"name": "First"}).json()["project_id"]
    second = client.post("/api/projects", json={"name": "Second"}).json()["project_id"]
    blank = client.post(
        f"/api/projects/{first}/creation-briefs/upload", data={"idempotency_key": "blank"},
        files={"script_file": ("blank.txt", b"   ", "text/plain")},
    )
    own = client.post(f"/api/projects/{first}/creation-briefs", json={
        "script_filename": "own.txt", "script_text": "첫 대본", "idempotency_key": "own", "capability_profile": {},
    }).json()
    cross_project = client.post(f"/api/projects/{second}/creation-briefs", json={
        "script_filename": "other.txt", "script_text": "둘 대본", "idempotency_key": "cross", "capability_profile": {},
        "script_asset_id": own["script_asset_id"],
    })
    assert blank.status_code == 400
    assert blank.json()["detail"] == "creation_brief_script_empty"
    assert cross_project.status_code == 404
