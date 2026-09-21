from __future__ import annotations

import asyncio

import pytest

from videobox_agent_gateway.hermes_approval_mcp_client import (
    HermesApprovalMcpClient,
    HermesApprovalQueueError,
)


class _Response:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")

    def json(self) -> dict:
        return self.payload


class _Http:
    def __init__(self, response_payload: dict | None = None) -> None:
        self.posts: list[tuple[str, dict | None]] = []
        self._response_payload = response_payload or {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [], "structuredContent": {"decision_id": "abc"}, "isError": False},
        }

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def post(self, path: str, json: dict | None = None):
        self.posts.append((path, json))
        return _Response(self._response_payload)


def _client(http: _Http, base_url: str = "http://127.0.0.1:19680") -> HermesApprovalMcpClient:
    return HermesApprovalMcpClient(
        base_url=base_url,
        http_client_factory=lambda **_: http,
    )


def test_rejects_urls_outside_the_two_allowed_forms() -> None:
    for bad in [
        "http://127.0.0.1:19680/extra-path",
        "http://127.0.0.1:9999",
        "https://127.0.0.1:19680",
        "http://evil.example.com:19680",
        "http://127.0.0.1:19680?x=1",
        "http://user:pass@127.0.0.1:19680",
    ]:
        with pytest.raises(ValueError):
            HermesApprovalMcpClient(base_url=bad)


def test_accepts_the_two_allowed_forms() -> None:
    HermesApprovalMcpClient(base_url="http://127.0.0.1:19680")
    HermesApprovalMcpClient(base_url="http://host.docker.internal:19680")


def test_submit_title_candidates_sends_a_tools_call_json_rpc_request() -> None:
    http = _Http()
    client = _client(http)

    async def call():
        return await client.submit_title_candidates(
            project_id="project-a",
            cycle_id="cycle-1",
            title_candidates=[{"index": 0, "text": "제목 후보 1"}],
            question="어느 제목이 좋을까요?",
            target="루이스 대표님",
        )

    result = asyncio.run(call())

    assert result == {"decision_id": "abc"}
    [(path, body)] = http.posts
    assert path == "/mcp"
    assert body["method"] == "tools/call"
    assert body["params"]["name"] == "submit_title_candidates"
    assert body["params"]["arguments"] == {
        "project_id": "project-a",
        "cycle_id": "cycle-1",
        "title_candidates": [{"index": 0, "text": "제목 후보 1"}],
        "question": "어느 제목이 좋을까요?",
        "target": "루이스 대표님",
    }


def test_submit_script_confirmation_calls_the_right_tool() -> None:
    http = _Http()
    client = _client(http)

    async def call():
        await client.submit_script_confirmation(
            project_id="project-a",
            cycle_id="cycle-1",
            script_candidates=[{"index": 0, "text": "대본 전문"}],
            question="대본 확정할까요?",
            target="루이스 대표님",
        )

    asyncio.run(call())

    [(_, body)] = http.posts
    assert body["params"]["name"] == "submit_script_confirmation"


def test_submit_upload_request_calls_the_right_tool() -> None:
    http = _Http()
    client = _client(http)

    async def call():
        await client.submit_upload_request(
            project_id="project-a",
            cycle_id="cycle-1",
            upload_target="youtube",
            upload_scheduled_summary_ko="1분 30초 셀러 교육 영상",
            question="업로드해도 될까요?",
            target="루이스 대표님",
        )

    asyncio.run(call())

    [(_, body)] = http.posts
    assert body["params"]["name"] == "submit_upload_request"


def test_mcp_tool_error_response_raises_without_leaking_raw_text() -> None:
    http = _Http(
        response_payload={
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": "some internal detail"}], "isError": True},
        }
    )
    client = _client(http)

    async def call():
        await client.submit_title_candidates(
            project_id="p", cycle_id="c", title_candidates=[], question="q", target="t",
        )

    with pytest.raises(HermesApprovalQueueError) as excinfo:
        asyncio.run(call())
    assert "internal detail" not in str(excinfo.value)


def test_json_rpc_error_response_raises() -> None:
    http = _Http(
        response_payload={"jsonrpc": "2.0", "id": 1, "error": {"code": -32602, "message": "bad"}}
    )
    client = _client(http)

    async def call():
        await client.submit_upload_request(
            project_id="p", cycle_id="c", upload_target="youtube",
            upload_scheduled_summary_ko="s", question="q", target="t",
        )

    with pytest.raises(HermesApprovalQueueError):
        asyncio.run(call())


def test_transport_failure_raises_the_same_error_type() -> None:
    class _BrokenHttp(_Http):
        async def post(self, path: str, json: dict | None = None):
            raise RuntimeError("connection refused")

    client = _client(_BrokenHttp())

    async def call():
        await client.submit_script_confirmation(
            project_id="p", cycle_id="c", script_candidates=[], question="q", target="t",
        )

    with pytest.raises(HermesApprovalQueueError):
        asyncio.run(call())
