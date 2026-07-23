import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import test from "node:test";

const e2eDirectory = fileURLToPath(new URL("..", import.meta.url));

test("every Playwright browser spec uses the global loopback network fixture", async () => {
  const specs = (await readdir(e2eDirectory)).filter((name) => name.endsWith(".spec.mjs")).sort();
  assert.ok(specs.length > 0);
  for (const spec of specs) {
    const source = await readFile(`${e2eDirectory}/${spec}`, "utf8");
    assert.match(source, /from "\.\/support\/test-fixtures\.mjs"/, spec);
  }
});
