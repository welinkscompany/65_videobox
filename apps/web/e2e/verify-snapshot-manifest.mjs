import { createHash } from "node:crypto";
import { readdir, readFile, stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const manifestName = "playwright-snapshot-manifest.json";
const pngSignature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);

function rootPath(snapshotRoot) {
  return snapshotRoot instanceof URL ? fileURLToPath(snapshotRoot) : snapshotRoot;
}

function pngSize(bytes) {
  if (bytes.length < 24 || !bytes.subarray(0, 8).equals(pngSignature)) throw new Error("not a PNG");
  return { width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20) };
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function generatorErrors(generator) {
  const errors = [];
  if (generator?.runner !== "Playwright") errors.push("generator.runner must be Playwright");
  if (generator?.browser !== "chromium") errors.push("generator.browser must be chromium");
  if (generator?.fixture?.network !== "loopback-only") errors.push("generator.fixture.network must be loopback-only");
  if (generator?.fixture?.api !== "e2e/support/fake-api-server.mjs") errors.push("generator.fixture.api must name the fixed local fake API");
  if (generator?.clock?.mode !== "fixed" || generator.clock?.epoch_ms !== 0) errors.push("generator.clock must pin epoch_ms 0");
  if (generator?.capture?.animations !== "disabled" || generator.capture?.caret !== "hide") errors.push("generator.capture must disable animations and hide the caret");
  return errors;
}

export async function verifySnapshotManifest(snapshotRoot = new URL("./snapshots/", import.meta.url)) {
  const root = rootPath(snapshotRoot);
  const errors = [];
  let manifest;
  try {
    manifest = JSON.parse(await readFile(`${root}/${manifestName}`, "utf8"));
  } catch (error) {
    return [`cannot read ${manifestName}: ${error instanceof Error ? error.message : String(error)}`];
  }
  if (manifest?.manifest_version !== 1) errors.push("manifest_version must be 1");
  errors.push(...generatorErrors(manifest?.generator));
  if (!Array.isArray(manifest?.snapshots) || !manifest.snapshots.length) return [...errors, "snapshots must be a non-empty array"];

  const entries = manifest.snapshots;
  const expected = new Set(entries.map((entry) => entry.path));
  if (expected.size !== entries.length) errors.push("manifest snapshot paths must be unique");
  const actual = new Set((await readdir(root)).filter((name) => name.endsWith(".png")));
  for (const name of [...actual].filter((name) => !expected.has(name)).sort()) errors.push(`unexpected PNG: ${name}`);
  for (const name of [...expected].filter((name) => !actual.has(name)).sort()) errors.push(`missing PNG: ${name}`);

  for (const entry of entries) {
    if (typeof entry?.path !== "string" || entry.path.includes("/") || entry.path.includes("\\")) { errors.push(`invalid snapshot path: ${String(entry?.path)}`); continue; }
    try {
      const file = `${root}/${entry.path}`;
      const bytes = await readFile(file);
      const dimensions = pngSize(bytes);
      const fileStat = await stat(file);
      if (entry.bytes !== fileStat.size) errors.push(`${entry.path}: bytes mismatch`);
      if (entry.sha256 !== sha256(bytes)) errors.push(`${entry.path}: sha256 mismatch`);
      if (entry.viewport?.width !== dimensions.width || entry.viewport?.height !== dimensions.height) errors.push(`${entry.path}: viewport mismatch`);
    } catch (error) {
      errors.push(`${entry.path}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  return errors;
}

if (process.argv[1] && new URL(`file:///${process.argv[1].replace(/\\/g, "/")}`).href === import.meta.url) {
  const errors = await verifySnapshotManifest();
  if (errors.length) {
    console.error(errors.join("\n"));
    process.exitCode = 1;
  } else {
    console.log(`verified ${manifestName}`);
  }
}
