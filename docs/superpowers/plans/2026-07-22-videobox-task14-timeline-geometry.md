# VideoBox Task 14 Timeline Geometry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic, read-only timeline time/frame/pixel, geometry, snapping, and hit-test helpers without creating UI interaction or editing mutations.

**Architecture:** Keep canonical values at the seconds API boundary. `time-scale.ts` is the only frame-conversion and quantization boundary; the other three modules consume only explicit primitive data and return descriptors. The OSS source map records inspected OpenCut classic pure-math files and a verifier blocks forbidden runtime imports from the new module directory.

**Tech Stack:** TypeScript 5, Vitest, Vite production build, Python/PowerShell provenance verifier.

---

## Fixed scope and provenance

- Production files are limited to `apps/web/src/features/editor/timeline/{time-scale,timeline-geometry,snapping,hit-testing}.ts`.
- Tests are colocated `*.test.ts`; no React, DOM, canvas, API, `EditorCommandPort`, mutation, navigation, browser renderer, storage, provider, Hermes, or Mem0 code is allowed.
- The inspected upstream is read-only reference material at `OpenCut-app/opencut-classic@cf5e79e919144200294fb9fed22a222592a0aeea`; no upstream source text is copied.

| Upstream pure-math path | Git blob SHA | SHA-256 |
| --- | --- | --- |
| `apps/web/src/fps/utils.ts` | `c2a57fbbe2268cbedf957fcc16056a18333f5bed` | `b3d091725124abe21b348d34cb15643200fb8e650cbb2fab3ce16fb68c6dac28` |
| `apps/web/src/timeline/pixel-utils.ts` | `71e8466a7c0a603571244a570ad7ffcd45e25691` | `373bcd4b0d9fd88da7cffb05bd3ea3368c8aabcb13f275147cfceb59e70eaef0` |
| `apps/web/src/timeline/snapping/build.ts` | `87d3db2e5864c377f38465c88e9533280aa71b03` | `7cf9b8dc203a691af38e99d16ceb401cb881055b93244f9f6afa65338ef46e1a` |
| `apps/web/src/timeline/snapping/resolve.ts` | `dcbc670da91d1003694a506a739f6848e1a7e571` | `73f7865940cd914b09070ca3daa03325b03a31bd33ebb6766dc0975736c6fc0d` |
| `apps/web/src/timeline/snapping/threshold.ts` | `f03111dc4ab189eddf9bffdcf17d5ab26eae7a8a` | `951ed0604bcd5960384a520a14cf66f554c2580f4e0098e0307939db73ced686` |
| `apps/web/src/timeline/zoom-utils.ts` | `39090d9275569c897f40af745ab938100afa5c97` | `00d105f58146956d915b4614ee1796a73513ff786bed90dd07d1245ee2fb84b6` |

### Task 1: Record and enforce the Task 14 reference-only boundary

**Files:**
- Modify: `docs/oss/editor-ui-source-map.json`
- Modify: `tests/test_editor_ui_source_provenance.py`
- Modify: `scripts/verify-editor-ui-source-provenance.ps1`
- Test: `tests/test_editor_ui_source_provenance.py`

- [ ] **Step 1: Add the failing provenance contract test.**

```python
def test_task14_timeline_math_is_reference_only_and_blocks_runtime_imports():
    source_map = read_json(SOURCE_MAP_PATH)
    decision = next(item for item in source_map["reference_only_decisions"] if item["task"] == "Task 14 timeline geometry")
    assert decision["source_pin"] == "opencut-classic"
    assert decision["materialized_paths"] == []
    assert decision["inspected_upstream_paths"] == [
        {"path": "apps/web/src/fps/utils.ts", "sha256": "b3d091725124abe21b348d34cb15643200fb8e650cbb2fab3ce16fb68c6dac28"},
        {"path": "apps/web/src/timeline/pixel-utils.ts", "sha256": "373bcd4b0d9fd88da7cffb05bd3ea3368c8aabcb13f275147cfceb59e70eaef0"},
        {"path": "apps/web/src/timeline/snapping/build.ts", "sha256": "7cf9b8dc203a691af38e99d16ceb401cb881055b93244f9f6afa65338ef46e1a"},
        {"path": "apps/web/src/timeline/snapping/resolve.ts", "sha256": "73f7865940cd914b09070ca3daa03325b03a31bd33ebb6766dc0975736c6fc0d"},
        {"path": "apps/web/src/timeline/snapping/threshold.ts", "sha256": "951ed0604bcd5960384a520a14cf66f554c2580f4e0098e0307939db73ced686"},
        {"path": "apps/web/src/timeline/zoom-utils.ts", "sha256": "00d105f58146956d915b4614ee1796a73513ff786bed90dd07d1245ee2fb84b6"},
    ]
    for relative in decision["local_paths"]:
        content = (ROOT / relative).read_text(encoding="utf-8")
        assert not any(term.lower() in content.lower() for term in decision["forbidden_import_terms"])
```

- [ ] **Step 2: Run the exact test to verify RED.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_editor_ui_source_provenance.py -k task14_timeline_math_is_reference_only`

Expected: FAIL because the `Task 14 timeline geometry` decision does not exist yet.

- [ ] **Step 3: Add only metadata and independent verifier support.**

Add a `reference_only_decisions` entry with six exact `inspected_upstream_paths`, the four local module paths, empty `materialized_paths`, and these forbidden case-insensitive terms: `EditorCore`, `next/`, `database`, `renderer`, `IndexedDB`, `OPFS`, `browser-export`, `EditorCommandPort`, `document`, `window`, `canvas`.

Add an independent PowerShell loop that requires `task`, `source_pin`, `reference`, `materialized_paths`, `local_paths`, `inspected_upstream_paths`, and `forbidden_import_terms`; validates each upstream path as repo-relative and each SHA-256; requires `materialized_paths.Count -eq 0`; then checks every listed local module exists and contains none of the forbidden terms. Do not add a `THIRD_PARTY_NOTICES.md` entry because no upstream file is materialized.

- [ ] **Step 4: Run the focused provenance suite to verify GREEN.**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_editor_ui_source_provenance.py`

Expected: PASS; this is the provenance-focused Python suite only, not the full Python regression.

- [ ] **Step 5: Run the independent verifier.**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-editor-ui-source-provenance.ps1`

Expected: exit code 0 with the existing provenance success message.

### Task 2: Implement the canonical time and scale contract

**Files:**
- Create: `apps/web/src/features/editor/timeline/time-scale.ts`
- Create: `apps/web/src/features/editor/timeline/time-scale.test.ts`

- [ ] **Step 1: Write one failing test at a time for rational conversion and the public API.**

```ts
import { clampTime, frameToSeconds, quantizeToFrame, secondsToFrameHalfUp, TimelineScale } from "./time-scale";

const ntsc = { num: 30_000, den: 1_001 } as const;

it("uses rational 30000/1001 half-up frame quantization", () => {
  expect(secondsToFrameHalfUp((10.5 * ntsc.den) / ntsc.num, ntsc)).toBe(11);
  expect(quantizeToFrame((10.5 * ntsc.den) / ntsc.num, ntsc)).toBeCloseTo((11 * ntsc.den) / ntsc.num);
});
```

Add separate exact tests for 24fps conversion, safe/finite validation, non-negative frames, inverse time/pixel conversion, zoom-anchor preservation, ordered finite clamp bounds, and repeated `quantizeToFrame` stability.

- [ ] **Step 2: Run each new exact test to verify RED.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline/time-scale.test.ts -t "uses rational 30000/1001 half-up frame quantization"`

Expected: FAIL because `./time-scale` is absent.

- [ ] **Step 3: Add the minimal independent implementation.**

```ts
export type RationalFps = Readonly<{ num: number; den: number }>;
export type TimelineScale = Readonly<{ pixelsPerSecond: number; originSec: number }>;

export function frameToSeconds(frame: number, fps: RationalFps): number;
export function secondsToFrameHalfUp(seconds: number, fps: RationalFps): number;
export function quantizeToFrame(seconds: number, fps: RationalFps): number;
export function timeToPixels(timeSec: number, scale: TimelineScale): number;
export function pixelsToTime(pixel: number, scale: TimelineScale): number;
export function zoomAroundAnchor(scale: TimelineScale, anchorPixel: number, nextPixelsPerSecond: number): TimelineScale;
export function clampTime(timeSec: number, range: Readonly<{ startSec: number; endSec: number }>): number;
```

All validators throw `RangeError`. `secondsToFrameHalfUp` is exactly `Math.floor(seconds * fps.num / fps.den + 0.5)`. `zoomAroundAnchor` derives the old anchor time first and returns an adjusted `originSec` so that `pixelsToTime(anchorPixel, result)` equals the old anchor time; it does not call quantization.

- [ ] **Step 4: Run the file suite to verify GREEN.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline/time-scale.test.ts`

Expected: PASS.

### Task 3: Implement read-only timeline layout and neighbor lookup

**Files:**
- Create: `apps/web/src/features/editor/timeline/timeline-geometry.ts`
- Create: `apps/web/src/features/editor/timeline/timeline-geometry.test.ts`
- Modify: `apps/web/src/features/editor/timeline/time-scale.ts` only if Task 3 requires exported scale helpers already defined in Task 2

- [ ] **Step 1: Write failing geometry tests.**

```ts
import { deriveClipRect, findClipNeighbors, TIMELINE_LANES, selectVisibleClips } from "./timeline-geometry";

it("uses a half-open viewport so a shared boundary belongs only to the following clip", () => {
  const clips = [{ id: "a", lane: "narration", startSec: 0, endSec: 1 }, { id: "b", lane: "narration", startSec: 1, endSec: 2 }];
  expect(selectVisibleClips(clips, { startSec: 1, endSec: 2 }).map(({ id }) => id)).toEqual(["b"]);
});
```

Add focused tests for `TIMELINE_LANES` exact order, finite rect coordinates, lane-index vertical geometry, input validation, stable neighbor ordering by `(startSec, endSec, id)`, and proof that geometry inputs contain neither output/crop/rotation nor canvas values.

- [ ] **Step 2: Run the exact new test to verify RED.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline/timeline-geometry.test.ts -t "uses a half-open viewport"`

Expected: FAIL because `./timeline-geometry` is absent.

- [ ] **Step 3: Add only read-only data types and helpers.**

```ts
export const TIMELINE_LANES = ["narration", "broll", "bgm", "sfx", "overlay"] as const;
export type TimelineLane = (typeof TIMELINE_LANES)[number];
export type TimelineClip = Readonly<{ id: string; lane: TimelineLane; startSec: number; endSec: number }>;
export type TimelineViewport = Readonly<{ startSec: number; endSec: number; topPx: number; heightPx: number }>;
export type ClipRect = Readonly<{ clipId: string; lane: TimelineLane; x: number; y: number; width: number; height: number }>;
```

`selectVisibleClips` uses `clip.startSec < viewport.endSec && clip.endSec > viewport.startSec`; `deriveClipRect` uses only the passed scale, lane height, viewport, and seconds; `findClipNeighbors` sorts a copied array and returns `{ previous, next }` without changing its input.

- [ ] **Step 4: Run the file suite to verify GREEN.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline/timeline-geometry.test.ts`

Expected: PASS.

### Task 4: Implement deterministic frame-grid snapping

**Files:**
- Create: `apps/web/src/features/editor/timeline/snapping.ts`
- Create: `apps/web/src/features/editor/timeline/snapping.test.ts`

- [ ] **Step 1: Write a failing threshold/tie test.**

```ts
import { chooseSnapCandidate } from "./snapping";

it("includes the pixel threshold and resolves an equal distance by candidate kind", () => {
  const result = chooseSnapCandidate({
    proposedSec: 1.1,
    scale: { pixelsPerSecond: 100, originSec: 0 }, fps: { num: 24, den: 1 }, thresholdPx: 10,
    candidates: [{ kind: "neighbor-start", id: "z", timeSec: 1 }, { kind: "playhead", id: "p", timeSec: 1.2 }],
  });
  expect(result).toMatchObject({ kind: "playhead", id: "p" });
});
```

Add isolated tests for only permitted candidate kinds, frame quantization before dedupe, equality threshold, every tie-break key, and shuffled-input invariance.

- [ ] **Step 2: Run the exact test to verify RED.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline/snapping.test.ts -t "includes the pixel threshold"`

Expected: FAIL because `./snapping` is absent.

- [ ] **Step 3: Add the minimal chooser.**

```ts
export type SnapKind = "playhead" | "selected-start" | "selected-end" | "neighbor-start" | "neighbor-end";
export type SnapCandidate = Readonly<{ kind: SnapKind; id: string; timeSec: number }>;
export type SnapResult = Readonly<{ kind: SnapKind; id: string; timeSec: number; frame: number }>;
export function chooseSnapCandidate(input: Readonly<{ proposedSec: number; scale: TimelineScale; fps: RationalFps; thresholdPx: number; candidates: readonly SnapCandidate[] }>): SnapResult | null;
```

Quantize every candidate with Task 2 functions, retain the lexically smallest `(kind rank, id, timeSec)` record per frame, convert `thresholdPx` through `pixelsToTime`, include equality, and sort candidates by `(distance, kind rank, id, quantized time)` before returning the first one. Do not mutate or apply any timeline state.

- [ ] **Step 4: Run the file suite to verify GREEN.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline/snapping.test.ts`

Expected: PASS.

### Task 5: Implement pure hit classification

**Files:**
- Create: `apps/web/src/features/editor/timeline/hit-testing.ts`
- Create: `apps/web/src/features/editor/timeline/hit-testing.test.ts`

- [ ] **Step 1: Write the failing priority tests.**

```ts
import { classifyTimelineHit } from "./hit-testing";

it("prefers a selected clip start handle over a same-lane body", () => {
  expect(classifyTimelineHit({ point: { x: 101, y: 10 }, lane: "narration", edgeHandlePx: 8, selectedClipId: "selected", rects: [
    { clipId: "body", lane: "narration", x: 90, y: 0, width: 40, height: 20, zIndex: 10 },
    { clipId: "selected", lane: "narration", x: 100, y: 0, width: 40, height: 20, zIndex: 0 },
  ] })).toEqual({ kind: "edge", edge: "start", clipId: "selected" });
});
```

Add exact tests for selected end handles, same-lane highest z-index, lexical clip-ID resolution for equal priority, gap, empty timeline, and overlapping short-clip handles choosing `start`.

- [ ] **Step 2: Run the exact test to verify RED.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline/hit-testing.test.ts -t "prefers a selected clip start handle"`

Expected: FAIL because `./hit-testing` is absent.

- [ ] **Step 3: Add the pure classifier.**

```ts
export type HitRect = Readonly<{ clipId: string; lane: TimelineLane; x: number; y: number; width: number; height: number; zIndex: number }>;
export type TimelineHit = Readonly<{ kind: "edge"; edge: "start" | "end"; clipId: string }> | Readonly<{ kind: "body"; clipId: string }> | Readonly<{ kind: "gap"; lane: TimelineLane }> | Readonly<{ kind: "empty" }>;
export function classifyTimelineHit(input: Readonly<{ point: Readonly<{ x: number; y: number }>; lane?: TimelineLane; edgeHandlePx: number; selectedClipId?: string; rects: readonly HitRect[] }>): TimelineHit;
```

Validate finite coordinates. Check selected edge zones before bodies; when both selected edge zones contain the point, return `start`; for bodies filter to the supplied lane and point containment then rank by descending `zIndex`, ascending clip ID; return `gap` only with a supplied lane and `empty` otherwise. It returns data only.

- [ ] **Step 4: Run the file suite to verify GREEN.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline/hit-testing.test.ts`

Expected: PASS.

### Task 6: Close the Task 14 contract and record evidence

**Files:**
- Modify: `docs/development-status-2026-06-29.ko.md`
- Create: `docs/handoffs/2026-07-22-videobox-task14-timeline-geometry-implementation-handoff.ko.md`
- Modify: `docs/superpowers/plans/2026-07-22-videobox-task14-timeline-geometry.md` to tick completed steps

- [ ] **Step 1: Run the complete Task 14 focused frontend suite.**

Run: `npm --prefix apps/web test -- --run src/features/editor/timeline`

Expected: all four Task 14 files pass.

- [ ] **Step 2: Run the full frontend test attempt.**

Run: `npm --prefix apps/web test`

Expected: record the actual result; a failure outside Task 14 remains an explicit non-green boundary, never a pass claim.

- [ ] **Step 3: Run the production build and provenance gates.**

Run: `npm --prefix apps/web run build`

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_editor_ui_source_provenance.py`

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-editor-ui-source-provenance.ps1`

Expected: record each command's independent result. Do not run the full Python regression.

- [ ] **Step 4: Perform independent reviews before documentation and commit.**

Check spec compliance, code quality, plan gaps, and source-to-runtime reverse direction. Confirm production changes stay in the four pure modules; inspect imports and `git diff --check`; confirm the source map's Task 14 decision has no materialized path and all forbidden import checks are active.

- [ ] **Step 5: Update SSOT and handoff.**

Document only verified commands/results, the six read-only upstream paths/SHA-256 values, excluded boundaries, any test/build warning, and the next Task 15 gate. Keep official Task 9 progress at `9/22 (40.9%)`, remaining `59.1%`; do not mark Task 9 accepted.

- [ ] **Step 6: Commit and push the closed task.**

Run: `git status --short`, verify `.tmp-final-fence-debug/` remains untracked and unstaged, then `git add` only Task 14 source/tests/provenance/docs, `git diff --cached --check`, `git commit -m "feat: add pure timeline geometry"`, and `git push origin codex/videobox-container-compatibility`.

Expected: push only after all above gates have evidence; never stage or remove `.tmp-final-fence-debug/`.

## Plan self-review

- Spec coverage: Tasks 2–5 cover all four requested pure modules, rational FPS/half-up quantization, layout/visibility/neighbors, snapping tie rules, and hit priorities. Task 1 records all inspected upstream paths and blocks forbidden source-to-runtime imports. Task 6 supplies all required validation, independent review, SSOT/handoff, commit, and push gates.
- Scope check: no task adds navigation, pointer handling, React/DOM/canvas, API, command port, mutation, renderer, provider, Hermes, or Mem0 work. `document`, `window`, and `canvas` are verifier-forbidden in Task 14 sources.
- Placeholder/type check: public type names and signatures are defined before dependent tasks use them; commands are concrete. The six upstream hashes are complete and record read-only inspection rather than a source copy.
