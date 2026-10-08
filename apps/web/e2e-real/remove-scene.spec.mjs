import { expect, test } from "@playwright/test";
import { openEditor, readFixture, serverManifest, serverSession } from "./support/realFlow.mjs";

// 점검 §3-5 / 계획 H Task 12: 장면을 빼면 구멍이 남는다(출하 기본 leave_gap). 화면은 그 구멍을
// `빈 구간 1개`·`뺀 장면 자리`로 말해야 하고, 되돌리기 한 번에 원래로 돌아온다. 진짜 백엔드로 잰다.
const SCENE = "scene-2";
const NEXT = "scene-3";
const CLIP = /^영상 2번째 장면, \d+초부터$/;

const sceneOf = (session, id) => session.segments.find((segment) => segment.segment_id === id);
const removedGaps = (manifest) => manifest.gap_slots.filter((gap) => String(gap.gap_id).startsWith("removed:"));

test("장면 2를 빼면 구멍을 빈 구간으로 세고, 되돌리면 원래로 돌아온다", async ({ page, request }) => {
  const { clean } = readFixture();
  await openEditor(page, clean);
  const before = await serverSession(request, clean);
  const beforeScene = sceneOf(before, SCENE);
  const beforeNext = sceneOf(before, NEXT);
  expect(beforeScene.cut_action).toBe("keep");
  expect(removedGaps(await serverManifest(request, clean))).toEqual([]);
  await expect(page.getByText(/빈 구간 0개/)).toBeVisible();

  // 장면 2를 고르고 Delete.
  await page.getByRole("button", { name: CLIP }).click();
  await page.keyboard.press("Delete");

  await expect.poll(async () => sceneOf(await serverSession(request, clean), SCENE).cut_action, { timeout: 8000 }).toBe("remove");
  const removed = await serverSession(request, clean);
  // 출하 기본 leave_gap: 뒤 장면은 제자리, 당긴 흔적(ripple_removed_sec)도 없다.
  expect(sceneOf(removed, NEXT).start_sec).toBeCloseTo(beforeNext.start_sec, 6);
  expect(sceneOf(removed, NEXT).end_sec).toBeCloseTo(beforeNext.end_sec, 6);
  expect(sceneOf(removed, SCENE).start_sec).toBeCloseTo(beforeScene.start_sec, 6);

  const manifest = await serverManifest(request, clean);
  expect(removedGaps(manifest)).toEqual([
    expect.objectContaining({ gap_id: `removed:${SCENE}`, segment_id: SCENE, reason: "removed_scene" }),
  ]);
  expect(removedGaps(manifest)[0].start_sec).toBeCloseTo(beforeScene.start_sec, 3);
  expect(removedGaps(manifest)[0].end_sec).toBeCloseTo(beforeScene.end_sec, 3);

  // 화면: 머리 문장과 발 문장이 구멍을 말한다.
  await expect(page.getByText(/빈 구간 1개/)).toBeVisible();
  await expect(page.getByText("빈 구간: 뺀 장면 자리")).toBeVisible();

  // Control+Z 한 번 -> 서버가 원래대로, 화면도 0개.
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("Control+Z");
  await expect.poll(async () => sceneOf(await serverSession(request, clean), SCENE).cut_action, { timeout: 8000 }).toBe("keep");
  const restored = await serverSession(request, clean);
  for (const id of [SCENE, NEXT]) {
    expect(sceneOf(restored, id).start_sec).toBeCloseTo(sceneOf(before, id).start_sec, 6);
    expect(sceneOf(restored, id).end_sec).toBeCloseTo(sceneOf(before, id).end_sec, 6);
  }
  expect(removedGaps(await serverManifest(request, clean))).toEqual([]);
  await expect(page.getByText(/빈 구간 0개/)).toBeVisible();
});
