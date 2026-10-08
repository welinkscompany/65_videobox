import path from "node:path";

import { defineConfig } from "@playwright/test";

import { buildChildEnv } from "./e2e-real/support/childEnv.mjs";

// 진짜 FastAPI + 진짜 저장소(고정 시험 프로젝트)로 도는 e2e (2026-10-08 계획 H Task 1).
const loopbackHost = "127.0.0.1";
// 포트는 러너(run-real-flow.mjs)가 빈 포트로 넣는다. 없으면 8000(살아 있는 API 포트)에 붙지 않고 멈춘다.
if (!process.env.PLAYWRIGHT_WEB_PORT || !process.env.PLAYWRIGHT_FAKE_API_PORT) {
  throw new Error("npm run test:e2e:real-flow 로 실행하세요 (포트는 러너가 정합니다)");
}
const port = Number(process.env.PLAYWRIGHT_WEB_PORT);
const apiPort = Number(process.env.PLAYWRIGHT_FAKE_API_PORT);
const python = path.resolve(process.platform === "win32" ? "../../.venv/Scripts/python.exe" : "../../.venv/bin/python");
const apiScript = path.resolve("../../scripts/e2e_real_editor_api.py");
const fixtureFile = process.env.VIDEOBOX_E2E_FIXTURE_FILE ?? "test-results/real-flow-fixture.json";
// 허용 목록 환경: 소유자 셸의 VIDEOBOX_*·토큰이 자식 서버에 닿지 않는다.
const environment = buildChildEnv(process.env, { PLAYWRIGHT_FAKE_API_PORT: String(apiPort) });

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
