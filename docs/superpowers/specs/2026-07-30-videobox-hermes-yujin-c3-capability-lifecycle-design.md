# VideoBox Hermes Yujin C3 Capability Lifecycle Design

## 1. Purpose

C3 adds a short-lived, one-action capability lifecycle to the existing Yujin
creator run without adding a new network route or any editor mutation
authority. The capability proves only that the Agent Gateway authorized one
specific VideoBox API action for one current run:

- release the already allowlisted creator context to the existing Gateway
  reservation; or
- publish one typed proposal through the existing terminal transaction.

The capability never authorizes Apply, render, export, database access,
filesystem access, raw-media access, provider access, or arbitrary tools.

## 2. Fixed boundaries

- The Agent Gateway is the only Ed25519 issuer and the only process that
  receives the private key.
- The VideoBox API receives only the matching public key.
- Hermes, the browser, Dashboard, logs, source files, public SSE, and proposal
  bodies receive no key material and no capability token.
- The existing API-to-Gateway service token remains the transport
  authentication boundary.
- The existing `reserve -> attach -> stream -> release/cancel` topology is
  reused. There is no Gateway-to-API callback.
- The existing `hermes_capability_ledger` is the only replay/state ledger.
  C3 extends it; it does not add a second token-hash or replay table.
- The existing `director_hermes_runs`, Director messages, terminal CAS,
  creator projection, explicit Apply path, and single PreviewStage remain
  authoritative.
- Local and automated tests use injected deterministic keys and make zero
  external provider calls.

## 3. Rejected approaches

### 3.1 Gateway-to-API callback

Rejected because it adds a new inbound route, authentication direction,
retry/idempotency owner, timeout surface, and network dependency. C3 can carry
the same proof through the existing reserve response and terminal stream.

### 3.2 API-owned issuer

Rejected because it gives the API the private signing key and contradicts the
approved gateway-only issuer ownership.

### 3.3 One token with multiple actions

Rejected because consuming one action would leave ambiguous authority for the
other action. C3 issues two independent capabilities, each containing exactly
one action.

## 4. Claims and key format

The compact capability is a three-part, base64url-encoded Ed25519 signed token.
The protected header is exact:

```json
{
  "alg": "EdDSA",
  "kid": "configured-key-id",
  "typ": "VBC"
}
```

The payload has no optional or extra claims:

```text
schema_version = "videobox.yujin-capability.v1"
iss = "videobox-agent-gateway"
sub = "yujin-video-director"
aud = "videobox-api"
capability_id = opaque identifier, also used as ledger jti
project_id
conversation_id
run_id
session_id
session_revision = strict positive integer
asset_index_revision = strict non-negative integer
action = exactly "read_context" or "publish_proposal"
iat = integer UTC epoch seconds
nbf = integer UTC epoch seconds
exp = integer UTC epoch seconds
```

The lifetime is at most five minutes. `iat <= now`, `nbf <= now`, and
`exp > now` are required. The configured key ID must select the one expected
public key. Unknown algorithms, keys, claims, types, actions, or extra fields
fail closed.

The Gateway receives a base64url raw 32-byte Ed25519 private key through
`VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64`. The workspace API receives only
the base64url raw 32-byte public key through
`VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64`. Both receive the non-secret key ID.
Missing, malformed, mismatched, or placeholder configuration keeps the live
Hermes Yujin capability path unavailable. Tests inject keys directly.

The base `compose.yaml` remains non-issuing when the Yujin profile is not
selected. The `compose.hermes-yujin.yaml` overlay is the only deployed C3
authority profile: it delivers the private key only to
`videobox-agent-gateway`, the public key only to `videobox-workspace`, and the
same key ID to both. `start-hermes-yujin.ps1` refuses missing, placeholder,
malformed, or mismatched pairs before container start and verifies the merged
environment allowlists. It does not generate, print, or persist key material.
The merged Compose authority metadata must state that issuance, gateway audit,
the revoke writer, and the gateway-only lifecycle are deployed while the base
profile remains disabled.

Key replacement is a coordinated single-key operation, not a rolling
multi-key deployment. The Gateway private key, API public key, and shared
non-secret key ID are replaced together while new admissions are quiesced.
Restart reconciliation interrupts active runs and revokes their still-issued
capabilities before the new key accepts work. A token signed by the old or an
unknown key fails closed immediately after replacement. C3 does not add a key
management UI, remote KMS, overlapping verification window, or automatic key
rotation.

## 5. Existing-topology lifecycle

### 5.1 Issue and register

1. VideoBox durably creates the user message, run, and `run_started` event.
2. VideoBox calls the existing Gateway reserve endpoint with the exact run
   identity.
3. The Gateway issues one `read_context` token and one `publish_proposal`
   token.
4. The reserve response returns:
   - the existing one-time attach ticket;
   - the full `read_context` token;
   - redacted metadata for both capabilities;
   - no `publish_proposal` token.
5. The Gateway keeps the publish token only in its bounded in-memory run
   reservation.
6. VideoBox validates the response shape and registers both capability IDs as
   `issued` in the existing durable ledger with the exact run scope.
7. Registration failure releases the Gateway reservation, revokes any
   successfully registered issued capability when the ledger is available,
   and terminalizes the VideoBox run as blocked. If the ledger itself is
   unavailable, the reconciliation rule in section 5.4 applies.

The service-token-authenticated reserve response delivers metadata. The later
Ed25519 verification is the authority check; response metadata alone never
authorizes an action.

### 5.2 Consume `read_context`

1. Before sending creator context bytes, VideoBox verifies the token signature,
   header, lifetime, exact action, and exact current
   project/conversation/run/session/revision/asset-index scope.
2. The store atomically changes the matching ledger row from `issued` to
   `consumed` and appends a redacted accepted audit event.
3. Replay, revoked, expired, missing, wrong-scope, or unavailable-ledger
   results stop before the existing context attach request.
4. Only after successful consume does VideoBox send the already allowlisted
   context through the existing attach ticket.

### 5.3 Consume `publish_proposal`

1. Hermes receives only the existing untrusted-data prompt envelope. It never
   receives a capability.
2. On a valid completed Hermes stream, the Gateway adds the retained
   `publish_proposal` token to one internal terminal frame.
3. `AgentGatewayClient` parses that field but never emits it to the browser,
   public SSE, message text, logs, or proposal DTO.
4. VideoBox performs its existing strict creator projection and current
   revision/asset/source checks.
5. If there is a typed proposal, VideoBox verifies the publish token and passes
   the verified claims to the existing terminal store transaction.
6. That transaction rechecks exact run scope, atomically changes the matching
   ledger row from `issued` to `consumed`, appends the accepted audit event,
   and stores the assistant/proposal/terminal event.
7. A missing, replayed, expired, revoked, wrong-scope, or invalid publish
   capability discards the proposal and preserves a safe assistant/manual
   fallback. It never calls Apply.
8. A completed response with no proposal revokes the unused publish
   capability before or with terminal cleanup.

Signature verification occurs before the transaction; durable scope, state,
and current editor truth are rechecked in the transaction. A verified token
alone cannot publish stale data.

### 5.4 Revoke and expire

- Admission/request cancellation or prepare failure after Gateway issuance but
  before read consume releases the reservation and revokes both capabilities.
- Public explicit cancel occurs only after the run is owned by
  `HermesRunService`; it preserves an already consumed read capability and
  revokes the still-issued publish capability.
- Blocked completion, invalid response, terminal failure, Gateway release, and
  API startup reconciliation revoke all still-`issued` capabilities for that
  run.
- Successful completion revokes every still-unused capability after the
  proposal decision.
- Revocation is idempotent. It changes `issued` to `revoked` but does not
  overwrite an already `consumed` decision.
- Expired issued rows become unusable before authorization. Bounded cleanup
  runs only after the durable decision and must not turn an accepted consume
  into an error if cleanup fails.
- If the ledger or audit transaction is unavailable, authorization and
  proposal persistence fail closed with mutation zero. The process-held token
  is discarded and the Gateway reservation is released, but C3 does not claim
  that an unavailable database was durably updated. A bounded in-process retry
  and the existing startup reconciliation later atomically interrupt the run
  and transition its still-issued rows to `revoked`. Until reconciliation,
  active-run/current-revision CAS plus the unavailable/discarded token prevents
  use; expiry is the final bound. Recovery tests must prove that no provider
  retry or proposal mutation occurs.

## 6. Durable ledger and redacted audit

The existing ledger is extended with:

```text
project_id + capability_id primary identity
lifecycle_version = "videobox.yujin-capability.v1" | "legacy_retired"
conversation_id
run_id
session_id
session_revision
asset_index_revision
action
state = issued | consumed | revoked
expires_at
recorded_at
updated_at
```

An append-only audit event records each accepted registration, consume,
revocation, replay denial, scope denial, expiry denial, or unavailable
decision. It contains only:

```text
audit_event_id
capability_id = trusted durable ID or null when no exact row exists
project_id
conversation_id
run_id
action
outcome
reason
occurred_at
```

It never contains the token, signature, key, prompt, context, proposal,
assistant text, provider body, storage URI, raw media, or service credentials.
The ledger remains the only authorization state; the audit table is evidence,
not a second replay authority.

Verification receives a trusted `ExpectedCapability` loaded from the durable
issued row by the request's already-known project/run/action scope. Only after
signature and exact-claim verification may the token's claims participate in
consume. Malformed or signature-invalid token claims are untrusted input:
denial audit identity is taken only from the durable expected row and trusted
request scope, never from an unverified token, and the raw token is never
persisted or logged. If no exact expected row exists, the denial audit uses
only the trusted request identifiers that are available and no fabricated
capability ID.

The old jti-only prototype rows cannot be honestly backfilled with
conversation/run/session/revision/action scope. The SQLite table rebuild and
PostgreSQL migration therefore mark every pre-C3 row
`lifecycle_version="legacy_retired"` and leave unavailable scope columns null.
Those rows remain non-authorizing tombstones until normal expiry cleanup; their
historical consumed/revoked state is preserved and no audit history is
invented. Only newly registered, fully scoped
`videobox.yujin-capability.v1` rows may transition from `issued` to `consumed`.
The old consume-if-absent behavior is removed: consume succeeds only for one
exact, pre-registered issued row. Migration tests cover old SQLite and
PostgreSQL fixtures as well as fresh databases.

SQLite uses `BEGIN IMMEDIATE`. PostgreSQL uses the existing explicit transaction
and row-lock pattern. Concurrent consume has one winner. Registration,
consume/revoke state transition, audit append, and proposal terminal persistence
use one transaction wherever they belong to the same action.

## 7. Legacy prototype retirement

The conditional HS256 `get_project_status` capability route is an undeployed
prototype and is not part of the creator runtime. C3 removes it rather than
running two signing systems. C4 operational status continues through the
service-token-authenticated health/status boundary and does not reuse creator
capabilities.

The historical non-executing static tool contract in
`agent_gateway_contract.py` remains untouched. It is not a deployed capability
issuer or executor.

## 8. Error behavior

Internal stable reasons distinguish:

```text
hermes_capability_malformed
hermes_capability_signature_invalid
hermes_capability_key_unknown
hermes_capability_expired
hermes_capability_not_yet_valid
hermes_capability_scope_forbidden
hermes_capability_action_forbidden
hermes_capability_replayed
hermes_capability_revoked
hermes_capability_unavailable
```

Browser-facing behavior remains simple: no internal reason, token, or key is
shown. Context authorization failure blocks the run with manual editing still
available. Proposal authorization failure drops the proposal and keeps a safe
assistant/manual fallback. There is no automatic retry and no automatic Apply.

## 9. TDD acceptance matrix

### Issue and configuration

- valid Ed25519 issue produces exact header/claims and two one-action tokens;
- private key exists only in Gateway configuration;
- API configuration accepts only the matching public key;
- missing/malformed/placeholder/mismatched key configuration fails closed;
- reserve response and logs never expose the publish token or private key.
- coordinated key replacement interrupts/revokes active old-key work and an
  old or unknown key fails closed without a proposal mutation.

### Consume and replay

- valid read consume happens before context attach;
- valid publish consume is atomic with proposal terminal persistence;
- replay has exactly one winner under SQLite and PostgreSQL concurrency;
- consume of a missing row never creates a consumed row;
- legacy jti-only rows remain non-authorizing after SQLite/PostgreSQL
  migration and fresh rows retain their full scope;
- wrong project, conversation, run, session, session revision, asset-index
  revision, action, audience, issuer, subject, key, algorithm, lifetime, type,
  or extra claim is denied with mutation zero;
- malformed/signature-invalid denial audit uses only durable expected metadata
  and never an unverified claim;
- attempted `apply`, `render`, `export`, `database`, `filesystem`, or
  `raw_media` action cannot be issued or consumed.

### Revoke, failure, and restart

- admission/request cancellation or prepare failure after issuance and before
  read consume revokes both issued capabilities;
- public cancel after read consume leaves read consumed and revokes publish;
- blocked/completed-without-proposal/invalid terminal revokes publish;
- successful proposal consumes publish and leaves no issued capability;
- API restart interrupts the run and revokes its issued capability without a
  provider retry;
- repeated revoke is idempotent;
- ledger/audit failure stops authorization and preserves manual editing;
- after ledger recovery, bounded/startup reconciliation interrupts the run and
  revokes the still-issued row without provider retry or proposal mutation;
- cleanup failure after committed consume does not reverse success.

### Redaction and external effects

- audit shape contains only the nine allowlisted fields;
- token, signature, key, prompt, context, proposal, assistant text, provider
  body, raw media, storage URI, and credentials are absent from audit/log/UI;
- local/test external provider call count is zero;
- explicit Apply before user selection remains zero.

## 10. Reverse runtime trace

```text
VideoBox durable run begin
→ existing authenticated Gateway reserve
→ Gateway Ed25519 read/publish issue
→ VideoBox durable issued registration
→ verify + consume read_context
→ existing attach ticket + allowlisted context
→ existing Hermes prompt/stream
→ internal terminal publish token
→ API strict proposal projection
→ verify publish_proposal
→ terminal transaction:
   current truth CAS
   + issued→consumed
   + redacted audit
   + assistant/proposal/event
→ browser receives only durable public event/message/proposal DTO
→ user explicit selection
→ existing EditorCommandPort Apply
```

Failure trace:

```text
admission cancellation / public cancel / blocked / invalid / restart
→ revoke still-issued capability rows
→ redacted audit
→ durable blocked/interrupted truth
→ no provider retry
→ no proposal mutation
→ manual editor remains available
```

Database-unavailable recovery trace:

```text
verification or terminal transaction cannot reach ledger
→ proposal/context authorization fails closed
→ discard process-held token + release Gateway reservation
→ mutation zero and no provider retry
→ bounded retry or startup reconciliation after DB recovery
→ interrupt active run + revoke still-issued rows atomically
```

## 11. Scope exclusions

C3 does not add:

- a Gateway-to-API callback;
- source copy or OpenCut runtime;
- a new provider or provider API;
- Hermes tools, terminal, file, DB, filesystem, or raw-media access;
- Apply, render, export, or CapCut capability;
- automatic candidate selection or automatic Apply;
- Mem0 or memory injection;
- SaaS authentication, teams, billing, or cloud publishing;
- Task 9 human/environment or CapCut Desktop proof.

## 12. Success criteria

C3 is complete only when:

1. both one-action capabilities follow issued/consumed/revoked lifecycle;
2. replay and wrong-scope attempts leave proposal/editor mutation at zero;
3. publish consume and terminal proposal persistence are atomic;
4. cancel, failure, restart, and post-database-recovery reconciliation revoke
   every remaining issued capability without claiming an impossible database
   write during an outage;
5. private/public key ownership and secret-free surfaces are verified;
6. redacted audit contains no forbidden data;
7. SQLite and actual PostgreSQL concurrency/migration tests pass;
8. independent spec, quality, gap, and reverse reviews have no Critical or
   Important finding;
9. focused relevant suites, full relevant regression, build, provenance,
   plan-state, and `git diff --check` pass;
10. actual provider, human browser, user media, and CapCut checks remain
    explicitly unclaimed unless separately executed.
