import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { App } from "./App";
import type { ReviewSnapshot } from "./api";

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

const jobsResponse = {
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

const partialRegenerationPreflightResponse = {
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

function createFetchMock({
  geminiKeys = geminiKeysResponse,
  editingSession = editingSessionResponse,
  latestEditingSession = editingSessionResponse,
  reviewSnapshot = reviewSnapshotResponse,
  candidateReviewSnapshot = candidateReviewSnapshotResponse,
  partialRegenerationResult = partialRegenerationResultResponse,
  jobs = jobsResponse,
}: {
  geminiKeys?: { keys: Array<Record<string, unknown>> };
  editingSession?: typeof editingSessionResponse;
  latestEditingSession?: typeof editingSessionResponse | null;
  reviewSnapshot?: typeof reviewSnapshotResponse;
  candidateReviewSnapshot?: ReviewSnapshot;
  partialRegenerationResult?: typeof partialRegenerationResultResponse;
  jobs?: typeof jobsResponse;
} = {}) {
  const state = {
    editingSession: structuredClone(editingSession),
    geminiKeys: structuredClone(geminiKeys),
    candidateReviewSnapshot: structuredClone(candidateReviewSnapshot),
    candidateTimelineReviewStatus: partialRegenerationResult.timeline.review_status,
  };

  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
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
    if (url.endsWith("/api/projects/project_001/timelines/timeline_build_job_005")) {
      return new Response(JSON.stringify(timelineResponse));
    }
    if (url.endsWith("/api/projects/project_001/timelines/partial_regeneration_job_001")) {
      return new Response(
        JSON.stringify({
          ...partialRegenerationResultResponse,
          timeline: {
            ...partialRegenerationResultResponse.timeline,
            review_status: state.candidateTimelineReviewStatus,
          },
        }),
      );
    }
    if (url.endsWith("/api/projects/project_001/review-snapshots/timeline_build_job_005")) {
      return new Response(JSON.stringify(reviewSnapshot));
    }
    if (url.endsWith("/api/projects/project_001/review-snapshots/partial_regeneration_job_001")) {
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
      if (latestEditingSession == null) {
        return new Response("not found", { status: 404 });
      }
      return new Response(JSON.stringify(latestEditingSession));
    }
    if (
      url.endsWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/caption",
      ) &&
      init?.method === "PATCH"
    ) {
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
        "/api/projects/project_001/editing-sessions/editing_session_001/partial-regeneration/preflight",
      ) &&
      init?.method === "POST"
    ) {
      return new Response(JSON.stringify(partialRegenerationPreflightResponse));
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

describe("App", () => {
  it("renders a local-first operator dashboard from API data", async () => {
    const fetchMock = createFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: /videobox operator dashboard/i }),
    ).toBeInTheDocument();
    expect(await screen.findByText(/operator review demo/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /timeline summary/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /review snapshot/i })).toBeInTheDocument();
    expect((await screen.findAllByText(/preview_render_job_006/i)).length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/capcut_export_job_007/i)).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /review snapshot/i }));

    expect(await screen.findByText(/applied and pending recommendations/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /approve recommendation/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reject recommendation/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /mark for manual edit/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /rebuild timeline draft/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/jobs/build-timeline",
        expect.objectContaining({
          method: "POST",
        }),
      );
    });

    expect(await screen.findByRole("button", { name: /reopen review/i })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /generate subtitle file/i }));
    fireEvent.click(await screen.findByRole("button", { name: /render preview artifact/i }));
    fireEvent.click(await screen.findByRole("button", { name: /export capcut payload/i }));

    expect(await screen.findByText(/playable_html_preview/i)).toBeInTheDocument();
    expect(await screen.findAllByText(/subtitle_001\.srt/i)).toHaveLength(2);
    expect(await screen.findByText(/mock capcut payload written/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/projects", undefined);
    });
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
        (job) => job.job_type !== "preview_render" && job.job_type !== "capcut_export",
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
      await screen.findByRole("button", { name: /approve timeline/i }),
    ).toBeDisabled();
    expect(
      await screen.findByRole("button", { name: /render preview artifact/i }),
    ).toBeDisabled();
    expect(
      await screen.findByRole("button", { name: /export capcut payload/i }),
    ).toBeDisabled();
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
      expect(screen.getByRole("button", { name: /approve timeline/i })).toBeEnabled();
    });
    expect(
      await screen.findByRole("button", { name: /generate subtitle file/i }),
    ).toBeDisabled();
    expect(
      await screen.findByRole("button", { name: /render preview artifact/i }),
    ).toBeDisabled();
    expect(
      await screen.findByRole("button", { name: /export capcut payload/i }),
    ).toBeDisabled();
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

    const subtitleCard = (await screen.findByText("Subtitle render")).closest("article");
    const previewCard = (await screen.findByText("Preview render")).closest("article");
    const exportCard = (await screen.findByText("CapCut export")).closest("article");

    expect(subtitleCard).not.toBeNull();
    expect(previewCard).not.toBeNull();
    expect(exportCard).not.toBeNull();

    expect(within(subtitleCard!).getByText("pending")).toBeInTheDocument();
    expect(within(subtitleCard!).getByText("not-started")).toBeInTheDocument();
    expect(within(previewCard!).getByText("pending")).toBeInTheDocument();
    expect(within(previewCard!).getByText("not-started")).toBeInTheDocument();
    expect(within(exportCard!).getByText("pending")).toBeInTheDocument();
    expect(within(exportCard!).getByText("not-started")).toBeInTheDocument();
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

    expect(await screen.findByText(/operator review demo/i)).toBeInTheDocument();
    expect(await screen.findByText(/timeline_001/i)).toBeInTheDocument();
    expect(await screen.findByText(/gemini routing state unavailable/i)).toBeInTheDocument();
    expect(screen.queryByText(/request failed: \/api\/projects\/project_001\/providers\/gemini\/keys/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/no gemini routing keys configured for this project/i)).not.toBeInTheDocument();
  });

  it("renders masked Gemini keys with routing state visibility and never leaks raw secrets", async () => {
    const fetchMock = createFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByRole("heading", { name: /gemini provider keys/i })).toBeInTheDocument();
    expect(await screen.findByText(/primary routing key/i)).toBeInTheDocument();
    expect(await screen.findByText("AIza...1234")).toBeInTheDocument();
    expect(await screen.findByText(/fallback cooldown key/i)).toBeInTheDocument();
    expect(await screen.findByText(/429 quota exceeded/i)).toBeInTheDocument();
    expect(await screen.findByText(/2026-06-28T00:05:00Z/i)).toBeInTheDocument();
    expect(screen.getAllByText(/consecutive failures/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/AIzaSyDANGER_SECRET/i)).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue(/AIzaSyDANGER_SECRET/i)).not.toBeInTheDocument();
  });

  it("creates, updates, disables, and re-enables Gemini keys while refreshing the dashboard state", async () => {
    const fetchMock = createFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByRole("heading", { name: /gemini provider keys/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /add gemini key/i }));
    fireEvent.change(screen.getByLabelText(/label/i), {
      target: { value: "Burst quota key" },
    });
    fireEvent.change(screen.getByLabelText(/api key/i), {
      target: { value: "AIzaSyDANGER_SECRET" },
    });
    fireEvent.change(screen.getByLabelText(/primary model/i), {
      target: { value: "gemini-2.5-flash" },
    });
    fireEvent.change(screen.getByLabelText(/cheap model/i), {
      target: { value: "gemini-2.5-flash-lite" },
    });
    fireEvent.change(screen.getByLabelText(/high quality model/i), {
      target: { value: "gemini-2.5-pro" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save gemini key/i }));

    expect(await screen.findByText(/burst quota key/i)).toBeInTheDocument();
    expect(screen.getByText("AIza...9999")).toBeInTheDocument();
    expect(screen.queryByText(/AIzaSyDANGER_SECRET/i)).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue(/AIzaSyDANGER_SECRET/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /edit primary routing key/i }));
    fireEvent.change(screen.getByLabelText(/label/i), {
      target: { value: "Primary routing key v2" },
    });
    fireEvent.change(screen.getByLabelText(/cheap model/i), {
      target: { value: "gemini-2.5-flash" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    expect(await screen.findByText(/primary routing key v2/i)).toBeInTheDocument();
    expect(screen.getAllByText(/gemini-2.5-flash/i).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /disable primary routing key v2/i }));
    await waitFor(() => {
      expect(screen.getAllByText(/^disabled$/i).length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByRole("button", { name: /enable primary routing key v2/i }));
    await waitFor(() => {
      expect(screen.getAllByText(/^active$/i).length).toBeGreaterThan(1);
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

    expect(await screen.findByText(/operator review demo/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /editing session/i }));

    fireEvent.click(await screen.findByRole("button", { name: /start editing session/i }));

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
    expect(await screen.findByText(/asset_manual_002/i)).toBeInTheDocument();
    expect(
      screen.getByText(/meeting context: summarize the active discussion\./i),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /request regeneration preflight/i }));

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

    expect(await screen.findByText(/expected affected output areas/i)).toBeInTheDocument();
    expect(screen.getAllByText(/b-roll track/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/timeline preview/i)).toBeInTheDocument();
    expect(screen.getByText(/capcut export/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /run partial regeneration/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/partial-regeneration",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            segment_ids: ["seg_002"],
            fields: ["broll", "explanation_card"],
          }),
        }),
      );
    });

    expect(await screen.findByText(/partial_regeneration_job_001/i)).toBeInTheDocument();
    expect(screen.getAllByText(/b-roll asset replaced with regenerated recommendation/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/timeline_002/i)).toBeInTheDocument();
  });

  it("rebases regeneration field selection when switching the target segment", async () => {
    const fetchMock = createFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /editing session/i }));
    fireEvent.click(await screen.findByRole("button", { name: /start editing session/i }));

    expect(await screen.findByRole("button", { name: /seg_002/i })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /broll/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /explanation card/i })).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: /seg_001/i }));

    expect(screen.getByRole("checkbox", { name: /caption/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /broll/i })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /explanation card/i })).not.toBeChecked();
  });

  it("shows a timeline-centered editing shell with changed-vs-preserved context after partial regeneration", async () => {
    const fetchMock = createFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /editing session/i }));
    fireEvent.click(await screen.findByRole("button", { name: /start editing session/i }));
    fireEvent.click(await screen.findByRole("button", { name: /request regeneration preflight/i }));
    fireEvent.click(await screen.findByRole("button", { name: /run partial regeneration/i }));

    expect(await screen.findByRole("heading", { name: /timeline-centered editor shell/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /selected segment detail/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /track impact summary/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /changed segment focus/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /preserved timeline area/i })).toBeInTheDocument();

    expect(screen.getByText(/seg_002 changed in current run/i)).toBeInTheDocument();
    expect(screen.getByText(/seg_001 preserved from prior timeline/i)).toBeInTheDocument();
    expect(screen.getAllByText(/^changed segments 1$/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/preserved segments 1/i)).toBeInTheDocument();

    expect(screen.getByText(/narration track/i)).toBeInTheDocument();
    expect(screen.getByText(/b-roll track/i)).toBeInTheDocument();
    expect(screen.getByText(/overlay track/i)).toBeInTheDocument();
    expect(screen.getByText(/asset_broll_regenerated_002/i)).toBeInTheDocument();
  });

  it("shows operator review decision guidance when changed segments are ready for sign-off", async () => {
    const fetchMock = createFetchMock();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /editing session/i }));
    fireEvent.click(await screen.findByRole("button", { name: /start editing session/i }));
    fireEvent.click(await screen.findByRole("button", { name: /request regeneration preflight/i }));
    fireEvent.click(await screen.findByRole("button", { name: /run partial regeneration/i }));

    expect(await screen.findByRole("heading", { name: /operator review decision loop/i })).toBeInTheDocument();
    expect(screen.getByText(/ready changed segments 1/i)).toBeInTheDocument();
    expect(screen.getByText(/review blockers 0/i)).toBeInTheDocument();
    expect(screen.getByText(/seg_002 ready for operator sign-off/i)).toBeInTheDocument();
    expect(screen.getByText(/approve updated timeline/i)).toBeInTheDocument();
    expect(
      screen.getByText(/all changed outputs are ready and the candidate timeline can now be approved/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /approve timeline/i })).toBeEnabled();
    expect(screen.getByText(/seg_001 remains stable outside the current rerun/i)).toBeInTheDocument();
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

    fireEvent.click(await screen.findByRole("button", { name: /editing session/i }));
    fireEvent.click(await screen.findByRole("button", { name: /start editing session/i }));
    fireEvent.click(await screen.findByRole("button", { name: /request regeneration preflight/i }));
    fireEvent.click(await screen.findByRole("button", { name: /run partial regeneration/i }));

    expect(await screen.findByRole("heading", { name: /operator review decision loop/i })).toBeInTheDocument();
    expect(screen.getByText(/ready changed segments 0/i)).toBeInTheDocument();
    expect(screen.getByText(/review blockers 1/i)).toBeInTheDocument();
    expect(screen.getByText(/seg_002 still needs operator review/i)).toBeInTheDocument();
    expect(screen.getByText(/hold before preview\/export/i)).toBeInTheDocument();
    expect(screen.getByText(/rerun suggested if the changed output is still incorrect/i)).toBeInTheDocument();
    expect(screen.getByText(/seg_001 remains stable outside the current rerun/i)).toBeInTheDocument();
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

    fireEvent.click(await screen.findByRole("button", { name: /editing session/i }));
    fireEvent.click(await screen.findByRole("button", { name: /start editing session/i }));
    fireEvent.click(await screen.findByRole("button", { name: /request regeneration preflight/i }));
    fireEvent.click(await screen.findByRole("button", { name: /run partial regeneration/i }));

    const approveButton = await screen.findByRole("button", { name: /approve timeline/i });
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
      expect(screen.getByRole("button", { name: /generate subtitle file/i })).toBeEnabled();
    });

    fireEvent.click(screen.getByRole("button", { name: /generate subtitle file/i }));
    fireEvent.click(screen.getByRole("button", { name: /render preview artifact/i }));
    fireEvent.click(screen.getByRole("button", { name: /export capcut payload/i }));

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

    fireEvent.click(await screen.findByRole("button", { name: /editing session/i }));
    fireEvent.click(await screen.findByRole("button", { name: /start editing session/i }));
    fireEvent.click(await screen.findByRole("button", { name: /request regeneration preflight/i }));
    fireEvent.click(await screen.findByRole("button", { name: /run partial regeneration/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /approve timeline/i })).toBeEnabled();
    });

    fireEvent.change(screen.getByDisplayValue("Team meeting overview"), {
      target: { value: "Team meeting overview refreshed" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save caption/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project_001/editing-sessions/editing_session_001/segments/seg_002/caption",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({
            caption_text: "Team meeting overview refreshed",
          }),
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /approve timeline/i })).toBeDisabled();
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

    fireEvent.click(await screen.findByRole("button", { name: /editing session/i }));

    expect(await screen.findByText(/editing_session_001/i)).toBeInTheDocument();
    expect(await screen.findByText(/partial_regeneration_job_001/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /approve timeline/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /generate subtitle file/i })).toBeDisabled();
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

    fireEvent.click(await screen.findByRole("button", { name: /editing session/i }));

    expect(await screen.findByText(/editing_session_001/i)).toBeInTheDocument();
    expect(screen.queryByText(/partial_regeneration_job_001/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /approve timeline/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /generate subtitle file/i })).toBeEnabled();
  });
});
