from __future__ import annotations

import hashlib
import math
import os
import subprocess
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import pytest

from videobox_core_engine.provider_trace import response_provider_trace
from videobox_core_engine.lm_studio_smoke_evidence import write_live_media_smoke_evidence
from videobox_provider_interfaces.embeddings import EmbeddingRequest
from videobox_provider_interfaces.lm_studio import (
    LMStudioEmbeddingProvider,
    LMStudioHTTPTransport,
    LMStudioProviderError,
    LMStudioVisionProvider,
)
from videobox_provider_interfaces.vision import FIXED_VISION_LAYERS, FIXED_VISION_RESPONSE_SCHEMA, VisionAnalysisRequest
from videobox_storage.local_project_store import LocalProjectStore


_LIVE_SMOKE_ENV = "VIDEOBOX_RUN_LM_STUDIO_MEDIA_SMOKE"
_LIVE_SMOKE_ENABLE_VALUE = "1"
_NATIVE_MODELS_ENDPOINT = "http://127.0.0.1:1234/api/v1/models"
_OPENAI_LOOPBACK_PREFIX = "http://127.0.0.1:1234/v1/"
_LIVE_SMOKE_SKIP_REASON = (
    "LM Studio live media smoke is disabled; set "
    "VIDEOBOX_RUN_LM_STUDIO_MEDIA_SMOKE=1 to permit only 127.0.0.1:1234."
)


def _require_live_smoke_opt_in() -> None:
    if os.environ.get(_LIVE_SMOKE_ENV) != _LIVE_SMOKE_ENABLE_VALUE:
        pytest.skip(_LIVE_SMOKE_SKIP_REASON)


def _small_jpeg() -> bytes:
    from PIL import Image

    image = Image.new("RGB", (16, 8), "#38598b")
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _artifact_root() -> Path:
    return Path(os.environ.get("VIDEOBOX_LM_STUDIO_SMOKE_ARTIFACT_ROOT", "artifacts/lm-studio-media-smoke"))


def _git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_live_smoke_requires_explicit_environment_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_LIVE_SMOKE_ENV, raising=False)

    with pytest.raises(pytest.skip.Exception, match="live media smoke is disabled"):
        _require_live_smoke_opt_in()


@pytest.mark.live_lmstudio
def test_lm_studio_local_media_runtime_smoke() -> None:
    """Runs only by explicit opt-in and never substitutes a fake provider."""
    _require_live_smoke_opt_in()
    transport = LMStudioHTTPTransport()
    try:
        profile = transport.capability_profile(timeout_seconds=15)
    except LMStudioProviderError as exc:
        pytest.skip(f"LM Studio live media smoke blocked: {exc.code}: {exc}")

    if profile.vision_model_name is None:
        pytest.skip(
            "LM Studio live media smoke blocked: no loaded native Vision model is available."
        )

    try:
        transport.preflight(model_name=profile.vision_model_name, capability="vision", timeout_seconds=15)
    except LMStudioProviderError as exc:
        pytest.fail(f"LM Studio live media smoke Vision candidate failed preflight: {exc.code}: {exc}")

    source = _small_jpeg()
    vision_response = LMStudioVisionProvider(transport=transport).analyze_images(
        VisionAnalysisRequest(
            model_name=profile.vision_model_name,
            prompt="Return a concise description of this test image.",
            images=(source,),
            response_schema=FIXED_VISION_RESPONSE_SCHEMA,
            provider_context={"source_sha256": hashlib.sha256(source).hexdigest()},
        )
    )
    output = vision_response.output_data
    assert set(output) == {"layers", "summary", "confidence", "review_reasons"}
    assert set(output["layers"]) == set(FIXED_VISION_LAYERS)
    assert isinstance(output["summary"], str) and output["summary"].strip()
    assert isinstance(output["confidence"], float | int) and not isinstance(output["confidence"], bool)
    assert all(isinstance(tag, str) for values in output["layers"].values() for tag in values)
    assert all(isinstance(reason, str) for reason in output["review_reasons"])

    trace = response_provider_trace(vision_response)
    assert trace == {
        "routing_mode": "local_first",
        "final_provider": "lm_studio",
        "fallback_reasons": [],
    }
    assert "http://127.0.0.1:1234/v1" == transport.base_url

    if profile.embedding_model_name is None:
        pytest.skip(
            "LM Studio live media smoke blocked after vision: no loaded model advertises "
            "native embedding capability."
        )
    try:
        transport.preflight(model_name=profile.embedding_model_name, capability="embedding", timeout_seconds=15)
    except LMStudioProviderError as exc:
        pytest.fail(f"LM Studio live media smoke embedding candidate failed preflight: {exc.code}: {exc}")
    embedding_response = LMStudioEmbeddingProvider(transport=transport).embed(
        EmbeddingRequest(model_name=profile.embedding_model_name, inputs=(output["summary"],))
    )
    assert len(embedding_response.vectors) == 1
    assert embedding_response.vectors[0]
    assert all(math.isfinite(value) for value in embedding_response.vectors[0])

    root = _artifact_root()
    store = LocalProjectStore(root / "projects")
    project = store.bootstrap_project("LM Studio live media smoke")
    source_sha256 = hashlib.sha256(source).hexdigest()
    analysis = store.create_media_analysis(
        project_id=project.project_id,
        asset_id="live-smoke-source",
        idempotency_key=f"{source_sha256}:{profile.embedding_model_name}",
        cache_key=f"live-smoke:{profile.embedding_model_name}",
    )
    claim = store.claim_media_analysis(project_id=project.project_id, analysis_id=analysis["analysis_id"])
    assert claim is not None
    store.record_media_embedding(
        project_id=project.project_id,
        analysis_id=analysis["analysis_id"],
        source_sha256=source_sha256,
        profile_hash=f"live-smoke:{profile.embedding_model_name}",
        embedding=list(embedding_response.vectors[0]),
    )
    completed = store.complete_media_analysis(
        project_id=project.project_id,
        analysis_id=analysis["analysis_id"],
        expected_attempt=claim["attempt"],
        result={"summary": output["summary"]},
    )
    assert completed is not None
    matches = LocalProjectStore(root / "projects").find_local_media_embedding_matches(
        project_id=project.project_id,
        query_embedding=list(embedding_response.vectors[0]),
        limit=1,
    )
    assert matches == [
        {
            "analysis_id": analysis["analysis_id"],
            "asset_id": "live-smoke-source",
            "source_sha256": source_sha256,
            "profile_hash": f"live-smoke:{profile.embedding_model_name}",
            "score": pytest.approx(1.0),
        }
    ]

    endpoints = transport.requested_endpoints
    assert endpoints and all(
        endpoint == _NATIVE_MODELS_ENDPOINT or endpoint.startswith(_OPENAI_LOOPBACK_PREFIX) for endpoint in endpoints
    )
    evidence = {
        "git_head": _git_head(),
        "command": "VIDEOBOX_RUN_LM_STUDIO_MEDIA_SMOKE=1 pytest -q -m live_lmstudio tests/test_lm_studio_media_smoke.py",
        "test_totals": {"passed": 1, "skipped": 0},
        "profile": {
            "vision_model_name": profile.vision_model_name,
            "embedding_model_name": profile.embedding_model_name,
            "variant": "native_api_v1_inventory_plus_live_fixed_schema_probe",
        },
        "sample_sha256": source_sha256,
        "requested_endpoints": endpoints,
        "loopback_request_count": len(endpoints),
        "external_provider_calls": 0,
        "provider_trace": trace,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    artifact = write_live_media_smoke_evidence(artifact_root=root, evidence=evidence)
    assert artifact.read_text(encoding="utf-8")
    assert __import__("json").loads(artifact.read_text(encoding="utf-8")) == evidence
