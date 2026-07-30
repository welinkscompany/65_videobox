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

test.beforeEach(async ({ page }) => {
  await installFixedClock(page);
  await page.route(
    "**/api/projects/local-draft/editing-sessions/editor-workbench-e2e",
    (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(editingSession) }),
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
  const expectedDensity = width >= 1600 ? "desktop-both" : width >= 1280 ? "desktop-single" : "drawer";
  await expect(workbench).toHaveAttribute("data-editor-density", expectedDensity);
  await expect(page.getByRole("button", { name: "clip-1 클립 선택" })).toBeVisible();
  const previewBox = await previewSlot.boundingBox();
  expect(previewBox?.width).toBeGreaterThanOrEqual(width >= 1600 ? 720 : width >= 1280 ? 640 : 0);
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
  const rightDock = page.getByRole("complementary", { name: "유진과 편집 항목" });
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
  await expect.poll(async () => (await page.getByRole("complementary", { name: "유진과 편집 항목" }).boundingBox())?.width ?? 0).toBeCloseTo(resizedWidth, 0);
  await page.getByRole("button", { name: "유진과 편집 항목" }).click();
  await expect(workbench).toHaveAttribute("data-editor-density", "desktop-single");
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

test("narrow drawer traps focus and returns it to its trigger", async ({ page }) => {
  await page.addInitScript(() => localStorage.removeItem("videobox.editor-workbench.ui"));
  await page.route("**/api/projects", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ projects: [{ project_id: "local-draft", name: "편집 작업판", status: "active", root_storage_uri: "local://editor-workbench" }] }) }));
  await page.route("**/playback-manifest", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(manifest) }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/projects/local-draft/editor?session_id=editor-workbench-e2e");
  const trigger = page.getByRole("button", { name: "유진과 편집 항목" });
  await trigger.click();
  const drawer = page.getByRole("dialog", { name: "유진과 편집 항목" });
  await expect(drawer).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  await expect(trigger).toBeFocused();
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
  await page.getByRole("button", { name: "유진과 편집 항목" }).click();
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
  await page.getByRole("button", { name: "닫기" }).click();
  await expect(conversation).toHaveCount(0);
  await page.getByRole("button", { name: "유진과 편집 항목" }).click();

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
