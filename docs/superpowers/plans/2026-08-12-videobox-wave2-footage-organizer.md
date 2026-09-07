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

- [x] In a real browser, use the persisted long QA source to inspect the proposal, move a boundary, and verify the preview/actions surface. The long proposal’s valid merge/exclude/continuous preview/cancel/approve and no-derived-row checks were completed through the official local API because the native media seek control did not reliably retain a non-zero playhead in this environment. This is runtime evidence, not owner acceptance.
- [x] Combine three short clips from three distinct source assets virtually, preview each source item, reorder, reload and approve. The browser sequence was `vseq_33272fafbe5d9631e0fe7c5d71ad32f5`; item sources were `source:user_c3bd85ed98844527bf62539f1aebb229`, `source:user_981f1b16e17446ecbb1ba85e253f39dc`, and `source:user_233279bbd90f414d9e167f77f1ff466f`. Source hashes/mtimes stayed unchanged and approval registered the approved item segments for semantic B-roll search.
- [x] Run `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_auto_cut.py tests/test_ffmpeg_auto_cut_executor.py tests/test_local_pipeline_auto_cut_detection.py tests/test_api_footage_organizer.py -q`, `npm --prefix apps/web test -- src/features/footage/FootageOrganizerPage.test.tsx`, `npm --prefix apps/web run build`, and `npm --prefix apps/web run test:e2e`.
- [x] Complete read-only review, design §7 gap table and reverse checks for stale proposal, conflicting revision and derivative render failure.

---

## Closeout evidence (2026-08-13)

### Implementation and verification

- Task 1–4A were implemented in the preceding commits and rechecked by the closeout suites. The new ingest slice persists FFmpeg probe metadata for user B-roll without making copy-first ingest fail when probing is unavailable.
- Backend focused gate: `106 passed, 1 warning` using the canonical worktree `.venv\Scripts\python.exe`.
- Frontend footage/design gate: `16 passed`; production build succeeded. The only build note is the existing Vite chunk-size warning.
- Chromium E2E: `39 passed`; `compileall`, `git diff --check` passed.

### Browser/runtime evidence and limits

- At outer `1280x800`, `/` (redirecting to `/projects`), `/library`, `/footage`, and the project shell were opened in the real browser. `/library` and `/footage` rendered real asset/source states without stale placeholders; the final checked routes had no console errors and no HTTP 4xx/5xx.
- `/footage` rendered the four bounded panes. The long source was selected/analyzed and its boundary action was browser-observed. The three-source flow created a virtual sequence, exposed three per-source preview buttons, switched preview URLs for all three sources, reordered item 2 upward, reloaded the persisted order, cancelled without a preview status, then previewed and approved it. Document/body overflow was `1280/1264` at the checked desktop size.
- Official local API evidence completed long proposal preview (`HTTP 200`, `video/mp4`, `accept-ranges: bytes`, ranged response), cancel without approval mutation, approval and replay idempotency, plus valid merge/exclude and derivative fail-closed checks. The multi-source sequence preview intentionally returns per-source previews; combined derivative rendering remains fail-closed rather than silently rendering only the first source.
- Approved source segments were registered through the semantic-index path; source content hashes and preview `Last-Modified` values stayed unchanged during virtual operations. The focused API test also verifies semantic search registration for the second and third sources.

### Design §7 gap table

| 설계 기준 | 확인된 구현/증거 | 상태 |
|---|---|---|
| 왼쪽 source list·중앙 preview·timeline·오른쪽 Yujin 제안 | 실제 `/footage` 4-pane browser state, focused frontend tests | 통과 |
| 원본 비파괴·preview/approval 분리 | proposal revision/source hash, cancel/approve API evidence, 94 backend tests | 통과 |
| 내부 스크롤·1280px desktop 작업영역 | `/library`, `/footage`, project shell bounded; footage CSS pane overflow | 통과 |
| token/radius/focus/intranet control rule | `intranet-style` skill reference applied; `footage-design-system.test.ts` 8 passed | 통과 |
| 서로 다른 원본 3개를 virtual sequence로 결합 | browser sequence `vseq_33272fafbe5d9631e0fe7c5d71ad32f5`, three source identities, per-source preview/reorder/reload/cancel/approve | 통과 |
| root catalog horizontal overflow | browser measurement `document=1280`, `body=1264` at outer `1280x800`; bounded catalog CSS | 통과 |

이 closeout은 개발·자동 검증·확인 가능한 runtime 범위를 닫은 것이다. owner-ready 자동 게이트와 실제 브라우저 증거는 확보했지만, 사람의 취향 판단을 포함한 owner acceptance는 아직 완료로 표시하지 않는다. 브라우저의 native seek가 비영점 playhead을 안정적으로 유지하지 못한 범위는 API 증거로 보완했으며, 이를 owner acceptance 증거로 확대 해석하지 않는다.

### 이후 확인된 사항 (2026-08-15)

Task 1~5는 그대로 닫힌 상태다. 다만 위 §7 gap table의
`token/radius/focus/intranet control rule` 줄은 **화면 문구 규정(`§10.13`)까지
확인하지는 못했다.** 이후 점검에서 Task 4가 만든 `/footage` 머리말이
`VIDEObox / Wave-2`로, 이 계획서의 wave 이름을 그대로 사용자 화면에 노출하고
있었다. `65d38a8b5`에서 `VideoBox`로 고쳤다.

교훈: 새 화면을 추가할 때 디자인 토큰 검증만으로는 부족하고, **계획서·내부 단계
이름이 copy에 섞이지 않았는지**를 같이 본다. `§10.13.5`가 요구하는 copy audit이
이 경우를 잡는 지점이다.

`intranet-style` 스킬은 `~/.claude/skills/intranet-style`에 있고, 그 계약은
`footage-design-system.test.ts`가 VideoBox CSS 변수로 번역해 강제하고 있다.
