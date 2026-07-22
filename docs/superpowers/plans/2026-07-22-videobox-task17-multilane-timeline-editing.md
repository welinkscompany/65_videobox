# VideoBox Task 17 Multi-lane Timeline Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add revision-safe independent placement editing for B-roll, BGM, SFX, overlay, and captions, including a multi-lane move, and materialize the same result into the editor, FFmpeg output, and CapCut draft.

**Architecture:** A pure placement module assigns stable IDs, validates/quantizes patches, and applies persisted overrides to a materialized timeline. One revisioned batch endpoint saves the overrides atomically. TimelineDock owns selection/drafts; the workbench route commits once and refreshes authoritative state.

**Tech Stack:** Python 3.11, FastAPI/Pydantic, LocalProjectStore CAS, React 19, TypeScript, Vitest, FFmpeg composition, PyCapCut.

---

### Task 1: Define placement identity and pure frame rules

**Files:**
- Create: `packages/core-engine/src/videobox_core_engine/timeline_placements.py`
- Create: `tests/test_timeline_placements.py`

- [ ] **Step 1: Add the failing contract tests.**

```python
from videobox_core_engine.timeline_placements import apply_placement_changes, collect_placements

def test_collects_each_media_clip_and_caption_by_stable_identity() -> None:
    placements = collect_placements(timeline=timeline(), session={"segments": []}, fps_num=30000, fps_den=1001)
    assert set(placements) == {"broll:b-1", "bgm:m-1", "sfx:s-1", "overlay:o-1", "caption:c-1"}

def test_batch_persistence_quantizes_but_rejects_out_of_range_values() -> None:
    result = apply_placement_changes(
        placements=placements(),
        changes=[
            {"placement_id": "broll:b-1", "kind": "broll", "start_sec": 0.01, "end_sec": 1.99},
            {"placement_id": "caption:c-1", "kind": "caption", "start_sec": 0.99, "end_sec": 2.99},
        ],
        output_duration_sec=3, fps_num=30, fps_den=1,
    )
    assert result["broll:b-1"]["start_sec"] == 0
    assert result["caption:c-1"]["end_sec"] == 3
```

Add separate exact failures for duplicate/unknown IDs, mismatched kind, non-finite values, empty changes, negative/out-of-output values, non-positive duration, one-frame violation, and input non-mutation.

- [ ] **Step 2: Run RED.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_timeline_placements.py`

Expected: FAIL because the module is absent.

- [ ] **Step 3: Implement the minimal pure contract.**

```python
PLACEMENT_KINDS = frozenset({"broll", "bgm", "sfx", "overlay", "caption"})

def placement_id(*, kind: str, base_id: str) -> str:
    if kind not in PLACEMENT_KINDS or not base_id.strip():
        raise ValueError("timeline_placement_identity_invalid")
    return f"{kind}:{base_id}"

def apply_placement_changes(*, placements, changes, output_duration_sec, fps_num, fps_den) -> dict[str, dict[str, object]]:
    """Return normalized override records without mutating the inputs."""
```

Use integer half-up frames and return values sorted by placement ID. This server-side helper validates a submitted final layout and rejects out-of-range values; only the later UI move helper clamps a shared draft delta.

- [ ] **Step 4: Run GREEN and commit.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_timeline_placements.py`

Expected: PASS.

```powershell
git add packages/core-engine/src/videobox_core_engine/timeline_placements.py tests/test_timeline_placements.py
git commit -m "feat: define timeline placement contract"
```

### Task 2: Persist a batch and materialize it once for all consumers

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/editing_session.py`
- Modify: `packages/core-engine/src/videobox_core_engine/editing_session_and_regeneration.py`
- Modify: `packages/core-engine/src/videobox_core_engine/composition_plan.py`
- Modify: `packages/core-engine/src/videobox_core_engine/editor_playback_manifest.py`
- Modify: `tests/test_editor_timeline_mutations.py`
- Modify: `tests/test_exact_preview_remediation.py`

- [ ] **Step 1: Add failing atomicity and parity tests.**

```python
updated = pipeline.update_editing_session_timeline_placements(
    project_id=project.project_id, session_id=session["session_id"], expected_revision=1,
    changes=[{"placement_id": "broll:b-1", "kind": "broll", "start_sec": 2, "end_sec": 4}],
)
assert updated["session_revision"] == 2
assert updated["segments"][0]["start_sec"] == 0
assert updated["timeline_placement_overrides"]["broll:b-1"]["start_sec"] == 2
```

Test every placement kind, a rejected multi-change batch with no revision change, legacy empty overrides, undo/redo restoration, and manifest/FFmpeg materialization retaining source SHA, revision, controls, warnings, overlay/caption payload, and persisted caption IDs across split/merge.

- [ ] **Step 2: Run RED.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_editor_timeline_mutations.py tests/test_exact_preview_remediation.py -k "placement"`

Expected: FAIL because the mutation and materialization do not exist.

- [ ] **Step 3: Store normalized overrides and apply them after current session construction.**

```python
def set_timeline_placement_overrides(*, session: dict[str, Any], overrides: dict[str, dict[str, object]]) -> dict[str, Any]:
    updated = deepcopy(session)
    updated["timeline_placement_overrides"] = deepcopy(overrides)
    return _record_undoable_mutation(
        before=session, updated=updated,
        mutation_type="timeline_placement_update", segment_id=",".join(sorted(overrides)),
    )
```

The pipeline loads session plus source timeline, calls Task 1 validation before one store CAS, and keeps the expected revision unchanged. At the end of `materialize_editing_session_timeline`, apply overrides to materialized tracks, export overlays, and `session_captions`. Make `build_editor_playback_manifest` use that materialized result rather than raw source timing.

- [ ] **Step 4: Run GREEN and commit.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_editor_timeline_mutations.py tests/test_exact_preview_remediation.py -k "placement"`

Expected: PASS.

```powershell
git add packages/core-engine/src/videobox_core_engine/editing_session.py packages/core-engine/src/videobox_core_engine/editing_session_and_regeneration.py packages/core-engine/src/videobox_core_engine/composition_plan.py packages/core-engine/src/videobox_core_engine/editor_playback_manifest.py tests/test_editor_timeline_mutations.py tests/test_exact_preview_remediation.py
git commit -m "feat: persist timeline placement overrides"
```

### Task 3: Add the typed revisioned endpoint and command port

**Files:**
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `services/api/src/videobox_api/routers/editing_session.py`
- Modify: `services/api/src/videobox_api/orchestration.py`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/features/editor/editorCommandPort.ts`
- Modify: `apps/web/src/features/editor/editorCommandPort.test.ts`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Add failing API and web payload tests.**

```python
response = client.patch(
    f"/api/projects/{project_id}/editing-sessions/{session_id}/timeline-placements",
    json={"expected_revision": 1, "changes": [{"placement_id": "sfx:s-1", "kind": "sfx", "start_sec": 1, "end_sec": 2}]},
)
assert response.status_code == 200
assert response.json()["session_revision"] == 2
```

```ts
await port.setTimelinePlacements({ changes: [{ placementId: "caption:seg-1", kind: "caption", startSec: 1, endSec: 2 }] });
expect(api.updateEditingSessionTimelinePlacements).toHaveBeenCalledWith("p", "s", {
  expected_revision: 7,
  changes: [{ placement_id: "caption:seg-1", kind: "caption", start_sec: 1, end_sec: 2 }],
});
```

Cover 409, schema rejection, duplicate placement IDs, and no persistent change on 422.

- [ ] **Step 2: Run RED.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_api.py -k "timeline_placement"`

Run: `npm --prefix apps/web test -- --run src/features/editor/editorCommandPort.test.ts -t "timeline placements"`

Expected: both FAIL because no endpoint or port method exists.

- [ ] **Step 3: Add the narrow request types, route, and one port method.**

```python
class TimelinePlacementChangeRequest(BaseModel):
    placement_id: str = Field(min_length=3)
    kind: Literal["broll", "bgm", "sfx", "overlay", "caption"]
    start_sec: float = Field(ge=0, allow_inf_nan=False)
    end_sec: float = Field(gt=0, allow_inf_nan=False)

class TimelinePlacementPatchRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    changes: list[TimelinePlacementChangeRequest] = Field(min_length=1)
```

Use existing conflict/422 handling. Name the TypeScript command `setTimelinePlacements`, map camelCase at the API edge only, and never make its expected revision optional.

- [ ] **Step 4: Run GREEN and commit.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_api.py -k "timeline_placement"`

Run: `npm --prefix apps/web test -- --run src/features/editor/editorCommandPort.test.ts`

Expected: PASS.

```powershell
git add services/api/src/videobox_api/models.py services/api/src/videobox_api/routers/editing_session.py services/api/src/videobox_api/orchestration.py apps/web/src/api.ts apps/web/src/features/editor/editorCommandPort.ts apps/web/src/features/editor/editorCommandPort.test.ts tests/test_api.py
git commit -m "feat: expose timeline placement mutation"
```

### Task 4: Project stable placement IDs and pure multi-selection drafts

**Files:**
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/features/editor/editorViewModel.ts`
- Create: `apps/web/src/features/editor/timeline/placementMutation.ts`
- Create: `apps/web/src/features/editor/timeline/placementMutation.test.ts`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Add failing manifest and helper tests.**

```ts
expect(derivePlacementMove({
  selected: [
    { placementId: "broll:b-1", kind: "broll", startSec: 1, endSec: 2 },
    { placementId: "caption:s-1", kind: "caption", startSec: 3, endSec: 4 },
  ],
  proposedDeltaSec: -2, durationSec: 10, fps: { num: 30, den: 1 },
})).toEqual([
  { placementId: "broll:b-1", kind: "broll", startSec: 0, endSec: 1 },
  { placementId: "caption:s-1", kind: "caption", startSec: 2, endSec: 3 },
]);
```

Also prove one-frame trim, no input mutation, and a placement ID on every non-narration manifest clip/caption.

- [ ] **Step 2: Run RED.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline/placementMutation.test.ts`

Expected: FAIL because helper/manifest field are absent.

- [ ] **Step 3: Add the narrow pure UI types.**

```ts
export type TimelinePlacement = Readonly<{
  placementId: string;
  kind: "broll" | "bgm" | "sfx" | "overlay" | "caption";
  startSec: number;
  endSec: number;
}>;
export function derivePlacementMove(input: Readonly<{ selected: readonly TimelinePlacement[]; proposedDeltaSec: number; durationSec: number; fps: RationalFps }>): TimelinePlacement[];
export function derivePlacementTrim(input: Readonly<{ placement: TimelinePlacement; edge: "start" | "end"; proposedSec: number; durationSec: number; fps: RationalFps }>): TimelinePlacement;
```

Use Task 14 time helpers only. Do not import React, DOM, API, or command-port modules.

- [ ] **Step 4: Run GREEN and commit.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline/placementMutation.test.ts`

Expected: PASS.

```powershell
git add services/api/src/videobox_api/models.py apps/web/src/api.ts apps/web/src/features/editor/editorViewModel.ts apps/web/src/features/editor/timeline/placementMutation.ts apps/web/src/features/editor/timeline/placementMutation.test.ts tests/test_api.py
git commit -m "feat: project timeline placement drafts"
```

### Task 5: Add accessible local multi-lane drafts to TimelineDock

**Files:**
- Modify: `apps/web/src/features/editor/timeline/TimelineDock.tsx`
- Modify: `apps/web/src/features/editor/timeline/timeline-dock.test.tsx`

- [ ] **Step 1: Add failing interaction tests.**

```tsx
fireEvent.click(timelineClipSelection("b-1"));
fireEvent.click(timelineClipSelection("caption:seg-1"), { shiftKey: true });
fireEvent.pointerDown(screen.getByRole("button", { name: "선택한 2개 항목 이동" }), { clientX: 100, pointerId: 7 });
fireEvent.pointerMove(screen.getByTestId("timeline-track"), { clientX: 130, pointerId: 7 });
expect(onSetTimelinePlacements).not.toHaveBeenCalled();
fireEvent.pointerUp(screen.getByTestId("timeline-track"), { clientX: 130, pointerId: 7 });
expect(onSetTimelinePlacements).toHaveBeenCalledTimes(1);
```

Cover every placement kind, one-item trim, Shift toggle, keyboard one-frame move/trim, saving disabled, pointer cancel/no-move, capture outside the control, no per-move request, and unchanged Task 16 narration behavior.

- [ ] **Step 2: Run RED.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline/timeline-dock.test.tsx -t "multi-lane"`

Expected: FAIL because placement selection/drafts are absent.

- [ ] **Step 3: Keep all selection and draft state local.**

```ts
type SetTimelinePlacements = Readonly<{ changes: readonly TimelinePlacement[] }>;
type Props = Readonly<{ onSetTimelinePlacements?: (input: SetTimelinePlacements) => void; /* existing props */ }>;
```

Use the existing stable track wrapper for pointer capture. Render native sibling controls, never nested buttons. Only release one changed batch on pointerup. Dock must not import `api` or `EditorCommandPort`.

- [ ] **Step 4: Run GREEN and commit.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline/timeline-dock.test.tsx`

Expected: PASS.

```powershell
git add apps/web/src/features/editor/timeline/TimelineDock.tsx apps/web/src/features/editor/timeline/timeline-dock.test.tsx
git commit -m "feat: edit multilane timeline placements"
```

### Task 6: Route one request and verify FFmpeg/CapCut parity

**Files:**
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbench.tsx`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Modify: `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`
- Modify: `tests/test_exact_preview_remediation.py`
- Modify: `tests/test_pycapcut_adapter.py`

- [ ] **Step 1: Add failing route/race/parity tests.**

```tsx
await dragSelectedPlacements();
await waitFor(() => expect(api.updateEditingSessionTimelinePlacements).toHaveBeenCalledWith(
  "project-a", "session-a", expect.objectContaining({ expected_revision: 1 }),
));
await waitFor(() => expect(loadManifest).toHaveBeenCalledTimes(2));
```

```python
assert capcut_track("broll")[0]["start_sec"] == 2.0
assert preview_plan.tracks["bgm"][0].start_sec == 2.0
```

Cover success, conflict, ordinary failure, no retry, A→B→A route race, and all five kinds without source identity drift.

- [ ] **Step 2: Run RED.**

Run: `npm --prefix apps/web test -- --run src/features/editor/workbench/editor-workbench-route.test.tsx -t "timeline placements"`

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_exact_preview_remediation.py tests/test_pycapcut_adapter.py -k "placement"`

Expected: FAIL because no callback/race/parity coverage exists.

- [ ] **Step 3: Reuse Task 16's route fence.**

```tsx
onSetTimelinePlacements={(input) => commitTimelineMutation((port) => port.setTimelinePlacements(input))}
```

Thread it through `EditorWorkbench`. Do not create a preview job; the Task 2 materialized timeline is the only timing source for preview/final/CapCut.

- [ ] **Step 4: Run GREEN and commit.**

Run: `npm --prefix apps/web test -- --run src/features/editor/workbench/editor-workbench-route.test.tsx`

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_exact_preview_remediation.py tests/test_pycapcut_adapter.py -k "placement"`

Expected: PASS.

```powershell
git add apps/web/src/features/editor/workbench/EditorWorkbench.tsx apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx tests/test_exact_preview_remediation.py tests/test_pycapcut_adapter.py
git commit -m "feat: commit multilane placement changes"
```

### Task 7: Review, verify, and close out

**Files:**
- Modify: `docs/development-status-2026-06-29.ko.md`
- Modify: `docs/implementation-plan.ko.md`
- Create: `docs/handoffs/2026-07-22-videobox-task17-multilane-timeline-editing-closeout.ko.md`

- [ ] **Step 1: Run focused suites and reviews.**

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_timeline_placements.py tests/test_editor_timeline_mutations.py tests/test_api.py -k "timeline_placement or placement"
npm --prefix apps/web test -- --run src/features/editor/timeline src/features/editor/workbench src/features/editor/editorCommandPort.test.ts
```

Expected: focused core/API/frontend suites pass; no Critical/Important issue remains in identity, atomicity, parity, exactly-once, race, or provenance review.

- [ ] **Step 2: Run closeout gates.**

```powershell
npm --prefix apps/web test
npm --prefix apps/web run build
.venv\Scripts\python.exe -m pytest -q tests/test_editor_ui_source_provenance.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-editor-ui-source-provenance.ps1
git diff --check
```

Do not run or claim the full Python regression.

- [ ] **Step 3: Update SSOT, handoff, commit, and push.**

Record exact evidence, remaining Task 9 human acceptance, protected `.tmp-final-fence-debug/` classification, and official cumulative progress **9/22 (40.9%)**, remaining **59.1%**.

```powershell
git add <Task-17-files-excluding-.tmp-final-fence-debug>
git commit -m "feat: enable multilane timeline editing"
git push origin codex/videobox-container-compatibility
```

## Plan self-review

- Spec coverage: Tasks 1–2 create the shared source-of-truth and output parity; Tasks 3–4 expose one typed path; Tasks 5–6 implement local gestures and revision-safe commit; Task 7 verifies and records completion.
- Scope: Task 17 changes independent placement only. It does not reuse narration bounds or add provider, preview-job, OpenCut-runtime, or external-network work.
- Type consistency: the one end-to-end vocabulary is `placement_id`/`placementId`, `changes`, `timeline_placement_overrides`, `setTimelinePlacements`, and the five fixed kinds.
