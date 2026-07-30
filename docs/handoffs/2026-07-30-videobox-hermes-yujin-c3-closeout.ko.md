# VideoBox Hermes Yujin C3 closeout handoff

## 한눈에 보기

C3 capability lifecycle은 기술 closeout했다. Eugene/Yujin이 VideoBox 문맥을
읽거나 typed proposal을 게시할 때 쓰는 권한은 이제 Ed25519로 서명되고, 현재
project/conversation/run/session/revision/asset revision과 정확히 한 action에
묶인다. 이미 쓴 권한, 취소·회수된 권한, 오래되거나 위조된 권한은 다시 쓸 수
없다.

Hermes가 실패해도 자동 Apply는 일어나지 않으며 기존 Director/editor 수동
편집은 유지된다.

## 실제 구현 범위

- Gateway private key / API public key 분리
- read/publish one-action capability issue, register, consume, replay reject,
  revoke와 redacted audit
- SQLite/PostgreSQL durable ledger, migration, retention/recovery
- session → asset → ledger current-truth lock order와 concurrent
  consume/revoke 직렬화
- terminal proposal transaction과 publish consume의 원자적 결합
- base Compose 비활성, Yujin overlay 전용 authority와 안전한 key rotation
- verifier/preparation/audit 실패의 고정 503, cleanup/revoke, 비밀 비노출
- deterministic non-live creator smoke용 메모리 내 ephemeral issuer/verifier

추가하지 않은 범위는 provider 호출/확장, Gateway→API callback, source copy,
OpenCut runtime, Hermes-owned Mem0, SaaS, 자동 Apply, render/export/filesystem
capability다.

## fresh 검증

- C3 focused: `468 passed, 33 skipped`
- disposable PostgreSQL 16 C3 전체: `38 passed, 0 skipped`
  - 검증 뒤 정확한 test container 제거/부재 확인
- 전체 Python: `2367 passed, 41 skipped, 1 warning`
- 전체 frontend: `50 files / 668 tests passed`
- production build: 통과
- Hermes profile/runtime/20-ID plan-state/zero-tools verifier: 통과
- Editor UI OSS source provenance/UI-system verifier: 통과
- `py_compile`, `git diff --check`: 통과
- 독립 spec/quality/gap/reverse/final regression review:
  `Critical 0 / Important 0 / Minor 0`, PASS

기존 Starlette multipart warning, React `act(...)`, jsdom navigation,
intentional ErrorBoundary stderr, 500 kB bundle warning은 비실패 출력이다.

실제 Hermes/provider 호출, 브라우저 사람 E2E, 실제 service-stop drill, 사용자
원본 영상 재생·청취, CapCut Desktop 사람 검증과 Task 9 사람/환경 acceptance는
실행하지 않았다.

## 진행률

- Hermes Yujin initiative: **14/20 (70.0%)**, 잔여 **30.0%**
- Phase C / realtime-reliability child: **3/4 (75.0%)**, 잔여 **25.0%**
- VideoBox 공식 누적: **9/22 (40.9%)**, 잔여 **59.1%**

공식 누적은 Task 9 사람/환경 acceptance와 별도이므로 올리지 않는다.

## 재개 안전선

- canonical worktree:
  `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility`
- branch/upstream:
  `codex/videobox-container-compatibility` /
  `origin/codex/videobox-container-compatibility`
- 아래 untracked는 기존 범위 밖 잔재이므로 열거나 stage/remove/delete하지 않는다.
  - `.tmp-final-fence-debug/`
  - `.tmp-real-video-dogfood/`
  - `apps/web/.tmp-real-video-dogfood/`

재개 전 이 handoff를 포함한 closeout commit이 upstream과 `0/0`인지, worktree에
위 보호 untracked 외 예상치 못한 변경이 없는지 다시 확인한다.

## 다음 goal prompt

`C4만 진행한다. 기존 dashboard/status ownership을 source-grounded로 다시
조사하고, http_ready와 provider_ready/chat_verified를 구분하는 typed status,
named Yujin service만 건드리는 안전한 restart, redacted failure drills,
모든 장애 뒤 manual editor fallback을 TDD로 구현한다. 실제 provider 성공은
HTTP readiness로 추정하지 말고, 가능한 로컬 runtime drill과 미실행 human/live
gate를 분리한다. 독립 spec/quality/gap/reverse review, full Python/frontend,
build, verifiers, SSOT/handoff, commit/push까지 닫는다.`
