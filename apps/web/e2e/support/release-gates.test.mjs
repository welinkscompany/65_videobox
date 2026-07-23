import assert from "node:assert/strict";
import test from "node:test";

import { assessWorkbenchPerformance, isAllowedBrowserRequest } from "./release-gates.mjs";

test("browser network gate allows only loopback, data, and blob request URLs", () => {
  for (const url of [
    "http://127.0.0.1:41940/api/projects",
    "http://localhost:41941/",
    "http://[::1]:41941/",
    "data:application/json,{}",
    "blob:http://127.0.0.1:41941/fixture",
  ]) assert.equal(isAllowedBrowserRequest(url), true, url);

  assert.equal(isAllowedBrowserRequest("https://provider.example.invalid/v1/chat"), false);
});

test("performance report has a fixed five-sample protocol and fails only structural or 20 percent regression", () => {
  const report = assessWorkbenchPerformance({
    browserVersion: "149.0.7827.55",
    ciProfile: "chromium-headless-workers-1-1920x1080",
    warmupMs: 12,
    measurementsMs: [12, 14, 13, 15, 11],
  });

  assert.deepEqual(report, {
    schema: "videobox-workbench-performance-v1",
    browser: { engine: "chromium", version: "149.0.7827.55", ci_profile: "chromium-headless-workers-1-1920x1080" },
    interaction: "right_dock_drag",
    warmup_count: 1,
    measurement_count: 5,
    baseline_median_ms: 92,
    baseline_p95_ms: 108,
    baseline_capture_profile: "chromium-headless-workers-1-1920x1080",
    baseline_capture_intent: "calibrated reference capture on 2026-07-23",
    regression_limit_percent: 20,
    warmup_ms: 12,
    measurements_ms: [12, 14, 13, 15, 11],
    median_ms: 13,
    p95_ms: 15,
    regression: false,
    structural_failure: false,
  });

  assert.equal(assessWorkbenchPerformance({ browserVersion: "149.0.7827.55", ciProfile: "chromium-headless-workers-1-1920x1080", warmupMs: 1, measurementsMs: [111, 111, 111, 111, 111] }).regression, true);
  assert.equal(assessWorkbenchPerformance({ browserVersion: "123", ciProfile: "ci", warmupMs: 1, measurementsMs: [1, 2] }).structural_failure, true);
  assert.equal(assessWorkbenchPerformance({ browserVersion: "123", ciProfile: "chromium-headless-workers-1-1920x1080", warmupMs: 1, measurementsMs: [1, 1, 1, 1, 1] }).structural_failure, true);
});
