import { describe, expect, it } from "vitest";
import { derivePlacementMove, derivePlacementTrim } from "./placementMutation";

const placement = { placementId: "broll:b-1", kind: "broll" as const, startSec: 2, endSec: 4 };
const common = { durationSec: 10, fps: { num: 25, den: 1 } };

describe("placement mutations", () => {
  it("moves independently placed media within the output and frame-snaps it", () => {
    expect(derivePlacementMove({ ...common, placement, proposedStartSec: 9 })).toEqual({ startSec: 8, endSec: 10 });
  });
  it("trims every mutable kind while retaining one frame", () => {
    expect(derivePlacementTrim({ ...common, placement: { ...placement, placementId: "caption:c-1", kind: "caption" }, edge: "start", proposedSec: 9 })).toEqual({ startSec: 3.96, endSec: 4 });
    expect(derivePlacementTrim({ ...common, placement, edge: "end", proposedSec: 2 })).toEqual({ startSec: 2, endSec: 2.04 });
  });
});
