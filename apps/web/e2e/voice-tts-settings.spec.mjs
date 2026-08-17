import { expect, test } from "./support/test-fixtures.mjs";

const projectId = "project_internal_voice";
const activeSegmentId = "segment_internal_active";
const removedSegmentId = "segment_internal_removed";
const internalIdPattern = /project_internal|session_internal|timeline_internal|segment_internal|sample_internal|candidate_internal|asset_internal/;

function json(body, status = 200) {
  return {
    body: JSON.stringify(body),
    contentType: "application/json",
    status,
  };
}

function silentWav() {
  const sampleRate = 8_000;
  const sampleCount = 800;
  const wav = Buffer.alloc(44 + sampleCount, 128);
  wav.write("RIFF", 0);
  wav.writeUInt32LE(36 + sampleCount, 4);
  wav.write("WAVEfmt ", 8);
  wav.writeUInt32LE(16, 16);
  wav.writeUInt16LE(1, 20);
  wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(sampleRate, 24);
  wav.writeUInt32LE(sampleRate, 28);
  wav.writeUInt16LE(1, 32);
  wav.writeUInt16LE(8, 34);
  wav.write("data", 36);
  wav.writeUInt32LE(sampleCount, 40);
  return wav;
}

test("manages voice samples and TTS listening review at the canonical settings route", async ({ page }) => {
  const state = {
    samples: [
      {
        asset_id: "sample_internal_original",
        asset_type: "voice_sample_audio",
        storage_uri: "local://voice/original.wav",
      },
    ],
    candidates: [
      {
        candidate_id: "candidate_internal_existing",
        project_id: projectId,
        segment_id: activeSegmentId,
        asset_id: "asset_internal_existing",
        source_text: "남겨 둔 문장을 제 목소리로 읽습니다.",
        technical_status: "accepted",
        operator_review_status: "pending",
        created_at: "2026-07-24T00:00:00Z",
      },
    ],
  };
  const browserRequests = [];
  const apiRequests = [];
  const unexpectedApiCalls = [];
  let uploadWasMultipart = false;
  let uploadIncludedFilename = false;
  let assetContentRequestCount = 0;

  page.on("request", (request) => {
    browserRequests.push({
      method: request.method(),
      resourceType: request.resourceType(),
      url: request.url(),
    });
  });
  await page.addInitScript(() => {
    window.localStorage.removeItem("videobox.last-valid-project");
  });
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const path = url.pathname;
    const contentType = request.headers()["content-type"] ?? "";
    apiRequests.push({ contentType, method, path, postData: request.postData() });

    if (method === "GET" && path === "/api/projects") {
      await route.fulfill(json({
        projects: [
          {
            project_id: projectId,
            name: "목소리 데모",
            status: "active",
            root_storage_uri: "local://voice-demo",
          },
        ],
      }));
      return;
    }
    if (method === "GET" && path === `/api/projects/${projectId}/assets/voice-sample`) {
      await route.fulfill(json({ assets: state.samples }));
      return;
    }
    if (method === "POST" && path === `/api/projects/${projectId}/assets/voice-sample`) {
      const payload = request.postDataJSON();
      if (payload.source_path !== "D:\\voices\\registered.wav") {
        await route.fulfill(json({ detail: "unexpected local path" }, 400));
        return;
      }
      const sample = {
        asset_id: "sample_internal_registered",
        asset_type: "voice_sample_audio",
        storage_uri: "local://voice/registered.wav",
      };
      state.samples.push(sample);
      await route.fulfill(json(sample, 201));
      return;
    }
    if (method === "POST" && path === `/api/projects/${projectId}/assets/voice-sample/upload`) {
      const uploadBody = request.postDataBuffer()?.toString("latin1") ?? "";
      uploadWasMultipart = contentType.startsWith("multipart/form-data; boundary=");
      uploadIncludedFilename = uploadBody.includes('filename="uploaded-voice.wav"');
      const sample = {
        asset_id: "sample_internal_uploaded",
        asset_type: "voice_sample_audio",
        storage_uri: "local://voice/uploaded.wav",
      };
      state.samples.push(sample);
      await route.fulfill(json(sample, 201));
      return;
    }
    if (method === "GET" && path === `/api/projects/${projectId}/editing-sessions/latest`) {
      await route.fulfill(json({
        session_id: "session_internal_voice",
        project_id: projectId,
        timeline_id: "timeline_internal_voice",
        session_revision: 4,
        history: [],
        segments: [
          {
            segment_id: removedSegmentId,
            caption_text: "삭제된 문장은 선택할 수 없습니다.",
            start_sec: 0,
            end_sec: 2,
            cut_action: "remove",
            review_required: false,
            broll_override: null,
            visual_overlays: [],
            music_override: null,
            sfx_override: null,
            tts_replacement: null,
          },
          {
            segment_id: activeSegmentId,
            caption_text: "남겨 둔 문장을 제 목소리로 읽습니다.",
            start_sec: 2,
            end_sec: 5,
            cut_action: "keep",
            review_required: false,
            broll_override: null,
            visual_overlays: [],
            music_override: null,
            sfx_override: null,
            tts_replacement: null,
          },
        ],
      }));
      return;
    }
    if (
      method === "GET"
      && path === `/api/projects/${projectId}/segments/${activeSegmentId}/tts-candidates`
    ) {
      await route.fulfill(json({ candidates: state.candidates }));
      return;
    }
    if (method === "POST" && path === `/api/projects/${projectId}/tts-candidates`) {
      const payload = request.postDataJSON();
      if (
        payload.segment_id !== activeSegmentId
        || payload.segment_text !== "남겨 둔 문장을 제 목소리로 읽습니다."
        || payload.voice_sample_asset_id !== "sample_internal_original"
        || payload.target_duration_sec !== 3
      ) {
        await route.fulfill(json({ detail: "unexpected generation payload" }, 400));
        return;
      }
      const candidate = {
        candidate_id: "candidate_internal_generated",
        project_id: projectId,
        segment_id: activeSegmentId,
        asset_id: "asset_internal_generated",
        asset_type: "generated_tts_audio",
        storage_uri: "local://tts/generated.wav",
        source_text: payload.segment_text,
        technical_status: "accepted",
        operator_review_status: "pending",
        created_at: "2026-07-24T00:01:00Z",
      };
      state.candidates.push(candidate);
      await route.fulfill(json(candidate, 201));
      return;
    }
    const reviewMatch = path.match(
      new RegExp(`^/api/projects/${projectId}/tts-candidates/([^/]+)/listening-review$`),
    );
    if (method === "PATCH" && reviewMatch) {
      const candidate = state.candidates.find((item) => item.candidate_id === reviewMatch[1]);
      const decision = request.postDataJSON().decision;
      if (!candidate || !["approved", "rejected"].includes(decision)) {
        await route.fulfill(json({ detail: "unexpected listening review" }, 400));
        return;
      }
      candidate.operator_review_status = decision;
      await route.fulfill(json(candidate));
      return;
    }
    const assetMatch = path.match(
      new RegExp(`^/api/projects/${projectId}/assets/([^/]+)/content$`),
    );
    if (method === "GET" && assetMatch) {
      assetContentRequestCount += 1;
      await route.fulfill({
        body: silentWav(),
        contentType: "audio/wav",
        headers: { "Accept-Ranges": "bytes" },
        status: 200,
      });
      return;
    }

    // 목소리 화면이 자산 단계로 옮겨오면서 자산 화면 자신의 조회가 함께 실린다.
    // 전부 로컬 조회이고, 이 spec이 지키려는 것은 **바깥 provider를 부르지 않는 것**이다.
    if (method === "GET" && path === "/api/media-inbox/assets") {
      await route.fulfill(json({ assets: [] }));
      return;
    }
    if (method === "GET" && path === `/api/projects/${projectId}/assets/broll-video`) {
      await route.fulfill(json({ assets: [] }));
      return;
    }
    if (method === "GET" && path === `/api/projects/${projectId}/media-analysis`) {
      await route.fulfill(json({ items: [] }));
      return;
    }
    if (method === "GET" && path === `/api/projects/${projectId}/assets/narration-audio`) {
      await route.fulfill(json({ assets: [] }));
      return;
    }
    if (method === "GET" && path === "/api/library/assets") {
      await route.fulfill(json({ assets: [], total: 0 }));
      return;
    }
    if (method === "GET" && path === "/api/media-library/assets") {
      await route.fulfill(json({ assets: [] }));
      return;
    }
    if (method === "GET" && path === "/api/media-library/install-state") {
      await route.fulfill(json({ installed: false, missing_asset_ids: [], asset_ids: [] }));
      return;
    }
    if (method === "GET" && path.endsWith("/media-library/recent")) {
      await route.fulfill(json({ asset_ids: [] }));
      return;
    }
    if (method === "GET" && path.endsWith("/media-library/favorites")) {
      await route.fulfill(json({ asset_ids: [] }));
      return;
    }

    unexpectedApiCalls.push({ method, path });
    await route.fulfill(json({ detail: "unexpected E2E API request" }, 501));
  });

  // 목소리 만들기는 2026-08-16에 설정에서 자산 단계의 `내레이션`으로 옮겼다.
  // 옛 설정 주소는 살아 있고 길만 알려 준다.
  await page.goto("/settings/voice");
  await expect(page).toHaveURL(/\/settings\/voice$/);
  await expect(page.getByRole("link", { name: "내레이션 열기" })).toBeVisible();

  await page.goto(`/projects/${projectId}/assets`);
  await page.getByRole("tab", { name: "내레이션" }).click();
  await expect(page.getByRole("region", { name: "내 목소리와 읽어보기 후보" })).toBeVisible();
  await expect(page.getByText("저장한 내 목소리 1개")).toBeVisible();

  await page.getByLabel("음성 파일이 있는 곳").fill("  D:\\voices\\registered.wav  ");
  await page.getByRole("button", { name: "이 위치로 추가" }).click();
  await expect(page.getByText("저장한 내 목소리 2개")).toBeVisible();

  await page.getByLabel("음성 파일 업로드").setInputFiles({
    buffer: Buffer.from("deterministic local voice fixture"),
    mimeType: "audio/wav",
    name: "uploaded-voice.wav",
  });
  await page.getByRole("button", { name: "파일 업로드", exact: true }).click();
  await expect(page.getByText("저장한 내 목소리 3개")).toBeVisible();
  expect(uploadWasMultipart).toBe(true);
  expect(uploadIncludedFilename).toBe(true);

  await page.getByRole("button", { name: "목록 새로고침" }).click();
  await expect(page.getByText("목소리 목록을 새로 불러왔어요.")).toBeVisible();
  await expect(page.getByRole("option", { name: /남겨 둔 문장을 제 목소리로 읽습니다/ })).toHaveCount(1);
  await expect(page.getByRole("option", { name: /삭제된 문장은 선택할 수 없습니다/ })).toHaveCount(0);

  await page.getByLabel("후보를 만들 구간").selectOption(activeSegmentId);
  await expect(page.getByText("후보 1 · 청취 확인 필요")).toBeVisible();
  const firstAudio = page.getByLabel("후보 1 들어보기");
  await expect(firstAudio).toHaveAttribute(
    "src",
    `/api/projects/${projectId}/assets/asset_internal_existing/content`,
  );
  await firstAudio.evaluate((audio) => audio.load());
  await expect.poll(() => assetContentRequestCount).toBeGreaterThan(0);

  await page.getByRole("button", { name: "내 목소리 후보 만들기" }).click();
  await expect(page.getByText("후보 2 · 청취 확인 필요")).toBeVisible();
  await expect(page.getByLabel("후보 2 들어보기")).toHaveAttribute(
    "src",
    `/api/projects/${projectId}/assets/asset_internal_generated/content`,
  );

  await page.getByRole("button", { name: "후보 1 청취 승인" }).click();
  await expect(page.getByText("후보 1 · 청취 승인됨")).toBeVisible();
  await page.getByRole("button", { name: "후보 2 청취 거부" }).click();
  await expect(page.getByText("후보 2 · 청취 거부됨")).toBeVisible();
  await expect(page.getByRole("button", { name: /자동.*적용|적용/ })).toHaveCount(0);

  await page.reload();
  await expect(page).toHaveURL(/\/assets$/);
  // 새로고침하면 자산 화면은 첫 탭으로 돌아온다. 내레이션을 다시 골라야 한다.
  await page.getByRole("tab", { name: "내레이션" }).click();
  await expect(page.getByText("저장한 내 목소리 3개")).toBeVisible();
  await page.getByLabel("후보를 만들 구간").selectOption(activeSegmentId);
  await expect(page.getByText("후보 1 · 청취 승인됨")).toBeVisible();
  await expect(page.getByText("후보 2 · 청취 거부됨")).toBeVisible();

  const visibleCopy = await page.locator("body").innerText();
  const accessibilityCopy = await page.locator("body").ariaSnapshot();
  expect(visibleCopy).not.toMatch(internalIdPattern);
  expect(accessibilityCopy).not.toMatch(internalIdPattern);
  expect(unexpectedApiCalls.map((call) => `${call.method} ${call.path}`).join(" | ")).toBe("");
  expect(
    apiRequests.filter(({ path }) => new RegExp(
      ["provider", "hermes", "mem0", "openai", ["ge", "mini"].join(""), "elevenlabs"].join("|"),
      "i",
    ).test(path)),
  ).toEqual([]);
  expect(
    apiRequests.filter(({ path }) => (
      /\/editing-sessions\/[^/]+\/segments\/[^/]+\/tts-replacement(?:\/apply)?$/.test(path)
      || /\/tts-candidates\/[^/]+\/apply$/.test(path)
    )),
  ).toEqual([]);
  expect(
    apiRequests.filter(({ method, path }) => method === "POST" && path === `/api/projects/${projectId}/tts-candidates`),
  ).toHaveLength(1);
  expect(
    apiRequests.filter(({ method, path }) => method === "PATCH" && path.endsWith("/listening-review")),
  ).toHaveLength(2);
  expect(state.samples).toHaveLength(3);
  expect(state.candidates.map(({ operator_review_status }) => operator_review_status)).toEqual([
    "approved",
    "rejected",
  ]);

  const currentOrigin = new URL(page.url()).origin;
  const forbiddenBrowserRequests = browserRequests.filter(({ url }) => {
    const parsed = new URL(url);
    if (parsed.protocol === "data:" || parsed.protocol === "blob:") return false;
    return parsed.origin !== currentOrigin
      || !["127.0.0.1", "localhost", "[::1]", "::1"].includes(parsed.hostname);
  });
  expect(forbiddenBrowserRequests).toEqual([]);
});
