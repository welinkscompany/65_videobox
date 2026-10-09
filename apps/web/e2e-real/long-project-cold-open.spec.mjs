import { readFileSync } from "node:fs";

import { expect, test } from "@playwright/test";
import { readFixture } from "./support/realFlow.mjs";

// 2026-10-09 마감 점검: 742e1924(120초, 영상 15개 중 하나가 90~102초에 놓여 뒤 영상과 같은 줄에서 겹침)를 처음 열면
// "화면을 그리다 멈췄어요"(RangeError: Rectangle width and height must be positive)가 났다.
// 실제 매니페스트 모양을 응답에 얹어(나머지는 진짜 백엔드) 여러 크기·여러 번 처음 열어 본다.
const REAL_742 = JSON.parse(readFileSync("src/features/editor/__fixtures__/manifest-742e1924-no-narration.json", "utf-8"));
const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 1280, height: 720 },
  { width: 800, height: 597 },
  { width: 375, height: 812 },
];
const LOADS_PER_VIEWPORT = Number(process.env.COLD_LOADS ?? 10);

test("120초·겹친 영상이 있는 실제 모양을 처음 열 때마다 편집기가 죽지 않고 첫 60초가 칸 안에 들어온다", async ({ page }) => {
  test.setTimeout(900_000); // 네 크기 x 여러 번 처음 열기
  const { noNarration } = readFixture();
  await page.route("**/playback-manifest", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    await route.fulfill({ response, json: { ...REAL_742, project_id: body.project_id, session_id: body.session_id, timeline_id: body.timeline_id, session_revision: body.session_revision } });
  });
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error" && !m.text().startsWith("Failed to load resource")) console.log("CONSOLE_ERR", m.text().slice(0, 600)); });
  page.on("pageerror", (error) => errors.push(String(error)));
  page.on("response", (r) => { if (r.status() >= 500) console.log("HTTP5XX", r.status(), r.url()); });
  let loads = 0;
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    for (let index = 0; index < LOADS_PER_VIEWPORT; index += 1) {
      await page.goto("about:blank");
      await page.goto(`/projects/${noNarration.projectId}/editor?session_id=${noNarration.sessionId}`);
      await expect(page.getByRole("region", { name: "타임라인" })).toBeVisible();
      await page.waitForTimeout(600); // 잰 폭이 들어오고 다시 맞추는 시간
      await expect(page.getByText("화면을 그리다 멈췄어요")).toHaveCount(0);
      const fit = await page.getByRole("region", { name: "타임라인" }).evaluate((region) => {
        const lanes = region.querySelector(".vb-timeline-lanes-viewport");
        return { pxPerSec: Number(region.getAttribute("data-pixels-per-second")), laneWidth: lanes ? lanes.clientWidth : 0 };
      });
      expect(fit.laneWidth).toBeGreaterThan(0);
      // 처음 배율은 최대 60초가 칸을 채우는 값이다(그보다 긴 영상은 처음 60초). 그 60초가 칸 안에 든다.
      expect(fit.pxPerSec * 60).toBeLessThanOrEqual(fit.laneWidth + 1);
      loads += 1;
    }
  }
  expect(errors.filter((message) => /Rectangle width/.test(message))).toEqual([]);
  console.log(`COLD_LOADS_DONE ${loads}`);
});

test("짧은 영상(0907 같은 3.75초)은 처음 열 때 전체 길이가 칸 안에 들어오고(20초 창), 전체 보기는 칸을 채운다", async ({ page }) => {
  const { clean } = readFixture();
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await page.goto("about:blank");
    await page.goto(`/projects/${clean.projectId}/editor?session_id=${clean.sessionId}`);
    await expect(page.getByRole("region", { name: "타임라인" })).toBeVisible();
    await page.waitForTimeout(600);
    const fit = await page.getByRole("region", { name: "타임라인" }).evaluate((region) => {
      const lanes = region.querySelector(".vb-timeline-lanes-viewport");
      return { pxPerSec: Number(region.getAttribute("data-pixels-per-second")), laneWidth: lanes ? lanes.clientWidth : 0 };
    });
    expect(fit.pxPerSec * 3.7512).toBeLessThanOrEqual(fit.laneWidth + 1);
    // P2(2026-10-09): 처음 창은 적어도 20초라 짧은 영상은 칸의 일부만 채운다(뒤는 빈 자리). 칸을 채우는 것은 `전체 보기`가 한다.
    expect(fit.pxPerSec * 20).toBeGreaterThan(fit.laneWidth * 0.9);
    expect(fit.pxPerSec * 20).toBeLessThanOrEqual(fit.laneWidth + 1);
    await page.getByRole("button", { name: "타임라인 전체 보기" }).click();
    const filled = await page.getByRole("region", { name: "타임라인" }).evaluate((region) => Number(region.getAttribute("data-pixels-per-second")));
    expect(filled * 3.7512).toBeLessThanOrEqual(fit.laneWidth + 1);
    expect(filled * 3.7512).toBeGreaterThan(fit.laneWidth * 0.9);
  }
});

// 마감 점검 d: 0907(7.75초)은 처음 열 때 끝 1.2초가 잘려 있었다 -- 실제 매니페스트 모양으로 네 크기에서 클립 오른쪽 끝이 칸 안인지 잰다.
const REAL_0907 = JSON.parse(readFileSync("src/features/editor/__fixtures__/manifest-0907-b26195af.json", "utf-8"));
test("0907 실제 모양(7.75초)은 네 크기에서 처음 열 때 마지막 클립 끝까지 칸 안에 보인다", async ({ page }) => {
  const { clean } = readFixture();
  await page.route("**/playback-manifest", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    await route.fulfill({ response, json: { ...REAL_0907, project_id: body.project_id, session_id: body.session_id, timeline_id: body.timeline_id, session_revision: body.session_revision } });
  });
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await page.goto("about:blank");
    await page.goto(`/projects/${clean.projectId}/editor?session_id=${clean.sessionId}`);
    await expect(page.getByRole("region", { name: "타임라인" })).toBeVisible();
    await page.waitForTimeout(800);
    const fit = await page.getByRole("region", { name: "타임라인" }).evaluate((region) => {
      const lanes = region.querySelector(".vb-timeline-lanes-viewport");
      const rights = [...region.querySelectorAll('[data-testid="timeline-clip"]')].map((clip) => clip.getBoundingClientRect().right);
      return { laneWidth: lanes.clientWidth, laneRight: lanes.getBoundingClientRect().right, maxRight: Math.max(...rights), scrollWidth: lanes.scrollWidth };
    });
    expect(fit.maxRight, JSON.stringify(viewport)).toBeLessThanOrEqual(fit.laneRight + 1);
    expect(fit.scrollWidth).toBeLessThanOrEqual(fit.laneWidth + 1);
  }
});
