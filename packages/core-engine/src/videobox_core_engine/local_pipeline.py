from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import tempfile
import uuid
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
from videobox_core_engine.auto_cut import AutoCutPlanner
from videobox_core_engine.capcut_handoff import CapCutHandoffError, CapCutHandoffService
from videobox_core_engine.ffmpeg_auto_cut_executor import FfmpegAutoCutExecutor
from videobox_core_engine.ffmpeg_final_renderer import FinalRenderError, FfmpegFinalRenderer
from videobox_core_engine.composition_plan import CompositionPlan, materialize_editing_session_timeline
from videobox_core_engine.exact_preview import ExactPreviewRequest, fingerprint_exact_preview
from videobox_storage.timeline_clip_source_resolution import TimelineClipSourceError, resolve_generic_asset_uri
from videobox_core_engine.output_source_verifier import (
    OutputSourceStaleError,
    capture_output_source_snapshots,
    verify_output_freshness,
    verify_output_source_snapshots,
)
from videobox_core_engine.ass_subtitles import render_editing_session_ass
from videobox_core_engine.thumbnail_generator import ThumbnailGenerationError, generate_video_thumbnail
from videobox_core_engine.tts_acceptance import assess_tts_audio
from videobox_core_engine.editing_session import (
    build_editing_session,
    build_partial_regeneration_request,
    clear_segment_broll_override,
    clear_segment_music_override,
    clear_segment_visual_overlays,
    clear_segment_tts_replacement,
    remove_segment_explanation_card,
    remove_segment_image_overlay,
    remove_segment_table_overlay,
    select_segment_tts_replacement,
    update_segment_explanation_card,
    update_segment_image_overlay,
    update_segment_broll_override,
    update_segment_caption,
    update_segment_cut_action,
    update_segment_music_override,
    update_segment_table_overlay,
    update_segment_visual_overlay,
)
from videobox_core_engine.script_draft_session import (
    apply_narration_alignment_to_script_draft,
    build_provisional_script_draft_session,
)
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
from videobox_storage.local_project_store import EditingSessionRevisionConflict, LocalProjectStore, sha256_file
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
from videobox_core_engine.editing_session_and_regeneration import EditingSessionConflict, EditingSessionRegenerationMixin
from videobox_core_engine._pipeline_private_helpers import _PipelinePrivateHelpersMixin


@dataclass(frozen=True)
class _ExactPreviewSourceRevalidation:
    """Full-hash result plus a constant-time publish-boundary file check."""

    is_current: bool
    file_stats: tuple[tuple[Path, int, int], ...] = ()

    def still_matches(self) -> bool:
        if not self.is_current:
            return False
        try:
            for path, expected_size, expected_mtime_ns in self.file_stats:
                stat = path.stat()
                if not path.is_file() or stat.st_size != expected_size or stat.st_mtime_ns != expected_mtime_ns:
                    return False
            return True
        except OSError:
            return False


class LocalPipelineRunner(EditingSessionRegenerationMixin, _PipelinePrivateHelpersMixin):
    def __init__(
        self,
        store: LocalProjectStore,
        *,
        stt_provider: STTProvider | None = None,
        segment_analyzer: SegmentAnalyzer | None = None,
        broll_recommender: RecommendationProvider | None = None,
        music_recommender: RecommendationProvider | None = None,
        review_guidance_builder: ReviewGuidanceBuilder | None = None,
        output_operator_copy_builder: OutputOperatorCopyBuilder | None = None,
        timeline_builder: TimelineBuilder | None = None,
        preview_renderer: PreviewRenderer | None = None,
        capcut_exporter: CapCutExportAdapter | None = None,
        auto_cut_planner: AutoCutPlanner | None = None,
        auto_cut_executor: FfmpegAutoCutExecutor | None = None,
        final_renderer: FfmpegFinalRenderer | None = None,
        pycapcut_exporter: Any | None = None,
        capcut_handoff_service: CapCutHandoffService | None = None,
        tts_provider: Any | None = None,
        transcript_aligner: TranscriptAligner | None = None,
    ) -> None:
        self.store = store
        self.stt_provider = stt_provider or MockSTTProvider()
        self.segment_analyzer = segment_analyzer or HeuristicSegmentAnalyzer()
        self.broll_recommender = broll_recommender or KeywordBrollRecommender()
        self.music_recommender = music_recommender or RuleBasedMusicRecommender()
        self.review_guidance_builder = review_guidance_builder or HeuristicReviewGuidanceBuilder()
        self.output_operator_copy_builder = output_operator_copy_builder or StaticOutputOperatorCopyBuilder()
        self.timeline_builder = timeline_builder or TimelineBuilder()
        self.preview_renderer = preview_renderer or PreviewRenderer(store=self.store)
        self.capcut_exporter = capcut_exporter or CapCutExportAdapter()
        self.auto_cut_planner = auto_cut_planner or AutoCutPlanner()
        self.auto_cut_executor = auto_cut_executor or FfmpegAutoCutExecutor(planner=self.auto_cut_planner)
        self.final_renderer = final_renderer or FfmpegFinalRenderer(store=store)
        # No eager default: pycapcut pulls in Windows-only automation deps that
        # aren't installed by default, so this stays unset unless the caller
        # (create_app, when CapCutDraftExportConfig.enabled) explicitly injects one.
        self.pycapcut_exporter = pycapcut_exporter
        self.capcut_handoff_service = capcut_handoff_service or CapCutHandoffService()
        # No eager default: gtts needs network access, elevenlabs needs an API
        # key, and local_xtts needs a heavy optional install — none of these
        # should run implicitly for callers/tests that don't opt in.
        self.tts_provider = tts_provider
        self.transcript_aligner = transcript_aligner or HeuristicTranscriptAligner()

    def build_composition_plan(
        self, *, timeline: dict[str, Any], editing_session: dict[str, Any] | None = None,
        project_id: str | None = None,
    ) -> CompositionPlan:
        """Extract the one pure plan/caption input for output consumers.

        It has no job, provider, or mutation side effect.  Task 2 will use the
        returned plan plus the same session captions to build both final and
        proxy ffmpeg commands.
        """
        materialized_timeline = materialize_editing_session_timeline(
            timeline=timeline, editing_session=editing_session,
            project_id=project_id or str(timeline.get("project_id") or "") or None,
        )
        captions = materialized_timeline.get("session_captions") if isinstance(materialized_timeline.get("session_captions"), list) else [
            segment for segment in (editing_session.get("segments", []) if isinstance(editing_session, dict) else [])
            if isinstance(segment, dict) and str(segment.get("cut_action") or "keep") != "remove"
        ]
        extractor = getattr(self.final_renderer, "extract_composition_plan", None)
        # Existing callers intentionally inject small recording renderers.  A
        # missing optional extraction hook is a compatibility case, whereas an
        # exception from a real hook remains authoritative and must propagate.
        if callable(extractor):
            return extractor(timeline=materialized_timeline, captions=captions)
        return CompositionPlan.from_timeline(timeline=materialized_timeline, captions=captions)

    def _exact_preview_inputs(
        self, *, project_id: str, session_id: str, start_sec: float | None = None, end_sec: float | None = None
    ) -> tuple[dict[str, Any], dict[str, Any], CompositionPlan, str]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        source_timeline = self.store.get_timeline_run(project_id=project_id, timeline_id=str(session["timeline_id"]))
        timeline = materialize_editing_session_timeline(
            timeline=source_timeline, editing_session=session, project_id=project_id,
        )
        plan = self.build_composition_plan(timeline=source_timeline, editing_session=session, project_id=project_id)
        full_duration_sec = plan.duration_sec
        if start_sec is not None or end_sec is not None:
            if start_sec is None or end_sec is None:
                raise ValueError("exact_preview_invalid_range")
            ExactPreviewRequest(
                session_id=session_id, expected_revision=int(session["session_revision"]), start_sec=float(start_sec), end_sec=float(end_sec),
            ).validate_duration(full_duration_sec)
            plan = plan.for_range(start_sec=float(start_sec), end_sec=float(end_sec))
        used_asset_sha256: dict[str, str] = {}
        for item in plan.items:
            identity = item.asset_id or f"{item.track_type}:{item.clip_id}"
            try:
                if item.track_type == "narration":
                    source = self.final_renderer._resolve_narration_clip_source(
                        project_id=project_id, timeline=timeline,
                        clip={"asset_uri": item.asset_uri, "start_sec": item.start_sec, "end_sec": item.end_sec},
                    ).path
                else:
                    source = resolve_generic_asset_uri(
                        store=self.store, project_id=project_id, asset_uri=str(item.asset_uri or "")
                    )
                used_asset_sha256[identity] = sha256_file(source) if source.is_file() else f"missing:{identity}"
            except (KeyError, OSError, ValueError, TimelineClipSourceError, FinalRenderError):
                # A request still gets a durable, fenced generation so the
                # worker can report an explicit recoverable failed state.
                used_asset_sha256[identity] = f"missing:{identity}"
        resolved_overlays: list[dict[str, Any]] = []
        for index, overlay in enumerate(plan.export_overlays):
            normalized = dict(overlay)
            asset_uri = str(normalized.get("asset_uri") or "")
            asset_id = str(normalized.get("asset_id") or "")
            if not asset_uri and asset_id:
                asset_uri = f"local://projects/{project_id}/assets/{asset_id}"
            if asset_uri:
                identity = f"export_overlay:{asset_id or index}"
                try:
                    source = resolve_generic_asset_uri(store=self.store, project_id=project_id, asset_uri=asset_uri)
                    used_asset_sha256[identity] = sha256_file(source) if source.is_file() else f"missing:{identity}"
                except (KeyError, OSError, ValueError, TimelineClipSourceError):
                    used_asset_sha256[identity] = f"missing:{identity}"
            resolved_overlays.append(normalized)
        fingerprint = fingerprint_exact_preview(
            plan=plan,
            session_captions=plan.captions,
            used_asset_sha256=used_asset_sha256,
            overlay_inputs=resolved_overlays,
            settings={"canvas": plan.canonical_dict()["canvas"]},
        )
        return session, timeline, plan, fingerprint

    def _capture_exact_preview_source_snapshots(
        self, *, project_id: str, session: dict[str, Any], timeline: dict[str, Any], plan: CompositionPlan,
    ) -> dict[Path, str] | None:
        """Capture byte identities for the exact worker's local inputs.

        ``finish_exact_preview`` owns the SQLite writer lock while publishing.
        Its fence must therefore not rebuild the plan through store accessors:
        those open schema-initializing SQLite connections and self-deadlock on
        Windows.  The session revision is verified by the storage transaction;
        Revalidation hashes run *before* the storage writer transaction.  The
        transaction subsequently consumes the captured boolean plus its own
        session CAS, avoiding a multi-second writer lock on large media.
        """
        expected_by_path: dict[Path, str] = {}
        try:
            for item in plan.items:
                if item.track_type == "narration":
                    path = self.final_renderer._resolve_narration_clip_source(
                        project_id=project_id, timeline=timeline,
                        clip={"asset_uri": item.asset_uri, "start_sec": item.start_sec, "end_sec": item.end_sec},
                    ).path
                else:
                    path = resolve_generic_asset_uri(
                        store=self.store, project_id=project_id, asset_uri=str(item.asset_uri or ""),
                    )
                if not path.is_file():
                    raise FileNotFoundError(path)
                expected_by_path[path.resolve()] = sha256_file(path)
            for overlay in plan.export_overlays:
                asset_uri = str(overlay.get("asset_uri") or "")
                asset_id = str(overlay.get("asset_id") or "")
                if not asset_uri and asset_id:
                    asset_uri = f"local://projects/{project_id}/assets/{asset_id}"
                if not asset_uri:
                    continue
                path = resolve_generic_asset_uri(store=self.store, project_id=project_id, asset_uri=asset_uri)
                if not path.is_file():
                    raise FileNotFoundError(path)
                expected_by_path[path.resolve()] = sha256_file(path)
            timeline_path = self.store.project_root(project_id) / "timelines" / f"{session['timeline_id']}.json"
            if not timeline_path.is_file():
                raise FileNotFoundError(timeline_path)
            expected_by_path[timeline_path.resolve()] = sha256_file(timeline_path)
        except (KeyError, OSError, ValueError, TimelineClipSourceError, FinalRenderError):
            return None
        return expected_by_path

    @staticmethod
    def _revalidate_exact_preview_source_snapshots(
        snapshots: dict[Path, str] | None,
    ) -> _ExactPreviewSourceRevalidation:
        """Full-hash exact-preview inputs outside the durable writer lock."""
        if snapshots is None:
            return _ExactPreviewSourceRevalidation(is_current=False)
        try:
            file_stats: list[tuple[Path, int, int]] = []
            for path, expected in snapshots.items():
                before = path.stat()
                if not path.is_file() or sha256_file(path) != expected:
                    return _ExactPreviewSourceRevalidation(is_current=False)
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    return _ExactPreviewSourceRevalidation(is_current=False)
                file_stats.append((path, after.st_size, after.st_mtime_ns))
            return _ExactPreviewSourceRevalidation(is_current=True, file_stats=tuple(file_stats))
        except OSError:
            return _ExactPreviewSourceRevalidation(is_current=False)

    def start_exact_preview(
        self, *, project_id: str, session_id: str, expected_revision: int, start_sec: float | None = None, end_sec: float | None = None
    ) -> dict[str, Any]:
        # A fresh API/pipeline process may inherit a durable ``running`` claim
        # from a worker that died.  Recover only claims older than the store's
        # bounded threshold before cache coalescing, so live owners retain
        # their generation/owner fence and late completion still cannot win.
        self.store.recover_inherited_exact_preview_claims(
            project_id=project_id, process_epoch=str(self.store.exact_preview_process_epoch),
        )
        self.store.recover_stale_exact_preview_claims(project_id=project_id)
        self._best_effort_cleanup_exact_previews(project_id=project_id)
        session, _timeline, plan, fingerprint = self._exact_preview_inputs(
            project_id=project_id, session_id=session_id, start_sec=start_sec, end_sec=end_sec
        )
        if int(session["session_revision"]) != expected_revision:
            raise EditingSessionConflict(session)
        request = ExactPreviewRequest(
            session_id=session_id, expected_revision=expected_revision, start_sec=start_sec, end_sec=end_sec
        )
        return self.store.begin_exact_preview(
            project_id=project_id, request=request, fingerprint=fingerprint, duration_sec=plan.duration_sec,
            source_duration_sec=self.build_composition_plan(
                timeline=self.store.get_timeline_run(project_id=project_id, timeline_id=str(session["timeline_id"])),
                editing_session=session, project_id=project_id,
            ).duration_sec,
        )

    def run_exact_preview(self, *, project_id: str, generation_id: str) -> None:
        record = self.store.get_exact_preview(project_id=project_id, generation_id=generation_id)
        owner_token = f"exact-preview-worker:{self.store.exact_preview_process_epoch}:{uuid.uuid4().hex}"
        if not self.store.claim_exact_preview(project_id=project_id, generation_id=generation_id, owner_token=owner_token):
            return
        try:
            session, timeline, plan, fingerprint = self._exact_preview_inputs(
                project_id=project_id,
                session_id=str(record["session_id"]),
                start_sec=record.get("start_sec"), end_sec=record.get("end_sec"),
            )
            if int(session["session_revision"]) != int(record["expected_revision"]) or fingerprint != str(record["fingerprint"]):
                self.store.mark_exact_preview_stale(project_id=project_id, generation_id=generation_id, reason="source_fingerprint_changed")
                return
            source_snapshots = self._capture_exact_preview_source_snapshots(
                project_id=project_id, session=session, timeline=timeline, plan=plan,
            )
            with tempfile.TemporaryDirectory(prefix="videobox_exact_preview_") as raw_dir:
                raw = Path(raw_dir)
                ass_path = raw / "captions.ass"
                ass_path.write_text(
                    render_editing_session_ass(
                        {"caption_style": session.get("caption_style") or {}, "segments": [
                            {"caption_text": cue.text, "caption_style": cue.style, "start_sec": cue.start_sec, "end_sec": cue.end_sec}
                            for cue in plan.captions
                        ]},
                        video_width=plan.width,
                        video_height=plan.height,
                    ),
                    encoding="utf-8",
                )
                output_path = raw / "exact-preview.mp4"
                self.final_renderer.render_exact_preview_to_mp4(
                    project_id=project_id, composition_plan=plan, timeline_context=timeline,
                    output_path=output_path, subtitle_ass_path=ass_path,
                )
                # Rendering can take long enough for media bytes or session
                # materialization to change.  Rebuild immediately before the
                # durable publish and never publish a mismatched proxy.
                source_revalidation = self._revalidate_exact_preview_source_snapshots(source_snapshots)
                if not source_revalidation.is_current:
                    self.store.mark_exact_preview_stale(
                        project_id=project_id, generation_id=generation_id, reason="publish_revalidation_failed",
                    )
                    return
                if not self.store.finish_exact_preview(
                    project_id=project_id, generation_id=generation_id, fingerprint=fingerprint,
                    artifact_path=output_path, owner_token=owner_token,
                    source_fence_result=source_revalidation.is_current,
                    source_fence=lambda _connection: source_revalidation.still_matches(),
                ):
                    return
        except Exception as exc:
            self.store.fail_exact_preview(
                project_id=project_id, generation_id=generation_id, owner_token=owner_token, error_message=str(exc)
            )
        finally:
            self._best_effort_cleanup_exact_previews(project_id=project_id)

    def _best_effort_cleanup_exact_previews(self, *, project_id: str) -> None:
        """Bound preview retention without allowing cleanup faults to reject work."""
        try:
            self.store.cleanup_exact_preview_artifacts(
                project_id=project_id,
                keep_last=5,
                orphan_older_than_seconds=300,
            )
        except Exception:
            # Generation records and their owner fences are authoritative.
            # Cleanup is deliberately non-authoritative maintenance only.
            return

    def get_exact_preview_status(self, *, project_id: str, generation_id: str) -> dict[str, Any]:
        record = self.store.get_exact_preview(project_id=project_id, generation_id=generation_id)
        # Every read is a fence: source replacement or session edits make a
        # previously-successful MP4 unavailable before its URL can be exposed.
        if record["state"] in {"pending", "running", "succeeded"}:
            try:
                session, _timeline, _plan, fingerprint = self._exact_preview_inputs(
                    project_id=project_id, session_id=str(record["session_id"]),
                    start_sec=record.get("start_sec"), end_sec=record.get("end_sec"),
                )
                if int(session["session_revision"]) != int(record["expected_revision"]) or fingerprint != str(record["fingerprint"]):
                    self.store.mark_exact_preview_stale(project_id=project_id, generation_id=generation_id, reason="read_revalidation_failed")
                    record = self.store.get_exact_preview(project_id=project_id, generation_id=generation_id)
            except Exception:
                self.store.mark_exact_preview_stale(project_id=project_id, generation_id=generation_id, reason="source_unavailable")
                record = self.store.get_exact_preview(project_id=project_id, generation_id=generation_id)
        return record

    def register_narration_asset(self, *, project_id: str, source_path: Path) -> dict[str, Any]:
        asset = self.store.register_asset(
            project_id=project_id,
            asset_type=AssetType.NARRATION_AUDIO,
            source_path=source_path,
        )
        return self._asset_payload(asset)

    def register_script_asset(self, *, project_id: str, source_path: Path) -> dict[str, Any]:
        asset = self.store.register_asset(
            project_id=project_id,
            asset_type=AssetType.SCRIPT_DOCUMENT,
            source_path=source_path,
        )
        return self._asset_payload(asset)

    def create_creation_brief(self, *, runtime: object, **kwargs: Any) -> dict[str, Any]:
        """Keep script-first intake on the local pipeline boundary.

        Retained-input atomicity remains owned by ``LocalProjectStore``; this
        adapter deliberately constructs no provider or network transport.
        """
        return self.store.create_creation_brief(runtime=runtime, **kwargs)

    def register_broll_asset(
        self,
        *,
        project_id: str,
        source_path: Path,
        title: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        asset = self.store.register_asset(
            project_id=project_id,
            asset_type=AssetType.BROLL_VIDEO,
            source_path=source_path,
            metadata={"title": title or source_path.stem, "tags": tags or []},
        )
        self._try_generate_broll_thumbnail(project_id=project_id, asset=asset)
        return self._asset_payload(asset)

    def _try_generate_broll_thumbnail(self, *, project_id: str, asset: Any) -> None:
        # Best-effort: a fixture/test video that isn't real footage (or a
        # missing ffmpeg binary) shouldn't fail asset registration — the
        # picker just falls back to a text label when no thumbnail exists.
        try:
            video_path = self.store.resolve_storage_uri(project_id=project_id, storage_uri=asset.storage_uri)
            thumbnail_path = self.store.thumbnail_storage_path(project_id=project_id, asset_id=asset.asset_id)
            generate_video_thumbnail(video_path, thumbnail_path)
            self.store.update_asset_metadata(
                project_id=project_id,
                asset_id=asset.asset_id,
                metadata_patch={
                    "thumbnail_uri": self.store.thumbnail_storage_uri(
                        project_id=project_id, asset_id=asset.asset_id
                    )
                },
            )
        except ThumbnailGenerationError:
            pass

    def register_raw_video_asset(self, *, project_id: str, source_path: Path) -> dict[str, Any]:
        asset = self.store.register_asset(
            project_id=project_id,
            asset_type=AssetType.RAW_VIDEO,
            source_path=source_path,
        )
        return self._asset_payload(asset)

    def register_voice_sample_asset(self, *, project_id: str, source_path: Path) -> dict[str, Any]:
        asset = self.store.register_asset(
            project_id=project_id,
            asset_type=AssetType.VOICE_SAMPLE_AUDIO,
            source_path=source_path,
        )
        return self._asset_payload(asset)

    def generate_tts_replacement_candidate(
        self,
        *,
        project_id: str,
        segment_text: str,
        voice_sample_asset_id: str,
        segment_id: str | None = None,
        target_duration_sec: float | None = None,
    ) -> dict[str, Any]:
        if self.tts_provider is None:
            raise RuntimeError(
                "TTS synthesis is not configured. Enable TTSEngineConfig and install the "
                "matching engine package (see requirements-runtime.txt)."
            )
        voice_sample_asset = self.store.get_asset(project_id=project_id, asset_id=voice_sample_asset_id)
        if voice_sample_asset["asset_type"] != AssetType.VOICE_SAMPLE_AUDIO.value:
            raise ValueError("generate_tts_replacement_candidate requires a voice_sample_audio asset.")
        voice_sample_path = self.store.resolve_storage_uri(
            project_id=project_id, storage_uri=voice_sample_asset["storage_uri"]
        )
        try:
            with tempfile.TemporaryDirectory(prefix="videobox_tts_candidate_") as raw_work_dir:
                output_path = Path(raw_work_dir) / "tts_candidate.wav"
                tts_result = self.tts_provider.synthesize(
                    TTSRequest(
                        text=segment_text,
                        voice_sample_uri=str(voice_sample_path),
                        output_path=output_path,
                        target_duration_sec=target_duration_sec,
                    )
                )
                acceptance = (
                    assess_tts_audio(path=output_path, target_duration_sec=target_duration_sec)
                    if target_duration_sec is not None
                    else None
                )
                asset = self.store.register_asset(
                    project_id=project_id,
                    asset_type=AssetType.GENERATED_TTS_AUDIO,
                    source_path=output_path,
                    metadata={"provider_name": tts_result.provider_name, "source_text": segment_text},
                )
        except Exception as exc:
            raise RuntimeError(
                "TTS candidate generation failed; original narration remains selected."
            ) from exc
        # Recorded as a comparable A/B candidate only when the caller
        # associates it with a segment; ad-hoc previews without a segment_id
        # still work exactly as before, just without a saved comparison row.
        if segment_id:
            candidate = self.store.save_tts_candidate(
                project_id=project_id,
                segment_id=segment_id,
                asset_id=asset.asset_id,
                source_text=segment_text,
                acceptance=acceptance,
            )
            return {**self._asset_payload(asset), **candidate}
        return self._asset_payload(asset)

    def register_sfx_asset(self, *, project_id: str, source_path: Path) -> dict[str, Any]:
        asset = self.store.register_asset(
            project_id=project_id,
            asset_type=AssetType.SFX,
            source_path=source_path,
        )
        return self._asset_payload(asset)

    def list_tts_replacement_candidates(self, *, project_id: str, segment_id: str) -> list[dict[str, Any]]:
        return self.store.list_tts_candidates(project_id=project_id, segment_id=segment_id)

    def review_tts_replacement_candidate(
        self,
        *,
        project_id: str,
        candidate_id: str,
        decision: str,
    ) -> dict[str, Any]:
        return self.store.update_tts_candidate_listening_review(
            project_id=project_id,
            candidate_id=candidate_id,
            decision=decision,
        )

    def run_auto_cut_detection(self, *, project_id: str, raw_video_asset_id: str) -> dict[str, Any]:
        asset = self.store.get_asset(project_id=project_id, asset_id=raw_video_asset_id)
        if asset["asset_type"] != AssetType.RAW_VIDEO.value:
            raise ValueError("auto_cut detection requires a raw_video asset.")
        asset_path = self.store.resolve_storage_uri(project_id=project_id, storage_uri=asset["storage_uri"])
        detection = self.auto_cut_executor.run_full_detection(asset_path)
        return self.plan_auto_cut_segments(
            project_id=project_id,
            raw_video_asset_id=raw_video_asset_id,
            total_duration=detection["total_duration"],
            scene_timestamps=detection["scene_timestamps"],
            black_regions=detection["black_regions"],
            segment_samples=detection["segment_samples"],
        )

    def plan_auto_cut_segments(
        self,
        *,
        project_id: str,
        raw_video_asset_id: str,
        total_duration: float,
        scene_timestamps: list[float],
        black_regions: list[dict[str, float]],
        segment_samples: list[dict[str, Any]],
    ) -> dict[str, Any]:
        asset = self.store.get_asset(project_id=project_id, asset_id=raw_video_asset_id)
        if asset["asset_type"] != AssetType.RAW_VIDEO.value:
            raise ValueError("auto_cut planning requires a raw_video asset.")

        should_auto_cut = self.auto_cut_planner.should_auto_cut(total_duration=total_duration)
        planned_segments = (
            self.auto_cut_planner.plan_segments(
                total_duration=total_duration,
                scene_timestamps=scene_timestamps,
                black_regions=black_regions,
            )
            if should_auto_cut
            else []
        )
        if should_auto_cut:
            planned_boundaries = sorted(
                (round(segment.start_sec, 2), round(segment.end_sec, 2))
                for segment in planned_segments
            )
            sample_boundaries = sorted(
                (round(float(sample["start_sec"]), 2), round(float(sample["end_sec"]), 2))
                for sample in segment_samples
            )
            if sample_boundaries != planned_boundaries:
                raise ValueError("auto_cut segment_samples must match planned segment boundaries.")
        kept_segments = (
            sorted(
                self.auto_cut_planner.filter_segments(segment_samples),
                key=lambda segment: (segment.start_sec, segment.end_sec),
            )
            if should_auto_cut
            else []
        )
        return {
            "asset_id": asset["asset_id"],
            "storage_uri": asset["storage_uri"],
            "should_auto_cut": should_auto_cut,
            "scene_detection_filter": self.auto_cut_planner.build_scene_detection_filter(),
            "blackdetect_filter": self.auto_cut_planner.build_blackdetect_filter(),
            "planned_segments": [
                {
                    "start_sec": segment.start_sec,
                    "end_sec": segment.end_sec,
                }
                for segment in planned_segments
            ],
            "kept_segments": [
                {
                    "start_sec": segment.start_sec,
                    "end_sec": segment.end_sec,
                    "duration_sec": segment.duration_sec,
                    "avg_brightness": segment.avg_brightness,
                    "scene_change_count": segment.scene_change_count,
                    "reasons": list(segment.reasons),
                }
                for segment in kept_segments
            ],
        }

    def start_transcription(self, *, project_id: str, narration_asset_id: str) -> dict[str, Any]:
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.TRANSCRIPTION,
            input_ref=narration_asset_id,
            status=JobStatus.RUNNING,
        )
        asset = self.store.get_asset(project_id=project_id, asset_id=narration_asset_id)
        asset_path = self.store.resolve_storage_uri(project_id=project_id, storage_uri=asset["storage_uri"])
        stt_result = self.stt_provider.transcribe(STTRequest(source_path=asset_path))
        transcript = self.store.save_transcript(
            project_id=project_id,
            source_asset_id=narration_asset_id,
            transcript_text=stt_result.text,
            segments=[
                {
                    "start_sec": segment.start_sec,
                    "end_sec": segment.end_sec,
                    "text": segment.text,
                    "confidence": segment.confidence,
                }
                for segment in stt_result.segments
            ],
            provider_name=stt_result.provider_name,
        )
        self.store.update_job(
            project_id=project_id,
            job_id=job["job_id"],
            status=JobStatus.SUCCEEDED,
            output_ref=transcript["transcript_id"],
        )
        return {"job_id": job["job_id"], "status": JobStatus.SUCCEEDED.value}

    def get_transcription_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        transcript = self.store.get_transcript(project_id=project_id, transcript_id=job["output_ref"])
        return {
            "job_id": job["job_id"],
            "status": job["status"],
            "transcript_id": transcript["transcript_id"],
            "transcript_uri": transcript["transcript_uri"],
            "transcript_text": transcript["transcript_text"],
            "segments": transcript["segments"],
        }

    def start_segment_analysis(
        self,
        *,
        project_id: str,
        transcription_job_id: str,
        script_asset_id: str | None,
    ) -> dict[str, Any]:
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.SEGMENT_ANALYSIS,
            input_ref=transcription_job_id,
            status=JobStatus.RUNNING,
        )
        try:
            transcription_job = self.store.get_job(project_id=project_id, job_id=transcription_job_id)
            transcript = self.store.get_transcript(
                project_id=project_id,
                transcript_id=transcription_job["output_ref"],
            )
            script_text = self._load_script_text(project_id=project_id, script_asset_id=script_asset_id)
            aligned_transcript_segments = self.transcript_aligner.align(
                transcript_segments=transcript["segments"],
                script_text=script_text,
            )
        except Exception as exc:
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            raise
        try:
            segments = self.segment_analyzer.analyze(
                project_id=project_id,
                transcript_segments=aligned_transcript_segments,
                script_text=script_text,
            )
        except Exception as exc:
            failed_job = self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            self._save_failed_provider_trace_audit_event(
                project_id=project_id,
                job=failed_job,
                source_job_id=transcription_job_id,
                exc=exc,
            )
            raise
        try:
            analysis = self.store.save_segment_analysis(
                project_id=project_id,
                transcript_id=transcript["transcript_id"],
                script_asset_id=script_asset_id,
                segments=segments,
            )
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.SUCCEEDED,
                output_ref=analysis["segment_analysis_id"],
            )
        except Exception as exc:
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            raise
        return {"job_id": job["job_id"], "status": JobStatus.SUCCEEDED.value}

    def get_segment_analysis_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        analysis = self.store.get_segment_analysis(
            project_id=project_id,
            segment_analysis_id=job["output_ref"],
        )
        return {
            "job_id": job["job_id"],
            "status": job["status"],
            "segment_analysis_id": analysis["segment_analysis_id"],
            "segments": analysis["segments"],
            "file_uri": analysis["file_uri"],
        }

    def start_broll_recommendation(
        self,
        *,
        project_id: str,
        segment_analysis_job_id: str,
    ) -> dict[str, Any]:
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.BROLL_RECOMMENDATION,
            input_ref=segment_analysis_job_id,
            status=JobStatus.RUNNING,
        )
        try:
            analysis = self._load_segment_analysis_from_job(
                project_id=project_id,
                segment_analysis_job_id=segment_analysis_job_id,
            )
            assets = self.store.list_assets(project_id=project_id, asset_type=AssetType.BROLL_VIDEO)
        except Exception as exc:
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            raise
        try:
            candidates = self.broll_recommender.recommend(
                RecommendationRequest(
                    project_id=project_id,
                    recommendation_type=RecommendationType.BROLL,
                    segments=analysis["segments"],
                    assets=assets,
                )
            )
        except Exception as exc:
            failed_job = self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            self._save_failed_provider_trace_audit_event(
                project_id=project_id,
                job=failed_job,
                source_job_id=segment_analysis_job_id,
                exc=exc,
            )
            raise
        try:
            run = self.store.save_recommendation_run(
                project_id=project_id,
                recommendation_type=RecommendationType.BROLL,
                source_job_id=segment_analysis_job_id,
                recommendations=[self._candidate_payload(candidate) for candidate in candidates],
            )
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.SUCCEEDED,
                output_ref=run["recommendation_run_id"],
            )
        except Exception as exc:
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            raise
        return {"job_id": job["job_id"], "status": JobStatus.SUCCEEDED.value}

    def get_broll_recommendation_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        run = self.store.get_recommendation_run(
            project_id=project_id,
            recommendation_run_id=job["output_ref"],
            recommendation_type=RecommendationType.BROLL,
        )
        return {"job_id": job["job_id"], "status": job["status"], "recommendations": run["recommendations"]}

    def start_music_recommendation(
        self,
        *,
        project_id: str,
        segment_analysis_job_id: str,
    ) -> dict[str, Any]:
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.MUSIC_RECOMMENDATION,
            input_ref=segment_analysis_job_id,
            status=JobStatus.RUNNING,
        )
        try:
            analysis = self._load_segment_analysis_from_job(
                project_id=project_id,
                segment_analysis_job_id=segment_analysis_job_id,
            )
        except Exception as exc:
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            raise
        try:
            candidates = self.music_recommender.recommend(
                RecommendationRequest(
                    project_id=project_id,
                    recommendation_type=RecommendationType.BGM,
                    segments=analysis["segments"],
                    assets=[],
                )
            )
        except Exception as exc:
            failed_job = self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            self._save_failed_provider_trace_audit_event(
                project_id=project_id,
                job=failed_job,
                source_job_id=segment_analysis_job_id,
                exc=exc,
            )
            raise
        try:
            run = self.store.save_recommendation_run(
                project_id=project_id,
                recommendation_type=RecommendationType.BGM,
                source_job_id=segment_analysis_job_id,
                recommendations=[self._candidate_payload(candidate) for candidate in candidates],
            )
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.SUCCEEDED,
                output_ref=run["recommendation_run_id"],
            )
        except Exception as exc:
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            raise
        return {"job_id": job["job_id"], "status": JobStatus.SUCCEEDED.value}

    def get_music_recommendation_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        run = self.store.get_recommendation_run(
            project_id=project_id,
            recommendation_run_id=job["output_ref"],
            recommendation_type=RecommendationType.BGM,
        )
        return {"job_id": job["job_id"], "status": job["status"], "recommendations": run["recommendations"]}

    def build_timeline(
        self,
        *,
        project_id: str,
        segment_analysis_job_id: str,
        recommendation_job_ids: list[str],
    ) -> dict[str, Any]:
        analysis = self._load_segment_analysis_from_job(
            project_id=project_id,
            segment_analysis_job_id=segment_analysis_job_id,
        )
        recommendations: list[dict[str, Any]] = []
        for recommendation_job_id in recommendation_job_ids:
            job = self.store.get_job(project_id=project_id, job_id=recommendation_job_id)
            job_type = str(job["job_type"])
            recommendation_type = (
                RecommendationType.BROLL
                if job_type == JobType.BROLL_RECOMMENDATION.value
                else RecommendationType.BGM
            )
            run = self.store.get_recommendation_run(
                project_id=project_id,
                recommendation_run_id=job["output_ref"],
                recommendation_type=recommendation_type,
            )
            recommendations.extend(
                [
                    {
                        **item,
                        "recommendation_type": recommendation_type.value,
                    }
                    for item in run["recommendations"]
                ]
            )
        transcript = self.store.get_transcript(
            project_id=project_id,
            transcript_id=str(analysis["transcript_id"]),
        )
        narration_asset = self.store.get_asset(
            project_id=project_id,
            asset_id=str(transcript["source_asset_id"]),
        )
        timeline = self.timeline_builder.build(
            project_id=project_id,
            segments=analysis["segments"],
            recommendations=recommendations,
            narration_source_uri=str(narration_asset["storage_uri"]),
            asset_uri_validator=lambda asset_id, expected_type, uri: self._is_valid_project_audio_recommendation_uri(asset_id, expected_type, uri, project_id),
        )
        timeline_payload = {
            "project_id": timeline.project_id,
            "narration_source_uri": timeline.narration_source_uri,
            "tracks": [
                {
                    "track_id": track.track_id,
                    "track_type": track.track_type,
                    "clips": [
                        {
                            "clip_id": clip.clip_id,
                            "segment_id": clip.segment_id,
                            "asset_uri": clip.asset_uri,
                            "start_sec": clip.start_sec,
                            "end_sec": clip.end_sec,
                            "clip_type": clip.clip_type,
                            "recommendation_id": clip.recommendation_id,
                            "asset_id": clip.asset_id,
                            "media_controls": clip.media_controls,
                            "expected_content_sha256": clip.expected_content_sha256,
                            "media_revision": clip.media_revision,
                            "warning_provenance": clip.warning_provenance,
                        }
                        for clip in track.clips
                    ],
                }
                for track in timeline.tracks
            ],
            "review_flags": [
                {
                    "code": flag.code,
                    "segment_id": flag.segment_id,
                    "message": flag.message,
                }
                for flag in timeline.review_flags
            ],
            "caption_segments": timeline.caption_segments,
            "applied_recommendations": timeline.applied_recommendations,
            "pending_recommendations": timeline.pending_recommendations,
            "recommendation_decisions": timeline.recommendation_decisions,
            "export_overlays": timeline.export_overlays,
            "lineage": {
                "segment_analysis_job_id": segment_analysis_job_id,
                "recommendation_job_ids": recommendation_job_ids,
            },
        }
        persisted = self.store.save_timeline_run(
            project_id=project_id,
            output_mode=timeline.output_mode,
            timeline_payload=timeline_payload,
        )
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.TIMELINE_BUILD,
            input_ref=segment_analysis_job_id,
            status=JobStatus.RUNNING,
        )
        self.store.update_job(
            project_id=project_id,
            job_id=job["job_id"],
            status=JobStatus.SUCCEEDED,
            output_ref=persisted["timeline_id"],
        )
        return {"job_id": job["job_id"], "status": JobStatus.SUCCEEDED.value}

    def create_editing_session(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        timeline = self.get_timeline_result(project_id=project_id, job_id=timeline_job_id)["timeline"]
        segments = self._segments_for_timeline(project_id=project_id, timeline=timeline)
        session_payload = build_editing_session(
            project_id=project_id,
            timeline=timeline,
            segments=segments,
        )
        return self.store.save_editing_session(
            project_id=project_id,
            timeline_id=str(timeline["timeline_id"]),
            session_payload=session_payload,
        )

    def start_timeline_build(
        self,
        *,
        project_id: str,
        segment_analysis_job_id: str,
        recommendation_job_ids: list[str],
    ) -> dict[str, Any]:
        return self.build_timeline(
            project_id=project_id,
            segment_analysis_job_id=segment_analysis_job_id,
            recommendation_job_ids=recommendation_job_ids,
        )

    def get_timeline_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        if str(job.get("job_type")) == JobType.PARTIAL_REGENERATION.value:
            partial_regeneration = self.store.get_partial_regeneration_run(
                project_id=project_id,
                partial_regeneration_id=str(job["output_ref"]),
            )
            timeline = partial_regeneration["timeline"]
        else:
            timeline = self.store.get_timeline_run(project_id=project_id, timeline_id=job["output_ref"])
        timeline = self._hydrate_timeline_review_status(project_id=project_id, timeline=timeline)
        return {"job_id": job["job_id"], "status": job["status"], "timeline": timeline}

    def get_review_snapshot(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        timeline = self.get_timeline_result(project_id=project_id, job_id=job_id)["timeline"]
        timeline_applied_recommendations = timeline.get("applied_recommendations", [])
        if not isinstance(timeline_applied_recommendations, list):
            timeline_applied_recommendations = []
        else:
            timeline_applied_recommendations = [
                item
                for item in timeline_applied_recommendations
                if isinstance(item, dict) and not _is_runtime_blocking_pending_recommendation(item)
            ]
        timeline_pending_recommendations = timeline.get("pending_recommendations", [])
        if not isinstance(timeline_pending_recommendations, list):
            timeline_pending_recommendations = []
        else:
            timeline_pending_recommendations = [
                item
                for item in timeline_pending_recommendations
                if _is_runtime_blocking_pending_recommendation(item)
            ]
        timeline_review_flags = timeline.get("review_flags", [])
        if not isinstance(timeline_review_flags, list):
            timeline_review_flags = []
        else:
            timeline_review_flags = [
                item for item in timeline_review_flags if _is_runtime_blocking_review_flag(item)
            ]
        snapshot = self.store.build_review_snapshot(
            project_id=project_id,
            timeline_id=str(timeline.get("timeline_id") or ""),
            segments=self.store.list_segments(project_id=project_id),
            timeline_applied_recommendations=deepcopy(timeline_applied_recommendations),
            timeline_pending_recommendations=deepcopy(timeline_pending_recommendations),
            timeline_review_flags=timeline_review_flags,
        )
        snapshot["review_status"] = timeline["review_status"]
        current_review_status = _canonical_runtime_review_status(
            timeline["review_status"],
            default="draft",
        )
        current_operator_guidance_reuse_key = _build_review_guidance_reuse_key(snapshot)
        persisted_review_status = self.store.get_review_state(
            project_id=project_id,
            timeline_id=str(timeline["timeline_id"]),
        )["status"]
        persisted_operator_guidance = self.store.get_persisted_operator_guidance(
            project_id=project_id,
            timeline_id=str(timeline["timeline_id"]),
        )
        persisted_operator_guidance_reuse_key = None
        get_operator_guidance_reuse_key = getattr(
            self.store,
            "get_operator_guidance_reuse_key",
            None,
        )
        if callable(get_operator_guidance_reuse_key):
            persisted_operator_guidance_reuse_key = get_operator_guidance_reuse_key(
                project_id=project_id,
                timeline_id=str(timeline["timeline_id"]),
            )
        should_reuse_persisted_guidance = (
            persisted_operator_guidance is not None and current_review_status == persisted_review_status
        )
        if should_reuse_persisted_guidance and current_review_status == "blocked":
            should_reuse_persisted_guidance = (
                current_operator_guidance_reuse_key is not None
                and persisted_operator_guidance_reuse_key == current_operator_guidance_reuse_key
            )
        if should_reuse_persisted_guidance:
            snapshot["operator_guidance"] = persisted_operator_guidance
            return snapshot
        snapshot["operator_guidance"] = self.review_guidance_builder.build(
            project_id=project_id,
            review_snapshot=snapshot,
        )
        if current_review_status != persisted_review_status:
            return snapshot
        try:
            self.store.save_operator_guidance(
                project_id=project_id,
                timeline_id=str(timeline["timeline_id"]),
                operator_guidance=snapshot["operator_guidance"],
            )
        except Exception as exc:
            self._save_review_guidance_attempt_audit_event(
                project_id=project_id,
                timeline_job_id=job_id,
                timeline_job_type=str(job.get("job_type") or JobType.TIMELINE_BUILD.value),
                timeline_id=str(timeline["timeline_id"]),
                operator_guidance=snapshot["operator_guidance"],
                error_message=str(exc),
            )
            raise
        if current_operator_guidance_reuse_key is not None:
            save_operator_guidance_reuse_key = getattr(
                self.store,
                "save_operator_guidance_reuse_key",
                None,
            )
            if callable(save_operator_guidance_reuse_key):
                try:
                    save_operator_guidance_reuse_key(
                        project_id=project_id,
                        timeline_id=str(timeline["timeline_id"]),
                        reuse_key=current_operator_guidance_reuse_key,
                    )
                except Exception:
                    pass
        return snapshot

    def get_review_snapshot_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.get_review_snapshot(project_id=project_id, job_id=job_id)

    def approve_pending_recommendation(
        self,
        *,
        project_id: str,
        timeline_job_id: str,
        recommendation_id: str,
    ) -> dict[str, Any]:
        (
            original_timeline,
            original_review_state,
            timeline,
            original_recommendation,
            _,
        ) = self._prepare_pending_recommendation_decision(
            project_id=project_id,
            timeline_job_id=timeline_job_id,
            recommendation_id=recommendation_id,
            decision="approved",
        )
        self._persist_pending_recommendation_decision(
            project_id=project_id,
            timeline_job_id=timeline_job_id,
            timeline=timeline,
            recommendation_id=recommendation_id,
            auto_apply_allowed=True,
            review_required=False,
            decision_state="approved",
            rollback_recommendation=original_recommendation,
            original_timeline=original_timeline,
            original_review_status=str(original_review_state["status"]),
        )
        return self.get_review_snapshot(project_id=project_id, job_id=timeline_job_id)

    def reject_pending_recommendation(
        self,
        *,
        project_id: str,
        timeline_job_id: str,
        recommendation_id: str,
    ) -> dict[str, Any]:
        (
            original_timeline,
            original_review_state,
            timeline,
            original_recommendation,
            _,
        ) = self._prepare_pending_recommendation_decision(
            project_id=project_id,
            timeline_job_id=timeline_job_id,
            recommendation_id=recommendation_id,
            decision="rejected",
        )
        self._persist_pending_recommendation_decision(
            project_id=project_id,
            timeline_job_id=timeline_job_id,
            timeline=timeline,
            recommendation_id=recommendation_id,
            auto_apply_allowed=False,
            review_required=False,
            decision_state="rejected",
            rollback_recommendation=original_recommendation,
            original_timeline=original_timeline,
            original_review_status=str(original_review_state["status"]),
        )
        return self.get_review_snapshot(project_id=project_id, job_id=timeline_job_id)

    def approve_timeline_review(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        timeline = self.get_timeline_result(project_id=project_id, job_id=timeline_job_id)["timeline"]
        self._ensure_timeline_has_no_blockers(timeline)
        session = self._editing_session_for_output_timeline(
            project_id=project_id,
            timeline=timeline,
        )
        source_session_revision = None
        if session is not None:
            source_session_revision = int(session["session_revision"])
            self.store.bind_timeline_to_editing_session_revision(
                project_id=project_id,
                timeline_id=str(timeline["timeline_id"]),
                session_id=str(session["session_id"]),
                session_revision=source_session_revision,
            )
        return self.store.save_review_state(
            project_id=project_id,
            timeline_id=str(timeline["timeline_id"]),
            status="approved",
            source_session_revision=source_session_revision,
        )

    def reopen_timeline_review(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        timeline = self.get_timeline_result(project_id=project_id, job_id=timeline_job_id)["timeline"]
        review_flags, pending_recommendations = self._normalized_timeline_blockers(timeline)
        status = "blocked" if review_flags or pending_recommendations else "draft"
        return self.store.save_review_state(
            project_id=project_id,
            timeline_id=str(timeline["timeline_id"]),
            status=status,
        )

    def start_subtitle_render(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.SUBTITLE_RENDER,
            input_ref=timeline_job_id,
            status=JobStatus.RUNNING,
        )
        try:
            timeline = self.get_timeline_result(project_id=project_id, job_id=timeline_job_id)["timeline"]
            self._ensure_timeline_ready_for_output(timeline)
            segments = self._segments_for_timeline(project_id=project_id, timeline=timeline)
            subtitle_payload = {
                "format": "srt",
                "entries": [
                    {
                        "index": index,
                        "start_sec": float(segment["start_sec"]),
                        "end_sec": float(segment["end_sec"]),
                        "text": str(segment["text"]),
                    }
                    for index, segment in enumerate(segments, start=1)
                ],
                "notes": ["Subtitle file generated from approved review timeline."],
            }
            persisted = self.store.save_subtitle_run(
                project_id=project_id,
                timeline_id=str(timeline["timeline_id"]),
                subtitle_payload=subtitle_payload,
            )
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.SUCCEEDED,
                output_ref=persisted["subtitle_id"],
            )
        except Exception as exc:
            failed_job = self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            self._save_failed_provider_trace_audit_event(
                project_id=project_id,
                job=failed_job,
                source_job_id=timeline_job_id,
                exc=exc,
            )
            raise
        return {"job_id": job["job_id"], "status": JobStatus.SUCCEEDED.value}

    def get_subtitle_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        subtitle = self.store.get_subtitle_run(project_id=project_id, subtitle_id=job["output_ref"])
        return {"job_id": job["job_id"], "status": job["status"], "subtitle": subtitle}

    def start_preview_render(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.PREVIEW_RENDER,
            input_ref=timeline_job_id,
            status=JobStatus.RUNNING,
        )
        try:
            timeline = self.get_timeline_result(project_id=project_id, job_id=timeline_job_id)["timeline"]
            self._ensure_timeline_ready_for_output(timeline)
            self._ensure_output_dependencies_fresh(project_id=project_id, timeline=timeline)
            preview_payload = self.preview_renderer.build_preview_payload(project_id=project_id, timeline=timeline)
        except Exception as exc:
            failed_job = self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            self._save_failed_provider_trace_audit_event(
                project_id=project_id,
                job=failed_job,
                source_job_id=timeline_job_id,
                exc=exc,
            )
            raise
        try:
            output_copy = self.output_operator_copy_builder.build(
                project_id=project_id,
                timeline=timeline,
                output_target=JobType.PREVIEW_RENDER.value,
            )
        except Exception as exc:
            failed_job = self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            self._save_failed_provider_trace_audit_event(
                project_id=project_id,
                job=failed_job,
                source_job_id=timeline_job_id,
                exc=exc,
            )
            raise
        try:
            output_copy = self._normalize_output_copy(output_copy)
            preview_payload["notes"] = output_copy["notes"]
            preview_payload["provider_trace"] = output_copy["provider_trace"]
            persisted = self.store.save_preview_run(
                project_id=project_id,
                timeline_id=str(timeline["timeline_id"]),
                preview_payload=preview_payload,
            )
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.SUCCEEDED,
                output_ref=persisted["preview_id"],
            )
        except Exception as exc:
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            raise
        return {"job_id": job["job_id"], "status": JobStatus.SUCCEEDED.value}

    def get_preview_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        preview = self.store.get_preview_run(project_id=project_id, preview_id=job["output_ref"])
        return {"job_id": job["job_id"], "status": job["status"], "preview": preview}

    def start_capcut_export(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.CAPCUT_EXPORT,
            input_ref=timeline_job_id,
            status=JobStatus.RUNNING,
        )
        try:
            timeline = self.get_timeline_result(project_id=project_id, job_id=timeline_job_id)["timeline"]
            self._ensure_timeline_ready_for_output(timeline)
            self._ensure_output_dependencies_fresh(project_id=project_id, timeline=timeline)
            latest_subtitle = self.store.get_latest_subtitle_for_timeline(
                project_id=project_id,
                timeline_id=str(timeline["timeline_id"]),
            )
            export_payload = self.capcut_exporter.build_payload(
                project_id=project_id,
                timeline=timeline,
                subtitle_file_uri=latest_subtitle["file_uri"] if latest_subtitle else None,
            )
        except Exception as exc:
            failed_job = self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            self._save_failed_provider_trace_audit_event(
                project_id=project_id,
                job=failed_job,
                source_job_id=timeline_job_id,
                exc=exc,
            )
            raise
        try:
            output_copy = self.output_operator_copy_builder.build(
                project_id=project_id,
                timeline=timeline,
                output_target=JobType.CAPCUT_EXPORT.value,
                subtitle_file_uri=latest_subtitle["file_uri"] if latest_subtitle else None,
            )
        except Exception as exc:
            failed_job = self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            self._save_failed_provider_trace_audit_event(
                project_id=project_id,
                job=failed_job,
                source_job_id=timeline_job_id,
                exc=exc,
            )
            raise
        try:
            output_copy = self._normalize_output_copy(output_copy)
            export_payload["notes"] = output_copy["notes"]
            export_payload["provider_trace"] = output_copy["provider_trace"]
            persisted = self.store.save_capcut_export(
                project_id=project_id,
                timeline_id=str(timeline["timeline_id"]),
                export_payload=export_payload,
            )
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.SUCCEEDED,
                output_ref=persisted["export_id"],
            )
        except Exception as exc:
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            raise
        return {"job_id": job["job_id"], "status": JobStatus.SUCCEEDED.value}

    def get_capcut_export_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        export = self.store.get_export_run(project_id=project_id, export_id=job["output_ref"])
        return {"job_id": job["job_id"], "status": job["status"], "export": export}

    def start_final_render(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        """Synchronous convenience wrapper: create the job and run it to completion
        inline. Used by direct pipeline callers/tests. Real API usage should prefer
        start_final_render_job + run_final_render_job so the HTTP request does not
        block for the full render duration."""
        self.assert_timeline_output_allowed(project_id=project_id, timeline_job_id=timeline_job_id)
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.FINAL_RENDER,
            input_ref=timeline_job_id,
            status=JobStatus.RUNNING,
        )
        self.run_final_render_job(project_id=project_id, timeline_job_id=timeline_job_id, job=job)
        refreshed_job = self.store.get_job(project_id=project_id, job_id=job["job_id"])
        if refreshed_job["status"] == JobStatus.FAILED.value:
            raise RuntimeError(refreshed_job["error_message"])
        return {"job_id": job["job_id"], "status": refreshed_job["status"]}

    def start_final_render_job(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        """Create a RUNNING final-render job and return immediately. The caller
        (the API layer) is responsible for invoking run_final_render_job in the
        background so the HTTP request does not block for the render duration."""
        self.assert_timeline_output_allowed(project_id=project_id, timeline_job_id=timeline_job_id)
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.FINAL_RENDER,
            input_ref=timeline_job_id,
            status=JobStatus.RUNNING,
        )
        return {"job_id": job["job_id"], "status": job["status"]}

    def run_final_render_job(self, *, project_id: str, timeline_job_id: str, job: dict[str, Any]) -> None:
        try:
            self.assert_timeline_output_allowed(project_id=project_id, timeline_job_id=timeline_job_id)
            timeline = self.get_timeline_result(project_id=project_id, job_id=timeline_job_id)["timeline"]
            self._ensure_timeline_ready_for_output(timeline)
            self._ensure_output_dependencies_fresh(project_id=project_id, timeline=timeline)
            latest_subtitle = self.store.get_latest_subtitle_for_timeline(
                project_id=project_id,
                timeline_id=str(timeline["timeline_id"]),
            )
            subtitle_file_path = (
                self.store.resolve_storage_uri(project_id=project_id, storage_uri=latest_subtitle["file_uri"])
                if latest_subtitle
                else None
            )
            editing_session = self._editing_session_for_output_timeline(project_id=project_id, timeline=timeline)
            materialized_timeline = materialize_editing_session_timeline(
                timeline=timeline, editing_session=editing_session, project_id=project_id,
            )
            # Establish the same immutable timeline/caption input that the
            # exact-preview worker will consume in Task 2.  Rendering remains
            # on the existing final path in this Task 1 extraction slice.
            composition_plan = self.build_composition_plan(
                timeline=timeline, editing_session=editing_session, project_id=project_id,
            )
            with tempfile.TemporaryDirectory(prefix="videobox_final_render_") as raw_render_dir:
                render_output_path = Path(raw_render_dir) / "output.mp4"
                subtitle_ass_path = None
                if editing_session is not None:
                    subtitle_ass_path = Path(raw_render_dir) / "captions.ass"
                    subtitle_ass_path.write_text(
                        render_editing_session_ass(
                            {
                                "caption_style": editing_session.get("caption_style") or {},
                                "segments": [
                                    {"caption_text": cue.text, "caption_style": cue.style, "start_sec": cue.start_sec, "end_sec": cue.end_sec}
                                    for cue in composition_plan.captions
                                ],
                            },
                            video_width=composition_plan.width,
                            video_height=composition_plan.height,
                        ),
                        encoding="utf-8",
                    )
                # Capture every actual materialized composition asset before
                # FFmpeg starts.  The same snapshots are rechecked inside the
                # durable writer fence after the potentially long render.
                source_snapshots = capture_output_source_snapshots(
                    store=self.store, project_id=project_id, timeline=materialized_timeline,
                )
                self.final_renderer.render_timeline_to_mp4(
                    project_id=project_id,
                    timeline=materialized_timeline,
                    output_path=render_output_path,
                    subtitle_file_path=subtitle_file_path,
                    subtitle_ass_path=subtitle_ass_path,
                    composition_plan=composition_plan,
                    on_progress=lambda percent: self.store.update_job_progress(
                        project_id=project_id, job_id=job["job_id"], progress_percent=percent
                    ),
                )
                # The renderer can run for minutes.  Re-check both the durable
                # session/review contract and the *materialized* override inputs
                # before an output file becomes a final-render export.
                self._ensure_output_dependencies_fresh(project_id=project_id, timeline=timeline)

                def final_source_fence(connection: Any) -> bool:
                    # save_final_render executes this after staging the MP4 but
                    # before it inserts the durable export pointer.  Keeping
                    # this check at the storage publish boundary closes the
                    # post-render source TOCTOU window.
                    # The session revision is checked by save_final_render's
                    # transaction.  This deliberately has no store/database
                    # reads: the storage writer lock is already held here.
                    def current_media_revision(asset_id: str) -> str | None:
                        row = connection.execute(
                            """SELECT created_at FROM assets
                               WHERE project_id = ? AND asset_id = ?""",
                            (project_id, asset_id),
                        ).fetchone()
                        return str(row["created_at"]) if row is not None else None

                    verify_output_source_snapshots(
                        source_snapshots,
                        media_revision_lookup=current_media_revision,
                    )
                    return True

                persisted = self.store.save_final_render(
                    project_id=project_id,
                    timeline_id=str(timeline["timeline_id"]),
                    source_output_path=render_output_path,
                    source_session_id=str(editing_session["session_id"]) if editing_session is not None else None,
                    source_session_revision=int(editing_session["session_revision"]) if editing_session is not None else None,
                    source_fence=final_source_fence,
                )
        except Exception as exc:
            failed_job = self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            self._save_failed_provider_trace_audit_event(
                project_id=project_id,
                job=failed_job,
                source_job_id=timeline_job_id,
                exc=exc,
            )
            return
        self.store.update_job(
            project_id=project_id,
            job_id=job["job_id"],
            status=JobStatus.SUCCEEDED,
            output_ref=persisted["export_id"],
        )

    def get_final_render_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        if not job["output_ref"]:
            return {"job_id": job["job_id"], "status": job["status"], "render": None}
        render = self.store.get_final_render_export(project_id=project_id, export_id=job["output_ref"])
        return {"job_id": job["job_id"], "status": job["status"], "render": render}

    def start_capcut_draft_export(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        """Synchronous convenience wrapper: create the job and run it to completion
        inline. Used by direct pipeline callers/tests. Real API usage should prefer
        start_capcut_draft_export_job + run_capcut_draft_export_job so the HTTP
        request does not block for the full export duration."""
        self.assert_timeline_output_allowed(project_id=project_id, timeline_job_id=timeline_job_id)
        job = self.start_capcut_draft_export_job(project_id=project_id, timeline_job_id=timeline_job_id)
        self.run_capcut_draft_export_job(
            project_id=project_id,
            timeline_job_id=timeline_job_id,
            job={"job_id": job["job_id"]},
        )
        refreshed_job = self.store.get_job(project_id=project_id, job_id=job["job_id"])
        if refreshed_job["status"] == JobStatus.FAILED.value:
            raise RuntimeError(refreshed_job["error_message"])
        return {"job_id": job["job_id"], "status": refreshed_job["status"]}

    def start_capcut_draft_export_job(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        """Create a RUNNING CapCut draft export job and return immediately. The
        caller (the API layer) is responsible for invoking run_capcut_draft_export_job
        in the background so the HTTP request does not block for the export duration."""
        self.assert_timeline_output_allowed(project_id=project_id, timeline_job_id=timeline_job_id)
        if self.pycapcut_exporter is None:
            raise RuntimeError(
                "Real CapCut draft export is not configured. Enable CapCutDraftExportConfig "
                "and install the 'pycapcut' package (see requirements-runtime.txt)."
            )
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.CAPCUT_DRAFT_EXPORT,
            input_ref=timeline_job_id,
            status=JobStatus.RUNNING,
        )
        return {"job_id": job["job_id"], "status": job["status"]}

    def run_capcut_draft_export_job(
        self, *, project_id: str, timeline_job_id: str, job: dict[str, Any]
    ) -> None:
        try:
            timeline = self.get_timeline_result(project_id=project_id, job_id=timeline_job_id)["timeline"]
            self._ensure_timeline_ready_for_output(timeline)
            self._ensure_output_dependencies_fresh(project_id=project_id, timeline=timeline)
            latest_subtitle = self.store.get_latest_subtitle_for_timeline(
                project_id=project_id,
                timeline_id=str(timeline["timeline_id"]),
            )
            subtitle_file_path = (
                self.store.resolve_storage_uri(project_id=project_id, storage_uri=latest_subtitle["file_uri"])
                if latest_subtitle
                else None
            )
            editing_session = self._editing_session_for_output_timeline(project_id=project_id, timeline=timeline)
            with tempfile.TemporaryDirectory(prefix="videobox_capcut_draft_") as raw_drafts_root:
                draft_path = self.pycapcut_exporter.export_timeline(
                    project_id=project_id,
                    timeline=timeline,
                    drafts_root=Path(raw_drafts_root),
                    draft_name=str(timeline["timeline_id"]),
                    subtitle_file_path=subtitle_file_path,
                    editing_session=editing_session,
                )
                persisted = self.store.save_capcut_draft_export(
                    project_id=project_id,
                    timeline_id=str(timeline["timeline_id"]),
                    source_draft_path=getattr(draft_path, "draft_path", draft_path),
                    notes=list(getattr(draft_path, "capcut_compatibility_warnings", [])),
                )
        except Exception as exc:
            failed_job = self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            self._save_failed_provider_trace_audit_event(
                project_id=project_id,
                job=failed_job,
                source_job_id=timeline_job_id,
                exc=exc,
            )
            return
        self.store.update_job(
            project_id=project_id,
            job_id=job["job_id"],
            status=JobStatus.SUCCEEDED,
            output_ref=persisted["export_id"],
        )

    def create_script_draft_editing_session(self, *, project_id: str, script_asset_id: str) -> dict[str, Any]:
        asset = self.store.get_asset(project_id=project_id, asset_id=script_asset_id)
        if str(asset.get("asset_type")) != AssetType.SCRIPT_DOCUMENT.value:
            raise ValueError("script_asset_id must reference a script_document asset.")
        script_path = self.store.resolve_storage_uri(project_id=project_id, storage_uri=str(asset["storage_uri"]))
        session_payload = build_provisional_script_draft_session(
            project_id=project_id,
            script_asset_id=script_asset_id,
            script_text=script_path.read_text(encoding="utf-8"),
        )
        return self.store.save_editing_session(
            project_id=project_id,
            timeline_id=str(session_payload["timeline_id"]),
            session_payload=session_payload,
        )

    def apply_script_draft_narration_alignment(
        self,
        *,
        project_id: str,
        session_id: str,
        aligned_segments: list[dict[str, Any]],
        expected_revision: int,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        if int(session.get("session_revision") or 1) != expected_revision:
            raise EditingSessionConflict(session)
        updated, _ = apply_narration_alignment_to_script_draft(session=session, aligned_segments=aligned_segments)
        try:
            return self.store.update_script_draft_alignment_and_stale_proposals(
                project_id=project_id, session_id=session_id, session_payload=updated,
                expected_revision=expected_revision,
                source_script_segment_ids=list(updated.get("stale_proposal_source_script_segment_ids") or []),
            )
        except EditingSessionRevisionConflict:
            raise EditingSessionConflict(
                self.store.get_editing_session(project_id=project_id, session_id=session_id)
            ) from None

    def _editing_session_for_output_timeline(
        self, *, project_id: str, timeline: dict[str, Any]
    ) -> dict[str, Any] | None:
        try:
            session = self.store.get_latest_editing_session(project_id=project_id)
        except KeyError:
            return None
        if str(session.get("timeline_id") or "") != str(timeline.get("timeline_id") or ""):
            return None
        return session

    def _ensure_output_dependencies_fresh(self, *, project_id: str, timeline: dict[str, Any]) -> None:
        """A stale approval/subtitle must never authorize a new output artifact."""
        timeline_id = str(timeline.get("timeline_id") or "")
        if not timeline_id:
            return
        try:
            active_session = self.store.get_latest_editing_session(project_id=project_id)
        except KeyError:
            active_session = None
        if active_session is not None and str(active_session.get("timeline_id") or "") != timeline_id:
            raise OutputSourceStaleError("timeline is not the active editing session output")
        try:
            review = self.store.get_review_state(project_id=project_id, timeline_id=timeline_id)
        except KeyError:
            review = None
        subtitle = self.store.get_latest_subtitle_for_timeline(
            project_id=project_id, timeline_id=timeline_id, include_stale=True
        )
        verify_output_freshness(
            editing_session=active_session,
            timeline=timeline,
            subtitle=subtitle,
            review=review,
        )

    def get_capcut_draft_export_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        if not job["output_ref"]:
            return {
                "job_id": job["job_id"],
                "status": job["status"],
                "export": None,
                "error_message": job.get("error_message"),
            }
        export = self.store.get_capcut_draft_export(project_id=project_id, export_id=job["output_ref"])
        return {
            "job_id": job["job_id"],
            "status": job["status"],
            "export": export,
            "error_message": job.get("error_message"),
        }

    def assert_timeline_output_allowed(self, *, project_id: str, timeline_job_id: str) -> None:
        timeline = self.get_timeline_result(project_id=project_id, job_id=timeline_job_id)["timeline"]
        if timeline.get("gap_slots") or timeline.get("placeholder_policy") == "in_app_only":
            raise ValueError("draft_bundle_gap_blocks_final_and_capcut_output")

    def register_capcut_draft_handoff(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        result = self.get_capcut_draft_export_result(project_id=project_id, job_id=job_id)
        export = result["export"]
        if export is None:
            raise RuntimeError("CapCut 초안 결과가 없어 등록할 수 없습니다. 실제 CapCut 초안 내보내기를 다시 실행하세요.")
        source_path = self.store.resolve_storage_uri(project_id=project_id, storage_uri=export["file_uri"])
        try:
            registered = self.capcut_handoff_service.register(
                source_draft_path=source_path,
                export_id=str(export["export_id"]),
            )
            handoff = {
                "status": registered.status,
                "source_file_uri": export["file_uri"],
                "registered_project_path": str(registered.registered_path),
                "error_message": None,
                "registered_at": registered.registered_at,
                "reused": registered.reused,
            }
        except CapCutHandoffError as exc:
            handoff = {
                "status": "failed",
                "source_file_uri": export["file_uri"],
                "registered_project_path": None,
                "error_message": str(exc),
                "registered_at": None,
                "reused": False,
            }
        self.store.update_capcut_draft_handoff(
            project_id=project_id,
            export_id=str(export["export_id"]),
            handoff=handoff,
        )
        return handoff

    def get_capcut_handoff_diagnostics(self) -> dict[str, Any]:
        diagnostics = self.capcut_handoff_service.diagnose()
        return {
            "status": diagnostics.status,
            "installation_path": str(diagnostics.installation_path) if diagnostics.installation_path else None,
            "detected_version": diagnostics.detected_version,
            "is_supported": diagnostics.is_supported,
            "project_root_path": str(diagnostics.project_root_path),
            "project_root_exists": diagnostics.project_root_exists,
            "write_access": diagnostics.write_access,
            "recovery_message": diagnostics.recovery_message,
            "checked_at": diagnostics.checked_at,
        }

