import { expect, test } from "@playwright/test";
import { openEditor, readFixture, serverManifest, serverSession } from "./support/realFlow.mjs";

// 내레이션 줄이 없고 자막의 계보 id가 낡은 프로젝트(742e1924 실제 모양, 2026-10-09 실기 점검).
// [소유 id 끝부분, 구간]
const SCENES = ["0.00–2.00초 구간", "2.00–4.50초 구간", "4.50–7.00초 구간", "7.00–9.50초 구간"];

async function selectClipBy(page, prefix, ordinal) {
  await page.locator(`[data-testid="timeline-clip"][data-clip-id^="${prefix}"]`).nth(ordinal)
    .locator('[data-native-control="timeline-clip-select"]').click();
  await page.waitForTimeout(250);
}

test("고정 시험 프로젝트가 실제 모양이다 -- 내레이션 없음, 낡은 자막 계보 id", async ({ request }) => {
  const manifest = await serverManifest(request, readFixture().noNarration);
  const narration = manifest.tracks.find((track) => track.track_type === "narration");
  expect(narration?.clips ?? []).toEqual([]);
  const stale = manifest.captions.filter((caption) => caption.segment_id !== caption.owning_segment_id);
  expect(stale.length).toBeGreaterThanOrEqual(2);
  expect(new Set(manifest.captions.map((caption) => caption.owning_segment_id)).size).toBe(4);
});

test("영상 줄과 캡션 줄의 어느 클립을 눌러도 오른쪽 편집 항목은 그 장면이다", async ({ page }) => {
  await openEditor(page, readFixture().noNarration);
  for (const prefix of ["broll:", "caption:"]) {
    for (const order of [2, 3, 1, 2, 0, 3]) {
      await selectClipBy(page, prefix, order);
      await expect(page.getByRole("region", { name: "편집 항목" })).toContainText(SCENES[order]);
    }
  }
});

test("장면을 고르면 자르기 단추가 열린다", async ({ page }) => {
  await openEditor(page, readFixture().noNarration);
  await selectClipBy(page, "caption:", 2);
  await expect(page.getByRole("button", { name: /^빼기/ })).toBeEnabled();
});

test("캡션 3번째에서 속도를 바꾸면 서버에서는 셋째 장면만 바뀐다", async ({ page, request }) => {
  const { noNarration } = readFixture();
  await openEditor(page, noNarration);
  const rates = async () => Object.fromEntries((await serverSession(request, noNarration)).segments.map((segment) => [segment.segment_id, segment.ripple_playback_rate ?? null]));
  const before = await rates();
  const ids = Object.keys(before);
  expect(ids).toHaveLength(4);
  await selectClipBy(page, "caption:", 2);
  const speed = page.getByRole("region", { name: "편집 항목" }).getByRole("spinbutton", { name: "속도", exact: true });
  try {
    await speed.fill("1.5");
    await speed.press("Enter");
    await expect.poll(async () => (await rates())[ids[2]]).toBe(1.5);
    expect(await rates()).toEqual({ ...before, [ids[2]]: 1.5 });
  } finally {
    if ((await rates())[ids[2]] !== before[ids[2]]) {
      await page.getByRole("button", { name: "실행 취소" }).click();
      await expect.poll(rates).toEqual(before);
    }
  }
});
