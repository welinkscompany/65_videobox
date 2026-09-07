import { describe, expect, it } from "vitest";

import { frameToSeconds, pixelsToTime } from "./time-scale";
import {
  createTimelineNavigation,
  navigationKeyAction,
  projectVisibleTimelineClips,
  reduceTimelineNavigation,
  type TimelineNavigationState,
} from "./timelineNavigation";

const options = {
  durationSec: 20,
  viewportWidthPx: 100,
  fps: { num: 30_000, den: 1_001 },
};

describe("timeline navigation", () => {
  it("clamps seek and preserves the anchor time while zooming", () => {
    const initial = createTimelineNavigation({ durationSec: 20, pixelsPerSecond: 10 });
    const sought = reduceTimelineNavigation(initial, { type: "seek", seconds: 99 }, options);
    const zoomed = reduceTimelineNavigation(
      { ...sought, viewportStartSec: 5 },
      { type: "zoom", pixelsPerSecond: 20, anchorPx: 50 },
      options,
    );

    expect(sought.playheadSec).toBe(20);
    expect(zoomed.viewportStartSec).toBe(7.5);
    expect(pixelsToTime(50, {
      pixelsPerSecond: zoomed.pixelsPerSecond,
      originSec: zoomed.viewportStartSec,
    })).toBe(10);
  });

  it("uses absolute scrolling and clamps scrolling and seeking to the timeline bounds", () => {
    const initial = createTimelineNavigation({ durationSec: 20, pixelsPerSecond: 10 });
    const moved = reduceTimelineNavigation(
      { ...initial, viewportStartSec: 5 },
      { type: "scroll", seconds: 2 },
      options,
    );
    const right = reduceTimelineNavigation(moved, { type: "scroll", seconds: 99 }, options);
    const left = reduceTimelineNavigation(right, { type: "scroll", seconds: -99 }, options);
    const sought = reduceTimelineNavigation(left, { type: "seek", seconds: -1 }, options);

    expect(moved.viewportStartSec).toBe(2);
    expect(right.viewportStartSec).toBe(10);
    expect(left.viewportStartSec).toBe(0);
    expect(sought.playheadSec).toBe(0);
  });

  it("clamps a near-end zoom origin and preserves a reachable anchor", () => {
    const nearEnd: TimelineNavigationState = {
      viewportStartSec: 10,
      pixelsPerSecond: 10,
      playheadSec: 20,
      selectedClipId: null,
    };
    const scale = { pixelsPerSecond: nearEnd.pixelsPerSecond, originSec: nearEnd.viewportStartSec };
    const clamped = reduceTimelineNavigation(
      nearEnd,
      { type: "zoom", pixelsPerSecond: 20, anchorPx: 150 },
      options,
    );
    const preserved = reduceTimelineNavigation(
      nearEnd,
      { type: "zoom", pixelsPerSecond: 20, anchorPx: 100 },
      options,
    );

    expect(pixelsToTime(150, scale)).toBe(25);
    expect(clamped.viewportStartSec).toBe(15);
    expect(pixelsToTime(100, {
      pixelsPerSecond: preserved.pixelsPerSecond,
      originSec: preserved.viewportStartSec,
    })).toBe(pixelsToTime(100, scale));
  });

  it("maps navigation keys to exact frame steps and local actions", () => {
    const state: TimelineNavigationState = {
      viewportStartSec: 0,
      pixelsPerSecond: 100,
      playheadSec: 0.02,
      selectedClipId: null,
    };

    expect(navigationKeyAction("ArrowRight", false, { state, fps: options.fps })).toEqual({
      type: "seek",
      seconds: frameToSeconds(2, options.fps),
    });
    expect(navigationKeyAction("ArrowLeft", false, { state, fps: options.fps })).toEqual({
      type: "seek",
      seconds: 0,
    });
    expect(navigationKeyAction("Home", false, { state, fps: options.fps })).toEqual({ type: "seek", bound: "start" });
    expect(navigationKeyAction("End", false, { state, fps: options.fps })).toEqual({ type: "seek", bound: "end" });
    // 확대는 **배율**로 전달한다. 절대값으로 보내면 두 번을 같은 상태에서 계산한
    // 순간(React가 한 묶음으로 처리할 때) 두 번째가 첫 번째를 덮어써 한 칸만 먹는다.
    // 실제 컨테이너에서 빠르게 두 번 누르면 100 → 125 → 125가 나왔다.
    expect(navigationKeyAction("+", false, { state, fps: options.fps })).toEqual({ type: "zoom", factor: 1.25 });
    expect(navigationKeyAction("-", false, { state, fps: options.fps })).toEqual({ type: "zoom", factor: 1 / 1.25 });
    expect(navigationKeyAction("ArrowRight", true, { state, fps: options.fps })).toBeNull();
    expect(navigationKeyAction("x", false, { state, fps: options.fps })).toBeNull();
  });

  it("compounds two zoom steps that were both computed from the same state", () => {
    // 한 묶음 안에서 두 번 누르면 둘 다 **같은 옛 상태**를 보고 계산한다. 배율로
    // 보내면 reducer가 자기 상태에서 곱하므로 두 번 눌린 만큼 두 칸 간다.
    const options = { durationSec: 20, viewportWidthPx: 400, fps: { num: 30, den: 1 } } as const;
    const state = createTimelineNavigation({ durationSec: 20, pixelsPerSecond: 100 });
    const action = navigationKeyAction("+", false, { state, fps: options.fps });
    if (!action) throw new Error("zoom action is missing");

    const once = reduceTimelineNavigation(state, action, options);
    const twice = reduceTimelineNavigation(once, action, options);

    expect(once.pixelsPerSecond).toBeCloseTo(125, 6);
    expect(twice.pixelsPerSecond).toBeCloseTo(156.25, 6);
  });

  it("advances 10,000 ArrowRight actions by exact rational frame indices", () => {
    const repeatedOptions = { ...options, durationSec: 1_000 };
    let state = createTimelineNavigation({ durationSec: repeatedOptions.durationSec, pixelsPerSecond: 100 });

    for (let index = 0; index < 10_000; index += 1) {
      const action = navigationKeyAction("ArrowRight", false, { state, fps: repeatedOptions.fps });
      expect(action).not.toBeNull();
      state = reduceTimelineNavigation(state, action!, repeatedOptions);
    }

    expect(state.playheadSec).toBe(frameToSeconds(10_000, repeatedOptions.fps));
  });

  it("keeps selection local and rejects invalid navigation inputs", () => {
    const initial = createTimelineNavigation({ durationSec: 20, pixelsPerSecond: 10 });
    const selected = reduceTimelineNavigation(initial, { type: "select", clipId: "clip-a" }, options);
    const cleared = reduceTimelineNavigation(selected, { type: "select", clipId: null }, options);

    expect(selected.selectedClipId).toBe("clip-a");
    expect(cleared.selectedClipId).toBeNull();
    expect(() => createTimelineNavigation({ durationSec: -1, pixelsPerSecond: 10 })).toThrow(RangeError);
    expect(() => createTimelineNavigation({ durationSec: 1, pixelsPerSecond: 0 })).toThrow(RangeError);
    expect(() => reduceTimelineNavigation(initial, { type: "seek", seconds: Number.NaN }, options)).toThrow(RangeError);
    expect(() => reduceTimelineNavigation(initial, { type: "zoom", pixelsPerSecond: 10, anchorPx: Number.NaN }, options)).toThrow(RangeError);
    // 넘쳐 버린 확대는 거부한다. 계산이 키 처리기에서 reducer로 옮겨 갔으므로
    // **막는 자리도 같이 옮겼다** -- 곱하는 쪽이 막는다.
    expect(() => reduceTimelineNavigation(
      { ...initial, pixelsPerSecond: Number.MAX_VALUE },
      { type: "zoom", factor: 2 },
      options,
    )).toThrow(RangeError);
    expect(() => reduceTimelineNavigation({ ...initial, pixelsPerSecond: Number.MIN_VALUE }, { type: "scroll", seconds: 0 }, {
      durationSec: 1,
      viewportWidthPx: Number.MAX_VALUE,
      fps: options.fps,
    })).toThrow(RangeError);
    expect(() => reduceTimelineNavigation(initial, { type: "seek", bound: "middle" } as never, options)).toThrow(RangeError);
  });

  it("projects visible source clips into fixed timeline lanes", () => {
    const rects = projectVisibleTimelineClips({
      clips: [
        { id: "narration", role: "narration", startSec: 0.5, endSec: 1.5 },
        { id: "broll", role: "broll", startSec: 1, endSec: 2 },
        { id: "sfx", role: "sfx", startSec: 1, endSec: 1.5 },
      ],
      viewport: { startSec: 1, endSec: 2, topPx: 0, heightPx: 100 },
      pixelsPerSecond: 100,
      originSec: 1,
      laneHeightPx: 20,
    });

    expect(rects).toEqual([
      { clipId: "narration", lane: "narration", x: 0, y: 0, width: 50, height: 20 },
      { clipId: "broll", lane: "broll", x: 0, y: 20, width: 100, height: 20 },
      { clipId: "sfx", lane: "sfx", x: 0, y: 60, width: 50, height: 20 },
    ]);
  });

  it("keeps half-open visibility boundaries and projection input immutable", () => {
    const input = Object.freeze({
      clips: Object.freeze([
        Object.freeze({ id: "ends-at-start", role: "narration" as const, startSec: 0, endSec: 1 }),
        Object.freeze({ id: "inside", role: "broll" as const, startSec: 1, endSec: 2 }),
        Object.freeze({ id: "starts-at-end", role: "sfx" as const, startSec: 2, endSec: 3 }),
      ]),
      viewport: Object.freeze({ startSec: 1, endSec: 2, topPx: 0, heightPx: 100 }),
      pixelsPerSecond: 100,
      originSec: 1,
      laneHeightPx: 20,
    });

    const rects = projectVisibleTimelineClips(input);

    expect(rects.map((rect) => rect.clipId)).toEqual(["inside"]);
    expect(input).toEqual({
      clips: [
        { id: "ends-at-start", role: "narration", startSec: 0, endSec: 1 },
        { id: "inside", role: "broll", startSec: 1, endSec: 2 },
        { id: "starts-at-end", role: "sfx", startSec: 2, endSec: 3 },
      ],
      viewport: { startSec: 1, endSec: 2, topPx: 0, heightPx: 100 },
      pixelsPerSecond: 100,
      originSec: 1,
      laneHeightPx: 20,
    });
  });

  it("does not mutate the supplied state, action, or options", () => {
    const state = Object.freeze<TimelineNavigationState>({
      viewportStartSec: 1,
      pixelsPerSecond: 10,
      playheadSec: 2,
      selectedClipId: null,
    });
    const action = Object.freeze({ type: "select" as const, clipId: "clip-a" });
    const frozenOptions = Object.freeze({
      durationSec: 20,
      viewportWidthPx: 100,
      fps: Object.freeze({ num: 30_000, den: 1_001 }),
    });

    const result = reduceTimelineNavigation(state, action, frozenOptions);

    expect(result).not.toBe(state);
    expect(state).toEqual({ viewportStartSec: 1, pixelsPerSecond: 10, playheadSec: 2, selectedClipId: null });
    expect(action).toEqual({ type: "select", clipId: "clip-a" });
    expect(frozenOptions).toEqual({ durationSec: 20, viewportWidthPx: 100, fps: { num: 30_000, den: 1_001 } });
  });
});
