from __future__ import annotations

import sys
import socket
import inspect
import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC_PATHS = [
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


def _allow_live_lmstudio(request: pytest.FixtureRequest, address: object) -> bool:
    return (
        request.node.get_closest_marker("live_lmstudio") is not None
        and os.environ.get("VIDEOBOX_RUN_LM_STUDIO_MEDIA_SMOKE") == "1"
        and isinstance(address, tuple)
        and len(address) >= 2
        and address[0] == "127.0.0.1"
        and address[1] == 1234
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
