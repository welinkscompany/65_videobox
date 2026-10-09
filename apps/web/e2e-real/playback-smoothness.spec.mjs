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

// 계획 P Task 3 (원인 3·4): 스페이스는 늘 재생/정지이고, 미리보기 밖을 눌러도 0초로 튀지 않는다.
test("스페이스는 영상 그림을 누른 뒤에도·타임라인을 누른 뒤에도 재생/정지이고, 미리보기 밖을 눌러도 위치가 그대로다", async ({ page }) => {
  test.setTimeout(240_000);
  await installPlaybackProbe(page);
  await withLongPreview(page);
  await openEditor(page, readFixture().playback);
  await expect(page.getByLabel("편집본 미리보기")).toBeVisible({ timeout: 90_000 });
  const state = () => page.evaluate(() => { const v = document.querySelector("video"); return { paused: v.paused, t: v.currentTime }; });
  const pauseNow = () => page.evaluate(() => { window.__pb.harness = true; document.querySelector("video").pause(); window.__pb.harness = false; });
  await page.waitForFunction(() => document.querySelector("video")?.readyState >= 2);

  // (가) 아무 데도 초점이 없을 때 / 영상 그림을 누른 뒤 / 타임라인을 누른 뒤 -- 스페이스가 켜고 끈다.
  const starters = [
    ["초점 없음", async () => { await page.evaluate(() => document.activeElement?.blur?.()); }],
    ["영상 그림 클릭 뒤", async () => { await page.getByLabel("편집본 미리보기").click(); }],
    ["타임라인 제목 클릭 뒤", async () => { await page.locator(".vb-editor-workbench__timeline-head h2").click(); }],
  ];
  for (const [name, prepare] of starters) {
    await pauseNow();
    await prepare();
    await page.keyboard.press("Space");
    await page.waitForTimeout(700);
    expect((await state()).paused, `${name}: 스페이스로 재생`).toBe(false);
    await page.keyboard.press("Space");
    await page.waitForTimeout(400);
    expect((await state()).paused, `${name}: 스페이스로 정지`).toBe(true);
  }

  // (나) 재생 단추로 재생 2초 -> 타임라인 제목 클릭 -> 계속 재생·위치 보존(예전: 0초·정지).
  await pauseNow();
  await page.getByRole("button", { name: "재생 또는 일시정지" }).click();
  await page.waitForTimeout(2000);
  const before = await state();
  await page.locator(".vb-editor-workbench__timeline-head h2").click();
  await page.waitForTimeout(600);
  const after = await state();
  expect(after.paused).toBe(false);
  expect(after.t).toBeGreaterThanOrEqual(before.t - 0.3);
  expect(after.t).toBeGreaterThan(2);
  await pauseNow();

  // (다) 음소거 단추에 초점이 있으면 스페이스는 그 단추를 누른다(재생 상태 그대로·음소거가 바뀜).
  const mute = page.getByRole("button", { name: /^음소거/ });
  const pressedBefore = await mute.getAttribute("aria-pressed");
  await mute.focus();
  await page.keyboard.press("Space");
  await page.waitForTimeout(400);
  expect(await mute.getAttribute("aria-pressed")).not.toBe(pressedBefore);
  expect((await state()).paused).toBe(true);
  await mute.click(); // 되돌린다

  // (라) 글 쓰는 칸에서는 띄어쓰기이고 재생이 안 바뀐다.
  const input = page.locator("input[type='text'], input:not([type]), textarea").first();
  if (await input.count()) {
    await input.focus();
    await page.keyboard.press("Space");
    await page.waitForTimeout(400);
    expect((await state()).paused).toBe(true);
  }
});

// 계획 P Task 4: 재생 빠르기 0.25~2배. 보는 속도만 바뀐다(완성 영상은 그대로).
test("재생 빠르기 0.5배·2배가 실제로 그만큼 흐르고, 다시 열어도 기억한다", async ({ page }) => {
  test.setTimeout(420_000);
  await installPlaybackProbe(page);
  await withLongPreview(page);
  await openEditor(page, readFixture().playback);
  await expect(page.getByLabel("편집본 미리보기")).toBeVisible({ timeout: 90_000 });
  await page.waitForFunction(() => document.querySelector("video")?.readyState >= 2);
  const rateSelect = () => page.getByLabel("재생 빠르기");
  const videoState = () => page.evaluate(() => { const v = document.querySelector("video"); return { paused: v.paused, rate: v.playbackRate, defaultRate: v.defaultPlaybackRate }; });
  const blur = () => page.evaluate(() => document.activeElement?.blur?.());
  const pauseNow = () => page.evaluate(() => { window.__pb.harness = true; document.querySelector("video").pause(); window.__pb.harness = false; });

  // 0.5배: 3회 잰다.
  await rateSelect().selectOption("0.5");
  expect((await videoState()).rate).toBe(0.5);
  const half = [];
  for (const startSec of [0, 6, 12]) half.push(await measurePlayback(page, { startSec, seconds: 8, start: "button" }));
  console.log("PLAYBACK_0_5X", JSON.stringify(half));
  for (const run of half) { expect(run.appSeeksWhilePlaying).toBe(0); expect(run.mediaTimeBackwardSteps).toBe(0); }
  expect(median(half.map((r) => r.effectiveRate))).toBeGreaterThanOrEqual(0.45);
  expect(median(half.map((r) => r.effectiveRate))).toBeLessThanOrEqual(0.55);
  expect(median(half.map((r) => r.playheadGapP95))).toBeLessThanOrEqual(100);   // 실측 p95 18~19(절반 속도라 같은 픽셀이 두 배 머물러도 낮다)

  // L: 멈춰 있으면 지금 빠르기(0.5)로 재생만 한다. K: 멈춘다(빠르기 그대로).
  await pauseNow(); await blur();
  await page.keyboard.press("l");
  await page.waitForTimeout(300);
  let state = await videoState();
  expect(state.paused).toBe(false); expect(state.rate).toBe(0.5);
  await page.keyboard.press("k");
  await page.waitForTimeout(200);
  state = await videoState();
  expect(state.paused).toBe(true); expect(state.rate).toBe(0.5);
  expect(await rateSelect().inputValue()).toBe("0.5");

  // 재생 중 L 두 번: 0.5 -> 0.75 -> 1 ... 에서 올라간다. 2배까지 L로 올린다.
  await rateSelect().selectOption("1");
  await pauseNow(); await blur();
  await page.keyboard.press("l");              // 멈춰 있었으니 재생만
  await page.waitForTimeout(300);
  await page.keyboard.press("l");              // 1 -> 1.5
  await page.keyboard.press("l");              // 1.5 -> 2
  await page.waitForTimeout(200);
  state = await videoState();
  expect(state.rate).toBe(2); expect(state.defaultRate).toBe(2);
  expect(await rateSelect().inputValue()).toBe("2");
  await pauseNow();

  // 2배: 3회 잰다.
  const double = [];
  for (const startSec of [0, 6, 12]) double.push(await measurePlayback(page, { startSec, seconds: 8, start: "button" }));
  console.log("PLAYBACK_2X", JSON.stringify(double));
  for (const run of double) { expect(run.appSeeksWhilePlaying).toBe(0); expect(run.mediaTimeBackwardSteps).toBe(0); }
  expect(median(double.map((r) => r.effectiveRate))).toBeGreaterThanOrEqual(1.8);
  expect(median(double.map((r) => r.effectiveRate))).toBeLessThanOrEqual(2.1);
  expect(median(double.map((r) => r.playheadGapP95))).toBeLessThanOrEqual(100);

  // 다시 열어도 기억한다(localStorage).
  await page.reload();
  await expect(page.getByLabel("편집본 미리보기")).toBeVisible({ timeout: 90_000 });
  await page.waitForFunction(() => document.querySelector("video")?.readyState >= 1);
  expect(await rateSelect().inputValue()).toBe("2");
  await expect.poll(async () => (await videoState()).rate).toBe(2);

  // J로 1배까지 내려 놓는다: 2 -> 1.5 -> 1. 화살표는 멈추고 한 프레임.
  await blur();
  await page.keyboard.press("j"); await page.keyboard.press("j");
  expect(await rateSelect().inputValue()).toBe("1");
  await pauseNow(); await blur();
  const t0 = await page.evaluate(() => document.querySelector("video").currentTime);
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(300);
  const t1 = await page.evaluate(() => document.querySelector("video").currentTime);
  expect(t1 - t0).toBeGreaterThan(0.02);
  expect(t1 - t0).toBeLessThan(0.1);
  await page.keyboard.press("ArrowLeft");
  await page.waitForTimeout(300);
  const t2 = await page.evaluate(() => document.querySelector("video").currentTime);
  expect(Math.abs(t2 - t0)).toBeLessThan(0.02);
});
