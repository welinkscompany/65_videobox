import { expect, test } from "@playwright/test";

const snapshots = [[1920, 1080], [1440, 900], [1280, 800], [768, 1024], [390, 844]];
const manifest = { project_id: "local-draft", session_id: "editor-workbench-e2e", timeline_id: "timeline-e2e", session_revision: 7, timeline_version: "v7", timebase: "seconds", fps: { num: 30, den: 1 }, output: { width: 1080, height: 1920, sample_aspect_ratio: "1:1", rotation: 0, duration_sec: 12 }, tracks: [{ track_id: "narration", track_type: "narration", clips: [{ clip_id: "clip-1", segment_id: "segment-1", clip_type: "narration", asset_id: "asset-1", asset_uri: "local://asset-1", start_sec: 0, end_sec: 12, media_controls: {} }] }], captions: [{ segment_id: "segment-1", text: "여름 여행을 소개합니다.", start_sec: 0, end_sec: 12, style: { font_family: "Pretendard", font_size_px: 24, text_color: "#fff", outline_color: "#000", outline_width_px: 1, background_color: "#00000000", position_x_percent: 50, position_y_percent: 90, horizontal_align: "center", safe_area_enabled: true, shadow_blur_px: 0 } }], gap_slots: [], source_status: { status: "current", source_session_id: "editor-workbench-e2e", source_session_revision: 7 }, audition: { asset_urls: {} }, exact_preview: { status: "unavailable", url: null, source_session_id: "editor-workbench-e2e", source_session_revision: 7 } };

for (const [width, height] of snapshots) test(`editor workbench snapshot ${width}x${height}`, async ({ page }) => {
  await page.route("**/api/projects", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ projects: [{ project_id: "local-draft", name: "편집 작업판", status: "active", root_storage_uri: "local://editor-workbench" }] }) }));
  await page.route("**/playback-manifest", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(manifest) }));
  await page.setViewportSize({ width, height });
  await page.goto("/projects/local-draft/editor?session_id=editor-workbench-e2e");
  await expect(page.getByRole("region", { name: "편집 작업판" })).toBeVisible();
  await expect(page.getByRole("region", { name: "미리보기 자리" })).toBeVisible();
  await expect(page.locator("audio, video")).toHaveCount(0);
  if (width >= 1280) await expect(page.getByRole("region", { name: "미리보기 자리" })).toHaveAttribute("data-preview-min-width", width >= 1600 ? "720" : "640");
  await page.screenshot({ path: `e2e/snapshots/editor-workbench-${width}x${height}.png`, animations: "disabled", caret: "hide" });
});
