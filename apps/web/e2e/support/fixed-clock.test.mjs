import assert from "node:assert/strict";
import { test } from "node:test";

import { fixedClockEpochMs, fixedClockInit, installFixedClock, playwrightSnapshotOptions, waitForStableCapture } from "./fixed-clock.mjs";

test("pins Date construction and Date.now without freezing browser timers", async () => {
  const nativeDate = globalThis.Date;
  try {
    fixedClockInit(fixedClockEpochMs);
    assert.equal(Date.now(), 0);
    assert.equal(new Date().toISOString(), "1970-01-01T00:00:00.000Z");
    assert.equal(new Date("2026-07-23T00:00:00.000Z").toISOString(), "2026-07-23T00:00:00.000Z");
  } finally {
    globalThis.Date = nativeDate;
  }
});

test("installs the same fixed clock before a snapshot navigation", async () => {
  const calls = [];
  await installFixedClock({ addInitScript: async (...args) => { calls.push(args); } });
  assert.deepEqual(calls, [[fixedClockInit, fixedClockEpochMs]]);
});

test("waits for fonts and two paint frames before writing a deterministic snapshot", async () => {
  const calls = [];
  await waitForStableCapture({ evaluate: async (callback) => { calls.push(callback); } });
  assert.equal(calls.length, 1);
});

test("captures for visual checks without overwriting approved artifacts unless explicitly requested", () => {
  assert.deepEqual(playwrightSnapshotOptions("e2e/snapshots/example.png", false), { animations: "disabled", caret: "hide" });
  assert.deepEqual(playwrightSnapshotOptions("e2e/snapshots/example.png", true), { path: "e2e/snapshots/example.png", animations: "disabled", caret: "hide" });
});
