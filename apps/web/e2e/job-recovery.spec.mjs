import { expect, test } from "./support/test-fixtures.mjs";

const fakeApiBaseUrl = `http://127.0.0.1:${Number(process.env.PLAYWRIGHT_FAKE_API_PORT ?? 8000)}`;

test("job status lazily retries a global row with the row project and refreshes global truth", async ({ page }) => {
  expect((await page.request.post(`${fakeApiBaseUrl}/__e2e/reset-jobs`)).status()).toBe(200);
  await page.goto("/projects/local-draft/home");

  await page.getByRole("button", { name: "작업 상태" }).click();
  const dialog = page.getByRole("dialog", { name: "작업 상태" });
  const recovery = page.getByRole("region", { name: "작업 복구" });
  await expect(recovery.getByText("음성 받아쓰기")).toBeVisible();
  await recovery.getByRole("button", { name: "모든 프로젝트" }).click();
  await expect(recovery.getByText("보관한 영상")).toBeVisible();

  let releaseRetry;
  let retryRequestCount = 0;
  await page.route("**/api/projects/archive-project/jobs/job-recovery-global/retry", async (route) => {
    retryRequestCount += 1;
    await new Promise((resolve) => { releaseRetry = resolve; });
    await route.continue();
  });
  await recovery.getByRole("button", { name: "다시 실행" }).click();
  await expect.poll(() => retryRequestCount).toBe(1);
  await expect(dialog.getByRole("button", { name: "Close" })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible();
  await expect(recovery.getByRole("button", { name: "다시 실행" })).toBeDisabled();
  releaseRetry();

  await expect(recovery.getByText("작업을 다시 시작했어요. 최신 상태를 확인했습니다.")).toBeVisible();
  await expect(recovery.getByText("완료됐어요")).toBeVisible();
  await expect(recovery.getByRole("button", { name: "다시 실행" })).toHaveCount(0);
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(dialog).toHaveCount(0);
  await page.getByRole("button", { name: "작업 상태" }).click();
  await expect(page.getByRole("dialog", { name: "작업 상태" })).toBeVisible();
  expect(retryRequestCount).toBe(1);

  const state = await (await page.request.get(`${fakeApiBaseUrl}/__e2e/job-state`)).json();
  expect(state).toMatchObject({
    retry_count: 1,
    retried_project_id: "archive-project",
    retried_job_id: "job-recovery-global",
  });
  expect(state.global_jobs).toEqual(expect.arrayContaining([
    expect.objectContaining({ job_id: "job-recovery-global", status: "failed" }),
    expect.objectContaining({ job_id: "job-recovery-global-retry", status: "succeeded" }),
  ]));
  expect(state.global_list_count).toBeGreaterThanOrEqual(2);
});
