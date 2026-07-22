# VideoBox Task 18 Synchronized Transcript and Caption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep transcript rows, linked captions, timeline selection, and playback position synchronized without introducing separate caption timing.

**Architecture:** Pure navigation and transcript projection operate on the immutable editor view model. React panels own local selection/focus only; `EditorWorkbenchRoute` remains the sole revision-bound mutation owner.

**Tech Stack:** TypeScript, React 19, Vitest, existing editor manifest/command port.

---

### Task 1: Pure transcript projection and playback navigation

**Files:** Create `apps/web/src/features/editor/transcript/playbackNavigation.ts`, `apps/web/src/features/editor/transcript/transcriptProjection.ts`, and tests.

- [x] **Step 1: Write RED tests** for half-open active selection, clamped seek, missing caption skip, stable segment ordering, and 1,000-row visible-window bounds.
- [x] **Step 2: Run RED** with `npm --prefix apps/web test -- --run src/features/editor/transcript` and expect missing modules.
- [x] **Step 3: Implement pure helpers** with no React/API imports; preserve supplied `segmentId`, `startSec`, `endSec`, and caption text only.
- [x] **Step 4: Run GREEN** with the same command.

### Task 2: Transcript and linked-caption surfaces

**Files:** Create `apps/web/src/features/editor/transcript/TranscriptPanel.tsx`/`CaptionLane.tsx`, tests; modify `PreviewStage.tsx`, `EditorWorkbench.tsx`, and `TimelineDock.tsx` only through typed props. Existing `EditorViewModel` already carries the required persisted IDs and ranges.

- [x] **Step 1: Write RED tests** for row-to-seek selection, timeline-to-row selection, keyboard navigation, IME guard, virtualized row count, and linked caption label.
- [x] **Step 2: Implement local selection/focus**; do not add caption drag/resize or direct API imports.
- [x] **Step 3: Run focused GREEN** for transcript/timeline/workbench tests.

### Task 3: Revision-safe caption text save and route fence

**Files:** Modify `editorCommandPort.ts`, `EditorWorkbenchRoute.tsx`, tests, and existing API type only if the typed caption method is absent.

- [x] **Step 1: Write RED route tests** for exactly-one save, conflict/failure refresh, and A→B→A race suppression.
- [x] **Step 2: Reuse existing caption command** through the Route; disable controls during save and preserve creator-language recovery text.
- [x] **Step 3: Run focused GREEN** for command-port and route tests.

### Task 4: Review and closeout

- [x] **Step 1:** independent spec/quality/gap/source-to-runtime review; resolve Critical/Important findings.
- [x] **Step 2:** run focused suites, `npm --prefix apps/web test`, `npm --prefix apps/web run build`, provenance verifier, and `git diff --check`.
- [x] **Step 3:** update status/handoff, commit, and push. Do not run or claim full Python regression; retain Task 9 at 9/22 (40.9%).

## Plan self-review

The plan separates pure range logic, local UI state, and revisioned save ownership. It explicitly prevents a second caption-time authority and limits the new DOM window for large transcripts.
