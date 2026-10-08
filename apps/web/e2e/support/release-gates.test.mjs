import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { assessWorkbenchPerformance, isAllowedBrowserRequest } from "./release-gates.mjs";

// 기준선은 기계에 맞춰 다시 잴 수 있다(2026-09-20, 2026-10-02). 값을 여기 숫자로 박아 두면
// 재측정할 때마다 이 시험이 깨진다 -- 2026-09-20 재측정 뒤 실제로 깨진 채 남아 있었다.
// 기준선 파일을 그대로 읽고, **20% 규칙만은 여기서 직접 지킨다.**
const baseline = JSON.parse(readFileSync(new URL("./workbench-performance-baseline.json", import.meta.url), "utf8"));

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
    baseline_median_ms: baseline.median_ms,
    baseline_p95_ms: baseline.p95_ms,
    baseline_capture_profile: "chromium-headless-workers-1-1920x1080",
    baseline_capture_intent: baseline.capture_intent,
    regression_limit_percent: 20,
    warmup_ms: 12,
    measurements_ms: [12, 14, 13, 15, 11],
    median_ms: 13,
    p95_ms: 15,
    regression: false,
    structural_failure: false,
  });

  // 한도는 기준선 중앙값의 120%다. 한도 바로 위는 회귀, 한도 그 자체는 회귀가 아니다.
  assert.equal(baseline.regression_limit_percent, 20);
  const limitMs = baseline.median_ms * 1.2;
  const overLimit = Math.floor(limitMs) + 1;
  assert.equal(assessWorkbenchPerformance({ browserVersion: baseline.browser_version, ciProfile: baseline.capture_profile, warmupMs: 1, measurementsMs: [overLimit, overLimit, overLimit, overLimit, overLimit] }).regression, true);
  assert.equal(assessWorkbenchPerformance({ browserVersion: baseline.browser_version, ciProfile: baseline.capture_profile, warmupMs: 1, measurementsMs: [limitMs, limitMs, limitMs, limitMs, limitMs] }).regression, false);
  assert.equal(assessWorkbenchPerformance({ browserVersion: "123", ciProfile: "ci", warmupMs: 1, measurementsMs: [1, 2] }).structural_failure, true);
  assert.equal(assessWorkbenchPerformance({ browserVersion: "123", ciProfile: "chromium-headless-workers-1-1920x1080", warmupMs: 1, measurementsMs: [1, 1, 1, 1, 1] }).structural_failure, true);
});
