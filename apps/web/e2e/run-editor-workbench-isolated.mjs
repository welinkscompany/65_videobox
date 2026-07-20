import { spawn } from "node:child_process";

const child = spawn(process.execPath, ["./node_modules/@playwright/test/cli.js", "test", "e2e/editor-workbench.spec.mjs"], {
  stdio: "inherit",
  env: { ...process.env, PLAYWRIGHT_SKIP_FAKE_API: "1", PLAYWRIGHT_WEB_PORT: "4174" },
});

child.on("error", (error) => {
  console.error(error);
  process.exitCode = 1;
});
child.on("exit", (code, signal) => {
  process.exitCode = code ?? (signal ? 1 : 0);
});
