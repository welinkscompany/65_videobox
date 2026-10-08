import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";
import { openEditor, readFixture, serverManifest } from "./support/realFlow.mjs";

// 점검 §3-2 / 계획 H Task 11: 미리보기를 기다리는 동안 무거운 세션을 다시 읽지 않고,
// 요청이 겹치지 않고, 끝나면 멈추고, 기다리는 동안 앞 화면이 남는다. 진짜 백엔드로 잰다.
const OUT_DIR = path.resolve("../../.superpowers/sdd/2026-10-08-editor-core-repair-h.ko/task-11-shots");
const CLIP = /^영상 2번째 장면, \d+초부터$/;

const kindOf = (url) => {
  const { pathname } = new URL(url);
  if (/\/exact-previews\/[^/]+$/.test(pathname)) return "status";
  if (/\/playback-manifest$/.test(pathname)) return "manifest";
  if (/\/editing-sessions\/[^/]+$/.test(pathname)) return "session";
  return null;
};

// 실패 원인 수집: 미리보기 관련 응답을 전부 모아 두었다가, 시험이 실패하면 서버가 준 이유(error_message)와
// 서버가 지금 말하는 상태를 한꺼번에 찍는다.
let diag = [];
test.beforeEach(async ({ page }) => {
  diag = [];
  page.on("response", async (response) => {
    const url = response.url();
    if (!/exact-preview/.test(url) || /\/content/.test(url)) return;
    diag.push({ at: new Date().toISOString().slice(11, 23), method: response.request().method(), path: new URL(url).pathname.split("/").slice(-2).join("/"), status: response.status(), body: (await response.text().catch(() => "")).slice(0, 700) });
  });
});
test.afterEach(async ({ request }, testInfo) => {
  const failedBodies = diag.filter((item) => /"status":\s*"(failed|stale)"/.test(item.body)).map((item) => `${item.at} ${item.method} ${item.path} ${item.body}`);
  console.log("RUN-DIAG", JSON.stringify({ test: testInfo.title, outcome: testInfo.status, failedBodies }));
  if (testInfo.status === testInfo.expectedStatus) return;
  let server = null;
  try { server = (await serverManifest(request, readFixture().clean)).exact_preview; } catch (error) { server = String(error); }
  console.log("FAIL-DIAG", JSON.stringify({ test: testInfo.title, responses: diag, serverExactPreview: server }));
});

const PLAYER = "video[aria-label='편집본 미리보기']";

// 앞 시험이 남긴 상태가 낡았을 수 있다 -- 재생기가 안 보이면 새로 만들기를 눌러 맞춘다.
async function ensurePreview(page) {
  const player = page.locator(PLAYER);
  if (!(await player.isVisible({ timeout: 8000 }).catch(() => false))) {
    const refresh = page.getByRole("button", { name: "미리보기 새로 만들기" });
    if (await refresh.isVisible().catch(() => false)) await refresh.click();
  }
  await expect(player).toBeVisible({ timeout: 120_000 });
}

test("미리보기를 기다리는 동안 가벼운 상태만 묻고, 겹치지 않고, 앞 화면이 남는다", async ({ page, request }) => {
  mkdirSync(OUT_DIR, { recursive: true });
  const { clean } = readFixture();
  await openEditor(page, clean);
  // 열자마자 자동으로 미리보기를 만든다 -- 그것이 끝나 재생기가 보일 때까지 기다린 뒤에 잰다.
  const exactVideo = page.getByLabel("편집본 미리보기").first();
  await ensurePreview(page);

  // 재생기가 그림을 잡을 틈(loadeddata)을 준다.
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: CLIP }).click();
  // 분할은 재생 위치가 고른 장면 안쪽일 때만 된다 -- 장면 2의 한가운데로 옮긴다.
  const manifest = await serverManifest(request, clean);
  const scene = manifest.tracks.find((track) => track.track_type === "narration").clips[1];
  const middle = (scene.start_sec + scene.end_sec) / 2;
  await page.evaluate((t) => { const v = document.querySelector("video[aria-label='편집본 미리보기']"); v.pause(); v.currentTime = t; }, middle);
  await expect(page.getByRole("button", { name: /^분할/ })).toBeEnabled({ timeout: 5000 });

  const log = [];
  const record = async (response) => {
    const request = response.request();
    const kind = kindOf(request.url());
    if (!kind || request.method() !== "GET") return;
    let bytes = 0;
    try { bytes = (await response.body()).length; } catch { /* 본문을 못 읽는 응답은 0으로 센다 */ }
    log.push({ kind, url: request.url(), end: Date.now(), bytes, startedAt: starts.get(request) });
  };
  const starts = new Map();
  page.on("request", (request) => { if (kindOf(request.url()) && request.method() === "GET") starts.set(request, Date.now()); });
  page.on("response", (response) => { void record(response); });

  const markedAt = Date.now();
  await page.keyboard.press("Control+B");

  // 기다리는 동안 앞 화면(그림) 또는 '만드는 중' 문구가 보인 적이 있는지 계속 본다.
  let sawWaitingCopy = false;
  let sawStill = false;
  let finished = false;
  const trail = [];
  const watcher = (async () => {
    while (!finished) {
      const state = await page.evaluate(() => ({
        videos: document.querySelectorAll("video[aria-label='편집본 미리보기']").length,
        still: document.querySelectorAll(".vb-preview-stage__still").length,
        copy: document.querySelector(".vb-preview-stage__empty")?.textContent ?? "",
        status: document.querySelector(".vb-preview-stage__status")?.textContent ?? "",
      }));
      if (state.still > 0) sawStill = true;
      if (/만드는 중이에요/.test(state.copy)) sawWaitingCopy = true;
      const key = JSON.stringify(state);
      if (trail.at(-1)?.key !== key) trail.push({ t: Date.now() - markedAt, key });
      await page.waitForTimeout(100);
    }
  })();

  // 분할 직후 재생기가 사라졌다가(편집 반영) 새 미리보기가 오면 다시 보인다.
  await expect(page.locator("video[aria-label='편집본 미리보기']")).toHaveCount(0, { timeout: 30_000 }).catch(() => {});
  await expect(page.locator("video[aria-label='편집본 미리보기']")).toBeVisible({ timeout: 120_000 });
  const readyAt = Date.now();
  finished = true;
  await watcher;
  await page.waitForTimeout(3000); // 끝난 뒤에는 더 묻지 않는지 본다.
  const quietEnd = Date.now();
  await page.screenshot({ path: path.join(OUT_DIR, "after-ready.png") });

  const during = log.filter((item) => item.end <= quietEnd);
  const count = (kind) => during.filter((item) => item.kind === kind).length;
  const afterReady = during.filter((item) => item.end > readyAt + 1500);

  // 같은 종류 요청이 동시에 둘 이상 진행된 순간이 있는가.
  let maxOverlap = 0;
  for (const kind of ["status", "manifest", "session"]) {
    const spans = during.filter((item) => item.kind === kind);
    for (const a of spans) {
      const concurrent = spans.filter((b) => b.startedAt < a.end && a.startedAt < b.end).length;
      maxOverlap = Math.max(maxOverlap, concurrent);
    }
  }
  const sessionBytes = during.filter((item) => item.kind === "session").map((item) => item.bytes);
  const summary = {
    waitedMs: readyAt - markedAt,
    requests: { session: count("session"), manifest: count("manifest"), status: count("status") },
    maxOverlap,
    sessionBytes,
    requestsAfterReadyPlus1500: afterReady.length,
    sawStill,
    sawWaitingCopy,
    trail,
  };
  writeFileSync(path.join(OUT_DIR, "preview-wait-summary.json"), JSON.stringify(summary, null, 2));
  console.log("PREVIEW-WAIT", JSON.stringify(summary));

  expect(count("session")).toBeLessThanOrEqual(2);
  expect(count("manifest")).toBeLessThanOrEqual(2);
  expect(count("status")).toBeGreaterThanOrEqual(1);
  expect(maxOverlap).toBeLessThanOrEqual(1);
  expect(sawStill || sawWaitingCopy).toBe(true);
  expect(afterReady).toHaveLength(0);

  // 분할은 되돌린다.
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("Control+Z");
  void exactVideo;
  await ensurePreview(page);
});

// 2분 멈춤 재현: 세션·매니페스트 응답이 1.2초 기다리기 간격보다 느리면, 예전에는 뒤 요청이 앞 응답을
// 무효로 만들어 서버가 끝나도 화면이 '만드는 중'에 멈췄다. 그 상황에서 새 미리보기가 제때 뜨는지 본다.
test("응답이 느려도 서버가 끝나면 새 미리보기가 뜬다 (2분 멈춤 재현)", async ({ page, request }) => {
  const { clean } = readFixture();
  await openEditor(page, clean);
  await ensurePreview(page);
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: CLIP }).click();
  const manifest = await serverManifest(request, clean);
  const scene = manifest.tracks.find((track) => track.track_type === "narration").clips[1];
  await page.evaluate((t) => { const v = document.querySelector("video[aria-label='편집본 미리보기']"); v.pause(); v.currentTime = t; }, (scene.start_sec + scene.end_sec) / 2);
  await expect(page.getByRole("button", { name: /^분할/ })).toBeEnabled({ timeout: 5000 });

  // 세션·매니페스트 읽기만 2.5초 늦춘다(0907에서는 14~23초였다). 상태 길과 미리보기 내용은 그대로 둔다.
  await page.route(/\/editing-sessions\/[^/]+(\/playback-manifest)?(\?.*)?$/, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    await new Promise((resolve) => setTimeout(resolve, 2500));
    return route.continue();
  });
  const calls = [];
  page.on("response", async (response) => {
    const url = response.url();
    if (/exact-preview/.test(url) && !/\/content/.test(url)) calls.push(`${response.request().method()} ${new URL(url).pathname.split("/").slice(-2).join("/")} ${response.status()} ${(await response.text().catch(() => "")).slice(0, 260)}`);
  });
  const startedAt = Date.now();
  await page.keyboard.press("Control+B");
  let readyAfterMs = null;
  try {
    await expect(page.locator("video[aria-label='편집본 미리보기']")).toBeVisible({ timeout: 40_000 });
    readyAfterMs = Date.now() - startedAt;
  } catch { /* 40초 안에 안 뜨면 멈춘 것이다 */ }
  console.log("SLOW-RESPONSE-HANG", JSON.stringify({ readyAfterMs, calls }));
  expect(readyAfterMs, "새 미리보기가 40초 안에 떠야 한다").not.toBeNull();
  expect(readyAfterMs).toBeLessThan(15_000);

  await page.unroute(/.*/).catch(() => {});
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("Control+Z");
  await ensurePreview(page);
});

// 같은 재현을 더 센 모양으로: 서버가 긴 영상을 만드는 중인 것처럼 처음 8초 동안 '만드는 중'이라고 답하게 하고
// (세션·매니페스트는 2.5초 늦게), 8초 뒤부터는 진짜 답(완성)을 준다. 예전 기다리기는 뒤 요청이 앞 응답을 계속
// 무효로 만들어 서버가 끝난 뒤에도 영영 '만드는 중'에 멈췄다.
test("서버가 끝난 뒤에도 화면이 '만드는 중'에 멈추지 않는다 (긴 렌더 모의)", async ({ page, request }) => {
  const { clean } = readFixture();
  await openEditor(page, clean);
  await ensurePreview(page);
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: CLIP }).click();
  const manifest = await serverManifest(request, clean);
  const scene = manifest.tracks.find((track) => track.track_type === "narration").clips[1];
  await page.evaluate((t) => { const v = document.querySelector("video[aria-label='편집본 미리보기']"); v.pause(); v.currentTime = t; }, (scene.start_sec + scene.end_sec) / 2);
  await expect(page.getByRole("button", { name: /^분할/ })).toBeEnabled({ timeout: 5000 });

  let faking = false;
  let fakeEndsAt = 0;
  const stillRendering = () => faking && Date.now() < fakeEndsAt;
  await page.route(/\/editing-sessions\/[^/]+(\/playback-manifest)?(\?.*)?$/, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    await new Promise((resolve) => setTimeout(resolve, 2500));
    if (!/playback-manifest/.test(route.request().url()) || !stillRendering()) return route.continue();
    const response = await route.fetch();
    const body = await response.json();
    body.exact_preview = { ...body.exact_preview, status: "running", url: null, generation_id: body.exact_preview.generation_id ?? "fake-generation" };
    return route.fulfill({ response, json: body });
  });
  await page.route(/\/exact-previews\/[^/]+$/, async (route) => {
    if (!stillRendering()) return route.continue();
    const response = await route.fetch();
    const body = await response.json();
    return route.fulfill({ response, json: { ...body, status: "running", content_url: null } });
  });
  const heavy = { session: 0, manifest: 0, status: 0 };
  const sessionBytes = [];
  page.on("request", (request) => {
    const kind = kindOf(request.url());
    if (kind && request.method() === "GET" && stillRendering()) heavy[kind] += 1;
  });
  page.on("response", async (response) => {
    if (kindOf(response.url()) === "session" && response.request().method() === "GET") sessionBytes.push((await response.body().catch(() => Buffer.alloc(0))).length);
  });
  const startedAt = Date.now();
  faking = true;
  fakeEndsAt = startedAt + 8000;
  await page.keyboard.press("Control+B");
  let readyAfterMs = null;
  try {
    await expect(page.locator(PLAYER)).toBeVisible({ timeout: 40_000 });
    readyAfterMs = Date.now() - startedAt;
  } catch { /* 40초 안에 안 뜨면 멈춘 것이다 */ }
  console.log("LONG-RENDER-HANG", JSON.stringify({ fakeRenderMs: 8000, requestsDuring8s: heavy, perSecond: Object.fromEntries(Object.entries(heavy).map(([k, v]) => [k, +(v / 8).toFixed(2)])), sessionBytes, readyAfterMs, lateAfterRenderDoneMs: readyAfterMs === null ? null : readyAfterMs - 8000 }));
  expect(readyAfterMs, "서버가 끝났는데 40초가 지나도 새 미리보기가 안 뜬다").not.toBeNull();

  await page.unroute(/.*/).catch(() => {});
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("Control+Z");
  await ensurePreview(page);
});
