# VideoBox Hermes Yujin Creator Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Yujin이 현재 VideoBox 프로젝트를 이해해 지원되는 편집만 추천하고, 사용자가 선택한 추천만 기존 EditorCommandPort로 안전하게 적용·미리보기·출력 확인할 수 있게 한다.

**Architecture:** VideoBox API가 현재 revision의 allowlisted creator context를 만들고, Agent Gateway가 발급·소비하는 짧은 one-time context capability를 붙여 gateway에 전달한다. Gateway가 schema/revision/size를 다시 검증한 복사본만 Hermes에 보낸다. Hermes 응답은 엄격한 typed proposal envelope로 검증하고 기존 Director proposal/candidate 모델로 투영한다. 실제 mutation은 브라우저의 기존 current-revision `EditorCommandPort`와 route epoch fence가 수행한다.

**Tech Stack:** Python domain models and core engine, FastAPI/Pydantic, React/TypeScript, existing DirectorProposal DTO/API, EditorCommandPort, PreviewCoordinator/PreviewStage, Vitest/Pytest

---

Parent: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-master-plan.md`
Requires: Phase A task A4 complete.

Child progress: **4/5 tasks (80.0%), remaining 20.0%**.

## Supported-control rule

Before each task, inspect the actual `EditorCommandPort` and backend DTO. The exposed Inspector control matrix must be generated from real supported operations, not from OpenCut UI concepts or model suggestions.

Initial allowed recommendation kinds:

```text
broll
bgm
sfx
caption
voice
overlay
output_check
```

A kind may remain in the domain union only when a current backend/command implementation and focused apply test exist. Otherwise reject it as `unsupported_kind` and do not render an Apply button.

## B1 — Build current-revision creator context

- [x] **B1** Build the allowlisted current-revision creator context and typed read DTOs.

**Files:**

- Create: `packages/domain-models/src/videobox_domain_models/yujin_creator_context.py`
- Create: `packages/core-engine/src/videobox_core_engine/yujin_creator_context.py`
- Create: `services/agent-gateway/src/videobox_agent_gateway/creator_context.py`
- Modify: `services/agent-gateway/src/videobox_agent_gateway/main.py`
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `services/api/src/videobox_api/agent_gateway_client.py`
- Modify: `services/api/src/videobox_api/hermes_run_service.py`
- Modify: `services/api/src/videobox_api/routers/hermes_conversation.py`
- Modify: `services/api/src/videobox_api/main.py` only if dependency wiring requires it
- Modify: `packages/storage-abstractions/src/videobox_storage/sqlite_schema.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/postgres_schema.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Modify: matching existing gateway/API/frontend tests
- Create: `tests/test_yujin_creator_context.py`
- Create: `tests/test_agent_gateway_creator_context.py`
- Create: `tests/test_api_yujin_creator_context.py`

**Contract:**

```python
class YujinCreatorContext(BaseModel):
    schema_version: Literal["videobox.yujin-context.v1"]
    project_id: str
    session_id: str
    session_revision: int
    asset_index_revision: int
    timeline_id: str
    timeline_version: str
    selected_script_id: str | None
    selected_segment_id: str | None
    segment_summaries: tuple[SegmentSummary, ...]
    media_candidates: tuple[MediaCandidateSummary, ...]
    timeline_summary: TimelineSummary
    supported_controls: tuple[SupportedControl, ...]
```

Forbidden fields:

- host paths
- `storage_uri`, `asset_uri`, URL, path, raw media bytes, or full metadata
- provider credentials
- OAuth state
- full database records
- raw Mem0 records
- internal gateway ticket

Builder and bound rules:

- backend-only builder reads only the `LocalProjectStore` selected project/session/timeline, project-materialized assets, and pure playback manifest; it must not import frontend projection or the global `MediaLibraryStore`
- caller supplies `expected_session_revision: int` and optional `selected_segment_id`; selection must belong to that exact session revision
- read session and asset-index revision before collection and re-read both after collection; mismatch fails before gateway reservation, context attach, or Hermes prompt
- playback source must be `current` and match the selected session/revision
- deterministic order is segments `(start_sec, segment_id)`, media `(kind, asset_id)`, controls `kind`
- at most 32 segment summaries and 48 project media candidates
- segment text is at most 256 UTF-8 bytes, media title 128 UTF-8 bytes, and at most 8 tags of 64 UTF-8 bytes each
- canonical context JSON is at most 48,000 bytes; collection/text truncation is deterministic and the strict final payload is rejected if still oversized
- `selected_script_id` comes only from `session.script_asset_id`
- B1 controls are discovery metadata only: `broll/bgm/sfx/caption/voice/overlay` use `recommendation_only`, while `output_check` is `read_only`; they grant no Apply authority and do not define B4's apply matrix

**RED:**

1. Add tests for strict nested DTOs, deterministic ordering/truncation, separate session/asset revisions, stable schema version, current playback fence, and forbidden field denial.
2. Add stale and TOCTOU tests: expected revision mismatch, selected-segment mismatch, or pre/post session/asset-index change must fail before gateway reservation/attach/prompt.
3. Add an external/provider-network spy and require call count `0`.
4. Add gateway state-machine tests for reservation, one attach, one stream, replay/expiry/mismatch/schema/size rejection, bounded ledger, and concurrent atomic ownership. Every invalid path must keep `HermesRpcClient.stream_prompt` call count `0`.
5. Add API/frontend tests for exact expected revision/selection request, idempotency identity, stale `409`, redacted preparation failure, and draft/manual editor preservation.
6. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_yujin_creator_context.py tests/test_api_yujin_creator_context.py -q
   ```

   Expected RED: context builder does not exist.

**GREEN:**

7. Build the bounded context only inside VideoBox from the allowed local snapshot sources.
8. Add a gateway-only opaque attach-ticket state machine without touching `hermes_capability_authority`, Ed25519 issuance, public capability routes, durable revoke/audit, or key rotation:
   - authenticated `POST /internal/hermes/runs` creates a reservation and returns a 30-second high-entropy opaque `attach_context` ticket bound to exact project/conversation/run/session/session-revision/asset-index-revision identity
   - authenticated `POST /internal/hermes/runs/{run_id}/context` receives the ticket only in a private header, validates identity/schema/revisions/48,000-byte limit, consumes it exactly once, and stores validated canonical context
   - authenticated `POST /internal/hermes/runs/{run_id}/stream` streams exactly once only after attach
   - the raw attach ticket expires after 30 seconds; a successfully attached context gets a separate 300-second queue TTL
   - authenticated idempotent `DELETE /internal/hermes/runs/{run_id}` releases rejected/cancelled prepared state
   - ledger holds at most 64 entries, compares a ticket digest instead of raw ticket, and removes consumed/released/expired state
   - retire the context-free `/internal/hermes/stream` production bypass
9. Put the gateway-validated canonical context and user text inside one escaped, delimited JSON data block labeled `untrusted_creator_context`, preceded by a fixed trusted instruction that forbids following embedded instructions, requesting credentials, or invoking tools. Neither data field is a system/tool instruction and B1 returns recommendation-only free text.
10. Require `expected_session_revision >= 1` and optional `selected_segment_id` in public run creation. Same `client_message_id` is idempotent only when session, text, expected revision, and selection all match.
11. After local durable begin, API creates the gateway reservation and attaches the already-built context before prompt dispatch. Ticket data is never returned to the browser or stored in Director metadata/DB. Preparation failure settles the owned durable run blocked and returns a redacted error before `201`.
12. A non-legacy stale durable `pending` row is owner-token CAS reclaimed after 300 seconds and re-prepared with the same exact context identity. A live pending owner returns an in-progress failure instead of a false local terminal. Migrated legacy terminal rows replay without dispatch; migrated legacy pending rows are atomically settled blocked with manual fallback.
13. Run focused tests and `git diff --check`.
14. Leave B1 `[~]` for controller review; do not update progress or SSOT closeout. Commit only explicitly staged files:

   ```powershell
   git add <only-the-files-actually-modified-for-B1>
   git commit -m "feat: provide bounded Yujin creator context"
   ```

## B2 — Add typed creator skills and proposal validation

- [x] **B2** Add Yujin creator skills and validate typed recommendation/proposal responses.

**Files:**

- Modify: `config/hermes/yujin/distribution.yaml`
- Create: `config/hermes/yujin/skills/videobox-creator/SKILL.md`
- Create: `packages/domain-models/src/videobox_domain_models/yujin_creator_proposals.py`
- Create: `packages/core-engine/src/videobox_core_engine/yujin_creator_proposal_adapter.py`
- Modify: `services/api/src/videobox_api/hermes_run_service.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Modify: `scripts/verify-hermes-yujin-profile.ps1`
- Create: `tests/test_yujin_creator_proposals.py`
- Create: `tests/test_yujin_creator_proposal_adapter.py`
- Modify: `tests/test_hermes_run_service.py`
- Modify: `tests/test_hermes_yujin_profile_distribution.py`

**Response envelope:**

```python
class YujinCreatorResponse(BaseModel):
    schema_version: Literal["videobox.yujin-response.v1"]
    reply_text: str
    proposal: YujinProposal | None

class YujinProposal(BaseModel):
    proposal_id: str
    base_revision: str
    title: str
    rationale: str
    operations: tuple[YujinOperation, ...]
```

Each operation must carry:

- discriminated supported `kind`
- target script/segment/track identifiers
- typed parameters with bounds
- `requires_materialization`
- human-readable preview summary

**RED:**

1. Test rejection for:
   - unknown schema version;
   - unknown operation kind;
   - missing target;
   - non-current base revision;
   - duplicate operation IDs;
   - absolute paths/URLs/secrets in parameters;
   - an operation unsupported by the current control matrix;
   - prose or markdown pretending to be JSON.
2. Test that a valid proposal is projected into existing Director proposal candidates but does not call any mutation.
3. Run focused tests and expect RED.

**GREEN:**

4. Teach the skill to return exactly one trailing
   `videobox-yujin-response` fenced JSON payload after the human reply, never
   executable code. The payload `reply_text` must equal the trimmed visible
   prefix.
5. Parse only that payload. Withhold any partial opening fence from SSE and
   publish no machine bytes after a fence begins. On failure persist only the
   conversational prefix plus a nonblocking manual fallback, never raw machine
   JSON.
6. Rebuild the current creator context before terminal projection. A changed
   session/asset/context discards only the proposal and keeps the human reply
   plus manual fallback.
7. Map a valid response into the existing Director proposal/candidate DTO as
   immutable `candidate_only`, with null preview URI and no materialization,
   apply, or editing-session mutation. Do not create a parallel frontend
   protocol.
8. Save the candidate-only proposal and link the assistant message inside the
   owned terminal CAS transaction. A CAS loser must save neither an orphan nor
   a duplicate proposal. Log only proposal ID, schema version, operation count,
   and validation outcome.
9. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_yujin_creator_proposals.py tests/test_yujin_creator_proposal_adapter.py tests/test_hermes_yujin_profile_distribution.py -q
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-profile.ps1 -StaticOnly
   git diff --check
   ```

10. Mark B2 `[x]`, synchronize progress, and commit:

   ```powershell
   git add config/hermes/yujin packages services/api tests docs/superpowers/plans
   git commit -m "feat: validate typed Yujin creator proposals"
   ```

## B3 — Implement B-roll, BGM, and SFX recommendation/apply

- [x] **B3** Support revision-safe B-roll, BGM, and SFX recommendation/apply paths.

**Files:**

- Modify: `packages/core-engine/src/videobox_core_engine/yujin_creator_proposal_adapter.py`
- Modify: `packages/core-engine/src/videobox_core_engine/director_proposal_service.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Modify: `services/api/src/videobox_api/hermes_run_service.py`
- Modify: `services/api/src/videobox_api/routers/director_proposals.py`
- Modify: `config/hermes/yujin/skills/videobox-creator/SKILL.md`
- Modify: `apps/web/src/features/editor/editorCommandPort.ts`
- Modify: `apps/web/src/features/editor/editorCommandPort.test.ts`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Modify: `apps/web/src/features/editor/workbench/rightDockTypes.ts`
- Modify: `apps/web/src/features/editor/workbench/RightDock.tsx`
- Modify: `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`
- Modify: `apps/web/src/features/editor/workbench/right-dock.test.tsx`
- Create: `tests/test_yujin_media_proposal_adapter.py`
- Modify: `tests/test_hermes_run_service.py`
- Modify: `tests/test_api_media_director.py`

**Narrow B3 contract amendment (2026-07-27):**

- Only context media kinds `raw_video` and `broll_video` may become actionable
  B-roll. `image` and every B4 kind remain non-actionable/manual fallback.
- The saved proposal may become `ready` only after a fresh creator-context recheck
  and server-side attestation of the exact asset/type, current bytes SHA-256,
  media revision, eligibility, asset-index revision, editing session, and segment
  alignment. A proposal with no actionable B3 candidate remains `candidate_only`.
- RightDock only projects typed details and emits selection/apply intent. It must
  disable non-actionable, stale, wrong-status, and wrong-revision candidates.
- Route owns the first mutation: await the existing Director candidate materialize
  endpoint, recheck route/director epoch and current revision after the await, then
  call `EditorCommandPort.applyMedia`. Yujin B3 never uses `batchApply`.
- Existing generic candidate gates and legacy Director apply/batch behavior remain
  unchanged. Yujin preview/materialize re-attest the exact current asset truth,
  while Yujin direct REST apply/batch routes are proposal-level forbidden so the
  only edit mutation path remains the current-revision `EditorCommandPort`.

**TDD acceptance matrix:**

| Kind | Candidate source | Precondition | Existing command boundary | Stale completion |
|---|---|---|---|---|
| B-roll video | current `raw_video`/`broll_video` projection | exact target segment start/duration; `contain → fit`, `cover → crop` | materialize, then existing B-roll `applyMedia` path | zero mutation |
| BGM | current `bgm` candidate | start matches exactly one segment; optional duration equals that segment; volume/fades only | materialize, then existing BGM `applyMedia` path | zero mutation |
| SFX | current `sfx` candidate | start equals the target segment start; volume only | materialize, then existing SFX `applyMedia` path | zero mutation |
| Image/B4/deferred | current context only | never actionable in B3 | manual fallback only | zero mutation |

**RED:**

1. Add backend adapter tests for valid asset IDs, media-kind preservation, duration/placement bounds, and unsupported asset rejection.
2. Add frontend tests that require:
   - proposal display does not mutate;
   - only the selected proposal/operation applies;
   - `baseRevision !== currentRevision` disables Apply;
   - route epoch change during materialize yields zero mutation;
   - materialize failure yields zero mutation and preserves manual editor;
   - double-click or duplicate completion applies once.
3. Run focused tests and expect at least one intentional failure for each kind.

**GREEN:**

4. Reuse the Task 19 candidate materialize API and post-await
   route/director-epoch/current-revision guards; do not duplicate fetch/materialize
   logic inside RightDock.
5. Keep Route as asset truth and API owner. `RightDock` emits candidate selection/apply intent only.
6. Preserve real media kinds; do not label audio as video or admit image into the
   actionable B-roll path.
7. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_yujin_media_proposal_adapter.py -q
   npm --prefix apps/web test -- --run src/features/editor/workbench/editor-workbench-route.test.tsx src/features/editor/workbench/right-dock.test.tsx
   git diff --check
   ```

8. After controller review, mark B3 `[x]`, synchronize progress, and commit:

   ```powershell
   git add packages apps/web tests docs/superpowers/plans
   git commit -m "feat: apply Yujin media recommendations"
   ```

## B4 — Implement supported captions, voice, overlay, and output checks

- [x] **B4** Support only existing caption, voice/TTS, overlay, and output-check controls.

**Files:**

- Inspect first: `apps/web/src/features/editor/editorCommandPort.ts`
- Inspect first: current caption, voice, overlay, and output DTO/route implementations
- Modify only supported unions in: `packages/domain-models/src/videobox_domain_models/yujin_creator_proposals.py`
- Modify: `packages/domain-models/src/videobox_domain_models/yujin_creator_context.py`
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_creator_context.py`
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_creator_proposal_adapter.py`
- Modify: `packages/core-engine/src/videobox_core_engine/director_proposal_service.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Modify: `services/api/src/videobox_api/hermes_run_service.py`
- Modify: `services/api/src/videobox_api/routers/director_proposals.py`
- Modify: `config/hermes/yujin/skills/videobox-creator/SKILL.md`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Modify: `apps/web/src/features/editor/workbench/rightDockTypes.ts`
- Modify: `apps/web/src/features/editor/workbench/RightDock.tsx`
- Create: `tests/test_yujin_text_voice_overlay_proposal_adapter.py`
- Modify: `tests/test_yujin_creator_context.py`
- Modify: `tests/test_hermes_run_service.py`
- Modify: `tests/test_api_media_director.py`
- Modify: `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`
- Modify: `apps/web/src/features/editor/workbench/right-dock.test.tsx`

**Narrow B4 contract amendment (2026-07-28):**

- Caption recommendations may call only the existing `setCaptionText` command or
  the complete existing eleven-field `setCaptionStyle` DTO. Independent caption
  timing and the old `placement` shortcut are unsupported.
- Voice recommendations may reference only a persisted TTS candidate whose
  technical status is accepted and whose listening review is approved for the
  exact current segment and asset. Creator context exposes that bounded identity,
  and context construction plus terminal proposal activation fence the TTS
  candidate truth. Free-form voice text, speed, sample, or provider selection is
  unsupported.
- Overlay recommendations use only the existing exact discriminated commands:
  explanation card (`title/body/text`), image (`asset_id/text`) with a current
  project image-asset attestation, or table (`columns/rows/text`). The old generic
  `x/y/opacity` shape and every generic effect payload are unsupported.
- `output_check` is a separate read-only finding. B4 supports only
  `timeline_gaps`, derived from the fenced creator-context timeline summary. It
  is never selectable and cannot call preview render, final render, export, or
  any other mutation. Claims for missing media, preview readiness, export
  readiness, or CapCut freshness remain unavailable until an authoritative
  bounded read model exists.
- A mixed B3/B4 proposal may use one generalized Yujin actionable mode, but the
  existing B3 media mode remains readable. Direct Yujin proposal apply/batch
  stays forbidden. RightDock emits only one explicit selection; Route owns the
  current-revision/route-epoch preflight and exactly one typed
  `EditorCommandPort` mutation.
- Unsupported OpenCut effect, transition, keyframe, mask, filter, animation, and
  automatic apply remain rejected. Manual editor controls and the single
  `PreviewStage` player remain available if Yujin is unavailable.

**TDD acceptance matrix:**

| Kind | Proven input | Existing command boundary | Non-actionable/rejected |
|---|---|---|---|
| Caption text | current segment plus bounded text | `setCaptionText` | placement, independent timing |
| Caption style | complete existing eleven-field style DTO | `setCaptionStyle`, current caption scope | partial/unknown style payload |
| Voice/TTS | current approved candidate ID, asset ID, segment ID | `applyTtsCandidate` | text, speed, sample/provider choice, stale/unapproved candidate |
| Explanation overlay | title, body, text | `applyOverlay(explanation-card)` | generic effect fields |
| Image overlay | current image asset ID, text | `applyOverlay(image)` | absent/wrong-kind/stale asset, x/y/opacity |
| Table overlay | bounded columns, rows, text | `applyOverlay(table)` | malformed table or generic effect fields |
| Output check | fenced timeline `gap_count` | read-only finding, zero command | preview/export/render/CapCut readiness claims |

**Reverse runtime trace:**

1. A saved operation is derived only from a fresh creator-context identifier and
   exact supported payload; unsupported shapes fail before persistence.
2. Terminal persistence rechecks current session, asset index, referenced image
   asset or approved TTS candidate, and keeps output findings read-only.
3. RightDock display has zero mutation and cannot select a read-only or stale
   entry.
4. Explicit Apply reaches Route, which checks route/director epoch and current
   revision before and after any await, then invokes exactly one existing typed
   command.
5. The command advances one editing-session revision; the normal reload path
   refreshes the existing one-player preview. Failure or staleness advances no
   revision and leaves manual editing available.

**RED:**

1. Build a test-generated support matrix from actual backend/port capabilities.
2. For every supported control, add a happy-path proposal/apply test.
3. For every named but unsupported OpenCut effect, add a rejection test and require no Inspector Apply UI.
4. Require captions/text length, time range, volume, voice identifier, and overlay bounds to use the existing DTO constraints.
5. Require `output_check` to be read-only and incapable of starting render/export.

**GREEN:**

6. Extend only operations proven by the matrix. Remove kinds from the visible list if implementation evidence is missing.
7. Use existing caption, voice/TTS, overlay, and readiness commands; do not add a generic “effect payload” escape hatch.
8. Label read-only output findings separately from actionable recommendations.
9. Run focused backend/frontend tests and `git diff --check`.
10. Mark B4 `[x]`, synchronize progress, and commit:

   ```powershell
   git add packages apps/web tests docs/superpowers/plans
   git commit -m "feat: add supported Yujin editing controls"
   ```

## B5 — Prove explicit apply, preview, and output reverse path

- [ ] **B5** Prove explicit apply, one-player preview, output reverse smoke, manual fallback, and Phase B closeout.

**Files:**

- Modify: `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`
- Modify: `apps/web/src/features/editor/workbench/right-dock.test.tsx`
- Modify: `apps/web/src/features/editor/preview/preview-coordinator.test.ts`
- Modify: `apps/web/src/features/editor/preview/preview-stage.test.tsx`
- Create: `scripts/smoke-hermes-yujin-creator-flow.ps1`
- Create: `docs/handoffs/2026-07-26-videobox-hermes-yujin-phase-b-closeout.ko.md`
- Modify: `docs/implementation-plan.ko.md`
- Modify: `docs/development-status-2026-06-29.ko.md`

**Reverse trace acceptance:**

```text
current revision context
→ Hermes typed response
→ schema/control validation
→ Director proposal candidate
→ Inspector displays candidate
→ zero mutation before click
→ user selects Apply
→ route epoch/current revision fence
→ EditorCommandPort
→ PreviewCoordinator
→ sole PreviewStage player
→ existing output readiness/output route
```

**RED:**

1. Add an end-to-end component test proving mutation call count remains `0` until explicit Apply.
2. Add a one-player test that fails if RightDock mounts a media player or bypasses PreviewCoordinator.
3. Add stale proposal, stale async materialize, unsupported effect, Hermes stopped, and output-not-ready tests.
4. Add a scroll/state test: close/open Inspector preserves conversation, selected candidate, player ownership, and scroll restoration.

**GREEN and verification:**

5. Implement only missing wiring revealed by the tests.
6. Add a non-live creator smoke using a fake Hermes response and real local VideoBox API/store.
7. Add an explicit `-Live` smoke that uses a disposable project/sample asset copy, requests one harmless supported edit, requires human-like explicit apply simulation, checks preview manifest/output readiness, and never overwrites source media.
8. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_yujin_creator_context.py tests/test_yujin_creator_proposals.py tests/test_yujin_creator_proposal_adapter.py tests/test_yujin_media_proposal_adapter.py tests/test_yujin_text_voice_overlay_proposal_adapter.py -q
   npm --prefix apps/web test -- --run src/features/editor/workbench src/features/editor/preview/preview-coordinator.test.ts src/features/editor/preview/preview-stage.test.tsx
   .\.venv\Scripts\python.exe -m pytest -q
   npm --prefix apps/web test -- --run
   npm --prefix apps/web run test:e2e:editor-workbench
   npm --prefix apps/web run build
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-editor-ui-source-provenance.ps1
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/smoke-hermes-yujin-creator-flow.ps1
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-plan-state.ps1
   git diff --check
   ```

9. Run the live smoke only when local Hermes/provider credentials are configured:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/smoke-hermes-yujin-creator-flow.ps1 -Live
   ```

10. Perform spec, quality, gap, and reverse reviews. Critical findings block closeout; Important findings are fixed or explicitly accepted in the handoff.
11. Mark B5 `[x]`, synchronize progress and SSOT, commit and push:

   ```powershell
   git add apps/web packages services scripts tests docs
   git commit -m "feat: complete Yujin creator editing flow"
   git push origin codex/videobox-container-compatibility
   ```

Expected Phase B outcome: B-roll, music, SFX, and only genuinely supported text/voice/overlay controls can be recommended; nothing applies automatically; the existing single preview player and output path remain authoritative.
