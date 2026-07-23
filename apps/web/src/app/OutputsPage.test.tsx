import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { api } from "../api";
import { OutputsPage } from "./OutputsPage";

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

function stubCanonicalSubtitleApi({
  reviewStatus = "approved",
  reviewFlags = [],
  pendingRecommendations = [],
  jobs = [activeTimelineJob],
}: {
  reviewStatus?: string;
  reviewFlags?: unknown[];
  pendingRecommendations?: unknown[];
  jobs?: typeof activeTimelineJob[];
} = {}) {
  vi.spyOn(api, "getLatestEditingSession").mockResolvedValue({ session_id: "session-a", project_id: "project_a", timeline_id: "timeline-a" } as never);
  vi.spyOn(api, "listJobs").mockResolvedValue(jobs as never);
  vi.spyOn(api, "getTimeline").mockResolvedValue({
    job_id: activeTimelineJob.job_id, status: "succeeded", timeline: {
      timeline_id: "timeline-a", project_id: "project_a", version: "v1", output_mode: "short", review_status: reviewStatus,
      tracks: [], review_flags: reviewFlags, pending_recommendations: pendingRecommendations,
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
      export_id: "capcut-a", timeline_id: "timeline-a", export_type: "capcut_draft", file_uri: "local://draft.zip", status: "succeeded", notes: [],
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

  it("keeps subtitle failure recoverable until the user explicitly tries again", async () => {
    stubCanonicalSubtitleApi();
    const renderSubtitle = vi.spyOn(api, "renderSubtitle").mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({ job_id: subtitleJob.job_id, status: "succeeded" });
    vi.spyOn(api, "getSubtitle").mockResolvedValue({
      job_id: subtitleJob.job_id, status: "succeeded", subtitle: {
        subtitle_id: "subtitle-a", project_id: "project_a", timeline_id: "timeline-a", format: "srt", file_uri: "local://subtitle.srt", status: "succeeded", notes: [],
      },
    });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "자막 만들기" }));
    expect(await screen.findByText("자막을 만들지 못했어요. 편집 상태를 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
    expect(renderSubtitle).toHaveBeenCalledTimes(1);
    const retry = screen.getByRole("button", { name: "자막 만들기" });
    expect(retry).toBeEnabled();
    fireEvent.click(retry);
    await waitFor(() => expect(renderSubtitle).toHaveBeenCalledTimes(2));
  });

  it("keeps subtitle retry available when a status refresh finishes before its request", async () => {
    stubCanonicalSubtitleApi();
    let resolveSubtitle!: (result: { job_id: string; status: string }) => void;
    const pendingSubtitle = new Promise<{ job_id: string; status: string }>((resolve) => { resolveSubtitle = resolve; });
    const renderSubtitle = vi.spyOn(api, "renderSubtitle").mockReturnValueOnce(pendingSubtitle as never).mockRejectedValueOnce(new Error("offline"));

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "자막 만들기" }));
    expect(screen.getByRole("button", { name: "자막 만드는 중" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "상태 다시 확인" }));
    await waitFor(() => expect(api.listJobs).toHaveBeenCalledTimes(2));
    resolveSubtitle({ job_id: subtitleJob.job_id, status: "succeeded" });

    const retry = await screen.findByRole("button", { name: "자막 만들기" });
    expect(retry).toBeEnabled();
    fireEvent.click(retry);
    await waitFor(() => expect(renderSubtitle).toHaveBeenCalledTimes(2));
  });

  it("does not offer project A's subtitle action while project B is still loading", async () => {
    const projectBSession = new Promise<null>(() => {});
    const projectBJobs = new Promise<[]>(() => {});
    vi.spyOn(api, "getLatestEditingSession").mockImplementation((requestedProjectId) => (
      requestedProjectId === "project_b"
        ? projectBSession as never
        : Promise.resolve({ session_id: "session-a", project_id: "project_a", timeline_id: "timeline-a" }) as never
    ));
    vi.spyOn(api, "listJobs").mockImplementation((requestedProjectId) => (
      requestedProjectId === "project_b" ? projectBJobs as never : Promise.resolve([activeTimelineJob]) as never
    ));
    vi.spyOn(api, "getTimeline").mockResolvedValue({
      job_id: activeTimelineJob.job_id, status: "succeeded", timeline: {
        timeline_id: "timeline-a", project_id: "project_a", version: "v1", output_mode: "short", review_status: "approved",
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
        : Promise.resolve({ session_id: "session-a", project_id: "project_a", timeline_id: "timeline-a" }) as never
    ));
    vi.spyOn(api, "listJobs").mockImplementation((requestedProjectId) => (
      requestedProjectId === "project_b" ? projectBJobs as never : Promise.resolve([activeTimelineJob]) as never
    ));
    vi.spyOn(api, "getTimeline").mockResolvedValue({
      job_id: activeTimelineJob.job_id, status: "succeeded", timeline: {
        timeline_id: "timeline-a", project_id: "project_a", version: "v1", output_mode: "short", review_status: "approved",
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

  it("shows a current final preview and ready CapCut handoff using read-only APIs only", async () => {
    stubReadOnlyOutputApi();
    const openEditor = vi.fn();
    const startFinalRender = vi.spyOn(api, "startFinalRender");
    const startCapcutDraftExport = vi.spyOn(api, "startCapcutDraftExport");
    const registerCapcutDraftHandoff = vi.spyOn(api, "registerCapcutDraftHandoff");

    render(<OutputsPage projectId="project_a" onOpenEditor={openEditor} />);

    expect(await screen.findByText("완성본을 확인할 수 있어요.")).toBeVisible();
    expect(screen.getByLabelText("완성본 재생")).toHaveAttribute("src", "/api/projects/project_a/final-renders/final-current/content");
    expect(screen.getByText("CapCut에서 초안을 열 수 있어요.")).toBeVisible();
    expect(startFinalRender).not.toHaveBeenCalled();
    expect(startCapcutDraftExport).not.toHaveBeenCalled();
    expect(registerCapcutDraftHandoff).not.toHaveBeenCalled();
  });

  it("keeps read-only output status available when the active session lookup fails", async () => {
    stubReadOnlyOutputApi();
    vi.spyOn(api, "getLatestEditingSession").mockRejectedValue(new Error("offline"));

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByText("완성본을 확인할 수 있어요.")).toBeVisible();
    expect(screen.getByRole("button", { name: "자막 만들기" })).toBeDisabled();
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
});
