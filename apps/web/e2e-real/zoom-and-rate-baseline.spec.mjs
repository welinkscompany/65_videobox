import { expect, test } from "@playwright/test";
import { openEditor, readFixture } from "./support/realFlow.mjs";
import { collect, ensureLongPreviewMp4, installPlaybackProbe, measurePlayback, median, startPlayback, withLongPreview } from "./support/playbackProbe.mjs";

// 2026-10-09 계획 P2 Task 0: 기준 측정 + 첫 RED.
//  1) 타임라인 처음 배율 -- 길이 7.75·30·120·600초 x 1440x900·1280x720 (ZOOM_BASELINE 출력).
//  2) 빠르기 상한 -- 같은 30초 미리보기를 1·2·3·4·6·8배로 틀어 본다 (RATE_CEILING 출력).
//  3) RED 두 개 -- "처음 창 >= 20초"(Task 2)와 "8배까지 된다"(Task 1, 이제 GREEN).
// 문턱(RED)은 Task 1·2가 GREEN으로 만든다. 측정 시험은 출력만 하고 통과한다.
// covers: zoom-initial-window, rate-4x
// (serial 아님: 앞 RED가 실패해도 뒤 RED가 건너뛰어지지 않게. workers=1이라 어차피 차례로 돈다.)
test.beforeAll(() => ensureLongPreviewMp4());

const VIEWPORTS = [{ width: 1440, height: 900 }, { width: 1280, height: 720 }];
const DURATIONS = [7.75, 30, 120, 600];

async function stretchTo(page, durationSec) {
  await page.route("**/playback-manifest", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.output.duration_sec = durationSec;
    await route.fulfill({ response, json: body });
  });
}

const measureZoom = (page) => page.evaluate(() => {
  const root = document.querySelector("[data-pixels-per-second]");
  const pps = Number(root.getAttribute("data-pixels-per-second"));
  const viewport = document.querySelector(".vb-timeline-lanes-viewport").getBoundingClientRect();
  const majors = [...document.querySelectorAll(".vb-ruler-major")].map((el) => {
    const r = el.getBoundingClientRect();
    return { label: el.textContent, left: r.left, right: r.right, end: el.classList.contains("vb-ruler-major--end") };
  });
  const anchor = (m) => (m.end ? m.right : m.left);
  const gaps = majors.slice(1).map((m, i) => Math.round((anchor(m) - anchor(majors[i])) * 10) / 10);
  return {
    pps, viewportPx: Math.round(viewport.width * 10) / 10, visibleSec: Math.round((viewport.width / pps) * 100) / 100,
    rulerLabels: majors.slice(0, 3).map((m) => m.label), rulerMajorCount: majors.length, rulerGapPx: gaps.slice(0, 3),
    zoomOutDisabled: document.querySelector("[aria-label='타임라인 축소']")?.disabled,
    zoomInDisabled: document.querySelector("[aria-label='타임라인 확대']")?.disabled,
  };
});

for (const viewport of VIEWPORTS) {
  for (const durationSec of DURATIONS) {
    test(`배율 기준: ${durationSec}초 @${viewport.width}x${viewport.height}`, async ({ page }) => {
      await stretchTo(page, durationSec);
      await openEditor(page, readFixture().clean, viewport);
      await page.waitForTimeout(500);
      const m = await measureZoom(page);
      console.log("ZOOM_BASELINE", JSON.stringify({ durationSec, viewport: `${viewport.width}x${viewport.height}`, ...m }));
      expect(m.pps).toBeGreaterThan(0);
    });
  }
}

const RATES = [1, 2, 3, 4, 6, 8];
const STARTS = [0, 5];

async function audioProbe(page, rate) {
  return page.evaluate(async (r) => {
    const video = document.querySelector("video");
    const out = { rate: r, mutedAttr: video.muted, volume: video.volume, playbackRateNow: video.playbackRate };
    try {
      window.__audio ??= new WeakMap();
      if (!window.__audio.has(video)) {
        const ctx = new AudioContext();
        const src = ctx.createMediaElementSource(video);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 2048;
        src.connect(analyser); analyser.connect(ctx.destination);
        window.__audio.set(video, { ctx, analyser });
      }
      const { ctx, analyser } = window.__audio.get(video);
      await ctx.resume();
      const buf = new Float32Array(analyser.fftSize);
      let peak = 0; let rmsMax = 0;
      for (let i = 0; i < 10; i += 1) {
        analyser.getFloatTimeDomainData(buf);
        let sum = 0; for (const v of buf) { sum += v * v; peak = Math.max(peak, Math.abs(v)); }
        rmsMax = Math.max(rmsMax, Math.sqrt(sum / buf.length));
        await new Promise((res) => setTimeout(res, 50));
      }
      out.rmsMax = rmsMax; out.peak = peak; out.ctxState = ctx.state;
    } catch (error) { out.audioError = String(error); }
    out.decodedBytes = video.webkitAudioDecodedByteCount ?? null;
    return out;
  }, rate);
}

// 4배로 끝까지 틀면 어떻게 되나 -- 앱이 끝에서 스스로 되감지 않는지(계획 Task 1이 지킬 것)의 현재 값.
test("빠르기 기준: 4배로 끝에 닿을 때 (RATE_END)", async ({ page }) => {
  test.setTimeout(120_000);
  await installPlaybackProbe(page);
  await withLongPreview(page);
  await openEditor(page, readFixture().playback);
  await expect(page.getByLabel("편집본 미리보기")).toBeVisible({ timeout: 90_000 });
  await page.waitForFunction(() => document.querySelector("video")?.readyState >= 2);
  await page.evaluate((r) => { window.__pb.harness = true; document.querySelector("video").playbackRate = r; window.__pb.harness = false; }, 4);
  await startPlayback(page, { startSec: 24, start: "button" });
  await page.waitForTimeout(4000);
  const end = await page.evaluate(() => {
    const v = document.querySelector("video");
    return { paused: v.paused, ended: v.ended, t: v.currentTime, rate: v.playbackRate, appSeeks: window.__pb.setterCalls.filter((c) => !c.harness).length, lastSeeks: window.__pb.setterCalls.filter((c) => !c.harness).slice(0, 3).map((c) => ({ to: c.to, from: c.from, paused: c.paused })) };
  });
  console.log("RATE_END", JSON.stringify(end));
});

test("빠르기 상한 기준: 1·2·3·4·6·8배 (RATE_CEILING)", async ({ page }) => {
  test.setTimeout(600_000);
  await installPlaybackProbe(page);
  await withLongPreview(page);
  await openEditor(page, readFixture().playback);
  await expect(page.getByLabel("편집본 미리보기")).toBeVisible({ timeout: 90_000 });
  await page.waitForFunction(() => document.querySelector("video")?.readyState >= 2);
  const table = [];
  for (const rate of RATES) {
    const runs = [];
    for (const startSec of STARTS) {
      await page.evaluate((r) => { window.__pb.harness = true; document.querySelector("video").playbackRate = r; window.__pb.harness = false; }, rate);
      await startPlayback(page, { startSec, start: "button" });
      // 끝(30초)에 닿으면 재생이 멈추므로 소리 재기(≈0.6초) 몫까지 빼고 28초 안에서 끝나게 한다.
      const seconds = Math.min(8, Math.max(1.5, (27 - startSec) / rate - 0.6));
      await page.evaluate(() => { const v = document.querySelector("video"); window.__pb.rate0 = v.playbackRate; window.__pb.dec0 = v.webkitAudioDecodedByteCount ?? null; });
      const audio = await audioProbe(page, rate);
      const sample = await collect(page, { seconds });
      const extra = await page.evaluate(() => {
        const v = document.querySelector("video"); const q = v.getVideoPlaybackQuality();
        return { rateAfter: v.playbackRate, dec1: v.webkitAudioDecodedByteCount ?? null, dropped: q.droppedVideoFrames - window.__pb.q0.dropped, total: q.totalVideoFrames - window.__pb.q0.total, endTime: v.currentTime, rate0: window.__pb.rate0, dec0: window.__pb.dec0 };
      });
      runs.push({ startSec, seconds, ...sample, audio, ...extra });
    }
    table.push({ rate, runs });
  }
  console.log("RATE_CEILING", JSON.stringify(table));
  expect(table.length).toBe(RATES.length);
  for (const run of table.find((row) => row.rate === 1).runs) expect(run.effectiveRate).toBeGreaterThanOrEqual(0.95);
});

// ---- RED ----------------------------------------------------------------------------------------
// Task 2 전에는 7.75·30초 프로젝트가 영상 전체를 칸에 맞춰 처음 창이 20초보다 훨씬 좁다.
test("RED: 짧은 프로젝트의 처음 타임라인 창은 적어도 20초를 보여 준다", async ({ page }) => {
  await stretchTo(page, 7.75);
  await openEditor(page, readFixture().clean, { width: 1440, height: 900 });
  await page.waitForTimeout(500);
  const m = await measureZoom(page);
  console.log("RED_ZOOM", JSON.stringify(m));
  expect(m.visibleSec).toBeGreaterThanOrEqual(20);
});

// Task 1 (A): L 키로 4배·8배까지 올리면 실제로 그 속도로 흐르고, 재생 머리 시계도 따라간다.
test("8배까지 된다: L 키로 올려 4배·8배에서 실효 ±5%, 앱 탐색 0, 머리 시계 매끈", async ({ page }) => {
  test.setTimeout(240_000);
  await installPlaybackProbe(page);
  await withLongPreview(page);
  await openEditor(page, readFixture().playback);
  await expect(page.getByLabel("편집본 미리보기")).toBeVisible({ timeout: 90_000 });
  await page.waitForFunction(() => document.querySelector("video")?.readyState >= 2);
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  const rateNow = () => page.evaluate(() => document.querySelector("video").playbackRate);
  const result = {};
  // 멈춘 첫 L은 재생만 한다(1배) -> 1.5·2·3·4.
  for (let i = 0; i < 5; i += 1) await page.keyboard.press("l");
  expect(await rateNow()).toBe(4);
  result[4] = await measurePlayback(page, { startSec: 0, seconds: 5 });
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  for (let i = 0; i < 6; i += 1) await page.keyboard.press("l"); // 멈춘 첫 L은 재생만 -> 6 -> 8 -> 8(끝에서 멈춘다)
  expect(await rateNow()).toBe(8);
  result[8] = await measurePlayback(page, { startSec: 0, seconds: 3 });
  console.log("RATE_L_KEYS", JSON.stringify(result));
  for (const rate of [4, 8]) {
    const run = result[rate];
    expect(run.effectiveRate / rate).toBeGreaterThan(0.95);
    expect(run.effectiveRate / rate).toBeLessThan(1.05);
    expect(run.appSeeksWhilePlaying).toBe(0);
    expect(run.mediaTimeBackwardSteps).toBe(0);
    expect(run.playheadGapP95).toBeLessThanOrEqual(100);
  }
});
