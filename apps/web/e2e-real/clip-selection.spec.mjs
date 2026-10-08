import { readFileSync } from "node:fs";

import { expect, test } from "@playwright/test";
import { openEditor, readFixture, serverSession } from "./support/realFlow.mjs";

// 0907 고정 시험 프로젝트의 영상 장면 경계(초). 3번째 장면 시작이 1.8990646이다.
const RANGES = ["0.00–1.33초 구간", "1.33–1.90초 구간", "1.90–2.93초 구간"];
const PLAYER_REPORTED_BEFORE_BOUNDARY = 1.899064; // 점검 §3-1 실측: 1.8990646으로 옮기라는 말에 재생기가 알려 온 시각

// 고정 시험 프로젝트에는 아직 만들어 둔 미리보기 영상이 없어 재생기가 아예 뜨지 않는다(= 결함의 입력 신호가 없다).
// 매니페스트 응답에만 `미리보기 있음`을 얹고 작은 mp4를 내어 재생기를 띄운다. 나머지(세션·타임라인·편집 항목)는 진짜 백엔드다.
const TINY_MP4 = Buffer.from(
  /const validTinyPlayableMp4 = Buffer\.from\("([^"]+)"/.exec(readFileSync("e2e/support/fake-api-server.mjs", "utf-8"))[1],
  "base64",
);

async function withPreviewPlayer(page) {
  await page.route("**/playback-manifest", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.exact_preview = {
      status: "current", url: "/__e2e/exact-preview.mp4", source_session_id: body.session_id,
      source_session_revision: body.session_revision, generation_id: "e2e", timeline_start_sec: 0,
      timeline_end_sec: body.output.duration_sec, artifact_revision: 1,
    };
    await route.fulfill({ response, json: body });
  });
  await page.route("**/__e2e/exact-preview.mp4", (route) => route.fulfill({ status: 200, contentType: "video/mp4", body: TINY_MP4 }));
}

async function playerReports(page, seconds) {
  await page.getByLabel("편집본 미리보기").evaluate((video, value) => {
    Object.defineProperty(video, "currentTime", { configurable: true, writable: true, value });
    video.dispatchEvent(new Event("timeupdate"));
  }, seconds);
}

test("영상 3번째 클립을 누르면 오른쪽 편집 항목은 셋째 장면이다", async ({ page }) => {
  await withPreviewPlayer(page);
  await openEditor(page, readFixture().clean);
  await expect(page.getByLabel("편집본 미리보기")).toBeVisible({ timeout: 90_000 });
  await page.getByRole("button", { name: /^영상 3번째 장면/ }).click();
  await page.waitForTimeout(500); // 재생기가 seeked/timeupdate를 올려 보낼 시간
  await playerReports(page, PLAYER_REPORTED_BEFORE_BOUNDARY);
  await page.waitForTimeout(300);
  await expect(page.getByRole("region", { name: "편집 항목" })).toContainText("1.90–2.93초 구간");
});

test("이웃한 클립을 번갈아 눌러도 매번 누른 장면이 잡힌다", async ({ page }) => {
  await withPreviewPlayer(page);
  await openEditor(page, readFixture().clean);
  await expect(page.getByLabel("편집본 미리보기")).toBeVisible({ timeout: 90_000 });
  const starts = [0, 1.3324, 1.8990646];
  for (const k of [3, 2, 3, 1, 3, 2]) {
    await page.getByRole("button", { name: new RegExp(`^영상 ${k}번째 장면`) }).click();
    await page.waitForTimeout(400);
    await playerReports(page, Math.max(0, starts[k - 1] - 1e-6));
    await page.waitForTimeout(300);
    await expect(page.getByRole("region", { name: "편집 항목" })).toContainText(RANGES[k - 1]);
  }
});

test("3번째 클립에서 속도를 바꾸면 서버에서는 셋째 장면만 바뀐다", async ({ page, request }) => {
  const { clean } = readFixture();
  await withPreviewPlayer(page);
  await openEditor(page, clean);
  await expect(page.getByLabel("편집본 미리보기")).toBeVisible({ timeout: 90_000 });
  const rates = async () => Object.fromEntries((await serverSession(request, clean)).segments.map((segment) => [segment.segment_id, segment.ripple_playback_rate ?? null]));
  const before = await rates();
  expect(Object.keys(before)).toEqual(["scene-1", "scene-2", "scene-3", "scene-4"]);

  await page.getByRole("button", { name: /^영상 3번째 장면/ }).click();
  await page.waitForTimeout(400);
  await playerReports(page, 1.8990646 - 1e-6);
  await page.waitForTimeout(300);
  const speed = page.getByRole("region", { name: "편집 항목" }).getByRole("spinbutton", { name: "속도", exact: true });
  try {
    await speed.fill("1.5");
    await speed.press("Enter");
    await expect.poll(async () => (await rates())["scene-3"]).toBe(1.5);
    expect(await rates()).toEqual({ ...before, "scene-3": 1.5 });
  } finally {
    // 공유 시험 프로젝트를 원래대로 -- 실행 취소.
    if ((await rates())["scene-3"] !== before["scene-3"]) {
      await page.getByRole("button", { name: "실행 취소" }).click();
      await expect.poll(rates).toEqual(before);
    }
  }
});
