import net from "node:net";

export async function findFreeLoopbackPort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const { port } = server.address();
  await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  return port;
}

export async function isolatedE2eEnvironment(environment, findFreePort = findFreeLoopbackPort) {
  const next = { ...environment };
  const fakeApiPort = next.PLAYWRIGHT_FAKE_API_PORT ?? String(await findFreePort());
  let webPort = next.PLAYWRIGHT_WEB_PORT ?? String(await findFreePort());
  while (webPort === fakeApiPort) webPort = String(await findFreePort());
  return { ...next, PLAYWRIGHT_FAKE_API_PORT: fakeApiPort, PLAYWRIGHT_WEB_PORT: webPort };
}

export async function runE2eCommand({ env = process.env, findFreePort, run, args = process.argv.slice(2) }) {
  const isolatedEnvironment = await isolatedE2eEnvironment(env, findFreePort);
  const playwrightStatus = await run(process.execPath, ["./node_modules/@playwright/test/cli.js", "test", ...args], isolatedEnvironment);
  if (playwrightStatus !== 0) return playwrightStatus;
  return run(process.execPath, ["./e2e/verify-snapshot-manifest.mjs"], isolatedEnvironment);
}
