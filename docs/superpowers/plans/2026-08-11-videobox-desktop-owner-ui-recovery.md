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

- [ ] **Step 1: Add failing rendered contract tests.** Render the dialog and job recovery fixture at the existing Vitest DOM boundary and assert the shell-owned dialog usage has a bounded-content class and a labelled close button; assert the shell has a `data-vb-desktop-shell` hook. The test must fail before the hooks exist.
- [ ] **Step 2: Run the focused test and record the failure.** Run from `apps/web`: `pnpm exec vitest run src/styles/product-shell.visual.test.tsx --reporter=verbose`. Expected: FAIL because the new hooks are absent.
- [ ] **Step 3: Add minimal shell hooks and CSS fallback.** Add a stable `data-vb-desktop-shell` hook to the product shell and `vb-dialog-content` class at the existing shell `DialogContent` call site. Add only the bounded fallback rules needed for `max-width: 35rem`, `max-height: 70vh`, `overflow-y: auto`, `padding: 1.5rem`, and centered positioning; keep the generated Radix dialog source and state behavior intact.
- [ ] **Step 3a: Update source-preservation metadata when ProductShell changes.** Compute the normalized SHA-256 with the repository's existing provenance verifier rules and update both `ProductShell.tsx` entries in `docs/oss/editor-ui-source-map.json`; run the focused provenance verifier before committing.
- [ ] **Step 4: Rebuild and compare assets.** Run `pnpm run build` from `apps/web`; capture the generated CSS/JS names. Start/check the local runtime only through `scripts/owner-ready.ps1`, then compare the served HTML asset names with this build. If they differ, stop the visual gate and rebuild through the approved owner-ready path.
- [ ] **Step 5: Run focused tests and build.** Run `pnpm exec vitest run src/styles/product-shell.visual.test.tsx src/app/ProductShell.test.tsx --reporter=verbose` and `pnpm run build`. Expected: PASS and production build success.
- [ ] **Step 6: Commit the slice.** Run `git diff --check`, stage only the touched files, and commit `fix: restore shared desktop visual contract`.

## Task 2: Sidebar, project picker, and job-status dialog

**Files:**
- Modify: `apps/web/src/app/ProductShell.tsx`
- Modify: `apps/web/src/styles/product-shell.css`
- Modify: `apps/web/src/features/jobs/JobRecovery.tsx`
- Modify: `apps/web/src/app/ProductShell.test.tsx`
- Modify: `apps/web/src/features/jobs/JobRecovery.test.tsx`

- [ ] **Step 1: Add failing shell tests.** Assert each primary nav button exposes a Lucide icon plus a hideable Korean label, collapsed mode exposes an accessible name/tooltip, and each project row has one selection button plus one `더보기` menu trigger. Assert archive/delete controls are not direct row siblings.
- [ ] **Step 2: Add failing job-state tests.** Supply fixtures with `progress_percent`, `started_at`, `finished_at`, `error_message`, and retryable/blocked statuses. Assert the dialog renders bounded job rows, progress text, failure text, and only the retryable action.
- [ ] **Step 3: Run both focused tests to verify failure.** Run `pnpm exec vitest run src/app/ProductShell.test.tsx src/features/jobs/JobRecovery.test.tsx --reporter=verbose`. Expected: FAIL on icon/menu/state assertions.
- [ ] **Step 4: Implement navigation and project menu.** Map the existing nav labels to existing Lucide icons, render a `span` label hidden only when `data-state=collapsed`, and add tooltip/aria-label for icon-only mode. Move archive/delete into the existing `DropdownMenu`; preserve current confirmation and API callbacks.
- [ ] **Step 5: Implement bounded job rows.** Add a `data-vb-job-dialog` section class and render job type, project, status, progress, start/finish times, error, and retry action using the existing DTO. Keep errors scoped to the dialog and preserve retry behavior.
- [ ] **Step 6: Add shell containment CSS.** Set `min-width: 0` on shell/main/content flex children, remove the project-row `button { width: 100% }` collision, and enforce 256px expanded/64px editor rail widths. Use desktop-only rules; do not add mobile interaction.
- [ ] **Step 7: Run focused tests and browser screenshot.** Run the focused Vitest command again, then use the real browser at 1440×900 and 1280×800 to open the picker, job dialog, and collapsed editor rail. Expected: no overlap, dialog centered and internally scrollable, labels readable.
- [ ] **Step 8: Commit.** Run `git diff --check` and commit `fix: contain desktop shell and job recovery`.

## Task 3: Project entry, home next action, and creation draft continuity

**Files:**
- Modify: `apps/web/src/app/AppRouter.tsx`
- Modify: existing home feature component if route inspection identifies one
- Modify: `apps/web/src/features/creation/CreationInterview.tsx`
- Modify: `apps/web/src/features/creation/CreationInterview.test.tsx`
- Modify: relevant `AppRouter` tests

- [ ] **Step 1: Add failing project-card tests.** Mock existing `Project` and `HomeSummary` values and assert each card shows status summary and exactly one primary next action: `계속 편집`, `자산 준비`, or `새 영상 시작`.
- [ ] **Step 2: Add failing creation continuity tests.** Provide an in-progress creation brief and assert `초안 이어서 하기` is shown before a new creation CTA; assert supported file guidance is visible before file selection.
- [ ] **Step 3: Run focused tests.** Run `pnpm exec vitest run src/app/AppRouter.test.tsx src/features/creation/CreationInterview.test.tsx --reporter=verbose`. Expected: FAIL on new summary and resume assertions.
- [ ] **Step 4: Wire existing data only.** Reuse `Project.status`, existing home summary loader/API, and creation brief state. Do not add a `last_edited_at` or thumbnail backend field. Keep project creation and navigation semantics unchanged.
- [ ] **Step 5: Add browser acceptance.** At 1440×900 verify a project card communicates its next action and the home page has one dominant next step without overlapping sidebar controls.
- [ ] **Step 6: Commit.** Run focused tests and `git diff --check`, then commit `feat: clarify desktop project next actions`.

## Task 4: Asset workspace tabs, thumbnails, and bounded pagination

**Files:**
- Modify: `apps/web/src/features/media/MediaWorkspacePage.tsx`
- Modify: `apps/web/src/features/media/MediaLibraryBrowser.tsx`
- Modify: `apps/web/src/features/media/MediaLibraryBrowser.test.tsx`
- Modify: `apps/web/src/features/media/MediaWorkspacePage.test.tsx`
- Reuse: `apps/web/src/features/editor/assets/editorAssetProjection.ts`

- [ ] **Step 1: Add failing pagination tests.** Fixture more than 24 music/SFX items; assert only 24 article/card nodes render, page navigation changes the slice, and changing type/search resets to page one.
- [ ] **Step 2: Add failing tab tests.** Assert the default `내 영상` view does not render music/SFX cards, `가져오기` does not render library articles, and each tab has loading, empty, error, and retry regions.
- [ ] **Step 3: Run focused media tests.** Run `pnpm exec vitest run src/features/media/MediaLibraryBrowser.test.tsx src/features/media/MediaWorkspacePage.test.tsx --reporter=verbose`. Expected: FAIL on tab and cap assertions.
- [ ] **Step 4: Implement local tab state.** Keep the existing `자산` route and API calls. Render only the selected tab. Keep upload and inbox sections inside `가져오기`; keep project video cards inside `내 영상`.
- [ ] **Step 5: Implement bounded page slicing.** Use a constant `PAGE_SIZE = 24`, derive `pageItems = filteredItems.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)`, clamp page after data changes, and render labelled previous/next/page controls.
- [ ] **Step 6: Implement truthful cards.** Reuse thumbnail/preview URLs and projection fields. Truncate filenames with full accessible names, show duration/orientation/audio/analysis state, and make retry/detail actions local to the card.
- [ ] **Step 7: Run tests and browser proof.** Run focused media tests and build. In the browser at 1440×900 verify tab isolation, thumbnail presence, page cap, import-card containment, and document height bounded to the active view.
- [ ] **Step 8: Commit.** Run `git diff --check` and commit `feat: bound desktop asset workspace`.

## Task 5: Editor desktop containment and truthful preview/save states

**Files:**
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbench.tsx`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Modify: `apps/web/src/features/editor/workbench/RightDock.tsx`
- Modify: `apps/web/src/features/editor/assets/EditorAssetBrowser.tsx`
- Modify: `apps/web/src/styles/editor-workbench.css`
- Modify existing workbench and asset-browser tests

- [ ] **Step 1: Add failing layout tests.** Assert the workbench exposes a viewport-bound root, internal vertical scroll regions, a timeline-owned horizontal scroller, and dock mode state. Assert editor asset cards render `길이 확인 중` for null duration and disable apply while review status is pending.
- [ ] **Step 2: Add failing preview/save state tests.** Use existing preview state and editor mutation fixtures to assert loading, empty, failed, ready, saving, saved, and save-failed copy/actions.
- [ ] **Step 3: Run focused editor tests.** Run `pnpm exec vitest run src/features/editor/workbench/editor-workbench.test.tsx src/features/editor/workbench/editor-workbench-route.test.tsx src/features/editor/assets/EditorAssetBrowser.test.tsx src/features/editor/preview/preview-stage.test.tsx --reporter=verbose`. Expected: FAIL on new state/layout assertions.
- [ ] **Step 4: Implement desktop grid policy.** Preserve the 3-part logical structure. At `min-width: 1920px`, show both docks with preview min 720px; below 1920px, show one dock with explicit named toggle. Add `min-width: 0` to all grid/flex children.
- [ ] **Step 5: Move scroll ownership inward.** Set workbench height to the available viewport below the product header, panel content to `overflow-y: auto`, timeline viewport to `overflow-x: auto`, and document/main to `overflow-x: hidden` only at the editor boundary.
- [ ] **Step 6: Implement card and state copy.** Reuse current projection and PreviewStage. Replace false zero duration, separate preview states, expose save status in the header, and put license/preference details behind a compact disclosure.
- [ ] **Step 7: Run tests and four viewport screenshots.** Run focused editor tests and `pnpm run build`. Use the browser at 1920×1080, 1440×900, 1366×768, and 1280×800. Expected: document `scrollWidth <= innerWidth`, internal panel/timeline scrolling, no black unexplained preview.
- [ ] **Step 8: Commit.** Run `git diff --check` and commit `fix: contain desktop editor workbench`.

## Task 6: Review stale recovery and output readiness

**Files:**
- Modify: `apps/web/src/features/review/TimelineReviewPage.tsx`
- Modify: `apps/web/src/app/OutputsPage.tsx`
- Modify: `apps/web/src/features/review/TimelineReviewPage.test.tsx`
- Modify: `apps/web/src/app/OutputsPage.test.tsx`

- [ ] **Step 1: Add failing stale-review tests.** Assert stale state explains that the edit changed after review, renders `현재 편집본으로 검토본 다시 만들기` as primary, and provides `편집으로 돌아가기` as secondary; assert refresh is not the only action.
- [ ] **Step 2: Add failing output-gate tests.** Assert blocked output shows an ordered readiness checklist with the blocking reason and a link/action to the resolving screen; assert output controls become enabled only when all gates pass.
- [ ] **Step 3: Run focused tests.** Run `pnpm exec vitest run src/features/review/TimelineReviewPage.test.tsx src/app/OutputsPage.test.tsx --reporter=verbose`. Expected: FAIL on the new copy and readiness assertions.
- [ ] **Step 4: Implement stale recovery.** Preserve existing review API and decision calls. Add explicit cause/action copy and route back to the current editor session without mutating until the user chooses rebuild.
- [ ] **Step 5: Implement readiness checklist.** Derive checklist items from existing review/output state. Keep CapCut readiness separate from actual Desktop completion. Keep disabled buttons accompanied by cause and resolving action.
- [ ] **Step 6: Run tests and browser flow.** Run focused tests and inspect stale review/output at 1440×900. Expected: each blocked state has one obvious next action.
- [ ] **Step 7: Commit.** Run `git diff --check` and commit `feat: make review and output recovery actionable`.

## Task 7: Runtime parity, full regression, and desktop visual gate

**Files:**
- Modify only if the existing harness needs selectors: `apps/web/e2e/` existing runner files
- Create ignored evidence: `artifacts/qa/desktop-owner-ui-recovery/`

- [ ] **Step 1: Build the exact source.** From `apps/web`, run `pnpm run build`; record the generated CSS/JS names and commit SHA in the ignored evidence manifest.
- [ ] **Step 2: Start/check through the approved wrapper.** Run `scripts/owner-ready.ps1 -Mode Check -Json`. If blocked because the branch is ahead of upstream, record that exact reason and do not claim runtime parity. If startup is authorized and required, use `scripts/owner-ready.ps1 -Mode Start` only.
- [ ] **Step 3: Run frontend focused and full tests.** Run the focused commands from Tasks 1–6, then `pnpm test`, `pnpm run build`, and the existing isolated Chromium E2E command. Expected: all pass on the same source SHA.
- [ ] **Step 4: Capture four desktop viewports.** Use actual browser screenshots for project entry, home, assets, editor, review, and output at 1920×1080, 1440×900, 1366×768, and 1280×800. Inspect every saved image before accepting it.
- [ ] **Step 5: Verify browser metrics.** For home/assets/editor assert `document.documentElement.scrollWidth <= innerWidth`; assert sidebar descendants remain within the sidebar rect; assert active asset cards ≤24; assert dialog max width/height/padding.
- [ ] **Step 6: Commit verification evidence only if repository policy allows.** Keep screenshots and receipts ignored unless the existing handoff policy requires a checked-in manifest. Never stage protected residue or source media.

## Task 8: Mutation E2E in a dedicated QA project

**Files:**
- Use existing UI/API contracts; no new backend schema.
- Evidence: ignored `artifacts/qa/desktop-owner-ui-recovery/`
- Handoff: existing current VideoBox status/handoff document after owner review

- [ ] **Step 1: Prepare isolated input.** Choose an owner-approved sample copy; preserve the original read-only. Record filename, byte size, and SHA-256 of the copy in the ignored manifest.
- [ ] **Step 2: Create a dedicated QA project through the UI.** Use the exact name `VideoBox PC QA <date-time>`. Do not use `My Project` or another existing owner project.
- [ ] **Step 3: Run creation and import.** Paste the approved script or select the approved script copy, create the brief, import the video, wait for analysis state, and record every visible loading/error/retry state.
- [ ] **Step 4: Run editing.** Apply video/B-roll/BGM/SFX in the editor, confirm save success, reload the route, and confirm the same revision and assets are restored.
- [ ] **Step 5: Run stale review recovery.** Generate review, make one real edit, confirm stale status, rebuild review for the current revision, inspect blockers, and approve only when the checklist is clear.
- [ ] **Step 6: Generate outputs.** Create subtitles, final MP4, and CapCut draft. Do not publish or upload externally.
- [ ] **Step 7: Verify artifacts.** Assert each file exists and is nonzero; run FFprobe against the MP4 and assert video stream, audio stream when expected, duration, and readable codec metadata.
- [ ] **Step 8: Perform owner media acceptance.** In the browser, watch the MP4 and listen through speech/BGM/SFX; inspect caption timing. Use `scripts/owner-ready.ps1 -Mode OpenCapCut` only for the approved QA draft, then have the owner confirm it opens in CapCut Desktop.
- [ ] **Step 9: Preserve evidence and stop before cleanup.** Keep the QA project and outputs until the owner explicitly approves cleanup. Do not delete them automatically.

## Task 9: Handoff and completion decision

- [ ] **Step 1: Pin final HEAD and verify clean status.** Run `git status --short`, `git diff --check`, `git log -1 --oneline`, and `git rev-list --left-right --count '@{upstream}...HEAD'`.
- [ ] **Step 2: Separate gates in the handoff.** Record automated tests, browser visual proof, artifact/FFprobe proof, and owner media acceptance as separate rows. Never collapse them into one green test count.
- [ ] **Step 3: Report unrun gates.** If CapCut Desktop, audio listening, or owner approval did not happen, state them as pending and do not call the product owner-ready.
- [ ] **Step 4: Commit the handoff only after all required gates are honestly recorded.** Use a docs-only commit with the current branch and exact evidence paths.

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
