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
    const editingSessionInternal = {
      session_id: "session_internal_voice",
      project_id: projectId,
      timeline_id: "timeline_internal_voice",
      session_revision: 4,
      undo_count: 0,
      redo_count: 0,
      updated_at: "2026-07-24T00:00:00Z",
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
    };
    if (method === "GET" && path === `/api/projects/${projectId}/editing-sessions/latest`) {
      await route.fulfill(json(editingSessionInternal));
      return;
    }
    // `/assets`(옛 자산 화면 주소)가 이제 `/editor`로 리다이렉트되면서
    // (`AppRouter.tsx` beforeLoad), `CanonicalEditorEntry`가 위 `latest`로
    // 찾은 세션 id로 곧장 편집기를 연다 -- 편집기는 **특정 id로** 세션과
    // 재생 정보를 다시 부른다. 이 둘을 안 채우면 "재생 내용을 불러오지
    // 못했어요" 오류 화면만 뜨고 그 아래 내레이션 단추까지 못 간다.
    if (method === "GET" && path === `/api/projects/${projectId}/editing-sessions/session_internal_voice`) {
      await route.fulfill(json(editingSessionInternal));
      return;
    }
    // 편집기가 열리면서 자연히 같이 부르는 것들이다(대화 이어받기·출력
    // 변형·전환 추천·유진 선호·작업 목록·현재 미리보기 요청) -- 이 시험이
    // 지키려는 것과 무관해 내용은 비워 둔다.
    if (method === "GET" && path === `/api/projects/${projectId}/director/sessions/session_internal_voice/reload`) {
      await route.fulfill(json({ conversation: null, messages: [], proposal: null, references: [] }));
      return;
    }
    if (method === "GET" && path === `/api/projects/${projectId}/output-variants`) {
      await route.fulfill(json({ variants: [] }));
      return;
    }
    if (method === "GET" && path === `/api/projects/${projectId}/editing-sessions/session_internal_voice/transition-suggestions`) {
      await route.fulfill(json({ suggestions: [] }));
      return;
    }
    if (method === "GET" && path === `/api/projects/${projectId}/director/preferences`) {
      await route.fulfill(json({}));
      return;
    }
    if (method === "GET" && path === `/api/projects/${projectId}/jobs`) {
      await route.fulfill(json({ jobs: [] }));
      return;
    }
    if (method === "POST" && path === `/api/projects/${projectId}/editing-sessions/session_internal_voice/exact-preview`) {
      await route.fulfill(json({ status: "unavailable", url: null, source_session_id: "session_internal_voice", source_session_revision: 4 }, 202));
      return;
    }
    if (method === "GET" && path === `/api/projects/${projectId}/editing-sessions/session_internal_voice/playback-manifest`) {
      await route.fulfill(json({
        project_id: projectId,
        session_id: "session_internal_voice",
        timeline_id: "timeline_internal_voice",
        session_revision: 4,
        timeline_version: "v4",
        timebase: "seconds",
        fps: { num: 30, den: 1 },
        output: { width: 1080, height: 1920, sample_aspect_ratio: "1:1", rotation: 0, duration_sec: 5 },
        tracks: [],
        captions: [],
        gap_slots: [],
        source_status: { status: "current", source_session_id: "session_internal_voice", source_session_revision: 4 },
        audition: { asset_urls: {} },
        exact_preview: { status: "unavailable", url: null, source_session_id: "session_internal_voice", source_session_revision: 4 },
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

  // `/assets`(구주소 별칭)는 이제 옛 자산 화면을 안 그린다 -- `AppRouter.tsx`의
  // `beforeLoad`가 `return_to` 없는 `assets` 단계 요청을 전부 `/editor`로
  // 리다이렉트한다(독립 "미디어" 단계 화면이 2026-09-01에 편집기로 접혔다).
  // 내레이션도 더 이상 탭이 아니라 **팝업**이다(owner 승인 2026-08-27,
  // `EditorAssetBrowser.tsx`의 "내레이션" 단추 → `Dialog`) -- 도크가
  // 220~400px라 목소리 등록·후보 생성·청취 승인을 다 넣기엔 좁아서다.
  await page.goto(`/projects/${projectId}/assets`);
  await expect(page.getByRole("region", { name: "편집 작업판" })).toBeVisible();
  await expect(page).toHaveURL(/\/editor\?session_id=/);
  await page.getByRole("button", { name: "내레이션", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "내레이션" })).toBeVisible();
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
  // 새로고침하면 이미 정식 주소(`/editor?session_id=...`)에 있으니 그대로
  // 남는다 -- 리다이렉트는 `/assets`로 **들어올 때만** 한 번 걸린다. 팝업은
  // 새로고침으로 닫힌 채 돌아오니 내레이션을 다시 열어야 한다.
  await expect(page.getByRole("region", { name: "편집 작업판" })).toBeVisible();
  await expect(page).toHaveURL(/\/editor\?session_id=/);
  await page.getByRole("button", { name: "내레이션", exact: true }).click();
  await expect(page.getByText("저장한 내 목소리 3개")).toBeVisible();
  await page.getByLabel("후보를 만들 구간").selectOption(activeSegmentId);
  await expect(page.getByText("후보 1 · 청취 승인됨")).toBeVisible();
  await expect(page.getByText("후보 2 · 청취 거부됨")).toBeVisible();

  const visibleCopy = await page.locator("body").innerText();
  // `ariaSnapshot()`에는 링크의 href도 덤프한다. 테스트용 project id가 URL에
  // 들어가는 것은 화면이나 보조기기 이름 누출이 아니므로, URL 문자열 대신 실제
  // 접근성 이름을 만드는 속성·연결 텍스트만 검사한다.
  const accessibleLabels = await page.locator("[aria-label], [aria-labelledby], img[alt]").evaluateAll((nodes) => nodes.map((node) => {
    const labelledBy = node.getAttribute("aria-labelledby");
    const labelledByText = labelledBy
      ? labelledBy.split(/\s+/).map((id) => document.getElementById(id)?.textContent ?? "").join(" ")
      : "";
    return [node.getAttribute("aria-label") ?? "", labelledByText, node.getAttribute("alt") ?? ""].join(" ");
  }).join("\n"));
  expect(visibleCopy).not.toMatch(internalIdPattern);
  expect(accessibleLabels).not.toMatch(internalIdPattern);
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
