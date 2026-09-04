"""**이 주체가 이걸 해도 되는가**를 답하는 단 하나의 자리.

지금 답은 언제나 `True`다. VideoBox는 owner 1인용 로컬 제품이고 요금제가
없다(`CLAUDE.md` §6). 이 파일은 권한 기능이 아니라 **이음매**다.

무엇을 사는가: 나중에 구독 등급별로 무언가를 막을 때, 막는 판단이 화면·라우터·
서비스에 흩어지지 않고 이 함수 하나에서 난다. 지금 규칙을 미리 적어 두지 않는
이유는 그 규칙이 아직 승인되지 않았기 때문이다 -- 지어내면 나중에 owner가 정한
것과 어긋난다.

일부러 안 한 것: 능력 이름 목록(enum)을 만들지 않았다. 아무것도 막지 않는 지금
목록은 검증하는 것이 없으면서 새 기능마다 손봐야 하는 부담만 만든다. 실제로
막을 것이 정해질 때 그 목록도 같이 만든다.
"""

from __future__ import annotations

from videobox_domain_models.principal import Principal


def can(principal: Principal, capability: str) -> bool:
    """`principal`이 `capability`를 쓸 수 있는가.

    지금은 무조건 허용이다. 이 함수가 `False`를 돌려주기 시작하는 순간이
    곧 구독 기능의 시작이고, 그건 owner 명시 승인이 필요한 변경이다.
    """

    # 인자를 읽지 않는다는 사실 자체가 지금의 계약이다 -- 아무도 막히지 않는다.
    del principal, capability
    return True
