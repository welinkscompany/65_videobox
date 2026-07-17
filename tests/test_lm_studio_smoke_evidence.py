from __future__ import annotations

import json

import pytest

from videobox_core_engine.lm_studio_smoke_evidence import write_live_media_smoke_evidence


def test_live_media_smoke_success_evidence_is_durable_and_local_only(tmp_path) -> None:
    artifact = write_live_media_smoke_evidence(
        artifact_root=tmp_path / "artifacts",
        evidence={
            "git_head": "f740913",
            "command": "pytest -q -m live_lmstudio tests/test_lm_studio_media_smoke.py",
            "test_totals": {"passed": 1, "skipped": 0},
            "profile": {
                "vision_model_name": "vision-local",
                "embedding_model_name": "embedding-local",
                "variant": "default",
            },
            "sample_sha256": "a" * 64,
            "requested_endpoints": [
                "http://127.0.0.1:1234/api/v1/models",
                "http://127.0.0.1:1234/v1/chat/completions",
                "http://127.0.0.1:1234/v1/embeddings",
            ],
            "loopback_request_count": 3,
            "external_provider_calls": 0,
            "gemini_calls": 0,
            "provider_trace": {
                "routing_mode": "local_first",
                "final_provider": "lm_studio",
                "fallback_reasons": [],
            },
            "timestamp": "2026-07-15T00:00:00+00:00",
        },
    )

    assert artifact == tmp_path / "artifacts" / "live-media-success.json"
    assert json.loads(artifact.read_text(encoding="utf-8"))["external_provider_calls"] == 0
    assert json.loads(artifact.read_text(encoding="utf-8"))["gemini_calls"] == 0


@pytest.mark.parametrize(
    ("profile", "sample_sha256"),
    [
        ({"vision_model_name": "vision", "embedding_model_name": "embedding", "variant": ""}, "a" * 64),
        ({"vision_model_name": "vision", "embedding_model_name": "embedding", "variant": "default"}, "not-a-sha"),
    ],
)
def test_live_media_smoke_success_evidence_rejects_incomplete_profile_or_sample_hash(tmp_path, profile, sample_sha256) -> None:
    evidence = {
        "git_head": "f740913",
        "command": "pytest -q -m live_lmstudio tests/test_lm_studio_media_smoke.py",
        "test_totals": {"passed": 1, "skipped": 0},
        "profile": profile,
        "sample_sha256": sample_sha256,
        "requested_endpoints": ["http://127.0.0.1:1234/v1/models"],
        "loopback_request_count": 1,
        "external_provider_calls": 0,
        "gemini_calls": 0,
        "provider_trace": {"routing_mode": "local_first", "final_provider": "lm_studio", "fallback_reasons": []},
        "timestamp": "2026-07-15T00:00:00+00:00",
    }

    with pytest.raises(ValueError, match="variant|sample_sha256"):
        write_live_media_smoke_evidence(artifact_root=tmp_path / "artifacts", evidence=evidence)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1:1234/v1/chat/completions?redirect=http://example.invalid",
        "http://127.0.0.1:1234/api/v1/models#fragment",
    ],
)
def test_live_media_smoke_success_evidence_rejects_nonexact_loopback_endpoint(tmp_path, endpoint: str) -> None:
    evidence = {
        "git_head": "f740913",
        "command": "pytest -q -m live_lmstudio tests/test_lm_studio_media_smoke.py",
        "test_totals": {"passed": 1, "skipped": 0},
        "profile": {"vision_model_name": "vision", "embedding_model_name": "embedding", "variant": "live"},
        "sample_sha256": "a" * 64,
        "requested_endpoints": [endpoint],
        "loopback_request_count": 1,
        "external_provider_calls": 0,
        "gemini_calls": 0,
        "provider_trace": {"routing_mode": "local_first", "final_provider": "lm_studio", "fallback_reasons": []},
        "timestamp": "2026-07-15T00:00:00+00:00",
    }

    with pytest.raises(ValueError, match="exact LM Studio loopback"):
        write_live_media_smoke_evidence(artifact_root=tmp_path / "artifacts", evidence=evidence)
