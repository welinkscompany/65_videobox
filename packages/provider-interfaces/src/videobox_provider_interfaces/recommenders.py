from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from videobox_domain_models.recommendations import RecommendationType


@dataclass(slots=True, frozen=True)
class RecommendationRequest:
    project_id: str
    recommendation_type: RecommendationType
    segments: list[dict[str, Any]]
    assets: list[dict[str, Any]]


@dataclass(slots=True, frozen=True)
class RecommendationCandidate:
    target_segment_id: str
    selected_asset_id: str | None
    score: float
    reason: str
    auto_apply_allowed: bool
    review_required: bool
    payload: dict[str, Any]


class RecommendationProvider(Protocol):
    provider_name: str

    def recommend(self, request: RecommendationRequest) -> list[RecommendationCandidate]:
        """Return recommendation candidates for the given segments."""
