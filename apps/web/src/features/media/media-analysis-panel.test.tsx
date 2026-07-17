import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MediaAnalysisPanel } from "./MediaAnalysisPanel";

const mocks = vi.hoisted(() => ({
  listMediaAnalysis: vi.fn().mockResolvedValue({
    items: [{ analysis_id: "analysis_1", asset_id: "asset_1", status: "needs_review", progress_percent: 100, queue_position: null, error_code: null, error_message: null, result: null, created_at: "now" }],
  }),
  mediaAnalysisPreview: vi.fn().mockResolvedValue({ analysis_id: "analysis_1", preview: { duration_sec: 1 } }),
}));

vi.mock("../../api", () => ({
  api: {
    listMediaAnalysis: mocks.listMediaAnalysis,
    cancelMediaAnalysis: vi.fn(),
    retryMediaAnalysis: vi.fn(),
    reviewMediaAnalysis: vi.fn(),
    mediaAnalysisPreview: mocks.mediaAnalysisPreview,
  },
}));

describe("MediaAnalysisPanel", () => {
  it("shows review state and loads preview before selecting the asset", async () => {
    const onSelectAsset = vi.fn();
    render(<MediaAnalysisPanel projectId="project_1" onSelectAsset={onSelectAsset} />);

    expect(await screen.findByText(/확인이 필요해요/)).toBeInTheDocument();
    expect(screen.getByLabelText("asset_1 수동 태그")).toBeInTheDocument();
    expect(screen.queryByText(/needs_review|세션|파이프라인|job/i)).not.toBeInTheDocument();

    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "미리보기" })); });

    await vi.waitFor(() => expect(mocks.mediaAnalysisPreview).toHaveBeenCalledWith("project_1", "asset_1"));
    expect(onSelectAsset).toHaveBeenCalledWith("asset_1");
    expect(screen.getByText("미리보기 · 1초")).toBeInTheDocument();

    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "새로고침" })); });
    expect(screen.queryByText("미리보기 · 1초")).not.toBeInTheDocument();
  });

  it("gives a next action instead of exposing a failed analysis detail", async () => {
    mocks.listMediaAnalysis.mockResolvedValueOnce({
      items: [{ analysis_id: "analysis_2", asset_id: "asset_2", status: "failed", progress_percent: 0, queue_position: null, error_code: "provider_error", error_message: "provider session failed", result: null, created_at: "now" }],
    });
    render(<MediaAnalysisPanel projectId="project_1" />);

    expect(await screen.findByText("분석을 마치지 못했어요. 다시 시도하거나 직접 선택해 주세요.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "다시 분석하기" })).toBeInTheDocument();
    expect(screen.queryByText("provider session failed")).not.toBeInTheDocument();
  });
});
