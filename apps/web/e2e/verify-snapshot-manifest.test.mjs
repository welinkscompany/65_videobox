import assert from "node:assert/strict";
import { cp, mkdir, rm, writeFile } from "node:fs/promises";
import { test } from "node:test";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { verifySnapshotManifest } from "./verify-snapshot-manifest.mjs";

const snapshots = new URL("./snapshots/", import.meta.url);

test("pins the exact Playwright PNG set, dimensions, hashes, and deterministic capture contract", async () => {
  const errors = await verifySnapshotManifest(snapshots);
  assert.deepEqual(errors, []);
});

test("rejects a PNG that is absent from the manifest", async () => {
  const copied = join(tmpdir(), `videobox-snapshot-manifest-${process.pid}`);
  await rm(copied, { recursive: true, force: true });
  await mkdir(copied, { recursive: true });
  try {
    await cp(snapshots, copied, { recursive: true });
    await writeFile(join(copied, "unexpected.png"), new Uint8Array([137, 80, 78, 71]));
    const errors = await verifySnapshotManifest(copied);
    assert.ok(errors.some((error) => error.includes("unexpected.png")));
  } finally {
    await rm(copied, { recursive: true, force: true });
  }
});
