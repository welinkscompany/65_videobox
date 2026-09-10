import { describe, expect, it } from "vitest";

import {
  TIMELINE_LANES,
  deriveClipRect,
  findClipNeighbors,
  selectVisibleClips,
} from "./timeline-geometry";
import type { TimelineClip } from "./timeline-geometry";

describe("timeline geometry", () => {
  it("uses a half-open viewport", () => {
    const clips = [
      { id: "ends-at-start", lane: "narration" as const, startSec: 0, endSec: 1 },
      { id: "starts-at-end", lane: "broll" as const, startSec: 2, endSec: 3 },
      { id: "inside", lane: "bgm" as const, startSec: 1, endSec: 2 },
    ];

    expect(selectVisibleClips(clips, { startSec: 1, endSec: 2 }).map((clip) => clip.id)).toEqual(["inside"]);
  });

  it("keeps stable lanes in narration, broll, bgm, sfx, overlay order", () => {
    expect(TIMELINE_LANES).toEqual(["narration", "broll", "bgm", "sfx", "overlay", "caption"]);
  });

  it("keeps only the shared-boundary clip in a half-open viewport", () => {
    const clips = [
      { id: "before", lane: "narration" as const, startSec: 0, endSec: 1 },
      { id: "shared", lane: "broll" as const, startSec: 1, endSec: 2 },
      { id: "after", lane: "bgm" as const, startSec: 2, endSec: 3 },
    ];

    expect(selectVisibleClips(clips, { startSec: 1, endSec: 2 }).map((clip) => clip.id)).toEqual(["shared"]);
  });

  it("returns no clips for an empty viewport", () => {
    const clips = [
      { id: "spans-empty-viewport", lane: "narration" as const, startSec: 0, endSec: 2 },
    ];

    expect(selectVisibleClips(clips, { startSec: 1, endSec: 1 })).toEqual([]);
  });

  it("derives finite data-only clip rectangles without rotation or canvas inputs", () => {
    const rect = deriveClipRect(
      { id: "clip-1", lane: "broll", startSec: 2, endSec: 4 },
      { startSec: 0, endSec: 8, topPx: 12, heightPx: 200 },
      { pixelsPerSecond: 100, originSec: 1 },
      30,
    );

    expect(rect).not.toBeNull();
    if (rect === null) {
      throw new Error("Expected visible clip geometry");
    }
    expect(rect).toEqual({ clipId: "clip-1", lane: "broll", x: 100, y: 30, width: 200, height: 30 });
    expect(Object.keys(rect)).toEqual(["clipId", "lane", "x", "y", "width", "height"]);
  });

  // 자유 멀티트랙 Phase 7 -- 줄이 **데이터에서** 온다.
  //
  // 지금은 `TIMELINE_LANES` 여섯 개가 코드에 박혀 있어서, 트랙을 추가해도
  // (Phase 5의 문) 화면에 줄이 안 생긴다. 같은 종류 트랙 둘은 한 줄 안에서
  // 겹쳐 그려진다.
  describe("줄을 세션 트랙 목록에서 뽑을 때", () => {
    const rows = ["narration", "broll", "track-broll-2", "bgm", "sfx", "overlay", "caption"] as const;
    const viewport = { startSec: 0, endSec: 8, topPx: 0, heightPx: 400 };
    const scale = { pixelsPerSecond: 100, originSec: 0 };

    it("추가한 트랙의 클립은 그 트랙 줄에 놓인다", () => {
      const rect = deriveClipRect(
        { id: "clip-2", lane: "broll", trackId: "track-broll-2", startSec: 0, endSec: 1 },
        viewport, scale, 30, rows,
      );

      expect(rect?.y).toBe(60); // rows[2]
    });

    it("이름표가 없는 클립은 그 종류의 줄에 그대로 놓인다", () => {
      const rect = deriveClipRect(
        { id: "clip-1", lane: "broll", startSec: 0, endSec: 1 },
        viewport, scale, 30, rows,
      );

      expect(rect?.y).toBe(30); // rows[1]
    });

    it("모르는 이름표는 작업판을 죽이지 않고 그 종류의 줄로 내린다", () => {
      // `requireClip`이 모르는 줄에 `RangeError`를 던지면 작업판 **전체**가
      // 죽는다. 지운 트랙의 이름표가 남아 있는 것만으로 편집기를 못 여는
      // 상태가 되면 안 된다.
      const rect = deriveClipRect(
        { id: "clip-3", lane: "broll", trackId: "track-broll-지워짐", startSec: 0, endSec: 1 },
        viewport, scale, 30, rows,
      );

      expect(rect?.y).toBe(30);
    });

    it("줄 목록을 안 주면 예전 여섯 줄 그대로다", () => {
      // 지금 있는 편집본은 전부 이 길로 온다 -- 한 픽셀도 움직이면 안 된다.
      for (const [index, lane] of TIMELINE_LANES.entries()) {
        const rect = deriveClipRect({ id: `c-${lane}`, lane, startSec: 0, endSec: 1 }, viewport, scale, 30);
        expect(rect?.y).toBe(index * 30);
      }
    });
  });

  it("clips partially visible time geometry to the viewport", () => {
    expect(deriveClipRect(
      { id: "partial", lane: "narration", startSec: 0, endSec: 5 },
      { startSec: 2, endSec: 4, topPx: 0, heightPx: 30 },
      { pixelsPerSecond: 10, originSec: 0 },
      20,
    )).toEqual({ clipId: "partial", lane: "narration", x: 20, y: 0, width: 20, height: 20 });
  });

  it("returns null when a clip has no positive time intersection with the viewport", () => {
    expect(deriveClipRect(
      { id: "outside", lane: "narration", startSec: 0, endSec: 1 },
      { startSec: 1, endSec: 3, topPx: 0, heightPx: 30 },
      { pixelsPerSecond: 10, originSec: 0 },
      20,
    )).toBeNull();
  });

  it("clips lane geometry to the vertical viewport", () => {
    expect(deriveClipRect(
      { id: "vertical", lane: "broll", startSec: 0, endSec: 2 },
      { startSec: 0, endSec: 2, topPx: 45, heightPx: 10 },
      { pixelsPerSecond: 10, originSec: 0 },
      30,
    )).toEqual({ clipId: "vertical", lane: "broll", x: 0, y: 45, width: 20, height: 10 });
  });

  it("returns null when a lane has no positive vertical intersection with the viewport", () => {
    expect(deriveClipRect(
      { id: "outside-lane", lane: "broll", startSec: 0, endSec: 2 },
      { startSec: 0, endSec: 2, topPx: 0, heightPx: 30 },
      { pixelsPerSecond: 10, originSec: 0 },
      30,
    )).toBeNull();
  });

  it("rejects invalid clip data and time viewport bounds", () => {
    const validClip = { id: "valid", lane: "narration" as const, startSec: 0, endSec: 1 };

    expect(() => selectVisibleClips([{ ...validClip, id: "" }], { startSec: 0, endSec: 1 })).toThrow(RangeError);
    expect(() => selectVisibleClips([{ ...validClip, lane: "dialogue" as never }], { startSec: 0, endSec: 1 })).toThrow(RangeError);
    expect(() => selectVisibleClips([{ ...validClip, startSec: 1, endSec: 1 }], { startSec: 0, endSec: 1 })).toThrow(RangeError);
    expect(() => selectVisibleClips([validClip], { startSec: 2, endSec: 1 })).toThrow(RangeError);
  });

  it("rejects nonpositive geometry viewport height and invalid geometry inputs", () => {
    const validClip = { id: "valid", lane: "narration" as const, startSec: 0, endSec: 1 };
    const validViewport = { startSec: 0, endSec: 2, topPx: 0, heightPx: 100 };
    const validScale = { pixelsPerSecond: 100, originSec: 0 };

    expect(() => deriveClipRect(validClip, validViewport, validScale, 0)).toThrow(RangeError);
    expect(() => deriveClipRect(validClip, { ...validViewport, heightPx: 0 }, validScale, 10)).toThrow(RangeError);
    expect(() => deriveClipRect(validClip, { ...validViewport, topPx: -1 }, validScale, 10)).toThrow(RangeError);
    expect(() => deriveClipRect(validClip, { ...validViewport, heightPx: Number.POSITIVE_INFINITY }, validScale, 10)).toThrow(RangeError);
    expect(() => deriveClipRect(validClip, validViewport, { pixelsPerSecond: 0, originSec: 0 }, 10)).toThrow(RangeError);
  });

  it("rejects nonfinite rectangle overflows", () => {
    const validClip = { id: "valid", lane: "narration" as const, startSec: 0, endSec: 1 };
    const validViewport = { startSec: 0, endSec: Number.MAX_VALUE, topPx: 0, heightPx: 100 };
    const validScale = { pixelsPerSecond: 100, originSec: 0 };

    expect(() => deriveClipRect(
      { ...validClip, startSec: Number.MAX_VALUE / 2, endSec: Number.MAX_VALUE },
      validViewport,
      { pixelsPerSecond: 3, originSec: 0 },
      10,
    )).toThrow(RangeError);
    expect(() => deriveClipRect({ ...validClip, lane: "broll" }, { ...validViewport, topPx: Number.MAX_VALUE }, validScale, Number.MAX_VALUE)).toThrow(RangeError);
  });

  it("finds deterministic neighbors from a sorted copy without mutating clips", () => {
    const clips = [
      { id: "later", lane: "overlay" as const, startSec: 5, endSec: 6 },
      { id: "target", lane: "broll" as const, startSec: 2, endSec: 4 },
      { id: "earlier", lane: "narration" as const, startSec: 0, endSec: 1 },
      { id: "tied-id-first", lane: "sfx" as const, startSec: 2, endSec: 4 },
    ];
    const originalOrder = clips.map((clip) => clip.id);

    expect(findClipNeighbors(clips, "target")).toEqual({
      previous: clips[2],
      next: clips[3],
    });
    expect(clips.map((clip) => clip.id)).toEqual(originalOrder);
    expect(() => findClipNeighbors(clips, "missing")).toThrow(RangeError);
  });

  it("uses exact code-unit ID ordering instead of locale ordering for tied clips", () => {
    const clips = [
      { id: "z", lane: "overlay" as const, startSec: 2, endSec: 4 },
      { id: "a", lane: "broll" as const, startSec: 2, endSec: 4 },
      { id: "Z", lane: "narration" as const, startSec: 2, endSec: 4 },
    ];

    expect(findClipNeighbors(clips, "a")).toEqual({
      previous: clips[2],
      next: clips[0],
    });
  });

  it("rejects duplicate clip IDs before finding neighbors", () => {
    const clips = [
      { id: "duplicate", lane: "narration" as const, startSec: 0, endSec: 1 },
      { id: "duplicate", lane: "broll" as const, startSec: 1, endSec: 2 },
    ];

    expect(() => findClipNeighbors(clips, "duplicate")).toThrow(RangeError);
  });

  it("rejects sparse clip arrays before finding neighbors", () => {
    const clips = new Array<TimelineClip>(1);

    expect(() => findClipNeighbors(clips, "missing")).toThrow(RangeError);
  });
});
