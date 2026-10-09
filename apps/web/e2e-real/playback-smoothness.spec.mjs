import { expect, test } from "@playwright/test";
import { openEditor, readFixture } from "./support/realFlow.mjs";
import { installPlaybackProbe, measurePlayback, median, withLongPreview, ensureLongPreviewMp4 } from "./support/playbackProbe.mjs";

// 2026-10-09 실측(.superpowers/sdd/playback-diagnosis-2026-10-09.md): 재생 중 미리보기가 자기를 20초에 67~74번 되감아
// 실제 0.62~0.70배로 흔들리며 돌았다. 맨 <video>는 같은 파일을 30fps·1.00배로 튼다.
test.describe.configure({ mode: "serial" });
test.beforeAll(() => ensureLongPreviewMp4());

test("1배로 틀면 미리보기가 스스로 되감지 않고 실제 속도로 흐른다", async ({ page }) => {
  test.setTimeout(240_000);
  await installPlaybackProbe(page);
  await withLongPreview(page);
  await openEditor(page, readFixture().playback);
  await expect(page.getByLabel("편집본 미리보기")).toBeVisible({ timeout: 90_000 });
  const runs = [];
  for (const startSec of [0, 8, 17]) runs.push(await measurePlayback(page, { startSec, seconds: 10, start: "button" }));
  console.log("PLAYBACK_1X", JSON.stringify(runs));
  for (const run of runs) {
    expect(run.appSeeksWhilePlaying).toBe(0);          // 실측 고장 67~74/20초, 고친 뒤 0
    expect(run.mediaTimeBackwardSteps).toBe(0);         // 실측 고장 52~59/20초
  }
  expect(median(runs.map((r) => r.effectiveRate))).toBeGreaterThanOrEqual(0.93);   // 고장 0.62~0.70, 정상 1.00
  expect(median(runs.map((r) => r.decodedPerPresented))).toBeLessThanOrEqual(1.3); // 고장 3.1~6.6, 정상 1.0
  expect(median(runs.map((r) => r.rvfcFps))).toBeGreaterThanOrEqual(25);           // 정상 30.0(바쁜 기계 여유)
  expect(median(runs.map((r) => r.rvfcGapMax))).toBeLessThanOrEqual(250);          // 눈에 보이는 멈춤 없음(정상 50)
  for (const run of runs) expect(run.longTasksOver100).toBeLessThanOrEqual(1);      // 실측 0
  expect(median(runs.map((r) => r.reactCommitsPerSec))).toBeLessThanOrEqual(12);   // 실측 7 — 프레임마다 그리기로 바뀌면 잡는다
  // 재생 머리·시간 글자는 timeupdate(≈4Hz)가 아니라 화면 프레임마다 흐른다(계획 P Task 2).
  expect(median(runs.map((r) => r.playheadGapP95))).toBeLessThanOrEqual(100);      // 실측 고장 p50 300·p95 400
  expect(median(runs.map((r) => r.readoutGapP95))).toBeLessThanOrEqual(150);       // 0.1초 글자라 100ms 단위로 바뀐다(프레임 어림 포함 실측 107~118, 고장 276~280)
});
