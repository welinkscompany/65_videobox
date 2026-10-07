"""호스트 다리 셋(목소리 8199·캡컷 8200·그림 8201)이 같이 쓰는 문지기 (2026-10-02).

2026-10-01 보안 점검: 세 다리는 127.0.0.1에만 묶여 있지만 **이 컴퓨터의 아무
프로세스나, 브라우저의 아무 웹페이지나** 부를 수 있었다(text/plain POST는 CORS
사전 확인 없이 나간다). owner 결정(2026-10-02)은 "공유 토큰까지"다.

세 가지를 이 차례로 본다.

1. **Host**: `127.0.0.1:<포트>`·`localhost:<포트>`·`host.docker.internal:<포트>`만 받는다.
   DNS 리바인딩으로 들어온 요청은 Host에 남의 이름이 실린다.
2. **토큰**: `X-VideoBox-Bridge-Token`이 `VIDEOBOX_BRIDGE_TOKEN`과 같아야 한다. 웹페이지가
   이 헤더를 붙이면 사전 확인(OPTIONS)을 먼저 보내는데, 다리는 그것에 답하지 않는다.
   비교는 `hmac.compare_digest`로 한다.
3. **JSON만**: POST는 `application/json`만 받고, 아니면 415를 낸다.

표준 라이브러리만 쓴다. 목소리 다리는 chatterbox 전용 파이썬(`.venv-chatterbox`)에서 돈다.
판단(`check_request`)은 소켓과 떼어 두었다. 시험이 연결을 못 열기 때문이다.

토큰은 `.env.container`의 한 줄이다. `scripts/owner-ready.ps1 -Mode Start`가 없을 때만
만들고, compose가 컨테이너에 넘기며(`compose.yaml`), 다리는 같은 파일을 여기서 직접 읽는다.
부르는 쪽 헤더는 `videobox_provider_interfaces.host_bridge_auth`가 만든다. 두 곳의 이름은
`tests/test_host_bridge_guard.py`가 대조한다.
"""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from pathlib import Path
from typing import Any

TOKEN_HEADER = "X-VideoBox-Bridge-Token"
TOKEN_ENV = "VIDEOBOX_BRIDGE_TOKEN"
#: `owner-ready.ps1`은 32바이트를 base64url로 적는다(43자). 사람이 손으로 넣은 짧은 값은 받지 않는다.
MINIMUM_TOKEN_LENGTH = 32
_ALLOWED_HOST_NAMES = ("127.0.0.1", "localhost", "host.docker.internal")


class BridgeTokenMissing(RuntimeError):
    """토큰이 없거나 너무 짧다. 다리는 이때 뜨지 않는다. 아무나 받는 것보다 안 뜨는 편이 안전하다."""


def read_env_file_value(env_file: Path, name: str) -> str:
    """`.env.container`에서 `name=` 한 줄의 값을 읽는다. BOM·CRLF·따옴표를 견딘다. 없으면 `""`."""

    try:
        text = Path(env_file).read_text(encoding="utf-8-sig")
    except OSError:
        return ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip() == name:
            return value.strip().strip('"').strip("'").strip()
    return ""


def load_bridge_token(environ: Mapping[str, str], env_file: Path) -> str:
    token = str(environ.get(TOKEN_ENV) or "").strip() or read_env_file_value(env_file, TOKEN_ENV)
    if len(token) < MINIMUM_TOKEN_LENGTH:
        raise BridgeTokenMissing(
            f"{TOKEN_ENV}가 없거나 너무 짧습니다({MINIMUM_TOKEN_LENGTH}자 이상 필요). "
            "PowerShell에서 .\\scripts\\owner-ready.ps1 -Mode Start 를 한 번 실행하면 "
            ".env.container에 만들어집니다."
        )
    return token


def check_request(
    *,
    method: str,
    headers: Any,
    port: int,
    expected_token: str,
    require_token: bool = True,
) -> tuple[int, dict[str, object]] | None:
    """막아야 하면 `(상태 코드, 답)`을, 통과면 `None`을 돌려준다.

    `headers`는 `.get(name)`이 되는 것이면 된다. 다리에서는 `self.headers`
    (`http.client.HTTPMessage`)를 넘기고, 그쪽은 이름의 대소문자를 가리지 않는다.
    """

    host = str(headers.get("Host") or "").strip().lower()
    if host not in {f"{name}:{port}" for name in _ALLOWED_HOST_NAMES}:
        return 400, {"error": "host_not_allowed"}
    if require_token:
        if not expected_token:
            return 503, {"error": "bridge_token_not_configured"}
        supplied = str(headers.get(TOKEN_HEADER) or "")
        if not hmac.compare_digest(supplied.encode("utf-8"), expected_token.encode("utf-8")):
            return 401, {"error": "bridge_token_required"}
    if method.upper() == "POST":
        content_type = str(headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return 415, {"error": "json_required"}
    return None


__all__ = [
    "MINIMUM_TOKEN_LENGTH",
    "TOKEN_ENV",
    "TOKEN_HEADER",
    "BridgeTokenMissing",
    "check_request",
    "load_bridge_token",
    "read_env_file_value",
]
