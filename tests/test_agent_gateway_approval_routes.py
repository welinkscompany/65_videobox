from __future__ import annotations

from fastapi.testclient import TestClient

from videobox_agent_gateway.hermes_approval_mcp_client import (
    HermesApprovalMcpClient,
    HermesApprovalQueueError,
)
from videobox_agent_gateway.main import create_app

_TOKEN = "service-secret-that-is-at-least-32-bytes"


class _FakeApprovalClient(HermesApprovalMcpClient):
    def __init__(self) -> None:
        # 부모 __init__의 URL 검증을 건너뛴다 -- 실제 HTTP 호출을 안 한다.
        self.calls: list[tuple[str, dict]] = []
        self._fail = False

    async def submit_title_candidates(self, **kwargs):
        self.calls.append(("submit_title_candidates", kwargs))
        if self._fail:
            raise HermesApprovalQueueError("hermes_approval_queue_unavailable")
        return {"decision_id": "title-1"}

    async def submit_script_confirmation(self, **kwargs):
        self.calls.append(("submit_script_confirmation", kwargs))
        if self._fail:
            raise HermesApprovalQueueError("hermes_approval_queue_unavailable")
        return {"decision_id": "script-1"}

    async def submit_upload_request(self, **kwargs):
        self.calls.append(("submit_upload_request", kwargs))
        if self._fail:
            raise HermesApprovalQueueError("hermes_approval_queue_unavailable")
        return {"decision_id": "upload-1"}


def _app_and_client() -> tuple[_FakeApprovalClient, TestClient]:
    fake = _FakeApprovalClient()
    app = create_app(approval_client=fake, service_token=_TOKEN)
    return fake, TestClient(app)


def test_routes_are_absent_when_no_approval_client_is_configured() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/internal/approvals/title-candidates",
        headers={"Authorization": f"Bearer {_TOKEN}"},
        json={
            "project_id": "p", "cycle_id": "c",
            "title_candidates": [{"index": 0, "text": "t"}],
            "question": "q", "target": "t",
        },
    )
    assert response.status_code == 404


def test_title_candidates_requires_a_valid_service_token() -> None:
    _, client = _app_and_client()
    response = client.post(
        "/internal/approvals/title-candidates",
        json={
            "project_id": "p", "cycle_id": "c",
            "title_candidates": [{"index": 0, "text": "t"}],
            "question": "q", "target": "t",
        },
    )
    assert response.status_code == 401


def test_title_candidates_happy_path_calls_the_client_and_reports_queued() -> None:
    fake, client = _app_and_client()
    response = client.post(
        "/internal/approvals/title-candidates",
        headers={"Authorization": f"Bearer {_TOKEN}"},
        json={
            "project_id": "project-a", "cycle_id": "cycle-1",
            "title_candidates": [{"index": 0, "text": "제목 후보"}],
            "question": "어느 제목이 좋을까요?", "target": "루이스 대표님",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"queued": True, "decision_id": "title-1"}
    [(name, kwargs)] = fake.calls
    assert name == "submit_title_candidates"
    assert kwargs["project_id"] == "project-a"
    assert kwargs["title_candidates"] == [{"index": 0, "text": "제목 후보"}]


def test_script_confirmation_happy_path() -> None:
    fake, client = _app_and_client()
    response = client.post(
        "/internal/approvals/script-confirmation",
        headers={"Authorization": f"Bearer {_TOKEN}"},
        json={
            "project_id": "project-a", "cycle_id": "cycle-1",
            "script_candidates": [{"index": 0, "text": "대본 전문"}],
            "question": "대본 확정할까요?", "target": "루이스 대표님",
        },
    )
    assert response.status_code == 200
    assert response.json()["decision_id"] == "script-1"


def test_upload_request_happy_path() -> None:
    fake, client = _app_and_client()
    response = client.post(
        "/internal/approvals/upload-request",
        headers={"Authorization": f"Bearer {_TOKEN}"},
        json={
            "project_id": "project-a", "cycle_id": "cycle-1",
            "upload_target": "youtube",
            "upload_scheduled_summary_ko": "1분 30초 셀러 교육 영상",
            "question": "업로드해도 될까요?", "target": "루이스 대표님",
        },
    )
    assert response.status_code == 200
    assert response.json()["decision_id"] == "upload-1"


def test_missing_required_field_is_rejected_before_reaching_the_client() -> None:
    fake, client = _app_and_client()
    response = client.post(
        "/internal/approvals/upload-request",
        headers={"Authorization": f"Bearer {_TOKEN}"},
        json={"project_id": "project-a", "cycle_id": "cycle-1"},
    )
    assert response.status_code == 422
    assert fake.calls == []


def test_queue_failure_surfaces_as_502_not_a_silent_success() -> None:
    fake = _FakeApprovalClient()
    fake._fail = True
    app = create_app(approval_client=fake, service_token=_TOKEN)
    client = TestClient(app)
    response = client.post(
        "/internal/approvals/upload-request",
        headers={"Authorization": f"Bearer {_TOKEN}"},
        json={
            "project_id": "p", "cycle_id": "c", "upload_target": "youtube",
            "upload_scheduled_summary_ko": "s", "question": "q", "target": "t",
        },
    )
    assert response.status_code == 502
