import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import type { EditorViewModel } from "../editorViewModel";
import { gapReasonLabel, TimelineDock } from "./TimelineDock";
import { createPlaybackClock } from "../preview/playbackClock";

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

/** **컷 편집 직후의 실제 모양**(2026-09-18 실물 재현: project 0907-b26195af).
 *  영상(broll) 트랙 0초 자리에 0.3초짜리 자투리 클립이 남는다 -- 자르기를 하면
 *  흔히 생기는 모양이고, 실제로 트랙 음소거 버튼이 이 클립의 클릭을 가로챘다.
 *  오버레이는 15초부터라 뭉치 폭 밖 -- "클립이 없으면 그대로 뜬다"는 대조군이다. */
const cutEditedBrollView: EditorViewModel = {
  ...view,
  tracks: [
    { trackId: "n", role: "narration", clips: [{ clipId: "n-1", segmentId: "segment-1", type: "narration", assetId: null, assetUri: null, startSec: 0, endSec: 5, controls: {} }] },
    { trackId: "b", role: "broll", clips: [
      { clipId: "b-cut-1", segmentId: "segment-2", type: "broll", assetId: null, assetUri: null, startSec: 0, endSec: 0.3, controls: {} },
      { clipId: "b-cut-2", segmentId: "segment-4", type: "broll", assetId: null, assetUri: null, startSec: 0.3, endSec: 9, controls: {} },
    ] },
    { trackId: "o", role: "overlay", clips: [{ clipId: "o-late", segmentId: "segment-3", type: "overlay", assetId: null, assetUri: null, startSec: 15, endSec: 18, controls: {} }] },
  ],
  captions: [],
  gaps: [],
};

/** **2026-09-18 실물 재현** (project 0907-b26195af, 사진 브이로그 실기 0907):
 *  오버레이 다섯 개가 `placementId`(=clipId) `overlay:export-overlay-
 *  timeline_001:001-0` 하나를 같이 쓰고 있었다 -- 내보내기 겹쳐얹기가 남긴
 *  자투리로 보인다. 이 중복이 `classifyTimelineHit`의 "clipId는 겹치면 안
 *  된다" 전제(`hit-testing.ts` `requireInput`)를 깨서, 콘솔에
 *  `RangeError: Rect clipIds must be unique`가 나며 **내레이션을 포함한
 *  타임라인 전체의 클릭 고르기가 통째로 죽었다** -- 트림 손잡이가 영영 안 뜨는
 *  것처럼 보인 진짜 원인이었다(dead-zone과는 별개 결함).*/
const duplicateOverlayPlacementView: EditorViewModel = {
  ...view,
  tracks: [
    { trackId: "n", role: "narration", clips: [{ clipId: "n-1", segmentId: "segment-1", type: "narration", assetId: null, assetUri: null, startSec: 0, endSec: 5, controls: {} }] },
    { trackId: "o1", role: "overlay", clips: [{ clipId: "o-a", segmentId: "segment-3", type: "overlay", assetId: null, assetUri: null, startSec: 6, endSec: 8, controls: {}, placementId: "overlay:dup" }] },
    { trackId: "o2", role: "overlay", clips: [{ clipId: "o-b", segmentId: "segment-4", type: "overlay", assetId: null, assetUri: null, startSec: 10, endSec: 12, controls: {}, placementId: "overlay:dup" }] },
  ],
  captions: [],
  gaps: [],
};

/** **2026-09-19 실물 재현**(project 0907-b26195af): 장면을 두 번 나누고 순서를
 *  바꾸면, 백엔드 세그먼트 배열의 순서가 화면 시간순과 어긋난다. 배열 순서
 *  그대로 순번을 매기면 "4번째 → 7번째 → 5번째"처럼 꼬인다 -- 화면에서
 *  실측했다. 여기 클립 배열도 일부러 시간순이 아니게(3초짜리를 맨 앞에) 둔다. */
const outOfOrderNarrationView: EditorViewModel = {
  ...view,
  tracks: [
    {
      trackId: "n",
      role: "narration",
      clips: [
        { clipId: "n-third", segmentId: "segment-third", type: "narration", assetId: null, assetUri: null, startSec: 6, endSec: 9, controls: {} },
        { clipId: "n-first", segmentId: "segment-first", type: "narration", assetId: null, assetUri: null, startSec: 0, endSec: 3, controls: {} },
        { clipId: "n-second", segmentId: "segment-second", type: "narration", assetId: null, assetUri: null, startSec: 3, endSec: 6, controls: {} },
      ],
    },
    ...view.tracks.filter((track) => track.role !== "narration"),
  ],
  captions: [],
  gaps: [],
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

// **처음 배율이 이제 영상 길이와 화면 폭에서 나온다**(`timelineZoomScale.ts`,
// 대표님 지시 2026-09-12): 한 화면에 60초, 영상이 그보다 짧으면 영상 전체.
// 그래서 60초 이하짜리는 처음부터 통째로 한 화면에 들어오고, **뷰포트가 실제로
// 옆으로 밀리는 일**을 재려면 60초보다 긴 영상이어야 한다. 아래 긴 fixture들이
// 그 자리다 -- 예전처럼 좁은 폭(200px)을 주는 것으로는 더 이상 만들 수 없다.
const longNarrationView: EditorViewModel = {
  ...view,
  output: { ...view.output, durationSec: 120 },
  tracks: [{
    trackId: "long-narration",
    role: "narration",
    clips: Array.from({ length: 10 }, (_, index) => ({
      clipId: `long-${index + 1}`,
      segmentId: `long-segment-${index + 1}`,
      type: "narration" as const,
      assetId: null,
      assetUri: null,
      startSec: index * 10,
      endSec: (index + 1) * 10,
      controls: {},
    })),
  }],
  captions: [],
  gaps: [],
};

/** 옆으로 밀 수 있는 영상 하나. 600px에 240초면 10px/초, 한 화면에 60초다. */
const scrollableView: EditorViewModel = {
  ...view,
  output: { ...view.output, durationSec: 240 },
  tracks: [{
    trackId: "n",
    role: "narration",
    clips: [{ clipId: "n-1", segmentId: "segment-1", type: "narration", assetId: null, assetUri: null, startSec: 0, endSec: 240, controls: {} }],
  }],
  captions: [],
  gaps: [],
};

/** 옆으로 민 뷰포트에서 0초가 아닌 클립을 자르는 자리. 위와 같은 배율(10px/초)이다. */
const scrolledOffsetView: EditorViewModel = {
  ...view,
  output: { ...view.output, durationSec: 120 },
  tracks: [{
    trackId: "n",
    role: "narration",
    clips: [{ clipId: "n-offset", segmentId: "segment-offset", type: "narration", assetId: null, assetUri: null, startSec: 30, endSec: 80, controls: {} }],
  }],
  captions: [],
  gaps: [],
};

/** 20초짜리 `view`를 예전과 같은 100px/초로 그리는 폭. 배율 규칙이 `폭 / 60초`가
 *  아니라 `폭 / 영상 길이`를 쓰는 구간이라 2000 / 20초 = 100px/초다. 아래 시험들이
 *  재는 것은 배율이 아니라 좌표 계산이라 그 기준을 그대로 유지한다. */
const WIDTH_FOR_100_PX_PER_SECOND = 2000;

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

function pointer(target: Element, type: string, clientX = 0, modifiers: { shiftKey?: boolean } = {}) {
  fireEvent(target, new MouseEvent(type, { bubbles: true, cancelable: true, clientX, ...modifiers }));
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
    // 자리는 CSS 클래스(.vb-trim-handle--start/end, .vb-clip-body-drag)가 정한다 -- 인라인 3등분은 없어졌다.
    expect(start).toHaveClass("vb-trim-handle", "vb-trim-handle--start");
    expect(end).toHaveAttribute("data-trim-edge", "end");
    expect(end).toHaveClass("vb-trim-handle", "vb-trim-handle--end");
    expect(reorder).toHaveAttribute("data-reorder-control", "true");
    expect(reorder).toHaveClass("vb-clip-body-drag");
  });

  it("겹치는 clipId을 가진 다른 레인이 있어도 내레이션 클립을 고르고 트림 손잡이를 볼 수 있다 (2026-09-18 실물 재현)", () => {
    const onSelectSegment = vi.fn();
    render(<TimelineDock onSelectSegment={onSelectSegment} view={duplicateOverlayPlacementView} viewportWidthPx={400} />);

    // 오버레이 레인에 clipId가 겹치는 클립 둘이 있어도 던지지 않는다 -- 던지면
    // 그 어떤 클립도(내레이션 포함) 고를 수 없다.
    expect(() => selectTimelineClip("n-1")).not.toThrow();
    expect(onSelectSegment).toHaveBeenCalledWith("segment-1");
    expect(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" })).toBeInTheDocument();
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
    render(<TimelineDock onTrimNarration={onTrimNarration} view={view} viewportWidthPx={WIDTH_FOR_100_PX_PER_SECOND} />);
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
    render(<TimelineDock onReorderNarration={onReorderNarration} view={longNarrationView} viewportWidthPx={600} />);
    const timeline = screen.getByRole("region", { name: "타임라인" });
    fireEvent.wheel(timeline, { deltaX: 50 });
    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "5");
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
    expect(timelineClip("n-1")).toHaveAttribute("data-selected", "true");
  });

  it("applies trim pointer movement as a relative delta for a nonzero clip in a scrolled viewport", () => {
    const onTrimNarration = vi.fn();
    // 10px/초, 한 화면에 60초. 200px를 밀면 20초 옆으로 간다.
    render(<TimelineDock onTrimNarration={onTrimNarration} view={scrolledOffsetView} viewportWidthPx={600} />);
    const timeline = screen.getByRole("region", { name: "타임라인" });
    fireEvent.wheel(timeline, { deltaX: 200 });
    selectTimelineClip("n-offset");
    mockTimelineRect("n-offset", 140);
    mockTimelineTrackRect(40);

    const control = screen.getByRole("button", { name: "내레이션 1번째 장면, 30초부터 시작 자르기" });
    pointer(control, "pointerdown", 240);
    pointer(control, "pointermove", 340);
    pointer(control, "pointerup", 340);

    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "20");
    expect(onTrimNarration).toHaveBeenCalledWith({ segmentId: "segment-offset", startSec: 40, endSec: 80 });
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
    render(<TimelineDock onTrimNarration={onTrimNarration} view={view} viewportWidthPx={WIDTH_FOR_100_PX_PER_SECOND} />);
    selectTimelineClip("n-1");
    mockTimelineTrackRect();

    const control = screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터 시작 자르기" });
    pointer(control, "pointerdown", 0);
    pointer(control, "pointermove", 200);
    expect(timelineClip("n-1")).toHaveAttribute("data-start-seconds", "2");
    // 20초가 전부 보이므로 막대가 화면 끝에서 잘리지 않는다: 2~5초 = 300px.
    expect(timelineClip("n-1")).toHaveStyle({ left: "200px", width: "300px" });
    expect(onTrimNarration).not.toHaveBeenCalled();

    pointer(control, "pointercancel", 200);
    expect(timelineClip("n-1")).toHaveAttribute("data-start-seconds", "0");
    expect(timelineClip("n-1")).toHaveStyle({ left: "0px", width: "500px" });
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
    render(<TimelineDock onReorderNarration={onReorderNarration} view={longNarrationView} viewportWidthPx={600} />);
    const timeline = screen.getByRole("region", { name: "타임라인" });
    fireEvent.wheel(timeline, { deltaX: 50 });
    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "5");
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
    render(<TimelineDock onReorderNarration={onReorderNarration} view={longNarrationView} viewportWidthPx={600} />);
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
    // 20초짜리는 처음 배율에서 통째로 한 화면에 들어온다(`timelineZoomScale.ts`).
    // "보이는 것만 그린다"는 아래에서 늘린 뒤에 다시 잰다.
    expect(screen.getAllByTestId("timeline-clip").map((clip) => clip.getAttribute("data-clip-id")).sort())
      .toEqual(["b-1", "n-1", "o-late"]);
    expect(screen.queryByText("o-late")).toBeNull();
    expect(screen.getByLabelText("눈금 0초")).toBeInTheDocument();
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "0");
    // §10.13: 내부 이유 코드(`asset_required`)는 화면에 나가지 않는다.
    expect(screen.getByText("빈 구간: 미디어 없음")).toBeInTheDocument();
    expect(screen.queryByText(/asset_required/)).toBeNull();
    expect(screen.getByText("현재 캡션: 첫 자막")).toBeInTheDocument();
    expect(screen.getByText((_, element) => element?.textContent === "스냅: 항목 시작 (0초)" )).toBeInTheDocument();

    // 늘리면 보이는 구간이 좁아지고, 그 밖의 막대는 **그려지지도 않는다.**
    for (let step = 0; step < 8; step += 1) fireEvent.keyDown(window, { key: "=", ctrlKey: true });
    expect(screen.getAllByTestId("timeline-clip").map((clip) => clip.getAttribute("data-clip-id"))).toEqual(["n-1"]);
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

  it("트랙 머리는 클립 층 밖의 고정 칸이라 0초 클립이 있어도 마우스로 눌린다 (2026-10-08 §3-4)", () => {
    const onUpdateTrackStates = vi.fn();
    render(<TimelineDock view={cutEditedBrollView} viewportWidthPx={400} onUpdateTrackStates={onUpdateTrackStates} />);

    const headers = screen.getByRole("list", { name: "고정 트랙" });
    const track = screen.getByTestId("timeline-track");
    expect(track.contains(headers)).toBe(false);
    expect(headers.contains(track)).toBe(false);
    expect(headers.closest(".vb-timeline-body")).toBe(track.closest(".vb-timeline-body"));
    for (const name of ["내레이션 트랙 잠금", "내레이션 트랙 음소거", "영상 트랙 잠금", "영상 트랙 숨기기", "영상 트랙 음소거"]) {
      expect(screen.getByRole("button", { name }).style.pointerEvents).toBe("");
    }
    fireEvent.click(screen.getByRole("button", { name: "영상 트랙 음소거" }));
    expect(onUpdateTrackStates).toHaveBeenCalledWith({ broll: { muted: true } });
    // 0초 자투리 클립도 그대로 고를 수 있다.
    selectTimelineClip("b-cut-1");
    expect(timelineClipSelection("b-cut-1")).toHaveAttribute("aria-pressed", "true");
  });

  it("머리 칸의 이름·빈자리·눈금 여백을 눌러도 재생 위치가 움직이지 않는다", () => {
    render(<TimelineDock view={view} viewportWidthPx={400} playbackSec={5} />);
    const playhead = screen.getByTestId("timeline-playhead");
    expect(playhead.getAttribute("data-seconds")).toBe("5");
    const headers = screen.getByRole("list", { name: "고정 트랙" });
    // 머리 칸은 클립 칸 왼쪽 밖이라 거기서 잰 x는 음수다 -- 그 클릭은 seek가 아니다.
    fireEvent.click(screen.getByText("영상"));
    fireEvent.click(headers.children[0] as HTMLElement);
    fireEvent.click(headers.parentElement!.querySelector(".vb-timeline-lane-headers__ruler-spacer") as HTMLElement);
    expect(playhead.getAttribute("data-seconds")).toBe("5");
  });

  it("제목 줄(\"타임라인\")을 눌러도 재생 위치가 0초로 움직이지 않는다(2026-10-09 실측)", () => {
    render(<TimelineDock view={view} viewportWidthPx={400} playbackSec={5} />);
    const playhead = screen.getByTestId("timeline-playhead");
    fireEvent.click(screen.getByRole("heading", { name: "타임라인" }), { clientX: 0 });
    expect(playhead.getAttribute("data-seconds")).toBe("5");
  });

  it("재생줄과 클립은 같은 원점(클립 칸 왼쪽)에 놓인다", () => {
    render(<TimelineDock view={view} viewportWidthPx={400} playbackSec={5} />);
    const playhead = screen.getByTestId("timeline-playhead");
    expect(playhead.parentElement).toBe(screen.getByTestId("timeline-track").parentElement);
    const n1 = screen.getAllByTestId("timeline-clip").find((clip) => clip.getAttribute("data-clip-id") === "b-1")!;
    expect(playhead.style.left).toBe(n1.style.left); // b-1은 5초에 시작한다
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
    render(<TimelineDock view={view} viewportWidthPx={WIDTH_FOR_100_PX_PER_SECOND} />);

    const timeline = screen.getByRole("region", { name: "타임라인" });
    // 클립 칸(머리 칸 밖)의 빈 자리를 누르면 그 시각으로 간다.
    fireEvent.click(screen.getByRole("group", { name: "타임라인 클립" }), { clientX: 200 });
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "2");
    expect(screen.getByText("스냅 없음")).toBeInTheDocument();
    fireEvent.keyDown(timeline, { key: "ArrowRight" });
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "2.04");
    fireEvent.keyDown(timeline, { key: "End" });
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "20");
    fireEvent.keyDown(timeline, { key: "Home" });
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "0");
    // 맨 `+`도 그대로 듣는다. 단축키를 더했다고 예전 키를 거두지 않는다.
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
    render(<TimelineDock view={view} viewportWidthPx={WIDTH_FOR_100_PX_PER_SECOND} />);
    const timeline = screen.getByRole("region", { name: "타임라인" });
    expect(timeline).toHaveAttribute("data-pixels-per-second", "100");

    fireEvent.click(screen.getByRole("button", { name: "타임라인 확대" }));
    expect(timeline).toHaveAttribute("data-pixels-per-second", "125");
    fireEvent.click(screen.getByRole("button", { name: "타임라인 축소" }));
    expect(timeline).toHaveAttribute("data-pixels-per-second", "100");
  });

  it("듣는 자리는 단추·키뿐 아니라 밖에서 오는 명령도 같은 표를 탄다", () => {
    // 유진에게 "타임라인 좀 늘려줘"라고 말해도 이 자리를 타야 한다(대표님 상시
    // 지시, task-3-brief.md). `EditorWorkbenchRoute`는 이 컴포넌트의 `dispatch`를
    // 모르므로, 단추·키와 같은 `runZoom` 표를 거치는 선언적 명령 하나가 필요하다.
    // `requestId`가 바뀔 때만 실행한다 -- 같은 명령을 값만 유지한 채 다시
    // 렌더하면(다른 상태 변화로) 또 실행되어 계속 늘어나는 사고를 막는다.
    const { rerender } = render(
      <TimelineDock view={view} viewportWidthPx={WIDTH_FOR_100_PX_PER_SECOND} zoomCommand={null} />,
    );
    const timeline = screen.getByRole("region", { name: "타임라인" });
    expect(timeline).toHaveAttribute("data-pixels-per-second", "100");

    rerender(
      <TimelineDock view={view} viewportWidthPx={WIDTH_FOR_100_PX_PER_SECOND} zoomCommand={{ command: "in", requestId: 1 }} />,
    );
    expect(timeline).toHaveAttribute("data-pixels-per-second", "125");

    // 같은 requestId로 다시 렌더해도 한 번 더 늘지 않는다.
    rerender(
      <TimelineDock view={view} viewportWidthPx={WIDTH_FOR_100_PX_PER_SECOND} zoomCommand={{ command: "in", requestId: 1 }} />,
    );
    expect(timeline).toHaveAttribute("data-pixels-per-second", "125");

    rerender(
      <TimelineDock view={view} viewportWidthPx={WIDTH_FOR_100_PX_PER_SECOND} zoomCommand={{ command: "out", requestId: 2 }} />,
    );
    expect(timeline).toHaveAttribute("data-pixels-per-second", "100");
  });

  it("fits the whole timeline into view with one control", () => {
    // 확대·축소는 한 칸씩만 움직인다. 긴 영상에서 전체를 다시 보려면 축소를
    // 열 번 눌러야 했다 -- 캡컷에는 전체 맞춤이 따로 있다. 확대와 **같은
    // 경로**를 타므로 계산이 두 벌이 되지 않는다.
    render(<TimelineDock view={scrollableView} viewportWidthPx={600} />);
    const timeline = screen.getByRole("region", { name: "타임라인" });
    fireEvent.wheel(timeline, { deltaX: 600 });
    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "60");

    fireEvent.click(screen.getByRole("button", { name: "타임라인 전체 보기" }));

    // 240초짜리를 600px에 담으면 초당 2.5px이고, 왼쪽 끝에서 시작한다.
    expect(timeline).toHaveAttribute("data-pixels-per-second", "2.5");
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
    // 화면 밖 상태가 아니라 실제 좌표를 갖는다. 1000px에 20초면 초당 50px이다.
    expect(marker.style.left).toBe("150px");
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
    render(<TimelineDock onPlaybackSeek={onPlaybackSeek} view={view} viewportWidthPx={WIDTH_FOR_100_PX_PER_SECOND} />);
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
    const { rerender } = render(<TimelineDock playbackSec={0} view={scrollableView} viewportWidthPx={600} />);
    const timeline = screen.getByRole("region", { name: "타임라인" });
    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "0");

    // 600px·초당 10px이면 0~60초만 보인다. 70초는 화면 밖이다.
    rerender(<TimelineDock playbackSec={70} view={scrollableView} viewportWidthPx={600} />);

    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "70");
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "70");
  });

  it("does not drag a deliberately scrolled viewport back to the resting playhead", () => {
    // 따라가기는 재생 위치가 **움직일 때**만이다. 편집자가 다른 구간을 보려고
    // 옆으로 민 뷰포트를 가만히 있는 재생 머리가 도로 끌어당기면 안 된다.
    render(<TimelineDock playbackSec={0} view={scrollableView} viewportWidthPx={600} />);
    const timeline = screen.getByRole("region", { name: "타임라인" });

    fireEvent.wheel(timeline, { deltaX: 600 });

    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "60");
    expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "0");
  });

  it("scrolls its local viewport from horizontal wheel pixels and clamps at both bounds", () => {
    render(<TimelineDock view={scrollableView} viewportWidthPx={600} />);

    const timeline = screen.getByRole("region", { name: "타임라인" });
    fireEvent.wheel(timeline, { deltaX: 200 });
    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "20");
    fireEvent.wheel(timeline, { deltaX: 10_000 });
    // 240초에서 보이는 60초를 뺀 180초가 오른쪽 끝이다.
    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "180");
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
    expect(timelineClip("n-1")).toHaveAttribute("data-selected", "true");

    rerender(<TimelineDock view={{ ...view, tracks: [], captions: [], gaps: [] }} viewportWidthPx={400} />);
    expect(screen.getByText("타임라인이 비어 있어요.")).toBeInTheDocument();
  });

  it("keeps a clip's displayed ordinal stable across scrolling instead of renumbering the visible batch", () => {
    render(<TimelineDock view={thousandClipHourView} viewportWidthPx={800} />);

    expect(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터" })).toBeInTheDocument();

    // 800px에 한 화면 60초면 초당 13.333px이다. 4800px를 밀면 360초 옆으로 간다.
    fireEvent.wheel(screen.getByRole("region", { name: "타임라인" }), { deltaX: 4_800 });

    // bulk-100 is the 101st narration clip overall -- it must read "101번째",
    // not renumber back to "1번째" just because it's now the first one
    // visible in the scrolled viewport.
    expect(screen.getByRole("button", { name: "내레이션 101번째 장면, 360초부터" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^내레이션 1번째/ })).not.toBeInTheDocument();
  });

  it("uses half-open filtering rather than a first-N cap for 1000 clips across a 60-minute fixture", () => {
    render(<TimelineDock view={thousandClipHourView} viewportWidthPx={800} />);

    // 한 화면 60초에 3.6초짜리 막대면 열일곱 개가 걸친다(마지막은 57.6~61.2초).
    // 1000개 가운데 **보이는 것만** 그려야 한다는 것이 이 시험이 지키는 것이다.
    const visibleIds = Array.from({ length: 17 }, (_, index) => `bulk-${index}`);
    expect(screen.getAllByTestId("timeline-clip")).toHaveLength(17);
    expect(screen.getAllByTestId("timeline-clip").map((clip) => clip.getAttribute("data-clip-id"))).toEqual(visibleIds);
    expect(screen.getAllByTestId("timeline-clip").some((clip) => clip.getAttribute("data-clip-id") === "bulk-17")).toBe(false);

    fireEvent.wheel(screen.getByRole("region", { name: "타임라인" }), { deltaX: 4_800 });

    const laterClips = screen.getAllByTestId("timeline-clip");
    expect(laterClips.length).toBeLessThanOrEqual(300);
    expect(laterClips.map((clip) => clip.getAttribute("data-clip-id")))
      .toEqual(Array.from({ length: 17 }, (_, index) => `bulk-${100 + index}`));
    // 반열린 구간이다 -- 356.4~360초짜리는 360초에서 끝나므로 안 걸린다.
    expect(laterClips.some((clip) => clip.getAttribute("data-clip-id") === "bulk-99")).toBe(false);
  });
});

describe("빈 구간 이유", () => {
  it("백엔드가 내보내는 이유를 창작자 말로 옮기고, 모르는 코드는 원문 대신 일반 문구로 말한다", () => {
    expect(gapReasonLabel("asset_gap")).toBe("미디어 없음");
    expect(gapReasonLabel("asset_required")).toBe("미디어 없음");
    expect(gapReasonLabel("장면을 보여 줄 영상이 없어요.")).toBe("영상 없음");
    expect(gapReasonLabel("some_new_internal_code")).toBe("미디어 없음");
    expect(gapReasonLabel("")).toBe("미디어 없음");
    expect(gapReasonLabel(undefined)).toBe("미디어 없음");
  });

  it("뺀 장면 자리는 미디어 없음이 아니라 뺀 장면 자리라고 말하고, 머리 문장이 센다", () => {
    expect(gapReasonLabel("removed_scene")).toBe("뺀 장면 자리");
    const removedView: EditorViewModel = {
      ...view,
      gaps: [{ gapId: "removed:s2", segmentId: "s2", startSec: 2, endSec: 3.7, reason: "removed_scene" }],
    };
    render(<TimelineDock view={removedView} viewportWidthPx={400} />);
    expect(screen.getByText(/빈 구간 1개/)).toBeInTheDocument();
    expect(screen.getByText("빈 구간: 뺀 장면 자리")).toBeInTheDocument();
    expect(screen.queryByText(/removed_scene/)).toBeNull();
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

describe("얹은 영상 오버레이 클립 이름 (최종 리뷰 발견)", () => {
  // `clipContentLabel`은 `clipNames.test.ts`에서 함수 단위로는 이미 맞게 시험됐다.
  // 그런데 화면(TimelineDock.tsx)이 그 함수에 `assetUri`를 실어 보내는 배선
  // 줄을 지워도 기존 262개 시험이 전부 초록이었다 -- 배선이 실제로 화면까지
  // 이어지는지를 재는 시험이 하나도 없었기 때문이다. 이 시험이 그 자리를 채운다.
  it("assetUri가 .mp4로 끝나면 막대 이름이 \"오버레이 1 · 영상\"이다", () => {
    const videoOverlayView: EditorViewModel = {
      ...view,
      tracks: [
        {
          trackId: "o",
          role: "overlay",
          clips: [{
            clipId: "o-video",
            segmentId: "segment-3",
            type: "overlay",
            assetId: "asset-video",
            assetUri: "https://videobox.local/assets/asset-video.mp4",
            // 기본 뷰포트(viewportWidthPx=400, 초당 100px)로는 0~4초만
            // 보인다 -- 원래 자리(15~18초)는 화면 밖이라 아예 안 그려진다.
            startSec: 0,
            endSec: 3,
            controls: {},
            overlayType: "image_overlay",
            overlayPayload: {},
          }],
        },
      ],
      captions: [],
      gaps: [],
    };

    render(<TimelineDock view={videoOverlayView} viewportWidthPx={400} />);

    expect(screen.getByRole("group", { name: /오버레이 1 · 영상/ })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: /오버레이 1 · 그림/ })).toBeNull();
  });
});

// 대표님 실제 영상과 같은 길이(494.837초, 94장면). 여기서 배율을 재야 "긴 영상에서
// 말이 되는가"를 짐작이 아니라 숫자로 답할 수 있다.
const ownerLongView: EditorViewModel = {
  ...view,
  output: { ...view.output, durationSec: 494.837 },
  tracks: [{
    trackId: "owner-narration",
    role: "narration",
    clips: Array.from({ length: 94 }, (_, index) => ({
      clipId: `owner-${index}`,
      segmentId: `owner-segment-${index}`,
      type: "narration" as const,
      assetId: null,
      assetUri: null,
      startSec: (index * 494.837) / 94,
      endSec: ((index + 1) * 494.837) / 94,
      controls: {},
    })),
  }],
  captions: [],
  gaps: [],
};

const fifteenSecondView: EditorViewModel = {
  ...view,
  output: { ...view.output, durationSec: 15 },
  tracks: [{
    trackId: "short-narration",
    role: "narration",
    clips: [{ clipId: "short-1", segmentId: "short-segment-1", type: "narration", assetId: null, assetUri: null, startSec: 0, endSec: 15, controls: {} }],
  }],
  captions: [],
  gaps: [],
};

function timelinePixelsPerSecond(): number {
  const value = screen.getByRole("region", { name: "타임라인" }).getAttribute("data-pixels-per-second");
  return Number(value);
}

describe("타임라인을 늘리고 줄인다 (대표님 지시 2026-09-12)", () => {
  it("처음 배율을 영상 길이에서 잡는다 -- 한 화면에 60초, 영상이 더 짧으면 영상 전체", () => {
    // 예전에는 100px/초로 못박혀 있어서 494초 영상이 49,483px이 됐다. 1200px짜리
    // 타임라인에 12초만 보였다는 뜻이다.
    render(<TimelineDock view={ownerLongView} viewportWidthPx={1200} />);
    expect(timelinePixelsPerSecond()).toBeCloseTo(20, 6);

    cleanup();

    // 15초짜리에 같은 규칙을 쓰면 영상 전체가 화면을 꽉 채운다. 빈 자리를 그리지 않는다.
    render(<TimelineDock view={fifteenSecondView} viewportWidthPx={1200} />);
    expect(timelinePixelsPerSecond()).toBeCloseTo(80, 6);
  });

  it("타임라인에 초점이 없어도 단축키가 듣는다", () => {
    // 대표님: "이걸 단축키로 쉽게 늘리고 줄이고를 할수 있어야지". 먼저 타임라인을
    // 눌러 초점을 맞추라고 하면 "쉽게"가 아니다. 컷 단축키가 이미 창 전체에서
    // 듣는다(`EditorWorkbench.tsx`) -- 같은 방식이다.
    render(<TimelineDock view={ownerLongView} viewportWidthPx={1200} />);
    expect(timelinePixelsPerSecond()).toBeCloseTo(20, 6);

    fireEvent.keyDown(window, { key: "=", ctrlKey: true });
    expect(timelinePixelsPerSecond()).toBeCloseTo(25, 6);

    fireEvent.keyDown(window, { key: "-", ctrlKey: true });
    expect(timelinePixelsPerSecond()).toBeCloseTo(20, 6);

    fireEvent.keyDown(window, { key: "0", ctrlKey: true });
    expect(timelinePixelsPerSecond()).toBeCloseTo(1200 / 494.837, 6);
  });

  it("늘려도 보고 있던 지점이 화면에 그대로 남는다", () => {
    // `zoomAroundAnchor`가 앵커를 받는 이유다. 앵커는 **재생 머리** -- 대표님이
    // 지금 보고 있는 자리이고, 다음 편집이 일어나는 자리다.
    render(<TimelineDock playbackSec={30} view={ownerLongView} viewportWidthPx={1200} />);
    const playhead = () => screen.getByTestId("timeline-playhead").style.left;

    // 30초 × 20px/초 = 600px. 1200px 화면의 한가운데다.
    expect(playhead()).toBe("600px");

    fireEvent.keyDown(window, { key: "=", ctrlKey: true });

    // 배율은 올라갔는데(가만히 있어서 통과하지 못하게) 재생 머리는 같은 자리에 있다.
    expect(timelinePixelsPerSecond()).toBeCloseTo(25, 6);
    expect(playhead()).toBe("600px");

    fireEvent.keyDown(window, { key: "-", ctrlKey: true });

    expect(timelinePixelsPerSecond()).toBeCloseTo(20, 6);
    expect(playhead()).toBe("600px");
  });

  it("한계에서 단추와 키가 같은 판단을 한다", () => {
    // `cutShortcuts.ts`가 정한 규약: "키는 툴바가 정한 것을 그대로 쓴다."
    // 단추가 잠겼는데 키로는 통하면 화면이 말한 것과 다른 일이 일어난다.
    render(<TimelineDock view={ownerLongView} viewportWidthPx={1200} />);
    const zoomIn = () => screen.getByRole("button", { name: "타임라인 확대" });
    const zoomOut = () => screen.getByRole("button", { name: "타임라인 축소" });

    for (let step = 0; step < 20; step += 1) fireEvent.keyDown(window, { key: "=", ctrlKey: true });
    expect(timelinePixelsPerSecond()).toBeCloseTo(400, 6);
    expect(zoomIn()).toBeDisabled();
    fireEvent.keyDown(window, { key: "=", ctrlKey: true });
    expect(timelinePixelsPerSecond()).toBeCloseTo(400, 6);

    for (let step = 0; step < 40; step += 1) fireEvent.keyDown(window, { key: "-", ctrlKey: true });
    // 줄이기를 계속 누르면 `전체 보기`와 **정확히 같은 자리**에 선다. 그 너머는
    // 빈 자리뿐이라 더 줄일 이유가 없다.
    expect(timelinePixelsPerSecond()).toBeCloseTo(1200 / 494.837, 6);
    expect(zoomOut()).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "타임라인 전체 보기" }));
    expect(timelinePixelsPerSecond()).toBeCloseTo(1200 / 494.837, 6);
  });

  it("Ctrl과 바퀴로 늘리고 줄인다 -- 캡컷과 같다", () => {
    // 캡컷은 `Ctrl` + 바퀴로 타임라인을 늘리고 줄인다. 키와 단추만 있으면
    // 손이 자판으로 갔다 와야 한다 -- 대표님: "내가 직접 조작할수 있게 해야지".
    render(<TimelineDock view={ownerLongView} viewportWidthPx={1200} />);
    const timeline = screen.getByRole("region", { name: "타임라인" });
    mockTimelineTrackRect();

    fireEvent.wheel(timeline, { ctrlKey: true, deltaY: -120, clientX: 600 });
    expect(timelinePixelsPerSecond()).toBeCloseTo(25, 6);

    fireEvent.wheel(timeline, { ctrlKey: true, deltaY: 120, clientX: 600 });
    expect(timelinePixelsPerSecond()).toBeCloseTo(20, 6);
  });

  it("바퀴로 늘리면 **손가락이 있던 자리**가 제자리에 남는다 -- 재생 머리가 아니다", () => {
    // 키는 재생 머리를 기준으로 늘린다(위 시험). 바퀴는 다르다 -- 손가락이 가리킨
    // 자리가 움직이면 늘리는 느낌이 어긋난다. 그래서 `zoomAroundAnchor`가 기준점을
    // 받는다.
    render(<TimelineDock view={ownerLongView} viewportWidthPx={1200} />);
    const timeline = screen.getByRole("region", { name: "타임라인" });
    // 트랙 원점으로 잰다. 섹션 원점으로 재면 안쪽 여백만큼 어긋난다
    // (`handleClick`이 같은 이유로 트랙을 본다).
    mockTimelineTrackRect(40);

    // 재생 머리는 0초에 있고, 손가락은 화면 가운데 600px -- 20px/초이니 30초다.
    const timeAtPointer = () => {
      const pps = Number(timeline.getAttribute("data-pixels-per-second"));
      const start = Number(timeline.getAttribute("data-viewport-start-seconds"));
      return 600 / pps + start;
    };
    expect(timeAtPointer()).toBeCloseTo(30, 6);

    fireEvent.wheel(timeline, { ctrlKey: true, deltaY: -120, clientX: 640 });

    expect(timelinePixelsPerSecond()).toBeCloseTo(25, 6);
    // 기준점이 재생 머리(0초)였다면 시작이 0으로 남고 손가락 아래는 24초가 된다.
    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "6");
    expect(timeAtPointer()).toBeCloseTo(30, 6);
  });

  it("Shift와 바퀴는 타임라인을 옆으로 민다", () => {
    render(<TimelineDock view={ownerLongView} viewportWidthPx={1200} />);
    const timeline = screen.getByRole("region", { name: "타임라인" });

    // 20px/초에서 100px이면 5초다.
    fireEvent.wheel(timeline, { shiftKey: true, deltaY: 100 });
    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "5");
    expect(timelinePixelsPerSecond()).toBeCloseTo(20, 6);

    fireEvent.wheel(timeline, { shiftKey: true, deltaY: -100 });
    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "0");
  });

  it("맨 바퀴는 예전 그대로다 -- 세로는 건드리지 않고 가로만 민다", () => {
    render(<TimelineDock view={ownerLongView} viewportWidthPx={1200} />);
    const timeline = screen.getByRole("region", { name: "타임라인" });

    // 세로 바퀴는 가로채지 않는다. 타임라인 칸은 `overflow:auto`라 위아래로
    // 스크롤된다 -- 그걸 막으면 아래쪽 트랙을 볼 수 없다.
    expect(fireEvent.wheel(timeline, { deltaY: 120 })).toBe(true);
    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "0");
    expect(timelinePixelsPerSecond()).toBeCloseTo(20, 6);

    // 가로 바퀴(트랙패드)는 예전처럼 옆으로 민다.
    fireEvent.wheel(timeline, { deltaX: 100 });
    expect(timeline).toHaveAttribute("data-viewport-start-seconds", "5");
  });

  it("바퀴로 늘릴 때 브라우저가 화면을 통째로 확대하지 않는다", () => {
    // React는 `wheel`을 **passive로** 단다(19.1.0에서 실측: `{passive:true}`).
    // 그래서 `onWheel` 안에서 `preventDefault()`를 불러도 아무 일이 없고,
    // `Ctrl`+바퀴는 타임라인이 아니라 **브라우저 화면 전체**가 확대된다.
    // 막으려면 passive가 아닌 listener를 직접 달아야 한다.
    render(<TimelineDock view={ownerLongView} viewportWidthPx={1200} />);
    const timeline = screen.getByRole("region", { name: "타임라인" });
    mockTimelineTrackRect();

    // `dispatchEvent`는 막혔으면 false를 준다.
    expect(fireEvent.wheel(timeline, { ctrlKey: true, deltaY: -120, clientX: 600 })).toBe(false);
    expect(fireEvent.wheel(timeline, { shiftKey: true, deltaY: 100 })).toBe(false);
  });

  it("타임라인을 닫으면 바퀴 listener도 같이 걷는다", () => {
    // 뜨거운 면에 listener를 남기면 없는 기능보다 나쁘다.
    const { unmount } = render(<TimelineDock view={ownerLongView} viewportWidthPx={1200} />);
    const timeline = screen.getByRole("region", { name: "타임라인" });
    const removeListener = vi.spyOn(timeline, "removeEventListener");

    unmount();

    expect(removeListener.mock.calls.filter(([type]) => type === "wheel")).toHaveLength(1);
  });

  it("단추·키·바퀴가 한계를 두고 다투지 않는다", () => {
    // `cutShortcuts.ts`가 정한 규약이다. 한계 판단은 `zoomControls` 한 곳에만 있고
    // 바퀴도 거기를 지난다 -- 세 갈래가 따로 세면 단추는 잠겼는데 바퀴로는
    // 한 칸 더 가는 어긋남이 생긴다.
    render(<TimelineDock view={ownerLongView} viewportWidthPx={1200} />);
    const timeline = screen.getByRole("region", { name: "타임라인" });
    mockTimelineTrackRect();

    for (let step = 0; step < 40; step += 1) fireEvent.wheel(timeline, { ctrlKey: true, deltaY: -120, clientX: 600 });
    expect(timelinePixelsPerSecond()).toBeCloseTo(400, 6);
    expect(screen.getByRole("button", { name: "타임라인 확대" })).toBeDisabled();

    for (let step = 0; step < 80; step += 1) fireEvent.wheel(timeline, { ctrlKey: true, deltaY: 120, clientX: 600 });
    expect(timelinePixelsPerSecond()).toBeCloseTo(1200 / 494.837, 6);
    expect(screen.getByRole("button", { name: "타임라인 축소" })).toBeDisabled();
  });

  it("길이가 틀리게 와도 타임라인이 열린다", () => {
    // 같은 계획의 다른 조각이 고치는 결함 -- 494초 세션의 길이가 5.0으로 온다.
    // 그 값이 고쳐지기 전에도 배율은 유한해야 한다. 0으로 나누면
    // `createTimelineNavigation`이 RangeError를 던져 편집기가 통째로 안 열린다.
    render(<TimelineDock view={{ ...ownerLongView, output: { ...ownerLongView.output, durationSec: 5 } }} viewportWidthPx={1200} />);
    expect(Number.isFinite(timelinePixelsPerSecond())).toBe(true);
    expect(timelinePixelsPerSecond()).toBeGreaterThan(0);

    cleanup();

    render(<TimelineDock view={{ ...ownerLongView, output: { ...ownerLongView.output, durationSec: 0 } }} viewportWidthPx={1200} />);
    expect(timelinePixelsPerSecond()).toBe(100);
    // 길이를 모르면 전체 보기로 갈 자리도 없다. 단추는 잠겨 있어야 한다 --
    // 눌러도 아무 일 없는 단추는 "있는데 안 되는 것"보다 나쁘다.
    expect(screen.getByRole("button", { name: "타임라인 전체 보기" })).toBeDisabled();
  });

  it("장면 번호는 배열 순서가 아니라 시간순으로 매긴다", () => {
    render(<TimelineDock view={outOfOrderNarrationView} viewportWidthPx={400} />);

    expect(screen.getByRole("button", { name: "내레이션 1번째 장면, 0초부터" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "내레이션 2번째 장면, 3초부터" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "내레이션 3번째 장면, 6초부터" })).toBeInTheDocument();
  });
});

/** 가장자리 손잡이·몸통 끌기(2026-10-08 점검 §3-8, 스파이크 H-c). */
describe("가장자리 손잡이와 몸통 끌기", () => {
  const placedView: EditorViewModel = {
    ...view,
    tracks: view.tracks.map((track) => track.role === "broll"
      ? { ...track, clips: track.clips.map((clip) => ({ ...clip, placementId: "broll:b-1" })) }
      : track),
  };
  const bothPlacedView: EditorViewModel = {
    ...placedView,
    tracks: placedView.tracks.map((track) => track.role === "overlay"
      ? { ...track, clips: track.clips.map((clip) => ({ ...clip, placementId: "overlay:o-late" })) }
      : track),
  };
  const brollHandles = () => ({
    start: screen.getByRole("button", { name: /영상 1.* 시작 자르기$/ }),
    end: screen.getByRole("button", { name: /영상 1.* 끝 자르기$/ }),
    move: screen.getByRole("button", { name: /영상 1.* 이동$/ }),
  });

  it("자르기 손잡이는 클립 양 끝의 얇은 띠이고 글자를 보이지 않는다 (2026-10-08 §3-8)", () => {
    render(<TimelineDock view={placedView} viewportWidthPx={400} onUpdatePlacements={vi.fn()} />);
    selectTimelineClip("broll:b-1");
    const { start, end, move } = brollHandles();
    expect(start).toHaveClass("vb-trim-handle", "vb-trim-handle--start");
    expect(end).toHaveClass("vb-trim-handle", "vb-trim-handle--end");
    expect(move).toHaveClass("vb-clip-body-drag");
    for (const control of [start, end, move]) expect(control.querySelector(".sr-only")).not.toBeNull();
    expect(start.closest("[data-placement-controls]")).not.toBeNull();
  });

  it("내레이션 손잡이도 같은 띠이고 순서 바꾸기가 몸통을 덮는다", () => {
    render(<TimelineDock view={view} viewportWidthPx={400} />);
    selectTimelineClip("n-1");
    const start = screen.getByRole("button", { name: /내레이션 1.* 시작 자르기$/ });
    const reorder = screen.getByRole("button", { name: /내레이션 1.* 순서 바꾸기$/ });
    expect(start).toHaveClass("vb-trim-handle", "vb-trim-handle--start");
    expect(reorder).toHaveClass("vb-clip-body-drag");
    expect(reorder.querySelector(".sr-only")).not.toBeNull();
  });

  it("손잡이는 키보드로 한 프레임씩 그대로 움직인다", () => {
    const onUpdatePlacements = vi.fn();
    render(<TimelineDock view={placedView} viewportWidthPx={400} onUpdatePlacements={onUpdatePlacements} />);
    selectTimelineClip("broll:b-1");
    fireEvent.keyDown(brollHandles().end, { key: "ArrowLeft" });
    expect(onUpdatePlacements).toHaveBeenCalledTimes(1);
    expect(onUpdatePlacements.mock.calls[0][0].changes[0].endSec).toBeCloseTo(9 - 1 / 25, 6);
  });

  it("좁은 클립은 손잡이만 그리고 몸통 끌기는 확대 안내로 바꾼다", () => {
    const narrowView: EditorViewModel = {
      ...cutEditedBrollView,
      tracks: cutEditedBrollView.tracks.map((track) => track.role === "broll"
        ? { ...track, clips: track.clips.map((clip) => ({ ...clip, placementId: `broll:${clip.clipId}` })) }
        : track),
    };
    render(<TimelineDock view={narrowView} viewportWidthPx={400} onUpdatePlacements={vi.fn()} />);
    selectTimelineClip("broll:b-cut-1"); // 0.3초 -- 몇 px짜리 자투리
    const move = screen.getByRole("button", { name: /이동$/ });
    expect(move).toHaveClass("sr-only");
    expect(move).not.toHaveClass("vb-clip-body-drag");
    expect(move.closest("[data-testid=timeline-clip]")).toHaveAttribute("title", "확대하면 끌어서 옮길 수 있어요");
    // 키보드는 산다: 같은 단추가 살아 있고 초점을 받는다.
    expect(move).toBeEnabled();
    expect(screen.getByRole("button", { name: /시작 자르기$/ })).toHaveClass("vb-trim-handle");
  });

  it("넓은 클립에는 확대 안내 제목이 없다", () => {
    render(<TimelineDock view={placedView} viewportWidthPx={400} onUpdatePlacements={vi.fn()} />);
    selectTimelineClip("broll:b-1");
    expect(timelineClip("broll:b-1")).not.toHaveAttribute("title");
  });

  it("몸통을 끌면 그만큼 옮겨서 놓을 때 한 번만 저장한다", () => {
    const onUpdatePlacements = vi.fn();
    render(<TimelineDock view={placedView} viewportWidthPx={400} onUpdatePlacements={onUpdatePlacements} />);
    selectTimelineClip("broll:b-1");
    const pps = timelinePixelsPerSecond();
    const { move } = brollHandles();
    pointer(move, "pointerdown", 100);
    pointer(move, "pointermove", 100 + 2 * pps);
    expect(onUpdatePlacements).not.toHaveBeenCalled();
    pointer(move, "pointerup", 100 + 2 * pps);
    expect(onUpdatePlacements).toHaveBeenCalledTimes(1);
    const change = onUpdatePlacements.mock.calls[0][0].changes[0];
    expect(change.startSec).toBeCloseTo(7, 1);
    expect(change.endSec).toBeCloseTo(11, 1);
  });

  it("가장자리 손잡이를 끌면 그 끝만 줄어든다", () => {
    const onUpdatePlacements = vi.fn();
    render(<TimelineDock view={placedView} viewportWidthPx={400} onUpdatePlacements={onUpdatePlacements} />);
    selectTimelineClip("broll:b-1");
    const pps = timelinePixelsPerSecond();
    const { end } = brollHandles();
    pointer(end, "pointerdown", 300);
    pointer(end, "pointermove", 300 - pps);
    pointer(end, "pointerup", 300 - pps);
    const change = onUpdatePlacements.mock.calls[0][0].changes[0];
    expect(change.startSec).toBe(5);
    expect(change.endSec).toBeCloseTo(8, 1);
  });

  it("3px 안쪽의 흔들림은 끌기가 아니고 놓아도 저장하지 않는다", () => {
    const onUpdatePlacements = vi.fn();
    render(<TimelineDock view={placedView} viewportWidthPx={400} onUpdatePlacements={onUpdatePlacements} />);
    selectTimelineClip("broll:b-1");
    const { move, end } = brollHandles();
    pointer(move, "pointerdown", 100);
    pointer(move, "pointermove", 102);
    pointer(move, "pointerup", 102);
    pointer(end, "pointerdown", 300);
    pointer(end, "pointermove", 298);
    pointer(end, "pointerup", 298);
    expect(onUpdatePlacements).not.toHaveBeenCalled();
    expect(timelineClip("broll:b-1")).toHaveAttribute("data-start-seconds", "5");
  });

  it("Esc를 누르면 끌던 것을 버리고 놓아도 저장하지 않는다", () => {
    const onUpdatePlacements = vi.fn();
    render(<TimelineDock view={placedView} viewportWidthPx={400} onUpdatePlacements={onUpdatePlacements} />);
    selectTimelineClip("broll:b-1");
    const { move } = brollHandles();
    pointer(move, "pointerdown", 100);
    pointer(move, "pointermove", 180);
    expect(timelineClip("broll:b-1")).not.toHaveAttribute("data-start-seconds", "5");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(timelineClip("broll:b-1")).toHaveAttribute("data-start-seconds", "5");
    pointer(move, "pointerup", 180);
    expect(onUpdatePlacements).not.toHaveBeenCalled();
  });

  it("pointercancel이나 캡처를 잃으면 끌던 것을 버린다", () => {
    const onUpdatePlacements = vi.fn();
    render(<TimelineDock view={placedView} viewportWidthPx={400} onUpdatePlacements={onUpdatePlacements} />);
    selectTimelineClip("broll:b-1");
    const { move, start } = brollHandles();
    pointer(move, "pointerdown", 100);
    pointer(move, "pointermove", 180);
    pointer(move, "pointercancel");
    pointer(move, "pointerup", 180);
    expect(onUpdatePlacements).not.toHaveBeenCalled();

    pointer(start, "pointerdown", 100);
    pointer(start, "pointermove", 140);
    fireEvent.lostPointerCapture(screen.getByTestId("timeline-track"));
    expect(timelineClip("broll:b-1")).toHaveAttribute("data-start-seconds", "5");
    pointer(start, "pointerup", 140);
    expect(onUpdatePlacements).not.toHaveBeenCalled();
  });

  it("클립 밖(트랙 칸 어디)에서 놓아도 끌던 값으로 저장한다", () => {
    const onUpdatePlacements = vi.fn();
    render(<TimelineDock view={placedView} viewportWidthPx={400} onUpdatePlacements={onUpdatePlacements} />);
    selectTimelineClip("broll:b-1");
    const pps = timelinePixelsPerSecond();
    const { move } = brollHandles();
    pointer(move, "pointerdown", 100);
    pointer(move, "pointermove", 100 + pps);
    pointer(screen.getByTestId("timeline-track"), "pointerup", 100 + pps);
    expect(onUpdatePlacements).toHaveBeenCalledTimes(1);
    expect(onUpdatePlacements.mock.calls[0][0].changes[0].startSec).toBeCloseTo(6, 1);
  });

  it("커서: 손잡이는 좌우 크기, 몸통은 잡기, 크기는 변수에서 온다", () => {
    const css = readFileSync(resolve(process.cwd(), "src/styles/editor-workbench.css"), "utf8");
    expect(css).toMatch(/\.vb-trim-handle\s*\{[^}]*cursor:\s*ew-resize/);
    expect(css).toMatch(/\.vb-clip-body-drag\s*\{[^}]*cursor:\s*grab/);
    expect(css).toMatch(/\.vb-trim-handle\s*\{[^}]*width:\s*var\(--vb-trim-hit-w\)/);
    expect(css).toMatch(/\.vb-trim-handle::before\s*\{[^}]*width:\s*var\(--vb-trim-handle-w\)/);
    expect(css).toMatch(/\.vb-clip-body-drag\s*\{[^}]*left:\s*var\(--vb-trim-hit-w\)/);
  });
  it("몸통을 흔들림(2px)만 하고 놓으면 클릭이라 그 클립을 고르고 시작으로 이동한다", () => {
    const onUpdatePlacements = vi.fn();
    const onPlaybackSeek = vi.fn();
    const onSelectSegment = vi.fn();
    render(<TimelineDock view={bothPlacedView} viewportWidthPx={400} onPlaybackSeek={onPlaybackSeek} onSelectSegment={onSelectSegment} onUpdatePlacements={onUpdatePlacements} />);
    selectTimelineClip("broll:b-1");
    onPlaybackSeek.mockClear(); onSelectSegment.mockClear();
    const move = screen.getByRole("button", { name: /영상 1.* 이동$/ });
    pointer(move, "pointerdown", 100);
    pointer(move, "pointermove", 102);
    pointer(move, "pointerup", 102);
    expect(onUpdatePlacements).not.toHaveBeenCalled();
    expect(onPlaybackSeek).toHaveBeenCalledWith(5);
    expect(onSelectSegment).toHaveBeenCalledWith("segment-2");
  });

  it("고른 클립 몸통의 Shift+클릭은 끌기가 아니라 고르기 토글이다", () => {
    const onUpdatePlacements = vi.fn();
    render(<TimelineDock view={bothPlacedView} viewportWidthPx={400} onUpdatePlacements={onUpdatePlacements} />);
    selectTimelineClip("broll:b-1");
    fireEvent.click(timelineClipSelection("overlay:o-late"), { shiftKey: true });
    expect(screen.getByText("고른 항목 2개")).toBeInTheDocument();
    const move = screen.getByRole("button", { name: /오버레이.* 이동$/ });
    pointer(move, "pointerdown", 100, { shiftKey: true });
    pointer(move, "pointermove", 200, { shiftKey: true });
    pointer(move, "pointerup", 200, { shiftKey: true });
    expect(onUpdatePlacements).not.toHaveBeenCalled();
    expect(screen.queryByText("고른 항목 2개")).toBeNull();
  });

  it("여럿 고른 상태에서 한 클립 몸통을 그냥 누르면 그 클립 하나만 남는다", () => {
    render(<TimelineDock view={bothPlacedView} viewportWidthPx={400} onUpdatePlacements={vi.fn()} />);
    selectTimelineClip("broll:b-1");
    fireEvent.click(timelineClipSelection("overlay:o-late"), { shiftKey: true });
    expect(screen.getByText("고른 항목 2개")).toBeInTheDocument();
    const move = screen.getByRole("button", { name: /오버레이.* 이동$/ });
    pointer(move, "pointerdown", 100);
    pointer(move, "pointerup", 100);
    expect(screen.queryByText("고른 항목 2개")).toBeNull();
  });
});

describe("끌기·자르기 중 붙기 (스파이크 H-d)", () => {
  // 영상 두 개: b-1 5~9초, b-2 12~14초. 400px 폭 / 20초 = 20px/초.
  const twoPlacedView: EditorViewModel = {
    ...view,
    tracks: view.tracks.map((track) => track.role === "broll"
      ? { ...track, clips: [
        { ...track.clips[0]!, placementId: "broll:b-1" },
        { clipId: "b-2", segmentId: "segment-5", type: "broll" as const, assetId: null, assetUri: null, startSec: 12, endSec: 14, controls: {}, placementId: "broll:b-2" },
      ] }
      : track),
  };
  const handlesOf = (name: string) => ({
    start: screen.getByRole("button", { name: new RegExp(`${name}.* 시작 자르기$`) }),
    end: screen.getByRole("button", { name: new RegExp(`${name}.* 끝 자르기$`) }),
    move: screen.getByRole("button", { name: new RegExp(`${name}.* 이동$`) }),
  });

  it("옮기기: b-2 시작이 b-1 끝(9초)에서 1px 안이면 정확히 9초에 붙고 안내선이 9초 자리에 선다", () => {
    const onUpdatePlacements = vi.fn();
    render(<TimelineDock view={twoPlacedView} viewportWidthPx={400} onUpdatePlacements={onUpdatePlacements} />);
    selectTimelineClip("broll:b-2");
    const pps = timelinePixelsPerSecond();
    expect(pps).toBe(20);
    const { move } = handlesOf("영상 2");
    pointer(move, "pointerdown", 300);
    pointer(move, "pointermove", 300 - 3 * pps + 1); // 시작 9.05초
    const guide = document.querySelector<HTMLElement>(".vb-timeline-snap-guide");
    expect(guide).not.toBeNull();
    expect(guide!.style.left).toBe(`${9 * pps}px`);
    pointer(move, "pointerup", 300 - 3 * pps + 1);
    expect(onUpdatePlacements).toHaveBeenCalledTimes(1);
    expect(onUpdatePlacements.mock.calls[0][0].changes[0].startSec).toBe(9);
    expect(onUpdatePlacements.mock.calls[0][0].changes[0].endSec).toBe(11);
    expect(document.querySelector(".vb-timeline-snap-guide")).toBeNull();
  });

  it("옮기기: 끝이 옆 클립 시작(12초)에 닿아도 붙는다 -- b-1 끝 변이 b-2 시작으로", () => {
    const onUpdatePlacements = vi.fn();
    render(<TimelineDock view={twoPlacedView} viewportWidthPx={400} onUpdatePlacements={onUpdatePlacements} />);
    selectTimelineClip("broll:b-1");
    const pps = timelinePixelsPerSecond();
    const { move } = handlesOf("영상 1");
    pointer(move, "pointerdown", 100);
    pointer(move, "pointermove", 100 + 3 * pps - 1); // 끝 11.95초
    pointer(move, "pointerup", 100 + 3 * pps - 1);
    const change = onUpdatePlacements.mock.calls[0][0].changes[0];
    expect(change.endSec).toBe(12);
    expect(change.startSec).toBe(8);
  });

  it("끝 손잡이: b-1 끝이 b-2 시작(12초)에서 1px 안이면 12초에 붙는다", () => {
    const onUpdatePlacements = vi.fn();
    render(<TimelineDock view={twoPlacedView} viewportWidthPx={400} onUpdatePlacements={onUpdatePlacements} />);
    selectTimelineClip("broll:b-1");
    const pps = timelinePixelsPerSecond();
    const { end } = handlesOf("영상 1");
    pointer(end, "pointerdown", 180);
    pointer(end, "pointermove", 180 + 3 * pps - 1);
    pointer(end, "pointerup", 180 + 3 * pps - 1);
    expect(onUpdatePlacements.mock.calls[0][0].changes[0].endSec).toBe(12);
  });

  it("임계(8px) 밖이면 붙지 않고 안내선도 없다", () => {
    const onUpdatePlacements = vi.fn();
    render(<TimelineDock view={twoPlacedView} viewportWidthPx={400} onUpdatePlacements={onUpdatePlacements} />);
    selectTimelineClip("broll:b-2");
    const pps = timelinePixelsPerSecond();
    const { move } = handlesOf("영상 2");
    pointer(move, "pointerdown", 300);
    pointer(move, "pointermove", 300 - 2 * pps); // 시작 10초: 9초와 20px, 다른 후보도 8px 밖
    expect(document.querySelector(".vb-timeline-snap-guide")).toBeNull();
    pointer(move, "pointerup", 300 - 2 * pps);
    expect(onUpdatePlacements.mock.calls[0][0].changes[0].startSec).toBe(10);
  });

  it("키보드 한 프레임 조작에는 붙기를 걸지 않는다", () => {
    const onUpdatePlacements = vi.fn();
    render(<TimelineDock view={twoPlacedView} viewportWidthPx={400} onUpdatePlacements={onUpdatePlacements} />);
    selectTimelineClip("broll:b-1");
    fireEvent.keyDown(handlesOf("영상 1").end, { key: "ArrowRight" });
    expect(onUpdatePlacements.mock.calls[0][0].changes[0].endSec).toBeCloseTo(9.04, 6);
  });

  it("Esc로 버리면 안내선도 사라지고 저장하지 않는다", () => {
    const onUpdatePlacements = vi.fn();
    render(<TimelineDock view={twoPlacedView} viewportWidthPx={400} onUpdatePlacements={onUpdatePlacements} />);
    selectTimelineClip("broll:b-2");
    const pps = timelinePixelsPerSecond();
    const { move } = handlesOf("영상 2");
    pointer(move, "pointerdown", 300);
    pointer(move, "pointermove", 300 - 3 * pps + 1);
    expect(document.querySelector(".vb-timeline-snap-guide")).not.toBeNull();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(document.querySelector(".vb-timeline-snap-guide")).toBeNull();
    pointer(move, "pointerup", 300 - 3 * pps + 1);
    expect(onUpdatePlacements).not.toHaveBeenCalled();
  });

  it("내레이션 끝 손잡이: 재생줄(6.48초)에서 1px 안이면 6.48초에 붙는다", () => {
    const onTrimNarration = vi.fn();
    render(<TimelineDock view={twoNarrationView} viewportWidthPx={400} onTrimNarration={onTrimNarration} />);
    selectTimelineClip("n-2");
    const pps = timelinePixelsPerSecond();
    fireEvent.click(screen.getByTestId("timeline-track"), { clientX: 6.48 * pps }); // 재생줄을 6.48초(25fps 프레임 위)로
    const end = screen.getByRole("button", { name: /내레이션 2.* 끝 자르기$/ });
    pointer(end, "pointerdown", 40);
    pointer(end, "pointermove", 40 + 4.48 * pps - 1); // 끝 6.43초
    expect(document.querySelector(".vb-timeline-snap-guide")).not.toBeNull();
    pointer(end, "pointerup", 40 + 4.48 * pps - 1);
    expect(onTrimNarration).toHaveBeenCalledTimes(1);
    expect(onTrimNarration.mock.calls[0][0].endSec).toBeCloseTo(6.48, 9);
  });
  it("고른 클립의 재생줄(시작)에도 끝은 붙는다: b-2를 왼쪽으로 끌면 끝이 12초 재생줄에 붙어 시작이 10초", () => {
    const onUpdatePlacements = vi.fn();
    render(<TimelineDock view={twoPlacedView} viewportWidthPx={400} onUpdatePlacements={onUpdatePlacements} playbackSec={12} />);
    selectTimelineClip("broll:b-2"); // 재생줄이 b-2 시작(12초)에 선다(화면에서는 고르면 소유자가 재생 위치를 시작으로 옮긴다)
    const pps = timelinePixelsPerSecond();
    const { move } = handlesOf("영상 2");
    pointer(move, "pointerdown", 300);
    pointer(move, "pointermove", 300 - 2 * pps - 1); // 시작 9.95 -> 끝 11.95
    pointer(move, "pointerup", 300 - 2 * pps - 1);
    const change = onUpdatePlacements.mock.calls[0][0].changes[0];
    expect(change.startSec).toBe(10);
    expect(change.endSec).toBe(12);
  });

  it("고른 클립 시작 손잡이를 5px 안쪽으로 끌어도 재생줄(처음 시작)로 도로 붙지 않는다", () => {
    const onUpdatePlacements = vi.fn();
    render(<TimelineDock view={twoPlacedView} viewportWidthPx={400} onUpdatePlacements={onUpdatePlacements} playbackSec={5} />);
    selectTimelineClip("broll:b-1"); // 재생줄 5초 = 시작
    const { start } = handlesOf("영상 1");
    pointer(start, "pointerdown", 100);
    pointer(start, "pointermove", 105);
    pointer(start, "pointerup", 105);
    expect(document.querySelector(".vb-timeline-snap-guide")).toBeNull();
    expect(onUpdatePlacements.mock.calls[0][0].changes[0].startSec).toBeCloseTo(5.24, 2);
  });
});

describe("눈금 간격 (스파이크 H-e)", () => {
  const longView: EditorViewModel = { ...view, output: { ...view.output, durationSec: 120 } };

  it("120초 전체 보기(1343px)는 121개 대신 15초마다 9개이고 글자 위치가 시간과 맞는다", () => {
    render(<TimelineDock view={longView} viewportWidthPx={1343} />);
    fireEvent.click(screen.getByRole("button", { name: "타임라인 전체 보기" })); // 처음 화면은 60초만 보인다
    const marks = screen.getAllByRole("listitem", { name: /^눈금/ });
    expect(marks).toHaveLength(9);
    expect(screen.getByLabelText("눈금 15초")).toBeInTheDocument();
    expect(screen.getByLabelText("눈금 120초")).toHaveTextContent("2:00");
    const pps = timelinePixelsPerSecond();
    expect(pps).toBeCloseTo(1343 / 120, 5);
    expect(parseFloat(screen.getByLabelText("눈금 15초").style.left)).toBeCloseTo(15 * pps, 2);
    expect(screen.getByLabelText("눈금 15초")).toHaveTextContent("15s");
  });

  it("칸 끝에 닿는 마지막 눈금만 글자를 선 왼쪽에 얹고, aria 이름은 그대로다", () => {
    render(<TimelineDock view={longView} viewportWidthPx={1343} />);
    fireEvent.click(screen.getByRole("button", { name: "타임라인 전체 보기" }));
    expect(screen.getByRole("listitem", { name: "눈금 120초" })).toHaveClass("vb-ruler-major--end");
    expect(screen.getByRole("listitem", { name: "눈금 105초" })).not.toHaveClass("vb-ruler-major--end");
    expect(document.querySelectorAll(".vb-ruler-major--end")).toHaveLength(1);
  });

  it("잔눈금은 글자 없이 15초 사이 3초마다 그려진다", () => {
    const { container } = render(<TimelineDock view={longView} viewportWidthPx={1343} />);
    fireEvent.click(screen.getByRole("button", { name: "타임라인 전체 보기" }));
    const minors = container.querySelectorAll(".vb-ruler-minor");
    expect(minors.length).toBeGreaterThan(30);
    for (const minor of minors) {
      expect(minor).toHaveAttribute("aria-hidden", "true");
      expect(minor.textContent).toBe("");
    }
  });

  it("짧은 영상(20초, 400px = 20px/초)은 6초마다가 아니라 최소 간격을 지킨다", () => {
    render(<TimelineDock view={view} viewportWidthPx={400} />);
    // 20px/초 x 120px 최소 -> 10초(200px)마다: 0, 10, 20
    expect(screen.getAllByRole("listitem", { name: /^눈금/ }).map((el) => el.getAttribute("aria-label"))).toEqual(["눈금 0초", "눈금 10초", "눈금 20초"]);
  });

  describe("처음 배율을 잰 칸 폭으로 다시 맞춘다 (2026-10-09 정적 검토)", () => {
    // 첫 렌더의 바깥 폭(머리 칸 포함)보다 실제 클립 칸이 좁다. ResizeObserver가 실제 폭을 알려 오면 맞춘다.
    function stubObserver(): { report: (width: number) => void } {
      const callbacks: Array<(entries: unknown[]) => void> = [];
      vi.stubGlobal("ResizeObserver", class { constructor(callback: (entries: unknown[]) => void) { callbacks.push(callback); } observe() {} unobserve() {} disconnect() {} });
      return { report: (width) => act(() => { for (const callback of callbacks) callback([{ contentRect: { width } }]); }) };
    }
    afterEach(() => { vi.unstubAllGlobals(); });

    it("잰 폭이 처음 들어오면 영상 전체가 그 폭 안에 들어온다 (끝 1초가 가려지지 않는다)", () => {
      const observer = stubObserver();
      // 바깥 폭 1000(머리 칸 144px 포함), 실제 칸 폭 856.
      render(<TimelineDock view={view} viewportWidthPx={1000} />);
      const timeline = screen.getByRole("region", { name: "타임라인" });
      expect(Number(timeline.getAttribute("data-pixels-per-second")) * view.output.durationSec).toBeGreaterThan(856); // 고치기 전 상태: 넘친다
      observer.report(856);
      const pxPerSec = Number(timeline.getAttribute("data-pixels-per-second"));
      expect(pxPerSec * view.output.durationSec).toBeLessThanOrEqual(856 + 1e-6);
      expect(pxPerSec).toBeCloseTo(856 / view.output.durationSec, 6);
    });

    it("0·음수·NaN·아주 작은 잰 폭이 와도 던지지 않고 배율이 유한한 양수로 남으며, 120초 실제 모양도 죽지 않는다", () => {
      const observer = stubObserver();
      const long: EditorViewModel = {
        ...view,
        output: { ...view.output, durationSec: 120 },
        tracks: [{ trackId: "b", role: "broll", clips: Array.from({ length: 15 }, (_, index) => ({ clipId: `b-${index}`, segmentId: `s-${index}`, type: "broll", assetId: null, assetUri: null, startSec: index === 0 ? 90 : 12 + index * 6, endSec: index === 0 ? 102 : 18 + index * 6, controls: {} })) }],
        captions: [], gaps: [],
      };
      render(<TimelineDock view={long} viewportWidthPx={1190} />);
      const timeline = screen.getByRole("region", { name: "타임라인" });
      for (const width of [0, -5, Number.NaN, 1, 3, 856, 856, 1175]) {
        expect(() => observer.report(width)).not.toThrow();
        const pxPerSec = Number(timeline.getAttribute("data-pixels-per-second"));
        expect(Number.isFinite(pxPerSec) && pxPerSec > 0).toBe(true);
      }
      // 처음 배율은 최대 60초가 칸을 채우는 값이다(60초보다 긴 영상은 처음 60초만 보이고 나머지는 전체 보기). 그 60초가 칸 안에 든다.
      expect(Number(timeline.getAttribute("data-pixels-per-second")) * 60).toBeLessThanOrEqual(1175 + 1e-6);
    });

    it("0907 실제 수치: 7.75초, 바깥 폭 1360, 잰 칸 폭 1175 -> 처음 열면 전체가 1175 안에 든다 (마감 점검 d)", () => {
      const observer = stubObserver();
      const short: EditorViewModel = { ...view, output: { ...view.output, durationSec: 7.75 }, tracks: [], captions: [], gaps: [] };
      render(<TimelineDock view={short} viewportWidthPx={1360} />);
      const timeline = screen.getByRole("region", { name: "타임라인" });
      observer.report(1175);
      const pxPerSec = Number(timeline.getAttribute("data-pixels-per-second"));
      expect(pxPerSec * 7.75).toBeLessThanOrEqual(1175 + 1e-6);
      expect(pxPerSec * 7.75).toBeGreaterThan(1175 * 0.99);
      for (const [width, duration] of [[1190, 3.75], [1000, 30], [640, 7.75], [300, 59.9]] as const) {
        cleanup();
        const o = stubObserver();
        render(<TimelineDock view={{ ...short, output: { ...short.output, durationSec: duration } }} viewportWidthPx={width + 185} />);
        o.report(width);
        const px = Number(screen.getByRole("region", { name: "타임라인" }).getAttribute("data-pixels-per-second"));
        expect(px * duration, `${width}/${duration}`).toBeLessThanOrEqual(width + 1e-6);
      }
    });

    it("칸 폭이 먼저 들어오고 영상 길이가 나중에 정해져도(편집기가 자리만 먼저 뜬 경우) 새 길이로 다시 맞춘다 (마감 점검 d 원인)", () => {
      const observer = stubObserver();
      const placeholder: EditorViewModel = { ...view, output: { ...view.output, durationSec: 1 }, tracks: [], captions: [], gaps: [] };
      const rendered = render(<TimelineDock view={placeholder} viewportWidthPx={1360} />);
      const timeline = screen.getByRole("region", { name: "타임라인" });
      observer.report(1175);
      rendered.rerender(<TimelineDock view={{ ...placeholder, output: { ...placeholder.output, durationSec: 7.75 } }} viewportWidthPx={1360} />);
      const pxPerSec = Number(timeline.getAttribute("data-pixels-per-second"));
      expect(pxPerSec * 7.75).toBeLessThanOrEqual(1175 + 1e-6);
      expect(pxPerSec * 7.75).toBeGreaterThan(1175 * 0.99);
    });

    it("사람이 이미 배율을 건드렸다면 폭이 바뀌어도 다시 맞추지 않는다", () => {
      const observer = stubObserver();
      render(<TimelineDock view={view} viewportWidthPx={1000} />);
      const timeline = screen.getByRole("region", { name: "타임라인" });
      observer.report(856);
      fireEvent.click(screen.getByRole("button", { name: "타임라인 확대" }));
      const zoomed = timeline.getAttribute("data-pixels-per-second");
      observer.report(700);
      expect(timeline.getAttribute("data-pixels-per-second")).toBe(zoomed);
    });
  });

  it("같은 줄에서 겹친 두 영상 클립은 누른 쪽이 골라진다 -- 중심이 겹쳐도 이름순으로 다른 클립이 잡히지 않는다 (742e1924 90초 영상)", () => {
    const overlapped: EditorViewModel = {
      ...view, captions: [], gaps: [],
      tracks: [{ trackId: "b", role: "broll", clips: [
        { clipId: "b-aaa", segmentId: "segment-1", type: "broll", assetId: null, assetUri: null, startSec: 2, endSec: 8, controls: {} },
        { clipId: "b-zzz", segmentId: "segment-2", type: "broll", assetId: null, assetUri: null, startSec: 4, endSec: 10, controls: {} },
      ] }],
    };
    const onSelectSegment = vi.fn();
    render(<TimelineDock view={overlapped} viewportWidthPx={WIDTH_FOR_100_PX_PER_SECOND} onSelectSegment={onSelectSegment} />);
    // 두 클립 모두 중심(5~7초)이 겹침: b-aaa 중심 5초는 b-zzz 안(4~10초)에도 속한다.
    fireEvent.click(timelineClipSelection("b-zzz"));
    fireEvent.click(timelineClipSelection("b-aaa"));
    expect(onSelectSegment.mock.calls.map((call) => call[0])).toEqual(["segment-2", "segment-1"]);
  });

  describe("재생 시계(2026-10-09 계획 P Task 2)", () => {
    const pxPerSec = () => Number(screen.getByRole("region", { name: "타임라인" }).getAttribute("data-pixels-per-second"));
    it("재생 중 시계가 흐르면 재생 머리는 transform만 움직이고 left는 React 상태를 따른다", () => {
      const clock = createPlaybackClock(2);
      render(<TimelineDock playbackClock={clock} playbackSec={2} view={view} viewportWidthPx={1000} />);
      const playhead = screen.getByTestId("timeline-playhead");
      const left = playhead.style.left;
      act(() => clock.publish(2.5, true));
      expect(playhead.style.transform).toBe(`translateX(${0.5 * pxPerSec()}px)`);
      expect(playhead.style.left).toBe(left);
      expect(playhead).toHaveAttribute("data-seconds", "2");
    });
    it("멈춘 뒤 React가 새 재생 위치로 다시 그리면 transform은 지워지고 left가 새 값이다", () => {
      const clock = createPlaybackClock(2);
      const { rerender } = render(<TimelineDock playbackClock={clock} playbackSec={2} view={view} viewportWidthPx={1000} />);
      const playhead = screen.getByTestId("timeline-playhead");
      act(() => clock.publish(2.5, true));
      act(() => clock.publish(2.5, false));
      rerender(<TimelineDock playbackClock={clock} playbackSec={2.5} view={view} viewportWidthPx={1000} />);
      expect(playhead.style.transform).toBe("");
      expect(playhead.style.left).toBe(`${2.5 * pxPerSec()}px`);
      expect(playhead).toHaveAttribute("data-seconds", "2.5");
    });
    it("재생 중 React가 다시 그려도(timeupdate) 시계의 앞선 만큼 transform을 바로 다시 잡는다", () => {
      const clock = createPlaybackClock(2);
      const { rerender } = render(<TimelineDock playbackClock={clock} playbackSec={2} view={view} viewportWidthPx={1000} />);
      const playhead = screen.getByTestId("timeline-playhead");
      act(() => clock.publish(2.3, true));
      rerender(<TimelineDock playbackClock={clock} playbackSec={2.2} view={view} viewportWidthPx={1000} />);
      expect(playhead.style.transform).toBe(`translateX(${(2.3 - 2.2) * pxPerSec()}px)`);
    });
    it("아래 재생 위치 글자도 재생 중에는 시계를 따르고, 멈추면 상태로 돌아온다", () => {
      const clock = createPlaybackClock(2);
      const { rerender } = render(<TimelineDock playbackClock={clock} playbackSec={2} view={view} viewportWidthPx={1000} />);
      const readout = screen.getByLabelText("재생 위치");
      expect(readout.textContent).toBe("2초");
      act(() => clock.publish(2.5, true));
      expect(readout.textContent).toBe("2.5초");
      expect(readout.getAttribute("aria-live")).toBe("off");
      act(() => clock.publish(2.5, false));
      rerender(<TimelineDock playbackClock={clock} playbackSec={2.5} view={view} viewportWidthPx={1000} />);
      expect(readout.textContent).toBe("2.5초");
      expect(readout).toHaveAttribute("data-seconds", "2.5");
    });
    it("시계가 보이는 구간 끝을 넘으면 그 순간 그 자리로 넘긴다", () => {
      const clock = createPlaybackClock(0);
      render(<TimelineDock playbackClock={clock} playbackSec={0} view={scrollableView} viewportWidthPx={600} />);
      const timeline = screen.getByRole("region", { name: "타임라인" });
      expect(timeline).toHaveAttribute("data-viewport-start-seconds", "0");
      act(() => clock.publish(59, true));
      expect(timeline).toHaveAttribute("data-viewport-start-seconds", "0");
      act(() => clock.publish(60.2, true));
      expect(timeline).toHaveAttribute("data-viewport-start-seconds", "60.2");
      act(() => clock.publish(60.3, true));
      expect(timeline).toHaveAttribute("data-viewport-start-seconds", "60.2");
    });
    it("사용자가 옆으로 밀어 두면 다시 재생하기 전까지 시계가 구간을 끌어오지 않는다", () => {
      const clock = createPlaybackClock(0);
      render(<TimelineDock playbackClock={clock} playbackSec={0} view={scrollableView} viewportWidthPx={600} />);
      const timeline = screen.getByRole("region", { name: "타임라인" });
      act(() => clock.publish(1, true));
      fireEvent.wheel(timeline, { deltaX: 100 });
      const pushed = timeline.getAttribute("data-viewport-start-seconds");
      expect(pushed).not.toBe("0");
      act(() => clock.publish(Number(pushed) - 5, true)); // 보이는 구간 앞쪽 밖
      act(() => clock.publish(75, true));
      expect(timeline.getAttribute("data-viewport-start-seconds")).toBe(pushed);
      act(() => clock.publish(75, false));
      act(() => clock.publish(75.1, true)); // 다시 재생 시작
      expect(timeline.getAttribute("data-viewport-start-seconds")).toBe("75.1");
    });
    it("시계 없이도 예전과 똑같이 동작한다(재생 머리 transform 없음)", () => {
      render(<TimelineDock playbackSec={2} view={view} viewportWidthPx={1000} />);
      expect(screen.getByTestId("timeline-playhead").style.transform).toBe("");
    });
  });
});
