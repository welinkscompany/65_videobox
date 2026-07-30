# VideoBox Hermes Yujin Mem0 Auxiliary Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자가 명시적으로 승인한 편집 취향만 Hermes의 Mem0 보조기억에 저장하고, 이후 Yujin 추천에 제한적으로 활용하며 Mem0 장애가 대화나 편집을 막지 않게 한다.

**Architecture:** VideoBox는 memory candidate와 승인 상태만 관리한다. 실제 Mem0 Platform 자격증명과 provider adapter는 격리된 Hermes 런타임이 소유한다. 승인된 후보만 Agent Gateway 경계를 통해 Hermes Mem0에 기록되고, retrieval 결과는 정책 필터와 크기 제한을 통과한 텍스트만 creator context에 주입된다.

**Tech Stack:** Hermes official Mem0 plugin, Mem0 Platform, Python/Pydantic, FastAPI, React/TypeScript, fake provider adapters for tests

---

Parent: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-master-plan.md`
Requires: Phase C task C4 complete.

Child progress: **4/5 tasks (80.0%), remaining 20.0%**. These five tasks are D1, D2, D3, D4, and F1.

> 2026-07-30 D4 closeout: the explicit RightDock producer and bounded
> approved+stored retrieval passed independent spec/quality/gap/reverse review
> with `Critical 0 / Important 0 / Minor 0`. The live Mem0 canary remains
> separately unrun because no live environment or authority was supplied.

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

- [x] **D1** Add typed memory candidate/policy DTOs with explicit approval as the only write gate.

**2026-07-30 source-grounded D1 amendment:**

- D1 is a local approval-workflow slice only. Candidate create/approve/reject
  performs Hermes, Gateway, Mem0, provider, network and editing mutation `0`;
  it does not enqueue or imply a provider write. D2 is the first slice allowed
  to attempt an approved write.
- Add the fixed visible scope `creator`. A candidate remains sourced from one
  exact project/conversation, but it is not project/editing truth. D2 must map
  this fixed scope to a stable isolated Hermes user/agent namespace instead of
  exposing a VideoBox internal ID.
- Candidate IDs are server-generated. Create requires a bounded
  `client_request_id`; exact replay in the same project/conversation returns
  the original row, while reuse with different canonical input is a conflict.
- D1 POST is an explicit user-initiated request to make a pending candidate
  from already-owned conversation messages. It is not hidden chat inference
  and Hermes does not write the workflow table directly.
- Require `1..8` unique source message IDs and verify every ID belongs to the
  named current project/conversation. Canonicalize them by durable conversation
  message order before fingerprinting and persistence. Do not reuse
  `director_preferences` or static `UserPreferenceConsent` as memory authority.
- Persist candidate state and a body-free lifecycle audit atomically. Invalid
  policy input persists neither a candidate nor an audit row. Same approve or
  reject is idempotent; the opposite terminal decision is a fixed conflict.
- Add tables through the shared SQLite schema used to derive PostgreSQL schema,
  and verify common Local/PostgreSQL store behavior. A SQLite-only D1 is not
  complete.
- Policy limits are deterministic and reusable: supported category and fixed
  `creator` scope only, short single-line canonical text, bounded UTF-8 size,
  no full source-message echo, secret/auth/token/password/API-key/JWT,
  contact/payment identifier, or local/UNC/file path. Public errors never echo
  rejected text.
- Candidate listing is deterministic and bounded to the latest 100 rows. D1
  request-validation and policy errors use fixed non-echo public codes.

**Files:**

- Create: `packages/domain-models/src/videobox_domain_models/yujin_memory.py`
- Create: `packages/core-engine/src/videobox_core_engine/yujin_memory_policy.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/sqlite_schema.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/postgres_schema.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Create: `services/api/src/videobox_api/routers/yujin_memory.py`
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `services/api/src/videobox_api/main.py`
- Create: `tests/test_yujin_memory_policy.py`
- Create: `tests/test_yujin_memory_store.py`
- Create: `tests/test_api_yujin_memory.py`
- Modify: `tests/test_postgres_project_store.py`

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
    client_request_id: str
    project_id: str
    conversation_id: str
    memory_scope: Literal["creator"]
    source_message_ids: tuple[str, ...]
    category: Literal["pacing", "caption", "audio", "tone", "workflow"]
    proposed_text: str
    status: MemoryCandidateStatus
    created_at: datetime
    updated_at: datetime
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
3. Test D1 approve records explicit consent but schedules and performs no
   provider write; D2 is the only planned provider boundary.
4. Test repeated approve/reject operations are idempotent and conflicting terminal transitions fail safely.
5. Test create idempotency/fingerprint conflicts, exact message ownership,
   atomic body-free audit, SQLite/PostgreSQL parity, and editing mutation `0`.
   Also test audit-failure rollback, configured Gateway/provider call `0`,
   bounded deterministic listing, canonical source order, and validation
   response non-echo.
6. Run focused tests and expect RED.

**GREEN:**

7. Store candidates in VideoBox as approval workflow records, not as preference truth used directly by Yujin.
8. Require explicit endpoint intent for approve/reject; never infer approval from chat wording.
9. Add audit fields for state changes without storing proposed/source/provider request/response bodies.
10. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_yujin_memory_policy.py tests/test_yujin_memory_store.py tests/test_api_yujin_memory.py -q
   git diff --check
   ```

11. Mark D1 `[x]`, synchronize progress, and commit:

   ```powershell
   git add packages services/api tests docs/superpowers/plans
   git commit -m "feat: add Yujin memory approval policy"
   ```

**2026-07-30 closeout evidence:**

- Candidate create/list/approve/reject is a local approval workflow only.
  Gateway, Hermes, Mem0, provider, network, and editor mutation remain `0`.
- Policy and durable-store guards reject raw transcript echoes, secret/token/
  credential patterns, Korean sensitive labels, contact/payment identifiers,
  local/UNC/tilde/dot-relative/drive-relative paths, remote/web URIs,
  post-NFKC length expansion, and hidden control characters.
- Candidate plus body-free audit writes are atomic. A per-candidate monotonic
  `event_order` makes the reverse trace deterministic even when lifecycle
  timestamps are identical.
- Fresh focused verification: `96 passed`. Related Director/API/PostgreSQL
  regression: `39 passed, 34 skipped`. A separate disposable PostgreSQL 16
  D1 workflow test passed and its container was removed.
- Independent spec and quality/gap/reverse reviews finished with
  `Critical 0 / Important 0 / Minor 0`, PASS. External provider/Mem0 live
  calls were not run and are not claimed.

## D2 — Add Hermes-owned Mem0 Platform adapter

- [x] **D2** Add a Hermes-owned Mem0 Platform adapter without exposing credentials or raw provider records.

### 2026-07-30 source-grounded D2 amendment

The originally planned direct activation of the official Mem0 provider in the
interactive Yujin profile is forbidden. The exact pinned Hermes image
`nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787`
(OCI revision `e89bc58a5ba80ec6be19b43beca37cbb03091afd`, Hermes
`v2026.7.7.2`) automatically prefetches memory and calls
`sync_turn(..., infer=True)` for ordinary conversation turns when its Mem0
provider is active. Its system prompt also permits unrequested `mem0_add`.
That behavior conflicts with VideoBox's explicit-approval-only contract and
would make pending/rejected provider-call count greater than zero.

The pinned Hermes RPC surface also has no deterministic public external
`tool.execute` operation. Asking the model to call `mem0_add` would therefore
be nondeterministic and retry-unsafe. Mem0 Platform V3 add may return an
asynchronous `event_id`, not a durable memory ID, so an event ID must never be
reported or persisted as a memory ID.

Authoritative evidence:

- pinned Hermes Mem0 plugin:
  `https://raw.githubusercontent.com/NousResearch/hermes-agent/v2026.7.7.2/plugins/memory/mem0/__init__.py`
- pinned Hermes Mem0 backend:
  `https://raw.githubusercontent.com/NousResearch/hermes-agent/v2026.7.7.2/plugins/memory/mem0/_backend.py`
- Hermes programmatic integration:
  `https://github.com/nousresearch/hermes-agent/blob/main/website/docs/developer-guide/programmatic-integration.md`
- Mem0 add and event polling:
  `https://docs.mem0.ai/api-reference/memory/add-memories` and
  `https://docs.mem0.ai/api-reference/events/get-event`

The amended boundary is:

```text
explicit VideoBox approve
→ separate explicit store request
→ authenticated Agent Gateway
→ authenticated videobox-hermes-memory-adapter
→ Mem0 Platform
```

The memory adapter is an optional process derived from the exact pinned Hermes
image. It replaces the image entrypoint, pins `mem0ai==2.0.10`, and never runs
the Hermes agent loop, `MemoryManager`, automatic prefetch, or `sync_turn`.
The interactive Yujin profile keeps `memory.provider` inactive. Chat and manual
editing must start and remain usable when the adapter, credential, or provider
is unavailable.

`MEM0_API_KEY` exists only in the adapter process. The adapter has no host
port, database/media/OAuth mount, or VideoBox provider-readable identifier.
It joins only a dedicated internal memory network and provider egress. The
Gateway receives only the adapter URL and a service credential, has no provider
egress, and never receives the Mem0 credential. Workspace/browser/frontend
receive neither.

Candidate approval and provider processing are separate durable state
machines. `status` remains the consent state
`pending | approved | rejected`; `storage_status` is
`not_requested | claimed | event_pending | stored | failed_retryable |
ambiguous`. Approve remains provider-call zero. Only an approved candidate plus
an explicit store request may claim a provider operation. A server-generated
opaque external reference, operation idempotency key, bounded store request ID
and fingerprint, bounded event reference, bounded memory reference, attempt
count, claim token/expiry, call-start marker, and body-free audit are persisted
before/after provider operations. Provider metadata is limited to:

```json
{
  "source": "videobox_yujin_approved_v1",
  "category": "<allowlisted category>",
  "external_ref": "<server-generated opaque reference>"
}
```

Project, conversation, message, candidate, session, revision, media, local
path, credential, and raw provider fields are never sent to Mem0. The provider
call uses `infer=False` and the fixed Hermes namespaces
`videobox-owner-v1`/`videobox-yujin-v1`.

Direct durable memory IDs may settle to `stored`. An add response containing
only an event ID settles to `event_pending`; subsequent explicit store/retry
first polls or reconciles it and never blindly repeats add. Timeout is
`ambiguous`, not success. Exactly one matching result may settle to `stored`;
zero, multiple, malformed, or text/metadata-mismatched results fail closed.
Provider event/memory IDs and raw bodies remain internal and never appear in a
browser response or log.

The public store contract is:

```http
POST /api/projects/{project_id}/director/memory-candidates/{candidate_id}/store
Content-Type: application/json

{"client_request_id": "<1..128 exact safe ID>"}
```

The response contains only `candidate_id`, consent `status`,
`storage_status`, and `retryable`. It never contains provider, event, memory,
operation, source-message, conversation, or raw provider fields. Missing or
cross-project candidates return fixed `404 memory_candidate_missing`;
pending/rejected candidates, a live claim, or an idempotency conflict return
fixed `409` codes; unavailable/invalid provider settlement returns fixed
`503 memory_save_unavailable`. D3 implements one user Approve click as two
ordered requests, `approve` then `store`, so approve itself always remains
provider-call zero. A separate explicit Retry click sends a new store request
ID.

Durable transition truth:

| Consent / storage | Explicit action or observed result | Next storage state | cumulative add |
|---|---|---|---:|
| pending / not_requested | approve | approved / not_requested | 0 |
| approved / not_requested | store CAS; persist claim before I/O | claimed | 0 |
| claimed, call not started | expired lease reclaim | claimed | at most 1 |
| claimed, call started | direct durable exact result | stored | 1 |
| claimed, call started | event reference | event_pending | 1 |
| claimed, call started | response lost/timeout | ambiguous | 1 |
| event_pending | explicit retry | poll/reconcile same event | 1 |
| event success, one exact text/metadata match | settle | stored | 1 |
| event confirmed failed | settle | failed_retryable | 1 |
| ambiguous | explicit retry | reconcile only | 1 |
| stored | any replay | stored locally | 1 |

An expired pre-call claim may be reclaimed. Once `call_started` is durable,
unknown settlement never permits blind add. `failed_retryable` permits a new
add only when the previous attempt is durably proven not started or the event
is durably confirmed failed with zero matching memory; otherwise it reconciles
only. Same `client_request_id` with the same fingerprint replays; a changed
fingerprint conflicts. Claim expiry uses a bounded server clock and compare-
and-swap. Crash/reload must not erase claim, event, ambiguous, or stored truth.

**Files:**

- Modify: `config/hermes/yujin/distribution.yaml`
- Create: `config/hermes/yujin/skills/videobox-memory/SKILL.md`
- Create: `services/agent-gateway/src/videobox_agent_gateway/memory_gateway.py`
- Create: `services/agent-gateway/src/videobox_agent_gateway/hermes_memory_adapter.py`
- Modify: `services/agent-gateway/src/videobox_agent_gateway/main.py`
- Modify: `services/api/src/videobox_api/agent_gateway_client.py`
- Create: `services/api/src/videobox_api/yujin_memory_service.py`
- Modify: `services/api/src/videobox_api/routers/yujin_memory.py`
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `services/api/src/videobox_api/main.py`
- Modify: `packages/domain-models/src/videobox_domain_models/yujin_memory.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/sqlite_schema.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/postgres_schema.py`
- Create: `docker/hermes-memory-adapter.Dockerfile`
- Modify: `compose.hermes-yujin.yaml`
- Modify: `.env.container.example`
- Create: `tests/test_agent_gateway_memory.py`
- Create: `tests/test_hermes_memory_adapter.py`
- Create: `tests/test_yujin_memory_service.py`
- Modify: `tests/test_api_yujin_memory.py`
- Modify: `tests/test_agent_gateway_client.py`
- Modify: `tests/test_yujin_memory_store.py`
- Modify: `tests/test_postgres_project_store.py`
- Modify: `tests/test_sqlite_migration_concurrency.py`
- Modify: `tests/test_hermes_yujin_compose_contract.py`
- Modify: `tests/test_hermes_yujin_profile_distribution.py`

**Adapter protocol:**

```python
class HermesMemoryGateway(Protocol):
    async def add_approved(self, request: ApprovedMemoryWrite) -> MemoryWriteOutcome: ...
    async def reconcile(self, request: MemoryReconcile) -> MemoryWriteOutcome: ...
    async def search(self, request: MemorySearch) -> tuple[RetrievedMemory, ...]: ...
    async def delete(self, request: MemoryDelete) -> None: ...
```

The internal outcome distinguishes a durable reference from an asynchronous
event. Browser-visible DTOs contain only approval/storage status and retryable
state; they never contain `memory_id`, `event_id`, or provider raw fields.
The internal model is a discriminated status union or has an equivalent
cross-field validator: `stored` requires exactly one bounded memory ref,
`event_pending` requires exactly one bounded event ref, and failure/ambiguous
states cannot carry a memory ref. Impossible combinations are rejected.

```python
class MemoryWriteOutcome(BaseModel):
    status: Literal["stored", "event_pending", "failed_retryable", "ambiguous"]
    memory_ref: str | None = None
    event_ref: str | None = None
```

**RED:**

1. Use fake adapter/provider and fake agent-gateway clients to test direct
   durable add, asynchronous event polling, reconcile, search/delete success,
   timeout, malformed/multiple result, provider rejection, and unavailable
   configuration.
2. Require pending/rejected/cross-project candidate store requests, approve,
   list/reload, and startup to perform Gateway/provider call `0`.
3. Require approved plus explicit store to add exactly once. Replay and two
   concurrent store requests must keep cumulative add count `1`.
4. Require event-only add to remain pending. Replay polls/reconciles rather
   than adds. Timeout/unknown settlement never auto-adds. Only one exact
   matching durable result becomes stored.
5. Require compose/profile tests to prove:
   - Mem0 credential exists only in the isolated memory adapter;
   - interactive Yujin profile does not activate a memory provider;
   - adapter derives from the exact Hermes digest and pins `mem0ai==2.0.10`;
   - adapter has no host port, DB/media/OAuth mount, or ordinary data network;
   - Gateway has no provider egress and no Mem0 credential;
   - browser/API responses never contain it;
   - no Mem0 client is instantiated in editor/frontend code;
   - provider payload contains no VideoBox internal ID.
6. Require all ordinary tests to assert external provider call count `0`.
7. Require provider success followed by local settle failure to reconcile to
   one memory, not issue a second add.
8. Require adapter/provider unavailability to leave candidate approved and
   chat/manual editing operational.
9. Require the adapter to use a distinct service token present only in Gateway
   and adapter. Its client accepts only
   `http://videobox-hermes-memory-adapter:8082`, sets `trust_env=False`,
   forbids redirects, bounds connect/read timeout and response size, and maps
   all transport/provider bodies to fixed errors.
10. Require Gateway/Yujin health and chat startup to have no hard
    `depends_on: adapter service_healthy`. Missing key/configuration lazily
    leaves memory unconfigured with provider call `0`.
11. Require old SQLite database migration and disposable PostgreSQL parity for
    all new consent/storage, claim, request-id, event, and audit fields.

**GREEN:**

12. Build the isolated adapter from the exact Hermes image, replace its
   entrypoint, pin the exact SDK derivative, and expose only authenticated
   add/reconcile/search/delete endpoints. Do not expose generic Hermes tool
   execution.
13. Persist a claim and opaque external reference before calling the Gateway.
   Use compare-and-swap settlement and body-free monotonic audit. Failed or
   ambiguous writes keep approval and require an explicit retry.
14. Call add with approved text, stable Hermes namespace, `infer=False`, and the
   exact minimal metadata above.
15. Map provider errors to fixed public statuses while logging only operation,
    a non-reversible candidate digest, duration, and stable outcome.
16. Keep delete server-owned: browser submits the candidate handle only; the
    server resolves and verifies its private mapping.
17. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_agent_gateway_memory.py tests/test_hermes_memory_adapter.py tests/test_yujin_memory_service.py tests/test_api_yujin_memory.py tests/test_agent_gateway_client.py tests/test_yujin_memory_store.py tests/test_postgres_project_store.py tests/test_sqlite_migration_concurrency.py tests/test_hermes_yujin_compose_contract.py tests/test_hermes_yujin_profile_distribution.py -q
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-profile.ps1 -StaticOnly
   git diff --check
   ```

18. Mark D2 `[x]`, synchronize progress, and commit:

   ```powershell
   git add config/hermes/yujin compose.hermes-yujin.yaml .env.container.example docker/hermes-memory-adapter.Dockerfile services/agent-gateway services/api tests docs/superpowers/plans docs/superpowers/specs
   git commit -m "feat: connect approved memory to Hermes Mem0"
   ```

## D3 — Add approve, list, and delete UI

- [x] **D3** Add approve/list/delete UI and ensure pending/rejected candidates are never injected.

**Files:**

- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/api.test.ts`
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `services/api/src/videobox_api/routers/yujin_memory.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Modify: `tests/test_api_yujin_memory.py`
- Modify: `tests/test_yujin_memory_store.py`
- Modify: `tests/test_postgres_project_store.py`
- Modify: `apps/web/src/features/editor/workbench/rightDockTypes.ts`
- Modify: `apps/web/src/features/editor/workbench/RightDock.tsx`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Modify: `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`
- Create: `apps/web/src/features/editor/workbench/YujinMemoryPanel.tsx`
- Create: `apps/web/src/features/editor/workbench/yujin-memory-panel.test.tsx`

**RED:**

1. Test:
   - new candidates render as pending with Approve/Reject;
   - neither pending nor rejected candidate appears in applied memory context;
   - Approve requires one explicit click and shows saving/stored/failed state;
   - that click sends ordered approve then store requests, while approve
     failure/stale sends store `0`;
   - reload of approved/not-requested renders explicit Store and never
     auto-stores; `claimed` is a non-clickable processing state;
   - an expired claim alone becomes retryable: pre-call reclaims add and a
     call-started claim reconciles without blind add; private timestamps and
     refs remain absent;
   - failed save can be retried only by explicit click;
   - every retry uses a new client request ID;
   - Delete requires explicit click and removes the stored reference on success;
   - close/open RightDock preserves Route-owned candidate state and scroll;
   - late list/approve/store/delete completion after route navigation cannot
     mutate the new route;
   - Mem0 unavailable does not disable chat or manual editor.
2. Require API type guards to reject unknown status/category/provider fields,
   unsafe/oversize/duplicate IDs and text, invalid UTC/order, cross-scope list
   rows, and non-retryable `claimed`.
3. Require the backend list to accept a strict current `conversation_id`,
   verify it belongs to the project, filter project+conversation before
   `LIMIT 100`, and expose only public `storage_status`/`retryable`.

**GREEN:**

4. Keep candidate state ownership in Route or durable API/store, not component-local transient state.
5. Render short policy-safe text only; do not expose source transcript or provider record.
6. Keep the memory section secondary to conversation and creator recommendations.
7. Keep every memory browser request same-origin and redirect-denied.
8. Run:

   ```powershell
   npm --prefix apps/web test -- --run src/features/editor/workbench/yujin-memory-panel.test.tsx src/features/editor/workbench/right-dock.test.tsx src/features/editor/workbench/editor-workbench-route.test.tsx
   git diff --check
   ```

9. Mark D3 `[x]`, synchronize progress, and commit:

   ```powershell
   git add apps/web docs/superpowers/plans
   git commit -m "feat: review Yujin memory in editor"
   ```

**Execution evidence (2026-07-30):**

- Backend list RED `2 failed` → GREEN `2 passed`; current conversation is
  filtered before the 100-row limit and public storage state is restored.
- Frontend typed API RED `5 failed` plus guard-review RED `12 failed` and
  zero-width-text RED `1 failed` → GREEN `20 memory tests`; candidate DTOs are
  scope-bound and provider/private fields
  are rejected.
- RightDock panel RED `3 failed` → GREEN `3 passed`; Route memory slice RED
  `3 failed` → GREEN `5 passed`, then the complete Route file passed
  `114/114`, including expired-claim retry and late list/approve/store/delete
  route fencing.
- Final focused frontend set passed `4 files / 178 tests`; memory store/API
  backend passed `49 tests`.
- Disposable PostgreSQL 16 parity passed `1`, with `40 deselected` and the
  exact D3 container removed afterward.
- Disposable PostgreSQL 16 expired-claim parity passed `1`, with `41
  deselected`; pre-call reclaim used add, call-started recovery used
  reconcile-only, and the exact test container was removed afterward.
- Final independent spec/quality/gap/reverse re-review passed with
  `Critical 0 / Important 0 / Minor 0`.
- This D3 task did not run the full frontend suite, production build, full
  Python regression, live Mem0/provider call, or human browser acceptance;
  those are not claimed here.
- D3 is a management UI for existing/seeded durable candidates only. It does
  not claim a production conversation-to-candidate producer or E2E.

## D4 — Add retrieval injection and close Phase D

- [x] **D4** Add bounded retrieval injection, unavailable fallback, live canary, and Phase D closeout.

Closeout evidence (2026-07-30):

- the only production producer is the explicit current-RightDock
  `기억 후보 만들기` form; it sends 1–8 unique completed durable message IDs
  from the current owned conversation and one typed short candidate to the
  existing POST;
- retrieval is admitted only for a newly owned durable dispatch, performs at
  most one 750 ms search, revalidates exact local approved+stored private
  mapping, injects at most five ID-free preferences within 1,400 characters,
  and drops the memory section first at the 48 KiB context cap;
- replay, unsafe full prompts, the exact create action, unrelated or
  non-approved/non-stored records, malformed/oversize records, timeout and
  outage all produce search `0` or `memories=()` as applicable, without
  blocking chat/manual fallback;
- focused backend memory gate: **149 passed, 1 existing warning**; directly
  impacted creator-context/Gateway/Hermes/API gate: **188 passed, 1 existing
  warning**; focused frontend API/RightDock/Route gate: **3 files / 173
  passed**; full frontend: **52 files / 724 passed**; disposable PostgreSQL 16
  retrieval-row parity: **1 passed** with exact container cleanup confirmed;
  production frontend build succeeded;
  default smoke reported
  `network_calls=0 provider_calls=0 credentials_printed=false`;
- independent spec/quality/gap/reverse review passed with
  `Critical 0 / Important 0 / Minor 0`;
- live Mem0 add/search/delete, full Python regression, browser human E2E,
  provenance, commit, and push are not part of this evidence. Live and human
  proofs remain explicitly unrun; the mandatory full regression/provenance
  gates remain assigned to F1.

**Files:**

- Modify: `packages/core-engine/src/videobox_core_engine/yujin_creator_context.py`
- Modify: `services/agent-gateway/src/videobox_agent_gateway/memory_gateway.py`
- Modify: `services/api/src/videobox_api/yujin_memory_service.py`
- Modify: `services/api/src/videobox_api/hermes_run_service.py`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Modify: the smallest existing RightDock memory producer surface
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

1. Test exactly one production candidate producer:
   - only an explicit current-RightDock `기억 후보 만들기` action calls the
     existing `POST .../memory-candidates`;
   - it uses only completed message IDs from the current owned conversation
     and one typed policy-safe short candidate;
   - route/project/conversation changes fence late results;
   - page load, message/run completion, provider response, approve, store, and
     retry produce automatic candidate create/approve/store `0` and provider
     call `0`.
2. Test relevant approved retrieval, unrelated result filtering, duplicate collapse, deleted memory exclusion, malformed/oversize record rejection, timeout fallback, and zero-network fake path.
3. Test that pending/rejected/failed candidates cannot enter context even if a fake provider returns matching text.
4. Test the prompt/context marks memory as user-approved preference, not system truth or mandatory instruction.
5. Test a Mem0 outage still produces a Hermes run and manual fallback.

**GREEN:**

6. Implement only the explicit producer above by reusing the existing
   candidate POST and server ownership/source/policy validation. Do not add a
   second producer, automatic create, automatic approval, or automatic store.
7. Search before context serialization with a strict timeout; on any failure continue with an empty tuple.
8. Never write retrieval output back to VideoBox as a new memory automatically.
9. Add a live canary that requires explicit `-Live
   -ApproveDisposableAdd` and a disposable tagged memory:
   - add only after an explicit scripted approval step;
   - retrieve it;
   - delete it;
   - confirm it is no longer returned;
   - print IDs/status only, never credentials or raw provider bodies.
10. Run non-live gate:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_yujin_memory_policy.py tests/test_yujin_memory_store.py tests/test_agent_gateway_memory.py tests/test_yujin_memory_service.py tests/test_yujin_memory_retrieval.py tests/test_api_yujin_memory.py -q
   npm --prefix apps/web test -- --run
   npm --prefix apps/web run build
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-plan-state.ps1
   git diff --check
   ```

11. If separately configured and authorized, run:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/smoke-hermes-yujin-mem0.ps1 -Live -ApproveDisposableAdd
   ```

   Otherwise report live Mem0 write/read/delete as unrun.

12. Perform spec, quality, gap, and reverse reviews. Mark D4 `[x]`, synchronize progress and SSOT, then commit and push:

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
