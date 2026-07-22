# VideoBox Task 20 Eugene conversation, recommendations, and Inspector design

## Approval record

- Scope approval: 2026-07-23 user instruction to develop the remaining VideoBox editor MVP work quickly, with reviews only where they reduce risk.
- This specification authorizes only the Task 20 editor RightDock integration below. It does not authorize a provider/API expansion, Hermes, Mem0, source copy, OpenCut runtime, automatic apply, or a new media player.

## Goal

Replace the disabled RightDock placeholders with a persistent Eugene conversation, inline recommendation cards, and a typed Inspector. The creator can continue manual editing whenever Eugene cannot prepare a response or recommendation.

## Confirmed contracts

- `EditorWorkbenchRoute` owns the current project/session manifest, route epoch, mutation fence, refresh, and `EditorCommandPort`. Its child workbench must not fetch, mutate, or retain a stale route result.
- `EditorWorkbench` owns selected narration segment, playback position, audition request, local panel state, and the sole `PreviewStage`. `PreviewCoordinator` remains the one-player owner; no Director player may be mounted.
- Existing Director APIs already provide durable reload, conversation creation, message list/send with idempotent client ID and `202 + Retry-After`, immutable proposal/candidate DTOs, and proposal preflight. Task 20 consumes these unchanged.
- `EditorCommandPort` supports B-roll, BGM, SFX, their existing media controls, caption text/style, and explanation-card/image/table overlays. It has no voice command and no generic OpenCut effect command.
- The browser runtime allows only same-origin or loopback network URLs. Tests must prove no external provider request; production UI must not expose provider/runtime/revision wording.

## Decision and alternatives

1. **Chosen: a workbench-specific callback adapter.** The route reads existing Director state and provides typed callbacks; the RightDock owns only UI state. It preserves the one-player and revision-fence boundaries.
2. Reuse `DirectorWorkspace` directly. Rejected: it owns a separate asset player and proposal-apply path, so it can create duplicate playback and bypass the workbench mutation boundary.
3. Build a new conversation/proposal backend. Rejected: the current DTO/API already meets persistence and idempotency needs; duplicating it would expand provider/API scope without MVP value.

## Architecture

### Route-owned Director state and safe request lifecycle

`EditorWorkbenchRoute` adds a Director load state keyed by `projectId:sessionId` and guarded by the same route epoch. It calls `reloadDirectorSession`; only a user submit creates a missing conversation. It reads messages with the recovered or newly created conversation ID. A route change invalidates pending load/send completions before they can update UI.

The adapter keeps the same client message ID through a `202` retry. It does not invent an assistant exchange, proposal, candidate, or mutation on error. A blocked/failed request shows creator-language recovery copy and leaves the existing asset browser, transcript, timeline, preview, and manual apply controls usable.

### Persistent RightDock surface

Create a `RightDock` composition with three simultaneously mounted sections: `EugeneConversation`, `InlineRecommendations`, and `InspectorPanel`. Inspector is an in-place disclosure, not a route change or conditional replacement of the dock. Consequently its open/close action preserves composer draft, conversation history, candidate selection, scroll position, and the workbench audition request. The selected segment/range, selected placement when available, matching proposal revision, and matching gap slot are passed as typed context to the visible conversation/recommendation labels; internal IDs and revision terminology are not shown to creators.

Conversation history renders recovered messages in stable creation order. The composer stays visible for usable sessions. During `202`, it keeps the draft/client ID and gives one retry action after the advertised delay. When Eugene is blocked, the dock explains that the creator can use the already visible manual media, caption, timeline, and Inspector controls; it never disables them.

### Inline recommendation and explicit action boundary

Recommendations render from the existing immutable `DirectorProposal`/`DirectorCandidate` DTO. Cards show creator-safe target scene, rationale, availability/review/right warning, and chosen state. Cards have no fetch, preview player, materialization, or direct mutation.

Task 20 does **not** add automatic apply. An assistant action-intent may be displayed as a recommendation only until the creator presses the explicit `추천 적용` button. That button is route-owned: it preflights the immutable proposal, calls the existing atomic `batchApplyDirectorProposal` with the current expected revision, and refreshes the manifest under the mutation/route fence. It never retries a conflict or failed apply. Candidate preview uses the existing workbench `PreviewStage` request callback only after a local URL is accepted. No recommendation has a second audio/video element.

### Typed Inspector registry

Create a pure Inspector projection/registry keyed by the current selection:

| Selection | Exposed fields | Existing command path |
| --- | --- | --- |
| B-roll clip | read-only context only | none; its renderer controls are not round-trip-safe in the current manifest response contract |
| BGM, SFX clip | fade in/out | `updateMediaControls` |
| linked caption | text and current style fields; no independent timing | `setCaptionText`, `setCaptionStyle` |
| explanation card | title, body, text | `applyOverlay({ kind: "explanation-card" })` |
| image/table overlay | existing typed image/table values | `applyOverlay` typed variants |
| narration, gap, no selection | read-only context or empty guidance | none |

Voice, keyframes, masks, transitions, generic effects, independent caption timing, B-roll renderer controls that the current manifest response cannot round-trip, and every backend-unsupported OpenCut control are absent. Inspector submissions are callback-only; the route decides whether the existing current-revision command port is invoked and refreshes the authoritative manifest afterward.

## State and error rules

- RightDock UI state is keyed only to the active workbench route. Project/session change resets it; Inspector toggling does not.
- Scroll restoration uses a dock-local element and is never global-window scrolling. Preview playback stops only under existing stage rules.
- Any stale load/send/preflight completion is ignored. It cannot refresh the manifest, call a command port, replace the current conversation, or move the player.
- Unsupported selection is rendered as an empty Inspector state, not a disabled fictional control.
- A missing/failed Director reload is contained to Eugene; it never prevents manual editing or exact preview.

## Accessibility and creator copy

- Composer, history, recommendations, Inspector disclosure, selection summary, status, and retry action receive semantic labels and keyboard access.
- Inspector disclosure uses `aria-expanded`; narrow drawer focus/escape/return behavior remains owned by `EditorWorkbench`.
- Visible and accessible creator copy uses video-making terms. It excludes provider, runtime, API, model, context, revision, and internal IDs.

## Provenance and non-goals

This is an independent TypeScript/React adapter and registry. It does not materialize OpenCut, copy upstream code, import an OpenCut dependency, or amend OSS notices/source maps. It does not expand API types/endpoints or invoke external providers. The existing network guard and source-provenance verifier remain required closeout gates.

## TDD acceptance matrix

| Case | RED/GREEN evidence |
| --- | --- |
| recovered conversation/messages display in order and composer stays visible | focused RightDock test; no create request on reload |
| missing conversation is created once only after submit | route/adapter test; stable client message ID across retry |
| `202` retry and blocked/failed Eugene retain draft and manual fallback | focused RightDock test; zero editor command calls |
| inline candidate preview reaches one `PreviewStage` player and explicit creator apply preflights then sends one current-revision batch apply | workbench/route + preview DOM test: at most one audio/video, local URL only; conflict/failure sends no retry |
| Inspector disclosure preserves conversation draft, card selection, dock scroll, and current audition request | RightDock/workbench state-preservation test |
| Inspector registry exposes only exact command-port fields | pure projection test plus absent voice/effect/timing assertions |
| a valid Inspector save uses one current revision route command and refreshes manifest | route test; conflict/failure sends no retry command |
| A-to-B route switch ignores old Director load/send/preflight and makes zero old-route commands | route-epoch test |
| local/test UI makes no external provider request | network guard/fake provider counter test |

## Reverse runtime trace

`EditorWorkbenchRoute` reads `reloadDirectorSession` and `listDirectorMessages` behind its route epoch → it passes DTOs and callbacks to `EditorWorkbench` → `RightDock` renders presentation components → optional candidate preview callback creates an `AuditionRequest` → `PreviewStage` rejects non-local URLs and delegates only to `PreviewCoordinator` → an explicit creator recommendation apply preflights then calls the existing atomic batch endpoint under the route mutation fence → any supported Inspector intent returns upward → route captures current revision in `EditorCommandPort` → existing API endpoint → route refreshes manifest. No RightDock child imports `api`, makes a provider call, materializes assets, mounts media, or mutates a session directly.

## Spec self-review

- Placeholder scan: no TODO/TBD or unspecified implementation route remains.
- Consistency: Inspector mutations use the existing route command port; recommendation apply uses the existing preflighted atomic batch endpoint, always after an explicit creator action.
- Scope: API/provider/OpenCut/Hermes/Mem0/automatic apply and unsupported voice/effects are explicitly excluded.
- Ambiguity resolved: “persistent” means durable server conversation/messages plus route-lifetime UI state; Inspector toggling preserves UI state but project/session navigation resets it.
