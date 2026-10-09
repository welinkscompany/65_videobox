import { expect, test } from "@playwright/test";
import { openEditor, readFixture, serverManifest, serverSession } from "./support/realFlow.mjs";
import { ensureLongPreviewMp4, installPlaybackProbe, withLongPreview } from "./support/playbackProbe.mjs";

// 2026-10-09 계획 P2 -- 캡컷 PC 단축키를 진짜 백엔드·진짜 Chromium으로 밟는 시험. 편집 키는 `shortcuts` 고정 프로젝트에서만 누른다
// (재생 측정용 `playback`을 바꾸지 않는다). 아래 `// covers: <id>`는 `editorShortcuts.test.ts`의 덮개 시험이 읽는다 --
// 단축키 표의 모든 줄이 여기(또는 playback-smoothness.spec.mjs)에서 진짜 브라우저로 밟혀야 한다.
// 고정 프로젝트: 내레이션 네 장면(0~7.5~15~22.5~30초) + 장면 3(15~22.5초)에 영상 배치 하나. 세션 개정 번호·장면 경계를 서버에서 읽어 단언하고,
// 편집 키마다 Ctrl+Z로 원래대로 돌려 놓는다(serial -- 앞 시험이 남긴 상태가 뒤 시험을 흔들지 않게).
test.describe.configure({ mode: "serial" });
test.beforeAll(() => ensureLongPreviewMp4());
// 편집 뒤 미리보기 매니페스트를 다시 받는 중에 시험이 끝나면 `route.fetch: Test ended`가 시험 탓으로 잡힌다 -- 끝낼 때 길을 풀고 간다.
test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "ignoreErrors" }); });

const SCENE_2 = /^내레이션 2번째 장면, \d+초부터$/;
const SCENE_3 = /^내레이션 3번째 장면, \d+초부터$/;
const BROLL_1 = /^영상 1번째 장면, \d+초부터$/;
const sceneOf = (session, id) => session.segments.find((segment) => segment.segment_id === id);
const brollOf = async (request, fixture) => {
  const manifest = await serverManifest(request, fixture);
  const clip = manifest.tracks.find((track) => track.track_type === "broll").clips.find((item) => item.segment_id === "scene-3");
  return { start: clip.start_sec, end: clip.end_sec, revision: manifest.session_revision };
};
const bounds = (session) => session.segments.map((segment) => [segment.segment_id, segment.start_sec, segment.end_sec, segment.cut_action]);

const readout = async (page) => Number(await page.locator('output[aria-label="재생 위치"]').getAttribute("data-seconds"));
const videoTime = (page) => page.evaluate(() => document.querySelector("video").currentTime);
const keyNotice = (page) => page.getByRole("status", { name: "자르기 안내" });
const writes = (page) => {
  const seen = [];
  page.on("request", (req) => {
    if (!["GET", "HEAD", "OPTIONS"].includes(req.method()) && req.url().includes("/editing-sessions/")) seen.push(`${req.method()} ${new URL(req.url()).pathname}`);
  });
  return seen;
};

/** 저장이 끝날 때까지 기다린다 -- 사람이 하듯 상태 줄이 "저장하고 있어요"를 벗어나길 본다. */
const settled = (page) => expect.poll(async () => {
  const text = await page.getByRole("status", { name: "편집 저장 상태" }).allTextContents();
  return text.some((line) => /저장하고 있어요|불러오고 있어요/.test(line));
}, { timeout: 15_000 }).toBe(false);
const undo = async (page) => {
  await settled(page);
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("Control+Z");
};

/** ArrowRight를 n번. 누름마다 재생 위치가 움직일 때까지 기다린다(아래 "연타" 시험이 이유를 잰다). */
async function stepFrames(page, count) {
  for (let i = 0; i < count; i += 1) {
    const before = await videoTime(page);
    for (let attempt = 0; attempt < 3; attempt += 1) {
      await page.keyboard.press("ArrowRight");
      const moved = await page.waitForFunction((t) => document.querySelector("video").currentTime > t + 0.01, before, { timeout: 1000 }).then(() => true, () => false);
      if (moved) break;
    }
  }
}

/** 장면을 고르고(누르면 그 장면 시작으로 간다) 본문으로 초점을 옮긴다. */
async function pick(page, name) {
  await page.getByRole("button", { name }).click();
  await page.locator("body").click({ position: { x: 5, y: 5 } });
}

async function openShortcuts(page, { viewport } = {}) {
  const { shortcuts } = readFixture();
  await withLongPreview(page);
  await openEditor(page, shortcuts, viewport);
  await page.waitForSelector("video", { timeout: 15_000 });
  return shortcuts;
}

// covers: trim-left
test("Q 키는 고른 장면의 재생 위치 왼쪽을 잘라 내고(빈자리는 그대로), Ctrl+Z로 정확히 돌아온다", async ({ page, request }) => {
  const fx = await openShortcuts(page);
  const before = await serverSession(request, fx);
  await pick(page, SCENE_2);
  await stepFrames(page, 30);                       // 7.5초 + 30프레임 = 8.5초
  await expect.poll(() => videoTime(page), { timeout: 5000 }).toBeCloseTo(8.5, 1);
  await page.keyboard.press("q");
  await expect.poll(async () => sceneOf(await serverSession(request, fx), "scene-2").start_sec, { timeout: 8000 }).toBeCloseTo(8.5, 2);
  const after = await serverSession(request, fx);
  expect(sceneOf(after, "scene-2").end_sec).toBeCloseTo(before.segments.find((s) => s.segment_id === "scene-2").end_sec, 6);
  // 다른 장면은 한 프레임도 안 움직인다(빼기 정책: 빈자리를 남기고 뒤를 당기지 않는다).
  expect(bounds(after).filter(([id]) => id !== "scene-2")).toEqual(bounds(before).filter(([id]) => id !== "scene-2"));
  await undo(page);
  await expect.poll(async () => sceneOf(await serverSession(request, fx), "scene-2").start_sec, { timeout: 8000 }).toBeCloseTo(7.5, 6);
  expect(bounds(await serverSession(request, fx))).toEqual(bounds(before));
});

// covers: trim-right
test("W 키는 고른 장면의 재생 위치 오른쪽을 잘라 내고, Ctrl+Z로 정확히 돌아온다", async ({ page, request }) => {
  const fx = await openShortcuts(page);
  const before = await serverSession(request, fx);
  await pick(page, SCENE_2);
  await stepFrames(page, 30);
  await expect.poll(() => videoTime(page), { timeout: 5000 }).toBeCloseTo(8.5, 1);
  await page.keyboard.press("w");
  await expect.poll(async () => sceneOf(await serverSession(request, fx), "scene-2").end_sec, { timeout: 8000 }).toBeCloseTo(8.5, 2);
  const after = await serverSession(request, fx);
  expect(sceneOf(after, "scene-2").start_sec).toBeCloseTo(7.5, 6);
  expect(bounds(after).filter(([id]) => id !== "scene-2")).toEqual(bounds(before).filter(([id]) => id !== "scene-2"));
  await undo(page);
  await expect.poll(async () => sceneOf(await serverSession(request, fx), "scene-2").end_sec, { timeout: 8000 }).toBeCloseTo(15, 6);
  expect(bounds(await serverSession(request, fx))).toEqual(bounds(before));
});

test("재생 위치가 고른 장면 밖이면 Q·W는 아무것도 바꾸지 않고 이유를 한 줄로 알린다", async ({ page, request }) => {
  const fx = await openShortcuts(page);
  const before = await serverSession(request, fx);
  const seen = writes(page);
  await pick(page, SCENE_2);                         // 7.5초 -- 장면 시작 바로 위(반 프레임 안)
  await page.keyboard.press("q");
  await expect(keyNotice(page)).toHaveText("재생 위치를 고른 장면 안으로 옮겨 주세요.");
  await page.keyboard.press("Home");                 // 0초 -- 아예 밖
  await page.keyboard.press("w");
  await expect(keyNotice(page)).toHaveText("재생 위치를 고른 장면 안으로 옮겨 주세요.");
  await page.waitForTimeout(500);
  expect(await serverSession(request, fx)).toEqual(before);
  expect(seen).toEqual([]);
  await expect(keyNotice(page)).toBeHidden({ timeout: 6000 });   // 4초 뒤 사라진다
});

test("트랙을 잠그면 Q는 자르지 않고 '잠긴 트랙이에요.'라고 알린다", async ({ page, request }) => {
  const fx = await openShortcuts(page);
  const before = await serverSession(request, fx);
  const seen = writes(page);
  await pick(page, SCENE_2);
  await stepFrames(page, 30);
  await page.getByRole("button", { name: "내레이션 트랙 잠금" }).click();
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("q");
  await expect(keyNotice(page)).toHaveText("잠긴 트랙이에요.");
  await page.waitForTimeout(500);
  expect(await serverSession(request, fx)).toEqual(before);
  expect(seen).toEqual([]);
});

test("고른 장면이 없으면 Q·W는 '장면을 먼저 골라 주세요.'라고 알리고 서버는 그대로다", async ({ page, request }) => {
  const fx = await openShortcuts(page);
  const before = await serverSession(request, fx);
  const seen = writes(page);
  // 처음 열면 0초의 장면이 이미 골라져 있다 -- 재생 위치를 장면 사이 빈 곳(영상 끝 뒤)으로 옮겨 고른 것을 풀어 본다.
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("End");
  await page.keyboard.press("q");
  await expect(keyNotice(page)).toBeVisible();
  const text = (await keyNotice(page).textContent()) ?? "";
  console.log("NO_SELECTION_NOTICE", text);
  expect(["장면을 먼저 골라 주세요.", "재생 위치를 고른 장면 안으로 옮겨 주세요."]).toContain(text);
  await page.waitForTimeout(500);
  expect(await serverSession(request, fx)).toEqual(before);
  expect(seen).toEqual([]);
});

test("영상 배치 하나를 고르면 Q·W는 그 배치를 자르고, 되돌리기로 돌아온다", async ({ page, request }) => {
  const fx = await openShortcuts(page);
  const before = await brollOf(request, fx);
  const sessionBefore = await serverSession(request, fx);
  expect([before.start, before.end]).toEqual([15, 22.5]);
  await pick(page, BROLL_1);                          // 배치를 고르고 15초로
  await stepFrames(page, 30);                         // 16초
  await expect.poll(() => videoTime(page), { timeout: 5000 }).toBeCloseTo(16, 1);
  await page.keyboard.press("q");
  await expect.poll(async () => (await brollOf(request, fx)).start, { timeout: 8000 }).toBeCloseTo(16, 2);
  expect((await brollOf(request, fx)).end).toBeCloseTo(22.5, 4);
  // 영상 배치만 잘렸다 -- 내레이션 장면 경계는 그대로.
  expect(bounds(await serverSession(request, fx)).map(([id, s, e]) => [id, s, e])).toEqual(bounds(sessionBefore).map(([id, s, e]) => [id, s, e]));
  await undo(page);
  await expect.poll(async () => (await brollOf(request, fx)).start, { timeout: 8000 }).toBeCloseTo(15, 4);
  await settled(page);
  await page.keyboard.press("w");
  await expect.poll(async () => (await brollOf(request, fx)).end, { timeout: 8000 }).toBeCloseTo(16, 2);
  expect((await brollOf(request, fx)).start).toBeCloseTo(15, 4);
  await undo(page);
  await expect.poll(async () => (await brollOf(request, fx)).end, { timeout: 8000 }).toBeCloseTo(22.5, 4);
});

test("장면이 최소 길이(0.2초)보다 짧아지는 자르기는 거절되고, 한국어로 알리고, 아무것도 안 바뀐다", async ({ page, request }) => {
  const fx = await openShortcuts(page);
  const before = await serverSession(request, fx);
  await pick(page, SCENE_2);
  await stepFrames(page, 3);                          // 7.6초 -- 시작에서 0.1초
  await expect.poll(() => videoTime(page), { timeout: 5000 }).toBeCloseTo(7.6, 1);
  await page.keyboard.press("w");                     // 7.5~7.6 (0.1초)
  const status = page.getByRole("status", { name: /편집 저장 상태|자르기 안내/ });
  await expect(status.first()).toBeVisible({ timeout: 8000 });
  await settled(page);
  const messages = (await status.allTextContents()).join(" | ");
  console.log("MIN_LENGTH_MESSAGE", messages);
  expect(await serverSession(request, fx)).toEqual(before);
  expect(messages).toMatch(/[가-힣]/);
  expect(messages).not.toMatch(/revision|provider|runtime|job|pipeline|model|Error|undefined/i);
});

// covers: split
// covers: undo
// covers: redo
test("Ctrl+B로 나누고, Ctrl+Z·Ctrl+Shift+Z·Ctrl+Y로 되돌리고 다시 한다", async ({ page, request }) => {
  const fx = await openShortcuts(page);
  const before = await serverSession(request, fx);
  expect(before.segments).toHaveLength(4);
  await pick(page, SCENE_2);
  await stepFrames(page, 30);
  await expect.poll(() => videoTime(page), { timeout: 5000 }).toBeCloseTo(8.5, 1);
  const count = async () => (await serverSession(request, fx)).segments.length;
  await page.keyboard.press("Control+b");
  await expect.poll(count, { timeout: 8000 }).toBe(5);
  const split = await serverSession(request, fx);
  const ranges = split.segments.map((s) => [Number(s.start_sec.toFixed(2)), Number(s.end_sec.toFixed(2))]).sort((a, b) => a[0] - b[0]);
  expect(ranges).toEqual([[0, 7.5], [7.5, 8.5], [8.5, 15], [15, 22.5], [22.5, 30]]);
  expect(split.segments.some((s) => s.segment_id === "scene-2" && Math.abs(s.start_sec - 7.5) < 1e-6 && Math.abs(s.end_sec - 8.5) < 0.02)).toBe(true);
  await undo(page);                                    // Ctrl+Z
  await expect.poll(count, { timeout: 8000 }).toBe(4);
  await settled(page);
  await page.keyboard.press("Control+Shift+Z");        // 다시 하기
  await expect.poll(count, { timeout: 8000 }).toBe(5);
  await settled(page);
  await page.keyboard.press("Control+z");
  await expect.poll(count, { timeout: 8000 }).toBe(4);
  await settled(page);
  await page.keyboard.press("Control+y");              // 다시 하기 (다른 키)
  await expect.poll(count, { timeout: 8000 }).toBe(5);
  await settled(page);
  await page.keyboard.press("Control+z");
  await expect.poll(count, { timeout: 8000 }).toBe(4);
  expect(bounds(await serverSession(request, fx))).toEqual(bounds(before));
});

// covers: delete
test("Delete는 고른 장면을 빼되 뒤 장면을 당기지 않고, Ctrl+Z로 되살린다", async ({ page, request }) => {
  const fx = await openShortcuts(page);
  const before = await serverSession(request, fx);
  await pick(page, SCENE_3);
  await page.keyboard.press("Delete");
  await expect.poll(async () => sceneOf(await serverSession(request, fx), "scene-3").cut_action, { timeout: 8000 }).toBe("remove");
  const after = await serverSession(request, fx);
  expect(sceneOf(after, "scene-4").start_sec).toBeCloseTo(22.5, 6);   // leave_gap -- 뒤 장면은 제자리
  expect(sceneOf(after, "scene-4").end_sec).toBeCloseTo(30, 6);
  await undo(page);
  await expect.poll(async () => sceneOf(await serverSession(request, fx), "scene-3").cut_action, { timeout: 8000 }).toBe("keep");
  expect(bounds(await serverSession(request, fx))).toEqual(bounds(before));
});

// covers: prev-cut
// covers: next-cut
// covers: go-start
// covers: go-end
test("End·위아래 화살표·Home은 재생 위치만 옮기고 서버는 아무것도 쓰지 않는다", async ({ page, request }) => {
  const fx = await openShortcuts(page);
  const before = await serverSession(request, fx);
  const seen = writes(page);
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  const expectAt = async (seconds) => {
    await expect.poll(() => readout(page), { timeout: 5000 }).toBeCloseTo(seconds, 1);
    await expect.poll(() => videoTime(page), { timeout: 5000 }).toBeCloseTo(seconds, 1);
  };
  await page.keyboard.press("End");        await expectAt(30);
  await page.keyboard.press("ArrowUp");    await expectAt(22.5);
  await page.keyboard.press("ArrowUp");    await expectAt(15);
  await page.keyboard.press("ArrowDown");  await expectAt(22.5);
  await page.keyboard.press("ArrowDown");  await expectAt(30);
  await page.keyboard.press("ArrowDown");  await expectAt(30);   // 더 뒤가 없으면 그대로
  await page.keyboard.press("Home");       await expectAt(0);
  await page.keyboard.press("ArrowUp");    await expectAt(0);
  await page.keyboard.press("ArrowDown");  await expectAt(7.5);
  const after = await serverSession(request, fx);
  expect(after.session_revision).toBe(before.session_revision);
  expect(after).toEqual(before);
  expect(seen).toEqual([]);
});

// covers: zoom-in
// covers: zoom-out
// covers: zoom-fit
test("Ctrl+=·Ctrl+-는 1.25배씩 늘고 줄며, Shift+Z와 Ctrl+0은 영상 전체를 칸에 맞추고, 서버는 안 건드린다", async ({ page, request }) => {
  const fx = await openShortcuts(page);
  const before = await serverSession(request, fx);
  const seen = writes(page);
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  const region = page.getByRole("region", { name: "타임라인" });
  const pps = async () => Number(await region.getAttribute("data-pixels-per-second"));
  const trackWidth = async () => (await page.getByRole("group", { name: "타임라인 클립" }).boundingBox()).width;
  const fit = await pps();
  expect(fit).toBeCloseTo((await trackWidth()) / 30, 0);          // 처음 창 = 영상 전체(30초)
  await page.keyboard.press("Control+=");
  await expect.poll(pps).toBeCloseTo(fit * 1.25, 1);
  await page.keyboard.press("Control+-");
  await expect.poll(pps).toBeCloseTo(fit, 1);
  await page.keyboard.press("Control+=");
  await page.keyboard.press("Control+=");
  await expect.poll(pps).toBeCloseTo(fit * 1.5625, 1);
  await page.keyboard.press("Shift+Z");
  await expect.poll(pps).toBeCloseTo(fit, 1);
  await page.keyboard.press("Control+=");
  await expect.poll(pps).toBeCloseTo(fit * 1.25, 1);
  await page.keyboard.press("Control+0");
  await expect.poll(pps).toBeCloseTo(fit, 1);
  expect(Math.abs((await pps()) * 30 - (await trackWidth()))).toBeLessThan(2);   // 맞춤 = 칸 폭 ÷ 30
  await page.keyboard.press("z");                                  // 맨 z는 아무 일도 안 한다
  expect(await pps()).toBeCloseTo(fit, 1);
  expect(await serverSession(request, fx)).toEqual(before);
  expect(seen).toEqual([]);
});

test("유진 입력칸에 q·w·Delete를 쳐도 장면은 안 잘리고 입력칸에는 글자가 들어간다", async ({ page, request }) => {
  const fx = await openShortcuts(page);
  const before = await serverSession(request, fx);
  const seen = writes(page);
  await pick(page, SCENE_2);
  await stepFrames(page, 30);
  const box = page.locator("#vb-eugene-request");
  if (!(await box.isVisible())) await page.getByRole("button", { name: "유진", exact: true }).click();
  await expect(box).toBeVisible();
  await box.focus();
  await page.keyboard.type("qw");
  await page.keyboard.press("Delete");
  await page.keyboard.press("Home");                   // 글칸 안의 Home은 글칸 몫이다 -- 재생 위치도 그대로
  await expect(box).toHaveValue("qw");
  await page.waitForTimeout(500);
  expect(await serverSession(request, fx)).toEqual(before);
  expect(seen).toEqual([]);
  expect(await videoTime(page)).toBeCloseTo(8.5, 1);
});

test("ArrowRight를 간격 없이 30번 눌러도 정확히 30프레임 가고, 그 뒤 재생 위치를 혼자 흔들지 않는다 (키 연타 결함)", async ({ page }) => {
  // 2026-10-09 계획 P2 Task 4 실측: 고치기 전에는 30번 중 10~14번이 씹히고 미리보기가 두 값 사이를 초당 230번 오갔다.
  const { shortcuts } = readFixture();
  await installPlaybackProbe(page);
  await withLongPreview(page);
  await openEditor(page, shortcuts);
  await page.waitForSelector("video", { timeout: 15_000 });
  await pick(page, SCENE_2);
  await page.waitForTimeout(800);
  const t0 = await videoTime(page);
  await page.evaluate(() => { window.__pb.setterCalls.length = 0; });
  for (let i = 0; i < 30; i += 1) await page.keyboard.press("ArrowRight");   // 일부러 기다리지 않는다
  await page.waitForTimeout(1500);
  const settledTime = await videoTime(page);
  const writesAfterBurst = await page.evaluate(() => window.__pb.setterCalls.length);
  expect(settledTime - t0).toBeCloseTo(1.0, 1);                 // 30프레임 = 1초, 한 프레임 오차도 안 난다
  expect(await readout(page)).toBeCloseTo(settledTime, 1);      // 타임라인 숫자와 미리보기가 같은 곳을 가리킨다
  expect(writesAfterBurst).toBeLessThanOrEqual(40);              // 누름 30 + 여유. 고치기 전엔 300 이상
  await page.evaluate(() => { window.__pb.setterCalls.length = 0; });
  await page.waitForTimeout(2000);
  expect(await page.evaluate(() => window.__pb.setterCalls.length)).toBe(0);   // 혼자 계속 흔들지 않는다
});
