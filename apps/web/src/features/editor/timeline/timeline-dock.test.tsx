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
  captions: [{ segmentId: "segment-1", text: "첫 자막", startSec: 0, endSec: 5, style: { fontFamily: "Pretendard", fontSizePx: 28, textColor: "#fff", outlineColor: "#000", outlineWidthPx: 1, backgroundColor: "#00000000", positionXPercent: 50, positionYPercent: 90, horizontalAlign: "center", safeAreaEnabled: true, shadowBlurPx: 0, bold: false, italic: false, letterSpacingPx: 0 } }],
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
  const clip = timelineClip(clipId);
  const button = clip.querySelector('[data-native-control="timeline-clip-select"]');
  if (!button) throw new Error(`Missing selection control for ${clipId}`);
  return button as HTMLButtonElement;
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
  it("selects and seeks an independent media placement through the same timeline click", () => {
    const onSelectSegment = vi.fn();
    const onPlaybackSeek = vi.fn();
    const placed = {
      ...view,
      tracks: view.tracks.map((track) => track.role === "broll"
        ? { ...track, clips: track.clips.map((clip) => ({ ...clip, placementId: "broll:b-1" })) }
        : track),
    };
    render(<TimelineDock view={placed} viewportWidthPx={1000} onSelectSegment={onSelectSegment} onPlaybackSeek={onPlaybackSeek} />);

    selectTimelineClip("broll:b-1");

    expect(onSelectSegment).toHaveBeenCalledWith("segment-2");
    expect(onPlaybackSeek).toHaveBeenCalledWith(5);
  });

  it("commits one frame-snapped placement update for a selected independent lane", () => {
    const onUpdatePlacements = vi.fn();
    const mutable = { ...view, tracks: view.tracks.map((track) => track.role === "broll" ? { ...track, clips: track.clips.map((clip) => ({ ...clip, placementId: "broll:b-1" })) } : track) };
    render(<TimelineDock view={mutable} viewportWidthPx={1000} onUpdatePlacements={onUpdatePlacements} />);

    selectTimelineClip("broll:b-1");
    fireEvent.keyDown(screen.getByRole("button", { name: "영상 1번째 장면, 5초부터 이동" }), { key: "ArrowRight" });

    expect(onUpdatePlacements).toHaveBeenCalledWith({ changes: [{ placementId: "broll:b-1", kind: "broll", startSec: 5.04, endSec: 9.04 }] });
  });
  /** **스페이스는 더 이상 고르기가 아니다**(owner 지적, 2026-09-05). 장면 칸이
   *  `<button>`이라 스페이스를 자기가 먹었고, 그래서 장면을 한 번 고르면
   *  타임라인에서 스페이스를 눌러도 재생/정지가 안 됐다. 편집기 타임라인에서
   *  스페이스는 재생/정지가 업계 표준이고 캡컷도 그렇다 --
   *  `preview/preview-stage.test.tsx`가 그쪽을 지킨다. 고르기는 클릭과 Enter다. */
  it("selects narration clips with Enter, leaving Space to play and pause", () => {
    render(<TimelineDock view={twoNarrationView} viewportWidthPx={400} />);

    const firstClip = timelineClipSelection("n-1");
    firstClip.focus();
    expect(firstClip).toHaveFocus();
    fireEvent.keyDown(firstClip, { key: "Enter" });
    expect(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" })).toBeInTheDocument();

    const secondClip = timelineClipSelection("n-2");
    secondClip.focus();
    expect(secondClip).toHaveFocus();
    fireEvent.keyDown(secondClip, { key: " " });
    // 고른 장면이 그대로다 -- 스페이스는 재생 쪽으로 지나간다.
    expect(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "내레이션 2번째 장면, 1초부터 시작 자르기" })).toBeNull();
    fireEvent.keyDown(secondClip, { key: "Enter" });
    expect(screen.getByRole("button", { name: "내레이션 2번째 장면, 1초부터 시작 자르기" })).toBeInTheDocument();
  });

  it("marks the timeline as a surface where the space bar plays", () => {
    // 표시가 사라지면 스페이스가 다시 안 먹는다 -- 읽는 곳은
    // `preview/preview-stage.tsx` 한 곳뿐이라 여기서 못박아 둔다.
    render(<TimelineDock view={twoNarrationView} viewportWidthPx={400} />);

    expect(screen.getByRole("region", { name: "타임라인" })).toHaveAttribute("data-timeline-surface", "true");
  });

  it("keeps the selection button separate from narration mutation buttons", () => {
    render(<TimelineDock view={view} viewportWidthPx={400} />);

    const selection = timelineClipSelection("n-1");
    fireEvent.click(selection);

    expect(selection).toHaveAttribute("aria-pressed", "true");
    expect(selection).not.toContainElement(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" }));
    expect(selection).not.toContainElement(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 끝 자르기" }));
    expect(selection).not.toContainElement(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 순서 바꾸기" }));
  });

  it("anchors trim handles and the reorder control inside the selected clip", () => {
    render(<TimelineDock view={view} viewportWidthPx={400} />);
    selectTimelineClip("n-1");

    const start = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" });
    const end = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 끝 자르기" });
    const reorder = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 순서 바꾸기" });
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

    expect(screen.queryByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" })).toBeNull();
    selectTimelineClip("n-1");
    expect(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 끝 자르기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 순서 바꾸기" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "b-1 시작 자르기" })).toBeNull();
  });

  it("keeps trim pointer moves local and commits one meaningful frame-aligned result on pointer up", () => {
    const onTrimNarration = vi.fn();
    render(<TimelineDock onTrimNarration={onTrimNarration} view={view} viewportWidthPx={400} />);
    selectTimelineClip("n-1");
    mockTimelineRect("n-1");
    mockTimelineTrackRect();

    const control = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" });
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

    const control = screen.getByRole("button", { name: "내레이션 1번째 장면, 3초부터 시작 자르기" });
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

    const control = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 끝 자르기" });
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

    const control = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 순서 바꾸기" });
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

    const control = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 순서 바꾸기" });
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

    const control = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 순서 바꾸기" });
    pointer(control, "pointerdown", 140);
    pointer(control, "pointerup", 140);

    expect(onReorderNarration).not.toHaveBeenCalled();
    expect(timelineClip("long-1")).toHaveAttribute("data-start-seconds", "0");
  });

  it("disables narration mutation controls while saving", () => {
    const onTrimNarration = vi.fn();
    render(<TimelineDock isSaving mutationMessage="저장 중" onTrimNarration={onTrimNarration} view={view} viewportWidthPx={400} />);

    selectTimelineClip("n-1");
    const control = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" });
    expect(control).toBeDisabled();
    expect(screen.getByText("저장 중")).toBeInTheDocument();
    pointer(control, "pointerdown", 0);
    pointer(control, "pointerup", 100);
    expect(onTrimNarration).not.toHaveBeenCalled();
  });

  it("keeps mutation-control clicks out of the existing clip selection handler", () => {
    render(<TimelineDock view={view} viewportWidthPx={400} />);

    selectTimelineClip("n-1");
    fireEvent.click(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" }));
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

    const control = screen.getByRole("button", { name: "내레이션 1번째 장면, 3초부터 시작 자르기" });
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

    const control = screen.getByRole("button", { name: "내레이션 1번째 장면, 3초부터 끝 자르기" });
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

    const control = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" });
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

    const control = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 순서 바꾸기" });
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

    const control = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 순서 바꾸기" });
    const track = screen.getByTestId("timeline-track");
    pointer(control, "pointerdown", 0);
    pointer(control, "pointermove", 1_000);
    expect(screen.queryByRole("button", { name: "내레이션 1번째 장면, 0초부터 순서 바꾸기" })).toBeNull();
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

    const control = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 순서 바꾸기" });
    const track = screen.getByTestId("timeline-track");
    pointer(control, "pointerdown", 0);
    pointer(control, "pointermove", 1_000);
    expect(screen.queryByText("long-1")).toBeNull();
    pointer(track, "pointercancel", 1_000);

    expect(timelineClip("long-1")).toHaveAttribute("data-start-seconds", "0");
    expect(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 순서 바꾸기" })).toBeInTheDocument();
    expect(onReorderNarration).not.toHaveBeenCalled();
  });

  it("trims the selected narration by one frame with keyboard arrows", () => {
    const onTrimNarration = vi.fn();
    render(<TimelineDock onTrimNarration={onTrimNarration} view={view} viewportWidthPx={400} />);
    selectTimelineClip("n-1");

    fireEvent.keyDown(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" }), { key: "ArrowRight" });
    fireEvent.keyDown(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 끝 자르기" }), { key: "ArrowLeft" });

    expect(onTrimNarration).toHaveBeenNthCalledWith(1, { segmentId: "segment-1", startSec: 0.04, endSec: 5 });
    expect(onTrimNarration).toHaveBeenNthCalledWith(2, { segmentId: "segment-1", startSec: 0, endSec: 4.96 });
  });

  it("reorders the selected narration by one position with keyboard arrows", () => {
    const onReorderNarration = vi.fn();
    render(<TimelineDock onReorderNarration={onReorderNarration} view={twoNarrationView} viewportWidthPx={400} />);
    selectTimelineClip("n-1");

    fireEvent.keyDown(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 순서 바꾸기" }), { key: "ArrowRight" });

    expect(onReorderNarration).toHaveBeenCalledTimes(1);
    expect(onReorderNarration).toHaveBeenCalledWith(expect.objectContaining({ segmentIds: ["segment-2", "segment-1"] }));
  });

  it("renders fixed lanes, only visible clips, ruler, gaps, captions, nearest source snap, and local playhead", () => {
    render(<TimelineDock view={view} viewportWidthPx={400} />);

    const timeline = screen.getByRole("region", { name: "타임라인" });
    expect(timeline).toHaveAttribute("tabindex", "0");
    expect(screen.getAllByRole("listitem", { name: /내레이션/ })).toHaveLength(1);
    expect(screen.getAllByRole("listitem", { name: /영상/ })).toHaveLength(1);
    expect(screen.getAllByRole("listitem", { name: /배경 음악/ })).toHaveLength(1);
    expect(screen.getAllByRole("listitem", { name: /효과음/ })).toHaveLength(1);
    expect(screen.getAllByRole("listitem", { name: /오버레이/ })).toHaveLength(1);
    expect(screen.getByTestId("timeline-clip")).toHaveAttribute("data-clip-id", "n-1");
    expect(screen.queryByText("o-late")).toBeNull();
    expect(screen.getByLabelText("눈금 0초")).toBeInTheDocument();
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "0");
    expect(screen.getByText("미디어 공백: asset_required")).toBeInTheDocument();
    expect(screen.getByText("현재 캡션: 첫 자막")).toBeInTheDocument();
    expect(screen.getByText((_, element) => element?.textContent === "스냅: 항목 시작 (0초)" )).toBeInTheDocument();
  });

  it("names each clip in plain language instead of exposing its internal clip ID", () => {
    const earlyBrollView: EditorViewModel = {
      ...view,
      tracks: [
        ...view.tracks.filter((track) => track.role !== "broll"),
        { trackId: "b", role: "broll", clips: [{ clipId: "b-1", segmentId: "segment-2", type: "broll", assetId: null, assetUri: null, startSec: 1, endSec: 3, controls: {} }] },
      ],
    };
    render(<TimelineDock view={earlyBrollView} viewportWidthPx={400} />);

    // n-1 is the 1st (and only) narration clip, starting at 0s.
    expect(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터" })).toBeInTheDocument();
    // b-1 is the 1st (and only) broll clip, starting at 1s.
    expect(screen.getByRole("button", { name: "영상 1번째 장면, 1초부터" })).toBeInTheDocument();
    expect(screen.queryByText("n-1")).not.toBeInTheDocument();
    expect(screen.queryByText("b-1")).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/segment_draft|session-broll/);
  });

  it("numbers clips by their position within their own lane, not across all lanes", () => {
    render(<TimelineDock view={twoNarrationView} viewportWidthPx={400} />);

    expect(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "내레이션 2번째 장면, 1초부터" })).toBeInTheDocument();
  });

  it("shows a short left-anchored name whose text is the start of the accessible name", () => {
    // 전체 이름("내레이션 1번째 장면, 0초부터")을 막대 전체에 깔면 썸네일·파형이
    // 덮인다. 보이는 것은 짧은 이름뿐이되, 접근 이름의 **앞부분**이어야 한다 --
    // 보이는 글자로 음성 호출했을 때 어긋나지 않는 조건이고, 내부 ID가 보이는
    // 글자로 새는 것도 함께 막는다(F-3).
    render(<TimelineDock view={view} viewportWidthPx={400} />);

    const selectionButton = timelineClipSelection("n-1");
    expect(selectionButton).toHaveAccessibleName("내레이션 1번째 장면, 0초부터");
    expect(selectionButton.textContent).toBe("내레이션 1");
    expect("내레이션 1번째 장면, 0초부터".startsWith(selectionButton.textContent ?? "")).toBe(true);
    const name = selectionButton.querySelector(".vb-timeline-clip__name");
    expect(name).not.toBeNull();
  });

  it("shows a linked caption but never exposes independent caption timing controls", () => {
    const captionPlacementView: EditorViewModel = {
      ...view,
      captions: [{ ...view.captions[0], placementId: "caption:segment-1" }],
    };
    render(<TimelineDock view={captionPlacementView} viewportWidthPx={400} />);

    selectTimelineClip("caption:segment-1");

    expect(screen.queryByRole("button", { name: "caption:segment-1 이동" })).toBeNull();
    expect(screen.queryByRole("button", { name: "caption:segment-1 시작 자르기" })).toBeNull();
    expect(screen.queryByRole("button", { name: "caption:segment-1 끝 자르기" })).toBeNull();
  });

  it("keeps the fixed lane list free of non-listitem direct children", () => {
    render(<TimelineDock view={view} viewportWidthPx={400} />);

    const laneList = screen.getByRole("list", { name: "고정 트랙" });
    expect(Array.from(laneList.children)).toHaveLength(6);
    expect(Array.from(laneList.children).every((child) => child.getAttribute("role") === "listitem")).toBe(true);
    expect(screen.getByRole("group", { name: "타임라인 클립" })).not.toBe(laneList);
  });

  it("트랙 이름과 잠금·눈·음소거가 클립에 가리지 않는다", () => {
    // **2026-09-03 실측:** 클립 층은 트랙 전체를 `inset: 0`으로 덮는다. 고정 트랙
    // 줄이 그 아래 깔려 있어서, 0초에서 시작하는 클립이 있으면 트랙 이름과 버튼이
    // 통째로 가려졌다 -- 클립 배경이 불투명이라 **보이지도 않고**, 누르면 버튼이
    // 아니라 **클립이 선택됐다**(브라우저에서 트랙 버튼 13개 전부 확인).
    //
    // jsdom은 자리를 계산하지 않아 "가려졌다"를 직접 잴 수 없다. 그래서 가리지
    // 않게 하는 두 조건을 지킨다: 클립 층보다 위에 있을 것, 그리고 빈 자리는
    // 통과시켜 이번엔 반대로 클립을 못 누르는 일이 없을 것.
    render(<TimelineDock view={view} viewportWidthPx={400} />);

    const laneRow = screen.getByRole("list", { name: "고정 트랙" }).children[0] as HTMLElement;
    expect(Number(laneRow.style.zIndex)).toBeGreaterThan(0);
    expect(laneRow.style.pointerEvents).toBe("none");

    for (const name of ["내레이션 트랙 잠금", "내레이션 트랙 음소거"]) {
      expect(screen.getByRole("button", { name }).style.pointerEvents).toBe("auto");
    }
  });

  it("locks a track so its clips cannot be trimmed or moved until unlocked again", () => {
    // owner 지시 2026-08-22: 트랙 잠금이 있어야 한다. 이 잠금은 세션 동안만 유지되고
    // (새로고침하면 풀림), 눌린 트랙의 자르기·순서 바꾸기·이동 버튼을 막는다.
    render(<TimelineDock view={view} viewportWidthPx={400} />);
    selectTimelineClip("n-1");

    const start = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" });
    expect(start).not.toBeDisabled();

    const lockButton = screen.getByRole("button", { name: "내레이션 트랙 잠금" });
    expect(lockButton).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(lockButton);
    expect(lockButton).toHaveAttribute("aria-pressed", "true");

    expect(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 끝 자르기" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 순서 바꾸기" })).toBeDisabled();

    fireEvent.click(lockButton);
    expect(lockButton).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" })).not.toBeDisabled();
  });

  it("offers eye and mute only on the tracks where they would do something", () => {
    // `capcut-observed` 기록 §2는 트랙마다 잠금·눈·음소거를 그리지만, 우리는
    // **뜻이 있는 것만** 그린다(기록 §4: "띠에 없는 기능의 자리를 만들지
    // 않는다"). 캡션 트랙 음소거는 눌러도 아무 일도 안 일어나고, 서버도
    // 그 조합을 422로 거절한다(`track_states.py`).
    render(<TimelineDock view={view} viewportWidthPx={400} onUpdateTrackStates={vi.fn()} />);

    expect(screen.getByRole("button", { name: "영상 트랙 숨기기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "영상 트랙 음소거" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "내레이션 트랙 음소거" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "내레이션 트랙 숨기기" })).toBeNull();
    expect(screen.getByRole("button", { name: "캡션 트랙 숨기기" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "캡션 트랙 음소거" })).toBeNull();
    expect(screen.queryByRole("button", { name: "배경 음악 트랙 숨기기" })).toBeNull();
  });

  it("sends the whole track-state map, not just the one that changed", () => {
    // 서버는 보낸 것을 전체 상태로 받는다. 누른 것만 보내면 이미 켜져 있던
    // 다른 트랙의 눈·음소거가 조용히 꺼진다.
    const onUpdateTrackStates = vi.fn();
    const withStates: EditorViewModel = { ...view, trackStates: { bgm: { muted: true } } };
    render(<TimelineDock view={withStates} viewportWidthPx={400} onUpdateTrackStates={onUpdateTrackStates} />);

    fireEvent.click(screen.getByRole("button", { name: "영상 트랙 숨기기" }));

    expect(onUpdateTrackStates).toHaveBeenCalledWith({ broll: { hidden: true }, bgm: { muted: true } });
  });

  it("draws eye and mute from the saved session, not from its own state", () => {
    // 저장이 원본이다. 화면이 따로 들고 있으면 저장이 실패해도 켜진 것처럼 보인다.
    const hiddenBroll: EditorViewModel = { ...view, trackStates: { broll: { hidden: true } } };
    render(<TimelineDock view={hiddenBroll} viewportWidthPx={400} onUpdateTrackStates={vi.fn()} />);

    expect(screen.getByRole("button", { name: "영상 트랙 숨기기" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "영상 트랙 음소거" })).toHaveAttribute("aria-pressed", "false");
  });

  it("shows eye and mute disabled rather than hidden when nothing can save them", () => {
    // 있는데 안 되는 것과 아예 없는 것은 다르다.
    render(<TimelineDock view={view} viewportWidthPx={400} />);

    expect(screen.getByRole("button", { name: "영상 트랙 숨기기" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "영상 트랙 음소거" })).toBeDisabled();
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

  it("draws the clip's own picture on video clips instead of only its name", () => {
    // 캡컷은 클립 위에 영상 썸네일을 그린다. 눈으로 어디가 어느 장면인지 찾는 것이
    // 그것이다. 지금은 `영상 1번째 장면, 0초부터` 같은 글자뿐이라 화면만 보고는
    // 무엇이 들어 있는지 알 수 없었다.
    //
    // 그림은 새로 만들지 않는다. 자산 카드가 이미 쓰는 그 주소를 그대로 쓴다.
    const withPicture: EditorViewModel = {
      ...view,
      tracks: view.tracks.map((track) => track.role === "broll"
        ? { ...track, clips: track.clips.map((clip) => ({ ...clip, assetId: "asset-b" })) }
        : track),
    };
    // 400px면 0~4초만 보이고 5~9초 B-roll은 그려지지도 않는다.
    // 주소는 소유자가 정해서 넘긴다 -- 타임라인은 서버를 알지 않는다.
    render(<TimelineDock view={withPicture} viewportWidthPx={1000} clipPictures={new Map([["b-1", "/api/projects/p/assets/asset-b/thumbnail"]])} />);

    const picture = document.querySelector('[data-clip-picture="true"]');
    expect(picture).not.toBeNull();
    expect(picture?.getAttribute("src")).toContain("/assets/asset-b/thumbnail");
  });

  it("draws a waveform on sound clips, not a video thumbnail", () => {
    // 소리에는 썸네일이 없다. 크고 작은 데를 눈으로 찾으려면 파형이어야 한다.
    const withSound: EditorViewModel = {
      ...view,
      tracks: [{
        trackId: "m", role: "bgm",
        clips: [{ clipId: "m-1", segmentId: "segment-1", type: "bgm", assetId: "asset-m", assetUri: null, startSec: 0, endSec: 4, controls: {} }],
      }],
      captions: [],
      gaps: [],
    };
    render(<TimelineDock view={withSound} viewportWidthPx={1000} clipPictures={new Map([["m-1", "/api/projects/p/assets/asset-m/waveform"]])} />);

    const picture = document.querySelector('[data-clip-picture="true"]');
    expect(picture?.getAttribute("src")).toContain("/assets/asset-m/waveform");
  });

  it("hides a picture that fails to load instead of showing a broken icon", () => {
    // 스냅샷을 보고 찾았다. 그 자산에 파형·썸네일이 없으면(ffmpeg가 없거나 404)
    // 클립 위에 **깨진 이미지 아이콘**이 그대로 뜬다. 그림이 없는 것과 고장난
    // 것처럼 보이는 것은 다르다.
    const withPicture: EditorViewModel = {
      ...view,
      tracks: view.tracks.map((track) => track.role === "broll"
        ? { ...track, clips: track.clips.map((clip) => ({ ...clip, assetId: "asset-b" })) }
        : track),
    };
    render(<TimelineDock view={withPicture} viewportWidthPx={1000} clipPictures={new Map([["b-1", "/missing.png"]])} />);

    const picture = document.querySelector('[data-clip-picture="true"]') as HTMLImageElement;
    fireEvent.error(picture);

    expect(document.querySelector('[data-clip-picture="true"]')).toBeNull();
  });

  it("never asks for a picture a clip has no asset for", () => {
    // 내레이션 클립에는 영상이 없다. 없는 그림을 부르면 매 클립마다 404가 나간다.
    render(<TimelineDock view={view} viewportWidthPx={400} />);

    const narration = screen.getAllByTestId("timeline-clip").find((clip) => clip.getAttribute("data-clip-id") === "n-1");
    expect(narration?.querySelector('[data-clip-picture="true"]')).toBeNull();
  });

  it("puts timeline zoom on visible controls, not only on keys nobody presses", () => {
    // 확대·축소는 `+`/`-` 키로만 됐다. 안내 문구에 적혀 있어도 **눈에 보이는 단추가
    // 없으면 안 쓰는 기능**이다 -- 2026-08-17에 컷 도구가 정확히 그랬다(엔진은 다
    // 있는데 부를 자리가 없었다). 키와 단추는 같은 경로를 탄다.
    render(<TimelineDock view={view} viewportWidthPx={400} />);
    const timeline = screen.getByRole("region", { name: "타임라인" });
    expect(timeline).toHaveAttribute("data-pixels-per-second", "100");

    fireEvent.click(screen.getByRole("button", { name: "타임라인 확대" }));
    expect(timeline).toHaveAttribute("data-pixels-per-second", "125");
    fireEvent.click(screen.getByRole("button", { name: "타임라인 축소" }));
    expect(timeline).toHaveAttribute("data-pixels-per-second", "100");
  });

  it("fits the whole timeline into view with one control", () => {
    // 확대·축소는 한 칸씩만 움직인다. 긴 영상에서 전체를 다시 보려면 축소를
    // 열 번 눌러야 했다 -- 캡컷에는 전체 맞춤이 따로 있다. 확대와 **같은
    // 경로**를 타므로 계산이 두 벌이 되지 않는다.
    render(<TimelineDock view={view} viewportWidthPx={400} />);
    const timeline = screen.getByRole("region", { name: "타임라인" });
    fireEvent.wheel(timeline, { deltaX: 600 });
    fireEvent.click(screen.getByRole("button", { name: "타임라인 확대" }));
    expect(timeline).not.toHaveAttribute("data-viewport-start-seconds", "0");

    fireEvent.click(screen.getByRole("button", { name: "타임라인 전체 보기" }));

    // 20초짜리를 400px에 담으면 초당 20px이고, 왼쪽 끝에서 시작한다.
    expect(timeline).toHaveAttribute("data-pixels-per-second", "20");
    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "0");
  });

  it("starts from an externally owned playback position without bouncing it back to zero", () => {
    const onPlaybackSeek = vi.fn();
    render(<TimelineDock onPlaybackSeek={onPlaybackSeek} playbackSec={2.5} view={view} viewportWidthPx={400} />);

    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "2.5");
    expect(onPlaybackSeek).toHaveBeenCalledWith(2.5);
  });

  it("never names an edit control with an internal clip id", () => {
    // 장면을 고르면 `clip_narration_7568b55139 시작 자르기` 같은 이름이 나왔다.
    // 사용자에게 내부 clip ID를 그대로 보여 주는 것은 §10.13 위반이고, 애초에
    // 무엇을 자르는지 알 수 없다. 같은 자리에 이미 사람이 읽는 이름이 있다.
    render(<TimelineDock view={view} viewportWidthPx={1000} />);
    selectTimelineClip("n-1");

    for (const control of ["시작 자르기", "끝 자르기", "순서 바꾸기"]) {
      const button = screen.getByRole("button", { name: new RegExp(`${control}$`) });
      expect(button.getAttribute("aria-label")).not.toContain("n-1");
      expect(button.getAttribute("aria-label")).toContain("번째 장면");
    }
  });

  it("draws the playhead as a line the eye can find, not just a number", () => {
    // 캡컷은 재생 위치가 눈금부터 트랙까지 관통하는 세로선이다. 우리는 맨 아래에
    // 숫자 하나뿐이라 어디서 나뉘는지 보이지 않았다. 2026-08-17 owner 지적.
    render(<TimelineDock playbackSec={3} view={view} viewportWidthPx={1000} />);

    const marker = screen.getByTestId("timeline-playhead");
    expect(marker).toHaveAttribute("data-seconds", "3");
    // 화면 밖 상태가 아니라 실제 좌표를 갖는다.
    expect(marker.style.left).toBe("300px");
  });

  it("moves the playhead line together with the position", () => {
    render(<TimelineDock view={view} viewportWidthPx={1000} />);
    const timeline = screen.getByLabelText("타임라인");
    timeline.getBoundingClientRect = () => ({ left: 0, top: 0, right: 1000, bottom: 200, width: 1000, height: 200, x: 0, y: 0, toJSON: () => ({}) });

    fireEvent.click(timeline, { clientX: 250 });

    expect(screen.getByTestId("timeline-playhead").style.left).toBe("250px");
  });

  it("keeps moving the playhead when the owner echoes the position back", () => {
    // 2026-08-17에 실제 앱에서 확인: 타임라인을 눌러도 재생 위치가 첫 클릭 자리에
    // 붙박였다. 우리가 올려보낸 위치가 `playbackSec`으로 되돌아오는데, 그때 우리
    // playheadSec은 이미 다음 자리로 가 있어서 서로를 되돌리는 고리가 생겼다.
    // 그래서 `나누기`가 영영 열리지 않았다.
    const { rerender } = render(<TimelineDock onPlaybackSeek={() => undefined} playbackSec={0} view={view} viewportWidthPx={1000} />);
    const timeline = screen.getByLabelText("타임라인");
    timeline.getBoundingClientRect = () => ({ left: 0, top: 0, right: 1000, bottom: 200, width: 1000, height: 200, x: 0, y: 0, toJSON: () => ({}) });

    fireEvent.click(timeline, { clientX: 100 });
    const first = screen.getByLabelText("재생 위치").getAttribute("data-seconds");
    // 소유자가 그 값을 그대로 돌려준다 -- 실제 앱이 하는 일이다.
    rerender(<TimelineDock onPlaybackSeek={() => undefined} playbackSec={Number(first)} view={view} viewportWidthPx={1000} />);

    fireEvent.click(timeline, { clientX: 300 });

    expect(screen.getByLabelText("재생 위치")).not.toHaveAttribute("data-seconds", first);
  });

  it("drags the playhead to scrub the position, without a duplicate seek from the trailing click", () => {
    // 클릭만 되던 때는 자를 자리를 찾으려면 찍고 확인하고 다시 찍기를 반복해야
    // 했다. 트림 손잡이와 같은 상대 이동 방식이라 눈금 원점과 무관하게 정확하다.
    const onPlaybackSeek = vi.fn();
    render(<TimelineDock onPlaybackSeek={onPlaybackSeek} view={view} viewportWidthPx={400} />);
    const handle = screen.getByRole("button", { name: "재생 위치 끌기" });

    pointer(handle, "pointerdown", 100);
    pointer(handle, "pointermove", 300);
    // 문지르는 동안 위치가 실시간으로 움직인다 -- 미리보기가 그 자리를 바로 보여준다.
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "2");
    pointer(handle, "pointerup", 300);
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "2");
    expect(onPlaybackSeek).toHaveBeenCalledWith(2);

    // 드래그 끝에 브라우저가 쏘는 click이 타임라인 onClick으로 새면 좌표계가 다른
    // 두 번째 seek이 위치를 튕긴다. 단추에서 난 click은 무시되어야 한다.
    fireEvent.click(handle, { clientX: 40 });
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "2");
  });

  it("keeps the playhead where it is when the handle is pressed and released without moving", () => {
    render(<TimelineDock playbackSec={1.5} view={view} viewportWidthPx={400} />);
    const handle = screen.getByRole("button", { name: "재생 위치 끌기" });

    pointer(handle, "pointerdown", 150);
    pointer(handle, "pointerup", 150);

    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "1.5");
  });

  it("follows the playhead past the viewport edge during playback", () => {
    // 확대해 놓고 재생하면 재생 머리가 보이는 구간을 지나쳐 버리는데 타임라인은
    // 그대로였다. 밖에서 온 재생 위치가 구간을 벗어나면 뷰포트가 따라가야 한다.
    const { rerender } = render(<TimelineDock playbackSec={0} view={view} viewportWidthPx={400} />);
    const timeline = screen.getByRole("region", { name: "타임라인" });
    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "0");

    // 400px·초당 100px이면 0~4초만 보인다. 5초는 화면 밖이다.
    rerender(<TimelineDock playbackSec={5} view={view} viewportWidthPx={400} />);

    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "5");
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "5");
  });

  it("does not drag a deliberately scrolled viewport back to the resting playhead", () => {
    // 따라가기는 재생 위치가 **움직일 때**만이다. 편집자가 다른 구간을 보려고
    // 옆으로 민 뷰포트를 가만히 있는 재생 머리가 도로 끌어당기면 안 된다.
    render(<TimelineDock playbackSec={0} view={view} viewportWidthPx={400} />);
    const timeline = screen.getByRole("region", { name: "타임라인" });

    fireEvent.wheel(timeline, { deltaX: 600 });

    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "6");
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

  it("keeps a clip's displayed ordinal stable across scrolling instead of renumbering the visible batch", () => {
    render(<TimelineDock view={thousandClipHourView} viewportWidthPx={800} />);

    expect(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터" })).toBeInTheDocument();

    fireEvent.wheel(screen.getByRole("region", { name: "타임라인" }), { deltaX: 36_000 });

    // bulk-100 is the 101st narration clip overall -- it must read "101번째",
    // not renumber back to "1번째" just because it's now the first one
    // visible in the scrolled viewport.
    expect(screen.getByRole("button", { name: "내레이션 101번째 장면, 360초부터" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^내레이션 1번째/ })).not.toBeInTheDocument();
  });

  it("uses half-open filtering rather than a first-N cap for 1000 clips across a 60-minute fixture", () => {
    render(<TimelineDock view={thousandClipHourView} viewportWidthPx={800} />);

    expect(screen.getAllByTestId("timeline-clip")).toHaveLength(3);
    expect(screen.getAllByTestId("timeline-clip").map((clip) => clip.getAttribute("data-clip-id"))).toEqual(["bulk-0", "bulk-1", "bulk-2"]);
    expect(screen.getAllByTestId("timeline-clip").some((clip) => clip.getAttribute("data-clip-id") === "bulk-3")).toBe(false);

    fireEvent.wheel(screen.getByRole("region", { name: "타임라인" }), { deltaX: 36_000 });

    const laterClips = screen.getAllByTestId("timeline-clip");
    expect(laterClips.length).toBeLessThanOrEqual(300);
    expect(laterClips.map((clip) => clip.getAttribute("data-clip-id"))).toEqual(["bulk-100", "bulk-101", "bulk-102"]);
    expect(laterClips.some((clip) => clip.getAttribute("data-clip-id") === "bulk-99")).toBe(false);
  });
});

describe("타임라인 상태 문구", () => {
  it("영어 원값 대신 창작자 언어로 최신 여부를 말한다", () => {
    // `stale`은 원본 timeline provenance이며 현재 session 편집은 이미 반영돼 있다.
    render(<TimelineDock view={{ ...view, source: { status: "current" } } as never} viewportWidthPx={400} />);
    expect(screen.getByText(/원본과 편집본 일치/)).toBeInTheDocument();
    expect(screen.queryByText(/current/)).toBeNull();

    cleanup();

    render(<TimelineDock view={{ ...view, source: { status: "stale" } } as never} viewportWidthPx={400} />);
    expect(screen.getByText(/현재 편집본 기준/)).toBeInTheDocument();
    expect(screen.queryByText(/stale/)).toBeNull();
  });
});
