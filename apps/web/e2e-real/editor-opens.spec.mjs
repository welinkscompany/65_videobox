import { expect, test } from "@playwright/test";
import { openEditor, readFixture, serverManifest } from "./support/realFlow.mjs";

test("진짜 백엔드의 고정 시험 프로젝트가 편집기로 열린다", async ({ page, request }) => {
  const { clean } = readFixture();
  await openEditor(page, clean);
  const manifest = await serverManifest(request, clean);
  const narration = manifest.tracks.find((track) => track.track_type === "narration");
  expect(narration.clips.map((clip) => clip.start_sec)).toEqual([0, 1.3324, 1.8990646, 2.9281]);
  await expect(page.getByTestId("timeline-clip")).not.toHaveCount(0);
});
