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

from fastapi import HTTPException, Request, status

#: 개발 서버·컨테이너가 화면을 내주는 자리(`docker/workspace-nginx.conf`).
#: Tauri 셸이 다른 origin(예: `tauri://`)으로 뜨게 되면 여기 추가해야 한다.
TRUSTED_ORIGINS = frozenset(
    {
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    }
)


def require_trusted_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin is not None and origin not in TRUSTED_ORIGINS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"reason": "untrusted_origin"},
        )


__all__ = ["TRUSTED_ORIGINS", "require_trusted_origin"]
