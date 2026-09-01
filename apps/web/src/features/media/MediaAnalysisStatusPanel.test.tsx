import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api, type BrollAsset, type MediaAnalysis } from "../../api";
import { MediaAnalysisStatusPanel } from "./MediaAnalysisStatusPanel";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const asset = (projectId = "project-a"): BrollAsset => ({
  asset_id: `asset-${projectId}`,
  asset_type: "broll_video",
  storage_uri: `local://${projectId}/asset`,
  created_at: "2026-07-23T00:00:00Z",
  metadata: { title: "회의 장면", duration_seconds: 5 },
});

const analysis = (status: string, index: number): MediaAnalysis => ({
  analysis_id: `analysis-internal-${index}`,
  asset_id: index === 1 ? "asset-project-a" : `asset-internal-${index}`,
  status,
  progress_percent: status === "running" ? 50 : 100,
  queue_position: null,
  error_code: status === "failed" ? "provider_internal" : null,
  error_message: status === "failed" ? "provider session internal" : null,
  result: null,
  created_at: "2026-07-23T00:00:00Z",
});

describe("MediaAnalysisStatusPanel", () => {
  it("확인할 분석이 없으면 아무것도 그리지 않는다", async () => {
    vi.spyOn(api, "listBrollAssets").mockResolvedValue([]);
    vi.spyOn(api, "listMediaAnalysis").mockResolvedValue({ items: [] });
    const { container } = render(<MediaAnalysisStatusPanel projectId="project-a" />);

    await waitFor(() => expect(api.listMediaAnalysis).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("분석 상태와 진행률을 원본 이름과 함께 보여 준다", async () => {
    vi.spyOn(api, "listBrollAssets").mockResolvedValue([asset()]);
    vi.spyOn(api, "listMediaAnalysis").mockResolvedValue({ items: [analysis("needs_review", 1)] });
    render(<MediaAnalysisStatusPanel projectId="project-a" />);

    expect(await screen.findByRole("heading", { name: "분석 상태" })).toBeVisible();
    expect(screen.getAllByText("회의 장면")[0]).toBeVisible();
    expect(screen.getByText(/확인이 필요해요/)).toBeVisible();
    expect(document.body.textContent).not.toMatch(/asset-project-a|analysis-internal|needs_review|provider session/i);
  });

  it("미리보기를 부르고 결과를 보여 준다", async () => {
    vi.spyOn(api, "listBrollAssets").mockResolvedValue([asset()]);
    vi.spyOn(api, "listMediaAnalysis").mockResolvedValue({ items: [analysis("succeeded", 1)] });
    vi.spyOn(api, "mediaAnalysisPreview").mockResolvedValue({ analysis_id: "analysis-internal-1", preview: { duration_sec: 5 } });
    render(<MediaAnalysisStatusPanel projectId="project-a" />);

    fireEvent.click(await screen.findByRole("button", { name: "미리보기" }));

    expect(await screen.findByText("미리보기 길이 5초")).toBeVisible();
    expect(api.mediaAnalysisPreview).toHaveBeenCalledWith("project-a", "asset-project-a");
  });

  it("멈추기·다시 분석하기·태그 확인을 부르고 목록을 다시 읽는다", async () => {
    vi.spyOn(api, "listBrollAssets").mockResolvedValue([asset()]);
    vi.spyOn(api, "listMediaAnalysis").mockResolvedValue({
      items: [analysis("running", 2), analysis("failed", 3), analysis("needs_review", 1)],
    });
    const cancel = vi.spyOn(api, "cancelMediaAnalysis").mockResolvedValue(analysis("cancelled", 2));
    const retry = vi.spyOn(api, "retryMediaAnalysis").mockResolvedValue(analysis("queued", 3));
    const review = vi.spyOn(api, "reviewMediaAnalysis").mockResolvedValue(analysis("succeeded", 1));
    render(<MediaAnalysisStatusPanel projectId="project-a" />);

    fireEvent.click(await screen.findByRole("button", { name: "분석 멈추기" }));
    await waitFor(() => expect(cancel).toHaveBeenCalledWith("project-a", "analysis-internal-2"));

    fireEvent.click(await screen.findByRole("button", { name: "다시 분석하기" }));
    await waitFor(() => expect(retry).toHaveBeenCalledWith("project-a", "analysis-internal-3"));

    fireEvent.change(await screen.findByLabelText("회의 장면 태그"), { target: { value: "회의, 실내" } });
    fireEvent.click(screen.getByRole("button", { name: "태그 확인" }));
    await waitFor(() => expect(review).toHaveBeenCalledWith("project-a", "analysis-internal-1", { place: ["회의", "실내"] }));
  });

  it("프로젝트가 바뀌면 늦게 도착한 이전 프로젝트 결과를 버린다", async () => {
    let resolveA!: (value: { items: MediaAnalysis[] }) => void;
    vi.spyOn(api, "listBrollAssets").mockResolvedValue([asset()]);
    vi.spyOn(api, "listMediaAnalysis").mockImplementation((projectId) => (
      projectId === "project-a"
        ? new Promise((resolve) => { resolveA = resolve; })
        : Promise.resolve({ items: [analysis("succeeded", 9)] })
    ));
    const { rerender } = render(<MediaAnalysisStatusPanel projectId="project-a" />);

    rerender(<MediaAnalysisStatusPanel projectId="project-b" />);
    await screen.findByRole("heading", { name: "분석 상태" });
    await act(async () => resolveA({ items: [analysis("needs_review", 1)] }));

    expect(screen.queryByText(/확인이 필요해요/)).not.toBeInTheDocument();
  });
});
