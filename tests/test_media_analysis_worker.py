from __future__ import annotations

import json
from pathlib import Path

import pytest

from videobox_core_engine.settings import resolve_enable_local_media_analysis
from videobox_api.main import create_app


def test_resolve_enable_local_media_analysis_defaults_to_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIDEOBOX_MEDIA_ANALYSIS_ENABLED", raising=False)
    assert resolve_enable_local_media_analysis() is False


def test_resolve_enable_local_media_analysis_reads_env_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIDEOBOX_MEDIA_ANALYSIS_ENABLED", "1")
    assert resolve_enable_local_media_analysis() is True


def test_app_factory_without_arguments_wires_the_real_worker_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The container factory is invoked with zero arguments (Task 1's pattern).
    Enabling the env flag must be enough to swap out
    _UnavailableMediaAnalysisService for the real MediaAnalysisService --
    without this, worker.py's `create_app --factory` path silently keeps
    every B-roll analysis permanently blocked, the same class of bug Task 1
    found for STT."""
    monkeypatch.setenv("VIDEOBOX_MEDIA_ANALYSIS_ENABLED", "1")

    calls: list[str] = []

    class _FakeResponse:
        def __init__(self, payload: dict) -> None:
            self._body = json.dumps(payload).encode("utf-8")

        def read(self) -> bytes:
            return self._body

        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

    def fake_http_client(request, timeout=None, allow_redirects=False):  # noqa: ANN001
        calls.append(request.full_url)
        if request.full_url.endswith("/api/v1/models"):
            return _FakeResponse(
                {
                    "models": [
                        {
                            "type": "llm",
                            "capabilities": {"vision": True},
                            "loaded_instances": [{"id": "test-vision-model"}],
                        }
                    ]
                }
            )
        raise AssertionError(f"unexpected request during preflight-only test: {request.full_url}")

    app = create_app(projects_root=tmp_path / "projects", media_analysis_http_client=fake_http_client)

    assert app.state.media_analysis_vision_provider is not None
    assert calls, "expected the app factory to preflight the LM Studio worker when the flag is set"


def test_app_factory_without_arguments_stays_unavailable_when_not_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIDEOBOX_MEDIA_ANALYSIS_ENABLED", raising=False)

    app = create_app(projects_root=tmp_path / "projects")

    assert app.state.media_analysis_vision_provider is None
