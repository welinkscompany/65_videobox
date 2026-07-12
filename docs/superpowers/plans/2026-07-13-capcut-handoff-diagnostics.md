# CapCut Handoff Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show deterministic, safe CapCut handoff readiness diagnostics before a user registers a draft.

**Architecture:** Extend the existing handoff domain service with a non-registering diagnostics record; expose it through the output router and use the current app reload lifecycle to render a separate CapCut connection card.

**Tech Stack:** Python 3.12, pathlib/tempfile, FastAPI/Pydantic, React/TypeScript, Vitest, pytest.

---

### Task 1: Domain diagnostics RED/GREEN

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/capcut_handoff.py`
- Modify: `tests/test_capcut_handoff.py`

- [x] Add failing tests for highest version selection, missing executable/root, denied write probe, and no project copy side effect.
- [x] Run `./.venv/Scripts/python.exe -m pytest tests/test_capcut_handoff.py -q` and capture expected missing `diagnose` failure.
- [x] Implement immutable `CapCutHandoffDiagnostics` and `CapCutHandoffService.diagnose()` with a transient write probe.
- [x] Re-run the focused domain test file green.

### Task 2: Diagnostics API RED/GREEN

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
- Modify: `services/api/src/videobox_api/orchestration.py`
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `services/api/src/videobox_api/routers/outputs.py`
- Modify: `tests/test_api_capcut_draft_export_endpoint.py`

- [x] Add an API contract test using injected fake `local_app_data` that expects the entire diagnostics shape and no LLM call.
- [x] Run the targeted API test and capture 404/red failure.
- [x] Add pipeline/orchestrator delegation, Pydantic response model, and `GET /api/capcut/handoff-diagnostics`.
- [x] Re-run focused API/domain tests green.

### Task 3: Output diagnostics UI RED/GREEN

**Files:**
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/app.test.tsx`

- [x] Add frontend RED tests for ready details, failed Korean recovery/retry, and reload restoration.
- [x] Run the selected tests and capture missing-card failure.
- [x] Add API type/client, app state refresh lifecycle, and Korean card.
- [x] Re-run selected UI tests green.

### Task 4: Live proof and closeout

**Files:**
- Modify: `docs/implementation-plan.ko.md`
- Modify: `docs/development-status-2026-06-29.ko.md`

- [x] Run current Windows diagnostics and record version/path/root/write result.
- [x] Run full `.venv\\Scripts\\python.exe -m pytest -q`, `npm --prefix apps/web test`, and `npm --prefix apps/web run build`.
- [x] Update SSOT, run `git diff --check`, leave `artifacts/` untracked, commit and push.
