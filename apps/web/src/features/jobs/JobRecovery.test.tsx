import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, type JobRecord } from "../../api";
import { JobRecovery } from "./JobRecovery";

const job = (overrides: Partial<JobRecord> = {}): JobRecord => ({
  job_id: "job-internal-1",
  project_id: "project-a",
  job_type: "transcription",
  status: "failed",
  input_ref: "asset-internal-1",
  output_ref: null,
  error_message: "provider internal details",
  started_at: "2026-07-23T00:00:00Z",
  finished_at: "2026-07-23T00:00:01Z",
  ...overrides,
});

beforeEach(() => {
  vi.spyOn(api, "listJobs").mockResolvedValue([job()]);
  vi.spyOn(api, "listAllJobs").mockResolvedValue([
    { ...job({ project_id: "project-b", job_id: "job-global-internal" }), project_name: "두 번째 영상" },
  ]);
  vi.spyOn(api, "retryJob").mockResolvedValue({ job_id: "job-new", status: "succeeded" });
});

afterEach(() => vi.restoreAllMocks());

describe("JobRecovery", () => {
  it("lazily shows current and global work without mutating on mount", async () => {
    render(<JobRecovery projectId="project-a" />);

    expect(await screen.findByText("음성 받아쓰기")).toBeVisible();
    expect(screen.getByText("다시 확인이 필요해요")).toBeVisible();
    expect(api.retryJob).not.toHaveBeenCalled();
    expect(api.listAllJobs).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toMatch(/job-internal|asset-internal|transcription|provider internal/i);
    expect(screen.getByRole("button", { name: "현재 프로젝트" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "모든 프로젝트" })).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(screen.getByRole("button", { name: "모든 프로젝트" }));
    expect(await screen.findByText("두 번째 영상")).toBeVisible();
    expect(api.listAllJobs).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "현재 프로젝트" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "모든 프로젝트" })).toHaveAttribute("aria-pressed", "true");
  });

  it("retries a global row with its own project and job IDs, single-flight, then refreshes global truth", async () => {
    let releaseRetry!: (value: { job_id: string; status: string }) => void;
    vi.mocked(api.listAllJobs)
      .mockResolvedValueOnce([
        { ...job({ project_id: "project-b", job_id: "job-global-internal" }), project_name: "두 번째 영상" },
      ])
      .mockResolvedValueOnce([
        { ...job({ project_id: "project-b", job_id: "job-global-internal" }), project_name: "두 번째 영상" },
        {
          ...job({
            project_id: "project-b",
            job_id: "job-new",
            status: "succeeded",
            started_at: "2026-07-23T00:00:02Z",
            finished_at: "2026-07-23T00:00:03Z",
          }),
          project_name: "두 번째 영상",
        },
      ]);
    vi.mocked(api.retryJob).mockImplementation(() => new Promise((resolve) => { releaseRetry = resolve; }));
    render(<JobRecovery projectId="project-a" />);
    await screen.findByText("음성 받아쓰기");
    fireEvent.click(screen.getByRole("button", { name: "모든 프로젝트" }));
    const retry = await screen.findByRole("button", { name: "다시 실행" });

    fireEvent.click(retry);
    fireEvent.click(retry);
    expect(api.retryJob).toHaveBeenCalledTimes(1);
    expect(api.retryJob).toHaveBeenCalledWith("project-b", "job-global-internal");
    await act(async () => releaseRetry({ job_id: "job-new", status: "succeeded" }));
    await waitFor(() => expect(api.listAllJobs).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("작업을 다시 시작했어요. 최신 상태를 확인했습니다.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "다시 실행" })).not.toBeInTheDocument();
  });

  it("offers retry only on the newest exact-lineage attempt and allows a later newest failure", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([
      job({
        job_id: "old-failed",
        started_at: "2026-07-23T00:00:00Z",
        finished_at: "2026-07-23T00:00:10Z",
      }),
      job({
        job_id: "new-running",
        status: "running",
        started_at: "2026-07-23T00:00:05Z",
        finished_at: null,
      }),
      job({
        job_id: "earlier-succeeded-other-lineage",
        input_ref: "asset-internal-2",
        status: "succeeded",
        started_at: "2026-07-23T00:00:02Z",
        finished_at: "2026-07-23T00:00:03Z",
      }),
      job({
        job_id: "later-failed-other-lineage",
        input_ref: "asset-internal-2",
        started_at: "2026-07-23T00:00:03Z",
        finished_at: "2026-07-23T00:00:04Z",
      }),
    ]);
    render(<JobRecovery projectId="project-a" />);

    const retry = await screen.findByRole("button", { name: "다시 실행" });
    fireEvent.click(retry);
    await waitFor(() => expect(api.retryJob).toHaveBeenCalledWith("project-a", "later-failed-other-lineage"));
  });

  it("offers generic retry only for supported failed jobs with an input reference", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([
      job({ job_id: "supported-failed", job_type: "broll_recommendation" }),
      job({ job_id: "supported-blocked", job_type: "music_recommendation", status: "blocked" }),
      job({ job_id: "no-input", job_type: "subtitle_render", input_ref: null }),
      job({ job_id: "preview", job_type: "preview_render" }),
      job({ job_id: "capcut", job_type: "capcut_export" }),
      job({ job_id: "timeline", job_type: "timeline_build" }),
      job({ job_id: "analysis", job_type: "segment_analysis" }),
      job({ job_id: "partial", job_type: "partial_regeneration" }),
      job({ job_id: "unknown", job_type: "unknown_type" }),
    ]);
    render(<JobRecovery projectId="project-a" />);

    expect(await screen.findAllByRole("button", { name: "다시 실행" })).toHaveLength(1);
    expect(screen.getByText("장면 추천")).toBeVisible();
    expect(screen.getByText("음악 추천")).toBeVisible();
    expect(screen.getByText("자동 재시도 대신 원래 화면에서 직접 다시 실행해 주세요.")).toBeVisible();
    expect(document.body.textContent).not.toMatch(/preview_render|capcut_export|timeline_build|segment_analysis|partial_regeneration|unknown_type/);
  });

  it("refreshes authoritative current truth after a retry refusal and recovers list errors", async () => {
    vi.mocked(api.retryJob).mockRejectedValue(new Error("cannot retry internal"));
    vi.mocked(api.listJobs)
      .mockRejectedValueOnce(new Error("offline internal"))
      .mockResolvedValue([job()]);
    render(<JobRecovery projectId="project-a" />);

    expect(await screen.findByText("작업 상태를 불러오지 못했어요.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "다시 불러오기" }));
    const retry = await screen.findByRole("button", { name: "다시 실행" });
    fireEvent.click(retry);
    expect(await screen.findByText("자동으로 다시 시작하지 못했어요. 해당 화면에서 직접 다시 실행해 주세요.")).toBeVisible();
    await waitFor(() => expect(api.listJobs).toHaveBeenCalledTimes(3));
  });

  it("does not claim a retry is confirmed when the authoritative refresh fails", async () => {
    vi.mocked(api.listJobs)
      .mockResolvedValueOnce([job()])
      .mockRejectedValueOnce(new Error("refresh failed"));
    render(<JobRecovery projectId="project-a" />);

    fireEvent.click(await screen.findByRole("button", { name: "다시 실행" }));

    expect(await screen.findByText("작업 상태를 불러오지 못했어요.")).toBeVisible();
    expect(screen.queryByText("작업을 다시 시작했어요. 최신 상태를 확인했습니다.")).not.toBeInTheDocument();
  });

  it("keeps an old current retry from refetching, messaging, or unlocking a newer retry after current-global-current", async () => {
    let releaseOld!: (value: { job_id: string; status: string }) => void;
    let releaseNew!: (value: { job_id: string; status: string }) => void;
    vi.mocked(api.retryJob)
      .mockImplementationOnce(() => new Promise((resolve) => { releaseOld = resolve; }))
      .mockImplementationOnce(() => new Promise((resolve) => { releaseNew = resolve; }));
    render(<JobRecovery projectId="project-a" />);
    fireEvent.click(await screen.findByRole("button", { name: "다시 실행" }));
    fireEvent.click(screen.getByRole("button", { name: "모든 프로젝트" }));
    await screen.findByText("두 번째 영상");
    fireEvent.click(screen.getByRole("button", { name: "현재 프로젝트" }));
    const newRetry = await screen.findByRole("button", { name: "다시 실행" });
    fireEvent.click(newRetry);

    await act(async () => releaseOld({ job_id: "old-new", status: "succeeded" }));
    expect(screen.getByRole("button", { name: "다시 실행" })).toBeDisabled();
    expect(screen.queryByText("작업을 다시 시작했어요. 최신 상태를 확인했습니다.")).not.toBeInTheDocument();

    await act(async () => releaseNew({ job_id: "new-new", status: "succeeded" }));
    expect(await screen.findByText("작업을 다시 시작했어요. 최신 상태를 확인했습니다.")).toBeVisible();
    expect(api.listJobs).toHaveBeenCalledTimes(3);
  });

  it("discards a late current-project response after A changes to B", async () => {
    let resolveA!: (value: JobRecord[]) => void;
    vi.mocked(api.listJobs).mockImplementation((projectId) => (
      projectId === "project-a"
        ? new Promise((resolve) => { resolveA = resolve; })
        : Promise.resolve([job({ project_id: "project-b", job_type: "final_render" })])
    ));
    const { rerender } = render(<JobRecovery projectId="project-a" />);

    rerender(<JobRecovery projectId="project-b" />);
    expect(await screen.findByText("완성본 만들기")).toBeVisible();
    await act(async () => resolveA([job({ job_type: "transcription" })]));
    expect(screen.queryByText("음성 받아쓰기")).not.toBeInTheDocument();
    expect(screen.getByTestId("job-recovery")).toHaveAttribute("data-project-id", "project-b");
  });
});
