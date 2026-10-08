import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";
import { openEditor, readFixture, serverManifest } from "./support/realFlow.mjs";

// 스파이크 H-d: 끌기·자르기 중 옆 클립 가장자리에 붙는다. 진짜 마우스·진짜 백엔드로 서버 값을 잰다.
const SHOT_DIR = path.resolve("../../.superpowers/sdd/2026-10-08-editor-core-repair-h.ko/task-9-shots");
const SCENE = "scene-3";
const NEXT_START_SEC = 2.9281; // 고정 프로젝트 장면 4 시작(장면 3 끝과 같다)
const FPS = 30;
const clipName = (suffix = "") => new RegExp(`^영상 3번째 장면, [0-9]+초부터${suffix}$`);
const handle = (page, suffix) => page.getByRole("button", { name: clipName(` ${suffix}`) });

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

async function dragTo(page, from, dx) {
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(from.x + dx / 2, from.y, { steps: 4 });
  await page.mouse.move(from.x + dx, from.y, { steps: 4 });
}

const settled = (page) => expect(handle(page, "끝 자르기")).toBeEnabled({ timeout: 10_000 });
const guide = (page) => page.locator(".vb-timeline-snap-guide");

async function open(page) {
  const { clean } = readFixture();
  await openEditor(page, clean);
  await page.getByRole("button", { name: clipName() }).click();
  await expect(handle(page, "끝 자르기")).toBeVisible();
  await settled(page);
  return clean;
}

test("끝 손잡이를 장면 4 시작 5px 앞까지 끌면 그 프레임에 붙고 안내선이 서며 명령은 한 번이다", async ({ page, request }) => {
  mkdirSync(SHOT_DIR, { recursive: true });
  const clean = await open(page);
  const before = await brollOf(request, clean);
  expect(before.end).toBeCloseTo(NEXT_START_SEC, 3);

  // 먼저 끝을 40px 안쪽으로 줄여 붙을 거리 밖에서 시작한다(되돌리기로 돌아온다).
  const pps = Number(await page.getByRole("region", { name: "타임라인" }).getAttribute("data-pixels-per-second"));
  const end = await center(handle(page, "끝 자르기"));
  await dragTo(page, end, -40);
  await expect(guide(page)).toHaveCount(0); // 40px는 임계 밖: 안내선 없음
  await page.mouse.up();
  await expect.poll(async () => (await brollOf(request, clean)).revision, { timeout: 5000 }).toBe(before.revision + 1);
  const shortened = await brollOf(request, clean);
  expect(shortened.end).toBeLessThan(before.end - 0.05);
  await settled(page);

  // 이제 끝 손잡이를 오른쪽으로 장면 4 시작 5px 앞까지 끌면 붙는다.
  const end2 = await center(handle(page, "끝 자르기"));
  const gapPx = (NEXT_START_SEC - shortened.end) * pps;
  await dragTo(page, end2, gapPx - 5);
  await expect(guide(page)).toHaveCount(1);
  const geometry = await page.evaluate(() => {
    const track = document.querySelector("[data-timeline-track]").getBoundingClientRect();
    const g = document.querySelector(".vb-timeline-snap-guide").getBoundingClientRect();
    return { guideX: g.x + g.width / 2 - track.x, guideW: g.width, guideTop: g.top - track.top, guideHeight: g.height, trackHeight: track.height };
  });
  console.log("GUIDE", JSON.stringify(geometry), "expected x", (Math.round(NEXT_START_SEC * FPS) / FPS) * pps);
  expect(Math.abs(geometry.guideX - (Math.round(NEXT_START_SEC * FPS) / FPS) * pps)).toBeLessThan(1.5);
  expect(geometry.guideHeight).toBeCloseTo(geometry.trackHeight, 0);
  const colors = await page.evaluate(() => {
    const probe = document.createElement("i");
    probe.style.color = "var(--vb-accent)";
    document.body.append(probe);
    const accent = getComputedStyle(probe).color;
    probe.remove();
    return { guide: getComputedStyle(document.querySelector(".vb-timeline-snap-guide")).backgroundColor, accent };
  });
  console.log("COLORS", JSON.stringify(colors));
  expect(colors.guide).toBe(colors.accent);
  await page.screenshot({ path: path.join(SHOT_DIR, "snap-guide-1440.png") });
  const midDrag = await brollOf(request, clean);
  expect(midDrag.revision).toBe(shortened.revision); // 끄는 동안은 저장하지 않는다
  await page.mouse.up();
  await expect.poll(async () => (await brollOf(request, clean)).revision, { timeout: 5000 }).toBe(shortened.revision + 1);
  const snapped = await brollOf(request, clean);
  console.log("SNAP", JSON.stringify({ before, shortened, snapped }));
  // 서버 값 = 장면 4 시작의 프레임 반올림 값. 붙지 않았다면 5px 앞(= 2.9151초 -> 87프레임 = 2.9)이 저장됐을 것이다.
  expect(snapped.end).toBeCloseTo(Math.round(NEXT_START_SEC * FPS) / FPS, 4);
  expect(snapped.end).not.toBeCloseTo(87 / FPS, 3);
  await expect(guide(page)).toHaveCount(0);

  // 되돌리기 두 번으로 처음 값.
  for (const target of [shortened.end, before.end]) {
    await settled(page);
    await page.locator("body").click({ position: { x: 5, y: 5 } });
    await page.keyboard.press("Control+Z");
    await expect.poll(async () => (await brollOf(request, clean)).end, { timeout: 5000 }).toBeCloseTo(target, 3);
  }
});

test("끌던 중 Esc는 안내선을 걷고 저장하지 않는다 / 임계 밖·처음 자리에서는 안내선이 없다", async ({ page, request }) => {
  const clean = await open(page);
  const pps = Number(await page.getByRole("region", { name: "타임라인" }).getAttribute("data-pixels-per-second"));
  // 처음 끝(= 장면 4 시작)으로는 도로 붙지 않는다: 4px 앞까지 끌어도 안내선이 없다.
  const first = await center(handle(page, "끝 자르기"));
  await page.mouse.move(first.x, first.y);
  await page.mouse.down();
  await page.mouse.move(first.x - 30, first.y, { steps: 4 });
  await page.mouse.move(first.x - 4, first.y, { steps: 4 });
  await expect(guide(page)).toHaveCount(0);
  await page.keyboard.press("Escape");
  await page.mouse.up();
  await page.waitForTimeout(400);

  // 줄여 저장해 둔 뒤(되돌리지 않는다 -- 프로젝트는 시험마다 새로 만들어진다), 4px 앞에서 안내선, Esc로 걷는다.
  const end = await center(handle(page, "끝 자르기"));
  await dragTo(page, end, -(0.6 * pps));
  await expect(guide(page)).toHaveCount(0);
  await page.mouse.up();
  await expect.poll(async () => (await brollOf(request, clean)).end, { timeout: 5000 }).toBeLessThan(2.7);
  await settled(page);
  const before = await brollOf(request, clean);
  const end2 = await center(handle(page, "끝 자르기"));
  await page.mouse.move(end2.x, end2.y);
  await page.mouse.down();
  await page.mouse.move(end2.x + 0.6 * pps - 4, end2.y, { steps: 8 }); // 장면 4 시작 4px 앞
  await expect(guide(page)).toHaveCount(1);
  await page.keyboard.press("Escape");
  await expect(guide(page)).toHaveCount(0);
  await page.mouse.up();
  await page.waitForTimeout(600);
  expect(await brollOf(request, clean)).toEqual(before);
});
