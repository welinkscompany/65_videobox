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
  await expect(page.getByRole("heading", { name: "어떻게 시작할까요?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "전체 메뉴" })).toBeVisible();
  await expect(page.getByText(/provider|billing|account/i)).toHaveCount(0);
});

test("an empty local catalog keeps project creation in the catalog shell", async ({ page }) => {
  await page.route("**/api/projects", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ projects: [] }) });
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "프로젝트" })).toBeVisible();
  await expect(page.getByRole("button", { name: "+ 새 프로젝트 만들기" })).toBeVisible();
});

test("desktop shell keeps global destinations separate from the open project's four stages", async ({ page }) => {
  // 왼쪽 기둥은 없앴다 -- 위 띠 하나가 그 일을 받는다
  // (docs/decisions/2026-08-21-capcut-shell-layout.ko.md, owner 승인 2026-08-21).
  // 구분은 그대로다: 전역 목적지는 한 겹 접힌 메뉴 안, 단계는 띠 위에 펼쳐져 있다.
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/projects/local-draft/home");
  await expect(page.getByRole("navigation", { name: "전체 메뉴" })).toHaveCount(0);
  const menuTrigger = page.getByRole("button", { name: "전체 메뉴", exact: true });
  await expect(menuTrigger).toHaveAttribute("aria-expanded", "false");
  await menuTrigger.click();
  const menu = page.getByRole("navigation", { name: "전체 메뉴" });
  await expect(menu.getByRole("link")).toHaveCount(3);
  await expect(menu.getByRole("button", { name: "설정" })).toBeVisible();
  await expect(menuTrigger).toHaveAttribute("aria-expanded", "true");
  await page.keyboard.press("Escape");
  await expect(menu).toHaveCount(0);
  await expect(menuTrigger).toBeFocused();
  await expect(page.getByRole("navigation", { name: "프로젝트 단계" }).getByRole("button")).toHaveCount(4);
});

test("unknown project route offers canonical recovery without a project-scoped request", async ({ page }) => {
  const projectScopedRequests = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/projects/missing-project/")) projectScopedRequests.push(request.url());
  });

  await page.goto("/projects/missing-project/home");

  await expect(page.getByRole("heading", { name: "프로젝트를 찾을 수 없어요" })).toBeVisible();
  await page.getByRole("button", { name: "여름 여행 영상" }).click();
  await expect(page).toHaveURL(/\/projects\/local-draft\/home$/);
  expect(projectScopedRequests).toEqual([]);
});

test("the top bar keeps creator navigation reachable on a narrow screen", async ({ page }) => {
  // 좁은 화면에서도 띠는 그대로 있다. 기둥 시절에는 Sheet로 접혀 있어서 단계를
  // 누르기 전에 `메뉴 열기`를 먼저 눌러야 했다. 그 한 겹이 없어졌다.
  // Sheet와 접기 띠(`SidebarRail`)를 잡던 시험도 함께 지웠다 -- 지킬 대상이 없다.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/projects/local-draft/home");
  await page.getByRole("button", { name: "재료" }).click();
  await expect(page).toHaveURL(/\/projects\/local-draft\/media$/);
  await expect(page.getByRole("heading", { name: "자산 보관함" })).toBeVisible();
});

test("Home start choices and settings tabs follow their visible routes", async ({ page }) => {
  await page.goto("/projects/local-draft/home");
  for (const name of ["대본이 있어요", "찍어 둔 영상이 있어요", "아직 아무것도 없어요"]) {
    await expect(page.getByRole("button", { name: new RegExp(`^${name}`) })).toBeVisible();
  }
  await page.getByRole("button", { name: /^찍어 둔 영상이 있어요/ }).click();
  await expect(page).toHaveURL(/\/projects\/local-draft\/create$/);
  await page.goto("/projects/local-draft/home");
  await page.getByRole("button", { name: /^아직 아무것도 없어요/ }).click();
  await expect(page).toHaveURL(/\/projects\/local-draft\/create$/);
  await page.goto("/settings/general");
  await page.getByTestId("settings-page").getByRole("button", { name: "화면", exact: true }).click();
  await expect(page).toHaveURL(/\/settings\/appearance\?project_id=local-draft$/);
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
