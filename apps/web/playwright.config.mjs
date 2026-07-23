import { defineConfig } from "@playwright/test";

const loopbackHost = "127.0.0.1";
const port = Number(process.env.PLAYWRIGHT_WEB_PORT ?? 4173);
const fakeApiPort = Number(process.env.PLAYWRIGHT_FAKE_API_PORT ?? 8000);
const fakeApiEnvironment = { ...process.env, PLAYWRIGHT_FAKE_API_PORT: String(fakeApiPort) };
const fakeApiServer = {
  command: "node ./e2e/support/fake-api-server.mjs",
  url: `http://${loopbackHost}:${fakeApiPort}/health`,
  env: fakeApiEnvironment,
  reuseExistingServer: Boolean(process.env.PLAYWRIGHT_REUSE_EXISTING),
  timeout: 30_000,
};

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://${loopbackHost}:${port}`,
    trace: "retain-on-failure",
    video: "off",
  },
  webServer: [
    ...(process.env.PLAYWRIGHT_SKIP_FAKE_API ? [] : [fakeApiServer]),
    {
      command: `npm run dev -- --host ${loopbackHost} --port ${port} --strictPort`,
      url: `http://${loopbackHost}:${port}`,
      env: fakeApiEnvironment,
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
