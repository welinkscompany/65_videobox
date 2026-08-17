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

test("a bigger screen never shrinks the preview, and extra screen height goes to the timeline", async ({ page }) => {
  const state = { current: manifest(), retryBodies: [], rangeRequests: [] };
  const measure = () => page.evaluate(() => {
    const video = document.querySelector(".vb-preview-stage__media-shell video");
    const shell = document.querySelector(".vb-preview-stage__media-shell");
    const timeline = document.querySelector(".vb-editor-workbench__timeline");
    if (!video || !shell || !timeline) throw new Error("preview or timeline is missing");
    return {
      videoHeight: video.getBoundingClientRect().height,
      shellHeight: shell.getBoundingClientRect().height,
      timelineHeight: timeline.getBoundingClientRect().height,
    };
  });
  const at = async (width, height) => {
    await page.setViewportSize({ width, height });
    await expect.poll(async () => (await measure()).videoHeight).toBeGreaterThan(0);
    return measure();
  };

  await page.setViewportSize({ width: 1440, height: 900 });
  await openEditor(page, state);
  await expect.poll(() => page.locator(".vb-preview-stage__media-shell video").evaluate((node) => node.readyState >= HTMLMediaElement.HAVE_METADATA)).toBe(true);

  // 같은 높이에서 폭만 넓힌다. 타임라인이 먹는 높이는 폭과 아무 상관이 없어야
  // 하는데, 예전에는 1499px를 경계로 상한이 두 벌이라 1600x900이 1440x900보다
  // 미리보기를 107px 작게 그렸다. 옛 가드는 1440x900과 1920x**1080**만 비교해서
  // 늘어난 화면 높이에 가려 이걸 놓쳤다 -- 높이를 고정해야 보인다.
  const sameHeight = [await measure(), await at(1500, 900), await at(1600, 900), await at(1920, 900)];
  for (const wider of sameHeight.slice(1)) expect(wider.videoHeight).toBeCloseTo(sameHeight[0].videoHeight, 0);

  // 화면이 높아지면 미리보기는 줄지 않고, 늘어난 높이는 타임라인이 가져간다
  // (owner 승인 2026-08-17: 캡컷처럼 아래쪽을 타임라인이 쓴다).
  const medium = sameHeight[0];
  const fullHd = await at(1920, 1080);
  expect(fullHd.videoHeight).toBeGreaterThanOrEqual(medium.videoHeight);
  expect(fullHd.timelineHeight).toBeGreaterThan(medium.timelineHeight);

  // 2026-08-15에 출력 변형을 접어 미리보기 판을 되찾았을 때 넣은 줄이다. 그때는
  // `400px`라는 숫자로 적었는데, 타임라인이 아래쪽을 넉넉히 쓰게 되자 그 숫자가
  // 승인된 정책보다 먼저 걸렸다. 지키려는 것은 숫자가 아니라 **미리보기가 여전히
  // 작업판에서 가장 큰 한 칸**이라는 것이다. 승인된 하한(화면 면적 20.8%)은 아래
  // `whole timeline` 가드가 실제 면적으로 잰다.
  const workbenchHeight = await page.locator(".vb-editor-workbench").evaluate((node) => node.getBoundingClientRect().height);
  expect(fullHd.shellHeight).toBeGreaterThan(workbenchHeight / 3);

  // 폰에서도 **둘 다 보여야 한다.** 2026-08-17에 타임라인 상한을 40vh로 올렸을 때
  // 390x844에서 타임라인이 364px를 먹고 미리보기 영상이 **0px**가 됐다 -- 단위
  // 테스트도 스냅샷도 초록이었다. 그 스냅샷은 미리보기가 빈 상태라 영상이 없었고,
  // 그래서 무너질 것이 없었다. 실제 영상을 올려놓고 높이를 재야 보인다.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByRole("region", { name: "편집 작업판" })).toBeVisible();
  await expect(page.locator(".vb-preview-stage__media-shell video")).toHaveCount(1);
  await expect.poll(async () => (await measure()).videoHeight).toBeGreaterThan(0);
  const phone = await measure();
  expect(phone.videoHeight).toBeGreaterThan(40);
  expect(phone.timelineHeight).toBeGreaterThan(150);
  // 40px는 넉넉해서 고른 값이 아니라 **지금 실제로 나오는 값(약 60px)** 아래에
  // 둔 선이다. 390px에서는 미리보기 판의 글자 줄 여섯 개가 줄바꿈되면서 292px짜리
  // 판에서 230px를 가져간다 -- 남은 자리가 그것뿐이다. 이걸 더 키우려면 그 글자
  // 줄들을 좁은 화면에서 어떻게 접을지 정해야 하고, 그건 owner 판단이다.
  // 여기서 지키는 것은 "0px로 무너지지 않는다"이다.
});

test("a Full HD screen shows the whole timeline without hiding it in its own scroll, and still keeps the approved preview size", async ({ page }) => {
  const state = {
    current: manifest({
      tracks: [
        { track_id: "narration", track_type: "narration", clips: [{ clip_id: "n1", segment_id: "segment-1", clip_type: "narration", asset_id: "a1", asset_uri: "local://a1", start_sec: 0, end_sec: 6, media_controls: {} }, { clip_id: "n2", segment_id: "segment-2", clip_type: "narration", asset_id: "a1", asset_uri: "local://a1", start_sec: 6, end_sec: 12, media_controls: {} }] },
        { track_id: "broll", track_type: "broll", clips: [{ clip_id: "b1", segment_id: "segment-1", clip_type: "broll", asset_id: "a2", asset_uri: "local://a2", start_sec: 1, end_sec: 5, media_controls: {} }] },
      ],
    }),
    retryBodies: [],
  };
  await page.setViewportSize({ width: 1920, height: 1080 });
  await openEditor(page, state);
  await expect.poll(() => page.locator(".vb-preview-stage__media-shell video").evaluate((node) => node.readyState >= HTMLMediaElement.HAVE_METADATA)).toBe(true);

  const seen = await page.evaluate(() => {
    const timeline = document.querySelector(".vb-editor-workbench__timeline");
    const video = document.querySelector(".vb-preview-stage__media-shell video").getBoundingClientRect();
    return {
      hidden: timeline.scrollHeight - timeline.clientHeight,
      areaPercent: (video.width * video.height) / (window.innerWidth * window.innerHeight) * 100,
    };
  });

  // owner가 2026-08-17에 승인한 것은 "타임라인을 아래쪽으로 넉넉히"였다. 그때 든
  // 이유가 이것이다 -- **눈금과 트랙이 자체 스크롤 안에 숨는다.** 숨은 픽셀이 0이어야
  // 승인한 것이 실제로 된 것이다.
  expect(seen.hidden).toBeLessThanOrEqual(1);
  // 같은 승인문이 감수 사항으로 "미리보기 세로 공간이 줄어든다"를 적었고, 조건은
  // 하나였다 -- **예전 8.5% 수준으로 되돌아가지 않는다.** 2026-07-22에 되찾은
  // 수준이 화면 면적의 20.8%이므로 그것을 바닥으로 둔다.
  expect(seen.areaPercent).toBeGreaterThanOrEqual(20.8);
});

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
  const previewGeometry = await page.evaluate(() => {
    const preview = document.querySelector(".vb-editor-workbench__preview");
    const media = document.querySelector(".vb-preview-stage__media-shell");
    const video = document.querySelector(".vb-preview-stage__media-shell video");
    const box = (selector) => {
      const node = document.querySelector(selector);
      if (!node) return null;
      const rect = node.getBoundingClientRect();
      return { top: rect.top, height: rect.height, scrollHeight: node.scrollHeight };
    };
    if (!preview || !media || !video) throw new Error("preview geometry nodes are missing");
    const mediaBox = media.getBoundingClientRect();
    const videoBox = video.getBoundingClientRect();
    return {
      previewClientHeight: preview.clientHeight,
      previewScrollHeight: preview.scrollHeight,
      mediaClientHeight: media.clientHeight,
      videoWidth: videoBox.width,
      videoHeight: videoBox.height,
      videoTop: videoBox.top,
      videoBottom: videoBox.bottom,
      mediaTop: mediaBox.top,
      mediaBottom: mediaBox.bottom,
      workbench: box(".vb-editor-workbench"),
      toolbar: box(".vb-editor-workbench__toolbar"),
      body: box(".vb-editor-workbench__body"),
      variants: box(".vb-editor-variants"),
      timeline: box(".vb-editor-workbench__timeline"),
      panels: box(".vb-editor-workbench__panels"),
      stagePanel: box(".vb-editor-workbench__stage-panel"),
      stage: box(".vb-preview-stage"),
    };
  });
  expect(previewGeometry.previewScrollHeight).toBeLessThanOrEqual(previewGeometry.previewClientHeight + 1);
  expect(previewGeometry.mediaClientHeight).toBeGreaterThan(0);
  expect(previewGeometry.videoWidth).toBeGreaterThan(0);
  expect(previewGeometry.videoHeight).toBeGreaterThanOrEqual(120);
  expect(previewGeometry.videoTop).toBeGreaterThanOrEqual(previewGeometry.mediaTop - 1);
  expect(previewGeometry.videoBottom).toBeLessThanOrEqual(previewGeometry.mediaBottom + 1);
  // A real user gesture calls the component's native HTMLMediaElement.play()
  // path, avoiding an autoplay-policy bypass in the test harness.
  const playbackButton = page.getByRole("button", { name: "재생 또는 일시정지" });
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

  // 이 테스트가 지키는 것은 **원본 미리보기가 편집본 플레이어를 대체하고 다시
  // 돌아오는가**다. 재료 열을 여는 클릭은 그 원본 버튼에 닿기 위한 수단이었는데,
  // 이제 그 열은 기본으로 펴져 있다 -- 누르면 오히려 닫혀 버튼이 사라진다.
  await expect(page.getByRole("complementary", { name: "자산과 대본" })).toBeVisible();
  await page.getByRole("button", { name: "B-roll · 1번째 장면 원본 열기" }).click();
  const audition = page.getByLabel("B-roll · 1번째 장면 소스 미리보기");
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
