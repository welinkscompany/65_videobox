# VideoBox Hermes Yujin Mem0 Auxiliary Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자가 명시적으로 승인한 편집 취향만 Hermes의 Mem0 보조기억에 저장하고, 이후 Yujin 추천에 제한적으로 활용하며 Mem0 장애가 대화나 편집을 막지 않게 한다.

**Architecture:** VideoBox는 memory candidate와 승인 상태만 관리한다. 실제 Mem0 Platform 자격증명과 provider adapter는 격리된 Hermes 런타임이 소유한다. 승인된 후보만 Agent Gateway 경계를 통해 Hermes Mem0에 기록되고, retrieval 결과는 정책 필터와 크기 제한을 통과한 텍스트만 creator context에 주입된다.

**Tech Stack:** Hermes official Mem0 plugin, Mem0 Platform, Python/Pydantic, FastAPI, React/TypeScript, fake provider adapters for tests

---

Parent: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-master-plan.md`
Requires: Phase C task C4 complete.

Child progress: **0/5 tasks (0.0%), remaining 100.0%**. These five tasks are D1, D2, D3, D4, and F1.

## Memory policy

Allowed examples:

- preferred pacing or cut density
- preferred subtitle style supported by current controls
- preferred BGM loudness/range
- recurring channel tone or intro/outro preference
- rejected editing preference when useful to avoid repeating it

Forbidden examples:

- passwords, API keys, OAuth tokens, cookies, auth headers
- personal payment/contact identifiers
- raw transcript or entire conversation by default
- local filesystem paths
- raw media or signed media URLs
- VideoBox DB/internal IDs not required for memory meaning
- unapproved inferred traits

Candidate states:

```text
pending → approved → stored
pending → rejected
stored → deleted
approved → failed (retryable by explicit user action)
```

No automatic transition from `pending` to `approved`.

## D1 — Add typed memory candidate and policy DTOs

- [ ] **D1** Add typed memory candidate/policy DTOs with explicit approval as the only write gate.

**Files:**

- Create: `packages/domain-models/src/videobox_domain_models/yujin_memory.py`
- Create: `packages/core-engine/src/videobox_core_engine/yujin_memory_policy.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Create: `services/api/src/videobox_api/routers/yujin_memory.py`
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `services/api/src/videobox_api/main.py`
- Create: `tests/test_yujin_memory_policy.py`
- Create: `tests/test_yujin_memory_store.py`
- Create: `tests/test_api_yujin_memory.py`

**Contract:**

```python
class MemoryCandidateStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STORED = "stored"
    FAILED = "failed"
    DELETED = "deleted"

class YujinMemoryCandidate(BaseModel):
    candidate_id: str
    project_id: str
    conversation_id: str
    source_message_ids: tuple[str, ...]
    category: Literal["pacing", "caption", "audio", "tone", "workflow"]
    proposed_text: str
    status: MemoryCandidateStatus
    created_at: datetime
```

**Endpoints:**

```text
POST /api/projects/{project_id}/director/memory-candidates
GET  /api/projects/{project_id}/director/memory-candidates
POST /api/projects/{project_id}/director/memory-candidates/{candidate_id}/approve
POST /api/projects/{project_id}/director/memory-candidates/{candidate_id}/reject
```

**RED:**

1. Test candidate creation never invokes an external provider.
2. Test policy rejection for forbidden patterns, excessive length, empty text, raw transcript, unknown category, and cross-project access.
3. Test approve is the only transition that can schedule a provider write.
4. Test repeated approve/reject operations are idempotent and conflicting terminal transitions fail safely.
5. Run focused tests and expect RED.

**GREEN:**

6. Store candidates in VideoBox as approval workflow records, not as preference truth used directly by Yujin.
7. Require explicit endpoint intent for approve/reject; never infer approval from chat wording.
8. Add audit fields for state changes without storing provider request/response bodies.
9. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_yujin_memory_policy.py tests/test_yujin_memory_store.py tests/test_api_yujin_memory.py -q
   git diff --check
   ```

10. Mark D1 `[x]`, synchronize progress, and commit:

   ```powershell
   git add packages services/api tests docs/superpowers/plans
   git commit -m "feat: add Yujin memory approval policy"
   ```

## D2 — Add Hermes-owned Mem0 Platform adapter

- [ ] **D2** Add a Hermes-owned Mem0 Platform adapter without exposing credentials or raw provider records.

**Files:**

- Modify: `config/hermes/yujin/distribution.yaml`
- Create: `config/hermes/yujin/skills/videobox-memory/SKILL.md`
- Create: `services/agent-gateway/src/videobox_agent_gateway/memory_gateway.py`
- Modify: `services/agent-gateway/src/videobox_agent_gateway/main.py`
- Modify: `services/api/src/videobox_api/agent_gateway_client.py`
- Create: `services/api/src/videobox_api/yujin_memory_service.py`
- Modify: `services/api/src/videobox_api/routers/yujin_memory.py`
- Modify: `compose.yaml`
- Modify: `.env.container.example`
- Create: `tests/test_agent_gateway_memory.py`
- Create: `tests/test_yujin_memory_service.py`
- Modify: `tests/test_hermes_yujin_compose_contract.py`
- Modify: `tests/test_hermes_yujin_profile_distribution.py`

**Adapter protocol:**

```python
class HermesMemoryGateway(Protocol):
    async def add_approved(self, request: ApprovedMemoryWrite) -> StoredMemoryRef: ...
    async def search(self, request: MemorySearch) -> tuple[RetrievedMemory, ...]: ...
    async def delete(self, request: MemoryDelete) -> None: ...
```

VideoBox-visible `StoredMemoryRef` contains only:

```python
class StoredMemoryRef(BaseModel):
    provider: Literal["mem0"]
    memory_id: str
```

**RED:**

1. Use fake Hermes/plugin and fake agent-gateway clients to test add/search/delete success, timeout, malformed response, provider rejection, and unavailable configuration.
2. Require that non-approved candidate writes are rejected before any gateway call.
3. Require compose/profile tests to prove:
   - Mem0 credential exists only in Hermes runtime configuration;
   - browser/API responses never contain it;
   - no Mem0 client is instantiated in editor/frontend code;
   - no DB/media mount is added.
4. Require all ordinary tests to assert external provider call count `0`.

**GREEN:**

5. Configure the official Hermes Mem0 plugin in Platform mode inside the isolated Yujin profile.
6. Implement the bounded command inside `videobox-agent-gateway`; it can invoke only `mem0_add`, `mem0_search`, or `mem0_delete` with typed arguments. Do not expose generic Hermes tool execution.
7. Call `mem0_add` with approved text, stable Hermes user/agent namespace, `infer=False`, and minimal metadata.
8. Map provider errors to stable public statuses while logging only operation, candidate ID, duration, and outcome.
9. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_agent_gateway_memory.py tests/test_yujin_memory_service.py tests/test_api_yujin_memory.py tests/test_hermes_yujin_compose_contract.py tests/test_hermes_yujin_profile_distribution.py -q
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-profile.ps1 -StaticOnly
   git diff --check
   ```

10. Mark D2 `[x]`, synchronize progress, and commit:

   ```powershell
   git add config/hermes/yujin compose.yaml .env.container.example services/agent-gateway services/api tests docs/superpowers/plans
   git commit -m "feat: connect approved memory to Hermes Mem0"
   ```

## D3 — Add approve, list, and delete UI

- [ ] **D3** Add approve/list/delete UI and ensure pending/rejected candidates are never injected.

**Files:**

- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/features/editor/workbench/rightDockTypes.ts`
- Modify: `apps/web/src/features/editor/workbench/RightDock.tsx`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Modify: `apps/web/src/features/editor/workbench/right-dock.test.tsx`
- Modify: `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`
- Create: `apps/web/src/features/editor/workbench/yujin-memory-panel.test.tsx`
- Create or modify the smallest right-dock memory component discovered during implementation

**RED:**

1. Test:
   - new candidates render as pending with Approve/Reject;
   - neither pending nor rejected candidate appears in applied memory context;
   - Approve requires one explicit click and shows saving/stored/failed state;
   - failed save can be retried only by explicit click;
   - Delete requires explicit click and removes the stored reference on success;
   - close/open RightDock preserves Route-owned candidate state and scroll;
   - Mem0 unavailable does not disable chat or manual editor.
2. Require API type guards to reject unknown status/category/provider fields.

**GREEN:**

3. Keep candidate state ownership in Route or durable API/store, not component-local transient state.
4. Render short policy-safe text only; do not expose source transcript or provider record.
5. Keep the memory section secondary to conversation and creator recommendations.
6. Run:

   ```powershell
   npm --prefix apps/web test -- --run src/features/editor/workbench/yujin-memory-panel.test.tsx src/features/editor/workbench/right-dock.test.tsx src/features/editor/workbench/editor-workbench-route.test.tsx
   git diff --check
   ```

7. Mark D3 `[x]`, synchronize progress, and commit:

   ```powershell
   git add apps/web docs/superpowers/plans
   git commit -m "feat: review Yujin memory in editor"
   ```

## D4 — Add retrieval injection and close Phase D

- [ ] **D4** Add bounded retrieval injection, unavailable fallback, live canary, and Phase D closeout.

**Files:**

- Modify: `packages/core-engine/src/videobox_core_engine/yujin_creator_context.py`
- Modify: `services/agent-gateway/src/videobox_agent_gateway/memory_gateway.py`
- Modify: `services/api/src/videobox_api/yujin_memory_service.py`
- Modify: `services/api/src/videobox_api/hermes_run_service.py`
- Create: `tests/test_yujin_memory_retrieval.py`
- Create: `scripts/smoke-hermes-yujin-mem0.ps1`
- Create: `docs/handoffs/2026-07-26-videobox-hermes-yujin-phase-d-closeout.ko.md`
- Modify: `docs/implementation-plan.ko.md`
- Modify: `docs/development-status-2026-06-29.ko.md`

**Retrieval limits:**

- one bounded search per new user prompt
- top-k no greater than 5
- only approved/stored preference namespace
- maximum injected characters fixed by the context model
- deterministic category/order
- provider unavailable/empty/malformed result becomes `memories=()`
- no automatic retry that can delay the chat hot path beyond its timeout

**RED:**

1. Test relevant approved retrieval, unrelated result filtering, duplicate collapse, deleted memory exclusion, malformed/oversize record rejection, timeout fallback, and zero-network fake path.
2. Test that pending/rejected/failed candidates cannot enter context even if a fake provider returns matching text.
3. Test the prompt/context marks memory as user-approved preference, not system truth or mandatory instruction.
4. Test a Mem0 outage still produces a Hermes run and manual fallback.

**GREEN:**

5. Search before context serialization with a strict timeout; on any failure continue with an empty tuple.
6. Never write retrieval output back to VideoBox as a new memory automatically.
7. Add a live canary that requires explicit `-Live` and a disposable tagged memory:
   - add only after an explicit scripted approval step;
   - retrieve it;
   - delete it;
   - confirm it is no longer returned;
   - print IDs/status only, never credentials or raw provider bodies.
8. Run non-live gate:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_yujin_memory_policy.py tests/test_yujin_memory_store.py tests/test_agent_gateway_memory.py tests/test_yujin_memory_service.py tests/test_yujin_memory_retrieval.py tests/test_api_yujin_memory.py -q
   npm --prefix apps/web test -- --run
   npm --prefix apps/web run build
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-plan-state.ps1
   git diff --check
   ```

9. If separately configured and authorized, run:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/smoke-hermes-yujin-mem0.ps1 -Live
   ```

   Otherwise report live Mem0 write/read/delete as unrun.

10. Perform spec, quality, gap, and reverse reviews. Mark D4 `[x]`, synchronize progress and SSOT, then commit and push:

   ```powershell
   git add packages services apps/web scripts tests docs
   git commit -m "feat: add approved Yujin memory"
   git push origin codex/videobox-container-compatibility
   ```

## F1 — Final integration audit and closeout

- [ ] **F1** Run independent spec/quality/gap/reverse reviews, required suites, build, provenance, SSOT/handoff, commit, and push.

**Files:**

- Create: `docs/handoffs/2026-07-26-videobox-hermes-yujin-final-closeout.ko.md`
- Modify: `docs/implementation-plan.ko.md`
- Modify: `docs/development-status-2026-06-29.ko.md`
- Modify: all five linked plans only for final statuses/evidence

**Independent review lenses:**

1. **Spec:** every design acceptance is implemented or explicitly marked out of scope.
2. **Quality:** types, bounds, errors, concurrency, cleanup, and duplication are acceptable.
3. **Gap:** no unsupported Inspector control, automatic apply, direct Hermes mutation, direct browser-to-Hermes path, secret leak, or hidden external call exists.
4. **Reverse:** trace from output/preview mutation back to explicit user selection and current revision; trace from memory injection back to stored approved candidate.

Critical findings block completion. Important findings are fixed before closeout unless the written design explicitly accepts the limitation.

**Final verification:**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_yujin_profile_contract.py tests/test_yujin_agent_package_contract.py tests/test_hermes_yujin_compose_contract.py tests/test_hermes_yujin_profile_distribution.py tests/test_agent_gateway_hermes_rpc_client.py tests/test_agent_gateway_api.py tests/test_agent_gateway_client.py tests/test_hermes_run_store.py tests/test_hermes_run_service.py tests/test_api_hermes_conversation.py tests/test_hermes_yujin_capability_lifecycle.py tests/test_yujin_creator_context.py tests/test_agent_gateway_creator_context.py tests/test_yujin_creator_proposals.py tests/test_yujin_creator_proposal_adapter.py tests/test_yujin_media_proposal_adapter.py tests/test_yujin_text_voice_overlay_proposal_adapter.py tests/test_yujin_memory_policy.py tests/test_yujin_memory_store.py tests/test_agent_gateway_memory.py tests/test_yujin_memory_service.py tests/test_yujin_memory_retrieval.py tests/test_api_yujin_memory.py -q
.\.venv\Scripts\python.exe -m pytest -q
npm --prefix apps/web test -- --run
npm --prefix apps/web run test:e2e
npm --prefix apps/web run build
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-editor-ui-source-provenance.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-editor-ui-system.ps1
npm --prefix apps/web test -- --run src/external-runtime-assets.test.ts src/test/network-guard.test.ts src/ui-system.test.tsx
Push-Location apps/web
npx --yes @cyclonedx/cyclonedx-npm@4.1.1 --package-lock-only --omit optional --output-file "$env:TEMP\videobox-hermes-yujin-sbom.json"
Pop-Location
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-runtime.ps1 -StaticOnly
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-profile.ps1 -StaticOnly
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-plan-state.ps1
docker compose config --quiet
git diff --check
git status --short
git branch --show-current
git rev-parse HEAD
git rev-parse '@{upstream}'
git rev-list --left-right --count 'HEAD...@{upstream}'
git worktree list
```

The full Python regression is mandatory for F1 because this initiative changes backend and storage code. If it cannot run or does not pass, leave F1 `[!]` or `[~]` and do not claim final completion.

Final live canaries remain separately reported:

- Yujin chat
- creator proposal/apply/preview/output
- Mem0 add/search/delete

An unavailable credential/provider is an unrun live proof, not a failed local implementation and not a passing canary.

**Closeout:**

1. Mark F1 `[x]` only after all mandatory non-live gates pass and Critical review findings are zero.
2. Set initiative progress to **20/20 (100.0%), remaining 0.0%** in master and child mirrors.
3. Keep existing VideoBox cumulative status separate; Task 9 human/CapCut acceptance remains open until a human/environment proof occurs.
4. Confirm protected untracked paths were not staged, modified, or deleted.
5. Commit and push:

   ```powershell
   git add docs
   git commit -m "docs: close Hermes Yujin integration"
   git push origin codex/videobox-container-compatibility
   ```

Expected final outcome: the owner can converse with Yujin, request supported edits, explicitly apply and preview them, keep working through runtime/memory failures, and manage only approved Hermes auxiliary memories.
