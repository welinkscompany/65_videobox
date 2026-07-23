import { spawn } from "node:child_process";

import { runE2eCommand } from "./support/e2e-command-runner.mjs";

function run(command, args, env) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd: process.cwd(), env, stdio: "inherit" });
    child.once("error", reject);
    child.once("exit", (code, signal) => resolve(code ?? (signal ? 1 : 0)));
  });
}

process.exitCode = await runE2eCommand({
  run,
  args: ["e2e/editor-workbench.spec.mjs"],
});
