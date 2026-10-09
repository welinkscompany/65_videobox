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
    // 화면은 `?include_history=false`를 붙여 읽는다 -- 끝의 `*`가 그 쿼리를 받는다.
    "**/api/projects/local-draft/editing-sessions/exact-preview-e2e*",
    (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(editingSession(state.current)) }),
  );
  await page.route("**/exact-preview", async (route) => {
    state.retryBodies.push(route.request().postDataJSON());
    state.current = state.afterRetry ?? state.current;
    await route.fulfill({ contentType: "application/json", status: 202, body: JSON.stringify({ status: "pending", generation_id: "generation-8", timeline_start_sec: 2, timeline_end_sec: 8, artifact_revision: state.current.session_revision, fingerprint: "e2e" }) });
  });
  // 기다리는 동안 화면이 묻는 가벼운 상태 길. 시험이 `state.status`로 답을 정한다(기본: 아직 만드는 중).
  await page.route(/\/exact-previews\/[^/]+$/, (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ status: "running", generation_id: "generation-8", timeline_start_sec: 2, timeline_end_sec: 8, artifact_revision: 8, fingerprint: "e2e", ...(state.status ?? {}) }),
  }));
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

async function ensureDockOpen(page, name) {
  const workbench = page.getByRole("region", { name: "편집 작업판" });
  await expect.poll(async () => Number(await workbench.getAttribute("data-available-workbench-width"))).toBeGreaterThan(0);
  if (await page.getByRole("complementary", { name }).count()) return;
  await page.getByRole("button", { name }).click();
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

  // **두 도크를 다 편 상태도 잰다.** 오른쪽까지 열면 미리보기 폭이 320px 줄어
  // 면적이 확 떨어진다 -- 여기서는 18.9%로 위의 20.8% 아래다.
  //
  // 그래서 위 하한을 낮추지 않았고, 타임라인을 도로 줄이지도 않았다. 둘은 이
  // 조합에서 **동시에 만족시킬 수 없다**: 1920x1080에서 오른쪽 도크가 폭을 가져가면
  // "눈금과 트랙이 다 보인다"와 "면적 20.8%"가 서로를 배제한다.
  //
  // 20.8%는 2026-07-22에 **기본 배치에서** 되찾은 값이고, 오른쪽 도크를 여는 것은
  // 창작자가 미리보기 폭을 참고 패널과 바꾸겠다고 고른 것이다. 그 선택까지 같은
  // 하한으로 묶으면 승인문이 실제로 정한 것보다 좁게 잠근다. 승인문이 건 조건은
  // 하나였다 -- **예전 8.5% 수준으로 되돌아가지 않을 것.** 그것을 지킨다.
  await ensureDockOpen(page, "세부 정보");
  await expect(page.getByRole("region", { name: "편집 작업판" })).toHaveAttribute("data-editor-density", "desktop-both");
  const bothDocks = await page.evaluate(() => {
    const video = document.querySelector(".vb-preview-stage__media-shell video").getBoundingClientRect();
    return (video.width * video.height) / (window.innerWidth * window.innerHeight) * 100;
  });
  expect(bothDocks).toBeGreaterThanOrEqual(15);
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
  // 재생 위치와 전체 길이를 함께 보여 준다. 전체 길이는 출력 형식에 따라 붙으므로
  // 위치 값만 완전하게 지킨다.
  await expect(page.locator(".vb-preview-stage__playback output")).toContainText("타임라인 3.5");
  await expect(page.locator("audio, video")).toHaveCount(1);
});

// 셋 다 **빈 타임라인이 아닌** 매니페스트를 준다. `EditorWorkbench.tsx`가
// `PreviewStage`에 넘기는 `projectIsEmpty`는 `view.tracks.length === 0`로만
// 정해지고(2026-09-04 owner 지시: "아직 아무것도 안 넣었으면 실패라고 말하지
// 않는다"), 트랙이 비어 있으면 exact_preview 상태(pending/stale/failed)와
// 무관하게 항상 "여기에 영상이 나와요"(빈 프로젝트 안내)만 그린다. 이 세
// 시험은 원래 `tracks: []`인 채로 상태별 안내 문구를 기대해서 서로 모순이었다
// -- 실제로 지키려는 것("이미 채운 프로젝트에서 exact preview 상태를 있는
// 그대로 보여준다")을 재려면 트랙을 채워야 한다. 빈 프로젝트 안내 자체를
// 지키는 시험은 `empty-project-stage.test.tsx`에 이미 있고 그대로 둔다.
const oneNarrationClip = [
  { track_id: "narration", track_type: "narration", clips: [{ clip_id: "n1", segment_id: "segment-1", clip_type: "narration", asset_id: "a1", asset_uri: "local://a1", start_sec: 0, end_sec: 6, media_controls: {} }] },
];

test("pending proxy explains that playback is unavailable and does not mount media", async ({ page }) => {
  const state = { current: manifest({ tracks: oneNarrationClip, exact: { status: "pending", url: null, artifact_revision: null } }), retryBodies: [] };
  await openEditor(page, state);

  await expect(page.locator(".vb-preview-stage__empty")).toContainText("미리보기를 준비하고 있어요.");
  await expect(page.locator("audio, video")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "미리보기 새로 만들기" })).toBeVisible();
});

test("source revision makes an older exact proxy stale and blocks its player", async ({ page }) => {
  const state = { current: manifest({ tracks: oneNarrationClip, revision: 8, exact: { status: "succeeded", url: "/api/projects/local-draft/exact-previews/generation-7/content", artifact_revision: 7, timeline_start_sec: 2, timeline_end_sec: 8 } }), retryBodies: [] };
  await openEditor(page, state);

  await expect(page.locator(".vb-preview-stage__empty")).toContainText("편집이 바뀌었어요. 미리보기를 새로 만들어 주세요.");
  await expect(page.locator("audio, video")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "미리보기 새로 만들기" })).toBeVisible();
});

test("failed proxy retry requests the current revision and refreshes the surfaced status", async ({ page }) => {
  const state = {
    current: manifest({ tracks: oneNarrationClip, exact: { status: "failed", url: null, artifact_revision: null } }),
    afterRetry: manifest({ tracks: oneNarrationClip, exact: { status: "running", url: null, artifact_revision: null } }),
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
  // 돌아오는가**다. 미디어 열을 여는 클릭은 그 원본 버튼에 닿기 위한 수단이었는데,
  // 이제 그 열은 기본으로 펴져 있다 -- 누르면 오히려 닫혀 버튼이 사라진다.
  await expect(page.getByRole("complementary", { name: "미디어" })).toBeVisible();
  // "원본 열기" 버튼은 네이티브 `<details>`("원본 확인")로 접혀 있다
  // (`EditorAssetBrowser.tsx`: `pane === "media" && sourceCheck ? <details
  // className="vb-editor-assets__aside"><summary>원본 확인</summary>...`).
  // "미디어 분석"과 같은 무늬다 -- 기본으로 닫혀 있어 열기 전까지는 안의
  // 단추가 `hidden`이다.
  await page.getByText("원본 확인", { exact: true }).click();
  // "B-roll"은 2026-09-07에 화면에서 "영상"으로 통일됐다(owner 승인,
  // `SideNav.tsx` 주석 참고 -- 자료실 분류 목록도 이미 "영상"이었다).
  await page.getByRole("button", { name: "영상 · 1번째 장면 원본 열기" }).click();
  const audition = page.getByLabel("영상 · 1번째 장면 원본 재생");
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

test("1280x720에서도 타임라인이 한 화면 안에서 트랙 셋 이상을 보여 준다 (2026-10-08 §3-9)", async ({ page }) => {
  const clip = (id, type, segment, from, to) => ({ clip_id: id, segment_id: segment, clip_type: type, asset_id: `a-${id}`, asset_uri: `local://a-${id}`, start_sec: from, end_sec: to, media_controls: {} });
  const state = {
    current: manifest({
      tracks: [
        { track_id: "narration", track_type: "narration", clips: [clip("n1", "narration", "segment-1", 0, 6), clip("n2", "narration", "segment-2", 6, 12)] },
        { track_id: "broll", track_type: "broll", clips: [clip("b1", "broll", "segment-1", 1, 5)] },
        { track_id: "bgm", track_type: "bgm", clips: [clip("m1", "bgm", "segment-1", 0, 12)] },
      ],
    }),
    retryBodies: [],
  };
  await page.setViewportSize({ width: 1280, height: 720 });
  // 가짜 서버에 없는 목록 길(자산·가로세로)은 빈 목록으로 답한다. 안 그러면 "불러오지 못했어요" 상태 글
  // 두 줄이 작업판 위에 붙어 작업판을 화면 아래로 밀어, 이 시험이 재려는 배치가 아니라 그 글을 잰다.
  const empty = (body) => (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/api/projects/local-draft/assets/broll-video", empty({ assets: [] }));
  await page.route("**/api/media-library/assets", empty({ assets: [] }));
  await page.route("**/api/library/assets*", empty({ assets: [], total: 0 }));
  await page.route("**/api/projects/local-draft/output-variants*", empty({ variants: [] }));
  await openEditor(page, state);
  await expect(page.getByRole("region", { name: "타임라인" })).toBeVisible();
  await expect.poll(() => page.locator(".vb-preview-stage__media-shell video").evaluate((node) => node.readyState >= HTMLMediaElement.HAVE_METADATA)).toBe(true);
  const seen = await page.evaluate(() => {
    const timeline = document.querySelector(".vb-editor-workbench__timeline");
    const box = timeline.getBoundingClientRect();
    // 트랙 줄(머리 칸의 항목)이 타임라인 상자 안에 통째로 보이는 개수.
    const lanes = [...document.querySelectorAll('.vb-timeline-lane-headers [role="listitem"]')].map((el) => el.getBoundingClientRect());
    const video = document.querySelector(".vb-preview-stage__media-shell video").getBoundingClientRect();
    return {
      docOverflow: document.documentElement.scrollHeight - window.innerHeight,
      bottom: box.bottom,
      height: box.height,
      lanesFullyVisible: lanes.filter((r) => r.top >= box.top - 1 && r.bottom <= Math.min(box.bottom, window.innerHeight) + 1).length,
      videoHeight: video.height,
    };
  });
  // 원인(2026-10-08 측정): 껍데기가 `min-height: 100svh`뿐이라 작업판 내용(미리보기 판 459px 등)이
  // 화면보다 크면 껍데기가 800px로 같이 자라 타임라인이 757px로 밀렸다(85px 중 37px만 보임).
  expect(seen.docOverflow).toBeLessThanOrEqual(1);
  expect(seen.bottom).toBeLessThanOrEqual(720);
  expect(seen.height).toBeGreaterThanOrEqual(130); // 눈금 + 32px 트랙 셋
  expect(seen.lanesFullyVisible).toBeGreaterThanOrEqual(3);
  // 미리보기가 사라지지는 않는다(영상 높이 바닥).
  expect(seen.videoHeight).toBeGreaterThan(100);
});
