# VideoBox offline synthetic evidence intake 인수인계

**날짜:** 2026-07-19
**브랜치:** `codex/videobox-container-compatibility`
**상태:** actual provider 호출 없이 fixture-only consent/budget/intake recovery contract 완료.

## 완료 범위

- `OwnerEvidenceImportGrant`는 opaque owner/grant ref, checked-in corpus SHA, exact `synthetic_*` provider와 `synthetic_fixture` runtime, literal offline scope, UTC expiry, capture/token/latency budget을 묶는다.
- 이는 real user authentication, consent issuance, OAuth credential, provider authorization이 아니다. grant를 만드는 UI/API/issuer도 이 범위에 없다.
- `EvidenceIntakeGateway.preflight`는 side effect 없이 synthetic capture/grant/expiry/budget/replay를 확인한다. `accept`는 prepared journal과 process-crash 뒤 자동 해제되는 OS advisory lock으로 **전용 marked accepted-intake evidence sink**와 audit pair를 복구한다. sink mutation은 gateway의 private in-process writer capability만 허용하고 외부는 read verification만 한다. 이것은 hostile in-process code 보안이 아닌 ordinary application-code bypass 방지 contract다. 일반 parent evidence ledger는 pre-gate/offline test evidence이며 intake grant/audit/budget를 우회하거나 intake sink를 막지 않는다.
- accepted-intake evidence append와 accepted audit은 exact one-to-one이다. ledger/audit 중 어느 write에서 중단돼도 다음 fresh gateway retry가 original prepared time·grant binding으로 복구하며, expiry 뒤 retry는 새 승인이 아니다.
- 정상 writable path의 accepted와 denied는 non-authorizing audit event로 남는다. denied event는 capture append/budget 사용 `0`이다. lock/audit I/O 불가는 audit을 억지로 만들지 않고 stable fail-closed로 끝난다. malformed capture/grant의 raw text는 audit에 쓰지 않으며, owner/grant는 unkeyed SHA-256 correlation hash만 남긴다. 이는 confidentiality 보장이 아니다.
- audit은 application-level tamper-evident chain이다. signing key/external anchor/retention/size cap은 아직 없으므로 OS/adversary-proof immutable storage라고 주장하지 않는다.

## 검증

- TDD RED: module import 부재, grant rebinding, usage aggregate rehash, tampered state stable deny, ledger/audit write interruption, capture-id journal wedge, expiry/retry timestamp, denied audit 부재, stale-lock recovery, concurrent denied audit loss를 차례로 재현했다.
- focused: intake/evidence/harness `106 passed` (기존 Starlette multipart PendingDeprecationWarning 1건).
- independent spec/quality review: P0/P1/blocking P2 0.
- Windows malformed concurrent deny 64개를 5회 실행해 매번 audit 64/64를 확인했다. `compileall`, `git diff --check`도 통과했다.
- production build와 `--network none --read-only` image import를 통과했다. full Python suite는 `1246 tests collected`까지 확인했지만 실행이 124초 timeout 및 종료 중 pytest stdout `OSError`로 끝나 full-pass로 기록하지 않는다.

## 다음 Goal

기존 §23 범위 안에서 actual provider 호출 없이 **유진의 versioned prompt/profile와 read-only 업무영역**을 정한다. prompt priority, structured response union, untrusted context handling, allowed status-read tool, injection/cross-project/approval-bypass negative fixture를 TDD로 고정한다. Hermes bridge, OAuth, GPT/Qwen/Gemini call, DB/API route activation, mutation/render/export은 계속 시작하지 않는다.
