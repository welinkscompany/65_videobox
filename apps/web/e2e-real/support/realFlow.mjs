import { readFileSync } from "node:fs";
import path from "node:path";

import { expect } from "@playwright/test";

const fixtureFile = path.resolve(process.env.VIDEOBOX_E2E_FIXTURE_FILE ?? "test-results/real-flow-fixture.json");

/** @returns {{ clean: Fixture, duplicatedOverlays: Fixture }} Fixture = { projectId, sessionId, timelineId } */
export function readFixture() {
  return JSON.parse(readFileSync(fixtureFile, "utf-8"));
}

export async function openEditor(page, fixture, viewport) {
  await page.setViewportSize(viewport ?? { width: 1440, height: 900 });
  await page.goto(`/projects/${fixture.projectId}/editor?session_id=${fixture.sessionId}`);
  await expect(page.getByRole("region", { name: "타임라인" })).toBeVisible();
}

async function getJson(request, path) {
  const response = await request.get(path);
  expect(response.ok(), `${path} -> ${response.status()}`).toBeTruthy();
  return response.json();
}

// include_history=false: Task 11 전에는 서버가 이 인자를 무시한다.
export function serverSession(request, fixture) {
  return getJson(request, `/api/projects/${fixture.projectId}/editing-sessions/${fixture.sessionId}?include_history=false`);
}

export function serverManifest(request, fixture) {
  return getJson(request, `/api/projects/${fixture.projectId}/editing-sessions/${fixture.sessionId}/playback-manifest`);
}
