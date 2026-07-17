from __future__ import annotations

from videobox_domain_models.recommendations import RecommendationType


VALID_CANONICAL_RECOMMENDATION_TYPES = {
    RecommendationType.TTS_REPLACEMENT.value,
    RecommendationType.BROLL.value,
    RecommendationType.BGM.value,
    RecommendationType.SFX.value,
    RecommendationType.OVERLAY.value,
}


def canonical_recommendation_type(value: object) -> str:
    return str(value or "").strip().lower()
