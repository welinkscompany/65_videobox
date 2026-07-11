from __future__ import annotations

import sys
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


class _DeterministicOfflineRuntime:
    def generate_structured(self, **_: object) -> object:
        raise LLMProviderError(
            provider_name="deterministic_test_runtime",
            message="Tests use deterministic heuristic fallback instead of live LLM HTTP.",
            retryable=False,
            error_code="DETERMINISTIC_TEST_FALLBACK",
        )


@pytest.fixture(autouse=True)
def _replace_live_llm_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    import videobox_api.main as api_main

    def build_deterministic_runtime(**_: object) -> _DeterministicOfflineRuntime:
        return _DeterministicOfflineRuntime()

    def forbidden_urlopen(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Tests must not call a live LLM HTTP transport.")

    monkeypatch.setattr(api_main, "build_local_first_runtime_service", build_deterministic_runtime)
    monkeypatch.setattr(api_main, "urlopen", forbidden_urlopen)
