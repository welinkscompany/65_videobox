import { describe, expect, it } from "vitest";

import { classifyTimelineHit } from "./hit-testing";

describe("classifyTimelineHit", () => {
  it("prefers a selected clip start handle over a same-lane body", () => {
    expect(classifyTimelineHit({
      point: { x: 101, y: 10 },
      lane: "narration",
      edgeHandlePx: 8,
      selectedClipId: "selected",
      rects: [
        { clipId: "body", lane: "narration", x: 90, y: 0, width: 40, height: 20, zIndex: 10 },
        { clipId: "selected", lane: "narration", x: 100, y: 0, width: 40, height: 20, zIndex: 0 },
      ],
    })).toEqual({ kind: "edge", edge: "start", clipId: "selected" });
  });

  it("classifies a selected clip end handle", () => {
    expect(classifyTimelineHit({
      point: { x: 139, y: 10 },
      lane: "narration",
      edgeHandlePx: 8,
      selectedClipId: "selected",
      rects: [{ clipId: "selected", lane: "narration", x: 100, y: 0, width: 40, height: 20, zIndex: 0 }],
    })).toEqual({ kind: "edge", edge: "end", clipId: "selected" });
  });

  it("does not classify a selected edge from another supplied lane", () => {
    expect(classifyTimelineHit({
      point: { x: 101, y: 10 },
      lane: "broll",
      edgeHandlePx: 8,
      selectedClipId: "selected",
      rects: [{ clipId: "selected", lane: "narration", x: 100, y: 0, width: 40, height: 20, zIndex: 0 }],
    })).toEqual({ kind: "gap", lane: "broll" });
  });

  it("chooses the highest z-index among same-lane bodies", () => {
    expect(classifyTimelineHit({
      point: { x: 20, y: 10 },
      lane: "broll",
      edgeHandlePx: 4,
      rects: [
        { clipId: "low", lane: "broll", x: 0, y: 0, width: 40, height: 20, zIndex: 1 },
        { clipId: "high", lane: "broll", x: 0, y: 0, width: 40, height: 20, zIndex: 2 },
      ],
    })).toEqual({ kind: "body", clipId: "high" });
  });

  it("uses lexical code-unit clip IDs to resolve equal body priority", () => {
    expect(classifyTimelineHit({
      point: { x: 20, y: 10 },
      lane: "broll",
      edgeHandlePx: 4,
      rects: [
        { clipId: "z", lane: "broll", x: 0, y: 0, width: 40, height: 20, zIndex: 2 },
        { clipId: "a", lane: "broll", x: 0, y: 0, width: 40, height: 20, zIndex: 2 },
      ],
    })).toEqual({ kind: "body", clipId: "a" });
  });

  it("returns a lane gap even when another lane contains the point", () => {
    expect(classifyTimelineHit({
      point: { x: 20, y: 10 },
      lane: "narration",
      edgeHandlePx: 4,
      rects: [{ clipId: "other", lane: "broll", x: 0, y: 0, width: 40, height: 20, zIndex: 1 }],
    })).toEqual({ kind: "gap", lane: "narration" });
  });

  it("returns empty without a lane and no containing selected edge", () => {
    expect(classifyTimelineHit({
      point: { x: 20, y: 10 },
      edgeHandlePx: 4,
      rects: [],
    })).toEqual({ kind: "empty" });
  });

  it("chooses start when a short selected clip has overlapping edge zones", () => {
    expect(classifyTimelineHit({
      point: { x: 102, y: 10 },
      lane: "narration",
      edgeHandlePx: 8,
      selectedClipId: "selected",
      rects: [{ clipId: "selected", lane: "narration", x: 100, y: 0, width: 4, height: 20, zIndex: 0 }],
    })).toEqual({ kind: "edge", edge: "start", clipId: "selected" });
  });

  it("rejects invalid values and duplicate IDs without mutating rects", () => {
    const rects = [
      { clipId: "b", lane: "narration" as const, x: 0, y: 0, width: 20, height: 20, zIndex: 1 },
      { clipId: "a", lane: "narration" as const, x: 0, y: 0, width: 20, height: 20, zIndex: 1 },
    ];
    const original = structuredClone(rects);

    expect(() => classifyTimelineHit({
      point: { x: Number.NaN, y: 0 }, lane: "narration", edgeHandlePx: 4, rects,
    })).toThrow(RangeError);
    expect(() => classifyTimelineHit({
      point: { x: 0, y: 0 }, lane: "narration", edgeHandlePx: 0, rects,
    })).toThrow(RangeError);
    expect(() => classifyTimelineHit({
      point: { x: 0, y: 0 }, lane: "narration", edgeHandlePx: 4, rects: [{ ...rects[0], width: 0 }],
    })).toThrow(RangeError);
    expect(() => classifyTimelineHit({
      point: { x: 0, y: 0 }, lane: "narration", edgeHandlePx: 4, rects: [{ ...rects[0], zIndex: Number.POSITIVE_INFINITY }],
    })).toThrow(RangeError);
    expect(() => classifyTimelineHit({
      point: { x: 0, y: 0 }, lane: "narration", edgeHandlePx: 4, rects: [rects[0], { ...rects[0] }],
    })).toThrow(RangeError);
    expect(() => classifyTimelineHit({
      point: { x: 0, y: 0 }, lane: "invalid" as "narration", edgeHandlePx: 4, rects,
    })).toThrow(RangeError);
    expect(() => classifyTimelineHit({
      point: { x: 0, y: 0 }, lane: "narration", edgeHandlePx: 4, selectedClipId: "", rects,
    })).toThrow(RangeError);
    expect(() => classifyTimelineHit({
      point: { x: 0, y: 0 }, lane: "narration", edgeHandlePx: 4, rects: [{ ...rects[0], lane: "invalid" as "narration" }],
    })).toThrow(RangeError);
    expect(rects).toEqual(original);
  });
});
