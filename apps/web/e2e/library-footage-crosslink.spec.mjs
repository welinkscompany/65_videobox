import { expect, test } from "./support/test-fixtures.mjs";

// 2026-08-16까지 /footage에는 E2E가 전혀 없었고, /library<->footage 교차 링크도
// 자동 검증이 없었다(수동 브라우저 확인뿐). 이 스펙이 둘 다 처음 메운다.
// 카드 레벨 진입점(선택 없이 바로 클릭 가능)까지 다룬다는 점이 기존 미리보기
// 패널 전용 링크와의 차이다.

function asset({ id, name, duration = 12 }) {
  return {
    library_asset_id: id,
    asset_id: id,
    media_type: "broll",
    origin: "user",
    lifecycle: "ready",
    content_sha256: id.padEnd(64, "0").slice(0, 64),
    byte_count: 32,
    mime_type: "video/mp4",
    managed_relative_path: `assets/${id}`,
    technical_metadata: { duration_seconds: duration, width: 1920, height: 1080 },
    machine_metadata: { description: name },
    user_metadata: { filename: name, tags: [] },
    created_at: "2026-08-12T00:00:00Z",
    updated_at: "2026-08-12T00:00:00Z",
    trashed_at: null,
    preview_url: `/api/library/assets/${id}/preview`,
    thumbnail_url: `/api/library/assets/${id}/thumbnail`,
    waveform_url: null,
  };
}

const first = asset({ id: "asset-first", name: "commute.mp4", duration: 12 });
const second = asset({ id: "asset-second", name: "walkthrough.mp4", duration: 8 });

async function installApi(page, { usageLocations = [] } = {}) {
  await page.route("**/api/library/assets/*/usage", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ library_asset_id: "ignored", locations: usageLocations }) });
  });
  await page.route("**/api/library/assets?**", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ assets: [first, second], total: 2 }) });
  });
}

test("library card crosslink selects the source on /footage without requiring a prior click", async ({ page }) => {
  await installApi(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/library");
  await expect(page.getByTestId("library-workspace")).toBeVisible();

  const card = page.locator('[data-testid="library-asset-card"]').filter({ hasText: second.user_metadata.filename });
  const crosslink = card.getByRole("link", { name: "구간 정리하기" });
  await expect(crosslink).toHaveAttribute("href", `/footage?library_asset_id=${second.library_asset_id}`);
  await crosslink.click();

  await expect(page.getByTestId("footage-workspace")).toBeVisible();
  await expect(page.getByRole("heading", { name: second.user_metadata.filename })).toBeVisible();
});

test("footage source-list crosslink returns to /library with the same asset selected", async ({ page }) => {
  await installApi(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(`/footage?library_asset_id=${first.library_asset_id}`);
  await expect(page.getByTestId("footage-workspace")).toBeVisible();
  await expect(page.getByRole("heading", { name: first.user_metadata.filename })).toBeVisible();

  const sourceRow = page.getByTestId("footage-source-list").locator(".vb-footage-source-row").filter({ hasText: first.user_metadata.filename });
  const crosslink = sourceRow.getByRole("link", { name: `${first.user_metadata.filename} 라이브러리에서 보기` });
  await expect(crosslink).toHaveAttribute("href", `/library?library_asset_id=${first.library_asset_id}`);
  await crosslink.click();

  await expect(page.getByTestId("library-workspace")).toBeVisible();
  await expect(page.getByTestId("library-preview-player")).toBeVisible();
  await expect(page.getByRole("heading", { name: first.user_metadata.filename })).toBeVisible();
});

test("the crosslink is available on every card without first selecting one", async ({ page }) => {
  await installApi(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/library");
  await expect(page.getByTestId("library-workspace")).toBeVisible();

  // No card click happened yet -- the default selection (first asset) must
  // not be a prerequisite for the second card's own crosslink to work.
  const links = page.locator('[data-testid="library-asset-card"]').getByRole("link", { name: "구간 정리하기" });
  await expect(links).toHaveCount(2);
});

test("a library asset's in-use location links to that project's assets screen", async ({ page }) => {
  // 위치를 알려주면서 갈 길은 안 주면 owner가 다시 찾아 헤맨다. 이 링크가
  // 라이브러리 -> 프로젝트 방향을 닫는다(반대 방향은 프로젝트 자산 화면의
  // "라이브러리 영상" 고르기가 담당한다).
  await installApi(page, {
    usageLocations: [
      { project_id: "my-project", materialized_asset_id: "asset-copy", reference_id: "ref-1", location: { kind: "project_asset", label: "프로젝트 편집본" } },
      { location: { kind: "derived_sequence", label: "묶음" } },
    ],
  });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/library");
  await page.locator('[data-testid="library-asset-card"]').filter({ hasText: first.user_metadata.filename }).click();

  const usage = page.locator(".vb-library-usage");
  await expect(usage).toBeVisible();
  const entry = usage.getByRole("link", { name: "프로젝트 편집본 미디어 화면 열기" });
  await expect(entry).toHaveAttribute("href", "/projects/my-project/assets");
  // 프로젝트를 특정할 수 없는 위치는 링크가 되지 않는다.
  await expect(usage.getByText("묶음")).toBeVisible();
  await expect(usage.getByRole("link", { name: /묶음/ })).toHaveCount(0);
});
