"""Identity primitives for revision-bound exact preview artifacts."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from math import isfinite
from typing import Any, Mapping

from videobox_core_engine.composition_plan import COMPOSITION_VERSION, CaptionCue, CompositionPlan

EXACT_PREVIEW_PROFILE = "proxy_720p_h264_aac_v1"


def _canonical(value: Any) -> str:
    def encode(item: object) -> object:
        if is_dataclass(item):
            return asdict(item)
        raise TypeError(f"exact_preview_noncanonical_value:{type(item).__name__}")
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=encode)


@dataclass(frozen=True, slots=True)
class ExactPreviewRequest:
    session_id: str
    expected_revision: int
    start_sec: float | None = None
    end_sec: float | None = None
    profile: str = EXACT_PREVIEW_PROFILE

    def __post_init__(self) -> None:
        if not self.session_id or self.expected_revision < 1 or self.profile != EXACT_PREVIEW_PROFILE:
            raise ValueError("exact_preview_invalid_request")
        if (self.start_sec is None) != (self.end_sec is None):
            raise ValueError("exact_preview_invalid_range")
        if self.start_sec is not None and (
            not isfinite(float(self.start_sec))
            or self.end_sec is None
            or not isfinite(float(self.end_sec))
            or self.start_sec < 0
            or self.end_sec <= self.start_sec
        ):
            raise ValueError("exact_preview_invalid_range")

    def validate_duration(self, duration_sec: float) -> None:
        if not isfinite(float(duration_sec)) or duration_sec < 0 or (self.end_sec is not None and self.end_sec > duration_sec):
            raise ValueError("exact_preview_invalid_range")

    def cache_key(self, *, source_fingerprint: str) -> str:
        return "sha256:" + hashlib.sha256(_canonical({"session_id": self.session_id, "expected_revision": self.expected_revision, "start_sec": self.start_sec, "end_sec": self.end_sec, "profile": self.profile, "source_fingerprint": source_fingerprint}).encode()).hexdigest()


def fingerprint_exact_preview(*, plan: CompositionPlan, session_captions: object, used_asset_sha256: Mapping[str, str], overlay_inputs: object | None = None, settings: object | None = None, profile: str = EXACT_PREVIEW_PROFILE) -> str:
    if profile != EXACT_PREVIEW_PROFILE:
        raise ValueError("exact_preview_invalid_profile")
    value = {"plan": plan.canonical_dict(), "session_captions": session_captions, "used_asset_sha256": dict(sorted(used_asset_sha256.items())), "overlay_inputs": {} if overlay_inputs is None else overlay_inputs, "settings": {} if settings is None else settings, "composition_version": COMPOSITION_VERSION, "profile": profile}
    return "sha256:" + hashlib.sha256(_canonical(value).encode()).hexdigest()


__all__ = ["EXACT_PREVIEW_PROFILE", "ExactPreviewRequest", "fingerprint_exact_preview"]
