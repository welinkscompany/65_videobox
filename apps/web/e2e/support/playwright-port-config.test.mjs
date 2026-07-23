import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import test from "node:test";

const fakeApiPort = "41891";
const configProbe = [
  'import config from "./playwright.config.mjs";',
  'console.log(JSON.stringify(config.webServer));',
].join(" ");

test("configured fake API port is shared by the Playwright server and Vite proxy", async () => {
  const probe = spawnSync(process.execPath, ["--input-type=module", "--eval", configProbe], {
    cwd: new URL("../..", import.meta.url),
    env: { ...process.env, PLAYWRIGHT_FAKE_API_PORT: fakeApiPort },
    encoding: "utf8",
  });

  assert.equal(probe.status, 0, probe.stderr);
  const [fakeApiServer, viteServer] = JSON.parse(probe.stdout);
  assert.equal(fakeApiServer.url, `http://127.0.0.1:${fakeApiPort}/health`);
  assert.equal(fakeApiServer.env.PLAYWRIGHT_FAKE_API_PORT, fakeApiPort);
  assert.equal(viteServer.env.PLAYWRIGHT_FAKE_API_PORT, fakeApiPort);

  const viteConfig = await readFile(new URL("../../vite.config.ts", import.meta.url), "utf8");
  assert.match(viteConfig, /PLAYWRIGHT_FAKE_API_PORT/);
  assert.match(viteConfig, /127\.0\.0\.1:\$\{fakeApiPort\}/);
});
