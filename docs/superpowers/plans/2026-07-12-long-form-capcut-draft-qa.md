# Long-form CapCut Draft QA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce repeatable deterministic evidence for three 600-second VideoBox projects through ingest, editing, SRT, styled MP4 and real CapCut draft export without claiming CapCut desktop interaction.

**Architecture:** Keep the existing production-readiness smoke as the real API/FFmpeg/pycapcut integration harness. Add named fixture profiles that only vary deterministic media and editing-session controls, then add an aggregate runner that invokes all three profiles in isolated artifact roots and emits a compact evidence manifest. Persist CapCut compatibility warnings in export metadata so the aggregate check can verify the returned warning instead of inferring it from draft JSON.

**Tech Stack:** Python 3.12, FastAPI TestClient, LocalProjectStore, FFmpeg/ffprobe, pycapcut, PowerShell fast-path, pytest.

---

### Task 1: Fixture profile contract and RED tests

**Files:**
- Modify: `tests/test_production_readiness_smoke_script.py`
- Create: `tests/test_long_form_capcut_draft_qa_script.py`
- Create: `scripts/verify-long-form-capcut-draft-qa.py`

- [x] Write tests requiring exactly `loop`, `crop_pad_overlay`, and `audio_ducking` profiles; each profile must report fixture name, final SHA, SRT path, draft path, checks, and an explicit `desktop_capcut_opened: false` field.
- [x] Run the focused tests and observe missing-module/profile failures.
- [x] Add only the fixture profile value objects and aggregate runner API necessary for the tests.
- [x] Re-run focused tests and confirm green.

### Task 2: Real profile media/edit paths

**Files:**
- Modify: `scripts/verify-production-readiness-smoke.py`
- Modify: `tests/test_production_readiness_smoke_script.py`

- [x] Write RED integration-contract tests for crop/pad/trim+image/text overlay and BGM/SFX gain/fade/ducking profiles.
- [x] Extend the existing TestClient smoke path so each profile registers deterministic media, saves the required editing overrides, runs partial regeneration and approval, then validates timeline/draft JSON rather than synthetic marker values.
- [x] Verify each profile returns SRT, styled MP4 SHA, real `draft_content.json`, exact-duration proof and only its expected media-control checks.
- [x] Run focused smoke tests green.

### Task 3: Persist CapCut compatibility warnings

**Files:**
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Modify: `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
- Modify: `tests/test_local_pipeline_capcut_draft_export.py`

- [x] Write a RED test proving a real draft export with ducking returns the adapter warning through the persisted export result after temporary export cleanup.
- [x] Add `notes` metadata to CapCut draft persistence and propagate `CapCutDraftExportResult.capcut_compatibility_warnings` without changing generic legacy export behavior.
- [x] Run the focused storage/pipeline test green.

### Task 4: Fast-path, SSOT, and release evidence

**Files:**
- Modify: `scripts/dev-fast-path.ps1`
- Modify: `tests/test_dev_fast_path.py`
- Modify: `docs/implementation-plan.ko.md`
- Modify: `docs/development-status-2026-06-29.ko.md`

- [x] Write RED test for a `long-form-capcut-qa` fast-path mode.
- [x] Add the mode, require/generate the existing 600-second Korean fixture, and write artifacts under `artifacts/long-form-capcut-qa/`.
- [x] Run all three profiles, record paths/SHA/warnings in SSOT, and state that desktop CapCut open/edit/export remains manual QA.
- [x] Run `.venv\\Scripts\\python.exe -m pytest -q`, `npm --prefix apps/web test`, `npm --prefix apps/web run build`, and `./scripts/dev-fast-path.ps1 -Mode long-form-capcut-qa`.
- [x] Run `git diff --check` and `git status --short`; do not stage `artifacts/`; commit and push the code/docs only.
