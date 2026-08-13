# VideoBox Wave 4 Yujin, Review and Multi-Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 유진의 상황별 제안을 출력 변형까지 안전하게 적용하고, 현재 변형을 검토한 뒤 가로·세로 영상을 독립적으로 출력·복구한다.

**Architecture:** Extend the strict Yujin operation union with variant identity and bounded reframe/layout operations. Reviews bind master, variant and derived timeline revisions. A batch output endpoint is only an envelope that creates/reuses independent existing final-render jobs per variant.

**Tech Stack:** Pydantic strict unions, existing proposal attestation and transactions, FastAPI, review/output lineage, FFmpeg, React/Vitest/Playwright.

---

## Current implementation audit (2026-08-13)

| Task | Current state | Implemented evidence | Remaining implementation |
| --- | --- | --- | --- |
| 1. Contextual starters | partial | `RightDock` fixed four-chip empty-state baseline, zero-send/focus tests, commit `2a4e28eb7` | surface/selection/blocker registry, `다른 예시`, `전체 보기`, local usage-frequency promotion, Home integration |
| 2. Variant proposals | not implemented | existing creator proposal adapter handles current session/media proposal contracts | `variant_id`, `base_variant_revision`, reframe/layout/audio operations and vertical-full story rejection |
| 3. Preview/apply/undo | partial baseline | existing session proposal preview/apply/manual undo paths | dual master+variant revision preflight, variant transaction, double-apply protection and variant before/after cards |
| 4. Variant review lineage | partial baseline | existing timeline/session review and Wave 3 output source verification | persist/select exact variant revision, variant-specific staleness and grouped creator actions |
| 5. Independent outputs | not implemented | existing single timeline `/jobs/final-render` and one `OutputsPage` final card | `/variant-renders` envelope, independent sibling jobs/cards/retry and optional highlight selection |
| 6. In-app output verification | partial baseline | existing single final MP4 player and retry action | horizontal/vertical players, start/middle/end proof, per-result confirmation and folder action |
| 7. Wave gate | not run | Wave 3 runtime/browser gate is complete | complete Wave 4 implementation, focused/full regression, real browser reverse flow and review |

Existing baselines are reusable but do not satisfy the bundled Wave 4 checkboxes below. Check a task only when every requirement in that checkbox is implemented and verified.

### Task 1: Add contextual starter registry

**Files:**
- Create: `apps/web/src/features/yujin/starterRegistry.ts`
- Create: `apps/web/src/features/yujin/YujinStarters.tsx`
- Modify: `apps/web/src/features/editor/workbench/RightDock.tsx`
- Modify: `apps/web/src/features/home/HomeYujinChat.tsx`
- Test: `apps/web/src/features/yujin/YujinStarters.test.tsx`

- [x] Baseline completed in the focused conversation-starter plan: four immutable Right Dock chips fill/focus the composer with zero send/mutation (`2a4e28eb7`).

- [ ] Write failing tests for 4–6 starters by plan/assets/footage/edit/review/output context, `다른 예시`, `전체 보기`, recent-frequency promotion, and click-fills-composer-with-zero-send/zero-mutation.
- [ ] Run RED with `npm --prefix apps/web test -- src/features/yujin/YujinStarters.test.tsx`.
- [ ] Implement a pure registry keyed by surface, selection kind and blockers. Persist only starter usage counts locally; never edit project data from a starter click.
- [ ] Repeat the previous Vitest command, run `git diff --check`, and commit `feat: add contextual yujin conversation starters`.

### Task 2: Extend strict proposals for output variants

**Files:**
- Modify: `packages/domain-models/src/videobox_domain_models/yujin_creator_proposals.py`
- Modify: `packages/domain-models/src/videobox_domain_models/yujin_creator_context.py`
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_creator_proposal_adapter.py`
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_creator_context.py`
- Test: `tests/test_yujin_creator_proposals.py`
- Test: `tests/test_yujin_creator_proposal_adapter.py`

- [ ] Write failing strict-model tests for `variant_id`, `base_variant_revision`, focal/crop, caption layout, safe-area and bounded audio correction. Assert raw filesystem/DB/shell/render/HTTP operations and `vertical_full` story changes are rejected.
- [ ] Run RED with `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_yujin_creator_proposals.py tests/test_yujin_creator_proposal_adapter.py -q`.
- [ ] Extend discriminated unions and context with current surface, selection, master identity and variant identity. Validate referenced assets/segments and both revisions before projection.
- [ ] Repeat the previous pytest command, run `git diff --check`, and commit `feat: bind yujin proposals to output variants`.

### Task 3: Preserve preview/apply/undo transaction semantics

**Files:**
- Modify: `services/api/src/videobox_api/routers/director_proposals.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Modify: `apps/web/src/features/editor/workbench/RightDock.tsx`
- Test: `tests/test_yujin_media_proposal_adapter.py`
- Test: `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`

- [ ] Add failing tests: proposal preview/cancel causes zero session/variant changes; stale master or variant returns refresh; explicit apply creates exactly one transaction; undo restores; double-click does not duplicate.
- [ ] Run RED with `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_yujin_media_proposal_adapter.py tests/test_yujin_text_voice_overlay_proposal_adapter.py -q` and `npm --prefix apps/web test -- src/features/editor/workbench/editor-workbench-route.test.tsx`.
- [ ] Extend preflight and atomic apply to validate both revisions and record affected variant fields. Keep candidate materialization and proposal lifecycle transactional. Do not let model output call store/render directly.
- [ ] Render compact cards with change list, evidence, uncertainty, `변경 전후`, `수정`, `미리보기`, then enabled `적용`.
- [ ] Repeat the previous backend and frontend commands, run `git diff --check`, and commit `feat: apply yujin variant edits safely`.

### Task 4: Bind review to variant lineage

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/output_source_verifier.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Modify: `apps/web/src/features/review/timeline-review-state.ts`
- Modify: `apps/web/src/features/review/TimelineReviewPage.tsx`
- Test: `tests/test_review_timeline.py`
- Test: `tests/test_output_source_verifier.py`
- Test: review frontend tests

- [ ] Write failing tests for exact project/timeline/session/session-revision/variant/variant-revision identity, master edit staling both default variants, variant-only edit staling only that variant, and legacy compatibility.
- [ ] Run RED with `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_review_timeline.py tests/test_output_source_verifier.py -q` and `npm --prefix apps/web test -- src/features/review/timeline-review-state.test.ts src/features/review/TimelineReviewPage.test.tsx`.
- [ ] Persist variant identity on new review approvals/snapshots and make current-state selection fail closed on mismatch. Show problems grouped by `내용/자막/화면/소리/자산`, with navigable position and creator action.
- [ ] Repeat the previous backend/frontend commands, run `git diff --check`, and commit `feat: review exact output variant revisions`.

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

- [ ] Write failing tests for `POST /api/projects/{id}/variant-renders` returning itemized variant/timeline/job statuses, horizontal success plus vertical failure, retry vertical only, idempotent double submit and optional highlight absent until created.
- [ ] Run RED with `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_api_final_render_endpoint.py tests/test_final_render_idempotency.py -q` and `npm --prefix apps/web test -- src/app/OutputsPage.test.tsx`.
- [ ] Implement the envelope by materializing each selected variant and calling existing `create_or_reuse_active_final_render_job` independently. Never create a shared terminal status or cancel successful siblings.
- [ ] Split output UI state per variant card. Default checked: `가로 영상`, `세로 영상`; optional `세로 하이라이트` only if present. Keep subtitle and CapCut compatibility advanced/optional.
- [ ] Implement actionable blockers for missing source, format, current review, renderer and space. Reconcile authoritative state after response loss.
- [ ] Repeat the previous backend/frontend commands, run `npm --prefix apps/web run build`, and commit `feat: render horizontal and vertical outputs independently`.

### Task 6: Verify actual output media in app

**Files:**
- Modify: `apps/web/src/app/OutputsPage.tsx`
- Modify: `apps/web/src/app/OutputsPage.test.tsx`
- Modify: `apps/web/e2e/z-script-first-vertical.spec.mjs`

- [ ] Add failing UI/E2E tests for Range-playable horizontal/vertical content, start/middle/end seek, result confirmation, retry failed only and `폴더 열기`/`다시 만들기` actions.
- [ ] Run RED with `npm --prefix apps/web test -- src/app/OutputsPage.test.tsx` and `npm --prefix apps/web run test:e2e -- z-script-first-vertical.spec.mjs`.
- [ ] Wire content URLs to bounded video players; result confirmation is explicit user state and not inferred from render success.
- [ ] Repeat the previous commands, run `git diff --check`, and commit `feat: verify rendered variants inside videobox`.

### Task 7: Wave 4 gate

- [ ] Real browser: starter fills input; send proposal; preview then cancel proves zero mutation; resend, preview, apply exactly once, undo, reapply.
- [ ] Review both current default variants, edit master and prove stale, rebuild/approve. Render both where one controlled fake failure occurs, retain success, retry failure only, then play both.
- [ ] Run `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_yujin_creator_proposals.py tests/test_yujin_creator_proposal_adapter.py tests/test_yujin_media_proposal_adapter.py tests/test_review_timeline.py tests/test_output_source_verifier.py tests/test_output_publish_fences.py tests/test_final_render_idempotency.py tests/test_api_final_render_endpoint.py -q`, `npm --prefix apps/web test -- src/features/yujin src/features/review src/app/OutputsPage.test.tsx`, `npm --prefix apps/web run build`, and `npm --prefix apps/web run test:e2e`; then complete owner-ready runtime proof.
- [ ] Read-only review focuses on model boundary, double apply, lineage mismatch, sibling cancellation, stale UI and creator copy. Complete design §§10–11/§13 gap and reverse table.
