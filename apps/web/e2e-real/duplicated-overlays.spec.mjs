import { expect, test } from "@playwright/test";
import { readFixture, serverManifest, serverSession } from "./support/realFlow.mjs";

test("오염된 편집판에서도 오버레이 id가 겹치지 않고 자리 옮기기가 저장된다", async ({ request }) => {
  const fixture = readFixture().duplicatedOverlays;
  const manifest = await serverManifest(request, fixture);
  const overlays = manifest.tracks.filter((track) => track.track_type === "overlay").flatMap((track) => track.clips);
  const ids = overlays.map((clip) => clip.placement_id ?? clip.clip_id);
  expect(new Set(ids).size).toBe(ids.length);
  expect(overlays.map((clip) => clip.segment_id).sort()).toEqual(["timeline_001:001", "timeline_001:001__split_3"]);
  const before = await serverSession(request, fixture);
  const target = overlays[0];
  const response = await request.patch(`/api/projects/${fixture.projectId}/editing-sessions/${fixture.sessionId}/timeline-placements`, {
    data: { expected_revision: before.session_revision, changes: [{ placement_id: target.placement_id, kind: "overlay", start_sec: target.start_sec, end_sec: target.end_sec - 0.1 }] },
  });
  expect(response.status()).toBe(200);
});
