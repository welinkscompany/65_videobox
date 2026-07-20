# VideoBox Exact Preview Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` task-by-task. Every production step starts with an observed RED, then GREEN, spec review, quality review, and source-to-runtime verification.

**Goal:** current editing revision에서만 재생되는 FFmpeg exact proxy와 이를 정직하게 표시하는 PreviewStage를 만든다.

**Architecture:** final composition path가 proxy의 sole composition authority다. durable exact-preview record/job은 request cache key와 generation fence로 current artifact를 선택하며, FastAPI는 project-scoped Range delivery만 한다. React PreviewStage는 immutable playback manifest와 exact-preview status를 읽고 current artifact일 때만 one player를 mount한다.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, SQLite LocalProjectStore, existing FfmpegFinalRenderer, React 19/TypeScript/Vitest, Playwright.

---

### Task 1: Extract common composition plan and define durable exact-preview identity

**Files:**
- Create: `packages/core-engine/src/videobox_core_engine/exact_preview.py`
- Create: `packages/core-engine/src/videobox_core_engine/composition_plan.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/sqlite_schema.py`
- Modify: `packages/core-engine/src/videobox_core_engine/ffmpeg_final_renderer.py`
- Modify: `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
- Modify: `packages/core-engine/src/videobox_core_engine/editor_playback_manifest.py`
- Modify: `services/api/src/videobox_api/orchestration.py`
- Modify: `services/api/src/videobox_api/main.py`
- Modify: `services/api/src/videobox_api/models.py`
- Test: `tests/test_exact_preview_artifact.py`

- [ ] **Step 1: Write RED tests** for one canonical cache key and record:

```python
request = ExactPreviewRequest(session_id="session-1", expected_revision=7, start_sec=2.0, end_sec=12.0)
assert request.cache_key(source_fingerprint="sha256:abc") == request.cache_key(source_fingerprint="sha256:abc")
assert store.finish_exact_preview(project_id=project_id, generation_id="old", fingerprint="sha256:abc", artifact_path=mp4) is False
```

- [ ] **Step 2: Run RED.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_exact_preview_artifact.py`

Expected: FAIL because no exact-preview request/record or generation fence exists.

- [ ] **Step 3: Implement the smallest common contract.** LocalPipelineRunner obtains the current editing session's canonical ASS/caption input, then extracts a pure `CompositionPlan` from the current final renderer before changing output behavior. It must cover every intersecting clip's source in/out, canonical timeline offset, B-roll/overlay visibility, narration/BGM/SFX controls, canvas/fps/SAR/rotation and clipped ASS cues. `for_range(start,end)` shifts every retained item once and yields output PTS zero. Final and proxy renderers consume the same plan/caption input; full output behavior remains regression-tested.

- [ ] **Step 4: Implement durable identity/lifecycle.** Define `ExactPreviewRequest` validation (`0 <= start < end <= duration`), `proxy_720p_h264_aac_v1`, fingerprint SHA-256 over canonical plan/session caption/used asset SHA/overlay/settings/composition version/profile, and SQLite migration/CRUD for pending/running/succeeded/failed/obsolete records. `begin_exact_preview` coalesces a current key or supersedes it; it claims ownership atomically. `finish_exact_preview` rechecks generation, revision and fingerprint before pointer update. Session/source invalidation includes `exact_preview_renders` in the same SQLite transaction. Restart recovery reclaims stale running claims, retry creates a new generation, temporary output is atomically published then fenced in DB, and retention/orphan cleanup is bounded.

- [ ] **Step 5: Run GREEN** with crossing clips, one-time offsets, final/proxy same-plan/same-caption-input parity, coalescing, supersession, restart recovery, source/revision/fingerprint invalidation, project isolation, failed-write rollback, orphan cleanup and retention cases.

- [ ] **Step 6: Commit** `feat: add exact preview composition fence`.

### Task 2: Render and deliver exact FFmpeg proxy artifacts

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/ffmpeg_final_renderer.py`
- Modify: `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
- Modify: `services/api/src/videobox_api/orchestration.py`
- Modify: `services/api/src/videobox_api/routers/outputs.py`
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `packages/core-engine/src/videobox_core_engine/editor_playback_manifest.py`
- Test: `tests/test_exact_preview_artifact.py`
- Test: `tests/test_api_exact_preview.py`

- [ ] **Step 1: Write RED tests** proving a selected 2–12 second range and full session render a real H.264/AAC faststart MP4, expose `timeline_start_sec`, `timeline_end_sec`, `artifact_revision`, `generation_id`, and reject stale/foreign/missing/unsafe content. Add a Range request assertion:

```python
response = client.get(content_url, headers={"Range": "bytes=2-5"})
assert response.status_code == 206
assert response.headers["accept-ranges"] == "bytes"
assert client.get(content_url, headers={"Range": "bytes=999-1000"}).status_code == 416
```

- [ ] **Step 2: Run RED** using `.venv\Scripts\python.exe -m pytest -q tests/test_exact_preview_artifact.py tests/test_api_exact_preview.py`.

- [ ] **Step 3: Implement minimal reuse.** Add `render_exact_preview_to_mp4` which consumes Task 1's range-normalized CompositionPlan; do not trim a completed full render or duplicate track composition. Fix `proxy_720p_h264_aac_v1` as aspect-preserving 720-long-edge scale/pad, output fps/SAR/rotation, yuv420p, AAC and `-movflags +faststart`, with burned ASS only and no subtitle stream. Pipeline creates/runs the fenced job and writes atomically under the project preview root. Router owns POST/status/content exact-preview routes and uses `deliver_file` for current-only `video/mp4` Range delivery. `main.py` includes the router. Preview creation does not call output approval or CapCut APIs.

- [ ] **Step 3a: Switch the canonical manifest.** Replace `orchestration.get_editor_playback_manifest`'s legacy final-render export scan with exact-preview durable status. Extend API/adapter fixtures to expose `pending|running|succeeded|failed|stale|unavailable`, generation/range/fingerprint metadata without leaking storage paths, and never label a legacy final render URL as the exact proxy.

- [ ] **Step 4: Run GREEN** plus real ffprobe checks for PTS zero, duration, profile fields, burned-captions/no subtitle stream, B-roll/audio controls, gap/missing-source recovery, Range/isolation and stale late-completion fence. Add status/content GET REDs that mutate a tracked source after success and prove revalidation marks the record stale, removes the playable URL and refuses `206` delivery.

- [ ] **Step 5: Commit** `feat: render revision-bound exact preview proxies`.

### Task 3: Build the proper PreviewStage UX without mutation

**Files:**
- Create: `apps/web/src/features/editor/preview/exactPreviewState.ts`
- Create: `apps/web/src/features/editor/preview/PreviewStage.tsx`
- Create: `apps/web/src/features/editor/preview/previewCoordinator.tsx`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/features/editor/editorViewModel.ts`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbench.tsx`
- Modify: `apps/web/src/styles/editor-workbench.css`
- Test: `apps/web/src/features/editor/preview/preview-stage.test.tsx`
- Test: `apps/web/src/features/editor/preview/preview-coordinator.test.tsx`
- Test: `apps/web/src/features/editor/workbench/editor-workbench.test.tsx`

- [ ] **Step 1: Write RED component tests** for exact current, pending, stale, failed, range time mapping, keyboard play/pause, no duplicate visual caption, and exactly one shared player. Assert stale state has no video source; selecting an immutable manifest clip creates typed `{ url, mediaKind: "video" | "audio", timelineRange }`, stops exact media, mounts that audition in the same player shell, and return restores the exact label without treating audition as `편집본 미리보기`.

- [ ] **Step 2: Run RED.**

Run: `npm --prefix apps/web test -- src/features/editor/preview/preview-stage.test.tsx src/features/editor/preview/preview-coordinator.test.tsx src/features/editor/workbench/editor-workbench.test.tsx`

Expected: FAIL because Task 11 has only a preview slot.

- [ ] **Step 3: Implement smallest complete accessible UX.** `ExactPreviewState` maps API data into Korean user copy and allowed action. One discriminated `PreviewCoordinator` owns `exact|audition` and one active media id; every mode change, scroll-away, or unmount stops the old player and the DOM mounts only one media element. Hover may preload poster/metadata but never audio; touch uses explicit first-tap preview then `사용` action remains out of scope. `PreviewStage` mounts `<video>` for a current exact artifact and, in audition mode, mounts `<video>` or `<audio>` from immutable typed `mediaKind` in the same player shell; it exposes labelled controls, maps media time to timeline time, updates transcript/ARIA status, and provides explicit retry/refresh action for non-current exact states. It uses burned captions only and never overlays visual captions. Workbench replaces only the Task 11 slot; docks/timeline stay read-only.

- [ ] **Step 4: Run GREEN** and assert zero command-port mutation, no audition autoplay, one mounted player, focus/scroll/unmount stop, keyboard/touch recovery, no external network, and no visual caption overlay over burned proxy.

- [ ] **Step 5: Commit** `feat: add exact preview stage`.

### Task 4: Verify source-to-runtime behavior and close out honestly

**Files:**
- Create: `apps/web/e2e/exact-preview.spec.mjs`
- Modify: `docs/superpowers/plans/2026-07-17-videobox-oss-dashboard-editor-adoption.md`
- Modify: `docs/development-status-2026-06-29.ko.md`
- Modify: `docs/handoffs/2026-07-20-videobox-hermes-dashboard-platform-handoff.ko.md`

- [ ] **Step 1: Write E2E RED** for each user-facing state: current proxy play/seek mapping, pending, stale after source revision, failed retry, and audition/exact separation.
- [ ] **Step 2: Run RED** with `npm --prefix apps/web run test:e2e -- e2e/exact-preview.spec.mjs`.
- [ ] **Step 3: Implement only test-required fixture/intercepts and UI wiring; do not make a renderer mock claim exact parity.**
- [ ] **Step 4: Run GREEN and all gates:** focused backend/API, actual FFmpeg fixture, affected Python suite, full frontend, production build, isolated Playwright, provenance/UI checks, `git diff --check`. Record actual cold/warm timing and fail the slice if the stated 20s/500ms gates miss.
- [ ] **Step 5: Obtain independent spec review, then code-quality review, fix Critical/Important findings, update SSOT only from evidence, commit/push with Task 9 and Task 11 approval state unchanged.**
