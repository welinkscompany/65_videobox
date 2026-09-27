"""services/mcp/src/videobox_mcp/auth.py 시험 -- Bearer 인증 미들웨어만 확인한다.

MCP 프로토콜 핸드셰이크(session 초기화 등)는 여기서 시험하지 않는다 --
그건 `test_mcp_http_transport.py`(Task 5)의 몫이다. 여기서는 미들웨어가
토큰 없음/틀림에서 401을 내고, 맞으면 다음 앱으로 넘기는지만 본다.
"""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from videobox_mcp.auth import BearerAuthMiddleware


def _app_with_auth(token: str) -> Starlette:
    async def ok(_request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/probe", ok, methods=["GET"])])
    app.add_middleware(BearerAuthMiddleware, token=token)
    return app


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong-token"},
        {"Authorization": "secret-token"},  # "Bearer " 접두 없음
    ],
)
def test_missing_or_wrong_token_is_rejected(headers: dict[str, str]) -> None:
    app = _app_with_auth("secret-token")
    client = TestClient(app)
    response = client.get("/probe", headers=headers)

    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}


def test_correct_token_passes_through() -> None:
    app = _app_with_auth("secret-token")
    client = TestClient(app)
    response = client.get("/probe", headers={"Authorization": "Bearer secret-token"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
