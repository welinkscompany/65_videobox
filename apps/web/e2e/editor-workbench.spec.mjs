import { expect, test } from "./support/test-fixtures.mjs";
import { installFixedClock, playwrightSnapshotOptions, waitForStableCapture } from "./support/fixed-clock.mjs";

const snapshots = [[1920, 1080], [1440, 900], [1280, 800], [768, 1024], [390, 844]];
const manifest = { project_id: "local-draft", session_id: "editor-workbench-e2e", timeline_id: "timeline-e2e", session_revision: 7, timeline_version: "v7", timebase: "seconds", fps: { num: 30, den: 1 }, output: { width: 1080, height: 1920, sample_aspect_ratio: "1:1", rotation: 0, duration_sec: 12 }, tracks: [{ track_id: "narration", track_type: "narration", clips: [{ clip_id: "clip-1", segment_id: "segment-1", clip_type: "narration", asset_id: "asset-1", asset_uri: "local://asset-1", start_sec: 0, end_sec: 12, media_controls: {} }] }], captions: [{ segment_id: "segment-1", text: "여름 여행을 소개합니다.", start_sec: 0, end_sec: 12, style: { font_family: "Pretendard", font_size_px: 24, text_color: "#fff", outline_color: "#000", outline_width_px: 1, background_color: "#00000000", position_x_percent: 50, position_y_percent: 90, horizontal_align: "center", safe_area_enabled: true, shadow_blur_px: 0 } }], gap_slots: [], source_status: { status: "current", source_session_id: "editor-workbench-e2e", source_session_revision: 7 }, audition: { asset_urls: {} }, exact_preview: { status: "unavailable", url: null, source_session_id: "editor-workbench-e2e", source_session_revision: 7 } };
const editingSession = {
  project_id: "local-draft",
  session_id: "editor-workbench-e2e",
  timeline_id: "timeline-e2e",
  session_revision: 7,
  undo_count: 0,
  redo_count: 0,
  updated_at: "2026-07-24T00:00:00Z",
  history: [],
  segments: [{
    segment_id: "segment-1",
    start_sec: 0,
    end_sec: 12,
    caption_text: "여름 여행을 소개합니다.",
    cut_action: "keep",
    review_required: false,
    broll_override: null,
    music_override: null,
    sfx_override: null,
    tts_replacement: null,
    visual_overlays: [],
  }],
};
const yujinCaptionProposal = {
  proposal_id: "yujin-caption-text",
  revision_code: "P01",
  revision: 1,
  base_session_revision: 7,
  asset_index_revision: 1,
  source_session_id: "editor-workbench-e2e",
  target_segment_ids: ["segment-1"],
  source_script_segment_ids: ["segment-1"],
  status: "ready",
  diff: { proposal_mode: "yujin_actionable_v1" },
  expires_at: null,
  candidates: [{
    candidate_id: "candidate-caption-text",
    visible_reference_code: "P01-CAPTION-TEXT-01",
    media_type: "caption",
    asset_id: "candidate-caption-text",
    library_asset_id: null,
    reason_chips: ["읽기 쉬운 자막"],
    scores: {},
    availability: "actionable",
    review_status: "approved",
    preview_uri: null,
    controls: { text: "추천 자막으로 바꿉니다." },
    expected_content_sha256: null,
    media_revision: "r1",
    canonical_metadata: {
      schema_version: "videobox.yujin-response.v1",
      yujin_actionable_operation: true,
      command_kind: "set_caption_text",
      target_segment_id: "segment-1",
      requires_materialization: false,
      base_session_revision: 7,
      asset_index_revision: 1,
    },
    license_policy: "local",
    warning_provenance: [],
  }],
};
const outputVariant = {
  variant_id: "vertical-full",
  kind: "vertical_full",
  source_session_id: "editor-workbench-e2e",
  source_session_revision: 7,
  variant_revision: 1,
  overrides: { crop: null, focal: null, caption: null, safe_area: null, audio: null },
  locks: [],
  conflicts: [],
  selected_segment_ids: null,
  master_segment_ids: ["segment-1"],
};
const horizontalVariant = { ...outputVariant, variant_id: "horizontal", kind: "horizontal" };

// 왼쪽 미디어 열은 기본으로 펴져 있다(owner 승인 2026-08-17). 도크 버튼은 토글이라
// 무조건 누르면 **열린 것을 닫아 버린다.** 도크를 여는 것이 목적인 자리에서는
// 닫혀 있을 때만 누른다.
// 첫 프레임은 작업판 폭이 아직 0이라 잠깐 `drawer`로 잡히고, 그 순간에는 펴져 있는
// 도크도 DOM에 없다. 폭이 측정된 뒤에 판단하지 않으면 열린 것을 닫힌 것으로 읽고
// 눌러서 닫아 버린다 -- 2026-08-17 세 번째 시도가 여기서 실패가 늘었다.
async function ensureDockOpen(page, name) {
  await expect
    .poll(async () => Number(await page.getByRole("region", { name: "편집 작업판" }).getAttribute("data-available-workbench-width")))
    .toBeGreaterThan(0);
  if (await page.getByRole("complementary", { name }).count()) return;
  await page.getByRole("button", { name }).click();
}

// 유진 패널은 "세부 정보" 도크와 더 이상 같은 것이 아니다(owner 지시
// 2026-08-30, `EditorWorkbench.tsx`: "캡컷 EditPilot처럼 도크와 무관하게
// 화면 구석에 뜬다"). "세부 정보"는 기본으로 캡션·컷 편집 패널("편집 항목")을
// 보여주고, 유진 대화창은 따로 있는 "유진" 단추로 연다 -- 둘은 독립된 열림
// 상태를 갖는다(`yujinOpen`/`setYujinOpen`은 오른쪽 도크 상태와 분리돼 있다).
async function ensureYujinOpen(page) {
  if (await page.getByRole("region", { name: "유진" }).count()) return;
  await page.getByRole("button", { name: "유진" }).click();
}

test.beforeEach(async ({ page }) => {
  await installFixedClock(page);
  await page.route(
    "**/api/projects/local-draft/editing-sessions/editor-workbench-e2e",
    (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(editingSession) }),
  );
  await page.route(
    "**/api/projects/local-draft/output-variants?session_id=editor-workbench-e2e",
    (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ variants: [horizontalVariant, outputVariant] }) }),
  );
});

for (const [width, height] of snapshots) test(`editor workbench snapshot ${width}x${height}`, async ({ page }) => {
  await page.addInitScript(() => localStorage.removeItem("videobox.editor-workbench.ui"));
  await page.route("**/api/projects", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ projects: [{ project_id: "local-draft", name: "편집 작업판", status: "active", root_storage_uri: "local://editor-workbench" }] }) }));
  await page.route("**/playback-manifest", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(manifest) }));
  await page.setViewportSize({ width, height });
  await page.goto("/projects/local-draft/editor?session_id=editor-workbench-e2e");
  await expect(page.getByRole("region", { name: "편집 작업판" })).toBeVisible();
  const workbench = page.getByRole("region", { name: "편집 작업판" });
  const preview = page.getByRole("region", { name: "미리보기" });
  const previewSlot = page.locator(".vb-editor-workbench__preview");
  await expect(preview).toBeVisible();
  await expect(page.locator("audio, video")).toHaveCount(0);
  // 넓은 화면의 새 세션은 미디어와 세부 정보를 함께 열어 둔다. 창작자는 편집기에서
  // 미리보기와 두 도크를 한 번에 비교해야 하므로, 기본 배치를 예전 단일 도크로
  // 되돌리지 않는다.
  // 1280px에서는 두 패널을 열면 미리보기에 필요한 720px이 남지 않아 한쪽만
  // 보이는 것이 정상이다. 이 스냅샷 묶음에서는 1440px부터 양쪽이 함께 들어간다.
  const expectedDensity = width >= 1440 ? "desktop-both" : width >= 1280 ? "desktop-single" : "drawer";
  await expect(workbench).toHaveAttribute("data-editor-density", expectedDensity);
  await expect(page.getByRole("button", { name: "내레이션 1번째 장면, 0초부터" })).toBeVisible();
  const previewBox = await previewSlot.boundingBox();
  expect(previewBox?.width).toBeGreaterThanOrEqual(width >= 1280 ? 640 : 0);
  await waitForStableCapture(page);
  await page.screenshot(playwrightSnapshotOptions(`e2e/snapshots/editor-workbench-${width}x${height}.png`));
});

test("desktop pointer drag persists the actual dock width across reload", async ({ page }) => {
  await page.route("**/api/projects", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ projects: [{ project_id: "local-draft", name: "편집 작업판", status: "active", root_storage_uri: "local://editor-workbench" }] }) }));
  await page.route("**/playback-manifest", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(manifest) }));
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  await page.evaluate(() => localStorage.removeItem("videobox.editor-workbench.ui"));
  await page.goto("/projects/local-draft/editor?session_id=editor-workbench-e2e");
  const workbench = page.getByRole("region", { name: "편집 작업판" });
  // 이 테스트가 지키는 것은 **드래그한 도크 폭이 새로고침 뒤에도 남는가**다.
  // `desktop-both`는 오른쪽 크기 조절 핸들이 있는 상태를 만드는 수단이지 목적이
  // 아니다 -- 기본값이 바뀌어도 같은 상태에 도달하도록 열려 있는 것은 그냥 둔다.
  await ensureDockOpen(page, "미디어");
  await ensureDockOpen(page, "세부 정보");
  await expect(workbench).toHaveAttribute("data-editor-density", "desktop-both");
  const rightDock = page.getByRole("complementary", { name: "세부 정보" });
  const before = await rightDock.boundingBox();
  const handle = await page.getByLabel("오른쪽 패널 크기 조절").boundingBox();
  if (!handle) throw new Error("right resize handle is missing");
  await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2);
  await page.mouse.down();
  await page.mouse.move(handle.x - 80, handle.y + handle.height / 2, { steps: 6 });
  await page.mouse.up();
  await expect.poll(async () => (await rightDock.boundingBox())?.width ?? 0).toBeGreaterThan((before?.width ?? 0));
  const resizedWidth = (await rightDock.boundingBox())?.width ?? 0;
  await page.reload();
  await expect(workbench).toHaveAttribute("data-editor-density", "desktop-both");
  await expect.poll(async () => (await page.getByRole("complementary", { name: "세부 정보" }).boundingBox())?.width ?? 0).toBeCloseTo(resizedWidth, 0);
  // "세부 정보"는 더 이상 접히지 않는다(owner 지시 2026-08-30, 캡컷과 같은
  // 상시 노출 -- `EditorWorkbench.tsx`의 `openRightPane`은 이미 보이면 아무
  // 일도 하지 않는다). 예전에는 이 단추가 닫기 토글이라 눌러서
  // `desktop-single`로 접히는지까지 같이 쟀는데, 그 기능 자체가 없어졌다 --
  // 지금은 반대로 **눌러도 안 접히는 것**이 지켜야 할 계약이다.
  await page.getByRole("button", { name: "세부 정보" }).click();
  await expect(workbench).toHaveAttribute("data-editor-density", "desktop-both");
  await expect(page.getByRole("complementary", { name: "세부 정보" })).toBeVisible();
});

test("constrains real workbench body geometry and keeps the single preview at least half-width", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("videobox.editor-workbench.ui", JSON.stringify({ leftOpen: true, rightOpen: false, activeDrawer: null, leftSize: 280, rightSize: 320 })));
  await page.route("**/api/projects", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ projects: [{ project_id: "local-draft", name: "편집 작업판", status: "active", root_storage_uri: "local://editor-workbench" }] }) }));
  await page.route("**/playback-manifest", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(manifest) }));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/projects/local-draft/editor?session_id=editor-workbench-e2e");
  const workbench = page.getByRole("region", { name: "편집 작업판" });
  const body = page.locator(".vb-editor-workbench__body");
  const preview = page.getByRole("region", { name: "미리보기" });
  const previewSlot = page.locator(".vb-editor-workbench__preview");
  await expect(workbench).toHaveAttribute("data-editor-density", "desktop-single");
  const bodyBox = await body.boundingBox();
  await expect(preview).toBeVisible();
  const previewBox = await previewSlot.boundingBox();
  expect(Number(await workbench.getAttribute("data-available-workbench-width"))).toBeCloseTo(bodyBox?.width ?? 0, 0);
  expect(previewBox?.width ?? 0).toBeGreaterThanOrEqual(Math.max(640, (bodyBox?.width ?? 0) / 2));
});

test("every toolbar control stays reachable on a phone-width screen", async ({ page }) => {
  await page.addInitScript(() => localStorage.removeItem("videobox.editor-workbench.ui"));
  await page.route("**/api/projects", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ projects: [{ project_id: "local-draft", name: "편집 작업판", status: "active", root_storage_uri: "local://editor-workbench" }] }) }));
  await page.route("**/playback-manifest", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(manifest) }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/projects/local-draft/editor?session_id=editor-workbench-e2e");
  await expect(page.getByRole("region", { name: "편집 작업판" })).toBeVisible();

  // 툴바 버튼 줄이 화면 밖으로 나가면 작업판이 `overflow:hidden`이라 가로로 밀어
  // 볼 수도 없다. 컷 도구가 툴바에 붙은 뒤 390px에서 `빼기`부터 오른쪽이 통째로
  // 손에 닿지 않았다 -- 미디어 열도 유진이도 열 수 없다는 뜻이다.
  //
  // 줄바꿈 대신 옆으로 밀어 보게 했으므로, 지켜야 할 것은 "처음부터 다 보인다"가
  // 아니라 **끝까지 밀면 마지막 버튼에 닿는다**이다. 툴바 높이도 함께 본다 --
  // 줄바꿈으로 풀었을 때 툴바가 화면의 3분의 1을 먹고 미리보기가 무너졌다.
  const row = page.locator(".vb-editor-workbench__toolbar div").first();
  expect(await row.evaluate((node) => /(auto|scroll)/.test(getComputedStyle(node).overflowX))).toBe(true);
  await row.evaluate((node) => { node.scrollLeft = node.scrollWidth; });
  // **범위를 툴바 안으로 좁혔다(2026-08-27).** 이 시험이 지키는 것은 "툴바를 끝까지
  // 밀면 마지막 단추에 닿는다"이므로 애초에 툴바 안에서 찾는 것이 맞는 표현이었다.
  // 이름이 겹치지 않던 동안 우연히 통했을 뿐이다.
  //
  // 겹친 이유를 남겨 둔다(역사 기록): 이름을 `미디어` 하나로 모으면서(owner
  // 승인 2026-08-27) 위 띠의 단계 단추와 편집기 도크 단추가 한때 **같은
  // 이름**이었다. 위 띠의 "미디어" 단추는 2026-09-01에 없어졌다(독립 화면이
  // 편집기 도크로 접힘, `2026-08-27-editor-centered-shell-direction.ko.md`
  // 순서 2 실행) -- 이제 이 이름을 쓰는 단추는 편집기 도크 것 하나뿐이라
  // 아래 scoped lookup은 더 이상 모호함을 피하기 위한 것이 아니라 그냥
  // 정확한 범위 지정이다.
  const workbench = page.getByLabel("편집 작업판");
  for (const name of ["빼기", "세부 정보"]) {
    const right = await workbench.getByRole("button", { name }).evaluate((node) => node.getBoundingClientRect().right);
    expect(right).toBeLessThanOrEqual(390 + 1);
  }
  // "미디어"는 더 이상 이 스크롤 도구줄의 단추가 아니다(owner 승인
  // 2026-08-30 2단계 -- 왼쪽 패널의 실제 탭(미디어·오디오·텍스트·캡션·대본·
  // 전환)이 패널을 연 뒤에만 보이던 것에서, 창 맨 위 `.vb-editor-workbench__rail`
  // 이라는 **별도의 상시 노출 세로 띠**로 옮겨졌다 -- 접근성 role도 `button`이
  // 아니라 `tab`이다(`왼쪽 패널` tablist). 이 띠는 도구줄과 같이 밀리지
  // 않고 72px 고정폭이라 처음부터 닿는다 -- 여기서 지키는 것은 "닿는다"이지
  // "도구줄 스크롤로 닿는다"가 아니다.
  const mediaTab = workbench.getByRole("tab", { name: "미디어" });
  await expect(mediaTab).toBeVisible();
  const mediaTabRight = await mediaTab.evaluate((node) => node.getBoundingClientRect().right);
  expect(mediaTabRight).toBeLessThanOrEqual(390 + 1);
  const toolbarHeight = await page.locator(".vb-editor-workbench__toolbar").evaluate((node) => node.getBoundingClientRect().height);
  expect(toolbarHeight).toBeLessThan(844 / 4);
});

test("narrow drawer traps focus and returns it to its trigger", async ({ page }) => {
  await page.addInitScript(() => localStorage.removeItem("videobox.editor-workbench.ui"));
  await page.route("**/api/projects", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ projects: [{ project_id: "local-draft", name: "편집 작업판", status: "active", root_storage_uri: "local://editor-workbench" }] }) }));
  await page.route("**/playback-manifest", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(manifest) }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/projects/local-draft/editor?session_id=editor-workbench-e2e");
  const trigger = page.getByRole("button", { name: "세부 정보" });
  await trigger.click();
  const drawer = page.getByRole("dialog", { name: "세부 정보" });
  await expect(drawer).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test("server-backed output variants keep revision lineage through materialize, lock, and highlight order", async ({ page }) => {
  let currentVariant = structuredClone(outputVariant);
  let highlightVariant = null;
  const patchBodies = [];
  const materializations = [];
  await page.route("**/api/projects/local-draft/output-variants", async (route) => {
    const request = route.request();
    if (request.method() === "POST") {
      highlightVariant = { ...currentVariant, variant_id: "vertical-highlight", kind: "vertical_highlight", variant_revision: 1, selected_segment_ids: ["segment-1"] };
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ variant: highlightVariant }) });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ variants: highlightVariant ? [horizontalVariant, currentVariant, highlightVariant] : [horizontalVariant, currentVariant] }) });
  });
  await page.route("**/api/projects/local-draft/output-variants/**", async (route) => {
    const request = route.request();
    const url = request.url();
    if (request.method() === "PATCH") {
      const body = request.postDataJSON();
      patchBodies.push(body);
      currentVariant = { ...currentVariant, variant_revision: currentVariant.variant_revision + 1, overrides: { ...currentVariant.overrides, ...(body.patch.overrides ?? {}) }, locks: body.patch.lock_fields ? body.patch.lock_fields.map((field) => ({ field, base_master_revision: currentVariant.source_session_revision })) : currentVariant.locks, selected_segment_ids: body.patch.selected_segment_ids ?? currentVariant.selected_segment_ids };
      if (highlightVariant && url.endsWith("vertical-highlight")) highlightVariant = { ...highlightVariant, variant_revision: highlightVariant.variant_revision + 1, selected_segment_ids: body.patch.selected_segment_ids ?? highlightVariant.selected_segment_ids };
      const responseVariant = url.endsWith("vertical-highlight") ? highlightVariant : currentVariant;
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ variant: responseVariant }) });
      return;
    }
    if (request.method() === "POST" && url.endsWith("/materialize")) {
      materializations.push(request.postDataJSON());
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ materialization: { timeline_id: "timeline-vertical-1", source_session_id: "editor-workbench-e2e", source_session_revision: currentVariant.source_session_revision, source_variant_id: currentVariant.variant_id, source_variant_revision: currentVariant.variant_revision } }) });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ variant: currentVariant }) });
  });
  await page.route("**/api/projects", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ projects: [{ project_id: "local-draft", name: "편집 작업판", status: "active", root_storage_uri: "local://editor-workbench" }] }) }));
  await page.route("**/playback-manifest", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(manifest) }));
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/projects/local-draft/editor?session_id=editor-workbench-e2e");
  await page.getByRole("button", { name: "출력 변형 펼치기" }).click();
  await page.getByRole("tab", { name: "세로" }).click();
  await expect(page.getByText("서버 변형 버전 1")).toBeVisible();
  await page.getByRole("button", { name: "크롭 저장" }).click();
  await expect.poll(() => patchBodies.length).toBe(1);
  await expect(page.getByText("서버 변형 버전 2")).toBeVisible();
  // 단추 문구는 "크롭·자막 잠금"이 아니라 "크롭·캡션 잠금"이다
  // (`VariantServerControls.tsx`) -- 출력 변형 조작 안에서는 "캡션"으로
  // 부른다(편집기 오른쪽 도크의 "캡션 조정 항목"과 같은 용어).
  await page.getByRole("button", { name: "크롭·캡션 잠금" }).click();
  await expect.poll(() => patchBodies.length).toBe(2);
  await expect(page.getByText("출력 변형을 저장했어요.")).toBeVisible();
  await expect(page.getByText("서버 변형 버전 3")).toBeVisible();
  await page.getByRole("button", { name: "세로 변형 준비" }).click();
  await expect.poll(() => materializations.length).toBe(1);
  await page.getByRole("button", { name: "하이라이트 변형 만들기" }).click();
  await expect(page.getByRole("button", { name: "전체 장면으로 되돌리기" })).toBeVisible();
  await page.getByRole("button", { name: "전체 장면으로 되돌리기" }).click();
  await expect.poll(() => patchBodies.length).toBe(3);
  expect(materializations[0]).toEqual({ expected_master_session_revision: 7 });
});

test("Yujin applies one persisted caption only after explicit selection and preserves route state with output POST zero", async ({ page }) => {
  let activeSession = editingSession;
  let activeManifest = manifest;
  const captionPatches = [];
  const outputPosts = [];
  const persistedMessages = [
    { message_id: "message-user", conversation_id: "conversation-e2e", project_id: "local-draft", session_id: "editor-workbench-e2e", role: "user", text: "자막을 다듬어 줘", proposal_id: null, metadata: {}, client_message_id: "client-e2e", created_at: "1" },
    { message_id: "message-assistant", conversation_id: "conversation-e2e", project_id: "local-draft", session_id: "editor-workbench-e2e", role: "assistant", text: "자막 후보를 준비했어요.", proposal_id: "yujin-caption-text", metadata: { hermes_run_id: "run-e2e" }, client_message_id: null, created_at: "2" },
    ...Array.from({ length: 16 }, (_, index) => ({
      message_id: `history-${index}`,
      conversation_id: "conversation-e2e",
      project_id: "local-draft",
      session_id: "editor-workbench-e2e",
      role: index % 2 === 0 ? "user" : "assistant",
      text: `이전 대화 ${index + 1} — 닫고 다시 열어도 스크롤 위치를 확인할 만큼 충분히 긴 내용입니다.`,
      proposal_id: null,
      metadata: {},
      client_message_id: index % 2 === 0 ? `history-client-${index}` : null,
      created_at: String(index + 3),
    })),
  ];
  let trackOutputPosts = false;
  page.on("request", (request) => {
    if (trackOutputPosts && request.method() === "POST") outputPosts.push(request.url());
  });
  await page.addInitScript(() => localStorage.removeItem("videobox.editor-workbench.ui"));
  await page.route("**/api/projects", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ projects: [{ project_id: "local-draft", name: "편집 작업판", status: "active", root_storage_uri: "local://editor-workbench" }] }),
  }));
  await page.route("**/playback-manifest", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify(activeManifest),
  }));
  await page.route(
    "**/api/projects/local-draft/editing-sessions/editor-workbench-e2e",
    (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(activeSession) }),
  );
  await page.route("**/api/projects/local-draft/director/sessions/editor-workbench-e2e/reload", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      conversation: { conversation_id: "conversation-e2e", project_id: "local-draft", session_id: "editor-workbench-e2e" },
      messages: persistedMessages,
      proposal: yujinCaptionProposal,
      references: [],
    }),
  }));
  await page.route("**/api/projects/local-draft/director/proposals/yujin-caption-text/preflight", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ status: "ready" }),
  }));
  await page.route(
    "**/api/projects/local-draft/editing-sessions/editor-workbench-e2e/segments/segment-1/caption",
    async (route) => {
      captionPatches.push(route.request().postDataJSON());
      activeSession = {
        ...editingSession,
        session_revision: 8,
        updated_at: "2026-07-24T00:00:01Z",
        segments: [{ ...editingSession.segments[0], caption_text: "추천 자막으로 바꿉니다." }],
      };
      activeManifest = {
        ...manifest,
        session_revision: 8,
        timeline_version: "v8",
        captions: [{ ...manifest.captions[0], text: "추천 자막으로 바꿉니다." }],
        source_status: { status: "current", source_session_id: "editor-workbench-e2e", source_session_revision: 8 },
        exact_preview: { status: "unavailable", url: null, source_session_id: "editor-workbench-e2e", source_session_revision: 8 },
      };
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(activeSession) });
    },
  );

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/projects/local-draft/editor?session_id=editor-workbench-e2e");
  const preview = page.getByRole("region", { name: "미리보기" });
  await expect(preview).toBeVisible();
  await preview.evaluate((element) => { element.setAttribute("data-b5-player", "same"); });
  // 390px에서 "세부 정보"는 **모달 서랍**(`aria-modal="true"`, "narrow drawer
  // traps focus" 시험이 지키는 포커스 가둠)이라, 열려 있으면 화면 구석에
  // 뜨는 "유진" 단추까지 덮어 눌리지 않는다. 이 시험이 쓰는 대화·후보
  // 선택·자막 적용은 전부 유진 패널 자체 안에 있어서(`YujinPanel.tsx`) 굳이
  // "세부 정보" 서랍을 열 필요가 없다 -- 열면 오히려 유진에 닿는 길을 막는다.
  await ensureYujinOpen(page);
  const draft = page.getByRole("textbox", { name: "유진에게 요청하기" });
  await draft.fill("닫아도 남을 초안");
  const candidate = page.getByRole("radio", { name: "P01-CAPTION-TEXT-01 선택" });
  await expect(candidate).not.toBeChecked();
  expect(captionPatches).toHaveLength(0);

  await candidate.check();
  expect(captionPatches).toHaveLength(0);
  const conversation = page.getByRole("log", { name: "유진 대화" });
  const savedScrollTop = await conversation.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
    element.dispatchEvent(new Event("scroll"));
    return element.scrollTop;
  });
  expect(savedScrollTop).toBeGreaterThan(0);
  // 유진 패널은 "세부 정보" 도크의 서랍이 아니라 **독립된 열림 상태**를 가진
  // 떠 있는 패널이다(owner 지시 2026-08-30) -- 닫는 단추도 그 패널 것
  // ("유진 닫기")이지 도크의 "닫기"가 아니다. "세부 정보"를 닫았다 열어도
  // 유진 패널은 원래 열려 있던 상태 그대로다(둘의 열림 상태가 분리돼 있으니).
  // 이 시험이 실제로 지키려는 것("패널을 닫았다 다시 열어도 입력·스크롤
  // 위치가 남는다")은 유진 패널 자체를 닫고 여는 것으로 재야 맞게 잰다.
  await page.getByRole("button", { name: "유진 닫기" }).click();
  await expect(conversation).toHaveCount(0);
  await ensureYujinOpen(page);

  await expect(draft).toHaveValue("닫아도 남을 초안");
  await expect(candidate).toBeChecked();
  await expect(page.getByText("자막을 다듬어 줘")).toBeVisible();
  await expect(page.getByText("자막 후보를 준비했어요.")).toBeVisible();
  await expect.poll(() => conversation.evaluate((element) => element.scrollTop)).toBe(savedScrollTop);
  await expect(page.locator('[data-b5-player="same"]')).toHaveCount(1);

  await page.getByRole("button", { name: "선택한 추천 적용" }).click();
  await expect.poll(() => captionPatches.length).toBe(1);
  expect(captionPatches[0]).toEqual({
    caption_text: "추천 자막으로 바꿉니다.",
    expected_revision: 7,
    proposal_id: "yujin-caption-text",
    candidate_id: "candidate-caption-text",
  });
  await expect(page.getByRole("region", { name: "편집 작업판" })).toHaveAttribute("data-editor-revision", "8");

  trackOutputPosts = true;
  await page.goto("/projects/local-draft/outputs");
  await expect(page.getByTestId("outputs-page")).toBeVisible();
  expect(outputPosts).toHaveLength(0);
});

test("owned conversational-editing fixture keeps explicit AI speed apply reversible after refresh", async ({ page }) => {
  // This is deliberately a project created only for this browser contract.  Do
  // not substitute a representative or owner project: the route mutates and
  // then reloads its editing-session state three times below.
  const projectId = "owned-conversational-editing-fixture";
  const sessionId = "owned-ai-edit-session";
  const proposalId = "owned-speed-proposal";
  const baseSession = {
    ...structuredClone(editingSession),
    project_id: projectId,
    session_id: sessionId,
    timeline_id: "owned-ai-edit-timeline",
    session_revision: 7,
    undo_count: 0,
    redo_count: 0,
    segments: [
      { ...editingSession.segments[0], segment_id: "scene-1", start_sec: 0, end_sec: 8, caption_text: "첫 장면" },
      { ...editingSession.segments[0], segment_id: "scene-2", start_sec: 8, end_sec: 16, caption_text: "두 번째 장면" },
    ],
  };
  const baseManifest = {
    ...structuredClone(manifest),
    project_id: projectId,
    session_id: sessionId,
    timeline_id: "owned-ai-edit-timeline",
    session_revision: 7,
    timeline_version: "v7",
    output: { ...manifest.output, duration_sec: 16 },
    tracks: [{
      ...manifest.tracks[0],
      clips: [
        { ...manifest.tracks[0].clips[0], clip_id: "owned-clip-1", segment_id: "scene-1", start_sec: 0, end_sec: 8 },
        { ...manifest.tracks[0].clips[0], clip_id: "owned-clip-2", segment_id: "scene-2", start_sec: 8, end_sec: 16 },
      ],
    }],
    captions: [
      { ...manifest.captions[0], segment_id: "scene-1", text: "첫 장면", start_sec: 0, end_sec: 8 },
      { ...manifest.captions[0], segment_id: "scene-2", text: "두 번째 장면", start_sec: 8, end_sec: 16 },
    ],
    source_status: { status: "current", source_session_id: sessionId, source_session_revision: 7 },
    exact_preview: { status: "unavailable", url: null, source_session_id: sessionId, source_session_revision: 7 },
  };
  const proposal = {
    proposal_id: proposalId,
    revision_code: "P-AI-SPEED-01",
    revision: 1,
    base_session_revision: 7,
    asset_index_revision: 1,
    source_session_id: sessionId,
    target_segment_ids: ["scene-2"],
    source_script_segment_ids: ["scene-2"],
    status: "ready",
    diff: {
      proposal_mode: "yujin_editing_candidate_v1",
      operations: [{ intent: "set_scene_speed", segment_id: "scene-2", rate: 2 }],
      follow_up_questions: ["이 구간만 미리 볼까요?"],
    },
    expires_at: null,
    candidates: [],
  };
  const fastSession = { ...baseSession, session_revision: 8, undo_count: 1, redo_count: 0 };
  const undoneSession = { ...baseSession, session_revision: 9, undo_count: 0, redo_count: 1 };
  const redoneSession = { ...baseSession, session_revision: 10, undo_count: 1, redo_count: 0 };
  const fastManifest = {
    ...baseManifest,
    session_revision: 8,
    timeline_version: "v8",
    output: { ...baseManifest.output, duration_sec: 12 },
    tracks: [{ ...baseManifest.tracks[0], clips: [baseManifest.tracks[0].clips[0], { ...baseManifest.tracks[0].clips[1], end_sec: 12, media_controls: { playback_rate: 2 } }] }],
    captions: [baseManifest.captions[0], { ...baseManifest.captions[1], end_sec: 12 }],
    source_status: { status: "current", source_session_id: sessionId, source_session_revision: 8 },
    exact_preview: { status: "unavailable", url: null, source_session_id: sessionId, source_session_revision: 8 },
  };
  const undoneManifest = { ...baseManifest, session_revision: 9, timeline_version: "v9", source_status: { status: "current", source_session_id: sessionId, source_session_revision: 9 }, exact_preview: { status: "unavailable", url: null, source_session_id: sessionId, source_session_revision: 9 } };
  const redoneManifest = { ...fastManifest, session_revision: 10, timeline_version: "v10", source_status: { status: "current", source_session_id: sessionId, source_session_revision: 10 }, exact_preview: { status: "unavailable", url: null, source_session_id: sessionId, source_session_revision: 10 } };
  let activeSession = baseSession;
  let activeManifest = baseManifest;
  const appliedBodies = [];
  const createdProposalBodies = [];
  // 적용 전에 **저장된 편집본을 건드린 횟수**. 후보 결과 미리보기는 읽기 전용이므로
  // 여기에 한 건도 쌓이면 안 된다(2026-08-26 인계 Task 3의 핵심 안전 성질).
  const sessionMutationCalls = [];
  const proposalPreviewStatusCalls = [];
  const proposalPreviewGenerationId = "owned-proposal-preview-1";
  const proposalPreviewContentUrl = `/api/projects/${projectId}/proposal-previews/${proposalPreviewGenerationId}/content`;

  await page.addInitScript(() => localStorage.removeItem("videobox.editor-workbench.ui"));
  await page.route("**/api/projects", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ projects: [{ project_id: projectId, name: "소유 대화형 편집 검증", status: "active", root_storage_uri: "local://owned-conversational-editing-fixture" }] }) }));
  await page.route(`**/api/projects/${projectId}/editing-sessions/${sessionId}/playback-manifest`, (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(activeManifest) }));
  await page.route(`**/api/projects/${projectId}/editing-sessions/${sessionId}`, (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(activeSession) }));
  await page.route(`**/api/projects/${projectId}/director/conversations`, async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ conversation_id: "owned-ai-conversation", project_id: projectId, session_id: sessionId }) });
  });
  await page.route(`**/api/projects/${projectId}/director/conversations/owned-ai-conversation/messages`, async (route) => {
    const body = route.request().postDataJSON();
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({
      user_message: { message_id: "owned-user-message", conversation_id: "owned-ai-conversation", project_id: projectId, session_id: sessionId, role: "user", text: body.text, proposal_id: null, metadata: {}, client_message_id: body.client_message_id, created_at: "2026-08-26T00:00:00Z" },
      assistant_message: { message_id: "owned-assistant-message", conversation_id: "owned-ai-conversation", project_id: projectId, session_id: sessionId, role: "assistant", text: "두 번째 장면 속도 편집안을 확인해 볼게요.", proposal_id: null, metadata: {}, client_message_id: null, created_at: "2026-08-26T00:00:01Z" },
    }) });
  });
  await page.route(`**/api/projects/${projectId}/editing-sessions/${sessionId}/yujin-editing-proposals`, async (route) => {
    createdProposalBodies.push(route.request().postDataJSON());
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(proposal) });
  });
  await page.route(`**/api/projects/${projectId}/editing-sessions/${sessionId}/yujin-editing-proposals/${proposalId}/preflight`, (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ proposal_id: proposalId, status: "ready", diff: proposal.diff }) }));
  await page.route(`**/api/projects/${projectId}/editing-sessions/${sessionId}/yujin-editing-proposals/${proposalId}/apply`, async (route) => {
    appliedBodies.push(route.request().postDataJSON());
    activeSession = fastSession;
    activeManifest = fastManifest;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(activeSession) });
  });
  await page.route(`**/api/projects/${projectId}/editing-sessions/${sessionId}/undo`, async (route) => {
    expect(route.request().postDataJSON()).toEqual({ expected_revision: 8 });
    activeSession = undoneSession;
    activeManifest = undoneManifest;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(activeSession) });
  });
  await page.route(`**/api/projects/${projectId}/editing-sessions/${sessionId}/redo`, async (route) => {
    expect(route.request().postDataJSON()).toEqual({ expected_revision: 9 });
    activeSession = redoneSession;
    activeManifest = redoneManifest;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(activeSession) });
  });
  await page.route(`**/api/projects/${projectId}/editing-sessions/${sessionId}/selected-range-preview`, async (route) => {
    sessionMutationCalls.push("selected-range-preview");
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({}) });
  });
  await page.route(`**/api/projects/${projectId}/editing-sessions/${sessionId}/exact-preview`, (route) => {
    sessionMutationCalls.push("exact-preview");
    return route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({}) });
  });
  // 후보 결과 미리보기. 저장된 편집본과 **다른 주소**이고 세션을 바꾸지 않는다.
  await page.route(`**/api/projects/${projectId}/editing-sessions/${sessionId}/yujin-editing-proposals/${proposalId}/preview`, (route) => route.fulfill({
    status: 202,
    contentType: "application/json",
    body: JSON.stringify({ status: "pending", generation_id: proposalPreviewGenerationId, content_url: null, error_message: null }),
  }));
  await page.route(`**/api/projects/${projectId}/proposal-previews/${proposalPreviewGenerationId}`, (route) => {
    proposalPreviewStatusCalls.push(route.request().url());
    const ready = proposalPreviewStatusCalls.length > 1;
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({
      status: ready ? "succeeded" : "running",
      generation_id: proposalPreviewGenerationId,
      content_url: ready ? proposalPreviewContentUrl : null,
      error_message: null,
    }) });
  });

  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`/projects/${projectId}/editor?session_id=${sessionId}`);
  await expect(page.getByRole("region", { name: "편집 작업판" })).toHaveAttribute("data-editor-revision", "7");
  await ensureDockOpen(page, "세부 정보");
  await ensureYujinOpen(page);
  await page.getByRole("textbox", { name: "유진에게 요청하기" }).fill("두 번째 장면을 두 배로 빠르게");
  await page.getByRole("button", { name: "요청 보내기" }).click();
  await expect(page.getByText("두 번째 장면 속도 편집안을 확인해 볼게요.")).toBeVisible();
  // **말로 시킨 편집은 확인 클릭 없이 바로 적용된다(owner 2026-09-01,
  // `decisions/2026-09-01-yujin-chat-applies-edits-directly.ko.md`,
  // `EditorWorkbenchRoute.tsx`의 `interpretAndApplySpokenEdit`).** 예전에는
  // "이 대화로 편집안 만들기" → "편집안 보기" → "이 구간 미리보기" → "이
  // 편집안 적용"을 네 번 눌러야 했다. owner가 실제로 써 보고 "말로 컷 편집이
  // 되는지 확인한 적이 없는 것 같다"고 지적해 그 단계를 없앴다 -- 유진이
  // 스스로 해석할 수 있는 지시라면 `요청 보내기` 한 번으로 제안이 만들어지고
  // (`createYujinEditingProposal`) 곧바로 적용까지 간다(`applyEditingProposalNow`).
  // 안전장치는 이제 클릭이 아니라 **되돌리기**다 -- 아래 실행 취소/다시 실행이
  // 그것을 잰다. (미리보기 없이 세션을 바꾸지 않는다는 옛 안전 성질은 유진이
  // 직접 적용하지 못해 사람이 수동으로 편집안을 확인해야 하는 경로에서만 남아
  // 있고, 이 시험의 깔끔한 지시 시나리오로는 더 이상 걸리지 않는다 -- 범위 밖.)
  await expect.poll(() => createdProposalBodies.length).toBe(1);
  expect(createdProposalBodies[0]).toEqual({ instruction: "두 번째 장면을 두 배로 빠르게" });
  await expect.poll(() => appliedBodies.length).toBe(1);
  expect(appliedBodies[0]).toEqual({ expected_revision: 7 });
  await expect(page.getByRole("region", { name: "편집 작업판" })).toHaveAttribute("data-editor-revision", "8");
  await page.reload();
  await expect(page.getByRole("region", { name: "편집 작업판" })).toHaveAttribute("data-editor-revision", "8");
  await page.getByRole("button", { name: "실행 취소" }).click();
  await expect(page.getByRole("region", { name: "편집 작업판" })).toHaveAttribute("data-editor-revision", "9");
  await page.reload();
  await expect(page.getByRole("region", { name: "편집 작업판" })).toHaveAttribute("data-editor-revision", "9");
  await page.getByRole("button", { name: "다시 실행" }).click();
  await expect(page.getByRole("region", { name: "편집 작업판" })).toHaveAttribute("data-editor-revision", "10");
  await page.reload();
  await expect(page.getByRole("region", { name: "편집 작업판" })).toHaveAttribute("data-editor-revision", "10");
});
