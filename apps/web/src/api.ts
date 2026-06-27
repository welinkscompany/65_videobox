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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    throw new Error(`Request failed: ${path} (${response.status})`);
  }
  return (await response.json()) as T;
}

export const api = {
  listProjects: async (): Promise<Project[]> => {
    const payload = await request<{ projects: Project[] }>("/api/projects");
    return payload.projects;
  },
  getProject: (projectId: string) => request<Project>(`/api/projects/${projectId}`),
  listJobs: async (projectId: string): Promise<JobRecord[]> => {
    const payload = await request<{ jobs: JobRecord[] }>(`/api/projects/${projectId}/jobs`);
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
  getSubtitle: (projectId: string, jobId: string) =>
    request<SubtitleJob>(`/api/projects/${projectId}/subtitles/${jobId}`),
  getPreview: (projectId: string, jobId: string) =>
    request<PreviewJob>(`/api/projects/${projectId}/previews/${jobId}`),
  getExport: (projectId: string, jobId: string) =>
    request<ExportJob>(`/api/projects/${projectId}/exports/${jobId}`),
};
