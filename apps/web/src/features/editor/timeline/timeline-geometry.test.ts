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
