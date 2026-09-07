"""컨테이너 안에서 **이 컴퓨터의 캡컷 폴더**를 다루는 다리를 부른다.

## 왜 다리인가

캡컷 초안이 실제로 들어가야 하는 곳은
`C:/Users/<사람>/AppData/Local/CapCut/User Data/Projects/com.lveditor.draft`다.
**컨테이너는 그 폴더를 못 본다.** 연결해 줄 수도 있지만 그건 owner의 실제 캡컷
자료를 통째로 컨테이너에 붙이는 일이라, 초안 하나 넘기려고 치르기엔 비싸다.

그래서 목소리 복제(`host_tts_bridge_provider`, 8199)·그림 생성(ComfyUI, 8188)과
**같은 방식**을 쓴다: 이 컴퓨터에서 도는 작은 서비스를 부른다. 캡컷은 **8200**이다
(`docs/development-fast-path.ko.md` §10.14 조항 2-C와 같은 규칙).

## 초안은 경로로 보낸다 (목소리와 다른 점)

목소리 다리는 샘플 오디오를 **내용으로** 실어 보낸다. 컨테이너와 호스트가 같은
경로를 안 보기 때문이다. 캡컷은 사정이 다르다 -- 초안이 놓인 `/videobox-data`는
이 컴퓨터의 폴더를 그대로 연결한 것이라 **같은 파일이 양쪽에 다 보인다.**
그래서 폴더를 통째로 실어 보내는 대신 `CapCutHostPathMap`으로 옮긴 **호스트
경로**를 보낸다. 대응이 안 되면 보내지 않고 정직하게 실패한다.

## 나가는 곳은 이 컴퓨터뿐이다

주소 검사는 목소리 다리와 같다 -- 정해진 호스트·정해진 포트·경로 없음·
리다이렉트 금지. 요청 직전에 다시 확인한다.
"""

from __future__ import annotations

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
#: 목소리(8199) 옆자리. 바꾸려면 여기와 compose와 `scripts/start-capcut.ps1`을 같이 바꾼다.
BRIDGE_PORT = 8200
#: 다리를 어디로 부를지. compose가 채운다. 비면 다리를 안 쓴다(호스트 직접 실행).
ENVIRONMENT_VARIABLE = "VIDEOBOX_CAPCUT_BRIDGE_URL"


class CapCutHostBridgeUnavailable(RuntimeError):
    """다리가 안 켜져 있거나 대답하지 않는다."""


class CapCutHostBridgeRefused(RuntimeError):
    """다리는 대답했지만 요청을 거절했다."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise HTTPError(req.full_url, code, "capcut bridge redirects are forbidden", headers, fp)


@dataclass(slots=True)
class CapCutHostBridge:
    """이 컴퓨터에서 도는 캡컷 다리(`scripts/host_capcut_service.py`)를 부른다."""

    base_url: str = f"http://127.0.0.1:{BRIDGE_PORT}"
    timeout_seconds: int = 120
    http_client: Callable[..., Any] | None = None

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "CapCutHostBridge | None":
        source = environment if environment is not None else os.environ
        base_url = (source.get(ENVIRONMENT_VARIABLE) or "").strip()
        if not base_url:
            return None
        return cls(base_url=base_url)

    def _endpoint(self, path: str) -> str:
        """요청 직전에 다시 확인한다 -- 시작할 때 통과한 것과 이 요청이 거기로
        간다는 것은 다른 말이다(목소리 다리와 같은 이유)."""
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
            raise CapCutHostBridgeRefused(
                f"CapCut bridge must be http://127.0.0.1:{BRIDGE_PORT}, or "
                f"http://host.docker.internal:{BRIDGE_PORT} in the container."
            )
        return f"{self.base_url}{path}"

    def diagnose(self) -> dict[str, Any]:
        return self._request("GET", "/diagnostics", None)

    def register(
        self, *, draft_host_path: str, export_id: str, ownership_token: str | None = None
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/register",
            {
                "draft_host_path": draft_host_path,
                "export_id": export_id,
                "ownership_token": ownership_token,
            },
        )

    def cleanup(
        self,
        *,
        export_id: str,
        registered_host_path: str,
        ownership_token: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/cleanup",
            {
                "export_id": export_id,
                "registered_host_path": registered_host_path,
                "ownership_token": ownership_token,
            },
        )

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
            raise CapCutHostBridgeRefused(f"CapCut bridge refused ({exc.code}): {detail}") from exc
        except (URLError, OSError) as exc:
            raise CapCutHostBridgeUnavailable(f"CapCut bridge is not answering: {exc}") from exc
        try:
            decoded = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
        except (ValueError, AttributeError) as exc:
            raise CapCutHostBridgeRefused("CapCut bridge returned a reply we could not read.") from exc
        if not isinstance(decoded, dict):
            raise CapCutHostBridgeRefused("CapCut bridge returned an unexpected reply.")
        return decoded


__all__ = [
    "BRIDGE_PORT",
    "ENVIRONMENT_VARIABLE",
    "CapCutHostBridge",
    "CapCutHostBridgeRefused",
    "CapCutHostBridgeUnavailable",
]
