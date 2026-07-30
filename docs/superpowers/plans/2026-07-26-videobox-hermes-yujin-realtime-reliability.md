# VideoBox Hermes Yujin Realtime Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이미 작동하는 Yujin 편집 흐름을 새로고침, 연결 끊김, 중복 이벤트, 취소, 재시도, 만료 토큰, 런타임 장애에서도 예측 가능하게 복구되도록 만든다.

**Architecture:** Phase A의 메모리 이벤트 큐를 VideoBox 로컬 저장소의 append-only run/event record로 교체한다. 브라우저는 마지막 event cursor로 VideoBox SSE에 재연결하고, Agent Gateway만 Hermes ticket/WebSocket을 소유한다. capability는 gateway private key로 발급하고 VideoBox에는 public verification key만 전달하며, 한 번만 소비되고 취소·만료·재생 공격은 명시적으로 거부된다.

**Tech Stack:** Python local storage abstractions, FastAPI SSE, Hermes JSON-RPC/WebSocket, React/TypeScript, Pytest/Vitest, PowerShell operational verifiers

---

Parent: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-master-plan.md`
Requires: Phase B task B5 complete.

Child progress: **3/4 tasks (75.0%), remaining 25.0%**.

## C1 — Persist run and event cursors

- [x] **C1** Persist run/event cursors and restore final or interrupted conversation state.

**2026-07-30 source-grounded C1 amendment:**

- B1/B2 already created the authoritative `director_hermes_runs` row,
  user-before-dispatch transaction, owner-token terminal CAS, assistant link,
  durable public draft, and completed-run reconstruction. C1 extends that row
  and its store; it does not create a second run store or duplicate message
  model.
- Persist only the current public SSE contract
  (`run_started`, `text_delta`, `blocked`, `run_completed`). The written
  design's future `proposal_ready` and `memory_reference` names gain no new
  producer or browser exposure in C1.
- Preserve legacy `pending`, `completed`, and `blocked`; add `streaming` and
  `interrupted`. C1 never writes a new `failed` synonym. Startup atomically
  settles orphaned `pending/streaming` rows as `interrupted`, stores one
  fail-closed assistant/terminal event, and never reclaims or redispatches
  provider work.
- Durable event payload retention is bounded to 30 days and the newest 128
  terminal run streams per project, while active streams are never pruned.
  The minimal run/client-message/assistant tombstone remains for conversation
  lifetime so the one-assistant invariant survives pruning. A scoped events
  request for a pruned stream returns `410 hermes_run_events_expired`; unknown
  or other-project runs remain indistinguishable `404`.
- C1 accepts and replays strictly after a validated backend
  `Last-Event-ID`. Browser reconnect/backoff and suffix-parser adoption remain
  C2; C1 does not silently expand frontend behavior.
- The current product has one VideoBox API owner per project store. Multi-API
  lease coordination is not introduced by C1.

**Files:**

- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/sqlite_schema.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/postgres_schema.py`
- Modify: `services/api/src/videobox_api/hermes_run_service.py`
- Modify: `services/api/src/videobox_api/routers/hermes_conversation.py`
- Modify: `services/api/src/videobox_api/main.py`
- Create: `tests/test_hermes_run_store.py`
- Modify: `tests/test_hermes_run_service.py`
- Modify: `tests/test_api_hermes_conversation.py`

**Domain contract:**

```python
active statuses = {"pending", "streaming"}
terminal statuses = {"completed", "blocked", "interrupted"}
public event types = {"run_started", "text_delta", "blocked", "run_completed"}
```

Storage invariants:

- `(run_id, event_id)` unique
- status terminal transition exactly once
- one final Director assistant message per `client_message_id`
- no raw provider payload, credential, ticket, cookie, or capability token stored
- bounded retention documented and enforced

**RED:**

1. Test append ordering, duplicate event rejection, terminal idempotency, reload reconstruction, interrupted-run recovery, and redacted serialization.
2. Test SSE `Last-Event-ID` replay starts after the supplied cursor.
3. Test an unknown/other-project run returns not found without leaking existence.
4. Run focused tests and expect RED.

**GREEN:**

5. Add the smallest append/list/finalize/recover methods to `LocalProjectStore`.
6. Replace the Phase A queue as the source of replay truth while retaining a bounded notification queue for active delivery.
7. On process startup, mark orphaned `pending/streaming` runs `interrupted`; do not silently resubmit provider work.
8. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_hermes_run_store.py tests/test_hermes_run_service.py tests/test_api_hermes_conversation.py tests/test_director_conversation.py -q
   git diff --check
   ```

9. Mark C1 `[x]`, synchronize progress, and commit:

   ```powershell
   git add packages services/api tests docs/superpowers/plans
   git commit -m "feat: persist Yujin run events"
   ```

## C2 — Add reconnect, cancel, retry, and stale-run fencing

- [x] **C2** Add bounded reconnect, cancel, retry, duplicate suppression, and stale-run fencing.

**2026-07-30 source-grounded C2 amendment:**

- Reuse the existing `director_hermes_runs` row and add only nullable
  `retry_of_run_id`; do not create a second run or conversation store.
- A route-owned run survives RightDock close and non-terminal reconnect
  exhaustion. Route/project navigation or unmount cancels that exact run once;
  terminal truth or successful explicit cancel releases ownership. While
  ownership remains, new Hermes send/retry and legacy Director start are
  blocked, but manual editing and explicit cancel remain available.
- Browser reconnect starts with the initial open inside the same bounded helper,
  then uses `100/250/500ms` backoff and strict durable `Last-Event-ID`
  duplicate suppression. Provider work is never automatically retried after
  prompt acceptance.
- Exact `ticket_expired` before prompt acceptance can mint one fresh ticket.
  Login failure, generic disconnect, malformed acceptance, and any
  post-acceptance loss use stable public failure codes without a provider retry.
- Explicit cancel owns durable `interrupted` state even if the upstream
  interruption concurrently emits a public `blocked` terminal. Repeated or
  concurrent cancel calls share one owner and one upstream interrupt.
- SQLite and PostgreSQL use a durable conversation-scoped `message_order`.
  This replaces runtime SQLite `rowid` ordering, preserves user/assistant pairs
  under identical timestamps, and safely migrates pre-C2 databases.
- The accepted file set therefore also includes the existing storage schemas,
  project store, PostgreSQL compatibility/integration tests, and the non-live
  Hermes fake harnesses needed to exercise the official run-aware port. This is
  backend-parity remediation, not a new capability, provider, or apply path.

**Files:**

- Modify: `services/agent-gateway/src/videobox_agent_gateway/hermes_rpc_client.py`
- Modify: `services/agent-gateway/src/videobox_agent_gateway/main.py`
- Modify: `services/api/src/videobox_api/agent_gateway_client.py`
- Modify: `services/api/src/videobox_api/hermes_run_service.py`
- Modify: `services/api/src/videobox_api/routers/hermes_conversation.py`
- Modify: `apps/web/src/features/editor/workbench/hermesSseClient.ts`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Modify: `apps/web/src/features/editor/workbench/RightDock.tsx`
- Modify: `tests/test_agent_gateway_hermes_rpc_client.py`
- Modify: `tests/test_hermes_run_service.py`
- Modify: `apps/web/src/features/editor/workbench/hermesSseClient.test.ts`
- Modify: `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`

**Endpoints:**

```text
POST /api/projects/{project_id}/director/conversations/{conversation_id}/hermes-runs/{run_id}/cancel
POST /api/projects/{project_id}/director/conversations/{conversation_id}/hermes-runs/{run_id}/retry
```

**Retry policy:**

- browser SSE reconnect: at most 3 attempts with bounded backoff, same run/cursor
- expired WS ticket before prompt acceptance: obtain one fresh ticket and retry once
- provider run after prompt acceptance: never automatic retry
- explicit Retry creates a new run linked to `retry_of_run_id`
- no token-level resume claim; replay uses stored public events

**RED:**

1. Test connection loss before/after prompt acceptance, expired ticket, duplicate delta, duplicate complete, cancel before ready, cancel while streaming, cancel after complete, retry of failed/interrupted, and retry rejection for active run.
2. Test route/project/revision/epoch change fences all later events and candidate publication.
3. Test closing/opening RightDock does not cancel the route-owned run.
4. Test cancel/retry buttons never disable manual editing.

**GREEN:**

5. Map cancel to official `session.interrupt` when an upstream session exists, then finalize local status.
6. Keep `lastEventId` per run and ignore event IDs less than or equal to the last accepted ID.
7. Replace generic exception text with stable public codes:

   ```text
   hermes_unavailable
   hermes_ticket_expired
   hermes_timeout
   hermes_interrupted
   hermes_invalid_response
   ```

8. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_agent_gateway_hermes_rpc_client.py tests/test_agent_gateway_api.py tests/test_agent_gateway_client.py tests/test_hermes_run_service.py tests/test_api_hermes_conversation.py -q
   npm --prefix apps/web test -- --run src/features/editor/workbench/hermesSseClient.test.ts src/features/editor/workbench/editor-workbench-route.test.tsx
   git diff --check
   ```

9. Mark C2 `[x]`, synchronize progress, and commit:

   ```powershell
   git add services/api apps/web tests docs/superpowers/plans
   git commit -m "feat: recover and cancel Yujin runs"
   ```

## C3 — Complete capability lifecycle

- [x] **C3** Complete issue/consume/replay/revoke capability lifecycle with redacted audit evidence.

**2026-07-30 source-grounded amendment:** The authoritative C3 contract is
`docs/superpowers/specs/2026-07-30-videobox-hermes-yujin-c3-capability-lifecycle-design.md`.
The executable TDD sequence is
`docs/superpowers/plans/2026-07-30-videobox-hermes-yujin-c3-capability-lifecycle.md`.
It replaces the earlier multi-action/base-revision sketch below with two exact
one-action capabilities bound to the current
project/conversation/run/session/session-revision/asset-index-revision. It
reuses the existing API-to-Gateway `reserve -> attach -> stream ->
release/cancel` topology and the existing durable ledger. It does not add a
Gateway-to-API callback, an API private key, a second replay ledger, editor
mutation authority, or a provider call.

**Files:**

- Inspect/reuse: `packages/core-engine/src/videobox_core_engine/agent_gateway_contract.py`
- Modify: `requirements-agent-gateway.txt`
- Modify: `requirements-container.txt`
- Modify: `requirements-dev.txt`
- Create: `services/agent-gateway/src/videobox_agent_gateway/context_capabilities.py`
- Modify: `services/agent-gateway/src/videobox_agent_gateway/creator_context.py`
- Modify: `services/agent-gateway/src/videobox_agent_gateway/main.py`
- Modify: `services/api/src/videobox_api/hermes_capabilities.py`
- Modify: `services/api/src/videobox_api/hermes_capability_authority.py`
- Modify: `services/api/src/videobox_api/agent_gateway_client.py`
- Modify: `services/api/src/videobox_api/hermes_run_service.py`
- Modify: `services/api/src/videobox_api/main.py`
- Retire: `services/api/src/videobox_api/routers/hermes_internal.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/sqlite_schema.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/postgres_schema.py`
- Create: `services/api/src/videobox_api/hermes_capability_audit.py`
- Modify: `compose.yaml`
- Modify: `compose.hermes-yujin.yaml`
- Modify: `.env.container.example`
- Modify: `scripts/start-hermes-yujin.ps1`
- Create: `tests/test_hermes_yujin_capability_lifecycle.py`
- Modify: `tests/test_agent_gateway_api.py`
- Modify: `tests/test_agent_gateway_creator_context.py`
- Modify: `tests/test_agent_gateway_client.py`
- Modify: `tests/test_hermes_run_service.py`
- Modify: `tests/test_postgres_project_store.py`
- Modify: `tests/test_hermes_capability_authority_contract.py`
- Modify/retire: `tests/test_api_hermes_project_status.py`
- Modify: `tests/test_hermes_yujin_compose_contract.py`
- Modify: `tests/test_start_hermes_yujin_script.py`

**Capability claims:**

```python
class YujinCapabilityClaims(BaseModel):
    schema_version: Literal["videobox.yujin-capability.v1"]
    iss: Literal["videobox-agent-gateway"]
    sub: Literal["yujin-video-director"]
    aud: Literal["videobox-api"]
    capability_id: str
    project_id: str
    conversation_id: str
    run_id: str
    session_id: str
    session_revision: int
    asset_index_revision: int
    action: Literal["read_context", "publish_proposal"]
    iat: int
    nbf: int
    exp: int
```

Each token contains exactly one action. Never issue an `apply`, `render`,
`export`, DB, filesystem, or raw-media action.

**RED:**

1. Add lifecycle tests:
   - valid issue and one-time consume;
   - replay denied;
   - expiry denied;
   - wrong project/run/revision/action denied;
   - cancellation revokes unused capability;
   - successful/failed completion revokes remaining capability;
   - legacy jti-only SQLite/PostgreSQL rows migrate as non-authorizing
     tombstones rather than fabricated scoped rows;
   - ledger recovery reconciliation revokes issued rows without provider retry;
   - coordinated single-key replacement rejects old-key tokens;
   - audit record contains IDs/outcome only, not token/body/secret.
2. Add a reverse test that starts from an attempted apply action and proves no capability path can authorize it.
3. Run focused capability tests and expect RED for uncovered gaps.

**GREEN:**

4. Replace the static shared-secret prototype at the deployed boundary with one Ed25519 system:
   - private key exists only in `videobox-agent-gateway`;
   - VideoBox API receives only the public verification key;
   - source, logs, browser, Hermes, and Dashboard receive neither key material;
   - pin `cryptography==45.0.6` in gateway, workspace, and development
     requirements so a clean local `.venv` can run the issuer/verifier tests.
5. Reuse existing authority/store consume and revoke primitives after verification; do not create a second replay ledger.
6. Bind consume to one exact pre-registered issued row and the current
   project/conversation/run/session/session-revision/asset-index-revision plus
   one exact action. Remove consume-if-absent behavior.
7. Use the existing capability ID/JTI as the replay identity. Migrate legacy
   unscoped rows as non-authorizing tombstones, and derive denial-audit identity
   only from trusted durable/request metadata.
8. Keep base Compose issuance disabled. Enable the C3 authority only in the
   Hermes Yujin overlay, inject the private key into Gateway only and public key
   into workspace only, and make the start script reject an invalid or
   mismatched pair without printing key material.
9. Run focused tests, then run the PostgreSQL lifecycle/migration/concurrency
   cases against a disposable PostgreSQL 16 container with
   `VIDEOBOX_TEST_POSTGRES_URL` set. A skipped PostgreSQL case is not a pass:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_hermes_yujin_capability_lifecycle.py tests/test_hermes_capability_authority_contract.py tests/test_agent_gateway_api.py tests/test_agent_gateway_creator_context.py tests/test_agent_gateway_client.py tests/test_hermes_run_service.py tests/test_postgres_project_store.py tests/test_hermes_yujin_compose_contract.py tests/test_start_hermes_yujin_script.py -q
   $env:VIDEOBOX_TEST_POSTGRES_URL = "<disposable PostgreSQL 16 test URL>"
   .\.venv\Scripts\python.exe -m pytest tests/test_postgres_project_store.py -k "hermes_capability" -q
   git diff --check
   ```

10. Mark C3 `[x]`, synchronize progress, and commit:

   ```powershell
   # Use the exact-file staging, authority checks, commit, push, and post-push
   # verification block in the linked 2026-07-30 C3 detailed plan.
   ```

## C4 — Add operations, failure drills, and Phase C closeout

- [ ] **C4** Add dashboard health/restart/fallback operations, failure drills, and Phase C closeout.

**Files:**

- Create: `scripts/get-hermes-yujin-status.ps1`
- Create: `scripts/restart-hermes-yujin.ps1`
- Create: `scripts/test-hermes-yujin-failure-drills.ps1`
- Modify: dashboard/status UI files discovered in Phase 0
- Create: focused frontend dashboard/status test beside the modified component
- Create: `docs/handoffs/2026-07-26-videobox-hermes-yujin-phase-c-closeout.ko.md`
- Modify: `docs/implementation-plan.ko.md`
- Modify: `docs/development-status-2026-06-29.ko.md`

**Status vocabulary:**

```text
not_configured
stopped
starting
http_ready
provider_ready
chat_verified
degraded
```

`http_ready` must never be displayed as `chat_verified`.

**RED:**

1. Add script/UI tests for:
   - container absent;
   - stopped;
   - HTTP ready but provider unavailable;
   - expired auth;
   - live chat verified;
   - degraded after a previously successful canary.
2. Require status payloads/logs to redact usernames only if sensitive, and always redact passwords, hashes, cookies, tickets, provider response bodies, and memory records.
3. Require restart script to restart only the named Yujin service and never delete volumes or old containers.

**GREEN:**

4. Implement read-only status collection and a named restart action.
5. Implement failure drills:
   - stop runtime during stream;
   - browser SSE disconnect and reconnect;
   - expired ticket;
   - duplicate event;
   - API restart with interrupted run recovery;
   - provider failure;
   - all cases preserve manual editor.
6. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_hermes_run_store.py tests/test_agent_gateway_hermes_rpc_client.py tests/test_agent_gateway_api.py tests/test_agent_gateway_client.py tests/test_hermes_run_service.py tests/test_hermes_yujin_capability_lifecycle.py tests/test_api_hermes_conversation.py -q
   npm --prefix apps/web test -- --run
   npm --prefix apps/web run build
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-hermes-yujin-failure-drills.ps1 -StaticOnly
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-plan-state.ps1
   git diff --check
   ```

7. When a configured runtime is available, run the named local failure drills separately and record which destructive simulation ran. Do not infer provider success from HTTP readiness.
8. Perform independent spec, quality, gap, and reverse reviews; fix Critical/Important findings or record an explicit accepted limitation.
9. Mark C4 `[x]`, synchronize progress and SSOT, commit and push:

   ```powershell
   git add scripts apps/web services packages tests docs
   git commit -m "feat: harden Yujin realtime runs"
   git push origin codex/videobox-container-compatibility
   ```

Expected Phase C outcome: reload/reconnect/cancel/retry behavior is deterministic, capability replay is rejected, operational status tells the truth, and every tested failure leaves manual editing available.
