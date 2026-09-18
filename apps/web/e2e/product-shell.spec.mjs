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
  // "전체 메뉴"(접힌 단추)는 `home` 화면에는 더 이상 없다(owner 지시
  // 2026-09-05, `docs/decisions/2026-09-05-one-way-to-start.ko.md`가 가리키는
  // `SideNav` 상시 세로 메뉴로 대체됐다 -- 캡컷처럼 자료실·촬영본 정리가 한
  // 번 더 접히지 않고 첫 화면에 상시 보인다). 접힌 메뉴는 단계 화면(이야기·
  // 편집·확인과 내보내기)에만 남아 있고, 아래 세 번째 시험이 그걸 검증한다.
  await expect(page.getByRole("navigation", { name: "화면 이동" })).toBeVisible();
  await expect(page.getByText(/provider|billing|account/i)).toHaveCount(0);
});

test("an empty local catalog keeps project creation in the catalog shell", async ({ page }) => {
  await page.route("**/api/projects", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ projects: [] }) });
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "프로젝트" })).toBeVisible();
  // 문구는 "+ 새 프로젝트 만들기"에서 "+ 새로 만들기"로 바뀌었다(owner 재지시
  // 2026-08-30, `+ 새 프로젝트 만들기`는 그 시점에 편집기로 바로 가는 지름길이
  // 됐다 -- 이름을 안 묻는다). "시작하는 문은 하나다" 결정(2026-09-05)도 이
  // 단추 하나로 시작을 모은다.
  await expect(page.getByRole("button", { name: "+ 새로 만들기" })).toBeVisible();
});

test("desktop shell keeps global destinations separate from the open project's three stages", async ({ page }) => {
  // 왼쪽 기둥은 없앴다 -- 위 띠 하나가 그 일을 받는다
  // (docs/decisions/2026-08-21-capcut-shell-layout.ko.md, owner 승인 2026-08-21).
  // 구분은 그대로다: 전역 목적지는 한 겹 접힌 메뉴 안, 단계는 띠 위에 펼쳐져 있다.
  //
  // **"home"이 아니라 "create" 단계에서 확인한다(2026-09-18 갱신).**
  // 2026-09-05 이후 `home`(프로젝트 목록) 화면은 상시 `SideNav`(`화면 이동`)를
  // 쓰고 접힌 "전체 메뉴"를 `hideGlobalMenu`로 숨긴다(`ProductShell.tsx`
  // `sideNavPlace`). 접힌 "전체 메뉴"는 지금도 단계 화면(이야기·편집·확인과
  // 내보내기)에는 그대로 남아 있다 -- `SideNav`가 그 자리를 대신 그리지 않는
  // 화면들이다. 이 시험이 지키려는 것("전역 목적지는 접힌 메뉴 안")은 그
  // 화면들에서 확인해야 실제로 지켜지는 것을 잰다.
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/projects/local-draft/create");
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
  // "미디어" 단계 단추는 없다(2026-09-01) -- 독립 화면이 편집기 도크로
  // 접히면서 따로 갈 화면이 아니게 됐다.
  await expect(page.getByRole("navigation", { name: "프로젝트 단계" }).getByRole("button")).toHaveCount(3);
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
  //
  // "미디어" 단계 단추는 없다(2026-09-01, 독립 화면이 편집기로 접혔다) --
  // 남은 단계("편집") 하나로 같은 것(좁은 화면에서도 단계 단추가 바로
  // 눌린다)을 확인한다.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/projects/local-draft/home");
  await page.getByRole("button", { name: "편집" }).click();
  await expect(page).toHaveURL(/\/projects\/local-draft\/editor/);
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
  await expect(page.getByRole("heading", { name: "추가 미디어가 필요해요" })).toBeVisible();
  const addAssets = page.getByRole("link", { name: "미디어 추가" });
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
