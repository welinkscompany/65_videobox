import { describe, expect, it } from "vitest";
import { activeSegmentIdAt, clampPlaybackSeconds } from "./playbackNavigation";

const entries = [{ segmentId: "s-1", startSec: 0, endSec: 2 }, { segmentId: "s-2", startSec: 2, endSec: 4 }];

describe("playback navigation", () => {
  it("clamps nonnegative playback seconds to the output duration", () => {
    expect(clampPlaybackSeconds(-1, 4)).toBe(0);
    expect(clampPlaybackSeconds(9, 4)).toBe(4);
  });
  it("uses half-open segment ranges so a boundary activates the next row", () => {
    expect(activeSegmentIdAt(entries, 2)).toBe("s-2");
    expect(activeSegmentIdAt(entries, 4)).toBeNull();
  });
});
