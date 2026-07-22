# VideoBox Task 15 Read-only Timeline Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render and navigate a fixed-lane editor timeline locally without issuing an editing command or changing an editing session.

**Architecture:** A pure `timelineNavigation` reducer projects immutable `EditorViewModel` seconds data into Task 14 clip geometry. `TimelineDock` renders those descriptors and owns only local viewport/playhead/selection state; `EditorWorkbench` supplies the view model and never turns navigation into an API call.

**Tech Stack:** React 19, TypeScript, Vitest, existing Task 14 pure modules, Vite.

---

### Task 1: Add pure read-only navigation projection

**Files:**
- Create: `apps/web/src/features/editor/timeline/timelineNavigation.ts`
- Create: `apps/web/src/features/editor/timeline/timelineNavigation.test.ts`

- [x] **Step 1: Write failing reducer tests.**

```ts
it("clamps seek and preserves the anchor time while zooming", () => {
  const state = createTimelineNavigation({ durationSec: 60, pixelsPerSecond: 80 });
  expect(reduceTimelineNavigation(state, { type: "seek", seconds: 99 })).toMatchObject({ playheadSec: 60 });
  expect(reduceTimelineNavigation(state, { type: "zoom", anchorPx: 200, pixelsPerSecond: 160 }).playheadSec).toBe(0);
});
```

Also test fixed lane projection, half-open visible clips, frame keyboard step through `time-scale`, input-event guard, local selection, and no mutation of view inputs.

- [x] **Step 2: Run RED.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline/timelineNavigation.test.ts -t "clamps seek"`

Expected: FAIL because `timelineNavigation` is absent.

- [x] **Step 3: Implement minimal pure contracts.**

```ts
export type TimelineNavigationState = Readonly<{ viewportStartSec: number; pixelsPerSecond: number; playheadSec: number; selectedClipId: string | null }>;
export type TimelineNavigationAction = Readonly<{ type: "seek"; seconds: number }> | Readonly<{ type: "scroll"; seconds: number }> | Readonly<{ type: "zoom"; anchorPx: number; pixelsPerSecond: number }> | Readonly<{ type: "select"; clipId: string | null }>;
export function createTimelineNavigation(input: Readonly<{ durationSec: number; pixelsPerSecond: number }>): TimelineNavigationState;
export function reduceTimelineNavigation(state: TimelineNavigationState, action: TimelineNavigationAction, context: Readonly<{ durationSec: number; viewportWidthPx: number; fps: RationalFps }>): TimelineNavigationState;
```

Use `clampTime`, `zoomAroundAnchor`, `timeToPixels`, `pixelsToTime`, and Task 14 geometry only. The reducer must not import React, API, preview, or command modules.

- [x] **Step 4: Run GREEN.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline/timelineNavigation.test.ts`

Expected: PASS.

### Task 2: Render the accessible TimelineDock

**Files:**
- Create: `apps/web/src/features/editor/timeline/TimelineDock.tsx`
- Create: `apps/web/src/features/editor/timeline/timeline-dock.test.tsx`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbench.tsx`

- [x] **Step 1: Write failing component tests.**

```tsx
render(<TimelineDock view={fixtureView} viewportWidthPx={800} />);
expect(screen.getByRole("region", { name: "타임라인" })).toBeVisible();
expect(screen.getAllByRole("listitem", { name: /내레이션/ })).toHaveLength(1);
fireEvent.keyDown(screen.getByRole("region", { name: "타임라인" }), { key: "ArrowRight" });
expect(screen.getByLabelText("재생 위치")).toHaveAttribute("data-seconds", "0.04");
```

Cover ruler/playhead, clip-only visible range, gap/caption/snap display, click seek, arrow/Home/End/+/- navigation, input guard, focus, and assertions that mocked API and `EditorCommandPort` are unused.

- [x] **Step 2: Run RED.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline/timeline-dock.test.tsx -t "renders fixed lanes"`

Expected: FAIL because `TimelineDock` is absent.

- [x] **Step 3: Implement presentation-only Dock and mount it.**

```tsx
export function TimelineDock({ view, viewportWidthPx }: { view: EditorViewModel; viewportWidthPx: number }) {
  // useReducer only for TimelineNavigationState; render role="region" and immutable descriptors.
}
```

Replace the static `vb-editor-workbench__timeline` summary with `<TimelineDock view={view} viewportWidthPx={availableWorkbenchWidth} />`. Do not add API props, mutation callbacks, trim handles, drag handlers, canvas, or preview writes.

- [x] **Step 4: Run GREEN.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline/timeline-dock.test.tsx`

Expected: PASS.

### Task 3: Add structural performance and boundary regressions

**Files:**
- Modify: `apps/web/src/features/editor/timeline/timeline-dock.test.tsx`
- Modify: `tests/test_editor_ui_source_provenance.py`
- Modify: `scripts/verify-editor-ui-source-provenance.ps1`

- [x] **Step 1: Write failing limits.**

```tsx
it("renders no more than 300 clips for 1000 clips across a 60-minute fixture", () => {
  render(<TimelineDock view={thousandClipHourView} viewportWidthPx={800} />);
  expect(screen.getAllByTestId("timeline-clip").length).toBeLessThanOrEqual(300);
});
```

Add source-to-runtime assertions that Task 14 math files remain free of React/DOM/API imports and Task 15 Dock has no `EditorCommandPort`/mutation import.

- [x] **Step 2: Run RED.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline/timeline-dock.test.tsx -t "renders no more than 300 clips"`

Expected: FAIL before visible-range filtering is complete.

- [x] **Step 3: Implement only range filtering and verifier rules.**

Derive visible clips before JSX, cap no clip artificially, and let the fixture prove the real viewport result. Extend the independent verifier with a Task 15 read-only scan for `EditorCommandPort`, `fetch(`, `axios`, and mutation verbs imported by the Dock.

- [x] **Step 4: Run GREEN.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline/timeline-dock.test.tsx`

Expected: PASS.

### Task 4: Close Task 15

**Files:**
- Modify: `docs/development-status-2026-06-29.ko.md`
- Create: `docs/handoffs/2026-07-22-videobox-task15-read-only-navigation-closeout.ko.md`

- [x] **Step 1: Run closeout verification.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline`

Run: `npm --prefix apps/web test`

Run: `npm --prefix apps/web run build`

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_editor_ui_source_provenance.py`

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-editor-ui-source-provenance.ps1`

Run: `git diff --check`

Record actual results; do not run or claim the full Python regression.

- [x] **Step 2: Commit and push only after spec, quality, gap, and source-to-runtime reviews have no open Critical/Important findings.**

Run: `git add apps/web/src/features/editor/timeline apps/web/src/features/editor/workbench/EditorWorkbench.tsx tests/test_editor_ui_source_provenance.py scripts/verify-editor-ui-source-provenance.ps1 docs`

Run: `git diff --cached --check`

Run: `git commit -m "feat: navigate the fixed-track timeline"`

Run: `git push origin codex/videobox-container-compatibility`

## Plan self-review

- Coverage: Tasks 1–3 map every accepted navigation, accessibility, performance, Task 14 reuse, and no-mutation requirement to tests and source boundaries.
- Scope: no Task 16 command, pointer drag, trim, asset, preview, provider, or Hermes work appears.
- Consistency: `TimelineNavigationState`, `TimelineDock`, `EditorViewModel`, `RationalFps`, and the Task 14 helper names are defined before use; each change has an exact RED and GREEN command.
