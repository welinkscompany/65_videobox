import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { App } from "./App";
import type {
  BrollAsset,
  EditingSession,
  JobRecord,
  PartialRegenerationPreflight,
  RecommendationItem,
  ReviewSnapshot,
  TimelineJob,
  TimelinePayload,
  TtsCandidateRecord,
} from "./api";

type JobFixture = Omit<JobRecord, "project_id">;

const projectsResponse = {
  projects: [
    {
      project_id: "project_001",
      name: "Operator Review Demo",
      status: "active",
      root_storage_uri: "local://projects/project_001",
    },
  ],
};

const projectResponse = {
  project_id: "project_001",
  name: "Operator Review Demo",
  status: "active",
  root_storage_uri: "local://projects/project_001",
};

const capcutDiagnosticsReadyResponse = {
  status: "ready",
  installation_path: "C:/Users/operator/AppData/Local/CapCut/Apps/8.9.1.3802/CapCut.exe",
  detected_version: "8.9.1.3802",
  is_supported: true,
  project_root_path: "C:/Users/operator/AppData/Local/CapCut/User Data/Projects/com.lveditor.draft",
  project_root_exists: true,
  write_access: true,
  recovery_message: null,
  checked_at: "2026-07-13T00:00:00Z",
};

const jobsResponse: { jobs: JobFixture[] } = {
  jobs: [
    {
      job_id: "transcription_job_001",
      job_type: "transcription",
      status: "succeeded",
      input_ref: "asset_001",
      output_ref: "transcript_001",
      error_message: null,
      started_at: "2026-06-28T00:00:00Z",
      finished_at: "2026-06-28T00:00:01Z",
    },
    {
      job_id: "segment_analysis_job_002",
      job_type: "segment_analysis",
      status: "succeeded",
      input_ref: "transcription_job_001",
      output_ref: "segment_analysis_001",
      error_message: null,
      started_at: "2026-06-28T00:00:02Z",
      finished_at: "2026-06-28T00:00:03Z",
    },
    {
      job_id: "broll_recommendation_job_003",
      job_type: "broll_recommendation",
      status: "succeeded",
      input_ref: "segment_analysis_job_002",
      output_ref: "broll_001",
      error_message: null,
      started_at: "2026-06-28T00:00:04Z",
      finished_at: "2026-06-28T00:00:05Z",
    },
    {
      job_id: "music_recommendation_job_004",
      job_type: "music_recommendation",
      status: "succeeded",
      input_ref: "segment_analysis_job_002",
      output_ref: "bgm_001",
      error_message: null,
      started_at: "2026-06-28T00:00:06Z",
      finished_at: "2026-06-28T00:00:07Z",
    },
    {
      job_id: "timeline_build_job_005",
      job_type: "timeline_build",
      status: "succeeded",
      input_ref: "segment_analysis_job_002",
      output_ref: "timeline_001",
      error_message: null,
      started_at: "2026-06-28T00:00:08Z",
      finished_at: "2026-06-28T00:00:09Z",
    },
    {
      job_id: "preview_render_job_006",
      job_type: "preview_render",
      status: "succeeded",
      input_ref: "timeline_build_job_005",
      output_ref: "preview_001",
      error_message: null,
      started_at: "2026-06-28T00:00:10Z",
      finished_at: "2026-06-28T00:00:11Z",
    },
    {
      job_id: "capcut_export_job_007",
      job_type: "capcut_export",
      status: "succeeded",
      input_ref: "timeline_build_job_005",
      output_ref: "export_001",
      error_message: null,
      started_at: "2026-06-28T00:00:12Z",
      finished_at: "2026-06-28T00:00:13Z",
    },
    {
      job_id: "subtitle_render_job_008",
      job_type: "subtitle_render",
      status: "succeeded",
      input_ref: "timeline_build_job_005",
      output_ref: "subtitle_001",
      error_message: null,
      started_at: "2026-06-28T00:00:11Z",
      finished_at: "2026-06-28T00:00:12Z",
    },
  ],
};

const timelineResponse = {
  job_id: "timeline_build_job_005",
  status: "succeeded",
  timeline: {
    timeline_id: "timeline_001",
    project_id: "project_001",
    version: "v001",
    output_mode: "review",
    review_status: "approved",
    created_at: "2026-06-28T00:00:09Z",
    tracks: [
      {
        track_id: "narration_primary",
        track_type: "narration",
        clips: [
          {
            clip_id: "clip_narration_001",
            segment_id: "seg_001",
            asset_uri: "local://projects/project_001/segments/seg_001",
            start_sec: 0,
            end_sec: 3.5,
            clip_type: "narration",
            recommendation_id: null,
          },
        ],
      },
      {
        track_id: "broll_overlay",
        track_type: "broll",
        clips: [
          {
            clip_id: "clip_broll_001",
            segment_id: "seg_001",
            asset_uri: "local://projects/project_001/assets/asset_broll_001",
            start_sec: 0,
            end_sec: 3.5,
            clip_type: "broll",
            recommendation_id: "rec_001",
          },
        ],
      },
      {
        track_id: "music_bed",
        track_type: "bgm",
        clips: [
          {
            clip_id: "clip_bgm_001",
            segment_id: "seg_001",
            asset_uri: "local://projects/project_001/music/suggested",
            start_sec: 0,
            end_sec: 3.5,
            clip_type: "bgm",
            recommendation_id: "rec_010",
          },
        ],
      },
    ],
    review_flags: [
    ],
    applied_recommendations: [
      {
        recommendation_id: "rec_001",
        target_segment_id: "seg_001",
        recommendation_type: "broll",
        selected_asset_id: "asset_broll_001",
        score: 0.96,
        reason: "Matched office overview keywords",
        auto_apply_allowed: true,
        review_required: false,
        payload: { tags: ["office", "overview"] },
        created_at: "2026-06-28T00:00:05Z",
      },
    ],
    pending_recommendations: [
    ],
  },
};

const reviewSnapshotResponse: ReviewSnapshot = {
  project_id: "project_001",
  timeline_id: "timeline_001",
  review_status: "approved",
  segments: [
    {
      segment_id: "seg_001",
      text: "Office overview",
      start_sec: 0,
      end_sec: 3.5,
      confidence: 0.98,
      review_required: false,
      cleanup_decision: "keep",
    },
    {
      segment_id: "seg_002",
      text: "Team meeting overview",
      start_sec: 3.5,
      end_sec: 7.8,
      confidence: 0.96,
      review_required: false,
      cleanup_decision: "keep",
    },
  ],
  applied_recommendations: timelineResponse.timeline.applied_recommendations,
  pending_recommendations: timelineResponse.timeline.pending_recommendations,
  review_flags: timelineResponse.timeline.review_flags,
};

const previewResponse = {
  job_id: "preview_render_job_006",
  status: "succeeded",
  preview: {
    preview_id: "preview_001",
    timeline_id: "timeline_001",
    file_uri: "local://projects/project_001/previews/preview_001.html",
    artifact_kind: "playable_html_preview",
    created_at: "2026-06-28T00:00:11Z",
    notes: ["Playable local HTML preview generated for operator review."],
  },
};

const exportResponse = {
  job_id: "capcut_export_job_007",
  status: "succeeded",
  export: {
    export_id: "export_001",
    timeline_id: "timeline_001",
    export_type: "capcut",
    file_uri: "local://projects/project_001/exports/capcut/export_001/capcut_payload.json",
    subtitle_file_uri: "local://projects/project_001/subtitles/subtitle_001.srt",
    created_at: "2026-06-28T00:00:13Z",
    notes: ["Mock CapCut payload written for local post-editing handoff."],
  },
};

const subtitleResponse = {
  job_id: "subtitle_render_job_008",
  status: "succeeded",
  subtitle: {
    subtitle_id: "subtitle_001",
    timeline_id: "timeline_001",
    format: "srt",
    file_uri: "local://projects/project_001/subtitles/subtitle_001.srt",
    created_at: "2026-06-28T00:00:12Z",
    notes: ["Subtitle file generated from approved review timeline."],
  },
};

const editingSessionResponse = {
  project_id: "project_001",
  timeline_id: "timeline_001",
  session_id: "editing_session_001",
  session_revision: 1,
  created_at: "2026-06-28T00:00:14Z",
  updated_at: "2026-06-28T00:00:17Z",
  segments: [
    {
      segment_id: "seg_001",
      caption_text: "Office overview",
      start_sec: 0,
      end_sec: 3.5,
      cut_action: "keep",
      review_required: false,
      broll_override: null,
      visual_overlays: [],
      music_override: null,
      tts_replacement: null,
    },
    {
      segment_id: "seg_002",
      caption_text: "Team meeting overview",
      start_sec: 3.5,
      end_sec: 7.8,
      cut_action: "keep",
      review_required: false,
      broll_override: { asset_id: "asset_manual_002" },
      visual_overlays: [
        {
          overlay_type: "explanation_card",
          title: "Meeting context",
          body: "Summarize the active discussion.",
          text: "Meeting context: Summarize the active discussion.",
        },
      ],
      music_override: null,
      tts_replacement: null,
    },
  ],
  history: [
    {
      mutation_type: "broll_override_update",
      segment_id: "seg_002",
      asset_id: "asset_manual_002",
    },
  ],
};

const partialRegenerationPreflightResponse: PartialRegenerationPreflight = {
  session_id: "editing_session_001",
  segment_ids: ["seg_002"],
  fields: ["broll", "explanation_card"],
  downstream_steps: ["broll_refresh", "overlay_refresh", "timeline_build"],
  targeted_segments: [editingSessionResponse.segments[1]],
  affected_output_areas: [
    "b-roll track",
    "visual overlays",
    "timeline preview",
    "subtitle render",
    "capcut export",
  ],
  predicted_review_status_after_rerun: "draft",
  prediction_reasons: [],
};

const blockedPartialRegenerationPreflightResponse: PartialRegenerationPreflight = {
  ...partialRegenerationPreflightResponse,
  fields: ["caption"],
  downstream_steps: ["segment_refresh", "timeline_build"],
  targeted_segments: [
    {
      ...editingSessionResponse.segments[1],
      review_required: true,
    },
  ],
  affected_output_areas: [
    "segment copy",
    "timeline preview",
    "subtitle render",
    "capcut export",
  ],
  predicted_review_status_after_rerun: "blocked",
  prediction_reasons: [
    "source timeline already has unresolved review blockers that rerun will preserve",
    "selected segments already require operator review, so rerun output stays blocked",
  ],
};

const partialRegenerationResponse = {
  job_id: "partial_regeneration_job_001",
  status: "succeeded",
  session_id: "editing_session_001",
  segment_ids: ["seg_002"],
  fields: ["broll", "explanation_card"],
  downstream_steps: ["broll_refresh", "overlay_refresh", "timeline_build"],
  delta: {
    regenerated_segments: [
      {
        segment_id: "seg_002",
        changed_fields: ["broll", "explanation_card"],
        output_changes: [
          "b-roll asset replaced with regenerated recommendation",
          "explanation card text refreshed",
        ],
      },
    ],
    timeline_id: "timeline_002",
  },
};

const partialRegenerationResultResponse = {
  job_id: "partial_regeneration_job_001",
  status: "succeeded",
  partial_regeneration_id: "partial_regeneration_run_001",
  session_id: "editing_session_001",
  session_updated_at: "2026-06-28T00:00:17Z",
  source_timeline_id: "timeline_001",
  timeline_id: "timeline_002",
  segment_ids: ["seg_002"],
  fields: ["broll", "explanation_card"],
  downstream_steps: ["broll_refresh", "overlay_refresh", "timeline_build"],
  regenerated_segments: [
    {
      segment_id: "seg_002",
      changed_fields: ["broll", "explanation_card"],
      output_changes: [
        "b-roll asset replaced with regenerated recommendation",
        "explanation card text refreshed",
      ],
    },
  ],
  timeline: {
    timeline_id: "timeline_002",
    project_id: "project_001",
    version: "v002",
    output_mode: "review",
    review_status: "draft",
    tracks: [
      {
        track_id: "narration_primary",
        track_type: "narration",
        clips: [
          {
            clip_id: "clip_narration_001",
            segment_id: "seg_001",
            asset_uri: "local://projects/project_001/segments/seg_001",
            start_sec: 0,
            end_sec: 3.5,
            clip_type: "narration",
            recommendation_id: null,
          },
          {
            clip_id: "clip_narration_002",
            segment_id: "seg_002",
            asset_uri: "local://projects/project_001/segments/seg_002",
            start_sec: 3.5,
            end_sec: 7.8,
            clip_type: "narration",
            recommendation_id: null,
          },
        ],
      },
      {
        track_id: "broll_overlay",
        track_type: "broll",
        clips: [
          {
            clip_id: "clip_broll_002",
            segment_id: "seg_002",
            asset_uri: "local://projects/project_001/assets/asset_broll_regenerated_002",
            start_sec: 3.5,
            end_sec: 7.8,
            clip_type: "broll",
            recommendation_id: "rec_broll_regenerated_002",
          },
        ],
      },
      {
        track_id: "overlay_track",
        track_type: "overlay",
        clips: [
          {
            clip_id: "clip_overlay_002",
            segment_id: "seg_002",
            asset_uri: "inline://overlay/explanation_card/seg_002",
            start_sec: 3.5,
            end_sec: 7.8,
            clip_type: "overlay",
            recommendation_id: "rec_overlay_regenerated_002",
          },
        ],
      },
    ],
    review_flags: [],
    applied_recommendations: [],
    pending_recommendations: [],
  },
};

const reviewRequiredEditingSessionResponse = {
  ...editingSessionResponse,
  segments: editingSessionResponse.segments.map((segment) =>
    segment.segment_id === "seg_002"
      ? {
          ...segment,
          review_required: true,
        }
      : segment,
  ),
};

const reviewRequiredSnapshotResponse: ReviewSnapshot = {
  ...reviewSnapshotResponse,
  review_status: "blocked",
  pending_recommendations: [
    {
      recommendation_id: "rec_tts_review_002",
      target_segment_id: "seg_002",
      recommendation_type: "tts_replacement",
      selected_asset_id: null,
      score: 0.61,
      reason: "Narration replacement still requires operator confirmation.",
      auto_apply_allowed: false,
      review_required: true,
      payload: { provider: "gemini_fallback" },
      created_at: "2026-06-28T00:00:15Z",
    },
  ],
  review_flags: [
    {
      code: "segment_review_required",
      segment_id: "seg_002",
      message: "Changed narration still needs operator review before approval.",
    },
  ],
};

const candidateReviewSnapshotResponse: ReviewSnapshot = {
  ...reviewSnapshotResponse,
  timeline_id: "timeline_002",
  review_status: "draft",
  applied_recommendations: [],
  pending_recommendations: [],
  review_flags: [],
};

const candidateApprovedReviewSnapshotResponse: ReviewSnapshot = {
  ...candidateReviewSnapshotResponse,
  review_status: "approved",
};

const blockedReviewSnapshotResponse: ReviewSnapshot = {
  ...reviewSnapshotResponse,
  review_status: "blocked",
  segments: reviewSnapshotResponse.segments.map((segment) =>
    segment.segment_id === "seg_002"
      ? {
          ...segment,
          text: "Team meeting restart",
          confidence: 0.78,
          review_required: true,
          cleanup_decision: "review",
        }
      : segment,
  ),
  pending_recommendations: [
    {
      recommendation_id: "rec_011",
      target_segment_id: "seg_002",
      recommendation_type: "tts_replacement",
      selected_asset_id: null,
      score: 0.74,
      reason: "Pronunciation restart detected",
      auto_apply_allowed: false,
      review_required: true,
      payload: { provider: "voicebox" },
      created_at: "2026-06-28T00:00:06Z",
    },
  ],
  review_flags: [
    {
      code: "segment_review_required",
      segment_id: "seg_002",
      message: "Segment requires operator review before export.",
    },
  ],
};

const geminiKeysResponse = {
  keys: [
    {
      key_id: "gemini_key_001",
      project_id: "project_001",
      label: "Primary routing key",
      masked_api_key: "AIza...1234",
      primary_model: "gemini-2.5-pro",
      cheap_model: "gemini-2.5-flash-lite",
      high_quality_model: "gemini-2.5-pro",
      status: "active",
      cooldown_until: null,
      consecutive_failures: 0,
      last_error: null,
      last_used_at: "2026-06-28T00:00:20Z",
      created_at: "2026-06-28T00:00:15Z",
      updated_at: "2026-06-28T00:00:20Z",
    },
    {
      key_id: "gemini_key_002",
      project_id: "project_001",
      label: "Fallback cooldown key",
      masked_api_key: "AIza...5678",
      primary_model: "gemini-2.5-flash",
      cheap_model: "gemini-2.5-flash-lite",
      high_quality_model: "gemini-2.5-pro",
      status: "cooldown",
      cooldown_until: "2026-06-28T00:05:00Z",
      consecutive_failures: 3,
      last_error: "429 quota exceeded",
      last_used_at: "2026-06-28T00:00:18Z",
      created_at: "2026-06-28T00:00:16Z",
      updated_at: "2026-06-28T00:00:21Z",
    },
  ],
};

const brollAssetsResponse = {
  assets: [
    {
      asset_id: "asset_broll_archive_001",
      asset_type: "broll_video",
      storage_uri: "local://projects/project_001/assets/imported/office-lobby-pan.mp4",
      metadata: {
        title: "Office lobby pan",
        tags: ["office", "lobby"],
      },
      created_at: "2026-07-06T00:00:00Z",
    },
    {
      asset_id: "asset_broll_archive_002",
      asset_type: "broll_video",
      storage_uri: "local://projects/project_001/assets/imported/team-whiteboard.mp4",
      metadata: {
        title: "Team whiteboard",
        tags: ["team", "planning"],
      },
      created_at: "2026-07-06T00:00:01Z",
    },
  ],
};

function createFetchMock({
  geminiKeys = geminiKeysResponse,
  brollAssets = brollAssetsResponse,
  brollBatchImportStatus,
  timeline = timelineResponse,
  editingSession = editingSessionResponse,
  latestEditingSession = editingSessionResponse,
  latestEditingSessionStatus,
  candidateResultStatus,
  candidateReviewStatus,
  candidatePreflightStatus,
  editingMutationStatus,
  editingMutationConflictSession,
  reviewSnapshot = reviewSnapshotResponse,
  candidateReviewSnapshot = candidateReviewSnapshotResponse,
  partialRegenerationResult = partialRegenerationResultResponse,
  partialRegenerationPreflight = partialRegenerationPreflightResponse,
  jobs = jobsResponse,
  finalRenderResult,
  capcutDraftResult,
  capcutDraftResults,
  capcutHandoffResult,
  capcutDiagnostics = capcutDiagnosticsReadyResponse,
  capcutDiagnosticsResponses,
  ttsCandidates = [],
  ttsListeningReviewStatuses,
  voiceSampleUploadStatus,
  voiceSamples = { assets: [] },
  mediaLibraryAssets = [],
  mediaLibraryUnavailable = false,
}: {
  geminiKeys?: { keys: Array<Record<string, unknown>> };
  brollAssets?: { assets: BrollAsset[] };
  brollBatchImportStatus?: number;
  timeline?: TimelineJob;
  editingSession?: EditingSession;
  latestEditingSession?: EditingSession | null;
  latestEditingSessionStatus?: number;
  candidateResultStatus?: number;
  candidateReviewStatus?: number;
  candidatePreflightStatus?: number;
  editingMutationStatus?: number;
  editingMutationConflictSession?: EditingSession;
  reviewSnapshot?: ReviewSnapshot;
  candidateReviewSnapshot?: ReviewSnapshot;
  partialRegenerationResult?: typeof partialRegenerationResultResponse;
  partialRegenerationPreflight?: typeof partialRegenerationPreflightResponse;
  jobs?: typeof jobsResponse;
  finalRenderResult?: Record<string, unknown>;
  capcutDraftResult?: Record<string, unknown>;
  capcutDraftResults?: Record<string, Record<string, unknown>>;
  capcutHandoffResult?: Record<string, unknown>;
  capcutDiagnostics?: Record<string, unknown>;
  capcutDiagnosticsResponses?: Array<Record<string, unknown>>;
  ttsCandidates?: TtsCandidateRecord[];
  ttsListeningReviewStatuses?: number[];
  voiceSampleUploadStatus?: number;
  voiceSamples?: { assets: Array<Record<string, unknown>> };
  mediaLibraryAssets?: Array<Record<string, unknown>>;
  mediaLibraryUnavailable?: boolean;
} = {}) {
  const state: {
    timeline: TimelinePayload;
    editingSession: EditingSession;
    geminiKeys: { keys: Array<Record<string, unknown>> };
    brollAssets: { assets: BrollAsset[] };
    voiceSamples: { assets: Array<Record<string, unknown>> };
    reviewSnapshot: ReviewSnapshot;
    candidateReviewSnapshot: ReviewSnapshot;
    candidateTimelineReviewStatus: string;
    ttsCandidates: TtsCandidateRecord[];
    mediaLibraryAssets: Array<Record<string, unknown>>;
    mediaLibraryFavorites: string[];
    mediaLibraryRecent: string[];
    mediaLibraryFavoritesByProject: Record<string, string[]>;
    mediaLibraryRecentByProject: Record<string, string[]>;
  } = {
    timeline: structuredClone(timeline.timeline),
    editingSession: structuredClone(editingSession) as EditingSession,
    geminiKeys: structuredClone(geminiKeys),
    brollAssets: structuredClone(brollAssets),
    voiceSamples: structuredClone(voiceSamples),
    reviewSnapshot: structuredClone(reviewSnapshot),
    candidateReviewSnapshot: structuredClone(candidateReviewSnapshot),
    candidateTimelineReviewStatus: partialRegenerationResult.timeline.review_status,
    ttsCandidates: structuredClone(ttsCandidates),
    mediaLibraryAssets: structuredClone(mediaLibraryAssets),
    mediaLibraryFavorites: [],
    mediaLibraryRecent: [],
    mediaLibraryFavoritesByProject: {},
    mediaLibraryRecentByProject: {},
  };

  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/api/capcut/handoff-diagnostics")) {
      return new Response(JSON.stringify(capcutDiagnosticsResponses?.shift() ?? capcutDiagnostics));
    }
    if (mediaLibraryUnavailable && url.startsWith("/api/media-library/")) {
      return new Response("media library unavailable", { status: 503 });
    }
    if (url.endsWith("/api/media-library/assets")) {
      return new Response(JSON.stringify({ assets: state.mediaLibraryAssets }));
    }
    if (url.endsWith("/api/media-library/install-state")) {
      return new Response(JSON.stringify({ status: state.mediaLibraryAssets.length ? "installed" : "not_installed", installed_asset_count: state.mediaLibraryAssets.length }));
    }
    const projectLibraryMatch = url.match(/\/api\/projects\/([^/]+)\/media-library\/(favorites|recent)$/);
    if (projectLibraryMatch) {
      const [, projectId, kind] = projectLibraryMatch;
      const values = kind === "favorites" ? state.mediaLibraryFavoritesByProject[projectId] ?? [] : state.mediaLibraryRecentByProject[projectId] ?? [];
      return new Response(JSON.stringify({ asset_ids: values }));
    }
    const projectFavoriteMatch = url.match(/\/api\/projects\/([^/]+)\/media-library\/assets\/(.+)\/favorite$/);
    if (projectFavoriteMatch && init?.method === "PUT") {
      const [, projectId, encodedAssetId] = projectFavoriteMatch;
      const assetId = decodeURIComponent(encodedAssetId);
      const current = state.mediaLibraryFavoritesByProject[projectId] ?? [];
      const enabled = Boolean(JSON.parse(String(init.body ?? "{}")).enabled);
      state.mediaLibraryFavoritesByProject[projectId] = enabled ? [...new Set([...current, assetId])] : current.filter((item) => item !== assetId);
      return new Response(JSON.stringify({ asset_ids: state.mediaLibraryFavoritesByProject[projectId] }));
    }
    if (url.endsWith("/api/media-library/favorites")) {
      return new Response(JSON.stringify({ asset_ids: state.mediaLibraryFavorites }));
    }
    if (url.endsWith("/api/media-library/recent")) {
      return new Response(JSON.stringify({ asset_ids: state.mediaLibraryRecent }));
    }
    if (/\/api\/media-library\/assets\/.+\/favorite$/.test(url) && init?.method === "PUT") {
      const assetId = decodeURIComponent(url.split("/").slice(-2)[0] ?? "");
      state.mediaLibraryFavorites = state.mediaLibraryFavorites.includes(assetId)
        ? state.mediaLibraryFavorites.filter((item) => item !== assetId)
        : [assetId, ...state.mediaLibraryFavorites];
      return new Response(JSON.stringify({ asset_ids: state.mediaLibraryFavorites }));
    }
    if (/\/api\/media-library\/assets\/.+\/materialize$/.test(url) && init?.method === "POST") {
      const assetId = decodeURIComponent(url.split("/").slice(-2)[0] ?? "");
      state.mediaLibraryRecent = [assetId];
      const projectId = String(JSON.parse(String(init.body ?? "{}")).project_id ?? "");
      if (projectId) state.mediaLibraryRecentByProject[projectId] = [assetId];
      return new Response(JSON.stringify({ asset_id: "asset_materialized_music_001", asset_type: "bgm", storage_uri: "local://projects/project_001/assets/imported/music-001.mp3" }), { status: 201 });
    }
    if (url.endsWith("/api/projects")) {
      return new Response(JSON.stringify(projectsResponse));
    }
    if (url.endsWith("/api/projects/project_001")) {
      return new Response(JSON.stringify(projectResponse));
    }
    if (url.endsWith("/api/projects/project_001/jobs")) {
      return new Response(JSON.stringify(jobs));
    }
    if (
      url.endsWith("/api/projects/project_001/assets/broll-video/batch") &&
      init?.method === "POST"
    ) {
      if (brollBatchImportStatus != null && brollBatchImportStatus >= 400) {
        return new Response("B-roll import failed", { status: brollBatchImportStatus });
      }
      const importedAssets = [
        {
          asset_id: "asset_broll_archive_003",
          asset_type: "broll_video",
          storage_uri: "local://projects/project_001/assets/imported/factory-line.mp4",
          metadata: {
            title: "factory-line",
            tags: ["folder-import"],
          },
          created_at: "2026-07-06T00:00:02Z",
        },
      ];
      state.brollAssets = {
        assets: [...state.brollAssets.assets, ...importedAssets],
      };
      return new Response(JSON.stringify({ assets: importedAssets }), { status: 201 });
    }
    if (url.endsWith("/api/projects/project_001/assets/broll-video")) {
      return new Response(JSON.stringify(state.brollAssets));
    }
    if (url.endsWith("/api/projects/project_001/assets/voice-sample") && !init?.method) {
      return new Response(JSON.stringify(state.voiceSamples));
    }
    if (
      url.endsWith("/api/projects/project_001/assets/voice-sample/upload") &&
      init?.method === "POST"
    ) {
      if (voiceSampleUploadStatus != null && voiceSampleUploadStatus >= 400) {
        return new Response("voice upload failed", { status: voiceSampleUploadStatus });
      }
      const uploadedAsset = {
        asset_id: "asset_voice_uploaded_001",
        asset_type: "voice_sample_audio",
        storage_uri: "local://projects/project_001/assets/imported/my-voice.wav",
      };
      state.voiceSamples = { assets: [uploadedAsset, ...state.voiceSamples.assets] };
      return new Response(JSON.stringify(uploadedAsset), { status: 201 });
    }
    const listeningReviewMatch = url.match(
      /\/api\/projects\/project_001\/tts-candidates\/([^/]+)\/listening-review$/,
    );
    if (listeningReviewMatch && init?.method === "PATCH") {
      const status = ttsListeningReviewStatuses?.shift() ?? 200;
      if (status >= 400) {
        return new Response("listening review failed", { status });
      }
      const decision = JSON.parse(String(init.body ?? "{}")) as { decision?: string };
      const candidate = state.ttsCandidates.find(
        (item) => item.candidate_id === listeningReviewMatch[1],
      );
      if (!candidate) {
        return new Response("candidate not found", { status: 404 });
      }
      candidate.operator_review_status = decision.decision === "rejected" ? "rejected" : "approved";
      return new Response(JSON.stringify(candidate));
    }
    if (/\/api\/projects\/project_001\/segments\/[^/]+\/tts-candidates$/.test(url)) {
      return new Response(JSON.stringify({ candidates: state.ttsCandidates }));
    }
    if (
      url.endsWith("/api/projects/project_001/jobs/build-timeline") &&
      init?.method === "POST"
    ) {
      return new Response(
        JSON.stringify({
          job_id: "timeline_build_job_005",
          status: "succeeded",
        }),
      );
    }
    if (
      url.endsWith("/api/projects/project_001/jobs/preview-render") &&
      init?.method === "POST"
    ) {
      return new Response(
        JSON.stringify({
          job_id: "preview_render_job_006",
          status: "succeeded",
        }),
      );
    }
    if (
      url.endsWith("/api/projects/project_001/jobs/capcut-export") &&
      init?.method === "POST"
    ) {
      return new Response(
        JSON.stringify({
          job_id: "capcut_export_job_007",
          status: "succeeded",
        }),
      );
    }
    if (
      url.endsWith("/api/projects/project_001/jobs/subtitle-render") &&
      init?.method === "POST"
    ) {
      return new Response(
        JSON.stringify({
          job_id: "subtitle_render_job_008",
          status: "succeeded",
        }),
      );
    }
    if (
      url.endsWith("/api/projects/project_001/jobs/final-render") &&
      init?.method === "POST"
    ) {
      return new Response(
        JSON.stringify({
          job_id: String(finalRenderResult?.job_id ?? "final_render_job_009"),
          status: "running",
        }),
        { status: 202 },
      );
    }
    if (url.endsWith("/api/projects/project_001/final-renders/final_render_job_009")) {
      return new Response(
        JSON.stringify(
          finalRenderResult ?? {
            job_id: "final_render_job_009",
            status: "succeeded",
            render: {
              export_id: "final_render_001",
              timeline_id: "timeline_001",
              export_type: "final_render",
              file_uri: "local://projects/project_001/exports/final/output.mp4",
              status: "succeeded",
            },
            error_message: null,
          },
        ),
      );
    }
    if (
      url.endsWith("/api/projects/project_001/jobs/capcut-draft-export") &&
      init?.method === "POST"
    ) {
      return new Response(
        JSON.stringify({
          job_id: String(capcutDraftResult?.job_id ?? "capcut_draft_job_009"),
          status: "running",
        }),
        { status: 202 },
      );
    }
    const capcutDraftMatch = url.match(/\/api\/projects\/project_001\/capcut-draft-exports\/(capcut_draft_job_\d+)$/);
    if (capcutDraftMatch) {
      return new Response(
        JSON.stringify(
          capcutDraftResults?.[capcutDraftMatch[1]] ?? capcutDraftResult ?? {
            job_id: "capcut_draft_job_009",
            status: "succeeded",
            export: {
              export_id: "capcut_draft_001",
              timeline_id: "timeline_001",
              export_type: "capcut_draft",
              file_uri: "local://projects/project_001/exports/capcut-draft/draft",
              status: "succeeded",
              notes: ["ducking is not natively supported by CapCut draft export; apply it in CapCut after import"],
            },
            error_message: null,
          },
        ),
      );
    }
    if (
      url.endsWith("/api/projects/project_001/capcut-draft-exports/capcut_draft_job_009/handoff") &&
      init?.method === "POST"
    ) {
      return new Response(
        JSON.stringify(
          capcutHandoffResult ?? {
            handoff: {
              status: "ready",
              source_file_uri: "local://projects/project_001/exports/capcut-draft/draft",
              registered_project_path: "C:/CapCut/User Data/Projects/com.lveditor.draft/videobox-export_001",
              error_message: null,
              registered_at: "2026-07-12T00:02:30Z",
              reused: false,
            },
          },
        ),
      );
    }
    if (url.endsWith("/api/projects/project_001/timelines/timeline_build_job_005")) {
      return new Response(
        JSON.stringify({
          ...timeline,
          timeline: state.timeline,
        }),
      );
    }
    if (url.endsWith("/api/projects/project_001/timelines/partial_regeneration_job_001")) {
      return new Response(
        JSON.stringify({
          job_id: "partial_regeneration_job_001",
          status: partialRegenerationResult.status,
          timeline: {
            ...partialRegenerationResult.timeline,
            review_status: state.candidateTimelineReviewStatus,
          },
        }),
      );
    }
    if (url.endsWith("/api/projects/project_001/review-snapshots/timeline_build_job_005")) {
      return new Response(JSON.stringify(state.reviewSnapshot));
    }
    if (
      url.includes("/api/projects/project_001/review-snapshots/timeline_build_job_005/recommendations/") &&
      url.endsWith("/approve") &&
      init?.method === "POST"
    ) {
      const recommendationId = url.split("/").slice(-2)[0] ?? "";
      const approved: RecommendationItem | undefined = state.reviewSnapshot.pending_recommendations.find(
        (item) => item.recommendation_id === recommendationId,
      );
      if (!approved) {
        return new Response("recommendation not found", { status: 404 });
      }
      const nextApproved = {
        ...approved,
        auto_apply_allowed: true,
        review_required: false,
      };
      state.reviewSnapshot = {
        ...state.reviewSnapshot,
        review_status: "draft",
        applied_recommendations: [...state.reviewSnapshot.applied_recommendations, nextApproved],
        pending_recommendations: state.reviewSnapshot.pending_recommendations.filter(
          (item) => item.recommendation_id !== recommendationId,
        ),
        review_flags: state.reviewSnapshot.review_flags.filter(
          (flag) =>
            !(
              flag.code === `${approved.recommendation_type}_review_required` &&
              flag.segment_id === approved.target_segment_id
            ),
        ),
      };
      state.timeline = {
        ...state.timeline,
        review_status: "draft",
        applied_recommendations: [...state.timeline.applied_recommendations, nextApproved],
        pending_recommendations: state.timeline.pending_recommendations.filter(
          (item) => item.recommendation_id !== recommendationId,
        ),
        review_flags: state.timeline.review_flags.filter(
          (flag) =>
            !(
              String(flag.code ?? "") === `${approved.recommendation_type}_review_required` &&
              String(flag.segment_id ?? "") === approved.target_segment_id
            ),
        ),
      };
      return new Response(JSON.stringify(state.reviewSnapshot));
    }
    if (url.endsWith("/api/projects/project_001/review-snapshots/partial_regeneration_job_001")) {
      if (candidateReviewStatus != null) {
        return new Response("candidate review error", { status: candidateReviewStatus });
      }
      return new Response(
        JSON.stringify({
          ...state.candidateReviewSnapshot,
          review_status: state.candidateTimelineReviewStatus,
        }),
      );
    }
    if (
      url.endsWith("/api/projects/project_001/review-approvals/timeline_build_job_005/approve") &&
      init?.method === "POST"
    ) {
      return new Response(
        JSON.stringify({
          timeline_id: "timeline_001",
          review_status: "approved",
          approved_at: "2026-06-28T00:00:10Z",
        }),
      );
    }
    if (
      url.endsWith("/api/projects/project_001/review-approvals/timeline_build_job_005/reopen") &&
      init?.method === "POST"
    ) {
      return new Response(
        JSON.stringify({
          timeline_id: "timeline_001",
          review_status: "draft",
          approved_at: null,
        }),
      );
    }
    if (
      url.endsWith("/api/projects/project_001/review-approvals/partial_regeneration_job_001/approve") &&
      init?.method === "POST"
    ) {
      state.candidateTimelineReviewStatus = "approved";
      return new Response(
        JSON.stringify({
          timeline_id: "timeline_002",
          review_status: "approved",
          approved_at: "2026-06-28T00:00:18Z",
        }),
      );
    }
    if (
      url.endsWith("/api/projects/project_001/review-approvals/partial_regeneration_job_001/reopen") &&
      init?.method === "POST"
    ) {
      state.candidateTimelineReviewStatus = "draft";
      return new Response(
        JSON.stringify({
          timeline_id: "timeline_002",
          review_status: "draft",
          approved_at: null,
        }),
      );
    }
    if (url.endsWith("/api/projects/project_001/previews/preview_render_job_006")) {
      return new Response(JSON.stringify(previewResponse));
    }
    if (url.endsWith("/api/projects/project_001/subtitles/subtitle_render_job_008")) {
      return new Response(JSON.stringify(subtitleResponse));
    }
    if (url.endsWith("/api/projects/project_001/exports/capcut_export_job_007")) {
      return new Response(JSON.stringify(exportResponse));
    }
    if (
      url.endsWith("/api/projects/project_001/editing-sessions") &&
      init?.method === "POST"
    ) {
      return new Response(JSON.stringify(state.editingSession), {
        status: 201,
      });
    }
    if (url.endsWith("/api/projects/project_001/editing-sessions/editing_session_001")) {
      return new Response(JSON.stringify(state.editingSession));
    }
    if (url.endsWith("/api/projects/project_001/editing-sessions/latest")) {
      if (latestEditingSessionStatus != null) {
        return new Response("latest session error", { status: latestEditingSessionStatus });
      }
      if (latestEditingSession == null) {
        return new Response("not found", { status: 404 });
      }
      return new Response(JSON.stringify(latestEditingSession));
    }
    if (url.endsWith("/caption-style/preflight") && init?.method === "POST") {
      return new Response(JSON.stringify({ affected_segment_ids: ["seg_002"] }));
    }
    if (url.endsWith("/caption-style") && init?.method === "PATCH") {
      return new Response(JSON.stringify(state.editingSession));
    }
    if (url.endsWith("/api/projects/project_001/editor-library/presets")) {
      return new Response(JSON.stringify([
        { preset_id: "builtin:clean", name: "Clean", scope: "built_in", style: { font_size: 42 } },
      ]));
    }
    if (url.endsWith("/api/projects/project_001/editor-library/favorites")) {
      return new Response(JSON.stringify([]));
    }
    if (/\/api\/projects\/project_001\/editor-library\/favorites\//.test(url) && init?.method === "PUT") {
      return new Response(JSON.stringify({ favorite_id: url.split("/").pop(), favorite_type: "preset", enabled: true }));
    }
    if (url.endsWith("/api/projects/project_001/editor-library/recent-presets")) {
      return new Response(JSON.stringify([]));
    }
    if (
      url.endsWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/caption",
      ) &&
      init?.method === "PATCH"
    ) {
      if (editingMutationConflictSession) {
        return new Response(
          JSON.stringify({ latest_session: editingMutationConflictSession }),
          { status: 409 },
        );
      }
      if (editingMutationStatus != null && editingMutationStatus >= 400) {
        return new Response("caption save failed", { status: editingMutationStatus });
      }
      const payload = JSON.parse(String(init.body)) as { caption_text: string };
      state.editingSession = {
        ...state.editingSession,
        segments: state.editingSession.segments.map((segment) =>
          segment.segment_id === "seg_002"
            ? {
                ...segment,
                caption_text: payload.caption_text,
              }
            : segment,
        ),
      };
      return new Response(JSON.stringify(state.editingSession));
    }
    if (
      url.endsWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/music",
      ) &&
      init?.method === "PATCH"
    ) {
      const payload = JSON.parse(String(init.body)) as {
        asset_id: string;
      };
      state.editingSession = {
        ...state.editingSession,
        segments: state.editingSession.segments.map((segment) =>
          segment.segment_id === "seg_002"
            ? {
                ...segment,
                music_override: {
                  asset_id: payload.asset_id,
                },
              }
            : segment,
        ),
      };
      return new Response(JSON.stringify(state.editingSession));
    }
    if (
      url.startsWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/music",
      ) &&
      init?.method === "DELETE"
    ) {
      state.editingSession = {
        ...state.editingSession,
        segments: state.editingSession.segments.map((segment) =>
          segment.segment_id === "seg_002"
            ? {
                ...segment,
                music_override: null,
              }
            : segment,
        ),
      };
      return new Response(JSON.stringify(state.editingSession));
    }
    if (
      url.endsWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/broll",
      ) &&
      init?.method === "PATCH"
    ) {
      const payload = JSON.parse(String(init.body)) as {
        asset_id: string;
      };
      state.editingSession = {
        ...state.editingSession,
        segments: state.editingSession.segments.map((segment) =>
          segment.segment_id === "seg_002"
            ? {
                ...segment,
                broll_override: {
                  asset_id: payload.asset_id,
                },
              }
            : segment,
        ),
      };
      state.mediaLibraryRecentByProject.project_001 = [payload.asset_id];
      return new Response(JSON.stringify(state.editingSession));
    }
    if (
      url.startsWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/broll",
      ) &&
      init?.method === "DELETE"
    ) {
      state.editingSession = {
        ...state.editingSession,
        segments: state.editingSession.segments.map((segment) =>
          segment.segment_id === "seg_002"
            ? {
                ...segment,
                broll_override: null,
              }
            : segment,
        ),
      };
      return new Response(JSON.stringify(state.editingSession));
    }
    if (
      url.endsWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/explanation-card",
      ) &&
      init?.method === "PATCH"
    ) {
      const payload = JSON.parse(String(init.body)) as {
        title: string;
        body: string;
        text: string;
      };
      state.editingSession = {
        ...state.editingSession,
        segments: state.editingSession.segments.map((segment) =>
          segment.segment_id === "seg_002"
            ? {
                ...segment,
                visual_overlays: [
                  ...segment.visual_overlays.filter(
                    (overlay) => String(overlay.overlay_type ?? "") !== "explanation_card",
                  ),
                  {
                    overlay_type: "explanation_card",
                    title: payload.title,
                    body: payload.body,
                    text: payload.text,
                  },
                ],
              }
            : segment,
        ),
      };
      return new Response(JSON.stringify(state.editingSession));
    }
    if (
      url.startsWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/explanation-card",
      ) &&
      init?.method === "DELETE"
    ) {
      state.editingSession = {
        ...state.editingSession,
        segments: state.editingSession.segments.map((segment) =>
          segment.segment_id === "seg_002"
            ? {
                ...segment,
                visual_overlays: segment.visual_overlays.filter(
                  (overlay) => String(overlay.overlay_type ?? "") !== "explanation_card",
                ),
              }
            : segment,
        ),
      };
      return new Response(JSON.stringify(state.editingSession));
    }
    if (
      url.endsWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/image-overlay",
      ) &&
      init?.method === "PATCH"
    ) {
      const payload = JSON.parse(String(init.body)) as {
        asset_id: string;
        text: string;
      };
      state.editingSession = {
        ...state.editingSession,
        segments: state.editingSession.segments.map((segment) =>
          segment.segment_id === "seg_002"
            ? {
                ...segment,
                visual_overlays: [
                  ...segment.visual_overlays.filter(
                    (overlay) => String(overlay.overlay_type ?? "") !== "image_overlay",
                  ),
                  {
                    overlay_type: "image_overlay",
                    asset_id: payload.asset_id,
                    text: payload.text,
                  },
                ],
              }
            : segment,
        ),
      };
      return new Response(JSON.stringify(state.editingSession));
    }
    if (
      url.startsWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/image-overlay",
      ) &&
      init?.method === "DELETE"
    ) {
      state.editingSession = {
        ...state.editingSession,
        segments: state.editingSession.segments.map((segment) =>
          segment.segment_id === "seg_002"
            ? {
                ...segment,
                visual_overlays: segment.visual_overlays.filter(
                  (overlay) => String(overlay.overlay_type ?? "") !== "image_overlay",
                ),
              }
            : segment,
        ),
      };
      return new Response(JSON.stringify(state.editingSession));
    }
    if (
      url.endsWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/table-overlay",
      ) &&
      init?.method === "PATCH"
    ) {
      const payload = JSON.parse(String(init.body)) as {
        columns: string[];
        rows: string[][];
        text: string;
      };
      state.editingSession = {
        ...state.editingSession,
        segments: state.editingSession.segments.map((segment) =>
          segment.segment_id === "seg_002"
            ? {
                ...segment,
                visual_overlays: [
                  ...segment.visual_overlays.filter(
                    (overlay) => String(overlay.overlay_type ?? "") !== "table_overlay",
                  ),
                  {
                    overlay_type: "table_overlay",
                    columns: payload.columns,
                    rows: payload.rows,
                    text: payload.text,
                  },
                ],
              }
            : segment,
        ),
      };
      return new Response(JSON.stringify(state.editingSession));
    }
    if (
      url.startsWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/table-overlay",
      ) &&
      init?.method === "DELETE"
    ) {
      state.editingSession = {
        ...state.editingSession,
        segments: state.editingSession.segments.map((segment) =>
          segment.segment_id === "seg_002"
            ? {
                ...segment,
                visual_overlays: segment.visual_overlays.filter(
                  (overlay) => String(overlay.overlay_type ?? "") !== "table_overlay",
                ),
              }
            : segment,
        ),
      };
      return new Response(JSON.stringify(state.editingSession));
    }
    if (
      url.endsWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/tts-replacement",
      ) &&
      init?.method === "PATCH"
    ) {
      const payload = JSON.parse(String(init.body)) as {
        recommendation_id: string;
        asset_id: string;
      };
      state.editingSession = {
        ...state.editingSession,
        segments: state.editingSession.segments.map((segment) =>
          segment.segment_id === "seg_002"
            ? {
                ...segment,
                tts_replacement: {
                  recommendation_id: payload.recommendation_id,
                  asset_id: payload.asset_id,
                },
              }
            : segment,
        ),
      };
      return new Response(JSON.stringify(state.editingSession));
    }
    if (
      url.startsWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/tts-replacement",
      ) &&
      init?.method === "DELETE"
    ) {
      state.editingSession = {
        ...state.editingSession,
        segments: state.editingSession.segments.map((segment) =>
          segment.segment_id === "seg_002"
            ? {
                ...segment,
                tts_replacement: null,
              }
            : segment,
        ),
      };
      return new Response(JSON.stringify(state.editingSession));
    }
    if (
      url.endsWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/partial-regeneration/preflight",
      ) &&
      init?.method === "POST"
    ) {
      if (candidatePreflightStatus != null) {
        return new Response("candidate preflight error", { status: candidatePreflightStatus });
      }
      return new Response(JSON.stringify(partialRegenerationPreflight));
    }
    if (
      url.endsWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/partial-regeneration",
      ) &&
      init?.method === "POST"
    ) {
      return new Response(JSON.stringify(partialRegenerationResponse), {
        status: 202,
      });
    }
    if (url.endsWith("/api/projects/project_001/partial-regenerations/partial_regeneration_job_001")) {
      if (candidateResultStatus != null) {
        return new Response("candidate result error", { status: candidateResultStatus });
      }
      return new Response(
        JSON.stringify({
          ...partialRegenerationResult,
          timeline: {
            ...partialRegenerationResult.timeline,
            review_status: state.candidateTimelineReviewStatus,
          },
        }),
      );
    }
    if (url.endsWith("/api/projects/project_001/providers/gemini/keys")) {
      if (init?.method === "POST") {
        const payload = JSON.parse(String(init.body)) as {
          label: string;
          primary_model: string;
          cheap_model: string;
          high_quality_model: string;
        };
        state.geminiKeys.keys = [
          ...state.geminiKeys.keys,
          {
            key_id: "gemini_key_003",
            project_id: "project_001",
            label: payload.label,
            masked_api_key: "AIza...9999",
            primary_model: payload.primary_model,
            cheap_model: payload.cheap_model,
            high_quality_model: payload.high_quality_model,
            status: "active",
            cooldown_until: null,
            consecutive_failures: 0,
            last_error: null,
            last_used_at: null,
            created_at: "2026-06-28T00:00:30Z",
            updated_at: "2026-06-28T00:00:30Z",
          },
        ];
        return new Response(JSON.stringify(state.geminiKeys.keys[state.geminiKeys.keys.length - 1]));
      }
      return new Response(JSON.stringify(state.geminiKeys));
    }
    if (
      url.endsWith("/api/projects/project_001/providers/gemini/keys/gemini_key_001") &&
      init?.method === "PATCH"
    ) {
      const payload = JSON.parse(String(init.body)) as Record<string, string>;
      state.geminiKeys.keys = state.geminiKeys.keys.map((item) =>
        item.key_id === "gemini_key_001"
          ? {
              ...item,
              ...payload,
              updated_at: "2026-06-28T00:01:00Z",
            }
          : item,
      );
      return new Response(
        JSON.stringify(state.geminiKeys.keys.find((item) => item.key_id === "gemini_key_001")),
      );
    }
    if (
      url.endsWith("/api/projects/project_001/providers/gemini/keys/gemini_key_001/disable") &&
      init?.method === "POST"
    ) {
      state.geminiKeys.keys = state.geminiKeys.keys.map((item) =>
        item.key_id === "gemini_key_001"
          ? {
              ...item,
              status: "disabled",
              updated_at: "2026-06-28T00:01:10Z",
            }
          : item,
      );
      return new Response(
        JSON.stringify(state.geminiKeys.keys.find((item) => item.key_id === "gemini_key_001")),
      );
    }
    if (
      url.endsWith("/api/projects/project_001/providers/gemini/keys/gemini_key_001/enable") &&
      init?.method === "POST"
    ) {
      state.geminiKeys.keys = state.geminiKeys.keys.map((item) =>
        item.key_id === "gemini_key_001"
          ? {
              ...item,
              status: "active",
              updated_at: "2026-06-28T00:01:20Z",
            }
          : item,
      );
      return new Response(
        JSON.stringify(state.geminiKeys.keys.find((item) => item.key_id === "gemini_key_001")),
      );
    }
    return Promise.reject(new Error(`Unhandled fetch: ${url}`));
  });
}

it("does not copy a rejected TTS candidate into the editing draft", async () => {
  const fetchMock = createFetchMock({
    ttsCandidates: [
      {
        candidate_id: "tts_candidate_001",
        project_id: "project_001",
        segment_id: "seg_002",
        asset_id: "asset_tts_rejected",
        source_text: "거부된 개인 음성 후보",
        technical_status: "rejected",
        operator_review_status: "pending",
        target_duration_sec: 3,
        actual_duration_sec: 1,
        failure_code: "duration_mismatch",
        created_at: "2026-07-12T00:00:00Z",
      },
    ],
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);

  fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
  fireEvent.click(await screen.findByRole("button", { name: /편집 시작/i }));

  expect(await screen.findByText(/선택 불가 · duration_mismatch/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /이 후보 선택/i })).toBeDisabled();
});

it("requires listening approval before selecting a TTS candidate and restores the approval after reload", async () => {
  const fetchMock = createFetchMock({
    ttsCandidates: [
      {
        candidate_id: "tts_candidate_approved_001",
        project_id: "project_001",
        segment_id: "seg_002",
        asset_id: "asset_tts_approved",
        source_text: "청취 승인 전 개인 음성 후보",
        technical_status: "accepted",
        operator_review_status: "pending",
        target_duration_sec: 3,
        actual_duration_sec: 3,
        failure_code: null,
        created_at: "2026-07-12T00:00:00Z",
      },
    ],
  });
  vi.stubGlobal("fetch", fetchMock);

  const view = render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
  fireEvent.click(await screen.findByRole("button", { name: /편집 시작/i }));

  expect(await screen.findByText(/기술 검증 통과 · 청취 승인 대기/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /이 후보 선택/i })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "청취 승인" }));

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project_001/tts-candidates/tts_candidate_approved_001/listening-review",
      expect.objectContaining({ method: "PATCH" }),
    ),
  );
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: "청취 승인" })).not.toBeInTheDocument(),
  );
  expect(screen.getByRole("button", { name: /이 후보 선택/i })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: /이 후보 선택/i }));
  expect(screen.getByLabelText("TTS 추천 ID")).toHaveValue(
    "tts_candidate_approved_001",
  );
  expect(screen.getByLabelText("TTS 자산 ID")).toHaveValue("asset_tts_approved");

  view.unmount();
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
  fireEvent.click(await screen.findByRole("button", { name: /편집 시작/i }));
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: "청취 승인" })).not.toBeInTheDocument(),
  );
  expect(screen.getByRole("button", { name: /이 후보 선택/i })).toBeEnabled();
});

it("recovers after a failed TTS listening approval save", async () => {
  const fetchMock = createFetchMock({
    ttsListeningReviewStatuses: [500, 200],
    ttsCandidates: [
      {
        candidate_id: "tts_candidate_retry_001",
        project_id: "project_001",
        segment_id: "seg_002",
        asset_id: "asset_tts_retry",
        source_text: "재시도 청취 후보",
        technical_status: "accepted",
        operator_review_status: "pending",
        target_duration_sec: 3,
        actual_duration_sec: 3,
        failure_code: null,
        created_at: "2026-07-12T00:00:00Z",
      },
    ],
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
  fireEvent.click(await screen.findByRole("button", { name: /편집 시작/i }));

  fireEvent.click(await screen.findByRole("button", { name: "청취 승인" }));
  expect(await screen.findByText(/TTS 청취 승인 실패/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /이 후보 선택/i })).toBeDisabled();

  fireEvent.click(screen.getByRole("button", { name: "청취 승인" }));
  expect(await screen.findByText(/기술 검증 통과 · 청취 승인됨/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /이 후보 선택/i })).toBeEnabled();
});

describe("App", () => {
  it("uploads a selected voice sample and makes its asset ID available to TTS generation", async () => {
    const fetchMock = createFetchMock();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^설정$/i }));
    const picker = screen.getByLabelText("음성 샘플 파일 선택");
    fireEvent.change(picker, {
      target: { files: [new File(["voice"], "my voice.wav", { type: "audio/wav" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: "선택한 파일 업로드" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/assets/voice-sample/upload",
        expect.objectContaining({ method: "POST", body: expect.any(FormData) }),
      ),
    );
    expect(await screen.findByDisplayValue("asset_voice_uploaded_001")).toBeInTheDocument();
  });

  it("keeps the selected voice file recoverable after an upload failure", async () => {
    const fetchMock = createFetchMock({ voiceSampleUploadStatus: 500 });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^설정$/i }));
    const picker = screen.getByLabelText("음성 샘플 파일 선택");
    fireEvent.change(picker, {
      target: { files: [new File(["voice"], "retry.wav", { type: "audio/wav" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: "선택한 파일 업로드" }));

    expect(await screen.findByText(/음성 샘플 업로드 실패/i)).toBeInTheDocument();
    expect(screen.getByText("선택됨 · retry.wav")).toBeInTheDocument();
  });

  it("restores the latest registered voice sample ID after refresh", async () => {
    const fetchMock = createFetchMock({
      voiceSamples: {
        assets: [
          {
            asset_id: "asset_voice_restored_001",
            asset_type: "voice_sample_audio",
            storage_uri: "local://projects/project_001/assets/imported/restored.wav",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^설정$/i }));
    expect(await screen.findByDisplayValue("asset_voice_restored_001")).toBeInTheDocument();
  });

  it("restores the last successful final and CapCut artifacts after reload", async () => {
    const restoredJobs = structuredClone(jobsResponse);
    restoredJobs.jobs.push(
      {
        job_id: "final_render_job_009",
        job_type: "final_render",
        status: "succeeded",
        input_ref: "timeline_build_job_005",
        output_ref: "final_render_001",
        error_message: null,
        started_at: "2026-07-12T00:00:00Z",
        finished_at: "2026-07-12T00:01:00Z",
      },
      {
        job_id: "capcut_draft_job_009",
        job_type: "capcut_draft_export",
        status: "succeeded",
        input_ref: "timeline_build_job_005",
        output_ref: "capcut_draft_001",
        error_message: null,
        started_at: "2026-07-12T00:01:00Z",
        finished_at: "2026-07-12T00:02:00Z",
      },
    );
    const fetchMock = createFetchMock({ jobs: restoredJobs });
    vi.stubGlobal("fetch", fetchMock);

    const firstRender = render(<App />);
    expect(await screen.findByText(/exports\/final\/output.mp4/i)).toBeInTheDocument();
    expect(screen.getByText(/exports\/capcut-draft\/draft/i)).toBeInTheDocument();
    expect(screen.getByText(/CapCut에서 후처리 필요/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "CapCut 초안 다시 시도" })).not.toBeInTheDocument();
    firstRender.unmount();

    render(<App />);
    expect(await screen.findByText(/exports\/final\/output.mp4/i)).toBeInTheDocument();
    expect(screen.getByText(/exports\/capcut-draft\/draft/i)).toBeInTheDocument();
    expect(screen.getByText(/CapCut에서 후처리 필요/i)).toBeInTheDocument();
  });

  it("does not render a CapCut after-processing warning when the persisted notes are empty", async () => {
    const restoredJobs = structuredClone(jobsResponse);
    restoredJobs.jobs.push({
      job_id: "capcut_draft_job_009",
      job_type: "capcut_draft_export",
      status: "succeeded",
      input_ref: "timeline_build_job_005",
      output_ref: "capcut_draft_001",
      error_message: null,
      started_at: "2026-07-12T00:01:00Z",
      finished_at: "2026-07-12T00:02:00Z",
    });
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        jobs: restoredJobs,
        capcutDraftResult: {
          job_id: "capcut_draft_job_009",
          status: "succeeded",
          export: {
            export_id: "capcut_draft_001",
            timeline_id: "timeline_001",
            export_type: "capcut_draft_export",
            file_uri: "local://projects/project_001/exports/capcut-draft/draft",
            status: "succeeded",
            notes: [],
          },
          error_message: null,
        },
      }),
    );

    render(<App />);

    expect(await screen.findByText(/exports\/capcut-draft\/draft/i)).toBeInTheDocument();
    expect(screen.queryByText(/CapCut에서 후처리 필요/i)).not.toBeInTheDocument();
  });

  it("restores a registered CapCut project path after reload", async () => {
    const restoredJobs = structuredClone(jobsResponse);
    restoredJobs.jobs.push({
      job_id: "capcut_draft_job_009",
      job_type: "capcut_draft_export",
      status: "succeeded",
      input_ref: "timeline_build_job_005",
      output_ref: "capcut_draft_001",
      error_message: null,
      started_at: "2026-07-12T00:01:00Z",
      finished_at: "2026-07-12T00:02:00Z",
    });
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        jobs: restoredJobs,
        capcutDraftResult: {
          job_id: "capcut_draft_job_009",
          status: "succeeded",
          export: {
            export_id: "capcut_draft_001",
            timeline_id: "timeline_001",
            export_type: "capcut_draft_export",
            file_uri: "local://projects/project_001/exports/capcut-draft/draft",
            status: "succeeded",
            notes: [],
            handoff: {
              status: "ready",
              source_file_uri: "local://projects/project_001/exports/capcut-draft/draft",
              registered_project_path: "C:/CapCut/User Data/Projects/com.lveditor.draft/videobox-export_001",
              error_message: null,
              registered_at: "2026-07-12T00:02:30Z",
              reused: false,
            },
          },
          error_message: null,
        },
      }),
    );

    render(<App />);

    expect(await screen.findByText("CapCut에 열기 준비")).toBeInTheDocument();
    expect(screen.getByText(/videobox export 001/i)).toBeInTheDocument();
  });

  it("shows and restores CapCut connection readiness details after reload", async () => {
    const fetchMock = createFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    const firstRender = render(<App />);
    expect(await screen.findByText("CapCut 연결 진단")).toBeInTheDocument();
    expect(screen.getByText("연결 준비 완료")).toBeInTheDocument();
    expect(screen.getByText("8.9.1.3802 · 지원됨")).toBeInTheDocument();
    expect(screen.getByText(/CapCut\/Apps\/8.9.1.3802\/CapCut.exe/i)).toBeInTheDocument();
    firstRender.unmount();

    render(<App />);
    expect(await screen.findByText("CapCut 연결 진단")).toBeInTheDocument();
    expect(screen.getByText("연결 준비 완료")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/capcut/handoff-diagnostics", undefined);
  });

  it("shows Korean CapCut diagnostic recovery guidance and retries the machine check", async () => {
    const failedDiagnostics = {
      status: "failed",
      installation_path: null,
      detected_version: null,
      is_supported: false,
      project_root_path: "C:/Users/operator/AppData/Local/CapCut/User Data/Projects/com.lveditor.draft",
      project_root_exists: false,
      write_access: false,
      recovery_message: "CapCut을 한 번 실행해 프로젝트 폴더를 만든 뒤 다시 진단하세요.",
      checked_at: "2026-07-13T00:00:00Z",
    };
    const fetchMock = createFetchMock({
      capcutDiagnosticsResponses: [failedDiagnostics, capcutDiagnosticsReadyResponse],
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    expect(await screen.findByText("CapCut 연결 진단")).toBeInTheDocument();
    expect(screen.getByText("연결 준비 필요")).toBeInTheDocument();
    expect(screen.getByText(/CapCut을 한 번 실행해 프로젝트 폴더를 만든 뒤/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "다시 진단" }));

    expect(await screen.findByText("연결 준비 완료")).toBeInTheDocument();
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/capcut/handoff-diagnostics", undefined),
    );
  });

  it("shows a Korean CapCut registration failure and retries it without losing the draft", async () => {
    const restoredJobs = structuredClone(jobsResponse);
    restoredJobs.jobs.push({
      job_id: "capcut_draft_job_009",
      job_type: "capcut_draft_export",
      status: "succeeded",
      input_ref: "timeline_build_job_005",
      output_ref: "capcut_draft_001",
      error_message: null,
      started_at: "2026-07-12T00:01:00Z",
      finished_at: "2026-07-12T00:02:00Z",
    });
    const fetchMock = createFetchMock({
      jobs: restoredJobs,
      capcutDraftResult: {
        job_id: "capcut_draft_job_009",
        status: "succeeded",
        export: {
          export_id: "capcut_draft_001",
          timeline_id: "timeline_001",
          export_type: "capcut_draft_export",
          file_uri: "local://projects/project_001/exports/capcut-draft/draft",
          status: "succeeded",
          notes: [],
          handoff: {
            status: "failed",
            source_file_uri: "local://projects/project_001/exports/capcut-draft/draft",
            registered_project_path: null,
            error_message: "CapCut 설치를 확인한 뒤 다시 시도하세요.",
            registered_at: null,
            reused: false,
          },
        },
        error_message: null,
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByText(/CapCut 등록 실패: CapCut 설치를 확인/i)).toBeInTheDocument();
    expect(screen.getByText(/exports\/capcut-draft\/draft/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "CapCut 등록 다시 시도" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/capcut-draft-exports/capcut_draft_job_009/handoff",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    expect(await screen.findByText("CapCut에 열기 준비")).toBeInTheDocument();
  });

  it("restores the latest failed CapCut draft export while preserving the earlier successful artifact", async () => {
    const restoredJobs: { jobs: JobFixture[] } = {
      jobs: jobsResponse.jobs.filter((job) => job.job_type !== "capcut_draft_export"),
    };
    restoredJobs.jobs.push(
      {
        job_id: "capcut_draft_job_008",
        job_type: "capcut_draft_export",
        status: "succeeded",
        input_ref: "timeline_build_job_005",
        output_ref: "capcut_draft_001",
        error_message: null,
        started_at: "2026-07-13T00:01:00Z",
        finished_at: "2026-07-13T00:02:00Z",
      },
      {
        job_id: "capcut_draft_job_009",
        job_type: "capcut_draft_export",
        status: "failed",
        input_ref: "timeline_build_job_005",
        output_ref: null,
        error_message: "CapCut draft package could not be written.",
        started_at: "2026-07-13T00:03:00Z",
        finished_at: "2026-07-13T00:04:00Z",
      },
    );
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        jobs: restoredJobs,
        capcutDraftResults: {
          capcut_draft_job_008: {
            job_id: "capcut_draft_job_008",
            status: "succeeded",
            export: {
              export_id: "capcut_draft_001",
              timeline_id: "timeline_001",
              export_type: "capcut_draft_export",
              file_uri: "local://projects/project_001/exports/capcut-draft/draft",
              status: "succeeded",
              notes: [],
            },
            error_message: null,
          },
          capcut_draft_job_009: {
            job_id: "capcut_draft_job_009",
            status: "failed",
            export: null,
            error_message: "CapCut draft package could not be written.",
          },
        },
      }),
    );

    render(<App />);

    expect(await screen.findByText(/CapCut 초안 내보내기 실패/)).toBeInTheDocument();
    expect(screen.getByText(/CapCut draft package could not be written/i)).toBeInTheDocument();
    expect(screen.getByText(/마지막 성공 유지.*exports\/capcut-draft\/draft/i)).toBeInTheDocument();
  });

  it("renders a final-render failure with a null artifact without unmounting the dashboard", async () => {
    const fetchMock = createFetchMock({
      finalRenderResult: {
        job_id: "final_render_job_009",
        status: "failed",
        render: null,
        error_message: "FFmpeg could not resolve the requested B-roll source.",
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await screen.findByText("timeline_001");
    fireEvent.click(await screen.findByRole("button", { name: "완성본 렌더" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/jobs/final-render",
        expect.objectContaining({ method: "POST" }),
      ),
    );

    expect(await screen.findByText("완성본 렌더 실패")).toBeInTheDocument();
    expect(screen.getByText(/B-roll source/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "VideoBox 작업판" })).toBeInTheDocument();
  });

  it("renders a CapCut draft failure with a null artifact without unmounting the dashboard", async () => {
    const fetchMock = createFetchMock({
      capcutDraftResult: {
        job_id: "capcut_draft_job_009",
        status: "failed",
        export: null,
        error_message: "CapCut draft package could not be written.",
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await screen.findByText("timeline_001");

    fireEvent.click(screen.getByRole("button", { name: "CapCut 초안(실제)" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/jobs/capcut-draft-export",
        expect.any(Object),
      );
    });

    expect(await screen.findByText("CapCut 초안 내보내기 실패")).toBeInTheDocument();
    expect(screen.getByText(/CapCut draft package/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "CapCut 초안 다시 시도" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "VideoBox 작업판" })).toBeInTheDocument();
  });

  it("offers a retry action after a failed final render", async () => {
    const fetchMock = createFetchMock({
      finalRenderResult: {
        job_id: "final_render_job_009",
        status: "failed",
        render: null,
        error_message: "FFmpeg failed.",
      },
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    await screen.findByText("timeline_001");

    fireEvent.click(screen.getByRole("button", { name: "완성본 렌더" }));
    await screen.findByText("완성본 렌더 실패");

    fireEvent.click(screen.getByRole("button", { name: "완성본 렌더 다시 시도" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.filter(
          ([url, init]) =>
            String(url).endsWith("/api/projects/project_001/jobs/final-render") && init?.method === "POST",
        ),
      ).toHaveLength(2);
    });
  });

  it("renders the dashboard with Korean short labels instead of explanatory English copy", async () => {
    vi.stubGlobal("fetch", createFetchMock());

    render(<App />);

    expect(await screen.findByRole("heading", { name: /VideoBox 작업판/i })).toBeInTheDocument();
    expect(screen.getByText(/프로젝트 · 타임라인 · 검수 · 출력/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /개요/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^검수$/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /진행/i })).toBeInTheDocument();
    expect(screen.getByText(/^전사$/i)).toBeInTheDocument();
    expect(screen.queryByText(/Local-first review shell/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Inspect projects/i)).not.toBeInTheDocument();
  });

  it("renders a local-first operator dashboard from API data", async () => {
    const fetchMock = createFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: /VideoBox 작업판/i }),
    ).toBeInTheDocument();
    expect(await screen.findByText(/작업자 검수 데모/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /타임라인/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /스냅샷/i })).toBeInTheDocument();
    expect((await screen.findAllByText(/preview_render_job_006/i)).length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/capcut_export_job_007/i)).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /^검수$/i }));

    expect(await screen.findByRole("heading", { name: /^추천 항목$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /추천 승인/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /추천 거절/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /수동 편집/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /타임라인 재생성/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/jobs/build-timeline",
        expect.objectContaining({
          method: "POST",
        }),
      );
    });

    expect(await screen.findByRole("button", { name: /검수 재개/i })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /자막 생성/i }));
    fireEvent.click(await screen.findByRole("button", { name: /미리보기 생성/i }));
    fireEvent.click(await screen.findByRole("button", { name: /캡컷 내보내기/i }));

    expect(await screen.findByText(/HTML 미리보기/i)).toBeInTheDocument();
    expect(await screen.findAllByText(/subtitle_001\.srt/i)).toHaveLength(2);
    expect(await screen.findByText(/캡컷 초안 생성/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/projects", undefined);
    });
  });

  it("opens the pending recommendation target in the editing session and narrows the rerun field to the relevant recommendation type", async () => {
    const fetchMock = createFetchMock({
      reviewSnapshot: blockedReviewSnapshotResponse,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^검수$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /추천 검수 · seg_002/i }));

    expect(await screen.findByRole("heading", { name: /편집기/i })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /대상 세그먼트/i })).toHaveValue("seg_002");
    expect(screen.getByRole("checkbox", { name: /TTS/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /B롤/i })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /설명 카드/i })).not.toBeChecked();
  });

  it("approves a pending recommendation through the review action and refreshes the review snapshot", async () => {
    const actionableTimeline: TimelineJob = {
      ...timelineResponse,
      timeline: {
        ...timelineResponse.timeline,
        review_status: "blocked",
        applied_recommendations: [],
        pending_recommendations: [
          {
            recommendation_id: "rec_broll_review_002",
            target_segment_id: "seg_002",
            recommendation_type: "broll",
            selected_asset_id: "asset_broll_review_002",
            score: 0.88,
            reason: "Operator should confirm the suggested B-roll pick.",
            auto_apply_allowed: false,
            review_required: true,
            payload: { tags: ["team", "meeting"] },
            created_at: "2026-06-30T00:00:00Z",
          },
        ],
        review_flags: [
          {
            code: "broll_review_required",
            segment_id: "seg_002",
            message: "Operator must confirm the B-roll pick before approval.",
          },
        ],
      },
    };
    const actionableReviewSnapshot: ReviewSnapshot = {
      ...reviewSnapshotResponse,
      review_status: "blocked",
      applied_recommendations: [],
      pending_recommendations: actionableTimeline.timeline.pending_recommendations,
      review_flags: actionableTimeline.timeline.review_flags,
    };
    const fetchMock = createFetchMock({
      timeline: actionableTimeline,
      reviewSnapshot: actionableReviewSnapshot,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^검수$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /^추천 승인$/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/review-snapshots/timeline_build_job_005/recommendations/rec_broll_review_002/approve",
        expect.objectContaining({
          method: "POST",
        }),
      );
    });

    await waitFor(() => {
      expect(
        screen.queryByText(/operator must confirm the b-roll pick before approval/i),
      ).not.toBeInTheDocument();
    });
    expect(
      screen.getByRole("button", { name: /^추천 승인$/i }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: /타임라인 승인/i })).toBeEnabled();
  });

  it("opens the actionable pending recommendation in the editing session when marked for manual edit", async () => {
    const actionableTimeline: TimelineJob = {
      ...timelineResponse,
      timeline: {
        ...timelineResponse.timeline,
        review_status: "blocked",
        applied_recommendations: [],
        pending_recommendations: [
          {
            recommendation_id: "rec_broll_review_002",
            target_segment_id: "seg_002",
            recommendation_type: "broll",
            selected_asset_id: "asset_broll_review_002",
            score: 0.88,
            reason: "Operator should confirm the suggested B-roll pick.",
            auto_apply_allowed: false,
            review_required: true,
            payload: { tags: ["team", "meeting"] },
            created_at: "2026-06-30T00:00:00Z",
          },
        ],
        review_flags: [
          {
            code: "broll_review_required",
            segment_id: "seg_002",
            message: "Operator must confirm the B-roll pick before approval.",
          },
        ],
      },
    };
    const actionableReviewSnapshot: ReviewSnapshot = {
      ...reviewSnapshotResponse,
      review_status: "blocked",
      applied_recommendations: [],
      pending_recommendations: actionableTimeline.timeline.pending_recommendations,
      review_flags: actionableTimeline.timeline.review_flags,
    };
    const fetchMock = createFetchMock({
      timeline: actionableTimeline,
      reviewSnapshot: actionableReviewSnapshot,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^검수$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /수동 편집/i }));

    expect(await screen.findByRole("heading", { name: /편집기/i })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /대상 세그먼트/i })).toHaveValue("seg_002");
    expect(screen.getByRole("checkbox", { name: /B롤/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /TTS/i })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /설명 카드/i })).not.toBeChecked();
  });

  it("shows B-roll recommendation evidence with archived asset metadata in the review snapshot", async () => {
    const brollRecommendation = {
      recommendation_id: "rec_broll_review_002",
      target_segment_id: "seg_002",
      recommendation_type: "broll",
      selected_asset_id: "asset_broll_archive_002",
      score: 0.88,
      reason: "Matched meeting keywords.",
      auto_apply_allowed: false,
      review_required: true,
      payload: { matched_tags: ["team", "meeting"] },
      created_at: "2026-06-30T00:00:00Z",
    };
    const reviewSnapshot: ReviewSnapshot = {
      ...reviewSnapshotResponse,
      review_status: "blocked",
      applied_recommendations: [],
      pending_recommendations: [brollRecommendation],
      review_flags: [],
    };
    vi.stubGlobal("fetch", createFetchMock({ reviewSnapshot }));

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^검수$/i }));

    expect(await screen.findByText(/팀 화이트보드/i)).toBeInTheDocument();
    expect(screen.getByText(/asset_broll_archive_002/i)).toBeInTheDocument();
    expect(screen.getByText(/점수 0.88/i)).toBeInTheDocument();
    expect(screen.getByText(/^회의$/i)).toBeInTheDocument();
    expect(screen.getByText(/매칭: 팀, 회의/i)).toBeInTheDocument();
    expect(screen.getByText(/태그: 팀, 기획/i)).toBeInTheDocument();
  });

  it("opens the flagged segment in the editing session without overwriting its default rerun scope when no direct field mapping exists", async () => {
    const fetchMock = createFetchMock({
      reviewSnapshot: blockedReviewSnapshotResponse,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^검수$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /편집 확인 · seg_002/i }));

    expect(await screen.findByRole("heading", { name: /편집기/i })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /대상 세그먼트/i })).toHaveValue("seg_002");
    expect(screen.getByRole("checkbox", { name: /B롤/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /설명 카드/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /TTS/i })).not.toBeChecked();
  });

  it("opens the review snapshot segment directly in the editing session", async () => {
    const fetchMock = createFetchMock({
      reviewSnapshot: blockedReviewSnapshotResponse,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^검수$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /편집 열기 · seg_002/i }));

    expect(await screen.findByRole("heading", { name: /편집기/i })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /대상 세그먼트/i })).toHaveValue("seg_002");
    expect(screen.getByRole("checkbox", { name: /B롤/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /설명 카드/i })).toBeChecked();
  });

  it("falls back to the segment default rerun scope when a pending recommendation type is not mapped to an editor field", async () => {
    const fetchMock = createFetchMock({
      reviewSnapshot: {
        ...blockedReviewSnapshotResponse,
        pending_recommendations: [
          {
            recommendation_id: "rec_012",
            target_segment_id: "seg_002",
            recommendation_type: "manual_review",
            selected_asset_id: null,
            score: 0.41,
            reason: "Operator should inspect this segment manually.",
            auto_apply_allowed: false,
            review_required: true,
            payload: {},
            created_at: "2026-06-28T00:00:07Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^검수$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /추천 검수 · seg_002/i }));

    expect(await screen.findByRole("heading", { name: /편집기/i })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /대상 세그먼트/i })).toHaveValue("seg_002");
    expect(screen.getByRole("checkbox", { name: /B롤/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /설명 카드/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /TTS/i })).not.toBeChecked();
  });

  it("disables preview and export controls until review blockers are cleared", async () => {
    const blockedTimelineResponse = {
      ...timelineResponse,
      timeline: {
        ...timelineResponse.timeline,
        review_flags: [
          {
            code: "segment_review_required",
            segment_id: "seg_002",
            message: "Segment requires operator review before export.",
          },
        ],
        pending_recommendations: [
          {
            recommendation_id: "rec_011",
            target_segment_id: "seg_002",
            recommendation_type: "tts_replacement",
            selected_asset_id: null,
            score: 0.74,
            reason: "Pronunciation restart detected",
            auto_apply_allowed: false,
            review_required: true,
            payload: { provider: "voicebox" },
            created_at: "2026-06-28T00:00:06Z",
          },
        ],
      },
    };
    const blockedReviewSnapshotResponse = {
      ...reviewSnapshotResponse,
      review_status: "blocked",
      segments: reviewSnapshotResponse.segments.map((segment) =>
        segment.segment_id === "seg_002"
          ? {
              ...segment,
              text: "Team meeting restart",
              confidence: 0.78,
              review_required: true,
              cleanup_decision: "review",
            }
          : segment,
      ),
      pending_recommendations: blockedTimelineResponse.timeline.pending_recommendations,
      review_flags: blockedTimelineResponse.timeline.review_flags,
    };
    const blockedJobsResponse = {
      jobs: jobsResponse.jobs.filter(
        (job) =>
          job.job_type !== "subtitle_render" &&
          job.job_type !== "preview_render" &&
          job.job_type !== "capcut_export",
      ),
    };

    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/projects")) {
        return Promise.resolve(new Response(JSON.stringify(projectsResponse)));
      }
      if (url.endsWith("/api/projects/project_001")) {
        return Promise.resolve(new Response(JSON.stringify(projectResponse)));
      }
      if (url.endsWith("/api/projects/project_001/jobs")) {
        return Promise.resolve(new Response(JSON.stringify(blockedJobsResponse)));
      }
      if (url.endsWith("/api/projects/project_001/timelines/timeline_build_job_005")) {
        return Promise.resolve(new Response(JSON.stringify(blockedTimelineResponse)));
      }
      if (url.endsWith("/api/projects/project_001/review-snapshots/timeline_build_job_005")) {
        return Promise.resolve(new Response(JSON.stringify(blockedReviewSnapshotResponse)));
      }
      if (url.endsWith("/api/projects/project_001/providers/gemini/keys")) {
        return Promise.resolve(new Response(JSON.stringify(geminiKeysResponse)));
      }
      return Promise.reject(new Error(`Unhandled fetch: ${url}`));
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(
      await screen.findByRole("button", { name: /타임라인 승인/i }),
    ).toBeDisabled();
    expect(
      await screen.findByRole("button", { name: /미리보기 생성/i }),
    ).toBeDisabled();
    expect(
      await screen.findByRole("button", { name: /캡컷 내보내기/i }),
    ).toBeDisabled();
    expect(await screen.findByText(/내보내기 보류/i)).toBeInTheDocument();
    expect(screen.getByText(/검수 표시 1/i)).toBeInTheDocument();
    expect(screen.getByText(/대기 추천 1/i)).toBeInTheDocument();
    expect(screen.getByText(/다음: 검수 탭에서 보류 항목 처리/i)).toBeInTheDocument();
  });

  it("keeps output actions disabled until operator approval even when blockers are clear", async () => {
    const cleanTimelineResponse = {
      ...timelineResponse,
      timeline: {
        ...timelineResponse.timeline,
        review_flags: [],
        pending_recommendations: [],
      },
    };
    const draftReviewSnapshotResponse = {
      ...reviewSnapshotResponse,
      review_status: "draft",
      review_flags: [],
      pending_recommendations: [],
    };
    const draftJobsResponse = {
      jobs: jobsResponse.jobs.filter(
        (job) =>
          job.job_type !== "preview_render" &&
          job.job_type !== "capcut_export" &&
          job.job_type !== "subtitle_render",
      ),
    };

    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/projects")) {
        return Promise.resolve(new Response(JSON.stringify(projectsResponse)));
      }
      if (url.endsWith("/api/projects/project_001")) {
        return Promise.resolve(new Response(JSON.stringify(projectResponse)));
      }
      if (url.endsWith("/api/projects/project_001/jobs")) {
        return Promise.resolve(new Response(JSON.stringify(draftJobsResponse)));
      }
      if (url.endsWith("/api/projects/project_001/timelines/timeline_build_job_005")) {
        return Promise.resolve(new Response(JSON.stringify(cleanTimelineResponse)));
      }
      if (url.endsWith("/api/projects/project_001/review-snapshots/timeline_build_job_005")) {
        return Promise.resolve(new Response(JSON.stringify(draftReviewSnapshotResponse)));
      }
      if (url.endsWith("/api/projects/project_001/providers/gemini/keys")) {
        return Promise.resolve(new Response(JSON.stringify(geminiKeysResponse)));
      }
      return Promise.reject(new Error(`Unhandled fetch: ${url}`));
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /타임라인 승인/i })).toBeEnabled();
    });
    expect(
      await screen.findByRole("button", { name: /자막 생성/i }),
    ).toBeDisabled();
    expect(
      await screen.findByRole("button", { name: /미리보기 생성/i }),
    ).toBeDisabled();
    expect(
      await screen.findByRole("button", { name: /캡컷 내보내기/i }),
    ).toBeDisabled();
    expect(await screen.findByText(/승인 필요/i)).toBeInTheDocument();
    expect(screen.getByText(/다음: 타임라인 승인/i)).toBeInTheDocument();
  });

  it("surfaces approved output readiness before export generation", async () => {
    vi.stubGlobal("fetch", createFetchMock());

    render(<App />);

    expect(await screen.findByText(/내보내기 가능/i)).toBeInTheDocument();
    expect(screen.getByText(/다음: 미리보기 또는 캡컷 내보내기/i)).toBeInTheDocument();
  });

  it("hides stale output stage success from older timelines", async () => {
    const staleOutputJobsResponse = {
      jobs: [
        {
          job_id: "timeline_build_job_004",
          job_type: "timeline_build",
          status: "succeeded",
          input_ref: "segment_analysis_job_002",
          output_ref: "timeline_000",
          error_message: null,
          started_at: "2026-06-28T00:00:07Z",
          finished_at: "2026-06-28T00:00:08Z",
        },
        ...jobsResponse.jobs.map((job) =>
          job.job_type === "subtitle_render" ||
          job.job_type === "preview_render" ||
          job.job_type === "capcut_export"
            ? {
                ...job,
                input_ref: "timeline_build_job_004",
              }
            : job,
        ),
      ],
    };

    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/projects")) {
        return Promise.resolve(new Response(JSON.stringify(projectsResponse)));
      }
      if (url.endsWith("/api/projects/project_001")) {
        return Promise.resolve(new Response(JSON.stringify(projectResponse)));
      }
      if (url.endsWith("/api/projects/project_001/jobs")) {
        return Promise.resolve(new Response(JSON.stringify(staleOutputJobsResponse)));
      }
      if (url.endsWith("/api/projects/project_001/timelines/timeline_build_job_005")) {
        return Promise.resolve(new Response(JSON.stringify(timelineResponse)));
      }
      if (url.endsWith("/api/projects/project_001/review-snapshots/timeline_build_job_005")) {
        return Promise.resolve(new Response(JSON.stringify(reviewSnapshotResponse)));
      }
      if (url.endsWith("/api/projects/project_001/providers/gemini/keys")) {
        return Promise.resolve(new Response(JSON.stringify(geminiKeysResponse)));
      }
      return Promise.reject(new Error(`Unhandled fetch: ${url}`));
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const subtitleCard = (await screen.findByText("자막")).closest("article");
    const previewCard = (await screen.findByText("미리보기")).closest("article");
    const exportCard = (await screen.findByText("캡컷")).closest("article");

    expect(subtitleCard).not.toBeNull();
    expect(previewCard).not.toBeNull();
    expect(exportCard).not.toBeNull();

    expect(within(subtitleCard!).getByText("대기")).toBeInTheDocument();
    expect(within(previewCard!).getByText("대기")).toBeInTheDocument();
    expect(within(exportCard!).getByText("대기")).toBeInTheDocument();

    fireEvent.click(screen.getByText(/단계별 job ID 보기/i));
    expect(screen.getAllByText(/미시작/i).length).toBeGreaterThan(0);
  });

  it("keeps the baseline dashboard usable when Gemini key loading fails", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/projects")) {
        return Promise.resolve(new Response(JSON.stringify(projectsResponse)));
      }
      if (url.endsWith("/api/projects/project_001")) {
        return Promise.resolve(new Response(JSON.stringify(projectResponse)));
      }
      if (url.endsWith("/api/projects/project_001/jobs")) {
        return Promise.resolve(new Response(JSON.stringify(jobsResponse)));
      }
      if (url.endsWith("/api/projects/project_001/timelines/timeline_build_job_005")) {
        return Promise.resolve(new Response(JSON.stringify(timelineResponse)));
      }
      if (url.endsWith("/api/projects/project_001/review-snapshots/timeline_build_job_005")) {
        return Promise.resolve(new Response(JSON.stringify(reviewSnapshotResponse)));
      }
      if (url.endsWith("/api/projects/project_001/previews/preview_render_job_006")) {
        return Promise.resolve(new Response(JSON.stringify(previewResponse)));
      }
      if (url.endsWith("/api/projects/project_001/subtitles/subtitle_render_job_008")) {
        return Promise.resolve(new Response(JSON.stringify(subtitleResponse)));
      }
      if (url.endsWith("/api/projects/project_001/exports/capcut_export_job_007")) {
        return Promise.resolve(new Response(JSON.stringify(exportResponse)));
      }
      if (url.endsWith("/api/projects/project_001/providers/gemini/keys")) {
        return Promise.resolve(new Response("provider unavailable", { status: 503 }));
      }
      return Promise.reject(new Error(`Unhandled fetch: ${url}`));
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByText(/작업자 검수 데모/i)).toBeInTheDocument();
    expect(await screen.findByText(/timeline_001/i)).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /^설정$/i }));
    expect(await screen.findByText(/제미나이 라우팅 오류/i)).toBeInTheDocument();
    expect(screen.queryByText(/request failed: \/api\/projects\/project_001\/providers\/gemini\/keys/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/제미나이 키 없음/i)).not.toBeInTheDocument();
  });

  it("renders masked Gemini keys with routing state visibility and never leaks raw secrets", async () => {
    const fetchMock = createFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /^설정$/i }));

    expect(await screen.findByRole("heading", { name: /^키$/i })).toBeInTheDocument();
    expect(await screen.findByText(/기본 라우팅 키/i)).toBeInTheDocument();
    expect(await screen.findByText("AIza...1234")).toBeInTheDocument();
    expect(await screen.findByText(/대기 예비 키/i)).toBeInTheDocument();
    expect(await screen.findByText(/429 할당량 초과/i)).toBeInTheDocument();
    expect(await screen.findByText(/2026-06-28T00:05:00Z/i)).toBeInTheDocument();
    expect(screen.getAllByText(/연속 실패/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/AIzaSyDANGER_SECRET/i)).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue(/AIzaSyDANGER_SECRET/i)).not.toBeInTheDocument();
  });

  it("creates, updates, disables, and re-enables Gemini keys while refreshing the dashboard state", async () => {
    const fetchMock = createFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /^설정$/i }));

    expect(await screen.findByRole("heading", { name: /^키$/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /키 추가/i }));
    fireEvent.change(screen.getByLabelText(/이름/i), {
      target: { value: "Burst quota key" },
    });
    fireEvent.change(screen.getByLabelText(/API 키/i), {
      target: { value: "AIzaSyDANGER_SECRET" },
    });
    fireEvent.change(screen.getByLabelText(/기본 모델/i), {
      target: { value: "gemini-2.5-flash" },
    });
    fireEvent.change(screen.getByLabelText(/저가 모델/i), {
      target: { value: "gemini-2.5-flash-lite" },
    });
    fireEvent.change(screen.getByLabelText(/고품질 모델/i), {
      target: { value: "gemini-2.5-pro" },
    });
    fireEvent.click(screen.getByRole("button", { name: /키 저장/i }));

    expect(await screen.findByText(/긴급 할당 키/i)).toBeInTheDocument();
    expect(screen.getByText("AIza...9999")).toBeInTheDocument();
    expect(screen.queryByText(/AIzaSyDANGER_SECRET/i)).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue(/AIzaSyDANGER_SECRET/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /기본 라우팅 키 수정/i }));
    fireEvent.change(screen.getByLabelText(/이름/i), {
      target: { value: "Primary routing key v2" },
    });
    fireEvent.change(screen.getByLabelText(/저가 모델/i), {
      target: { value: "gemini-2.5-flash" },
    });
    fireEvent.click(screen.getByRole("button", { name: /변경 저장/i }));

    expect(await screen.findByText(/기본 라우팅 키 v2/i)).toBeInTheDocument();
    expect(screen.getAllByText(/gemini-2.5-flash/i).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /기본 라우팅 키 v2 중지/i }));
    await waitFor(() => {
      expect(screen.getAllByText(/^중지$/i).length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByRole("button", { name: /기본 라우팅 키 v2 사용/i }));
    await waitFor(() => {
      expect(screen.getAllByText(/^사용$/i).length).toBeGreaterThan(1);
    });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/providers/gemini/keys",
        expect.anything(),
      );
    });
  });

  it("supports the thin editing flow with session load, regeneration preflight, and partial regeneration delta visibility", async () => {
    const fetchMock = createFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByText(/작업자 검수 데모/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^편집$/i }));

    fireEvent.click(await screen.findByRole("button", { name: /편집 시작/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            timeline_job_id: "timeline_build_job_005",
          }),
        }),
      );
    });

    expect(await screen.findByText(/editing_session_001/i)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /seg_002/i })).toBeInTheDocument();
    expect(await screen.findByText(/asset_broll_archive_002/i)).toBeInTheDocument();
    expect(
      screen.getByText(/meeting context: summarize the active discussion\./i),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /사전 확인/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/partial-regeneration/preflight",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            segment_ids: ["seg_002"],
            fields: ["broll", "explanation_card"],
          }),
        }),
      );
    });

    expect(await screen.findByText(/영향 출력/i)).toBeInTheDocument();
    expect(screen.getAllByText(/B롤 트랙/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/타임라인 미리보기/i)).toBeInTheDocument();
    expect(screen.getByText(/캡컷 전달/i)).toBeInTheDocument();
    expect(screen.getByText(/재생성 초안/i)).toBeInTheDocument();
    expect(
      screen.getByText(/초안 · 승인 필요/i),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /부분 재생성/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/partial-regeneration",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            expected_revision: 1,
            segment_ids: ["seg_002"],
            fields: ["broll", "explanation_card"],
          }),
        }),
      );
    });

    expect(await screen.findByText(/partial_regeneration_job_001/i)).toBeInTheDocument();
    expect(screen.getAllByText(/B롤 교체/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/timeline_002/i)).toBeInTheDocument();
  });

  it("requires a fresh preflight before partial regeneration can run for the current scope", async () => {
    const fetchMock = createFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /편집 시작/i }));

    const runButton = await screen.findByRole("button", { name: /부분 재생성/i });
    expect(runButton).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: /사전 확인/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/partial-regeneration/preflight",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            segment_ids: ["seg_002"],
            fields: ["broll", "explanation_card"],
          }),
        }),
      );
    });

    await waitFor(() => {
      expect(runButton).toBeEnabled();
    });

    fireEvent.click(screen.getByRole("button", { name: /seg_001/i }));
    expect(runButton).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: /seg_002/i }));
    expect(runButton).toBeDisabled();

    fireEvent.click(screen.getByRole("checkbox", { name: /B롤/i }));
    expect(runButton).toBeDisabled();
  });

  it("keeps explanation image table and tts validation in the thin editor and exposes a read-only preflight scope before execution", async () => {
    const fetchMock = createFetchMock({
      partialRegenerationPreflight: {
        ...partialRegenerationPreflightResponse,
        fields: [
          "explanation_card",
          "image_overlay",
          "table_overlay",
          "tts_replacement",
        ],
        downstream_steps: ["overlay_refresh", "tts_refresh", "timeline_build"],
        affected_output_areas: [
          "visual overlays",
          "narration track",
          "timeline preview",
          "subtitle render",
          "capcut export",
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /편집 시작/i }));

    fireEvent.change(screen.getByLabelText(/설명 텍스트/i), {
      target: { value: "Meeting context: capture the approved discussion points." },
    });
    fireEvent.click(screen.getByRole("button", { name: /설명 저장/i }));

    fireEvent.change(screen.getByLabelText(/이미지 자산 ID/i), {
      target: { value: "asset_image_002" },
    });
    fireEvent.change(screen.getByLabelText(/이미지 텍스트/i), {
      target: { value: "Image overlay summary for the discussion." },
    });
    fireEvent.click(screen.getByRole("button", { name: /이미지 저장/i }));

    fireEvent.change(screen.getByLabelText(/표 열/i), {
      target: { value: "Topic, Owner" },
    });
    fireEvent.change(screen.getByLabelText(/표 행/i), {
      target: { value: "Launch plan, Louis\nQA follow-up, Team" },
    });
    fireEvent.change(screen.getByLabelText(/표 텍스트/i), {
      target: { value: "Table overlay summary for operator review." },
    });
    fireEvent.click(screen.getByRole("button", { name: /표 저장/i }));

    fireEvent.change(screen.getByLabelText(/TTS 추천 ID/i), {
      target: { value: "rec_tts_002" },
    });
    fireEvent.change(screen.getByLabelText(/TTS 자산 ID/i), {
      target: { value: "tts_asset_002" },
    });
    fireEvent.click(screen.getByRole("button", { name: /TTS 저장/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/explanation-card",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({
            expected_revision: 1,
            title: "Meeting context",
            body: "Summarize the active discussion.",
            text: "Meeting context: capture the approved discussion points.",
          }),
        }),
      );
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/image-overlay",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          expected_revision: 1,
          asset_id: "asset_image_002",
          text: "Image overlay summary for the discussion.",
        }),
      }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/table-overlay",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          expected_revision: 1,
          columns: ["Topic", "Owner"],
          rows: [
            ["Launch plan", "Louis"],
            ["QA follow-up", "Team"],
          ],
          text: "Table overlay summary for operator review.",
        }),
      }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/tts-replacement",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          expected_revision: 1,
          recommendation_id: "rec_tts_002",
          asset_id: "tts_asset_002",
        }),
      }),
    );

    fireEvent.click(screen.getByRole("checkbox", { name: /B롤/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /이미지/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /표/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /TTS/i }));

    fireEvent.click(screen.getByRole("button", { name: /사전 확인/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/partial-regeneration/preflight",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            segment_ids: ["seg_002"],
            fields: [
              "explanation_card",
              "image_overlay",
              "table_overlay",
              "tts_replacement",
            ],
          }),
        }),
      );
    });

    expect(
      await screen.findByRole("heading", { name: /사전 확인 범위/i }),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/seg_002 포함/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/설명 카드 선택/i)).toBeInTheDocument();
    expect(screen.getByText(/이미지 선택/i)).toBeInTheDocument();
    expect(screen.getByText(/표 선택/i)).toBeInTheDocument();
    expect(screen.getByText(/TTS 선택/i)).toBeInTheDocument();
    expect(
      screen.getByText(/읽기 전용 · 타임라인 유지/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/partial_regeneration_job_001/i)).not.toBeInTheDocument();
    expect(
      fetchMock,
    ).not.toHaveBeenCalledWith(
      "/api/projects/project_001/editing-sessions/editing_session_001/partial-regeneration",
      expect.anything(),
    );
  });

  it("keeps incomplete explanation image table music and tts drafts local until the operator enters enough data to save", async () => {
    const fetchMock = createFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /편집 시작/i }));
    expect(await screen.findByText(/editing_session_001/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/설명 텍스트/i), {
      target: { value: "" },
    });

    const explanationButton = screen.getByRole("button", { name: /설명 저장/i });
    const imageButton = screen.getByRole("button", { name: /이미지 저장/i });
    const tableButton = screen.getByRole("button", { name: /표 저장/i });
    const musicButton = screen.getByRole("button", { name: /음악 저장/i });
    const ttsButton = screen.getByRole("button", { name: /TTS 저장/i });

    expect(explanationButton).toBeDisabled();
    expect(imageButton).toBeDisabled();
    expect(tableButton).toBeDisabled();
    expect(musicButton).toBeDisabled();
    expect(ttsButton).toBeDisabled();
    expect(explanationButton).toHaveAttribute("aria-describedby", "seg_002-explanation-save-help");
    expect(imageButton).toHaveAttribute("aria-describedby", "seg_002-image-save-help");
    expect(tableButton).toHaveAttribute("aria-describedby", "seg_002-table-save-help");
    expect(musicButton).toHaveAttribute("aria-describedby", "seg_002-music-save-help");
    expect(ttsButton).toHaveAttribute("aria-describedby", "seg_002-tts-save-help");
    expect(screen.getByText(/설명 텍스트 필요/i)).toBeInTheDocument();
    expect(screen.getByText(/이미지 ID 필요/i)).toBeInTheDocument();
    expect(screen.getByText(/표 텍스트 필요/i)).toBeInTheDocument();
    expect(screen.getByText(/음악 ID 필요/i)).toBeInTheDocument();
    expect(
      screen.getByText(/TTS 추천 ID · 자산 ID 필요/i),
    ).toBeInTheDocument();

    fireEvent.click(explanationButton);
    fireEvent.click(imageButton);
    fireEvent.click(tableButton);
    fireEvent.click(musicButton);
    fireEvent.click(ttsButton);

    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/explanation-card",
      expect.anything(),
    );
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/image-overlay",
      expect.anything(),
    );
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/table-overlay",
      expect.anything(),
    );
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/music",
      expect.anything(),
    );
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/tts-replacement",
      expect.anything(),
    );
  });

  async function renderStartedEditingSession(fetchMock = createFetchMock()) {
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /편집 시작/i }));
    return fetchMock;
  }

  async function runCandidateToApprovalReady() {
    fireEvent.click(await screen.findByRole("button", { name: /사전 확인/i }));
    fireEvent.click(await screen.findByRole("button", { name: /부분 재생성/i }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /타임라인 승인/i })).toBeEnabled();
    });
  }

  async function expectCandidateInvalidated() {
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /타임라인 승인/i })).toBeDisabled();
    });
    expect(screen.queryByText(/partial_regeneration_job_001/i)).not.toBeInTheDocument();
  }

  it("places an archived B-roll card through the sole manual library path with SHA identity", async () => {
    const fetchMock = await renderStartedEditingSession();

    const card = (await screen.findByText("asset_broll_archive_002")).closest("article");
    expect(card).not.toBeNull();
    fireEvent.click(card!.querySelector("button:last-of-type")!);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/broll",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ expected_revision: 1, asset_id: "asset_broll_archive_002", media_controls: { expected_content_sha256: "", media_revision: "2026-07-06T00:00:01Z" } }),
        }),
      );
    });
  });

  it("refreshes project recent media state after applying a local B-roll", async () => {
    const fetchMock = await renderStartedEditingSession();
    const recentCallsBeforeApply = fetchMock.mock.calls.filter(([url, init]) =>
      String(url).endsWith("/api/projects/project_001/media-library/recent") && !init,
    ).length;
    const card = (await screen.findByText("asset_broll_archive_002")).closest("article");
    expect(card).not.toBeNull();

    fireEvent.click(within(card!).getByRole("button", { name: /선택 구간에 B롤 적용/i }));

    await waitFor(() => expect(fetchMock.mock.calls.filter(([url, init]) =>
      String(url).endsWith("/api/projects/project_001/media-library/recent") && !init,
    )).toHaveLength(recentCallsBeforeApply + 1));
    fireEvent.click(screen.getByRole("button", { name: "B롤 필터: 최근" }));
    expect(screen.getByText("asset_broll_archive_002")).toBeInTheDocument();
  });

  it("shows a short success message after saving an editing change", async () => {
    await renderStartedEditingSession();

    fireEvent.change(screen.getByDisplayValue("Team meeting overview"), {
      target: { value: "Team meeting overview refreshed" },
    });
    fireEvent.click(screen.getByRole("button", { name: /자막 저장/i }));

    expect(await screen.findByText(/자막 저장됨/i)).toBeInTheDocument();
  });

  it("shows a short failure message near the editor when an editing save fails", async () => {
    await renderStartedEditingSession(createFetchMock({ editingMutationStatus: 500 }));

    fireEvent.change(screen.getByDisplayValue("Team meeting overview"), {
      target: { value: "Team meeting overview refreshed" },
    });
    fireEvent.click(screen.getByRole("button", { name: /자막 저장/i }));

    expect(await screen.findByText(/자막 저장 실패/i)).toBeInTheDocument();
  });

  it("reloads the latest session after a 409 without discarding the operator caption draft", async () => {
    const latestSession = {
      ...structuredClone(editingSessionResponse),
      session_revision: 2,
      segments: editingSessionResponse.segments.map((segment) =>
        segment.segment_id === "seg_002"
          ? { ...segment, caption_text: "Other operator update" }
          : segment,
      ),
    };
    await renderStartedEditingSession(createFetchMock({ editingMutationConflictSession: latestSession }));

    fireEvent.click(screen.getByRole("button", { name: /seg_002/i }));
    const captionInput = screen.getByDisplayValue("Team meeting overview");
    fireEvent.input(captionInput, {
      target: { value: "Keep my unsaved caption" },
    });
    expect(await screen.findByText("Keep my unsaved caption")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /자막 저장/i }));

    expect(await screen.findByText(/다른 편집 내용이 있습니다/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /최신 내용 적용/i }));
    expect(await screen.findByDisplayValue("Keep my unsaved caption")).toBeInTheDocument();
  });

  it("marks the selected caption preset as a project-scoped favorite", async () => {
    const fetchMock = await renderStartedEditingSession();

    fireEvent.click(await screen.findByRole("button", { name: /프리셋 즐겨찾기/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editor-library/favorites/project:project_001:builtin:clean",
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({ favorite_type: "preset", enabled: true }),
        }),
      ),
    );
  });

  it("marks a ManualMediaLibrary B-roll card with a project-scoped favorite id", async () => {
    const fetchMock = await renderStartedEditingSession();
    const card = (await screen.findByText("asset_broll_archive_002")).closest("article");
    expect(card).not.toBeNull();
    fireEvent.click(within(card!).getByRole("button", { name: /B롤 즐겨찾기$/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editor-library/favorites/pack:local:asset_broll_archive_002",
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({ favorite_type: "media", enabled: true }),
        }),
      ),
    );
  });

  it("filters ManualMediaLibrary B-roll cards by display name tags and asset id before explicit placement", async () => {
    const fetchMock = await renderStartedEditingSession();
    expect(await screen.findByText(/Office lobby pan/i)).toBeInTheDocument();
    expect(screen.getByText(/Team whiteboard/i)).toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox", { name: /^검색$/i }), {
      target: { value: "planning" },
    });
    expect(screen.queryByText(/Office lobby pan/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Team whiteboard/i)).toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox", { name: /^검색$/i }), {
      target: { value: "archive_001" },
    });
    expect(screen.getByText(/Office lobby pan/i)).toBeInTheDocument();
    expect(screen.queryByText(/Team whiteboard/i)).not.toBeInTheDocument();

    const card = screen.getByText(/Office lobby pan/i).closest("article");
    expect(card).not.toBeNull();
    fireEvent.click(within(card!).getByRole("button", { name: /선택 구간에 B롤 적용/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/broll",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({
            expected_revision: 1,
            asset_id: "asset_broll_archive_001",
            media_controls: { expected_content_sha256: "", media_revision: "2026-07-06T00:00:00Z" },
          }),
        }),
      );
    });
  });

  it("imports a B-roll folder and refreshes the ManualMediaLibrary cards", async () => {
    const fetchMock = await renderStartedEditingSession();
    const folderPath =
      "D:\\AI_Workspace_louis_office_50\\20_project\\65_videobox-project\\비롤_라이브러리\\검수완료";

    fireEvent.change(screen.getByLabelText(/B롤 폴더/i), {
      target: { value: folderPath },
    });
    fireEvent.change(screen.getByLabelText(/B롤 태그/i), {
      target: { value: "folder-import" },
    });
    fireEvent.click(screen.getByRole("button", { name: /B롤 가져오기/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/assets/broll-video/batch",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            source_directory: folderPath,
            source_paths: [],
            tags: ["folder-import"],
          }),
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByText(/factory-line/i)).toBeInTheDocument();
    });
    expect(await screen.findByText(/가져옴 1개/i)).toBeInTheDocument();
    expect(screen.getByText(/asset_broll_archive_003/i)).toBeInTheDocument();
  });

  it("shows a B-roll import error when folder import fails", async () => {
    await renderStartedEditingSession(createFetchMock({ brollBatchImportStatus: 400 }));

    fireEvent.change(screen.getByLabelText(/B롤 폴더/i), {
      target: { value: "D:\\missing\\비롤" },
    });
    fireEvent.click(screen.getByRole("button", { name: /B롤 가져오기/i }));

    expect(await screen.findByText(/B롤 가져오기 실패/i)).toBeInTheDocument();
  });

  it("removes the saved explanation card and invalidates the active candidate", async () => {
    const fetchMock = await renderStartedEditingSession(
      createFetchMock({ candidateReviewSnapshot: candidateReviewSnapshotResponse }),
    );

    await runCandidateToApprovalReady();
    fireEvent.click(screen.getByRole("button", { name: /설명 삭제/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/explanation-card?expected_revision=1",
        expect.objectContaining({
          method: "DELETE",
        }),
      );
    });
    await expectCandidateInvalidated();
    expect(screen.queryByRole("button", { name: /설명 삭제/i })).not.toBeInTheDocument();
    expect(screen.getByText(/설명 카드 없음/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/설명 텍스트/i)).toHaveValue("");
  });

  it("removes the saved image overlay and invalidates the active candidate", async () => {
    const fetchMock = await renderStartedEditingSession(
      createFetchMock({ candidateReviewSnapshot: candidateReviewSnapshotResponse }),
    );

    fireEvent.change(screen.getByLabelText(/이미지 자산 ID/i), {
      target: { value: "asset_image_002" },
    });
    fireEvent.click(screen.getByRole("button", { name: /이미지 저장/i }));

    await runCandidateToApprovalReady();
    fireEvent.click(screen.getByRole("button", { name: /이미지 삭제/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/image-overlay?expected_revision=1",
        expect.objectContaining({
          method: "DELETE",
        }),
      );
    });
    await expectCandidateInvalidated();
    expect(screen.queryByRole("button", { name: /이미지 삭제/i })).not.toBeInTheDocument();
    expect(screen.getByText(/이미지 없음/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/이미지 자산 ID/i)).toHaveValue("");
  });

  it("removes the saved table overlay and invalidates the active candidate", async () => {
    const fetchMock = await renderStartedEditingSession(
      createFetchMock({ candidateReviewSnapshot: candidateReviewSnapshotResponse }),
    );

    fireEvent.change(screen.getByLabelText(/표 텍스트/i), {
      target: { value: "Table overlay summary for operator review." },
    });
    fireEvent.click(screen.getByRole("button", { name: /표 저장/i }));

    await runCandidateToApprovalReady();
    fireEvent.click(screen.getByRole("button", { name: /표 삭제/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/table-overlay?expected_revision=1",
        expect.objectContaining({
          method: "DELETE",
        }),
      );
    });
    await expectCandidateInvalidated();
    expect(screen.queryByRole("button", { name: /표 삭제/i })).not.toBeInTheDocument();
    expect(screen.getByText(/표 없음/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/표 텍스트/i)).toHaveValue("");
  });

  it("clears the saved tts replacement and invalidates the active candidate", async () => {
    const fetchMock = await renderStartedEditingSession(
      createFetchMock({ candidateReviewSnapshot: candidateReviewSnapshotResponse }),
    );

    fireEvent.change(screen.getByLabelText(/TTS 추천 ID/i), {
      target: { value: "rec_tts_002" },
    });
    fireEvent.change(screen.getByLabelText(/TTS 자산 ID/i), {
      target: { value: "tts_asset_002" },
    });
    fireEvent.click(screen.getByRole("button", { name: /TTS 저장/i }));

    await runCandidateToApprovalReady();
    fireEvent.click(screen.getByRole("button", { name: /TTS 해제/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/tts-replacement?expected_revision=1",
        expect.objectContaining({
          method: "DELETE",
        }),
      );
    });
    await expectCandidateInvalidated();
    expect(screen.queryByRole("button", { name: /TTS 해제/i })).not.toBeInTheDocument();
    expect(screen.getByText(/TTS 없음/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/TTS 추천 ID/i)).toHaveValue("");
    expect(screen.getByLabelText(/TTS 자산 ID/i)).toHaveValue("");
  });

  it("saves the music override, invalidates the active candidate, and exposes music in the rerun scope", async () => {
    const fetchMock = await renderStartedEditingSession(
      createFetchMock({ candidateReviewSnapshot: candidateReviewSnapshotResponse }),
    );

    await runCandidateToApprovalReady();

    fireEvent.change(screen.getByLabelText(/음악 자산 ID/i), {
      target: { value: "music_manual_002" },
    });
    fireEvent.click(screen.getByRole("button", { name: /음악 저장/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/music",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({
            expected_revision: 1,
            asset_id: "music_manual_002",
          }),
        }),
      );
    });
    await expectCandidateInvalidated();
    expect(screen.getByLabelText(/음악 자산 ID/i)).toHaveValue("music_manual_002");
    expect(screen.getByRole("checkbox", { name: /^음악$/i })).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: /사전 확인/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/partial-regeneration/preflight",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            segment_ids: ["seg_002"],
            fields: ["broll", "explanation_card", "music"],
          }),
        }),
      );
    });
  });

  it("defaults the editor focus to a later segment that only carries a saved music override", async () => {
    const musicOnlyEditingSession = {
      ...editingSessionResponse,
      segments: editingSessionResponse.segments.map((segment) =>
        segment.segment_id === "seg_002"
          ? {
              ...segment,
              broll_override: null,
              visual_overlays: [],
              music_override: { asset_id: "music_manual_001" },
              tts_replacement: null,
              review_required: false,
            }
          : {
              ...segment,
              broll_override: null,
              visual_overlays: [],
              music_override: null,
              tts_replacement: null,
              review_required: false,
            },
      ),
    };
    const fetchMock = createFetchMock({
      editingSession: musicOnlyEditingSession,
      latestEditingSession: musicOnlyEditingSession,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /편집 시작/i }));

    expect(await screen.findByText(/editing_session_001/i)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /대상 세그먼트/i })).toHaveValue("seg_002");
    expect(screen.getByLabelText(/음악 자산 ID/i)).toHaveValue("music_manual_001");
    expect(screen.getByRole("checkbox", { name: /^음악$/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /B롤/i })).not.toBeChecked();
  });

  it("maps a backend image_card overlay into the image overlay preflight field", async () => {
    const imageCardEditingSession = {
      ...editingSessionResponse,
      segments: editingSessionResponse.segments.map((segment) =>
        segment.segment_id === "seg_002"
          ? {
              ...segment,
              broll_override: null,
              visual_overlays: [
                {
                  overlay_type: "image_card",
                  asset_id: "asset_image_002",
                  text: "Saved backend image card",
                },
              ],
              music_override: null,
              tts_replacement: null,
              review_required: false,
            }
          : {
              ...segment,
              broll_override: null,
              visual_overlays: [],
              music_override: null,
              tts_replacement: null,
              review_required: false,
            },
      ),
    };
    const fetchMock = createFetchMock({
      editingSession: imageCardEditingSession,
      latestEditingSession: imageCardEditingSession,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /편집 시작/i }));

    expect(await screen.findByText(/editing_session_001/i)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /대상 세그먼트/i })).toHaveValue("seg_002");

    fireEvent.click(screen.getByRole("button", { name: /사전 확인/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/partial-regeneration/preflight",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            segment_ids: ["seg_002"],
            fields: ["image_overlay"],
          }),
        }),
      );
    });
  });

  it("maps a backend legacy image overlay into the image overlay preflight field", async () => {
    const legacyImageEditingSession = {
      ...editingSessionResponse,
      segments: editingSessionResponse.segments.map((segment) =>
        segment.segment_id === "seg_002"
          ? {
              ...segment,
              broll_override: null,
              visual_overlays: [
                {
                  overlay_type: "image",
                  asset_id: "asset_image_legacy_002",
                  text: "Saved legacy image overlay",
                },
              ],
              music_override: null,
              tts_replacement: null,
              review_required: false,
            }
          : {
              ...segment,
              broll_override: null,
              visual_overlays: [],
              music_override: null,
              tts_replacement: null,
              review_required: false,
            },
      ),
    };
    const fetchMock = createFetchMock({
      editingSession: legacyImageEditingSession,
      latestEditingSession: legacyImageEditingSession,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /편집 시작/i }));

    expect(await screen.findByText(/editing_session_001/i)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /대상 세그먼트/i })).toHaveValue("seg_002");

    fireEvent.click(screen.getByRole("button", { name: /사전 확인/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/partial-regeneration/preflight",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            segment_ids: ["seg_002"],
            fields: ["image_overlay"],
          }),
        }),
      );
    });
  });

  it("maps a backend hook_title overlay into the visual overlay preflight field", async () => {
    const hookTitleEditingSession = {
      ...editingSessionResponse,
      segments: editingSessionResponse.segments.map((segment) =>
        segment.segment_id === "seg_002"
          ? {
              ...segment,
              broll_override: null,
              visual_overlays: [
                {
                  overlay_type: "hook_title",
                  asset_id: "asset_hook_title_002",
                  text: "Saved legacy hook title overlay",
                },
              ],
              music_override: null,
              tts_replacement: null,
              review_required: false,
            }
          : {
              ...segment,
              broll_override: null,
              visual_overlays: [],
              music_override: null,
              tts_replacement: null,
              review_required: false,
            },
      ),
    };
    const fetchMock = createFetchMock({
      editingSession: hookTitleEditingSession,
      latestEditingSession: hookTitleEditingSession,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /편집 시작/i }));

    expect(await screen.findByText(/editing_session_001/i)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /대상 세그먼트/i })).toHaveValue("seg_002");

    fireEvent.click(screen.getByRole("button", { name: /사전 확인/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/partial-regeneration/preflight",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            segment_ids: ["seg_002"],
            fields: ["visual_overlay"],
          }),
        }),
      );
    });
  });

  it("maps a backend canonical visual_overlay into the visual overlay preflight field", async () => {
    const visualOverlayEditingSession = {
      ...editingSessionResponse,
      segments: editingSessionResponse.segments.map((segment) =>
        segment.segment_id === "seg_002"
          ? {
              ...segment,
              broll_override: null,
              visual_overlays: [
                {
                  overlay_type: "visual_overlay",
                  asset_id: "asset_visual_overlay_002",
                  text: "Saved canonical visual overlay",
                },
              ],
              music_override: null,
              tts_replacement: null,
              review_required: false,
            }
          : {
              ...segment,
              broll_override: null,
              visual_overlays: [],
              music_override: null,
              tts_replacement: null,
              review_required: false,
            },
      ),
    };
    const fetchMock = createFetchMock({
      editingSession: visualOverlayEditingSession,
      latestEditingSession: visualOverlayEditingSession,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /편집 시작/i }));

    expect(await screen.findByText(/editing_session_001/i)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /대상 세그먼트/i })).toHaveValue("seg_002");

    fireEvent.click(screen.getByRole("button", { name: /사전 확인/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/partial-regeneration/preflight",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            segment_ids: ["seg_002"],
            fields: ["visual_overlay"],
          }),
        }),
      );
    });
  });

  it("clears the saved music override and invalidates the active candidate", async () => {
    const musicPreflightResponse: PartialRegenerationPreflight = {
      ...partialRegenerationPreflightResponse,
      fields: ["broll", "explanation_card", "music"],
      downstream_steps: ["broll_refresh", "music_refresh", "overlay_refresh", "timeline_build"],
      affected_output_areas: [
        "b-roll track",
        "music bed",
        "visual overlays",
        "timeline preview",
        "subtitle render",
        "capcut export",
      ],
    };
    const musicResultResponse = {
      ...partialRegenerationResultResponse,
      fields: ["broll", "explanation_card", "music"],
      downstream_steps: ["broll_refresh", "music_refresh", "overlay_refresh", "timeline_build"],
      regenerated_segments: [
        {
          segment_id: "seg_002",
          changed_fields: ["broll", "explanation_card", "music"],
          output_changes: [
            "b-roll asset replaced with regenerated recommendation",
            "music bed replaced with manual override",
            "explanation card text refreshed",
          ],
        },
      ],
    };
    const fetchMock = await renderStartedEditingSession(
      createFetchMock({
        candidateReviewSnapshot: candidateReviewSnapshotResponse,
        partialRegenerationPreflight: musicPreflightResponse,
        partialRegenerationResult: musicResultResponse,
      }),
    );

    fireEvent.change(screen.getByLabelText(/음악 자산 ID/i), {
      target: { value: "music_manual_002" },
    });
    fireEvent.click(screen.getByRole("button", { name: /음악 저장/i }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /음악 해제/i })).toBeInTheDocument();
    });

    await runCandidateToApprovalReady();
    fireEvent.click(screen.getByRole("button", { name: /음악 해제/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/music?expected_revision=1",
        expect.objectContaining({
          method: "DELETE",
        }),
      );
    });
    await expectCandidateInvalidated();
    expect(screen.queryByRole("button", { name: /음악 해제/i })).not.toBeInTheDocument();
    expect(screen.getByLabelText(/음악 자산 ID/i)).toHaveValue("");
    expect(screen.getByRole("checkbox", { name: /^음악$/i })).not.toBeChecked();
  });

  it("clears the selected-range B-roll override from the ManualMediaLibrary and invalidates the active candidate", async () => {
    const fetchMock = await renderStartedEditingSession(
      createFetchMock({ candidateReviewSnapshot: candidateReviewSnapshotResponse }),
    );

    await runCandidateToApprovalReady();
    fireEvent.click(screen.getByRole("button", { name: /선택 구간 B롤 해제/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/broll?expected_revision=1",
        expect.objectContaining({
          method: "DELETE",
        }),
      );
    });
    await expectCandidateInvalidated();
    expect(screen.getByText(/B롤 해제됨/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /선택 구간 B롤 해제/i })).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /B롤/i })).not.toBeChecked();
  });

  it("blocks preflight and rerun while an editing save is still in flight", async () => {
    const baseFetch = createFetchMock();
    let resolveImageSave: ((response: Response) => void) | null = null;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (
        url.endsWith(
          "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/image-overlay",
        ) &&
        init?.method === "PATCH"
      ) {
        return new Promise<Response>((resolve) => {
          resolveImageSave = resolve;
        });
      }
      return baseFetch(input, init);
    });

    await renderStartedEditingSession(fetchMock);

    fireEvent.change(screen.getByLabelText(/이미지 자산 ID/i), {
      target: { value: "asset_image_002" },
    });
    fireEvent.click(screen.getByRole("button", { name: /이미지 저장/i }));

    const requestButton = screen.getByRole("button", {
      name: /사전 확인/i,
    });
    const runButton = screen.getByRole("button", { name: /부분 재생성/i });

    expect(requestButton).toBeDisabled();
    expect(runButton).toBeDisabled();

    fireEvent.click(requestButton);
    fireEvent.click(runButton);

    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/projects/project_001/editing-sessions/editing_session_001/partial-regeneration/preflight",
      expect.anything(),
    );
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/projects/project_001/editing-sessions/editing_session_001/partial-regeneration",
      expect.anything(),
    );

    const imageSaveResolver = resolveImageSave as unknown as (response: Response) => void;
    expect(imageSaveResolver).not.toBeNull();
    imageSaveResolver(
      new Response(
        JSON.stringify({
          ...editingSessionResponse,
          segments: editingSessionResponse.segments.map((segment) =>
            segment.segment_id === "seg_002"
              ? {
                  ...segment,
                  visual_overlays: [
                    ...segment.visual_overlays.filter(
                      (overlay) => String(overlay.overlay_type ?? "") !== "image_overlay",
                    ),
                    {
                      overlay_type: "image_overlay",
                      asset_id: "asset_image_002",
                      text: "",
                    },
                  ],
                }
              : segment,
          ),
        }),
      ),
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /사전 확인/i })).toBeEnabled();
    });
  });

  it("blocks preflight and rerun while a clear mutation is still in flight", async () => {
    const baseFetch = createFetchMock();
    let resolveTtsClear: ((response: Response) => void) | null = null;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (
        url.startsWith(
          "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/tts-replacement",
        ) &&
        init?.method === "DELETE"
      ) {
        return new Promise<Response>((resolve) => {
          resolveTtsClear = resolve;
        });
      }
      return baseFetch(input, init);
    });

    await renderStartedEditingSession(fetchMock);

    fireEvent.change(screen.getByLabelText(/TTS 추천 ID/i), {
      target: { value: "rec_tts_002" },
    });
    fireEvent.change(screen.getByLabelText(/TTS 자산 ID/i), {
      target: { value: "tts_asset_002" },
    });
    fireEvent.click(screen.getByRole("button", { name: /TTS 저장/i }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /TTS 해제/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /TTS 해제/i }));

    const requestButton = screen.getByRole("button", {
      name: /사전 확인/i,
    });
    const runButton = screen.getByRole("button", { name: /부분 재생성/i });

    expect(requestButton).toBeDisabled();
    expect(runButton).toBeDisabled();

    const ttsClearResolver = resolveTtsClear as unknown as (response: Response) => void;
    expect(ttsClearResolver).not.toBeNull();
    ttsClearResolver(
      new Response(
        JSON.stringify({
          ...editingSessionResponse,
          segments: editingSessionResponse.segments.map((segment) =>
            segment.segment_id === "seg_002"
              ? {
                  ...segment,
                  tts_replacement: null,
                }
              : segment,
          ),
        }),
      ),
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /사전 확인/i })).toBeEnabled();
    });
  });

  it("disables run again while a replacement preflight request is still in flight", async () => {
    const baseFetch = createFetchMock();
    const pendingPreflightResolvers: Array<(value: Response) => void> = [];
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (
        url.endsWith(
          "/api/projects/project_001/editing-sessions/editing_session_001/partial-regeneration/preflight",
        ) &&
        init?.method === "POST"
      ) {
        return new Promise<Response>((resolve) => {
          pendingPreflightResolvers.push(resolve);
        });
      }
      return baseFetch(input, init);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /편집 시작/i }));

    const requestButton = await screen.findByRole("button", {
      name: /사전 확인/i,
    });
    const runButton = screen.getByRole("button", { name: /부분 재생성/i });

    fireEvent.click(requestButton);
    expect(runButton).toBeDisabled();

    pendingPreflightResolvers.shift()?.(
      new Response(JSON.stringify(partialRegenerationPreflightResponse)),
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /부분 재생성/i })).toBeEnabled();
    });

    fireEvent.click(requestButton);
    expect(screen.getByRole("button", { name: /부분 재생성/i })).toBeDisabled();

    pendingPreflightResolvers.shift()?.(
      new Response(JSON.stringify(partialRegenerationPreflightResponse)),
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /부분 재생성/i })).toBeEnabled();
    });
  });

  it("rebases regeneration field selection when switching the target segment", async () => {
    const fetchMock = createFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /편집 시작/i }));

    expect(await screen.findByRole("button", { name: /seg_002/i })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /B롤/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /설명 카드/i })).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: /seg_001/i }));

    expect(screen.getByRole("checkbox", { name: /자막/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /B롤/i })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /설명 카드/i })).not.toBeChecked();
  });

  it("shows a blocked preflight warning before execution when the rerun preserves existing review blockers", async () => {
    const fetchMock = createFetchMock({
      editingSession: reviewRequiredEditingSessionResponse,
      partialRegenerationPreflight: blockedPartialRegenerationPreflightResponse,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /편집 시작/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /B롤/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /설명 카드/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /자막/i }));
    fireEvent.click(await screen.findByRole("button", { name: /사전 확인/i }));

    expect(await screen.findByText(/재검수 보류/i)).toBeInTheDocument();
    expect(
      screen.getByText(/기존 보류 유지/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/보류 · 확인 필요/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /부분 재생성/i })).toBeEnabled();
  });

  it("shows a timeline-centered editing shell with changed-vs-preserved context after partial regeneration", async () => {
    const fetchMock = createFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /편집 시작/i }));
    fireEvent.click(await screen.findByRole("button", { name: /사전 확인/i }));
    fireEvent.click(await screen.findByRole("button", { name: /부분 재생성/i }));

    expect(await screen.findByRole("heading", { name: /편집기/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /상세/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^트랙$/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^변경$/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /유지 영역/i })).toBeInTheDocument();

    expect(screen.getByText(/seg_002 변경/i)).toBeInTheDocument();
    expect(screen.getAllByText(/seg_001 유지/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/^변경 1$/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/유지 1/i)).toBeInTheDocument();

    expect(screen.getByText(/내레이션 트랙/i)).toBeInTheDocument();
    expect(screen.getByText(/B롤 트랙/i)).toBeInTheDocument();
    expect(screen.getByText(/화면 표시 트랙/i)).toBeInTheDocument();
    expect(screen.getByText(/asset_broll_regenerated_002/i)).toBeInTheDocument();
  });

  it("shows operator review decision guidance when changed segments are ready for sign-off", async () => {
    const fetchMock = createFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /편집 시작/i }));
    fireEvent.click(await screen.findByRole("button", { name: /사전 확인/i }));
    fireEvent.click(await screen.findByRole("button", { name: /부분 재생성/i }));

    expect(await screen.findByRole("heading", { name: /^판단$/i })).toBeInTheDocument();
    expect(screen.getByText(/준비 1/i)).toBeInTheDocument();
    expect(screen.getByText(/보류 0/i)).toBeInTheDocument();
    expect(screen.getByText(/seg_002 승인 준비/i)).toBeInTheDocument();
    expect(screen.getByText(/승인 가능/i)).toBeInTheDocument();
    expect(
      screen.getByText(/변경 출력 준비/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /타임라인 승인/i })).toBeEnabled();
    expect(screen.getAllByText(/seg_001 유지/i).length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/review-snapshots/partial_regeneration_job_001",
        undefined,
      );
    });
  });

  it("holds the decision loop when changed segments still require operator review", async () => {
    const fetchMock = createFetchMock({
      editingSession: reviewRequiredEditingSessionResponse,
      reviewSnapshot: reviewRequiredSnapshotResponse,
      candidateReviewSnapshot: reviewRequiredSnapshotResponse,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /편집 시작/i }));
    fireEvent.click(await screen.findByRole("button", { name: /사전 확인/i }));
    fireEvent.click(await screen.findByRole("button", { name: /부분 재생성/i }));

    expect(await screen.findByRole("heading", { name: /^판단$/i })).toBeInTheDocument();
    expect(screen.getByText(/준비 0/i)).toBeInTheDocument();
    expect(screen.getByText(/보류 1/i)).toBeInTheDocument();
    expect(screen.getByText(/seg_002 검수 필요/i)).toBeInTheDocument();
    expect(screen.getByText(/출력 보류/i)).toBeInTheDocument();
    expect(screen.getByText(/재생성 권장/i)).toBeInTheDocument();
    expect(screen.getAllByText(/seg_001 유지/i).length).toBeGreaterThan(0);
  });

  it("routes approval and output generation through the active partial-regeneration candidate", async () => {
    const fetchMock = createFetchMock({
      candidateReviewSnapshot: candidateReviewSnapshotResponse,
      jobs: {
        jobs: jobsResponse.jobs.filter(
          (job) =>
            job.job_type !== "preview_render" &&
            job.job_type !== "capcut_export" &&
            job.job_type !== "subtitle_render",
        ),
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /편집 시작/i }));
    fireEvent.click(await screen.findByRole("button", { name: /사전 확인/i }));
    fireEvent.click(await screen.findByRole("button", { name: /부분 재생성/i }));

    const approveButton = await screen.findByRole("button", { name: /타임라인 승인/i });
    await waitFor(() => {
      expect(approveButton).toBeEnabled();
    });

    fireEvent.click(approveButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/review-approvals/partial_regeneration_job_001/approve",
        expect.objectContaining({
          method: "POST",
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /자막 생성/i })).toBeEnabled();
    });

    fireEvent.click(screen.getByRole("button", { name: /자막 생성/i }));
    fireEvent.click(screen.getByRole("button", { name: /미리보기 생성/i }));
    fireEvent.click(screen.getByRole("button", { name: /캡컷 내보내기/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/jobs/subtitle-render",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            timeline_job_id: "partial_regeneration_job_001",
          }),
        }),
      );
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project_001/jobs/preview-render",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          timeline_job_id: "partial_regeneration_job_001",
        }),
      }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project_001/jobs/capcut-export",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          timeline_job_id: "partial_regeneration_job_001",
        }),
      }),
    );
  });

  it("invalidates the active candidate target after a new editing mutation", async () => {
    const fetchMock = createFetchMock({
      candidateReviewSnapshot: candidateReviewSnapshotResponse,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /편집 시작/i }));
    fireEvent.click(await screen.findByRole("button", { name: /사전 확인/i }));
    fireEvent.click(await screen.findByRole("button", { name: /부분 재생성/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /타임라인 승인/i })).toBeEnabled();
    });

    fireEvent.change(screen.getByDisplayValue("Team meeting overview"), {
      target: { value: "Team meeting overview refreshed" },
    });
    fireEvent.click(screen.getByRole("button", { name: /자막 저장/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/caption",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({
            expected_revision: 1,
            caption_text: "Team meeting overview refreshed",
          }),
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /타임라인 승인/i })).toBeDisabled();
    });
    expect(screen.queryByText(/partial_regeneration_job_001/i)).not.toBeInTheDocument();
  });

  it("resumes the latest editing session candidate after refresh when freshness is provable", async () => {
    const fetchMock = createFetchMock({
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/latest",
        undefined,
      );
    });
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/partial-regenerations/partial_regeneration_job_001",
        undefined,
      );
    });
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/partial-regeneration/preflight",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            segment_ids: ["seg_002"],
            fields: ["broll", "explanation_card"],
          }),
        }),
      );
    });

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/editing_session_001/i)).toBeInTheDocument();
    expect(await screen.findByText(/partial_regeneration_job_001/i)).toBeInTheDocument();
    expect(screen.getByText(/재생성 초안/i)).toBeInTheDocument();
    expect(
      screen.getByText(/초안 · 승인 필요/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/^재개 범위$/i)).toBeInTheDocument();
    expect(screen.getByText(/범위 1개/i)).toBeInTheDocument();
    expect(screen.getAllByText(/seg_002 포함/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/B롤 재개/i)).toBeInTheDocument();
    expect(screen.getByText(/설명 카드 재개/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /타임라인 승인/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /자막 생성/i })).toBeDisabled();
  });

  it("treats latest editing session 404 as a normal no-session case", async () => {
    const fetchMock = createFetchMock({
      latestEditingSession: null,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect((await screen.findAllByText(/편집 세션 없음/i)).length).toBeGreaterThan(0);
    expect(screen.queryByText(/편집 세션 복구 실패/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /편집 시작/i })).toBeEnabled();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/projects/project_001/partial-regenerations/partial_regeneration_job_001",
      undefined,
    );
  });

  it("shows a restore warning when latest editing session fetch fails with non-404 error", async () => {
    const fetchMock = createFetchMock({
      latestEditingSession: null,
      latestEditingSessionStatus: 500,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/편집 세션 복구 실패/i)).toBeInTheDocument();
    expect(screen.getByText(/기존 타임라인 유지/i)).toBeInTheDocument();
    expect(screen.getAllByText(/편집 세션 없음/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /편집 시작/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /자막 생성/i })).toBeEnabled();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/projects/project_001/partial-regenerations/partial_regeneration_job_001",
      undefined,
    );
  });

  it("clears the restore warning after the operator starts a fresh editing session", async () => {
    const fetchMock = createFetchMock({
      latestEditingSession: null,
      latestEditingSessionStatus: 500,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
    expect(await screen.findByText(/편집 세션 복구 실패/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /편집 시작/i }));

    expect(await screen.findByText(/editing_session_001/i)).toBeInTheDocument();
    expect(screen.queryByText(/편집 세션 복구 실패/i)).not.toBeInTheDocument();
  });

  it("shows a degraded resume warning when the resumed candidate result cannot be restored", async () => {
    const fetchMock = createFetchMock({
      candidateResultStatus: 500,
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/후보 복구 실패/i)).toBeInTheDocument();
    expect(screen.getByText(/기존 타임라인 유지/i)).toBeInTheDocument();
    expect(screen.queryByText(/partial_regeneration_job_001/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /자막 생성/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /검수 재개/i })).toBeEnabled();
  });

  it("shows a degraded resume warning when the resumed candidate review snapshot cannot be restored", async () => {
    const fetchMock = createFetchMock({
      candidateReviewStatus: 500,
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/후보 복구 실패/i)).toBeInTheDocument();
    expect(screen.getByText(/기존 타임라인 유지/i)).toBeInTheDocument();
    expect(screen.queryByText(/partial_regeneration_job_001/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /자막 생성/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /검수 재개/i })).toBeEnabled();
  });

  it("shows a limited restore warning when resumed preflight interpretation cannot be restored", async () => {
    const fetchMock = createFetchMock({
      candidatePreflightStatus: 500,
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/재개 범위 확인 · 검수 예측 없음/i)).toBeInTheDocument();
    expect(screen.getByText(/재개 범위 확인 · 검수 예측 없음/i)).toBeInTheDocument();
    expect(screen.getByText(/partial_regeneration_job_001/i)).toBeInTheDocument();
    expect(screen.getByText(/^재개 범위$/i)).toBeInTheDocument();
    expect(screen.getAllByText("미시작").length).toBeGreaterThan(0);
    expect(screen.getAllByText("대기").length).toBeGreaterThan(0);
    expect(screen.queryByText(/재생성 초안/i)).not.toBeInTheDocument();
  });

  it("clears resumed candidate restore warnings when the operator changes the rerun target", async () => {
    const fetchMock = createFetchMock({
      candidatePreflightStatus: 500,
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/재개 범위 확인 · 검수 예측 없음/i)).toBeInTheDocument();

    fireEvent.change(screen.getByRole("combobox", { name: /대상 세그먼트/i }), {
      target: { value: "seg_002" },
    });

    await waitFor(() => {
      expect(
        screen.queryByText(/재개 범위 확인 · 검수 예측 없음/i),
      ).not.toBeInTheDocument();
    });
  });

  it("clears resumed candidate restore warnings when the operator changes the rerun fields", async () => {
    const fetchMock = createFetchMock({
      candidatePreflightStatus: 500,
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/재개 범위 확인 · 검수 예측 없음/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("checkbox", { name: /자막/i }));

    await waitFor(() => {
      expect(
        screen.queryByText(/재개 범위 확인 · 검수 예측 없음/i),
      ).not.toBeInTheDocument();
    });
  });

  it("clears resumed candidate restore warnings when the operator reopens review", async () => {
    const fetchMock = createFetchMock({
      candidateReviewSnapshot: candidateApprovedReviewSnapshotResponse,
      candidatePreflightStatus: 500,
      partialRegenerationResult: {
        ...partialRegenerationResultResponse,
        timeline: {
          ...partialRegenerationResultResponse.timeline,
          review_status: "approved",
        },
      },
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/재개 범위 확인 · 검수 예측 없음/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /검수 재개/i }));

    await waitFor(() => {
      expect(
        screen.queryByText(/재개 범위 확인 · 검수 예측 없음/i),
      ).not.toBeInTheDocument();
    });
  });

  it("clears resumed candidate restore warnings when the operator approves the active candidate timeline", async () => {
    const fetchMock = createFetchMock({
      candidatePreflightStatus: 500,
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/재개 범위 확인 · 검수 예측 없음/i)).toBeInTheDocument();

    const approveButton = screen.getByRole("button", { name: /타임라인 승인/i });
    await waitFor(() => {
      expect(approveButton).toBeEnabled();
    });
    fireEvent.click(approveButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/review-approvals/partial_regeneration_job_001/approve",
        expect.objectContaining({
          method: "POST",
        }),
      );
    });
    await waitFor(() => {
      expect(
        screen.queryByText(/재개 범위 확인 · 검수 예측 없음/i),
      ).not.toBeInTheDocument();
    });
  });

  it("clears resumed candidate restore warnings when the operator requests a fresh preflight", async () => {
    const baseFetchMock = createFetchMock({
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    let preflightRequestCount = 0;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (
        url.endsWith(
          "/api/projects/project_001/editing-sessions/editing_session_001/partial-regeneration/preflight",
        ) &&
        init?.method === "POST"
      ) {
        preflightRequestCount += 1;
        if (preflightRequestCount === 1) {
          return Promise.resolve(new Response("candidate preflight error", { status: 500 }));
        }
      }
      return baseFetchMock(input, init);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/재개 범위 확인 · 검수 예측 없음/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /사전 확인/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/partial-regeneration/preflight",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            segment_ids: ["seg_002"],
            fields: ["broll", "explanation_card"],
          }),
        }),
      );
    });
    await waitFor(() => {
      expect(
        screen.queryByText(/재개 범위 확인 · 검수 예측 없음/i),
      ).not.toBeInTheDocument();
    });
    expect(await screen.findByText(/재생성 초안/i)).toBeInTheDocument();
  });

  it("reuses blocked preflight interpretation on refresh-resume for the latest fresh candidate", async () => {
    const fetchMock = createFetchMock({
      editingSession: reviewRequiredEditingSessionResponse,
      latestEditingSession: reviewRequiredEditingSessionResponse,
      partialRegenerationPreflight: blockedPartialRegenerationPreflightResponse,
      partialRegenerationResult: {
        ...partialRegenerationResultResponse,
        fields: ["caption"],
        downstream_steps: ["segment_refresh", "timeline_build"],
      },
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/partial-regeneration/preflight",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            segment_ids: ["seg_002"],
            fields: ["caption"],
          }),
        }),
      );
    });

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/partial_regeneration_job_001/i)).toBeInTheDocument();
    expect(screen.getByText(/재검수 보류/i)).toBeInTheDocument();
    expect(
      screen.getByText(/기존 보류 유지/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/보류 · 확인 필요/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /타임라인 승인/i })).toBeEnabled();
  });

  it("aligns the selected rerun scope with the resumed candidate before reusing preflight interpretation", async () => {
    const fetchMock = createFetchMock({
      partialRegenerationPreflight: {
        ...partialRegenerationPreflightResponse,
        fields: ["caption"],
        downstream_steps: ["segment_refresh", "timeline_build"],
        affected_output_areas: [
          "segment copy",
          "timeline preview",
          "subtitle render",
          "capcut export",
        ],
      },
      partialRegenerationResult: {
        ...partialRegenerationResultResponse,
        fields: ["caption"],
        downstream_steps: ["segment_refresh", "timeline_build"],
      },
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/partial_regeneration_job_001/i)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /자막/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /B롤/i })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /설명 카드/i })).not.toBeChecked();
  });

  it("does not reuse resumed preflight interpretation when the restored preflight scope differs from the resumed candidate", async () => {
    const fetchMock = createFetchMock({
      partialRegenerationPreflight: {
        ...partialRegenerationPreflightResponse,
        segment_ids: ["seg_001"],
        fields: ["caption"],
        downstream_steps: ["segment_refresh", "timeline_build"],
        targeted_segments: [editingSessionResponse.segments[0]],
        affected_output_areas: [
          "segment copy",
          "timeline preview",
          "subtitle render",
          "capcut export",
        ],
      },
      partialRegenerationResult: {
        ...partialRegenerationResultResponse,
        segment_ids: ["seg_002"],
        fields: ["broll", "explanation_card"],
      },
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/partial_regeneration_job_001/i)).toBeInTheDocument();
    expect(
      screen.getByText(/재개 범위 확인 · 검수 예측 없음/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/재개 범위 확인 · 검수 예측 없음/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/재생성 초안/i)).not.toBeInTheDocument();
    expect(screen.getByText(/^재개 범위$/i)).toBeInTheDocument();
    expect(screen.getByText(/seg_002 포함/i)).toBeInTheDocument();
    expect(screen.getByText(/B롤 재개/i)).toBeInTheDocument();
    expect(screen.getByText(/설명 카드 재개/i)).toBeInTheDocument();
  });

  it("does not reuse resumed preflight interpretation when the restored preflight session_id differs from the resumed candidate session", async () => {
    const fetchMock = createFetchMock({
      partialRegenerationPreflight: {
        ...partialRegenerationPreflightResponse,
        session_id: "editing_session_999",
        segment_ids: ["seg_002"],
        fields: ["broll", "explanation_card"],
      },
      partialRegenerationResult: {
        ...partialRegenerationResultResponse,
        session_id: "editing_session_001",
        segment_ids: ["seg_002"],
        fields: ["broll", "explanation_card"],
      },
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/partial_regeneration_job_001/i)).toBeInTheDocument();
    expect(
      screen.getByText(/재개 범위 확인 · 검수 예측 없음/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/재개 범위 확인 · 검수 예측 없음/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/재생성 초안/i)).not.toBeInTheDocument();
    expect(screen.getByText(/^재개 범위$/i)).toBeInTheDocument();
    expect(screen.getByText(/seg_002 포함/i)).toBeInTheDocument();
    expect(screen.getByText(/B롤 재개/i)).toBeInTheDocument();
    expect(screen.getByText(/설명 카드 재개/i)).toBeInTheDocument();
  });

  it("does not reuse resumed preflight interpretation when the restored preflight fields include duplicates", async () => {
    const fetchMock = createFetchMock({
      partialRegenerationPreflight: {
        ...partialRegenerationPreflightResponse,
        segment_ids: ["seg_002"],
        fields: ["broll", "explanation_card", "broll"],
      },
      partialRegenerationResult: {
        ...partialRegenerationResultResponse,
        session_id: "editing_session_001",
        segment_ids: ["seg_002"],
        fields: ["broll", "explanation_card"],
      },
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/partial_regeneration_job_001/i)).toBeInTheDocument();
    expect(
      screen.getByText(/재개 범위 확인 · 검수 예측 없음/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/재개 범위 확인 · 검수 예측 없음/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/재생성 초안/i)).not.toBeInTheDocument();
    expect(screen.getByText(/^재개 범위$/i)).toBeInTheDocument();
    expect(screen.getByText(/seg_002 포함/i)).toBeInTheDocument();
    expect(screen.getByText(/B롤 재개/i)).toBeInTheDocument();
    expect(screen.getByText(/설명 카드 재개/i)).toBeInTheDocument();
  });

  it("does not reuse resumed preflight interpretation when restored targeted segments differ from the resumed candidate scope", async () => {
    const fetchMock = createFetchMock({
      partialRegenerationPreflight: {
        ...partialRegenerationPreflightResponse,
        session_id: "editing_session_001",
        segment_ids: ["seg_002"],
        fields: ["broll", "explanation_card"],
        targeted_segments: [editingSessionResponse.segments[0]],
      },
      partialRegenerationResult: {
        ...partialRegenerationResultResponse,
        session_id: "editing_session_001",
        segment_ids: ["seg_002"],
        fields: ["broll", "explanation_card"],
      },
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/partial_regeneration_job_001/i)).toBeInTheDocument();
    expect(
      screen.getByText(/재개 범위 확인 · 검수 예측 없음/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/재개 범위 확인 · 검수 예측 없음/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/재생성 초안/i)).not.toBeInTheDocument();
    expect(screen.getByText(/^재개 범위$/i)).toBeInTheDocument();
    expect(screen.getByText(/seg_002 포함/i)).toBeInTheDocument();
    expect(screen.getByText(/B롤 재개/i)).toBeInTheDocument();
    expect(screen.getByText(/설명 카드 재개/i)).toBeInTheDocument();
  });

  it("does not reuse resumed preflight interpretation when restored targeted segment review state differs from the editing session", async () => {
    const fetchMock = createFetchMock({
      partialRegenerationPreflight: {
        ...partialRegenerationPreflightResponse,
        session_id: "editing_session_001",
        segment_ids: ["seg_002"],
        fields: ["broll", "explanation_card"],
        targeted_segments: [
          {
            ...editingSessionResponse.segments[1],
            review_required: true,
          },
        ],
      },
      partialRegenerationResult: {
        ...partialRegenerationResultResponse,
        session_id: "editing_session_001",
        segment_ids: ["seg_002"],
        fields: ["broll", "explanation_card"],
      },
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/partial_regeneration_job_001/i)).toBeInTheDocument();
    expect(
      screen.getByText(/재개 범위 확인 · 검수 예측 없음/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/재개 범위 확인 · 검수 예측 없음/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/재생성 초안/i)).not.toBeInTheDocument();
    expect(screen.getByText(/^재개 범위$/i)).toBeInTheDocument();
    expect(screen.getByText(/seg_002 포함/i)).toBeInTheDocument();
    expect(screen.getByText(/B롤 재개/i)).toBeInTheDocument();
    expect(screen.getByText(/설명 카드 재개/i)).toBeInTheDocument();
  });

  it("does not reuse resumed preflight interpretation when restored targeted segment tts replacement differs from the editing session", async () => {
    const fetchMock = createFetchMock({
      partialRegenerationPreflight: {
        ...partialRegenerationPreflightResponse,
        session_id: "editing_session_001",
        segment_ids: ["seg_002"],
        fields: ["broll", "explanation_card"],
        targeted_segments: [
          {
            ...editingSessionResponse.segments[1],
            tts_replacement: {
              recommendation_id: "rec_tts_seg_002",
              asset_id: "asset_tts_002",
            },
          },
        ],
      },
      partialRegenerationResult: {
        ...partialRegenerationResultResponse,
        session_id: "editing_session_001",
        segment_ids: ["seg_002"],
        fields: ["broll", "explanation_card"],
      },
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/partial_regeneration_job_001/i)).toBeInTheDocument();
    expect(
      screen.getByText(/재개 범위 확인 · 검수 예측 없음/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/재개 범위 확인 · 검수 예측 없음/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/재생성 초안/i)).not.toBeInTheDocument();
    expect(screen.getByText(/^재개 범위$/i)).toBeInTheDocument();
    expect(screen.getByText(/seg_002 포함/i)).toBeInTheDocument();
    expect(screen.getByText(/B롤 재개/i)).toBeInTheDocument();
    expect(screen.getByText(/설명 카드 재개/i)).toBeInTheDocument();
  });

  it("does not reuse resumed preflight interpretation when restored targeted segment visual overlays differ from the editing session", async () => {
    const fetchMock = createFetchMock({
      partialRegenerationPreflight: {
        ...partialRegenerationPreflightResponse,
        session_id: "editing_session_001",
        segment_ids: ["seg_002"],
        fields: ["broll", "explanation_card"],
        targeted_segments: [
          {
            ...editingSessionResponse.segments[1],
            visual_overlays: [
              {
                overlay_type: "explanation_card",
                title: "Restored mismatch",
                body: "Different overlay state",
                text: "Restored mismatch: Different overlay state",
              },
            ],
          },
        ],
      },
      partialRegenerationResult: {
        ...partialRegenerationResultResponse,
        session_id: "editing_session_001",
        segment_ids: ["seg_002"],
        fields: ["broll", "explanation_card"],
      },
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/partial_regeneration_job_001/i)).toBeInTheDocument();
    expect(
      screen.getByText(/재개 범위 확인 · 검수 예측 없음/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/재개 범위 확인 · 검수 예측 없음/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/재생성 초안/i)).not.toBeInTheDocument();
    expect(screen.getByText(/^재개 범위$/i)).toBeInTheDocument();
    expect(screen.getByText(/seg_002 포함/i)).toBeInTheDocument();
    expect(screen.getByText(/B롤 재개/i)).toBeInTheDocument();
    expect(screen.getByText(/설명 카드 재개/i)).toBeInTheDocument();
  });

  it("does not reuse resumed preflight interpretation when restored targeted segment broll override differs from the editing session", async () => {
    const fetchMock = createFetchMock({
      partialRegenerationPreflight: {
        ...partialRegenerationPreflightResponse,
        session_id: "editing_session_001",
        segment_ids: ["seg_002"],
        fields: ["broll", "explanation_card"],
        targeted_segments: [
          {
            ...editingSessionResponse.segments[1],
            broll_override: {
              asset_id: "asset_broll_restored_mismatch_002",
            },
          },
        ],
      },
      partialRegenerationResult: {
        ...partialRegenerationResultResponse,
        session_id: "editing_session_001",
        segment_ids: ["seg_002"],
        fields: ["broll", "explanation_card"],
      },
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/partial_regeneration_job_001/i)).toBeInTheDocument();
    expect(
      screen.getByText(/재개 범위 확인 · 검수 예측 없음/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/재개 범위 확인 · 검수 예측 없음/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/재생성 초안/i)).not.toBeInTheDocument();
    expect(screen.getByText(/^재개 범위$/i)).toBeInTheDocument();
    expect(screen.getByText(/seg_002 포함/i)).toBeInTheDocument();
    expect(screen.getByText(/B롤 재개/i)).toBeInTheDocument();
    expect(screen.getByText(/설명 카드 재개/i)).toBeInTheDocument();
  });

  it("does not reuse resumed preflight interpretation when restored targeted segment music override differs from the editing session", async () => {
    const fetchMock = createFetchMock({
      partialRegenerationPreflight: {
        ...partialRegenerationPreflightResponse,
        session_id: "editing_session_001",
        segment_ids: ["seg_002"],
        fields: ["music", "explanation_card"],
        targeted_segments: [
          {
            ...editingSessionResponse.segments[1],
            music_override: {
              asset_id: "asset_music_restored_mismatch_002",
            },
          },
        ],
      },
      partialRegenerationResult: {
        ...partialRegenerationResultResponse,
        session_id: "editing_session_001",
        segment_ids: ["seg_002"],
        fields: ["music", "explanation_card"],
      },
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/partial_regeneration_job_001/i)).toBeInTheDocument();
    expect(
      screen.getByText(/재개 범위 확인 · 검수 예측 없음/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/재개 범위 확인 · 검수 예측 없음/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/재생성 초안/i)).not.toBeInTheDocument();
    expect(screen.getByText(/^재개 범위$/i)).toBeInTheDocument();
    expect(screen.getByText(/seg_002 포함/i)).toBeInTheDocument();
    expect(screen.getByText(/음악 재개/i)).toBeInTheDocument();
    expect(screen.getByText(/설명 카드 재개/i)).toBeInTheDocument();
  });

  it("does not reuse preflight interpretation for a resumed multi-segment candidate that the current editor cannot represent", async () => {
    const fetchMock = createFetchMock({
      partialRegenerationResult: {
        ...partialRegenerationResultResponse,
        segment_ids: ["seg_001", "seg_002"],
        fields: ["caption", "broll"],
      },
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/partial-regenerations/partial_regeneration_job_001",
        undefined,
      );
    });

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/partial_regeneration_job_001/i)).toBeInTheDocument();
    expect(screen.getByText(/^재개 범위$/i)).toBeInTheDocument();
    expect(screen.getByText(/범위 2개/i)).toBeInTheDocument();
    expect(screen.getByText(/seg_001 포함/i)).toBeInTheDocument();
    expect(screen.getByText(/seg_002 포함/i)).toBeInTheDocument();
    expect(screen.getByText(/자막 재개/i)).toBeInTheDocument();
    expect(screen.getByText(/B롤 재개/i)).toBeInTheDocument();
    expect(screen.getByText(/다중 세그먼트 · 수동 확인/i)).toBeInTheDocument();
    expect(
      fetchMock,
    ).not.toHaveBeenCalledWith(
      "/api/projects/project_001/editing-sessions/editing_session_001/partial-regeneration/preflight",
      expect.anything(),
    );
    expect(screen.queryByText(/재생성 초안/i)).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /자막/i })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /B롤/i })).toBeChecked();
  });

  it("clears resumed multi-segment scope when the operator changes the rerun target", async () => {
    const fetchMock = createFetchMock({
      partialRegenerationResult: {
        ...partialRegenerationResultResponse,
        segment_ids: ["seg_001", "seg_002"],
        fields: ["caption", "broll"],
      },
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/partial_regeneration_job_001/i)).toBeInTheDocument();
    expect(screen.getByText(/범위 2개/i)).toBeInTheDocument();
    expect(screen.getByText(/다중 세그먼트 · 수동 확인/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /seg_001/i }));

    await waitFor(() => {
      expect(screen.queryByText(/partial_regeneration_job_001/i)).not.toBeInTheDocument();
    });
    expect(screen.queryByText(/범위 2개/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/다중 세그먼트 · 수동 확인/i),
    ).not.toBeInTheDocument();
  });

  it("clears resumed multi-segment scope when the operator changes the rerun fields", async () => {
    const fetchMock = createFetchMock({
      partialRegenerationResult: {
        ...partialRegenerationResultResponse,
        segment_ids: ["seg_001", "seg_002"],
        fields: ["caption", "broll"],
      },
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/partial_regeneration_job_001/i)).toBeInTheDocument();
    expect(screen.getByText(/범위 2개/i)).toBeInTheDocument();
    expect(screen.getByText(/다중 세그먼트 · 수동 확인/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("checkbox", { name: /자막/i }));

    await waitFor(() => {
      expect(screen.queryByText(/partial_regeneration_job_001/i)).not.toBeInTheDocument();
    });
    expect(screen.queryByText(/범위 2개/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/다중 세그먼트 · 수동 확인/i),
    ).not.toBeInTheDocument();
  });

  it("falls back to the stable timeline when the latest candidate freshness is no longer provable", async () => {
    const fetchMock = createFetchMock({
      latestEditingSession: {
        ...editingSessionResponse,
        timeline_id: "timeline_002",
        updated_at: "2026-06-28T00:00:20Z",
      },
      jobs: {
        jobs: [
          ...jobsResponse.jobs,
          {
            job_id: "partial_regeneration_job_001",
            job_type: "partial_regeneration",
            status: "succeeded",
            input_ref: "editing_session_001",
            output_ref: "partial_regeneration_run_001",
            error_message: null,
            started_at: "2026-06-28T00:00:16Z",
            finished_at: "2026-06-28T00:00:17Z",
          },
        ],
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/latest",
        undefined,
      );
    });

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/editing_session_001/i)).toBeInTheDocument();
    expect(screen.queryByText(/partial_regeneration_job_001/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /타임라인 승인/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /자막 생성/i })).toBeEnabled();
  });

  it("reopens narration and script ingest for the selected project after a refresh", async () => {
    vi.stubGlobal("fetch", createFetchMock());

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "소스 등록" }));

    expect(await screen.findByRole("heading", { name: "기존 프로젝트 소스 등록" })).toBeInTheDocument();
    expect(screen.getByLabelText("나레이션 로컬 경로")).toBeInTheDocument();
    expect(screen.getByLabelText("스크립트 로컬 경로")).toBeInTheDocument();
  });

  it("shows the fixed five-track timeline controls after restoring an editing session", async () => {
    vi.stubGlobal("fetch", createFetchMock());
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByRole("heading", { name: "고정 트랙 타임라인" })).toBeInTheDocument();
    expect(screen.getByText("나레이션")).toBeInTheDocument();
    expect(screen.getAllByText("B롤").length).toBeGreaterThan(0);
    expect(screen.getAllByText("BGM").length).toBeGreaterThan(0);
    expect(screen.getAllByText("SFX").length).toBeGreaterThan(0);
    expect(screen.getAllByText("오버레이").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "분할" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "실행 취소" })).toBeInTheDocument();
  });

  it("separates verified BGM and SFX library items, previews without mutation, persists favorites, and materializes before applying", async () => {
    const fetchMock = createFetchMock({
      mediaLibraryAssets: [
        {
          library_asset_id: "pack:starter-001:music-001",
          asset_id: "music-001",
          media_type: "music",
          duration_seconds: 12.5,
          version: "1.0.0",
          verified: true,
          available: true,
          tags: ["calm", "office"],
          source: "Synthetic source",
          creator: "Synthetic creator",
          official_license_url: "https://example.test/license",
          attribution_required: true,
          attribution_text: "Music by Synthetic creator",
        },
        {
          library_asset_id: "pack:starter-001:sfx-missing",
          asset_id: "sfx-missing",
          media_type: "sfx",
          duration_seconds: 1,
          version: "1.0.0",
          verified: false,
          available: false,
          tags: ["impact"],
          source: "Synthetic source",
          creator: "Synthetic creator",
          official_license_url: "https://example.test/license",
        },
      ],
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
    expect(await screen.findByRole("heading", { name: "BGM 라이브러리" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "SFX 라이브러리" })).toBeInTheDocument();
    expect(screen.getByText("설치된 검증 미디어 2개")).toBeInTheDocument();
    expect(screen.getByText("Starter pack 설치됨")).toBeInTheDocument();
    expect(screen.getByText(/Synthetic creator · 1.0.0 · 12.5초/i)).toBeInTheDocument();
    expect(screen.getByText(/표기 필요: Music by Synthetic creator/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "SFX 적용" })).toBeDisabled();

    const search = screen.getByPlaceholderText("BGM, SFX, 태그 또는 길이");
    fireEvent.change(search, { target: { value: "BGM" } });
    expect(screen.getByText("music-001")).toBeInTheDocument();
    expect(screen.queryByText("sfx-missing")).not.toBeInTheDocument();
    fireEvent.change(search, { target: { value: "calm" } });
    expect(screen.getByText("music-001")).toBeInTheDocument();
    fireEvent.change(search, { target: { value: "12.5" } });
    expect(screen.getByText("music-001")).toBeInTheDocument();
    fireEvent.change(search, { target: { value: "" } });

    fireEvent.click(screen.getByRole("button", { name: "BGM 미리보기" }));
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringMatching(/materialize|\/music$/),
      expect.anything(),
    );
    expect(screen.getByText(/미리보기 선택됨/i)).toBeInTheDocument();
    expect(screen.getByTestId("media-library-preview")).toHaveAttribute(
      "src",
      "/api/media-library/assets/pack%3Astarter-001%3Amusic-001/preview",
    );

    fireEvent.click(screen.getByRole("button", { name: "BGM 즐겨찾기" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project_001/media-library/assets/pack%3Astarter-001%3Amusic-001/favorite",
      expect.objectContaining({ method: "PUT" }),
    ));
    fireEvent.click(screen.getByRole("button", { name: "즐겨찾기" }));
    expect(screen.getByText("music-001")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "BGM 적용" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/media-library/assets/pack%3Astarter-001%3Amusic-001/materialize",
        expect.objectContaining({ method: "POST", body: JSON.stringify({ project_id: "project_001" }) }),
      );
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/music",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ expected_revision: 1, asset_id: "asset_materialized_music_001" }),
        }),
      );
    });
    fireEvent.click(screen.getByRole("button", { name: "최근" }));
    expect(screen.getByText("music-001")).toBeInTheDocument();
  });

  it("keeps the restored editor usable when the global media library is unavailable", async () => {
    vi.stubGlobal("fetch", createFetchMock({ mediaLibraryUnavailable: true }));
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));

    expect(await screen.findByText(/미디어 라이브러리를 사용할 수 없습니다/i)).toBeInTheDocument();
    expect(screen.getByText("editing_session_001")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "분할" })).toBeEnabled();
  });

  it("restores media favorites and recent usage from the active project after an app reload", async () => {
    const fetchMock = createFetchMock({
      mediaLibraryAssets: [{
        library_asset_id: "pack:starter-001:music-001",
        asset_id: "music-001",
        media_type: "music",
        duration_seconds: 12.5,
        version: "1.0.0",
        verified: true,
        available: true,
        tags: ["calm"],
        source: "Synthetic source",
        creator: "Synthetic creator",
        official_license_url: "https://example.test/license",
        attribution_required: false,
        attribution_text: "",
      }],
    });
    vi.stubGlobal("fetch", fetchMock);
    const firstRender = render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
    fireEvent.click(await screen.findByRole("button", { name: "BGM 즐겨찾기" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project_001/media-library/assets/pack%3Astarter-001%3Amusic-001/favorite",
      expect.objectContaining({ method: "PUT" }),
    ));
    fireEvent.click(screen.getByRole("button", { name: "BGM 적용" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/media-library/assets/pack%3Astarter-001%3Amusic-001/materialize",
      expect.objectContaining({ method: "POST" }),
    ));

    firstRender.unmount();
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /^편집$/i }));
    await screen.findByRole("button", { name: "즐겨찾기" });

    await waitFor(() => expect(fetchMock.mock.calls.filter(([url, init]) =>
      String(url).endsWith("/api/projects/project_001/media-library/favorites") && !init,
    )).toHaveLength(2));
    await waitFor(() => expect(fetchMock.mock.calls.filter(([url, init]) =>
      String(url).endsWith("/api/projects/project_001/media-library/recent") && !init,
    )).toHaveLength(3));
    fireEvent.click(screen.getByRole("button", { name: "즐겨찾기" }));
    expect(screen.getByText("music-001")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "최근" }));
    expect(screen.getByText("music-001")).toBeInTheDocument();
  });
});
