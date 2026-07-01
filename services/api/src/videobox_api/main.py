from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from videobox_api.orchestration import ApiOrchestrator, build_local_first_runtime_service
from videobox_core_engine.auto_cut import AutoCutPlanner
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_core_engine.output_operator_copy import LocalFirstOutputOperatorCopyBuilder
from videobox_core_engine.recommenders import LocalFirstKeywordBrollRecommender, LocalFirstMusicRecommender
from videobox_core_engine.review_guidance import LocalFirstReviewGuidanceBuilder
from videobox_core_engine.script_scene_planner import LocalFirstSegmentAnalyzer
from videobox_core_engine.settings import (
    DEFAULT_PROJECTS_ROOT,
    AutoCutConfig,
    LocalOpenAICompatibleRuntimeConfig,
)
from videobox_domain_models.recommendations import RecommendationType
from videobox_provider_interfaces.gemini import GeminiHTTPTransport, GeminiRESTStructuredProvider
from videobox_provider_interfaces.llm import LLMProviderConfig
from videobox_storage.local_project_store import LocalProjectStore

VALID_PREVIEW_RECOMMENDATION_TYPES = {
    RecommendationType.TTS_REPLACEMENT.value,
    RecommendationType.BROLL.value,
    RecommendationType.BGM.value,
    RecommendationType.OVERLAY.value,
}
VALID_PREVIEW_REVIEW_FLAG_CODES = {
    "segment_review_required",
    "broll_review_required",
    "tts_replacement_review_required",
}


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1)


class ProjectResponse(BaseModel):
    project_id: str
    name: str
    status: str
    root_storage_uri: str


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]


class AssetRegistrationRequest(BaseModel):
    source_path: str = Field(min_length=1)


class BrollAssetRegistrationRequest(AssetRegistrationRequest):
    title: str | None = None
    tags: list[str] = Field(default_factory=list)


class AssetResponse(BaseModel):
    asset_id: str
    asset_type: str
    storage_uri: str


class AutoCutBlackRegionRequest(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_bounds(self) -> "AutoCutBlackRegionRequest":
        if self.end <= self.start:
            raise ValueError("black_regions end must be greater than start.")
        return self


class AutoCutSegmentSampleRequest(BaseModel):
    start_sec: float = Field(ge=0)
    end_sec: float = Field(ge=0)
    avg_brightness: float | None = Field(default=None, ge=0)
    scene_change_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_bounds(self) -> "AutoCutSegmentSampleRequest":
        if self.end_sec <= self.start_sec:
            raise ValueError("segment_samples end_sec must be greater than start_sec.")
        return self


class AutoCutPlanRequest(BaseModel):
    raw_video_asset_id: str = Field(min_length=1)
    total_duration: float = Field(gt=0)
    scene_timestamps: list[float] = Field(default_factory=list)
    black_regions: list[AutoCutBlackRegionRequest] = Field(default_factory=list)
    segment_samples: list[AutoCutSegmentSampleRequest] = Field(default_factory=list)


class AutoCutPlannedSegmentResponse(BaseModel):
    start_sec: float
    end_sec: float


class AutoCutKeptSegmentResponse(AutoCutPlannedSegmentResponse):
    duration_sec: float
    avg_brightness: float | None = None
    scene_change_count: int | None = None
    reasons: list[str] = Field(default_factory=list)


class AutoCutPlanResponse(BaseModel):
    asset_id: str
    storage_uri: str
    should_auto_cut: bool
    scene_detection_filter: str
    blackdetect_filter: str
    planned_segments: list[AutoCutPlannedSegmentResponse] = Field(default_factory=list)
    kept_segments: list[AutoCutKeptSegmentResponse] = Field(default_factory=list)


class StartTranscriptionRequest(BaseModel):
    narration_asset_id: str = Field(min_length=1)


class StartJobResponse(BaseModel):
    job_id: str
    status: str


class JobRecordResponse(BaseModel):
    job_id: str
    project_id: str
    job_type: str
    status: str
    input_ref: str | None = None
    output_ref: str | None = None
    error_message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class JobListResponse(BaseModel):
    jobs: list[JobRecordResponse]


class TranscriptionJobResponse(StartJobResponse):
    transcript_uri: str


class StartSegmentAnalysisRequest(BaseModel):
    transcription_job_id: str = Field(min_length=1)
    script_asset_id: str | None = None


class StartRecommendationRequest(BaseModel):
    segment_analysis_job_id: str = Field(min_length=1)


class BuildTimelineRequest(BaseModel):
    segment_analysis_job_id: str = Field(min_length=1)
    recommendation_job_ids: list[str] = Field(default_factory=list)


class OutputJobRequest(BaseModel):
    timeline_job_id: str = Field(min_length=1)


class CreateEditingSessionRequest(BaseModel):
    timeline_job_id: str = Field(min_length=1)


class CaptionOverrideRequest(BaseModel):
    caption_text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_caption_text(self) -> "CaptionOverrideRequest":
        caption_text = self.caption_text.strip()
        if not caption_text:
            raise ValueError("caption_text must not be blank.")
        self.caption_text = caption_text
        return self


class CutActionOverrideRequest(BaseModel):
    cut_action: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_cut_action(self) -> "CutActionOverrideRequest":
        cut_action = self.cut_action.strip()
        if cut_action not in {"keep", "remove", "trim"}:
            raise ValueError("cut_action must be one of: keep, remove, trim.")
        self.cut_action = cut_action
        return self


class BrollOverrideRequest(BaseModel):
    asset_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_asset_id(self) -> "BrollOverrideRequest":
        asset_id = self.asset_id.strip()
        if not asset_id:
            raise ValueError("asset_id must not be blank.")
        self.asset_id = asset_id
        return self


class VisualOverlayRequest(BaseModel):
    overlay_type: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_visual_overlay(self) -> "VisualOverlayRequest":
        overlay_type = self.overlay_type.strip()
        asset_id = self.asset_id.strip()
        if not overlay_type:
            raise ValueError("overlay_type must not be blank.")
        if not asset_id:
            raise ValueError("asset_id must not be blank.")
        self.overlay_type = overlay_type
        self.asset_id = asset_id
        return self


class ExplanationCardRequest(BaseModel):
    title: str = ""
    body: str = ""
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_explanation_card(self) -> "ExplanationCardRequest":
        title = self.title.strip()
        body = self.body.strip()
        text = self.text.strip()
        if not text:
            raise ValueError("text must not be blank.")
        self.title = title
        self.body = body
        self.text = text
        return self


class ImageOverlayRequest(BaseModel):
    asset_id: str = Field(min_length=1)
    text: str = ""

    @model_validator(mode="after")
    def validate_image_overlay(self) -> "ImageOverlayRequest":
        asset_id = self.asset_id.strip()
        if not asset_id:
            raise ValueError("asset_id must not be blank.")
        self.asset_id = asset_id
        self.text = self.text.strip()
        return self


class TableOverlayRequest(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_table_overlay(self) -> "TableOverlayRequest":
        text = self.text.strip()
        if not text:
            raise ValueError("text must not be blank.")
        self.columns = [str(item).strip() for item in self.columns]
        self.rows = [[str(cell).strip() for cell in row] for row in self.rows]
        self.text = text
        return self


class TTSReplacementRequest(BaseModel):
    recommendation_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_tts_replacement(self) -> "TTSReplacementRequest":
        recommendation_id = self.recommendation_id.strip()
        asset_id = self.asset_id.strip()
        if not recommendation_id:
            raise ValueError("recommendation_id must not be blank.")
        if not asset_id:
            raise ValueError("asset_id must not be blank.")
        self.recommendation_id = recommendation_id
        self.asset_id = asset_id
        return self


class PartialRegenerationRequest(BaseModel):
    segment_ids: list[str] = Field(min_length=1)
    fields: list[str] = Field(min_length=1)


class PartialRegenerationResponse(BaseModel):
    job_id: str | None = None
    status: str | None = None
    session_id: str | None = None
    segment_ids: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)
    downstream_steps: list[str] = Field(default_factory=list)
    targeted_segments: list[dict[str, object]] = Field(default_factory=list)
    affected_output_areas: list[str] = Field(default_factory=list)
    predicted_review_status_after_rerun: str = "unknown"
    prediction_reasons: list[str] = Field(default_factory=list)
    delta: dict[str, object] | None = None


class PartialRegenerationJobResponse(StartJobResponse):
    partial_regeneration_id: str
    session_id: str
    session_updated_at: str | None = None
    source_timeline_id: str
    timeline_id: str
    segment_ids: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)
    downstream_steps: list[str] = Field(default_factory=list)
    regenerated_segments: list[dict[str, object]] = Field(default_factory=list)
    timeline: TimelinePayloadResponse
    created_at: str | None = None


class EditingSessionSegmentResponse(BaseModel):
    segment_id: str
    caption_text: str
    start_sec: float
    end_sec: float
    cut_action: str
    review_required: bool
    broll_override: dict[str, object] | None = None
    visual_overlays: list[dict[str, object]] = Field(default_factory=list)
    music_override: dict[str, object] | None = None
    tts_replacement: dict[str, object] | None = None


class EditingSessionHistoryEntryResponse(BaseModel):
    mutation_type: str
    segment_id: str
    caption_text: str | None = None
    cut_action: str | None = None
    asset_id: str | None = None
    overlay_type: str | None = None
    recommendation_id: str | None = None


class EditingSessionResponse(BaseModel):
    session_id: str
    project_id: str
    timeline_id: str
    segments: list[EditingSessionSegmentResponse]
    history: list[EditingSessionHistoryEntryResponse] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class SegmentAnalysisRecord(BaseModel):
    segment_id: str | None = None
    text: str
    start_sec: float
    end_sec: float
    confidence: float
    review_required: bool
    cleanup_decision: str
    provider_trace: "ProviderTraceResponse"


class ProviderTraceResponse(BaseModel):
    routing_mode: str
    final_provider: str
    fallback_reasons: list[str] = Field(default_factory=list)


class RecommendationItemResponse(BaseModel):
    recommendation_id: str
    target_segment_id: str
    selected_asset_id: str | None = None
    score: float
    reason: str
    auto_apply_allowed: bool
    review_required: bool
    payload: dict[str, object]
    created_at: str
    provider_trace: ProviderTraceResponse


class SegmentAnalysisJobResponse(StartJobResponse):
    segments: list[SegmentAnalysisRecord]


class RecommendationJobResponse(StartJobResponse):
    recommendation_type: str
    recommendations: list[RecommendationItemResponse]


class TimelineClipResponse(BaseModel):
    clip_id: str
    segment_id: str
    asset_uri: str
    start_sec: float
    end_sec: float
    clip_type: str
    recommendation_id: str | None = None


class TimelineTrackResponse(BaseModel):
    track_id: str
    track_type: str
    clips: list[TimelineClipResponse]


class ReviewFlagResponse(BaseModel):
    code: str
    segment_id: str
    message: str


class TimelinePayloadResponse(BaseModel):
    timeline_id: str
    project_id: str
    version: str
    output_mode: str
    review_status: str = "draft"
    tracks: list[TimelineTrackResponse]
    review_flags: list[ReviewFlagResponse]
    applied_recommendations: list[RecommendationItemResponse] = Field(default_factory=list)
    pending_recommendations: list[RecommendationItemResponse] = Field(default_factory=list)
    created_at: str | None = None


class TimelineJobResponse(StartJobResponse):
    timeline: TimelinePayloadResponse


class ReviewSnapshotResponse(BaseModel):
    project_id: str
    timeline_id: str
    review_status: str
    segments: list[SegmentAnalysisRecord]
    applied_recommendations: list[RecommendationItemResponse]
    pending_recommendations: list[RecommendationItemResponse]
    review_flags: list[ReviewFlagResponse]
    operator_guidance: "OperatorGuidanceResponse"


class OperatorGuidanceResponse(BaseModel):
    summary: str
    action_items: list[str]
    provider_trace: ProviderTraceResponse


class ReviewApprovalResponse(BaseModel):
    timeline_id: str
    project_id: str
    review_status: str
    approved_at: str | None = None
    updated_at: str


class PreviewArtifactResponse(BaseModel):
    preview_id: str
    project_id: str
    timeline_id: str
    file_uri: str
    player_uri: str | None = None
    status: str
    artifact_kind: str
    notes: list[str] = Field(default_factory=list)
    provider_trace: ProviderTraceResponse
    created_at: str | None = None


class PreviewJobResponse(StartJobResponse):
    preview: PreviewArtifactResponse


class ExportArtifactResponse(BaseModel):
    export_id: str
    project_id: str
    timeline_id: str
    export_type: str
    file_uri: str
    subtitle_file_uri: str | None = None
    status: str
    adapter: str | None = None
    capcut_tracks: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    provider_trace: ProviderTraceResponse
    created_at: str | None = None


class ExportJobResponse(StartJobResponse):
    export: ExportArtifactResponse


class ProviderTraceAuditSummaryResponse(BaseModel):
    total_entries: int
    provider_counts: dict[str, int] = Field(default_factory=dict)
    fallback_entry_count: int
    fallback_reason_counts: dict[str, int] = Field(default_factory=dict)
    artifact_type_counts: dict[str, int] = Field(default_factory=dict)


class ProviderTraceAuditEntryResponse(BaseModel):
    artifact_type: str
    artifact_id: str
    job_type: str | None = None
    job_id: str | None = None
    source_job_id: str | None = None
    timeline_id: str | None = None
    status: str
    finished_at: str | None = None
    created_at: str | None = None
    error_message: str | None = None
    provider_trace: ProviderTraceResponse


class ProviderTraceAuditResponse(BaseModel):
    summary: ProviderTraceAuditSummaryResponse
    entries: list[ProviderTraceAuditEntryResponse]
    direct_entries: list[ProviderTraceAuditEntryResponse] = Field(default_factory=list)
    upstream_entries: list[ProviderTraceAuditEntryResponse] = Field(default_factory=list)


class SubtitleArtifactResponse(BaseModel):
    subtitle_id: str
    project_id: str
    timeline_id: str
    format: str
    file_uri: str
    status: str
    notes: list[str] = Field(default_factory=list)
    created_at: str | None = None


class SubtitleJobResponse(StartJobResponse):
    subtitle: SubtitleArtifactResponse


class GeminiProviderKeyCreateRequest(BaseModel):
    label: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    primary_model: str = Field(min_length=1)
    cheap_model: str = Field(min_length=1)
    high_quality_model: str = Field(min_length=1)


class GeminiProviderKeyUpdateRequest(BaseModel):
    label: str | None = None
    primary_model: str | None = None
    cheap_model: str | None = None
    high_quality_model: str | None = None


class GeminiProviderKeyResponse(BaseModel):
    key_id: str
    project_id: str
    label: str
    masked_api_key: str
    primary_model: str
    cheap_model: str
    high_quality_model: str
    status: str
    cooldown_until: str | None = None
    consecutive_failures: int
    last_error: str | None = None
    last_used_at: str | None = None
    created_at: str
    updated_at: str


class GeminiProviderKeyListResponse(BaseModel):
    keys: list[GeminiProviderKeyResponse]


def _is_valid_preflight_visual_overlay(overlay: object) -> bool:
    if not isinstance(overlay, dict):
        return False
    overlay_type = str(overlay.get("overlay_type") or "").strip()
    if not overlay_type:
        return False
    if overlay_type not in {
        "image",
        "image_card",
        "image_overlay",
        "explanation_card",
        "table_card",
        "table_overlay",
        "hook_title",
        "visual_overlay",
    }:
        return False
    if overlay_type in {"explanation_card", "table_card", "table_overlay"}:
        return bool(str(overlay.get("text") or "").strip())
    if overlay_type in {"hook_title", "visual_overlay"}:
        return bool(str(overlay.get("text") or "").strip()) or bool(
            str(overlay.get("asset_id") or "").strip()
        )
    return bool(str(overlay.get("asset_id") or "").strip())


def _build_targeted_segments(
    session: dict[str, Any],
    segment_ids: list[str],
) -> list[dict[str, object]]:
    segment_lookup: dict[str, dict[str, object]] = {}
    for segment in session.get("segments", []):
        segment_id = str(segment.get("segment_id") or "").strip()
        if not segment_id:
            continue
        segment_lookup[segment_id] = segment

    targeted_segments: list[dict[str, object]] = []
    for segment_id in segment_ids:
        segment = segment_lookup.get(str(segment_id or ""))
        if not isinstance(segment, dict):
            continue
        cut_action = str(segment.get("cut_action") or "keep")
        if cut_action not in {"keep", "remove", "trim"}:
            cut_action = "keep"
        review_required = segment.get("review_required", False)
        if isinstance(review_required, str):
            normalized_review_required = review_required.strip().lower()
            review_required = normalized_review_required not in {"", "0", "false", "no", "off"}
        elif not isinstance(review_required, bool):
            review_required = False
        broll_override = segment.get("broll_override")
        if not isinstance(broll_override, dict):
            broll_override = None
        else:
            broll_asset_id = broll_override.get("asset_id")
            if not isinstance(broll_asset_id, str) or not broll_asset_id.strip():
                broll_override = None
        visual_overlays = segment.get("visual_overlays")
        if not isinstance(visual_overlays, list):
            visual_overlays = []
        else:
            visual_overlays = [
                overlay
                for overlay in visual_overlays
                if _is_valid_preflight_visual_overlay(overlay)
            ]
        music_override = segment.get("music_override")
        if not isinstance(music_override, dict):
            music_override = None
        else:
            music_asset_id = music_override.get("asset_id")
            if not isinstance(music_asset_id, str) or not music_asset_id.strip():
                music_override = None
        tts_replacement = segment.get("tts_replacement")
        if not isinstance(tts_replacement, dict):
            tts_replacement = None
        else:
            recommendation_id = tts_replacement.get("recommendation_id")
            asset_id = tts_replacement.get("asset_id")
            if (
                not isinstance(recommendation_id, str)
                or not recommendation_id.strip()
                or not isinstance(asset_id, str)
                or not asset_id.strip()
            ):
                tts_replacement = None
        targeted_segments.append(
            {
                "segment_id": segment_id,
                "caption_text": str(segment.get("caption_text") or ""),
                "cut_action": cut_action,
                "review_required": bool(review_required),
                "broll_override": broll_override,
                "visual_overlays": visual_overlays,
                "music_override": music_override,
                "tts_replacement": tts_replacement,
            }
        )
    return targeted_segments


def _build_affected_output_areas(downstream_steps: list[str]) -> list[str]:
    areas: list[str] = []
    for step in downstream_steps:
        if step == "segment_refresh" and "segment copy" not in areas:
            areas.append("segment copy")
        if step == "broll_refresh" and "b-roll track" not in areas:
            areas.append("b-roll track")
        if step == "music_refresh" and "music bed" not in areas:
            areas.append("music bed")
        if step == "overlay_refresh" and "visual overlays" not in areas:
            areas.append("visual overlays")
        if step == "tts_refresh" and "narration track" not in areas:
            areas.append("narration track")
        if step == "timeline_build":
            for area in ["timeline preview", "subtitle render", "capcut export"]:
                if area not in areas:
                    areas.append(area)
    return areas


def _build_preflight_review_prediction(
    *,
    source_timeline: dict[str, Any],
    targeted_segments: list[dict[str, object]],
    fields: list[str],
) -> tuple[str, list[str]]:
    prediction_reasons: list[str] = []
    source_review_flags = source_timeline.get("review_flags")
    if not isinstance(source_review_flags, list):
        source_review_flags = []
    else:
        source_review_flags = [
            flag
            for flag in source_review_flags
            if (
                isinstance(flag, dict)
                and str(flag.get("code") or "").strip() in VALID_PREVIEW_REVIEW_FLAG_CODES
                and str(flag.get("segment_id") or "").strip()
            )
        ]
    source_pending_recommendations = source_timeline.get("pending_recommendations")
    if not isinstance(source_pending_recommendations, list):
        source_pending_recommendations = []
    else:
        source_pending_recommendations = [
            item
            for item in source_pending_recommendations
            if (
                isinstance(item, dict)
                and str(item.get("recommendation_id") or "").strip()
                and str(item.get("target_segment_id") or "").strip()
                and str(item.get("recommendation_type") or "").strip()
                in VALID_PREVIEW_RECOMMENDATION_TYPES
            )
        ]
    if source_review_flags or source_pending_recommendations:
        prediction_reasons.append(
            "source timeline already has unresolved review blockers that rerun will preserve"
        )
    if any(bool(segment.get("review_required")) for segment in targeted_segments):
        prediction_reasons.append(
            "selected segments already require operator review, so rerun output stays blocked"
        )
    known_fields = {
        "caption",
        "cut_action",
        "broll",
        "music",
        "visual_overlay",
        "explanation_card",
        "image_overlay",
        "table_overlay",
        "tts_replacement",
    }
    if prediction_reasons:
        return "blocked", prediction_reasons
    if any(field not in known_fields for field in fields):
        return "unknown", ["rerun review status could not be predicted for the requested field set"]
    return "draft", []


def create_app(
    *,
    projects_root: Path | None = None,
    local_runtime_config: LocalOpenAICompatibleRuntimeConfig | None = None,
    auto_cut_config: AutoCutConfig | None = None,
    local_first_runtime_service_factory=None,
) -> FastAPI:
    app = FastAPI(title="VideoBox API", version="0.1.0")
    store = LocalProjectStore(projects_root or DEFAULT_PROJECTS_ROOT)
    resolved_local_runtime_config = local_runtime_config or LocalOpenAICompatibleRuntimeConfig()
    runtime_service_factory = local_first_runtime_service_factory or (
        lambda project_store: build_local_first_runtime_service(
            store=project_store,
            gemini_provider=GeminiRESTStructuredProvider(
                transport=GeminiHTTPTransport(http_client=urlopen)
            ),
            gemini_config=LLMProviderConfig(provider_name="gemini", enabled=True),
            local_runtime_config=resolved_local_runtime_config,
            local_http_client=urlopen,
        )
    )
    runtime_service = runtime_service_factory(store)
    resolved_auto_cut_config = auto_cut_config or AutoCutConfig()
    pipeline = LocalPipelineRunner(
        store,
        segment_analyzer=LocalFirstSegmentAnalyzer(runtime_service=runtime_service),
        broll_recommender=LocalFirstKeywordBrollRecommender(runtime_service=runtime_service),
        music_recommender=LocalFirstMusicRecommender(runtime_service=runtime_service),
        review_guidance_builder=LocalFirstReviewGuidanceBuilder(runtime_service=runtime_service),
        output_operator_copy_builder=LocalFirstOutputOperatorCopyBuilder(runtime_service=runtime_service),
        auto_cut_planner=AutoCutPlanner(config=resolved_auto_cut_config),
    )
    orchestrator = ApiOrchestrator(store, pipeline=pipeline)
    app.state.local_runtime_config = resolved_local_runtime_config
    app.state.auto_cut_config = resolved_auto_cut_config
    app.state.build_local_first_runtime_service = build_local_first_runtime_service
    app.state.local_first_runtime_service_factory = runtime_service_factory
    app.state.local_http_client = urlopen

    def _http_error(exc: Exception) -> HTTPException:
        if isinstance(exc, FileNotFoundError):
            return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        if isinstance(exc, LookupError | KeyError):
            return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        if isinstance(exc, ValueError):
            return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/projects", status_code=status.HTTP_201_CREATED)
    def create_project(payload: CreateProjectRequest) -> ProjectResponse:
        project = store.bootstrap_project(name=payload.name)
        return ProjectResponse(
            project_id=project.project_id,
            name=project.name,
            status=project.status.value,
            root_storage_uri=project.root_storage_uri,
        )

    @app.get("/api/projects")
    def list_projects() -> ProjectListResponse:
        projects = store.list_projects()
        return ProjectListResponse(
            projects=[
                ProjectResponse(
                    project_id=project["project_id"],
                    name=project["name"],
                    status=project["status"],
                    root_storage_uri=project["root_storage_uri"],
                )
                for project in projects
            ]
        )

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str) -> ProjectResponse:
        try:
            project = store.get_project(project_id=project_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return ProjectResponse(
            project_id=project["project_id"],
            name=project["name"],
            status=project["status"],
            root_storage_uri=project["root_storage_uri"],
        )

    @app.get("/api/projects/{project_id}/jobs")
    def list_project_jobs(project_id: str) -> JobListResponse:
        try:
            jobs = store.list_jobs(project_id=project_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return JobListResponse(jobs=[JobRecordResponse(**job) for job in jobs])

    @app.post("/api/projects/{project_id}/assets/narration-audio", status_code=status.HTTP_201_CREATED)
    def register_narration_audio(project_id: str, payload: AssetRegistrationRequest) -> AssetResponse:
        try:
            asset = orchestrator.register_narration_audio(
                project_id=project_id,
                source_path=Path(payload.source_path),
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return AssetResponse(
            asset_id=asset.asset_id,
            asset_type=asset.asset_type,
            storage_uri=asset.storage_uri,
        )

    @app.post("/api/projects/{project_id}/assets/script-document", status_code=status.HTTP_201_CREATED)
    def register_script_document(project_id: str, payload: AssetRegistrationRequest) -> AssetResponse:
        try:
            asset = orchestrator.register_script_document(
                project_id=project_id,
                source_path=Path(payload.source_path),
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return AssetResponse(
            asset_id=asset.asset_id,
            asset_type=asset.asset_type,
            storage_uri=asset.storage_uri,
        )

    @app.post("/api/projects/{project_id}/assets/broll-video", status_code=status.HTTP_201_CREATED)
    def register_broll_asset(project_id: str, payload: BrollAssetRegistrationRequest) -> AssetResponse:
        try:
            asset = orchestrator.register_broll_asset(
                project_id=project_id,
                source_path=Path(payload.source_path),
                title=payload.title,
                tags=payload.tags,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return AssetResponse(
            asset_id=asset.asset_id,
            asset_type=asset.asset_type,
            storage_uri=asset.storage_uri,
        )

    @app.post("/api/projects/{project_id}/assets/raw-video", status_code=status.HTTP_201_CREATED)
    def register_raw_video(project_id: str, payload: AssetRegistrationRequest) -> AssetResponse:
        try:
            asset = orchestrator.register_raw_video_asset(
                project_id=project_id,
                source_path=Path(payload.source_path),
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return AssetResponse(
            asset_id=asset.asset_id,
            asset_type=asset.asset_type,
            storage_uri=asset.storage_uri,
        )

    @app.post("/api/projects/{project_id}/jobs/auto-cut-plan")
    def plan_auto_cut(project_id: str, payload: AutoCutPlanRequest) -> AutoCutPlanResponse:
        try:
            result = orchestrator.plan_auto_cut_segments(
                project_id=project_id,
                raw_video_asset_id=payload.raw_video_asset_id,
                total_duration=payload.total_duration,
                scene_timestamps=payload.scene_timestamps,
                black_regions=[region.model_dump() for region in payload.black_regions],
                segment_samples=[segment.model_dump() for segment in payload.segment_samples],
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return AutoCutPlanResponse(**result)

    @app.post("/api/projects/{project_id}/jobs/transcription", status_code=status.HTTP_202_ACCEPTED)
    def start_transcription(project_id: str, payload: StartTranscriptionRequest) -> TranscriptionJobResponse:
        try:
            result = orchestrator.start_transcription(
                project_id=project_id,
                narration_asset_id=payload.narration_asset_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return TranscriptionJobResponse(**result)

    @app.get("/api/projects/{project_id}/jobs/transcription/{job_id}")
    def get_transcription_job(project_id: str, job_id: str) -> TranscriptionJobResponse:
        try:
            result = orchestrator.get_transcription_job(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return TranscriptionJobResponse(**result)

    @app.post("/api/projects/{project_id}/jobs/segment-analysis", status_code=status.HTTP_202_ACCEPTED)
    def start_segment_analysis(project_id: str, payload: StartSegmentAnalysisRequest) -> StartJobResponse:
        try:
            result = orchestrator.start_segment_analysis(
                project_id=project_id,
                transcription_job_id=payload.transcription_job_id,
                script_asset_id=payload.script_asset_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return StartJobResponse(job_id=result["job_id"], status=result["status"])

    @app.get("/api/projects/{project_id}/jobs/segment-analysis/{job_id}")
    def get_segment_analysis_job(project_id: str, job_id: str) -> SegmentAnalysisJobResponse:
        try:
            result = orchestrator.get_segment_analysis_job(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return SegmentAnalysisJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            segments=[SegmentAnalysisRecord(**segment) for segment in result["segments"]],
        )

    @app.post("/api/projects/{project_id}/jobs/broll-recommendation", status_code=status.HTTP_202_ACCEPTED)
    def start_broll_recommendation(project_id: str, payload: StartRecommendationRequest) -> StartJobResponse:
        try:
            result = orchestrator.start_broll_recommendation(
                project_id=project_id,
                segment_analysis_job_id=payload.segment_analysis_job_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return StartJobResponse(**result)

    @app.get("/api/projects/{project_id}/jobs/broll-recommendation/{job_id}")
    def get_broll_recommendation(project_id: str, job_id: str) -> RecommendationJobResponse:
        try:
            result = orchestrator.get_broll_recommendation_job(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return RecommendationJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            recommendation_type=result["recommendation_type"],
            recommendations=[RecommendationItemResponse(**item) for item in result["recommendations"]],
        )

    @app.post("/api/projects/{project_id}/jobs/music-recommendation", status_code=status.HTTP_202_ACCEPTED)
    def start_music_recommendation(project_id: str, payload: StartRecommendationRequest) -> StartJobResponse:
        try:
            result = orchestrator.start_music_recommendation(
                project_id=project_id,
                segment_analysis_job_id=payload.segment_analysis_job_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return StartJobResponse(**result)

    @app.get("/api/projects/{project_id}/jobs/music-recommendation/{job_id}")
    def get_music_recommendation(project_id: str, job_id: str) -> RecommendationJobResponse:
        try:
            result = orchestrator.get_music_recommendation_job(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return RecommendationJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            recommendation_type=result["recommendation_type"],
            recommendations=[RecommendationItemResponse(**item) for item in result["recommendations"]],
        )

    @app.post("/api/projects/{project_id}/jobs/build-timeline", status_code=status.HTTP_202_ACCEPTED)
    def build_timeline(project_id: str, payload: BuildTimelineRequest) -> StartJobResponse:
        try:
            result = orchestrator.build_timeline(
                project_id=project_id,
                segment_analysis_job_id=payload.segment_analysis_job_id,
                recommendation_job_ids=payload.recommendation_job_ids,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return StartJobResponse(**result)

    @app.get("/api/projects/{project_id}/timelines/{job_id}")
    def get_timeline(project_id: str, job_id: str) -> TimelineJobResponse:
        try:
            result = orchestrator.get_timeline_job(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return TimelineJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            timeline=TimelinePayloadResponse(**result["timeline"]),
        )

    @app.post("/api/projects/{project_id}/editing-sessions", status_code=status.HTTP_201_CREATED)
    def create_editing_session(project_id: str, payload: CreateEditingSessionRequest) -> EditingSessionResponse:
        try:
            result = orchestrator.create_editing_session(
                project_id=project_id,
                timeline_job_id=payload.timeline_job_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @app.get("/api/projects/{project_id}/editing-sessions/latest")
    def get_latest_editing_session(project_id: str) -> EditingSessionResponse:
        try:
            result = orchestrator.get_latest_editing_session(project_id=project_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @app.get("/api/projects/{project_id}/editing-sessions/{session_id}")
    def get_editing_session(project_id: str, session_id: str) -> EditingSessionResponse:
        try:
            result = orchestrator.get_editing_session(
                project_id=project_id,
                session_id=session_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @app.patch("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/caption")
    def patch_editing_session_caption(
        project_id: str,
        session_id: str,
        segment_id: str,
        payload: CaptionOverrideRequest,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.update_segment_caption(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                caption_text=payload.caption_text,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @app.patch("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/cut-action")
    def patch_editing_session_cut_action(
        project_id: str,
        session_id: str,
        segment_id: str,
        payload: CutActionOverrideRequest,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.update_segment_cut_action(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                cut_action=payload.cut_action,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @app.patch("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/broll")
    def patch_editing_session_broll_override(
        project_id: str,
        session_id: str,
        segment_id: str,
        payload: BrollOverrideRequest,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.update_segment_broll_override(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                asset_id=payload.asset_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @app.delete("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/broll")
    def delete_editing_session_broll_override(
        project_id: str,
        session_id: str,
        segment_id: str,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.clear_segment_broll_override(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @app.post(
        "/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration/preflight",
        response_model_exclude_none=True,
    )
    def preview_editing_session_partial_regeneration(
        project_id: str,
        session_id: str,
        payload: PartialRegenerationRequest,
    ) -> PartialRegenerationResponse:
        try:
            request_preview = orchestrator.build_editing_session_partial_regeneration_request(
                project_id=project_id,
                session_id=session_id,
                segment_ids=payload.segment_ids,
                fields=payload.fields,
            )
            session = orchestrator.get_editing_session(project_id=project_id, session_id=session_id)
            source_timeline = store.get_timeline_run(
                project_id=project_id,
                timeline_id=str(session["timeline_id"]),
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        targeted_segments = _build_targeted_segments(
            session=session,
            segment_ids=request_preview["segment_ids"],
        )
        request_preview["targeted_segments"] = targeted_segments
        request_preview["affected_output_areas"] = _build_affected_output_areas(
            request_preview["downstream_steps"],
        )
        predicted_review_status_after_rerun, prediction_reasons = _build_preflight_review_prediction(
            source_timeline=source_timeline,
            targeted_segments=targeted_segments,
            fields=request_preview["fields"],
        )
        request_preview["predicted_review_status_after_rerun"] = predicted_review_status_after_rerun
        request_preview["prediction_reasons"] = prediction_reasons
        return PartialRegenerationResponse(**request_preview)

    @app.post("/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration", status_code=status.HTTP_202_ACCEPTED)
    def start_editing_session_partial_regeneration(
        project_id: str,
        session_id: str,
        payload: PartialRegenerationRequest,
    ) -> PartialRegenerationResponse:
        try:
            result = orchestrator.start_editing_session_partial_regeneration(
                project_id=project_id,
                session_id=session_id,
                segment_ids=payload.segment_ids,
                fields=payload.fields,
            )
            session = orchestrator.get_editing_session(project_id=project_id, session_id=session_id)
            job_result = orchestrator.get_partial_regeneration_result(
                project_id=project_id,
                job_id=str(result["job_id"]),
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        result["targeted_segments"] = _build_targeted_segments(
            session=session,
            segment_ids=result["segment_ids"],
        )
        result["affected_output_areas"] = _build_affected_output_areas(result["downstream_steps"])
        result["delta"] = {
            "regenerated_segments": job_result["regenerated_segments"],
            "timeline_id": job_result["timeline_id"],
        }
        return PartialRegenerationResponse(**result)

    @app.get("/api/projects/{project_id}/partial-regenerations/{job_id}")
    def get_partial_regeneration_result(project_id: str, job_id: str) -> PartialRegenerationJobResponse:
        try:
            result = orchestrator.get_partial_regeneration_result(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return PartialRegenerationJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            partial_regeneration_id=result["partial_regeneration_id"],
            session_id=result["session_id"],
            session_updated_at=result.get("session_updated_at"),
            source_timeline_id=result["source_timeline_id"],
            timeline_id=result["timeline_id"],
            segment_ids=result["segment_ids"],
            fields=result["fields"],
            downstream_steps=result["downstream_steps"],
            regenerated_segments=result["regenerated_segments"],
            timeline=TimelinePayloadResponse(**result["timeline"]),
            created_at=result.get("created_at"),
        )

    @app.patch("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/visual-overlay")
    def patch_editing_session_visual_overlay(
        project_id: str,
        session_id: str,
        segment_id: str,
        payload: VisualOverlayRequest,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.update_segment_visual_overlay(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                overlay_type=payload.overlay_type,
                asset_id=payload.asset_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @app.delete("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/visual-overlay")
    def delete_editing_session_visual_overlay(
        project_id: str,
        session_id: str,
        segment_id: str,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.clear_segment_visual_overlays(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @app.patch("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/explanation-card")
    def patch_editing_session_explanation_card(
        project_id: str,
        session_id: str,
        segment_id: str,
        payload: ExplanationCardRequest,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.update_segment_explanation_card(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                title=payload.title,
                body=payload.body,
                text=payload.text,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @app.delete("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/explanation-card")
    def delete_editing_session_explanation_card(
        project_id: str,
        session_id: str,
        segment_id: str,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.remove_segment_explanation_card(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @app.patch("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/image-overlay")
    def patch_editing_session_image_overlay(
        project_id: str,
        session_id: str,
        segment_id: str,
        payload: ImageOverlayRequest,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.update_segment_image_overlay(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                asset_id=payload.asset_id,
                text=payload.text,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @app.delete("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/image-overlay")
    def delete_editing_session_image_overlay(
        project_id: str,
        session_id: str,
        segment_id: str,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.remove_segment_image_overlay(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @app.patch("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/table-overlay")
    def patch_editing_session_table_overlay(
        project_id: str,
        session_id: str,
        segment_id: str,
        payload: TableOverlayRequest,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.update_segment_table_overlay(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                columns=payload.columns,
                rows=payload.rows,
                text=payload.text,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @app.delete("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/table-overlay")
    def delete_editing_session_table_overlay(
        project_id: str,
        session_id: str,
        segment_id: str,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.remove_segment_table_overlay(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @app.patch("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/music")
    def patch_editing_session_music_override(
        project_id: str,
        session_id: str,
        segment_id: str,
        payload: BrollOverrideRequest,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.update_segment_music_override(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                asset_id=payload.asset_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @app.delete("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/music")
    def delete_editing_session_music_override(
        project_id: str,
        session_id: str,
        segment_id: str,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.clear_segment_music_override(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @app.patch("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/tts-replacement")
    def patch_editing_session_tts_replacement(
        project_id: str,
        session_id: str,
        segment_id: str,
        payload: TTSReplacementRequest,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.select_segment_tts_replacement(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                recommendation_id=payload.recommendation_id,
                asset_id=payload.asset_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @app.delete("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/tts-replacement")
    def delete_editing_session_tts_replacement(
        project_id: str,
        session_id: str,
        segment_id: str,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.clear_segment_tts_replacement(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @app.get("/api/projects/{project_id}/review-snapshots/{job_id}")
    def get_review_snapshot(project_id: str, job_id: str) -> ReviewSnapshotResponse:
        try:
            result = orchestrator.get_review_snapshot(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return ReviewSnapshotResponse(
            project_id=result["project_id"],
            timeline_id=result["timeline_id"],
            review_status=result["review_status"],
            segments=[SegmentAnalysisRecord(**item) for item in result["segments"]],
            applied_recommendations=[RecommendationItemResponse(**item) for item in result["applied_recommendations"]],
            pending_recommendations=[RecommendationItemResponse(**item) for item in result["pending_recommendations"]],
            review_flags=[ReviewFlagResponse(**item) for item in result["review_flags"]],
            operator_guidance=OperatorGuidanceResponse(**result["operator_guidance"]),
        )

    @app.post("/api/projects/{project_id}/review-snapshots/{job_id}/recommendations/{recommendation_id}/approve")
    def approve_pending_recommendation(
        project_id: str,
        job_id: str,
        recommendation_id: str,
    ) -> ReviewSnapshotResponse:
        try:
            result = orchestrator.approve_pending_recommendation(
                project_id=project_id,
                job_id=job_id,
                recommendation_id=recommendation_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return ReviewSnapshotResponse(
            project_id=result["project_id"],
            timeline_id=result["timeline_id"],
            review_status=result["review_status"],
            segments=[SegmentAnalysisRecord(**item) for item in result["segments"]],
            applied_recommendations=[RecommendationItemResponse(**item) for item in result["applied_recommendations"]],
            pending_recommendations=[RecommendationItemResponse(**item) for item in result["pending_recommendations"]],
            review_flags=[ReviewFlagResponse(**item) for item in result["review_flags"]],
            operator_guidance=OperatorGuidanceResponse(**result["operator_guidance"]),
        )

    @app.post("/api/projects/{project_id}/review-snapshots/{job_id}/recommendations/{recommendation_id}/reject")
    def reject_pending_recommendation(
        project_id: str,
        job_id: str,
        recommendation_id: str,
    ) -> ReviewSnapshotResponse:
        try:
            result = orchestrator.reject_pending_recommendation(
                project_id=project_id,
                job_id=job_id,
                recommendation_id=recommendation_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return ReviewSnapshotResponse(
            project_id=result["project_id"],
            timeline_id=result["timeline_id"],
            review_status=result["review_status"],
            segments=[SegmentAnalysisRecord(**item) for item in result["segments"]],
            applied_recommendations=[RecommendationItemResponse(**item) for item in result["applied_recommendations"]],
            pending_recommendations=[RecommendationItemResponse(**item) for item in result["pending_recommendations"]],
            review_flags=[ReviewFlagResponse(**item) for item in result["review_flags"]],
            operator_guidance=OperatorGuidanceResponse(**result["operator_guidance"]),
        )

    @app.post("/api/projects/{project_id}/review-approvals/{job_id}/approve", status_code=status.HTTP_202_ACCEPTED)
    def approve_review(project_id: str, job_id: str) -> ReviewApprovalResponse:
        try:
            result = orchestrator.approve_timeline_review(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return ReviewApprovalResponse(
            timeline_id=result["timeline_id"],
            project_id=result["project_id"],
            review_status=result["status"],
            approved_at=result["approved_at"],
            updated_at=result["updated_at"],
        )

    @app.post("/api/projects/{project_id}/review-approvals/{job_id}/reopen", status_code=status.HTTP_202_ACCEPTED)
    def reopen_review(project_id: str, job_id: str) -> ReviewApprovalResponse:
        try:
            result = orchestrator.reopen_timeline_review(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return ReviewApprovalResponse(
            timeline_id=result["timeline_id"],
            project_id=result["project_id"],
            review_status=result["status"],
            approved_at=result["approved_at"],
            updated_at=result["updated_at"],
        )

    @app.post("/api/projects/{project_id}/jobs/subtitle-render", status_code=status.HTTP_202_ACCEPTED)
    def start_subtitle_render(project_id: str, payload: OutputJobRequest) -> StartJobResponse:
        try:
            result = orchestrator.start_subtitle_render(
                project_id=project_id,
                timeline_job_id=payload.timeline_job_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return StartJobResponse(**result)

    @app.get("/api/projects/{project_id}/subtitles/{job_id}")
    def get_subtitle_result(project_id: str, job_id: str) -> SubtitleJobResponse:
        try:
            result = orchestrator.get_subtitle_result(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return SubtitleJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            subtitle=SubtitleArtifactResponse(**result["subtitle"]),
        )

    @app.post("/api/projects/{project_id}/jobs/preview-render", status_code=status.HTTP_202_ACCEPTED)
    def start_preview_render(project_id: str, payload: OutputJobRequest) -> StartJobResponse:
        try:
            result = orchestrator.start_preview_render(
                project_id=project_id,
                timeline_job_id=payload.timeline_job_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return StartJobResponse(**result)

    @app.get("/api/projects/{project_id}/previews/{job_id}")
    def get_preview_result(project_id: str, job_id: str) -> PreviewJobResponse:
        try:
            result = orchestrator.get_preview_result(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return PreviewJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            preview=PreviewArtifactResponse(**result["preview"]),
        )

    @app.post("/api/projects/{project_id}/jobs/capcut-export", status_code=status.HTTP_202_ACCEPTED)
    def start_capcut_export(project_id: str, payload: OutputJobRequest) -> StartJobResponse:
        try:
            result = orchestrator.start_capcut_export(
                project_id=project_id,
                timeline_job_id=payload.timeline_job_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return StartJobResponse(**result)

    @app.get("/api/projects/{project_id}/exports/{job_id}")
    def get_export_result(project_id: str, job_id: str) -> ExportJobResponse:
        try:
            result = orchestrator.get_capcut_export_result(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return ExportJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            export=ExportArtifactResponse(**result["export"]),
        )

    @app.get("/api/projects/{project_id}/provider-traces")
    def get_provider_trace_audit(
        project_id: str,
        timeline_id: str | None = None,
        include_upstream: bool = False,
        job_type: str | None = None,
        artifact_type: str | None = None,
        final_provider: str | None = None,
        fallback_reason: str | None = None,
    ) -> ProviderTraceAuditResponse:
        try:
            result = orchestrator.get_provider_trace_audit(
                project_id=project_id,
                timeline_id=timeline_id,
                include_upstream=include_upstream,
                job_type=job_type,
                artifact_type=artifact_type,
                final_provider=final_provider,
                fallback_reason=fallback_reason,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return ProviderTraceAuditResponse(
            summary=ProviderTraceAuditSummaryResponse(**result["summary"]),
            entries=[ProviderTraceAuditEntryResponse(**item) for item in result["entries"]],
            direct_entries=[
                ProviderTraceAuditEntryResponse(**item) for item in result.get("direct_entries", [])
            ],
            upstream_entries=[
                ProviderTraceAuditEntryResponse(**item) for item in result.get("upstream_entries", [])
            ],
        )

    @app.get("/api/projects/{project_id}/providers/gemini/keys")
    def list_gemini_provider_keys(project_id: str) -> GeminiProviderKeyListResponse:
        try:
            keys = orchestrator.list_gemini_provider_keys(project_id=project_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return GeminiProviderKeyListResponse(
            keys=[GeminiProviderKeyResponse(**item) for item in keys]
        )

    @app.post("/api/projects/{project_id}/providers/gemini/keys", status_code=status.HTTP_201_CREATED)
    def create_gemini_provider_key(
        project_id: str,
        payload: GeminiProviderKeyCreateRequest,
    ) -> GeminiProviderKeyResponse:
        try:
            result = orchestrator.save_gemini_provider_key(
                project_id=project_id,
                label=payload.label,
                api_key_secret=payload.api_key,
                primary_model=payload.primary_model,
                cheap_model=payload.cheap_model,
                high_quality_model=payload.high_quality_model,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return GeminiProviderKeyResponse(**result)

    @app.patch("/api/projects/{project_id}/providers/gemini/keys/{key_id}")
    def update_gemini_provider_key(
        project_id: str,
        key_id: str,
        payload: GeminiProviderKeyUpdateRequest,
    ) -> GeminiProviderKeyResponse:
        try:
            result = orchestrator.update_gemini_provider_key(
                project_id=project_id,
                key_id=key_id,
                label=payload.label,
                primary_model=payload.primary_model,
                cheap_model=payload.cheap_model,
                high_quality_model=payload.high_quality_model,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return GeminiProviderKeyResponse(**result)

    @app.post("/api/projects/{project_id}/providers/gemini/keys/{key_id}/disable")
    def disable_gemini_provider_key(project_id: str, key_id: str) -> GeminiProviderKeyResponse:
        try:
            result = orchestrator.set_gemini_provider_key_status(
                project_id=project_id,
                key_id=key_id,
                status="disabled",
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return GeminiProviderKeyResponse(**result)

    @app.post("/api/projects/{project_id}/providers/gemini/keys/{key_id}/enable")
    def enable_gemini_provider_key(project_id: str, key_id: str) -> GeminiProviderKeyResponse:
        try:
            result = orchestrator.set_gemini_provider_key_status(
                project_id=project_id,
                key_id=key_id,
                status="active",
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return GeminiProviderKeyResponse(**result)

    return app
