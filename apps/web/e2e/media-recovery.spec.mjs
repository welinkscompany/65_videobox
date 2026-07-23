import { expect, test } from "./support/test-fixtures.mjs";

const fakeApiBaseUrl = `http://127.0.0.1:${Number(process.env.PLAYWRIGHT_FAKE_API_PORT ?? 8000)}`;

test("the canonical media workspace previews and recovers local analysis with authoritative refreshes", async ({ page }) => {
  expect((await page.request.post(`${fakeApiBaseUrl}/__e2e/reset-media`)).status()).toBe(200);
  await page.goto("/projects/local-draft/media");

  await expect(page.getByRole("heading", { name: "자산 보관함" })).toBeVisible();
  await expect(page.getByText("항구 전경", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("분석을 마치지 못했어요 · 100%")).toBeVisible();

  await page.getByRole("article", { name: "항구 전경 분석" }).getByRole("button", { name: "미리보기" }).click();
  await expect(page.getByText("미리보기 길이 4초")).toBeVisible();

  await page.getByRole("button", { name: "분석 멈추기" }).click();
  await expect(page.getByText("분석을 멈췄어요 · 50%")).toBeVisible();
  await page.getByRole("button", { name: "다시 분석하기" }).click();
  await expect(page.getByText("분석을 기다리고 있어요 · 100%")).toBeVisible();

  await page.getByLabel("미디어 3 태그").fill("항구, 여행");
  await page.getByRole("button", { name: "태그 확인" }).click();
  await expect(page.getByRole("article", { name: "회의 장면 분석" }).getByText("준비가 끝났어요 · 100%")).toBeVisible();

  const state = await (await page.request.get(`${fakeApiBaseUrl}/__e2e/media-state`)).json();
  expect(state).toMatchObject({
    preview_count: 1,
    preview_asset_id: "asset-media-preview",
    cancel_count: 1,
    retry_count: 1,
    review_count: 1,
    review_body: { tags: { place: ["항구", "여행"] } },
  });
  expect(state.asset_list_count).toBeGreaterThanOrEqual(4);
  expect(state.analysis_list_count).toBeGreaterThanOrEqual(4);
});
