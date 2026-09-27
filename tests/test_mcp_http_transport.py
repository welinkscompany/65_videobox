"""HTTP 전송 배선 시험. MCP 프로토콜 핸드셰이크가 아니라 인증 게이트가
실제로 이 전송에도 걸려 있는지만 확인한다(Task 4는 미들웨어 단독,
여기는 실제 MCPServer.streamable_http_app과 합쳐졌을 때).
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from videobox_mcp.api_client import VideoBoxApiClient
from videobox_mcp.server import build_http_app


def _http_app(tmp_path: Path, token: str):
    from videobox_api.main import create_app

    app = create_app(projects_root=tmp_path)
    transport = httpx.ASGITransport(app=app)
    client = VideoBoxApiClient(base_url="http://testserver", transport=transport)
    return build_http_app(client, token=token, host="127.0.0.1")


def test_http_transport_rejects_missing_token(tmp_path: Path) -> None:
    """기존 `test_mcp_server.py`와 같은 스타일 -- 이 저장소는 async 시험에
    pytest-asyncio/anyio 마커를 쓰지 않고 `asyncio.run()`으로 감싼다.
    새 설정을 추가하지 않는다(YAGNI, 기존 관례 재사용)."""
    import asyncio

    app = _http_app(tmp_path, token="secret-token")
    transport = httpx.ASGITransport(app=app)

    async def run() -> httpx.Response:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8901") as client:
                return await client.post(
                    "/mcp",
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    headers={"Accept": "application/json, text/event-stream"},
                )

    response = asyncio.run(run())

    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}


def test_http_transport_accepts_correct_token_past_auth_layer(tmp_path: Path) -> None:
    import asyncio

    app = _http_app(tmp_path, token="secret-token")
    transport = httpx.ASGITransport(app=app)

    async def run() -> httpx.Response:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8901") as client:
                return await client.post(
                    "/mcp",
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    headers={
                        "Authorization": "Bearer secret-token",
                        "Accept": "application/json, text/event-stream",
                    },
                )

    response = asyncio.run(run())

    # 인증은 통과했다 -- MCP 세션 초기화 핸드셰이크를 안 거쳤다는 별개의
    # 프로토콜 오류(400)가 나온다. 401이 아니라는 것 자체가 이 시험의 증거다.
    assert response.status_code != 401
