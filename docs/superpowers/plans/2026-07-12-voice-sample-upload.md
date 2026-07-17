# Voice Sample Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add browser file upload for personal voice samples without replacing the compatible local-path registration route.

**Architecture:** FastAPI receives one multipart file, validates a small audio extension allowlist, stages it inside the project, then delegates to the existing voice-sample asset registration service. React sends `FormData`, surfaces recovery state, and continues using the returned asset ID for TTS candidates.

**Tech Stack:** Python 3.12, FastAPI/TestClient, SQLite local store, React/Vitest.

---

### Task 1: Upload API contract

**Files:**
- Modify: `services/api/src/videobox_api/routers/assets.py`
- Test: `tests/test_api.py`

- [ ] Write a TestClient multipart upload test asserting a WAV becomes a `voice_sample_audio` asset and a zero-byte file is rejected.
- [ ] Run the test and verify RED because the upload route is absent.
- [ ] Stage the uploaded bytes under a project-owned temporary path, call `register_voice_sample_asset`, and always delete the staged file.
- [ ] Re-run the focused test for GREEN.

### Task 2: Browser picker and recovery

**Files:**
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/App.tsx`
- Test: `apps/web/src/app.test.tsx`

- [ ] Write a failing UI test for file selection, upload request, returned asset-ID propagation, error recovery, and a refreshed session retaining the usable ID field.
- [ ] Implement `FormData` upload and a file input while retaining the path input fallback.
- [ ] Re-run frontend focused and full tests for GREEN.

### Task 3: Acceptance and closeout

**Files:**
- Modify: `scripts/verify-production-readiness-smoke.py`
- Modify: `tests/test_production_readiness_smoke_script.py`
- Modify: SSOT status and handoff docs

- [ ] Add deterministic smoke coverage that uses the upload endpoint for the voice sample before generating the pending-listening TTS candidate.
- [ ] Run focused tests, 600-second Korean smoke, frontend/backend full regressions, then update SSOT and push.
