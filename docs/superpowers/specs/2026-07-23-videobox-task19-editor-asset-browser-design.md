# VideoBox Task 19 editor asset browser design

## Approval record

- Scope approval: 2026-07-23 user instruction, “커밋, 푸쉬하고 다음 goal 진행해”.
- This document is the Task 19 written spec required by the Task 18 closeout. It authorizes only the local editor asset browser and safe preview/apply flow described here.

## Goal

Give the editor a small, keyboard-accessible browser for project B-roll and verified Starter Pack BGM/SFX. A user can inspect an asset, audition it through the existing one-player preview stage, and explicitly apply it to the selected narration segment under the existing revision fence.

## Confirmed current contracts

- `api.listBrollAssets(projectId)` is the project-local B-roll source. `BrollAsset.asset_type` already distinguishes video, image, and audio B-roll and its metadata already carries duration, analysis, review, and optional title/aspect information.
- `api.listMediaLibraryAssets()` is the Starter Pack source. A `MediaLibraryAsset` is `music` or `sfx`; only `available && verified` assets may be materialized.
- `api.materializeMediaLibraryAsset(libraryAssetId, projectId)` returns the project-local `asset_id` required by `EditorCommandPort.applyMedia`.
- `EditorCommandPort` supports only `broll`, `bgm`, and `sfx`; it carries `expectedRevision` to the existing editing-session mutation endpoints.
- `PreviewStage` owns the only `<audio>` or `<video>` element through `PreviewCoordinator`. It already rejects non-local URLs and separates source audition from the exact composed preview.

## Decision and alternatives considered

1. **Recommended: presentational browser, route-owned data/mutation, workbench-owned audition request.** The browser receives typed assets and callbacks. `EditorWorkbenchRoute` loads material and makes the materialize-plus-command operation. `EditorWorkbench` turns a preview request into the existing `PreviewStage` one-player audition. This reuses the established ownership boundaries.
2. Reuse `ManualMediaLibrary` inside the editor. Rejected: it fetches Director preferences directly and mounts its own audio/video elements, so it would fork both data and playback ownership.
3. Let each asset card fetch/materialize/apply itself. Rejected: it bypasses the route epoch/revision fence, complicates stale-route handling, and risks a session mutation after failed or obsolete work.

## Architecture

### Asset model and browser

Create a small pure projector and `EditorAssetBrowser`/`EditorAssetCard` feature under `apps/web/src/features/editor/assets/`.

- The projector normalizes project B-roll and library assets into one card model. It exposes the concrete apply kind (`broll`, `bgm`, or `sfx`), typed preview URL input, display title, duration, target-range copy, and preparation/licence/review state.
- B-roll `broll_video`, `broll_image`, and `broll_audio` are shown as B-roll types. Image/audio B-roll remains a B-roll apply command because that is the existing B-roll asset contract; the card truthfully labels its type.
- Starter Pack BGM/SFX are shown only if available. Unverified/unavailable items remain inspectable with their license state but their Apply button is disabled.
- The browser supports a text query and one type filter: all, B-roll, BGM, or SFX. It does not add favourites, Director preferences, recommendation ranking, drag/drop, upload, image-overlay mutation, voice replacement, automatic placement, or new persistence.
- Every card shows title, type, duration when known, intended selected-segment range, analysis/review state for B-roll, and verified/attribution state for library media. “Reason” is explicit manual intent: `직접 선택한 자산`; Task 20 owns recommendation reasons.

### Selection and explicit apply

- `EditorWorkbench` derives the target only from its selected narration segment. The browser displays `0.00–0.00초` only for a real selected narration clip; without one it says a segment must be selected and disables Apply.
- B-roll Apply requests `onApplyBroll(asset, targetSegmentId)`. BGM/SFX Apply requests `onApplyLibrary(asset, targetSegmentId)`. Preview remains enabled whenever the asset has a permitted local URL, even when no segment is selected.
- The route performs one `commitTimelineMutation` call for every apply. B-roll invokes `port.applyMedia({ kind: "broll", ... })`. BGM/SFX first materialize the library asset, then invoke the corresponding port command with the returned asset ID.
- Materialization failure happens before any command-port call. Therefore no editing-session mutation occurs. Any command conflict/failure follows the established single-command, refresh, no-retry fence.
- Saving disables every Apply action; it does not change the current manifest, browser query, or safe preview selection.

### One preview owner

- Cards do not mount native media, autoplay, or call playback APIs. A preview click emits an `AuditionSource` request to `EditorWorkbench`.
- `EditorWorkbench` keeps a monotonically identified audition request and passes it to `PreviewStage`.
- `PreviewStage` consumes that request through its existing `PreviewCoordinator`, pauses/releases the current exact or audition source, and still renders exactly one native media element. Returning to the exact preview remains explicit.
- Library preview URLs use `api.mediaLibraryPreviewUrl`; B-roll URLs use `api.assetContentUrl`. The existing local-URL gate remains the final browser-request gate.

### Route loading and stale protection

- `EditorWorkbenchRoute` loads the manifest as it does today and, independently, loads B-roll and Starter Pack lists for the current project. Asset-load failure is contained to the browser with a retry-safe message; the editor, transcript, timeline, and exact preview stay usable.
- Both asset load completion and apply completion are guarded by the same route key/epoch discipline used for the manifest. A response for a previous project/session cannot populate or mutate the current route.
- No endpoint, backend domain model, EditorCommandPort API, provider, Hermes, Mem0, network policy, source copy, or DOM/canvas pointer handler is changed.

## Accessibility and responsive behavior

- Cards use real buttons with descriptive labels. Query/filter controls have labels. The selected target is text, not drag-only state.
- Keyboard Enter/Space activates only the focused card control. On narrow layouts the existing left drawer carries the same browser; there is no second browser or player.
- Preview never autoplays. A card preview request does not save, materialize, alter selection, or mutate the editing session.

## Provenance

`opencut-classic` remains pinned at `cf5e79e919144200294fb9fed22a222592a0aeea` in `docs/oss/editor-ui-source-map.json` and is MIT/partial-port. Task 19 uses no copied upstream source, dependency, or runtime import: the implementation is a local typed adapter over VideoBox contracts. Therefore no new materialized upstream path or NOTICE entry is added; the existing provenance verifier must remain green.

## TDD acceptance matrix

1. Pure projection RED/GREEN: type/query filters; B-roll type label; unknown metadata; range/analysis/review/license labels; unavailable library asset is not applicable.
2. Browser RED/GREEN: query/filter result, selected-range display, explicit Apply only, disabled Apply without target or while saving, preview callback without mutation, no native media nodes in cards.
3. Workbench/PreviewStage RED/GREEN: a card request reaches the one `PreviewStage` player, switches exact/audition safely, keeps one `<audio>`/`<video>`, blocks non-local sources, and works in the left drawer.
4. Route RED/GREEN: lists load independently; B-roll command has the current revision; library materializes before exactly one BGM/SFX command; materialize failure makes zero command calls and refreshes safely; stale project/session completions are ignored.
5. Finish with focused frontend tests, full frontend attempt, production build, provenance verifier, diff/status checks, independent spec/quality/gap/source-to-runtime reviews, then SSOT/handoff/commit/push. Do not run or claim the full Python regression.

## Non-goals and constraints

- Voice candidates, voice replacement, image-overlay apply, Director/Eugene recommendations, favourites/recent/pin/exclude, ingest/upload, drag/drop, automatic apply, and persistent preference mutation are excluded. Voice and image-overlay need different existing command contracts and belong to later scoped work.
- No actual OpenCut current runtime, source copy, React/player dependency import, pointer/canvas handler, provider/API expansion, Hermes, or Mem0 work is allowed.
- Task 9 official cumulative progress remains **9/22 (40.9%)** until Task 19 closes. The remaining proportion is **59.1%**.
