"""API 경계에서 주체를 받는 통로.

라우터가 `Depends(get_principal)`로 이걸 받는다. 지금은 고정된 1인 로컬
owner를 돌려줄 뿐이라 동작이 바뀌지 않는다 -- 인증 헤더도, 쿠키도, 토큰도
읽지 않는다(`CLAUDE.md` §6이 다중 사용자 인증을 owner 승인 대상으로 둔다).

나중에 로그인이 생기면 **여기 한 곳**이 요청에서 주체를 꺼내게 된다. 라우터는
이미 주체를 받고 있으므로 그때 라우터를 고칠 필요가 없다.

이 함수는 요청 인자를 하나도 선언하지 않는다. 선언하면 FastAPI가 공개
스키마에 쿼리 파라미터를 새로 만들고, 그건 기존 클라이언트가 보는 계약이
바뀌는 것이다.
"""

from __future__ import annotations

from videobox_domain_models.principal import Principal, resolve_principal


def get_principal() -> Principal:
    return resolve_principal()
