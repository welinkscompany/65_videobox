from __future__ import annotations

from uuid import uuid4

from videobox_domain_models.recommendations import RecommendationRecord
from videobox_domain_models.segments import SegmentRecord
from videobox_timeline_schema.models import (
    TimelineClip,
    TimelineRecord,
    TimelineReviewFlag,
    TimelineTrack,
)


class TimelineBuilder:
    def build(
        self,
        *,
        project_id: str,
        segments: list[SegmentRecord],
        recommendations: list[RecommendationRecord],
    ) -> TimelineRecord:
        clips = [
            TimelineClip(
                clip_id=f"clip_{index + 1:03d}",
                segment_id=segment.segment_id,
                asset_uri=f"local://projects/{project_id}/segments/{segment.segment_id}",
                start_sec=segment.start_sec,
                end_sec=segment.end_sec,
            )
            for index, segment in enumerate(segments)
        ]
        review_flags: list[TimelineReviewFlag] = []
        for segment in segments:
            if segment.review_required:
                review_flags.append(
                    TimelineReviewFlag(
                        code="segment_review_required",
                        segment_id=segment.segment_id,
                        message="Segment requires operator review before export.",
                    )
                )
        for recommendation in recommendations:
            if recommendation.review_required:
                review_flags.append(
                    TimelineReviewFlag(
                        code=f"{recommendation.recommendation_type.value}_review_required",
                        segment_id=recommendation.target_segment_id,
                        message=recommendation.reason,
                    )
                )
        return TimelineRecord(
            timeline_id=f"timeline_{uuid4().hex[:12]}",
            project_id=project_id,
            version="v001",
            output_mode="review",
            tracks=[
                TimelineTrack(
                    track_id="narration_primary",
                    track_type="narration",
                    clips=clips,
                )
            ],
            review_flags=review_flags,
        )
