import path from "node:path";

import { defineConfig } from "@playwright/test";

// 진짜 FastAPI + 진짜 저장소(고정 시험 프로젝트)로 도는 e2e (2026-10-08 계획 H Task 1).
const loopbackHost = "127.0.0.1";
const port = Number(process.env.PLAYWRIGHT_WEB_PORT ?? 4173);
const apiPort = Number(process.env.PLAYWRIGHT_FAKE_API_PORT ?? 8000);
const python = path.resolve(process.platform === "win32" ? "../../.venv/Scripts/python.exe" : "../../.venv/bin/python");
const apiScript = path.resolve("../../scripts/e2e_real_editor_api.py");
const fixtureFile = process.env.VIDEOBOX_E2E_FIXTURE_FILE ?? "test-results/real-flow-fixture.json";
const environment = { ...process.env, PLAYWRIGHT_FAKE_API_PORT: String(apiPort) };

export default defineConfig({
  testDir: "./e2e-real",
  timeout: 120_000,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://${loopbackHost}:${port}`,
    trace: "retain-on-failure",
    video: "off",
  },
  webServer: [
    {
      command: `"${python}" "${apiScript}" --port ${apiPort} --fixture-file ${fixtureFile}`,
      url: `http://${loopbackHost}:${apiPort}/health`,
      env: environment,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `npm run dev -- --host ${loopbackHost} --port ${port} --strictPort`,
      url: `http://${loopbackHost}:${port}`,
      env: environment,
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
