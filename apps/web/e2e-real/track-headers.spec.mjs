import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";
import { openEditor, readFixture, serverManifest } from "./support/realFlow.mjs";

// 점검 §3-4: 트랙 머리 단추 9개가 마우스로 안 눌렸다(클립 층이 위에 덮고 있었다). 진짜 포인터로 잰다.
const SHOT_DIR = path.resolve("../../.superpowers/sdd/2026-10-08-editor-core-repair-h.ko/task-7-shots");
const HEADER_BUTTONS = [
  "내레이션 트랙 잠금", "내레이션 트랙 음소거",
  "영상 트랙 잠금", "영상 트랙 숨기기", "영상 트랙 음소거",
  "오버레이 트랙 잠금", "오버레이 트랙 숨기기",
  "캡션 트랙 잠금", "캡션 트랙 숨기기",
];

async function center(page, name) {
  const button = page.getByRole("button", { name, exact: true });
  // 타임라인 칸은 낮아서 아래 트랙은 세로로 스크롤해야 보인다 -- 사용자가 하는 그대로 보이는 자리로 옮긴 뒤 잰다.
  await button.scrollIntoViewIfNeeded();
  const box = await button.boundingBox();
  expect(box, name).not.toBeNull();
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

const hitLabel = (page, { x, y }) => page.evaluate(([px, py]) => document.elementFromPoint(px, py)?.closest("button")?.getAttribute("aria-label") ?? null, [x, y]);

test("트랙 머리 단추는 진짜 마우스로 눌리고 서버에 남고 되돌려진다", async ({ page, request }) => {
  const { clean } = readFixture();
  await openEditor(page, clean);
  await expect(page.getByRole("button", { name: "영상 트랙 음소거" })).toBeVisible();

  const report = {};
  for (const name of HEADER_BUTTONS) {
    report[name] = await hitLabel(page, await center(page, name));
  }
  console.log("HIT", JSON.stringify(report));
  for (const name of HEADER_BUTTONS) expect(report[name], `${name} 중심에서 잡히는 단추`).toBe(name);

  const statesOf = async () => (await serverManifest(request, clean)).track_states ?? {};
  // 앞 시험이 남긴 상태에 기대지 않도록 시작값을 읽어 그 반대로 바뀌는지 본다.
  const startMuted = Boolean((await statesOf()).broll?.muted);
  // 저장 중에는 단추가 잠기고(isSaving) 되돌리기도 저장이 끝난 뒤에야 쌓인다 -- 사람이 하듯 끝나길 기다린다.
  const settled = (name) => expect(page.getByRole("button", { name, exact: true })).toBeEnabled({ timeout: 10_000 });
  await settled("영상 트랙 음소거");
  const mute = await center(page, "영상 트랙 음소거");
  await page.mouse.click(mute.x, mute.y);
  await expect.poll(async () => Boolean((await statesOf()).broll?.muted), { timeout: 3000 }).toBe(!startMuted);
  await expect(page.getByRole("button", { name: "영상 트랙 음소거" })).toHaveAttribute("aria-pressed", String(!startMuted));

  await settled("영상 트랙 음소거");
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("Control+Z");
  await expect.poll(async () => Boolean((await statesOf()).broll?.muted), { timeout: 5000 }).toBe(startMuted);

  await settled("오버레이 트랙 숨기기");
  const startHidden = Boolean((await statesOf()).overlay?.hidden);
  const hide = await center(page, "오버레이 트랙 숨기기");
  await page.mouse.click(hide.x, hide.y);
  await expect.poll(async () => Boolean((await statesOf()).overlay?.hidden), { timeout: 3000 }).toBe(!startHidden);
  await settled("오버레이 트랙 숨기기");
  await page.keyboard.press("Control+Z");
  await expect.poll(async () => Boolean((await statesOf()).overlay?.hidden), { timeout: 5000 }).toBe(startHidden);
});

test("머리 칸은 클립 칸과 세로로 맞고 가로로 안 넘친다", async ({ page }) => {
  mkdirSync(SHOT_DIR, { recursive: true });
  const { clean } = readFixture();
  for (const viewport of [{ width: 1440, height: 900 }, { width: 1280, height: 720 }, { width: 375, height: 812 }]) {
    await openEditor(page, clean, viewport);
    await expect(page.getByRole("button", { name: "영상 트랙 음소거" })).toBeVisible();
    const m = await page.evaluate(() => {
      const section = document.querySelector('[aria-label="타임라인"]');
      const headers = [...document.querySelectorAll('.vb-timeline-lane-headers [role="listitem"]')].map((el) => el.getBoundingClientRect().top);
      const track = document.querySelector("[data-timeline-track]").getBoundingClientRect();
      const body = document.querySelector(".vb-timeline-body").getBoundingClientRect();
      const clips = [...document.querySelectorAll('[data-testid="timeline-clip"]')].map((c) => c.getBoundingClientRect());
      const headerBox = document.querySelector(".vb-timeline-lane-headers").getBoundingClientRect();
      return {
        overflow: section.scrollWidth - section.clientWidth, headers, trackTop: track.top, trackHeight: track.height, trackLeft: track.left,
        headerRight: headerBox.right, minClipLeft: Math.min(...clips.map((c) => c.left)), bodyW: body.width,
        pageOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      };
    });
    console.log("LAYOUT", viewport.width, JSON.stringify(m));
    expect(m.overflow).toBeLessThanOrEqual(1);
    expect(m.minClipLeft).toBeGreaterThanOrEqual(m.headerRight - 1);
    // 줄 높이는 CSS 변수가 정한다 -- 머리 줄 사이 간격(측정값)을 쓰고, 클립 칸 높이/6과도 맞아야 한다.
    const pitch = m.headers[1] - m.headers[0];
    expect(Math.abs(pitch * m.headers.length - m.trackHeight)).toBeLessThanOrEqual(1.5);
    m.headers.forEach((top, i) => expect(Math.abs(top - (m.trackTop + i * pitch))).toBeLessThanOrEqual(1.5));
    await page.getByRole("region", { name: "타임라인" }).screenshot({ path: path.join(SHOT_DIR, `timeline-${viewport.width}.png`) });
    await page.screenshot({ path: path.join(SHOT_DIR, `full-${viewport.width}.png`) });
  }
});
