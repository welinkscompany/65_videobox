import { expect, test } from "./support/test-fixtures.mjs";

const fakeApiBaseUrl = `http://127.0.0.1:${Number(process.env.PLAYWRIGHT_FAKE_API_PORT ?? 8000)}`;

test("the editor's media dock previews and recovers local analysis with authoritative refreshes", async ({ page }) => {
  // 독립 "미디어" 단계 화면은 편집기 도크로 접혔다(2026-09-01,
  // `docs/decisions/2026-08-27-editor-centered-shell-direction.ko.md` §순서 2
  // 실행). `/projects/local-draft/media`는 이제 편집기로 리다이렉트되고
  // (`workspaceRoute` beforeLoad -> `CanonicalEditorEntry`가 이 프로젝트의
  // 기존 세션을 찾아 곧바로 편집기를 연다), 도크가 이미 미디어 탭 기본값이라
  // 여기서 곧바로 같은 자산·분석 목록을 본다.
  expect((await page.request.post(`${fakeApiBaseUrl}/__e2e/reset-media`)).status()).toBe(200);
  await page.goto("/projects/local-draft/media");

  await expect(page.getByRole("tab", { name: "미디어" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText("항구 전경", { exact: true }).first()).toBeVisible();
  // 분석 상태 패널은 네이티브 `<details>`로 접혀 있다(`EditorAssetBrowser.tsx`:
  // `pane === "media" && analysisPanel ? <details className="vb-editor-assets__aside">
  // <summary>미디어 분석</summary>{analysisPanel}</details>`). 기본으로
  // 닫혀 있으니 안의 상태 문구는 열기 전까지 `hidden`이다.
  await page.getByText("미디어 분석", { exact: true }).click();
  await expect(page.getByText("분석을 마치지 못했어요 · 100%")).toBeVisible();

  await page.getByRole("article", { name: "항구 전경 분석" }).getByRole("button", { name: "미리보기" }).click();
  await expect(page.getByText("미리보기 길이 4초")).toBeVisible();

  await page.getByRole("button", { name: "분석 멈추기" }).click();
  await expect(page.getByText("분석을 멈췄어요 · 50%")).toBeVisible();
  await page.getByRole("button", { name: "다시 분석하기" }).click();
  await expect(page.getByText("분석을 기다리고 있어요 · 100%")).toBeVisible();

  // `assetTitle()`은 자산에 실제 제목(`metadata.title`)이 있으면 그것을 쓰고
  // "미디어 N"은 제목이 없을 때만 쓰는 대체다(`MediaAnalysisStatusPanel.tsx`).
  // 확인이 필요한 이 자산은 fake-api-server 시드에 제목 "회의 장면"이 있다
  // (`asset-media-review`) -- 그래서 칸 이름은 "미디어 3 태그"가 아니라
  // "회의 장면 태그"다.
  await page.getByLabel("회의 장면 태그").fill("항구, 여행");
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
