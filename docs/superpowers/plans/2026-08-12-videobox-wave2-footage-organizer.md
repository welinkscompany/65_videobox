# VideoBox Wave 2 Footage Organizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 긴 촬영본을 비파괴 구간으로 정리하고 짧은 촬영본을 가상 시퀀스로 묶어, 승인된 결과를 검색 가능한 B-roll로 등록한다.

**Architecture:** Existing `AutoCutPlanner`/analysis scene windows produce immutable proposal drafts. New global-library source segments and virtual sequences store only source references and user-approved boundaries/order; independent files are rendered only by an explicit derivative job.

**Tech Stack:** Python domain/store, SQLite, FFmpeg scene detection, FastAPI, React/TypeScript, Vitest/Playwright.

---

### Task 1: Persist footage proposals, source segments and virtual sequences

**Files:**
- Create: `packages/domain-models/src/videobox_domain_models/footage_organizer.py`
- Create: `packages/storage-abstractions/src/videobox_storage/footage_organizer_store.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/media_library_store.py`
- Test: `tests/test_footage_organizer_store.py`

- [x] Write failing tests for proposal status `draft|approved|rejected|stale`, source boundaries, immutable source hash, sequence item order, optimistic proposal revision, and user fields surviving reanalysis.
- [x] Run RED with `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_footage_organizer_store.py -q`.
- [x] Add tables `footage_proposals`, `footage_proposal_segments`, `library_source_segments`, `library_virtual_sequences`, `library_virtual_sequence_items`. Foreign keys must prevent source deletion while derived records exist.
- [x] Run `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_footage_organizer_store.py tests/test_sqlite_migration_concurrency.py -q`, then commit `feat: persist non destructive footage organization`.

### Task 2: Convert detection into explainable proposals

**Files:**
- Create: `packages/core-engine/src/videobox_core_engine/footage_organizer.py`
- Modify: `packages/core-engine/src/videobox_core_engine/auto_cut.py`
- Modify: `packages/core-engine/src/videobox_core_engine/ffmpeg_auto_cut_executor.py`
- Test: `tests/test_footage_organizer.py`
- Test: `tests/test_auto_cut.py`

- [x] Write failing tests that combine scene/black/static/audio/analysis windows into bounded suggestions with `reason_codes`, while short input returns a useful single segment and no original mutation.
- [x] Run RED with `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_footage_organizer.py tests/test_auto_cut.py -q`.
- [x] Implement `FootageOrganizerService.propose_segments(library_asset_id, idempotency_key)`. Reuse detection measurements, normalize boundaries, attach creator-language reason codes, and save a draft. Do not call editing-session split/merge.
- [x] Add pure edit operations `move_boundary`, `split_draft`, `merge_drafts`, `exclude_draft`, each requiring expected proposal revision.
- [x] Repeat the previous pytest command, run `git diff --check`, and commit `feat: turn footage analysis into editable proposals`.

### Task 3: Add approval, sequence and derivative APIs

**Files:**
- Create: `services/api/src/videobox_api/routers/footage_organizer.py`
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `services/api/src/videobox_api/main.py`
- Test: `tests/test_api_footage_organizer.py`

- [x] Write failing endpoint tests for propose/get/edit/preview/approve, virtual sequence create/reorder/preview/approve, and explicit derivative render. Assert preview/cancel causes zero library mutations and double approval is idempotent.
- [x] Run RED with `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_api_footage_organizer.py -q`.
- [x] Implement strict endpoints under `/api/footage`. Approval creates searchable `library_source_segments` or a virtual sequence in one transaction; independent render creates a job and derived asset, never overwrites source.
- [x] Reuse library preview Range delivery and register approved derived identities with the semantic index queue.
- [x] Repeat the previous pytest command, run `git diff --check`, and commit `feat: expose footage organization approval flow`.

### Task 4: Build the footage organizer workspace

**Files:**
- Create: `apps/web/src/features/footage/FootageOrganizerPage.tsx`
- Create: `apps/web/src/features/footage/FootageSourceList.tsx`
- Create: `apps/web/src/features/footage/FootagePreview.tsx`
- Create: `apps/web/src/features/footage/SceneTimeline.tsx`
- Create: `apps/web/src/features/footage/FootageSuggestions.tsx`
- Create: `apps/web/src/features/footage/footage.css`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/app/AppRouter.tsx`
- Test: `apps/web/src/features/footage/FootageOrganizerPage.test.tsx`

- [x] Write failing tests for four bounded panes, playhead/boundary synchronization, frame-step adjustment, merge/split/exclude, proposal preview, cancel, explicit apply and virtual sequence reorder.
- [x] Run RED with `npm --prefix apps/web test -- src/features/footage/FootageOrganizerPage.test.tsx`.
- [x] Add typed DTO/client methods and a footage-specific preview controller. Do not import editing `PreviewStage`; reuse only stable preview URL/range behavior.
- [x] Implement starter chips that fill the input only: `장면 변화로 나누기`, `출근 과정만 고르기`, `흔들린 구간 찾기`, `짧은 영상 묶기`, `세로 장면 고르기`, `30초 묶음 만들기`.
- [x] Run `npm --prefix apps/web test -- src/features/footage/FootageOrganizerPage.test.tsx` and `npm --prefix apps/web run build`, then commit `feat: add conversational footage organizer workspace`.

### Task 4A: Add bounded Yujin footage-plan interpretation

**Files:**
- Create: `packages/domain-models/src/videobox_domain_models/yujin_footage_proposals.py`
- Create: `packages/core-engine/src/videobox_core_engine/yujin_footage_proposal_adapter.py`
- Modify: `services/api/src/videobox_api/routers/footage_organizer.py`
- Modify: `apps/web/src/features/footage/FootageSuggestions.tsx`
- Test: `tests/test_yujin_footage_proposal_adapter.py`
- Test: `apps/web/src/features/footage/FootageOrganizerPage.test.tsx`

- [x] Write failing strict-adapter tests for intents `split_by_scene`, `select_process`, `exclude_quality`, `combine_similar`, `select_vertical`, `target_duration`; reject unknown source IDs, out-of-range boundaries, raw filesystem/renderer instructions and direct apply.
- [x] Run RED with `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_yujin_footage_proposal_adapter.py -q`.
- [x] Parse LM Studio output into a strict footage proposal that references the current footage proposal revision. The adapter may select/relabel draft boundaries but must call neither store nor FFmpeg.
- [x] Render the result through the same proposal preview and explicit approval path as manual suggestions; ambiguous requests return a short clarification instead of mutating.
- [x] Run the backend command and `npm --prefix apps/web test -- src/features/footage/FootageOrganizerPage.test.tsx`, then commit `feat: let yujin propose footage organization`.

### Task 5: Wave 2 gate

- [ ] In a real browser, copy a long QA source into the library, propose segments, move one boundary, merge two, exclude one, preview continuously, cancel once and verify no derived row, then approve. **Partial evidence only:** browser UI verified source selection, analysis, boundary controls and segment selection; ingest and merge/exclude were completed through the official local API because the in-app CLI upload/control path could not drive those stateful actions reliably.
- [ ] Combine three short clips virtually, reorder them, reload and approve. Verify source hashes and mtimes remain unchanged and results appear in semantic B-roll search. **Blocker:** current sequence storage/API intentionally requires every item to belong to one `source_id`; a cross-source three-file attempt returned HTTP 400. Same-source three-segment virtual sequence passed reorder/reload/preview/cancel/approve/replay, and source hash/preview Last-Modified values remained unchanged.
- [x] Run `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_auto_cut.py tests/test_ffmpeg_auto_cut_executor.py tests/test_local_pipeline_auto_cut_detection.py tests/test_api_footage_organizer.py -q`, `npm --prefix apps/web test -- src/features/footage/FootageOrganizerPage.test.tsx`, `npm --prefix apps/web run build`, and `npm --prefix apps/web run test:e2e`.
- [x] Complete read-only review, design §7 gap table and reverse checks for stale proposal, conflicting revision and derivative render failure.

---

## Closeout evidence (2026-08-12)

### Implementation and verification

- Task 1–4A were implemented in the preceding commits and rechecked by the closeout suites. The new ingest slice persists FFmpeg probe metadata for user B-roll without making copy-first ingest fail when probing is unavailable.
- Backend focused gate: `94 passed, 1 warning` using the canonical worktree `.venv\Scripts\python.exe`.
- Frontend footage/design gate: `11 passed`; production build succeeded. The only build note is the existing Vite chunk-size warning.
- Chromium E2E: `39 passed`; `compileall`, `git diff --check` passed.

### Browser/runtime evidence and limits

- At `1280x800`, `/`, `/library`, `/footage`, and the project shell were opened in the real browser. `/library` and `/footage` rendered real asset/source states without stale placeholders; console errors/warnings and HTTP 4xx/5xx were absent in the checked routes.
- `/footage` rendered the four bounded panes. Long-source selection, analysis, proposal preview state, boundary controls, segment selection and focus styling were browser-observed. The root catalog still reports horizontal overflow (`scrollWidth=1350`, `clientWidth=1280`); footage/library/project-shell overflow checks were bounded.
- Official local API evidence completed long proposal preview (`HTTP 200`, `video/mp4`, `accept-ranges: bytes`, ranged response), cancel without approval mutation, approval and replay idempotency. A same-source three-segment virtual sequence passed reorder/reload/preview/cancel/approval replay. A cross-source three-file sequence was rejected closed with HTTP 400 because the current contract is single-source.
- Approved source segments appeared in B-roll search and the live search response reported `semantic: true`; source content hashes and preview `Last-Modified` values stayed unchanged during virtual operations.

### Design §7 gap table

| 설계 기준 | 확인된 구현/증거 | 상태 |
|---|---|---|
| 왼쪽 source list·중앙 preview·timeline·오른쪽 Yujin 제안 | 실제 `/footage` 4-pane browser state, focused frontend tests | 통과 |
| 원본 비파괴·preview/approval 분리 | proposal revision/source hash, cancel/approve API evidence, 94 backend tests | 통과 |
| 내부 스크롤·1280px desktop 작업영역 | `/library`, `/footage`, project shell bounded; footage CSS pane overflow | 통과 |
| token/radius/focus/40px control rule | `intranet-style` skill reference applied; `footage-design-system.test.ts` 5 passed | 통과 |
| 서로 다른 원본 3개를 virtual sequence로 결합 | live cross-source attempt HTTP 400; storage enforces one source | 미충족 blocker |
| root catalog horizontal overflow | browser measurement `1350 > 1280` | 미해결 gap |

이 closeout은 개발·자동 검증·확인 가능한 runtime 범위를 닫은 것이다. 사람의 취향 판단을 포함한 owner acceptance, 실제 3-file cross-source sequence, root catalog overflow 수정은 완료로 표시하지 않는다.
