"""HTTP 전송 전용 Bearer 토큰 인증.

stdio 전송(로컬 프로세스 직접 실행)에는 안 건다 -- 호출자가 이미 같은
기계의 같은 사용자다. HTTP 전송만 밖에서 닿을 수 있으므로 여기만 잠근다.
`hmac.compare_digest`로 비교해 타이밍 공격을 막는다(openmic 패턴 준용,
`docs/superpowers/specs/2026-09-27-mcp-http-endpoint-for-ak-hermes-design.ko.md` §5).
"""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, token: str) -> None:
        super().__init__(app)
        self._expected = f"Bearer {token}"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        header = request.headers.get("authorization", "")
        if not hmac.compare_digest(header, self._expected):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)
