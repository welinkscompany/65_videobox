import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { assessWorkbenchPerformance, deterministicPerformanceReport, installBrowserNetworkGate } from "./support/release-gates.mjs";

const project = { project_id: "local-draft", name: "릴리스 게이트", status: "active", root_storage_uri: "local://release-gates" };
const manifest = {
  project_id: "local-draft", session_id: "release-gates-e2e", timeline_id: "timeline-release-gates", session_revision: 7, timeline_version: "v7",
  timebase: "seconds", fps: { num: 30, den: 1 }, output: { width: 1080, height: 1920, sample_aspect_ratio: "1:1", rotation: 0, duration_sec: 12 },
  tracks: [], captions: [], gap_slots: [], source_status: { status: "current", source_session_id: "release-gates-e2e", source_session_revision: 7 },
  audition: { asset_urls: {} }, exact_preview: { status: "unavailable", url: null, source_session_id: "release-gates-e2e", source_session_revision: 7 },
};

async function openWorkbench(page) {
  await page.route("**/api/projects", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ projects: [project] }) }));
  await page.route("**/playback-manifest", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(manifest) }));
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/projects/local-draft/editor?session_id=release-gates-e2e");
  await expect(page.getByRole("region", { name: "편집 작업판" })).toBeVisible();
}

test("browser network gate allows the real workbench to use only local request origins", async ({ page }) => {
  const gate = await installBrowserNetworkGate(page);
  try {
    await openWorkbench(page);
    gate.assertNoRemoteRequests();
  } finally {
    await gate.dispose();
  }
});

test("browser network gate aborts a remote origin before it leaves the test browser", async ({ page }) => {
  const gate = await installBrowserNetworkGate(page);
  try {
    await page.goto("/");
    await page.evaluate(() => {
      const image = new Image();
      image.src = "https://provider.example.invalid/blocked.png";
      document.body.append(image);
    });
    await expect.poll(() => {
      try { gate.assertNoRemoteRequests(); return false; } catch { return true; }
    }).toBe(true);
  } finally {
    await gate.dispose();
  }
});

async function measureRightDockDrag(page, offset) {
  const handle = page.getByLabel("오른쪽 패널 크기 조절");
  const box = await handle.boundingBox();
  if (!box) throw new Error("structural performance failure: right dock resize handle is missing");
  const startedAt = await page.evaluate(() => performance.now());
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + offset, box.y + box.height / 2, { steps: 3 });
  await page.mouse.up();
  return page.evaluate(async () => {
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    return performance.now();
  }).then((finishedAt) => finishedAt - startedAt);
}

test("workbench dock drag has fixed warmup and five-sample local performance evidence", async ({ page, browser }) => {
  await openWorkbench(page);
  const warmupMs = await measureRightDockDrag(page, -18);
  const measurementsMs = [];
  for (const offset of [18, -18, 18, -18, 18]) measurementsMs.push(await measureRightDockDrag(page, offset));

  const report = assessWorkbenchPerformance({
    browserVersion: browser.version(),
    ciProfile: "chromium-headless-workers-1-1920x1080",
    warmupMs,
    measurementsMs,
  });
  const reportPath = path.resolve("test-results", "editor-workbench-performance.json");
  await mkdir(path.dirname(reportPath), { recursive: true });
  await writeFile(reportPath, deterministicPerformanceReport(report), "utf8");

  expect(report.structural_failure).toBe(false);
  expect(report.regression).toBe(false);
  await expect(page.getByRole("complementary", { name: "유진과 편집 항목" })).toBeVisible();
});
