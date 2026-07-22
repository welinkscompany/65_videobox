import { afterEach, describe, expect, it, vi } from "vitest";
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

const twoNarrationView: EditorViewModel = {
  ...view,
  tracks: [
    {
      trackId: "n",
      role: "narration",
      clips: [
        { clipId: "n-1", segmentId: "segment-1", type: "narration", assetId: null, assetUri: null, startSec: 0, endSec: 1, controls: {} },
        { clipId: "n-2", segmentId: "segment-2", type: "narration", assetId: null, assetUri: null, startSec: 1, endSec: 2, controls: {} },
      ],
    },
    ...view.tracks.filter((track) => track.role !== "narration"),
  ],
};

const offsetNarrationView: EditorViewModel = {
  ...view,
  tracks: [
    {
      trackId: "n",
      role: "narration",
      clips: [
        { clipId: "n-offset", segmentId: "segment-offset", type: "narration", assetId: null, assetUri: null, startSec: 3, endSec: 8, controls: {} },
      ],
    },
  ],
  captions: [],
  gaps: [],
};

const longNarrationView: EditorViewModel = {
  ...view,
  tracks: [{
    trackId: "long-narration",
    role: "narration",
    clips: Array.from({ length: 10 }, (_, index) => ({
      clipId: `long-${index + 1}`,
      segmentId: `long-segment-${index + 1}`,
      type: "narration" as const,
      assetId: null,
      assetUri: null,
      startSec: index,
      endSec: index + 1,
      controls: {},
    })),
  }],
  captions: [],
  gaps: [],
};

function timelineClip(clipId: string): HTMLElement {
  const clip = screen.getAllByTestId("timeline-clip").find((item) => item.getAttribute("data-clip-id") === clipId);
  if (!clip) throw new Error(`Missing timeline clip ${clipId}`);
  return clip;
}

function timelineClipSelection(clipId: string): HTMLButtonElement {
  return screen.getByRole("button", { name: `${clipId} 클립 선택` });
}

function selectTimelineClip(clipId: string): void {
  fireEvent.click(timelineClipSelection(clipId));
}

function mockTimelineRect(clipId: string, left = 0) {
  const clip = timelineClip(clipId);
  vi.spyOn(clip, "getBoundingClientRect").mockReturnValue({
    bottom: 32, height: 32, left, right: left + 100, toJSON: () => ({}), top: 0, width: 100, x: left, y: 0,
  });
}

function mockTimelineTrackRect(left = 0) {
  const track = screen.getByTestId("timeline-track");
  vi.spyOn(track, "getBoundingClientRect").mockReturnValue({
    bottom: 160, height: 160, left, right: left + 400, toJSON: () => ({}), top: 0, width: 400, x: left, y: 0,
  });
}

function pointer(target: Element, type: string, clientX = 0) {
  fireEvent(target, new MouseEvent(type, { bubbles: true, cancelable: true, clientX }));
}

describe("TimelineDock", () => {
  it("selects narration clips with Enter and Space before exposing mutation controls", () => {
    render(<TimelineDock view={twoNarrationView} viewportWidthPx={400} />);

    const firstClip = timelineClipSelection("n-1");
    firstClip.focus();
    expect(firstClip).toHaveFocus();
    fireEvent.keyDown(firstClip, { key: "Enter" });
    expect(screen.getByRole("button", { name: "n-1 시작 자르기" })).toBeInTheDocument();

    const secondClip = timelineClipSelection("n-2");
    secondClip.focus();
    expect(secondClip).toHaveFocus();
    fireEvent.keyDown(secondClip, { key: " " });
    expect(screen.getByRole("button", { name: "n-2 시작 자르기" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "n-1 시작 자르기" })).toBeNull();
  });

  it("keeps the selection button separate from narration mutation buttons", () => {
    render(<TimelineDock view={view} viewportWidthPx={400} />);

    const selection = timelineClipSelection("n-1");
    fireEvent.click(selection);

    expect(selection).toHaveAttribute("aria-pressed", "true");
    expect(selection).not.toContainElement(screen.getByRole("button", { name: "n-1 시작 자르기" }));
    expect(selection).not.toContainElement(screen.getByRole("button", { name: "n-1 끝 자르기" }));
    expect(selection).not.toContainElement(screen.getByRole("button", { name: "n-1 순서 바꾸기" }));
  });

  it("anchors trim handles and the reorder control inside the selected clip", () => {
    render(<TimelineDock view={view} viewportWidthPx={400} />);
    selectTimelineClip("n-1");

    const start = screen.getByRole("button", { name: "n-1 시작 자르기" });
    const end = screen.getByRole("button", { name: "n-1 끝 자르기" });
    const reorder = screen.getByRole("button", { name: "n-1 순서 바꾸기" });
    const controls = start.parentElement;

    expect(controls).toHaveAttribute("data-mutation-controls", "true");
    expect(controls).toHaveStyle({ position: "absolute", inset: "0", overflow: "hidden" });
    expect(start).toHaveAttribute("data-trim-edge", "start");
    expect(start).toHaveStyle({ position: "absolute", left: "0", top: "0" });
    expect(end).toHaveAttribute("data-trim-edge", "end");
    expect(end).toHaveStyle({ position: "absolute", right: "0", top: "0" });
    expect(reorder).toHaveAttribute("data-reorder-control", "true");
    expect(reorder).toHaveStyle({ position: "absolute", left: "33.333%", width: "33.334%" });
  });

  it("renders mutation controls only for the selected narration clip", () => {
    render(<TimelineDock view={view} viewportWidthPx={400} />);

    expect(screen.queryByRole("button", { name: "n-1 시작 자르기" })).toBeNull();
    selectTimelineClip("n-1");
    expect(screen.getByRole("button", { name: "n-1 시작 자르기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "n-1 끝 자르기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "n-1 순서 바꾸기" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "b-1 시작 자르기" })).toBeNull();
  });

  it("keeps trim pointer moves local and commits one meaningful frame-aligned result on pointer up", () => {
    const onTrimNarration = vi.fn();
    render(<TimelineDock onTrimNarration={onTrimNarration} view={view} viewportWidthPx={400} />);
    selectTimelineClip("n-1");
    mockTimelineRect("n-1");
    mockTimelineTrackRect();

    const control = screen.getByRole("button", { name: "n-1 시작 자르기" });
    pointer(control, "pointerdown", 0);
    pointer(control, "pointermove", 200);
    pointer(control, "pointermove", 300);
    expect(onTrimNarration).not.toHaveBeenCalled();
    pointer(control, "pointerup", 200);

    expect(onTrimNarration).toHaveBeenCalledTimes(1);
    expect(onTrimNarration).toHaveBeenCalledWith({ segmentId: "segment-1", startSec: 2, endSec: 5 });
  });

  it("does not mutate when a trim handle is pressed and released without moving", () => {
    const onTrimNarration = vi.fn();
    render(<TimelineDock onTrimNarration={onTrimNarration} view={offsetNarrationView} viewportWidthPx={400} />);
    selectTimelineClip("n-offset");
    mockTimelineTrackRect(40);

    const control = screen.getByRole("button", { name: "n-offset 시작 자르기" });
    pointer(control, "pointerdown", 240);
    pointer(control, "pointerup", 240);

    expect(onTrimNarration).not.toHaveBeenCalled();
    expect(timelineClip("n-offset")).toHaveAttribute("data-start-seconds", "3");
  });

  it("discards a trim draft when its pointer is cancelled", () => {
    const onTrimNarration = vi.fn();
    render(<TimelineDock onTrimNarration={onTrimNarration} view={view} viewportWidthPx={400} />);
    selectTimelineClip("n-1");
    mockTimelineRect("n-1");
    mockTimelineTrackRect();

    const control = screen.getByRole("button", { name: "n-1 끝 자르기" });
    pointer(control, "pointerdown", 100);
    pointer(control, "pointermove", 200);
    pointer(control, "pointercancel");
    pointer(control, "pointerup", 200);

    expect(onTrimNarration).not.toHaveBeenCalled();
  });

  it("commits one narration reorder from pointer position only when released", () => {
    const onReorderNarration = vi.fn();
    render(<TimelineDock onReorderNarration={onReorderNarration} view={twoNarrationView} viewportWidthPx={400} />);
    selectTimelineClip("n-1");
    mockTimelineRect("n-1");
    mockTimelineTrackRect();

    const control = screen.getByRole("button", { name: "n-1 순서 바꾸기" });
    pointer(control, "pointerdown", 0);
    pointer(control, "pointermove", 250);
    expect(onReorderNarration).not.toHaveBeenCalled();
    pointer(control, "pointerup", 250);

    expect(onReorderNarration).toHaveBeenCalledTimes(1);
    expect(onReorderNarration).toHaveBeenCalledWith({
      segmentIds: ["segment-2", "segment-1"],
      boundsById: {
        "segment-1": { startSec: 1, endSec: 2 },
        "segment-2": { startSec: 0, endSec: 1 },
      },
    });
  });

  it("uses the release position for a narration reorder when no intermediate pointer move arrives", () => {
    const onReorderNarration = vi.fn();
    render(<TimelineDock onReorderNarration={onReorderNarration} view={twoNarrationView} viewportWidthPx={400} />);
    selectTimelineClip("n-1");
    mockTimelineTrackRect();

    const control = screen.getByRole("button", { name: "n-1 순서 바꾸기" });
    pointer(control, "pointerdown", 0);
    pointer(control, "pointerup", 250);

    expect(onReorderNarration).toHaveBeenCalledTimes(1);
    expect(onReorderNarration).toHaveBeenCalledWith(expect.objectContaining({ segmentIds: ["segment-2", "segment-1"] }));
  });

  it("does not reorder on a stationary press and release in a scrolled virtualized viewport", () => {
    const onReorderNarration = vi.fn();
    render(<TimelineDock onReorderNarration={onReorderNarration} view={longNarrationView} viewportWidthPx={200} />);
    const timeline = screen.getByRole("region", { name: "타임라인" });
    fireEvent.wheel(timeline, { deltaX: 50 });
    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "0.5");
    selectTimelineClip("long-1");
    mockTimelineTrackRect(40);

    const control = screen.getByRole("button", { name: "long-1 순서 바꾸기" });
    pointer(control, "pointerdown", 140);
    pointer(control, "pointerup", 140);

    expect(onReorderNarration).not.toHaveBeenCalled();
    expect(timelineClip("long-1")).toHaveAttribute("data-start-seconds", "0");
  });

  it("disables narration mutation controls while saving", () => {
    const onTrimNarration = vi.fn();
    render(<TimelineDock isSaving mutationMessage="저장 중" onTrimNarration={onTrimNarration} view={view} viewportWidthPx={400} />);

    selectTimelineClip("n-1");
    const control = screen.getByRole("button", { name: "n-1 시작 자르기" });
    expect(control).toBeDisabled();
    expect(screen.getByText("저장 중")).toBeInTheDocument();
    pointer(control, "pointerdown", 0);
    pointer(control, "pointerup", 100);
    expect(onTrimNarration).not.toHaveBeenCalled();
  });

  it("keeps mutation-control clicks out of the existing clip selection handler", () => {
    render(<TimelineDock view={view} viewportWidthPx={400} />);

    selectTimelineClip("n-1");
    fireEvent.click(screen.getByRole("button", { name: "n-1 시작 자르기" }));
    expect(screen.getByTestId("timeline-clip")).toHaveAttribute("data-selected", "true");
  });

  it("applies trim pointer movement as a relative delta for a nonzero clip in a scrolled viewport", () => {
    const onTrimNarration = vi.fn();
    render(<TimelineDock onTrimNarration={onTrimNarration} view={offsetNarrationView} viewportWidthPx={400} />);
    const timeline = screen.getByRole("region", { name: "타임라인" });
    fireEvent.wheel(timeline, { deltaX: 200 });
    selectTimelineClip("n-offset");
    mockTimelineRect("n-offset", 140);
    mockTimelineTrackRect(40);

    const control = screen.getByRole("button", { name: "n-offset 시작 자르기" });
    pointer(control, "pointerdown", 240);
    pointer(control, "pointermove", 340);
    pointer(control, "pointerup", 340);

    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "2");
    expect(onTrimNarration).toHaveBeenCalledWith({ segmentId: "segment-offset", startSec: 4, endSec: 8 });
  });

  it("clamps an end-handle drag outside the track to the timeline duration", () => {
    const onTrimNarration = vi.fn();
    render(<TimelineDock onTrimNarration={onTrimNarration} view={offsetNarrationView} viewportWidthPx={400} />);
    selectTimelineClip("n-offset");
    mockTimelineTrackRect(40);

    const control = screen.getByRole("button", { name: "n-offset 끝 자르기" });
    pointer(control, "pointerdown", 200);
    pointer(control, "pointermove", 10_200);
    pointer(control, "pointerup", 10_200);

    expect(onTrimNarration).toHaveBeenCalledWith({ segmentId: "segment-offset", startSec: 3, endSec: 20 });
  });

  it("shows a local trim draft while moving and restores the original geometry on cancel", () => {
    const onTrimNarration = vi.fn();
    render(<TimelineDock onTrimNarration={onTrimNarration} view={view} viewportWidthPx={400} />);
    selectTimelineClip("n-1");
    mockTimelineTrackRect();

    const control = screen.getByRole("button", { name: "n-1 시작 자르기" });
    pointer(control, "pointerdown", 0);
    pointer(control, "pointermove", 200);
    expect(timelineClip("n-1")).toHaveAttribute("data-start-seconds", "2");
    expect(timelineClip("n-1")).toHaveStyle({ left: "200px", width: "200px" });
    expect(onTrimNarration).not.toHaveBeenCalled();

    pointer(control, "pointercancel", 200);
    expect(timelineClip("n-1")).toHaveAttribute("data-start-seconds", "0");
    expect(timelineClip("n-1")).toHaveStyle({ left: "0px", width: "400px" });
    expect(onTrimNarration).not.toHaveBeenCalled();
  });

  it("shows a local reorder layout while moving and restores the original order on cancel", () => {
    const onReorderNarration = vi.fn();
    render(<TimelineDock onReorderNarration={onReorderNarration} view={twoNarrationView} viewportWidthPx={400} />);
    selectTimelineClip("n-1");
    mockTimelineTrackRect();

    const control = screen.getByRole("button", { name: "n-1 순서 바꾸기" });
    pointer(control, "pointerdown", 0);
    pointer(control, "pointermove", 250);
    expect(screen.getAllByTestId("timeline-clip").slice(0, 2).map((clip) => clip.getAttribute("data-clip-id"))).toEqual(["n-2", "n-1"]);
    expect(timelineClip("n-1")).toHaveAttribute("data-start-seconds", "1");
    expect(onReorderNarration).not.toHaveBeenCalled();

    pointer(control, "pointercancel", 250);
    expect(screen.getAllByTestId("timeline-clip").slice(0, 2).map((clip) => clip.getAttribute("data-clip-id"))).toEqual(["n-1", "n-2"]);
    expect(timelineClip("n-1")).toHaveAttribute("data-start-seconds", "0");
    expect(onReorderNarration).not.toHaveBeenCalled();
  });

  it("finishes one long reorder on the stable track after the selected control moves off viewport", () => {
    const onReorderNarration = vi.fn();
    render(<TimelineDock onReorderNarration={onReorderNarration} view={longNarrationView} viewportWidthPx={200} />);
    const timeline = screen.getByRole("region", { name: "타임라인" });
    fireEvent.wheel(timeline, { deltaX: 50 });
    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "0.5");
    selectTimelineClip("long-1");
    mockTimelineTrackRect();

    const control = screen.getByRole("button", { name: "long-1 순서 바꾸기" });
    const track = screen.getByTestId("timeline-track");
    pointer(control, "pointerdown", 0);
    pointer(control, "pointermove", 1_000);
    expect(screen.queryByRole("button", { name: "long-1 순서 바꾸기" })).toBeNull();
    pointer(track, "pointerup", 1_000);

    expect(onReorderNarration).toHaveBeenCalledTimes(1);
    expect(onReorderNarration).toHaveBeenCalledWith(expect.objectContaining({
      segmentIds: [
        "long-segment-2", "long-segment-3", "long-segment-4", "long-segment-5", "long-segment-6",
        "long-segment-7", "long-segment-8", "long-segment-9", "long-segment-10", "long-segment-1",
      ],
    }));
  });

  it("cancels a long off-viewport reorder on the stable track and restores the original clip", () => {
    const onReorderNarration = vi.fn();
    render(<TimelineDock onReorderNarration={onReorderNarration} view={longNarrationView} viewportWidthPx={200} />);
    fireEvent.wheel(screen.getByRole("region", { name: "타임라인" }), { deltaX: 50 });
    selectTimelineClip("long-1");
    mockTimelineTrackRect();

    const control = screen.getByRole("button", { name: "long-1 순서 바꾸기" });
    const track = screen.getByTestId("timeline-track");
    pointer(control, "pointerdown", 0);
    pointer(control, "pointermove", 1_000);
    expect(screen.queryByText("long-1")).toBeNull();
    pointer(track, "pointercancel", 1_000);

    expect(timelineClip("long-1")).toHaveAttribute("data-start-seconds", "0");
    expect(screen.getByRole("button", { name: "long-1 순서 바꾸기" })).toBeInTheDocument();
    expect(onReorderNarration).not.toHaveBeenCalled();
  });

  it("trims the selected narration by one frame with keyboard arrows", () => {
    const onTrimNarration = vi.fn();
    render(<TimelineDock onTrimNarration={onTrimNarration} view={view} viewportWidthPx={400} />);
    selectTimelineClip("n-1");

    fireEvent.keyDown(screen.getByRole("button", { name: "n-1 시작 자르기" }), { key: "ArrowRight" });
    fireEvent.keyDown(screen.getByRole("button", { name: "n-1 끝 자르기" }), { key: "ArrowLeft" });

    expect(onTrimNarration).toHaveBeenNthCalledWith(1, { segmentId: "segment-1", startSec: 0.04, endSec: 5 });
    expect(onTrimNarration).toHaveBeenNthCalledWith(2, { segmentId: "segment-1", startSec: 0, endSec: 4.96 });
  });

  it("reorders the selected narration by one position with keyboard arrows", () => {
    const onReorderNarration = vi.fn();
    render(<TimelineDock onReorderNarration={onReorderNarration} view={twoNarrationView} viewportWidthPx={400} />);
    selectTimelineClip("n-1");

    fireEvent.keyDown(screen.getByRole("button", { name: "n-1 순서 바꾸기" }), { key: "ArrowRight" });

    expect(onReorderNarration).toHaveBeenCalledTimes(1);
    expect(onReorderNarration).toHaveBeenCalledWith(expect.objectContaining({ segmentIds: ["segment-2", "segment-1"] }));
  });

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

  it("keeps the fixed lane list free of non-listitem direct children", () => {
    render(<TimelineDock view={view} viewportWidthPx={400} />);

    const laneList = screen.getByRole("list", { name: "고정 트랙" });
    expect(Array.from(laneList.children)).toHaveLength(5);
    expect(Array.from(laneList.children).every((child) => child.getAttribute("role") === "listitem")).toBe(true);
    expect(screen.getByRole("group", { name: "타임라인 클립" })).not.toBe(laneList);
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
    fireEvent.click(timelineClipSelection("n-1"));
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
