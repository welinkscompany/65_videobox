import { describe, expect, it } from "vitest";

import { PreviewCoordinator } from "./preview-coordinator";

describe("PreviewCoordinator", () => {
  it("keeps exactly one active media item and maps an audition range back to timeline time", () => {
    const coordinator = new PreviewCoordinator();
    coordinator.showExact({ id: "exact-r4", url: "/api/exact.mp4", timelineRange: { startSec: 0, endSec: 12 } });
    expect(coordinator.state).toMatchObject({ kind: "exact", activeMediaId: "exact-r4" });
    coordinator.showAudition({ id: "clip-a", url: "/api/a.mp4", mediaKind: "video", timelineRange: { startSec: 3, endSec: 8 } });
    expect(coordinator.state).toMatchObject({ kind: "audition", activeMediaId: "clip-a" });
    expect(coordinator.timelineTime(1.25)).toBe(4.25);
    expect(coordinator.timelineTime(99)).toBe(8);
    expect(coordinator.timelineTime(Number.NaN)).toBe(3);
    coordinator.stop();
    expect(coordinator.state).toEqual({ kind: "idle", activeMediaId: null });
  });
});
