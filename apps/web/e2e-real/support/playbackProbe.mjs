// 편집기 재생을 진짜 Chromium에서 프레임으로 재는 도우미 (2026-10-09 계획 P Task 0).
// 옛 진단 스크립트(.superpowers/sdd/playback-diagnosis-2026-10-09/scripts/measure-playback.mjs)의 INIT·measureOne을 옮겨 다듬었다.
// 쓰는 순서: installPlaybackProbe(page) → withLongPreview(page) → openEditor → measurePlayback(또는 startPlayback+collect) → assertSmooth.
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { expect } from "@playwright/test";

export const LONG_PREVIEW_MP4 = path.resolve("test-results/long-preview.mp4");

/** 제품 미리보기와 같은 모양(720x404, 30fps, 기본 keyint, B프레임 없음, faststart)의 30초 영상. 이미 있으면 그대로 쓴다. */
export function ensureLongPreviewMp4(mp4Path = LONG_PREVIEW_MP4) {
  if (existsSync(mp4Path)) return mp4Path;
  mkdirSync(path.dirname(mp4Path), { recursive: true });
  try {
    execFileSync("ffmpeg", [
      "-y", "-v", "error",
      "-f", "lavfi", "-i", "testsrc2=s=720x404:r=30:d=30",
      "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
      "-c:v", "libx264", "-bf", "0", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-movflags", "+faststart",
      mp4Path,
    ], { timeout: 120_000 });
  } catch (error) {
    throw new Error(`ffmpeg로 시험 영상을 만들지 못했습니다(ffmpeg가 있어야 합니다): ${error.message}`);
  }
  return mp4Path;
}

/** 매니페스트의 exact_preview를 0~30초 `current`로 얹고, 영상은 범위 요청(206)까지 내준다. 나머지는 진짜 백엔드. */
export async function withLongPreview(page, mp4Path = LONG_PREVIEW_MP4) {
  const buffer = readFileSync(mp4Path);
  await page.route("**/playback-manifest", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.exact_preview = {
      status: "current", url: "/__e2e/long-preview.mp4", source_session_id: body.session_id,
      source_session_revision: body.session_revision, generation_id: "e2e", timeline_start_sec: 0,
      timeline_end_sec: body.output.duration_sec, artifact_revision: body.session_revision,
    };
    await route.fulfill({ response, json: body });
  });
  await page.route("**/__e2e/long-preview.mp4", (route) => {
    const size = buffer.length;
    const range = /^bytes=(\d*)-(\d*)$/.exec(route.request().headers()["range"] ?? "");
    if (!range) {
      return route.fulfill({ status: 200, headers: { "accept-ranges": "bytes", "content-type": "video/mp4", "content-length": String(size) }, body: buffer });
    }
    const a = range[1] === "" ? Math.max(0, size - Number(range[2])) : Number(range[1]);
    const b = range[1] === "" || range[2] === "" ? size - 1 : Math.min(Number(range[2]), size - 1);
    return route.fulfill({
      status: 206,
      headers: { "content-range": `bytes ${a}-${b}/${size}`, "accept-ranges": "bytes", "content-type": "video/mp4", "content-length": String(b - a + 1) },
      body: buffer.subarray(a, b + 1),
    });
  });
}

const INIT = `(() => {
  const S = window.__pb = { setterCalls: [], commits: 0, longtasks: [], harness: false };
  window.__REACT_DEVTOOLS_GLOBAL_HOOK__ = { isDisabled: false, supportsFiber: true, renderers: new Map(), inject() { return 1; }, onCommitFiberRoot() { S.commits++; }, onCommitFiberUnmount() {}, onPostCommitFiberRoot() {}, onScheduleFiberRoot() {}, checkDCE() {}, on() {}, off() {}, emit() {}, sub() { return () => {}; } };
  const desc = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, "currentTime");
  Object.defineProperty(HTMLMediaElement.prototype, "currentTime", { configurable: true, get() { return desc.get.call(this); }, set(v) {
    S.setterCalls.push({ t: performance.now(), to: v, from: desc.get.call(this), paused: this.paused, harness: S.harness });
    desc.set.call(this, v);
  } });
  try { new PerformanceObserver((list) => { for (const e of list.getEntries()) S.longtasks.push({ t: e.startTime, d: e.duration }); }).observe({ type: "longtask", buffered: false }); } catch {}
})();`;

/** page.goto 전에 부른다. */
export function installPlaybackProbe(page) {
  return page.addInitScript(INIT);
}

/** 정렬 후 floor(0.95·n) 번째. 빈 배열이면 0. */
export function p95(values) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor(0.95 * sorted.length))];
}

export function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  if (!sorted.length) return 0;
  const mid = sorted.length >> 1;
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

const gaps = (times) => times.slice(1).map((t, i) => t - times[i]);

/**
 * startSec로 옮기고(harness 표시 아래 — "앱이 재생 중 스스로 옮긴 횟수"에 안 섞인다) 카운터를 비운 뒤 재생을 시작한다.
 * start: "space"(초점을 풀고 스페이스) | "button"(재생 또는 일시정지 단추).
 */
export async function startPlayback(page, { startSec = 0, start = "button" } = {}) {
  await page.evaluate(async (target) => {
    const video = document.querySelector("video");
    window.__pb.harness = true;
    video.pause();
    await new Promise((resolve) => {
      const done = () => { video.removeEventListener("seeked", done); resolve(); };
      video.addEventListener("seeked", done);
      video.currentTime = target;
      setTimeout(resolve, 4000);
    });
    window.__pb.harness = false;
  }, startSec);
  await page.waitForTimeout(1500);
  await page.evaluate(() => {
    const S = window.__pb;
    const video = document.querySelector("video");
    S.setterCalls = []; S.commits = 0; S.longtasks = []; S.rvfc = []; S.phChanges = []; S.roChanges = [];
    const quality = video.getVideoPlaybackQuality();
    S.q0 = { total: quality.totalVideoFrames, dropped: quality.droppedVideoFrames };
    S.running = true; S.startedAt = performance.now();
    const tick = (now, meta) => { S.rvfc.push({ now, mt: meta.mediaTime }); if (S.running) video.requestVideoFrameCallback(tick); };
    video.requestVideoFrameCallback(tick);
    // 재생 머리·시간 글자는 rAF마다 값이 바뀐 시각을 모은다(100ms 표본으로는 100ms 아래를 못 잰다).
    let lastLeft = null; let lastText = null;
    const raf = () => {
      if (!S.running) return;
      const playhead = document.querySelector("[data-testid='timeline-playhead']");
      const readout = document.querySelector(".vb-preview-stage__playback output");
      const now = performance.now();
      if (playhead) { const left = playhead.getBoundingClientRect().left; if (left !== lastLeft) { S.phChanges.push(now); lastLeft = left; } }
      if (readout) { const text = readout.textContent; if (text !== lastText) { S.roChanges.push(now); lastText = text; } }
      requestAnimationFrame(raf);
    };
    requestAnimationFrame(raf);
  });
  if (start === "space") {
    await page.evaluate(() => document.activeElement?.blur?.());
    await page.keyboard.press("Space");
  } else {
    await page.getByRole("button", { name: "재생 또는 일시정지" }).click();
  }
}

/**
 * startPlayback 뒤 seconds초를 기다렸다가 거두고 일시정지한다.
 * @returns {Promise<PlaybackSample>} PlaybackSample = { appSeeksWhilePlaying, mediaTimeBackwardSteps, effectiveRate, rvfcFps, rvfcGapMax,
 *   decodedPerPresented, longTasksOver100, playheadGapP95, readoutGapP95, reactCommitsPerSec, stillPlayingAtEnd }
 */
export async function collect(page, { seconds }) {
  await page.waitForTimeout(seconds * 1000);
  const raw = await page.evaluate(() => {
    const S = window.__pb;
    const video = document.querySelector("video");
    S.running = false;
    const quality = video.getVideoPlaybackQuality();
    const wallSec = (performance.now() - S.startedAt) / 1000;
    const out = {
      setterCalls: S.setterCalls, commits: S.commits, longtasks: S.longtasks, rvfc: S.rvfc, phChanges: S.phChanges, roChanges: S.roChanges,
      decoded: quality.totalVideoFrames - S.q0.total, wallSec, paused: video.paused,
    };
    S.harness = true; video.pause(); S.harness = false;
    return out;
  });
  const rv = raw.rvfc;
  const durSec = rv.length > 1 ? (rv[rv.length - 1].now - rv[0].now) / 1000 : 0;
  const mediaAdvance = rv.length > 1 ? rv[rv.length - 1].mt - rv[0].mt : 0;
  return {
    appSeeksWhilePlaying: raw.setterCalls.filter((c) => !c.paused && !c.harness).length,
    mediaTimeBackwardSteps: rv.slice(1).filter((x, i) => x.mt < rv[i].mt - 0.001).length,
    effectiveRate: durSec ? mediaAdvance / durSec : 0,
    rvfcFps: durSec ? rv.length / durSec : 0,
    rvfcGapMax: Math.max(0, ...gaps(rv.map((x) => x.now))),
    decodedPerPresented: rv.length ? raw.decoded / rv.length : 0,
    longTasksOver100: raw.longtasks.filter((l) => l.d > 100).length,
    playheadGapP95: p95(gaps(raw.phChanges)),
    readoutGapP95: p95(gaps(raw.roChanges)),
    reactCommitsPerSec: raw.commits / raw.wallSec,
    stillPlayingAtEnd: !raw.paused,
  };
}

export async function measurePlayback(page, { startSec = 0, seconds = 10, start = "button" } = {}) {
  await startPlayback(page, { startSec, start });
  return collect(page, { seconds });
}

/** 고친 뒤 모양의 판정(계획 P 임계값): 결정적인 값은 매회, 나머지는 여러 번 잰 것의 중앙값으로. */
export function assertSmooth(runs) {
  for (const run of runs) {
    expect(run.appSeeksWhilePlaying).toBe(0);
    expect(run.mediaTimeBackwardSteps).toBe(0);
    expect(run.longTasksOver100).toBeLessThanOrEqual(1);
  }
  expect(median(runs.map((r) => r.effectiveRate))).toBeGreaterThanOrEqual(0.93);
  expect(median(runs.map((r) => r.decodedPerPresented))).toBeLessThanOrEqual(1.3);
  expect(median(runs.map((r) => r.rvfcFps))).toBeGreaterThanOrEqual(25);
  expect(median(runs.map((r) => r.rvfcGapMax))).toBeLessThanOrEqual(250);
  expect(median(runs.map((r) => r.reactCommitsPerSec))).toBeLessThanOrEqual(12);
}
