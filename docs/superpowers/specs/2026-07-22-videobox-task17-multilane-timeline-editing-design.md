# VideoBox Task 17 Multi-lane Timeline Editing Design

## Goal

Let a creator move and trim the independent timeline placements for B-roll, BGM, SFX, overlays, and captions, including a multi-selection move across lanes. A completed gesture must make one revision-bound editing-session change and must produce the same placement in the editor manifest, exact FFmpeg preview/final render, and CapCut draft.

Task 16 narration trim/reorder remains intact. Task 17 does not change narration order, media asset selection, media controls, caption text/style, split/merge, or preview generation.

## Why a new placement contract is required

The current editing-session bounds/order commands address narration `segments`. B-roll, BGM, SFX, and overlays are stored as media overrides attached to a narration segment, and captions currently expose text/style rather than an independent timing mutation. Calling `setNarrationBounds` for a visual or audio drag would silently trim or move the narration source and all attached media. That is incorrect.

Task 17 therefore adds a durable, revisioned placement layer. The source timeline remains the base; an editing session stores only the explicit timing deltas that the creator has committed.

## Data contract

### Stable placement identity

Every editor-manifest clip and caption receives a stable `placement_id` composed from its persisted track type and base clip/caption identity. It is not a display label, array index, or a narration segment ID. Captions receive a persisted `caption_id` when the session content window is created; `placement_id` uses that ID, so split/merge can never make two caption placements collide. A placement also carries its `kind` (`broll`, `bgm`, `sfx`, `overlay`, or `caption`), source identity, and base time range.

The editing session gains `timeline_placement_overrides`, a map keyed by `placement_id`. Each value contains only:

```json
{
  "placement_id": "broll:clip-123",
  "kind": "broll",
  "start_sec": 4.0,
  "end_sec": 7.0
}
```

No asset URI, source SHA, media controls, caption text, or source trim is copied into the override. Materialization joins the override to the current base clip and rejects a missing kind/base identity rather than guessing.

### Revisioned batch endpoint

Add one typed endpoint:

`PATCH /api/projects/{project_id}/editing-sessions/{session_id}/timeline-placements`

Its request contains `expected_revision` and a non-empty complete list of placement changes. The server validates all changes before one atomic editing-session write. A successful request increments the session revision once, records one undoable history entry, and invalidates existing output freshness through the current session path. A stale revision returns the existing conflict response. There is no force mode and no automatic retry.

The response remains the existing editing-session representation. The client then fetches the authoritative playback manifest before showing the saved layout.

## Timing rules

- UI draft helpers clamp a multi-move's shared delta, then all committed endpoints quantize with the existing rational FPS half-up policy. The server rejects rather than silently clamps any submitted out-of-range or non-frame-valid change.
- A placement must satisfy `0 <= start_sec < end_sec <= output.duration_sec` and span at least one frame.
- Move preserves every selected placement duration and relative offset. The shared delta is clamped so every selected placement remains inside the output range.
- Trim changes one selected edge only. It never changes source media selection or narration bounds.
- B-roll, BGM, SFX, and overlay placements may overlap. Their persisted track order remains unchanged; Task 17 does not introduce z-order reordering.
- Caption placements may overlap other captions and media. They retain the same caption text/style and are independently materialized into subtitle/output timing.
- A batch cannot contain duplicate placement IDs, an unknown placement, a mismatched kind, non-finite values, or a source identity whose current base clip is absent. These cases fail closed without a revision change.

## Editor interaction

TimelineDock gains generic placement selection and local drafts while retaining Task 16 narration controls.

- A creator can select a non-narration clip or caption. Shift-click/Shift-key selection adds or removes placement IDs from the local selection.
- A selected placement exposes accessible start/end trim controls and a move control. Keyboard arrows offer the same one-frame trim/move action.
- A multi-selection move uses one pointer gesture and commits one batch request. A trim acts on one placement only.
- Pointer movement changes local state only. Pointer release commits once only when a real frame-quantized change exists; press-release without movement and pointer cancel issue no request.
- Saving disables Task 17 controls. Conflict/failure clears the draft, retains the last authoritative layout until refresh finishes, and shows creator-language retry guidance.

The Dock still never imports an API client or `EditorCommandPort`; it receives narrow async callbacks. `EditorWorkbenchRoute` owns the current-revision command port and the same A→B→A race fence used by Task 16.

## Materialization and outputs

The placement override is applied after base timeline/session media materialization and before these consumers are built:

1. editor playback manifest;
2. exact preview/final FFmpeg composition plan; and
3. CapCut draft adapter.

All three receive the same adjusted `start_sec`/`end_sec` while preserving source asset identity, source SHA/revision, media controls, rights warnings, and overlay/caption payload. A source/provenance failure remains fail-closed. Existing Task 9 human approval and CapCut Desktop import gates remain separate; Task 17 only proves the generated contracts agree.

## Scope boundaries

- Include: durable placement overrides, one revisioned batch endpoint, manifest/output/CapCut materialization, TimelineDock pointer/keyboard selection, and tests for all five placement kinds.
- Exclude: narration reorder/split/merge changes; asset replacement; media-control editing; caption text/style editing; track creation/deletion; z-order changes; preview-job start; provider/Hermes/Mem0; OpenCut runtime/source copy; and external network calls.
- The Task 14 pure time/geometry modules stay unchanged. New pure placement helpers may import only those helpers and no React/DOM/API code.

## Verification and completion

- RED→GREEN tests cover pure quantization/clamp/batch validation, atomic API conflict/rejection, manifest and FFmpeg/CapCut parity for every placement kind, one-request pointer release, cancel/no-move, multi-lane move, keyboard accessibility, disabled saving, and route race safety.
- Focused Python suites cover core/API/materialization; focused frontend suites cover timeline/route/command port. Full frontend attempt, production build, provenance verifier, targeted Python suites, `git diff --check`, independent quality/gap/source-to-runtime review, SSOT/handoff, commit, and push are required.
- Do not run or claim the full Python regression without separate user direction.

## Design self-review

- No placeholder or deferred semantic is used: placement identity, atomicity, timing rules, output consumers, and exclusions are explicit.
- The design does not reuse narration bounds for non-narration media, so it avoids corrupting narration/source timing.
- The feature is deliberately a broad Task 17, but its one shared placement contract prevents five incompatible lane implementations.
