import { describe, expect, it } from "vitest";
import { frameToSeconds } from "./time-scale";
import { deriveNarrationTrim, reorderNarrationLayout, type NarrationSegment } from "./narrationMutation";

const fps = { num: 24, den: 1 };

describe("narration mutation drafts", () => {
  it("snaps a proposed trim to the nearest rational frame", () => {
    const result = deriveNarrationTrim({
      clip: { segmentId: "middle", startSec: 1, endSec: 2 },
      edge: "start",
      proposedSec: 1.03,
      narration: [
        { segmentId: "first", startSec: 0, endSec: 1 },
        { segmentId: "middle", startSec: 1, endSec: 2 },
      ],
      durationSec: 3,
      fps,
    });

    expect(result).toEqual({ startSec: frameToSeconds(25, fps), endSec: 2 });
  });

  it("clamps the start trim to the predecessor end", () => {
    expect(deriveNarrationTrim({
      clip: { segmentId: "middle", startSec: 1, endSec: 2 },
      edge: "start",
      proposedSec: 0.1,
      narration: [
        { segmentId: "first", startSec: 0, endSec: 1 },
        { segmentId: "middle", startSec: 1, endSec: 2 },
        { segmentId: "last", startSec: 2, endSec: 3 },
      ],
      durationSec: 3,
      fps,
    })).toEqual({ startSec: 1, endSec: 2 });
  });

  it("keeps both trim bounds on rational frame boundaries after a non-grid predecessor", () => {
    const ntscFps = { num: 30_000, den: 1_001 };
    const clipEnd = frameToSeconds(62, ntscFps);

    expect(deriveNarrationTrim({
      clip: { segmentId: "middle", startSec: 1.01, endSec: clipEnd },
      edge: "start",
      proposedSec: 0,
      narration: [
        { segmentId: "first", startSec: 0, endSec: 1.01 },
        { segmentId: "middle", startSec: 1.01, endSec: clipEnd },
      ],
      durationSec: 3,
      fps: ntscFps,
    })).toEqual({
      startSec: frameToSeconds(31, ntscFps),
      endSec: frameToSeconds(62, ntscFps),
    });
  });

  it("clamps the end trim to the successor start", () => {
    expect(deriveNarrationTrim({
      clip: { segmentId: "middle", startSec: 1, endSec: 2 },
      edge: "end",
      proposedSec: 2.9,
      narration: [
        { segmentId: "first", startSec: 0, endSec: 1 },
        { segmentId: "middle", startSec: 1, endSec: 2 },
        { segmentId: "last", startSec: 2, endSec: 3 },
      ],
      durationSec: 3,
      fps,
    })).toEqual({ startSec: 1, endSec: 2 });
  });

  it("keeps exactly one frame when trim would collapse the clip", () => {
    const oneFrame = frameToSeconds(1, fps);

    expect(deriveNarrationTrim({
      clip: { segmentId: "only", startSec: 0, endSec: oneFrame },
      edge: "start",
      proposedSec: 10,
      narration: [{ segmentId: "only", startSec: 0, endSec: oneFrame }],
      durationSec: 10,
      fps,
    })).toEqual({ startSec: 0, endSec: oneFrame });
  });

  it("rejects invalid values and unknown narration segment ids", () => {
    const narration = [{ segmentId: "known", startSec: 0, endSec: 1 }];

    expect(() => deriveNarrationTrim({
      clip: { segmentId: "missing", startSec: 0, endSec: 1 },
      edge: "start",
      proposedSec: 0,
      narration,
      durationSec: 1,
      fps,
    })).toThrow(RangeError);
    expect(() => deriveNarrationTrim({
      clip: { segmentId: "known", startSec: 0, endSec: 1 },
      edge: "start",
      proposedSec: Number.NaN,
      narration,
      durationSec: 1,
      fps,
    })).toThrow(RangeError);
    expect(() => reorderNarrationLayout({ narration, movingId: "missing", targetIndex: 0 })).toThrow(RangeError);
    expect(() => reorderNarrationLayout({ narration, movingId: "known", targetIndex: 1.5 })).toThrow(RangeError);
  });

  it("rejects sparse narration arrays with RangeError", () => {
    const sparse = new Array(2) as NarrationSegment[];
    sparse[0] = { segmentId: "known", startSec: 0, endSec: 1 };

    expect(() => reorderNarrationLayout({ narration: sparse, movingId: "known", targetIndex: 0 })).toThrow(RangeError);
  });

  it("rejects same-start non-ASCII segment ids without locale-sensitive ordering", () => {
    expect(() => reorderNarrationLayout({
      narration: [
        { segmentId: "가", startSec: 0, endSec: 1 },
        { segmentId: "z", startSec: 0, endSec: 1 },
      ],
      movingId: "z",
      targetIndex: 0,
    })).toThrow(RangeError);
  });

  it("creates an immutable contiguous reorder layout from earliest start", () => {
    const narration = [
      { segmentId: "right", startSec: 2, endSec: 4 },
      { segmentId: "left", startSec: 0, endSec: 2 },
      { segmentId: "tail", startSec: 4, endSec: 5 },
    ];
    Object.freeze(narration);
    narration.forEach(Object.freeze);

    expect(reorderNarrationLayout({ narration, movingId: "right", targetIndex: 0 })).toEqual({
      segmentIds: ["right", "left", "tail"],
      boundsById: {
        right: { startSec: 0, endSec: 2 },
        left: { startSec: 2, endSec: 4 },
        tail: { startSec: 4, endSec: 5 },
      },
    });
    expect(narration).toEqual([
      { segmentId: "right", startSec: 2, endSec: 4 },
      { segmentId: "left", startSec: 0, endSec: 2 },
      { segmentId: "tail", startSec: 4, endSec: 5 },
    ]);
  });

  it("expands a previously shrunken start back to its predecessor boundary", () => {
    const original = { segmentId: "middle", startSec: 1, endSec: 2 };
    const predecessor = { segmentId: "first", startSec: 0, endSec: 1 };
    const shrunkenBounds = deriveNarrationTrim({
      clip: original,
      edge: "start",
      proposedSec: 1.5,
      narration: [predecessor, original],
      durationSec: 3,
      fps,
    });
    const shrunken = { segmentId: "middle", ...shrunkenBounds };

    expect(deriveNarrationTrim({
      clip: shrunken,
      edge: "start",
      proposedSec: 0.25,
      narration: [predecessor, shrunken],
      durationSec: 3,
      fps,
    })).toEqual({ startSec: 1, endSec: 2 });
  });

  it("expands a previously shrunken end back to its successor boundary", () => {
    const original = { segmentId: "middle", startSec: 1, endSec: 2 };
    const successor = { segmentId: "last", startSec: 2, endSec: 3 };
    const shrunkenBounds = deriveNarrationTrim({
      clip: original,
      edge: "end",
      proposedSec: 1.5,
      narration: [original, successor],
      durationSec: 3,
      fps,
    });
    const shrunken = { segmentId: "middle", ...shrunkenBounds };

    expect(deriveNarrationTrim({
      clip: shrunken,
      edge: "end",
      proposedSec: 2.75,
      narration: [shrunken, successor],
      durationSec: 3,
      fps,
    })).toEqual({ startSec: 1, endSec: 2 });
  });

  it("uses timeline zero and duration when the clip has no neighbours", () => {
    const clip = { segmentId: "only", startSec: 1, endSec: 2 };

    expect(deriveNarrationTrim({
      clip,
      edge: "start",
      proposedSec: 0,
      narration: [clip],
      durationSec: 4,
      fps,
    })).toEqual({ startSec: 0, endSec: 2 });
    expect(deriveNarrationTrim({
      clip,
      edge: "end",
      proposedSec: 4,
      narration: [clip],
      durationSec: 4,
      fps,
    })).toEqual({ startSec: 1, endSec: 4 });
  });

  it("keeps expanded bounds on safe frame sides of non-grid neighbours", () => {
    const ntscFps = { num: 30_000, den: 1_001 };
    const clip = {
      segmentId: "middle",
      startSec: frameToSeconds(40, ntscFps),
      endSec: frameToSeconds(60, ntscFps),
    };
    const narration = [
      { segmentId: "first", startSec: 0, endSec: 1.01 },
      clip,
      { segmentId: "last", startSec: 2.09, endSec: 3 },
    ];

    expect(deriveNarrationTrim({
      clip,
      edge: "start",
      proposedSec: 0,
      narration,
      durationSec: 4,
      fps: ntscFps,
    })).toEqual({
      startSec: frameToSeconds(31, ntscFps),
      endSec: frameToSeconds(60, ntscFps),
    });
    expect(deriveNarrationTrim({
      clip,
      edge: "end",
      proposedSec: 4,
      narration,
      durationSec: 4,
      fps: ntscFps,
    })).toEqual({
      startSec: frameToSeconds(40, ntscFps),
      endSec: frameToSeconds(62, ntscFps),
    });
  });

  it("clamps finite proposals outside the timeline instead of rejecting them", () => {
    const clip = { segmentId: "only", startSec: 1, endSec: 2 };

    expect(deriveNarrationTrim({
      clip,
      edge: "start",
      proposedSec: -100,
      narration: [clip],
      durationSec: 4,
      fps,
    })).toEqual({ startSec: 0, endSec: 2 });
    expect(deriveNarrationTrim({
      clip,
      edge: "end",
      proposedSec: 100,
      narration: [clip],
      durationSec: 4,
      fps,
    })).toEqual({ startSec: 1, endSec: 4 });
  });
});
