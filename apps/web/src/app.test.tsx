import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { App } from "./App";

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

const reviewSnapshotResponse = {
  project_id: "project_001",
  timeline_id: "timeline_001",
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
    file_uri: "local://projects/project_001/previews/preview_001.json",
    artifact_kind: "mock_preview_bundle",
    created_at: "2026-06-28T00:00:11Z",
    notes: ["Preview render is a structured local artifact in this phase."],
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
    created_at: "2026-06-28T00:00:13Z",
    notes: ["Mock CapCut payload written for local post-editing handoff."],
  },
};

describe("App", () => {
  it("renders a local-first operator dashboard from API data", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
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
      if (
        url.endsWith("/api/projects/project_001/jobs/build-timeline") &&
        init?.method === "POST"
      ) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              job_id: "timeline_build_job_005",
              status: "succeeded",
            }),
          ),
        );
      }
      if (
        url.endsWith("/api/projects/project_001/jobs/preview-render") &&
        init?.method === "POST"
      ) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              job_id: "preview_render_job_006",
              status: "succeeded",
            }),
          ),
        );
      }
      if (
        url.endsWith("/api/projects/project_001/jobs/capcut-export") &&
        init?.method === "POST"
      ) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              job_id: "capcut_export_job_007",
              status: "succeeded",
            }),
          ),
        );
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
      if (url.endsWith("/api/projects/project_001/exports/capcut_export_job_007")) {
        return Promise.resolve(new Response(JSON.stringify(exportResponse)));
      }
      return Promise.reject(new Error(`Unhandled fetch: ${url}`));
    });

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

    fireEvent.click(await screen.findByRole("button", { name: /render preview artifact/i }));
    fireEvent.click(await screen.findByRole("button", { name: /export capcut payload/i }));

    expect(await screen.findByText(/mock_preview_bundle/i)).toBeInTheDocument();
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
      return Promise.reject(new Error(`Unhandled fetch: ${url}`));
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(
      await screen.findByRole("button", { name: /render preview artifact/i }),
    ).toBeDisabled();
    expect(
      await screen.findByRole("button", { name: /export capcut payload/i }),
    ).toBeDisabled();
  });
});
