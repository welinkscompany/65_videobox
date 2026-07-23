import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const loopbackHosts = new Set(["127.0.0.1", "localhost", "[::1]", "::1"]);
const performanceBaseline = JSON.parse(readFileSync(new URL("./workbench-performance-baseline.json", import.meta.url), "utf8"));

export function isAllowedBrowserRequest(value) {
  try {
    const url = new URL(value);
    return url.protocol === "data:" || url.protocol === "blob:" ||
      ((url.protocol === "http:" || url.protocol === "https:") && loopbackHosts.has(url.hostname));
  } catch {
    return false;
  }
}

export async function installBrowserNetworkGate(page) {
  const violations = [];
  const seen = new Set();
  const record = (request) => {
    const url = request.url();
    if (!isAllowedBrowserRequest(url)) violations.push({ method: request.method(), resource_type: request.resourceType(), url });
  };
  const onRequest = (request) => {
    const key = `${request.method()} ${request.resourceType()} ${request.url()}`;
    if (seen.has(key)) return;
    seen.add(key);
    record(request);
  };
  const onRoute = async (route) => {
    const request = route.request();
    onRequest(request);
    if (!isAllowedBrowserRequest(request.url())) {
      await route.abort();
      return;
    }
    await route.continue();
  };
  const context = page.context();
  page.on("request", onRequest);
  await context.route("**/*", onRoute);
  return {
    assertNoRemoteRequests() {
      assert.deepEqual(violations, [], `remote browser requests are prohibited: ${JSON.stringify(violations)}`);
    },
    async dispose() {
      page.off("request", onRequest);
      await context.unroute("**/*", onRoute);
    },
  };
}

export function assessWorkbenchPerformance({ browserVersion, ciProfile, warmupMs, measurementsMs }) {
  const structuralFailure = !browserVersion || !ciProfile || !Number.isFinite(warmupMs) ||
    measurementsMs.length !== 5 || measurementsMs.some((value) => !Number.isFinite(value) || value < 0);
  const sorted = [...measurementsMs].sort((left, right) => left - right);
  const medianMs = structuralFailure ? null : sorted[2];
  const regression = !structuralFailure && medianMs > performanceBaseline.median_ms * (1 + performanceBaseline.regression_limit_percent / 100);
  return {
    schema: "videobox-workbench-performance-v1",
    browser: { engine: "chromium", version: browserVersion, ci_profile: ciProfile },
    interaction: "right_dock_drag",
    warmup_count: 1,
    measurement_count: 5,
    baseline_median_ms: performanceBaseline.median_ms,
    baseline_capture_profile: performanceBaseline.capture_profile,
    baseline_capture_intent: performanceBaseline.capture_intent,
    regression_limit_percent: performanceBaseline.regression_limit_percent,
    warmup_ms: warmupMs,
    measurements_ms: measurementsMs,
    median_ms: medianMs,
    regression,
    structural_failure: structuralFailure,
  };
}

export function deterministicPerformanceReport(report) {
  return `${JSON.stringify(report, null, 2)}\n`;
}
