# TTS Listening Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a human listening decision an explicit, persisted prerequisite for using a personal-voice TTS candidate.

**Architecture:** Keep technical acceptance and operator listening review separate in `tts_candidates`. A candidate-level API mutates only `pending` candidates to `approved` or `rejected`; the existing editing-session TTS selection validates that decision and candidate identity before storing a replacement.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, SQLite, React/Vitest, FFmpeg smoke.

---

### Task 1: Candidate review persistence and API

**Files:**
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Modify: `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `services/api/src/videobox_api/orchestration.py`
- Modify: `services/api/src/videobox_api/routers/assets.py`
- Test: `tests/test_api_tts_candidate_endpoint.py`

- [ ] Write failing tests for approved/rejected persistence and rejecting technical-failure candidates.
- [ ] Add a candidate lookup/update operation and candidate-level `PATCH` review endpoint.
- [ ] Verify focused tests are green.

### Task 2: Gate editing-session selection and UI

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/editing_session_and_regeneration.py`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/App.tsx`
- Test: `tests/test_editing_session.py`
- Test: `apps/web/src/app.test.tsx`

- [ ] Write failing contracts proving pending/rejected candidate selection preserves existing narration.
- [ ] Validate candidate ID, asset ID, segment ID, technical acceptance, and listening approval before selection.
- [ ] Add approve/reject buttons with persisted reload state and failure recovery.

### Task 3: Output acceptance and closeout

**Files:**
- Modify: `scripts/verify-production-readiness-smoke.py`
- Modify: `tests/test_production_readiness_smoke_script.py`
- Modify: SSOT status and handoff docs

- [ ] Require listening approval in deterministic 600-second smoke before replacement/output.
- [ ] Run frontend/backend full regressions, smoke, diff/status, then commit and push.
