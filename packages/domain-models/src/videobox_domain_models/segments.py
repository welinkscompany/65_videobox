from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True, frozen=True)
class SegmentRecord:
    segment_id: str
    project_id: str
    text: str
    start_sec: float
    end_sec: float
    confidence: float
    review_required: bool
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        text: str,
        start_sec: float,
        end_sec: float,
        confidence: float = 1.0,
        review_required: bool = False,
        segment_id: str | None = None,
    ) -> "SegmentRecord":
        return cls(
            segment_id=segment_id or f"seg_{uuid4().hex[:12]}",
            project_id=project_id,
            text=text,
            start_sec=start_sec,
            end_sec=end_sec,
            confidence=confidence,
            review_required=review_required,
            created_at=_utc_now(),
        )
