# VideoBox Hermes Yujin Runtime Chat Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 격리된 공식 Hermes Yujin 런타임을 실제로 구동하고, VideoBox RightDock에서 지속되는 실시간 대화가 작동하며 Hermes 장애 시에도 수동 편집이 유지되게 한다.

**Architecture:** 전용 `videobox-agent-gateway`만 Hermes `serve`의 인증된 JSON-RPC/WebSocket 클라이언트가 되고, VideoBox API는 gateway의 좁은 내부 stream을 브라우저 SSE로 중계한다. workspace↔gateway의 `videobox-agent-gateway-api-network`와 gateway↔Hermes의 `videobox-agent-gateway-network`를 서로 다른 internal network로 유지하고, Hermes만 `videobox-hermes-provider-egress`에 연결한다. 하나의 flat Docker network로는 Gateway-only 도달성을 보장할 수 없으므로 Docker forwarding 없이 gateway process만 application level bridge가 된다. Phase A에서는 진행 중 이벤트 큐는 프로세스 메모리에 한정하되 사용자·최종 응답은 기존 Director conversation 저장소에 영속화한다. Gateway와 Hermes에는 VideoBox DB/media mount를 제공하지 않는다.

**Tech Stack:** Docker Compose, official Hermes Agent v0.18.x pinned image, FastAPI StreamingResponse, Pydantic, httpx, websockets 15.0.1, React, TypeScript, Vitest

---

Parent: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-master-plan.md`
Design: `docs/superpowers/specs/2026-07-26-videobox-hermes-yujin-integration-design.md`

Child progress: **3/6 tasks (50.0%), remaining 50.0%**. These six tasks are master IDs P0-1, P0-2, A1, A2, A3, and A4.

## P0-1 — Confirm drift and official runtime contracts

- [x] **P0-1** Confirm live/source drift, official Hermes CLI/wire contracts, branch/upstream, protected paths, and current dependency pins.

**Files:**

- Create: `docs/handoffs/2026-07-26-videobox-hermes-yujin-audit-baseline.ko.md`
- Inspect: `compose.yaml`
- Inspect: `requirements-runtime.txt`
- Inspect: `requirements-container.txt`
- Inspect: `scripts/start-hermes-oauth-bootstrap.ps1`
- Inspect: `scripts/verify-hermes-oauth-bootstrap.ps1`
- Inspect: `services/api/src/videobox_api/main.py`

**Steps:**

1. Mark P0-1 `[~]` here and in the master mirror.
2. Run and record:

   ```powershell
   git status --short
   git branch --show-current
   git rev-parse HEAD
   git rev-parse '@{upstream}'
   git rev-list --left-right --count 'HEAD...@{upstream}'
   git worktree list
   git diff --check
   docker compose ps -a
   docker image inspect nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787
   ```

3. Confirm inside the pinned image:

   ```powershell
   docker run --rm nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787 hermes --version
   docker run --rm nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787 hermes serve --help
   docker run --rm nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787 hermes profile install --help
   ```

4. Verify proposed dependency wheels without installing them into the project:

   ```powershell
   $dependencyAudit = Join-Path $env:TEMP "videobox-hermes-yujin-dependency-audit"
   New-Item -ItemType Directory -Force -Path $dependencyAudit | Out-Null
   .\.venv\Scripts\python.exe -m pip download --only-binary=:all: --no-deps --dest $dependencyAudit httpx==0.28.1 websockets==15.0.1 cryptography==45.0.6
   ```

5. Record verified JSON-RPC methods `session.create`, `prompt.submit`, and `session.interrupt`; events `gateway.ready`, `message.delta`, and `message.complete`; REST ticket path `/api/auth/ws-ticket`; WebSocket path `/api/ws`.
6. Record existing exited/orphan containers without deleting them.
7. Confirm the three protected untracked directories remain untouched.
8. Mark P0-1 `[x]`, update both progress mirrors, run `git diff --check`, and commit:

   ```powershell
   git add docs/handoffs/2026-07-26-videobox-hermes-yujin-audit-baseline.ko.md docs/superpowers/plans
   git commit -m "docs: baseline Hermes Yujin execution state"
   ```

Expected: evidence distinguishes source configuration, container state, HTTP readiness, provider readiness, and live chat success.

## P0-2 — Add baseline reverse trace and plan-state verifier

- [x] **P0-2** Record reverse runtime trace and focused baseline; add the plan-state consistency verifier.

**Files:**

- Create: `scripts/verify-hermes-yujin-plan-state.ps1`
- Create: `tests/test_hermes_yujin_plan_state_contract.py`
- Modify: `docs/handoffs/2026-07-26-videobox-hermes-yujin-audit-baseline.ko.md`
- Inspect: `services/api/src/videobox_api/routers/director_proposals.py`
- Inspect: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Inspect: `apps/web/src/features/editor/workbench/RightDock.tsx`

**RED:**

1. Add a contract test that runs the verifier and requires:
   - exactly 20 unique master task IDs;
   - each child task ID exists in the master;
   - child/master status equality;
   - reported numerator equals `[x]` count;
   - no unfinished placeholder markers in these five plans.
2. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_hermes_yujin_plan_state_contract.py -q
   ```

   Expected RED: verifier file is absent.

**GREEN:**

3. Implement `scripts/verify-hermes-yujin-plan-state.ps1` using explicit plan paths and a task-line regex:

   ```powershell
   $taskPattern = '^- \[( |~|x|!)\] \*\*(P0-[12]|A[1-4]|B[1-5]|C[1-4]|D[1-4]|F1)\*\*'
   ```

4. Make mismatch output name the task ID, master status, and child status; exit nonzero on any mismatch.
5. Add the verified reverse trace from RightDock input through route epoch, API persistence, Hermes transport, SSE, final persistence, optional proposal, explicit apply, PreviewCoordinator, and output.
6. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_hermes_yujin_plan_state_contract.py -q
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-plan-state.ps1
   .\.venv\Scripts\python.exe -m pytest tests/test_director_conversation.py tests/test_api_hermes_project_status.py -q
   git diff --check
   ```

7. Mark P0-2 `[x]`, synchronize progress, and commit:

   ```powershell
   git add scripts/verify-hermes-yujin-plan-state.ps1 tests/test_hermes_yujin_plan_state_contract.py docs
   git commit -m "test: lock Hermes Yujin execution state"
   ```

## A1 — Add isolated Yujin Hermes runtime

- [x] **A1** Add the isolated official Hermes Yujin runtime topology and deterministic startup verification.

**Files:**

- Modify: `compose.yaml`
- Create: `compose.hermes-yujin.yaml`
- Modify: `.env.container.example`
- Create: `docker/agent-gateway.Dockerfile`
- Create: `docker/agent-gateway.Dockerfile.dockerignore`
- Create: `requirements-agent-gateway.txt`
- Create: `services/agent-gateway/src/videobox_agent_gateway/__init__.py`
- Create: `services/agent-gateway/src/videobox_agent_gateway/main.py`
- Create: `scripts/start-hermes-yujin.ps1`
- Create: `scripts/verify-hermes-yujin-runtime.ps1`
- Create: `tests/test_hermes_yujin_compose_contract.py`
- Create: `tests/test_start_hermes_yujin_script.py`
- Modify: `tests/test_compose_contract.py`

**RED:**

1. Add tests requiring service `videobox-hermes-yujin` to:
   - exist only in the opt-in `compose.hermes-yujin.yaml` overlay with profile `hermes-yujin`, leaving base Compose free of Yujin auth interpolation;
   - use the existing pinned official image digest;
   - run `hermes serve --host 0.0.0.0 --port 9120`;
   - join only `videobox-hermes-provider-egress` and the Hermes-facing internal `videobox-agent-gateway-network`;
   - expose no host port by default;
   - mount only the existing isolated OAuth state at `/opt/data`; A2 adds the versioned profile source later;
   - mount neither VideoBox DB nor media paths;
   - have no dependency on workspace, API, renderer, or edge services.
2. Require service `videobox-agent-gateway` to:
   - use a minimal dedicated Dockerfile and health-only FastAPI app at first;
   - use a Dockerfile-specific deny-all build-context allowlist that admits only its Dockerfile, requirements file, and gateway source tree;
   - join only the workspace-facing internal `videobox-agent-gateway-api-network` and Hermes-facing internal `videobox-agent-gateway-network`;
   - mount neither VideoBox DB/media nor Hermes home;
   - have no provider-egress network;
   - receive Hermes auth only through local container configuration and never print it.
3. Require `videobox-workspace` to join `videobox-agent-gateway-api-network`, never the Hermes-facing or provider-egress networks. Require both gateway networks to be `internal: true`. This two-network split is required because one flat client network would let workspace bypass the gateway and address Hermes directly.
4. Run the focused test and expect failure because the services are absent.

**GREEN:**

5. Keep base `compose.yaml` compatible with the pre-A1 default and put the workspace network augmentation, both A1 services, and both new internal networks in opt-in `compose.hermes-yujin.yaml`. Give both optional services profile `hermes-yujin`. Add the Hermes service with required environment variables sourced from local container configuration:

   ```yaml
   HERMES_DASHBOARD_BASIC_AUTH_USERNAME: ${HERMES_YUJIN_GATEWAY_USERNAME:?set in .env.container}
   HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH: ${HERMES_YUJIN_GATEWAY_PASSWORD_HASH:?set in .env.container}
   ```

   The agent-gateway receives the matching username and plaintext password through its own local-only container environment so it can obtain the authenticated session/ticket. VideoBox workspace/browser receives neither password nor hash. Never print any of these values in scripts or test output.

6. Add `docker/agent-gateway.Dockerfile.dockerignore` using Docker's Dockerfile-specific convention. Deny the repository root by default and allow only the exact gateway Dockerfile, `requirements-agent-gateway.txt`, required parent traversal directories, and `services/agent-gateway/src/**`.
7. Add healthchecks that prove both HTTP services respond, explicitly naming Hermes HTTP readiness—not provider success.
8. `start-hermes-yujin.ps1` must:
   - use the rendered Compose model—not a second raw `.env` parser—as the authority for the exact resolved credential environment;
   - reject missing, empty, unresolved, placeholder, mismatched username, or invalid URL values without echoing values;
   - verify the plaintext/password-hash relationship with the pinned Hermes image's canonical `plugins.dashboard_auth.basic._verify_password` under `--network none`;
   - offer `-ValidateOnly` so configuration and credential relationship can be checked without starting the services;
   - start only the named Yujin and agent-gateway services;
   - refuse to remove old containers or volumes.
9. A2 will extend the startup flow with Yujin profile installation; A1 must not reference a file that does not yet exist.
10. `verify-hermes-yujin-runtime.ps1` must prove container image digest, command, networks, mounts, health, and absence of DB/media mounts.
11. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_hermes_yujin_compose_contract.py tests/test_start_hermes_yujin_script.py tests/test_compose_contract.py -q
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-runtime.ps1 -StaticOnly
   # Run through the static verifier, or inject non-secret dummy required values
   # into a child process before docker compose config --quiet.
   git diff --check
   ```

12. Mark A1 `[x]`, synchronize progress, and commit:

   ```powershell
   git add compose.yaml .env.container.example docker/agent-gateway.Dockerfile requirements-agent-gateway.txt services/agent-gateway scripts tests docs/superpowers/plans
   git commit -m "feat: run isolated Yujin Hermes service"
   ```

## A2 — Install the Yujin Soul/profile package

- [ ] **A2** Install the versioned Yujin Soul/profile/skills package and verify ownership plus secret-free contents.

**Files:**

- Create: `config/hermes/yujin/distribution.yaml`
- Create: `config/hermes/yujin/SOUL.md`
- Create: `config/hermes/yujin/config.yaml`
- Create: `config/hermes/yujin/skills/videobox-editor/SKILL.md`
- Create: `scripts/install-hermes-yujin-profile.ps1`
- Create: `scripts/verify-hermes-yujin-profile.ps1`
- Modify: `scripts/start-hermes-yujin.ps1`
- Modify: `compose.yaml`
- Create: `tests/test_hermes_yujin_profile_distribution.py`
- Inspect/reuse: `packages/core-engine/src/videobox_core_engine/yujin_profile_contract.py`
- Inspect/reuse: `packages/core-engine/src/videobox_core_engine/yujin_agent_package_contract.py`

**RED:**

1. Add tests requiring:

   ```yaml
   name: videobox-yujin
   version: 1.0.0
   hermes_requires: ">=0.18.0"
   distribution_owned:
     - SOUL.md
     - config.yaml
     - skills/
   ```

2. Require the Soul to state:
   - Korean-first helpful editor identity;
   - no automatic apply;
   - no claim that preview/export succeeded without VideoBox evidence;
   - unsupported effects must not be suggested as actionable controls;
   - manual fallback must be offered on failure.
3. Require a secret scanner to reject API keys, OAuth tokens, passwords, local absolute user paths, and Mem0 credentials.
4. Run focused tests and expect RED because package files are absent.

**GREEN:**

5. Write the minimal Soul/profile and a first skill limited to conversation, clarification, and manual fallback. Creator proposal instructions arrive in Phase B.
6. Mount the versioned profile source read-only into the Yujin service. Extend the A1 startup script to install/verify the profile before starting the gateway.
7. The installer must call:

   ```powershell
   hermes profile install /opt/videobox-yujin-profile --name videobox-yujin --force -y
   ```

   inside the named container and never modify the host Hermes profile.
8. The verifier must compare declared ownership to real files and reject undeclared executable files.
9. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_hermes_yujin_profile_distribution.py tests/test_yujin_profile_contract.py tests/test_yujin_agent_package_contract.py -q
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-profile.ps1 -StaticOnly
   git diff --check
   ```

10. Mark A2 `[x]`, synchronize progress, and commit:

   ```powershell
   git add config/hermes/yujin compose.yaml scripts tests docs/superpowers/plans
   git commit -m "feat: install VideoBox Yujin profile"
   ```

## A3 — Implement Hermes transport and SSE run boundary

- [ ] **A3** Implement the minimal authenticated Hermes JSON-RPC/WebSocket client and API SSE run boundary.

**Files:**

- Modify: `requirements-agent-gateway.txt`
- Create: `services/agent-gateway/src/videobox_agent_gateway/hermes_rpc_client.py`
- Modify: `services/agent-gateway/src/videobox_agent_gateway/main.py`
- Create: `services/api/src/videobox_api/agent_gateway_client.py`
- Create: `services/api/src/videobox_api/hermes_run_service.py`
- Create: `services/api/src/videobox_api/routers/hermes_conversation.py`
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `services/api/src/videobox_api/main.py`
- Create: `tests/test_agent_gateway_hermes_rpc_client.py`
- Create: `tests/test_agent_gateway_api.py`
- Create: `tests/test_agent_gateway_client.py`
- Create: `tests/test_hermes_run_service.py`
- Create: `tests/test_api_hermes_conversation.py`

**Contracts:**

```python
class HermesRunCreateRequest(BaseModel):
    session_id: str
    client_message_id: str
    text: str

class HermesRunCreateResponse(BaseModel):
    run_id: str
    conversation_id: str
    events_url: str

class HermesStreamEvent(BaseModel):
    event_id: int
    event_type: Literal["run_started", "text_delta", "blocked", "run_completed"]
    text: str = ""
    retryable: bool = False
```

Endpoints:

```text
POST /api/projects/{project_id}/director/conversations/{conversation_id}/hermes-runs
GET  /api/projects/{project_id}/director/conversations/{conversation_id}/hermes-runs/{run_id}/events
```

**RED:**

1. Write gateway transport tests with fake HTTP and fake WebSocket peers that require:
   - authenticated cookie acquisition;
   - fresh single-use WS ticket;
   - `session.create` before `prompt.submit`;
   - mapping only allowlisted message events;
   - redaction of upstream exception bodies;
   - deterministic timeout and close.
2. Write gateway API tests for the one narrow internal stream endpoint and require it to reject arbitrary tool names, DB/media paths, provider fields, and caller-supplied Hermes credentials.
3. Write VideoBox API client/run tests requiring idempotency by `client_message_id`, user-message persistence before dispatch, final-message persistence on completion, and zero external calls.
4. Run focused tests; expected RED is missing modules/endpoints.

**GREEN:**

5. Pin `httpx==0.28.1` and `websockets==15.0.1` in `requirements-agent-gateway.txt`.
6. Implement gateway-owned `HermesRpcClient` with injected HTTP/WS factories so tests never use a real network.
7. Implement API-owned bounded in-memory run registry:
   - maximum active runs;
   - maximum queued event count;
   - per-run timeout;
   - terminal completion exactly once;
   - no provider payloads in public errors.
8. Reuse `LocalProjectStore.create_director_conversation`, `claim_director_message`, `get_director_exchange_by_client_message_id`, and message persistence rather than adding a second conversation store.
9. Register the router only when the agent-gateway URL is valid; the VideoBox API must never receive Hermes username/password.
10. When gateway or Hermes is unavailable, expose a typed unavailable result and preserve the existing local/manual Director path.
11. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_agent_gateway_hermes_rpc_client.py tests/test_agent_gateway_api.py tests/test_agent_gateway_client.py tests/test_hermes_run_service.py tests/test_api_hermes_conversation.py tests/test_director_conversation.py -q
   git diff --check
   ```

12. Mark A3 `[x]`, synchronize progress, and commit:

   ```powershell
   git add requirements-agent-gateway.txt services/agent-gateway services/api tests docs/superpowers/plans
   git commit -m "feat: stream Hermes runs through VideoBox API"
   ```

## A4 — Connect persistent RightDock chat and close Phase A

- [ ] **A4** Connect persistent RightDock chat, manual fallback, reload proof, live canary, and Phase A closeout.

**Files:**

- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/features/editor/workbench/rightDockTypes.ts`
- Modify: `apps/web/src/features/editor/workbench/RightDock.tsx`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Create: `apps/web/src/features/editor/workbench/hermesSseClient.ts`
- Modify: `apps/web/src/features/editor/workbench/right-dock.test.tsx`
- Modify: `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`
- Create: `apps/web/src/features/editor/workbench/hermesSseClient.test.ts`
- Create: `scripts/smoke-hermes-yujin-chat.ps1`
- Create: `docs/handoffs/2026-07-26-videobox-hermes-yujin-phase-a-closeout.ko.md`

**Frontend state:**

```ts
export type YujinRunState =
  | { kind: "idle" }
  | { kind: "streaming"; runId: string; routeEpoch: number; text: string }
  | { kind: "complete"; runId: string }
  | { kind: "unavailable"; message: string };
```

**RED:**

1. Add tests requiring:
   - existing persisted messages render after reload;
   - deltas append to one assistant bubble;
   - duplicate SSE event IDs are ignored;
   - route epoch change drops later deltas and final state mutation;
   - RightDock close/open preserves conversation and candidate/player/scroll ownership in Route;
   - Hermes unavailable displays a short fallback and leaves manual controls enabled;
   - no direct browser connection to Hermes.
2. Run:

   ```powershell
   npm --prefix apps/web test -- --run src/features/editor/workbench/hermesSseClient.test.ts src/features/editor/workbench/right-dock.test.tsx src/features/editor/workbench/editor-workbench-route.test.tsx
   ```

   Expected RED: SSE client and run state are absent.

**GREEN:**

3. Add typed API methods and an SSE parser that accepts only `run_started`, `text_delta`, `blocked`, and `run_completed`.
4. Keep conversation, run, scroll restoration key, and selected candidate state in `EditorWorkbenchRoute`; `RightDock` remains a controlled view adapter.
5. On failure, preserve typed user input where possible and expose “Yujin 없이 계속 편집” without disabling existing buttons.
6. Do not add auto-retry or midstream reconnect in Phase A.
7. Add a live canary script that:
   - requires explicit `-Live`;
   - checks configuration without echoing credentials;
   - creates or reuses a test conversation;
   - sends a harmless Korean prompt;
   - requires at least one delta and one complete event;
   - records no provider response body;
   - makes no edit proposal or apply call.
8. Run the non-live gate:

   ```powershell
   npm --prefix apps/web test -- --run src/features/editor/workbench/hermesSseClient.test.ts src/features/editor/workbench/right-dock.test.tsx src/features/editor/workbench/editor-workbench-route.test.tsx
   .\.venv\Scripts\python.exe -m pytest tests/test_agent_gateway_hermes_rpc_client.py tests/test_agent_gateway_api.py tests/test_agent_gateway_client.py tests/test_hermes_run_service.py tests/test_api_hermes_conversation.py tests/test_director_conversation.py -q
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-runtime.ps1 -StaticOnly
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-profile.ps1 -StaticOnly
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-plan-state.ps1
   npm --prefix apps/web run build
   git diff --check
   ```

9. Run the Phase A full non-live release gate required by the written design:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q
   npm --prefix apps/web test -- --run
   npm --prefix apps/web run test:e2e:editor-workbench
   npm --prefix apps/web run build
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-editor-ui-source-provenance.ps1
   ```

10. If credentials and provider access are configured, run separately:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/smoke-hermes-yujin-chat.ps1 -Live
   ```

   If not configured, report the live canary as unrun—not passed.

11. Stop only `videobox-hermes-yujin`, rerun the focused frontend fallback test, and prove manual editing controls remain enabled.
12. Run a focused spec, quality, gap, and reverse review. Fix Critical/Important findings before closeout.
13. Mark A4 `[x]`, update master/child progress, update SSOT status and handoff, then commit and push:

   ```powershell
   git add apps/web scripts docs services/api tests
   git commit -m "feat: stream Yujin chat into editor"
   git push origin codex/videobox-container-compatibility
   ```

Expected Phase A outcome: real Yujin chat works in RightDock when configured; final messages survive reload; closing the Inspector does not lose route-owned state; stopping Hermes does not block manual editing.
