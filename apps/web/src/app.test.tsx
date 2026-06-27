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
      {
        code: "segment_review_required",
        segment_id: "seg_002",
        message: "Segment requires operator review before export.",
      },
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
      text: "Team meeting restart",
      start_sec: 3.5,
      end_sec: 7.8,
      confidence: 0.78,
      review_required: true,
      cleanup_decision: "review",
    },
  ],
  applied_recommendations: timelineResponse.timeline.applied_recommendations,
  pending_recommendations: timelineResponse.timeline.pending_recommendations,
  review_flags: timelineResponse.timeline.review_flags,
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
      if (url.endsWith("/api/projects/project_001/timelines/timeline_build_job_005")) {
        return Promise.resolve(new Response(JSON.stringify(timelineResponse)));
      }
      if (url.endsWith("/api/projects/project_001/review-snapshots/timeline_build_job_005")) {
        return Promise.resolve(new Response(JSON.stringify(reviewSnapshotResponse)));
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

    fireEvent.click(screen.getByRole("button", { name: /review snapshot/i }));

    expect(await screen.findByText(/segment review required/i)).toBeInTheDocument();
    expect(screen.getByText(/tts replacement/i)).toBeInTheDocument();
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

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/projects", undefined);
    });
  });
});
