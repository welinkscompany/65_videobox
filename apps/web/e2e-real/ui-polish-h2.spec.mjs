import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";
import { openEditor, readFixture } from "./support/realFlow.mjs";

// 2026-10-10 계획 H 마감 점검에서 나온 화면 결함 넷(알림이 클릭을 가로챔 · 375 머리 칸 폭 · 375 단축키 패널 · 742 안내 줄 밀림).
const SHOT_DIR = path.resolve("../../docs/superpowers/audit-evidence/2026-10-08-editor-ui/after-h2");
const shot = (page, name) => { mkdirSync(SHOT_DIR, { recursive: true }); return page.screenshot({ path: path.join(SHOT_DIR, `${process.env.H2_TAG ?? "after"}-${name}.png`) }); };

/** 저장이 느린 척해 알림("변경 내용을 저장하고 있어요")이 계속 떠 있게 한다. */
async function holdSaves(page) {
  await page.route("**/api/**", async (route) => {
    if (route.request().method() === "GET") return route.continue();
    await new Promise((resolve) => setTimeout(resolve, 6000));
    return route.continue();
  });
}

for (const viewport of [{ width: 1280, height: 720 }, { width: 375, height: 812 }]) {
  test(`알림이 떠 있어도 타임라인 클릭을 가로채지 않는다 (${viewport.width}x${viewport.height})`, async ({ page }) => {
    const { clean } = readFixture();
    await openEditor(page, clean, viewport);
    await expect(page.getByRole("button", { name: "영상 트랙 음소거" })).toBeVisible();
    await page.waitForTimeout(500);
    await holdSaves(page);
    await page.getByRole("button", { name: "영상 트랙 음소거" }).scrollIntoViewIfNeeded();
    await page.getByRole("button", { name: "영상 트랙 음소거" }).click();
    const toast = page.locator("[data-sonner-toast]").first();
    await expect(toast).toBeVisible({ timeout: 5000 });
    await expect(toast).toHaveAttribute("data-mounted", "true");
    await page.waitForTimeout(600);
    await shot(page, `toast-${viewport.width}x${viewport.height}`);
    const blocked = await page.evaluate(() => {
      const box = document.querySelector(".vb-editor-workbench__timeline").getBoundingClientRect();
      const hits = [];
      const targets = [...document.querySelectorAll(".vb-timeline-clip, .vb-timeline-lane-headers button, .vb-timeline-ruler")];
      for (const el of targets) {
        const r = el.getBoundingClientRect();
        const x = Math.round(r.left + r.width / 2);
        const y = Math.round(r.top + r.height / 2);
        if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) continue;
        if (y < box.top || y > box.bottom) continue;
        const top = document.elementFromPoint(x, y);
        if (top?.closest("[data-sonner-toaster], [data-sonner-toast]")) hits.push(el.getAttribute("aria-label") ?? el.className);
      }
      // 알림 카드 자체 위의 점도 아래 요소가 받아야 한다(클립이 없는 자리여도 마찬가지).
      const card = document.querySelector("[data-sonner-toast]").getBoundingClientRect();
      for (const [fx, fy] of [[0.5, 0.5], [0.1, 0.5], [0.9, 0.5], [0.5, 0.2], [0.5, 0.8]]) {
        const top = document.elementFromPoint(card.left + card.width * fx, card.top + card.height * fy);
        if (top?.closest("[data-sonner-toaster], [data-sonner-toast]")) hits.push(`알림 카드 ${fx},${fy}`);
      }
      return { hits, total: targets.length };
    });
    console.log("TOASTBLOCK", `${viewport.width}x${viewport.height}`, JSON.stringify(blocked));
    expect(blocked.hits, "알림이 가로챈 요소").toEqual([]);
    // 화면 읽기 프로그램에는 계속 알려야 한다.
    expect(await page.locator("[aria-live]").count()).toBeGreaterThan(0);
  });
}

test("375에서 트랙 머리 칸이 화면 폭의 35%를 넘지 않는다", async ({ page }) => {
  const { clean } = readFixture();
  await openEditor(page, clean, { width: 375, height: 812 });
  await expect(page.getByRole("button", { name: "영상 트랙 음소거" })).toBeVisible();
  const m = await page.evaluate(() => {
    const headers = document.querySelector(".vb-timeline-lane-headers").getBoundingClientRect();
    const buttons = [...document.querySelectorAll(".vb-timeline-lane-headers button")].map((b) => { const r = b.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height) }; });
    return { width: headers.width, percent: Math.round((headers.width / innerWidth) * 1000) / 10, minBtn: Math.min(...buttons.map((b) => Math.min(b.w, b.h))), rows: [...document.querySelectorAll(".vb-timeline-lane-headers [role='listitem']")].map((n) => n.textContent) };
  });
  console.log("HEADERW", JSON.stringify(m));
  await shot(page, "375-headers");
  expect(m.percent).toBeLessThanOrEqual(35);
});

for (const viewport of [{ width: 375, height: 812 }, { width: 1280, height: 720 }]) {
  test(`단축키 안내가 잘리거나 유진 단추에 가려지지 않는다 (${viewport.width}x${viewport.height})`, async ({ page }) => {
    const { clean } = readFixture();
    await openEditor(page, clean, viewport);
    await expect(page.locator(".vb-preview-stage__media-shell video")).toHaveCount(1);
    await page.getByRole("button", { name: "단축키", exact: true }).click();
    const note = page.getByRole("note", { name: "편집 단축키" });
    await expect(note).toBeVisible();
    await page.waitForTimeout(300);
    await shot(page, `shortcuts-${viewport.width}x${viewport.height}`);
    const m = await page.evaluate(() => {
      const el = document.querySelector("#vb-playback-shortcuts");
      const r = el.getBoundingClientRect();
      const toggle = document.querySelector(".vb-yujin-panel__toggle")?.getBoundingClientRect();
      // 눈에 보이는 영역: 화면 + 모든 조상의 잘라내기(overflow)
      let visible = { left: 0, top: 0, right: innerWidth, bottom: innerHeight };
      for (let p = el.parentElement; p; p = p.parentElement) {
        const s = getComputedStyle(p);
        if (/(hidden|clip|auto|scroll)/.test(s.overflowX + s.overflowY)) {
          const b = p.getBoundingClientRect();
          visible = { left: Math.max(visible.left, b.left), top: Math.max(visible.top, b.top), right: Math.min(visible.right, b.right), bottom: Math.min(visible.bottom, b.bottom) };
        }
      }
      const clipped = Math.max(0, visible.top - r.top) + Math.max(0, r.bottom - visible.bottom) + Math.max(0, visible.left - r.left) + Math.max(0, r.right - visible.right);
      const overlap = toggle ? Math.max(0, Math.min(r.right, toggle.right) - Math.max(r.left, toggle.left)) * Math.max(0, Math.min(r.bottom, toggle.bottom) - Math.max(r.top, toggle.top)) : 0;
      return { clipped: Math.round(clipped), overlap: Math.round(overlap), scrollable: el.scrollHeight > el.clientHeight, rect: [Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)] };
    });
    console.log("SHORTCUTS", `${viewport.width}x${viewport.height}`, JSON.stringify(m));
    expect(m.clipped, "잘린 만큼").toBeLessThanOrEqual(1);
    expect(m.overlap, "유진 단추와 겹침").toBe(0);
    // 안내를 연 채로도 스페이스가 먹는다(대화 상자가 아니다).
    await page.evaluate(() => document.activeElement?.blur());
    await page.keyboard.press("Space");
    await expect(note).toBeVisible();
  });
}

test("742 모양에서 안내 줄이 생겨도 페이지가 밀리지 않는다 (1440x900)", async ({ page }) => {
  const { noNarration } = readFixture();
  await openEditor(page, noNarration, { width: 1440, height: 900 });
  await page.waitForTimeout(800);
  const measure = () => page.evaluate(() => ({ overflowY: document.documentElement.scrollHeight - innerHeight, timelineBottom: Math.round(document.querySelector(".vb-editor-workbench__timeline").getBoundingClientRect().bottom), previewH: Math.round(document.querySelector(".vb-preview-stage__media-shell video")?.getBoundingClientRect().height ?? 0) }));
  const before = await measure();
  // 가로·세로 버전 목록을 못 불러오게 해 안내 줄(`role=status`)이 실제로 생기게 한다 -- 마스터가 바뀌었어요 줄과 같은 자리·같은 줄이다.
  await page.route("**/output-variants?**", (route) => route.fulfill({ status: 500, contentType: "application/json", body: "{\"detail\":\"x\"}" }));
  await page.reload();
  await expect(page.getByRole("region", { name: "타임라인" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("status").filter({ hasText: "가로·세로 버전을 불러오지 못했어요" })).toHaveCount(1, { timeout: 15_000 });
  await page.waitForTimeout(500);
  const after = await measure();
  console.log("STATUSLINE", JSON.stringify({ before, after }));
  await shot(page, "742-status-1440x900");
  expect(after.overflowY, "세로 넘침").toBeLessThanOrEqual(1);
  expect(after.timelineBottom - before.timelineBottom, "타임라인 밀림").toBeLessThanOrEqual(1);
});
