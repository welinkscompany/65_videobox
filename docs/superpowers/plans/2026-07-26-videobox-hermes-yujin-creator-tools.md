# VideoBox Hermes Yujin Creator Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Yujin이 현재 VideoBox 프로젝트를 이해해 지원되는 편집만 추천하고, 사용자가 선택한 추천만 기존 EditorCommandPort로 안전하게 적용·미리보기·출력 확인할 수 있게 한다.

**Architecture:** VideoBox API가 현재 revision의 allowlisted creator context를 만들고, Agent Gateway가 발급·소비하는 짧은 one-time context capability를 붙여 gateway에 전달한다. Gateway가 schema/revision/size를 다시 검증한 복사본만 Hermes에 보낸다. Hermes 응답은 엄격한 typed proposal envelope로 검증하고 기존 Director proposal/candidate 모델로 투영한다. 실제 mutation은 브라우저의 기존 current-revision `EditorCommandPort`와 route epoch fence가 수행한다.

**Tech Stack:** Python domain models and core engine, FastAPI/Pydantic, React/TypeScript, existing DirectorProposal DTO/API, EditorCommandPort, PreviewCoordinator/PreviewStage, Vitest/Pytest

---

Parent: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-master-plan.md`
Requires: Phase A task A4 complete.

Child progress: **0/5 tasks (0.0%), remaining 100.0%**.

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

- [ ] **B1** Build the allowlisted current-revision creator context and typed read DTOs.

**Files:**

- Create: `packages/domain-models/src/videobox_domain_models/yujin_creator_context.py`
- Create: `packages/core-engine/src/videobox_core_engine/yujin_creator_context.py`
- Create: `services/agent-gateway/src/videobox_agent_gateway/context_capabilities.py`
- Create: `services/agent-gateway/src/videobox_agent_gateway/creator_context.py`
- Modify: `services/agent-gateway/src/videobox_agent_gateway/main.py`
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `services/api/src/videobox_api/agent_gateway_client.py`
- Modify: `services/api/src/videobox_api/hermes_run_service.py`
- Create: `tests/test_yujin_creator_context.py`
- Create: `tests/test_agent_gateway_creator_context.py`
- Create: `tests/test_api_yujin_creator_context.py`

**Contract:**

```python
class YujinCreatorContext(BaseModel):
    schema_version: Literal["videobox.yujin-context.v1"]
    project_id: str
    revision: str
    selected_script_id: str | None
    selected_segment_id: str | None
    segment_summaries: tuple[SegmentSummary, ...]
    media_candidates: tuple[MediaCandidateSummary, ...]
    timeline_summary: TimelineSummary
    supported_controls: tuple[SupportedControl, ...]
```

Forbidden fields:

- host paths
- raw media bytes or signed URLs
- provider credentials
- OAuth state
- full database records
- raw Mem0 records
- internal capability token

**RED:**

1. Add tests for deterministic ordering, bounded counts/text lengths, stable schema version, real current revision, and explicit field denial.
2. Add a stale revision test: a context requested for revision N must fail if the store is already N+1.
3. Add an external-network spy and require call count `0`.
4. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_yujin_creator_context.py tests/test_api_yujin_creator_context.py -q
   ```

   Expected RED: context builder does not exist.

**GREEN:**

5. Build context only inside VideoBox from existing project store, playback manifest, asset projection, and EditorCommandPort support metadata.
6. Use a two-step gateway exchange:
   - create the run and receive a short-lived opaque `attach_context` capability bound to project/conversation/run/revision;
   - attach exactly one context with that capability;
   - gateway verifies and consumes it before prompt submission.
7. Keep the signing secret gateway-only. Phase B may use a bounded in-memory consume ledger; C3 replaces it with the complete durable issue/consume/revoke lifecycle.
8. Inject the gateway-validated serialized context into the Hermes prompt envelope; do not add a Hermes DB/media mount or browser-facing raw endpoint.
9. Reject replay, revision mismatch, or over-limit context deterministically with a user-safe error and preserve the text draft/manual editor.
10. Run focused tests and `git diff --check`.
11. Mark B1 `[x]`, synchronize progress, and commit:

   ```powershell
   git add packages services/agent-gateway services/api tests docs/superpowers/plans
   git commit -m "feat: provide bounded Yujin creator context"
   ```

## B2 — Add typed creator skills and proposal validation

- [ ] **B2** Add Yujin creator skills and validate typed recommendation/proposal responses.

**Files:**

- Modify: `config/hermes/yujin/distribution.yaml`
- Create: `config/hermes/yujin/skills/videobox-creator/SKILL.md`
- Create: `packages/domain-models/src/videobox_domain_models/yujin_creator_proposals.py`
- Create: `packages/core-engine/src/videobox_core_engine/yujin_creator_proposal_adapter.py`
- Modify: `services/api/src/videobox_api/hermes_run_service.py`
- Create: `tests/test_yujin_creator_proposals.py`
- Create: `tests/test_yujin_creator_proposal_adapter.py`
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

4. Teach the skill to return one fenced machine payload after the human reply, never executable code.
5. Parse only the machine payload; on failure persist the conversational reply but discard the proposal and show a nonblocking explanation.
6. Map validated operations into the existing Director proposal DTO instead of creating a parallel frontend proposal protocol.
7. Ensure API logs include only proposal ID, schema version, operation count, and validation outcome.
8. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_yujin_creator_proposals.py tests/test_yujin_creator_proposal_adapter.py tests/test_hermes_yujin_profile_distribution.py -q
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-profile.ps1 -StaticOnly
   git diff --check
   ```

9. Mark B2 `[x]`, synchronize progress, and commit:

   ```powershell
   git add config/hermes/yujin packages services/api tests docs/superpowers/plans
   git commit -m "feat: validate typed Yujin creator proposals"
   ```

## B3 — Implement B-roll, BGM, and SFX recommendation/apply

- [ ] **B3** Support revision-safe B-roll, BGM, and SFX recommendation/apply paths.

**Files:**

- Modify: `packages/domain-models/src/videobox_domain_models/yujin_creator_proposals.py`
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_creator_proposal_adapter.py`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Modify: `apps/web/src/features/editor/workbench/rightDockTypes.ts`
- Modify: `apps/web/src/features/editor/workbench/RightDock.tsx`
- Modify: `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`
- Modify: `apps/web/src/features/editor/workbench/right-dock.test.tsx`
- Create: `tests/test_yujin_media_proposal_adapter.py`

**TDD acceptance matrix:**

| Kind | Candidate source | Precondition | Existing command boundary | Stale completion |
|---|---|---|---|---|
| B-roll image/video | current asset projection | playable or materializable media kind | existing B-roll EditorCommandPort path | zero mutation |
| BGM | current audio candidates | materialize success and post-await fence | existing BGM command | zero mutation |
| SFX | current audio candidates | materialize success and post-await fence | existing SFX command | zero mutation |

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

4. Reuse the Task 19 materialize and post-await route/current guards; do not duplicate fetch/materialize logic inside RightDock.
5. Keep Route as asset truth and API owner. `RightDock` emits candidate selection/apply intent only.
6. Preserve real media kinds; do not label audio as video or image as generic binary.
7. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_yujin_media_proposal_adapter.py -q
   npm --prefix apps/web test -- --run src/features/editor/workbench/editor-workbench-route.test.tsx src/features/editor/workbench/right-dock.test.tsx
   git diff --check
   ```

8. Mark B3 `[x]`, synchronize progress, and commit:

   ```powershell
   git add packages apps/web tests docs/superpowers/plans
   git commit -m "feat: apply Yujin media recommendations"
   ```

## B4 — Implement supported captions, voice, overlay, and output checks

- [ ] **B4** Support only existing caption, voice/TTS, overlay, and output-check controls.

**Files:**

- Inspect first: `apps/web/src/features/editor/editorCommandPort.ts`
- Inspect first: current caption, voice, overlay, and output DTO/route implementations
- Modify only supported unions in: `packages/domain-models/src/videobox_domain_models/yujin_creator_proposals.py`
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_creator_context.py`
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_creator_proposal_adapter.py`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Modify: `apps/web/src/features/editor/workbench/RightDock.tsx`
- Create: `tests/test_yujin_text_voice_overlay_proposal_adapter.py`
- Modify: `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`

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
