# CapCut Handoff Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register an immutable VideoBox real CapCut draft as a safe, directly openable Windows CapCut project and surface its persisted recovery state.

**Architecture:** Add a focused Windows handoff service that receives a source draft directory and discovers/validates the supported CapCut root. Persist only the resulting registration record under the existing CapCut export metadata, expose it through the current output API, and reuse the current export reload logic in the frontend.

**Tech Stack:** Python 3.12, pathlib/shutil, FastAPI/Pydantic, LocalProjectStore metadata JSON, React/TypeScript, Vitest, pytest.

---

### Task 1: Registration domain contract

**Files:**
- Create: `packages/core-engine/src/videobox_core_engine/capcut_handoff.py`
- Create: `tests/test_capcut_handoff.py`

- [x] Write failing tests for supported root discovery, missing executable/root, immutable source copy, idempotent reuse, incomplete collision cleanup, and temporary-copy rollback.
- [x] Run ` .venv\\Scripts\\python.exe -m pytest tests\\test_capcut_handoff.py -q` and confirm missing-module failure.
- [x] Implement `CapCutHandoffService.register(source_draft_path, export_id)` with `CapCutHandoffError`, `CapCutHandoffRecord`, injected local-app-data root, and injected copy function for deterministic rollback tests.
- [x] Re-run the focused test file and confirm green.

### Task 2: Persisted pipeline/API contract

**Files:**
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Modify: `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
- Modify: `services/api/src/videobox_api/orchestration.py`
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `services/api/src/videobox_api/routers/outputs.py`
- Modify: `tests/test_local_pipeline_capcut_draft_export.py`
- Modify: `tests/test_api_capcut_draft_export_endpoint.py`

- [x] Write RED contract tests for registration result persistence, null source artifact failure, API response fields, and deterministic `create_app` construction.
- [x] Add `update_capcut_draft_handoff` metadata merge/read support, pipeline/orchestrator registration methods, `POST /capcut-draft-exports/{job_id}/handoff`, and Pydantic response models.
- [x] Run the focused pipeline/API tests and confirm green.

### Task 3: Frontend readiness and recovery

**Files:**
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/app.test.tsx`
- Modify: `apps/web/src/styles.css`

- [x] Write RED UI tests for ready path, Korean failure/retry path, and reload recovery of the registered CapCut path.
- [x] Extend CapCut export types and API client, then render registration action/status beside the existing CapCut output card without replacing export artifact/error behavior.
- [x] Run the focused frontend tests and confirm green.

### Task 4: Real Windows CapCut proof and closeout

**Files:**
- Modify: `docs/implementation-plan.ko.md`
- Modify: `docs/development-status-2026-06-29.ko.md`

- [x] Generate/register a fresh loop draft through VideoBox; verify the registered path is not the source artifact and contains `draft_content.json`.
- [x] Open the registered project from CapCut Desktop and verify timeline visibility without a manual filesystem copy.
- [x] Run `.venv\\Scripts\\python.exe -m pytest -q`, `npm --prefix apps/web test`, and `npm --prefix apps/web run build`.
- [x] Update SSOT with supported path, recovery limitations, and live proof; run `git diff --check`, keep artifacts untracked, commit and push.
