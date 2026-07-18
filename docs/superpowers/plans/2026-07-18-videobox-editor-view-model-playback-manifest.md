# VideoBox Editor View Model and Playback Manifest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` task-by-task. Every production change begins with a focused RED test and receives spec-compliance then code-quality review.

**Goal:** Publish one project/session-scoped editor contract that safely supplies an authoritative view model, role-specific commands, and a playback manifest.

**Architecture:** The backend owns canonical seconds, revision/freshness, source provenance and URL authorization. A narrow frontend adapter converts this DTO into `EditorViewModel`; views never consume raw editing-session/timeline DTOs or issue ambiguous generic trim mutations. Existing editing-session commands remain their implementation target; Task 10 adds no competing editing truth.

**Tech stack:** FastAPI/Pydantic, LocalProjectStore, FFmpeg metadata, React/TypeScript/Vitest, existing loopback network guard.

**Scope boundary:** The user explicitly deferred Task 9 human/CapCut acceptance to a later session. Preserve its dirty technical changes and do not check off, commit, push, or otherwise close Task 9. Do not start Hermes/container, OpenCut runtime, SaaS auth/billing, waveform jobs, or Task 11 workbench UI.

---

### Task 1: Harden project-scoped media delivery before publishing playback URLs

**Files:**
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Modify: `services/api/src/videobox_api/routers/assets.py`
- Modify: `services/api/src/videobox_api/routers/outputs.py`
- Test: `tests/test_playback_delivery_contract.py`

- [ ] RED: add tests proving `storage://project-id/../other/file` is rejected, another project's asset/final artifact is 404, valid byte range returns `206` plus `Content-Range`, invalid range is `416`, and asset/final content has a verified MIME type.
- [ ] Verify RED with `.venv\\Scripts\\python.exe -m pytest -q tests/test_playback_delivery_contract.py`.
- [ ] GREEN: resolve a storage URI only when `Path.resolve()` remains under that project's storage root; centralize scoped FileResponse construction so asset audition and exact final artifact preserve isolation, Range semantics, and MIME.
- [ ] Verify GREEN with the focused command and existing asset/output API tests.

### Task 2: Define canonical timing and authoritative backend manifest

**Files:**
- Create: `packages/core-engine/src/videobox_core_engine/editor_playback_manifest.py`
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `services/api/src/videobox_api/orchestration.py`
- Modify: `services/api/src/videobox_api/routers/editing_session.py`
- Test: `tests/test_editor_view_model_api.py`

- [ ] RED: specify a named session manifest with `timebase="seconds"`, `fps_num/fps_den`, output width/height/SAR/rotation/duration, stable project/session/timeline/segment/clip/asset IDs, typed tracks, media controls, captions/style, gap slots, source SHA/media revision, and current/stale status. Add frame conversion fixtures for non-negative time using exactly `floor(seconds * fps_num / fps_den + 0.5)` at one boundary; use `frame * fps_den / fps_num` for the reverse mapping and do not persist frame values in the DTO.
- [ ] Verify RED using `.venv\\Scripts\\python.exe -m pytest -q tests/test_editor_view_model_api.py`.
- [ ] GREEN: build the manifest from the explicit editing session and its matching timeline only; surface audition URL separately from exact-preview/final artifact status. Keep seconds at the API edge and represent frame rate rationally instead of flattening it to a float.
- [ ] Verify project/session isolation, stale source behavior, and current revision behavior in the focused suite.

### Task 3: Expose only the supported role-action matrix

**Files:**
- Create: `apps/web/src/features/editor/editorViewModel.ts`
- Create: `apps/web/src/features/editor/editorCommandPort.ts`
- Modify: `apps/web/src/api.ts`
- Test: `apps/web/src/features/editor/editorViewModel.test.ts`
- Test: `apps/web/src/features/editor/editorCommandPort.test.ts`

- [ ] RED: type tests must allow narration split/merge/bounds/reorder; separate discriminated B-roll/BGM/SFX apply/clear/update-media-controls commands; supported overlay apply/clear; and caption text/style. `select` and `seek` stay local view state, not server mutations. They must reject a generic trim command, caption timing resize, and unsupported overlay fields.
- [ ] Verify RED with `npm --prefix apps/web test -- --run src/features/editor/editorViewModel.test.ts src/features/editor/editorCommandPort.test.ts`.
- [ ] GREEN: make `VideoBoxEditorAdapter` map the manifest and each typed port method to one existing revisioned API endpoint. Do not expose raw `Record<string, unknown>` controls to editor views.
- [ ] Verify adapter command payloads always contain project/session/expected revision and map no role to an ambiguous generic endpoint.

### Task 4: Wire the manifest entry point without migrating the workbench

**Files:**
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/app/AppRouter.tsx`
- Test: `apps/web/src/app/AppRouter.test.tsx`
- Test: `apps/web/src/app.test.tsx`

- [ ] RED: `/projects/$projectId/editor?session_id=$sessionId` loads that session's manifest, shows audition and exact-preview states distinctly, and never substitutes another project's/latest session. A stale artifact is not labeled as current playback.
- [ ] Verify RED with the two focused Vitest files.
- [ ] GREEN: use the new adapter at the legacy editor boundary only; retain the existing workspace layout and output ownership. Canonical editor links use `/editor`, while legacy compatibility remains a one-way adapter.
- [ ] Verify loopback-only traffic and existing Task 9 editor-session restoration regressions.

### Task 5: Close Task 10 only after independent verification

**Files:**
- Modify: `docs/superpowers/plans/2026-07-17-videobox-oss-dashboard-editor-adoption.md`
- Modify: `docs/development-status-2026-06-29.ko.md`
- Create: `docs/handoffs/2026-07-18-videobox-oss-dashboard-editor-adoption-slice-3-task-10-closeout.ko.md`

- [ ] Run focused backend/frontend suites, full affected backend/frontend suites, production build, loopback network guard, provenance/UI-system verifiers, and `git diff --check`.
- [ ] Obtain fresh independent spec review, code-quality review, plan-gap review, and source-to-runtime reverse validation; fix every P0/P1 before closeout.
- [ ] Update only Task 10 status/SSOT when all Task 10 criteria pass. Keep Task 9 at its existing technical-gate state.
- [ ] Commit only the logically closed Task 10 unit: `feat: expose an authoritative editor view model`; push only after the worktree and evidence are clean.

## Written-spec review result

- The initial implementation order is security delivery -> manifest -> typed frontend adapter -> legacy-boundary integration. This prevents a browser-accessible URL from being introduced before path containment/isolation/Range/MIME proof exists.
- Existing sessions persist seconds and revisioned command endpoints, but neither rational FPS nor one joined manifest exists; Task 10 fills this contract gap without reimplementing renderers.
- The Task 9 technical handoff requests a human gate before later implementation, but the user explicitly instructed Task 10 to begin. That exception is limited to this plan; it does not convert Task 9 into completed work.
