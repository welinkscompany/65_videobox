"""Bounded, allowlisted client for the AK-System Hermes 결재함 MCP connector.

**이 클라이언트는 아무것도 실행하지 않는다.** AK-System Hermes 저장소의
`videobox-mcp-connector-server.js`(W1015)가 노출하는 세 MCP 도구
(`submit_title_candidates`/`submit_script_confirmation`/`submit_upload_request`)는
전부 "대표님 결재함에 pending 항목을 넣는 것"만 한다 — 실제 유튜브 업로드
실행은 이 경로의 범위 밖이고, 승인 후에도 VideoBox 쪽 책임으로 남는다
(`docs/development-fast-path.ko.md` §10.14 2-D).

이 서버는 `127.0.0.1` 루프백에만 바인드한다(그 저장소의 config 주석 확인).
컨테이너 안에서는 `host.docker.internal`로 같은 자리에 닿는다 — 둘 다 같은
기계라 이 컴퓨터 밖으로 나가지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable
import itertools
from typing import Any
from urllib.parse import urlsplit


class HermesApprovalQueueError(RuntimeError):
    """A deliberately redacted Hermes 결재함 큐 전송 실패."""


_ALLOWED_HOSTS = ("127.0.0.1", "host.docker.internal")
_TIMEOUT_SECONDS_DEFAULT = 10.0
_id_counter = itertools.count(1)


def _default_http_client_factory(*, base_url: str, timeout: float):
    import httpx

    return httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        trust_env=False,
        follow_redirects=False,
    )


class HermesApprovalMcpClient:
    """세 결재함 게이트(제목 선택·대본 확정·업로드 승인)에 pending 항목을 넣는다."""

    def __init__(
        self,
        *,
        base_url: str,
        http_client_factory: Callable = _default_http_client_factory,
        timeout_seconds: float = _TIMEOUT_SECONDS_DEFAULT,
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in _ALLOWED_HOSTS
            or parsed.port != 19680
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("hermes_approval_url_must_be_internal")
        self._base_url = base_url.rstrip("/")
        self._http_factory = http_client_factory
        self._timeout = timeout_seconds

    async def submit_title_candidates(
        self,
        *,
        project_id: str,
        cycle_id: str,
        title_candidates: list[dict[str, Any]],
        question: str,
        target: str,
    ) -> dict[str, Any]:
        return await self._call_tool(
            "submit_title_candidates",
            {
                "project_id": project_id,
                "cycle_id": cycle_id,
                "title_candidates": title_candidates,
                "question": question,
                "target": target,
            },
        )

    async def submit_script_confirmation(
        self,
        *,
        project_id: str,
        cycle_id: str,
        script_candidates: list[dict[str, Any]],
        question: str,
        target: str,
    ) -> dict[str, Any]:
        return await self._call_tool(
            "submit_script_confirmation",
            {
                "project_id": project_id,
                "cycle_id": cycle_id,
                "script_candidates": script_candidates,
                "question": question,
                "target": target,
            },
        )

    async def submit_upload_request(
        self,
        *,
        project_id: str,
        cycle_id: str,
        upload_target: str,
        upload_scheduled_summary_ko: str,
        question: str,
        target: str,
    ) -> dict[str, Any]:
        return await self._call_tool(
            "submit_upload_request",
            {
                "project_id": project_id,
                "cycle_id": cycle_id,
                "upload_target": upload_target,
                "upload_scheduled_summary_ko": upload_scheduled_summary_ko,
                "question": question,
                "target": target,
            },
        )

    async def _call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        request_id = next(_id_counter)
        try:
            async with self._http_factory(
                base_url=self._base_url, timeout=self._timeout
            ) as http:
                response = await http.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "method": "tools/call",
                        "params": {"name": name, "arguments": arguments},
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as error:
            raise HermesApprovalQueueError(
                "hermes_approval_queue_unavailable"
            ) from error
        if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
            raise HermesApprovalQueueError("hermes_approval_queue_invalid_response")
        if "error" in payload:
            raise HermesApprovalQueueError("hermes_approval_queue_rejected")
        result = payload.get("result")
        if not isinstance(result, dict) or result.get("isError"):
            raise HermesApprovalQueueError("hermes_approval_queue_rejected")
        structured = result.get("structuredContent")
        return structured if isinstance(structured, dict) else {}
