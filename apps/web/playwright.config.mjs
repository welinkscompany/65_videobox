import { defineConfig } from "@playwright/test";

const loopbackHost = "127.0.0.1";
const port = 4173;

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
    {
      command: "node ./e2e/support/fake-api-server.mjs",
      url: `http://${loopbackHost}:8000/health`,
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: `npm run dev -- --host ${loopbackHost} --port ${port} --strictPort`,
      url: `http://${loopbackHost}:${port}`,
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
