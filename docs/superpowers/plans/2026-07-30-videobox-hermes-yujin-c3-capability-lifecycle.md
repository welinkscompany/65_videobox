# VideoBox Hermes Yujin C3 Capability Lifecycle Implementation Plan

> **For Codex:** Execute this plan with `subagent-driven-development`,
> `test-driven-development`, and `verification-before-completion`. Do not mark a
> checkbox complete before its RED and GREEN evidence is recorded.

**Goal:** 기존 Yujin 대화 실행에 Gateway 전용 Ed25519 발급, 정확히 한
동작만 허용하는 `read_context`/`publish_proposal` capability, durable
issue/consume/replay/revoke ledger와 redacted audit를 추가한다.

**Architecture:** 현재 API→Gateway
`reserve -> attach -> stream -> release/cancel` 경로만 재사용한다. Gateway는
private key로 두 capability를 발급하되 read token만 reserve 응답에 반환하고
publish token은 reservation에 보관했다가 내부 terminal frame에만 넣는다.
VideoBox API는 public key 검증과 durable ledger 결정을 소유한다. proposal
capability consume과 proposal/assistant/terminal 저장은 기존 terminal transaction
안에서 원자적으로 처리한다.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, `cryptography==45.0.6`,
SQLite, PostgreSQL 16, pytest, PowerShell, Docker Compose.

**Authoritative design:**
`docs/superpowers/specs/2026-07-30-videobox-hermes-yujin-c3-capability-lifecycle-design.md`

**Non-goals:** provider 추가/호출, Gateway→API callback, Apply/render/export
capability, source copy, OpenCut, Mem0, SaaS, 자동 Apply, Task 9/CapCut 사람
검증.

---

## Task 1 — Dependency and exact Ed25519 token contract

- [x] **1.1 RED:** clean development dependency and token contract tests fail.

**Files:**

- Create: `tests/test_hermes_yujin_capability_lifecycle.py`
- Modify: `requirements-agent-gateway.txt`
- Modify: `requirements-container.txt`
- Modify: `requirements-dev.txt`
- Create: `services/agent-gateway/src/videobox_agent_gateway/context_capabilities.py`
- Modify: `services/api/src/videobox_api/hermes_capabilities.py`

**Steps:**

1. In `tests/test_hermes_yujin_capability_lifecycle.py`, add tests for:
   - exact `alg=EdDSA`, `typ=VBC`, configured `kid`;
   - exact wire claims only: `schema_version`, `iss`, `sub`, `aud`,
     `capability_id`, project/conversation/run/session/revisions, one `action`,
     `iat`, `nbf`, `exp`;
   - 32-byte raw Ed25519 private/public key parsing;
   - maximum 300-second lifetime;
   - unknown/extra/missing/wrong-type claim, wrong algorithm/key/signature,
     future/expired token denial;
   - `apply`, `render`, `export`, DB, filesystem, raw-media action cannot be
     issued or verified;
   - API verifier exposes no `private_key` parameter. Raw 32-byte private and
     public material cannot be structurally distinguished; deployed runtime key ownership is verified in Task 7.
2. Run and capture RED:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_hermes_yujin_capability_lifecycle.py -q
   ```

   Expected: missing dependency/module or missing Ed25519 contract failures.

- [x] **1.2 GREEN:** implement only the pure issuer/verifier contract.

3. Pin `cryptography==45.0.6` in all three requirement files and install the
   updated development requirements into `.venv`.
4. In Gateway `context_capabilities.py`, implement:
   - strict immutable claim model;
   - canonical compact JSON and base64url codec;
   - `YujinCapabilityIssuer`;
   - two explicit helpers that can issue only `read_context` or
     `publish_proposal`;
   - injected clock and ID source for deterministic tests.
5. Replace the old HS256 prototype in API `hermes_capabilities.py` with:
   - strict Ed25519 parse/signature verifier;
   - `ExpectedCapability`;
   - `VerifiedYujinCapability`;
   - stable internal reason codes from the written design;
   - no in-memory replay authority.
6. Run GREEN and syntax checks:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_hermes_yujin_capability_lifecycle.py -q
   .\.venv\Scripts\python.exe -m py_compile services/agent-gateway/src/videobox_agent_gateway/context_capabilities.py services/api/src/videobox_api/hermes_capabilities.py
   git diff --check
   ```

---

## Task 2 — Durable scoped ledger, audit, and legacy migration

- [x] **2.1 RED:** exact registration/consume/revoke/audit/migration tests fail.

**Files:**

- Modify: `tests/test_hermes_yujin_capability_lifecycle.py`
- Modify: `tests/test_postgres_project_store.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/sqlite_schema.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/postgres_schema.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Create: `services/api/src/videobox_api/hermes_capability_audit.py`

**Steps:**

1. Add SQLite tests proving:
   - two fully scoped rows register atomically as `issued`;
   - duplicate/mismatched registration fails without a partial row;
   - consume succeeds only for an exact pre-registered `issued` row;
   - missing consume never creates a row;
   - replay has one winner;
   - revoke changes only `issued -> revoked` and is idempotent;
   - consumed is never overwritten by revoke;
   - audit has exactly nine allowlisted fields and forbidden data zero;
   - invalid-signature denial uses trusted expected metadata only;
   - no exact expected row produces `capability_id=null`;
   - a pre-C3 SQLite fixture migrates to `legacy_retired`, nullable unknown
     scope, and cannot authorize.
2. Add equivalent actual-PostgreSQL lifecycle, old-schema migration, and
   concurrent one-winner tests.
3. Run SQLite-focused RED:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_hermes_yujin_capability_lifecycle.py tests/test_postgres_project_store.py -k "hermes_capability and not postgres" -q
   ```

- [x] **2.2 GREEN:** implement one durable authority ledger and audit.

4. Rebuild/migrate `hermes_capability_ledger` with:
   - existing `(project_id, jti)` identity retained;
   - `lifecycle_version`;
   - nullable legacy scope columns;
   - action/state/timestamps;
   - no consume-if-absent behavior.
5. Create append-only `hermes_capability_audit` with exact redacted fields and
   indices for project/run/time lookup.
6. Add store primitives:
   - `register_hermes_run_capabilities(...)`;
   - `get_expected_hermes_capability(...)`;
   - `consume_registered_hermes_capability(...)`;
   - `revoke_issued_hermes_capabilities(...)`;
   - internal audit append using trusted metadata only.
7. Keep same methods in `LocalProjectStore` so `PostgresProjectStore` reuses the
   established connection/SQL compatibility layer.
8. Run GREEN:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_hermes_yujin_capability_lifecycle.py tests/test_postgres_project_store.py -k "hermes_capability and not postgres" -q
   git diff --check
   ```

---

## Task 3 — Gateway issue, reservation ownership, and token non-exposure

- [x] **3.1 RED:** Gateway reserve/attach/stream tests expose missing lifecycle.

**Files:**

- Modify: `tests/test_agent_gateway_api.py`
- Modify: `tests/test_agent_gateway_creator_context.py`
- Modify: `tests/test_agent_gateway_hermes_rpc_client.py`
- Modify: `services/agent-gateway/src/videobox_agent_gateway/creator_context.py`
- Modify: `services/agent-gateway/src/videobox_agent_gateway/main.py`

**Steps:**

1. Add tests proving:
   - reserve issues read/publish tokens with different IDs and one action each;
   - reserve response returns read token plus redacted metadata for both, but no
     publish token;
   - reservation retains publish token until stream ownership;
   - attach ticket behavior and exact identity checks remain unchanged;
   - internal `run_completed` frame alone carries publish token;
   - Gateway API route response and exact NDJSON schemas reject token placement
     on every nonterminal/blocked surface;
   - text delta, blocked frame, Hermes prompt, logs, and error bodies carry no
     token/key;
   - release/expiry removes the retained publish token;
   - capacity/replay behavior stays bounded.
2. Run RED:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_agent_gateway_api.py tests/test_agent_gateway_creator_context.py tests/test_agent_gateway_hermes_rpc_client.py -q
   ```

- [x] **3.2 GREEN:** extend the existing reservation, not the network topology.

3. Inject `YujinCapabilityIssuer` into `CreatorContextLedger/create_app`.
4. Make `reserve` return a structured bundle containing:
   - ticket;
   - read token;
   - trusted redacted read/publish metadata;
   - retained publish token stored only inside `_Reservation`.
5. Make `consume` transfer the retained publish token to the stream generator
   as process-local data.
6. Add the token only to the final internal `run_completed` NDJSON frame.
7. Keep Gateway endpoints, service-token authentication, network direction,
   context allowlist, and Hermes zero-tools path unchanged.
8. Make `_app_from_environment` fail closed to health-only mode when private
   key/key ID is absent or invalid.
9. Run GREEN:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_agent_gateway_api.py tests/test_agent_gateway_creator_context.py tests/test_agent_gateway_hermes_rpc_client.py -q
   .\.venv\Scripts\python.exe -m py_compile services/agent-gateway/src/videobox_agent_gateway/context_capabilities.py services/agent-gateway/src/videobox_agent_gateway/creator_context.py services/agent-gateway/src/videobox_agent_gateway/main.py
   git diff --check
   ```

---

## Task 4 — API reservation/register/read-consume/attach order

- [x] **4.1 RED:** reverse-order and failure-path client/service tests fail.

**Files:**

- Modify: `tests/test_agent_gateway_client.py`
- Modify: `tests/test_hermes_run_service.py`
- Modify: `services/api/src/videobox_api/agent_gateway_client.py`
- Modify: `services/api/src/videobox_api/hermes_run_service.py`

**Steps:**

1. Add tests that record exact call order:

   ```text
   durable begin
   -> Gateway reserve
   -> durable register read+publish
   -> load trusted expected read
   -> Ed25519 verify
   -> durable read consume+audit
   -> Gateway attach
   -> dispatch
   ```

2. Add failure tests:
   - malformed reservation shape releases Gateway and blocks run;
   - registration failure releases Gateway, revokes any registered row, and
     blocks;
   - read verify/replay/scope/audit failure stops before attach;
   - admission/request cancellation after issuance and before read consume
     releases Gateway and revokes both;
   - public cancel after read consume revokes publish only;
   - manual editing remains available and provider retry count stays zero.
3. Run RED:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_agent_gateway_client.py tests/test_hermes_run_service.py -q
   ```

- [x] **4.2 GREEN:** split prepare into explicit reservation and attach phases.

4. Add strict `AgentGatewayReservation`/capability metadata models.
5. Split `prepare_run` internally into:
   - `reserve_run(...) -> AgentGatewayReservation`;
   - `attach_run_context(..., reservation, context)`.
6. In `_admit`, coordinate durable registration and read authorization between
   those calls. Do not expose `_Run` or start dispatch before attach succeeds.
7. Add one bounded cleanup owner for admission failures; do not add provider
   auto retry.
8. Run GREEN:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_agent_gateway_client.py tests/test_hermes_run_service.py tests/test_api_hermes_conversation.py -q
   git diff --check
   ```

---

## Task 5 — Publish verification and atomic terminal transaction

- [x] **5.1 RED:** proposal persistence is impossible without exact publish consume.

**Files:**

- Modify: `tests/test_hermes_yujin_capability_lifecycle.py`
- Modify: `tests/test_hermes_run_service.py`
- Modify: `tests/test_postgres_project_store.py`
- Modify: `services/api/src/videobox_api/agent_gateway_client.py`
- Modify: `services/api/src/videobox_api/hermes_run_service.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`

**Steps:**

1. Add tests proving:
   - API client accepts publish token only on exact completed terminal frame;
   - publish token on delta/blocked/multiple terminal/extra field is rejected;
   - no proposal revokes unused publish capability;
   - valid proposal verifies against trusted expected row;
   - proposal insert, assistant message, terminal event, audit, and
     `issued -> consumed` commit atomically;
   - signature/replay/scope/current-revision/asset-index failure stores no
     proposal and no editor mutation, then stores safe assistant/manual
     fallback and revokes unused publish row;
   - transaction fault rolls back proposal, consume, audit, message, and
     terminal together;
   - Apply call count remains zero.
2. Run RED:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_hermes_yujin_capability_lifecycle.py tests/test_hermes_run_service.py tests/test_postgres_project_store.py -k "hermes_capability or publish_proposal" -q
   ```

- [x] **5.2 GREEN:** bind verified publish authority to terminal CAS.

3. Extend `AgentGatewayEvent` with process-local terminal capability data that
   is never serialized to public SSE/messages/proposals.
4. Store the terminal token only long enough for
   `_finish_terminal_serialized`.
5. Verify signature and exact trusted expected scope before the store call.
6. Extend `complete_director_hermes_run` with an internal verified capability
   decision:
   - exact issued row/current run/current revision recheck;
   - atomic consume+accepted audit when proposal exists;
   - atomic revoke when no proposal/blocked;
   - stable denial result that triggers proposal discard and one safe
     no-proposal terminal retry.
7. Preserve existing proposal collision/stale handling, candidate-only/manual
   fallback, and explicit `EditorCommandPort` Apply path.
8. Run GREEN:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_hermes_yujin_capability_lifecycle.py tests/test_hermes_run_service.py tests/test_postgres_project_store.py -k "hermes_capability or publish_proposal" -q
   git diff --check
   ```

---

## Task 6 — Cancel, restart reconciliation, DB outage, and key replacement

- [x] **6.1 RED:** lifecycle cleanup/recovery tests fail.

**Files:**

- Modify: `tests/test_hermes_yujin_capability_lifecycle.py`
- Modify: `tests/test_hermes_run_service.py`
- Modify: `tests/test_postgres_project_store.py`
- Modify: `services/api/src/videobox_api/main.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`

**Steps:**

1. Add tests for:
   - explicit cancel: consumed read remains consumed, issued publish revoked;
   - blocked/invalid/timeout/release: all remaining issued rows revoked;
   - startup recovery interrupts orphan and revokes issued rows in the same
     transaction;
   - ledger unavailable: authorization/proposal mutation zero, process token
     discarded, Gateway released;
   - after DB recovery, bounded/startup reconciliation revokes issued rows with
     provider retry zero;
   - old-key active run is interrupted/revoked during coordinated restart;
   - cleanup-after-consume failure does not reverse committed success.
2. Run RED.

- [x] **6.2 GREEN:** make cleanup durable when possible and honest during outage.

3. Fold capability revocation and audit into existing cancel/terminal/recovery
   transactions.
4. Add a bounded reconciliation task owner to API lifespan; reuse startup
   orphan recovery and do not create a provider retry loop.
5. During DB outage, fail closed and release/discard process state without
   claiming a durable write.
6. Run GREEN:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_hermes_yujin_capability_lifecycle.py tests/test_hermes_run_service.py tests/test_postgres_project_store.py -k "hermes_capability or recover_interrupted or reconciliation_scope or recovery_holds or public_cancel" -q
   git diff --check
   ```

---

## Task 7 — Retire HS256 prototype and wire the profile safely

- [x] **7.1 RED:** deployment contract tests fail for old route or wrong key placement.

**Files:**

- Modify: `tests/test_hermes_capability_authority_contract.py`
- Modify/retire: `tests/test_api_hermes_project_status.py`
- Modify: `tests/test_hermes_yujin_compose_contract.py`
- Modify: `tests/test_start_hermes_yujin_script.py`
- Modify: `services/api/src/videobox_api/hermes_capability_authority.py`
- Delete: `services/api/src/videobox_api/routers/hermes_internal.py`
- Modify: `services/api/src/videobox_api/main.py`
- Modify: `compose.yaml`
- Modify: `compose.hermes-yujin.yaml`
- Modify: `.env.container.example`
- Modify: `scripts/start-hermes-yujin.ps1`

**Steps:**

1. Add tests proving:
   - old conditional `/internal/hermes/projects/{project_id}/status` route and
     HS256 signer are absent;
   - base Compose remains non-issuing;
   - Yujin overlay gives private key only to Gateway, public key only to
     workspace, same key ID to both;
   - Hermes container receives neither key;
   - start script rejects missing/placeholder/malformed/mismatched pair;
   - start script/output never prints key material;
   - merged authority metadata says C3 lifecycle/audit/revoke writer deployed;
   - coordinated single-key replacement is the only supported rotation mode.
2. Run RED:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_hermes_capability_authority_contract.py tests/test_api_hermes_project_status.py tests/test_hermes_yujin_compose_contract.py tests/test_start_hermes_yujin_script.py -q
   ```

- [x] **7.2 GREEN:** remove the prototype and validate exact environment ownership.

3. Remove the router and old conditional verifier injection from `create_app`.
4. Update the authority contract to distinguish disabled base vs deployed
   Yujin overlay.
5. Add capability environment variables to example/overlay/start validation.
6. Validate private→public derivation with the pinned library without
   generating/storing/printing keys.
7. Run GREEN plus static verifiers:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_hermes_capability_authority_contract.py tests/test_api_hermes_project_status.py tests/test_hermes_yujin_compose_contract.py tests/test_start_hermes_yujin_script.py -q
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-profile.ps1 -StaticOnly
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-runtime.ps1 -StaticOnly
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-zero-tools.ps1
   git diff --check
   ```

---

## Task 8 — Actual PostgreSQL and focused reverse acceptance

- [x] **8.1** Run all C3 focused tests and actual PostgreSQL with zero relevant
skip.

**Execution evidence (2026-07-30):**

- C3 focused set: `435 passed, 30 skipped`; the skips are the PostgreSQL-only
  cases before `VIDEOBOX_TEST_POSTGRES_URL` is supplied, not claimed as pass.
- Disposable PostgreSQL 16 C3 selection: `14 passed, 19 deselected`, zero
  relevant skip; exact container
  `videobox-codex-c3-postgres-20260730` was removed and verified absent.
- Reverse acceptance selection: `13 passed`, covering forbidden Apply and
  other forbidden actions, publish without authority, consume ordering and
  replay, old/unknown key rejection, and ledger outage reconciliation.

**Steps:**

1. Run the focused set:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_hermes_yujin_capability_lifecycle.py tests/test_hermes_capability_authority_contract.py tests/test_agent_gateway_api.py tests/test_agent_gateway_creator_context.py tests/test_agent_gateway_hermes_rpc_client.py tests/test_agent_gateway_client.py tests/test_hermes_run_service.py tests/test_api_hermes_conversation.py tests/test_postgres_project_store.py tests/test_hermes_yujin_compose_contract.py tests/test_start_hermes_yujin_script.py -q
   ```

2. Start one exact disposable PostgreSQL 16 container, set
   `VIDEOBOX_TEST_POSTGRES_URL`, run the C3 migration/concurrency tests, record
   zero relevant skip, then remove only that exact named container and verify
   it is absent.

   ```powershell
   $c3PgName = "videobox-codex-c3-postgres-20260730"
   $c3Existing = docker ps -a --filter "name=^/$c3PgName$" --format "{{.Names}}"
   if ($c3Existing -contains $c3PgName) {
       throw "Refusing to reuse or remove an existing C3 PostgreSQL container."
   }
   $c3PgCreatedByThisRun = $false
   try {
       docker run -d --name $c3PgName -e POSTGRES_PASSWORD=videobox-c3-test -e POSTGRES_DB=videobox -p 127.0.0.1::5432 postgres:16-alpine
       if ($LASTEXITCODE -ne 0) { throw "Could not create C3 disposable PostgreSQL." }
       $c3PgCreatedByThisRun = $true
       for ($attempt = 0; $attempt -lt 30; $attempt++) {
           docker exec $c3PgName pg_isready -U postgres -d videobox
           if ($LASTEXITCODE -eq 0) { break }
           Start-Sleep -Seconds 1
       }
       if ($LASTEXITCODE -ne 0) { throw "C3 disposable PostgreSQL did not become ready." }
       $c3PgPort = ((docker port $c3PgName 5432/tcp) -split ":")[-1]
       $env:VIDEOBOX_TEST_POSTGRES_URL = "postgresql://postgres:videobox-c3-test@127.0.0.1:$c3PgPort/videobox"
       .\.venv\Scripts\python.exe -m pytest tests/test_postgres_project_store.py -k "hermes_capability or publish_proposal or publish_terminal or recover_interrupted" -q
       if ($LASTEXITCODE -ne 0) { throw "C3 PostgreSQL capability tests failed." }
   }
   finally {
       Remove-Item Env:VIDEOBOX_TEST_POSTGRES_URL -ErrorAction SilentlyContinue
       if ($c3PgCreatedByThisRun) {
           docker rm -f -- $c3PgName
       }
   }
   $c3Remaining = docker ps -a --filter "name=^/$c3PgName$" --format "{{.Names}}"
   if ($c3Remaining -contains $c3PgName) {
       throw "C3 disposable PostgreSQL container still exists."
   }
   ```

3. Run reverse tests from these attempted outcomes:
   - forged Apply capability;
   - proposal persisted without publish consume;
   - context attached before read consume;
   - replay winner twice;
   - old/unknown key after replacement;
   - DB outage followed by reconciliation.
4. Confirm every reverse trace stops before proposal/editor mutation and
   preserves manual fallback.

---

## Task 9 — Independent reviews and remediation

- [x] **9.1** Independent spec review.
- [x] **9.2** Independent code-quality review.
- [x] **9.3** Independent gap review.
- [x] **9.4** Independent reverse-runtime review.
- [x] **9.5** Remediate every Critical/Important finding with RED→GREEN tests.

**Review and remediation evidence (2026-07-30):**

- Final independent spec, quality, and gap/reverse reviews all reported
  `Critical 0 / Important 0 / Minor 0`.
- Read consume now rechecks and locks current session and asset-index truth
  before the capability ledger, preserving the PostgreSQL
  `session -> asset -> ledger` order and stopping stale context before attach.
- Capability-preparation failures return one fixed redacted `503`, record
  stable trusted/null-ID denial audits as appropriate, revoke issued
  capabilities, and preserve manual fallback with attach/provider/editor
  mutation zero.
- The PostgreSQL consume/revoke barrier identifies the consume worker
  explicitly; the final actual PostgreSQL store suite passed
  `38 passed, 0 skipped`, and the exact disposable container was removed and
  verified absent.
- Final focused remediation set passed `219 passed`; its `33 skipped` cases
  are PostgreSQL-only and are covered by the preceding actual PostgreSQL run.

**Review boundaries:**

- exact authoritative design conformance;
- token/key non-exposure;
- trusted-vs-untrusted audit identity;
- SQLite/PostgreSQL atomicity and migration;
- cancel/restart/outage honesty;
- explicit Apply/manual fallback;
- local/test external provider call count zero.

---

## Task 10 — Full verification, SSOT, commit, and push

- [x] **10.1** Run full relevant verification.
- [x] **10.2** Update plan/status/handoff only from fresh evidence.
- [x] **10.3** Commit and push one logically closed C3 implementation.

**Closeout evidence (2026-07-30):**

- C3 focused suite: `468 passed, 33 skipped`; the skips are PostgreSQL-only
  cases, separately executed against disposable PostgreSQL 16 as `38 passed,
  0 skipped`, with the exact container removed afterward.
- Full Python regression after final remediation: `2367 passed, 41 skipped,
  1 warning`; the warning is the existing Starlette multipart deprecation.
- Full frontend: `50 files / 668 tests passed`; production build passed with
  the existing non-failing 500 kB chunk warning.
- Hermes profile/runtime/plan-state/zero-tools, Editor UI source provenance and
  UI-system verifiers passed. `git diff --check` passed.
- Independent spec, quality, gap, reverse-runtime and final two-file regression
  review all ended `Critical 0 / Important 0 / Minor 0`.
- C3 closeout commit `c7d439e` was pushed to
  `origin/codex/videobox-container-compatibility`.
- No actual Hermes/provider call, browser human E2E, user-media acceptance,
  CapCut Desktop proof or Task 9 human/environment acceptance was claimed.

**Verification:**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_hermes_yujin_capability_lifecycle.py tests/test_hermes_capability_authority_contract.py tests/test_agent_gateway_api.py tests/test_agent_gateway_creator_context.py tests/test_agent_gateway_hermes_rpc_client.py tests/test_agent_gateway_client.py tests/test_hermes_run_service.py tests/test_api_hermes_conversation.py tests/test_postgres_project_store.py tests/test_hermes_yujin_compose_contract.py tests/test_start_hermes_yujin_script.py -q
# After every review remediation, repeat the exact disposable PostgreSQL 16
# block from Task 8 and require the C3 PostgreSQL cases to execute without skip.
.\.venv\Scripts\python.exe -m pytest -q
npm --prefix apps/web test -- --run
npm --prefix apps/web run build
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-profile.ps1 -StaticOnly
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-runtime.ps1 -StaticOnly
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-plan-state.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-hermes-yujin-zero-tools.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-editor-ui-source-provenance.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-editor-ui-system.ps1
git diff --check
```

**SSOT files:**

- Modify: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-master-plan.md`
- Modify: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-realtime-reliability.md`
- Modify: `docs/implementation-plan.ko.md`
- Modify: `docs/development-status-2026-06-29.ko.md`
- Create: `docs/handoffs/2026-07-30-videobox-hermes-yujin-c3-closeout.ko.md`

**Closeout rules:**

- C3 and only C3 becomes `[x]`.
- Hermes Yujin initiative becomes `14/20 (70.0%)`, remaining `30.0%`.
- Phase C becomes `3/4 (75.0%)`.
- Official cumulative remains `9/22 (40.9%)`, remaining `59.1%`.
- Actual provider/browser human/user media/CapCut/Task 9 remain unclaimed.
- Next goal is C4 only.

**Commit:**

```powershell
git diff --check
git status --short
git branch --show-current
git rev-parse HEAD
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
git rev-list --left-right --count HEAD...origin/codex/videobox-container-compatibility
git worktree list
git add -- requirements-agent-gateway.txt requirements-container.txt requirements-dev.txt services/agent-gateway/src/videobox_agent_gateway/context_capabilities.py services/agent-gateway/src/videobox_agent_gateway/creator_context.py services/agent-gateway/src/videobox_agent_gateway/main.py services/api/src/videobox_api/hermes_capabilities.py services/api/src/videobox_api/hermes_capability_authority.py services/api/src/videobox_api/hermes_capability_audit.py services/api/src/videobox_api/agent_gateway_client.py services/api/src/videobox_api/hermes_run_service.py services/api/src/videobox_api/main.py services/api/src/videobox_api/routers/hermes_internal.py packages/storage-abstractions/src/videobox_storage/local_project_store.py packages/storage-abstractions/src/videobox_storage/sqlite_schema.py packages/storage-abstractions/src/videobox_storage/postgres_schema.py tests/test_hermes_yujin_capability_lifecycle.py tests/test_postgres_project_store.py tests/test_agent_gateway_api.py tests/test_agent_gateway_creator_context.py tests/test_agent_gateway_hermes_rpc_client.py tests/test_agent_gateway_client.py tests/test_hermes_run_service.py tests/test_api_hermes_conversation.py tests/test_hermes_capability_authority_contract.py tests/test_api_hermes_project_status.py tests/test_hermes_yujin_compose_contract.py tests/test_start_hermes_yujin_script.py compose.yaml compose.hermes-yujin.yaml .env.container.example scripts/start-hermes-yujin.ps1 docs/superpowers/specs/2026-07-30-videobox-hermes-yujin-c3-capability-lifecycle-design.md docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-master-plan.md docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-realtime-reliability.md docs/superpowers/plans/2026-07-30-videobox-hermes-yujin-c3-capability-lifecycle.md docs/implementation-plan.ko.md docs/development-status-2026-06-29.ko.md docs/handoffs/2026-07-30-videobox-hermes-yujin-c3-closeout.ko.md
git diff --cached --check
git status --short
git commit -m "feat: complete Yujin capability lifecycle"
git push origin codex/videobox-container-compatibility
$c3Head = git rev-parse HEAD
$c3UpstreamHead = git rev-parse origin/codex/videobox-container-compatibility
if ($c3Head -cne $c3UpstreamHead) { throw "C3 push did not synchronize HEAD and upstream." }
git rev-list --left-right --count HEAD...origin/codex/videobox-container-compatibility
```

Never stage, delete, inspect, or alter:

- `.tmp-final-fence-debug/`
- `.tmp-real-video-dogfood/`
- `apps/web/.tmp-real-video-dogfood/`
