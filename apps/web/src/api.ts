export type Project = {
  project_id: string;
  name: string;
  status: string;
  root_storage_uri: string;
};

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
};

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

export type CaptionStyleMutationRequest = {
  expected_revision: number;
  scope: CaptionStyleScope;
  segment_ids: string[];
  style: CaptionStyleSnapshot;
};

export type CaptionStyleScopePreflight = {
  affected_segment_ids: string[];
};

export type EditingSessionHistoryEntry = {
  mutation_type: string;
  segment_id: string;
  caption_text?: string | null;
  cut_action?: string | null;
  asset_id?: string | null;
  overlay_type?: string | null;
  recommendation_id?: string | null;
};

export type EditingSession = {
  session_id: string;
  project_id: string;
  timeline_id: string;
  session_revision: number;
  caption_style?: CaptionStyleSnapshot | null;
  segments: EditingSessionSegment[];
  history: EditingSessionHistoryEntry[];
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

type RevisionedEditingSessionMutation = {
  expected_revision: number;
};

export type CaptionOverrideRequest = RevisionedEditingSessionMutation & {
  caption_text: string;
};

export type CutActionOverrideRequest = RevisionedEditingSessionMutation & {
  cut_action: string;
};

export type BrollOverrideRequest = RevisionedEditingSessionMutation & {
  asset_id: string;
};

export type MusicOverrideRequest = RevisionedEditingSessionMutation & {
  asset_id: string;
};

export type ExplanationCardRequest = RevisionedEditingSessionMutation & {
  title: string;
  body: string;
  text: string;
};

export type ImageOverlayRequest = RevisionedEditingSessionMutation & {
  asset_id: string;
  text: string;
};

export type TableOverlayRequest = RevisionedEditingSessionMutation & {
  columns: string[];
  rows: string[][];
  text: string;
};

export type TtsReplacementRequest = RevisionedEditingSessionMutation & {
  recommendation_id: string;
  asset_id: string;
};

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
};

export type GeminiProviderKey = {
  key_id: string;
  project_id: string;
  label: string;
  masked_api_key: string;
  primary_model: string;
  cheap_model: string;
  high_quality_model: string;
  status: string;
  cooldown_until: string | null;
  consecutive_failures: number;
  last_error: string | null;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
};

export type GeminiProviderKeyCreateRequest = {
  label: string;
  api_key: string;
  primary_model: string;
  cheap_model: string;
  high_quality_model: string;
};

export type GeminiProviderKeyUpdateRequest = {
  label?: string;
  primary_model?: string;
  cheap_model?: string;
  high_quality_model?: string;
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
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

export const api = {
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
  listProjects: async (): Promise<Project[]> => {
    const payload = await request<{ projects: Project[] }>("/api/projects");
    return payload.projects;
  },
  getProject: (projectId: string) => request<Project>(`/api/projects/${projectId}`),
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
  listBrollAssets: async (projectId: string): Promise<BrollAsset[]> => {
    const payload = await request<{ assets: BrollAsset[] }>(
      `/api/projects/${projectId}/assets/broll-video`,
    );
    return payload.assets;
  },
  importBrollBatch: async (
    projectId: string,
    payload: BrollBatchImportRequest,
  ): Promise<BrollAsset[]> => {
    const response = await request<{ assets: BrollAsset[] }>(
      `/api/projects/${projectId}/assets/broll-video/batch`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      },
    );
    return response.assets;
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
  renderPreview: (projectId: string, payload: OutputJobRequest) =>
    request<{ job_id: string; status: string }>(`/api/projects/${projectId}/jobs/preview-render`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }),
  exportCapcut: (projectId: string, payload: OutputJobRequest) =>
    request<{ job_id: string; status: string }>(`/api/projects/${projectId}/jobs/capcut-export`, {
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
  listGeminiProviderKeys: async (projectId: string): Promise<GeminiProviderKey[]> => {
    const payload = await request<{ keys: GeminiProviderKey[] }>(
      `/api/projects/${projectId}/providers/gemini/keys`,
    );
    return payload.keys;
  },
  createGeminiProviderKey: (
    projectId: string,
    payload: GeminiProviderKeyCreateRequest,
  ) =>
    request<GeminiProviderKey>(`/api/projects/${projectId}/providers/gemini/keys`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }),
  updateGeminiProviderKey: (
    projectId: string,
    keyId: string,
    payload: GeminiProviderKeyUpdateRequest,
  ) =>
    request<GeminiProviderKey>(`/api/projects/${projectId}/providers/gemini/keys/${keyId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }),
  disableGeminiProviderKey: (projectId: string, keyId: string) =>
    request<GeminiProviderKey>(
      `/api/projects/${projectId}/providers/gemini/keys/${keyId}/disable`,
      {
        method: "POST",
      },
    ),
  enableGeminiProviderKey: (projectId: string, keyId: string) =>
    request<GeminiProviderKey>(
      `/api/projects/${projectId}/providers/gemini/keys/${keyId}/enable`,
      {
        method: "POST",
      },
    ),
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
  retryJob: (projectId: string, jobId: string) =>
    request<{ job_id: string; status: string }>(`/api/projects/${projectId}/jobs/${jobId}/retry`, {
      method: "POST",
    }),
};
