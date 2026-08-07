export type Project = {
  project_id: string;
  name: string;
  status: string;
  root_storage_uri: string;
};

export type CreationInterviewQuestion = {
  question_id: string;
  field: string;
  prompt: string;
};

export type CreationBrief = {
  brief_id: string;
  project_id: string;
  idempotency_key: string;
  script_filename: string;
  script_text: string;
  script_asset_id: string | null;
  capability_profile: Record<string, unknown>;
  questions: CreationInterviewQuestion[];
  answers: Record<string, string>;
  current_step: number;
  status: string;
  revision: number;
  summary?: string | null;
  created_at: string;
  updated_at: string;
};

export type CreateCreationBriefRequest = {
  script_filename: string;
  script_text: string;
  idempotency_key: string;
  capability_profile: Record<string, unknown>;
  script_asset_id?: string;
};

export type DraftReadiness = { readiness_id: string; brief_id: string; status: "asset_check" | "planning" | "ready" | "needs_assets" | "failed" | "cancelled"; revision: number; result: { gap_slots?: { gap_slot_id: string; reason: string }[]; broll_candidates?: { asset_id: string; label: string; target_range: { start_sec: number; end_sec: number }; media_duration_sec?: number | null }[] } | null };
export type DraftReadinessRequest = { brief_id: string; narration_choice: { kind: "silent" | "existing" | "source_video"; asset_id?: string }; idempotency_key: string; expected_brief_revision: number; capability?: Record<string, unknown> };
export type NarrationOption = { asset_id: string; asset_type: "raw_video" | "narration_audio" };
export type MediaInboxAsset = { filename: string; size_bytes: number };
export type MediaInboxImport = { asset_id: string; project_id: string; asset_type: string; storage_uri: string };
export type AtomicDraftBundle = { bundle_id: string; session_id: string; timeline_id: string; timeline_job_id: string; segment_ids: string[]; asset_ids: string[]; clip_ids: string[]; gap_slots: { gap_slot_id: string; reason: string }[]; output_blocked: boolean };
export type AtomicDraftBundleRequest = { brief_id: string; readiness_id: string; expected_brief_revision: number; expected_readiness_revision: number; idempotency_key: string; allow_placeholder?: boolean };

export type JobRecord = {
  job_id: string;
  project_id: string;
  job_type: string;
  status: string;
  input_ref: string | null;
  output_ref: string | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  progress_percent?: number | null;
};

export type JobRecordWithProject = JobRecord & { project_name: string };

export type AssetBrowserPreview = {
  status: "pending" | "running" | "ready" | "failed";
  job_id: string | null;
  content_url: string | null;
  source_sha256: string;
  profile: string;
  error_code: string | null;
};

export type BrollAsset = {
  asset_id: string;
  asset_type: string;
  storage_uri: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type BrollBatchImportRequest = {
  source_paths: string[];
  source_directory?: string;
  tags: string[];
  recursive?: boolean;
};

export type BrollBatchImportResponse = {
  assets: BrollAsset[];
  analysis_jobs: MediaAnalysis[];
  failures: { source_path: string; reason: string }[];
};

export type MediaAnalysis = {
  analysis_id: string;
  asset_id: string;
  status: string;
  progress_percent: number;
  queue_position: number | null;
  error_code: string | null;
  error_message: string | null;
  result: Record<string, unknown> | null;
  created_at: string;
};

export type DirectorProposalCreateRequest = { session_id: string; expires_at?: string };
export type DirectorPreferences = { pin_asset?: string[]; exclude_asset?: string[]; exclude_creator?: string[]; exclude_tag?: string[] };
export type DirectorReference = { reference_code: string; immutable_id: string | { segment_id: string; track_type: string }; source: string };
export type DirectorCandidate = {
  candidate_id: string;
  visible_reference_code: string;
  media_type: string;
  asset_id: string;
  library_asset_id: string | null;
  reason_chips: string[];
  scores: Record<string, number>;
  availability: string;
  review_status: string;
  preview_uri: string | null;
  controls: Record<string, unknown>;
  expected_content_sha256: string | null;
  media_revision: string;
  canonical_metadata: Record<string, unknown>;
  license_policy: string;
  warning_provenance: string[];
};
export type DirectorProposalDiff = Record<string, unknown>;
export type DirectorApplyScope = "all" | "broll_only" | "selected_references";
export type DirectorProposal = {
  proposal_id: string;
  revision_code: string;
  revision: number;
  base_session_revision: number;
  asset_index_revision: number;
  source_session_id: string;
  target_segment_ids: string[];
  source_script_segment_ids: string[];
  status: string;
  diff: DirectorProposalDiff;
  expires_at: string | null;
  candidates: DirectorCandidate[];
};
export type DirectorProposalPreflight = { proposal_id?: string; status?: string; code?: "stale_proposal"; stale_reasons?: string[]; action?: "refresh"; diff?: DirectorProposalDiff };
export type ApplyDirectorProposalResponse = EditingSession;
export type DirectorConversation = { conversation_id: string; project_id: string; session_id: string };
export type DirectorMessage = { message_id: string; conversation_id: string; project_id: string; session_id: string; role: "user" | "assistant" | string; text: string; proposal_id: string | null; metadata: Record<string, unknown>; client_message_id: string | null; created_at: string };
export type DirectorActionIntent = { action: string; target: DirectorReference; proposal_preflight: Record<string, string | number> | null };
export type DirectorMessageExchange = { user_message: DirectorMessage; assistant_message: DirectorMessage; disambiguation?: { status: string; options: DirectorReference[] } | null; reference?: DirectorReference | null; action_intent?: DirectorActionIntent | null };
export type DirectorMessageSubmitRequest = { session_id: string; client_message_id: string; text: string };
export type DirectorMessageSendResult = { kind: "exchange"; exchange: DirectorMessageExchange } | { kind: "in_progress"; retryAfterSeconds: number };
export type DirectorReloadState = { conversation: DirectorConversation | null; messages: DirectorMessage[]; proposal: DirectorProposal | null; references: DirectorReference[] };
export type YujinMemoryCategory = "pacing" | "caption" | "audio" | "tone" | "workflow";
export type YujinMemoryConsentStatus = "pending" | "approved" | "rejected";
export type YujinMemoryStorageStatus =
  | "not_requested"
  | "claimed"
  | "event_pending"
  | "stored"
  | "failed_retryable"
  | "ambiguous"
  | "deleted";
export type YujinMemoryCandidate = {
  candidate_id: string;
  project_id: string;
  conversation_id: string;
  client_request_id: string;
  source_message_ids: string[];
  memory_scope: "creator";
  category: YujinMemoryCategory;
  proposed_text: string;
  status: YujinMemoryConsentStatus;
  storage_status: YujinMemoryStorageStatus;
  retryable: boolean;
  created_at: string;
  updated_at: string;
};
export type YujinMemoryCandidateCreate = {
  conversation_id: string;
  client_request_id: string;
  source_message_ids: string[];
  memory_scope: "creator";
  category: YujinMemoryCategory;
  proposed_text: string;
};
export type YujinMemoryStoreResult = {
  candidate_id: string;
  status: "approved";
  storage_status: YujinMemoryStorageStatus;
  retryable: boolean;
};
export type HermesRunCreateRequest = {
  session_id: string;
  client_message_id: string;
  text: string;
  expected_session_revision: number;
  selected_segment_id?: string | null;
};
export type HermesRunCreateResponse = { run_id: string; conversation_id: string; events_url: string };
export type HermesYujinStatusState =
  | "not_configured"
  | "stopped"
  | "starting"
  | "http_ready"
  | "provider_ready"
  | "chat_verified"
  | "degraded";
export type HermesYujinStatus = {
  state: HermesYujinStatusState;
  http_ready: boolean;
  provider_ready: boolean;
  chat_verified: boolean;
  checked_at: string;
  last_chat_verified_at: string | null;
  restart_available: false;
  status_basis: "application_path";
};
export type ArtifactFreshness = { source_session_revision: number; is_current?: boolean; invalidated_at?: string | null; invalidated_reason?: string | null };

export type TimelineClip = {
  clip_id: string;
  segment_id: string;
  asset_uri: string;
  start_sec: number;
  end_sec: number;
  clip_type: string;
  recommendation_id: string | null;
};

export type TimelineTrack = {
  track_id: string;
  track_type: string;
  clips: TimelineClip[];
};

export type ReviewFlag = {
  code: string;
  segment_id: string;
  message: string;
};

export type RecommendationItem = {
  recommendation_id: string;
  target_segment_id: string;
  recommendation_type: string;
  selected_asset_id: string | null;
  score: number;
  reason: string;
  auto_apply_allowed: boolean;
  review_required: boolean;
  payload: Record<string, unknown>;
  created_at: string;
};

export type TimelinePayload = {
  timeline_id: string;
  project_id: string;
  version: string;
  output_mode: string;
  review_status: string;
  created_at?: string | null;
  tracks: TimelineTrack[];
  review_flags: ReviewFlag[];
  applied_recommendations: RecommendationItem[];
  pending_recommendations: RecommendationItem[];
  source_session_id?: string | null;
  source_session_revision?: number | null;
};

export type TimelineJob = {
  job_id: string;
  status: string;
  timeline: TimelinePayload;
};

export type SegmentRecord = {
  segment_id: string;
  text: string;
  start_sec: number;
  end_sec: number;
  confidence: number;
  review_required: boolean;
  cleanup_decision: string;
  review_reasons?: string[];
};

export type ReviewSnapshot = {
  project_id: string;
  timeline_id: string;
  review_status: string;
  segments: SegmentRecord[];
  applied_recommendations: RecommendationItem[];
  pending_recommendations: RecommendationItem[];
  review_flags: ReviewFlag[];
};

export type EditingSessionSegment = {
  segment_id: string;
  caption_text: string;
  start_sec: number;
  end_sec: number;
  cut_action: string;
  review_required: boolean;
  broll_override: Record<string, unknown> | null;
  visual_overlays: Record<string, unknown>[];
  music_override: Record<string, unknown> | null;
  sfx_override?: Record<string, unknown> | null;
  tts_replacement: Record<string, unknown> | null;
  caption_style?: CaptionStyleSnapshot | null;
};

export type CaptionStyleSnapshot = Record<string, unknown>;

export type CaptionStyleScope =
  | 'current_caption'
  | 'selected_captions'
  | 'from_current'
  | 'whole_project'
  | 'project_default';

type OptionalYujinCandidateAttestation =
  | { proposal_id: string; candidate_id: string }
  | { proposal_id?: never; candidate_id?: never };

export type CaptionStyleMutationRequest = {
  expected_revision: number;
  scope: CaptionStyleScope;
  segment_ids: string[];
  style: CaptionStyleSnapshot;
} & OptionalYujinCandidateAttestation;

export type CaptionStyleScopePreflight = {
  affected_segment_ids: string[];
};

export type EditingSessionHistoryEntry = {
  action_id?: string;
  label?: string;
  created_at?: string;
  reversible?: boolean;
  blocked_reason?: string | null;
  mutation_type: string;
  segment_id: string;
  caption_text?: string | null;
  cut_action?: string | null;
  asset_id?: string | null;
  overlay_type?: string | null;
  recommendation_id?: string | null;
  inverse_payload?: Record<string, unknown> | null;
  forward_payload?: Record<string, unknown> | null;
};

export type EditingSession = {
  session_id: string;
  project_id: string;
  timeline_id: string;
  session_revision: number;
  caption_style?: CaptionStyleSnapshot | null;
  segments: EditingSessionSegment[];
  history: EditingSessionHistoryEntry[];
  undo_count?: number;
  redo_count?: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export type CreateEditingSessionRequest = {
  timeline_job_id: string;
};

export type EditorPreset = {
  preset_id: string;
  name: string;
  scope: "built_in" | "project" | "global";
  style: CaptionStyleSnapshot;
};

export type EditorFavorite = {
  favorite_id: string;
  favorite_type: "media" | "preset";
};

/** Authoritative, project/session-scoped editor read contract. Times are seconds. */
export type EditorMediaControls = {
  volume?: number;
  crop?: string;
  speed?: number;
  gain_db?: number;
  fade_in_sec?: number;
  fade_out_sec?: number;
  ducking?: boolean;
  fit?: "fit" | "crop";
  loop?: boolean;
  pad?: boolean;
  trim_start_sec?: number;
  preserve_source_audio?: boolean;
  in_sec?: number;
  out_sec?: number;
};
export type EditorPlaybackManifest = {
  project_id: string;
  session_id: string;
  timeline_id: string;
  session_revision: number;
  timeline_version: string;
  timebase: "seconds";
  fps: { num: number; den: number };
  output: { width: number; height: number; sample_aspect_ratio: string; rotation: number; duration_sec: number };
  tracks: Array<{
    track_id: string;
    track_type: "narration" | "broll" | "bgm" | "sfx" | "overlay";
    clips: Array<{
      clip_id: string; segment_id: string; placement_id?: string | null; clip_type: "narration" | "broll" | "bgm" | "sfx" | "overlay";
      asset_id: string | null; asset_uri: string | null; start_sec: number; end_sec: number;
      media_controls: EditorMediaControls; expected_content_sha256?: string | null; media_revision?: string | null;
      overlay_type?: "explanation_card" | "image_overlay" | "table_overlay" | null; overlay_payload?: Record<string, unknown>;
    }>;
  }>;
  captions: Array<{
    segment_id: string; caption_id: string; placement_id: string; text: string; start_sec: number; end_sec: number;
    style: { font_family: string; font_size_px: number; text_color: string; outline_color: string; outline_width_px: number; background_color: string; position_x_percent: number; position_y_percent: number; horizontal_align: "left" | "center" | "right"; safe_area_enabled: boolean; shadow_blur_px: number };
  }>;
  gap_slots: Array<{ gap_id: string; segment_id: string; start_sec: number; end_sec: number; reason: string }>;
  source_status: { status: "current" | "stale"; source_session_id?: string | null; source_session_revision?: number | null };
  audition: { asset_urls: Record<string, string> };
  exact_preview: { status: "current" | "succeeded" | "pending" | "running" | "failed" | "stale" | "unavailable"; url?: string | null; source_session_id?: string | null; source_session_revision?: number | null; generation_id?: string | null; timeline_start_sec?: number | null; timeline_end_sec?: number | null; artifact_revision?: number | null };
};
export type ExactPreviewResponse = {
  status: "pending" | "running" | "succeeded" | "failed" | "stale" | "unavailable";
  generation_id: string;
  timeline_start_sec: number;
  timeline_end_sec: number;
  artifact_revision: number;
  fingerprint: string;
  content_url?: string | null;
  error_message?: string | null;
};

type RevisionedEditingSessionMutation = {
  expected_revision: number;
};

export type SegmentSplitRequest = RevisionedEditingSessionMutation & { split_sec: number };
export type SegmentBoundsRequest = RevisionedEditingSessionMutation & { start_sec: number; end_sec: number };
export type SegmentOrderRequest = RevisionedEditingSessionMutation & {
  segment_ids: string[];
  bounds_by_id?: Record<string, { start_sec: number; end_sec: number }>;
};
export type TimelinePlacementPatchRequest = RevisionedEditingSessionMutation & {
  changes: Array<{ placement_id: string; kind: "broll" | "bgm" | "sfx" | "overlay" | "caption"; start_sec: number; end_sec: number }>;
};
export type FixedTimeline = {
  tracks: Array<{ role: "narration" | "broll" | "bgm" | "sfx" | "overlay"; clips: Record<string, unknown>[] }>;
};
export type SelectedRangePreview = {
  start_sec: number;
  end_sec: number;
  captions: Array<{ segment_id: string; caption_text: string; caption_style: CaptionStyleSnapshot }>;
  overlays: Array<Record<string, unknown>>;
  timeline: FixedTimeline;
};

export type CaptionOverrideRequest = RevisionedEditingSessionMutation & {
  caption_text: string;
} & OptionalYujinCandidateAttestation;

export type CutActionOverrideRequest = RevisionedEditingSessionMutation & {
  cut_action: string;
};

export type BrollOverrideRequest = RevisionedEditingSessionMutation & {
  asset_id: string;
  media_controls?: Record<string, unknown>;
};

export type MusicOverrideRequest = RevisionedEditingSessionMutation & {
  asset_id: string;
  media_controls?: Record<string, unknown>;
};

export type ExplanationCardRequest = RevisionedEditingSessionMutation & {
  title: string;
  body: string;
  text: string;
} & OptionalYujinCandidateAttestation;

export type ImageOverlayRequest = RevisionedEditingSessionMutation & {
  asset_id: string;
  text: string;
} & (
  | { proposal_id: string; candidate_id: string }
  | { proposal_id?: never; candidate_id?: never }
);

export type TableOverlayRequest = RevisionedEditingSessionMutation & {
  columns: string[];
  rows: string[][];
  text: string;
} & OptionalYujinCandidateAttestation;

export type TtsReplacementRequest = RevisionedEditingSessionMutation & {
  recommendation_id: string;
  asset_id: string;
} & OptionalYujinCandidateAttestation;

export type PartialRegenerationRequest = RevisionedEditingSessionMutation & {
  segment_ids: string[];
  fields: string[];
};

export type PartialRegenerationPreflight = {
  session_id: string | null;
  segment_ids: string[];
  fields: string[];
  downstream_steps: string[];
  targeted_segments: Record<string, unknown>[];
  affected_output_areas: string[];
  predicted_review_status_after_rerun: string;
  prediction_reasons: string[];
};

export type PartialRegenerationDelta = {
  regenerated_segments: Record<string, unknown>[];
  timeline_id: string | null;
};

export type PartialRegenerationRun = {
  job_id: string | null;
  status: string | null;
  session_id: string | null;
  segment_ids: string[];
  fields: string[];
  downstream_steps: string[];
  targeted_segments: Record<string, unknown>[];
  affected_output_areas: string[];
  delta: PartialRegenerationDelta | null;
};

export type PartialRegenerationJob = {
  job_id: string;
  status: string;
  partial_regeneration_id: string;
  session_id: string;
  session_updated_at?: string | null;
  source_timeline_id: string;
  timeline_id: string;
  segment_ids: string[];
  fields: string[];
  downstream_steps: string[];
  regenerated_segments: Record<string, unknown>[];
  timeline: TimelinePayload;
  created_at?: string | null;
};

export type BuildTimelineRequest = {
  segment_analysis_job_id: string;
  recommendation_job_ids: string[];
  orientation?: "landscape" | "vertical";
};

export type OutputJobRequest = {
  timeline_job_id: string;
};

export type PreviewArtifact = {
  preview_id: string;
  project_id: string;
  timeline_id: string;
  file_uri: string;
  player_uri?: string | null;
  status: string;
  artifact_kind: string;
  notes: string[];
  created_at?: string | null;
};

export type PreviewJob = {
  job_id: string;
  status: string;
  preview: PreviewArtifact;
};

export type ExportArtifact = {
  export_id: string;
  project_id: string;
  timeline_id: string;
  export_type: string;
  file_uri: string;
  subtitle_file_uri?: string | null;
  status: string;
  adapter?: string | null;
  notes: string[];
  created_at?: string | null;
};

export type ExportJob = {
  job_id: string;
  status: string;
  export: ExportArtifact;
};

export type SubtitleArtifact = {
  subtitle_id: string;
  project_id: string;
  timeline_id: string;
  format: string;
  file_uri: string;
  status: string;
  notes: string[];
  created_at?: string | null;
  source_session_id?: string | null;
  source_session_revision?: number | null;
  is_current?: boolean;
  invalidated_at?: string | null;
  invalidated_reason?: string | null;
};

export type SubtitleJob = {
  job_id: string;
  status: string;
  subtitle: SubtitleArtifact;
};

export type ReviewApproval = {
  timeline_id: string;
  project_id: string;
  review_status: string;
  approved_at: string | null;
  updated_at: string;
  source_session_id: string | null;
  source_session_revision: number | null;
  is_current: boolean;
  invalidated_at: string | null;
  invalidated_reason: string | null;
};

export type AssetResponse = {
  asset_id: string;
  asset_type: string;
  storage_uri: string;
};

export type AssetRegistrationRequest = {
  source_path: string;
};

export type TtsCandidateRequest = {
  segment_text: string;
  voice_sample_asset_id: string;
  segment_id?: string;
  target_duration_sec?: number;
};

export type MediaLibraryAsset = {
  library_asset_id: string;
  asset_id: string;
  media_type: "music" | "sfx";
  duration_seconds: number;
  version: string;
  verified: boolean;
  available: boolean;
  tags: string[];
  source: string;
  creator: string;
  official_license_url: string;
  evidence_timestamp?: string;
  attribution_required: boolean;
  attribution_text: string;
};

export type MediaLibraryInstallState = {
  status: "not_installed" | "installed" | "degraded";
  installed_asset_count: number;
};

export type TtsCandidateResponse = AssetResponse & {
  candidate_id?: string | null;
  segment_id?: string | null;
  source_text?: string | null;
  technical_status: string;
  operator_review_status: string;
  target_duration_sec?: number | null;
  actual_duration_sec?: number | null;
  failure_code?: string | null;
};

export type TtsCandidateRecord = {
  candidate_id: string;
  project_id: string;
  segment_id: string;
  asset_id: string;
  source_text: string;
  technical_status: string;
  operator_review_status: string;
  target_duration_sec?: number | null;
  actual_duration_sec?: number | null;
  failure_code?: string | null;
  created_at: string;
};

export type FinalRenderArtifact = {
  export_id: string;
  timeline_id: string;
  export_type: string;
  file_uri: string;
  status: string;
  created_at?: string | null;
  source_session_id?: string | null;
  source_session_revision?: number | null;
  is_current?: boolean;
};

export type FinalRenderJob = {
  job_id: string;
  status: string;
  render: FinalRenderArtifact | null;
  error_message?: string | null;
};

export type RegisteredAsset = {
  asset_id: string;
  asset_type: string;
  storage_uri: string;
};

export type CapCutDraftExportArtifact = {
  export_id: string;
  timeline_id: string;
  export_type: string;
  file_uri: string;
  status: string;
  created_at?: string | null;
  notes: string[];
  handoff?: CapCutDraftHandoff | null;
  source_session_id?: string | null;
  source_session_revision?: number | null;
  is_current: boolean;
  invalidated_at?: string | null;
  invalidated_reason?: string | null;
};

export type CapCutDraftHandoff = {
  status: string;
  source_file_uri: string;
  registered_project_path?: string | null;
  error_message?: string | null;
  registered_at?: string | null;
  reused: boolean;
  recoverable?: boolean;
  recoverable_at?: string | null;
  source_session_id?: string | null;
  source_session_revision?: number | null;
};

export type CapCutHandoffDiagnostics = {
  status: string;
  installation_path?: string | null;
  detected_version?: string | null;
  is_supported: boolean;
  project_root_path: string;
  project_root_exists: boolean;
  write_access: boolean;
  recovery_message?: string | null;
  checked_at: string;
};

export type CapCutDraftExportJob = {
  job_id: string;
  status: string;
  export: CapCutDraftExportArtifact | null;
  error_message?: string | null;
};

export class ApiConflictError<T> extends Error {
  constructor(public readonly latestSession: T, public readonly path: string) {
    super(`Editing session conflict: ${path}`);
    this.name = "ApiConflictError";
  }
}

export class CapcutDraftHandoffInProgressError extends Error {
  readonly code = "capcut_draft_handoff_in_progress";

  constructor() {
    super("CapCut draft handoff is already in progress");
    this.name = "CapcutDraftHandoffInProgressError";
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    if (response.status === 409) {
      const payload = (await response.json()) as { latest_session?: T };
      if (payload.latest_session !== undefined) {
        throw new ApiConflictError(payload.latest_session, path);
      }
    }
    throw new Error(`Request failed: ${path} (${response.status})`);
  }
  return (await response.json()) as T;
}

const hermesYujinStatusStates = new Set<HermesYujinStatusState>([
  "not_configured",
  "stopped",
  "starting",
  "http_ready",
  "provider_ready",
  "chat_verified",
  "degraded",
]);
const hermesYujinStatusKeys = [
  "chat_verified",
  "checked_at",
  "http_ready",
  "last_chat_verified_at",
  "provider_ready",
  "restart_available",
  "state",
  "status_basis",
] as const;
const hermesYujinReadinessByState: Partial<
  Record<HermesYujinStatusState, readonly [boolean, boolean, boolean]>
> = {
  not_configured: [false, false, false],
  stopped: [false, false, false],
  starting: [false, false, false],
  http_ready: [true, false, false],
  provider_ready: [true, true, false],
  chat_verified: [true, true, true],
};

function isStrictUtcTimestamp(value: unknown): value is string {
  if (typeof value !== "string") {
    return false;
  }
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|\+00:00)$/.exec(value);
  const timestamp = Date.parse(value);
  if (match === null || Number.isNaN(timestamp)) {
    return false;
  }
  const parsed = new Date(timestamp);
  return parsed.getUTCFullYear() === Number(match[1])
    && parsed.getUTCMonth() + 1 === Number(match[2])
    && parsed.getUTCDate() === Number(match[3])
    && parsed.getUTCHours() === Number(match[4])
    && parsed.getUTCMinutes() === Number(match[5])
    && parsed.getUTCSeconds() === Number(match[6]);
}

function parseHermesYujinStatus(value: unknown): HermesYujinStatus {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("hermes_yujin_status_invalid");
  }
  const payload = value as Record<string, unknown>;
  const expectedReadiness = typeof payload.state === "string"
    ? hermesYujinReadinessByState[payload.state as HermesYujinStatusState]
    : undefined;
  if (
    JSON.stringify(Object.keys(payload).sort()) !== JSON.stringify(hermesYujinStatusKeys)
    || typeof payload.state !== "string"
    || !hermesYujinStatusStates.has(payload.state as HermesYujinStatusState)
    || typeof payload.http_ready !== "boolean"
    || typeof payload.provider_ready !== "boolean"
    || typeof payload.chat_verified !== "boolean"
    || !isStrictUtcTimestamp(payload.checked_at)
    || (
      payload.last_chat_verified_at !== null
      && !isStrictUtcTimestamp(payload.last_chat_verified_at)
    )
    || payload.restart_available !== false
    || payload.status_basis !== "application_path"
    || (
      typeof payload.last_chat_verified_at === "string"
      && Date.parse(payload.last_chat_verified_at) > Date.parse(payload.checked_at as string)
    )
    || (
      expectedReadiness !== undefined
      && (
        payload.http_ready !== expectedReadiness[0]
        || payload.provider_ready !== expectedReadiness[1]
        || payload.chat_verified !== expectedReadiness[2]
      )
    )
    || (
      payload.state === "degraded"
      && (payload.provider_ready || payload.chat_verified)
    )
  ) {
    throw new Error("hermes_yujin_status_invalid");
  }
  return payload as HermesYujinStatus;
}

const yujinMemoryCategories = new Set<YujinMemoryCategory>([
  "pacing", "caption", "audio", "tone", "workflow",
]);
const yujinMemoryConsentStatuses = new Set<YujinMemoryConsentStatus>([
  "pending", "approved", "rejected",
]);
const yujinMemoryStorageStatuses = new Set<YujinMemoryStorageStatus>([
  "not_requested",
  "claimed",
  "event_pending",
  "stored",
  "failed_retryable",
  "ambiguous",
  "deleted",
]);
const yujinMemoryRetryableStatuses = new Set<YujinMemoryStorageStatus>([
  "event_pending", "failed_retryable", "ambiguous",
]);
const yujinMemorySafeId = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const yujinMemoryCandidateKeys = [
  "candidate_id",
  "category",
  "client_request_id",
  "conversation_id",
  "created_at",
  "memory_scope",
  "project_id",
  "proposed_text",
  "retryable",
  "source_message_ids",
  "status",
  "storage_status",
  "updated_at",
] as const;
const yujinMemoryStoreResultKeys = [
  "candidate_id", "retryable", "status", "storage_status",
] as const;

function hasExactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
) {
  return JSON.stringify(Object.keys(value).sort())
    === JSON.stringify([...expected].sort());
}

function isBoundedMemoryText(value: unknown): value is string {
  return typeof value === "string"
    && value.trim().length > 0
    && value.length <= 280
    && new TextEncoder().encode(value).length <= 1024
    && !/[\p{Cc}\p{Cf}\p{Cs}]/u.test(value);
}

function isSafeYujinMemoryId(value: unknown): value is string {
  return typeof value === "string" && yujinMemorySafeId.test(value);
}

function parseYujinMemoryCandidate(
  value: unknown,
): YujinMemoryCandidate {
  if (
    typeof value !== "object"
    || value === null
    || Array.isArray(value)
  ) {
    throw new Error("yujin_memory_candidate_invalid");
  }
  const candidate = value as Record<string, unknown>;
  const storageStatus = candidate.storage_status;
  const createdAt = candidate.created_at;
  const updatedAt = candidate.updated_at;
  if (
    !hasExactKeys(candidate, yujinMemoryCandidateKeys)
    || !isSafeYujinMemoryId(candidate.candidate_id)
    || typeof candidate.project_id !== "string"
    || !candidate.project_id
    || candidate.project_id.length > 256
    || !isSafeYujinMemoryId(candidate.conversation_id)
    || !isSafeYujinMemoryId(candidate.client_request_id)
    || !Array.isArray(candidate.source_message_ids)
    || candidate.source_message_ids.length < 1
    || candidate.source_message_ids.length > 8
    || candidate.source_message_ids.some(
      (messageId) => !isSafeYujinMemoryId(messageId),
    )
    || new Set(candidate.source_message_ids).size
      !== candidate.source_message_ids.length
    || candidate.memory_scope !== "creator"
    || typeof candidate.category !== "string"
    || !yujinMemoryCategories.has(
      candidate.category as YujinMemoryCategory,
    )
    || !isBoundedMemoryText(candidate.proposed_text)
    || typeof candidate.status !== "string"
    || !yujinMemoryConsentStatuses.has(
      candidate.status as YujinMemoryConsentStatus,
    )
    || typeof storageStatus !== "string"
    || !yujinMemoryStorageStatuses.has(
      storageStatus as YujinMemoryStorageStatus,
    )
    || typeof candidate.retryable !== "boolean"
    || (
      storageStatus !== "claimed"
      && candidate.retryable !== yujinMemoryRetryableStatuses.has(
        storageStatus as YujinMemoryStorageStatus,
      )
    )
    || (
      candidate.status !== "approved"
      && storageStatus !== "not_requested"
    )
    || !isStrictUtcTimestamp(createdAt)
    || !isStrictUtcTimestamp(updatedAt)
    || Date.parse(updatedAt) < Date.parse(createdAt)
  ) {
    throw new Error("yujin_memory_candidate_invalid");
  }
  return candidate as YujinMemoryCandidate;
}

function parseYujinMemoryStoreResult(
  value: unknown,
): YujinMemoryStoreResult {
  if (
    typeof value !== "object"
    || value === null
    || Array.isArray(value)
  ) {
    throw new Error("yujin_memory_store_result_invalid");
  }
  const result = value as Record<string, unknown>;
  const storageStatus = result.storage_status;
  if (
    !hasExactKeys(result, yujinMemoryStoreResultKeys)
    || !isSafeYujinMemoryId(result.candidate_id)
    || result.status !== "approved"
    || typeof storageStatus !== "string"
    || !yujinMemoryStorageStatuses.has(
      storageStatus as YujinMemoryStorageStatus,
    )
    || typeof result.retryable !== "boolean"
    || (
      storageStatus !== "claimed"
      && result.retryable !== yujinMemoryRetryableStatuses.has(
        storageStatus as YujinMemoryStorageStatus,
      )
    )
  ) {
    throw new Error("yujin_memory_store_result_invalid");
  }
  return result as YujinMemoryStoreResult;
}

function yujinMemoryRequestInit(
  init: RequestInit = {},
): RequestInit {
  return {
    ...init,
    credentials: "same-origin",
    redirect: "error",
  };
}

async function listYujinMemoryCandidatesRequest(
  projectId: string,
  conversationId: string,
): Promise<YujinMemoryCandidate[]> {
  const payload = await request<unknown>(
    `/api/projects/${encodeURIComponent(projectId)}`
    + "/director/memory-candidates"
    + `?conversation_id=${encodeURIComponent(conversationId)}`,
    yujinMemoryRequestInit(),
  );
  if (
    typeof payload !== "object"
    || payload === null
    || Array.isArray(payload)
    || !hasExactKeys(payload as Record<string, unknown>, ["candidates"])
    || !Array.isArray((payload as Record<string, unknown>).candidates)
  ) {
    throw new Error("yujin_memory_candidate_invalid");
  }
  const candidates = (
    (payload as { candidates: unknown[] }).candidates
      .map(parseYujinMemoryCandidate)
  );
  if (candidates.some((candidate) => (
    candidate.project_id !== projectId
    || candidate.conversation_id !== conversationId
  ))) {
    throw new Error("yujin_memory_candidate_invalid");
  }
  return candidates;
}

async function createYujinMemoryCandidateRequest(
  projectId: string,
  body: YujinMemoryCandidateCreate,
): Promise<YujinMemoryCandidate> {
  const payload = await request<unknown>(
    `/api/projects/${encodeURIComponent(projectId)}`
    + "/director/memory-candidates",
    yujinMemoryRequestInit({
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
  const candidate = parseYujinMemoryCandidate(payload);
  if (
    candidate.project_id !== projectId
    || candidate.conversation_id !== body.conversation_id
    || candidate.client_request_id !== body.client_request_id
    || candidate.memory_scope !== body.memory_scope
    || candidate.category !== body.category
    || candidate.proposed_text !== body.proposed_text
    || JSON.stringify(candidate.source_message_ids)
      !== JSON.stringify(body.source_message_ids)
  ) {
    throw new Error("yujin_memory_candidate_invalid");
  }
  return candidate;
}

async function yujinMemoryCandidateActionRequest(
  projectId: string,
  candidateId: string,
  action: "approve" | "reject",
): Promise<YujinMemoryCandidate> {
  const payload = await request<unknown>(
    `/api/projects/${encodeURIComponent(projectId)}`
    + `/director/memory-candidates/${encodeURIComponent(candidateId)}`
    + `/${action}`,
    yujinMemoryRequestInit({ method: "POST" }),
  );
  return parseYujinMemoryCandidate(payload);
}

async function storeYujinMemoryCandidateRequest(
  projectId: string,
  candidateId: string,
  clientRequestId: string,
): Promise<YujinMemoryStoreResult> {
  const payload = await request<unknown>(
    `/api/projects/${encodeURIComponent(projectId)}`
    + `/director/memory-candidates/${encodeURIComponent(candidateId)}`
    + "/store",
    yujinMemoryRequestInit({
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_request_id: clientRequestId }),
    }),
  );
  return parseYujinMemoryStoreResult(payload);
}

async function deleteYujinMemoryCandidateRequest(
  projectId: string,
  candidateId: string,
): Promise<YujinMemoryStoreResult> {
  const payload = await request<unknown>(
    `/api/projects/${encodeURIComponent(projectId)}`
    + `/director/memory-candidates/${encodeURIComponent(candidateId)}`
    + "/stored-memory",
    yujinMemoryRequestInit({ method: "DELETE" }),
  );
  return parseYujinMemoryStoreResult(payload);
}

async function getHermesYujinStatusRequest(
  signal?: AbortSignal,
): Promise<HermesYujinStatus> {
  const payload = await request<unknown>(
    "/api/hermes-yujin/status",
    { signal },
  );
  return parseHermesYujinStatus(payload);
}

async function registerCapcutDraftHandoffRequest(path: string): Promise<{ handoff: CapCutDraftHandoff }> {
  const response = await fetch(path, { method: "POST" });
  if (response.status === 400) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    if (payload?.detail === "capcut_draft_handoff_in_progress") throw new CapcutDraftHandoffInProgressError();
  }
  if (!response.ok) throw new Error(`Request failed: ${path} (${response.status})`);
  return (await response.json()) as { handoff: CapCutDraftHandoff };
}

async function sendDirectorMessageRequest(path: string, payload: DirectorMessageSubmitRequest, signal?: AbortSignal): Promise<DirectorMessageSendResult> {
  const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), signal });
  if (response.status === 202) {
    const retryAfterSeconds = Number(response.headers.get("Retry-After") ?? "1");
    return { kind: "in_progress", retryAfterSeconds: Number.isFinite(retryAfterSeconds) ? retryAfterSeconds : 1 };
  }
  if (!response.ok) throw new Error(`Request failed: ${path} (${response.status})`);
  return { kind: "exchange", exchange: (await response.json()) as DirectorMessageExchange };
}

async function preflightDirectorProposalRequest(path: string): Promise<DirectorProposalPreflight> {
  const response = await fetch(path, { method: "POST" });
  const payload = (await response.json()) as DirectorProposalPreflight;
  if (response.status === 409 && (payload.code === "stale_proposal" || payload.status === "stale")) return { ...payload, status: "stale", code: "stale_proposal" };
  if (!response.ok) throw new Error(`Request failed: ${path} (${response.status})`);
  return payload;
}

async function openHermesRunEventsRequest(
  projectId: string,
  conversationId: string,
  run: HermesRunCreateResponse,
  signal: AbortSignal,
  lastEventId = 0,
): Promise<Response> {
  const path = run.events_url;
  const expectedPath = `/api/projects/${encodeURIComponent(projectId)}/director/conversations/${encodeURIComponent(conversationId)}/hermes-runs/${encodeURIComponent(run.run_id)}/events`;
  let parsed: URL;
  try {
    parsed = new URL(path, window.location.origin);
  } catch {
    throw new Error("유진 응답을 시작하지 못했어요.");
  }
  if (
    run.conversation_id !== conversationId
    || !path.startsWith("/")
    || parsed.origin !== window.location.origin
    || parsed.search
    || parsed.hash
    || parsed.pathname !== expectedPath
    || path !== expectedPath
  ) {
    throw new Error("유진 응답을 시작하지 못했어요.");
  }
  if (
    !Number.isSafeInteger(lastEventId)
    || lastEventId < 0
  ) {
    throw new Error("유진 응답을 시작하지 못했어요.");
  }
  const headers = new Headers({ Accept: "text/event-stream" });
  if (lastEventId > 0) {
    headers.set("Last-Event-ID", String(lastEventId));
  }
  const response = await fetch(path, {
    method: "GET",
    headers,
    credentials: "same-origin",
    redirect: "error",
    signal,
  });
  if (!response.ok || response.redirected) {
    throw new Error("유진 응답을 시작하지 못했어요.");
  }
  return response;
}

async function cancelHermesRunRequest(
  projectId: string,
  conversationId: string,
  runId: string,
  signal?: AbortSignal,
): Promise<void> {
  const path = `/api/projects/${encodeURIComponent(projectId)}/director/conversations/${encodeURIComponent(conversationId)}/hermes-runs/${encodeURIComponent(runId)}/cancel`;
  const response = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    redirect: "error",
    signal,
  });
  if (response.status !== 204 || response.redirected) {
    throw new Error("유진 요청을 중단하지 못했어요.");
  }
}

async function retryHermesRunRequest(
  projectId: string,
  conversationId: string,
  runId: string,
  signal?: AbortSignal,
): Promise<HermesRunCreateResponse> {
  const path = `/api/projects/${encodeURIComponent(projectId)}/director/conversations/${encodeURIComponent(conversationId)}/hermes-runs/${encodeURIComponent(runId)}/retry`;
  const response = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    redirect: "error",
    signal,
  });
  if (response.status !== 201 || response.redirected) {
    throw new Error("같은 요청을 다시 시작하지 못했어요.");
  }
  const candidate = await response.json() as Record<string, unknown>;
  const expectedEventsUrl = `/api/projects/${encodeURIComponent(projectId)}/director/conversations/${encodeURIComponent(conversationId)}/hermes-runs/${encodeURIComponent(String(candidate.run_id ?? ""))}/events`;
  if (
    Object.keys(candidate).length !== 3
    || typeof candidate.run_id !== "string"
    || !candidate.run_id
    || candidate.conversation_id !== conversationId
    || candidate.events_url !== expectedEventsUrl
  ) {
    throw new Error("같은 요청을 다시 시작하지 못했어요.");
  }
  return candidate as HermesRunCreateResponse;
}

async function createHermesRunRequest(
  projectId: string,
  conversationId: string,
  payload: HermesRunCreateRequest,
  signal?: AbortSignal,
): Promise<HermesRunCreateResponse> {
  const path = `/api/projects/${encodeURIComponent(projectId)}/director/conversations/${encodeURIComponent(conversationId)}/hermes-runs`;
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    redirect: "error",
    signal,
    body: JSON.stringify(payload),
  });
  if (response.status !== 201 || response.redirected) {
    throw new Error("유진 응답을 시작하지 못했어요.");
  }
  let candidate: unknown;
  try {
    candidate = await response.json();
  } catch {
    throw new Error("유진 응답을 시작하지 못했어요.");
  }
  if (
    !candidate
    || typeof candidate !== "object"
    || Array.isArray(candidate)
    || Object.keys(candidate).length !== 3
  ) {
    throw new Error("유진 응답을 시작하지 못했어요.");
  }
  const run = candidate as Record<string, unknown>;
  if (
    typeof run.run_id !== "string"
    || !run.run_id
    || typeof run.conversation_id !== "string"
    || run.conversation_id !== conversationId
    || typeof run.events_url !== "string"
  ) {
    throw new Error("유진 응답을 시작하지 못했어요.");
  }
  const expectedEventsUrl = `${path}/${encodeURIComponent(run.run_id)}/events`;
  if (run.events_url !== expectedEventsUrl) {
    throw new Error("유진 응답을 시작하지 못했어요.");
  }
  return run as HermesRunCreateResponse;
}

export const api = {
  getHermesYujinStatus: (signal?: AbortSignal) =>
    getHermesYujinStatusRequest(signal),
  listYujinMemoryCandidates: (
    projectId: string,
    conversationId: string,
  ) => listYujinMemoryCandidatesRequest(projectId, conversationId),
  createYujinMemoryCandidate: (
    projectId: string,
    body: YujinMemoryCandidateCreate,
  ) => createYujinMemoryCandidateRequest(projectId, body),
  approveYujinMemoryCandidate: (
    projectId: string,
    candidateId: string,
  ) => yujinMemoryCandidateActionRequest(
    projectId, candidateId, "approve",
  ),
  rejectYujinMemoryCandidate: (
    projectId: string,
    candidateId: string,
  ) => yujinMemoryCandidateActionRequest(
    projectId, candidateId, "reject",
  ),
  storeYujinMemoryCandidate: (
    projectId: string,
    candidateId: string,
    clientRequestId: string,
  ) => storeYujinMemoryCandidateRequest(
    projectId, candidateId, clientRequestId,
  ),
  deleteYujinMemoryCandidate: (
    projectId: string,
    candidateId: string,
  ) => deleteYujinMemoryCandidateRequest(projectId, candidateId),
  createCreationBrief: (projectId: string, payload: CreateCreationBriefRequest) =>
    request<CreationBrief>(`/api/projects/${encodeURIComponent(projectId)}/creation-briefs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  uploadCreationBrief: (projectId: string, scriptFile: File, payload: { idempotency_key: string; capability_profile: Record<string, unknown> }) => {
    const form = new FormData();
    form.append("script_file", scriptFile);
    form.append("idempotency_key", payload.idempotency_key);
    form.append("capability_profile_json", JSON.stringify(payload.capability_profile));
    return request<CreationBrief>(`/api/projects/${encodeURIComponent(projectId)}/creation-briefs/upload`, { method: "POST", body: form });
  },
  getCreationBrief: (projectId: string, briefId: string) =>
    request<CreationBrief>(`/api/projects/${encodeURIComponent(projectId)}/creation-briefs/${encodeURIComponent(briefId)}`),
  answerCreationBriefQuestion: (projectId: string, briefId: string, questionId: string, payload: { answer: string; expected_revision?: number }) =>
    request<CreationBrief>(`/api/projects/${encodeURIComponent(projectId)}/creation-briefs/${encodeURIComponent(briefId)}/answers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question_id: questionId, ...payload }),
    }),
  previousCreationBriefQuestion: (projectId: string, briefId: string, payload: { expected_revision: number }) =>
    request<CreationBrief>(`/api/projects/${encodeURIComponent(projectId)}/creation-briefs/${encodeURIComponent(briefId)}/previous-question`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  updateCreationBriefSummary: (projectId: string, briefId: string, payload: { summary: string; expected_revision: number }) =>
    request<CreationBrief>(`/api/projects/${encodeURIComponent(projectId)}/creation-briefs/${encodeURIComponent(briefId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  approveCreationBrief: (projectId: string, briefId: string, payload: { expected_revision: number }) =>
    request<CreationBrief>(`/api/projects/${encodeURIComponent(projectId)}/creation-briefs/${encodeURIComponent(briefId)}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  bypassCreationBriefInterview: (projectId: string, briefId: string, payload: { expected_revision: number }) =>
    request<CreationBrief>(`/api/projects/${encodeURIComponent(projectId)}/creation-briefs/${encodeURIComponent(briefId)}/bypass`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  deleteCreationBrief: async (projectId: string, briefId: string): Promise<void> => {
    const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/creation-briefs/${encodeURIComponent(briefId)}`, { method: "DELETE" });
    if (!response.ok) throw new Error(`Request failed: creation brief delete (${response.status})`);
  },
  startDraftReadiness: (projectId: string, payload: DraftReadinessRequest) =>
    request<DraftReadiness>(`/api/projects/${encodeURIComponent(projectId)}/draft-readiness`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }),
  getDraftReadiness: (projectId: string, readinessId: string) => request<DraftReadiness>(`/api/projects/${encodeURIComponent(projectId)}/draft-readiness/${encodeURIComponent(readinessId)}`),
  retryDraftReadiness: (projectId: string, readinessId: string, expected_revision: number) => request<DraftReadiness>(`/api/projects/${encodeURIComponent(projectId)}/draft-readiness/${encodeURIComponent(readinessId)}/retry`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_revision }) }),
  completeDraftReadiness: (projectId: string, readinessId: string, expected_revision: number) => request<DraftReadiness>(`/api/projects/${encodeURIComponent(projectId)}/draft-readiness/${encodeURIComponent(readinessId)}/complete`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_revision }) }),
  updateDraftReadinessCandidate: (projectId: string, readinessId: string, asset_id: string, skipped: boolean, expected_revision: number) => request<DraftReadiness>(`/api/projects/${encodeURIComponent(projectId)}/draft-readiness/${encodeURIComponent(readinessId)}/candidates`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ asset_id, skipped, expected_revision }) }),
  updateDraftReadinessCandidateRange: (projectId: string, readinessId: string, asset_id: string, start_sec: number, end_sec: number, expected_revision: number) => request<DraftReadiness>(`/api/projects/${encodeURIComponent(projectId)}/draft-readiness/${encodeURIComponent(readinessId)}/candidates/range`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ asset_id, start_sec, end_sec, expected_revision }) }),
  cancelDraftReadiness: (projectId: string, readinessId: string, expected_revision: number) => request<DraftReadiness>(`/api/projects/${encodeURIComponent(projectId)}/draft-readiness/${encodeURIComponent(readinessId)}/cancel`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_revision }) }),
  createAtomicDraftBundle: (projectId: string, payload: AtomicDraftBundleRequest) => request<AtomicDraftBundle>(`/api/projects/${encodeURIComponent(projectId)}/draft-bundles`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }),
  listDraftNarrationOptions: async (projectId: string): Promise<NarrationOption[]> => (await request<{ assets: NarrationOption[] }>(`/api/projects/${encodeURIComponent(projectId)}/draft-readiness/narration-options`)).assets,
  uploadDraftNarration: (projectId: string, file: File) => { const form = new FormData(); form.append("file", file); return request<{ asset_id: string; asset_type: string }>(`/api/projects/${encodeURIComponent(projectId)}/draft-readiness/narration/upload`, { method: "POST", body: form }); },
  uploadDraftBroll: (projectId: string, file: File) => { const form = new FormData(); form.append("file", file); return request<{ asset_id: string; asset_type: string; scan_status: string }>(`/api/projects/${encodeURIComponent(projectId)}/draft-readiness/broll/upload`, { method: "POST", body: form }); },
  reloadDirectorSession: (projectId: string, sessionId: string) =>
    request<DirectorReloadState>(`/api/projects/${projectId}/director/sessions/${sessionId}/reload`),
  createDirectorConversation: (projectId: string, payload: { session_id: string }) =>
    request<DirectorConversation>(`/api/projects/${projectId}/director/conversations`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }),
  listDirectorMessages: async (projectId: string, conversationId: string, sessionId: string): Promise<DirectorMessage[]> =>
    (await request<{ messages: DirectorMessage[] }>(`/api/projects/${projectId}/director/conversations/${conversationId}/messages?session_id=${encodeURIComponent(sessionId)}`)).messages,
  sendDirectorMessage: (projectId: string, conversationId: string, payload: DirectorMessageSubmitRequest, signal?: AbortSignal) =>
    sendDirectorMessageRequest(`/api/projects/${projectId}/director/conversations/${conversationId}/messages`, payload, signal),
  prepareDirectorMessage: (projectId: string, conversationId: string, payload: DirectorMessageSubmitRequest) => {
    const submit = () => sendDirectorMessageRequest(`/api/projects/${projectId}/director/conversations/${conversationId}/messages`, payload);
    return { clientMessageId: payload.client_message_id, send: submit, retry: submit };
  },
  createHermesRun: (projectId: string, conversationId: string, payload: HermesRunCreateRequest, signal?: AbortSignal) =>
    createHermesRunRequest(projectId, conversationId, payload, signal),
  openHermesRunEvents: (
    projectId: string,
    conversationId: string,
    run: HermesRunCreateResponse,
    signal: AbortSignal,
    lastEventId = 0,
  ) => openHermesRunEventsRequest(
    projectId,
    conversationId,
    run,
    signal,
    lastEventId,
  ),
  cancelHermesRun: (
    projectId: string,
    conversationId: string,
    runId: string,
    signal?: AbortSignal,
  ) => cancelHermesRunRequest(
    projectId,
    conversationId,
    runId,
    signal,
  ),
  retryHermesRun: (
    projectId: string,
    conversationId: string,
    runId: string,
    signal?: AbortSignal,
  ) => retryHermesRunRequest(
    projectId,
    conversationId,
    runId,
    signal,
  ),
  applyDirectorProposal: (projectId: string, proposalId: string, payload: { candidate_ids: string[]; expected_revision: number }) =>
    request<ApplyDirectorProposalResponse>(`/api/projects/${projectId}/director/proposals/${proposalId}/apply`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ candidate_ids: payload.candidate_ids, expected_revision: payload.expected_revision }) }),
  batchApplyDirectorProposal: (projectId: string, proposalId: string, payload: { candidate_ids: string[]; expected_revision: number }) =>
    request<ApplyDirectorProposalResponse>(`/api/projects/${projectId}/director/proposals/${proposalId}/batch-apply`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }),
  materializeDirectorCandidate: (projectId: string, proposalId: string, candidateId: string) =>
    request<AssetResponse>(`/api/projects/${projectId}/director/proposals/${proposalId}/candidates/${encodeURIComponent(candidateId)}/materialize`, { method: "POST" }),
  directorCandidatePreviewUrl: (projectId: string, proposalId: string, candidateId: string) =>
    `/api/projects/${projectId}/director/proposals/${proposalId}/candidates/${encodeURIComponent(candidateId)}/preview`,
  createDirectorProposal: (projectId: string, payload: DirectorProposalCreateRequest) =>
    request<DirectorProposal>(`/api/projects/${projectId}/director/proposals`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }),
  getDirectorProposal: (projectId: string, proposalId: string) =>
    request<DirectorProposal>(`/api/projects/${projectId}/director/proposals/${proposalId}`),
  preflightDirectorProposal: (projectId: string, proposalId: string) =>
    preflightDirectorProposalRequest(`/api/projects/${projectId}/director/proposals/${proposalId}/preflight`),
  refreshDirectorProposal: (projectId: string, proposalId: string) =>
    request<DirectorProposal>(`/api/projects/${projectId}/director/proposals/${proposalId}/refresh`, { method: "POST" }),
  getDirectorPreferences: (projectId: string) => request<DirectorPreferences>(`/api/projects/${projectId}/director/preferences`),
  updateDirectorPreferences: (projectId: string, payload: DirectorPreferences) =>
    request<DirectorPreferences>(`/api/projects/${projectId}/director/preferences`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }),
  getMediaLibraryInstallState: () => request<MediaLibraryInstallState>("/api/media-library/install-state"),
  listMediaLibraryAssets: () => request<{ assets: MediaLibraryAsset[] }>("/api/media-library/assets"),
  listMediaLibraryFavorites: () => request<{ asset_ids: string[] }>("/api/media-library/favorites"),
  listRecentMediaLibraryAssetIds: () => request<{ asset_ids: string[] }>("/api/media-library/recent"),
  setMediaLibraryFavorite: (libraryAssetId: string, enabled: boolean) =>
    request<{ asset_ids: string[] }>(`/api/media-library/assets/${encodeURIComponent(libraryAssetId)}/favorite`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled }),
    }),
  listProjectMediaLibraryFavorites: (projectId: string) =>
    request<{ asset_ids: string[] }>(`/api/projects/${projectId}/media-library/favorites`),
  listProjectRecentMediaLibraryAssetIds: (projectId: string) =>
    request<{ asset_ids: string[] }>(`/api/projects/${projectId}/media-library/recent`),
  setProjectMediaLibraryFavorite: (projectId: string, libraryAssetId: string, enabled: boolean) =>
    request<{ asset_ids: string[] }>(`/api/projects/${projectId}/media-library/assets/${encodeURIComponent(libraryAssetId)}/favorite`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled }),
    }),
  materializeMediaLibraryAsset: (libraryAssetId: string, projectId: string) =>
    request<AssetResponse>(`/api/media-library/assets/${encodeURIComponent(libraryAssetId)}/materialize`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ project_id: projectId }),
    }),
  mediaLibraryPreviewUrl: (libraryAssetId: string) =>
    `/api/media-library/assets/${encodeURIComponent(libraryAssetId)}/preview`,
  listEditorPresets: (projectId: string) =>
    request<EditorPreset[]>(`/api/projects/${projectId}/editor-library/presets`),
  listEditorFavorites: (projectId: string) =>
    request<EditorFavorite[]>(`/api/projects/${projectId}/editor-library/favorites`),
  listRecentEditorPresetIds: (projectId: string) =>
    request<string[]>(`/api/projects/${projectId}/editor-library/recent-presets`),
  markRecentEditorPreset: (projectId: string, presetId: string) =>
    request<string[]>(`/api/projects/${projectId}/editor-library/recent-presets/${presetId}`, {
      method: "PUT",
    }),
  toggleEditorFavorite: (
    projectId: string,
    favoriteId: string,
    payload: { favorite_type: EditorFavorite["favorite_type"]; enabled: boolean },
  ) =>
    request<EditorFavorite & { enabled: boolean }>(
      `/api/projects/${projectId}/editor-library/favorites/${favoriteId}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    ),
  createProject: (payload: { name: string }) =>
    request<Project>("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  listProjects: async (includeArchived = false): Promise<Project[]> => {
    // Task 32: the server hides archived projects unless asked. Without this
    // the sidebar could never show one, so archiving was a one-way door.
    const payload = await request<{ projects: Project[] }>(
      includeArchived ? "/api/projects?include_archived=true" : "/api/projects",
    );
    return payload.projects;
  },
  getProject: (projectId: string) => request<Project>(`/api/projects/${projectId}`),
  archiveProject: (projectId: string) => request<Project>(`/api/projects/${encodeURIComponent(projectId)}/archive`, { method: "POST" }),
  restoreProject: (projectId: string) => request<Project>(`/api/projects/${encodeURIComponent(projectId)}/restore`, { method: "POST" }),
  deleteProjectPermanently: async (projectId: string): Promise<void> => {
    // Not request<T>(): a successful delete returns 204 with no body, and
    // request<T>() always calls response.json(), which throws on an empty
    // body.
    const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}?confirm=true`, { method: "DELETE" });
    if (!response.ok) throw new Error(`Request failed: /api/projects/${projectId} (${response.status})`);
  },
  registerNarrationAudio: (projectId: string, payload: { source_path: string }) =>
    request<RegisteredAsset>(`/api/projects/${projectId}/assets/narration-audio`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  registerScriptDocument: (projectId: string, payload: { source_path: string }) =>
    request<RegisteredAsset>(`/api/projects/${projectId}/assets/script-document`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  listMediaInboxAssets: async (): Promise<MediaInboxAsset[]> =>
    (await request<{ assets: MediaInboxAsset[] }>("/api/media-inbox/assets")).assets,
  importMediaInboxAsset: (projectId: string, filename: string) =>
    request<MediaInboxImport>(
      `/api/projects/${encodeURIComponent(projectId)}/media-inbox/import`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename }),
      },
    ),
  listBrollAssets: async (projectId: string): Promise<BrollAsset[]> => {
    const payload = await request<{ assets: BrollAsset[] }>(
      `/api/projects/${projectId}/assets/broll-video`,
    );
    return payload.assets;
  },
  importBrollBatch: async (
    projectId: string,
    payload: BrollBatchImportRequest,
  ): Promise<BrollBatchImportResponse> => {
    return request<BrollBatchImportResponse>(
      `/api/projects/${projectId}/assets/broll-video/batch`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      },
    );
  },
  listJobs: async (projectId: string): Promise<JobRecord[]> => {
    const payload = await request<{ jobs: JobRecord[] }>(`/api/projects/${projectId}/jobs`);
    return payload.jobs;
  },
  listAllJobs: async (): Promise<JobRecordWithProject[]> => {
    const payload = await request<{ jobs: JobRecordWithProject[] }>("/api/jobs");
    return payload.jobs;
  },
  buildTimeline: (projectId: string, payload: BuildTimelineRequest) =>
    request<{ job_id: string; status: string }>(`/api/projects/${projectId}/jobs/build-timeline`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }),
  approveTimeline: (projectId: string, jobId: string) =>
    request<ReviewApproval>(`/api/projects/${projectId}/review-approvals/${jobId}/approve`, {
      method: "POST",
    }),
  reopenTimeline: (projectId: string, jobId: string) =>
    request<ReviewApproval>(`/api/projects/${projectId}/review-approvals/${jobId}/reopen`, {
      method: "POST",
    }),
  renderSubtitle: (projectId: string, payload: OutputJobRequest) =>
    request<{ job_id: string; status: string }>(`/api/projects/${projectId}/jobs/subtitle-render`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }),
  getTimeline: (projectId: string, jobId: string) =>
    request<TimelineJob>(`/api/projects/${projectId}/timelines/${jobId}`),
  getReviewSnapshot: (projectId: string, jobId: string) =>
    request<ReviewSnapshot>(`/api/projects/${projectId}/review-snapshots/${jobId}`),
  getReviewApproval: (projectId: string, timelineId: string) =>
    request<ReviewApproval>(`/api/projects/${projectId}/review-approvals/timelines/${timelineId}`),
  approveReviewRecommendation: (
    projectId: string,
    jobId: string,
    recommendationId: string,
  ) =>
    request<ReviewSnapshot>(
      `/api/projects/${projectId}/review-snapshots/${jobId}/recommendations/${recommendationId}/approve`,
      {
        method: "POST",
      },
    ),
  createEditingSession: (projectId: string, payload: CreateEditingSessionRequest) =>
    request<EditingSession>(`/api/projects/${projectId}/editing-sessions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }),
  getEditingSession: (projectId: string, sessionId: string) =>
    request<EditingSession>(`/api/projects/${projectId}/editing-sessions/${sessionId}`),
  getLatestEditingSession: async (projectId: string): Promise<EditingSession | null> => {
    const response = await fetch(`/api/projects/${projectId}/editing-sessions/latest`, undefined);
    if (response.status === 404) {
      return null;
    }
    if (!response.ok) {
      throw new Error(
        `Request failed: /api/projects/${projectId}/editing-sessions/latest (${response.status})`,
      );
    }
    return (await response.json()) as EditingSession;
  },
  listMediaAnalysis: (projectId: string) => request<{ items: MediaAnalysis[] }>(`/api/projects/${projectId}/media-analysis`),
  cancelMediaAnalysis: (projectId: string, analysisId: string) => request<MediaAnalysis>(`/api/projects/${projectId}/media-analysis/${analysisId}/cancel`, { method: "POST" }),
  retryMediaAnalysis: (projectId: string, analysisId: string) => request<MediaAnalysis>(`/api/projects/${projectId}/media-analysis/${analysisId}/retry`, { method: "POST" }),
  reviewMediaAnalysis: (projectId: string, analysisId: string, tags: Record<string, string[]>) => request<MediaAnalysis>(`/api/projects/${projectId}/media-analysis/${analysisId}/review`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tags }) }),
  mediaAnalysisPreview: (projectId: string, assetId: string) => request<{ analysis_id: string; preview: unknown }>(`/api/projects/${projectId}/assets/${assetId}/analysis-preview`),
  getEditingSessionFixedTimeline: (projectId: string, sessionId: string) =>
    request<FixedTimeline>(`/api/projects/${projectId}/editing-sessions/${sessionId}/fixed-timeline`),
  getEditorPlaybackManifest: (projectId: string, sessionId: string) =>
    request<EditorPlaybackManifest>(`/api/projects/${encodeURIComponent(projectId)}/editing-sessions/${encodeURIComponent(sessionId)}/playback-manifest`),
  startExactPreview: (projectId: string, sessionId: string, payload: { expected_revision: number; start_sec?: number; end_sec?: number }) =>
    request<ExactPreviewResponse>(`/api/projects/${encodeURIComponent(projectId)}/editing-sessions/${encodeURIComponent(sessionId)}/exact-preview`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    }),
  previewEditingSessionSelectedRange: (projectId: string, sessionId: string, payload: { start_sec: number; end_sec: number }) =>
    request<SelectedRangePreview>(`/api/projects/${projectId}/editing-sessions/${sessionId}/selected-range-preview`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    }),
  splitEditingSessionSegment: (projectId: string, sessionId: string, segmentId: string, payload: SegmentSplitRequest) =>
    request<EditingSession>(`/api/projects/${projectId}/editing-sessions/${sessionId}/segments/${segmentId}/split`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    }),
  mergeEditingSessionSegments: (projectId: string, sessionId: string, payload: RevisionedEditingSessionMutation & { left_segment_id: string; right_segment_id: string }) =>
    request<EditingSession>(`/api/projects/${projectId}/editing-sessions/${sessionId}/segments/merge`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    }),
  updateEditingSessionSegmentBounds: (projectId: string, sessionId: string, segmentId: string, payload: SegmentBoundsRequest) =>
    request<EditingSession>(`/api/projects/${projectId}/editing-sessions/${sessionId}/segments/${segmentId}/bounds`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    }),
  reorderEditingSessionSegments: (projectId: string, sessionId: string, payload: SegmentOrderRequest) =>
    request<EditingSession>(`/api/projects/${projectId}/editing-sessions/${sessionId}/segment-order`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    }),
  updateEditingSessionTimelinePlacements: (projectId: string, sessionId: string, payload: TimelinePlacementPatchRequest) =>
    request<EditingSession>(`/api/projects/${projectId}/editing-sessions/${sessionId}/timeline-placements`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    }),
  undoEditingSession: (projectId: string, sessionId: string, expectedRevision: number) =>
    request<EditingSession>(`/api/projects/${projectId}/editing-sessions/${sessionId}/undo`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_revision: expectedRevision }),
    }),
  redoEditingSession: (projectId: string, sessionId: string, expectedRevision: number) =>
    request<EditingSession>(`/api/projects/${projectId}/editing-sessions/${sessionId}/redo`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_revision: expectedRevision }),
    }),
  previewEditingSessionCaptionStyleScope: (
    projectId: string,
    sessionId: string,
    payload: CaptionStyleMutationRequest,
  ) =>
    request<CaptionStyleScopePreflight>(
      `/api/projects/${projectId}/editing-sessions/${sessionId}/caption-style/preflight`,
      { method: 'POST', headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) },
    ),
  updateEditingSessionCaptionStyle: (
    projectId: string,
    sessionId: string,
    payload: CaptionStyleMutationRequest,
  ) =>
    request<EditingSession>(
      `/api/projects/${projectId}/editing-sessions/${sessionId}/caption-style`,
      { method: 'PATCH', headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) },
    ),
  updateEditingSessionCaption: (
    projectId: string,
    sessionId: string,
    segmentId: string,
    payload: CaptionOverrideRequest,
  ) =>
    request<EditingSession>(
      `/api/projects/${projectId}/editing-sessions/${sessionId}/segments/${segmentId}/caption`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      },
    ),
  updateEditingSessionCutAction: (
    projectId: string,
    sessionId: string,
    segmentId: string,
    payload: CutActionOverrideRequest,
  ) =>
    request<EditingSession>(
      `/api/projects/${projectId}/editing-sessions/${sessionId}/segments/${segmentId}/cut-action`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      },
    ),
  updateEditingSessionBroll: (
    projectId: string,
    sessionId: string,
    segmentId: string,
    payload: BrollOverrideRequest,
  ) =>
    request<EditingSession>(
      `/api/projects/${projectId}/editing-sessions/${sessionId}/segments/${segmentId}/broll`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      },
    ),
  clearEditingSessionBrollOverride: (
    projectId: string,
    sessionId: string,
    segmentId: string,
    expectedRevision: number,
  ) =>
    request<EditingSession>(
      `/api/projects/${projectId}/editing-sessions/${sessionId}/segments/${segmentId}/broll?expected_revision=${expectedRevision}`,
      {
        method: "DELETE",
      },
    ),
  updateEditingSessionMusicOverride: (
    projectId: string,
    sessionId: string,
    segmentId: string,
    payload: MusicOverrideRequest,
  ) =>
    request<EditingSession>(
      `/api/projects/${projectId}/editing-sessions/${sessionId}/segments/${segmentId}/music`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      },
    ),
  clearEditingSessionMusicOverride: (
    projectId: string,
    sessionId: string,
    segmentId: string,
    expectedRevision: number,
  ) =>
    request<EditingSession>(
      `/api/projects/${projectId}/editing-sessions/${sessionId}/segments/${segmentId}/music?expected_revision=${expectedRevision}`,
      {
        method: "DELETE",
      },
    ),
  updateEditingSessionSfxOverride: (
    projectId: string,
    sessionId: string,
    segmentId: string,
    payload: BrollOverrideRequest,
  ) =>
    request<EditingSession>(
      `/api/projects/${projectId}/editing-sessions/${sessionId}/segments/${segmentId}/sfx`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    ),
  clearEditingSessionSfxOverride: (
    projectId: string,
    sessionId: string,
    segmentId: string,
    expectedRevision: number,
  ) =>
    request<EditingSession>(
      `/api/projects/${projectId}/editing-sessions/${sessionId}/segments/${segmentId}/sfx?expected_revision=${expectedRevision}`,
      { method: "DELETE" },
    ),
  updateEditingSessionExplanationCard: (
    projectId: string,
    sessionId: string,
    segmentId: string,
    payload: ExplanationCardRequest,
  ) =>
    request<EditingSession>(
      `/api/projects/${projectId}/editing-sessions/${sessionId}/segments/${segmentId}/explanation-card`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      },
    ),
  removeEditingSessionExplanationCard: (
    projectId: string,
    sessionId: string,
    segmentId: string,
    expectedRevision: number,
  ) =>
    request<EditingSession>(
      `/api/projects/${projectId}/editing-sessions/${sessionId}/segments/${segmentId}/explanation-card?expected_revision=${expectedRevision}`,
      {
        method: "DELETE",
      },
    ),
  updateEditingSessionImageOverlay: (
    projectId: string,
    sessionId: string,
    segmentId: string,
    payload: ImageOverlayRequest,
  ) =>
    request<EditingSession>(
      `/api/projects/${projectId}/editing-sessions/${sessionId}/segments/${segmentId}/image-overlay`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      },
    ),
  removeEditingSessionImageOverlay: (
    projectId: string,
    sessionId: string,
    segmentId: string,
    expectedRevision: number,
  ) =>
    request<EditingSession>(
      `/api/projects/${projectId}/editing-sessions/${sessionId}/segments/${segmentId}/image-overlay?expected_revision=${expectedRevision}`,
      {
        method: "DELETE",
      },
    ),
  updateEditingSessionTableOverlay: (
    projectId: string,
    sessionId: string,
    segmentId: string,
    payload: TableOverlayRequest,
  ) =>
    request<EditingSession>(
      `/api/projects/${projectId}/editing-sessions/${sessionId}/segments/${segmentId}/table-overlay`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      },
    ),
  removeEditingSessionTableOverlay: (
    projectId: string,
    sessionId: string,
    segmentId: string,
    expectedRevision: number,
  ) =>
    request<EditingSession>(
      `/api/projects/${projectId}/editing-sessions/${sessionId}/segments/${segmentId}/table-overlay?expected_revision=${expectedRevision}`,
      {
        method: "DELETE",
      },
    ),
  updateEditingSessionTtsReplacement: (
    projectId: string,
    sessionId: string,
    segmentId: string,
    payload: TtsReplacementRequest,
  ) =>
    request<EditingSession>(
      `/api/projects/${projectId}/editing-sessions/${sessionId}/segments/${segmentId}/tts-replacement`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      },
    ),
  clearEditingSessionTtsReplacement: (
    projectId: string,
    sessionId: string,
    segmentId: string,
    expectedRevision: number,
  ) =>
    request<EditingSession>(
      `/api/projects/${projectId}/editing-sessions/${sessionId}/segments/${segmentId}/tts-replacement?expected_revision=${expectedRevision}`,
      {
        method: "DELETE",
      },
    ),
  previewPartialRegeneration: (
    projectId: string,
    sessionId: string,
    payload: Omit<PartialRegenerationRequest, "expected_revision">,
  ) =>
    request<PartialRegenerationPreflight>(
      `/api/projects/${projectId}/editing-sessions/${sessionId}/partial-regeneration/preflight`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      },
    ),
  runPartialRegeneration: (
    projectId: string,
    sessionId: string,
    payload: PartialRegenerationRequest,
  ) =>
    request<PartialRegenerationRun>(
      `/api/projects/${projectId}/editing-sessions/${sessionId}/partial-regeneration`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      },
    ),
  getPartialRegenerationResult: (projectId: string, jobId: string) =>
    request<PartialRegenerationJob>(`/api/projects/${projectId}/partial-regenerations/${jobId}`),
  getSubtitle: (projectId: string, jobId: string) =>
    request<SubtitleJob>(`/api/projects/${projectId}/subtitles/${jobId}`),
  getPreview: (projectId: string, jobId: string) =>
    request<PreviewJob>(`/api/projects/${projectId}/previews/${jobId}`),
  getExport: (projectId: string, jobId: string) =>
    request<ExportJob>(`/api/projects/${projectId}/exports/${jobId}`),
  registerVoiceSample: (projectId: string, payload: AssetRegistrationRequest) =>
    request<AssetResponse>(`/api/projects/${projectId}/assets/voice-sample`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }),
  uploadVoiceSample: (projectId: string, file: File) => {
    const payload = new FormData();
    payload.append("file", file);
    return request<AssetResponse>(`/api/projects/${projectId}/assets/voice-sample/upload`, {
      method: "POST",
      body: payload,
    });
  },
  listVoiceSamples: async (projectId: string): Promise<AssetResponse[]> => {
    const payload = await request<{ assets: AssetResponse[] }>(
      `/api/projects/${projectId}/assets/voice-sample`,
    );
    return payload.assets;
  },
  generateTtsCandidate: (projectId: string, payload: TtsCandidateRequest) =>
    request<TtsCandidateResponse>(`/api/projects/${projectId}/tts-candidates`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }),
  listTtsCandidates: (projectId: string, segmentId: string) =>
    request<{ candidates: TtsCandidateRecord[] }>(
      `/api/projects/${projectId}/segments/${segmentId}/tts-candidates`,
    ),
  reviewTtsCandidate: (projectId: string, candidateId: string, decision: "approved" | "rejected") =>
    request<TtsCandidateRecord>(
      `/api/projects/${projectId}/tts-candidates/${candidateId}/listening-review`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ decision }),
      },
    ),
  assetContentUrl: (projectId: string, assetId: string) =>
    `/api/projects/${projectId}/assets/${assetId}/content`,
  prepareAssetBrowserPreview: (projectId: string, assetId: string, signal?: AbortSignal) =>
    request<AssetBrowserPreview>(`/api/projects/${encodeURIComponent(projectId)}/assets/${encodeURIComponent(assetId)}/browser-preview`, { method: "POST", credentials: "same-origin", redirect: "error", signal }),
  getAssetBrowserPreview: (projectId: string, assetId: string, signal?: AbortSignal) =>
    request<AssetBrowserPreview>(`/api/projects/${encodeURIComponent(projectId)}/assets/${encodeURIComponent(assetId)}/browser-preview`, { credentials: "same-origin", redirect: "error", signal }),
  assetBrowserPreviewContentUrl: (projectId: string, assetId: string) =>
    `/api/projects/${encodeURIComponent(projectId)}/assets/${encodeURIComponent(assetId)}/browser-preview/content`,
  assetThumbnailUrl: (projectId: string, assetId: string) =>
    `/api/projects/${projectId}/assets/${assetId}/thumbnail`,
  startFinalRender: (projectId: string, payload: OutputJobRequest) =>
    request<{ job_id: string; status: string }>(`/api/projects/${projectId}/jobs/final-render`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }),
  getFinalRender: (projectId: string, jobId: string) =>
    request<FinalRenderJob>(`/api/projects/${projectId}/final-renders/${jobId}`),
  startCapcutDraftExport: (projectId: string, payload: OutputJobRequest) =>
    request<{ job_id: string; status: string }>(
      `/api/projects/${projectId}/jobs/capcut-draft-export`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      },
    ),
  getCapcutDraftExport: (projectId: string, jobId: string) =>
    request<CapCutDraftExportJob>(`/api/projects/${projectId}/capcut-draft-exports/${jobId}`),
  registerCapcutDraftHandoff: (projectId: string, jobId: string) =>
    registerCapcutDraftHandoffRequest(`/api/projects/${projectId}/capcut-draft-exports/${jobId}/handoff`),
  getCapcutHandoffDiagnostics: () => request<CapCutHandoffDiagnostics>("/api/capcut/handoff-diagnostics"),
  retryJob: (projectId: string, jobId: string) =>
    request<{ job_id: string; status: string }>(`/api/projects/${projectId}/jobs/${jobId}/retry`, {
      method: "POST",
    }),
};
