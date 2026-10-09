import { expect, test } from "@playwright/test";
import { openEditor, readFixture, serverSession } from "./support/realFlow.mjs";
import { ensureLongPreviewMp4, withLongPreview } from "./support/playbackProbe.mjs";

// 2026-10-09 계획 P2 Task 0 -- 캡컷 PC 단축키를 진짜 백엔드로 밟는 시험. 편집 키는 `shortcuts` 고정 프로젝트에서만 누른다
// (재생 측정용 `playback`을 바꾸지 않는다). 아래 `// covers: <id>`는 Task 3의 단축키 표 시험이 읽는다.
// 지금(Task 0)은 Q 키가 묶여 있지 않아 이 시험이 RED다 -- Task 4가 GREEN으로 만든다.
test.describe.configure({ mode: "serial" });
test.beforeAll(() => ensureLongPreviewMp4());

const sceneOf = (session, id) => session.segments.find((segment) => segment.segment_id === id);

// covers: trim-left
test("Q 키는 고른 장면의 재생 위치 왼쪽을 잘라 내고, Ctrl+Z로 돌아온다", async ({ page, request }) => {
  const { shortcuts } = readFixture();
  await withLongPreview(page);
  await openEditor(page, shortcuts);
  const before = sceneOf(await serverSession(request, shortcuts), "scene-2");   // 7.5~15
  await page.getByRole("button", { name: /^내레이션 2번째 장면, \d+초부터$/ }).click();  // 고르고 7.5초로(고정 프로젝트에는 내레이션 클립만 있다)
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  // 30프레임 = 8.5초. 누름마다 재생 위치가 움직일 때까지 기다린다 -- 빠르게 연타하면 일부가 합쳐져 위치가 8.0초 언저리에 머문다(Task 0 실측).
  for (let i = 0; i < 30; i += 1) {
    const t0 = await page.evaluate(() => document.querySelector("video").currentTime);
    // 가끔 한 번은 안 먹는다(실측 3회 중 1회) -- 안 움직였으면 한 번 더 누른다.
    for (let attempt = 0; attempt < 3; attempt += 1) {
      await page.keyboard.press("ArrowRight");
      const moved = await page.waitForFunction((t) => document.querySelector("video").currentTime > t + 0.01, t0, { timeout: 1000 }).then(() => true, () => false);
      if (moved) break;
    }
  }
  // 재생 위치가 정말 8.5초에 있어야 이 시험의 RED가 "Q가 안 묶여서"라고 말할 수 있다.
  await expect.poll(() => page.evaluate(() => document.querySelector("video").currentTime), { timeout: 5000 }).toBeCloseTo(8.5, 1);
  await page.keyboard.press("q");
  await expect.poll(async () => sceneOf(await serverSession(request, shortcuts), "scene-2").start_sec, { timeout: 8000 }).toBeCloseTo(8.5, 2);
  expect(sceneOf(await serverSession(request, shortcuts), "scene-2").end_sec).toBeCloseTo(before.end_sec, 6);
  await page.keyboard.press("Control+Z");
  await expect.poll(async () => sceneOf(await serverSession(request, shortcuts), "scene-2").start_sec, { timeout: 8000 }).toBeCloseTo(before.start_sec, 6);
});
