# VideoBox Hermes Yujin Integration Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자가 VideoBox 편집기 안에서 Yujin과 실시간으로 대화하고, Yujin의 추천을 검토한 뒤 선택 적용하여 실제 유튜브 영상을 빠르게 완성할 수 있게 한다.

**Architecture:** VideoBox가 프로젝트·타임라인·미디어의 유일한 진실 공급원과 실행 권한을 유지한다. 전용 `videobox-agent-gateway`가 공식 Hermes `serve` 런타임의 유일한 클라이언트가 되고, VideoBox API는 gateway를 거쳐 allowlist 문맥을 전달하며 브라우저에는 SSE만 중계한다. Docker topology는 workspace↔gateway API 전용 internal network와 gateway↔Hermes 전용 internal network를 분리하고, Hermes만 별도 provider-egress에 연결한다. 따라서 Docker forwarding 없이 gateway process만 application level에서 두 신뢰 구간을 잇는다. 모든 실제 편집은 기존 `EditorCommandPort`, revision fence, route epoch, one-player preview 경계를 재사용한다. Mem0는 Hermes 소유 보조기억이며 VideoBox 상태 저장소가 아니다.

**Tech Stack:** VideoBox Python 3.12, official Hermes image Python 3.13, FastAPI, Pydantic, httpx, websockets, React 19, TypeScript, Vitest, Docker Compose, Mem0 Platform

---

## 1. Authority and linked documents

- Written design: `docs/superpowers/specs/2026-07-26-videobox-hermes-yujin-integration-design.md`
- Phase A plan: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-runtime-chat-vertical-slice.md`
- Phase B plan: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-creator-tools.md`
- Phase C plan: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-realtime-reliability.md`
- Phase D plan: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-mem0-memory.md`
- Existing editor contract: `docs/superpowers/specs/2026-07-23-videobox-task19-editor-asset-browser-design.md`
- SSOT progress mirror:
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
  - latest handoff under `docs/handoffs/`

If a child plan conflicts with the written design, the written design wins. If implementation evidence invalidates the design, stop that task, mark it `[!]`, amend the design with the reason, obtain approval for a material scope change, and only then resume.

## 2. Scope guard

Included:

- isolated Yujin Hermes runtime and Soul/profile
- persistent Editor RightDock conversation
- inline typed creator recommendations
- explicit apply through existing editor commands
- B-roll, BGM, SFX, captions, voice/TTS, overlay controls only where the backend already supports them
- preview/output reverse smoke
- reconnect/cancel/retry and capability lifecycle after the first usable slice
- Mem0 candidate approval, retrieval, deletion, and fallback

Excluded:

- SaaS tenancy, billing, public signup, hosted multi-user operations
- OpenCut source copy or unsupported effect exposure
- Hermes direct DB/media mount or direct timeline mutation
- automatic proposal apply
- Mem0 as VideoBox SSOT
- Task 9 human/environment acceptance and CapCut Desktop proof

Minimum safety that is never deferred:

1. Secrets, OAuth state, raw memory records, and provider payloads are not returned to the browser or logs.
2. Hermes receives no VideoBox DB or media mount.
3. Hermes cannot render, export, or mutate the editor directly.
4. Only the proposal explicitly selected by the user can reach the current-revision `EditorCommandPort`.
5. Manual editing remains usable when Hermes, provider, SSE, or Mem0 is unavailable.
6. Local/test verification produces zero external provider calls unless a separately named live canary is explicitly run.

## 3. Progress accounting

This initiative has a fixed denominator of **20 tasks**. Do not add work silently. A new task requires a plan amendment that states whether it replaces an existing task or changes the denominator.

Status symbols:

- `[ ]` pending
- `[~]` in progress
- `[x]` complete
- `[!]` blocked

Only `[x]` counts as complete. Reopen `[x]` to `[~]` if later evidence finds a regression. The child task and this mirror must be updated in the same closeout commit.

Current initiative progress: **18/20 (90.0%), remaining 10.0%**.

The existing VideoBox official cumulative status remains separately fixed at **9/22 (40.9%), remaining 59.1%** until Task 9 human/environment acceptance. Do not combine that denominator with this initiative.

## 4. Master task mirror

### Phase 0 — bounded audit and baseline (2/2)

- [x] **P0-1** Confirm live/source drift, official Hermes CLI/wire contracts, branch/upstream, protected paths, and current dependency pins.
- [x] **P0-2** Record reverse runtime trace and focused baseline; add the plan-state consistency verifier.

### Phase A — working Yujin chat vertical slice (4/4)

- [x] **A1** Add the isolated official Hermes Yujin runtime topology and deterministic startup verification.
- [x] **A2** Install the versioned Yujin Soul/profile/skills package and verify ownership plus secret-free contents.
- [x] **A3** Implement the minimal authenticated Hermes JSON-RPC/WebSocket client and API SSE run boundary.
- [x] **A4** Connect persistent RightDock chat, manual fallback, reload proof, the bounded live-canary script, and the Phase A non-live technical closeout.

### Phase B — creator tools and explicit apply (5/5)

- [x] **B1** Build the allowlisted current-revision creator context and typed read DTOs.
- [x] **B2** Add Yujin creator skills and validate typed recommendation/proposal responses.
- [x] **B3** Support revision-safe B-roll, BGM, and SFX recommendation/apply paths.
- [x] **B4** Support only existing caption, voice/TTS, overlay, and output-check controls.
- [x] **B5** Prove explicit apply, one-player preview, output reverse smoke, manual fallback, and Phase B closeout.

### Phase C — realtime reliability and operations (4/4)

- [x] **C1** Persist run/event cursors and restore final or interrupted conversation state.
- [x] **C2** Add bounded reconnect, cancel, retry, duplicate suppression, and stale-run fencing.
- [x] **C3** Complete issue/consume/replay/revoke capability lifecycle with redacted audit evidence.
- [x] **C4** Add dashboard health/restart/fallback operations, failure drills, and Phase C closeout.

### Phase D — Hermes-owned Mem0 auxiliary memory (3/4)

- [x] **D1** Add typed memory candidate/policy DTOs with explicit approval as the only write gate.
- [x] **D2** Add a Hermes-owned Mem0 Platform adapter without exposing credentials or raw provider records.
- [x] **D3** Add approve/list/delete UI and ensure pending/rejected candidates are never injected.
- [ ] **D4** Add bounded retrieval injection, unavailable fallback, live canary, and Phase D closeout.

### Final integration closeout (0/1)

- [ ] **F1** Run independent spec/quality/gap/reverse reviews, required suites, build, provenance, SSOT/handoff, commit, and push.

## 5. Execution order and gates

Execute tasks strictly in this order:

```text
P0-1 → P0-2
→ A1 → A2 → A3 → A4
→ B1 → B2 → B3 → B4 → B5
→ C1 → C2 → C3 → C4
→ D1 → D2 → D3 → D4
→ F1
```

The first useful-owner checkpoint is **A4**. Its non-live technical code and gates are complete: when the separately configured runtime/provider environment is available, RightDock has the conversation path and manual fallback. This closeout does not claim that a live provider conversation or an actual Hermes service-stop drill was executed.

The first end-to-end creator checkpoint is **B5**: the user can request an edit, inspect a typed candidate, explicitly apply it, preview it, and reach the existing output path.

Do not delay A4 or B5 for:

- token-perfect reconnect
- complete audit dashboards
- full Mem0 UI
- every hypothetical editor effect
- SaaS concerns

Do not proceed past a task when:

- its focused RED test never failed for the intended reason;
- required GREEN verification is not passing;
- a Critical spec or security boundary is violated;
- the current revision/epoch fence cannot be proved;
- the only working route requires automatic apply or Hermes direct mutation.

## 6. TDD and closeout protocol

For each numbered task:

1. Change its status to `[~]` in the child plan and this mirror.
2. Add the smallest failing test for the named acceptance behavior.
3. Run that exact test and record the expected failure.
4. Implement the smallest contract that makes it pass.
5. Run focused tests and `git diff --check`.
6. Review the diff for scope, secrets, external-call boundaries, and protected paths.
7. Change the task to `[x]`, update the numerator and remaining percentage in both plans, and commit them with the implementation.
8. Push when the logical task or phase is closed and upstream divergence is confirmed.

External canaries are separate named commands. Unit, integration, frontend, and build checks must use fakes and assert external provider call count `0`.

## 7. Phase verification gates

### Phase A gate

- focused API Hermes transport tests
- focused Director conversation persistence tests
- focused RightDock/route tests
- Compose/profile verifiers
- one explicit local live chat canary, only after runtime credentials are configured; this remains operationally unrun in the approved non-live technical closeout
- manual editor fallback while Hermes is actually stopped; deterministic fallback tests passed, while the real service-stop/manual environment drill remains operationally unrun
- `git diff --check`

### Phase B gate

- typed creator context/proposal tests
- focused editor route and command-port tests
- revision and route-epoch stale completion tests
- B-roll/BGM/SFX/caption/voice/overlay supported-control matrix
- one-player ownership test
- output reverse smoke
- full frontend suite and production build
- Editor UI OSS provenance verifier
- `git diff --check`

### Phase C gate

- durable run/event store tests
- reconnect/cancel/retry and duplicate-delivery tests
- capability issue/consume/replay/revoke tests
- stopped-runtime, expired-ticket, provider-error, and browser-reload drills
- full relevant backend suite
- full frontend suite and build
- `git diff --check`

### Phase D gate

- memory approval-policy tests
- fake Mem0 adapter tests with external call count `0`
- approve/list/delete/retrieval UI tests
- unavailable/empty/malformed provider fallback
- one explicit live Mem0 canary only when separately authorized and configured
- full relevant backend/frontend suites and build
- `git diff --check`

### Final gate

- independent spec review
- independent quality review
- independent gap review
- independent reverse runtime review
- focused backend and frontend tests
- full Python regression if the final changed backend scope requires it; otherwise report it as unrun
- full frontend suite
- production build
- provenance verifier
- UI-system, external-runtime/network guard, and package-lock CycloneDX SBOM
- Compose/config/profile verifiers
- `git status --short`
- branch, HEAD, upstream divergence
- `git diff --check`
- SSOT and handoff update
- commit and push

## 8. Reverse runtime trace that must remain true

```text
User types in RightDock
→ EditorWorkbenchRoute captures current project/revision/route epoch
→ VideoBox API persists user message and creates a Hermes run
→ allowlisted context builder reads current VideoBox state
→ authenticated VideoBox Hermes client opens official /api/ws
→ session.create / prompt.submit
→ message.delta / message.complete
→ VideoBox SSE emits redacted typed events
→ route fence accepts only the current run
→ final assistant message persists
→ optional typed proposal is shown, not applied
→ user explicitly selects Apply
→ existing current-revision EditorCommandPort
→ PreviewCoordinator refreshes the sole PreviewStage player
→ existing output path
```

Mem0 is an optional side path:

```text
D3 management-only surface lists an existing/seeded durable candidate
→ current project+conversation list restores only public candidate/storage state
→ user explicitly clicks Approve and Store
→ approve completes with provider call 0
→ only then a new request ID reaches the Hermes-owned Mem0 adapter
→ failed/stale approve reaches no store; failed store waits for another click
→ Route preserves candidate and conversation scroll across drawer close/open
→ stored memory deletion also requires an explicit click
→ D4 adds exactly one production producer:
  current RightDock explicit "기억 후보 만들기"
  → current owned completed message IDs + typed policy-safe short candidate
  → existing POST memory-candidates
  → automatic create/approve/store/provider call 0
→ later bounded retrieval returns approved preference text
→ context builder injects only policy-filtered text
→ Mem0 failure returns empty memory context
→ conversation and manual editor continue
```

D3 does not claim conversation→candidate production E2E. D4 must add the
single explicit producer above without changing the 20-task denominator;
page load, message/run completion, provider response, approval, store, and
retry must never become a second or automatic producer.

## 9. Written spec self-review

Review result before implementation: **approved design covered, Critical/Important plan gap 0**.

Checks performed:

- all 20 master task IDs occur exactly once across the four child plans;
- child status and master status start aligned at pending;
- Phase A closes real streamed chat and reload/manual fallback before creator/reliability/memory expansion;
- Phase B covers B-roll/BGM/SFX and only backend-supported TTS/caption/overlay controls;
- public SSE names match the written design;
- RightDock never owns a second player or mutation port;
- Agent Gateway, not VideoBox API/browser, is the sole Hermes transport owner;
- gateway-only secret/private-key ownership is preserved;
- automatic apply, OpenCut source/runtime, SaaS, and generic provider/API expansion are absent;
- local/test external provider calls remain zero and live canaries are separate;
- Mem0 approval and failure fallback cannot alter VideoBox SSOT;
- final gate includes Python/frontend/E2E/build/provenance/UI/network/SBOM plus reverse review.

Corrections made during self-review:

1. Restored the authoritative official cumulative figure to `9/22 (40.9%)`, remaining `59.1%`.
2. Replaced direct API-to-Hermes ownership with the approved dedicated Agent Gateway split.
3. Replaced a shared signing-secret deployment with gateway-private/API-public Ed25519 capability verification for the hardened phase.
4. Corrected existing frontend test, provenance script, requirements file, and pinned Hermes image paths.
5. Added the full Phase A/Phase B and final release gates required by the written design.

Implementation-time unknowns are bounded to P0-1 evidence (current container drift, official CLI behavior, configured credentials). They do not authorize scope expansion.

## 10. Commit and handoff convention

Use small logical commits:

```text
docs: baseline Hermes Yujin execution state
feat: run isolated Yujin Hermes service
feat: stream Yujin chat into editor
feat: add typed Yujin creator proposals
feat: harden Yujin realtime runs
feat: add approved Yujin memory
docs: close Hermes Yujin integration
```

Every phase closeout must report in easy Korean:

- what now works
- actual scope
- initiative progress `n/20`
- existing VideoBox official cumulative `9/22 (40.9%)`, remaining `59.1%`, and Task 9 separation
- verification that ran and did not run
- external live canary status
- commit and push status
- exact next task prompt
