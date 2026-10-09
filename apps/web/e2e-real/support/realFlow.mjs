import { readFileSync } from "node:fs";
import path from "node:path";

import { expect } from "@playwright/test";

const fixtureFile = path.resolve(process.env.VIDEOBOX_E2E_FIXTURE_FILE ?? "test-results/real-flow-fixture.json");

/** @returns {{ clean: Fixture, duplicatedOverlays: Fixture, noNarration: Fixture, playback: Fixture, shortcuts: Fixture }} Fixture = { projectId, sessionId, timelineId } */
export function readFixture() {
  return JSON.parse(readFileSync(fixtureFile, "utf-8"));
}

export async function openEditor(page, fixture, viewport) {
  await page.setViewportSize(viewport ?? { width: 1440, height: 900 });
  await page.goto(`/projects/${fixture.projectId}/editor?session_id=${fixture.sessionId}`);
  await expect(page.getByRole("region", { name: "타임라인" })).toBeVisible({ timeout: 30_000 });
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

/**
 * 서버에 저장된 편집 상태의 비교용 사진(2026-10-08 계획 H Task 17).
 * 개정 번호·되돌리기 쌓기 개수는 빼고 장면 경계·속도·자르기 표시·트랙 상태·오버레이 자리만 담는다 -- "되돌리기가 정확하다"의 기준이다.
 */
export async function editSnapshot(request, fixture) {
  const [session, manifest] = await Promise.all([serverSession(request, fixture), serverManifest(request, fixture)]);
  return {
    segments: session.segments.map((segment) => ({
      segment_id: segment.segment_id,
      start_sec: segment.start_sec,
      end_sec: segment.end_sec,
      cut_action: segment.cut_action,
      ripple_playback_rate: segment.ripple_playback_rate ?? null,
    })),
    track_states: manifest.track_states ?? {},
    overlays: manifest.tracks.filter((track) => track.track_type === "overlay")
      .flatMap((track) => track.clips.map((clip) => [clip.placement_id ?? clip.clip_id, clip.segment_id, clip.start_sec, clip.end_sec])),
  };
}

/** 저장이 끝날 때까지 기다린다 -- 사람이 하듯 상태 줄이 "저장하고 있어요"를 벗어나길 본다(고정 잠깐 쉬기가 아니다). */
export function waitSaved(page) {
  return expect.poll(async () => {
    const lines = await page.getByRole("status", { name: "편집 저장 상태" }).allTextContents();
    return lines.some((line) => /저장하고 있어요|불러오고 있어요/.test(line));
  }, { timeout: 15_000 }).toBe(false);
}
