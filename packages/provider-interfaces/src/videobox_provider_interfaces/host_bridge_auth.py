"""컨테이너에서 이 컴퓨터의 다리 셋(목소리 8199·캡컷 8200·그림 8201)을 부를 때 붙이는 헤더.

받는 쪽 문지기는 `scripts/host_bridge_guard.py`다(2026-10-02, owner 결정 "공유 토큰까지").
두 곳의 이름(헤더·환경 변수)은 같아야 하고, `tests/test_host_bridge_guard.py`가 대조한다.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

TOKEN_HEADER = "X-VideoBox-Bridge-Token"
TOKEN_ENV = "VIDEOBOX_BRIDGE_TOKEN"


def bridge_request_headers(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """JSON 헤더에, 토큰이 있으면 토큰 헤더를 더한다.

    토큰이 없으면 **지어내지 않는다.** 다리가 401로 거절하고 그 사유가 그대로 올라간다.
    조용히 넘어가면 무엇을 고쳐야 하는지 아무도 모른다.
    """

    source = os.environ if environ is None else environ
    headers = {"Content-Type": "application/json"}
    token = str(source.get(TOKEN_ENV) or "").strip()
    if token:
        headers[TOKEN_HEADER] = token
    return headers


__all__ = ["TOKEN_ENV", "TOKEN_HEADER", "bridge_request_headers"]
