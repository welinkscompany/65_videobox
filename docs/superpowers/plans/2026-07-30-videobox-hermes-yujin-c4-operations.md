# VideoBox Hermes Yujin C4 operations implementation plan

Date: 2026-07-30
Design: `docs/superpowers/specs/2026-07-30-videobox-hermes-yujin-c4-operations-design.md`

Use TDD. Do not touch the protected untracked directories.

## Task 1 — Gateway truthful operational observation

- [ ] RED health tests for HTTP-only, safe non-empty public delta, safe
  complete-only/chat, allowlisted later failure/degraded and redaction.
- [ ] Add bounded internal Hermes HTTP probe that discards response bodies.
- [ ] Add injected probe plus one locked monotonic observer with epoch,
  generation, strict UTC clock and 10-minute evidence TTL.
- [ ] RED concurrent/late ordering, sticky degraded→new complete recovery, and
  cancel/stale/replay/unsafe/malformed non-degradation tests.

Files:

- `services/agent-gateway/src/videobox_agent_gateway/hermes_rpc_client.py`
- `services/agent-gateway/src/videobox_agent_gateway/main.py`
- `tests/test_agent_gateway_hermes_rpc_client.py`
- `tests/test_agent_gateway_api.py`
- `tests/test_hermes_yujin_compose_contract.py`

## Task 2 — Same-origin global status API

- [ ] RED strict DTO/mapping tests for all seven states.
- [ ] Add `AgentGatewayClient` health DTO/method.
- [ ] Add global `/api/hermes-yujin/status`; keep the retired project route 404.
- [ ] Add a dedicated short-timeout status client/service, explicit unconfigured
  wiring, epoch-change reset, TTL/clock-skew/restart tests and fixed redaction.
- [ ] Browser stopped/starting copy must mean application-path availability,
  while operator JSON uses Docker-observed basis.

Files:

- `services/api/src/videobox_api/agent_gateway_client.py`
- `services/api/src/videobox_api/models.py`
- new `services/api/src/videobox_api/hermes_operational_status.py`
- new `services/api/src/videobox_api/routers/hermes_operations.py`
- `services/api/src/videobox_api/main.py`
- new `tests/test_api_hermes_operations.py`
- `tests/test_api_hermes_project_status.py`

## Task 3 — Lazy read-only ProductShell status

- [ ] RED component tests for seven states, HTTP/chat distinction, redaction,
  strict UTC timestamps, request-epoch single-flight and failure fallback.
- [ ] RED ProductShell test: closed dialog performs request 0; open mounts once.
- [ ] Add typed API client and `HermesYujinStatus` beside JobRecovery.
- [ ] Extend copy policy and network guard coverage.

Files:

- `apps/web/src/api.ts`
- `apps/web/src/api.test.ts`
- new `apps/web/src/features/jobs/HermesYujinStatus.tsx`
- new `apps/web/src/features/jobs/HermesYujinStatus.test.tsx`
- `apps/web/src/app/ProductShell.tsx`
- `apps/web/src/app/ProductShell.test.tsx`
- `apps/web/src/user-copy-policy.test.ts`
- `apps/web/src/test/network-guard.test.ts` (test coverage only; no production
  guard change unless a RED test proves one is required)

## Task 4 — Read-only operator status script

- [ ] RED fake-Docker tests for not configured, absent, stopped, starting,
  HTTP-only, chat verified and degraded.
- [ ] RED strict operator DTO with exact three service rows and no raw
  container/port/mount/environment/error fields.
- [ ] RED output redaction tests.
- [ ] RED array/NDJSON Compose parsing and exact loopback/fixed-path/no-proxy/
  redirect/body-size/content-type/timeout tests.
- [ ] Implement exact-service Compose ps and optional loopback API status.

Files:

- new `scripts/get-hermes-yujin-status.ps1`
- new `tests/test_get_hermes_yujin_status_script.py`

## Task 5 — Exact named restart

- [ ] RED fake-Docker tests for exact service, unchanged container ID, bounded
  health wait and fixed failure markers.
- [ ] RED source/call guard against destructive verbs, recreate and any other
  service.
- [ ] Implement `compose restart videobox-hermes-yujin` only.

Files:

- new `scripts/restart-hermes-yujin.ps1`
- new `tests/test_restart_hermes_yujin_script.py`

## Task 6 — Canary drift repair

- [ ] RED current live canary test requiring `expected_session_revision`.
- [ ] Add explicit `ExpectedSessionRevision` argument and request field.
- [ ] Restrict live canary itself to exact loopback hosts and no
  userinfo/path/query/fragment.
- [ ] Preserve non-live network 0, redirect denial, timeout and body redaction.

Files:

- `scripts/smoke-hermes-yujin-chat.ps1`
- `tests/test_smoke_hermes_yujin_chat_script.py`

## Task 7 — Static and live-gated failure drills

- [ ] RED static mode proves Docker/network/provider calls 0 and names every
  required regression owner.
- [ ] RED live mode missing service-stop/conversation-write/disposable-project/
  positive-revision gates make Docker reads/network reads/mutations/writes 0.
- [ ] RED stage-B healthy baseline/same-ID/disposable-target read-only
  preflight failures record reads but keep Docker mutation/conversation write 0.
- [ ] RED first-safe-public-delta or prompt-accepted-active barrier, stop,
  durable interrupted/blocked, manual Director request, and `finally`
  same-ID/healthy recovery.
- [ ] RED `run_started`-only and fast-complete paths are unrun and never claim
  stop-during-stream.
- [ ] RED stop/canary/restart/health-timeout failures and recovery-fatal marker.
- [ ] RED success only after completed `finally`; recovery-fatal takes
  precedence over the original drill failure.
- [ ] Implement bounded static suite and exact-service live stop/recovery
  orchestration; abrupt process termination is recorded as an unhandled
  operational limitation.

Files:

- new `scripts/test-hermes-yujin-failure-drills.ps1`
- new `tests/test_hermes_yujin_failure_drills_script.py`
- `tests/test_agent_gateway_hermes_rpc_client.py`
- `tests/test_agent_gateway_api.py`
- `tests/test_hermes_run_store.py`
- `tests/test_hermes_run_service.py`
- `tests/test_api_hermes_conversation.py`
- `tests/test_hermes_yujin_capability_lifecycle.py`
- `apps/web/src/features/editor/workbench/hermesSseClient.test.ts`
- `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`

## Task 8 — Focused verification and independent reviews

- [ ] Run focused backend, frontend, script and static drill suites.
- [ ] Run independent spec, quality, gap and reverse reviews.
- [ ] Remediate every Critical/Important finding RED→GREEN.

## Task 9 — Full closeout

- [ ] Full Python regression.
- [ ] Full frontend and production build.
- [ ] Profile/runtime/plan-state/zero-tools/provenance/UI-system verifiers.
- [ ] If a configured local runtime exists, run the separately gated named live
  drill; otherwise record it unrun.
- [ ] Update master/child/implementation/status/handoff from fresh evidence.
- [ ] Mark C4 only complete: initiative `15/20 (75.0%)`, Phase C `4/4`.
- [ ] Keep official `9/22 (40.9%)`, remaining `59.1%`.
- [ ] Commit, push and verify upstream `0/0`.

Exact-file staging only:

```text
services/agent-gateway/src/videobox_agent_gateway/hermes_rpc_client.py
services/agent-gateway/src/videobox_agent_gateway/main.py
services/api/src/videobox_api/agent_gateway_client.py
services/api/src/videobox_api/models.py
services/api/src/videobox_api/hermes_operational_status.py
services/api/src/videobox_api/routers/hermes_operations.py
services/api/src/videobox_api/main.py
apps/web/src/api.ts
apps/web/src/api.test.ts
apps/web/src/features/jobs/HermesYujinStatus.tsx
apps/web/src/features/jobs/HermesYujinStatus.test.tsx
apps/web/src/app/ProductShell.tsx
apps/web/src/app/ProductShell.test.tsx
apps/web/src/user-copy-policy.test.ts
apps/web/src/test/network-guard.test.ts
scripts/get-hermes-yujin-status.ps1
scripts/restart-hermes-yujin.ps1
scripts/smoke-hermes-yujin-chat.ps1
scripts/test-hermes-yujin-failure-drills.ps1
tests/test_agent_gateway_hermes_rpc_client.py
tests/test_agent_gateway_api.py
tests/test_hermes_yujin_compose_contract.py
tests/test_api_hermes_operations.py
tests/test_api_hermes_project_status.py
tests/test_get_hermes_yujin_status_script.py
tests/test_restart_hermes_yujin_script.py
tests/test_smoke_hermes_yujin_chat_script.py
tests/test_hermes_yujin_failure_drills_script.py
docs/superpowers/specs/2026-07-30-videobox-hermes-yujin-c4-operations-design.md
docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-master-plan.md
docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-realtime-reliability.md
docs/superpowers/plans/2026-07-30-videobox-hermes-yujin-c4-operations.md
docs/implementation-plan.ko.md
docs/development-status-2026-06-29.ko.md
docs/handoffs/2026-07-30-videobox-hermes-yujin-phase-c-closeout.ko.md
```

Before and after staging, require `git status --short`,
`git diff --cached --name-only`, protected paths absent from the index, and
`git diff --cached --check`. Stop on unrelated tracked changes.

Do not claim actual provider, browser-human, user-media, CapCut or Task 9
acceptance unless separately executed.
