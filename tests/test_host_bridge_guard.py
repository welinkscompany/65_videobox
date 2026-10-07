"""호스트 다리 셋의 문지기 (2026-10-02, 점검 후속 A2).

목소리(8199)·캡컷(8200)·그림(8201) 다리는 127.0.0.1에만 묶여 있지만, 이 컴퓨터의
아무 프로세스나 브라우저의 아무 웹페이지나 부를 수 있었다. owner 결정은 "공유 토큰까지"다.

**소켓은 안 연다**(`tests/conftest.py`가 막는다). 판단 함수(`check_request`)를 그대로
부르고, 배선은 핸들러 객체를 소켓 없이 만들어 `do_GET`/`do_POST`를 직접 부른다.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from http.client import HTTPMessage
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "k3Y-" + "a1B2c3D4e5F6g7H8i9J0" * 2  # 44자


def _load(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "scripts" / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # 목소리 다리의 dataclass는 정의한 모듈을 sys.modules에서 찾는다
    # (`tests/test_host_tts_engine_licence.py::_bridge`와 같은 이유).
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


guard = _load("videobox_host_bridge_guard_under_test", "host_bridge_guard.py")


# --------------------------------------------------------------------------
# 1. 판단 함수
# --------------------------------------------------------------------------


def test_a_request_without_the_token_is_refused() -> None:
    refusal = guard.check_request(
        method="POST",
        headers={"Host": "127.0.0.1:8199", "Content-Type": "application/json"},
        port=8199,
        expected_token=TOKEN,
    )
    assert refusal == (401, {"error": "bridge_token_required"})


def test_a_wrong_token_is_refused() -> None:
    refusal = guard.check_request(
        method="POST",
        headers={"Host": "127.0.0.1:8199", "Content-Type": "application/json", guard.TOKEN_HEADER: TOKEN[:-1] + "x"},
        port=8199,
        expected_token=TOKEN,
    )
    assert refusal == (401, {"error": "bridge_token_required"})


def test_text_with_the_right_token_is_refused_as_not_json() -> None:
    refusal = guard.check_request(
        method="POST",
        headers={"Host": "127.0.0.1:8201", "Content-Type": "text/plain", guard.TOKEN_HEADER: TOKEN},
        port=8201,
        expected_token=TOKEN,
    )
    assert refusal == (415, {"error": "json_required"})


@pytest.mark.parametrize("content_type", ["application/json", "application/json; charset=utf-8", "Application/JSON"])
def test_json_with_the_right_token_from_the_container_passes(content_type: str) -> None:
    assert guard.check_request(
        method="POST",
        headers={"Host": "host.docker.internal:8200", "Content-Type": content_type, guard.TOKEN_HEADER: TOKEN},
        port=8200,
        expected_token=TOKEN,
    ) is None


@pytest.mark.parametrize("host", ["evil.example:8199", "127.0.0.1:9999", "127.0.0.1", "", "localhost.evil.example:8199"])
def test_a_foreign_host_is_refused_even_with_the_token(host: str) -> None:
    headers = {"Content-Type": "application/json", guard.TOKEN_HEADER: TOKEN}
    if host:
        headers["Host"] = host
    refusal = guard.check_request(method="POST", headers=headers, port=8199, expected_token=TOKEN)
    assert refusal == (400, {"error": "host_not_allowed"})


def test_an_empty_expected_token_never_lets_an_empty_header_through() -> None:
    """`compare_digest(b"", b"")`는 참이다. 토큰 없이 뜬 다리가 아무나 받으면 안 된다."""
    refusal = guard.check_request(
        method="POST",
        headers={"Host": "127.0.0.1:8199", "Content-Type": "application/json", guard.TOKEN_HEADER: ""},
        port=8199,
        expected_token="",
    )
    assert refusal == (503, {"error": "bridge_token_not_configured"})


def test_an_open_read_still_checks_the_host() -> None:
    assert guard.check_request(
        method="GET", headers={"Host": "localhost:8199"}, port=8199, expected_token=TOKEN, require_token=False
    ) is None
    assert guard.check_request(
        method="GET", headers={"Host": "evil.example:8199"}, port=8199, expected_token=TOKEN, require_token=False
    ) == (400, {"error": "host_not_allowed"})


def test_the_token_comes_from_the_environment_first(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.container"
    env_file.write_text(f"VIDEOBOX_BRIDGE_TOKEN={'f' * 40}\n", encoding="utf-8")
    assert guard.load_bridge_token({guard.TOKEN_ENV: TOKEN}, env_file) == TOKEN


def test_the_token_falls_back_to_the_env_file_with_bom_crlf_and_quotes(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.container"
    env_file.write_bytes(
        b"\xef\xbb\xbf# comment\r\nPOSTGRES_DB=videobox\r\n"
        + f'VIDEOBOX_BRIDGE_TOKEN="{TOKEN}"\r\n'.encode("utf-8")
    )
    assert guard.load_bridge_token({}, env_file) == TOKEN


@pytest.mark.parametrize(
    "content", ["", "VIDEOBOX_BRIDGE_TOKEN=\n", "VIDEOBOX_BRIDGE_TOKEN=short\n", "#VIDEOBOX_BRIDGE_TOKEN=" + "z" * 40 + "\n"]
)
def test_a_missing_or_short_token_stops_the_bridge(tmp_path: Path, content: str) -> None:
    env_file = tmp_path / ".env.container"
    env_file.write_text(content, encoding="utf-8")
    with pytest.raises(guard.BridgeTokenMissing):
        guard.load_bridge_token({}, env_file)


def test_a_missing_env_file_stops_the_bridge(tmp_path: Path) -> None:
    with pytest.raises(guard.BridgeTokenMissing):
        guard.load_bridge_token({}, tmp_path / "nope.env")


# --------------------------------------------------------------------------
# 2. 배선 -- 세 다리가 실제로 문지기를 부르는가
# --------------------------------------------------------------------------

tts = _load("videobox_host_tts_service_guard_test", "host_tts_service.py")
capcut = _load("videobox_host_capcut_service_guard_test", "host_capcut_service.py")
infographic = _load("videobox_host_infographic_service_guard_test", "host_infographic_service.py")

_TTS_HANDLER = type("TtsHandler", (tts._Handler,), {"bridge_token": TOKEN, "engine_choice": tts.resolve_engine({})})
_CAPCUT_HANDLER = type("CapCutHandler", (capcut._Handler,), {"bridge_token": TOKEN, "allowed_roots": ()})
_INFOGRAPHIC_HANDLER = type("InfographicHandler", (infographic._Handler,), {"bridge_token": TOKEN, "browser": None})


def _call(handler_class, *, method: str, path: str, port: int, headers: dict[str, str], body: bytes = b""):
    """소켓 없이 핸들러를 만들어 한 요청을 흘린다."""
    handler = handler_class.__new__(handler_class)
    message = HTTPMessage()
    for key, value in headers.items():
        message[key] = value
    if body:
        message["Content-Length"] = str(len(body))
    handler.headers = message
    handler.command = method
    handler.path = path
    handler.request_version = "HTTP/1.1"
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler.client_address = ("127.0.0.1", 50000)
    handler.server = SimpleNamespace(server_address=("127.0.0.1", port))
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()
    handler.close_connection = True
    getattr(handler, f"do_{method}")()
    head, _, payload = handler.wfile.getvalue().partition(b"\r\n\r\n")
    status = int(head.split(b" ")[1])
    return status, (json.loads(payload.decode("utf-8")) if payload else None)


_POSTS = [
    (_TTS_HANDLER, "/synthesize", 8199),
    (_CAPCUT_HANDLER, "/register", 8200),
    (_INFOGRAPHIC_HANDLER, "/render", 8201),
]


@pytest.mark.parametrize(("handler_class", "path", "port"), _POSTS)
def test_every_bridge_refuses_a_post_without_the_token(handler_class, path: str, port: int) -> None:
    status, _ = _call(
        handler_class, method="POST", path=path, port=port,
        headers={"Host": f"127.0.0.1:{port}", "Content-Type": "application/json"}, body=b"{}",
    )
    assert status == 401


@pytest.mark.parametrize(("handler_class", "path", "port"), _POSTS)
def test_every_bridge_refuses_text_even_with_the_token(handler_class, path: str, port: int) -> None:
    status, _ = _call(
        handler_class, method="POST", path=path, port=port,
        headers={"Host": f"127.0.0.1:{port}", "Content-Type": "text/plain", guard.TOKEN_HEADER: TOKEN}, body=b"x",
    )
    assert status == 415


@pytest.mark.parametrize(("handler_class", "path", "port"), _POSTS)
def test_every_bridge_refuses_a_foreign_host(handler_class, path: str, port: int) -> None:
    status, _ = _call(
        handler_class, method="POST", path=path, port=port,
        headers={"Host": "evil.example", "Content-Type": "application/json", guard.TOKEN_HEADER: TOKEN}, body=b"{}",
    )
    assert status == 400


def test_the_header_name_is_matched_without_case() -> None:
    status, payload = _call(
        _INFOGRAPHIC_HANDLER, method="GET", path="/diagnostics", port=8201,
        headers={"Host": "host.docker.internal:8201", "x-videobox-bridge-token": TOKEN},
    )
    assert status == 200
    assert payload["status"] == "browser_not_found"


def test_diagnostics_need_the_token() -> None:
    status, payload = _call(
        _CAPCUT_HANDLER, method="GET", path="/diagnostics", port=8200, headers={"Host": "127.0.0.1:8200"},
    )
    assert status == 401
    assert payload == {"error": "bridge_token_required"}


def test_voice_health_stays_open_for_the_start_script_but_checks_the_host() -> None:
    """`Start-VideoBox.ps1`이 토큰 없이 `/health`로 켜졌는지 묻는다."""
    status, payload = _call(_TTS_HANDLER, method="GET", path="/health", port=8199, headers={"Host": "127.0.0.1:8199"})
    assert status == 200
    assert payload["engine"] == "chatterbox"
    status, _ = _call(_TTS_HANDLER, method="GET", path="/health", port=8199, headers={"Host": "evil.example:8199"})
    assert status == 400


def test_a_passing_post_reaches_the_bridges_own_checks() -> None:
    """문지기를 통과하면 다리 자기 검사로 간다 -- 여기서는 브라우저가 없다는 503."""
    status, payload = _call(
        _INFOGRAPHIC_HANDLER, method="POST", path="/render", port=8201,
        headers={"Host": "127.0.0.1:8201", "Content-Type": "application/json", guard.TOKEN_HEADER: TOKEN}, body=b"{}",
    )
    assert (status, payload) == (503, {"error": "browser_not_found"})


def test_the_sender_and_the_receiver_use_the_same_names() -> None:
    """받는 쪽(스크립트)과 보내는 쪽(패키지)이 이름을 따로 들고 있다. 어긋나면 전부 401이다."""
    from videobox_provider_interfaces import host_bridge_auth

    assert host_bridge_auth.TOKEN_HEADER == guard.TOKEN_HEADER
    assert host_bridge_auth.TOKEN_ENV == guard.TOKEN_ENV
