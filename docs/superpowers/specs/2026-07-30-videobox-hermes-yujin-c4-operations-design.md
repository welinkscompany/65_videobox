# VideoBox Hermes Yujin C4 operations design

Date: 2026-07-30
Status: implementation contract
Parent: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-master-plan.md`

## 1. Goal

C4 makes Yujin operations truthful and recoverable without giving the browser
host or Docker authority.

It must:

- distinguish process/HTTP readiness from provider and completed-chat evidence;
- show a lazy, read-only status in the existing VideoBox job-status dialog;
- restart only `videobox-hermes-yujin` through an operator script;
- preserve OAuth state, old containers, manual editing, durable run recovery and
  all C1-C3 fences;
- provide static failure-drill evidence without external provider calls and a
  separately gated live drill surface.

## 2. Source-grounded ownership

- `ProductShell` owns the existing global `작업 상태` dialog.
- the browser may call only a same-origin VideoBox API route;
- VideoBox API may call only the existing internal Agent Gateway client;
- Agent Gateway may probe only the internal
  `http://videobox-hermes-yujin:9120/api/status`;
- Docker state and restart remain local PowerShell operator actions;
- the official `videobox-hermes-dashboard` remains provider configuration UI
  and is never restarted by C4.

The retired project route
`/internal/hermes/projects/{project_id}/status` remains absent.

## 3. Status contract

The public same-origin DTO is global, not project-scoped:

```text
GET /api/hermes-yujin/status

state:
  not_configured | stopped | starting | http_ready |
  provider_ready | chat_verified | degraded

http_ready: boolean
provider_ready: boolean
chat_verified: boolean
checked_at: UTC timestamp
last_chat_verified_at: UTC timestamp | null
restart_available: false
status_basis: application_path
```

`restart_available` is always false in the browser because there is no approved
host bridge.

Precedence:

1. no configured Agent Gateway client → `not_configured`;
2. configured but the Gateway conversation path is unreachable, with no prior
   verified chat → `stopped`;
3. Gateway conversation path reachable but Hermes HTTP probe false, with no
   prior verified chat → `starting`;
4. Hermes HTTP true, no provider/chat evidence → `http_ready`;
5. provider response observed but no completed chat → `provider_ready`;
6. a complete provider-backed message observed → `chat_verified`;
7. after a previously observed verified chat, an allowlisted later
   transport/auth/provider failure → `degraded`.

`http_ready` and `provider_ready` must never be displayed as `chat_verified`.
In the browser, `stopped` and `starting` describe application-path
availability, not a Docker container fact. User copy says “연결할 수 없음” or
“연결 준비 중”. Only the operator script may report Docker-observed service
state, with `status_basis: docker_compose`.

The API status service tracks the Gateway `observation_epoch`. When it changes,
API-local verified/degraded memory is discarded. After API restart it may trust
only fresh evidence returned by the current Gateway epoch. Evidence must be:

- produced after the Gateway process start;
- inside a fixed 10-minute freshness TTL;
- still before `evidence_valid_until`.

Expired evidence falls back to `http_ready`; the old
`last_chat_verified_at` is reference-only and cannot keep readiness elevated.

## 4. Gateway observation

Gateway `/health` remains internal process/readiness metadata. It may add only
allowlisted booleans/timestamps:

- `gateway_configured`
- `capability_routes_ready`
- `hermes_http_ready`
- `provider_ready`
- `chat_ready`
- `degraded`
- `observation_epoch`
- `process_started_at`
- `provider_observed_at`
- `last_chat_verified_at`
- `evidence_valid_until`
- `status_basis: gateway_observation`

The HTTP probe discards the Hermes response body and never mints a ticket,
starts a prompt or calls an external provider.

The probe is an explicit injected protocol so unconfigured/minimal test fakes
do not accidentally gain network behavior.

One locked observer owns a monotonic `(run_generation, event_sequence)`.
An older run's late failure cannot overwrite a newer run's success, and a
delayed HTTP probe cannot overwrite a newer stream observation.

Provider readiness is observed in `main._stream_public_lines` only after a
non-empty delta has passed all redaction/shape checks and is being emitted as a
public frame. Chat verification is observed only after a sanitized non-empty
`run_completed` public frame is emitted. A safe complete-only reply may move
directly to `chat_verified`.

Only final transport/auth/provider codes such as timeout, unavailable and
exhausted ticket expiry may mark degraded. Explicit user cancel/interruption,
browser SSE disconnect, stale/replayed capability, local validation, unsafe
output and malformed frame rejection do not change global readiness.

Degraded is sticky within the current observation epoch. HTTP recovery or one
delta cannot clear it; only a later valid public completion from a newer
generation returns to `chat_verified`. This is Gateway-level chat evidence,
not proof that a proposal was durably published or applied in the editor.

No username, password, password hash, cookie, ticket, service token,
capability, provider response body, prompt, media path or Mem0 record may
appear in health/status output or logs.

## 5. Browser UI

Create a small `HermesYujinStatus` panel in the existing `작업 상태` dialog.

- it mounts and fetches only after the dialog opens;
- it supports an explicit `다시 확인` read action;
- refresh is single-flight and stale responses do not replace a newer result;
- client request epoch and strict timezone-aware server `checked_at` both fence
  stale responses;
- fetch failure shows a simple unavailable message and manual-editing guidance;
- it does not poll on the application hot path;
- it does not expose a restart button or Docker/runtime/provider jargon;
- `JobRecovery`, navigation and editor controls remain usable.

The editor RightDock manual fallback remains authoritative and unchanged.

## 6. Operator scripts

### Read-only status

`scripts/get-hermes-yujin-status.ps1`:

- accepts an approved env file and injectable Docker executable for tests;
- uses exact Compose files/profile and read-only `ps`;
- parses only service/state/health/exit-code allowlisted fields;
- optionally queries the same-origin status route after exact services are
  running;
- emits one sanitized JSON DTO;
- never emits raw Docker JSON, stderr, labels, environment, mounts, logs or
  provider bodies.

Its operator DTO is strict and separate from the browser DTO:

```text
schema_version: v1
state: the seven-state vocabulary
status_basis: docker_compose
checked_at: strict UTC timestamp
http_ready: boolean
provider_ready: boolean
chat_verified: boolean
last_chat_verified_at: UTC timestamp | null
application_status_checked: boolean
services: exactly three rows
  name: videobox-workspace | videobox-agent-gateway | videobox-hermes-yujin
  present: boolean
  running: boolean
  health: unknown | starting | healthy | unhealthy
  exit_code: integer | null
```

No `restart_available`, container ID, raw error, port, mount, environment or
provider field is emitted. When configuration is missing, the three fixed
service rows remain present with `present=false` and no Docker call.

Compose JSON array and line-delimited JSON forms are both accepted, but only
exact allowlisted fields are parsed. stdout/stderr are drained concurrently.

The optional API URI is exact loopback only (`127.0.0.1`, `::1` or
`localhost`), fixed `/api/hermes-yujin/status`, no credentials/query/fragment,
redirects or environment proxy, with a short timeout, bounded body, JSON
content type and strict DTO.

Missing env/config is `not_configured`; configured absent/exited Yujin is
Docker-observed `stopped`; running but not healthy is Docker-observed
`starting`.

### Named restart

`scripts/restart-hermes-yujin.ps1`:

- has no free service-name parameter;
- targets only `videobox-hermes-yujin`;
- uses `docker compose restart videobox-hermes-yujin`;
- verifies the exact container ID is unchanged and waits boundedly for health;
- never uses `down`, `rm`, `remove`, `kill`, `prune`, `--volumes`, `-v`,
  `--force-recreate`, or another service;
- never creates, deletes or replaces the OAuth named volume;
- returns fixed redacted markers on failure.

Capability-key rotation remains owned by the coordinated
`start-hermes-yujin.ps1` path, not this restart action.

## 7. Failure drills

`scripts/test-hermes-yujin-failure-drills.ps1 -StaticOnly` is network-free and
Docker-free. It runs the bounded regression owners for:

- SSE disconnect/reconnect and Last-Event-ID duplicate suppression;
- exact pre-accept ticket expiry retry;
- connection/provider failure without automatic provider retry;
- API startup orphan → interrupted without redispatch;
- active capability revoke during recovery;
- blocked/unavailable UI with manual editor controls.

Live mode is separate and requires all of:

- `-Live`
- `-ConfirmServiceStop`
- `-ConfirmConversationWrite`
- `-ConfirmDisposableProject`
- approved env file
- explicit dedicated disposable project, session and strictly positive expected
  revision
- loopback VideoBox base URI

Preflight has two stages:

1. a pure syntactic gate validates switches, env-file shape, exact loopback URI,
   positive revision and disposable selectors. Failure here means Docker reads,
   network reads, Docker mutations and conversation writes are all 0;
2. only after stage 1, read-only Docker/API preflight verifies the exact Yujin
   container exists, is running and healthy, records its ID, and verifies the
   supplied project/session is the explicitly confirmed disposable target.
   Failure here records the actual read counts but keeps Docker mutations and
   conversation writes at 0.

The live drill creates a disposable run with a streaming HTTP reader and waits
for a bounded first safe public delta or an explicit Gateway
prompt-accepted-active barrier. Only after that provider-active barrier may it
record and execute `stop during stream`. Durable `run_started` alone is only
`stop after run creation` evidence and cannot satisfy this drill. A fast
completion or missing provider-active barrier is `unrun`, not success.

After any successful stop, every ordinary exit path uses `finally` to call the
exact restart script, require the same container ID and bounded healthy state,
then run the corrected bounded canary. Stop failure, stream/canary failure,
restart failure and health timeout have separate fixed markers; recovery
failure can never emit success. Abrupt process termination cannot guarantee
PowerShell `finally` and remains an explicit operational limitation.

The success marker is emitted only after `finally` finishes successfully and
outside the protected block. A recovery-fatal marker takes precedence over the
original drill failure so an operator cannot overlook a service left unhealthy.

The drill also verifies the durable run closes blocked/interrupted and performs
one legacy manual Director request against the confirmed disposable
conversation. Conversation rows are preserved as evidence; proposal creation
is possible, but automatic Apply/editor mutation remains 0.

It may stop/restart only `videobox-hermes-yujin`. It must not claim
browser-human, provider quality, user-media or CapCut proof.

The existing live chat canary must send `expected_session_revision`; otherwise
it is not a valid current API canary.

## 8. TDD acceptance matrix

| Boundary | RED acceptance |
|---|---|
| status DTO | strict seven-state DTO; no raw/unknown fields |
| HTTP truth | HTTP ready never becomes chat verified |
| observation | delta→provider ready; complete→chat verified; later failure→degraded |
| freshness | epoch/TTL/clock-skew and Gateway/API restart discard stale evidence |
| ordering | older late failure cannot overwrite newer success; valid new complete clears degraded |
| failure class | cancel/stale/replay/unsafe/malformed do not degrade |
| API absence | unconfigured/stopped fixed states and no internal detail |
| UI lazy load | dialog closed means status request 0 |
| UI fallback | status failure leaves jobs/navigation/manual editor usable |
| restart | exact one service, same container ID, no destructive verb/volume mutation |
| static drills | Docker/network/provider calls 0 |
| live gate A | invalid pure inputs cause Docker/network/write calls 0 |
| live gate B | read-only preflight failure records reads but mutation/write 0 |
| live recovery | healthy preflight, stream barrier and finally same-ID recovery |
| redaction | credentials, tickets, hashes, bodies and memory records absent |

## 9. Reverse runtime trace

```text
operator GET status
  -> Compose ps exact services
  -> optional loopback VideoBox status
  -> API internal Gateway health
  -> Gateway local Hermes HTTP probe only
  -> sanitized status

creator chat
  -> existing reserve/attach/stream
  -> safe non-empty public delta records provider observation
  -> safe non-empty public completion records chat verification
  -> allowlisted later transport/auth/provider failure records degraded
  -> epoch/TTL and monotonic generation reject stale observations
  -> no automatic Apply

operator restart
  -> exact Compose restart videobox-hermes-yujin
  -> same container ID + bounded health wait
  -> Gateway/API remain separate
  -> interrupted/blocked run uses existing durable recovery
  -> manual editor remains available
```

## 10. Non-goals

- browser-triggered restart or privileged host bridge
- Docker socket mount in workspace/API/web
- official Hermes dashboard source modification
- source copy, OpenCut runtime, unsupported effects or automatic Apply
- Mem0 implementation
- provider credential setup, SaaS, billing or multi-user operations
- Task 9 human/environment or CapCut Desktop acceptance

## 11. Self-review

Rejected alternatives:

1. Treating `/health` as chat success: false and unsafe.
2. Browser Docker control: requires a privileged bridge outside the approved
   authority model.
3. Reviving the project-scoped internal status route: wrong global ownership
   and conflicts with its retirement test.
4. Always-on polling: adds hot-path load and stale global state to every
   editor route.
5. Restart by recreate/down: can replace containers or disturb OAuth state.
6. Treating Gateway-unreachable as proven Docker stopped: only the operator
   script has that source of truth.

The chosen design keeps status read-only in the product, restart local and
named, and live/destructive evidence separately gated.
