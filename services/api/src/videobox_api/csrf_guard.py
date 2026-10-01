"""승인 문 다섯 개에 최소 CSRF 방어를 둔다.

2026-09-07 전체 점검 §1-7: principal(사람이 눌렀다는 증명) 검사가 사실상 없고
CORS 미들웨어도 없어, `127.0.0.1:5173`에 닿는 로컬 프로세스라면 무엇이든
검토 승인·촬영본 승인·기억 승인 저장·제안 적용을 사람 대신 누를 수 있었다.
owner가 악성 웹페이지를 열어 두면 그 페이지의 크로스오리진 POST가 CSRF로
같은 일을 할 수 있다.

정식 인증 시스템(SaaS·다중 사용자 인증, `CLAUDE.md` §6)이 아니라 그 앞의
값싼 방어 한 겹이다. `Origin` 헤더는 브라우저가 스스로 붙이고 페이지의 JS가
덮어쓸 수 없으므로, 그 값이 있는데 우리 화면이 아니면 확실히 다른 사이트에서
왔다는 뜻이다.

**Origin 헤더가 아예 없는 요청은 통과시킨다.** curl·스모크 스크립트·MCP 도구·
`owner_sample_edit_package.py` 같은 브라우저 밖 호출자는 전부 이 모양이고,
악성 웹페이지의 크로스오리진 POST는 브라우저가 반드시 Origin을 붙이므로 이
길로는 들어오지 못한다. 1인 로컬 제품이라 principal 자체를 증명하지는
못한다 -- §1-7의 나머지(정식 인증)는 owner 결정 대기다.
"""

from __future__ import annotations

import os

from fastapi import HTTPException, Request, status
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

#: 개발 서버·컨테이너가 화면을 내주는 자리(`docker/workspace-nginx.conf`).
#: Tauri 셸이 다른 origin(예: `tauri://`)으로 뜨게 되면 여기 추가해야 한다.
#: 5199는 로컬 dev 서버(`.claude/launch.json`)다 -- 컨테이너 웹(5173)과 일부러
#: 다른 포트를 쓴다. 둘을 같은 포트로 두면 로컬 파일 저장소와 컨테이너
#: Postgres 저장소가 섞여 보이는 사고가 재현된다(2026-08-08,
#: `development-fast-path.ko.md` "데이터 폴더가 두 벌이다" 절) -- 그래서 포트를
#: 합치는 대신 이 화이트리스트에 5199를 추가한다(2026-09-24, W1015 업로드
#: 승인 요청 실물 검증 중 5199에서 검토 승인이 조용히 403으로 막히는 걸 발견).
TRUSTED_ORIGINS = frozenset(
    {
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5199",
        "http://localhost:5199",
    }
)


def require_trusted_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin is not None and origin not in TRUSTED_ORIGINS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"reason": "untrusted_origin"},
        )


#: 2026-10-01 보안 점검 H1: DNS 리바인딩 방어. 공격자 도메인을 127.0.0.1로
#: 다시 풀게 하면 브라우저는 그 페이지를 같은 출처로 보지만, `Host` 헤더에는
#: 여전히 공격자 도메인이 실린다. 그래서 Host가 아래 이름이 아니면 거절한다.
#: `host.docker.internal`은 도커 안 호출자(MCP 등)가 쓰는 이름이고 공격자가
#: 브라우저에 그 이름을 쓰게 할 방법이 없다. `testserver`는 TestClient 기본값.
#: 다른 이름이 필요하면 `VIDEOBOX_ALLOWED_HOSTS`(쉼표 구분)로 더한다.
DEFAULT_ALLOWED_HOSTS = (
    "127.0.0.1",
    "localhost",
    "[::1]",
    "::1",
    "host.docker.internal",
    "testserver",
)


def allowed_hosts_from_environment() -> list[str]:
    extra = [
        item.strip()
        for item in os.environ.get("VIDEOBOX_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    ]
    return [*DEFAULT_ALLOWED_HOSTS, *extra]


_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class TrustedOriginMiddleware:
    """상태를 바꾸는 **모든** 요청에 `require_trusted_origin`과 같은 규칙을 건다.

    승인 문 넷에만 붙어 있던 검사를 전역으로 올린다(2026-10-01 보안 점검 H1·M1:
    쓰기 라우트 약 185개 중 나머지는 크로스오리진 POST·DELETE를 그대로 받았다).
    Origin이 없는 요청은 지금처럼 통과한다.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("method", "GET") not in _SAFE_METHODS:
            origin = None
            for key, value in scope.get("headers", ()):
                if key == b"origin":
                    origin = value.decode("latin-1")
                    break
            if origin is not None and origin not in TRUSTED_ORIGINS:
                response = JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": {"reason": "untrusted_origin"}},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


__all__ = [
    "DEFAULT_ALLOWED_HOSTS",
    "TRUSTED_ORIGINS",
    "TrustedOriginMiddleware",
    "allowed_hosts_from_environment",
    "require_trusted_origin",
]
