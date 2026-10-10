// 계획 I Task 0 기준선: 고치기 전 화면의 계산 스타일을 잰다. 측정이다 -- 항상 통과하고 JSON을 쓴다.
// 진짜 FastAPI + 임시 데이터 폴더(고정 시험 프로젝트)에서만 열고, 아무것도 누르지 않는다. 대표님 실제 스택(5173/8000)에는 닿지 않는다.
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

import { test } from "@playwright/test";

import { collectStyleInventory, summarizeInventory } from "../e2e/support/style-inventory.mjs";
import { readFixture } from "./support/realFlow.mjs";

const OUTPUT = path.resolve(`../../docs/superpowers/audit-evidence/${process.env.DESIGN_BASELINE_FILE ?? "2026-10-08-design-baseline.json"}`);

test("계획 I 기준선 -- 화면 여덟 개의 계산 스타일", async ({ page }) => {
  const { clean } = readFixture();
  const pages = [
    "/projects",
    "/library",
    "/library?kind=audio",
    "/footage",
    "/voices",
    "/settings/appearance",
    `/projects/${clean.projectId}/editor?session_id=${clean.sessionId}`,
    `/projects/${clean.projectId}/review`,
  ];
  const results = [];
  await page.setViewportSize({ width: 1440, height: 900 });
  for (const url of pages) {
    await page.goto(url);
    await page.waitForLoadState("networkidle").catch(() => {});
    await page.waitForTimeout(1500);
    const inventory = await collectStyleInventory(page);
    results.push({ requested: url, summary: summarizeInventory(inventory), inventory });
  }
  mkdirSync(path.dirname(OUTPUT), { recursive: true });
  writeFileSync(OUTPUT, JSON.stringify({ measuredAt: new Date().toISOString(), harness: "e2e-real (진짜 FastAPI + 임시 고정 프로젝트, Vite 개발 서버, Chromium)", viewport: "1440x900", pages: results }, null, 1));
  for (const r of results) console.log("BASELINE", r.requested, JSON.stringify(r.summary));
});
