from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


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


class TTSCandidateRequest(BaseModel):
    segment_text: str = Field(min_length=1)
    voice_sample_asset_id: str = Field(min_length=1)
    segment_id: str | None = None
    target_duration_sec: float | None = Field(default=None, gt=0)


class TTSCandidateRecordResponse(BaseModel):
    candidate_id: str
    project_id: str
    segment_id: str
    asset_id: str
    source_text: str
    technical_status: str = "legacy_unverified"
    operator_review_status: str = "pending"
    target_duration_sec: float | None = None
    actual_duration_sec: float | None = None
    failure_code: str | None = None
    created_at: str


class TTSCandidateListResponse(BaseModel):
    candidates: list[TTSCandidateRecordResponse]


class BrollBatchAssetRegistrationRequest(BaseModel):
    source_paths: list[str] = Field(default_factory=list)
    source_directory: str | None = None
    tags: list[str] = Field(default_factory=list)
    title_by_source_path: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_sources(self) -> "BrollBatchAssetRegistrationRequest":
        self.source_paths = [str(path).strip() for path in self.source_paths if str(path).strip()]
        if self.source_directory is not None:
            self.source_directory = self.source_directory.strip() or None
        self.tags = [str(tag).strip() for tag in self.tags if str(tag).strip()]
        self.title_by_source_path = {
            str(path).strip(): str(title).strip()
            for path, title in self.title_by_source_path.items()
            if str(path).strip() and str(title).strip()
        }
        if not self.source_paths and not self.source_directory:
            raise ValueError("source_paths or source_directory is required.")
        return self


class AssetResponse(BaseModel):
    asset_id: str
    asset_type: str
    storage_uri: str


class TTSCandidateResponse(AssetResponse):
    candidate_id: str | None = None
    segment_id: str | None = None
    source_text: str | None = None
    technical_status: str = "legacy_unverified"
    operator_review_status: str = "pending"
    target_duration_sec: float | None = None
    actual_duration_sec: float | None = None
    failure_code: str | None = None


class AssetArchiveItemResponse(AssetResponse):
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class AssetListResponse(BaseModel):
    assets: list[AssetArchiveItemResponse]


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


class AutoCutDetectRequest(BaseModel):
    raw_video_asset_id: str = Field(min_length=1)


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
    progress_percent: int | None = None


class JobListResponse(BaseModel):
    jobs: list[JobRecordResponse]


class JobRecordWithProjectResponse(JobRecordResponse):
    project_name: str


class AllJobsResponse(BaseModel):
    jobs: list[JobRecordWithProjectResponse]


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
    expected_revision: int = Field(ge=1)
    caption_text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_caption_text(self) -> "CaptionOverrideRequest":
        caption_text = self.caption_text.strip()
        if not caption_text:
            raise ValueError("caption_text must not be blank.")
        self.caption_text = caption_text
        return self


class CaptionStyleMutationRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    scope: str = Field(pattern="^(current_caption|selected_captions|from_current|whole_project|project_default)$")
    segment_ids: list[str] = Field(default_factory=list)
    style: dict[str, Any]


class CutActionOverrideRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    cut_action: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_cut_action(self) -> "CutActionOverrideRequest":
        cut_action = self.cut_action.strip()
        if cut_action not in {"keep", "remove", "trim"}:
            raise ValueError("cut_action must be one of: keep, remove, trim.")
        self.cut_action = cut_action
        return self


class BrollOverrideRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    asset_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_asset_id(self) -> "BrollOverrideRequest":
        asset_id = self.asset_id.strip()
        if not asset_id:
            raise ValueError("asset_id must not be blank.")
        self.asset_id = asset_id
        return self


class VisualOverlayRequest(BaseModel):
    expected_revision: int = Field(ge=1)
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
    expected_revision: int = Field(ge=1)
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
    expected_revision: int = Field(ge=1)
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
    expected_revision: int = Field(ge=1)
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
    expected_revision: int = Field(ge=1)
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


class TTSListeningReviewRequest(BaseModel):
    decision: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_decision(self) -> "TTSListeningReviewRequest":
        decision = self.decision.strip().lower()
        if decision not in {"approved", "rejected"}:
            raise ValueError("decision must be approved or rejected.")
        self.decision = decision
        return self


class PartialRegenerationRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    segment_ids: list[str] = Field(min_length=1)
    fields: list[str] = Field(min_length=1)


class PartialRegenerationPreflightRequest(BaseModel):
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
    timeline: "TimelinePayloadResponse"
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
    sfx_override: dict[str, object] | None = None
    tts_replacement: dict[str, object] | None = None
    caption_style: dict[str, object] | None = None


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
    session_revision: int
    caption_style: dict[str, object] | None = None
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
    review_reasons: list[str] = Field(default_factory=list)
    provider_trace: "ProviderTraceResponse"


class ProviderTraceResponse(BaseModel):
    routing_mode: str
    final_provider: str
    fallback_reasons: list[str] = Field(default_factory=list)


class RecommendationItemResponse(BaseModel):
    recommendation_id: str
    target_segment_id: str
    recommendation_type: str
    selected_asset_id: str | None = None
    score: float
    reason: str
    auto_apply_allowed: bool
    review_required: bool
    decision_state: str | None = None
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


class FinalRenderArtifactResponse(BaseModel):
    export_id: str
    timeline_id: str
    export_type: str
    file_uri: str
    status: str
    created_at: str | None = None


class FinalRenderJobResponse(StartJobResponse):
    render: FinalRenderArtifactResponse | None = None


class CapCutDraftExportArtifactResponse(BaseModel):
    export_id: str
    timeline_id: str
    export_type: str
    file_uri: str
    status: str
    created_at: str | None = None


class CapCutDraftExportJobResponse(StartJobResponse):
    export: CapCutDraftExportArtifactResponse | None = None


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


PartialRegenerationJobResponse.model_rebuild()
