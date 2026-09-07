"""인포그래픽 다리를 **부르는 쪽** — 컨테이너가 이 컴퓨터의 크롬에 닿는가.

세 가지가 같이 있어야 owner가 화면에서 인포그래픽 한 장을 받을 수 있다.

1. **경계**: 나가는 곳은 이 컴퓨터의 8201뿐이다. 그 밖은 요청 전에 막는다.
2. **정직**: 다리가 꺼져 있으면 "켜 주세요", 다리가 거절하면 "거절당했다"라고
   말한다. 둘을 뒤섞으면 owner가 엉뚱한 것을 고치게 된다.
3. **그림**: 못 읽는 그림을 빈 바이트로 돌려주면 부르는 쪽이 성공으로 착각한다.

**연결은 안 연다.** `http_client`를 손으로 주어 잰다. 이 저장소의 시험은 연결을
못 열게 막혀 있고(`tests/conftest.py`), 그 울타리는 옳다.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError

import pytest

from videobox_core_engine.infographic_host_bridge import (
    BRIDGE_PORT,
    ENVIRONMENT_VARIABLE,
    InfographicHostBridge,
    InfographicHostBridgeRefused,
    InfographicHostBridgeUnavailable,
)

_LOCAL = f"http://127.0.0.1:{BRIDGE_PORT}"
_CONTAINER = f"http://host.docker.internal:{BRIDGE_PORT}"


def _client(reply: dict[str, Any], *, calls: list[str] | None = None):
    """정해진 답을 돌려주는 가짜 다리."""

    def client(request, timeout):  # noqa: ANN001, ARG001
        if calls is not None:
            calls.append(request.full_url)
        return json.dumps(reply).encode("utf-8")

    return client


def _raising_client(error: BaseException):
    def client(request, timeout):  # noqa: ANN001, ARG001
        raise error

    return client


# --------------------------------------------------------------------------
# 1. 나가는 곳은 이 컴퓨터뿐
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "base_url",
    [
        f"https://127.0.0.1:{BRIDGE_PORT}",
        "http://127.0.0.1:9999",
        f"http://127.0.0.1:{BRIDGE_PORT}/somewhere",
        f"http://127.0.0.1:{BRIDGE_PORT}?html=x",
        f"http://user:pass@127.0.0.1:{BRIDGE_PORT}",
        f"http://user@127.0.0.1:{BRIDGE_PORT}",
        f"http://:pass@127.0.0.1:{BRIDGE_PORT}",
        f"http://example.com:{BRIDGE_PORT}",
    ],
)
def test_bridge_refuses_to_call_anywhere_but_this_computer(base_url: str) -> None:
    """설정 한 줄이 잘못 적히면 HTML이 밖으로 나간다. 요청 **직전에** 다시 본다."""
    bridge = InfographicHostBridge(
        base_url=base_url, http_client=_raising_client(AssertionError("나가면 안 된다"))
    )

    with pytest.raises(InfographicHostBridgeRefused):
        bridge.diagnose()


@pytest.mark.parametrize("base_url", [_LOCAL, _CONTAINER])
def test_bridge_allows_this_computer_and_the_container_address(base_url: str) -> None:
    """컨테이너에서는 `host.docker.internal`이 이 컴퓨터다. 둘 다 통과해야 한다."""
    calls: list[str] = []
    bridge = InfographicHostBridge(
        base_url=base_url, http_client=_client({"status": "ready"}, calls=calls)
    )

    assert bridge.diagnose() == {"status": "ready"}
    assert calls == [f"{base_url}/diagnostics"]


def test_bridge_is_off_when_nobody_configured_an_address(monkeypatch) -> None:
    """비어 있으면 기본 주소로 슬쩍 붙지 않는다 -- **기능이 꺼진 것**이다."""
    monkeypatch.delenv(ENVIRONMENT_VARIABLE, raising=False)
    assert InfographicHostBridge.from_environment() is None
    assert InfographicHostBridge.from_environment({ENVIRONMENT_VARIABLE: "   "}) is None

    configured = InfographicHostBridge.from_environment({ENVIRONMENT_VARIABLE: _LOCAL})
    assert configured is not None and configured.base_url == _LOCAL


# --------------------------------------------------------------------------
# 2. 그림 — 못 받은 것을 받았다고 하지 않는다
# --------------------------------------------------------------------------


def test_render_returns_the_bytes_the_host_drew() -> None:
    import base64

    png = b"\x89PNG\r\n\x1a\n" + bytes(range(64))
    bridge = InfographicHostBridge(
        http_client=_client({"png_base64": base64.b64encode(png).decode("ascii")})
    )

    assert bridge.render(html="<p>hi</p>") == png


def test_render_refuses_a_reply_that_carries_no_picture() -> None:
    """빈 바이트를 돌려주면 부르는 쪽이 성공으로 착각한다."""
    bridge = InfographicHostBridge(http_client=_client({"byte_size": 0}))

    with pytest.raises(InfographicHostBridgeRefused):
        bridge.render(html="<p>hi</p>")


def test_render_refuses_a_picture_we_cannot_read() -> None:
    bridge = InfographicHostBridge(http_client=_client({"png_base64": "이건 base64가 아니다"}))

    with pytest.raises(InfographicHostBridgeRefused):
        bridge.render(html="<p>hi</p>")


def test_render_refuses_a_picture_that_turns_out_to_be_empty(monkeypatch) -> None:
    """제대로 된 base64인데 **바이트가 0장**인 경우. 정상 경로로는 만들 수 없어서
    (빈 base64는 앞 관문이 먼저 잡는다) 풀어 주는 자리를 손으로 비게 만든다.
    이 한 줄이 없으면 0바이트 PNG가 성공으로 나간다."""
    import base64 as base64_module

    from videobox_core_engine import infographic_host_bridge

    monkeypatch.setattr(
        infographic_host_bridge.base64, "b64decode", lambda *args, **kwargs: b""
    )
    bridge = InfographicHostBridge(
        http_client=_client({"png_base64": base64_module.b64encode(b"x").decode("ascii")})
    )

    with pytest.raises(InfographicHostBridgeRefused):
        bridge.render(html="<p>hi</p>")


# --------------------------------------------------------------------------
# 3. 재기 — 잰 값이 없으면 없다고 한다
# --------------------------------------------------------------------------


def test_measure_returns_the_title_the_browser_settled_on() -> None:
    bridge = InfographicHostBridge(
        http_client=_client({"title": "<title>overflow=0 collisions=0</title>"})
    )

    assert bridge.measure(html="<p>hi</p>") == "<title>overflow=0 collisions=0</title>"


def test_measure_refuses_a_reply_with_no_measurement() -> None:
    """빈 문자열을 조용히 돌려주면 "겹침 없음"으로 읽혀 잘린 판이 통과한다."""
    bridge = InfographicHostBridge(http_client=_client({"status": "ready"}))

    with pytest.raises(InfographicHostBridgeRefused):
        bridge.measure(html="<p>hi</p>")


# --------------------------------------------------------------------------
# 4. 거절과 부재는 다른 말이다
# --------------------------------------------------------------------------


def test_a_bridge_that_answered_no_is_a_refusal_not_a_missing_bridge() -> None:
    """다리는 살아 있는데 요청을 거절한 것이다 -- "켜 주세요"라고 말하면 거짓말이 된다."""
    bridge = InfographicHostBridge(
        http_client=_raising_client(HTTPError(_LOCAL, 400, "html_is_required", {}, None))  # type: ignore[arg-type]
    )

    with pytest.raises(InfographicHostBridgeRefused) as failure:
        bridge.render(html="")

    assert "400" in str(failure.value)


def test_a_bridge_nobody_switched_on_is_reported_as_unavailable() -> None:
    """이쪽은 진짜로 "켜 주세요"다. 거절과 뒤섞으면 owner가 HTML을 고치려 든다."""
    bridge = InfographicHostBridge(http_client=_raising_client(URLError("connection refused")))

    with pytest.raises(InfographicHostBridgeUnavailable):
        bridge.diagnose()


def test_a_reply_we_cannot_read_is_a_refusal() -> None:
    def client(request, timeout):  # noqa: ANN001, ARG001
        return b"not json at all"

    bridge = InfographicHostBridge(http_client=client)

    with pytest.raises(InfographicHostBridgeRefused):
        bridge.diagnose()
