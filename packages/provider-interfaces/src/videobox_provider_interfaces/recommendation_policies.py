from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class RecommendationGuardrail:
    auto_apply_allowed: bool
    review_required: bool


def get_recommendation_guardrail(recommendation_type: str) -> RecommendationGuardrail:
    if recommendation_type == "tts_replacement":
        return RecommendationGuardrail(
            auto_apply_allowed=False,
            review_required=True,
        )
    if recommendation_type in {"broll", "bgm", "overlay"}:
        return RecommendationGuardrail(
            auto_apply_allowed=True,
            review_required=False,
        )
    return RecommendationGuardrail(
        auto_apply_allowed=True,
        review_required=False,
    )
