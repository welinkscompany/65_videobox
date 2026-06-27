from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True, frozen=True)
class TimelineClip:
    clip_id: str
    segment_id: str
    asset_uri: str
    start_sec: float
    end_sec: float
    clip_type: str = "narration"
    recommendation_id: str | None = None


@dataclass(slots=True, frozen=True)
class TimelineTrack:
    track_id: str
    track_type: str
    clips: list[TimelineClip] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class TimelineReviewFlag:
    code: str
    segment_id: str
    message: str


@dataclass(slots=True, frozen=True)
class TimelineRecord:
    timeline_id: str
    project_id: str
    version: str
    output_mode: str
    tracks: list[TimelineTrack]
    review_flags: list[TimelineReviewFlag]
    review_status: str = "draft"
    applied_recommendations: list[dict[str, object]] = field(default_factory=list)
    pending_recommendations: list[dict[str, object]] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utc_now)
