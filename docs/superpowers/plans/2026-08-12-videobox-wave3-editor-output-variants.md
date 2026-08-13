# VideoBox Wave 3 Creator Editor and Output Variants Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 편집 세션을 마스터로 유지하면서 직접 편집 UX와 연결된 가로·세로 출력 변형을 구축한다.

**Architecture:** New output variants store overrides, locks and conflicts rather than duplicate timelines. Each variant materializes to a derived timeline carrying master session/revision and variant/revision identity, allowing existing review/render machinery to remain authoritative.

**Tech Stack:** Pydantic domain models, SQLite/PostgreSQL-compatible project storage, existing editing engine, React workbench, Vitest/Playwright.

---

### Task 1: Define pure output-variant invariants

**Files:**
- Create: `packages/domain-models/src/videobox_domain_models/output_variants.py`
- Create: `packages/core-engine/src/videobox_core_engine/output_variants.py`
- Test: `tests/test_output_variants.py`

- [x] Write failing pure tests for `horizontal`, `vertical_full`, `vertical_highlight`; lock inheritance; master conflict; allowed crop/focal/caption/safe-area/audio overrides; and forbidden delete/reorder/story changes in `vertical_full`.
- [x] Run RED using `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_output_variants.py -q`.
- [x] Implement strict `OutputVariant`, `VariantOverride`, `VariantLock`, `VariantConflict` models and pure `rebase_variant`, `apply_variant_patch`, `materialize_variant` functions. Only highlight can select/reorder master segment IDs.
- [x] Repeat the previous pytest command, run `git diff --check`, and commit `feat: define linked output variant invariants`.

### Task 2: Persist and lazily seed variants

**Files:**
- Create: `packages/storage-abstractions/src/videobox_storage/_store_output_variants.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/sqlite_schema.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/postgres_schema.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Test: `tests/test_output_variant_store.py`
- Test: `tests/test_postgres_project_store.py`

- [x] Write failing tests for two default variants per latest session, optional highlight absence, idempotent legacy seeding, revision conflict, locks/conflicts persistence and SQLite/Postgres parity.
- [x] Run RED with `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_output_variant_store.py tests/test_postgres_project_store.py -q`.
- [x] Add project-scoped `output_variants` and `variant_materializations`. Preserve historic session/timeline JSON; seed horizontal/vertical-full lazily and transactionally.
- [x] Run the previous command plus `tests/test_sqlite_migration_concurrency.py`, then commit `feat: persist linked output variants`.

### Task 3: Add variant API and derived timeline identity

**Files:**
- Create: `services/api/src/videobox_api/routers/output_variants.py`
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `services/api/src/videobox_api/main.py`
- Modify: `packages/timeline-schema/src/videobox_timeline_schema/models.py`
- Modify: `packages/core-engine/src/videobox_core_engine/output_source_verifier.py`
- Test: `tests/test_api_output_variants.py`
- Test: `tests/test_output_source_verifier.py`

- [x] Write failing tests for list/create-highlight/patch/rebase/materialize and identity `{source_session_id, source_session_revision, source_variant_id, source_variant_revision}`. Missing/mismatched identity for new variants must fail closed; legacy artifacts follow an explicit compatibility branch.
- [x] Run RED with `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_api_output_variants.py tests/test_output_source_verifier.py -q`.
- [x] Implement endpoints and derived timeline creation. Materialization reuses current timeline-build path but generates one timeline/job identity per variant.
- [x] Repeat the previous pytest command, run `git diff --check`, and commit `feat: materialize revisioned output variants`.

### Task 4: Complete creator editing commands and persisted UI position

**Files:**
- Modify: `apps/web/src/features/editor/editorCommandPort.ts`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbench.tsx`
- Modify: `apps/web/src/features/editor/timeline/TimelineDock.tsx`
- Create: `apps/web/src/features/editor/workbench/editorUiState.ts`
- Test: corresponding existing `.test.ts`/`.test.tsx` files

- [x] Add failing tests for add/remove/move/replace, trim/split/merge/reorder, B-roll/music/SFX placement, volume/fade/mute/solo, caption text/time/line breaks, undo/redo and project/session-keyed selected segment/playhead restore.
- [x] Run `npm --prefix apps/web test -- src/features/editor/editorCommandPort.test.ts src/features/editor/workbench/editor-workbench-route.test.tsx src/features/editor/timeline/timeline-dock.test.tsx` and document which commands already pass versus missing UI wiring.
- [x] Wire existing API commands through `EditorCommandPort`; add only missing bounded audio/fade DTOs. Keep mutation single-flight, expected revision and authoritative reload after ambiguous failure.
- [x] Persist UI position by `{projectId, sessionId}` without treating localStorage as editing-data authority. Keep undo depth 10 for this wave; display it honestly and do not claim 100 undo levels.
- [x] Repeat the previous Vitest command, run `npm --prefix apps/web run build`, and commit `feat: complete creator editing command surface`.

### Task 5: Add aspect compare and lock/conflict UI

**Files:**
- Create: `apps/web/src/features/editor/variants/VariantSelector.tsx`
- Create: `apps/web/src/features/editor/variants/VariantCompare.tsx`
- Create: `apps/web/src/features/editor/variants/VariantConflictPanel.tsx`
- Create: `apps/web/src/features/editor/variants/variantProjection.ts`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbench.tsx`
- Modify: `apps/web/src/features/editor/preview/preview-stage.tsx`
- Modify: `apps/web/src/styles/editor-workbench.css`
- Test: new focused variant tests and existing preview/workbench tests

- [x] Write failing tests for `마스터/가로/세로/나란히`, synchronized playhead, safe areas, clip focal/crop, caption layout, user lock, master rebase and visible conflict resolution.
- [x] Run RED with `npm --prefix apps/web test -- src/features/editor/variants/VariantSelector.test.tsx src/features/editor/variants/VariantCompare.test.tsx src/features/editor/variants/VariantConflictPanel.test.tsx`.
- [x] Extract a focused variant controller before adding route state. Side-by-side uses one playback clock and two projections; it must not create two competing audio owners.
- [x] Implement creator-language conflicts: `직접 조정 유지`, `마스터 기준 다시 맞추기`. Never silently overwrite a lock.
- [x] Repeat the previous Vitest command, run `npm --prefix apps/web run build`, refresh provenance if required and commit `feat: add linked horizontal vertical editing`.

### Task 6: Wave 3 gate

> 2026-08-13 검증 메모: backend variant lifecycle, server-backed editor UI/e2e, 그리고 local owner-ready runtime의 실제 브라우저 검증을 완료했다. 아래 증거는 owner-ready Check와 실제 브라우저 동작을 분리해 기록하며, human owner acceptance로 간주하지 않는다.

- [x] Browser-edit a master, reload, prove same server revision/segment/playhead. Create horizontal/vertical materializations, change vertical crop/caption, lock it, edit master, prove lock survives and conflict appears.
- [x] Verify vertical-full rejects reorder/delete while optional highlight can be explicitly created and reordered.
- [x] Run `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_editor_timeline_mutations.py tests/test_timeline_placements.py tests/test_output_variants.py tests/test_output_variant_store.py tests/test_output_source_verifier.py -q`, `npm --prefix apps/web test -- src/features/editor`, `npm --prefix apps/web run build`, `npm --prefix apps/web run test:e2e:editor-workbench`, and real owner-ready browser captures at all four desktop viewports.
- [x] Read-only review must focus on route-epoch races, hook order, audio ownership, optimistic conflicts and old-project lazy seeding. Complete design §§8–9 gap/reverse table.

#### Review / gap-reverse evidence (2026-08-13)

| 검토축 | 확인된 증거 | 판정 | 남은 경계 |
| --- | --- | --- | --- |
| route-epoch / hook order | `EditorWorkbenchRoute` route-key reset guards plus editor route/workbench tests and production build | 통과 | 없음 |
| audio ownership | `VariantCompare` one-clock projection, master-only audio note, focused variant tests | 통과 | 실제 미디어 재생은 owner runtime에서 별도 확인 필요 |
| optimistic conflict | expected revision API tests, stale variant/source fail-closed tests, conflict panel tests, live master edit → conflict → `직접 조정 유지` PATCH 200 | 통과 | human owner acceptance 별도 |
| old-project lazy seeding | output-variant API/store tests for idempotent horizontal/vertical seed and SQLite/Postgres parity | 통과 | 실제 기존 owner project의 재시드 acceptance 미검증 |
| reverse failure paths | missing identity, stale source/variant revision, unresolved conflict, forbidden vertical mutation tests, live vertical materialize 201 and highlight create/order PATCH 200 | 통과 | human owner acceptance 별도 |

#### 실제 브라우저 증거 (2026-08-13)

- Runtime: `http://127.0.0.1:5173`, owner-ready Check pass, Hermes dashboard는 재시작하지 않음.
- Editor: 1280×800에서 vertical server variant revision 1 → crop PATCH 200 → lock PATCH 200 → revision 3을 확인했다.
- Master caption 저장 PATCH 200 뒤 master revision 4, server conflict 1건, `master_changed_while_locked`를 표시했다. `직접 조정 유지` PATCH 200 후 variant revision 5와 conflict 해소를 확인했다.
- Vertical materialize POST 201, optional highlight create POST 201, highlight order PATCH 200을 확인했다.
- `/`, `/library`, `/footage`, project home, editor에서 화면 폭 초과 없음, console errors 0건. Tab 이동 시 `나란히` 탭의 `:focus-visible` 적용을 확인했다.
- `owner-ready.ps1 -Mode Check -Json -TimeoutSec 8`: overall pass, VideoBox/Hermes HTTP 200, local model reachable, external provider calls 0, working tree/protected residue 0. 이는 human owner acceptance나 Hermes live chat 검증이 아니다.
