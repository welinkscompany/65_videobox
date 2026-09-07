"""지금 작업하는 **주체가 누구인가**를 답하는 단 하나의 자리.

VideoBox는 owner 1인용 로컬 제품이다. 결제·구독·다중 사용자 인증은 만들지
않는다(`CLAUDE.md` §6, `docs/decisions/2026-09-04-capcut-shell-with-my-assets.ko.md` §3).
이 파일은 그 기능이 아니라 **이음매**다.

왜 지금 만드는가: 소유자 개념이 없으면 "누구의 프로젝트인가"를 나중에 붙일 때
프로젝트·자산·세션·잡을 읽는 자리마다 따로 답을 만들게 된다. 답이 여러 벌이면
서로 어긋난다 — 이 저장소에서 이미 겪은 실패다(같은 지침을 두 벌 두었다가
어긋난 일, 루트 `CLAUDE.md`). 그래서 지금 1인일 때 **읽는 자리를 하나로**
고정해 둔다.

이 파일이 하지 않는 것: 로그인·세션·토큰·비밀번호·요금제 확인. 지금 이 함수는
설정에서 값을 읽어 고정된 주체 하나를 만들어 돌려줄 뿐이고, 설정이 없으면
지금까지의 동작과 100% 같다.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


# 1인 로컬 owner의 고정 식별자. 저장 경로에 쓰지 않는다 -- `ProjectRecord`의
# `root_storage_uri`는 이미 `local://projects/{id}` 형태로 위치를 추상화하고
# 있고, 거기에 소유자를 끼워 넣으면 기존 프로젝트 폴더가 전부 미아가 된다.
DEFAULT_OWNER_ID = "local-owner"

# 요금제 자리. 지금은 이 한 값뿐이고 아무것도 막지 않는다. 구독이 생기면
# `entitlements.can`이 이 값을 보게 된다.
DEFAULT_PLAN = "local"

OWNER_ID_ENV_VAR = "VIDEOBOX_OWNER_ID"
PLAN_ENV_VAR = "VIDEOBOX_OWNER_PLAN"


@dataclass(slots=True, frozen=True)
class Principal:
    """지금 요청을 일으킨 주체.

    frozen인 이유: 한 요청 안에서 주체가 바뀌면 앞뒤 권한 판단이 달라진다.
    바꿔야 한다면 새로 만들어 전달한다.
    """

    owner_id: str
    plan: str


def _read(env: Mapping[str, str], name: str, fallback: str) -> str:
    # 빈 문자열은 "설정 안 함"으로 본다. `.env.container`에 이름만 있고 값이
    # 비어 있던 줄이 실제로 있었고, 그걸 그대로 통과시키면 owner_id가 빈 키가
    # 된다(`videobox-mem0-approved-but-off`).
    value = (env.get(name) or "").strip()
    return value or fallback


def resolve_principal(*, env: Mapping[str, str] | None = None) -> Principal:
    """지금 주체를 돌려준다.

    `env`를 주지 않으면 프로세스 환경을 읽는다. 설정이 비어 있으면 고정된
    1인 로컬 owner다 -- 즉 기본값에서는 이 함수를 붙이기 전과 동작이 같다.
    """

    resolved_env = os.environ if env is None else env
    return Principal(
        owner_id=_read(resolved_env, OWNER_ID_ENV_VAR, DEFAULT_OWNER_ID),
        plan=_read(resolved_env, PLAN_ENV_VAR, DEFAULT_PLAN),
    )
