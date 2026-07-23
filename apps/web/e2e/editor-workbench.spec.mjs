import { expect, test } from "./support/test-fixtures.mjs";
import { installFixedClock, playwrightSnapshotOptions, waitForStableCapture } from "./support/fixed-clock.mjs";

const snapshots = [[1920, 1080], [1440, 900], [1280, 800], [768, 1024], [390, 844]];
const manifest = { project_id: "local-draft", session_id: "editor-workbench-e2e", timeline_id: "timeline-e2e", session_revision: 7, timeline_version: "v7", timebase: "seconds", fps: { num: 30, den: 1 }, output: { width: 1080, height: 1920, sample_aspect_ratio: "1:1", rotation: 0, duration_sec: 12 }, tracks: [{ track_id: "narration", track_type: "narration", clips: [{ clip_id: "clip-1", segment_id: "segment-1", clip_type: "narration", asset_id: "asset-1", asset_uri: "local://asset-1", start_sec: 0, end_sec: 12, media_controls: {} }] }], captions: [{ segment_id: "segment-1", text: "여름 여행을 소개합니다.", start_sec: 0, end_sec: 12, style: { font_family: "Pretendard", font_size_px: 24, text_color: "#fff", outline_color: "#000", outline_width_px: 1, background_color: "#00000000", position_x_percent: 50, position_y_percent: 90, horizontal_align: "center", safe_area_enabled: true, shadow_blur_px: 0 } }], gap_slots: [], source_status: { status: "current", source_session_id: "editor-workbench-e2e", source_session_revision: 7 }, audition: { asset_urls: {} }, exact_preview: { status: "unavailable", url: null, source_session_id: "editor-workbench-e2e", source_session_revision: 7 } };

test.beforeEach(async ({ page }) => {
  await installFixedClock(page);
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
