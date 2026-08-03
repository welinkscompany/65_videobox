# VideoBox Task 23 owner-ready MVP polish design

## Approval record

- Scope approval: 2026-08-03 user instruction, “기존 9/22 진행률은 폐기하고 Task 23 owner-ready MVP polish를 만들어 바로 진행해.”
- The previously proposed scope was explicitly accepted: HEVC automatic local preview, a repeatable real-sample edit package, one-command owner readiness, actual workflow QA, and Hermes pre-live readiness.
- This written design authorizes planning for the four slices below. Production implementation starts only after the written-spec review gate required by the repository workflow.

## Goal

Turn the technically closed local VideoBox stack into an owner-ready MVP that can preview the user's HEVC footage, diagnose and start the local stack, produce a repeatable review package from read-only samples, and prove Hermes readiness up to—but not across—the credentialed provider/live-Mem0 boundary.

## Progress authority

- The former official `9/22 (40.9%)`, remaining `59.1%` metric is retired by explicit user instruction. Existing occurrences remain historical records and are not rewritten retroactively.
- The completed Task 1–22 technical baseline remains historical context, not the active denominator.
- Task 23 is the new active production denominator: four slices. Planning does not count as production completion.
- Initial state is **0/4 (0.0%)**, remaining **100.0%**. A slice increments the metric only after its TDD acceptance, applicable full regression, reverse trace, SSOT, commit, and push gates pass.

## Current evidence and problem

- Five user MP4 samples were inspected read-only. Four are HEVC/AAC and one is H264/AAC.
- Chromium advances HEVC audio/time but reports `videoWidth=0` and `videoHeight=0`; the source audition therefore has no visible frame. H264 playback is visible.
- The current safe fallback in `PreviewStage` stops the unsupported audition and directs the creator to the exact edited preview. This prevents a misleading black player but does not make the original source inspectable.
- Exact preview/final rendering already uses local FFmpeg and produces browser-playable H264/AAC. Asset content already supports single-range HTTP 206 delivery. `PreviewStage` and `PreviewCoordinator` already enforce one-player ownership and local URL guards.
- Existing scripts already cover focused/full tests, creator-flow smoke, Hermes profile/runtime verification, non-live chat/creator flow, and CapCut draft output. Task 23 composes and extends these rather than duplicating them.

## Alternatives considered

### 1. Chosen: four bounded slices with a lazy local preview proxy

Create a browser-compatible proxy only after a creator requests video audition. Cache it by project, asset, immutable source SHA-256, and a versioned proxy profile. Reuse the existing one-player stage, job persistence, Range delivery, FFmpeg, route epoch, and local network guard. Then build one wrapper for owner diagnostics, one repeatable dogfood package, and one Hermes readiness summary around existing harnesses.

This minimizes import latency, avoids unused duplicate media, keeps failures contained, and produces independently verifiable increments.

### 2. Rejected: transcode every video during ingest

This makes all sources browser-ready before first use, but the 494-second 546MB sample would make project creation unnecessarily slow and double storage even when the clip is never auditioned. A failed transcode would also turn an otherwise valid ingest/final-render source into an import failure.

### 3. Rejected: keep only the exact-preview fallback

This requires applying a source before seeing it and makes media selection slow. It is safe but not owner-ready. It remains the fallback when proxy generation fails.

### 4. Rejected: one giant automation command that edits an existing owner project

A single opaque command would mix environment mutation, project edits, media generation, and provider readiness. It would be hard to retry safely and could alter a real project without a clear apply boundary. Task 23 instead keeps Check read-only, Start explicit, dogfood isolated by default, and existing-project mutation behind an explicit confirmation parameter.

## Slice 23A: lazy HEVC browser-preview proxy

### Backend ownership

Add a small `AssetBrowserPreviewService` owned by the API/orchestration boundary and a pure FFmpeg renderer under core-engine. The service accepts only a project-local registered video asset. It resolves the canonical source through `LocalProjectStore`, probes codec metadata with `FFmpegMediaProbe`, and reads or computes the authoritative source SHA-256.

The browser-ready profile is versioned and fixed to MP4, H264, `yuv420p`, AAC when audio exists, `faststart`, and a maximum 1280-pixel long edge. A source that is already MP4/H264 with AAC-or-no-audio returns the existing asset content URL without creating a proxy.

For an incompatible source, the service creates one durable `ASSET_PREVIEW_PROXY` job keyed by `project_id + asset_id + source_sha256 + profile`. A repeated start returns the existing pending/running/ready job. A failed job may be retried explicitly and creates a new attempt without deleting the previous evidence.

The generic job UI labels this job `원본 미리보기 준비`. Retry remains owned by the asset-preview UI and endpoint because the generic job retry router does not carry the required asset/source identity.

The renderer writes to a project-local temporary file, verifies the generated stream with ffprobe, rechecks the source SHA and current asset registration, and only then atomically publishes the MP4. Source change, asset replacement, route mismatch, corrupt output, or FFmpeg failure never publishes a proxy. The original file is never modified, renamed, deleted, or used as a destination.

### API contract

Three project-scoped endpoints are added under the existing asset router:

- `POST /api/projects/{project_id}/assets/{asset_id}/browser-preview` starts or reuses preparation and returns `200 ready`, `202 pending|running`, or a bounded creator-safe failure.
- `GET /api/projects/{project_id}/assets/{asset_id}/browser-preview` returns the current typed state without starting work.
- `GET /api/projects/{project_id}/assets/{asset_id}/browser-preview/content` serves only a current ready proxy through existing Range delivery. Already-compatible assets use their existing `/content` URL and never duplicate bytes.

The response is a strict DTO with `status`, `job_id`, `content_url`, `source_sha256`, `profile`, and `error_code`. It never returns a filesystem path, FFmpeg command, credential, raw stderr, or external URL.

### Frontend flow and state

`EditorWorkbenchRoute` owns the prepare/poll lifecycle because it already owns project/session route epoch and network calls. `EditorWorkbench` continues to own the audition request, and `PreviewStage` continues to own the only native media element.

When a creator requests a video audition, the route prepares the browser preview before emitting the `AuditionSource`:

1. ready: emit the local returned URL to the existing stage;
2. pending/running: show “원본 미리보기를 준비하고 있어요”, poll with bounded backoff, and keep exact preview/manual editing usable;
3. failed: show retry plus “편집본 미리보기에서 확인” fallback;
4. route change or newer request: ignore the obsolete completion and make zero current-route player or mutation changes.

Audio/image audition keeps the existing direct path. No card or route mounts a second player. Preparation never applies an asset, changes the session revision, starts exact/final rendering, or marks human acceptance.

## Slice 23B: owner one-click check, start, and diagnosis

Create `scripts/owner-ready.ps1` as a thin orchestrator over existing checked-in scripts. It has explicit modes:

- `Check` is the default and read-only. It verifies canonical worktree/branch, protected residue classification, Python/Node/npm, FFmpeg/ffprobe, Docker availability, Compose parse, loopback ports, VideoBox health, Hermes dashboard reachability, CapCut installation path, VideoBox data-root existence/access metadata, and Windows path-length headroom. It does not create a write probe.
- `Start` explicitly starts only the checked-in local VideoBox Compose services and waits for bounded health. It does not start a provider, inject a credential, edit an env file, or open CapCut.
- `Smoke` runs the existing focused creator/non-live Hermes/runtime verifiers and writes a sanitized JSON receipt under ignored `artifacts/owner-ready/`.
- `Open` opens the loopback VideoBox URL. `OpenCapCut` is a separate explicit switch and never edits or exports a project.

Every result is `pass`, `blocked`, or `fail` with a creator-readable recovery action. Missing credentials are `blocked`, not a failed local MVP. Secret values, environment dumps, full command lines containing secrets, and non-loopback URLs are never printed or written.

## Slice 23C: repeatable owner sample edit package

Create a runner that accepts a sample directory and defaults to an isolated ignored output root. It enumerates supported media without modifying the source, records size/duration/codec/SHA-256, and copies only selected inputs into the isolated project through the public local API path.

The runner reuses the existing deterministic creator-flow and rendering commands to produce one bounded review package containing:

- imported source inventory and source/copy hash comparison;
- a short browser-preview proof for H264 and HEVC-proxy playback;
- an editing session using B-roll, BGM, SFX, caption, TTS, and one supported overlay;
- current exact preview, final MP4, SRT, timeline/editing-session snapshot, CapCut draft, ffprobe summary, and reverse-trace manifest;
- a plain Korean review checklist for video, captions, voice, music, effects, transitions, rights, and export.

Default execution is isolated and may simulate explicit selections only inside its disposable QA project. An existing project is never changed unless the operator supplies project/session IDs plus an explicit confirmation flag. Product UI still forbids automatic apply; the runner cannot promote QA decisions into owner approval or memory.

## Slice 23D: Hermes readiness up to the live boundary

Reuse `verify-hermes-yujin-plan-state.ps1`, runtime/profile `-StaticOnly`, non-live chat, creator-flow smoke, and Mem0 non-live smoke. Add their sanitized results to the owner-ready receipt and verify that agent soul/profile files are mounted only through the pinned Hermes profile contract.

The readiness report distinguishes:

- `local_ready`: dashboard/profile/gateway/non-live conversation and zero-external-call tests pass;
- `credential_blocked`: `.env.container` or required real credential is absent/invalid;
- `live_ready`: reserved for a separately confirmed credentialed canary that was actually run.

Task 23 does not create credentials, choose a provider, call an external provider, expose VideoBox data to the Hermes dashboard, attach Mem0 as VideoBox SSOT, or claim live readiness from static configuration. Mem0 remains a Hermes auxiliary memory only.

## Cross-cutting safety and failure rules

- User samples remain read-only. All generated media stays in project-local or ignored artifact roots.
- Browser/API network remains same-origin or loopback. Local/test external provider call count is exactly zero.
- The existing route epoch, current session revision fence, source SHA fence, one-player ownership, explicit apply, and manual fallback remain mandatory.
- Preview-proxy preparation is inspection-only. It cannot mutate timeline/session/review/output approval.
- Process restart may mark an orphaned preview job failed; a later explicit retry may rebuild it. It must never serve a partial temporary file.
- Disk-full, FFmpeg missing, unsupported/corrupt media, source mutation, stale route, and Windows path-length failures return bounded error codes and preserve the original source and editor usability.
- Generated artifacts and existing protected untracked directories are evidence, not cleanup targets.

## TDD acceptance matrix

| Slice | RED/GREEN acceptance |
| --- | --- |
| 23A identity/probe | compatible H264/AAC uses original URL; HEVC and incompatible audio select the versioned proxy profile; non-video/project mismatch is rejected |
| 23A job/cache | first request creates one job; concurrent/repeated requests reuse it; source/profile change misses cache; explicit retry follows failure; no partial output is served |
| 23A publish fence | generated H264/AAC/yuv420p output passes ffprobe; changed SHA/asset registration rejects atomic publish and leaves source untouched |
| 23A API/Range | typed 200/202/failed states; current content supports 200/206/416; filesystem/raw stderr never appears |
| 23A UI | prepare before mount, visible pending/retry/fallback, route-epoch cancellation, one native player maximum, zero editor-command calls |
| 23B Check | read-only success and precise blocked states for missing Docker/FFmpeg/CapCut/env; no secret output and no process start in default mode |
| 23B Start/Smoke | only allowed local services start; bounded health; existing harness results aggregate into a sanitized receipt; external calls remain zero |
| 23C package | read-only source hashes equal recorded inputs; disposable project receives copies; all supported media controls reach final/SRT/CapCut outputs; reverse manifest resolves every artifact |
| 23C mutation guard | no existing project mutation without IDs plus confirmation; QA selections do not become owner approval or automatic UI apply |
| 23D readiness | local/static/non-live pass maps to `local_ready`; missing credential maps to `credential_blocked`; only observed live canary can map to `live_ready` |

## Reverse runtime trace

### HEVC audition

`asset card preview click → EditorWorkbenchRoute prepare call → project/asset lookup → source SHA + ffprobe → compatible original OR durable preview job → local FFmpeg temp output → ffprobe + source-SHA recheck → atomic project-local publish → Range content URL → local URL guard → EditorWorkbench audition request → PreviewCoordinator → sole PreviewStage video element`

Reverse proof starts from the mounted player URL and resolves it back to a current ready job, exact source SHA/profile, registered project asset, and unchanged user source hash.

### Owner package

`review package manifest → final MP4/SRT/CapCut draft → current editing-session revision/timeline → applied typed B-roll/BGM/SFX/caption/TTS/overlay controls → copied project assets → recorded source SHA → read-only user sample`

### Hermes readiness

`owner-ready receipt → individual verifier receipt → checked-in pinned profile/runtime contract → dashboard/gateway loopback boundary → zero-external-call non-live run`; missing credential ends at `credential_blocked` and cannot be inferred as live success.

## Closeout protocol

Each slice requires focused RED/GREEN evidence, affected backend/frontend tests, applicable real-media smoke, code review, plan-gap review, reverse runtime/output verification, `git diff --check`, protected-residue classification, SSOT/handoff update, one logical commit, and push. Task 23 final closeout additionally runs full Python, full frontend, production build, full editor E2E, provenance/UI-system, Compose/profile/runtime/network guards, user-sample package verification, and the six-gate release audit.

## Non-goals

- SaaS auth, billing, teams, cloud storage, publishing, upload to YouTube, analytics, marketplace, and multi-user collaboration.
- OpenCut runtime/source copy, a second media player, generic effects, masks, keyframes, transitions not supported by current backend commands, or automatic editing-session apply.
- External provider selection/call, credential generation, live Mem0 activation, or Mem0 as VideoBox persistence/SSOT.
- Human taste, listening quality, copyright, publication, and final-export approval. The review package prepares these decisions but never fabricates them.

## Spec self-review record

- Placeholder scan: no unfinished marker or deferred implementation placeholder remains.
- Consistency: all four slices preserve project-local storage, source SHA, route epoch, current revision, explicit apply, one-player, and zero-external-call boundaries.
- Scope: the umbrella is decomposed into four sequential, independently testable slices; detailed implementation plans must preserve that order rather than implement all subsystems in one patch.
- Ambiguity: `ready`, `blocked`, human approval, live readiness, existing-project mutation, retry, and progress counting have explicit definitions above.
