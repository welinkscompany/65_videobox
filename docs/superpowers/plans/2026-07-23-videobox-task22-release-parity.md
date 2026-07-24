# VideoBox Task 22 Release Parity Executable Plan

**Goal:** Replace every remaining legacy route owner with a canonical, local-only owner, retire superseded contracts explicitly, remove the legacy shell only after parity, and pass the Task 22 release audit without weakening revision, freshness, network, provenance, or human-acceptance gates.

**Authority:** `docs/superpowers/plans/2026-07-17-videobox-oss-dashboard-editor-adoption.md` Task 22. This file only decomposes that existing requirement; it does not reduce it.

## Fixed boundaries

- Work only in `videobox-container-compatibility`; preserve `?? .tmp-final-fence-debug/`, `?? .tmp-real-video-dogfood/`, and `?? apps/web/.tmp-real-video-dogfood/`.
- Keep FastAPI editing-session/timeline/review, FFmpeg and PyCapCut authoritative.
- Use the current editing session's `timeline_id`; never fall back to an unrelated latest timeline.
- Do not add source copy, OpenCut runtime, provider/API expansion, Hermes, Mem0, cloud, billing, automatic apply, or external local/test calls.
- Do not expose unsupported editor controls.
- Do not delete `App.tsx`, legacy CSS, routes, tests, or compatibility adapters until a route/component/E2E owner proves parity.
- Task 9 human/environment acceptance and real CapCut Desktop proof remain separate.
- Official cumulative progress remains `9/22 (40.9%)`, remaining `59.1%`.

## Required parity owner matrix

Every row must have a canonical route, component test, and E2E owner before 22D. A RED inventory test keeps the row failing until the three owners exist.

| Capability | Canonical route | Component owner | E2E owner |
| --- | --- | --- | --- |
| project create/select and source ingest | `/projects`, `/projects/:id/create` | `ProjectOnboarding`, `CreationInterview` | script-first journey |
| media list, analysis, preview, cancel/retry/review | `/projects/:id/media` | `MediaWorkspacePage` | media recovery journey |
| current/global job recovery | ProductShell job status | `JobRecovery` | failed-job recovery journey |
| script draft and atomic creation | `/projects/:id/create` | `CreationInterview`, `DraftGapMedia` | script-first journey |
| timeline/review/recommendation/approval | `/projects/:id/timeline`, `/projects/:id/review` | `TimelineReviewPage` | review-to-editor journey |
| exact preview, timeline, Eugene, assets, supported mutations | `/projects/:id/editor` | `EditorWorkbenchRoute` | editor workbench journey |
| settings and voice/TTS listening review | `/settings/*` | `SettingsPage`, `VoiceTtsSettings` | voice/TTS manual-review journey |
| subtitle, exact preview reference, final, CapCut draft/handoff | `/projects/:id/outputs` | `OutputsPage` | output journey |
| loading/error/refresh/project-switch recovery | every route above | owning component | corresponding journey |

`apps/web/src/task22-parity-owners.test.ts` is the final inventory owner. It must fail while any row lacks a route/component/E2E mapping and must remain after legacy removal.

## 22A — Canonical Timeline and Review

**RED**

1. Add pure selector tests proving only the newest succeeded `timeline_build` whose `output_ref` equals the current editing session's `timeline_id` is eligible.
2. Add blocker-union tests across timeline and review payloads.
3. Add route tests for loading/error/no-session/stale A→B response and prove the canonical page exposes no approve, reopen, or recommendation mutation and calls those endpoints zero times.
4. Add blocker tests proving a duplicate recommendation ID with divergent type, target, or reason becomes an explicit non-actionable conflict while retaining every source entry.
5. Add editor route tests proving `session_id + segment_id` focuses only the valid target segment, clears an older selected clip, and does not replace the session, conversation, player, dock, or scroll state.

**GREEN**

- Add a canonical `TimelineReviewPage` used by both `/timeline` and `/review`.
- Add a typed client wrapper for the existing local review-approval GET so `is_current` and durable approval state are visible; no backend route expansion.
- Independent reverse review found the existing approve/reopen/recommendation POST contracts are job-only and do not carry an expected editing-session revision. Until a revision-safe mutation contract exists, keep the canonical page fail-closed and read-only: show durable status and blockers, but expose no approval or recommendation mutation controls.
- Merge duplicate blockers by semantic identity while retaining all original source entries. A duplicate recommendation ID with divergent type, target, or reason is an explicit conflict blocker and is never actionable.
- Link a review segment to `/projects/<projectId>/editor?session_id=<current>&segment_id=<target>`.
- Do not expose rebuild for an existing editing session.

**Focused command**

`npm --prefix apps/web test -- src/features/review/timeline-review-state.test.ts src/features/review/TimelineReviewPage.test.tsx src/app/AppRouter.test.tsx src/features/editor/workbench/editor-workbench-route.test.tsx`

## 22B — Canonical Media and Job Recovery

**RED**

1. Add media route tests for asset list, analysis status, preview/cancel/retry/review, loading/error/empty, refresh recovery, and A→B epoch fencing.
2. Add ProductShell job-status tests for current-project and global job visibility, failed-job retry, retry single-flight, refresh recovery, and no mutation on mount.
   A global row must call `retryJob(row.project_id, row.job_id)`, never the currently selected project ID.
3. Add loopback/data/blob-only network assertions for both surfaces.

**GREEN**

- Replace the ordinary `/media` empty page with a canonical media workspace that reuses existing media/analysis APIs.
- Replace the static job dropdown with a typed recovery surface that reuses `listJobs`, `listAllJobs`, and `retryJob`.
- Keep `DraftGapMedia` as the creation return-path adapter without duplicating media truth.

**Focused command**

`npm --prefix apps/web test -- src/features/media/MediaWorkspacePage.test.tsx src/features/jobs/JobRecovery.test.tsx src/app/ProductShell.test.tsx src/app/AppRouter.test.tsx`

## 22C — Remaining Editor, Voice/TTS, and Output Contracts

### 22C1 — Supported editor commands and partial regeneration

**Status (2026-07-24): complete.** Canonical Inspector/command-port owners now cover the supported editor mutations and exact, persisted partial-regeneration preflight/run/result recovery. Unsupported effects and automatic apply remain absent.

**RED**

- Extend command-port, Inspector, route, and workbench tests for split/merge, undo/redo, cut action, clear B-roll/BGM/SFX, caption style, supported overlay edit/clear, and partial-regeneration preflight/run/resume.
- Assert unsupported effects, independent caption timing, automatic apply, and backend-unsupported B-roll controls remain absent.
- Assert every mutation is current-revision bound, single-flight, A→B epoch fenced, and followed by authoritative manifest refresh on success/conflict/failure.

**GREEN**

- Expose only controls implemented by the current API and playback/final/CapCut runtime.
- Keep partial regeneration as preview → explicit run/resume; never replace the active editing session automatically.

**Focused command**

`npm --prefix apps/web test -- src/features/editor/editorCommandPort.test.ts src/features/editor/inspector/inspectorRegistry.test.ts src/features/editor/workbench/editor-workbench-route.test.tsx src/features/editor/workbench/editor-workbench.test.tsx`

### 22C2 — Canonical voice and TTS manual review

Voice/TTS parity is mandatory because the parent Task 22 requires `settings/voice` and the existing local API supports it.

**Status (2026-07-24): complete.** `/settings/voice`, `VoiceTtsSettings`, component/route tests, and `voice-tts-settings.spec.mjs` now own the local manual-review flow. Listening review remains separate from explicit revisioned editor apply.

**RED**

- Add tests for voice sample local-path registration, file upload, list/reload, candidate creation for an explicit segment, candidate list, listening approve/reject, loading/error/retry, A→B project fence, and zero automatic apply.
- Add route and E2E tests proving the settings owner is canonical and no provider/external request occurs.

**GREEN**

- Add `VoiceTtsSettings` under the canonical settings route.
- Reuse `registerVoiceSample`, `uploadVoiceSample`, `listVoiceSamples`, `generateTtsCandidate`, `listTtsCandidates`, and `reviewTtsCandidate`.
- Keep TTS replacement apply in the editor as a separate explicit revisioned action; listening approval alone never mutates an editing session.

**Focused command**

`npm --prefix apps/web test -- src/features/settings/VoiceTtsSettings.test.tsx src/app/ProductShell.test.tsx src/app/AppRouter.test.tsx`

**Focused E2E command**

Create `apps/web/e2e/voice-tts-settings.spec.mjs`, then run:

`npm --prefix apps/web run test:e2e -- e2e/voice-tts-settings.spec.mjs`

### 22C3 — Superseded legacy output contracts

**Status (2026-07-24): complete.** `/projects/:id/outputs` now owns exact-preview status reference, current-revision subtitle/final/CapCut draft/handoff and stale recovery. Legacy output mutations are unreachable from the canonical production graph; one-player ownership remains in the editor.

**RED**

- Add inventory tests proving the canonical product has no reachable call to legacy `preview_render` or `exportCapcut`.
- Add output route/E2E assertions that exact preview, final render, current CapCut draft, handoff, stale recovery, and refresh own every retained output behavior.

**GREEN**

- Explicitly retire the UI reachability of old `preview_render` and `exportCapcut`; retain backend compatibility only if another persisted-data reader still requires it.
- Do not claim real CapCut Desktop proof from the automated handoff.

**Focused command**

`npm --prefix apps/web test -- src/app/OutputsPage.test.tsx src/task22-parity-owners.test.ts && npm --prefix apps/web run test:e2e -- e2e/z-script-first-vertical.spec.mjs`

Every migrated mutation begins with an observed focused RED and preserves current revision, route epoch, one-player ownership, refresh-after-conflict, and manual fallback.

## 22D — Remove Legacy Owners

**Status (2026-07-24): complete.** The unreachable legacy shell, output adapter, CSS, App-only Director/media/session bridges, obsolete tests and stale fast-path references are removed. Canonical creation helpers and persisted preview/export readers remain.

After every row in the parity owner matrix is GREEN and 22A–22C evidence is complete:

- Route `/timeline`, `/review`, `/settings`, `/editor`, `/media`, and `/outputs` only to canonical owners.
- Reduce `App.tsx` to root composition or remove it if `AppRoot` owns composition.
- Delete unused legacy CSS/components/tests only after `rg` and UI-system AST inventory prove no owner remains.
- Preserve persisted-data adapters that still serve current data.
- Run provenance, license/SBOM, rejected-import, external-network, and legacy-class inventories.

## 22E — Six-gate independent release audit

**Status (2026-07-24): complete.** Independent spec/quality/gap/reverse reviews found and closed output/session/review fences, PostgreSQL lock ordering, rejected-SFX identity, overlay duplication, Windows path-length, and final-render orphan/restart/thread-start claim recovery blockers. Current FFmpeg/SRT/PyCapCut artifacts were traced back to current editing-session/timeline/revision rows.

Execute and record all six gates from `docs/superpowers/plans/2026-07-13-release-audit-protocol.ko.md` against the current Task 22 baseline:

1. Independent code-quality review of the complete Task 22 diff.
2. Plan/spec/parity-gap review connecting every matrix row and explicit requirement to code, test, or pending human evidence.
3. Source-to-runtime reverse trace from current local FFmpeg/PyCapCut artifacts back to editing session, timeline, source and subtitle contracts.
4. Full-system verification commands from 22F.
5. Document/instruction review covering `AGENTS.md`, fast-path, implementation plan, status pointer, and handoff consistency.
6. Residue inventory/classification as preserve-evidence, tracked-source, historical-reference, or safe-to-delete. Never delete `?? .tmp-final-fence-debug/`, `?? .tmp-real-video-dogfood/`, or `?? apps/web/.tmp-real-video-dogfood/`.

Close every Critical/Important finding and re-run the affected gate. Human CapCut Desktop/listening approval remains explicitly pending when not observed.

## 22F — Release verification and closeout

**Status (2026-07-24): complete.** Current-focused, full frontend, build, full E2E, final Python regression, provenance/UI/network/SBOM, 600-second smoke and three-profile long-form QA were executed; this plan, SSOT and handoff form the single closeout commit/push unit. Human listening and real CapCut Desktop proof remain separate.

Run fresh:

1. `./scripts/dev-fast-path.ps1 -Mode current-focused`
2. `npm --prefix apps/web test`
3. `npm --prefix apps/web run build`
4. `npm --prefix apps/web run test:e2e`
5. `.venv\Scripts\python.exe -m pytest -q`
6. `./scripts/verify-editor-ui-source-provenance.ps1`
7. `./scripts/verify-editor-ui-system.ps1`
8. `npm --prefix apps/web test -- src/external-runtime-assets.test.ts src/test/network-guard.test.ts`
9. `./scripts/dev-fast-path.ps1 -Mode smoke`
10. `./scripts/dev-fast-path.ps1 -Mode long-form-capcut-qa`
11. `git diff --check`, scoped diff, `git status --short`, current branch/HEAD/upstream divergence, and `git worktree list`

Update the parent Task 22 checklist, implementation-plan pointer, development-status authoritative section, and final handoff only from observed evidence. Commit one logical closeout and push. Report real CapCut Desktop/listening/human gates separately and never replace them with automation.
