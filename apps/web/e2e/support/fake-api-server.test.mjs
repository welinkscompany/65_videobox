import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import net from "node:net";
import test from "node:test";
import { fileURLToPath } from "node:url";

const fakeServerPath = fileURLToPath(new URL("./fake-api-server.mjs", import.meta.url));

async function findAvailableLoopbackPort() {
  const server = net.createServer();
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();
  await new Promise((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
  return port;
}

async function waitForHealth(port) {
  const deadline = Date.now() + 2_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/health`);
      if (response.status === 200) return;
    } catch {
      // The child process is still binding its isolated port.
    }
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  throw new Error(`fake API did not bind isolated port ${port}`);
}

async function stop(child) {
  if (child.exitCode !== null) return;
  child.kill();
  await new Promise((resolve) => child.once("exit", resolve));
}

test("fake API retires the Gemini key-management route on its isolated port", async () => {
  const port = await findAvailableLoopbackPort();
  const child = spawn(process.execPath, [fakeServerPath], {
    env: { ...process.env, VIDEOBOX_E2E_FAKE_API_PORT: String(port) },
    stdio: "ignore",
  });

  try {
    await waitForHealth(port);
    const response = await fetch(
      `http://127.0.0.1:${port}/api/projects/local-draft/providers/gemini/keys`,
    );

    assert.equal(response.status, 404);
  } finally {
    await stop(child);
  }
});
