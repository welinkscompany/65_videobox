from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RecommendationType(StrEnum):
    TTS_REPLACEMENT = "tts_replacement"
    BROLL = "broll"
    BGM = "bgm"
    SFX = "sfx"
    OVERLAY = "overlay"


@dataclass(slots=True, frozen=True)
class RecommendationRecord:
    recommendation_id: str
    project_id: str
    target_segment_id: str
    recommendation_type: RecommendationType
    selected_asset_id: str | None
    reason: str
    score: float
    auto_apply_allowed: bool
    review_required: bool
    payload: dict[str, object] | None
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        target_segment_id: str,
        recommendation_type: RecommendationType,
        reason: str,
        score: float,
        selected_asset_id: str | None = None,
        payload: dict[str, object] | None = None,
        recommendation_id: str | None = None,
    ) -> "RecommendationRecord":
        review_required = recommendation_type is RecommendationType.TTS_REPLACEMENT
        return cls(
            recommendation_id=recommendation_id or f"rec_{uuid4().hex[:12]}",
            project_id=project_id,
            target_segment_id=target_segment_id,
            recommendation_type=recommendation_type,
            selected_asset_id=selected_asset_id,
            reason=reason,
            score=score,
            auto_apply_allowed=not review_required,
            review_required=review_required,
            payload=payload,
            created_at=_utc_now(),
        )
