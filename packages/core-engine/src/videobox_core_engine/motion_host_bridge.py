"""컨테이너 안에서 **이 컴퓨터의 모션 다리**(`scripts/host_motion_service.py`, 8202)를 부른다.

인포그래픽 다리(8201)의 부분 이식이다 -- 주소 검사·리다이렉트 금지·토큰 헤더는 같고,
영상 바이트를 base64로 받는다는 것과 거절 이유(`error`)를 이름째 올린다는 것이 다르다.

## 나가는 곳은 이 컴퓨터뿐이다

정해진 호스트·정해진 포트·경로 없음·리다이렉트 금지. 요청 직전에 다시 확인한다.
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

from videobox_provider_interfaces.host_bridge_auth import bridge_request_headers

#: 이 컴퓨터 안에서만 부른다. 컨테이너에서는 `host.docker.internal`이 호스트다.
_ALLOWED_HOSTS = frozenset({"127.0.0.1", "host.docker.internal"})
#: 인포그래픽(8201) 옆자리.
BRIDGE_PORT = 8202
#: 비면 다리를 안 쓴다(기능이 꺼진 것). compose가 채운다.
ENVIRONMENT_VARIABLE = "VIDEOBOX_MOTION_BRIDGE_URL"
#: 다리 상한 180초 + 여유. nginx 600초 안이다.
BRIDGE_TIMEOUT_SECONDS = 240


class MotionHostBridgeUnavailable(RuntimeError):
    """다리가 안 켜져 있거나 대답하지 않는다."""


class MotionHostBridgeTimedOut(RuntimeError):
    """다리가 제 시간에 대답하지 않았다."""


class MotionHostBridgeRefused(RuntimeError):
    """다리가 대답했지만 요청을 거절했다. `error`는 다리가 단 이유 이름이다."""

    def __init__(self, status: int, error: str, detail: str = "") -> None:
        super().__init__(f"Motion bridge refused ({status}): {error} {detail}".strip())
        self.status = status
        self.error = error
        self.detail = detail


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise HTTPError(req.full_url, code, "motion bridge redirects are forbidden", headers, fp)


@dataclass
class MotionClip:
    video_bytes: bytes
    format: str
    elapsed_sec: float


@dataclass(slots=True)
class MotionHostBridge:
    base_url: str = f"http://127.0.0.1:{BRIDGE_PORT}"
    timeout_seconds: int = BRIDGE_TIMEOUT_SECONDS
    http_client: Callable[..., Any] | None = None

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> "MotionHostBridge | None":
        source = environment if environment is not None else os.environ
        base_url = (source.get(ENVIRONMENT_VARIABLE) or "").strip()
        return cls(base_url=base_url) if base_url else None

    def _endpoint(self, path: str) -> str:
        """요청 직전에 다시 확인한다 -- 시작할 때 통과한 것과 이 요청이 거기로 간다는 것은 다른 말이다."""

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
            raise MotionHostBridgeRefused(
                0,
                "bridge_address_not_allowed",
                f"Motion bridge must be http://127.0.0.1:{BRIDGE_PORT}, or "
                f"http://host.docker.internal:{BRIDGE_PORT} in the container.",
            )
        return f"{self.base_url}{path}"

    def diagnose(self) -> dict[str, Any]:
        return self._request("GET", "/diagnostics", None)

    def render(self, *, template: str, variables: dict[str, Any], duration_sec: float, layout: str) -> MotionClip:
        """영상이 없거나 못 읽거나 종류가 틀리면 **거절로 다룬다** -- 빈 바이트를 돌려주면
        부르는 쪽이 성공으로 착각한다."""

        reply = self._request(
            "POST",
            "/render",
            {"template": template, "variables": variables, "duration_sec": duration_sec, "layout": layout},
        )
        encoded = reply.get("video_base64")
        fmt = reply.get("format")
        if not isinstance(encoded, str) or not encoded or fmt not in ("mp4", "webm"):
            raise MotionHostBridgeRefused(200, "no_video")
        try:
            video = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise MotionHostBridgeRefused(200, "no_video") from exc
        if not video:
            raise MotionHostBridgeRefused(200, "no_video")
        return MotionClip(video_bytes=video, format=fmt, elapsed_sec=float(reply.get("elapsed_sec") or 0.0))

    def _request(self, method: str, path: str, payload: dict[str, Any] | None) -> dict[str, Any]:
        http_request = Request(
            self._endpoint(path),
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            # 다리는 공유 토큰이 없으면 401로 거절한다(`scripts/host_bridge_guard.py`).
            headers=bridge_request_headers(),
            method=method,
        )
        try:
            if self.http_client is not None:
                body = self.http_client(http_request, timeout=self.timeout_seconds)
            else:
                with build_opener(_NoRedirect).open(http_request, timeout=self.timeout_seconds) as response:
                    body = response.read()
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace") if exc.fp else ""
            error = ""
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    error = str(parsed.get("error") or "")
            except ValueError:
                pass
            raise MotionHostBridgeRefused(exc.code, error, raw[:300]) from exc
        except TimeoutError as exc:
            raise MotionHostBridgeTimedOut(f"Motion bridge did not answer in time: {exc}") from exc
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise MotionHostBridgeTimedOut(f"Motion bridge did not answer in time: {exc}") from exc
            raise MotionHostBridgeUnavailable(f"Motion bridge is not answering: {exc}") from exc
        except OSError as exc:
            raise MotionHostBridgeUnavailable(f"Motion bridge is not answering: {exc}") from exc
        try:
            decoded = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
        except (ValueError, AttributeError) as exc:
            raise MotionHostBridgeRefused(200, "unreadable_reply") from exc
        if not isinstance(decoded, dict):
            raise MotionHostBridgeRefused(200, "unreadable_reply")
        return decoded


__all__ = [
    "BRIDGE_PORT",
    "BRIDGE_TIMEOUT_SECONDS",
    "ENVIRONMENT_VARIABLE",
    "MotionClip",
    "MotionHostBridge",
    "MotionHostBridgeRefused",
    "MotionHostBridgeTimedOut",
    "MotionHostBridgeUnavailable",
]
