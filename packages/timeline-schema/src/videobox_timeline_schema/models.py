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
    asset_id: str | None = None
    media_controls: dict[str, object] = field(default_factory=dict)
    expected_content_sha256: str | None = None
    media_revision: str | None = None
    warning_provenance: list[str] = field(default_factory=list)
    # 앞 장면에서 이 클립으로 넘어오는 방법(`{"type", "duration_sec", "chosen_by"}`).
    # **경계에 붙는 값**이라 들어오는 쪽에 싣는다 -- 경계는 이 클립의 시작 시각
    # 하나로 정해지므로 양쪽에 두면 서로 어긋날 자리가 생긴다.
    # 값의 뜻과 허용 범위는 `videobox_core_engine.transitions`가 정한다.
    transition: dict[str, object] | None = None


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
    caption_segments: list[dict[str, object]] = field(default_factory=list)
    narration_source_uri: str | None = None
    export_overlays: list[dict[str, object]] = field(default_factory=list)
    review_status: str = "draft"
    applied_recommendations: list[dict[str, object]] = field(default_factory=list)
    pending_recommendations: list[dict[str, object]] = field(default_factory=list)
    recommendation_decisions: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    source_session_id: str | None = None
    source_session_revision: int | None = None
    source_variant_id: str | None = None
    source_variant_revision: int | None = None
