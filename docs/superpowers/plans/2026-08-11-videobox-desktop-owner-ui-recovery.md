# VideoBox Desktop Owner UI Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the PC-only VideoBox flow usable for a real video from project entry through asset import, editing, review, output, and CapCut handoff, with bounded layout and truthful state.

**Architecture:** Preserve the approved left-sidebar, white/orange palette, editor 3-column contract, existing API DTOs, and current asset projection/preview owners. Work in bounded slices: first prove runtime CSS/JS parity and repair the product shell, then bound media/editor rendering, then make review/output states actionable, and finally run a mutation E2E in a dedicated QA project.

**Tech Stack:** React 19, TypeScript, Vite, Tailwind v4, Radix/shadcn primitives, Vitest, existing isolated Chromium E2E, PowerShell `scripts/owner-ready.ps1`, FFprobe.

---

## Working rules

- Work only in `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility` on `codex/videobox-container-compatibility`.
- Keep `.tmp-final-fence-debug/`, `.tmp-real-video-dogfood/`, and `apps/web/.tmp-real-video-dogfood/` untouched.
- Do not modify `main`, add mobile UX, change the palette, add a new route, or add a new dependency.
- Use `.venv\Scripts\python.exe -m pytest <absolute paths>` for backend verification only.
- Use `scripts/owner-ready.ps1` for container actions; do not call Docker Compose directly.
- Every visual claim requires an actual browser screenshot at the specified PC viewport.
- Commit each completed slice separately and run `git diff --check` before each commit.

## File map

### P0 shell and runtime parity

- Modify `apps/web/src/styles/product-shell.css`: containment, collapsed rail, project row, dialog fallback, desktop breakpoints.
- Modify `apps/web/src/app/ProductShell.tsx`: Lucide navigation icons, hideable labels/tooltips, compact project menu, job dialog class hooks.
- Modify `docs/oss/editor-ui-source-map.json`: refresh the normalized `ProductShell.tsx` materialized-file hash after the source-preservation-required edit.
- Modify `apps/web/src/app/ProductShell.test.tsx`: project row, collapsed rail, dialog structure and accessible names.
- Add or modify `apps/web/src/styles/product-shell.visual.test.tsx`: rendered layout contract tests that assert class hooks and semantic regions.
- Modify `apps/web/e2e/run-isolated.mjs` only if the existing isolated harness needs a new viewport route; do not create a second browser harness.

### Project entry and production state

- Modify `apps/web/src/app/AppRouter.tsx`: project card summaries and home next-action data wiring, reusing existing `Project` and `HomeSummary` contracts.
- Modify the home component file identified by the route loader in `apps/web/src/app/AppRouter.tsx` or its existing feature component; do not create a duplicate home route.
- Modify `apps/web/src/features/jobs/JobRecovery.tsx`: bounded dialog content, job timestamps/progress/error/retry presentation.
- Modify `apps/web/src/features/jobs/JobRecovery.test.tsx`: loading, failure, retryable, progress, and accessible dialog states.

### Assets

- Modify `apps/web/src/features/media/MediaWorkspacePage.tsx`: local tabs, import sections, project video section, bounded empty/loading/error states.
- Modify `apps/web/src/features/media/MediaLibraryBrowser.tsx`: filter state, page state, 24-item render cap, pagination semantics.
- Modify `apps/web/src/features/media/MediaLibraryBrowser.test.tsx` and `MediaWorkspacePage.test.tsx`: page cap, tab isolation, reset-on-filter, import card accessibility.
- Reuse `apps/web/src/features/editor/assets/editorAssetProjection.ts` and existing API thumbnail/preview URL helpers; do not create a second projection contract.

### Editor, review, output

- Modify `apps/web/src/features/editor/workbench/EditorWorkbench.tsx`, `EditorWorkbenchRoute.tsx`, `RightDock.tsx`, and `apps/web/src/styles/editor-workbench.css`: bounded desktop workbench, dock mode, internal scroll, save/preview state hooks.
- Modify `apps/web/src/features/editor/assets/EditorAssetBrowser.tsx`: compact thumbnail/status cards, unknown-duration wording, apply gating, license detail disclosure.
- Modify existing editor tests under `apps/web/src/features/editor/workbench/` and `apps/web/src/features/editor/assets/EditorAssetBrowser.test.tsx`.
- Modify `apps/web/src/features/review/TimelineReviewPage.tsx` and `TimelineReviewPage.test.tsx`: stale reason, rebuild/return actions, approval state.
- Modify `apps/web/src/app/OutputsPage.tsx` and `OutputsPage.test.tsx`: readiness checklist, actionable blocked conditions, output success/failure state.

### E2E evidence

- Add only bounded test helpers under the existing `apps/web/e2e/` harness if required for desktop screenshots and QA-project flow.
- Store implementation-run evidence under ignored `artifacts/qa/desktop-owner-ui-recovery/`; never stage protected residue or source video originals.
- Update the existing handoff/status document only after the implementation and owner acceptance gates have evidence.

## Task 1: Runtime CSS/JS parity and shared visual contract

**Files:**
- Modify: `apps/web/src/styles/index.css`
- Modify: `apps/web/src/styles/product-shell.css`
- Test: `apps/web/src/styles/product-shell.visual.test.tsx`

- [x] **Step 1: Add failing rendered contract tests.** Render the dialog and job recovery fixture at the existing Vitest DOM boundary and assert the shell-owned dialog usage has a bounded-content class and a labelled close button; assert the shell has a `data-vb-desktop-shell` hook. The test must fail before the hooks exist.
- [x] **Step 2: Run the focused test and record the failure.** Run from `apps/web`: `pnpm exec vitest run src/styles/product-shell.visual.test.tsx --reporter=verbose`. Expected: FAIL because the new hooks are absent.
- [x] **Step 3: Add minimal shell hooks and CSS fallback.** Add a stable `data-vb-desktop-shell` hook to the product shell and `vb-dialog-content` class at the existing shell `DialogContent` call site. Add only the bounded fallback rules needed for `max-width: 35rem`, `max-height: 70vh`, `overflow-y: auto`, `padding: 1.5rem`, and centered positioning; keep the generated Radix dialog source and state behavior intact.
- [x] **Step 3a: Update source-preservation metadata when ProductShell changes.** Compute the normalized SHA-256 with the repository's existing provenance verifier rules and update both `ProductShell.tsx` entries in `docs/oss/editor-ui-source-map.json`; run the focused provenance verifier before committing.
- [x] **Step 4: Rebuild and compare assets.** Added the approved `owner-ready.ps1 -Rebuild` path and rebuilt the workspace image. The official container serves a Node-20 build with different content hashes than the local Node-24 build, but the served assets contain the current source markers (`프로젝트 열기`, `다음 할 일`, project-scoped media API, `출력 준비 체크리스트`) and the browser proof below is from that rebuilt image.
- [x] **Step 5: Run focused tests and build.** Run `pnpm exec vitest run src/styles/product-shell.visual.test.tsx src/app/ProductShell.test.tsx --reporter=verbose` and `pnpm run build`. Expected: PASS and production build success.
- [x] **Step 6: Commit the slice.** Run `git diff --check`, stage only the touched files, and commit `fix: restore shared desktop visual contract`.

**Task 1 gate note:** The rebuilt official container was verified at the PC viewport: the shell hook is present, home/assets/review/output are bounded, and the editor workbench owns its internal scroll regions. Hash names differ between local Node 24 and container Node 20 builds, so parity is established by served-content markers and browser behavior rather than filename equality.

## Task 2: Sidebar, project picker, and job-status dialog

**Files:**
- Modify: `apps/web/src/app/ProductShell.tsx`
- Modify: `apps/web/src/styles/product-shell.css`
- Modify: `apps/web/src/features/jobs/JobRecovery.tsx`
- Modify: `apps/web/src/app/ProductShell.test.tsx`
- Modify: `apps/web/src/features/jobs/JobRecovery.test.tsx`

- [x] **Step 1: Add failing shell tests.**
- [x] **Step 2: Add failing job-state tests.**
- [x] **Step 3: Run both focused tests to verify failure.**
- [x] **Step 4: Implement navigation and project menu.**
- [x] **Step 5: Implement bounded job rows.**
- [x] **Step 6: Add shell containment CSS.**
- [x] **Step 7: Run focused tests and browser screenshot.**
- [x] **Step 8: Commit.**

## Task 3: Project entry, home next action, and creation draft continuity

**Files:**
- Modify: `apps/web/src/app/AppRouter.tsx`
- Modify: existing home feature component if route inspection identifies one
- Modify: `apps/web/src/features/creation/CreationInterview.tsx`
- Modify: `apps/web/src/features/creation/CreationInterview.test.tsx`
- Modify: relevant `AppRouter` tests

- [x] **Step 1: Add failing project-card tests.**
- [x] **Step 2: Add failing creation continuity tests.**
- [x] **Step 3: Run focused tests.**
- [x] **Step 4: Wire existing data only.**
- [x] **Step 5: Add browser acceptance.**
- [x] **Step 6: Commit.**

## Task 4: Asset workspace tabs, thumbnails, and bounded pagination

**Files:**
- Modify: `apps/web/src/features/media/MediaWorkspacePage.tsx`
- Modify: `apps/web/src/features/media/MediaLibraryBrowser.tsx`
- Modify: `apps/web/src/features/media/MediaLibraryBrowser.test.tsx`
- Modify: `apps/web/src/features/media/MediaWorkspacePage.test.tsx`
- Reuse: `apps/web/src/features/editor/assets/editorAssetProjection.ts`

- [x] **Step 1: Add failing pagination tests.**
- [x] **Step 2: Add failing tab tests.**
- [x] **Step 3: Run focused media tests.**
- [x] **Step 4: Implement local tab state.**
- [x] **Step 5: Implement bounded page slicing.**
- [x] **Step 6: Implement truthful cards.**
- [x] **Step 7: Run tests and browser proof.**
- [x] **Step 8: Commit.**

## Task 5: Editor desktop containment and truthful preview/save states

**Files:**
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbench.tsx`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Modify: `apps/web/src/features/editor/workbench/RightDock.tsx`
- Modify: `apps/web/src/features/editor/assets/EditorAssetBrowser.tsx`
- Modify: `apps/web/src/styles/editor-workbench.css`
- Modify existing workbench and asset-browser tests

- [x] **Step 1: Add failing layout tests.**
- [x] **Step 2: Add failing preview/save state tests.**
- [x] **Step 3: Run focused editor tests.**
- [x] **Step 4: Implement desktop grid policy.**
- [x] **Step 5: Move scroll ownership inward.**
- [x] **Step 6: Implement card and state copy.**
- [x] **Step 7: Run tests and four viewport screenshots.** Focused editor tests/build and official-container route captures are recorded for 1920×1080, 1440×900, 1366×768, and 1280×800 in `artifacts/qa/desktop-owner-ui-recovery/desktop-route-matrix.json` (ignored evidence).
- [x] **Step 8: Commit.**

## Task 6: Review stale recovery and output readiness

**Files:**
- Modify: `apps/web/src/features/review/TimelineReviewPage.tsx`
- Modify: `apps/web/src/app/OutputsPage.tsx`
- Modify: `apps/web/src/features/review/TimelineReviewPage.test.tsx`
- Modify: `apps/web/src/app/OutputsPage.test.tsx`

- [x] **Step 1: Add failing stale-review tests.**
- [x] **Step 2: Add failing output-gate tests.**
- [x] **Step 3: Run focused tests.**
- [x] **Step 4: Implement stale recovery.**
- [x] **Step 5: Implement readiness checklist.**
- [x] **Step 6: Run tests and browser flow.**
- [x] **Step 7: Commit.**

## Task 7: Runtime parity, full regression, and desktop visual gate

**Files:**
- Modify only if the existing harness needs selectors: `apps/web/e2e/` existing runner files
- Create ignored evidence: `artifacts/qa/desktop-owner-ui-recovery/`

- [x] **Step 1: Build the exact source.** `npx tsc -b` and `npm run build` passed; local Node 24 asset names were recorded in the build output.
- [x] **Step 2: Start/check through the approved wrapper.** `owner-ready.ps1 -Mode Start -Rebuild` rebuilt and started the workspace; VideoBox health passed. Full Check remains blocked only by Hermes dashboard availability.
- [x] **Step 3: Run frontend focused and full tests.** Full frontend Vitest run passed 61 files/850 tests; typecheck/build and changed-slice tests also pass. Isolated Chromium remains a fake API harness and is not counted as owner proof.
- [x] **Step 4: Capture four desktop viewports.** Official-container screenshots/metrics cover 1920×1080, 1440×900, 1366×768, and 1280×800 across home/media/editor/review/outputs; evidence is ignored under `artifacts/qa/desktop-owner-ui-recovery/`.
- [x] **Step 5: Verify browser metrics.** Official container metrics passed for home/assets/editor/review/output at 1440×900; editor `scrollWidth=1425` against `innerWidth=1440`, workbench height 768, and audio library capped at 24 cards.
- [x] **Step 6: Commit verification evidence only if repository policy allows.** Screenshots, generated media, and the mutation manifest remain ignored; only the handoff record is committed. Protected residue and source media were not staged.

## Task 8: Mutation E2E in a dedicated QA project

**Files:**
- Use existing UI/API contracts; no new backend schema.
- Evidence: ignored `artifacts/qa/desktop-owner-ui-recovery/`
- Handoff: existing current VideoBox status/handoff document after owner review

- [x] **Step 1: Prepare isolated input.** A generated/copy-isolated QA source and short narration were preserved read-only in ignored artifacts; hashes and byte-level evidence are in `qa-mutation-manifest.json`. This is a synthetic QA sample, not owner-approved production media.
- [ ] **Step 2: Create a dedicated QA project through the UI.** The exact display name `VideoBox PC QA 20260811153350` and slug were created in the official runtime, but the browser pipe closed before the UI click path; API creation is recorded separately and is not claimed as UI proof.
- [ ] **Step 3: Run creation and import.** Creation, upload, readiness retry, and completion succeeded against the official runtime API; visible UI loading/error/retry capture could not be completed after the browser transport closed.
- [ ] **Step 4: Run editing.** A real caption mutation advanced revision 1→2 and persisted in the session; route reload was not performed in a live browser after the browser transport closed.
- [x] **Step 5: Run stale review recovery.** The edit invalidated the prior review (`editing_session_mutation`), refresh rebuilt it for revision 2, and approval succeeded with no blockers.
- [x] **Step 6: Generate outputs.** Subtitle, final MP4, and CapCut draft jobs all succeeded against the approved timeline; no external publishing/upload was performed.
- [x] **Step 7: Verify artifacts.** SRT, MP4, and CapCut draft files are nonzero; FFprobe confirms 1920×1080 H.264/AAC, 5.0 seconds, 48 kHz stereo audio. A representative MP4 frame was inspected.
- [ ] **Step 8: Perform owner media acceptance.** MP4 frame/FFprobe evidence is recorded and the host CapCut 9.1.0.3879 Desktop flow was manually opened: a new project imported `output.mp4` and displayed the 5-second preview with captions. Full owner watch/listen and caption-timing acceptance is still pending; container handoff registration remains unavailable.
- [x] **Step 9: Preserve evidence and stop before cleanup.** The dedicated QA project and all outputs remain in runtime storage; no cleanup or deletion was performed.

## Task 9: Handoff and completion decision

- [x] **Step 1: Pin final HEAD and verify clean status.** HEAD is `2724a5f9e`; `git status --short` is clean, `git diff --check` passes, and upstream count is `0 0`.
- [x] **Step 2: Separate gates in the handoff.** Automated tests, browser visual proof, artifact/FFprobe proof, and owner media acceptance are recorded as separate gates in the handoff; they are not collapsed into one green test count.
- [x] **Step 3: Report unrun gates.** Full audio/video listening, caption-timing review, and owner approval remain explicitly pending; CapCut Desktop import/open is separately evidenced, and the product is not called owner-ready.
- [x] **Step 4: Commit the handoff only after all required gates are honestly recorded.** Handoff updates were committed and pushed on the current branch with exact evidence paths.

## Verification command reference

Run from `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility` unless noted.

```powershell
Set-Location apps/web
pnpm exec vitest run src/app/ProductShell.test.tsx src/features/jobs/JobRecovery.test.tsx --reporter=verbose
pnpm exec vitest run src/features/media/MediaLibraryBrowser.test.tsx src/features/media/MediaWorkspacePage.test.tsx --reporter=verbose
pnpm exec vitest run src/features/editor/workbench/editor-workbench.test.tsx src/features/editor/workbench/editor-workbench-route.test.tsx src/features/editor/assets/EditorAssetBrowser.test.tsx --reporter=verbose
pnpm exec vitest run src/features/review/TimelineReviewPage.test.tsx src/app/OutputsPage.test.tsx --reporter=verbose
pnpm test
pnpm run build
Set-Location ../..
.\scripts\owner-ready.ps1 -Mode Check -Json
git diff --check
```

## Plan self-review

- Spec coverage: runtime parity (Task 1/7), shell and sidebar (Task 2), project/home/create (Task 3), assets (Task 4), editor containment/save/preview (Task 5), review/output (Task 6), PC browser proof (Task 7), mutation production flow and owner acceptance (Task 8/9).
- Placeholder scan: no TODO, TBD, or unspecified “handle later” step is used.
- Type consistency: plan reuses existing `Project`, `HomeSummary`, `JobRecord`, editor asset projection, review state, and output state contracts; no new backend DTO is introduced.
- Scope: mobile, publishing, external provider calls, new routes, new dependencies, and backend schema changes remain excluded.
