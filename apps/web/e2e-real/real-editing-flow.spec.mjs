import { readFileSync } from "node:fs";

import { expect, test } from "@playwright/test";
import { editSnapshot, openEditor, readFixture, serverManifest, serverSession, waitSaved } from "./support/realFlow.mjs";
import { ensureLongPreviewMp4, installPlaybackProbe, startPlayback, collect, withLongPreview } from "./support/playbackProbe.mjs";

// 2026-10-08 계획 H Task 17 -- 실사용 편집 흐름 한 줄.
// 이번 점검의 결함(엉뚱한 장면이 잡힘, 트랙 단추가 안 눌림, 되돌리기가 어긋남, 오염된 편집판, 내보내기 창 충돌)은 가짜 API만 밟는 시험을
// 전부 통과했다. 여기서는 진짜 백엔드·고정 시험 프로젝트에서 사람이 하듯 누르고, **서버에 저장된 값**으로 잰다.
// 모든 편집은 되돌리고, 서버 사진(장면 경계·속도·자르기 표시·트랙 상태·오버레이)이 처음과 같은지 비교한다.
test.describe.configure({ mode: "serial" });
test.beforeAll(() => ensureLongPreviewMp4());

const SCENE_3_START = 1.8990646;
const SCENE_4_START = 2.9281;
const clipName = (kind, n, suffix = "") => new RegExp(`^${kind} ${n}번째 장면, \\d+초부터${suffix}$`);

// 고정 시험 프로젝트에는 만들어 둔 미리보기 영상이 없어 재생기가 아예 뜨지 않는다(= 결함의 입력 신호가 없다).
// 매니페스트 응답에만 `미리보기 있음`을 얹고 작은 mp4를 낸다. 세션·타임라인·편집 항목은 진짜 백엔드다.
const TINY_MP4 = Buffer.from(
  /const validTinyPlayableMp4 = Buffer\.from\("([^"]+)"/.exec(readFileSync("e2e/support/fake-api-server.mjs", "utf-8"))[1],
  "base64",
);
async function withPreviewPlayer(page) {
  await page.route("**/playback-manifest", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.exact_preview = {
      status: "current", url: "/__e2e/exact-preview.mp4", source_session_id: body.session_id,
      source_session_revision: body.session_revision, generation_id: "e2e", timeline_start_sec: 0,
      timeline_end_sec: body.output.duration_sec, artifact_revision: body.session_revision,
    };
    await route.fulfill({ response, json: body });
  });
  await page.route("**/__e2e/exact-preview.mp4", (route) => route.fulfill({ status: 200, contentType: "video/mp4", body: TINY_MP4 }));
}

/** 재생기가 `seconds`를 알려 오는 것을 흉내 낸다(점검 §3-1: 경계 바로 앞 값). */
async function playerReports(page, seconds) {
  await page.getByLabel("편집본 미리보기").evaluate((video, value) => {
    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value });
    video.dispatchEvent(new Event("timeupdate"));
  }, seconds);
}
/** 화면 프레임 두 번 -- 쉬는 시간이 아니라 "그릴 것을 다 그렸다"를 기다린다. */
const frames = (page) => page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));

const inspector = (page) => page.getByRole("region", { name: "편집 항목" });
const readout = async (page) => Number(await page.locator('output[aria-label="재생 위치"]').getAttribute("data-seconds"));
const sceneOf = (snapshot, id) => snapshot.segments.find((segment) => segment.segment_id === id);

async function undoOnce(page) {
  await waitSaved(page);
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("Control+Z");
}
/** 되돌린 뒤 서버 사진이 처음과 같아질 때까지 본다. */
const expectRestored = (request, fixture, baseline) => expect.poll(() => editSnapshot(request, fixture), { timeout: 10_000 }).toEqual(baseline);

// player:true는 재생기가 있어야 하는 1·2단계만 쓴다 -- 편집이 쌓인 프로젝트는 미리보기를 새로 만들어야 하므로 재생기가 안 뜨는 것이 설계다.
async function openClean(page, { player = false } = {}) {
  const { clean } = readFixture();
  if (player) await withPreviewPlayer(page);
  await openEditor(page, clean);
  if (player) await expect(page.getByLabel("편집본 미리보기")).toBeVisible({ timeout: 90_000 });
  return clean;
}

const pageErrors = new WeakMap();
test.beforeEach(({ page }) => {
  const errors = [];
  pageErrors.set(page, errors);
  page.on("pageerror", (error) => errors.push(error.message));
});
test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: "ignoreErrors" });
  expect(pageErrors.get(page), "콘솔 pageerror").toEqual([]);
});

let baseline; // 깨끗한 고정 프로젝트의 처음 서버 사진 -- 모든 단계가 이 모양으로 끝나야 한다.

test("1 클릭 -> 그 장면: 영상 3번째를 누르면 재생기가 경계 바로 앞을 알려 와도 편집 항목은 셋째 장면이다", async ({ page, request }) => {
  const clean = await openClean(page, { player: true });
  baseline = await editSnapshot(request, clean);
  expect(baseline.segments.map((segment) => segment.segment_id)).toEqual(["scene-1", "scene-2", "scene-3", "scene-4"]);

  for (const n of [3, 2, 3, 1, 3]) {
    const start = baseline.segments[n - 1].start_sec;
    await page.getByRole("button", { name: clipName("영상", n) }).click();
    await expect.poll(() => readout(page), { timeout: 5000 }).toBeCloseTo(start, 1);   // 누른 자리로 재생 위치가 갔다
    await playerReports(page, Math.max(0, start - 1e-6));                               // 재생기가 백만분의 1초 모자란 값을 올려 보낸다
    await frames(page);
    await expect(inspector(page)).toContainText(`${start.toFixed(2)}–${baseline.segments[n - 1].end_sec.toFixed(2)}초 구간`);
  }
  await expect(inspector(page)).toContainText("1.90–2.93초 구간");
  expect(await editSnapshot(request, clean)).toEqual(baseline);   // 고르기만 했다 -- 서버는 그대로
});

test("2 속도 -> 그 장면만: 속도 2를 넣으면 서버에서 scene-3만 바뀌고 scene-4는 그만큼 당겨지며 알림이 1초 안에 뜬다", async ({ page, request }) => {
  const clean = await openClean(page, { player: true });
  await page.getByRole("button", { name: clipName("영상", 3) }).click();
  await expect.poll(() => readout(page), { timeout: 5000 }).toBeCloseTo(SCENE_3_START, 1);
  await playerReports(page, SCENE_3_START - 1e-6);
  await frames(page);
  await expect(inspector(page)).toContainText("1.90–2.93초 구간");

  const speed = inspector(page).getByRole("spinbutton", { name: "속도", exact: true });
  await speed.fill("2");
  await speed.press("Enter");
  await expect(page.locator("[data-sonner-toast]").first()).toBeVisible({ timeout: 1000 });
  await expect.poll(async () => sceneOf(await editSnapshot(request, clean), "scene-3").ripple_playback_rate, { timeout: 8000 }).toBe(2);

  const after = await editSnapshot(request, clean);
  const half = (SCENE_4_START - SCENE_3_START) / 2;
  console.log("SPEED_AFTER", JSON.stringify(after.segments));
  expect(sceneOf(after, "scene-3").end_sec).toBeCloseTo(SCENE_3_START + half, 4);
  expect(sceneOf(after, "scene-3").start_sec).toBeCloseTo(SCENE_3_START, 6);
  for (const id of ["scene-1", "scene-2"]) expect(sceneOf(after, id), `${id}는 그대로`).toEqual(sceneOf(baseline, id));
  expect(sceneOf(after, "scene-4").ripple_playback_rate).toBe(null);
  expect(sceneOf(after, "scene-4").start_sec).toBeCloseTo(SCENE_4_START - half, 4);   // 속도의 리플(2026-09-04): 뒤 장면이 delta만큼 당겨진다
  expect(sceneOf(after, "scene-4").end_sec - sceneOf(after, "scene-4").start_sec).toBeCloseTo(sceneOf(baseline, "scene-4").end_sec - sceneOf(baseline, "scene-4").start_sec, 4);
});

test("3 되돌리기 -> 원래대로: Control+Z 한 번이면 서버 장면이 속도 전 사진과 같다", async ({ page, request }) => {
  const clean = await openClean(page);
  expect(sceneOf(await editSnapshot(request, clean), "scene-3").ripple_playback_rate).toBe(2);   // 앞 단계가 남긴 편집이 새 화면에도 저장돼 있다
  await undoOnce(page);
  await expectRestored(request, clean, baseline);
});

test("4 트랙 머리를 진짜 마우스로: 영상 트랙 음소거를 누르면 서버 track_states.broll.muted가 켜지고 되돌리면 꺼진다", async ({ page, request }) => {
  const clean = await openClean(page);
  const button = page.getByRole("button", { name: "영상 트랙 음소거", exact: true });
  await button.scrollIntoViewIfNeeded();
  await expect(button).toBeEnabled({ timeout: 10_000 });
  const box = await button.boundingBox();
  const at = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  const hit = await page.evaluate(([x, y]) => document.elementFromPoint(x, y)?.closest("button")?.getAttribute("aria-label") ?? null, [at.x, at.y]);
  expect(hit, "단추 중심에서 실제로 잡히는 단추").toBe("영상 트랙 음소거");

  await page.mouse.click(at.x, at.y);
  await expect.poll(async () => Boolean((await serverManifest(request, clean)).track_states?.broll?.muted), { timeout: 5000 }).toBe(true);
  await expect(button).toHaveAttribute("aria-pressed", "true");

  await undoOnce(page);
  await expect.poll(async () => Boolean((await serverManifest(request, clean)).track_states?.broll?.muted), { timeout: 8000 }).toBe(false);
  await expectRestored(request, clean, baseline);
});

test("5 분할·빼기: 장면 2 가운데에서 Control+B -> 장면 5개, 새 장면 Delete -> 빈 구간 1, Control+Z 두 번 -> 원래 경계", async ({ page, request }) => {
  const clean = await openClean(page);
  await page.getByRole("button", { name: "타임라인 전체 보기" }).click();
  await expect(page.getByText(/빈 구간 0개/)).toBeVisible();

  // 타임라인 눈금을 눌러 재생 위치를 장면 2(1.33–1.90) 가운데 1.6초로 옮긴다.
  const region = page.getByRole("region", { name: "타임라인" });
  const pps = Number(await region.getAttribute("data-pixels-per-second"));
  const track = await page.getByTestId("timeline-track").boundingBox();
  const ruler = await page.getByRole("list", { name: "시간 눈금" }).boundingBox();
  await page.mouse.click(track.x + 1.6 * pps, ruler.y + ruler.height / 2);
  await expect.poll(() => readout(page), { timeout: 5000 }).toBeCloseTo(1.6, 1);
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("Control+b");

  await expect.poll(async () => (await editSnapshot(request, clean)).segments.length, { timeout: 8000 }).toBe(5);
  const split = await editSnapshot(request, clean);
  const ranges = split.segments.map((s) => [Number(s.start_sec.toFixed(2)), Number(s.end_sec.toFixed(2))]).sort((a, b) => a[0] - b[0]);
  console.log("SPLIT_RANGES", JSON.stringify(ranges));
  expect(ranges.slice(0, 2)).toEqual([[0, 1.33], [1.33, 1.6]]);
  expect(ranges.slice(3)).toEqual([[1.9, 2.93], [2.93, 3.75]]);
  expect(ranges[2][0]).toBeCloseTo(1.6, 1);
  const created = split.segments.find((s) => !baseline.segments.some((b) => b.segment_id === s.segment_id));
  expect(created, "새로 생긴 장면").toBeTruthy();
  expect(created.start_sec).toBeCloseTo(1.6, 1);

  // 새 장면(영상 3번째)을 골라 Delete.
  await waitSaved(page);
  await page.getByRole("button", { name: clipName("영상", 3) }).click();
  await expect(inspector(page)).toContainText("1.60–1.90초 구간");
  await page.keyboard.press("Delete");
  await expect.poll(async () => sceneOf(await editSnapshot(request, clean), created.segment_id).cut_action, { timeout: 8000 }).toBe("remove");
  const removed = (await serverManifest(request, clean)).gap_slots.filter((gap) => String(gap.gap_id).startsWith("removed:"));
  expect(removed).toEqual([expect.objectContaining({ gap_id: `removed:${created.segment_id}`, reason: "removed_scene" })]);
  await expect(page.getByText(/빈 구간 1개/)).toBeVisible();

  await undoOnce(page);                                                   // 빼기 취소
  await expect.poll(async () => sceneOf(await editSnapshot(request, clean), created.segment_id).cut_action, { timeout: 8000 }).toBe("keep");
  await undoOnce(page);                                                   // 분할 취소
  await expect.poll(async () => (await editSnapshot(request, clean)).segments.length, { timeout: 8000 }).toBe(4);
  await expectRestored(request, clean, baseline);
  await expect(page.getByText(/빈 구간 0개/)).toBeVisible();
});

test("6 가장자리 끌기: 영상 2번째 끝 손잡이를 끌면 저장되고 되돌리면 원래 자리다", async ({ page, request }) => {
  const clean = await openClean(page);
  await page.getByRole("button", { name: "타임라인 전체 보기" }).click();
  await page.getByRole("button", { name: clipName("영상", 2) }).click();
  const end = page.getByRole("button", { name: clipName("영상", 2, " 끝 자르기") });
  await expect(end).toBeVisible();
  await expect(end).toBeEnabled({ timeout: 10_000 });
  await end.scrollIntoViewIfNeeded();
  const box = await end.boundingBox();
  const from = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  const brollEnd = async () => (await serverManifest(request, clean)).tracks.find((t) => t.track_type === "broll").clips.find((c) => c.segment_id === "scene-2").end_sec;
  const before = await brollEnd();

  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(from.x - 10, from.y, { steps: 4 });
  await page.mouse.move(from.x - 20, from.y, { steps: 4 });
  await page.mouse.up();
  await expect.poll(brollEnd, { timeout: 5000 }).toBeLessThan(before - 0.02);

  await undoOnce(page);
  await expect.poll(brollEnd, { timeout: 8000 }).toBeCloseTo(before, 4);
  await expectRestored(request, clean, baseline);
});

test("7 내보내기 창: 편집을 열 번 넘게 한 프로젝트에서도 열리고 Something went wrong이 없다", async ({ page, request }) => {
  const clean = await openClean(page);
  // 앞 단계가 편집 7번(속도·되돌리기·음소거·되돌리기·분할·빼기·되돌리기 둘·자르기·되돌리기)을 남겼다. 여기서 4번(음소거 두 번과 되돌리기 둘)을 더해 열 번을 넘긴다.
  const mute = page.getByRole("button", { name: "영상 트랙 음소거", exact: true });
  for (let i = 0; i < 2; i += 1) {
    await mute.scrollIntoViewIfNeeded();
    await expect(mute).toBeEnabled({ timeout: 10_000 });
    await mute.click();
    await expect.poll(async () => Boolean((await serverManifest(request, clean)).track_states?.broll?.muted), { timeout: 5000 }).toBe(true);
    await undoOnce(page);
    await expect.poll(async () => Boolean((await serverManifest(request, clean)).track_states?.broll?.muted), { timeout: 8000 }).toBe(false);
  }
  await page.getByRole("button", { name: "내보내기", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("list", { name: "내보낼 곳" }).or(dialog.getByText("내보낼 곳을 확인하고 있어요."))).toBeVisible({ timeout: 10_000 });
  await expect(dialog.getByRole("list", { name: "내보낼 곳" })).toBeVisible({ timeout: 15_000 });
  const text = await page.locator("body").innerText();
  expect(text).not.toContain("Something went wrong");
  expect(text).not.toContain("화면을 그리다 멈췄어요");
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expectRestored(request, clean, baseline);
});

test("8 스페이스·L·확대 기본: 스페이스로 재생/정지, 재생 중 스스로 되감지 않고, L은 빠르기를 올리고, Ctrl+=는 1.25배", async ({ page, request }) => {
  test.setTimeout(240_000);
  const { playback } = readFixture();
  await installPlaybackProbe(page);
  await withLongPreview(page);
  await page.addInitScript(() => { try { if (!window.sessionStorage.getItem("__cleared")) { window.localStorage.clear(); window.sessionStorage.setItem("__cleared", "1"); } } catch { /* ignore */ } });
  const writes = [];
  page.on("request", (req) => { if (!["GET", "HEAD", "OPTIONS"].includes(req.method()) && req.url().includes("/editing-sessions/")) writes.push(`${req.method()} ${new URL(req.url()).pathname}`); });
  await openEditor(page, playback);
  await expect(page.getByLabel("편집본 미리보기")).toBeVisible({ timeout: 90_000 });
  await page.waitForFunction(() => document.querySelector("video")?.readyState >= 2);
  const before = await editSnapshot(request, playback);
  const paused = () => page.evaluate(() => document.querySelector("video").paused);

  // 스페이스: 초점을 풀고 눌러 재생 -> 재생 중 4초 동안 앱이 스스로 되감지 않는다(메아리 되감기 고리) -> 스페이스로 정지.
  await startPlayback(page, { startSec: 0, start: "space" });
  await expect.poll(paused, { timeout: 5000 }).toBe(false);
  const sample = await collect(page, { seconds: 4 });
  console.log("SPACE_PLAYBACK", JSON.stringify({ appSeeks: sample.appSeeksWhilePlaying, backward: sample.mediaTimeBackwardSteps, rate: sample.effectiveRate }));
  expect(sample.appSeeksWhilePlaying).toBe(0);
  expect(sample.mediaTimeBackwardSteps).toBe(0);
  expect(sample.effectiveRate).toBeGreaterThan(0.85);
  await page.evaluate(() => document.activeElement?.blur?.());
  await page.keyboard.press("Space");
  await expect.poll(paused, { timeout: 3000 }).toBe(false);   // collect가 멈춰 둔 것을 스페이스가 다시 켠다
  await page.keyboard.press("Space");
  await expect.poll(paused, { timeout: 3000 }).toBe(true);

  // L: 멈춰 있으면 재생만, 재생 중에 누르면 1 -> 1.5.
  const rate = () => page.evaluate(() => document.querySelector("video").playbackRate);
  expect(await rate()).toBe(1);
  await page.keyboard.press("l");
  await expect.poll(paused, { timeout: 3000 }).toBe(false);
  await page.keyboard.press("l");
  await expect.poll(rate, { timeout: 3000 }).toBe(1.5);
  await expect(page.getByLabel("재생 빠르기")).toHaveValue("1.5");
  await page.keyboard.press("k");
  await expect.poll(paused, { timeout: 3000 }).toBe(true);

  // 확대: Ctrl+=는 1.25배, Ctrl+-는 원래로. 타임라인 배율은 화면 값이지 저장 값이 아니다.
  const region = page.getByRole("region", { name: "타임라인" });
  const pps = async () => Number(await region.getAttribute("data-pixels-per-second"));
  const fit = await pps();
  await page.keyboard.press("Control+=");
  await expect.poll(pps).toBeCloseTo(fit * 1.25, 1);
  await page.keyboard.press("Control+-");
  await expect.poll(pps).toBeCloseTo(fit, 1);

  expect(writes, "재생·확대는 서버에 아무것도 쓰지 않는다").toEqual([]);
  expect(await editSnapshot(request, playback)).toEqual(before);
});

test("9 오염된 고정 프로젝트: 속도와 가장자리 자르기가 저장되고(422 아님) 되돌려진다", async ({ page, request }) => {
  const dirty = readFixture().duplicatedOverlays;
  const base = await editSnapshot(request, dirty);
  const ids = base.overlays.map((overlay) => overlay[0]);
  expect(new Set(ids).size, "오버레이 id가 겹치지 않는다").toBe(ids.length);
  await openEditor(page, dirty);
  await page.getByRole("button", { name: "타임라인 전체 보기" }).click();
  const statuses = [];
  page.on("response", (response) => { if (response.request().method() !== "GET" && response.url().includes("/editing-sessions/")) statuses.push(`${response.request().method()} ${response.status()}`); });

  // (가) 속도: 영상 3번째 장면(timeline_001:001__split_2)만 바뀐다.
  await page.getByRole("button", { name: clipName("영상", 3) }).click();
  await expect(inspector(page)).toContainText("2.50–4.00초 구간");
  const speed = inspector(page).getByRole("spinbutton", { name: "속도", exact: true });
  await speed.fill("2");
  await speed.press("Enter");
  await expect.poll(async () => sceneOf(await editSnapshot(request, dirty), "timeline_001:001__split_2").ripple_playback_rate, { timeout: 8000 }).toBe(2);
  const sped = await editSnapshot(request, dirty);
  for (const id of ["timeline_001:001", "timeline_001:001__split_3"]) expect(sceneOf(sped, id), `${id}는 그대로`).toEqual(sceneOf(base, id));
  await undoOnce(page);
  await expectRestored(request, dirty, base);

  // (나) 가장자리: 영상 2번째 끝 손잡이를 끌어 자르기 -- 오염된 편집판에서도 저장이 200이어야 한다.
  await waitSaved(page);
  await page.getByRole("button", { name: clipName("영상", 2) }).click();
  const end = page.getByRole("button", { name: clipName("영상", 2, " 끝 자르기") });
  await expect(end).toBeEnabled({ timeout: 10_000 });
  await end.scrollIntoViewIfNeeded();
  const box = await end.boundingBox();
  const from = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  const brollEnd = async () => (await serverManifest(request, dirty)).tracks.find((t) => t.track_type === "broll").clips.find((c) => c.segment_id === "timeline_001:001__split_3").end_sec;
  const before = await brollEnd();
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(from.x - 10, from.y, { steps: 4 });
  await page.mouse.move(from.x - 20, from.y, { steps: 4 });
  await page.mouse.up();
  await expect.poll(brollEnd, { timeout: 5000 }).toBeLessThan(before - 0.02);
  await undoOnce(page);
  await expect.poll(brollEnd, { timeout: 8000 }).toBeCloseTo(before, 4);
  await expectRestored(request, dirty, base);

  console.log("DIRTY_WRITES", JSON.stringify(statuses));
  expect(statuses.filter((status) => /^PATCH /.test(status)), "속도·자르기 저장").toEqual(["PATCH 200", "PATCH 200"]);
  expect(statuses.filter((status) => Number(status.split(" ")[1]) >= 400), "쓰기 응답에 오류(422 등)가 없다").toEqual([]);
});
