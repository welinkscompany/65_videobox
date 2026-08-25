import { expect, test } from "./support/test-fixtures.mjs";
import { validLocalMp4Fixture } from "./support/valid-local-mp4-fixture.mjs";

function validWavFixture() {
  const sampleRate = 8_000;
  const sampleCount = sampleRate;
  const body = Buffer.alloc(44 + sampleCount * 2);
  body.write("RIFF", 0); body.writeUInt32LE(body.length - 8, 4); body.write("WAVE", 8);
  body.write("fmt ", 12); body.writeUInt32LE(16, 16); body.writeUInt16LE(1, 20); body.writeUInt16LE(1, 22);
  body.writeUInt32LE(sampleRate, 24); body.writeUInt32LE(sampleRate * 2, 28); body.writeUInt16LE(2, 32); body.writeUInt16LE(16, 34);
  body.write("data", 36); body.writeUInt32LE(sampleCount * 2, 40);
  for (let index = 0; index < sampleCount; index += 1) body.writeInt16LE(Math.round(Math.sin(index / 8) * 1_500), 44 + index * 2);
  return body;
}

const validAudioFixture = validWavFixture();

const media = {
  broll: { id: "asset-broll", name: "commute.mp4", mime: "video/mp4", label: "도시 출근 장면" },
  music: { id: "asset-music", name: "morning.mp3", mime: "audio/mpeg", label: "차분한 아침 음악" },
  sfx: { id: "asset-sfx", name: "door-effect.wav", mime: "audio/wav", label: "문 닫는 효과음" },
  qa: { id: "asset-qa-delete", name: "qa-unused.mp3", mime: "audio/mpeg", label: "QA 삭제 대상" },
};

function asset({ id, name, mime, label, mediaType, lifecycle = "ready" }) {
  const type = mediaType ?? (mime.startsWith("video/") ? "broll" : name.includes("effect") || name.includes("door") ? "sfx" : "music");
  return {
    library_asset_id: id,
    asset_id: id,
    media_type: type,
    origin: "user",
    lifecycle,
    content_sha256: id.padEnd(64, "0").slice(0, 64),
    byte_count: 32,
    mime_type: mime,
    managed_relative_path: `assets/${id}`,
    technical_metadata: { duration_seconds: type === "broll" ? 12 : 6, width: type === "broll" ? 1920 : null, height: type === "broll" ? 1080 : null },
    machine_metadata: { description: label },
    user_metadata: { filename: name, tags: [label] },
    created_at: "2026-08-12T00:00:00Z",
    updated_at: "2026-08-12T00:00:00Z",
    trashed_at: lifecycle === "trashed" ? "2026-08-12T00:00:00Z" : null,
    preview_url: `/api/library/assets/${id}/preview`,
    thumbnail_url: type === "broll" ? `/api/library/assets/${id}/thumbnail` : null,
    waveform_url: type !== "broll" ? `/api/library/assets/${id}/waveform` : null,
  };
}

function json(route, payload, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(payload) });
}

async function installLibraryApi(page) {
  const state = {
    assets: [
      asset({ ...media.broll, mediaType: "broll" }),
      asset({ ...media.music, mediaType: "music" }),
      asset({ ...media.sfx, mediaType: "sfx" }),
      asset({ ...media.qa, mediaType: "music" }),
    ],
    usage: new Map(),
    sourceBytesUnchanged: true,
    ingestCalls: 0,
    uploadedBodies: [],
  };

  await page.route("**/api/library/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const idMatch = path.match(/^\/api\/library\/assets\/([^/]+)(?:\/(.*))?$/);
    const id = idMatch ? decodeURIComponent(idMatch[1]) : null;
    const action = idMatch?.[2] ?? null;

    if (path === "/api/library/assets" && request.method() === "GET") {
      const query = url.searchParams.get("q")?.trim().toLowerCase() ?? "";
      if (query.includes("1000")) {
        const synthetic = Array.from({ length: 1000 }, (_, index) => asset({
          id: `synthetic-${index}`,
          name: `synthetic-${String(index).padStart(4, "0")}.mp4`,
          mime: "video/mp4",
          label: "1000행 레이아웃 fixture",
          mediaType: "broll",
        }));
        return json(route, { assets: synthetic, total: synthetic.length });
      }
      const includeTrashed = url.searchParams.get("include_trashed") === "true";
      const assets = state.assets.filter((item) => includeTrashed || item.lifecycle !== "trashed").filter((item) => {
        if (!query) return true;
        const filename = String(item.user_metadata?.filename ?? "").toLowerCase();
        const description = String(item.machine_metadata?.description ?? "").toLowerCase();
        return filename.includes(query) || description.includes(query) || (query === "도시" && item.media_type === "broll") || (query === "음악" && item.media_type === "music") || (query === "효과음" && item.media_type === "sfx");
      });
      return json(route, { assets, total: assets.length });
    }

    if (path === "/api/library/ingest" && request.method() === "POST") {
      state.ingestCalls += 1;
      const body = request.postDataBuffer() ?? Buffer.alloc(0);
      state.uploadedBodies.push(body);
      // The source fixtures are copied into the request; the fake authority never mutates them.
      if (!body.includes(Buffer.from("video-source")) && !body.includes(Buffer.from("music-source")) && !body.includes(Buffer.from("sfx-source"))) state.sourceBytesUnchanged = false;
      const bodyText = body.toString("utf8");
      if (bodyText.includes("commute.mp4")) {
        return json(route, { ingest_batch_id: "batch-broll", partial: false, items: [{ filename: "commute.mp4", state: "ready", library_asset_id: media.broll.id }] });
      }
      if (bodyText.includes("morning.mp3") || bodyText.includes("duplicate.mp3")) {
        return json(route, { ingest_batch_id: "batch-music", partial: false, items: [
          { filename: "morning.mp3", state: "ready", library_asset_id: media.music.id },
          { filename: "duplicate.mp3", state: "duplicate", library_asset_id: media.music.id },
        ] });
      }
      return json(route, { ingest_batch_id: "batch-sfx", partial: false, items: [{ filename: "door-effect.wav", state: "ready", library_asset_id: media.sfx.id }] });
    }

    if (id && action === "usage" && request.method() === "GET") {
      return json(route, { library_asset_id: id, locations: state.usage.get(id) ?? [] });
    }
    if (id && action === "materialize" && request.method() === "POST") {
      const location = { project_id: "local-draft", materialized_asset_id: `${id}-materialized`, reference_id: `ref-${id}`, location: { kind: "project", id: "local-draft", label: "여름 여행 영상 · 편집" } };
      state.usage.set(id, [location]);
      return json(route, { asset: state.assets.find((item) => item.library_asset_id === id), reference: { reference_id: location.reference_id, project_id: location.project_id, library_asset_id: id, materialized_asset_id: location.materialized_asset_id } }, 201);
    }
    if (id && action?.startsWith("references/") && request.method() === "DELETE") {
      state.usage.delete(id);
      return route.fulfill({ status: 204, body: "" });
    }
    if (id && action === "permanent" && request.method() === "DELETE") {
      if ((state.usage.get(id) ?? []).length > 0) return json(route, { detail: "asset_in_use", locations: state.usage.get(id) }, 409);
      state.assets = state.assets.filter((item) => item.library_asset_id !== id);
      return route.fulfill({ status: 204, body: "" });
    }
    if (id && action === "trash" && request.method() === "POST") {
      if ((state.usage.get(id) ?? []).length > 0) return json(route, { detail: "asset_in_use" }, 409);
      const next = state.assets.find((item) => item.library_asset_id === id);
      if (!next) return json(route, { detail: "not_found" }, 404);
      next.lifecycle = "trashed";
      next.trashed_at = "2026-08-12T00:01:00Z";
      return json(route, { asset: next });
    }
    if (id && action === "restore" && request.method() === "POST") {
      const next = state.assets.find((item) => item.library_asset_id === id);
      if (!next) return json(route, { detail: "not_found" }, 404);
      next.lifecycle = "ready";
      next.trashed_at = null;
      return json(route, { asset: next });
    }
    if (id && (action === "preview" || action === "thumbnail" || action === "waveform") && request.method() === "GET") {
      const contentType = action === "preview" ? (state.assets.find((item) => item.library_asset_id === id)?.media_type === "broll" ? "video/mp4" : "audio/mpeg") : "image/png";
      const body = action !== "preview" ? Buffer.from("derivative-bytes") : state.assets.find((item) => item.library_asset_id === id)?.media_type === "broll" ? validLocalMp4Fixture : validAudioFixture;
      return route.fulfill({ status: 200, contentType: action === "preview" && state.assets.find((item) => item.library_asset_id === id)?.media_type !== "broll" ? "audio/wav" : contentType, headers: { "Accept-Ranges": "bytes", "Content-Length": String(body.length) }, body });
    }
    return json(route, { detail: "unsupported_library_e2e_request" }, 404);
  });

  return state;
}

async function dispatchDrop(page, files) {
  await page.evaluate((items) => {
    const dataTransfer = new DataTransfer();
    for (const item of items) dataTransfer.items.add(new File([item.bytes], item.name, { type: item.type }));
    document.querySelector('[data-testid="library-dropzone"]')?.dispatchEvent(new DragEvent("drop", { bubbles: true, dataTransfer }));
  }, files);
}

async function fetchStatus(page, path, options = {}) {
  return page.evaluate(async ({ path, options }) => {
    const response = await fetch(path, { ...options, headers: { "content-type": "application/json", ...(options.headers ?? {}) } });
    let body = null;
    try { body = await response.json(); } catch { /* 204 */ }
    return { status: response.status, body };
  }, { path, options });
}

async function waitForMediaMetadata(locator) {
  await locator.evaluate((element) => {
    if (element.readyState >= 1) return;
    return new Promise((resolve, reject) => {
      element.addEventListener("loadedmetadata", () => resolve(), { once: true });
      element.addEventListener("error", () => reject(new Error("preview media failed to load")), { once: true });
    });
  });
}

test("library desktop keeps a bounded three-pane layout and reconciles mixed drop", async ({ page }) => {
  const state = await installLibraryApi(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/library");
  await expect(page.getByTestId("library-workspace")).toBeVisible();
  await expect(page.getByTestId("library-results-scroll")).toBeVisible();
  // 전역 목적지는 접힌 위 메뉴 한 곳에만 둔다. 메뉴를 연 뒤에만 링크가 DOM에
  // 나타나는 것이 현재 껍데기의 접근성 계약이다.
  await page.getByRole("button", { name: "전체 메뉴" }).click();
  await expect(page.getByRole("navigation", { name: "전체 메뉴" }).getByRole("link")).toHaveCount(3);

  await dispatchDrop(page, [
    { name: "commute.mp4", type: "video/mp4", bytes: "video-source" },
    { name: "morning.mp3", type: "audio/mpeg", bytes: "music-source" },
    { name: "duplicate.mp3", type: "audio/mpeg", bytes: "music-source" },
    { name: "door-effect.wav", type: "audio/wav", bytes: "sfx-source" },
    { name: "notes.txt", type: "text/plain", bytes: "invalid-source" },
  ]);
  await expect(page.getByRole("heading", { name: "등록 결과" })).toBeVisible();
  await expect(page.getByText("이미 등록됨")).toBeVisible();
  await expect(page.getByText("등록됨", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("notes.txt")).toBeVisible();
  await expect(page.getByText("확인 필요").first()).toBeVisible();
  expect(state.sourceBytesUnchanged).toBe(true);
  expect(state.uploadedBodies).toHaveLength(3);

  // Each media type has a real preview control in the right pane.
  await page.getByTestId("library-sidebar").getByRole("button", { name: "영상" }).click();
  await page.locator('[data-testid="library-asset-card"]').filter({ hasText: media.broll.name }).click();
  const videoPreview = page.locator(".vb-library-preview video");
  await expect(videoPreview).toHaveAttribute("src", /asset-broll\/preview/);
  await waitForMediaMetadata(videoPreview);
  await page.getByTestId("library-sidebar").getByRole("button", { name: "음악" }).click();
  await page.locator('[data-testid="library-audio-rows"] article').filter({ hasText: media.music.name }).click();
  const musicPreview = page.locator(".vb-library-preview audio");
  await expect(musicPreview).toHaveAttribute("src", /asset-music\/preview/);
  await waitForMediaMetadata(musicPreview);
  await page.getByTestId("library-sidebar").getByRole("button", { name: "효과음" }).click();
  await page.locator('[data-testid="library-audio-rows"] article').filter({ hasText: media.sfx.name }).click();
  const sfxPreview = page.locator(".vb-library-preview audio");
  await expect(sfxPreview).toHaveAttribute("src", /asset-sfx\/preview/);
  await waitForMediaMetadata(sfxPreview);

  // The list endpoint is the semantic-search authority for the desktop page.
  await page.getByTestId("library-sidebar").getByRole("button", { name: "전체" }).click();
  await page.getByPlaceholder("파일명·장면·분위기").fill("도시");
  await expect(page.locator('[data-testid="library-asset-card"]').filter({ hasText: media.broll.name })).toBeVisible();
  await page.getByTestId("library-sidebar").getByRole("button", { name: "음악" }).click();
  await page.getByPlaceholder("파일명·장면·분위기").fill("음악");
  await expect(page.locator('[data-testid="library-audio-rows"] article').filter({ hasText: media.music.name })).toBeVisible();
  await page.getByTestId("library-sidebar").getByRole("button", { name: "효과음" }).click();
  await page.getByPlaceholder("파일명·장면·분위기").fill("효과음");
  await expect(page.locator('[data-testid="library-audio-rows"] article').filter({ hasText: media.sfx.name })).toBeVisible();
  await page.getByPlaceholder("파일명·장면·분위기").fill("");
});

test("library uses the Full HD canvas for wider desktop panes without page overflow", async ({ page }) => {
  await installLibraryApi(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/library");
  await expect(page.getByTestId("library-workspace")).toBeVisible();
  const metrics = await page.evaluate(() => {
    const workspace = document.querySelector('[data-testid="library-workspace"]');
    const columns = getComputedStyle(workspace).gridTemplateColumns.split(" ").map((value) => Number.parseFloat(value));
    return {
      viewportWidth: window.innerWidth,
      workspaceWidth: workspace?.getBoundingClientRect().width ?? 0,
      // 이 화면은 이제 껍데기 안에 있다. 화면 전체가 아니라 **껍데기가 내준 자리**를
      // 남김없이 쓰는지가 기준이다(owner 지적 2026-08-19).
      availableWidth: workspace?.parentElement?.getBoundingClientRect().width ?? 0,
      leftPaneWidth: columns[0] ?? 0,
      previewPaneWidth: columns.at(-1) ?? 0,
      bodyScrollWidth: document.body.scrollWidth,
    };
  });
  // 껍데기가 본문에 주는 좌우 여백(최대 2.5rem씩)만 빼고 나머지를 다 쓴다.
  // 예전에는 화면 전체를 재던 자리다 -- 이제 좌측 메뉴가 늘 옆에 있으므로
  // 기준이 `화면`이 아니라 `내준 자리`다.
  expect(metrics.workspaceWidth).toBeGreaterThanOrEqual(metrics.availableWidth - 96);
  // 좌측 메뉴에 자리를 내주고도 세 칸이 넉넉히 살아 있어야 한다.
  expect(metrics.workspaceWidth).toBeGreaterThanOrEqual(1400);
  expect(metrics.leftPaneWidth).toBeGreaterThanOrEqual(256);
  expect(metrics.previewPaneWidth).toBeGreaterThanOrEqual(384);
  expect(metrics.bodyScrollWidth).toBeLessThanOrEqual(metrics.viewportWidth + 1);
});

test("library lifecycle blocks in-use delete, then allows remove, restore and explicit delete", async ({ page }) => {
  await installLibraryApi(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/library");
  await page.getByTestId("library-sidebar").getByRole("button", { name: "영상" }).click();
  await page.locator('[data-testid="library-asset-card"]').filter({ hasText: media.broll.name }).click();

  const materialized = await fetchStatus(page, `/api/library/assets/${media.broll.id}/materialize`, { method: "POST", body: JSON.stringify({ project_id: "local-draft" }) });
  expect(materialized.status).toBe(201);
  const blocked = await fetchStatus(page, `/api/library/assets/${media.broll.id}/permanent`, { method: "DELETE" });
  expect(blocked.status).toBe(409);
  expect(blocked.body.detail).toBe("asset_in_use");
  await page.reload();
  await page.getByTestId("library-sidebar").getByRole("button", { name: "영상" }).click();
  await page.locator('[data-testid="library-asset-card"]').filter({ hasText: media.broll.name }).click();
  await expect(page.getByText("사용 중인 위치")).toBeVisible();
  await expect(page.getByRole("button", { name: "휴지통으로 이동" })).toBeDisabled();

  const referenceRemoved = await fetchStatus(page, `/api/library/assets/${media.broll.id}/references/ref-${media.broll.id}`, { method: "DELETE" });
  expect(referenceRemoved.status).toBe(204);
  const deletedWhileUnused = await fetchStatus(page, `/api/library/assets/${media.broll.id}/permanent`, { method: "DELETE" });
  expect(deletedWhileUnused.status).toBe(204);

  const trash = await fetchStatus(page, `/api/library/assets/${media.qa.id}/trash`, { method: "POST" });
  expect(trash.status).toBe(200);
  const restore = await fetchStatus(page, `/api/library/assets/${media.qa.id}/restore`, { method: "POST" });
  expect(restore.status).toBe(200);
  const qaTrash = await fetchStatus(page, `/api/library/assets/${media.qa.id}/trash`, { method: "POST" });
  expect(qaTrash.status).toBe(200);
  const qaDelete = await fetchStatus(page, `/api/library/assets/${media.qa.id}/permanent`, { method: "DELETE" });
  expect(qaDelete.status).toBe(204);
});

test("1000 synthetic library rows stay inside the center scroll without mutating runtime data", async ({ page }) => {
  await installLibraryApi(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/library");
  await page.getByPlaceholder("파일명·장면·분위기").fill("1000-row fixture");
  await expect(page.locator('[data-testid="library-asset-card"]')).toHaveCount(24);
  const metrics = await page.evaluate(() => {
    const center = document.querySelector('[data-testid="library-results-scroll"]');
    const workspace = document.querySelector('[data-testid="library-workspace"]');
    return {
      centerClientHeight: center?.clientHeight ?? 0,
      centerScrollHeight: center?.scrollHeight ?? 0,
      workspaceScrollHeight: workspace?.scrollHeight ?? 0,
      workspaceClientHeight: workspace?.clientHeight ?? 0,
      bodyScrollHeight: document.body.scrollHeight,
      viewportHeight: window.innerHeight,
    };
  });
  expect(metrics.centerScrollHeight).toBeGreaterThan(metrics.centerClientHeight);
  expect(metrics.workspaceScrollHeight).toBeLessThanOrEqual(metrics.workspaceClientHeight + 1);
  expect(metrics.bodyScrollHeight).toBeLessThanOrEqual(metrics.viewportHeight + 16);
});
