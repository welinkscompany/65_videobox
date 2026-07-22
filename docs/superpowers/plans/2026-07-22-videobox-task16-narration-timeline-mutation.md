# VideoBox Task 16 Narration Timeline Mutation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Commit frame-safe narration trim and drag reorder from TimelineDock through the existing revisioned editing-session commands.

**Architecture:** Keep pointer drafts local to TimelineDock and expose two narrow mutation callbacks. EditorWorkbenchRoute creates the current-revision command port, commits only release-time requests, then refreshes its manifest for success, conflict, and failure. The command port carries a complete reorder layout instead of silently omitting required bounds.

**Tech Stack:** React 19, TypeScript, Vitest, existing `EditorCommandPort`, Task 14 time-scale helpers, Vite.

---

### Task 1: Repair the typed narration reorder contract

**Files:**
- Modify: `apps/web/src/features/editor/editorCommandPort.ts`
- Modify: `apps/web/src/features/editor/editorCommandPort.test.ts`

- [ ] **Step 1: Add a failing complete-layout test.**

```ts
await port.reorderNarration({
  segmentIds: ["right", "left"],
  boundsById: { right: { startSec: 0, endSec: 2 }, left: { startSec: 2, endSec: 4 } },
});
expect(api.reorderEditingSessionSegments).toHaveBeenCalledWith("p", "s", {
  expected_revision: 7,
  segment_ids: ["right", "left"],
  bounds_by_id: { right: { start_sec: 0, end_sec: 2 }, left: { start_sec: 2, end_sec: 4 } },
});
```

- [ ] **Step 2: Run RED.**

Run: `npm --prefix apps/web test -- --run src/features/editor/editorCommandPort.test.ts -t "complete layout"`

Expected: FAIL because `reorderNarration` has no `boundsById` input or payload.

- [ ] **Step 3: Forward the complete typed layout.**

```ts
reorderNarration(input: { segmentIds: string[]; boundsById: Record<string, { startSec: number; endSec: number }> }): Promise<EditingSession>;
// map each entry to { start_sec, end_sec } and call the existing endpoint with revise
```

- [ ] **Step 4: Run GREEN.**

Run: `npm --prefix apps/web test -- --run src/features/editor/editorCommandPort.test.ts`

Expected: PASS.

### Task 2: Add pure narration drag-draft helpers

**Files:**
- Create: `apps/web/src/features/editor/timeline/narrationMutation.ts`
- Create: `apps/web/src/features/editor/timeline/narrationMutation.test.ts`

- [ ] **Step 1: Write failing frame/clamp/reorder tests.**

```ts
expect(deriveNarrationTrim({ clip, edge: "start", proposedSec: 0.01, narration, fps })).toEqual({ startSec: frameToSeconds(1, fps), endSec: 2 });
expect(reorderNarrationLayout({ narration, movingId: "right", targetIndex: 0 })).toEqual({
  segmentIds: ["right", "left"],
  boundsById: { right: { startSec: 0, endSec: 2 }, left: { startSec: 2, endSec: 4 } },
});
```

Also cover adjacent-bound clamp, one-frame minimum, invalid/unknown IDs, and frozen input.

- [ ] **Step 2: Run RED.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline/narrationMutation.test.ts`

Expected: FAIL because the helper module is absent.

- [ ] **Step 3: Implement pure, immutable helpers.**

Use only `secondsToFrameHalfUp` and `frameToSeconds` from `time-scale`; sort a copied narration list by start time/ID, clamp a trim to neighbour bounds, and generate contiguous reorder bounds from the earliest start.

- [ ] **Step 4: Run GREEN.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline/narrationMutation.test.ts`

Expected: PASS.

### Task 3: Render local trim/reorder drafts and commit exactly once

**Files:**
- Modify: `apps/web/src/features/editor/timeline/TimelineDock.tsx`
- Modify: `apps/web/src/features/editor/timeline/timeline-dock.test.tsx`

- [ ] **Step 1: Write failing interaction tests.**

```tsx
fireEvent.pointerDown(screen.getByRole("button", { name: "n-1 시작 자르기" }), { clientX: 100, pointerId: 1 });
fireEvent.pointerMove(screen.getByRole("button", { name: "n-1 시작 자르기" }), { clientX: 150, pointerId: 1 });
expect(onTrimNarration).not.toHaveBeenCalled();
fireEvent.pointerUp(screen.getByRole("button", { name: "n-1 시작 자르기" }), { clientX: 150, pointerId: 1 });
expect(onTrimNarration).toHaveBeenCalledTimes(1);
```

Cover end trim, cancel, narration-only controls, body drag reorder, disabled saving state, and preserved click/keyboard navigation.

- [ ] **Step 2: Run RED.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline/timeline-dock.test.tsx -t "commits trim once"`

Expected: FAIL because controls and callbacks are absent.

- [ ] **Step 3: Implement local pointer drafts only.**

Add `onTrimNarration`, `onReorderNarration`, `isSaving`, and `mutationMessage` props. Render narration-only handles/body drag target, use pointer capture, and pass a pure draft result only from `pointerup`. Do not import `api` or `EditorCommandPort`, and never call a mutation from `pointermove`.

- [ ] **Step 4: Run GREEN.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline/timeline-dock.test.tsx`

Expected: PASS.

### Task 4: Wire revisioned callbacks and close out

**Files:**
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbench.tsx`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Modify: `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`
- Modify: `docs/development-status-2026-06-29.ko.md`
- Create: `docs/handoffs/2026-07-22-videobox-task16-narration-timeline-mutation-closeout.ko.md`

- [ ] **Step 1: Write failing route tests.**

```tsx
await user.pointer([{ target: trimHandle, keys: "[MouseLeft>]" }, { target: trimHandle }, { keys: "[/MouseLeft]" }]);
expect(api.updateEditingSessionSegmentBounds).toHaveBeenCalledWith("project-a", "session-a", "n-1", expect.objectContaining({ expected_revision: 1 }));
await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
```

Also make a revision-conflict rejection refresh the manifest and show a retry message without a second mutation.

- [ ] **Step 2: Run RED.**

Run: `npm --prefix apps/web test -- --run src/features/editor/workbench/editor-workbench-route.test.tsx -t "refreshes after narration trim"`

Expected: FAIL because no mutation callbacks are wired.

- [ ] **Step 3: Create current-revision port callbacks.**

Create `EditorCommandPort` from `state.view`, call `setNarrationBounds` or `reorderNarration` once, clear local draft through the changed view key, increment refresh token in `finally`, and retain the current view with a creator-safe mutation message until the refresh resolves.

- [ ] **Step 4: Run GREEN and closeout gates.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline src/features/editor/workbench src/features/editor/editorCommandPort.test.ts`

Run: `npm --prefix apps/web test`

Run: `npm --prefix apps/web run build`

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_editor_ui_source_provenance.py`

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-editor-ui-source-provenance.ps1`

Run: `git diff --check`

Do not run or claim the full Python regression. Update SSOT/handoff only after independent spec, quality, gap, and source-to-runtime reviews have no open Critical/Important findings; then stage Task 16 files, commit, and push.

## Plan self-review

- Coverage: Tasks 1–4 cover the backend-required reorder layout, pure frame/overlap rules, pointer lifecycle, exactly-once mutation, revision refresh, failure safety, and closeout verification.
- Scope: only existing narration bounds/order commands are used; no new backend/API, non-narration mutation, preview job, provider, or OpenCut work appears.
- Consistency: `boundsById` is camelCase only in UI/port types and is mapped once to the backend `bounds_by_id`; all local times are frame-quantized through Task 14 helpers.
