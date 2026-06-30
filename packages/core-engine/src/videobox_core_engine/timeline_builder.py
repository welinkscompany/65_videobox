from __future__ import annotations

from dataclasses import asdict
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
        segments: list[dict[str, object] | SegmentRecord],
        recommendations: list[dict[str, object] | RecommendationRecord],
        narration_source_uri: str | None = None,
        export_overlays: list[dict[str, object]] | None = None,
    ) -> TimelineRecord:
        normalized_segments = [self._segment_payload(segment) for segment in segments]
        normalized_recommendations = [
            self._recommendation_payload(recommendation)
            for recommendation in recommendations
        ]
        applied_recommendations: list[dict[str, object]] = []
        pending_recommendations: list[dict[str, object]] = []
        review_flags: list[TimelineReviewFlag] = []

        by_segment: dict[str, list[dict[str, object]]] = {}
        for recommendation in normalized_recommendations:
            by_segment.setdefault(str(recommendation["target_segment_id"]), []).append(recommendation)
            needs_review = (
                bool(recommendation.get("review_required"))
                or not bool(recommendation.get("auto_apply_allowed", False))
            )
            if needs_review:
                review_flags.append(
                    TimelineReviewFlag(
                        code=f"{recommendation['recommendation_type']}_review_required",
                        segment_id=str(recommendation["target_segment_id"]),
                        message=str(recommendation["reason"]),
                    )
                )

        narration_clips: list[TimelineClip] = []
        broll_clips: list[TimelineClip] = []
        music_clips: list[TimelineClip] = []

        for index, segment in enumerate(normalized_segments, start=1):
            segment_id = str(segment["segment_id"])
            narration_asset_uri = f"local://projects/{project_id}/segments/{segment_id}"
            for recommendation in by_segment.get(segment_id, []):
                if (
                    str(recommendation.get("recommendation_type") or "") == "tts_replacement"
                    and bool(recommendation.get("auto_apply_allowed"))
                    and not bool(recommendation.get("review_required"))
                ):
                    payload = recommendation.get("payload")
                    if not isinstance(payload, dict):
                        payload = {}
                    selected_asset_uri = str(payload.get("selected_asset_uri") or "").strip()
                    if selected_asset_uri:
                        narration_asset_uri = selected_asset_uri
                    break
            narration_clips.append(
                TimelineClip(
                    clip_id=f"clip_narration_{index:03d}",
                    segment_id=segment_id,
                    asset_uri=narration_asset_uri,
                    start_sec=float(segment["start_sec"]),
                    end_sec=float(segment["end_sec"]),
                    clip_type="narration",
                )
            )
            if bool(segment.get("review_required")):
                review_flags.append(
                    TimelineReviewFlag(
                        code="segment_review_required",
                        segment_id=segment_id,
                        message="Segment requires operator review before export.",
                    )
                )
            for recommendation in by_segment.get(segment_id, []):
                if bool(recommendation.get("auto_apply_allowed")) and not bool(recommendation.get("review_required")):
                    applied_recommendations.append(recommendation)
                    rec_type = str(recommendation["recommendation_type"])
                    if rec_type == "broll" and recommendation.get("selected_asset_id"):
                        broll_clips.append(
                            TimelineClip(
                                clip_id=f"clip_broll_{len(broll_clips) + 1:03d}",
                                segment_id=segment_id,
                                asset_uri=f"local://projects/{project_id}/assets/{recommendation['selected_asset_id']}",
                                start_sec=float(segment["start_sec"]),
                                end_sec=float(segment["end_sec"]),
                                clip_type="broll",
                                recommendation_id=str(recommendation["recommendation_id"]),
                            )
                        )
                    if rec_type == "bgm":
                        music_clips.append(
                            TimelineClip(
                                clip_id=f"clip_bgm_{len(music_clips) + 1:03d}",
                                segment_id=segment_id,
                                asset_uri=f"local://projects/{project_id}/music/{recommendation['selected_asset_id'] or 'suggested'}",
                                start_sec=float(segment["start_sec"]),
                                end_sec=float(segment["end_sec"]),
                                clip_type="bgm",
                                recommendation_id=str(recommendation["recommendation_id"]),
                            )
                        )
                else:
                    pending_recommendations.append(recommendation)

        tracks = [TimelineTrack(track_id="narration_primary", track_type="narration", clips=narration_clips)]
        if broll_clips:
            tracks.append(TimelineTrack(track_id="broll_overlay", track_type="broll", clips=broll_clips))
        if music_clips:
            tracks.append(TimelineTrack(track_id="music_bed", track_type="bgm", clips=music_clips))

        return TimelineRecord(
            timeline_id=f"timeline_{uuid4().hex[:12]}",
            project_id=project_id,
            version="v001",
            output_mode="review",
            tracks=tracks,
            review_flags=review_flags,
            narration_source_uri=narration_source_uri,
            export_overlays=export_overlays or [],
            applied_recommendations=applied_recommendations,
            pending_recommendations=pending_recommendations,
            recommendation_decisions={},
        )

    def _segment_payload(self, segment: dict[str, object] | SegmentRecord) -> dict[str, object]:
        if isinstance(segment, SegmentRecord):
            return {
                "segment_id": segment.segment_id,
                "text": segment.text,
                "start_sec": segment.start_sec,
                "end_sec": segment.end_sec,
                "confidence": segment.confidence,
                "review_required": segment.review_required,
                "cleanup_decision": "review" if segment.review_required else "keep",
            }
        return dict(segment)

    def _recommendation_payload(
        self,
        recommendation: dict[str, object] | RecommendationRecord,
    ) -> dict[str, object]:
        if isinstance(recommendation, RecommendationRecord):
            return {
                "recommendation_id": recommendation.recommendation_id,
                "target_segment_id": recommendation.target_segment_id,
                "recommendation_type": recommendation.recommendation_type.value,
                "selected_asset_id": recommendation.selected_asset_id,
                "score": recommendation.score,
                "reason": recommendation.reason,
                "auto_apply_allowed": recommendation.auto_apply_allowed,
                "review_required": recommendation.review_required,
                "payload": recommendation.payload or {},
                "created_at": recommendation.created_at.isoformat(),
            }
        return dict(recommendation)

    def build_review_snapshot(
        self,
        *,
        project_id: str,
        timeline_id: str,
        segments: list[dict[str, object]],
        recommendations: list[dict[str, object]],
        timeline_review_flags: list[TimelineReviewFlag],
    ) -> dict[str, object]:
        applied_recommendations = [
            recommendation
            for recommendation in recommendations
            if bool(recommendation.get("auto_apply_allowed")) and not bool(recommendation.get("review_required"))
        ]
        pending_recommendations = [
            recommendation
            for recommendation in recommendations
            if not bool(recommendation.get("auto_apply_allowed")) or bool(recommendation.get("review_required"))
        ]
        return {
            "project_id": project_id,
            "timeline_id": timeline_id,
            "segments": segments,
            "applied_recommendations": applied_recommendations,
            "pending_recommendations": pending_recommendations,
            "review_flags": [asdict(flag) for flag in timeline_review_flags],
        }
