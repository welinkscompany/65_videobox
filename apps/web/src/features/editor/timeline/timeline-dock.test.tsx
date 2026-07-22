import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import type { EditorViewModel } from "../editorViewModel";
import { TimelineDock } from "./TimelineDock";

afterEach(cleanup);

const view: EditorViewModel = {
  projectId: "project-a",
  sessionId: "session-a",
  timelineId: "timeline-a",
  timelineVersion: "v1",
  expectedRevision: 1,
  timebase: "seconds",
  fps: { num: 25, den: 1 },
  output: { width: 1080, height: 1920, sampleAspectRatio: "1:1", rotation: 0, durationSec: 20 },
  tracks: [
    { trackId: "n", role: "narration", clips: [{ clipId: "n-1", segmentId: "segment-1", type: "narration", assetId: null, assetUri: null, startSec: 0, endSec: 5, controls: {} }] },
    { trackId: "b", role: "broll", clips: [{ clipId: "b-1", segmentId: "segment-2", type: "broll", assetId: null, assetUri: null, startSec: 5, endSec: 9, controls: {} }] },
    { trackId: "o", role: "overlay", clips: [{ clipId: "o-late", segmentId: "segment-3", type: "overlay", assetId: null, assetUri: null, startSec: 15, endSec: 18, controls: {} }] },
  ],
  captions: [{ segmentId: "segment-1", text: "첫 자막", startSec: 0, endSec: 5, style: { fontFamily: "Pretendard", fontSizePx: 28, textColor: "#fff", outlineColor: "#000", outlineWidthPx: 1, backgroundColor: "#00000000", positionXPercent: 50, positionYPercent: 90, horizontalAlign: "center", safeAreaEnabled: true, shadowBlurPx: 0 } }],
  gaps: [{ gapId: "gap-1", segmentId: "segment-2", startSec: 3, endSec: 4, reason: "asset_required" }],
  source: { status: "current" },
  playback: { auditionUrls: {}, exactPreview: { status: "unavailable" } },
  local: { selectedSegmentId: null, seekSec: 0 },
};

const thousandClipHourView: EditorViewModel = {
  ...view,
  output: { ...view.output, durationSec: 60 * 60 },
  tracks: [{
    trackId: "bulk-narration",
    role: "narration",
    clips: Array.from({ length: 1_000 }, (_, index) => ({
      clipId: `bulk-${index}`,
      segmentId: `bulk-segment-${index}`,
      type: "narration" as const,
      assetId: null,
      assetUri: null,
      startSec: index * 3.6,
      endSec: (index + 1) * 3.6,
      controls: {},
    })),
  }],
  captions: [],
  gaps: [],
};

describe("TimelineDock", () => {
  it("renders fixed lanes, only visible clips, ruler, gaps, captions, nearest source snap, and local playhead", () => {
    render(<TimelineDock view={view} viewportWidthPx={400} />);

    const timeline = screen.getByRole("region", { name: "타임라인" });
    expect(timeline).toHaveAttribute("tabindex", "0");
    expect(screen.getAllByRole("listitem", { name: /내레이션/ })).toHaveLength(1);
    expect(screen.getAllByRole("listitem", { name: /B-roll/ })).toHaveLength(1);
    expect(screen.getAllByRole("listitem", { name: /BGM/ })).toHaveLength(1);
    expect(screen.getAllByRole("listitem", { name: /효과음/ })).toHaveLength(1);
    expect(screen.getAllByRole("listitem", { name: /오버레이/ })).toHaveLength(1);
    expect(screen.getByTestId("timeline-clip")).toHaveAttribute("data-clip-id", "n-1");
    expect(screen.queryByText("o-late")).toBeNull();
    expect(screen.getByLabelText("눈금 0초")).toBeInTheDocument();
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "0");
    expect(screen.getByText("자산 공백: asset_required")).toBeInTheDocument();
    expect(screen.getByText("현재 자막: 첫 자막")).toBeInTheDocument();
    expect(screen.getByText((_, element) => element?.textContent === "스냅: 항목 시작 (caption:segment-1:start, 0초)" )).toBeInTheDocument();
  });

  it("keeps click and keyboard navigation local while guarding editable targets", () => {
    render(<TimelineDock view={view} viewportWidthPx={400} />);

    const timeline = screen.getByRole("region", { name: "타임라인" });
    fireEvent.click(screen.getByRole("listitem", { name: "내레이션" }), { clientX: 200 });
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "2");
    expect(screen.getByText("스냅 없음")).toBeInTheDocument();
    fireEvent.keyDown(timeline, { key: "ArrowRight" });
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "2.04");
    fireEvent.keyDown(timeline, { key: "End" });
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "20");
    fireEvent.keyDown(timeline, { key: "Home" });
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "0");
    fireEvent.keyDown(timeline, { key: "+" });
    expect(timeline).toHaveAttribute("data-pixels-per-second", "125");

    const input = document.createElement("input");
    timeline.append(input);
    input.focus();
    fireEvent.keyDown(input, { key: "ArrowRight" });
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "0");
  });

  it("scrolls its local viewport from horizontal wheel pixels and clamps at both bounds", () => {
    render(<TimelineDock view={view} viewportWidthPx={400} />);

    const timeline = screen.getByRole("region", { name: "타임라인" });
    fireEvent.wheel(timeline, { deltaX: 200 });
    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "2");
    fireEvent.wheel(timeline, { deltaX: 10_000 });
    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "16");
    fireEvent.wheel(timeline, { deltaX: -10_000 });
    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "0");
  });

  it("retains focus on the timeline while handling keyboard navigation", () => {
    render(<TimelineDock view={view} viewportWidthPx={400} />);

    const timeline = screen.getByRole("region", { name: "타임라인" });
    timeline.focus();
    expect(document.activeElement).toBe(timeline);
    fireEvent.keyDown(timeline, { key: "ArrowRight" });
    expect(document.activeElement).toBe(timeline);
  });

  it("selects only a visible clip and gives the empty timeline an explicit state", () => {
    const { rerender } = render(<TimelineDock view={view} viewportWidthPx={400} />);
    fireEvent.click(screen.getByTestId("timeline-clip"));
    expect(screen.getByTestId("timeline-clip")).toHaveAttribute("data-selected", "true");

    rerender(<TimelineDock view={{ ...view, tracks: [], captions: [], gaps: [] }} viewportWidthPx={400} />);
    expect(screen.getByText("표시할 타임라인 항목이 없습니다.")).toBeInTheDocument();
  });

  it("uses half-open filtering rather than a first-N cap for 1000 clips across a 60-minute fixture", () => {
    render(<TimelineDock view={thousandClipHourView} viewportWidthPx={800} />);

    expect(screen.getAllByTestId("timeline-clip")).toHaveLength(3);
    expect(screen.getAllByTestId("timeline-clip").map((clip) => clip.getAttribute("data-clip-id"))).toEqual(["bulk-0", "bulk-1", "bulk-2"]);
    expect(screen.queryByText("bulk-3")).toBeNull();

    fireEvent.wheel(screen.getByRole("region", { name: "타임라인" }), { deltaX: 36_000 });

    const laterClips = screen.getAllByTestId("timeline-clip");
    expect(laterClips.length).toBeLessThanOrEqual(300);
    expect(laterClips.map((clip) => clip.getAttribute("data-clip-id"))).toEqual(["bulk-100", "bulk-101", "bulk-102"]);
    expect(screen.queryByText("bulk-99")).toBeNull();
    expect(screen.getByText("bulk-100")).toBeInTheDocument();
    expect(screen.getByText("bulk-102")).toBeInTheDocument();
  });
});
