# VideoBox Task 14 Timeline Geometry Design

## Goal

Make the editor timeline's time, frame, pixel, snapping, and hit-test calculations deterministic before any timeline UI navigation or editing mutation is added.

## Scope and boundaries

- Create pure TypeScript modules under `apps/web/src/features/editor/timeline/` only.
- Keep the API boundary in seconds. Do not add an API request, `EditorCommandPort` call, React state hook, pointer handler, DOM measurement, canvas dependency, or editing-session mutation.
- Task 15 owns visible timeline navigation. Task 16 owns drag and typed revisioned editing commands.
- Output width, height, sample aspect ratio, rotation, and media crop are not inputs to Task 14 timeline math.
- Preserve current exact-preview time origin; this task does not change preview playback or caption timing.

## Module design

### `time-scale.ts`

This is the only module allowed to convert between seconds and frames.

- `RationalFps` is `{ num: number; den: number }` with positive safe-integer numerator and denominator.
- A frame is a non-negative safe integer. Invalid, negative, or non-finite inputs throw `RangeError` instead of silently creating a different timeline position.
- `frameToSeconds(frame, fps)` computes `frame * den / num` without rounding.
- `secondsToFrameHalfUp(seconds, fps)` computes `floor(seconds * num / den + 0.5)`. This is the sole quantization point and fixes 29.97fps as `30000/1001` rather than a rounded decimal.
- `quantizeToFrame(seconds, fps)` is the composition of those two functions. Repeated quantization must not drift.
- `TimelineScale` stores positive finite `pixelsPerSecond` and finite `originSec`. `timeToPixels` and `pixelsToTime` are exact inverse transforms within floating-point tolerance.
- `zoomAroundAnchor` changes only pixels-per-second while preserving the timeline time under the supplied screen pixel. It never quantizes.
- `clampTime` clamps a finite time into a finite, ordered `[startSec, endSec]` range.

### `timeline-geometry.ts`

This module derives read-only timeline layout data from canonical seconds.

- The stable lane order is `narration`, `broll`, `bgm`, `sfx`, then `overlay`.
- A clip rect is derived from lane index, clip start/end seconds, a `TimelineScale`, lane height, and viewport. It returns only finite coordinates and never reads browser state.
- Visible-clip selection uses a half-open time interval `[viewportStartSec, viewportEndSec)` so adjacent clips neither overlap nor disappear at a shared boundary.
- Neighbor lookup returns the preceding and following clip by stable timeline order and then clip ID; it does not mutate clips or resolve overlap policy.

### `snapping.ts`

This module chooses a candidate position but does not apply a move.

- Candidates come only from the playhead, selected-range start/end, and neighboring clip start/end.
- Candidate times are first frame-quantized, then deduplicated by quantized frame.
- The pixel threshold converts to seconds through the current `TimelineScale`; equality is included in the threshold.
- Ties resolve deterministically by: shortest distance, candidate kind (`playhead`, selected start, selected end, neighbor start, neighbor end), stable candidate ID, then time.
- The result is either `null` or a read-only descriptor with the chosen quantized time and source. Input array order cannot change the result.

### `hit-testing.ts`

This module classifies a pointer coordinate against already-derived clip rects.

- Hit priority is: selected clip edge handle, same-lane clip body with highest `zIndex`, gap, then empty timeline.
- Equal-priority clips use lexical clip ID as the final tie-breaker.
- A short clip whose edge-handle zones overlap chooses the start edge deterministically.
- It returns a descriptor only; it does not select, seek, resize, or dispatch a command.

## OSS provenance

Task 14 may use only the `opencut-classic` MIT source pin already recorded in `docs/oss/editor-ui-source-map.json`. Before writing implementation, the plan must identify each inspected upstream pure-math path and SHA-256 from commit `cf5e79e919144200294fb9fed22a222592a0aeea`.

The VideoBox modules are an independent TypeScript implementation, not copied upstream files. No upstream copy header or `THIRD_PARTY_NOTICES.md` entry is added unless an upstream file is actually copied; this design forbids such copying. The provenance verifier must reject forbidden EditorCore, database, renderer, Next, IndexedDB/OPFS, and browser-export imports from Task 14 module paths.

## Tests and acceptance

- `time-scale.test.ts`: property-style seconds/pixels round trips, 24fps and `30000/1001` fixtures, half-up boundary fixture, invalid input rejection, clamp, zoom-anchor preservation, and repeated quantization stability.
- `timeline-geometry.test.ts`: role order, half-open visibility, finite rects, deterministic neighbors, and rotation/canvas independence.
- `snapping.test.ts`: threshold boundaries, frame-grid snapping, candidate deduplication, each tie-break level, and shuffled-input invariance.
- `hit-testing.test.ts`: selected edge priority, z-index/body priority, gap/empty outcomes, equal-ID tie-break, and short-clip edge overlap.
- The focused frontend command, full frontend test attempt, production build, and source-provenance verifier must run before closeout. The full Python regression remains outside Task 14 and is not claimed unless separately run.

## Non-goals

- No rendered ruler, tracks, clips, playhead, zoom control, scrolling, selection state, keyboard navigation, or virtualized DOM.
- No trim handles, drag behavior, undo/redo, caption editing, server validation, or command dispatch.
- No waveform, provider, Hermes, container, memory, OAuth, or external network work.
