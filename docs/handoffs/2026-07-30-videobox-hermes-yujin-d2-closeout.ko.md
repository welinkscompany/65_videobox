# VideoBox Hermes Yujin D2 closeout handoff

## 한눈에 보기

D2를 기술 closeout했다. 사용자가 기억 후보를 승인한 뒤에도 자동 저장하지
않고, 별도의 명시적 store 요청을 해야만 격리된 Hermes-derived adapter가
Mem0 Platform에 저장을 요청한다. Mem0가 없거나 실패해도 기존 채팅과 수동
편집은 유지되고 자동 Apply는 없다.

## 실제 구현 범위

- approved candidate 전용 explicit store API와 fixed public status
- durable request idempotency, claim/call-start, event/memory ref 분리
- provider 응답 유실·timeout의 ambiguous reconcile과 중복 add 방지
- SQLite/PostgreSQL 공통 storage 상태·body-free operation audit
- candidate handle만 받는 server-owned delete와 private mapping 검증
- provider delete 성공 뒤 local crash 복구와 terminal deleted CAS
- pinned Hermes image 기반 격리 adapter와 `mem0ai==2.0.10`
- adapter-only Mem0 key, gateway/adapter-only service token
- lazy provider construction, SDK telemetry 강제 비활성, startup provider call 0
- 빈 key와 refresh 실패 시 stale adapter 차단

추가하지 않은 범위는 retrieval prompt injection, D3 RightDock UI, 실제 Mem0
canary, source copy, OpenCut runtime, SaaS와 자동 Apply다.

## fresh 검증

- latest integrated D2: `298 passed, 36 skipped`
- D2 core focused with disposable PostgreSQL: `168 passed`
- Compose/Profile: `83 passed, 1 skipped`
- start/recovery/failure regression: `82 passed`
- disposable PostgreSQL Yujin memory: `2 passed`
- actual adapter image build: 통과
- network-none adapter import smoke: 통과
- profile/runtime StaticOnly verifier: 통과
- Python `compileall`: 통과
- `git diff --check`: 통과
- 독립 spec/quality/gap/reverse review:
  `Critical 0 / Important 0 / Minor 0`, PASS

Starlette multipart warning 1건은 기존 비실패 출력이다. latest integrated의
skip에는 환경변수 없이 실행한 PostgreSQL integration이 포함되며 D2 PostgreSQL
대상 2개는 disposable PostgreSQL 16에서 별도로 통과했다. Compose/Profile의
별도 skip 1건은 현재 Windows 계정의 symlink 생성 권한 제한이다.

전체 Python regression, 전체 frontend suite, production frontend build,
실제 Mem0/provider call, 브라우저 사람 E2E, 사용자 원본 영상 재생·청취,
CapCut Desktop 사람 검증과 Task 9 사람/환경 acceptance는 실행하지 않았고
통과로 간주하지 않는다.

## 진행률

- Hermes Yujin initiative: **17/20 (85.0%)**, 잔여 **15.0%**
- Phase D: **2/4 (50.0%)**, 잔여 **50.0%**
- Mem0 child: **2/5 (40.0%)**, 잔여 **60.0%**
- VideoBox 공식 누적: **9/22 (40.9%)**, 잔여 **59.1%**

공식 누적은 Task 9 사람/환경 acceptance와 별도이므로 올리지 않는다.

## 커밋·푸시 상태

- closeout 작성 시 기준 HEAD: `ff2cec166`
- D2 implementation/closeout commit: 아직 생성 전
- upstream push: 아직 실행 전

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

## 다음 goal prompt

`D3만 진행한다. D2의 durable candidate/store/delete API를 source-grounded로
확인하고 RightDock에 pending Approve/Reject, approved Store/Retry, stored
Delete 상태를 연결한다. explicit click 전 provider call 0, pending/rejected
retrieval 0, public provider ref 0을 유지한다. Inspector close/open 뒤 Route-owned
candidate와 scroll을 보존하고 Mem0 실패에도 chat/manual editor가 계속되게 한다.
focused frontend TDD와 독립 spec/quality/gap/reverse review 뒤 논리적으로 닫힌
단위만 commit/push하며 공식 누적 9/22 (40.9%)를 유지한다.`
