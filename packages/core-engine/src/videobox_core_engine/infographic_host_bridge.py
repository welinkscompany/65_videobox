"""컨테이너 안에서 **이 컴퓨터의 크롬**에게 그림을 그려 달라고 부르는 다리.

컨테이너에는 브라우저가 없다. 목소리 복제(8199)·캡컷(8200)과 같은 방식으로 이
컴퓨터에서 도는 작은 서비스(`scripts/host_infographic_service.py`)를 부른다.
인포그래픽은 **8201**이다(`docs/development-fast-path.ko.md` §10.14 조항 2-C와
같은 규칙).

## 그림은 내용으로 받는다

캡컷 다리는 호스트 경로를 주고받지만 여기는 PNG 바이트를 그대로 받는다. 한 장이
크지 않고(보통 40KB~2MB), 그러면 호스트에 아무것도 남지 않는다.

## 나가는 곳은 이 컴퓨터뿐이다

주소 검사는 캡컷 다리와 같다 -- 정해진 호스트·정해진 포트·경로 없음·리다이렉트
금지. 요청 직전에 다시 확인한다.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

#: 이 컴퓨터 안에서만 부른다. 컨테이너에서는 `host.docker.internal`이 호스트다.
_ALLOWED_HOSTS = frozenset({"127.0.0.1", "host.docker.internal"})
#: 캡컷(8200) 옆자리. 바꾸려면 여기와 compose와 `scripts/start-infographic.ps1`을 같이 바꾼다.
BRIDGE_PORT = 8201
#: 다리를 어디로 부를지. compose가 채운다. 비면 다리를 안 쓴다(기능이 꺼진 것).
ENVIRONMENT_VARIABLE = "VIDEOBOX_INFOGRAPHIC_BRIDGE_URL"


class InfographicHostBridgeUnavailable(RuntimeError):
    """다리가 안 켜져 있거나 대답하지 않는다."""


class InfographicHostBridgeRefused(RuntimeError):
    """다리는 대답했지만 요청을 거절했다."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise HTTPError(req.full_url, code, "infographic bridge redirects are forbidden", headers, fp)


@dataclass(slots=True)
class InfographicHostBridge:
    """이 컴퓨터에서 도는 그림 다리(`scripts/host_infographic_service.py`)를 부른다."""

    base_url: str = f"http://127.0.0.1:{BRIDGE_PORT}"
    timeout_seconds: int = 120
    http_client: Callable[..., Any] | None = None

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "InfographicHostBridge | None":
        source = environment if environment is not None else os.environ
        base_url = (source.get(ENVIRONMENT_VARIABLE) or "").strip()
        if not base_url:
            return None
        return cls(base_url=base_url)

    def _endpoint(self, path: str) -> str:
        """요청 직전에 다시 확인한다 -- 시작할 때 통과한 것과 이 요청이 거기로
        간다는 것은 다른 말이다(캡컷·목소리 다리와 같은 이유)."""

        parsed = urlparse(self.base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in _ALLOWED_HOSTS
            or parsed.port != BRIDGE_PORT
            or parsed.path
            or parsed.params
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise InfographicHostBridgeRefused(
                f"Infographic bridge must be http://127.0.0.1:{BRIDGE_PORT}, or "
                f"http://host.docker.internal:{BRIDGE_PORT} in the container."
            )
        return f"{self.base_url}{path}"

    def diagnose(self) -> dict[str, Any]:
        return self._request("GET", "/diagnostics", None)

    def render(self, *, html: str, width: int = 1920, height: int = 1080) -> bytes:
        """HTML을 PNG 바이트로. 다리가 그림을 안 주면 **거절로 다룬다** --
        빈 바이트를 돌려주면 부르는 쪽이 성공으로 착각한다."""

        reply = self._request(
            "POST", "/render", {"html": html, "width": width, "height": height}
        )
        encoded = reply.get("png_base64")
        if not isinstance(encoded, str) or not encoded:
            raise InfographicHostBridgeRefused("Infographic bridge returned no picture.")
        try:
            png = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise InfographicHostBridgeRefused(
                "Infographic bridge returned a picture we could not read."
            ) from exc
        if not png:
            raise InfographicHostBridgeRefused("Infographic bridge returned an empty picture.")
        return png

    def measure(self, *, html: str, width: int = 1920, height: int = 1080) -> str:
        """페이지를 브라우저에 올려 놓고 **다 놓인 뒤의 `<title>`**을 받는다.
        재기 코드가 잰 값을 거기에 적어 둔다(`infographic_layout_audit`)."""

        reply = self._request(
            "POST", "/measure", {"html": html, "width": width, "height": height}
        )
        title = reply.get("title")
        if not isinstance(title, str):
            raise InfographicHostBridgeRefused("Infographic bridge returned no measurement.")
        return title

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None
    ) -> dict[str, Any]:
        http_request = Request(
            self._endpoint(path),
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            if self.http_client is not None:
                body = self.http_client(http_request, timeout=self.timeout_seconds)
            else:
                with build_opener(_NoRedirect).open(
                    http_request, timeout=self.timeout_seconds
                ) as response:
                    body = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300] if exc.fp else ""
            # 다리는 살아 있는데 요청을 거절한 것이다 -- "켜 주세요"라고 말하면 거짓말이 된다.
            raise InfographicHostBridgeRefused(
                f"Infographic bridge refused ({exc.code}): {detail}"
            ) from exc
        except (URLError, OSError) as exc:
            raise InfographicHostBridgeUnavailable(
                f"Infographic bridge is not answering: {exc}"
            ) from exc
        try:
            decoded = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
        except (ValueError, AttributeError) as exc:
            raise InfographicHostBridgeRefused(
                "Infographic bridge returned a reply we could not read."
            ) from exc
        if not isinstance(decoded, dict):
            raise InfographicHostBridgeRefused("Infographic bridge returned an unexpected reply.")
        return decoded


__all__ = [
    "BRIDGE_PORT",
    "ENVIRONMENT_VARIABLE",
    "InfographicHostBridge",
    "InfographicHostBridgeRefused",
    "InfographicHostBridgeUnavailable",
]
