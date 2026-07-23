import { expect, test } from "./support/test-fixtures.mjs";
import { installFixedClock, playwrightSnapshotOptions, waitForStableCapture } from "./support/fixed-clock.mjs";

const loopbackHosts = new Set(["127.0.0.1", "localhost", "[::1]"]);
const snapshots = [
  [1920, 1080],
  [1440, 960],
  [1280, 800],
  [768, 1024],
  [390, 844],
];

async function blockExternalNetwork(page) {
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.protocol === "data:" || loopbackHosts.has(url.hostname)) return route.continue();
    return route.abort("blockedbyclient");
  });
}

test.beforeEach(async ({ page }) => {
  await installFixedClock(page);
  await blockExternalNetwork(page);
});

test("local catalog renders the creator shell without an external request", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/projects/local-draft/home");

  await expect(page.getByRole("button", { name: "작업 상태" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "다음 장면을 이어서 만들어 볼까요?" })).toBeVisible();
  await expect(page.getByText("작업 중인 초안 계속하기")).toBeVisible();
  await expect(page.getByText(/provider|billing|account/i)).toHaveCount(0);
});

test("an empty local catalog leads to the single project-start action", async ({ page }) => {
  await page.route("**/api/projects", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ projects: [] }) });
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "영상 만들기 시작" })).toBeVisible();
  await expect(page.getByRole("button", { name: "프로젝트 만들고 소스 등록" })).toBeVisible();
});

test("mobile menu exposes the same creator navigation", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/projects/local-draft/home");
  await page.getByRole("button", { name: "메뉴 열기" }).click();

  const menu = page.getByRole("dialog");
  await expect(menu.getByRole("button", { name: "자산" })).toBeVisible();
  await menu.getByRole("button", { name: "자산" }).click();
  await expect(page).toHaveURL(/\/projects\/local-draft\/media$/);
  await expect(page.getByRole("heading", { name: "자산 보관함" })).toBeVisible();
});

test("mobile Sheet closes with Escape and returns focus, while the desktop rail collapses", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/projects/local-draft/home");
  const trigger = page.getByRole("button", { name: "메뉴 열기" });
  await trigger.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(trigger).toBeFocused();

  await page.setViewportSize({ width: 1280, height: 800 });
  await page.reload();
  const sidebar = page.locator('[data-slot="sidebar"]').first();
  await expect(sidebar).toHaveAttribute("data-state", "expanded");
  await page.getByRole("button", { name: "사이드바 접기" }).click();
  await expect(sidebar).toHaveAttribute("data-state", "collapsed");
});

test("Home empty-state actions and settings tabs follow their visible routes", async ({ page }) => {
  await page.goto("/projects/local-draft/home");
  await page.getByRole("button", { name: "자산 준비하기" }).click();
  await expect(page).toHaveURL(/\/projects\/local-draft\/media$/);
  await page.goto("/settings/general");
  await page.getByRole("button", { name: "화면" }).click();
  await expect(page).toHaveURL(/\/settings\/appearance$/);
});

test("approved brief prepares a local draft without an editing-session mutation", async ({ page }) => {
  const editingMutations = [];
  page.on("request", (request) => { if (request.url().includes("/editing-sessions") && request.method() !== "GET") editingMutations.push(request.url()); });
  await page.addInitScript(() => { localStorage.setItem("videobox.creation-brief.local-draft", "brief-e2e"); localStorage.setItem("videobox.draft-readiness.local-draft", "readiness_e2e"); });
  await page.goto("/projects/local-draft/create");
  await expect(page.getByRole("heading", { name: "추가 자산이 필요해요" })).toBeVisible();
  const addAssets = page.getByRole("link", { name: "자산 추가" });
  await expect(addAssets).toHaveAttribute("href", /return_to=/);
  await addAssets.click();
  await expect(page.getByRole("heading", { name: "장면 영상 추가" })).toBeVisible();
  await page.locator("#gap-broll-file").setInputFiles({ name: "beach.mp4", mimeType: "video/mp4", buffer: Buffer.from("local-video") });
  await page.getByRole("button", { name: "영상 추가" }).click();
  await expect(page.getByText("영상 추가를 확인했어요. 기획으로 돌아가 다시 준비해 주세요.")).toBeVisible();
  await expect(page.getByRole("button", { name: "기획으로 돌아가기" })).toBeVisible();
  await page.getByRole("button", { name: "기획으로 돌아가기" }).click();
  await expect(page.getByRole("button", { name: "다시 준비" })).toBeVisible();
  await page.getByRole("button", { name: "다시 준비" }).click();
  await expect(page.getByRole("heading", { name: "초안이 준비됐어요" })).toBeVisible();
  await expect(page.getByRole("button", { name: /해변 장면 미리보기/ })).toBeVisible();
  expect(editingMutations).toEqual([]);
});

for (const [width, height] of snapshots) {
  test(`captures deterministic local shell at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.goto("/projects/local-draft/home");
    await expect(page.getByTestId("product-home")).toBeVisible();
    await waitForStableCapture(page);
    await page.screenshot(playwrightSnapshotOptions(`e2e/snapshots/product-shell-${width}.png`));
  });
}
