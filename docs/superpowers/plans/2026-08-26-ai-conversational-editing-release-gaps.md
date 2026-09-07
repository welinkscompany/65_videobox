# Conversational Editing Release Gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a creator preview the materialized result of a typed AI candidate before any saved mutation, then close proposal asset/currentness and clarification gaps.

**Architecture:** Candidate preview is a read-only render input, fingerprinted separately from a saved editing session. The service loads and preflights the durable proposal, applies its operations to a deep copy, materializes that copy, and publishes only a proposal-preview artifact. Apply remains the only route that saves or writes undo history.

**Tech Stack:** FastAPI, Pydantic, LocalProjectStore/LocalPipelineRunner, FFmpeg, React/TypeScript, pytest, Playwright.

---

### Task 1: Shared no-history proposal projection

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/editing_session.py`
- Test: `tests/test_editor_timeline_mutations.py`

- [ ] **Step 1: RED test**

```python
def test_projecting_ai_editing_proposal_does_not_change_history_or_revision() -> None:
    projected = project_yujin_editing_proposal(session=_session(), proposal=_speed_proposal())
    assert projected["segments"][0]["end_sec"] == 2
    assert projected["undo_stack"] == []
    assert projected["session_revision"] == 1
```

- [ ] **Step 2: Verify RED**

Run: `.venv/Scripts/python.exe -m pytest tests/test_editor_timeline_mutations.py::test_projecting_ai_editing_proposal_does_not_change_history_or_revision -q`

Expected: fail because `project_yujin_editing_proposal` does not exist.

- [ ] **Step 3: GREEN implementation**

Extract the exact typed operation loop from `apply_yujin_editing_proposal` into one private pure helper. Add `project_yujin_editing_proposal`: deep-copy the session, apply that helper, and preserve revision, freshness, history, undo and redo. Make the apply path call the same helper within its existing one user transaction.

- [ ] **Step 4: Verify and commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_editor_timeline_mutations.py -q`

```powershell
git add packages/core-engine/src/videobox_core_engine/editing_session.py tests/test_editor_timeline_mutations.py
git commit -m "기능: 유진 편집안 읽기 전용 투영 추가"
```

### Task 2: Durable proposal-preview artifact

**Files:**
- Modify: `packages/storage-abstractions/src/videobox_storage/sqlite_schema.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Modify: `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
- Modify: proposal API route module
- Test: `tests/test_api_media_director.py`

- [ ] **Step 1: RED API contract**

```python
preview = client.post(f"{root}/yujin-editing-proposals/{proposal_id}/preview")
assert preview.status_code == 202
assert preview.json()["proposal_id"] == proposal_id
assert client.get(root).json()["undo_stack"] == []
```

- [ ] **Step 2: Verify RED**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api_media_director.py -k yujin_editing_proposal_preview -q`

Expected: 404 because the route does not exist.

- [ ] **Step 3: GREEN implementation**

Create proposal-preview records distinct from `exact_preview_renders`, keyed by proposal ID, source session revision and projected-timeline fingerprint. Load/preflight proposal, project via Task 1, materialize, render proposal-preview MP4, revalidate source revision and asset fingerprints before publishing, and expose status/content routes. The route returns 409 with creator recovery copy on stale input.

- [ ] **Step 4: Verify and commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api_media_director.py -k yujin_editing_proposal_preview -q`

### Task 3: Dialog integration without session mutation

**Files:**
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Test: `apps/web/src/api.test.ts`
- Test: `apps/web/e2e/editor-workbench.spec.mjs`

- [ ] **Step 1: RED browser contract**

```javascript
await dialog.getByRole("button", { name: "이 구간 미리보기" }).click();
await expect.poll(() => proposalPreviewBodies.length).toBe(1);
expect(selectedRangeBodies).toHaveLength(0);
```

- [ ] **Step 2: Verify RED**

Run: `npx playwright test e2e/editor-workbench.spec.mjs --grep "owned conversational-editing fixture"`

Expected: fail because it calls selected-range preview for the unmodified session.

- [ ] **Step 3: GREEN implementation and commit**

Add typed proposal-preview client/status polling. Surface the returned read-only video as `편집안 미리보기`; do not call selected-range, exact-preview, or mutation routes before apply.

### Task 4: Asset identity, clarification, and real-output QA

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py`
- Modify: proposal API route module and adapter
- Test: `tests/test_yujin_editing_command_evaluation.py`
- Test: `tests/test_api_media_director.py`

- [ ] **Step 1: RED checks**

Prove the model prompt contains approved asset stable ID/name/type; mutate an approved asset without a session revision and prove preview/apply return stale; prove clarification returns the model’s `reply_text`, not echoed instruction.

- [ ] **Step 2: GREEN implementation**

Persist/revalidate required asset ID, approved type, hash and revision at preview/preflight/apply. Pass bounded approved-asset catalogue into the strict prompt. Preserve `YujinEditingResponse.reply_text` for clarification/rejection.

- [ ] **Step 3: QA and closeout**

Use a local-only owned fixture with valid local MP4: candidate → proposal-preview MP4 → explicit apply → refresh → undo/redo → exact preview → review approval → final MP4. CapCut remains optional. Run full pytest, web unit/type checks, and both E2E specs; update handoff with automated/runtime/human gates.

