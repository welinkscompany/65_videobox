import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";
import { openEditor, readFixture } from "./support/realFlow.mjs";

// 계획 H Task 13: 1280x720에서도 작업판이 한 화면에 들어온다(점검 9번). 진짜 API + 고정 시험 프로젝트로 잰다.
const SHOT_DIR = path.resolve("../../.superpowers/sdd/2026-10-08-editor-core-repair-h.ko/task-13-shots");

const measure = (page) => page.evaluate(() => {
  const q = (s) => document.querySelector(s);
  const timeline = q(".vb-editor-workbench__timeline");
  const box = timeline.getBoundingClientRect();
  const view = q(".vb-timeline-lanes-viewport")?.getBoundingClientRect();
  const lanes = [...document.querySelectorAll(".vb-timeline-lane-headers [role=\"listitem\"]")].map((el) => el.getBoundingClientRect());
  const video = q(".vb-preview-stage__media-shell video")?.getBoundingClientRect();
  const inspector = [...document.querySelectorAll("aside, [role='complementary']")].map((el) => {
    const r = el.getBoundingClientRect();
    return { name: el.getAttribute("aria-label"), width: Math.round(r.width), top: Math.round(r.top), bottom: Math.round(r.bottom) };
  });
  return {
    docOverflowY: document.documentElement.scrollHeight - window.innerHeight,
    docOverflowX: document.documentElement.scrollWidth - window.innerWidth,
    timelineTop: Math.round(box.top),
    timelineHeight: Math.round(box.height),
    timelineBottom: Math.round(box.bottom),
    hiddenInTimeline: timeline.scrollHeight - timeline.clientHeight,
    lanes: lanes.length,
    lanesFullyVisible: lanes.filter((r) => r.top >= box.top - 1 && r.bottom <= Math.min(box.bottom, window.innerHeight) + 1).length,
    laneHeight: lanes[0] ? Math.round(lanes[0].height) : null,
    videoHeight: video ? Math.round(video.height) : null,
    previewAreaPercent: video ? Math.round((video.width * video.height) / (window.innerWidth * window.innerHeight) * 1000) / 10 : null,
    toolbarCollapsed: q(".vb-editor-workbench__toolbar")?.getAttribute("data-collapsed"),
    inspector,
    viewportRect: view && { top: Math.round(view.top), bottom: Math.round(view.bottom) },
  };
});

const viewports = [
  { width: 1280, height: 720 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
  { width: 800, height: 597 },
  { width: 375, height: 812 },
];

for (const viewport of viewports) {
  test(`작업판 배치 (${viewport.width}x${viewport.height})`, async ({ page }) => {
    mkdirSync(SHOT_DIR, { recursive: true });
    const { clean } = readFixture();
    await openEditor(page, clean, viewport);
    await expect(page.locator(".vb-preview-stage__media-shell video")).toHaveCount(1);
    await page.waitForTimeout(500);
    const m = await measure(page);
    console.log("ONESCREEN", `${viewport.width}x${viewport.height}`, JSON.stringify(m));
    await page.screenshot({ path: path.join(SHOT_DIR, `${process.env.ONESCREEN_TAG ?? "after"}-${viewport.width}x${viewport.height}.png`) });
    expect(m.docOverflowX, "가로 넘침").toBeLessThanOrEqual(1);
    if (viewport.width >= 768) {
      expect(m.docOverflowY, "세로 넘침").toBeLessThanOrEqual(1);
      expect(m.timelineBottom).toBeLessThanOrEqual(viewport.height + 1);
    }
    if (viewport.width === 1280 && viewport.height === 720) {
      expect(m.lanesFullyVisible, "보이는 트랙").toBeGreaterThanOrEqual(3);
      expect(m.inspector.some((a) => a.width > 0 && a.bottom <= 720)).toBe(true);
    }
  });
}
