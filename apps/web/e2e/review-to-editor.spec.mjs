import { expect, test } from "./support/test-fixtures.mjs";

const fakeApiBaseUrl = `http://127.0.0.1:${Number(process.env.PLAYWRIGHT_FAKE_API_PORT ?? 8000)}`;

test("a review segment opens the pinned editor and selects that exact narration segment", async ({ page }) => {
  expect((await page.request.post(`${fakeApiBaseUrl}/api/projects/local-draft/draft-readiness/broll/upload`)).status()).toBe(201);
  expect((await page.request.post(`${fakeApiBaseUrl}/api/projects/local-draft/draft-readiness/readiness_e2e/complete`)).status()).toBe(200);
  expect((await page.request.post(`${fakeApiBaseUrl}/api/projects/local-draft/draft-bundles`)).status()).toBe(201);
  expect((await page.request.post(`${fakeApiBaseUrl}/__e2e/reset-review`)).status()).toBe(200);
  const resetState = await (await page.request.get(`${fakeApiBaseUrl}/__e2e/draft-state`)).json();
  expect(resetState).toMatchObject({
    uploaded_broll: false,
    bundle_sequence: 0,
    latest_bundle: null,
    readiness: { status: "needs_assets", revision: 1 },
    atomic_session: {
      session_id: "editing_session_e2e",
      project_id: "local-draft",
      timeline_id: "timeline_e2e",
      session_revision: 1,
      history: [],
      undo_count: 0,
      redo_count: 0,
    },
  });
  expect(resetState.atomic_session.segments).toHaveLength(1);
  expect(resetState.jobs).toHaveLength(2);
  await page.goto("/projects/local-draft/review");

  const segmentLink = page.getByRole("link", { name: "여름 여행을 소개합니다. 편집하기" });
  await expect(segmentLink).toHaveAttribute(
    "href",
    "/projects/local-draft/editor?session_id=editing_session_e2e&segment_id=segment-e2e",
  );
  await page.evaluate(() => {
    window.__videoboxReviewSpaSentinel = "alive";
    document.documentElement.dataset.videoboxReviewSpaSentinel = "alive";
  });
  await segmentLink.click();

  await expect(page).toHaveURL(/\/projects\/local-draft\/editor\?session_id=editing_session_e2e&segment_id=segment-e2e$/);
  expect(await page.evaluate(() => ({
    windowSentinel: window.__videoboxReviewSpaSentinel,
    documentSentinel: document.documentElement.dataset.videoboxReviewSpaSentinel,
  }))).toEqual({ windowSentinel: "alive", documentSentinel: "alive" });
  await expect(page.getByRole("region", { name: "편집 작업판" })).toBeVisible();
  await expect(page.getByRole("button", { name: "narration-e2e 클립 선택" })).toHaveAttribute("aria-pressed", "true");
});
