# VideoBox Task 15 Read-only Timeline Navigation Design

## Goal

Expose the Task 14 deterministic timeline calculations through a read-only editor timeline so a creator can inspect time, fixed lanes, visible clips, and the current playhead without changing an editing session.

## Scope

- Render a ruler, fixed `narration`/`broll`/`bgm`/`sfx`/`overlay` lanes, visible clip rectangles, gap slots, playhead, current caption highlight, snap indicator, and an explicit empty state.
- Add local navigation state only: viewport seconds, zoom, horizontal scroll, and current playhead seconds. Click/keyboard seek changes this local state only.
- Consume Task 14 `time-scale`, `timeline-geometry`, `snapping`, and `hit-testing`; seconds remain canonical and frame conversion remains exclusively in `time-scale`.
- Add a `TimelineDock`/read-only adapter boundary that projects the existing typed editor view model into immutable timeline inputs. It neither calls `EditorCommandPort` nor mutates API/session/revision/preview state.

## Non-goals

- No trim handle, pointer drag, split, merge, reorder, asset replacement, undo/redo, API request, or revisioned mutation; these belong to Task 16.
- No DOM/canvas measurement inside Task 14 modules; DOM concerns stay in Task 15 components.
- No change to exact FFmpeg preview, caption timing authority, provider/Hermes/Mem0, OpenCut runtime, or browser export.

## Design

`TimelineDock` owns a reducer-like local navigation model `{ viewportStartSec, pixelsPerSecond, playheadSec, selectedClipId }`. Its inputs are immutable editor projection plus fixed viewport width; its outputs are pure layout descriptors from Task 14 and presentational React components. Zoom preserves the time under its chosen anchor through `zoomAroundAnchor`; scroll clamps its viewport to the timeline duration; seek clamps to the same range.

The visible clip list is computed before React rendering using the half-open viewport contract. Fixed lane order comes from `TIMELINE_LANES`; a gap slot is display-only and cannot be selected as a command target. Selecting a clip affects local visual emphasis only. Caption highlighting uses existing segment-linked timing and never creates an independent cue time.

Keyboard navigation works only when focus is inside the timeline and the event target is not an editable input. Arrow keys step the playhead by a frame through `time-scale`; Home/End seek to bounds; `+`/`-` zoom around the playhead. This is local navigation, not an editing command.

## Performance and accessibility

- For the 60-minute/1,000-item fixture, render at most 300 clip DOM nodes after visible-range filtering.
- Pointer move schedules at most one React state commit per animation frame; click/keyboard operations do not allocate a session mutation.
- Ruler/lanes/clips use semantic labels, visible focus, and keyboard instructions; focus stays in the timeline during keyboard navigation.

## Tests and acceptance

- RED-first component tests cover lane order, visible-range rendering, ruler/playhead, seek/scroll/zoom clamp, snap indicator, gap/caption display, keyboard focus/input guard, and no `EditorCommandPort` or API invocation.
- A structural performance test fixes the 60-minute/1,000-item fixture at <=300 rendered clip nodes and one pointer-move commit per animation frame.
- Focused Task 15 frontend tests, full frontend attempt, production build, browser interaction smoke, provenance verifier, and `git diff --check` run before closeout. Full Python regression remains outside this task unless explicitly requested.

## Boundary decision

Task 15 may introduce React/DOM components only outside `apps/web/src/features/editor/timeline/{time-scale,timeline-geometry,snapping,hit-testing}.ts`. Those four Task 14 modules remain import-free pure math, and Task 15 must not weaken their provenance verifier contract.
