# VideoBox Task 18 Caption Time Authority Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make narration bounds the only caption-time authority, carry saved caption text through materialization, and prevent draft loss while a caption save is in flight.

**Architecture:** The core placement contract accepts only independently placeable media. It ignores historical caption overrides at materialization, so every output consumer receives narration-derived caption bounds; the revisioned caption command also synchronizes the matching durable content window text. The transcript UI receives the existing route saving state and cannot change its pending draft or selection until the authoritative refresh finishes.

**Tech Stack:** Python 3.12 core engine and pytest; TypeScript, React 19, Vitest.

---

### Task 1: Retire caption placement timing while preserving legacy sessions

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/timeline_placements.py`
- Modify: `tests/test_timeline_placements.py`
- Test: `tests/test_editor_view_model_api.py`

- [x] **Step 1: Write RED tests for legacy and new caption changes.**

```python
def test_legacy_caption_override_is_ignored_by_materialization() -> None:
    result = apply_timeline_placement_overrides(
        timeline={"tracks": [], "session_captions": [{"caption_id": "c-1", "segment_id": "seg-1", "start_sec": 0.0, "end_sec": 2.0}]},
        overrides={"caption:c-1": {"placement_id": "caption:c-1", "kind": "caption", "start_sec": 1.0, "end_sec": 2.0}},
    )
    assert result["session_captions"][0]["start_sec"] == 0.0

def test_caption_change_is_unknown_to_the_independent_placement_contract() -> None:
    with pytest.raises(ValueError, match="timeline_placement_unknown"):
        apply_placement_changes(placements=collect_timeline_placements(timeline=_timeline()), changes=[{"placement_id": "caption:c-1", "kind": "caption", "start_sec": 0.0, "end_sec": 1.0}], output_duration_sec=3, fps_num=30, fps_den=1)
```

- [x] **Step 2: Run RED.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_timeline_placements.py tests/test_editor_view_model_api.py`

Expected: failure because captions are still collected and their override is applied.

- [x] **Step 3: Implement the smallest core authority change.**

```python
PLACEMENT_KINDS = frozenset({"broll", "bgm", "sfx", "overlay", "caption"})
MUTABLE_PLACEMENT_KINDS = PLACEMENT_KINDS - {"caption"}

# Keep caption identity valid for the manifest, but do not collect
# session_captions as mutable placements. Before validating overrides, retain
# only non-caption legacy keys; those keys are intentionally inert on read.
active_overrides = {key: value for key, value in overrides.items() if not key.startswith("caption:")}
```

Use `active_overrides` for validation and track/overlay application. Keep caption payload and its generated start/end values untouched.

- [x] **Step 4: Run GREEN.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_timeline_placements.py tests/test_editor_view_model_api.py`

Expected: PASS. Do not run the full Python suite.

### Task 2: Lock every transcript edit control while the route saves

**Files:**
- Modify: `apps/web/src/features/editor/transcript/TranscriptPanel.tsx`
- Modify: `apps/web/src/features/editor/transcript/TranscriptPanel.test.tsx`
- Test: `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`

- [x] **Step 1: Write RED component coverage.**

```tsx
it("locks caption text and transcript navigation while a save is pending", () => {
  render(<TranscriptPanel entries={entries} playbackSec={0} selectedSegmentId="seg-1" isSaving onSaveCaption={vi.fn()} onSeek={vi.fn()} onSelectSegment={vi.fn()} />);
  expect(screen.getByRole("textbox", { name: "seg-1 자막 텍스트" })).toBeDisabled();
  expect(screen.getByRole("button", { name: /대본 선택/ })).toBeDisabled();
});
```

- [x] **Step 2: Run RED.**

Run: `npm --prefix apps/web run test -- --run src/features/editor/transcript/TranscriptPanel.test.tsx`

Expected: failure because only the save button is disabled.

- [x] **Step 3: Add the minimal disabled props.**

```tsx
<button disabled={isSaving} ... />
<textarea disabled={isSaving} ... />
```

Keep the IME guard and the existing revision-bound route mutation unchanged.

- [x] **Step 4: Run GREEN.**

Run: `npm --prefix apps/web run test -- --run src/features/editor/transcript/TranscriptPanel.test.tsx src/features/editor/workbench/editor-workbench-route.test.tsx`

Expected: PASS.

### Task 3: Close the repaired Task 18 contract

**Files:**
- Modify: `docs/development-status-2026-06-29.ko.md`
- Modify: `docs/superpowers/plans/2026-07-22-videobox-task18-caption-authority-repair.md`
- Create: `docs/handoffs/2026-07-23-videobox-task18-caption-authority-repair-closeout.ko.md`

- [x] **Step 1: Re-run affected tests and UI boundary checks.**

Run:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_timeline_placements.py tests/test_editor_view_model_api.py
npm --prefix apps/web run test -- --run src/features/editor/transcript src/features/editor/preview/preview-stage.test.tsx src/features/editor/timeline/timeline-dock.test.tsx src/features/editor/workbench/editor-workbench.test.tsx src/features/editor/workbench/editor-workbench-route.test.tsx
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-editor-ui-source-provenance.ps1
git diff --check
```

Expected: all selected tests and verifier pass. No full Python regression.

- [x] **Step 2: Perform independent spec/gap and source-to-runtime reverse reviews.**

Verify the source route refuses new caption changes; persisted `caption:*` overrides cannot change materialized preview/output/manifest times; panel controls cannot mutate draft during a pending request; text still reaches the existing revision-bound caption endpoint.

- [x] **Step 3: Run full frontend attempt and production build.**

Run:

```powershell
npm --prefix apps/web test
npm --prefix apps/web run build
```

Expected: pass, with only already-known non-failing warnings if emitted.

- [x] **Step 4: Update status and handoff, then commit and push.**

Record the legacy-override policy, exact commands/results, protected `.tmp-final-fence-debug/` status, Task 9 cumulative 9/22 (40.9%), and that Task 19 still needs its own written spec/approval before implementation.

## Plan self-review

Task 1 covers both historical and future timing paths; Task 2 prevents the identified user-visible draft loss; Task 3 verifies the repair boundary; Task 4 closes the persisted caption-text path through materialization and manifest. The only historical timing change is semantic read normalization, not a hidden session mutation.

### Task 4: Synchronize persisted caption text with materialized content windows

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/editing_session.py`
- Modify: `tests/test_editing_session.py`
- Modify: `tests/test_editor_view_model_api.py`

- [x] **Step 1: Write RED core and API regressions.**

```python
def test_caption_update_changes_the_matching_materialized_content_window() -> None:
    session = build_editing_session(...)
    updated = update_segment_caption(session=session, segment_id="seg-1", caption_text="after")
    materialized = materialize_editing_session_timeline(timeline=timeline, editing_session=updated)
    assert materialized["session_captions"][0]["caption_text"] == "after"

def test_caption_patch_reappears_in_the_authoritative_manifest(tmp_path) -> None:
    saved = client.patch(..., json={"caption_text": "after", "expected_revision": 1})
    assert saved.status_code == 200
    assert client.get(...).json()["captions"][0]["text"] == "after"
```

Add a merged-window case: editing `right` updates only the window where `source_segment_id == "right"` and preserves the `left` window.

- [x] **Step 2: Run RED.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_editing_session.py tests/test_editor_view_model_api.py`

Observed: the regular materialized and API→manifest assertions returned stale text; the merged-child assertion raised `KeyError` because only a top-level segment ID was searched. This demonstrated the missing `content_windows[].source_segment_id` write path.

- [x] **Step 3: Implement one revisioned window synchronization.**

```python
matched = False
for segment in updated.get("segments", []):
    if str(segment.get("segment_id")) == segment_id:
        segment["caption_text"] = normalized_caption
        matched = True
    for window in segment.get("content_windows", []) if isinstance(segment.get("content_windows"), list) else []:
        if isinstance(window, dict) and str(window.get("source_segment_id") or segment.get("segment_id")) == segment_id:
            window["caption_text"] = normalized_caption
            matched = True
if matched:
    return _apply_manual_mutation(...)
raise KeyError(...)
```

Do not rewrite unrelated content windows, materializer, output code, or API contracts.

- [x] **Step 4: Run GREEN.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_editing_session.py tests/test_editor_view_model_api.py`

Observed: `62 passed` with only the existing Starlette multipart PendingDeprecationWarning. Do not run the full Python suite.
