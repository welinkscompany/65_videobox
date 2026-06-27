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
    OVERLAY = "overlay"


@dataclass(slots=True, frozen=True)
class RecommendationRecord:
    recommendation_id: str
    project_id: str
    target_segment_id: str
    recommendation_type: RecommendationType
    reason: str
    score: float
    auto_apply_allowed: bool
    review_required: bool
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
        recommendation_id: str | None = None,
    ) -> "RecommendationRecord":
        review_required = recommendation_type is RecommendationType.TTS_REPLACEMENT
        return cls(
            recommendation_id=recommendation_id or f"rec_{uuid4().hex[:12]}",
            project_id=project_id,
            target_segment_id=target_segment_id,
            recommendation_type=recommendation_type,
            reason=reason,
            score=score,
            auto_apply_allowed=not review_required,
            review_required=review_required,
            created_at=_utc_now(),
        )
