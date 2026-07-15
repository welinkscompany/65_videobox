from __future__ import annotations

from types import SimpleNamespace

import pytest

import conftest as test_conftest


def _request(*, marked: bool) -> pytest.FixtureRequest:
    marker = object() if marked else None
    return SimpleNamespace(node=SimpleNamespace(get_closest_marker=lambda name: marker if name == "live_lmstudio" else None))  # type: ignore[return-value]


def test_live_lm_studio_socket_exception_requires_marker_and_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIDEOBOX_RUN_LM_STUDIO_MEDIA_SMOKE", raising=False)

    assert not test_conftest._allow_live_lmstudio(_request(marked=True), ("127.0.0.1", 1234))
    monkeypatch.setenv("VIDEOBOX_RUN_LM_STUDIO_MEDIA_SMOKE", "1")
    assert test_conftest._allow_live_lmstudio(_request(marked=True), ("127.0.0.1", 1234))
    assert not test_conftest._allow_live_lmstudio(_request(marked=False), ("127.0.0.1", 1234))
    assert not test_conftest._allow_live_lmstudio(_request(marked=True), ("127.0.0.1", 1235))
