import { expect, test } from "./support/test-fixtures.mjs";
import { fulfillLocalMp4WithRanges } from "./support/valid-local-mp4-fixture.mjs";

const project = {
  project_id: "local-draft",
  name: "정확 미리보기 E2E",
  status: "active",
  root_storage_uri: "local://exact-preview-e2e",
};

function manifest({
  revision = 7,
  exact = { status: "succeeded", url: "/api/projects/local-draft/exact-previews/generation-7/content", artifact_revision: 7, timeline_start_sec: 2, timeline_end_sec: 8 },
  auditionUrls = {},
  tracks = [],
} = {}) {
  return {
    project_id: "local-draft",
    session_id: "exact-preview-e2e",
    timeline_id: "timeline-exact-preview-e2e",
    session_revision: revision,
    timeline_version: `v${revision}`,
    timebase: "seconds",
    fps: { num: 30, den: 1 },
    output: { width: 1080, height: 1920, sample_aspect_ratio: "1:1", rotation: 0, duration_sec: 12 },
    tracks,
    captions: [],
    gap_slots: [],
    source_status: { status: "current", source_session_id: "exact-preview-e2e", source_session_revision: revision },
    audition: { asset_urls: auditionUrls },
    exact_preview: {
      source_session_id: "exact-preview-e2e",
      source_session_revision: revision,
      generation_id: "generation-7",
      ...exact,
    },
  };
}

function editingSession(playbackManifest) {
  const segmentIds = new Set(
    playbackManifest.tracks.flatMap((track) => track.clips.map((clip) => clip.segment_id)),
  );
  return {
    project_id: playbackManifest.project_id,
    session_id: playbackManifest.session_id,
    timeline_id: playbackManifest.timeline_id,
    session_revision: playbackManifest.session_revision,
    undo_count: 0,
    redo_count: 0,
    updated_at: "2026-07-24T00:00:00Z",
    history: [],
    segments: [...segmentIds].map((segmentId) => ({
      segment_id: segmentId,
      start_sec: 0,
      end_sec: playbackManifest.output.duration_sec,
      caption_text: "",
      cut_action: "keep",
      review_required: false,
      broll_override: null,
      music_override: null,
      sfx_override: null,
      tts_replacement: null,
      visual_overlays: [],
    })),
  };
}

async function installEditorRoutes(page, state) {
  await page.route("**/api/projects", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ projects: [project] }) }));
  await page.route("**/playback-manifest", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(state.current) }));
  await page.route(
    "**/api/projects/local-draft/editing-sessions/exact-preview-e2e",
    (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(editingSession(state.current)) }),
  );
  await page.route("**/exact-preview", async (route) => {
    state.retryBodies.push(route.request().postDataJSON());
    state.current = state.afterRetry ?? state.current;
    await route.fulfill({ contentType: "application/json", status: 202, body: JSON.stringify({ status: "pending", generation_id: "generation-8", timeline_start_sec: 2, timeline_end_sec: 8, artifact_revision: state.current.session_revision, fingerprint: "e2e" }) });
  });
  await page.route("**/content", async (route) => {
    const range = await route.request().headerValue("range");
    if (range) (state.rangeRequests ??= []).push(range);
    await fulfillLocalMp4WithRanges(route);
  });
}

async function openEditor(page, state) {
  await installEditorRoutes(page, state);
  await page.goto("/projects/local-draft/editor?session_id=exact-preview-e2e");
  await expect(page.getByRole("region", { name: "편집 작업판" })).toBeVisible();
}

test("current exact proxy plays a valid local MP4, requests bytes, and maps a native seek to the timeline", async ({ page }) => {
  const state = { current: manifest(), retryBodies: [], rangeRequests: [] };
  await openEditor(page, state);

  const video = page.getByLabel("편집본 미리보기");
  await expect(video).toHaveCount(1);
  await expect(video).toHaveAttribute("src", /exact-previews\/generation-7\/content$/);
  await expect(video).not.toHaveAttribute("autoplay");
  await expect(video).toHaveJSProperty("autoplay", false);
  await expect.poll(() => video.evaluate((node) => node.readyState >= HTMLMediaElement.HAVE_METADATA)).toBe(true);
  await expect.poll(() => video.evaluate((node) => node.readyState >= HTMLMediaElement.HAVE_FUTURE_DATA)).toBe(true);
  await expect.poll(() => video.evaluate((node) => node.duration)).toBeGreaterThan(1);
  // A real user gesture calls the component's native HTMLMediaElement.play()
  // path, avoiding an autoplay-policy bypass in the test harness.
  const playbackButton = page.getByRole("button", { name: "재생 또는 일시정지" });
  await playbackButton.scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate(() => new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve(window.scrollY)));
  }))).toBeGreaterThanOrEqual(0);
  await playbackButton.click();
  await expect.poll(() => video.evaluate((node) => !node.paused && node.currentTime > 0.05)).toBe(true);
  await playbackButton.click();
  await expect.poll(() => video.evaluate((node) => node.paused)).toBe(true);
  await expect.poll(() => state.rangeRequests.length).toBeGreaterThan(0);
  expect(state.rangeRequests).toContainEqual(expect.stringMatching(/^bytes=\d+-/));
  await video.evaluate((node) => { node.currentTime = 1.5; });
  await expect.poll(() => video.evaluate((node) => node.currentTime)).toBeCloseTo(1.5, 1);
  await expect(page.getByText("타임라인 3.5초", { exact: true })).toBeVisible();
  await expect(page.locator("audio, video")).toHaveCount(1);
});

test("pending proxy explains that playback is unavailable and does not mount media", async ({ page }) => {
  const state = { current: manifest({ exact: { status: "pending", url: null, artifact_revision: null } }), retryBodies: [] };
  await openEditor(page, state);

  await expect(page.locator(".vb-preview-stage__empty")).toContainText("미리보기를 준비하고 있어요.");
  await expect(page.locator("audio, video")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "미리보기 새로 만들기" })).toBeVisible();
});

test("source revision makes an older exact proxy stale and blocks its player", async ({ page }) => {
  const state = { current: manifest({ revision: 8, exact: { status: "succeeded", url: "/api/projects/local-draft/exact-previews/generation-7/content", artifact_revision: 7, timeline_start_sec: 2, timeline_end_sec: 8 } }), retryBodies: [] };
  await openEditor(page, state);

  await expect(page.locator(".vb-preview-stage__empty")).toContainText("이전 편집본 미리보기는 재생하지 않아요.");
  await expect(page.locator("audio, video")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "미리보기 새로 만들기" })).toBeVisible();
});

test("failed proxy retry requests the current revision and refreshes the surfaced status", async ({ page }) => {
  const state = {
    current: manifest({ exact: { status: "failed", url: null, artifact_revision: null } }),
    afterRetry: manifest({ exact: { status: "running", url: null, artifact_revision: null } }),
    retryBodies: [],
  };
  await openEditor(page, state);

  await expect(page.locator(".vb-preview-stage__empty")).toContainText("미리보기를 만들지 못했어요.");
  await page.getByRole("button", { name: "미리보기 새로 만들기" }).click();
  await expect.poll(() => state.retryBodies.length).toBe(1);
  expect(state.retryBodies).toEqual([{ expected_revision: 7 }]);
  await expect(page.locator(".vb-preview-stage__empty")).toContainText("편집본 미리보기를 만드는 중이에요.");
  await expect(page.locator("audio, video")).toHaveCount(0);
});

test("audition replaces the exact player without autoplay and can return to exact", async ({ page }) => {
  const state = {
    current: manifest({
      auditionUrls: { "asset-broll": "/api/projects/local-draft/assets/asset-broll/content" },
      tracks: [{ track_id: "broll", track_type: "broll", clips: [{ clip_id: "clip-broll", segment_id: "segment-1", clip_type: "broll", asset_id: "asset-broll", asset_uri: "local://asset-broll", start_sec: 4, end_sec: 9, media_controls: {} }] }],
    }),
    retryBodies: [],
  };
  await openEditor(page, state);

  await page.getByRole("button", { name: "B-roll · segment-1 원본 열기" }).click();
  const audition = page.getByLabel("B-roll · segment-1 소스 미리보기");
  await expect(audition).toHaveCount(1);
  await expect(audition).not.toHaveAttribute("autoplay");
  await expect(audition).toHaveJSProperty("autoplay", false);
  await expect(audition).toHaveJSProperty("paused", true);
  await expect(page.locator("audio, video")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "편집본으로 돌아가기" })).toBeVisible();
  await page.getByRole("button", { name: "편집본으로 돌아가기" }).click();
  await expect(page.getByLabel("편집본 미리보기")).toHaveCount(1);
  await expect(page.locator("audio, video")).toHaveCount(1);
});
