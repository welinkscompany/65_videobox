# VideoBox Wave 1 Personal Media Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** B-roll, 음악, 효과음을 앱에서 드래그앤드롭해 안전하게 복사·분석·검색·미리보기하고, 사용 위치를 보며 휴지통·복원·영구삭제할 수 있는 전역 개인 라이브러리를 만든다.

**Architecture:** `MediaLibraryStore`의 global SQLite authority에 pack과 구분되는 user-asset lifecycle tables를 추가한다. `LibraryIngestService`가 PC와 Drive mirror 모두 copy-only, content-addressed, idempotent ingest로 통합하며 프로젝트는 explicit reference를 통해 materialize한다.

**Tech Stack:** Python, SQLite, FastAPI multipart upload, FFmpeg/FFprobe, existing semantic indexers, React/TypeScript, Vitest/Playwright.

---

### Task 1: Define user library domain and migrate global SQLite

**Files:**
- Create: `packages/domain-models/src/videobox_domain_models/library_assets.py`
- Create: `packages/storage-abstractions/src/videobox_storage/library_user_asset_store.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/media_library_store.py`
- Test: `tests/test_library_user_asset_store.py`
- Test: `tests/test_sqlite_migration_concurrency.py`

- [ ] **Step 1: Write failing store tests.** Pin `LibraryMediaType = broll|music|sfx`, `LibraryAssetOrigin = builtin|user`, lifecycle `processing|ready|needs_attention|trashed`, unique `content_sha256`, user metadata separate from machine metadata, and idempotent concurrent schema creation.
- [ ] **Step 2: Run RED.** `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_library_user_asset_store.py tests/test_sqlite_migration_concurrency.py -q`. Expected: import/table failures.
- [ ] **Step 3: Add strict models and focused tables.** Create `library_user_assets`, `library_asset_derivatives`, `library_ingest_batches`, `library_ingest_items`, `library_project_references`. Store canonical managed relative path, hash, byte count, MIME, technical JSON, machine JSON, user JSON, lifecycle timestamps, provenance and idempotency key. Use `BEGIN IMMEDIATE`; never overload pack `media_assets`.
- [ ] **Step 4: Add migration compatibility.** Existing pack/audio/footage tables remain readable. New schema creation is additive and repeatable; two store constructors must not race or erase rows.
- [ ] **Step 5: Run GREEN and commit.** Repeat `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_library_user_asset_store.py tests/test_sqlite_migration_concurrency.py -q`, run `git diff --check`, then commit `feat: add global user media lifecycle store`.

### Task 2: Build copy-only idempotent ingest

**Files:**
- Create: `packages/core-engine/src/videobox_core_engine/library_ingest.py`
- Modify: `packages/core-engine/src/videobox_core_engine/media_inbox.py`
- Modify: `services/api/src/videobox_api/main.py`
- Test: `tests/test_library_ingest.py`
- Test: `tests/test_media_inbox.py`

- [ ] **Step 1: Write failing ingest tests.** Verify temp-copy → fsync/close → SHA recheck → atomic rename, same hash reuse, same name/different hash disambiguation, response-loss retry, partial batch success and source bytes unchanged.
- [ ] **Step 2: Run RED.** Run `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_library_ingest.py tests/test_media_inbox.py -q`; expected missing service/old move semantics failure.
- [ ] **Step 3: Implement `LibraryIngestService.ingest`.** Accept `media_type`, source stream/path, filename, idempotency key and provenance. Copy to a staging file under the managed root, validate size/hash, rename to a content-addressed destination, persist item state, and enqueue derivative/index work. Roll back only staged bytes on failure.
- [ ] **Step 4: Adapt Drive mirror.** Keep settled-file detection but call the ingest service in copy-only mode. Archive/move of the Drive mirror source is a separate explicit policy; default leaves the source unchanged.
- [ ] **Step 5: Run GREEN and commit.** Repeat the Step 2 command, run `git diff --check`, then commit `feat: unify safe local media ingest`.

### Task 3: Add lifecycle, usage and preview APIs

**Files:**
- Create: `services/api/src/videobox_api/routers/library_assets.py`
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `services/api/src/videobox_api/main.py`
- Modify: `packages/core-engine/src/videobox_core_engine/project_asset_materializer.py`
- Test: `tests/test_api_library_assets.py`
- Test: `tests/test_api_media_library.py`

- [ ] **Step 1: Write failing API tests.** Pin endpoints: `POST /api/library/ingest` multipart batch, `GET /api/library/assets`, `GET /api/library/assets/{id}`, preview/thumbnail/waveform, semantic search reuse, usage, trash, restore, permanent delete and project materialize. Assert starter assets reject trash, referenced assets return 409 with exact locations, and retries reuse the ingest item.
- [ ] **Step 2: Run RED.** Run `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_api_library_assets.py tests/test_api_media_library.py -q`; expected 404.
- [ ] **Step 3: Implement strict request/response DTOs.** Return creator-relevant state and stable internal codes; never expose absolute managed paths. Extend preview MIME to video and audio. Generate/cache thumbnail, proxy or waveform as derivatives keyed by source hash and derivative version.
- [ ] **Step 4: Record explicit references.** On project materialization, transactionally create `library_project_references` with project/asset identity. Usage inspection also scans current editing session/variant and derived sequence references before deletion. Keep internal rollback cleanup separate from user deletion guard.
- [ ] **Step 5: Run GREEN and commit.** Repeat the Step 2 command, run `git diff --check`, then commit `feat: expose safe personal library lifecycle`.

### Task 4: Connect automatic semantic indexing

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/library_audio_indexer.py`
- Modify: `packages/core-engine/src/videobox_core_engine/library_footage_indexer.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/media_library_store.py`
- Test: `tests/test_library_audio_indexer.py`
- Test: `tests/test_library_footage_indexer.py`
- Test: `tests/test_api_library_audio_search.py`

- [ ] **Step 1: Add failing tests.** New ready user assets must appear in pending index queries, content-renamed duplicates must not reanalyse, unavailable LM Studio must preserve measurements and pending embedding, and user-confirmed tags must survive reindex.
- [ ] **Step 2: Run RED.** Run `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_library_audio_indexer.py tests/test_library_footage_indexer.py tests/test_library_audio_index.py tests/test_api_library_audio_search.py -q`.
- [ ] **Step 3: Extend indexers by asset identity.** Link descriptors to `library_asset_id` plus content hash; keep `DESCRIPTION_VERSION`/`FOOTAGE_DESCRIPTION_VERSION`. Write machine description separately from user metadata. Use the existing Korean vision prompt and bounded maintenance batches.
- [ ] **Step 4: Run GREEN and commit.** Repeat the Step 2 command, run `git diff --check`, then commit `feat: index personal media for semantic search`.

### Task 5: Build the bounded desktop library UI

**Files:**
- Create: `apps/web/src/features/library/LibraryPage.tsx`
- Create: `apps/web/src/features/library/LibrarySidebar.tsx`
- Create: `apps/web/src/features/library/LibraryResults.tsx`
- Create: `apps/web/src/features/library/VideoAssetGrid.tsx`
- Create: `apps/web/src/features/library/AudioAssetRows.tsx`
- Create: `apps/web/src/features/library/LibraryPreviewPane.tsx`
- Create: `apps/web/src/features/library/AssetIngestDropzone.tsx`
- Create: `apps/web/src/features/library/IngestJobTable.tsx`
- Create: `apps/web/src/features/library/library.css`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/app/AppRouter.tsx`
- Test: `apps/web/src/features/library/LibraryPage.test.tsx`

- [ ] **Step 1: Write failing UI tests.** Assert three-pane layout, video grid, music/SFX waveform rows, 24-row bounded page, keyboard tabs, drop of mixed files, partial failure reconciliation, search reason, preview, usage blocker, trash/restore and a single primary action.
- [ ] **Step 2: Run RED.** `npm --prefix apps/web test -- src/features/library/LibraryPage.test.tsx`; expected missing components/client methods.
- [ ] **Step 3: Add typed client contracts.** Define `LibraryAsset`, `LibraryIngestBatch`, `LibraryUsage`, `LibrarySearchMatch`, and API methods matching Task 3. Use AbortController/epoch fences so a stale request from a previous filter cannot overwrite current results.
- [ ] **Step 4: Implement views.** Keep the shell fixed; only center results scroll. Video cards show thumbnail/duration/orientation/status. Audio rows show waveform, name, duration, play/favorite. Right pane owns full preview, metadata, provenance, usage and safe actions.
- [ ] **Step 5: Implement drag/drop reconciliation.** Dropping never immediately claims success. Show item states, reload authoritative batch after network loss, retry failed items only, and display duplicates as existing assets.
- [ ] **Step 6: Run GREEN/build and commit.** Run `npm --prefix apps/web test -- src/features/library/LibraryPage.test.tsx` and `npm --prefix apps/web run build`; commit `feat: add bounded personal media library workspace`.

### Task 5A: Extend the verified starter pack with usable B-roll

**Files:**
- Modify: `docs/starter-media-pack-license-research.ko.md`
- Modify: `scripts/build_starter_media_pack.py`
- Generate for verification only: `dist/starter-media-pack/manifest.json`
- Modify: `tests/test_build_starter_media_pack.py`
- Modify: `tests/test_starter_media_pack_release.py`

- [ ] **Step 1: Add failing release tests.** Require a small nonzero `broll` set with source page, creator, exact download, commercial/raw redistribution/conversion decisions, evidence hash, asset hash, FFprobe dimensions/duration and previewability. Reject repository-level code licenses as media evidence.
- [ ] **Step 2: Run RED.** Run `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_build_starter_media_pack.py tests/test_starter_media_pack_release.py -q`; expected FAIL because the current approved set has music/SFX but no B-roll.
- [ ] **Step 3: Research and pin only redistributable media.** Add individual CC0 or equivalently explicit raw-redistribution evidence to the ledger. Pexels/Pixabay/Mixkit-style personal-use downloads must not enter the distributable pack; they remain owner-import candidates.
- [ ] **Step 4: Extend the builder.** Download/build only pinned files, verify evidence and asset hashes, probe video streams, produce thumbnails and index rows, and fail closed on changed bytes or unavailable evidence.
- [ ] **Step 5: Run GREEN and commit.** Repeat the Step 2 command and run `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_real_starter_media_pack_e2e.py -q`; commit `feat: add verified starter broll pack`.

### Task 6: Preserve project asset workflow through references

**Files:**
- Modify: `apps/web/src/features/media/MediaWorkspacePage.tsx`
- Modify: `apps/web/src/features/media/MediaLibraryBrowser.tsx`
- Modify: `apps/web/src/features/media/MediaWorkspacePage.test.tsx`
- Modify: `apps/web/src/features/media/MediaLibraryBrowser.test.tsx`

- [ ] **Step 1: Add failing tests.** Project screen must separate `프로젝트 자산`, `라이브러리에서 찾기`, `새 파일 추가`, `촬영본 가져오기`; `프로젝트에서 빼기` must not trash the global asset.
- [ ] **Step 2: Run RED.** Run `npm --prefix apps/web test -- src/features/media/MediaWorkspacePage.test.tsx src/features/media/MediaLibraryBrowser.test.tsx`.
- [ ] **Step 3: Convert old browsers to adapters.** Reuse the global library search/preview components and project materialize API. Preserve project-scoped favorite/recent behavior. Do not duplicate library state inside `MediaWorkspacePage`.
- [ ] **Step 4: Run GREEN and commit.** Repeat the Step 2 command, run `npm --prefix apps/web run build`, then commit `feat: connect projects to personal media references`.

### Task 7: Wave 1 browser and failure gate

- [ ] Use owner-ready Start/Rebuild and Check; open `/library` in the real browser.
- [ ] Drop one B-roll, one music and one SFX file plus one duplicate and one invalid file. Verify originals remain byte-identical, partial failure is visible, all valid assets preview, and semantic search finds each type.
- [ ] Materialize one asset into a project, prove permanent delete is blocked with a navigable usage location, remove the project reference, trash, restore, then explicitly delete an unused QA asset.
- [ ] Verify 1000 synthetic response rows remain within the center pane without page growth; do not persist synthetic data to owner runtime.
- [ ] Run `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_library_user_asset_store.py tests/test_library_ingest.py tests/test_api_library_assets.py tests/test_library_audio_indexer.py tests/test_library_footage_indexer.py -q`, `npm --prefix apps/web test -- src/features/library/LibraryPage.test.tsx src/features/media/MediaWorkspacePage.test.tsx`, `npm --prefix apps/web run build`, and `npm --prefix apps/web run test:e2e`. Perform read-only code review, gap table for design §6/§12/§13, and reverse checks for retry and restore.
