# VideoBox Task 11 Editor Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILLS: use `subagent-driven-development`, `test-driven-development`, `requesting-code-review`, and `verification-before-completion`. Each production step starts with an observed RED and ends with GREEN evidence. Do not start Hermes, provider, OAuth, memory, renderer, or CapCut work.

**Goal:** 현재 authoritative `EditorViewModel`을 읽기 전용으로 배치하는 반응형 편집 작업판을 추가한다. 왼쪽 자산·대본·자막, 중앙 preview slot, 오른쪽 유진/Inspector, 하단 timeline dock을 동일 화면에서 보되, 새 편집 truth나 mutation 경로는 만들지 않는다.

**Architecture:** canonical `/projects/$projectId/editor?session_id=` route는 새 `EditorWorkbenchRoute`만 mount한다. 이 route는 `api.getEditorPlaybackManifest(projectId, sessionId)` 한 번을 읽고 `new VideoBoxEditorAdapter(manifest).viewModel`으로 변환한 뒤, returned `projectId`/`sessionId`가 route 값과 정확히 다르면 recovery UI로 fail-closed한다. Legacy `App.tsx` editor body는 해당 canonical route에서 mount하지 않아 project/session/revision truth가 중복되지 않는다. Workbench는 view model에서 파생한 metadata-only adapter surface와 dock 열림·크기·drawer 선택·disabled composer draft만 browser-local UI state로 보관한다. `react-resizable-panels`의 이미 pinned된 shadcn `Resizable` wrapper를 사용하며, exact FFmpeg preview와 실제 preview coordinator는 Task 12/13 범위로 남긴다.

**Tech Stack:** React 19.1, TypeScript 5.8, Vitest/Testing Library, Playwright, shadcn `Resizable`, existing `EditorViewModel`, `DirectorWorkspacePanel`, and `ManualMediaLibrary` adapters.

---

## Fixed boundaries

- Task 9은 사람/자산/CapCut gate 때문에 계속 unchecked이며, 이 Task가 progress를 바꾸지 않는다.
- Task 11은 read-only layout이다. `EditorCommandPort`, API mutation, renderer job, exact preview creation, asset apply, proposal apply, caption write, and timeline write를 호출하지 않는다.
- `EditorViewModel`의 project/session/revision/source/provenance는 그대로 표시만 한다. URL, App state, SQLite, API state에 또 하나의 selected project/session truth를 만들지 않는다.
- Task 11의 adapter는 metadata-only다. `ManualMediaLibrary`, `AssetPreviewPlayer`, `DirectorWorkspacePanel`, `DirectorWorkspace`를 mount하지 않으며, `audio`, `video`, preview URL, `play()`, API fetch, proposal/preflight/refresh, preference, or composer submit을 호출하지 않는다. Task 13만 audition/one-player를, Task 20만 persistent Eugene conversation/recommendation을 추가한다.
- Density resolver는 viewport가 아니라 `availableWorkbenchWidth`와 fixed toolbar/timeline/gutter/panel minimum을 입력으로 받는다. 1600px 이상도 계산된 preview width가 720px 이상일 때만 양쪽 dock을 연다. 1280–1599px는 계산된 preview가 640px 및 available width의 50% 이상인 한 dock만 연다. 실제 여유폭이 부족하면 즉시 single 또는 drawer로 normalize한다. 1280px 미만은 focus-managed drawer로 전환한다.
- 1920/1440/1280/768/390의 deterministic artifact와 두 번째 명시적 사용자 시각 승인이 없으면 Task 11 checkbox를 완료로 바꾸지 않는다. Task 14 interaction은 그 승인 뒤에만 시작한다.

## Files and responsibilities

- Create `apps/web/src/features/editor/workbench/editorWorkbenchLayout.ts`: available-width density calculation, permitted dock combination, preview minimum, and local-state normalization.
- Create `apps/web/src/features/editor/workbench/editorWorkbenchLayout.test.ts`: 1920/1440/1280/768/390 available-width thresholds, panel/gutter constraints, and invalid persisted-state tests.
- Create `apps/web/src/features/editor/workbench/editorWorkbenchReadOnlyAdapters.tsx`: manifest-derived asset/script/caption/Inspector summaries plus a local-only disabled Eugene draft area; no existing stateful panel component import.
- Create `apps/web/src/features/editor/workbench/EditorWorkbench.tsx`: semantic toolbar, dock composition, keyboard resize controls, focus-managed narrow drawers, and metadata-only adapter wrappers.
- Create `apps/web/src/features/editor/workbench/editor-workbench.test.tsx`: layout, focus return, UI-only persistence, zero network/mutation/media behavior, and typed manifest presentation tests.
- Create `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx` and `editor-workbench-route.test.tsx`: canonical session query validation, one authoritative view-model read, direct refresh, loading/recovery, and ProductShell collapsed ownership.
- Create `apps/web/src/styles/editor-workbench.css`; modify `apps/web/src/styles/index.css`: scoped workbench styles only.
- Modify `apps/web/src/app/AppRouter.tsx`, `ProductShell.tsx`, `ProductShell.test.tsx`, `routeManifest.test.ts`, and `AppRouter.test.tsx`: route the canonical editor query through `EditorWorkbenchRoute`, give `ProductShell` a route-scoped `forceCollapsed` initial state, and preserve direct-refresh contract. While the editor route remains mounted the user may explicitly reopen the sidebar; leaving/re-entering editor resets it collapsed and non-editor routes retain their existing default behavior.
- Create `apps/web/e2e/editor-workbench.spec.mjs`, `apps/web/e2e/snapshots/editor-workbench-{1920x1080,1440x900,1280x800,768x1024,390x844}.png`, `docs/prototypes/2026-07-20-editor-workbench/manifest.json`, `docs/decisions/2026-07-20-editor-workbench-visual-approval.ko.md`, and `tests/test_editor_workbench_artifacts.py`.
- Modify `docs/oss/editor-ui-source-map.json`, `tests/test_editor_ui_source_provenance.py`, and `scripts/verify-editor-ui-source-provenance.ps1` only to record/reference-check the Task 11 OpenCut classic panel-layout decision. The Task 11 entries must prove `materialized_paths=[]`, no Task 11 workbench file has an upstream copy header, and no EditorCore/Next/DB/renderer path is imported. Modify `THIRD_PARTY_NOTICES.md` only if an upstream file is copied.

## Task 1: Make density policy a pure, tested UI contract

- [ ] **Step 1: Write the meaningful product RED** in the existing `apps/web/src/app/AppRouter.test.tsx`. Route a populated `editor?session_id=` fixture at 1920 and 1440, then require `data-editor-density`, a preview-slot landmark, and a `data-preview-min-width` value meeting the density rule. The current legacy editor must fail these assertions before any new workbench module/test file is created.

- [ ] **Step 2: Run the product RED.**

Run: `npm --prefix apps/web test -- src/app/AppRouter.test.tsx`

Expected: FAIL because the current canonical editor route mounts the legacy page and exposes neither workbench density nor computed preview guard.

- [ ] **Step 3: Add focused pure tests** in `editorWorkbenchLayout.test.ts`.

```ts
expect(resolveEditorWorkbenchLayout({ viewportWidth: 1920, availableWorkbenchWidth: 1720, persisted: bothOpen })).toMatchObject({ mode: "desktop-both", previewMinPx: 720 })
expect(resolveEditorWorkbenchLayout({ viewportWidth: 1440, availableWorkbenchWidth: 1130, persisted: bothOpen })).toMatchObject({ mode: "desktop-single", leftOpen: true, rightOpen: false, previewMinPx: 640 })
expect(resolveEditorWorkbenchLayout({ viewportWidth: 768, availableWorkbenchWidth: 700, persisted: bothOpen })).toMatchObject({ mode: "drawer", leftOpen: false, rightOpen: false })
```

- [ ] **Step 4: Implement the smallest pure resolver.** Persist only `{ leftOpen, rightOpen, activeDrawer, leftSize, rightSize }`; normalize stale/invalid JSON and never include project, session, asset, or selected segment IDs.

- [ ] **Step 5: Run GREEN** for both the new resolver and existing route contract.

Run: `npm --prefix apps/web test -- src/features/editor/workbench/editorWorkbenchLayout.test.ts src/app/AppRouter.test.tsx`

Expected: PASS. Include exact 1600, 1599, 1280, 1279, 768, and 390 viewport boundaries plus cases where shell/sidebar/gutters leave insufficient available width. The returned panel constraints must make `previewWidth >= max(640, availableWorkbenchWidth / 2)` in single mode and `>= 720` in both-dock mode.

- [ ] **Step 6: Commit later with the completed Task 11 logical commit.**

## Task 2: Build the read-only semantic workbench shell

- [ ] **Step 1: Write the meaningful product RED** in the existing `apps/web/src/app/AppRouter.test.tsx`. The populated canonical editor route must require the five workbench landmarks, an empty `audio,video` query, exactly one `api.getEditorPlaybackManifest` call, and no Director/media API call. The legacy routed editor must fail this contract before a new component test file is created.

- [ ] **Step 2: Run the product RED.**

Run: `npm --prefix apps/web test -- src/app/AppRouter.test.tsx`

Expected: FAIL because the legacy routed editor lacks the workbench landmarks and mounts stateful panel/media behavior.

- [ ] **Step 3: Add focused component tests** in `editor-workbench.test.tsx` using an existing typed `EditorViewModel` fixture.

```tsx
render(<EditorWorkbench view={view} adapters={<EditorWorkbenchReadOnlyAdapters view={view} />} />)
expect(screen.getByRole("region", { name: "편집 작업판" })).toBeVisible()
expect(screen.getByRole("region", { name: "미리보기 자리" })).toBeVisible()
expect(screen.getByRole("complementary", { name: "자산과 대본" })).toBeVisible()
expect(screen.getByRole("complementary", { name: "유진과 Inspector" })).toBeVisible()
expect(screen.getByRole("region", { name: "타임라인" })).toBeVisible()
```

- [ ] **Step 4: Implement `EditorWorkbench`.** Use the pinned `ResizablePanelGroup`, `ResizablePanel`, and `ResizableHandle`; apply the resolver's actual min/max sizes to the panels. Render typed tracks/captions/gaps as read-only summaries. The central stage is a labelled slot, not a new video player. `EditorWorkbenchReadOnlyAdapters` derives asset/script/caption/Inspector text from the immutable view and renders an explicitly disabled local composer draft; it imports no current Director/media panel.

- [ ] **Step 4a: Lock the right dock contract.** The right dock must expose a disabled textarea with accessible label `유진에게 요청하기`, a separate disabled submit button labelled `요청 보내기`, `추천` with the exact empty message `추천은 다음 단계에서 준비합니다.`, and `Inspector` with manifest-derived selected segment/track/caption summary. Tests must assert all four controls/landmarks and must assert no proposal/conversation/preflight data is invented or fetched.

- [ ] **Step 5: Add keyboard/focus behavior.** Give resize handles accessible labels and arrow-key resize behavior. At narrow mode, open one `aria-modal` drawer at a time; Escape closes it and returns focus to its trigger. Do not use global key listeners that change media or editor mutation state.

- [ ] **Step 6: Run GREEN** for the component and product contract.

Run: `npm --prefix apps/web test -- src/features/editor/workbench/editor-workbench.test.tsx src/app/AppRouter.test.tsx`

Expected: PASS. Mock every Director/media API export plus `fetch`, assert zero calls after mount, drawer, resize, and disabled-composer interactions, and assert no `audio`/`video` element or preview URL appears. Assert no supplied mutation spy is called by buttons, drawers, or resizers.

## Task 3: Integrate without duplicating editor truth

- [ ] **Step 1: Write RED route/integration tests** in `AppRouter.test.tsx` and the relevant `App` test file.

```tsx
expect(renderedEditorWorkbench).toHaveAttribute("data-project-id", "project-1")
expect(renderedEditorWorkbench).toHaveAttribute("data-session-id", "session-1")
expect(screen.getByRole("button", { name: "요청 보내기" })).toBeDisabled()
expect(api.getEditorPlaybackManifest).toHaveBeenCalledWith("project-1", "session-1")
expect(api.getEditorPlaybackManifest).toHaveBeenCalledTimes(1)
```

- [ ] **Step 2: Run RED.**

Run: `npm --prefix apps/web test -- src/app/AppRouter.test.tsx src/app/routeManifest.test.ts src/app.test.tsx`

Expected: FAIL because the canonical routed editor still mounts the legacy page, does not force the ProductShell sidebar closed, and has no single immutable view-model read contract.

- [ ] **Step 3: Render `EditorWorkbenchRoute` only from `/projects/$projectId/editor?session_id=`.** It validates the session query, calls `api.getEditorPlaybackManifest(projectId, sessionId)` exactly once, creates `new VideoBoxEditorAdapter(manifest).viewModel`, and rejects a manifest whose project/session identity differs from the route. `WorkspacePage` wraps it in `ProductShell forceCollapsed`; direct refresh, missing session, fetch failure, and identity mismatch use recovery UI. `ProductShell` initializes collapsed for this route, permits one explicit user reopen while mounted, and resets collapsed after route exit/re-entry. `LegacyWorkspacePage` is not mounted for this canonical editor route and remains for parity until Task 22.

- [ ] **Step 4: Do not mount stateful adapters.** The route passes only the immutable editor view to the metadata-only adapters. There is no Director/media API, command port, or mutation callback prop in the Task 11 workbench interface.

- [ ] **Step 5: Run GREEN** with the same focused integration command.

## Task 4: Add scoped styling, source records, and visual evidence

- [ ] **Step 1: Write RED tests** for viewport `data-density`, stable landmarks, and actual preview `getBoundingClientRect().width` at 1920/1440/1280/768/390.

- [ ] **Step 2: Add `editor-workbench.css`** under a `.vb-editor-workbench` root. Keep responsive geometry in CSS, retain minimum preview sizes from the pure layout contract, and avoid global legacy-style changes.

- [ ] **Step 3: Update provenance records with RED-first verifier coverage.** First make `tests/test_editor_ui_source_provenance.py` and `verify-editor-ui-source-provenance.ps1` fail when a Task 11 workbench path has an upstream copy header/materialized path or forbidden EditorCore/Next/DB/renderer import. Then add the reference-only OpenCut classic panel-layout decision with `materialized_paths=[]`. Do not modify `THIRD_PARTY_NOTICES.md` unless a source file is copied; no Task 11 source file may carry an upstream copy header.

- [ ] **Step 4: Generate committed deterministic visual artifacts.** `editor-workbench.spec.mjs` must seed its local fake API with one immutable populated editor view, set exactly 1920x1080/1440x900/1280x800/768x1024/390x844, assert landmarks and preview bounds, then write the five named PNGs. `tests/test_editor_workbench_artifacts.py` must verify exact PNG set, dimensions, byte SHA-256, manifest digest, required Korean labels, and the linked approval record. `manifest.json` starts `approval.status="pending"`; only the user approval changes it to `approved`.

- [ ] **Step 5: Obtain the second explicit user visual approval.** Without it, commit technical work but leave Task 11 unchecked and record `approval_required` in the handoff.

## Task 5: Closeout gates

- [ ] Run focused Task 11 frontend tests, `npm --prefix apps/web test`, `npm --prefix apps/web run build`, `npm --prefix apps/web run test:e2e -- e2e/editor-workbench.spec.mjs`, `.venv\Scripts\python.exe -m pytest -q tests/test_editor_workbench_artifacts.py tests/test_editor_ui_source_provenance.py`, `./scripts/verify-editor-ui-source-provenance.ps1`, `./scripts/verify-editor-ui-system.ps1`, and `git diff --check`.
- [ ] Perform independent specification review, code-quality review, plan-gap review, and source→runtime reverse review. Fix Critical/Important findings and re-review.
- [ ] Update the 22-Task plan/status/handoff only from observed tests, artifacts, approval, and commit. Preserve Task 9 at `9/22 (40.9%)` until its separate human/asset/CapCut evidence exists.
- [ ] Create one logical Task 11 commit and push only after every required acceptance item is evidenced. If user visual approval is absent, do not mark Task 11 complete or pretend the release plan is complete.
