# Personal Voice TTS Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely verify and hand off personal-voice TTS candidates while keeping real-user listening approval explicit.

**Architecture:** Add a small TTS acceptance value object and store it with per-segment candidates. The local pipeline owns deterministic media validation; API and UI surface persisted state; existing review/output paths remain the only application path.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, SQLite, FFmpeg/ffprobe, React/Vitest.

---

### Task 1: Persist TTS candidate acceptance

**Files:**
- Create: `packages/core-engine/src/videobox_core_engine/tts_acceptance.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/sqlite_schema.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Test: `tests/test_tts_acceptance.py`
- Test: `tests/test_local_project_store.py`

- [ ] Write tests for rejected silent audio and accepted audio with `operator_review_status == "pending"`.
- [ ] Run `& .\.venv\Scripts\python.exe -m pytest tests/test_tts_acceptance.py tests/test_local_project_store.py -q -k "tts or acceptance"` and verify RED because the acceptance API and database fields do not exist.
- [ ] Implement `TtsAcceptance(technical_status, operator_review_status, target_duration_sec, actual_duration_sec, failure_code)` and migration-safe `tts_candidates` persistence.
- [ ] Re-run the exact tests for GREEN.
- [ ] Commit: `git commit -m "feat: persist tts candidate acceptance"`.

### Task 2: Gate synthesis without generic-voice fallback

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
- Modify: `packages/provider-interfaces/src/videobox_provider_interfaces/tts.py`
- Test: `tests/test_local_pipeline_tts_candidate.py`
- Test: `tests/test_tts_providers.py`

- [ ] Write a failing test where a provider exception creates no candidate and preserves the existing editing selection, plus a duration-mismatch rejection test.
- [ ] Run `& .\.venv\Scripts\python.exe -m pytest tests/test_local_pipeline_tts_candidate.py -q -k "failed_provider or duration_mismatch"` and verify RED.
- [ ] Add the requested target duration to `TTSRequest`, measure output with FFmpeg/ffprobe, reject invalid media, and raise a domain error that explicitly says original narration remains selected. Do not invoke gTTS as fallback.
- [ ] Re-run `& .\.venv\Scripts\python.exe -m pytest tests/test_local_pipeline_tts_candidate.py tests/test_tts_providers.py -q` for GREEN.
- [ ] Commit: `git commit -m "fix: gate personal voice tts candidates"`.

### Task 3: Surface candidate acceptance in API and UI

**Files:**
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `services/api/src/videobox_api/routers/assets.py`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/App.tsx`
- Test: `tests/test_api_tts_candidate_endpoint.py`
- Test: `apps/web/src/app.test.tsx`

- [ ] Write RED API assertions for `technical_status` and `operator_review_status`, and a RED UI assertion that a rejected candidate cannot populate the editing draft.
- [ ] Run `& .\.venv\Scripts\python.exe -m pytest tests/test_api_tts_candidate_endpoint.py -q -k "pending_operator_review"` and `Push-Location apps\web; npm test -- --run src/app.test.tsx -t "does not copy a rejected TTS candidate"; Pop-Location`.
- [ ] Return the candidate record from generation, show `기술 검증 통과 · 청취 승인 대기` for accepted candidates, show the rejection reason for failed candidates, and disable failed-candidate use.
- [ ] Re-run the same tests for GREEN, then commit: `git commit -m "feat: show personal voice tts acceptance"`.

### Task 4: Extend Korean FFmpeg/CapCut acceptance smoke and close out

**Files:**
- Modify: `scripts/verify-production-readiness-smoke.py`
- Modify: `tests/test_production_readiness_smoke_script.py`
- Modify: `docs/implementation-plan.ko.md`
- Modify: `docs/development-status-2026-06-29.ko.md`
- Create: `docs/handoffs/2026-07-12-personal-voice-tts-acceptance.ko.md`

- [ ] Write a RED smoke test asserting accepted TTS is pending listening review before approval and persists through final MP4 and CapCut draft after the existing output review.
- [ ] Run `& .\.venv\Scripts\python.exe -m pytest tests/test_production_readiness_smoke_script.py -q` and verify RED.
- [ ] Use the deterministic Korean WAV provider and the existing ten-minute narration fixture to run candidate generation, selection, regeneration, review, SRT, final render, and real CapCut draft export.
- [ ] Run focused tests, `Push-Location apps\web; npm test -- --run; npm run build; Pop-Location`, full `& .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`, and the real smoke command.
- [ ] Update SSOT/handoff, run `git diff --check` and `git status --short --branch`, then commit and push.

## Self-review

- Coverage: tasks 1-3 implement every persistence, fallback, duration, review, and UI requirement; task 4 proves SRT/final/CapCut handoff with the required real FFmpeg smoke.
- Scope: no provider vendoring, no generic fallback, no unrelated editor redesign.
- Consistency: accepted candidates remain pending human listening review; only the existing review flow applies them to output.
