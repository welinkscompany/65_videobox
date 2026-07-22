from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
import json
import tempfile
import warnings

from videobox_core_engine.canonical_boolish import (
    normalize_strict_boolish as _normalize_runtime_boolish,
)
from videobox_core_engine.canonical_operator_review_text import (
    canonical_operator_review_text as _canonical_runtime_operator_review_text,
)
from videobox_core_engine.canonical_recommendation import (
    canonical_recommendation_type as _canonical_runtime_recommendation_type,
    VALID_CANONICAL_RECOMMENDATION_TYPES as VALID_RESTORED_RECOMMENDATION_TYPES,
)
from videobox_core_engine.canonical_review_status import (
    canonical_review_status as _canonical_runtime_review_status,
)
from videobox_core_engine.canonical_source_uri import (
    canonical_source_uri as _canonical_runtime_source_uri,
)
from videobox_core_engine.canonical_review_flag import (
    canonical_review_flag_code as _canonical_runtime_review_flag_code,
    VALID_CANONICAL_REVIEW_FLAG_CODES as VALID_RUNTIME_BLOCKING_REVIEW_FLAG_CODES,
)
from videobox_core_engine.canonical_track import (
    canonical_track_type as _canonical_runtime_track_type,
    VALID_CANONICAL_TRACK_TYPES as VALID_RUNTIME_TRACK_TYPES,
)
from videobox_capcut_export import CapCutExportAdapter
from videobox_storage.local_project_store import EditingSessionRevisionConflict, sha256_file
from videobox_domain_models.assets import AssetType
from videobox_core_engine.auto_cut import AutoCutPlanner
from videobox_core_engine.ffmpeg_auto_cut_executor import FfmpegAutoCutExecutor
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_core_engine.editing_session import (
    build_editing_session,
    build_fixed_track_timeline,
    build_selected_range_preview,
    preview_caption_style_scope,
    update_caption_style,
    build_partial_regeneration_request,
    clear_segment_broll_override,
    clear_segment_music_override,
    clear_segment_sfx_override,
    clear_segment_visual_overlays,
    merge_adjacent_segments,
    redo,
    reorder_segments,
    clear_segment_tts_replacement,
    remove_segment_explanation_card,
    remove_segment_image_overlay,
    remove_segment_table_overlay,
    select_segment_tts_replacement,
    set_segment_bounds,
    set_timeline_placement_overrides,
    split_segment,
    undo,
    update_segment_explanation_card,
    update_segment_image_overlay,
    update_segment_broll_override,
    update_segment_caption,
    update_segment_cut_action,
    update_segment_music_override,
    update_segment_sfx_override,
    update_segment_table_overlay,
    update_segment_visual_overlay,
)
from videobox_core_engine.composition_plan import materialize_editing_session_timeline
from videobox_core_engine.timeline_placements import apply_placement_changes, collect_timeline_placements
from videobox_core_engine.output_operator_copy import (
    OutputOperatorCopyBuilder,
    StaticOutputOperatorCopyBuilder,
)
from videobox_core_engine.preview_renderer import PreviewRenderer
from videobox_core_engine.provider_trace import build_provider_trace
from videobox_core_engine.recommenders import KeywordBrollRecommender, RuleBasedMusicRecommender
from videobox_core_engine.review_action_mutations import (
    apply_approved_recommendation_to_timeline,
    extract_pending_recommendation_decision,
    filtered_review_flags_after_recommendation_decision,
    timeline_recommendation_decisions,
)
from videobox_core_engine.review_guidance import HeuristicReviewGuidanceBuilder, ReviewGuidanceBuilder
from videobox_core_engine.script_scene_planner import HeuristicSegmentAnalyzer, SegmentAnalyzer
from videobox_core_engine.timeline_builder import TimelineBuilder
from videobox_core_engine.transcript_alignment import HeuristicTranscriptAligner, TranscriptAligner
from videobox_domain_models.assets import AssetType
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_domain_models.recommendations import RecommendationType
from videobox_provider_interfaces.recommenders import RecommendationProvider, RecommendationRequest
from videobox_provider_interfaces.stt import MockSTTProvider, STTProvider, STTRequest
from videobox_provider_interfaces.tts import TTSRequest
from videobox_storage.local_project_store import LocalProjectStore
from videobox_core_engine._pipeline_shared_helpers import (
    _build_review_guidance_reuse_key,
    _canonical_runtime_pending_recommendation_reason,
    _canonical_runtime_review_flag_message,
    _is_runtime_blocking_pending_recommendation,
    _is_runtime_blocking_review_flag,
    _is_valid_runtime_overlay,
    _normalize_runtime_cut_action,
    _normalized_runtime_pending_recommendations,
    _runtime_pending_recommendation_identity_key,
)


class EditingSessionConflict(RuntimeError):
    def __init__(self, latest_session: dict[str, Any]) -> None:
        super().__init__("Editing session revision is stale.")
        self.latest_session = latest_session


class EditingSessionRegenerationMixin:
    def _resolve_project_asset_identity(
        self, *, project_id: str, asset_id: str, expected_type: AssetType | None = None,
    ) -> dict[str, str]:
        """Return the project-local immutable identity captured at selection.

        A session override is an output authority, not merely a browser UI
        choice.  Preserve the selected file's digest and registration revision
        next to its URI so both final render and the exact-preview proxy can
        reject a replacement before handing bytes to ffmpeg.
        """
        try:
            asset = self.store.get_asset(project_id=project_id, asset_id=asset_id)
            if expected_type is not None and asset.get("asset_type") != expected_type.value:
                raise ValueError("asset_missing")
            storage_uri = str(asset.get("storage_uri") or "")
            resolved_path = self.store.resolve_storage_uri(project_id=project_id, storage_uri=storage_uri)
            if not resolved_path.is_file():
                raise ValueError("asset_missing")
            return {
                "asset_uri": storage_uri,
                "expected_content_sha256": sha256_file(resolved_path),
                "media_revision": str(asset.get("created_at") or ""),
            }
        except (KeyError, ValueError):
            raise ValueError("asset_missing") from None

    def _resolve_project_audio_override(self, *, project_id: str, asset_id: str, expected_type: AssetType) -> str:
        return self._resolve_project_asset_identity(
            project_id=project_id, asset_id=asset_id, expected_type=expected_type,
        )["asset_uri"]

    @staticmethod
    def _persist_override_identity(
        *, updated_session: dict[str, Any], segment_id: str, field: str, identity: dict[str, str],
    ) -> None:
        for segment in updated_session.get("segments", []):
            if str(segment.get("segment_id") or "") == segment_id and isinstance(segment.get(field), dict):
                segment[field].update(identity)
                return
        raise KeyError(f"Segment not found in editing session: {segment_id}")

    @staticmethod
    def _persist_image_overlay_identity(
        *, updated_session: dict[str, Any], segment_id: str, asset_id: str, identity: dict[str, str],
    ) -> None:
        for segment in updated_session.get("segments", []):
            if str(segment.get("segment_id") or "") != segment_id:
                continue
            overlays = segment.get("visual_overlays")
            if not isinstance(overlays, list):
                break
            for overlay in reversed(overlays):
                if isinstance(overlay, dict) and str(overlay.get("asset_id") or "") == asset_id:
                    overlay.update(identity)
                    return
            break
        raise KeyError(f"Image overlay not found in editing session: {segment_id}")

    def _save_editing_session_with_revision(
        self,
        *,
        project_id: str,
        session_id: str,
        session: dict[str, Any],
        updated_session: dict[str, Any],
        expected_revision: int,
    ) -> dict[str, Any]:
        if int(session.get("session_revision") or 1) != expected_revision:
            raise EditingSessionConflict(session)
        try:
            return self.store.update_editing_session(
                project_id=project_id,
                session_id=session_id,
                session_payload=updated_session,
                expected_revision=expected_revision,
            )
        except EditingSessionRevisionConflict:
            raise EditingSessionConflict(
                self.store.get_editing_session(project_id=project_id, session_id=session_id)
            ) from None

    def preview_editing_session_caption_style_scope(self, *, project_id: str, session_id: str, scope: str, segment_ids: list[str]) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        return {"affected_segment_ids": preview_caption_style_scope(session=session, scope=scope, segment_ids=segment_ids)}

    def get_editing_session_fixed_timeline(self, *, project_id: str, session_id: str) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        return build_fixed_track_timeline(session=session)

    def preview_editing_session_selected_range(self, *, project_id: str, session_id: str, start_sec: float, end_sec: float) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        return build_selected_range_preview(session=session, start_sec=start_sec, end_sec=end_sec)

    def split_editing_session_segment(self, *, project_id: str, session_id: str, segment_id: str, split_sec: float, expected_revision: int) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=split_segment(session=session, segment_id=segment_id, split_sec=split_sec), expected_revision=expected_revision)

    def merge_editing_session_segments(self, *, project_id: str, session_id: str, left_segment_id: str, right_segment_id: str, expected_revision: int) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=merge_adjacent_segments(session=session, left_segment_id=left_segment_id, right_segment_id=right_segment_id), expected_revision=expected_revision)

    def set_editing_session_segment_bounds(self, *, project_id: str, session_id: str, segment_id: str, start_sec: float, end_sec: float, expected_revision: int) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=set_segment_bounds(session=session, segment_id=segment_id, start_sec=start_sec, end_sec=end_sec), expected_revision=expected_revision)

    def reorder_editing_session_segments(self, *, project_id: str, session_id: str, segment_ids: list[str], bounds_by_id: dict[str, dict[str, float]] | None, expected_revision: int) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=reorder_segments(session=session, segment_ids=segment_ids, bounds_by_id=bounds_by_id), expected_revision=expected_revision)

    def update_editing_session_timeline_placements(self, *, project_id: str, session_id: str, changes: list[dict[str, object]], expected_revision: int) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        source_timeline = self.store.get_timeline_run(project_id=project_id, timeline_id=str(session["timeline_id"]))
        materialized = materialize_editing_session_timeline(timeline=source_timeline, editing_session=session, project_id=project_id)
        output = source_timeline.get("output") if isinstance(source_timeline.get("output"), dict) else {}
        duration_sec = float(output.get("duration_sec") or max((float(item.get("end_sec") or 0.0) for track in materialized.get("tracks", []) if isinstance(track, dict) for item in track.get("clips", []) if isinstance(item, dict)), default=0.0))
        fps_num, fps_den = int(source_timeline.get("fps_num") or 30), int(source_timeline.get("fps_den") or 1)
        normalized = apply_placement_changes(placements=collect_timeline_placements(timeline=materialized), changes=changes, output_duration_sec=duration_sec, fps_num=fps_num, fps_den=fps_den)
        previous = session.get("timeline_placement_overrides") if isinstance(session.get("timeline_placement_overrides"), dict) else {}
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=set_timeline_placement_overrides(session=session, overrides={**previous, **normalized}), expected_revision=expected_revision)

    def undo_editing_session(self, *, project_id: str, session_id: str, expected_revision: int) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=undo(session=session), expected_revision=expected_revision)

    def redo_editing_session(self, *, project_id: str, session_id: str, expected_revision: int) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=redo(session=session), expected_revision=expected_revision)

    def update_editing_session_caption_style(self, *, project_id: str, session_id: str, style: dict[str, Any], scope: str, segment_ids: list[str], expected_revision: int) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated = update_caption_style(session=session, style=style, scope=scope, segment_ids=segment_ids)
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=updated, expected_revision=expected_revision)
    def update_editing_session_segment_caption(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        caption_text: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = update_segment_caption(
            session=session,
            segment_id=segment_id,
            caption_text=caption_text,
        )
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=updated_session, expected_revision=expected_revision)

    def get_editing_session(self, *, project_id: str, session_id: str) -> dict[str, Any]:
        return self.store.get_editing_session(project_id=project_id, session_id=session_id)

    def get_latest_editing_session(self, *, project_id: str) -> dict[str, Any]:
        return self.store.get_latest_editing_session(project_id=project_id)

    def update_editing_session_segment_cut_action(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        cut_action: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = update_segment_cut_action(
            session=session,
            segment_id=segment_id,
            cut_action=cut_action,
        )
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=updated_session, expected_revision=expected_revision)

    def update_editing_session_segment_broll_override(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        asset_id: str,
        media_controls: dict[str, Any] | None = None,
        expected_revision: int,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        # The browser must not be the source of truth for a local file digest.
        # Resolve and hash the registered project asset at mutation time so a
        # manual B-roll placement has the same immutable provenance as a
        # Director materialized candidate.
        asset = self.store.get_asset(project_id=project_id, asset_id=asset_id)
        if asset.get("asset_type") != AssetType.BROLL_VIDEO.value:
            raise ValueError("asset_missing")
        source = self.store.resolve_storage_uri(project_id=project_id, storage_uri=str(asset["storage_uri"]))
        if not source.is_file():
            raise FileNotFoundError(f"Manual B-roll source is unavailable: {asset_id}")
        identity_controls = {
            **dict(media_controls or {}),
            "expected_content_sha256": sha256_file(source),
            "media_revision": str(asset.get("created_at") or ""),
        }
        updated_session = update_segment_broll_override(
            session=session,
            segment_id=segment_id,
            asset_id=asset_id,
            media_controls=identity_controls,
        )
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=updated_session, expected_revision=expected_revision)

    def clear_editing_session_segment_broll_override(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = clear_segment_broll_override(
            session=session,
            segment_id=segment_id,
        )
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=updated_session, expected_revision=expected_revision)

    def build_editing_session_partial_regeneration_request(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_ids: list[str],
        fields: list[str],
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        return build_partial_regeneration_request(
            session=session,
            segment_ids=segment_ids,
            fields=fields,
        )

    def start_editing_session_partial_regeneration(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_ids: list[str],
        fields: list[str],
        expected_revision: int,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        captured_revision = int(session.get("session_revision") or 1)
        if captured_revision != expected_revision:
            raise EditingSessionConflict(session)
        request = build_partial_regeneration_request(
            session=session,
            segment_ids=segment_ids,
            fields=fields,
        )
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.PARTIAL_REGENERATION,
            input_ref=session_id,
            status=JobStatus.RUNNING,
        )
        published_timeline_id: str | None = None
        refreshed_session: dict[str, Any] | None = None
        partial_regeneration_id: str | None = None
        try:
            result = self._execute_partial_regeneration(
                project_id=project_id,
                session=session,
                request=request,
                output_session_revision=captured_revision + 1,
            )
            published_timeline_id = str(result["timeline_id"])
            try:
                refreshed_session = self.store.update_editing_session(
                    project_id=project_id,
                    session_id=session_id,
                    session_payload=session,
                    timeline_id=result["timeline_id"],
                    expected_revision=captured_revision,
                    invalidate_output_freshness=False,
                )
            except EditingSessionRevisionConflict:
                discard = getattr(self.store, "discard_partial_regeneration_timeline", None)
                if callable(discard):
                    discard(project_id=project_id, timeline_id=str(result["timeline_id"]))
                latest_session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
                raise EditingSessionConflict(latest_session) from None
            persisted = self.store.save_partial_regeneration_run(
                project_id=project_id,
                payload={
                    **result,
                    "session_updated_at": refreshed_session["updated_at"],
                },
            )
            partial_regeneration_id = str(persisted["partial_regeneration_id"])
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.SUCCEEDED,
                output_ref=persisted["partial_regeneration_id"],
            )
        except Exception as exc:
            # If the session CAS succeeded but publication of its regeneration
            # record/job failed, return the session to the prior durable
            # timeline and remove the otherwise-unreachable candidate output.
            cleanup_errors: list[str] = []
            if refreshed_session is not None and published_timeline_id is not None:
                try:
                    restore = getattr(self.store, "restore_editing_session_after_failed_publication", None)
                    if callable(restore):
                        restore(
                            project_id=project_id,
                            session_id=session_id,
                            session_payload=session,
                            expected_revision=int(refreshed_session["session_revision"]),
                        )
                    else:
                        self.store.update_editing_session(
                            project_id=project_id,
                            session_id=session_id,
                            session_payload=session,
                            timeline_id=str(session["timeline_id"]),
                            expected_revision=int(refreshed_session["session_revision"]),
                        )
                    discard = getattr(self.store, "discard_partial_regeneration_timeline", None)
                    if callable(discard):
                        discard(project_id=project_id, timeline_id=published_timeline_id)
                except EditingSessionRevisionConflict:
                    # A later user edit won the CAS; never overwrite that
                    # durable state while compensating this failed job.
                    pass
                except Exception as cleanup_exc:
                    cleanup_errors.append(str(cleanup_exc))
                    mark_cleanup_needed = getattr(self.store, "mark_partial_regeneration_cleanup_needed", None)
                    if callable(mark_cleanup_needed):
                        try:
                            mark_cleanup_needed(
                                project_id=project_id,
                                timeline_id=published_timeline_id,
                            )
                        except Exception as marker_exc:
                            cleanup_errors.append(str(marker_exc))
            if partial_regeneration_id is not None:
                discard_run = getattr(self.store, "discard_partial_regeneration_run", None)
                if callable(discard_run):
                    try:
                        discard_run(
                            project_id=project_id,
                            partial_regeneration_id=partial_regeneration_id,
                        )
                    except Exception as cleanup_exc:
                        cleanup_errors.append(str(cleanup_exc))
            error_message = str(exc)
            if cleanup_errors:
                error_message = f"{error_message}; cleanup reconciliation pending: {'; '.join(cleanup_errors)}"
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=error_message,
            )
            raise
        return {
            "job_id": job["job_id"],
            "status": JobStatus.SUCCEEDED.value,
            "session_id": session_id,
            "segment_ids": request["segment_ids"],
            "fields": request["fields"],
            "downstream_steps": request["downstream_steps"],
        }

    def get_partial_regeneration_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        result = self.store.get_partial_regeneration_run(
            project_id=project_id,
            partial_regeneration_id=str(job["output_ref"]),
        )
        result["timeline"] = self._hydrate_timeline_review_status(
            project_id=project_id,
            timeline=result["timeline"],
        )
        return {
            "job_id": job["job_id"],
            "status": job["status"],
            **result,
        }

    def _hydrate_timeline_review_status(
        self,
        *,
        project_id: str,
        timeline: dict[str, Any],
    ) -> dict[str, Any]:
        review_state = self.store.get_review_state(
            project_id=project_id,
            timeline_id=str(timeline["timeline_id"]),
        )
        review_flags = self._normalized_timeline_review_flags(timeline)
        blocker_review_flags, pending_recommendations = self._normalized_timeline_blockers(timeline)
        applied_recommendations = timeline.get("applied_recommendations", [])
        if not isinstance(applied_recommendations, list):
            applied_recommendations = []
        else:
            applied_recommendations = [
                item
                for item in applied_recommendations
                if isinstance(item, dict)
                and _canonical_runtime_recommendation_type(item.get("recommendation_type"))
                in VALID_RESTORED_RECOMMENDATION_TYPES
                and not _is_runtime_blocking_pending_recommendation(item)
            ]
        timeline["applied_recommendations"] = applied_recommendations
        timeline["review_flags"] = review_flags
        timeline["pending_recommendations"] = pending_recommendations
        timeline["review_status"] = (
            "blocked" if blocker_review_flags or pending_recommendations else review_state["status"]
        )
        return timeline

    def update_editing_session_segment_visual_overlay(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        overlay_type: str,
        asset_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = update_segment_visual_overlay(
            session=session,
            segment_id=segment_id,
            overlay_type=overlay_type,
            asset_id=asset_id,
        )
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=updated_session, expected_revision=expected_revision)

    def clear_editing_session_segment_visual_overlays(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = clear_segment_visual_overlays(
            session=session,
            segment_id=segment_id,
        )
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=updated_session, expected_revision=expected_revision)

    def update_editing_session_segment_explanation_card(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        title: str,
        body: str,
        text: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = update_segment_explanation_card(
            session=session,
            segment_id=segment_id,
            title=title,
            body=body,
            text=text,
        )
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=updated_session, expected_revision=expected_revision)

    def remove_editing_session_segment_explanation_card(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = remove_segment_explanation_card(
            session=session,
            segment_id=segment_id,
        )
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=updated_session, expected_revision=expected_revision)

    def update_editing_session_segment_image_overlay(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        asset_id: str,
        text: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = update_segment_image_overlay(
            session=session,
            segment_id=segment_id,
            asset_id=asset_id,
            text=text,
        )
        # Existing legacy sessions can still contain assetless cards.  A real
        # project asset, however, becomes a renderable source and must carry a
        # durable identity from the moment the user selects it.
        try:
            identity = self._resolve_project_asset_identity(project_id=project_id, asset_id=asset_id)
        except ValueError:
            identity = None
        if identity is not None:
            self._persist_image_overlay_identity(
                updated_session=updated_session, segment_id=segment_id, asset_id=asset_id, identity=identity,
            )
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=updated_session, expected_revision=expected_revision)

    def update_editing_session_segment_table_overlay(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        columns: list[str],
        rows: list[list[str]],
        text: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = update_segment_table_overlay(
            session=session,
            segment_id=segment_id,
            columns=columns,
            rows=rows,
            text=text,
        )
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=updated_session, expected_revision=expected_revision)

    def remove_editing_session_segment_image_overlay(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = remove_segment_image_overlay(
            session=session,
            segment_id=segment_id,
        )
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=updated_session, expected_revision=expected_revision)

    def remove_editing_session_segment_table_overlay(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = remove_segment_table_overlay(
            session=session,
            segment_id=segment_id,
        )
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=updated_session, expected_revision=expected_revision)

    def update_editing_session_segment_music_override(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        asset_id: str,
        media_controls: dict[str, Any] | None = None,
        expected_revision: int,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        identity = self._resolve_project_asset_identity(
            project_id=project_id, asset_id=asset_id, expected_type=AssetType.BGM,
        )
        updated_session = update_segment_music_override(
            session=session,
            segment_id=segment_id,
            asset_id=asset_id,
            asset_uri=identity["asset_uri"],
            media_controls=media_controls,
        )
        self._persist_override_identity(
            updated_session=updated_session, segment_id=segment_id, field="music_override", identity=identity,
        )
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=updated_session, expected_revision=expected_revision)

    def clear_editing_session_segment_music_override(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = clear_segment_music_override(
            session=session,
            segment_id=segment_id,
        )
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=updated_session, expected_revision=expected_revision)

    def update_editing_session_segment_sfx_override(self, *, project_id: str, session_id: str, segment_id: str, asset_id: str, media_controls: dict[str, Any] | None = None, expected_revision: int) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        identity = self._resolve_project_asset_identity(
            project_id=project_id, asset_id=asset_id, expected_type=AssetType.SFX,
        )
        updated_session = update_segment_sfx_override(
            session=session, segment_id=segment_id, asset_id=asset_id,
            asset_uri=identity["asset_uri"], media_controls=media_controls,
        )
        self._persist_override_identity(
            updated_session=updated_session, segment_id=segment_id, field="sfx_override", identity=identity,
        )
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=updated_session, expected_revision=expected_revision)

    def clear_editing_session_segment_sfx_override(self, *, project_id: str, session_id: str, segment_id: str, expected_revision: int) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=clear_segment_sfx_override(session=session, segment_id=segment_id), expected_revision=expected_revision)

    def select_editing_session_segment_tts_replacement(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        recommendation_id: str,
        asset_id: str,
        media_controls: dict[str, Any] | None = None,
        expected_revision: int,
    ) -> dict[str, Any]:
        try:
            candidate = self.store.get_tts_candidate(
                project_id=project_id,
                candidate_id=recommendation_id,
            )
        except KeyError:
            if recommendation_id.startswith("tts_candidate_"):
                raise
            candidate = None
        if candidate is None:
            # Legacy/imported narration replacements are not personal-voice candidates.
            # Only persisted personal-voice candidate IDs require listening approval.
            session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
            updated_session = select_segment_tts_replacement(
                session=session,
                segment_id=segment_id,
                recommendation_id=recommendation_id,
                asset_id=asset_id,
            )
            return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=updated_session, expected_revision=expected_revision)
        if candidate["segment_id"] != segment_id:
            raise ValueError("TTS candidate does not belong to the requested segment.")
        if candidate["asset_id"] != asset_id:
            raise ValueError("TTS candidate asset does not match the requested replacement.")
        if candidate["technical_status"] != "accepted":
            raise ValueError("TTS candidate failed technical acceptance and cannot replace narration.")
        if candidate["operator_review_status"] != "approved":
            raise ValueError("TTS candidate requires listening approval before it can replace narration.")
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = select_segment_tts_replacement(
            session=session,
            segment_id=segment_id,
            recommendation_id=recommendation_id,
            asset_id=asset_id,
        )
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=updated_session, expected_revision=expected_revision)

    def clear_editing_session_segment_tts_replacement(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = clear_segment_tts_replacement(
            session=session,
            segment_id=segment_id,
        )
        return self._save_editing_session_with_revision(project_id=project_id, session_id=session_id, session=session, updated_session=updated_session, expected_revision=expected_revision)

