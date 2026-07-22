# VideoBox Task 16 Narration Timeline Mutation Design

## Goal

Let a creator trim either end of a narration clip and drag narration clips into a new order in the TimelineDock. Each completed gesture sends exactly one revision-bound editing-session mutation and then refreshes the authoritative playback manifest.

## Scope

- Trim only `narration` clips. A start or end handle moves at frame precision, stays within the timeline, keeps at least one frame, and cannot overlap adjacent narration clips.
- Drag a narration clip body to reorder narration. Reorder creates one complete segment order and a complete non-overlapping `bounds_by_id` layout; it preserves each segment duration and lays the reordered narration contiguously from the current earliest narration start.
- Pointer move changes local draft state only. Pointer release or pointer cancel completes or discards that draft. No request is sent per pointer move.
- `EditorWorkbenchRoute` owns the current-revision `EditorCommandPort`, performs the mutation, refreshes its manifest after success or failure, and shows a creator-safe message. A conflict never overwrites newer state.

## Required correction

`EditorCommandPort.reorderNarration` currently sends only `segment_ids`; the backend requires `bounds_by_id` for a changed order. Its typed input must therefore include a complete bounds map and forward it unchanged. No new API endpoint is needed.

## Boundaries

- The Task 14 pure math modules remain unchanged and import-free.
- TimelineDock receives narrow async callbacks, not `EditorCommandPort` or `api`. Task 16 permits pointer-driven local drafts in the Dock, while provenance continues to forbid direct command-port/API imports, direct requests or `mutate()`, preview writes, and canvas.
- Do not change B-roll/BGM/SFX/overlay/caption timing, split/merge, undo/redo, preview generation, provider/Hermes/Mem0, OpenCut runtime, or backend persistence/API contracts.

## Interaction and failure rules

- The selected narration clip exposes accessible start/end trim controls and a drag control. Keyboard focus and existing read-only navigation stay intact.
- While saving, all Task 16 controls are disabled. A successful request clears the draft and refreshes the manifest; the existing exact preview naturally becomes stale through the refreshed source state but Task 16 does not start a preview job.
- A rejected mutation, including a revision conflict, clears the draft, reloads the manifest, and reports a safe retry message. It never retries or force-applies automatically.

## Verification

- RED→GREEN component tests cover frame-quantized trim, neighbour clamp, exactly one callback at pointer release, pointer cancel, drag reorder with complete bounds, disabled saving controls, conflict/failure refresh, and no per-move API call.
- Command-port tests prove the complete reorder payload retains `expected_revision` and `bounds_by_id`.
- Task 15 performance and Task 14/15 provenance rules remain green. Focused editor timeline/workbench/route tests, full frontend attempt, production build, provenance pytest, PowerShell verifier, and `git diff --check` are required before closeout. Do not run or claim the full Python regression.

## Acceptance decision

Task 16 is complete only when narration trim and reorder both reach the existing revisioned backend contract through one release-time request, refresh authoritative state after every outcome, and keep all non-narration mutation work outside the change.
