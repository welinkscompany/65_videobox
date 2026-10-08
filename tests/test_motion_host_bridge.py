"""컨테이너에서 이 컴퓨터의 모션 다리(8202)를 부르는 쪽."""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.error import HTTPError, URLError

import pytest

from videobox_core_engine.motion_host_bridge import (
    BRIDGE_PORT,
    BRIDGE_TIMEOUT_SECONDS,
    MotionHostBridge,
    MotionHostBridgeRefused,
    MotionHostBridgeTimedOut,
    MotionHostBridgeUnavailable,
)

_LOCAL = f"http://127.0.0.1:{BRIDGE_PORT}"
ORDER = {"template": "bar_compare", "variables": {"title": "t"}, "duration_sec": 6.0, "layout": "full"}


def _client(reply: dict[str, Any], *, seen: list | None = None):
    def client(request, timeout):  # noqa: ANN001
        if seen is not None:
            seen.append((request, timeout))
        return json.dumps(reply).encode("utf-8")
    return client


def _raising_client(error: BaseException):
    def client(request, timeout):  # noqa: ANN001, ARG001
        raise error
    return client


def _http_error(code: int, body: dict) -> HTTPError:
    import io
    return HTTPError(_LOCAL, code, "x", {}, io.BytesIO(json.dumps(body).encode("utf-8")))  # type: ignore[arg-type]


@pytest.mark.parametrize("base_url", [
    f"https://127.0.0.1:{BRIDGE_PORT}", "http://example.com:8202", "http://127.0.0.1:8201",
    f"http://127.0.0.1:{BRIDGE_PORT}/x", f"http://user:pw@127.0.0.1:{BRIDGE_PORT}",
])
def test_the_bridge_refuses_to_call_anywhere_but_this_computer(base_url: str) -> None:
    with pytest.raises(MotionHostBridgeRefused):
        MotionHostBridge(base_url=base_url, http_client=_client({})).diagnose()


@pytest.mark.parametrize("base_url", [_LOCAL, f"http://host.docker.internal:{BRIDGE_PORT}"])
def test_the_bridge_allows_this_computer_and_the_container_address(base_url: str) -> None:
    assert MotionHostBridge(base_url=base_url, http_client=_client({"status": "ready"})).diagnose() == {"status": "ready"}


def test_the_bridge_is_off_when_nobody_configured_an_address() -> None:
    assert MotionHostBridge.from_environment({}) is None
    assert MotionHostBridge.from_environment({"VIDEOBOX_MOTION_BRIDGE_URL": _LOCAL}).base_url == _LOCAL


def test_render_returns_the_bytes_the_host_made_and_waits_long_enough() -> None:
    seen: list = []
    reply = {"video_base64": base64.b64encode(b"MP4").decode(), "format": "mp4", "elapsed_sec": 14.2}
    clip = MotionHostBridge(http_client=_client(reply, seen=seen)).render(**ORDER)
    assert (clip.video_bytes, clip.format, clip.elapsed_sec) == (b"MP4", "mp4", 14.2)
    request, timeout = seen[0]
    assert timeout == BRIDGE_TIMEOUT_SECONDS
    assert json.loads(request.data.decode("utf-8")) == ORDER


@pytest.mark.parametrize("reply", [{}, {"video_base64": "!!!", "format": "mp4"}, {"video_base64": "", "format": "mp4"}, {"video_base64": "TVA0", "format": "gif"}])
def test_a_reply_without_a_usable_video_is_a_refusal(reply: dict) -> None:
    with pytest.raises(MotionHostBridgeRefused):
        MotionHostBridge(http_client=_client(reply)).render(**ORDER)


@pytest.mark.parametrize(("code", "error"), [(409, "motion_render_busy"), (503, "motion_engine_not_prepared"), (400, "text_not_allowed")])
def test_a_refusal_carries_the_bridges_own_reason(code: int, error: str) -> None:
    with pytest.raises(MotionHostBridgeRefused) as caught:
        MotionHostBridge(http_client=_raising_client(_http_error(code, {"error": error}))).render(**ORDER)
    assert (caught.value.status, caught.value.error) == (code, error)


def test_a_bridge_nobody_switched_on_is_unavailable() -> None:
    with pytest.raises(MotionHostBridgeUnavailable):
        MotionHostBridge(http_client=_raising_client(URLError("connection refused"))).render(**ORDER)


@pytest.mark.parametrize("error", [TimeoutError("timed out"), URLError(TimeoutError("timed out"))])
def test_waiting_too_long_is_its_own_answer(error: BaseException) -> None:
    with pytest.raises(MotionHostBridgeTimedOut):
        MotionHostBridge(http_client=_raising_client(error)).render(**ORDER)


def test_the_bridge_token_rides_along(monkeypatch) -> None:
    from videobox_provider_interfaces.host_bridge_auth import TOKEN_ENV, TOKEN_HEADER

    monkeypatch.setenv(TOKEN_ENV, "m" * 43)
    seen: list = []
    MotionHostBridge(http_client=_client({"status": "ready"}, seen=seen)).diagnose()
    assert seen[0][0].get_header(TOKEN_HEADER.capitalize()) == "m" * 43
