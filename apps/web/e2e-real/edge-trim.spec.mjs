import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";
import { openEditor, readFixture, serverManifest } from "./support/realFlow.mjs";

// 점검 §3-8 / 스파이크 H-c: 자르기 손잡이는 클립 양 끝, 몸통을 끌면 옮기기. 진짜 마우스·진짜 백엔드로 잰다.
const SHOT_DIR = path.resolve("../../.superpowers/sdd/2026-10-08-editor-core-repair-h.ko/task-8-shots");
const SCENE = "scene-2";
const CLIP = /^영상 2번째 장면, \d+초부터$/;
const CLIP_GROUP = /^영상 2번째 장면, \d+초부터 클립$/;
const clipName = (n, suffix = "") => new RegExp(`^영상 ${n}번째 장면, \\d+초부터${suffix}$`);
const handle = (page, suffix) => page.getByRole("button", { name: clipName(2, ` ${suffix}`) });

// 고정 프로젝트 장면 2의 영상 배치(초). 서버 매니페스트에서 읽는다 -- 화면 값이 아니라 저장된 값이다.
const brollOf = async (request, fixture) => {
  const manifest = await serverManifest(request, fixture);
  const clip = manifest.tracks.find((track) => track.track_type === "broll").clips.find((item) => item.segment_id === SCENE);
  return { start: clip.start_sec, end: clip.end_sec, revision: manifest.session_revision };
};

async function center(locator) {
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  return { x: box.x + box.width / 2, y: box.y + box.height / 2, box };
}

async function drag(page, from, dx, { up = true } = {}) {
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(from.x + dx / 2, from.y, { steps: 4 });
  await page.mouse.move(from.x + dx, from.y, { steps: 4 });
  if (up) await page.mouse.up();
}

// 저장 중에는 손잡이가 잠기고 되돌리기도 저장이 끝난 뒤에야 쌓인다 -- 사람이 하듯 끝나길 기다린다.
const settled = (page) => expect(handle(page, "끝 자르기")).toBeEnabled({ timeout: 10_000 });
const undo = async (page) => {
  await settled(page);
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("Control+Z");
};

test("가장자리 손잡이는 자르고 몸통은 옮기고 되돌려진다", async ({ page, request }) => {
  mkdirSync(SHOT_DIR, { recursive: true });
  const { clean } = readFixture();
  await openEditor(page, clean);
  await page.getByRole("button", { name: CLIP }).click();
  await expect(handle(page, "끝 자르기")).toBeVisible();

  // 손잡이 자리: 시작은 클립 왼쪽 끝, 끝은 오른쪽 끝, 몸통은 그 사이 -- 잡는 폭 14px.
  const clipBox = await page.getByRole("button", { name: CLIP }).boundingBox();
  const startBox = (await center(handle(page, "시작 자르기"))).box;
  const endBox = (await center(handle(page, "끝 자르기"))).box;
  const moveBox = (await center(handle(page, "이동"))).box;
  expect(Math.abs(startBox.x - clipBox.x)).toBeLessThanOrEqual(1);
  expect(Math.abs(endBox.x + endBox.width - (clipBox.x + clipBox.width))).toBeLessThanOrEqual(1);
  expect(startBox.width).toBeCloseTo(14, 0);
  expect(endBox.width).toBeCloseTo(14, 0);
  expect(Math.abs(moveBox.x - (startBox.x + startBox.width))).toBeLessThanOrEqual(1);
  const cursors = await page.evaluate(() => ({
    handle: getComputedStyle(document.querySelector(".vb-trim-handle")).cursor,
    body: getComputedStyle(document.querySelector(".vb-clip-body-drag")).cursor,
    strip: getComputedStyle(document.querySelector(".vb-trim-handle"), "::before").width,
  }));
  console.log("CURSORS", JSON.stringify(cursors));
  expect(cursors).toEqual({ handle: "ew-resize", body: "grab", strip: "8px" });
  await page.screenshot({ path: path.join(SHOT_DIR, "edge-handles-1440.png") });

  // 0) 클립을 고르면 재생 머리가 그 시작 모서리로 온다 -- 그 밑에 깔려도 시작 손잡이가 잡혀야 한다.
  const before = await brollOf(request, clean);
  const playheadX = await page.getByTestId("timeline-playhead").evaluate((el) => el.getBoundingClientRect().x);
  const startHandle = await center(handle(page, "시작 자르기"));
  console.log("PLAYHEAD_X", playheadX, "START_HANDLE_CENTER", startHandle.x);
  const hit = await page.evaluate(([x, y]) => document.elementFromPoint(x, y)?.getAttribute("aria-label"), [startHandle.x, startHandle.y]);
  expect(hit).toMatch(/시작 자르기$/);
  await drag(page, startHandle, 20);
  await expect.poll(async () => (await brollOf(request, clean)).start, { timeout: 3000 }).toBeGreaterThan(before.start + 0.02);
  expect((await brollOf(request, clean)).end).toBeCloseTo(before.end, 2);
  await undo(page);
  await expect.poll(async () => (await brollOf(request, clean)).start, { timeout: 5000 }).toBeCloseTo(before.start, 2);
  await settled(page);

  // 1) 끝 손잡이를 왼쪽으로 20px 끌면 끝이 줄어든다.
  const end = await center(handle(page, "끝 자르기"));
  await drag(page, end, -20);
  await expect.poll(async () => (await brollOf(request, clean)).end, { timeout: 3000 }).toBeLessThan(before.end - 0.02);
  const trimmed = await brollOf(request, clean);
  console.log("TRIM", JSON.stringify({ before, trimmed }));
  expect(trimmed.start).toBeCloseTo(before.start, 2); // 시작은 프레임 반올림만큼만 다르다
  await undo(page);
  await expect.poll(async () => (await brollOf(request, clean)).end, { timeout: 5000 }).toBeCloseTo(before.end, 4);

  // 2) 몸통을 오른쪽으로 15px 끌면 통째로 옮겨진다(길이는 그대로).
  // 선택된 클립은 몸통이 이동 단추에 덮여 있다 -- 선택이 풀렸을 때만 다시 고른다.
  if (!(await handle(page, "이동").isVisible())) await page.getByRole("button", { name: CLIP }).click();
  await settled(page);
  const body = await center(handle(page, "이동"));
  body.x = body.box.x + body.box.width * 0.3; // 재생 머리가 중앙에 있을 수 있어 왼쪽 쪽을 잡는다
  await drag(page, body, 15);
  await expect.poll(async () => (await brollOf(request, clean)).start, { timeout: 3000 }).toBeGreaterThan(before.start + 0.02);
  const moved = await brollOf(request, clean);
  console.log("MOVE", JSON.stringify({ before, moved }));
  expect(moved.end - moved.start).toBeCloseTo(before.end - before.start, 1);
  await undo(page);
  await expect.poll(async () => (await brollOf(request, clean)).start, { timeout: 5000 }).toBeCloseTo(before.start, 4);
  expect((await brollOf(request, clean)).end).toBeCloseTo(before.end, 4);
});

test("짧은 클릭·Esc·창 밖 놓기는 저장하지 않고 클릭은 클립을 고른다", async ({ page, request }) => {
  const { clean } = readFixture();
  await openEditor(page, clean);
  await page.getByRole("button", { name: CLIP }).click();
  await expect(handle(page, "이동")).toBeVisible();
  await settled(page);
  const before = await brollOf(request, clean);

  // 몸통 위 짧은 클릭(2px 흔들림)은 저장하지 않고 선택도 그대로다.
  const body = await center(handle(page, "이동"));
  body.x = body.box.x + body.box.width * 0.3;
  await page.mouse.move(body.x, body.y);
  await page.mouse.down();
  await page.mouse.move(body.x + 2, body.y);
  await page.mouse.up();
  await page.waitForTimeout(600);
  expect(await brollOf(request, clean)).toEqual(before);
  await expect(page.getByRole("button", { name: CLIP })).toHaveAttribute("aria-pressed", "true");

  // 위의 짧은 클릭이 재생 머리를 그 자리로 옮겼다(클릭 = 그 자리로 seek, 기존 동작) -- 머리와 안 겹치는 곳을 잡는다.
  body.x = body.box.x + body.box.width * 0.7;
  // 끌던 도중 Esc: 화면에서도 원래 자리로 돌아가고 서버는 그대로.
  await drag(page, body, 40, { up: false });
  // 끄는 중 화면 값은 렌더가 따라온 뒤에 바뀐다(느린 기계에서는 한 박자 늦다) -- 기다려서 본다.
  await expect.poll(async () => Number(await page.getByRole("group", { name: CLIP_GROUP }).getAttribute("data-start-seconds")), { timeout: 3000 }).toBeGreaterThan(before.start + 0.05);
  await page.keyboard.press("Escape");
  await page.mouse.up();
  await page.waitForTimeout(600);
  expect(await brollOf(request, clean)).toEqual(before);
  const after = await page.getByRole("group", { name: CLIP_GROUP }).getAttribute("data-start-seconds");
  expect(Number(after)).toBeCloseTo(before.start, 2);

  // 창 밖으로 끌고 나가 놓아도 끌던 값으로 한 번만 저장된다(캡처 덕분에 pointerup이 트랙으로 온다).
  const end = await center(handle(page, "끝 자르기"));
  await page.mouse.move(end.x, end.y);
  await page.mouse.down();
  await page.mouse.move(end.x - 20, end.y, { steps: 4 });
  await page.mouse.move(end.x - 20, -50, { steps: 4 });
  await page.mouse.up();
  await expect.poll(async () => (await brollOf(request, clean)).end, { timeout: 3000 }).toBeLessThan(before.end - 0.02);
  expect((await brollOf(request, clean)).revision).toBe(before.revision + 1);
  await undo(page);
  await expect.poll(async () => (await brollOf(request, clean)).end, { timeout: 5000 }).toBeCloseTo(before.end, 4);
});

test("좁은 클립은 손잡이만 그리고 넓은 클립은 가장자리·몸통이 겹치지 않는다 (스크린샷)", async ({ page }) => {
  mkdirSync(SHOT_DIR, { recursive: true });
  const { clean } = readFixture();
  for (const viewport of [{ width: 1440, height: 900 }, { width: 375, height: 812 }]) {
    await openEditor(page, clean, viewport);
    for (const n of [2, 4]) {
      // 좁은 화면은 타임라인 창이 좁아 4번째 클립이 창 밖(그려지지 않음)일 수 있다 -- 그려진 것만 본다.
      if ((await page.getByRole("button", { name: clipName(n) }).count()) === 0) continue;
      await page.getByRole("button", { name: clipName(n) }).click();
      await page.getByRole("button", { name: clipName(n, " 이동") }).scrollIntoViewIfNeeded();
      const m = await page.evaluate((index) => {
        const clip = [...document.querySelectorAll('[data-testid="timeline-clip"]')].find((c) => new RegExp(`^영상 ${index}번째`).test(c.getAttribute("aria-label")));
        const get = (suffix) => [...clip.querySelectorAll("button")].find((b) => b.getAttribute("aria-label").endsWith(suffix));
        const rect = (el) => { const r = el.getBoundingClientRect(); return { x: r.x, w: r.width }; };
        const c = clip.getBoundingClientRect();
        return { clipW: c.width, title: clip.getAttribute("title"), start: rect(get("시작 자르기")), end: rect(get("끝 자르기")), move: get("이동").className, moveRect: rect(get("이동")) };
      }, n);
      console.log("SHOT", viewport.width, n, JSON.stringify(m));
      if (m.clipW < 42) {
        expect(m.move).toContain("sr-only");
        expect(m.title).toBe("확대하면 끌어서 옮길 수 있어요");
      } else {
        expect(m.move).toContain("vb-clip-body-drag");
        // 손잡이 둘과 몸통은 서로 겹치지 않는다(옆으로 이어 붙는다).
        expect(m.start.x + m.start.w).toBeLessThanOrEqual(m.moveRect.x + 1);
        expect(m.moveRect.x + m.moveRect.w).toBeLessThanOrEqual(m.end.x + 1);
      }
      await page.getByRole("region", { name: "타임라인" }).screenshot({ path: path.join(SHOT_DIR, `selected-${n}-${viewport.width}.png`) });
    }
    await page.screenshot({ path: path.join(SHOT_DIR, `full-${viewport.width}.png`) });
  }
});

test("고른 클립 몸통의 클릭은 옛 고르기 단추처럼 고르고 시작으로 옮기며 Shift는 토글이다", async ({ page }) => {
  const { clean } = readFixture();
  await openEditor(page, clean);
  const playheadSeconds = () => page.getByTestId("timeline-playhead").getAttribute("data-seconds");
  const multi = page.getByText("고른 항목 2개");

  await page.getByRole("button", { name: clipName(2) }).click();
  await expect(handle(page, "이동")).toBeVisible();
  // 영상 3번째를 Shift로 더 고른다 -> 둘이 골라진다.
  await page.getByRole("button", { name: clipName(3) }).click({ modifiers: ["Shift"] });
  await expect(multi).toBeVisible();
  const body3 = page.getByRole("button", { name: clipName(3, " 이동") });
  const box = await body3.boundingBox();
  const at = (f) => ({ x: box.x + box.width * f, y: box.y + box.height / 2 });

  // Shift+클릭(끌기 아님) -> 토글로 빠진다. 끌지 않았으니 서버 값은 그대로(편집 저장 없음).
  const p = at(0.7);
  await page.keyboard.down("Shift");
  await page.mouse.move(p.x, p.y);
  await page.mouse.down();
  await page.mouse.move(p.x + 30, p.y, { steps: 3 });
  await page.mouse.up();
  await page.keyboard.up("Shift");
  await expect(multi).toBeHidden();

  // 다시 둘을 고르고, 그냥 클릭하면 그 클립 하나만 남고 재생 머리는 그 클립 시작으로 간다(옛 고르기 단추와 같다).
  await page.getByRole("button", { name: clipName(2) }).click({ modifiers: ["Shift"] }).catch(() => {});
  await page.getByRole("button", { name: clipName(3) }).click({ modifiers: ["Shift"] });
  await page.waitForTimeout(300);
  const q = at(0.5);
  await page.mouse.move(q.x, q.y);
  await page.mouse.down();
  await page.mouse.move(q.x + 2, q.y); // 2px 흔들림은 클릭이다
  await page.mouse.up();
  await page.waitForTimeout(400);
  await expect(multi).toBeHidden();
  await expect(page.getByRole("button", { name: clipName(3) })).toHaveAttribute("aria-pressed", "true");
  expect(Number(await playheadSeconds())).toBeCloseTo(1.8990646, 1);
});
