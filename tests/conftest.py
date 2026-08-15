from __future__ import annotations

import sys
import socket
import inspect
import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC_PATHS = [
    ROOT / "services" / "agent-gateway" / "src",
    ROOT / "services" / "api" / "src",
    ROOT / "packages" / "domain-models" / "src",
    ROOT / "packages" / "storage-abstractions" / "src",
    ROOT / "packages" / "provider-interfaces" / "src",
    ROOT / "packages" / "timeline-schema" / "src",
    ROOT / "packages" / "core-engine" / "src",
    ROOT / "packages" / "capcut-export" / "src",
]

for src_path in SRC_PATHS:
    sys.path.insert(0, str(src_path))

from videobox_provider_interfaces.llm import LLMProviderError


_LIVE_LMSTUDIO_OPT_IN_ENV_VARS = (
    "VIDEOBOX_RUN_LM_STUDIO_MEDIA_SMOKE",
    "VIDEOBOX_RUN_YUJIN_LOCAL_CONVERSATION_SMOKE",
)


def _allow_live_lmstudio(request: pytest.FixtureRequest, address: object) -> bool:
    return (
        request.node.get_closest_marker("live_lmstudio") is not None
        and any(os.environ.get(var) == "1" for var in _LIVE_LMSTUDIO_OPT_IN_ENV_VARS)
        and isinstance(address, tuple)
        and len(address) >= 2
        and address[0] == "127.0.0.1"
        and address[1] == 1234
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "docs_only: documentation contract tests that must not import or patch the API runtime",
    )


class _DeterministicOfflineRuntime:
    def generate_structured(self, **_: object) -> object:
        raise LLMProviderError(
            provider_name="deterministic_test_runtime",
            message="Tests use deterministic heuristic fallback instead of live LLM HTTP.",
            retryable=False,
            error_code="DETERMINISTIC_TEST_FALLBACK",
        )


@pytest.fixture(autouse=True)
def _replace_live_llm_runtime(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("docs_only") is not None:
        return
    import videobox_api.main as api_main

    def build_deterministic_runtime(**_: object) -> _DeterministicOfflineRuntime:
        return _DeterministicOfflineRuntime()

    def forbidden_urlopen(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Tests must not call a live LLM HTTP transport.")

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_bind = socket.socket.bind
    original_create_connection = socket.create_connection
    socketpair_listener_ports: set[int] = set()

    def is_socketpair_plumbing() -> bool:
        return any(
            frame.function == "_fallback_socketpair" and frame.filename.endswith("socket.py")
            for frame in inspect.stack()
        )

    def guarded_connect(sock: socket.socket, address: object) -> object:
        if _allow_live_lmstudio(request, address):
            return original_connect(sock, address)
        # asyncio on Windows implements socket.socketpair() with a private
        # loopback listener.  Permit only the exact ephemeral port bound by
        # that plumbing, never arbitrary loopback destinations.
        if (
            isinstance(address, tuple)
            and len(address) == 2
            and address[0] == "127.0.0.1"
            and address[1] in socketpair_listener_ports
            and is_socketpair_plumbing()
        ):
            socketpair_listener_ports.discard(address[1])
            return original_connect(sock, address)
        raise AssertionError("Tests must not open network connections.")

    def guarded_connect_ex(sock: socket.socket, address: object) -> int:
        if _allow_live_lmstudio(request, address):
            return original_connect_ex(sock, address)
        if (
            isinstance(address, tuple)
            and len(address) == 2
            and address[0] == "127.0.0.1"
            and address[1] in socketpair_listener_ports
            and is_socketpair_plumbing()
        ):
            socketpair_listener_ports.discard(address[1])
            return original_connect_ex(sock, address)
        raise AssertionError("Tests must not open network connections.")

    def guarded_bind(sock: socket.socket, address: object) -> object:
        result = original_bind(sock, address)
        if (
            is_socketpair_plumbing()
            and isinstance(address, tuple)
            and len(address) == 2
            and address[0] == "127.0.0.1"
        ):
            bound_address = sock.getsockname()
            if isinstance(bound_address, tuple) and isinstance(bound_address[1], int):
                socketpair_listener_ports.add(bound_address[1])
        return result

    def guarded_create_connection(address: object, *args: object, **kwargs: object) -> socket.socket:
        if _allow_live_lmstudio(request, address):
            return original_create_connection(address, *args, **kwargs)
        raise AssertionError("Tests must not open network connections.")

    monkeypatch.setattr(api_main, "build_local_only_runtime_service", build_deterministic_runtime)
    monkeypatch.setattr(api_main, "urlopen", forbidden_urlopen)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket.socket, "bind", guarded_bind)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)


# Drawing a text overlay needs a real font file on disk. These tests used to
# rely on the renderer's own default, which was a `C:\Windows\Fonts` path --
# so they only ever proved anything on a Windows dev machine and would have
# failed in the Linux container the product ships in. The test environment
# now names the font it has, instead of the product carrying a default that
# happens to suit one developer's machine.
_OVERLAY_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\arial.ttf",
)


@pytest.fixture(autouse=True, scope="session")
def _overlay_font_for_tests() -> None:
    if os.environ.get("VIDEOBOX_OVERLAY_FONT"):
        return
    for candidate in _OVERLAY_FONT_CANDIDATES:
        if Path(candidate).is_file():
            os.environ["VIDEOBOX_OVERLAY_FONT"] = candidate
            return
