import { describe, expect, it } from "vitest";
import { projectTranscriptEntries, visibleTranscriptWindow } from "./transcriptProjection";

describe("transcript projection", () => {
  it("keeps valid caption ranges in stable time order", () => {
    const result = projectTranscriptEntries({
      captions: [{ segmentId: "s-2", text: "둘", startSec: 2, endSec: 4 }, { segmentId: "s-1", text: "하나", startSec: 0, endSec: 2 }],
      narration: [{ segmentId: "s-1", startSec: 0, endSec: 2 }, { segmentId: "s-2", startSec: 2, endSec: 4 }],
    });
    expect(result.map((item) => item.segmentId)).toEqual(["s-1", "s-2"]);
  });
  it("keeps session caption ranges when one narration asset spans several visible segments", () => {
    const result = projectTranscriptEntries({
      captions: [
        { segmentId: "visible-1", text: "첫 장면", startSec: 0, endSec: 5 },
        { segmentId: "visible-2", text: "둘째 장면", startSec: 5, endSec: 10 },
      ],
      narration: [{ segmentId: "visible-1", startSec: 0, endSec: 10 }],
    });
    expect(result).toEqual([
      { segmentId: "visible-1", text: "첫 장면", startSec: 0, endSec: 5 },
      { segmentId: "visible-2", text: "둘째 장면", startSec: 5, endSec: 10 },
    ]);
  });
  it("limits a 1,000-row transcript to the requested mounted window", () => {
    const entries = Array.from({ length: 1000 }, (_, index) => ({ segmentId: `s-${index}`, text: "자막", startSec: index, endSec: index + 1 }));
    expect(visibleTranscriptWindow(entries, 500, 120)).toHaveLength(120);
  });
});
