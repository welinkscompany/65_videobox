import { spawn } from "node:child_process";

import { isolatedE2eEnvironment } from "../e2e/support/e2e-command-runner.mjs";

function run(command, args, env) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd: process.cwd(), env, stdio: "inherit" });
    child.once("error", reject);
    child.once("exit", (code, signal) => resolve(code ?? (signal ? 1 : 0)));
  });
}

// 이 묶음은 스냅샷을 쓰지 않으므로 스냅샷 목록 검사는 하지 않는다.
const environment = await isolatedE2eEnvironment(process.env);
process.exitCode = await run(
  process.execPath,
  ["./node_modules/@playwright/test/cli.js", "test", "--config", "playwright.real-flow.config.mjs", ...process.argv.slice(2)],
  environment,
);
