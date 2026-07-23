import assert from "node:assert/strict";
import test from "node:test";

import { isolatedE2eEnvironment, runE2eCommand } from "./e2e-command-runner.mjs";

test("ordinary E2E environment allocates separate non-default loopback ports", async () => {
  const available = [43101, 43102];
  const environment = await isolatedE2eEnvironment({}, async () => available.shift());

  assert.equal(environment.PLAYWRIGHT_FAKE_API_PORT, "43101");
  assert.equal(environment.PLAYWRIGHT_WEB_PORT, "43102");
  assert.notEqual(environment.PLAYWRIGHT_FAKE_API_PORT, "8000");
  assert.notEqual(environment.PLAYWRIGHT_WEB_PORT, "8000");
});

test("ordinary E2E environment preserves explicit port overrides", async () => {
  const environment = await isolatedE2eEnvironment({ PLAYWRIGHT_FAKE_API_PORT: "44001", PLAYWRIGHT_WEB_PORT: "44002" }, async () => {
    throw new Error("explicit ports must not allocate replacements");
  });

  assert.equal(environment.PLAYWRIGHT_FAKE_API_PORT, "44001");
  assert.equal(environment.PLAYWRIGHT_WEB_PORT, "44002");
});

test("E2E command runs the snapshot verifier only after Playwright succeeds", async () => {
  const calls = [];
  const available = [43103, 43104];
  const status = await runE2eCommand({
    env: {},
    findFreePort: async () => available.shift(),
    run: async (command, args, env) => {
      calls.push({ command, args, fakePort: env.PLAYWRIGHT_FAKE_API_PORT, webPort: env.PLAYWRIGHT_WEB_PORT });
      return 0;
    },
    args: ["e2e/exact-preview.spec.mjs"],
  });

  assert.equal(status, 0);
  assert.deepEqual(calls.map(({ args }) => args), [
    ["./node_modules/@playwright/test/cli.js", "test", "e2e/exact-preview.spec.mjs"],
    ["./e2e/verify-snapshot-manifest.mjs"],
  ]);
  assert.deepEqual(calls.map(({ fakePort, webPort }) => [fakePort, webPort]), [["43103", "43104"], ["43103", "43104"]]);
});

test("focused editor commands use isolated ports and the verifier", async () => {
  const calls = [];
  const available = [43105, 43106];
  const status = await runE2eCommand({
    env: {},
    findFreePort: async () => available.shift(),
    run: async (_command, args, env) => {
      calls.push({ args, fakePort: env.PLAYWRIGHT_FAKE_API_PORT, webPort: env.PLAYWRIGHT_WEB_PORT });
      return 0;
    },
    args: ["e2e/editor-workbench.spec.mjs"],
  });

  assert.equal(status, 0);
  assert.deepEqual(calls.map(({ args }) => args), [
    ["./node_modules/@playwright/test/cli.js", "test", "e2e/editor-workbench.spec.mjs"],
    ["./e2e/verify-snapshot-manifest.mjs"],
  ]);
  assert.deepEqual(calls.map(({ fakePort, webPort }) => [fakePort, webPort]), [
    ["43105", "43106"], ["43105", "43106"],
  ]);
});
