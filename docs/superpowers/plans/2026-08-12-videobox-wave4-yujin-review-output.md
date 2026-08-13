# VideoBox Wave 4 Yujin, Review and Multi-Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 유진의 상황별 제안을 출력 변형까지 안전하게 적용하고, 현재 변형을 검토한 뒤 가로·세로 영상을 독립적으로 출력·복구한다.

**Architecture:** Extend the strict Yujin operation union with variant identity and bounded reframe/layout operations. Reviews bind master, variant and derived timeline revisions. A batch output endpoint is only an envelope that creates/reuses independent existing final-render jobs per variant.

**Tech Stack:** Pydantic strict unions, existing proposal attestation and transactions, FastAPI, review/output lineage, FFmpeg, React/Vitest/Playwright.

---

## Current implementation audit (2026-08-13)

| Task | Current state | Implemented evidence | Remaining implementation |
| --- | --- | --- | --- |
| 1. Contextual starters | complete | `starterRegistry.ts`, `YujinStarters.tsx`, RightDock/Home/Footage integration, actual edit-selection context, 32 focused tests, Footage/editor route/design regression tests, build and diff-check | assets/review/output registry consumers belong to the later variant/review/output tasks; real browser/owner acceptance remains a Wave 5/gate concern |
| 2. Variant proposals | complete | `afefbc6`, `cc564073`, strict proposal/context tests, pure adapter boundary and finite-number rejection | owner/runtime/browser proof remains in Task 7 |
| 3. Preview/apply/undo | complete | `1c1b4533f`, transactional variant apply, CAS/double-apply tests and editor route tests | owner/runtime/browser proof remains in Task 7 |
| 4. Variant review lineage | complete | `9c1a63fbf`, SQLite/Postgres/API lineage persistence and frontend fail-closed reverse tests | owner/runtime/browser proof remains in Task 7 |
| 5. Independent outputs | complete | `43fca6ef7`, `/variant-renders`, independent materialization/jobs, idempotent sibling tests and per-variant cards | owner/runtime/browser proof remains in Task 7 |
| 6. In-app output verification | complete with one platform blocker | `41a51e16`, Playwright range seek and explicit result confirmation for horizontal/vertical | OS-level `폴더 열기` cannot be safely invoked from browser; visible storage URI remains available |
| 7. Wave gate | implementation and isolated QA complete; owner gate open | focused/full backend/frontend regression, build, isolated Playwright E2E, code-review/gap/reverse checks recorded below | real browser reverse flow, owner runtime proof and human acceptance |

Existing baselines are reusable but do not satisfy the bundled Wave 4 checkboxes below. Check a task only when every requirement in that checkbox is implemented and verified.

### Task 1: Add contextual starter registry

**Files:**
- Create: `apps/web/src/features/yujin/starterRegistry.ts`
- Create: `apps/web/src/features/yujin/YujinStarters.tsx`
- Modify: `apps/web/src/features/editor/workbench/RightDock.tsx`
- Modify: `apps/web/src/features/home/HomeYujinChat.tsx`
- Modify: `apps/web/src/features/footage/FootageSuggestions.tsx`
- Test: `apps/web/src/features/yujin/YujinStarters.test.tsx`
- Test: `apps/web/src/features/footage/FootageSuggestions.test.tsx`

- [x] Baseline completed in the focused conversation-starter plan: four immutable Right Dock chips fill/focus the composer with zero send/mutation (`2a4e28eb7`).

- [x] Write failing tests for 4–6 starters by plan/assets/footage/edit/review/output context, `다른 예시`, `전체 보기`, recent-frequency promotion, and click-fills-composer-with-zero-send/zero-mutation.
- [x] Run RED with `npm --prefix apps/web test -- src/features/yujin/YujinStarters.test.tsx` (expected module-missing failure before implementation).
- [x] Implement a pure registry keyed by surface, selection kind and blockers. Persist only starter usage counts locally; never edit project data from a starter click.
- [x] Repeat the previous Vitest command (7 passed), run `git diff --check`, and commit `feat: add contextual yujin conversation starters`.
- [x] Close review gaps: connect FootageSuggestions to the shared registry, derive RightDock selection from `selectedSegment`, keep Footage quick-fill enabled before proposal creation, and disable starter navigation with the composer.
- [x] Verify Home/Footage zero-send/zero-mutation integration and shared starter styling with focused regression tests, design-system tests, build, and diff-check.

### Task 2: Extend strict proposals for output variants

**Files:**
- Modify: `packages/domain-models/src/videobox_domain_models/yujin_creator_proposals.py`
- Modify: `packages/domain-models/src/videobox_domain_models/yujin_creator_context.py`
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_creator_proposal_adapter.py`
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_creator_context.py`
- Test: `tests/test_yujin_creator_proposals.py`
- Test: `tests/test_yujin_creator_proposal_adapter.py`

- [x] Write failing strict-model tests for `variant_id`, `base_variant_revision`, focal/crop, caption layout, safe-area and bounded audio correction. Assert unsafe operations and `vertical_full` story changes are rejected.
- [x] Run RED and the focused proposal pytest command.
- [x] Extend discriminated unions and context with current surface, selection, master identity and variant identity; validate both revisions before projection.
- [x] Repeat the focused pytest command, run `git diff --check`, and commit `afefbc6`/`cc564073`.

### Task 3: Preserve preview/apply/undo transaction semantics

**Files:**
- Modify: `services/api/src/videobox_api/routers/director_proposals.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Modify: `apps/web/src/features/editor/workbench/RightDock.tsx`
- Test: `tests/test_yujin_media_proposal_adapter.py`
- Test: `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`

- [x] Add failing tests for zero-mutation preview/cancel, stale revisions, one transactional apply, undo and double-click protection.
- [x] Run the focused backend/frontend RED and regression commands.
- [x] Extend preflight and atomic apply to validate both revisions and keep adapter/store/render boundaries separate.
- [x] Keep variant candidates on the explicit preview then approval path with actionable labels.
- [x] Repeat the focused commands, run `git diff --check`, and commit `1c1b4533f`.

### Task 4: Bind review to variant lineage

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/output_source_verifier.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Modify: `apps/web/src/features/review/timeline-review-state.ts`
- Modify: `apps/web/src/features/review/TimelineReviewPage.tsx`
- Test: `tests/test_review_timeline.py`
- Test: `tests/test_output_source_verifier.py`
- Test: review frontend tests

- [x] Write failing tests for exact project/timeline/session/session-revision/variant/variant-revision identity, stale mismatch and legacy compatibility.
- [x] Run the focused backend/frontend review commands.
- [x] Persist variant identity on new review approvals/snapshots and make current-state selection fail closed on mismatch.
- [x] Repeat the backend/frontend commands, run `git diff --check`, and commit `9c1a63fbf`.

### Task 5: Orchestrate independent horizontal and vertical outputs

**Files:**
- Modify: `services/api/src/videobox_api/routers/outputs.py`
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
- Create: `apps/web/src/features/outputs/VariantOutputCard.tsx`
- Create: `apps/web/src/features/outputs/variantOutputState.ts`
- Modify: `apps/web/src/app/OutputsPage.tsx`
- Test: `tests/test_api_final_render_endpoint.py`
- Test: `tests/test_final_render_idempotency.py`
- Test: `apps/web/src/app/OutputsPage.test.tsx`

- [x] Write failing tests for itemized variant/timeline/job statuses, independent siblings, idempotent double submit and optional highlight absence.
- [x] Run RED and the focused backend/frontend commands.
- [x] Implement the envelope by materializing each selected variant and calling independent `create_or_reuse_active_final_render_job` paths.
- [x] Split output UI state per variant card with default horizontal/vertical selection and optional highlight only when present.
- [x] Reconcile authoritative final-render status after the batch response and preserve successful siblings when one item fails.
- [x] Repeat the commands, run `npm --prefix apps/web run build`, and commit `43fca6ef7`.

### Task 6: Verify actual output media in app

**Files:**
- Modify: `apps/web/src/app/OutputsPage.tsx`
- Modify: `apps/web/src/app/OutputsPage.test.tsx`
- Modify: `apps/web/e2e/z-script-first-vertical.spec.mjs`

- [x] Add failing UI/E2E tests for range-playable horizontal/vertical content, start/middle/end seek, explicit result confirmation and per-variant retry.
- [x] Run the focused Vitest, build and Playwright commands.
- [x] Wire content URLs to bounded video players; result confirmation is an explicit user action.
- [x] Repeat the commands, run `git diff --check`, and commit `41a51e16`/`3bf75e02`.
- [ ] `폴더 열기` remains intentionally unavailable from the browser security boundary; the visible storage URI remains the safe alternative.

### Task 7: Wave 4 gate

- [ ] Real browser: starter fills input; send proposal; preview then cancel proves zero mutation; resend, preview, apply exactly once, undo, reapply.
- [ ] Review both current default variants, edit master and prove stale, rebuild/approve. Render both where one controlled fake failure occurs, retain success, retry failure only, then play both.
- [x] Run the focused backend command (`252 passed, 1 warning`), focused frontend command (`107 passed`), production build, full isolated Playwright E2E (`40 passed`) and targeted variant playback E2E (`2 passed`).
- [x] Code review, gap verification and reverse-flow checks covered model purity, finite-number and lineage rejection, double-apply/CAS, review staleness, independent sibling failure/retry and explicit output confirmation. The reviewer-found adapter/store boundary and context finite-number gaps were fixed in `cc564073`.
- [x] Update the plan with separate implementation, isolated QA, owner-runtime and browser evidence; do not conflate owner-ready Check with owner acceptance.
- [ ] Complete the real browser reverse flow and owner runtime proof at 1280x800 or wider; the prior in-app browser connection timed out, so human acceptance remains open.
