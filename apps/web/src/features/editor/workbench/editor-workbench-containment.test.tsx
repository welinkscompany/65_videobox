import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { EditorWorkbench } from "./EditorWorkbench";

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ width: 1200 } as DOMRect);
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 1920 });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); window.localStorage.clear(); });

const view = {
  projectId: "project-a", sessionId: "session-a", timelineId: "timeline-a", timelineVersion: "v1", expectedRevision: 3,
  timebase: "seconds", fps: { num: 30, den: 1 }, output: { width: 1080, height: 1920, sampleAspectRatio: "1:1", rotation: 0, durationSec: 3 },
  tracks: [], captions: [], gaps: [], source: { status: "current" }, playback: { auditionUrls: {}, exactPreview: { status: "unavailable" } },
  local: { selectedSegmentId: null, seekSec: 0 },
} as const;

describe("desktop editor containment contract", () => {
  it("exposes a viewport-bound workbench with inward scroll ownership", () => {
    render(<EditorWorkbench view={view} isSavingTimeline timelineMutationMessage="변경 내용을 저장하고 있어요." />);

    const workbench = screen.getByRole("region", { name: "편집 작업판" });
    expect(workbench).toHaveAttribute("data-editor-viewport", "bounded");
    expect(workbench.querySelector(".vb-editor-workbench__body")).toHaveAttribute("data-scroll-owner", "panels");
    expect(workbench.querySelector(".vb-editor-workbench__preview")).toHaveAttribute("data-scroll-owner", "preview");
    expect(workbench.querySelector(".vb-editor-workbench__timeline")).toHaveAttribute("data-scroll-owner", "timeline");
    expect(workbench).toHaveTextContent("변경 내용을 저장하고 있어요.");
  });

  it("reports saved and failed mutation states in the toolbar", () => {
    const { rerender } = render(<EditorWorkbench view={view} timelineMutationMessage="변경 내용을 저장했어요." />);
    expect(screen.getByRole("status", { name: "편집 저장 상태" })).toHaveTextContent("변경 내용을 저장했어요.");
    rerender(<EditorWorkbench view={view} timelineMutationMessage="변경 내용을 저장하지 못했어요. 최신 내용을 확인한 뒤 다시 시도해 주세요." />);
    expect(screen.getByRole("status", { name: "편집 저장 상태" })).toHaveTextContent("저장하지 못했어요");
  });
});
