from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_EXACT_LM_STUDIO_PREFIX = "http://127.0.0.1:1234/v1/"
_REQUIRED_EVIDENCE_FIELDS = frozenset(
    {
        "git_head",
        "command",
        "test_totals",
        "profile",
        "sample_sha256",
        "requested_endpoints",
        "loopback_request_count",
        "external_provider_calls",
        "gemini_calls",
        "provider_trace",
        "timestamp",
    }
)


def write_live_media_smoke_evidence(*, artifact_root: Path, evidence: dict[str, Any]) -> Path:
    """Persist a successful live-only smoke audit outside version control."""
    missing = _REQUIRED_EVIDENCE_FIELDS - set(evidence)
    if missing:
        raise ValueError(f"live smoke evidence is missing fields: {', '.join(sorted(missing))}")
    if evidence["external_provider_calls"] != 0 or evidence["gemini_calls"] != 0:
        raise ValueError("successful local smoke evidence must report zero external and Gemini calls")
    endpoints = evidence["requested_endpoints"]
    if (
        not isinstance(endpoints, list)
        or not endpoints
        or not all(isinstance(endpoint, str) and endpoint.startswith(_EXACT_LM_STUDIO_PREFIX) for endpoint in endpoints)
        or evidence["loopback_request_count"] != len(endpoints)
    ):
        raise ValueError("live smoke evidence must contain only exact LM Studio loopback requests")
    profile = evidence["profile"]
    trace = evidence["provider_trace"]
    if (
        not isinstance(profile, dict)
        or not str(profile.get("vision_model_name") or "").strip()
        or not str(profile.get("embedding_model_name") or "").strip()
        or not str(profile.get("variant") or "").strip()
        or not isinstance(trace, dict)
        or trace.get("final_provider") != "lm_studio"
        or trace.get("fallback_reasons") != []
    ):
        raise ValueError("live smoke evidence must identify an unfallbacked LM Studio vision, embedding, and variant profile")
    if not isinstance(evidence["sample_sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", evidence["sample_sha256"]) is None:
        raise ValueError("live smoke evidence sample_sha256 must be 64 lowercase hexadecimal characters")
    artifact_root.mkdir(parents=True, exist_ok=True)
    path = artifact_root / "live-media-success.json"
    path.write_text(json.dumps(evidence, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
