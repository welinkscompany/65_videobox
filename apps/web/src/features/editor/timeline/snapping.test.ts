import { describe, expect, it } from "vitest";

import { findTimelineSnap } from "./snapping";

describe("timeline snapping", () => {
  it("includes the pixel threshold", () => {
    expect(findTimelineSnap({
      candidates: [{ kind: "playhead", id: "playhead", timeSec: 1 }],
      proposedSec: 1.1,
      thresholdPx: 10,
      scale: { pixelsPerSecond: 100, originSec: 999 },
      fps: { num: 10, den: 1 },
    })).toEqual({ timeSec: 1, kind: "playhead", id: "playhead", frame: 10 });
  });

  it("quantizes candidates to frames and deduplicates a frame by kind rank", () => {
    expect(findTimelineSnap({
      candidates: [
        { kind: "neighbor-end", id: "later-rank", timeSec: 1.049 },
        { kind: "playhead", id: "earlier-rank", timeSec: 0.951 },
      ],
      proposedSec: 1,
      thresholdPx: 10,
      scale: { pixelsPerSecond: 100, originSec: 0 },
      fps: { num: 10, den: 1 },
    })).toEqual({ timeSec: 1, kind: "playhead", id: "earlier-rank", frame: 10 });
  });

  it("deduplicates same-kind candidates on a frame by code-unit ID in either input order", () => {
    const request = {
      proposedSec: 1,
      thresholdPx: 10,
      scale: { pixelsPerSecond: 100, originSec: 0 },
      fps: { num: 10, den: 1 },
    };
    const candidates = [
      { kind: "selected-start" as const, id: "a", timeSec: 0.951 },
      { kind: "selected-start" as const, id: "Z", timeSec: 1.049 },
    ];
    const expected = { timeSec: 1, kind: "selected-start", id: "Z", frame: 10 };

    expect(findTimelineSnap({ ...request, candidates })).toEqual(expected);
    expect(findTimelineSnap({ ...request, candidates: [...candidates].reverse() })).toEqual(expected);
  });

  it("keeps same-ID frame duplicates with different raw times input-order invariant", () => {
    const request = {
      proposedSec: 1,
      thresholdPx: 10,
      scale: { pixelsPerSecond: 100, originSec: 0 },
      fps: { num: 10, den: 1 },
    };
    const candidates = [
      { kind: "selected-start" as const, id: "same", timeSec: 0.951 },
      { kind: "selected-start" as const, id: "same", timeSec: 1.049 },
    ];

    expect(findTimelineSnap({ ...request, candidates })).toEqual({ timeSec: 1, kind: "selected-start", id: "same", frame: 10 });
    expect(findTimelineSnap({ ...request, candidates: [...candidates].reverse() })).toEqual({ timeSec: 1, kind: "selected-start", id: "same", frame: 10 });
  });

  it("prefers the shortest quantized distance before every other tie breaker", () => {
    expect(findTimelineSnap({
      candidates: [
        { kind: "playhead", id: "farther-higher-rank", timeSec: 0.75 },
        { kind: "neighbor-end", id: "closer-lower-rank", timeSec: 1.125 },
      ],
      proposedSec: 1,
      thresholdPx: 30,
      scale: { pixelsPerSecond: 100, originSec: 0 },
      fps: { num: 8, den: 1 },
    })).toEqual({ timeSec: 1.125, kind: "neighbor-end", id: "closer-lower-rank", frame: 9 });
  });

  it("uses the documented kind rank for equally distant frames", () => {
    expect(findTimelineSnap({
      candidates: [
        { kind: "neighbor-start", id: "lower-priority", timeSec: 0.875 },
        { kind: "selected-end", id: "higher-priority", timeSec: 1.125 },
      ],
      proposedSec: 1,
      thresholdPx: 13,
      scale: { pixelsPerSecond: 100, originSec: 0 },
      fps: { num: 8, den: 1 },
    })).toEqual({ timeSec: 1.125, kind: "selected-end", id: "higher-priority", frame: 9 });
  });

  it("uses code-unit ID ordering for equally distant candidates of the same kind", () => {
    expect(findTimelineSnap({
      candidates: [
        { kind: "selected-start", id: "a", timeSec: 1.125 },
        { kind: "selected-start", id: "Z", timeSec: 0.875 },
      ],
      proposedSec: 1,
      thresholdPx: 13,
      scale: { pixelsPerSecond: 100, originSec: 0 },
      fps: { num: 8, den: 1 },
    })).toEqual({ timeSec: 0.875, kind: "selected-start", id: "Z", frame: 7 });
  });

  it("uses the earlier quantized time as the final tie breaker", () => {
    expect(findTimelineSnap({
      candidates: [
        { kind: "selected-start", id: "same", timeSec: 1.125 },
        { kind: "selected-start", id: "same", timeSec: 0.875 },
      ],
      proposedSec: 1,
      thresholdPx: 13,
      scale: { pixelsPerSecond: 100, originSec: 0 },
      fps: { num: 8, den: 1 },
    })).toEqual({ timeSec: 0.875, kind: "selected-start", id: "same", frame: 7 });
  });

  it("is invariant to candidate order without mutating the candidate array", () => {
    const candidates = [
      { kind: "neighbor-end" as const, id: "neighbor", timeSec: 0.875 },
      { kind: "playhead" as const, id: "playhead", timeSec: 1.125 },
      { kind: "selected-start" as const, id: "selected", timeSec: 1.125 },
    ];
    const original = [...candidates];
    const request = {
      proposedSec: 1,
      thresholdPx: 13,
      scale: { pixelsPerSecond: 100, originSec: 0 },
      fps: { num: 8, den: 1 },
    };

    expect(findTimelineSnap({ ...request, candidates })).toEqual(findTimelineSnap({ ...request, candidates: [...candidates].reverse() }));
    expect(candidates).toEqual(original);
  });

  it("returns null when no candidate is inside the threshold", () => {
    expect(findTimelineSnap({
      candidates: [{ kind: "playhead", id: "playhead", timeSec: 2 }],
      proposedSec: 1,
      thresholdPx: 10,
      scale: { pixelsPerSecond: 100, originSec: 0 },
      fps: { num: 10, den: 1 },
    })).toBeNull();
  });

  it("rejects unknown candidates and nonfinite timeline inputs", () => {
    const valid = {
      candidates: [{ kind: "playhead", id: "playhead", timeSec: 1 }],
      proposedSec: 1,
      thresholdPx: 1,
      scale: { pixelsPerSecond: 100, originSec: 0 },
      fps: { num: 10, den: 1 },
    };

    expect(() => findTimelineSnap({ ...valid, candidates: [{ kind: "marker", id: "x", timeSec: 1 }] as never })).toThrow(RangeError);
    expect(() => findTimelineSnap({ ...valid, candidates: [{ kind: "playhead", id: "", timeSec: 1 }] })).toThrow(RangeError);
    expect(() => findTimelineSnap({ ...valid, candidates: [{ kind: "playhead", id: Number.POSITIVE_INFINITY as never, timeSec: 1 }] })).toThrow(RangeError);
    expect(() => findTimelineSnap({ ...valid, candidates: [{ kind: "playhead", id: "x", timeSec: Number.NaN }] })).toThrow(RangeError);
    expect(() => findTimelineSnap({ ...valid, proposedSec: Number.POSITIVE_INFINITY })).toThrow(RangeError);
    expect(() => findTimelineSnap({ ...valid, thresholdPx: -1 })).toThrow(RangeError);
  });

  it("accepts the largest safe frame without leaving the frame domain", () => {
    expect(findTimelineSnap({
      candidates: [{ kind: "playhead", id: "playhead", timeSec: Number.MAX_SAFE_INTEGER }],
      proposedSec: Number.MAX_SAFE_INTEGER,
      thresholdPx: 0,
      scale: { pixelsPerSecond: 1, originSec: 123 },
      fps: { num: 1, den: 1 },
    })).toEqual({ timeSec: Number.MAX_SAFE_INTEGER, kind: "playhead", id: "playhead", frame: Number.MAX_SAFE_INTEGER });
  });

  it("does not snap an adjacent quantized frame at a zero-pixel threshold", () => {
    expect(findTimelineSnap({
      candidates: [{ kind: "playhead", id: "adjacent", timeSec: 5_000_000_000_000.001 }],
      proposedSec: 5_000_000_000_000,
      thresholdPx: 0,
      scale: { pixelsPerSecond: 1, originSec: 0 },
      fps: { num: 1000, den: 1 },
    })).toBeNull();
  });
});
