import { expect, test } from "@playwright/test";

const fakeApiBaseUrl = `http://127.0.0.1:${Number(process.env.PLAYWRIGHT_FAKE_API_PORT ?? 8000)}`;

async function reset(page) {
  expect((await page.request.post(`${fakeApiBaseUrl}/__e2e/reset-draft`)).status()).toBe(200);
  await page.addInitScript(() => {
    localStorage.setItem("videobox.creation-brief.local-draft", "brief-e2e");
    localStorage.setItem("videobox.draft-readiness.local-draft", "readiness_e2e");
  });
}

test("gap-only approval preserves returned gap IDs and blocks final render and CapCut", async ({ page }) => {
  await reset(page);
  await page.goto("/projects/local-draft/create");
  const placeholderConfirmation = page.getByLabel("빈 구간을 남긴 채 편집용 초안을 만들겠습니다");
  await expect(placeholderConfirmation).toBeVisible();
  await placeholderConfirmation.check();
  await page.getByRole("button", { name: "빈 구간 포함 초안 만들기" }).click();
  await expect(page).toHaveURL(/\/projects\/local-draft\/editor\?session_id=/);
  const state = await (await page.request.get(`${fakeApiBaseUrl}/__e2e/draft-state`)).json();
  expect(state.latest_bundle.output_blocked).toBeTruthy();
  expect(state.latest_bundle.gap_slots).toHaveLength(1);
  expect(state.latest_bundle.segment_ids).toHaveLength(1);
  expect(state.latest_bundle.clip_ids).toHaveLength(2);
  await expect(page).toHaveURL(new RegExp(`/editor\\?session_id=${state.latest_bundle.session_id}$`));
  await expect(page.getByLabel("완성본 재생")).toHaveCount(0);
  await expect(page.getByLabel("현재 편집본 재생")).toHaveCount(0);
  expect((await page.request.post(`${fakeApiBaseUrl}/api/projects/local-draft/jobs/final-render`)).status()).toBe(400);
  expect((await page.request.post(`${fakeApiBaseUrl}/api/projects/local-draft/jobs/capcut-draft-export`)).status()).toBe(400);
});

test("ready-assets approval uses returned IDs and provides current-revision playback and CapCut smoke", async ({ page }) => {
  await reset(page);
  expect((await page.request.post(`${fakeApiBaseUrl}/api/projects/local-draft/draft-readiness/broll/upload`)).status()).toBe(201);
  expect((await page.request.post(`${fakeApiBaseUrl}/api/projects/local-draft/draft-readiness/readiness_e2e/complete`)).status()).toBe(200);
  const requested = [];
  page.on("request", (request) => requested.push(new URL(request.url()).hostname));
  await page.goto("/projects/local-draft/create");
  await page.getByRole("button", { name: "초안 만들기" }).click();
  const state = await (await page.request.get(`${fakeApiBaseUrl}/__e2e/draft-state`)).json();
  expect(state.latest_bundle.output_blocked).toBeFalsy();
  expect(state.latest_bundle.gap_slots).toEqual([]);
  await expect(page).toHaveURL(new RegExp(`/editor\\?session_id=${state.latest_bundle.session_id}$`));
  const video = page.getByLabel("편집본 미리보기");
  await expect(video).toHaveAttribute("src", new RegExp(`/final-renders/final-e2e-\\d+/content$`));
  const playback = await video.evaluate((element) => new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => reject(new Error("video metadata did not load")), 5000);
    element.addEventListener("loadedmetadata", () => {
      window.clearTimeout(timeout);
      resolve({ src: element.currentSrc, controls: element.controls, duration: element.duration });
    }, { once: true });
    element.addEventListener("error", () => {
      window.clearTimeout(timeout);
      reject(new Error("video failed to load"));
    }, { once: true });
    element.load();
  }));
  expect(playback.src).toContain(`/final-renders/final-e2e-${state.latest_bundle.bundle_id.split("-").at(-1)}/content`);
  expect(playback.controls).toBeTruthy();
  expect(playback.duration).toBeGreaterThan(0);
  const handoff = await page.request.post(`${fakeApiBaseUrl}/api/projects/local-draft/capcut-draft-exports/capcut-e2e/handoff`);
  expect((await handoff.json()).handoff.status).toBe("registered");
  expect(requested.every((host) => host === "127.0.0.1" || host === "localhost")).toBeTruthy();
});
