import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { api } from "../api";
import { finalRenderFailureMessage, OutputsPage } from "./OutputsPage";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const finalJob = {
  job_id: "final-current", project_id: "project_a", job_type: "final_render", status: "succeeded",
  input_ref: "timeline-a", output_ref: "final-a", error_message: null,
  started_at: "2026-07-23T09:00:00Z", finished_at: "2026-07-23T09:01:00Z",
};
const capcutJob = {
  job_id: "capcut-current", project_id: "project_a", job_type: "capcut_draft_export", status: "succeeded",
  input_ref: "timeline-a", output_ref: "capcut-a", error_message: null,
  started_at: "2026-07-23T09:00:00Z", finished_at: "2026-07-23T09:01:00Z",
};
const activeTimelineJob = {
  job_id: "timeline-current", project_id: "project_a", job_type: "timeline_build", status: "succeeded",
  input_ref: "readiness-a", output_ref: "timeline-a", error_message: null,
  started_at: "2026-07-23T09:00:00Z", finished_at: "2026-07-23T09:01:00Z",
};
const subtitleJob = {
  job_id: "subtitle-current", project_id: "project_a", job_type: "subtitle_render", status: "succeeded",
  input_ref: "timeline-current", output_ref: "subtitle-a", error_message: null,
  started_at: "2026-07-23T09:02:00Z", finished_at: "2026-07-23T09:03:00Z",
};
const currentFinalJob = {
  job_id: "final-current-timeline", project_id: "project_a", job_type: "final_render", status: "succeeded",
  input_ref: "timeline-current", output_ref: "final-current-timeline", error_message: null,
  started_at: "2026-07-23T09:04:00Z", finished_at: "2026-07-23T09:05:00Z",
};

const editingSession = {
  session_id: "session-a", project_id: "project_a", timeline_id: "timeline-a", session_revision: 7,
  segments: [], history: [],
};

const currentApproval = {
  timeline_id: "timeline-a",
  project_id: "project_a",
  review_status: "approved",
  approved_at: "2026-07-23T09:01:00Z",
  updated_at: "2026-07-23T09:01:00Z",
  source_session_id: "session-a",
  source_session_revision: 7,
  is_current: true,
  invalidated_at: null,
  invalidated_reason: null,
};

beforeEach(() => {
  vi.spyOn(api, "getReviewApproval").mockResolvedValue(currentApproval);
});

function playbackManifest({
  projectId = "project_a",
  sessionId = "session-a",
  timelineId = "timeline-a",
  revision = 7,
  exactPreview = {
    status: "succeeded",
    url: "/api/projects/project_a/exact-previews/exact-a/content",
    source_session_id: "session-a",
    source_session_revision: 7,
    artifact_revision: 7,
  },
}: {
  projectId?: string;
  sessionId?: string;
  timelineId?: string;
  revision?: number;
  exactPreview?: Record<string, unknown>;
} = {}) {
  return {
    project_id: projectId,
    session_id: sessionId,
    timeline_id: timelineId,
    session_revision: revision,
    timeline_version: `v${revision}`,
    timebase: "seconds",
    fps: { num: 30, den: 1 },
    output: { width: 1080, height: 1920, sample_aspect_ratio: "1:1", rotation: 0, duration_sec: 1 },
    tracks: [],
    captions: [],
    gap_slots: [],
    source_status: { status: "current", source_session_id: sessionId, source_session_revision: revision },
    audition: { asset_urls: {} },
    exact_preview: exactPreview,
  };
}

function stubCanonicalSubtitleApi({
  reviewStatus = "approved",
  reviewFlags = [],
  pendingRecommendations = [],
  timelinePendingRecommendations = pendingRecommendations,
  jobs = [activeTimelineJob],
}: {
  reviewStatus?: string;
  reviewFlags?: unknown[];
  pendingRecommendations?: unknown[];
  timelinePendingRecommendations?: unknown[];
  jobs?: typeof activeTimelineJob[];
} = {}) {
  vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(editingSession as never);
  vi.spyOn(api, "listJobs").mockResolvedValue(jobs as never);
  vi.spyOn(api, "getEditorPlaybackManifest").mockResolvedValue(playbackManifest({
    exactPreview: {
      status: "unavailable",
      url: null,
      source_session_id: editingSession.session_id,
      source_session_revision: editingSession.session_revision,
    },
  }) as never);
  vi.spyOn(api, "getTimeline").mockResolvedValue({
    job_id: activeTimelineJob.job_id, status: "succeeded", timeline: {
      timeline_id: "timeline-a", project_id: "project_a", version: "v1", output_mode: "short", review_status: reviewStatus,
      source_session_id: "session-a", source_session_revision: 7,
      tracks: [], review_flags: reviewFlags, pending_recommendations: timelinePendingRecommendations,
    },
  } as never);
  vi.spyOn(api, "getReviewSnapshot").mockResolvedValue({
    project_id: "project_a", timeline_id: "timeline-a", review_status: reviewStatus,
    segments: [], applied_recommendations: [], pending_recommendations: pendingRecommendations, review_flags: reviewFlags,
  } as never);
  vi.spyOn(api, "getCapcutHandoffDiagnostics").mockResolvedValue({
    status: "ready", is_supported: true, project_root_path: "local://capcut", project_root_exists: true, write_access: true, checked_at: "2026-07-23T09:01:00Z",
  });
}

function stubReadOnlyOutputApi() {
  vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(null);
  vi.spyOn(api, "listJobs").mockResolvedValue([finalJob, capcutJob]);
  vi.spyOn(api, "getFinalRender").mockResolvedValue({
    job_id: finalJob.job_id, status: "succeeded", render: {
      export_id: "final-a", timeline_id: "timeline-a", export_type: "final_render", file_uri: "local://final.mp4", status: "succeeded", is_current: true,
    },
  });
  vi.spyOn(api, "getCapcutDraftExport").mockResolvedValue({
    job_id: capcutJob.job_id, status: "succeeded", export: {
      export_id: "capcut-a", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft.zip", status: "succeeded", notes: [], is_current: true,
      handoff: { status: "ready", source_file_uri: "local://draft.zip", reused: false },
    },
  });
  vi.spyOn(api, "getCapcutHandoffDiagnostics").mockResolvedValue({
    status: "ready", is_supported: true, project_root_path: "local://capcut", project_root_exists: true, write_access: true, checked_at: "2026-07-23T09:01:00Z",
  });
}

describe("OutputsPage", () => {
  it("starts one subtitle render for the approved active timeline and refreshes its typed status", async () => {
    stubCanonicalSubtitleApi();
    const renderSubtitle = vi.spyOn(api, "renderSubtitle").mockResolvedValue({ job_id: subtitleJob.job_id, status: "succeeded" });
    vi.spyOn(api, "getSubtitle").mockResolvedValue({
      job_id: subtitleJob.job_id, status: "succeeded", subtitle: {
        subtitle_id: "subtitle-a", project_id: "project_a", timeline_id: "timeline-a", format: "srt", file_uri: "local://subtitle.srt", status: "succeeded", notes: [],
        source_session_id: "session-a", source_session_revision: 7, is_current: true,
      },
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    const action = await screen.findByRole("button", { name: "자막 만들기" });
    expect(action).toBeEnabled();
    fireEvent.click(action);

    await waitFor(() => expect(renderSubtitle).toHaveBeenCalledWith("project_a", { timeline_job_id: "timeline-current" }));
    await waitFor(() => expect(api.getSubtitle).toHaveBeenCalledWith("project_a", "subtitle-current"));
    expect(await screen.findByText("자막이 준비되었어요.")).toBeVisible();
    expect(renderSubtitle).toHaveBeenCalledTimes(1);
    // owner 요청(2026-08-28): "srt... 내보내기". 준비된 자막 옆에 실제로
    // 내려받는 문이 보여야 한다.
    expect(screen.getByRole("link", { name: "SRT 자막 파일 내려받기" })).toHaveAttribute(
      "href", "/api/projects/project_a/subtitles/subtitle-current/content",
    );
  });

  it("does not present a subtitle from an older session revision as current", async () => {
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, subtitleJob] as never });
    vi.spyOn(api, "getSubtitle").mockResolvedValue({
      job_id: subtitleJob.job_id,
      status: "succeeded",
      subtitle: {
        subtitle_id: "subtitle-old",
        project_id: "project_a",
        timeline_id: "timeline-a",
        format: "srt",
        file_uri: "local://subtitle-old.srt",
        status: "succeeded",
        notes: [],
        source_session_revision: 6,
        is_current: false,
      },
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByText("자막이 최신 편집본과 달라요.")).toBeVisible();
    expect(screen.queryByText("자막이 준비되었어요.")).not.toBeInTheDocument();
  });

  it("keeps subtitle rendering disabled when the active review has a blocker", async () => {
    stubCanonicalSubtitleApi({ reviewFlags: [{ code: "review_required", segment_id: "segment-a", message: "확인이 필요해요." }] });
    const renderSubtitle = vi.spyOn(api, "renderSubtitle");

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    const action = await screen.findByRole("button", { name: "자막 만들기" });
    expect(action).toBeDisabled();
    fireEvent.click(action);
    expect(renderSubtitle).not.toHaveBeenCalled();
  });

  it("keeps output mutations disabled when the approval belongs to an older session revision", async () => {
    stubCanonicalSubtitleApi();
    vi.mocked(api.getReviewApproval).mockResolvedValue({
      ...currentApproval,
      source_session_revision: 6,
      is_current: false,
      invalidated_at: "2026-07-23T09:02:00Z",
      invalidated_reason: "session_revision_changed",
    });
    const renderSubtitle = vi.spyOn(api, "renderSubtitle");

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    const action = await screen.findByRole("button", { name: "자막 만들기" });
    expect(action).toBeDisabled();
    fireEvent.click(action);
    expect(renderSubtitle).not.toHaveBeenCalled();
  });

  it("keeps output mutations disabled when approval has the same revision but another session id", async () => {
    stubCanonicalSubtitleApi();
    vi.mocked(api.getReviewApproval).mockResolvedValue({
      ...currentApproval,
      source_session_id: "session-b",
    });
    const renderSubtitle = vi.spyOn(api, "renderSubtitle");

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    const action = await screen.findByRole("button", { name: "자막 만들기" });
    expect(action).toBeDisabled();
    fireEvent.click(action);
    expect(renderSubtitle).not.toHaveBeenCalled();
  });

  it("reconciles authoritatively without a retry error when subtitle creation succeeds but readback fails", async () => {
    stubCanonicalSubtitleApi();
    const renderSubtitle = vi.spyOn(api, "renderSubtitle").mockResolvedValue({ job_id: subtitleJob.job_id, status: "succeeded" });
    vi.spyOn(api, "getSubtitle").mockRejectedValueOnce(new Error("readback failed"));

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "자막 만들기" }));

    await waitFor(() => expect(renderSubtitle).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByText("자막을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).not.toBeInTheDocument());
  });

  it("keeps subtitle failure recoverable until the user explicitly tries again", async () => {
    stubCanonicalSubtitleApi();
    const listJobs = vi.mocked(api.listJobs);
    const renderSubtitle = vi.spyOn(api, "renderSubtitle").mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({ job_id: subtitleJob.job_id, status: "succeeded" });
    vi.spyOn(api, "getSubtitle").mockResolvedValue({
      job_id: subtitleJob.job_id, status: "succeeded", subtitle: {
        subtitle_id: "subtitle-a", project_id: "project_a", timeline_id: "timeline-a", format: "srt", file_uri: "local://subtitle.srt", status: "succeeded", notes: [],
        source_session_id: "session-a", source_session_revision: 7, is_current: true,
      },
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "자막 만들기" }));
    expect(await screen.findByText("자막을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(listJobs).toHaveBeenCalledTimes(2);
    expect(renderSubtitle).toHaveBeenCalledTimes(1);
    const retry = screen.getByRole("button", { name: "자막 만들기" });
    expect(retry).toBeEnabled();
    fireEvent.click(retry);
    await waitFor(() => expect(renderSubtitle).toHaveBeenCalledTimes(2));
  });

  it("reconciles a rejected subtitle request from authoritative current state before showing an error", async () => {
    stubCanonicalSubtitleApi();
    vi.mocked(api.listJobs)
      .mockResolvedValueOnce([activeTimelineJob] as never)
      .mockResolvedValue([activeTimelineJob, subtitleJob] as never);
    vi.spyOn(api, "renderSubtitle").mockRejectedValue(new Error("request outcome unknown"));
    vi.spyOn(api, "getSubtitle").mockResolvedValue({
      job_id: subtitleJob.job_id, status: "succeeded", subtitle: {
        subtitle_id: "subtitle-a", project_id: "project_a", timeline_id: "timeline-a", format: "srt", file_uri: "local://subtitle.srt", status: "succeeded", notes: [],
        source_session_id: "session-a", source_session_revision: 7, is_current: true,
      },
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "자막 만들기" }));

    expect(await screen.findByText("자막이 준비되었어요.")).toBeVisible();
    expect(screen.queryByText("자막을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).not.toBeInTheDocument();
    expect(api.listJobs).toHaveBeenCalledTimes(2);
  });

  it("does not reconcile a rejected subtitle request from another session with the same revision", async () => {
    stubCanonicalSubtitleApi();
    vi.mocked(api.listJobs)
      .mockResolvedValueOnce([activeTimelineJob] as never)
      .mockResolvedValue([activeTimelineJob, subtitleJob] as never);
    vi.spyOn(api, "renderSubtitle").mockRejectedValue(new Error("request outcome unknown"));
    vi.spyOn(api, "getSubtitle").mockResolvedValue({
      job_id: subtitleJob.job_id, status: "succeeded", subtitle: {
        subtitle_id: "subtitle-b", project_id: "project_a", timeline_id: "timeline-a", format: "srt",
        file_uri: "local://subtitle-b.srt", status: "succeeded", notes: [],
        source_session_id: "session-b", source_session_revision: 7, is_current: true,
      },
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "자막 만들기" }));

    expect(await screen.findByText("자막을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(screen.getByText("자막이 최신 편집본과 달라요.")).toBeVisible();
  });

  it("shows a subtitle request error when refresh only returns the same current artifact", async () => {
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, subtitleJob] as never });
    vi.spyOn(api, "renderSubtitle").mockRejectedValue(new Error("offline before server"));
    vi.spyOn(api, "getSubtitle").mockResolvedValue({
      job_id: subtitleJob.job_id, status: "succeeded", subtitle: {
        subtitle_id: "subtitle-a", project_id: "project_a", timeline_id: "timeline-a", format: "srt", file_uri: "local://subtitle.srt", status: "succeeded", notes: [],
        source_session_id: "session-a", source_session_revision: 7, is_current: true,
      },
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByText("자막이 준비되었어요.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "자막 만들기" }));

    expect(await screen.findByText("자막을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(api.listJobs).toHaveBeenCalledTimes(2);
  });

  it("accepts a rejected subtitle request only when refresh finds a new pending job", async () => {
    const pendingSubtitleJob = {
      ...subtitleJob,
      job_id: "subtitle-pending",
      status: "pending",
      started_at: "2026-07-23T09:04:00Z",
      finished_at: null,
    };
    stubCanonicalSubtitleApi();
    vi.mocked(api.listJobs)
      .mockResolvedValueOnce([activeTimelineJob] as never)
      .mockResolvedValue([activeTimelineJob, pendingSubtitleJob] as never);
    vi.spyOn(api, "renderSubtitle").mockRejectedValue(new Error("request outcome unknown"));
    vi.spyOn(api, "getSubtitle").mockResolvedValue({
      job_id: pendingSubtitleJob.job_id,
      status: "pending",
      subtitle: null,
    } as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "자막 만들기" }));

    await waitFor(() => expect(api.listJobs).toHaveBeenCalledTimes(2));
    expect(screen.queryByText("자막을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).not.toBeInTheDocument();
  });

  it("clears an older mutation error when a later authoritative refresh finds the current artifact", async () => {
    stubCanonicalSubtitleApi();
    vi.spyOn(api, "renderSubtitle").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "getSubtitle").mockResolvedValue({
      job_id: subtitleJob.job_id, status: "succeeded", subtitle: {
        subtitle_id: "subtitle-a", project_id: "project_a", timeline_id: "timeline-a", format: "srt", file_uri: "local://subtitle.srt", status: "succeeded", notes: [],
        source_session_id: "session-a", source_session_revision: 7, is_current: true,
      },
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "자막 만들기" }));
    expect(await screen.findByText("자막을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).toBeVisible();

    vi.mocked(api.listJobs).mockResolvedValue([activeTimelineJob, subtitleJob] as never);
    fireEvent.click(screen.getByRole("button", { name: "상태 다시 확인" }));

    expect(await screen.findByText("자막이 준비되었어요.")).toBeVisible();
    expect(screen.queryByText("자막을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).not.toBeInTheDocument();
  });

  it("keeps one subtitle mutation locked across a manual refresh and reconciles it after completion", async () => {
    stubCanonicalSubtitleApi();
    let resolveSubtitle!: (result: { job_id: string; status: string }) => void;
    const pendingSubtitle = new Promise<{ job_id: string; status: string }>((resolve) => { resolveSubtitle = resolve; });
    const renderSubtitle = vi.spyOn(api, "renderSubtitle").mockReturnValue(pendingSubtitle as never);
    vi.mocked(api.listJobs)
      .mockResolvedValueOnce([activeTimelineJob] as never)
      .mockResolvedValueOnce([activeTimelineJob] as never)
      .mockResolvedValue([activeTimelineJob, subtitleJob] as never);
    vi.spyOn(api, "getSubtitle").mockResolvedValue({
      job_id: subtitleJob.job_id,
      status: "succeeded",
      subtitle: {
        subtitle_id: "subtitle-a",
        project_id: "project_a",
        timeline_id: "timeline-a",
        format: "srt",
        file_uri: "local://subtitle.srt",
        status: "succeeded",
        notes: [],
        source_session_id: "session-a",
        source_session_revision: 7,
        is_current: true,
      },
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "자막 만들기" }));
    expect(screen.getByRole("button", { name: "자막 만드는 중" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "상태 다시 확인" }));
    await waitFor(() => expect(api.listJobs).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("button", { name: "자막 만드는 중" })).toBeDisabled();
    resolveSubtitle({ job_id: subtitleJob.job_id, status: "succeeded" });

    expect(await screen.findByText("자막이 준비되었어요.")).toBeVisible();
    expect(renderSubtitle).toHaveBeenCalledTimes(1);
  });

  it("surfaces a subtitle failure after a manual refresh when no durable progress exists", async () => {
    stubCanonicalSubtitleApi();
    let rejectSubtitle!: (error: Error) => void;
    const pendingSubtitle = new Promise((_resolve, reject) => { rejectSubtitle = reject; });
    vi.spyOn(api, "renderSubtitle").mockReturnValue(pendingSubtitle as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "자막 만들기" }));
    fireEvent.click(screen.getByRole("button", { name: "상태 다시 확인" }));
    await waitFor(() => expect(api.listJobs).toHaveBeenCalledTimes(2));
    await act(async () => {
      rejectSubtitle(new Error("offline"));
      await Promise.resolve();
    });

    expect(await screen.findByText("자막을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
  });

  it("does not offer project A's subtitle action while project B is still loading", async () => {
    const projectBSession = new Promise<null>(() => {});
    const projectBJobs = new Promise<[]>(() => {});
    vi.spyOn(api, "getLatestEditingSession").mockImplementation((requestedProjectId) => (
      requestedProjectId === "project_b"
        ? projectBSession as never
        : Promise.resolve({
            session_id: "session-a",
            project_id: "project_a",
            timeline_id: "timeline-a",
            session_revision: 7,
            segments: [],
            history: [],
          }) as never
    ));
    vi.spyOn(api, "listJobs").mockImplementation((requestedProjectId) => (
      requestedProjectId === "project_b" ? projectBJobs as never : Promise.resolve([activeTimelineJob]) as never
    ));
    vi.spyOn(api, "getTimeline").mockResolvedValue({
      job_id: activeTimelineJob.job_id, status: "succeeded", timeline: {
        timeline_id: "timeline-a", project_id: "project_a", version: "v1", output_mode: "short", review_status: "approved",
        source_session_id: "session-a", source_session_revision: 7,
        tracks: [], review_flags: [], pending_recommendations: [],
      },
    } as never);
    vi.spyOn(api, "getReviewSnapshot").mockResolvedValue({
      project_id: "project_a", timeline_id: "timeline-a", review_status: "approved", segments: [], applied_recommendations: [], pending_recommendations: [], review_flags: [],
    } as never);
    vi.spyOn(api, "getCapcutHandoffDiagnostics").mockResolvedValue(null as never);
    const renderSubtitle = vi.spyOn(api, "renderSubtitle");

    const view = render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);
    expect(await screen.findByRole("button", { name: "자막 만들기" })).toBeEnabled();

    view.rerender(<OutputsPage projectId="project_b" onOpenEditor={vi.fn()} />);

    const action = screen.getByRole("button", { name: "자막 만들기" });
    expect(action).toBeDisabled();
    fireEvent.click(action);
    expect(renderSubtitle).not.toHaveBeenCalled();
  });

  it("does not let an in-flight project A subtitle request change project B state", async () => {
    let rejectProjectASubtitle!: (error: Error) => void;
    const projectASubtitle = new Promise<{ job_id: string; status: string }>((_resolve, reject) => { rejectProjectASubtitle = reject; });
    const projectBSession = new Promise<null>(() => {});
    const projectBJobs = new Promise<[]>(() => {});
    vi.spyOn(api, "getLatestEditingSession").mockImplementation((requestedProjectId) => (
      requestedProjectId === "project_b"
        ? projectBSession as never
        : Promise.resolve({ session_id: "session-a", project_id: "project_a", timeline_id: "timeline-a", session_revision: 7 }) as never
    ));
    vi.spyOn(api, "listJobs").mockImplementation((requestedProjectId) => (
      requestedProjectId === "project_b" ? projectBJobs as never : Promise.resolve([activeTimelineJob]) as never
    ));
    vi.spyOn(api, "getTimeline").mockResolvedValue({
      job_id: activeTimelineJob.job_id, status: "succeeded", timeline: {
        timeline_id: "timeline-a", project_id: "project_a", version: "v1", output_mode: "short", review_status: "approved",
        source_session_id: "session-a", source_session_revision: 7,
        tracks: [], review_flags: [], pending_recommendations: [],
      },
    } as never);
    vi.spyOn(api, "getReviewSnapshot").mockResolvedValue({
      project_id: "project_a", timeline_id: "timeline-a", review_status: "approved", segments: [], applied_recommendations: [], pending_recommendations: [], review_flags: [],
    } as never);
    vi.spyOn(api, "getCapcutHandoffDiagnostics").mockResolvedValue(null as never);
    vi.spyOn(api, "renderSubtitle").mockReturnValue(projectASubtitle as never);

    const view = render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "자막 만들기" }));
    expect(screen.getByRole("button", { name: "자막 만드는 중" })).toBeDisabled();

    view.rerender(<OutputsPage projectId="project_b" onOpenEditor={vi.fn()} />);
    rejectProjectASubtitle(new Error("offline"));

    await Promise.resolve();
    expect(screen.getByRole("button", { name: "자막 만들기" })).toBeDisabled();
    expect(screen.queryByText("자막을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "자막 만드는 중" })).not.toBeInTheDocument();
  });

  it("does not let a delayed project A subtitle state replace project B", async () => {
    let resolveProjectA!: (session: { session_id: string; project_id: string; timeline_id: string }) => void;
    const projectASession = new Promise<{ session_id: string; project_id: string; timeline_id: string }>((resolve) => { resolveProjectA = resolve; });
    vi.spyOn(api, "getLatestEditingSession").mockReturnValueOnce(projectASession as never).mockResolvedValueOnce(null);
    vi.spyOn(api, "listJobs").mockResolvedValue([activeTimelineJob] as never);
    vi.spyOn(api, "getCapcutHandoffDiagnostics").mockResolvedValue({
      status: "ready", is_supported: true, project_root_path: "local://capcut", project_root_exists: true, write_access: true, checked_at: "2026-07-23T09:01:00Z",
    });
    const getTimeline = vi.spyOn(api, "getTimeline");

    const view = render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);
    view.rerender(<OutputsPage projectId="project_b" onOpenEditor={vi.fn()} />);
    expect(await screen.findByText("아직 자막이 없어요.")).toBeVisible();

    resolveProjectA({ session_id: "session-a", project_id: "project_a", timeline_id: "timeline-a" });
    await waitFor(() => expect(getTimeline).not.toHaveBeenCalled());
    expect(screen.getByText("아직 자막이 없어요.")).toBeVisible();
    expect(screen.getByRole("button", { name: "자막 만들기" })).toBeDisabled();
  });

  it("starts one final render for the approved active timeline and refreshes its typed result", async () => {
    stubCanonicalSubtitleApi();
    const listJobs = vi.mocked(api.listJobs);
    listJobs.mockResolvedValueOnce([activeTimelineJob] as never).mockResolvedValue([activeTimelineJob, currentFinalJob] as never);
    const startFinalRender = vi.spyOn(api, "startFinalRender").mockResolvedValue({ job_id: currentFinalJob.job_id, status: "succeeded" });
    vi.spyOn(api, "getFinalRender").mockResolvedValue({
      job_id: currentFinalJob.job_id, status: "succeeded", render: {
        export_id: "final-current-timeline", timeline_id: "timeline-a", export_type: "final_render", file_uri: "local://final-current.mp4", status: "succeeded", source_session_id: "session-a", source_session_revision: 7, is_current: true,
      },
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "완성본 만들기" }));
    await waitFor(() => expect(startFinalRender).toHaveBeenCalledWith("project_a", { timeline_job_id: "timeline-current" }));
    await waitFor(() => expect(api.getFinalRender).toHaveBeenCalledWith("project_a", "final-current-timeline"));
    expect(await screen.findByLabelText("완성본 재생")).toHaveAttribute("src", "/api/projects/project_a/final-renders/final-current-timeline/content");
    expect(startFinalRender).toHaveBeenCalledTimes(1);
    // owner 요청(2026-08-28): "오디오만... 내보내기". 완성본 옆에 실제로
    // 내려받는 문이 보여야 한다.
    expect(screen.getByRole("link", { name: "오디오만 내려받기" })).toHaveAttribute(
      "href", "/api/projects/project_a/final-renders/final-current-timeline/audio-content",
    );
  });

  it("reconciles a rejected final request from authoritative current state before showing an error", async () => {
    stubCanonicalSubtitleApi();
    vi.mocked(api.listJobs)
      .mockResolvedValueOnce([activeTimelineJob] as never)
      .mockResolvedValue([activeTimelineJob, currentFinalJob] as never);
    vi.spyOn(api, "startFinalRender").mockRejectedValue(new Error("request outcome unknown"));
    vi.spyOn(api, "getFinalRender").mockResolvedValue({
      job_id: currentFinalJob.job_id, status: "succeeded", render: {
        export_id: "final-current-timeline", timeline_id: "timeline-a", export_type: "final_render", file_uri: "local://final-current.mp4", status: "succeeded", source_session_id: "session-a", source_session_revision: 7, is_current: true,
      },
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "완성본 만들기" }));

    expect(await screen.findByLabelText("완성본 재생")).toBeVisible();
    expect(screen.queryByText("완성본을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).not.toBeInTheDocument();
    expect(api.listJobs).toHaveBeenCalledTimes(2);
  });

  it("does not reconcile a rejected final request from another session with the same revision", async () => {
    stubCanonicalSubtitleApi();
    vi.mocked(api.listJobs)
      .mockResolvedValueOnce([activeTimelineJob] as never)
      .mockResolvedValue([activeTimelineJob, currentFinalJob] as never);
    vi.spyOn(api, "startFinalRender").mockRejectedValue(new Error("request outcome unknown"));
    vi.spyOn(api, "getFinalRender").mockResolvedValue({
      job_id: currentFinalJob.job_id, status: "succeeded", render: {
        export_id: "final-b", timeline_id: "timeline-a", export_type: "final_render",
        file_uri: "local://final-b.mp4", status: "succeeded",
        source_session_id: "session-b", source_session_revision: 7, is_current: true,
      },
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "완성본 만들기" }));

    expect(await screen.findByText("완성본을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(screen.getByText("완성본이 최신 편집본과 달라요.")).toBeVisible();
    expect(screen.queryByLabelText("완성본 재생")).not.toBeInTheDocument();
  });

  it("shows a final request error when refresh only returns the same current artifact", async () => {
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentFinalJob] as never });
    vi.spyOn(api, "startFinalRender").mockRejectedValue(new Error("offline before server"));
    vi.spyOn(api, "getFinalRender").mockResolvedValue({
      job_id: currentFinalJob.job_id, status: "succeeded", render: {
        export_id: "final-current-timeline", timeline_id: "timeline-a", export_type: "final_render", file_uri: "local://final-current.mp4", status: "succeeded", source_session_id: "session-a", source_session_revision: 7, is_current: true,
      },
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByLabelText("완성본 재생")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "완성본 만들기" }));

    expect(await screen.findByText("완성본을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(api.listJobs).toHaveBeenCalledTimes(2);
  });

  it("warns when the finished video carries no sound", async () => {
    // 무음 완성본이 아무 말 없이 나가던 문제. 렌더가 실제로 잰 결과가
    // "소리 없음"이면 내보내기 전에 화면에서 알려야 한다.
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentFinalJob] as never });
    vi.spyOn(api, "getFinalRender").mockResolvedValue({
      job_id: currentFinalJob.job_id, status: "succeeded", render: {
        export_id: "final-silent", timeline_id: "timeline-a", export_type: "final_render", file_uri: "local://final-silent.mp4", status: "succeeded", source_session_id: "session-a", source_session_revision: 7, is_current: true, has_sound: false,
      },
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByText("완성본에 소리가 들어 있지 않아요. 내레이션이나 음악을 넣고 다시 만들어 주세요.")).toBeVisible();
  });

  it("stays quiet about sound when the render carries sound or was not measured", async () => {
    // 재는 데 실패했을 때 경고를 띄우면 멀쩡한 완성본을 의심하게 된다.
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentFinalJob] as never });
    vi.spyOn(api, "getFinalRender").mockResolvedValue({
      job_id: currentFinalJob.job_id, status: "succeeded", render: {
        export_id: "final-unmeasured", timeline_id: "timeline-a", export_type: "final_render", file_uri: "local://final-unmeasured.mp4", status: "succeeded", source_session_id: "session-a", source_session_revision: 7, is_current: true,
      },
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByLabelText("완성본 재생")).toBeVisible();
    expect(screen.queryByText("완성본에 소리가 들어 있지 않아요. 내레이션이나 음악을 넣고 다시 만들어 주세요.")).not.toBeInTheDocument();
  });

  it("lets the owner say a finished video was good, and remembers it", async () => {
    // 자기개선의 재료는 기계가 잰 지표 + 사람의 판단이다. 판단을 받을 자리가
    // 화면에 없으면 라벨이 영영 쌓이지 않는다.
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentFinalJob] as never });
    const artifact = {
      export_id: "final-judged", timeline_id: "timeline-a", export_type: "final_render", file_uri: "local://final.mp4",
      status: "succeeded", source_session_id: "session-a", source_session_revision: 7, is_current: true, has_sound: true,
    };
    vi.spyOn(api, "getFinalRender").mockResolvedValue({ job_id: currentFinalJob.job_id, status: "succeeded", render: artifact });
    const verdict = vi.spyOn(api, "recordFinalRenderVerdict").mockResolvedValue({
      job_id: currentFinalJob.job_id, status: "succeeded", render: { ...artifact, owner_verdict: "good" },
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "이 완성본 좋아요" }));

    await waitFor(() => expect(verdict).toHaveBeenCalledWith("project_a", currentFinalJob.job_id, { verdict: "good" }));
    expect(await screen.findByText("좋았다고 기록했어요.")).toBeVisible();
  });

  it("lets the owner make a preview share link for a colleague and shows the url", async () => {
    // owner 요청(2026-08-28): 프리뷰 공유 링크. 동료가 앱 없이 이 링크만으로 완성본을
    // 볼 수 있어야 하니, 만든 뒤에는 화면에 그 주소가 그대로 보여야 한다.
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentFinalJob] as never });
    vi.spyOn(api, "getFinalRender").mockResolvedValue({
      job_id: currentFinalJob.job_id, status: "succeeded", render: {
        export_id: "final-shared", timeline_id: "timeline-a", export_type: "final_render", file_uri: "local://final.mp4",
        status: "succeeded", source_session_id: "session-a", source_session_revision: 7, is_current: true,
      },
    });
    const createPreviewShare = vi.spyOn(api, "createPreviewShare").mockResolvedValue({
      share_id: "preview-share-1", token: "opaque-token-abc", url: "/preview/opaque-token-abc",
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "동료에게 공유 링크 만들기" }));

    await waitFor(() => expect(createPreviewShare).toHaveBeenCalledWith("project_a", currentFinalJob.job_id));
    const link = await screen.findByDisplayValue(`${window.location.origin}/preview/opaque-token-abc`);
    expect(link).toBeVisible();
  });

  it("lets the owner revoke a preview share link -- code review found no way to take one back", async () => {
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentFinalJob] as never });
    vi.spyOn(api, "getFinalRender").mockResolvedValue({
      job_id: currentFinalJob.job_id, status: "succeeded", render: {
        export_id: "final-shared", timeline_id: "timeline-a", export_type: "final_render", file_uri: "local://final.mp4",
        status: "succeeded", source_session_id: "session-a", source_session_revision: 7, is_current: true,
      },
    });
    vi.spyOn(api, "createPreviewShare").mockResolvedValue({
      share_id: "preview-share-1", token: "opaque-token-abc", url: "/preview/opaque-token-abc",
    });
    const revokePreviewShare = vi.spyOn(api, "revokePreviewShare").mockResolvedValue({ revoked: true });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "동료에게 공유 링크 만들기" }));
    await screen.findByDisplayValue(`${window.location.origin}/preview/opaque-token-abc`);

    fireEvent.click(screen.getByRole("button", { name: "이 링크 취소하기" }));

    await waitFor(() => expect(revokePreviewShare).toHaveBeenCalledWith("project_a", "preview-share-1"));
    expect(await screen.findByText("이 링크를 취소했어요. 더 이상 열리지 않아요.")).toBeVisible();
    expect(screen.queryByDisplayValue(`${window.location.origin}/preview/opaque-token-abc`)).not.toBeInTheDocument();
  });

  it("saves the format of a video the owner liked, under a name they chose", async () => {
    // 자동 제작은 "어떻게 만들지"를 여기서 가져간다. 마음에 든 완성본을 봤을 때가
    // 그 포맷을 남길 유일한 순간이다.
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentFinalJob] as never });
    vi.spyOn(api, "getFinalRender").mockResolvedValue({
      job_id: currentFinalJob.job_id, status: "succeeded", render: {
        export_id: "final-liked", timeline_id: "timeline-a", export_type: "final_render", file_uri: "local://f.mp4",
        status: "succeeded", source_session_id: "session-a", source_session_revision: 7, is_current: true,
      },
    });
    const save = vi.spyOn(api, "saveFormatTemplate").mockResolvedValue({
      template_id: "format_template_1", name: "내 브이로그 포맷", caption_style: {},
    } as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);
    fireEvent.change(await screen.findByLabelText("포맷 이름"), { target: { value: "내 브이로그 포맷" } });
    fireEvent.click(screen.getByRole("button", { name: "이 포맷 저장하기" }));

    await waitFor(() => expect(save).toHaveBeenCalledWith("project_a", { name: "내 브이로그 포맷", session_id: "session-a" }));
    expect(await screen.findByText("포맷을 저장했어요. 다음 영상에서 편집 화면의 저장한 포맷에서 고를 수 있어요.")).toBeVisible();
  });

  it("will not save a format without a name a person can recognize", async () => {
    // 이름 없는 포맷이 쌓이면 다음 영상에서 무엇을 고를지 알 수 없다.
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentFinalJob] as never });
    vi.spyOn(api, "getFinalRender").mockResolvedValue({
      job_id: currentFinalJob.job_id, status: "succeeded", render: {
        export_id: "final-liked", timeline_id: "timeline-a", export_type: "final_render", file_uri: "local://f.mp4",
        status: "succeeded", source_session_id: "session-a", source_session_revision: 7, is_current: true,
      },
    });
    const save = vi.spyOn(api, "saveFormatTemplate");

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);
    await screen.findByLabelText("포맷 이름");
    fireEvent.click(screen.getByRole("button", { name: "이 포맷 저장하기" }));

    expect(save).not.toHaveBeenCalled();
  });

  it("keeps the judgement buttons away from a video that is not current", async () => {
    // 낡은 완성본을 평가하면 어느 편집본에 대한 판단인지 알 수 없어진다.
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentFinalJob] as never });
    vi.spyOn(api, "getFinalRender").mockResolvedValue({
      job_id: currentFinalJob.job_id, status: "succeeded", render: {
        export_id: "final-stale", timeline_id: "timeline-a", export_type: "final_render", file_uri: "local://stale.mp4",
        status: "succeeded", source_session_id: "session-old", source_session_revision: 3, is_current: false,
      },
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    await screen.findByText("완성본이 최신 편집본과 달라요.");
    expect(screen.queryByRole("button", { name: "이 완성본 좋아요" })).not.toBeInTheDocument();
  });

  it("accepts a rejected final request only when refresh finds a new running job", async () => {
    const runningFinalJob = {
      ...currentFinalJob,
      job_id: "final-running",
      status: "running",
      started_at: "2026-07-23T09:06:00Z",
      finished_at: null,
    };
    stubCanonicalSubtitleApi();
    vi.mocked(api.listJobs)
      .mockResolvedValueOnce([activeTimelineJob] as never)
      .mockResolvedValue([activeTimelineJob, runningFinalJob] as never);
    vi.spyOn(api, "startFinalRender").mockRejectedValue(new Error("request outcome unknown"));
    vi.spyOn(api, "getFinalRender").mockResolvedValue({
      job_id: runningFinalJob.job_id,
      status: "running",
      render: null,
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "완성본 만들기" }));

    expect(await screen.findByText("완성본을 만드는 중이에요.")).toBeVisible();
    expect(screen.queryByText("완성본을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).not.toBeInTheDocument();
  });

  it("ignores a final render from another timeline when choosing the current output", async () => {
    const oldFinal = { ...finalJob, input_ref: "timeline-old", job_id: "final-old" };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, oldFinal] as never });
    const getFinalRender = vi.spyOn(api, "getFinalRender").mockResolvedValue(null as never);
    const startFinalRender = vi.spyOn(api, "startFinalRender").mockResolvedValue({ job_id: currentFinalJob.job_id, status: "pending" });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByRole("button", { name: "완성본 만들기" })).toBeEnabled();
    expect(getFinalRender).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "완성본 만들기" }));
    await waitFor(() => expect(startFinalRender).toHaveBeenCalledWith("project_a", { timeline_job_id: "timeline-current" }));
  });

  it("does not present a final artifact with mismatched timeline or revision as current", async () => {
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentFinalJob] as never });
    vi.spyOn(api, "getFinalRender").mockResolvedValue({
      job_id: currentFinalJob.job_id, status: "succeeded", render: {
        export_id: "final-mismatch", timeline_id: "timeline-other", export_type: "final_render", file_uri: "local://final-other.mp4",
        status: "succeeded", source_session_revision: 6, is_current: true,
      },
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByText("완성본이 최신 편집본과 달라요.")).toBeVisible();
    expect(screen.queryByLabelText("완성본 재생")).not.toBeInTheDocument();
  });

  it("keeps failed final rendering recoverable through an explicit new final request", async () => {
    const failedCurrentFinal = { ...currentFinalJob, status: "failed", error_message: "encoder failed" };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, failedCurrentFinal] as never });
    vi.spyOn(api, "getFinalRender").mockResolvedValue({ job_id: failedCurrentFinal.job_id, status: "failed", render: null, error_message: "encoder failed" });
    const startFinalRender = vi.spyOn(api, "startFinalRender").mockResolvedValue({ job_id: currentFinalJob.job_id, status: "pending" });
    const retryJob = vi.spyOn(api, "retryJob");

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "완성본 다시 만들기" }));
    await waitFor(() => expect(startFinalRender).toHaveBeenCalledWith("project_a", { timeline_job_id: "timeline-current" }));
    expect(retryJob).not.toHaveBeenCalled();
  });

  it("does not start another final render while the current timeline already has one running", async () => {
    const runningCurrentFinal = { ...currentFinalJob, status: "running", finished_at: null };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, runningCurrentFinal] as never });
    vi.spyOn(api, "getFinalRender").mockResolvedValue({ job_id: runningCurrentFinal.job_id, status: "running", render: null });
    const startFinalRender = vi.spyOn(api, "startFinalRender");

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    const action = await screen.findByRole("button", { name: "완성본 만들기" });
    expect(action).toBeDisabled();
    fireEvent.click(action);
    expect(startFinalRender).not.toHaveBeenCalled();
  });

  it("keeps final rendering disabled when the timeline still has pending recommendations", async () => {
    stubCanonicalSubtitleApi({ timelinePendingRecommendations: [{ recommendation_id: "timeline-pending" }] });
    const startFinalRender = vi.spyOn(api, "startFinalRender");

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    const action = await screen.findByRole("button", { name: "완성본 만들기" });
    expect(action).toBeDisabled();
    fireEvent.click(action);
    expect(startFinalRender).not.toHaveBeenCalled();
  });

  it("does not start another final render when an older current-timeline job is still running", async () => {
    const runningOlderFinal = { ...currentFinalJob, job_id: "final-running-older", status: "running", started_at: "2026-07-23T09:03:00Z", finished_at: null };
    const succeededNewerFinal = { ...currentFinalJob, job_id: "final-succeeded-newer", started_at: "2026-07-23T09:06:00Z", finished_at: "2026-07-23T09:07:00Z" };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, runningOlderFinal, succeededNewerFinal] as never });
    vi.spyOn(api, "getFinalRender").mockResolvedValue({ job_id: succeededNewerFinal.job_id, status: "succeeded", render: { export_id: "final-succeeded-newer", timeline_id: "timeline-a", export_type: "final_render", file_uri: "local://newer.mp4", status: "succeeded", source_session_id: "session-a", source_session_revision: 7, is_current: true } } as never);
    const startFinalRender = vi.spyOn(api, "startFinalRender");

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    const action = await screen.findByRole("button", { name: "완성본 만들기" });
    expect(action).toBeDisabled();
    fireEvent.click(action);
    expect(startFinalRender).not.toHaveBeenCalled();
  });

  it("starts only one final render for rapid double clicks", async () => {
    stubCanonicalSubtitleApi();
    const pendingFinal = new Promise<{ job_id: string; status: string }>(() => {});
    const startFinalRender = vi.spyOn(api, "startFinalRender").mockReturnValue(pendingFinal as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    const action = await screen.findByRole("button", { name: "완성본 만들기" });
    fireEvent.click(action);
    fireEvent.click(action);
    expect(startFinalRender).toHaveBeenCalledTimes(1);
  });

  it("does not let a delayed final submission follow-up overwrite a newer manual refresh", async () => {
    stubCanonicalSubtitleApi();
    let resolveSubmissionJobs!: (jobs: typeof activeTimelineJob[]) => void;
    const delayedSubmissionJobs = new Promise<typeof activeTimelineJob[]>((resolve) => { resolveSubmissionJobs = resolve; });
    const submittedFinal = { ...currentFinalJob, job_id: "final-submitted", started_at: "2026-07-23T09:04:00Z", finished_at: "2026-07-23T09:05:00Z" };
    const refreshedFinal = { ...currentFinalJob, job_id: "final-refreshed", started_at: "2026-07-23T09:06:00Z", finished_at: "2026-07-23T09:07:00Z" };
    const listJobs = vi.mocked(api.listJobs);
    listJobs
      .mockResolvedValueOnce([activeTimelineJob] as never)
      .mockReturnValueOnce(delayedSubmissionJobs as never)
      .mockResolvedValue([activeTimelineJob, refreshedFinal] as never);
    vi.spyOn(api, "startFinalRender").mockResolvedValue({ job_id: submittedFinal.job_id, status: "succeeded" });
    vi.spyOn(api, "getFinalRender").mockImplementation((_projectId, jobId) => Promise.resolve({
      job_id: jobId, status: "succeeded", render: { export_id: jobId, timeline_id: "timeline-a", export_type: "final_render", file_uri: `local://${jobId}.mp4`, status: "succeeded", source_session_id: "session-a", source_session_revision: 7, is_current: true },
    }) as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "완성본 만들기" }));
    await waitFor(() => expect(listJobs).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole("button", { name: "상태 다시 확인" }));
    expect(await screen.findByLabelText("완성본 재생")).toHaveAttribute("src", "/api/projects/project_a/final-renders/final-refreshed/content");

    resolveSubmissionJobs([activeTimelineJob, submittedFinal] as never);
    await waitFor(() => expect(api.getFinalRender).toHaveBeenCalledWith("project_a", "final-submitted"));
    await waitFor(() => expect(screen.getByLabelText("완성본 재생")).toHaveAttribute("src", "/api/projects/project_a/final-renders/final-refreshed/content"));
  });

  it("does not surface an older final failure after a newer manual refresh", async () => {
    stubCanonicalSubtitleApi();
    let rejectFinal!: (error: Error) => void;
    const pendingFinal = new Promise((_resolve, reject) => { rejectFinal = reject; });
    vi.spyOn(api, "startFinalRender").mockReturnValue(pendingFinal as never);
    vi.mocked(api.listJobs)
      .mockResolvedValueOnce([activeTimelineJob] as never)
      .mockResolvedValue([activeTimelineJob, currentFinalJob] as never);
    vi.spyOn(api, "getFinalRender").mockResolvedValue({
      job_id: currentFinalJob.job_id,
      status: "succeeded",
      render: {
        export_id: "final-current",
        timeline_id: "timeline-a",
        export_type: "final_render",
        file_uri: "local://final-current.mp4",
        status: "succeeded",
        source_session_id: "session-a",
        source_session_revision: 7,
        is_current: true,
      },
    } as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "완성본 만들기" }));
    fireEvent.click(screen.getByRole("button", { name: "상태 다시 확인" }));
    expect(await screen.findByLabelText("완성본 재생")).toBeVisible();
    await act(async () => {
      rejectFinal(new Error("offline"));
      await Promise.resolve();
    });

    expect(screen.queryByText("완성본을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).not.toBeInTheDocument();
    expect(screen.getByLabelText("완성본 재생")).toBeVisible();
  });

  it("surfaces a final failure after a manual refresh when no durable progress exists", async () => {
    stubCanonicalSubtitleApi();
    let rejectFinal!: (error: Error) => void;
    const pendingFinal = new Promise((_resolve, reject) => { rejectFinal = reject; });
    vi.spyOn(api, "startFinalRender").mockReturnValue(pendingFinal as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "완성본 만들기" }));
    fireEvent.click(screen.getByRole("button", { name: "상태 다시 확인" }));
    await waitFor(() => expect(api.listJobs).toHaveBeenCalledTimes(2));
    await act(async () => {
      rejectFinal(new Error("offline"));
      await Promise.resolve();
    });

    expect(await screen.findByText("완성본을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
  });

  it("does not let an in-flight project A final render change project B state", async () => {
    let rejectProjectAFinal!: (error: Error) => void;
    const projectAFinal = new Promise<{ job_id: string; status: string }>((_resolve, reject) => { rejectProjectAFinal = reject; });
    const projectBSession = new Promise<null>(() => {});
    const projectBJobs = new Promise<[]>(() => {});
    vi.spyOn(api, "getLatestEditingSession").mockImplementation((requestedProjectId) => (
      requestedProjectId === "project_b"
        ? projectBSession as never
        : Promise.resolve({ session_id: "session-a", project_id: "project_a", timeline_id: "timeline-a", session_revision: 7 }) as never
    ));
    vi.spyOn(api, "listJobs").mockImplementation((requestedProjectId) => (
      requestedProjectId === "project_b" ? projectBJobs as never : Promise.resolve([activeTimelineJob]) as never
    ));
    vi.spyOn(api, "getTimeline").mockResolvedValue({
      job_id: activeTimelineJob.job_id, status: "succeeded", timeline: {
        timeline_id: "timeline-a", project_id: "project_a", version: "v1", output_mode: "short", review_status: "approved",
        source_session_id: "session-a", source_session_revision: 7,
        tracks: [], review_flags: [], pending_recommendations: [],
      },
    } as never);
    vi.spyOn(api, "getReviewSnapshot").mockResolvedValue({
      project_id: "project_a", timeline_id: "timeline-a", review_status: "approved", segments: [], applied_recommendations: [], pending_recommendations: [], review_flags: [],
    } as never);
    vi.spyOn(api, "getCapcutHandoffDiagnostics").mockResolvedValue(null as never);
    vi.spyOn(api, "startFinalRender").mockReturnValue(projectAFinal as never);

    const view = render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "완성본 만들기" }));
    expect(screen.getByRole("button", { name: "완성본 만드는 중" })).toBeDisabled();

    view.rerender(<OutputsPage projectId="project_b" onOpenEditor={vi.fn()} />);
    rejectProjectAFinal(new Error("offline"));

    await Promise.resolve();
    expect(screen.getByRole("button", { name: "완성본 만들기" })).toBeDisabled();
    expect(screen.queryByText("완성본을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "완성본 만드는 중" })).not.toBeInTheDocument();
  });

  it("starts one CapCut draft export for the approved active timeline and shows its local status", async () => {
    stubCanonicalSubtitleApi();
    const currentCapcutJob = { ...capcutJob, input_ref: "timeline-current", job_id: "capcut-current-timeline" };
    const listJobs = vi.mocked(api.listJobs);
    listJobs.mockResolvedValueOnce([activeTimelineJob] as never).mockResolvedValue([activeTimelineJob, currentCapcutJob] as never);
    const startCapcutDraftExport = vi.spyOn(api, "startCapcutDraftExport").mockResolvedValue({ job_id: currentCapcutJob.job_id, status: "succeeded" });
    vi.spyOn(api, "getCapcutDraftExport").mockResolvedValue({
      job_id: currentCapcutJob.job_id, status: "succeeded", export: {
        export_id: "capcut-current", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft-current.zip", status: "succeeded", notes: [], source_session_id: "session-a", source_session_revision: 7, is_current: true,
      },
    } as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "CapCut 초안 만들기" }));
    await waitFor(() => expect(startCapcutDraftExport).toHaveBeenCalledWith("project_a", { timeline_job_id: "timeline-current" }));
    await waitFor(() => expect(api.getCapcutDraftExport).toHaveBeenCalledWith("project_a", "capcut-current-timeline"));
    expect(await screen.findByText("CapCut 초안이 준비되었어요.")).toBeVisible();
    expect(screen.getByText("로컬 저장 위치: local://draft-current.zip")).toBeVisible();
    expect(screen.queryByRole("link", { name: /draft-current/i })).not.toBeInTheDocument();
    expect(startCapcutDraftExport).toHaveBeenCalledTimes(1);
  });

  it("reconciles a rejected CapCut draft request from authoritative current state before showing an error", async () => {
    const currentCapcutJob = { ...capcutJob, input_ref: "timeline-current", job_id: "capcut-current-timeline" };
    stubCanonicalSubtitleApi();
    vi.mocked(api.listJobs)
      .mockResolvedValueOnce([activeTimelineJob] as never)
      .mockResolvedValue([activeTimelineJob, currentCapcutJob] as never);
    vi.spyOn(api, "startCapcutDraftExport").mockRejectedValue(new Error("request outcome unknown"));
    vi.spyOn(api, "getCapcutDraftExport").mockResolvedValue({
      job_id: currentCapcutJob.job_id, status: "succeeded", export: {
        export_id: "capcut-current", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft-current.zip", status: "succeeded", notes: [], source_session_id: "session-a", source_session_revision: 7, is_current: true,
      },
    } as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "CapCut 초안 만들기" }));

    expect(await screen.findByText("CapCut 초안이 준비되었어요.")).toBeVisible();
    expect(screen.queryByText("CapCut 초안을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).not.toBeInTheDocument();
    expect(api.listJobs).toHaveBeenCalledTimes(2);
  });

  it("does not reconcile a rejected CapCut draft from another session with the same revision", async () => {
    const currentCapcutJob = { ...capcutJob, input_ref: "timeline-current", job_id: "capcut-current-timeline" };
    stubCanonicalSubtitleApi();
    vi.mocked(api.listJobs)
      .mockResolvedValueOnce([activeTimelineJob] as never)
      .mockResolvedValue([activeTimelineJob, currentCapcutJob] as never);
    vi.spyOn(api, "startCapcutDraftExport").mockRejectedValue(new Error("request outcome unknown"));
    vi.spyOn(api, "getCapcutDraftExport").mockResolvedValue({
      job_id: currentCapcutJob.job_id, status: "succeeded", export: {
        export_id: "capcut-b", timeline_id: "timeline-a", export_type: "capcut_draft",
        file_uri: "local://draft-b.zip", status: "succeeded", notes: [],
        source_session_id: "session-b", source_session_revision: 7, is_current: true,
      },
    } as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "CapCut 초안 만들기" }));

    expect(await screen.findByText("CapCut 초안을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(screen.getByText("CapCut 초안이 최신 편집본과 달라요.")).toBeVisible();
    expect(screen.queryByText("로컬 저장 위치: local://draft-b.zip")).not.toBeInTheDocument();
  });

  it("shows a CapCut draft request error when refresh only returns the same current artifact", async () => {
    const currentCapcutJob = { ...capcutJob, input_ref: "timeline-current", job_id: "capcut-current-timeline" };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentCapcutJob] as never });
    vi.spyOn(api, "startCapcutDraftExport").mockRejectedValue(new Error("offline before server"));
    vi.spyOn(api, "getCapcutDraftExport").mockResolvedValue({
      job_id: currentCapcutJob.job_id, status: "succeeded", export: {
        export_id: "capcut-current", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft-current.zip", status: "succeeded", notes: [], source_session_id: "session-a", source_session_revision: 7, is_current: true,
      },
    } as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByText("CapCut 초안이 준비되었어요.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "CapCut 초안 만들기" }));

    expect(await screen.findByText("CapCut 초안을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(api.listJobs).toHaveBeenCalledTimes(2);
  });

  it("accepts a rejected CapCut draft request only when refresh finds a new pending job", async () => {
    const pendingCapcutJob = {
      ...capcutJob,
      input_ref: "timeline-current",
      job_id: "capcut-pending",
      status: "pending",
      started_at: "2026-07-23T09:06:00Z",
      finished_at: null,
    };
    stubCanonicalSubtitleApi();
    vi.mocked(api.listJobs)
      .mockResolvedValueOnce([activeTimelineJob] as never)
      .mockResolvedValue([activeTimelineJob, pendingCapcutJob] as never);
    vi.spyOn(api, "startCapcutDraftExport").mockRejectedValue(new Error("request outcome unknown"));
    vi.spyOn(api, "getCapcutDraftExport").mockResolvedValue({
      job_id: pendingCapcutJob.job_id,
      status: "pending",
      export: null,
    } as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "CapCut 초안 만들기" }));

    expect(await screen.findByText("CapCut 초안을 만드는 중이에요.")).toBeVisible();
    expect(screen.queryByText("CapCut 초안을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).not.toBeInTheDocument();
  });

  it("does not present a stale CapCut draft as ready or expose its local URI", async () => {
    const staleCapcutJob = { ...capcutJob, input_ref: "timeline-current" };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, staleCapcutJob] as never });
    vi.spyOn(api, "getCapcutDraftExport").mockResolvedValue({
      job_id: staleCapcutJob.job_id, status: "succeeded", export: {
        export_id: "capcut-stale", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft-stale.zip", status: "succeeded", notes: [],
        source_session_revision: 1, is_current: false, invalidated_at: "2026-07-23T09:10:00Z", invalidated_reason: "editing_session_mutation",
      },
    } as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByText("CapCut 초안이 최신 편집본과 달라요.")).toBeVisible();
    expect(screen.queryByText("CapCut 초안이 준비되었어요.")).not.toBeInTheDocument();
    expect(screen.queryByText("로컬 저장 위치: local://draft-stale.zip")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "CapCut 초안 만들기" })).toBeEnabled();
  });

  it("ignores a CapCut draft from another timeline when choosing the current draft", async () => {
    const oldCapcut = { ...capcutJob, input_ref: "timeline-old", job_id: "capcut-old" };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, oldCapcut] as never });
    const getCapcutDraftExport = vi.spyOn(api, "getCapcutDraftExport");
    const startCapcutDraftExport = vi.spyOn(api, "startCapcutDraftExport").mockResolvedValue({ job_id: "capcut-next", status: "pending" });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByRole("button", { name: "CapCut 초안 만들기" })).toBeEnabled();
    expect(getCapcutDraftExport).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "CapCut 초안 만들기" }));
    await waitFor(() => expect(startCapcutDraftExport).toHaveBeenCalledWith("project_a", { timeline_job_id: "timeline-current" }));
  });

  it("does not present or register a CapCut artifact with mismatched timeline or revision as current", async () => {
    const currentCapcutJob = { ...capcutJob, input_ref: "timeline-current", job_id: "capcut-current-timeline" };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentCapcutJob] as never });
    vi.spyOn(api, "getCapcutDraftExport").mockResolvedValue({
      job_id: currentCapcutJob.job_id, status: "succeeded", export: {
        export_id: "capcut-mismatch", timeline_id: "timeline-other", export_type: "capcut_draft", file_uri: "local://draft-other.zip",
        status: "succeeded", notes: [], source_session_revision: 6, is_current: true,
        handoff: { status: "not_started", source_file_uri: "local://draft-other.zip", reused: false },
      },
    } as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByText("CapCut 초안이 최신 편집본과 달라요.")).toBeVisible();
    expect(screen.queryByText("로컬 저장 위치: local://draft-other.zip")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "CapCut에 등록" })).not.toBeInTheDocument();
  });

  it("fails final and CapCut current checks when the latest session belongs to another project", async () => {
    const currentCapcutJob = { ...capcutJob, input_ref: "timeline-current", job_id: "capcut-current-timeline" };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentFinalJob, currentCapcutJob] as never });
    vi.mocked(api.getLatestEditingSession).mockResolvedValue({ ...editingSession, project_id: "project_b" } as never);
    vi.spyOn(api, "getFinalRender").mockResolvedValue({
      job_id: currentFinalJob.job_id,
      status: "succeeded",
      render: {
        export_id: "final-cross-project",
        timeline_id: "timeline-a",
        export_type: "final_render",
        file_uri: "local://final-cross-project.mp4",
        status: "succeeded",
        source_session_revision: 7,
        is_current: true,
      },
    } as never);
    vi.spyOn(api, "getCapcutDraftExport").mockResolvedValue({
      job_id: currentCapcutJob.job_id,
      status: "succeeded",
      export: {
        export_id: "capcut-cross-project",
        timeline_id: "timeline-a",
        export_type: "capcut_draft",
        file_uri: "local://capcut-cross-project.zip",
        status: "succeeded",
        notes: [],
        source_session_revision: 7,
        is_current: true,
        handoff: { status: "pending", source_file_uri: "local://capcut-cross-project.zip", reused: false },
      },
    } as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByText("완성본이 최신 편집본과 달라요.")).toBeVisible();
    expect(screen.getByText("CapCut 초안이 최신 편집본과 달라요.")).toBeVisible();
    expect(screen.queryByLabelText("완성본 재생")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "CapCut에 등록" })).not.toBeInTheDocument();
  });

  it("does not start another CapCut draft while the current timeline already has one running", async () => {
    const runningCapcut = { ...capcutJob, input_ref: "timeline-current", status: "running", finished_at: null };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, runningCapcut] as never });
    vi.spyOn(api, "getCapcutDraftExport").mockResolvedValue({ job_id: runningCapcut.job_id, status: "running", export: null } as never);
    const startCapcutDraftExport = vi.spyOn(api, "startCapcutDraftExport");

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    const action = await screen.findByRole("button", { name: "CapCut 초안 만들기" });
    expect(action).toBeDisabled();
    fireEvent.click(action);
    expect(startCapcutDraftExport).not.toHaveBeenCalled();
  });

  it("keeps failed CapCut draft export recoverable through an explicit new request", async () => {
    const failedCapcut = { ...capcutJob, input_ref: "timeline-current", status: "failed", error_message: "writer failed" };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, failedCapcut] as never });
    vi.spyOn(api, "getCapcutDraftExport").mockResolvedValue({ job_id: failedCapcut.job_id, status: "failed", export: null, error_message: "writer failed" } as never);
    const startCapcutDraftExport = vi.spyOn(api, "startCapcutDraftExport").mockResolvedValue({ job_id: "capcut-retry", status: "pending" });
    const retryJob = vi.spyOn(api, "retryJob");

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "CapCut 초안 다시 만들기" }));
    await waitFor(() => expect(startCapcutDraftExport).toHaveBeenCalledWith("project_a", { timeline_job_id: "timeline-current" }));
    expect(retryJob).not.toHaveBeenCalled();
  });

  it("starts only one CapCut draft export for rapid double clicks", async () => {
    stubCanonicalSubtitleApi();
    const pendingCapcut = new Promise<{ job_id: string; status: string }>(() => {});
    const startCapcutDraftExport = vi.spyOn(api, "startCapcutDraftExport").mockReturnValue(pendingCapcut as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    const action = await screen.findByRole("button", { name: "CapCut 초안 만들기" });
    fireEvent.click(action);
    fireEvent.click(action);
    expect(startCapcutDraftExport).toHaveBeenCalledTimes(1);
  });

  it("does not let an in-flight project A CapCut draft change project B state", async () => {
    let rejectProjectACapcut!: (error: Error) => void;
    const projectACapcut = new Promise<{ job_id: string; status: string }>((_resolve, reject) => { rejectProjectACapcut = reject; });
    const projectBSession = new Promise<null>(() => {});
    const projectBJobs = new Promise<[]>(() => {});
    vi.spyOn(api, "getLatestEditingSession").mockImplementation((requestedProjectId) => (
      requestedProjectId === "project_b"
        ? projectBSession as never
        : Promise.resolve({ session_id: "session-a", project_id: "project_a", timeline_id: "timeline-a", session_revision: 7 }) as never
    ));
    vi.spyOn(api, "listJobs").mockImplementation((requestedProjectId) => (
      requestedProjectId === "project_b" ? projectBJobs as never : Promise.resolve([activeTimelineJob]) as never
    ));
    vi.spyOn(api, "getTimeline").mockResolvedValue({
      job_id: activeTimelineJob.job_id, status: "succeeded", timeline: {
        timeline_id: "timeline-a", project_id: "project_a", version: "v1", output_mode: "short", review_status: "approved",
        source_session_id: "session-a", source_session_revision: 7,
        tracks: [], review_flags: [], pending_recommendations: [],
      },
    } as never);
    vi.spyOn(api, "getReviewSnapshot").mockResolvedValue({
      project_id: "project_a", timeline_id: "timeline-a", review_status: "approved", segments: [], applied_recommendations: [], pending_recommendations: [], review_flags: [],
    } as never);
    vi.spyOn(api, "getCapcutHandoffDiagnostics").mockResolvedValue(null as never);
    vi.spyOn(api, "startCapcutDraftExport").mockReturnValue(projectACapcut as never);

    const view = render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "CapCut 초안 만들기" }));
    expect(screen.getByRole("button", { name: "CapCut 초안 만드는 중" })).toBeDisabled();

    view.rerender(<OutputsPage projectId="project_b" onOpenEditor={vi.fn()} />);
    rejectProjectACapcut(new Error("offline"));

    await Promise.resolve();
    expect(screen.getByRole("button", { name: "CapCut 초안 만들기" })).toBeDisabled();
    expect(screen.queryByText("CapCut 초안을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "CapCut 초안 만드는 중" })).not.toBeInTheDocument();
  });

  it("does not let a delayed CapCut submission replace a newer manual refresh", async () => {
    stubCanonicalSubtitleApi();
    let resolveSubmissionJobs!: (jobs: typeof activeTimelineJob[]) => void;
    const delayedSubmissionJobs = new Promise<typeof activeTimelineJob[]>((resolve) => { resolveSubmissionJobs = resolve; });
    const submittedCapcut = { ...capcutJob, input_ref: "timeline-current", job_id: "capcut-submitted" };
    const refreshedCapcut = { ...capcutJob, input_ref: "timeline-current", job_id: "capcut-refreshed", started_at: "2026-07-23T09:06:00Z", finished_at: "2026-07-23T09:07:00Z" };
    const listJobs = vi.mocked(api.listJobs);
    listJobs
      .mockResolvedValueOnce([activeTimelineJob] as never)
      .mockReturnValueOnce(delayedSubmissionJobs as never)
      .mockResolvedValue([activeTimelineJob, refreshedCapcut] as never);
    vi.spyOn(api, "startCapcutDraftExport").mockResolvedValue({ job_id: submittedCapcut.job_id, status: "succeeded" });
    vi.spyOn(api, "getCapcutDraftExport").mockImplementation((_projectId, jobId) => Promise.resolve({
      job_id: jobId, status: "succeeded", export: { export_id: jobId, timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: `local://${jobId}.zip`, status: "succeeded", notes: [], source_session_id: "session-a", source_session_revision: 7, is_current: true },
    }) as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "CapCut 초안 만들기" }));
    await waitFor(() => expect(listJobs).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole("button", { name: "상태 다시 확인" }));
    expect(await screen.findByText("로컬 저장 위치: local://capcut-refreshed.zip")).toBeVisible();

    resolveSubmissionJobs([activeTimelineJob, submittedCapcut] as never);
    await waitFor(() => expect(api.getCapcutDraftExport).toHaveBeenCalledWith("project_a", "capcut-submitted"));
    await waitFor(() => expect(screen.getByText("로컬 저장 위치: local://capcut-refreshed.zip")).toBeVisible());
  });

  it("does not surface an older CapCut export failure after a newer manual refresh", async () => {
    stubCanonicalSubtitleApi();
    const currentCapcutJob = { ...capcutJob, input_ref: "timeline-current", job_id: "capcut-current-timeline" };
    let rejectCapcut!: (error: Error) => void;
    const pendingCapcut = new Promise((_resolve, reject) => { rejectCapcut = reject; });
    vi.spyOn(api, "startCapcutDraftExport").mockReturnValue(pendingCapcut as never);
    vi.mocked(api.listJobs)
      .mockResolvedValueOnce([activeTimelineJob] as never)
      .mockResolvedValue([activeTimelineJob, currentCapcutJob] as never);
    vi.spyOn(api, "getCapcutDraftExport").mockResolvedValue({
      job_id: currentCapcutJob.job_id,
      status: "succeeded",
      export: {
        export_id: "capcut-current",
        timeline_id: "timeline-a",
        export_type: "capcut_draft",
        file_uri: "local://capcut-current.zip",
        status: "succeeded",
        notes: [],
        source_session_id: "session-a",
        source_session_revision: 7,
        is_current: true,
      },
    } as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "CapCut 초안 만들기" }));
    fireEvent.click(screen.getByRole("button", { name: "상태 다시 확인" }));
    expect(await screen.findByText("로컬 저장 위치: local://capcut-current.zip")).toBeVisible();
    await act(async () => {
      rejectCapcut(new Error("offline"));
      await Promise.resolve();
    });

    expect(screen.queryByText("CapCut 초안을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).not.toBeInTheDocument();
    expect(screen.getByText("로컬 저장 위치: local://capcut-current.zip")).toBeVisible();
  });

  it("surfaces a CapCut export failure after a manual refresh when no durable progress exists", async () => {
    stubCanonicalSubtitleApi();
    let rejectCapcut!: (error: Error) => void;
    const pendingCapcut = new Promise((_resolve, reject) => { rejectCapcut = reject; });
    vi.spyOn(api, "startCapcutDraftExport").mockReturnValue(pendingCapcut as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "CapCut 초안 만들기" }));
    fireEvent.click(screen.getByRole("button", { name: "상태 다시 확인" }));
    await waitFor(() => expect(api.listJobs).toHaveBeenCalledTimes(2));
    await act(async () => {
      rejectCapcut(new Error("offline"));
      await Promise.resolve();
    });

    expect(await screen.findByText("CapCut 초안을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
  });

  it("registers only the current CapCut draft after an explicit click and refreshes its typed handoff", async () => {
    const currentCapcutJob = { ...capcutJob, input_ref: "timeline-current", job_id: "capcut-current-timeline" };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentCapcutJob] as never });
    const getCapcutDraftExport = vi.spyOn(api, "getCapcutDraftExport")
      .mockResolvedValueOnce({
        job_id: currentCapcutJob.job_id, status: "succeeded", export: {
          export_id: "capcut-current", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft-current.zip", status: "succeeded", notes: [], source_session_id: "session-a", source_session_revision: 7, is_current: true,
          handoff: { status: "pending", source_file_uri: "local://draft-current.zip", reused: false },
        },
      } as never)
      .mockResolvedValueOnce({
        job_id: currentCapcutJob.job_id, status: "succeeded", export: {
          export_id: "capcut-current", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft-current.zip", status: "succeeded", notes: [], source_session_id: "session-a", source_session_revision: 7, is_current: true,
          handoff: { status: "ready", source_file_uri: "local://draft-current.zip", registered_project_path: "local://capcut/project", reused: false },
        },
      } as never);
    const registerCapcutDraftHandoff = vi.spyOn(api, "registerCapcutDraftHandoff").mockResolvedValue({
      handoff: { status: "ready", source_file_uri: "local://draft-current.zip", registered_project_path: "local://capcut/project", reused: false },
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByRole("button", { name: "CapCut에 등록" })).toBeEnabled();
    expect(registerCapcutDraftHandoff).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "CapCut에 등록" }));

    await waitFor(() => expect(registerCapcutDraftHandoff).toHaveBeenCalledWith("project_a", "capcut-current-timeline"));
    await waitFor(() => expect(getCapcutDraftExport).toHaveBeenLastCalledWith("project_a", "capcut-current-timeline"));
    expect(await screen.findByText("CapCut 등록 상태가 준비되었어요.")).toBeVisible();
    expect(screen.getByText("실제 CapCut Desktop에서 열기와 가져오기는 별도로 확인해야 해요.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "CapCut에 등록" })).not.toBeInTheDocument();
  });

  it("shows another durable CapCut registration as in progress without issuing a duplicate POST", async () => {
    const currentCapcutJob = { ...capcutJob, input_ref: "timeline-current", job_id: "capcut-current-timeline" };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentCapcutJob] as never });
    vi.spyOn(api, "getCapcutDraftExport").mockResolvedValue({
      job_id: currentCapcutJob.job_id, status: "succeeded", export: {
        export_id: "capcut-current", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft-current.zip", status: "succeeded", notes: [], source_session_id: "session-a", source_session_revision: 7, is_current: true,
        handoff: { status: "in_progress", source_file_uri: "local://draft-current.zip", reused: false, recoverable: false, recoverable_at: "2099-01-01T00:00:00+00:00" },
      },
    } as never);
    const registerCapcutDraftHandoff = vi.spyOn(api, "registerCapcutDraftHandoff");

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByText("CapCut 등록이 진행 중이에요. 잠시 후 상태를 다시 확인해 주세요.")).toBeVisible();
    expect(screen.queryByRole("button", { name: /CapCut에 등록|CapCut 등록 다시 시도/ })).not.toBeInTheDocument();
    expect(registerCapcutDraftHandoff).not.toHaveBeenCalled();
  });

  it("does not expose CapCut registration for a stale draft", async () => {
    const staleCapcutJob = { ...capcutJob, input_ref: "timeline-current" };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, staleCapcutJob] as never });
    vi.spyOn(api, "getCapcutDraftExport").mockResolvedValue({
      job_id: staleCapcutJob.job_id, status: "succeeded", export: {
        export_id: "capcut-stale", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft-stale.zip", status: "succeeded", notes: [], is_current: false,
        handoff: { status: "pending", source_file_uri: "local://draft-stale.zip", reused: false },
      },
    } as never);
    const registerCapcutDraftHandoff = vi.spyOn(api, "registerCapcutDraftHandoff");

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByText("CapCut 초안이 최신 편집본과 달라요.")).toBeVisible();
    expect(screen.queryByRole("button", { name: /CapCut에 등록|CapCut 등록 다시 시도/ })).not.toBeInTheDocument();
    expect(registerCapcutDraftHandoff).not.toHaveBeenCalled();
  });

  it("does not expose CapCut registration when the current export artifact did not succeed", async () => {
    const currentCapcutJob = { ...capcutJob, input_ref: "timeline-current", job_id: "capcut-current-timeline" };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentCapcutJob] as never });
    vi.spyOn(api, "getCapcutDraftExport").mockResolvedValue({
      job_id: currentCapcutJob.job_id, status: "succeeded", export: {
        export_id: "capcut-current", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft-current.zip", status: "failed", notes: [], is_current: true,
        handoff: { status: "pending", source_file_uri: "local://draft-current.zip", reused: false },
      },
    } as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByText("CapCut 초안이 최신 편집본과 달라요.")).toBeVisible();
    expect(screen.queryByRole("button", { name: /CapCut에 등록|CapCut 등록 다시 시도/ })).not.toBeInTheDocument();
  });

  it("keeps a failed current CapCut registration recoverable only by another explicit click", async () => {
    const currentCapcutJob = { ...capcutJob, input_ref: "timeline-current", job_id: "capcut-current-timeline" };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentCapcutJob] as never });
    vi.spyOn(api, "getCapcutDraftExport").mockResolvedValue({
      job_id: currentCapcutJob.job_id, status: "succeeded", export: {
        export_id: "capcut-current", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft-current.zip", status: "succeeded", notes: [], source_session_id: "session-a", source_session_revision: 7, is_current: true,
        handoff: { status: "failed", source_file_uri: "local://draft-current.zip", error_message: "write failed", reused: false },
      },
    } as never);
    const registerCapcutDraftHandoff = vi.spyOn(api, "registerCapcutDraftHandoff").mockResolvedValue({
      handoff: { status: "failed", source_file_uri: "local://draft-current.zip", error_message: "write failed", reused: false },
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    const action = await screen.findByRole("button", { name: "CapCut 등록 다시 시도" });
    expect(screen.getByText("CapCut 등록을 완료하지 못했어요. 상태를 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(registerCapcutDraftHandoff).not.toHaveBeenCalled();
    fireEvent.click(action);
    await waitFor(() => expect(registerCapcutDraftHandoff).toHaveBeenCalledTimes(1));
    await Promise.resolve();
    expect(registerCapcutDraftHandoff).toHaveBeenCalledTimes(1);
  });

  it("starts only one current CapCut registration for rapid double clicks", async () => {
    const currentCapcutJob = { ...capcutJob, input_ref: "timeline-current", job_id: "capcut-current-timeline" };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentCapcutJob] as never });
    vi.spyOn(api, "getCapcutDraftExport").mockResolvedValue({
      job_id: currentCapcutJob.job_id, status: "succeeded", export: {
        export_id: "capcut-current", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft-current.zip", status: "succeeded", notes: [], source_session_id: "session-a", source_session_revision: 7, is_current: true,
        handoff: { status: "pending", source_file_uri: "local://draft-current.zip", reused: false },
      },
    } as never);
    const pendingHandoff = new Promise<{ handoff: { status: string; source_file_uri: string; reused: boolean } }>(() => {});
    const registerCapcutDraftHandoff = vi.spyOn(api, "registerCapcutDraftHandoff").mockReturnValue(pendingHandoff as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    const action = await screen.findByRole("button", { name: "CapCut에 등록" });
    fireEvent.click(action);
    fireEvent.click(action);
    expect(registerCapcutDraftHandoff).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "CapCut 등록 중" })).toBeDisabled();
  });

  it("refetches the durable in-progress CapCut handoff after its typed 400 response", async () => {
    const currentCapcutJob = { ...capcutJob, input_ref: "timeline-current", job_id: "capcut-current-timeline" };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentCapcutJob] as never });
    vi.spyOn(api, "getCapcutDraftExport")
      .mockResolvedValueOnce({
        job_id: currentCapcutJob.job_id, status: "succeeded", export: {
          export_id: "capcut-current", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft-current.zip", status: "succeeded", notes: [], source_session_id: "session-a", source_session_revision: 7, is_current: true,
          handoff: { status: "pending", source_file_uri: "local://draft-current.zip", reused: false },
        },
      } as never)
      .mockResolvedValueOnce({
        job_id: currentCapcutJob.job_id, status: "succeeded", export: {
          export_id: "capcut-current", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft-current.zip", status: "succeeded", notes: [], source_session_id: "session-a", source_session_revision: 7, is_current: true,
          handoff: { status: "in_progress", source_file_uri: "local://draft-current.zip", reused: false, recoverable: false },
        },
      } as never);
    vi.spyOn(api, "registerCapcutDraftHandoff").mockRejectedValue(Object.assign(
      new Error("Request failed: handoff (400)"),
      { code: "capcut_draft_handoff_in_progress" },
    ));

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "CapCut에 등록" }));
    expect(await screen.findByText("CapCut 등록이 진행 중이에요. 잠시 후 상태를 다시 확인해 주세요.")).toBeVisible();
    expect(screen.queryByText("CapCut 등록 상태를 확인하지 못했어요. 상태를 다시 확인한 뒤 시도해 주세요.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /CapCut에 등록|CapCut 등록 다시 시도/ })).not.toBeInTheDocument();
  });

  it("reconciles a rejected CapCut handoff from authoritative ready state before showing an error", async () => {
    const currentCapcutJob = { ...capcutJob, input_ref: "timeline-current", job_id: "capcut-current-timeline" };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentCapcutJob] as never });
    vi.spyOn(api, "getCapcutDraftExport")
      .mockResolvedValueOnce({
        job_id: currentCapcutJob.job_id, status: "succeeded", export: {
          export_id: "capcut-current", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft-current.zip", status: "succeeded", notes: [], source_session_id: "session-a", source_session_revision: 7, is_current: true,
          handoff: { status: "pending", source_file_uri: "local://draft-current.zip", reused: false },
        },
      } as never)
      .mockResolvedValue({
        job_id: currentCapcutJob.job_id, status: "succeeded", export: {
          export_id: "capcut-current", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft-current.zip", status: "succeeded", notes: [], source_session_id: "session-a", source_session_revision: 7, is_current: true,
          handoff: { status: "ready", source_file_uri: "local://draft-current.zip", reused: true },
        },
      } as never);
    vi.spyOn(api, "registerCapcutDraftHandoff").mockRejectedValue(new Error("request outcome unknown"));

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "CapCut에 등록" }));

    expect(await screen.findByText("기존 CapCut 등록 정보를 다시 사용해요.")).toBeVisible();
    expect(screen.queryByText("CapCut 등록 상태를 확인하지 못했어요. 상태를 다시 확인한 뒤 시도해 주세요.")).not.toBeInTheDocument();
    expect(api.listJobs).toHaveBeenCalledTimes(2);
  });

  it("does not reconcile a rejected CapCut handoff from another session with the same revision", async () => {
    const currentCapcutJob = { ...capcutJob, input_ref: "timeline-current", job_id: "capcut-current-timeline" };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentCapcutJob] as never });
    vi.spyOn(api, "getCapcutDraftExport")
      .mockResolvedValueOnce({
        job_id: currentCapcutJob.job_id, status: "succeeded", export: {
          export_id: "capcut-current", timeline_id: "timeline-a", export_type: "capcut_draft",
          file_uri: "local://draft-current.zip", status: "succeeded", notes: [],
          source_session_id: "session-a", source_session_revision: 7, is_current: true,
          handoff: { status: "pending", source_file_uri: "local://draft-current.zip", reused: false },
        },
      } as never)
      .mockResolvedValue({
        job_id: currentCapcutJob.job_id, status: "succeeded", export: {
          export_id: "capcut-current", timeline_id: "timeline-a", export_type: "capcut_draft",
          file_uri: "local://draft-current.zip", status: "succeeded", notes: [],
          source_session_id: "session-b", source_session_revision: 7, is_current: true,
          handoff: { status: "ready", source_file_uri: "local://draft-current.zip", reused: true },
        },
      } as never);
    vi.spyOn(api, "registerCapcutDraftHandoff").mockRejectedValue(new Error("request outcome unknown"));

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "CapCut에 등록" }));

    expect(await screen.findByText("CapCut 등록 상태를 확인하지 못했어요. 상태를 다시 확인한 뒤 시도해 주세요.")).toBeVisible();
    expect(screen.getByText("CapCut 초안이 최신 편집본과 달라요.")).toBeVisible();
    expect(screen.queryByText("기존 CapCut 등록 정보를 다시 사용해요.")).not.toBeInTheDocument();
  });

  it("shows a CapCut handoff request error when refresh only returns the same failed handoff", async () => {
    const currentCapcutJob = { ...capcutJob, input_ref: "timeline-current", job_id: "capcut-current-timeline" };
    const failedDraft = {
      job_id: currentCapcutJob.job_id, status: "succeeded", export: {
        export_id: "capcut-current", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft-current.zip", status: "succeeded", notes: [], source_session_id: "session-a", source_session_revision: 7, is_current: true,
        handoff: { status: "failed", source_file_uri: "local://draft-current.zip", error_message: "write failed", reused: false },
      },
    };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentCapcutJob] as never });
    vi.spyOn(api, "getCapcutDraftExport").mockResolvedValue(failedDraft as never);
    vi.spyOn(api, "registerCapcutDraftHandoff").mockRejectedValue(new Error("offline before server"));

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "CapCut 등록 다시 시도" }));

    expect(await screen.findByText("CapCut 등록 상태를 확인하지 못했어요. 상태를 다시 확인한 뒤 시도해 주세요.")).toBeVisible();
    expect(api.listJobs).toHaveBeenCalledTimes(2);
  });

  it("does not let a delayed CapCut registration replace a newer manual refresh", async () => {
    const currentCapcutJob = { ...capcutJob, input_ref: "timeline-current", job_id: "capcut-current-timeline" };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentCapcutJob] as never });
    let resolveStaleHandoff!: (value: unknown) => void;
    const staleHandoff = new Promise((resolve) => { resolveStaleHandoff = resolve; });
    vi.spyOn(api, "getCapcutDraftExport")
      .mockResolvedValueOnce({
        job_id: currentCapcutJob.job_id, status: "succeeded", export: {
          export_id: "capcut-current", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft-current.zip", status: "succeeded", notes: [], source_session_id: "session-a", source_session_revision: 7, is_current: true,
          handoff: { status: "pending", source_file_uri: "local://draft-current.zip", reused: false },
        },
      } as never)
      .mockReturnValueOnce(staleHandoff as never)
      .mockResolvedValueOnce({
        job_id: currentCapcutJob.job_id, status: "succeeded", export: {
          export_id: "capcut-current", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft-current.zip", status: "succeeded", notes: [], source_session_id: "session-a", source_session_revision: 7, is_current: true,
          handoff: { status: "ready", source_file_uri: "local://draft-current.zip", reused: true },
        },
      } as never)
      .mockResolvedValue({
        job_id: currentCapcutJob.job_id, status: "succeeded", export: {
          export_id: "capcut-current", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft-current.zip", status: "succeeded", notes: [], source_session_id: "session-a", source_session_revision: 7, is_current: true,
          handoff: { status: "ready", source_file_uri: "local://draft-current.zip", reused: true },
        },
      } as never);
    vi.spyOn(api, "registerCapcutDraftHandoff").mockResolvedValue({
      handoff: { status: "failed", source_file_uri: "local://draft-current.zip", error_message: "old response", reused: false },
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "CapCut에 등록" }));
    await waitFor(() => expect(api.getCapcutDraftExport).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole("button", { name: "상태 다시 확인" }));
    expect(await screen.findByText("기존 CapCut 등록 정보를 다시 사용해요.")).toBeVisible();

    await act(async () => {
      resolveStaleHandoff({
        job_id: currentCapcutJob.job_id, status: "succeeded", export: {
          export_id: "capcut-current", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft-current.zip", status: "succeeded", notes: [], source_session_id: "session-a", source_session_revision: 7, is_current: true,
          handoff: { status: "failed", source_file_uri: "local://draft-current.zip", error_message: "old response", reused: false },
        },
      });
      await Promise.resolve();
    });

    expect(screen.getByText("기존 CapCut 등록 정보를 다시 사용해요.")).toBeVisible();
    expect(screen.queryByText("CapCut 등록을 완료하지 못했어요. 상태를 확인한 뒤 다시 시도해 주세요.")).not.toBeInTheDocument();
  });

  it("does not surface an older CapCut registration failure after a newer manual refresh", async () => {
    const currentCapcutJob = { ...capcutJob, input_ref: "timeline-current", job_id: "capcut-current-timeline" };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentCapcutJob] as never });
    const readyDraft = {
      job_id: currentCapcutJob.job_id,
      status: "succeeded",
      export: {
        export_id: "capcut-current",
        timeline_id: "timeline-a",
        export_type: "capcut_draft",
        file_uri: "local://draft-current.zip",
        status: "succeeded",
        notes: [],
        source_session_id: "session-a",
        source_session_revision: 7,
        is_current: true,
        handoff: { status: "ready", source_file_uri: "local://draft-current.zip", reused: true },
      },
    };
    vi.spyOn(api, "getCapcutDraftExport")
      .mockResolvedValueOnce({
        ...readyDraft,
        export: { ...readyDraft.export, handoff: { status: "pending", source_file_uri: "local://draft-current.zip", reused: false } },
      } as never)
      .mockResolvedValue(readyDraft as never);
    let rejectHandoff!: (error: Error) => void;
    const pendingHandoff = new Promise((_resolve, reject) => { rejectHandoff = reject; });
    vi.spyOn(api, "registerCapcutDraftHandoff").mockReturnValue(pendingHandoff as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "CapCut에 등록" }));
    fireEvent.click(screen.getByRole("button", { name: "상태 다시 확인" }));
    expect(await screen.findByText("기존 CapCut 등록 정보를 다시 사용해요.")).toBeVisible();
    await act(async () => {
      rejectHandoff(new Error("offline"));
      await Promise.resolve();
    });

    expect(screen.queryByText("CapCut 등록 상태를 확인하지 못했어요. 상태를 다시 확인한 뒤 시도해 주세요.")).not.toBeInTheDocument();
    expect(screen.getByText("기존 CapCut 등록 정보를 다시 사용해요.")).toBeVisible();
  });

  it("surfaces a CapCut registration failure after a manual refresh when no durable progress exists", async () => {
    const currentCapcutJob = { ...capcutJob, input_ref: "timeline-current", job_id: "capcut-current-timeline" };
    const pendingDraft = {
      job_id: currentCapcutJob.job_id,
      status: "succeeded",
      export: {
        export_id: "capcut-current",
        timeline_id: "timeline-a",
        export_type: "capcut_draft",
        file_uri: "local://draft-current.zip",
        status: "succeeded",
        notes: [],
        source_session_id: "session-a",
        source_session_revision: 7,
        is_current: true,
        handoff: { status: "pending", source_file_uri: "local://draft-current.zip", reused: false },
      },
    };
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentCapcutJob] as never });
    vi.spyOn(api, "getCapcutDraftExport").mockResolvedValue(pendingDraft as never);
    let rejectHandoff!: (error: Error) => void;
    const pendingHandoff = new Promise((_resolve, reject) => { rejectHandoff = reject; });
    vi.spyOn(api, "registerCapcutDraftHandoff").mockReturnValue(pendingHandoff as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "CapCut에 등록" }));
    fireEvent.click(screen.getByRole("button", { name: "상태 다시 확인" }));
    await waitFor(() => expect(api.getCapcutDraftExport).toHaveBeenCalledTimes(2));
    await act(async () => {
      rejectHandoff(new Error("offline"));
      await Promise.resolve();
    });

    expect(await screen.findByText("CapCut 등록 상태를 확인하지 못했어요. 상태를 다시 확인한 뒤 시도해 주세요.")).toBeVisible();
  });

  it("does not let an in-flight project A CapCut registration change project B state", async () => {
    const currentCapcutJob = { ...capcutJob, input_ref: "timeline-current", job_id: "capcut-current-timeline" };
    let rejectProjectAHandoff!: (error: Error) => void;
    const projectAHandoff = new Promise<{ handoff: { status: string; source_file_uri: string; reused: boolean } }>((_resolve, reject) => { rejectProjectAHandoff = reject; });
    const projectBSession = new Promise<null>(() => {});
    const projectBJobs = new Promise<[]>(() => {});
    vi.spyOn(api, "getLatestEditingSession").mockImplementation((requestedProjectId) => (
      requestedProjectId === "project_b"
        ? projectBSession as never
        : Promise.resolve({
            session_id: "session-a",
            project_id: "project_a",
            timeline_id: "timeline-a",
            session_revision: 7,
            segments: [],
            history: [],
          }) as never
    ));
    vi.spyOn(api, "listJobs").mockImplementation((requestedProjectId) => (
      requestedProjectId === "project_b" ? projectBJobs as never : Promise.resolve([activeTimelineJob, currentCapcutJob]) as never
    ));
    vi.spyOn(api, "getTimeline").mockResolvedValue({
      job_id: activeTimelineJob.job_id, status: "succeeded", timeline: {
        timeline_id: "timeline-a", project_id: "project_a", version: "v1", output_mode: "short", review_status: "approved",
        source_session_id: "session-a", source_session_revision: 7,
        tracks: [], review_flags: [], pending_recommendations: [],
      },
    } as never);
    vi.spyOn(api, "getReviewSnapshot").mockResolvedValue({
      project_id: "project_a", timeline_id: "timeline-a", review_status: "approved", segments: [], applied_recommendations: [], pending_recommendations: [], review_flags: [],
    } as never);
    vi.spyOn(api, "getCapcutDraftExport").mockResolvedValue({
      job_id: currentCapcutJob.job_id, status: "succeeded", export: {
        export_id: "capcut-current", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft-current.zip", status: "succeeded", notes: [], source_session_id: "session-a", source_session_revision: 7, is_current: true,
        handoff: { status: "pending", source_file_uri: "local://draft-current.zip", reused: false },
      },
    } as never);
    vi.spyOn(api, "getCapcutHandoffDiagnostics").mockResolvedValue(null as never);
    vi.spyOn(api, "registerCapcutDraftHandoff").mockReturnValue(projectAHandoff as never);

    const view = render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "CapCut에 등록" }));
    expect(screen.getByRole("button", { name: "CapCut 등록 중" })).toBeDisabled();

    view.rerender(<OutputsPage projectId="project_b" onOpenEditor={vi.fn()} />);
    await act(async () => {
      rejectProjectAHandoff(new Error("offline"));
      await Promise.resolve();
    });

    expect(screen.queryByRole("button", { name: "CapCut 등록 중" })).not.toBeInTheDocument();
    expect(screen.queryByText("CapCut 등록 상태를 확인하지 못했어요. 상태를 다시 확인한 뒤 시도해 주세요.")).not.toBeInTheDocument();
  });

  it("keeps historical outputs read-only and does not label them current without an editing session", async () => {
    stubReadOnlyOutputApi();
    const openEditor = vi.fn();
    const startFinalRender = vi.spyOn(api, "startFinalRender");
    const startCapcutDraftExport = vi.spyOn(api, "startCapcutDraftExport");
    const registerCapcutDraftHandoff = vi.spyOn(api, "registerCapcutDraftHandoff");

    render(<OutputsPage projectId="project_a" onOpenEditor={openEditor} />);

    expect(await screen.findByText("완성본이 최신 편집본과 달라요.")).toBeVisible();
    expect(screen.queryByLabelText("완성본 재생")).not.toBeInTheDocument();
    expect(screen.getByText("아직 CapCut 초안이 없어요.")).toBeVisible();
    expect(startFinalRender).not.toHaveBeenCalled();
    expect(startCapcutDraftExport).not.toHaveBeenCalled();
    expect(registerCapcutDraftHandoff).not.toHaveBeenCalled();
  });

  it("constrains a playable final video to its output card", async () => {
    stubCanonicalSubtitleApi({ reviewStatus: "approved", jobs: [activeTimelineJob, { ...finalJob, input_ref: "timeline-current" }] as never });
    vi.spyOn(api, "getFinalRender").mockResolvedValue({
      job_id: finalJob.job_id, status: "succeeded", render: {
      export_id: "final-current", timeline_id: "timeline-a", export_type: "final_render", file_uri: "local://final.mp4", status: "succeeded", is_current: true,
      source_session_id: "session-a", source_session_revision: 7,
      },
    });
    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);
    expect(await screen.findByLabelText("완성본 재생")).toHaveClass("vb-output-video");
  });

  it("shows an ordered readiness checklist with a resolving action when output is blocked", async () => {
    stubReadOnlyOutputApi();
    const onOpenEditor = vi.fn();

    render(<OutputsPage projectId="project_a" onOpenEditor={onOpenEditor} />);

    const checklist = await screen.findByRole("region", { name: "출력 준비 체크리스트" });
    expect(checklist).toBeVisible();
    expect(screen.getByRole("list", { name: "출력 준비 단계" })).toBeVisible();
    expect(within(checklist).getByText("편집본")).toBeVisible();
    expect(within(checklist).getByText("준비 필요")).toBeVisible();
    expect(within(checklist).getByText("검토")).toBeVisible();
    expect(within(checklist).getByText("승인 필요")).toBeVisible();
    expect(within(checklist).getByText("출력")).toBeVisible();
    expect(within(checklist).getByText("앞 단계 완료 필요")).toBeVisible();
    expect(within(checklist).queryByText("편집본을 먼저 준비해 주세요.")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "편집 화면 열기" }));
    expect(onOpenEditor).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "자막 만들기" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "완성본 만들기" })).toBeDisabled();
  });

  it("uses keyword statuses when the draft and review are ready but output still waits", async () => {
    stubCanonicalSubtitleApi({ reviewFlags: [{ code: "review_required", segment_id: "segment-a", message: "확인이 필요해요." }] });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    const checklist = await screen.findByRole("region", { name: "출력 준비 체크리스트" });
    expect(within(checklist).getByText("준비됨")).toBeVisible();
    expect(within(checklist).getByText("승인됨")).toBeVisible();
    expect(within(checklist).getByText("앞 단계 완료 필요")).toBeVisible();
    expect(within(checklist).queryByText("현재 편집본이 준비되었어요.")).not.toBeInTheDocument();
    expect(within(checklist).queryByText("현재 편집본 검토가 승인되었어요.")).not.toBeInTheDocument();
  });

  it("fails closed when the active session lookup fails", async () => {
    stubReadOnlyOutputApi();
    vi.spyOn(api, "getLatestEditingSession").mockRejectedValue(new Error("offline"));

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByText("출력 상태를 불러오지 못했어요.")).toBeVisible();
    expect(screen.queryByLabelText("완성본 재생")).not.toBeInTheDocument();
  });

  it("labels an old final as stale and keeps recovery in the editor", async () => {
    stubReadOnlyOutputApi();
    vi.spyOn(api, "getFinalRender").mockResolvedValue({
      job_id: finalJob.job_id, status: "succeeded", render: {
        export_id: "final-a", timeline_id: "timeline-a", export_type: "final_render", file_uri: "local://final.mp4", status: "succeeded", is_current: false,
      },
    });
    const openEditor = vi.fn();

    render(<OutputsPage projectId="project_a" onOpenEditor={openEditor} />);

    expect(await screen.findByText("완성본이 최신 편집본과 달라요.")).toBeVisible();
    expect(screen.getByText("편집에서 새 완성본 만들기를 실행해 주세요.")).toBeVisible();
    expect(screen.queryByLabelText("완성본 재생")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "편집 열기" }));
    expect(openEditor).toHaveBeenCalledOnce();
  });

  it("keeps a failed status read recoverable without offering output mutations", async () => {
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(null);
    const listJobs = vi.spyOn(api, "listJobs").mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce([]);
    const startFinalRender = vi.spyOn(api, "startFinalRender");
    const startCapcutDraftExport = vi.spyOn(api, "startCapcutDraftExport");

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByText("출력 상태를 불러오지 못했어요.")).toBeVisible();
    expect(screen.getByText("잠시 후 상태를 다시 확인하거나 편집 화면에서 작업을 이어가세요.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "상태 다시 확인" }));
    await waitFor(() => expect(listJobs).toHaveBeenCalledTimes(2));
    expect(startFinalRender).not.toHaveBeenCalled();
    expect(startCapcutDraftExport).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "자막 만들기" })).toBeDisabled();
  });

  it("does not let a delayed project A status response replace project B", async () => {
    let resolveProjectA!: (jobs: typeof finalJob[]) => void;
    const projectAJobs = new Promise<typeof finalJob[]>((resolve) => { resolveProjectA = resolve; });
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue(null);
    vi.spyOn(api, "listJobs").mockReturnValueOnce(projectAJobs).mockResolvedValueOnce([]);
    const getFinalRender = vi.spyOn(api, "getFinalRender").mockResolvedValue({
      job_id: finalJob.job_id, status: "succeeded", render: {
        export_id: "final-a", timeline_id: "timeline-a", export_type: "final_render", file_uri: "local://final.mp4", status: "succeeded", is_current: true,
      },
    });
    vi.spyOn(api, "getCapcutHandoffDiagnostics").mockResolvedValue({
      status: "ready", is_supported: true, project_root_path: "local://capcut", project_root_exists: true, write_access: true, checked_at: "2026-07-23T09:01:00Z",
    });

    const view = render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);
    view.rerender(<OutputsPage projectId="project_b" onOpenEditor={vi.fn()} />);
    expect(await screen.findByText("아직 완성본이 없어요.")).toBeVisible();

    resolveProjectA([finalJob]);
    await waitFor(() => expect(getFinalRender).not.toHaveBeenCalled());
    expect(screen.getByText("아직 완성본이 없어요.")).toBeVisible();
    expect(screen.queryByText("완성본을 확인할 수 있어요.")).not.toBeInTheDocument();
  });

  it("owns the current exact-preview reference without mounting a second player", async () => {
    stubCanonicalSubtitleApi();
    vi.mocked(api.getEditorPlaybackManifest).mockResolvedValue(playbackManifest() as never);
    const onOpenEditor = vi.fn();

    render(<OutputsPage projectId="project_a" onOpenEditor={onOpenEditor} />);

    expect(await screen.findByText("현재 편집본 미리보기가 준비되었어요.")).toBeVisible();
    expect(api.getEditorPlaybackManifest).toHaveBeenCalledWith("project_a", "session-a");
    expect(document.querySelector("audio, video")).toBeNull();
    expect(document.body).not.toHaveTextContent("/exact-previews/");
    fireEvent.click(screen.getByRole("button", { name: "편집에서 미리보기 열기" }));
    expect(onOpenEditor).toHaveBeenCalledOnce();
  });

  it.each([
    ["pending", "미리보기를 준비하고 있어요."],
    ["running", "미리보기를 준비하고 있어요."],
    ["failed", "미리보기를 만들지 못했어요."],
    ["unavailable", "아직 미리보기가 없어요."],
  ])("keeps an exact preview in %s creator-safe and read-only", async (status, copy) => {
    stubCanonicalSubtitleApi();
    const renderSubtitle = vi.spyOn(api, "renderSubtitle");
    const startFinalRender = vi.spyOn(api, "startFinalRender");
    const startCapcutDraftExport = vi.spyOn(api, "startCapcutDraftExport");
    const registerCapcutDraftHandoff = vi.spyOn(api, "registerCapcutDraftHandoff");
    vi.mocked(api.getEditorPlaybackManifest).mockResolvedValue(playbackManifest({
      exactPreview: {
        status,
        url: null,
        source_session_id: editingSession.session_id,
        source_session_revision: editingSession.session_revision,
      },
    }) as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByText(copy)).toBeVisible();
    expect(document.querySelector("audio, video")).toBeNull();
    expect(renderSubtitle).not.toHaveBeenCalled();
    expect(startFinalRender).not.toHaveBeenCalled();
    expect(startCapcutDraftExport).not.toHaveBeenCalled();
    expect(registerCapcutDraftHandoff).not.toHaveBeenCalled();
  });

  it("fails closed when an exact-preview response uses the non-backend current status", async () => {
    stubCanonicalSubtitleApi();
    vi.mocked(api.getEditorPlaybackManifest).mockResolvedValue(playbackManifest({
      exactPreview: {
        status: "current",
        url: "/api/projects/project_a/exact-previews/noncanonical/content",
        source_session_id: editingSession.session_id,
        source_session_revision: editingSession.session_revision,
        artifact_revision: editingSession.session_revision,
      },
    }) as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByText("미리보기가 최신 편집본과 달라요.")).toBeVisible();
    expect(document.body).not.toHaveTextContent("/exact-previews/noncanonical");
  });

  it("treats an older exact-preview revision as stale and recovers only after an explicit refresh", async () => {
    stubCanonicalSubtitleApi();
    vi.mocked(api.getEditorPlaybackManifest)
      .mockResolvedValueOnce(playbackManifest({
        exactPreview: {
          status: "succeeded",
          url: "/api/projects/project_a/exact-previews/old/content",
          source_session_id: "session-a",
          source_session_revision: 6,
          artifact_revision: 6,
        },
      }) as never)
      .mockResolvedValueOnce(playbackManifest() as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByText("미리보기가 최신 편집본과 달라요.")).toBeVisible();
    expect(document.body).not.toHaveTextContent("/exact-previews/old");
    fireEvent.click(screen.getByRole("button", { name: "상태 다시 확인" }));
    expect(await screen.findByText("현재 편집본 미리보기가 준비되었어요.")).toBeVisible();
    expect(api.getEditorPlaybackManifest).toHaveBeenCalledTimes(2);
  });

  it("keeps retained final output visible when the exact-preview status read fails", async () => {
    stubCanonicalSubtitleApi({ jobs: [activeTimelineJob, currentFinalJob] as never });
    vi.mocked(api.getEditorPlaybackManifest).mockRejectedValue(new Error("manifest unavailable"));
    vi.spyOn(api, "getFinalRender").mockResolvedValue({
      job_id: currentFinalJob.job_id,
      status: "succeeded",
      render: {
        export_id: "final-current-timeline",
        timeline_id: "timeline-a",
        export_type: "final_render",
        file_uri: "local://final.mp4",
        status: "succeeded",
        source_session_id: "session-a",
        source_session_revision: 7,
        is_current: true,
      },
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByText("미리보기 상태를 지금 확인할 수 없어요.")).toBeVisible();
    expect(screen.getByLabelText("완성본 재생")).toBeVisible();
  });

  it("does not let a delayed project A exact-preview response replace project B", async () => {
    let resolveA!: (value: ReturnType<typeof playbackManifest>) => void;
    const delayedA = new Promise<ReturnType<typeof playbackManifest>>((resolve) => { resolveA = resolve; });
    vi.spyOn(api, "getLatestEditingSession").mockImplementation((projectId) => Promise.resolve({
      ...editingSession,
      project_id: projectId,
      session_id: projectId === "project_a" ? "session-a" : "session-b",
      timeline_id: projectId === "project_a" ? "timeline-a" : "timeline-b",
    }) as never);
    vi.spyOn(api, "listJobs").mockResolvedValue([]);
    vi.spyOn(api, "getEditorPlaybackManifest").mockImplementation((projectId) => (
      projectId === "project_a"
        ? delayedA as never
        : Promise.resolve(playbackManifest({
          projectId: "project_b",
          sessionId: "session-b",
          timelineId: "timeline-b",
          exactPreview: {
            status: "succeeded",
            url: "/api/projects/project_b/exact-previews/current-b/content",
            source_session_id: "session-b",
            source_session_revision: 7,
            artifact_revision: 7,
          },
        })) as never
    ));
    vi.spyOn(api, "getCapcutHandoffDiagnostics").mockResolvedValue(null as never);
    const view = render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    view.rerender(<OutputsPage projectId="project_b" onOpenEditor={vi.fn()} />);
    expect(await screen.findByText("현재 편집본 미리보기가 준비되었어요.")).toBeVisible();

    await act(async () => {
      resolveA(playbackManifest({
        exactPreview: {
          status: "failed",
          url: null,
          source_session_id: "session-a",
          source_session_revision: 7,
        },
      }));
      await delayedA;
    });

    expect(screen.getByText("현재 편집본 미리보기가 준비되었어요.")).toBeVisible();
    expect(api.getEditorPlaybackManifest).toHaveBeenCalledWith("project_b", "session-b");
  });

  it("rejects an exact-preview manifest whose session project does not match the active route", async () => {
    vi.spyOn(api, "getLatestEditingSession").mockResolvedValue({ ...editingSession, project_id: "project_b" } as never);
    vi.spyOn(api, "listJobs").mockResolvedValue([]);
    vi.spyOn(api, "getEditorPlaybackManifest").mockResolvedValue(playbackManifest({ projectId: "project_b" }) as never);
    vi.spyOn(api, "getCapcutHandoffDiagnostics").mockResolvedValue(null as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByText("미리보기가 최신 편집본과 달라요.")).toBeVisible();
    expect(document.body).not.toHaveTextContent("/exact-previews/");
  });
});

describe("완성본 실패 이유", () => {
  it("검토 승인이 없어서 막힌 것이면 그렇게 말한다", () => {
    // 실제로 겪은 실패다. 백엔드는 이유를 알고 있었고, 화면은 `완성본을
    // 만들지 못했어요`만 말할 수 있었다 -- 정작 필요한 동작은 클릭 한 번이었다.
    expect(finalRenderFailureMessage("final_output_requires_review_approval")).toContain("검토");
  });

  it("모르는 코드는 원래 쓰던 한 줄로 돌아간다", () => {
    // 영어 코드가 화면에 그대로 나가는 것보다 덜 구체적인 편이 낫다.
    expect(finalRenderFailureMessage("something_new_from_the_engine")).toBe("완성본을 만들지 못했어요.");
    expect(finalRenderFailureMessage(null)).toBe("완성본을 만들지 못했어요.");
  });
});
