"""Hermes egress 허용목록 판정 -- 순수 로직, 소켓 없음.

`docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md` §2
Phase 1. **실제 호스트 이름 목록은 아직 안 정해졌다** — owner가 실제 로그인을
관찰 모드로 한 번 돌려 본 뒤 확정하기로 했다(§2 결정 2). 그래서 목록은
`allowlist_entries`로 주입만 하고, 여기서는 판정 로직만 굳힌다 — 나중에
진짜 목록이 정해지면 `config/hermes/egress_allowlist.json` 같은 파일에서
읽어와 이 함수에 넘기기만 하면 된다.

**scope로 나눈다** — `oauth_bootstrap`(로그인 한 번뿐)과
`provider_runtime`(매 대화 호출)은 필요한 호스트가 다를 수 있다. 한쪽
목록을 다른 쪽에 잘못 적용하면 허용 범위가 조용히 넓어진다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

EgressScope = Literal["oauth_bootstrap", "provider_runtime"]


@dataclass(frozen=True, slots=True)
class EgressAllowlist:
    """scope별 허용 호스트 이름 집합. 이름은 전부 소문자·정규화된 것으로 저장한다."""

    entries: dict[EgressScope, frozenset[str]] = field(default_factory=dict)

    def is_allowed(self, *, scope: EgressScope, hostname: str) -> bool:
        normalized = _normalize_hostname(hostname)
        if normalized is None:
            return False
        allowed = self.entries.get(scope, frozenset())
        for entry in allowed:
            if normalized == entry or normalized.endswith("." + entry):
                return True
        return False


def _normalize_hostname(hostname: object) -> str | None:
    """호스트 이름 하나를 소문자 ASCII로 정규화한다. 이상하면 `None`(거부)."""
    if not isinstance(hostname, str) or not hostname:
        return None
    stripped = hostname.strip()
    if not stripped or stripped != hostname:
        # 앞뒤 공백이 섞인 입력은 애초에 파싱이 잘못된 것으로 본다 --
        # 조용히 trim해서 통과시키지 않는다.
        return None
    try:
        ascii_only = stripped.encode("ascii").decode("ascii")
    except UnicodeEncodeError:
        # 비ASCII·유니코드 lookalike(동형 문자) 방어 -- 정규화해서
        # 통과시키지 않고 그냥 거부한다.
        return None
    lowered = ascii_only.lower()
    if not lowered or lowered.startswith(".") or lowered.endswith("."):
        return None
    if any(character.isspace() for character in lowered):
        return None
    return lowered
