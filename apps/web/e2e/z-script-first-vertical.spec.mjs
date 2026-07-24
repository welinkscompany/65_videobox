import { expect, test } from "./support/test-fixtures.mjs";

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
  page.on("request", (request) => requested.push(request.url()));
  await page.goto("/projects/local-draft/create");
  await page.getByRole("button", { name: "초안 만들기" }).click();
  const state = await (await page.request.get(`${fakeApiBaseUrl}/__e2e/draft-state`)).json();
  expect(state.latest_bundle.output_blocked).toBeFalsy();
  expect(state.latest_bundle.gap_slots).toEqual([]);
  await expect(page).toHaveURL(new RegExp(`/editor\\?session_id=${state.latest_bundle.session_id}$`));
  const video = page.getByLabel("편집본 미리보기");
  await expect(video).toHaveAttribute("src", new RegExp(`/exact-previews/exact-e2e-\\d+-r1/content$`));
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
  expect(playback.src).toContain(`/exact-previews/exact-e2e-${state.latest_bundle.bundle_id.split("-").at(-1)}-r1/content`);
  expect(playback.controls).toBeTruthy();
  expect(playback.duration).toBeGreaterThan(0);

  await page.goto("/projects/local-draft/outputs");
  await expect(page.getByText("현재 편집본 미리보기가 준비되었어요.")).toBeVisible();
  await expect(page.getByText("자막이 준비되었어요.")).toBeVisible();
  await expect(page.getByLabel("완성본 재생")).toBeVisible();
  await expect(page.getByText("CapCut 초안이 준비되었어요.")).toBeVisible();
  await expect(page.getByText("실제 CapCut Desktop에서 열기와 가져오기는 별도로 확인해야 해요.")).toBeVisible();
  await expect(page.locator("audio")).toHaveCount(0);
  await expect(page.locator("video")).toHaveCount(1);
  await page.getByRole("button", { name: "CapCut에 등록" }).click();
  await expect(page.getByText("CapCut 등록 상태가 준비되었어요.")).toBeVisible();

  expect((await page.request.post(`${fakeApiBaseUrl}/__e2e/mark-outputs-stale`)).status()).toBe(200);
  await page.getByRole("button", { name: "상태 다시 확인" }).click();
  await expect(page.getByText("미리보기가 최신 편집본과 달라요.")).toBeVisible();
  await expect(page.getByText("완성본이 최신 편집본과 달라요.")).toBeVisible();
  await expect(page.getByText("CapCut 초안이 최신 편집본과 달라요.")).toBeVisible();
  await expect(page.getByRole("button", { name: "CapCut에 등록" })).toHaveCount(0);
  await page.getByRole("button", { name: "편집에서 미리보기 열기" }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/local-draft/editor\\?session_id=${state.latest_bundle.session_id}$`));

  await page.goto("/projects/local-draft/outputs");
  await expect(page.getByText("미리보기가 최신 편집본과 달라요.")).toBeVisible();
  const recoveredOutputs = await (await page.request.post(`${fakeApiBaseUrl}/__e2e/mark-outputs-current`)).json();
  expect(recoveredOutputs.output_ids.final).toMatch(/-r2$/);
  await page.getByRole("button", { name: "상태 다시 확인" }).click();
  await expect(page.getByText("현재 편집본 미리보기가 준비되었어요.")).toBeVisible();
  await expect(page.getByText("완성본을 확인할 수 있어요.")).toBeVisible();
  await expect(page.getByText("CapCut 초안이 준비되었어요.")).toBeVisible();
  await expect(page.getByLabel("완성본 재생")).toHaveAttribute("src", new RegExp(`${recoveredOutputs.output_ids.final}/content$`));
  await expect(page.getByText(`로컬 저장 위치: local://${recoveredOutputs.output_ids.capcut}`)).toBeVisible();
  await page.getByRole("button", { name: "편집에서 미리보기 열기" }).click();
  await expect(page.getByLabel("편집본 미리보기")).toHaveAttribute("src", new RegExp(`${recoveredOutputs.output_ids.exact}/content$`));

  expect(requested.every((requestUrl) => {
    const parsed = new URL(requestUrl);
    return parsed.hostname === "127.0.0.1" || parsed.hostname === "localhost";
  })).toBeTruthy();
  expect(requested.some((requestUrl) => requestUrl.includes("/jobs/preview-render") || requestUrl.includes("/jobs/capcut-export"))).toBeFalsy();
});
