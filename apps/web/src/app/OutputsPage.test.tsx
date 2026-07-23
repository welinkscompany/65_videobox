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

function stubReadOnlyOutputApi() {
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
    expect(screen.queryByRole("button", { name: /만들기|내보내기|등록/ })).not.toBeInTheDocument();
  });
});
