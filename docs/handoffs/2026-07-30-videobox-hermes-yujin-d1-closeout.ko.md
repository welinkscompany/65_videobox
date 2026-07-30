# VideoBox Hermes Yujin D1 closeout handoff

## 한눈에 보기

D1을 기술 closeout했다. VideoBox에는 편집 취향을 바로 기억으로 쓰지 않고,
사용자가 검토할 `pending` 후보와 approve/reject 기록만 둔다. 승인해도 D1에서는
외부 Mem0나 provider를 호출하지 않는다.

Hermes가 없거나 막혀도 기존 Director와 editor 수동 편집은 그대로 사용할 수
있고 자동 Apply는 없다.

## 실제 구현 범위

- 고정 `creator` scope의 typed candidate/status/category DTO
- 현재 project/conversation source message 소유권과 durable 순서 확인
- canonical request fingerprint와 bounded client request idempotency
- SQLite/PostgreSQL 공통 candidate·body-free audit schema
- pending create, bounded latest-100 list, explicit approve/reject API
- 같은 결정 replay와 반대 결정 conflict
- router와 durable store의 동일 memory policy guard
- 동일 timestamp에도 고정되는 per-candidate `event_order`
- public validation/error의 rejected body non-echo

추가하지 않은 범위는 Mem0/provider write, retrieval, UI, source copy,
OpenCut runtime, SaaS와 자동 Apply다.

## fresh 검증

- D1 focused: `96 passed`
- 관련 Director/API/PostgreSQL regression: `39 passed, 34 skipped`
- disposable PostgreSQL 16 D1 workflow: `1 passed`
- disposable PostgreSQL container cleanup: 통과
- `py_compile`: 통과
- 20-ID plan-state verifier: 통과
- `git diff --check`: 통과
- 독립 spec 및 quality/gap/reverse review:
  `Critical 0 / Important 0 / Minor 0`, PASS

Starlette multipart warning 1건은 기존 비실패 출력이다.

전체 Python/frontend regression과 production build는 D1에서 다시 실행하지
않았다. 실제 Mem0/provider 호출, 브라우저 사람 E2E, 사용자 원본 영상
재생·청취, CapCut Desktop 사람 검증과 Task 9 사람/환경 acceptance도 실행하지
않았고 통과로 간주하지 않는다.

## 진행률

- Hermes Yujin initiative: **16/20 (80.0%)**, 잔여 **20.0%**
- Phase D: **1/4 (25.0%)**, 잔여 **75.0%**
- Mem0 child: **1/5 (20.0%)**, 잔여 **80.0%**
- VideoBox 공식 누적: **9/22 (40.9%)**, 잔여 **59.1%**

공식 누적은 Task 9 사람/환경 acceptance와 별도이므로 올리지 않는다.

## 커밋·푸시 상태

- closeout 작성 시 기준 HEAD: `aebb7e08b`
- D1 implementation/closeout commit: `7a1559f68`
- upstream push: `7a1559f68` push 뒤 `0/0` 확인

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

`D2만 진행한다. 먼저 현재 Gateway client/service/router, Hermes Yujin
distribution/skill, Compose secret·network 경계와 D1 approved candidate의
current truth를 source-grounded로 확인한다. approved 상태만 explicit user action
뒤 Hermes 소유 Mem0 adapter에 전달하고 pending/rejected는 provider call 0으로
막는다. VideoBox는 Mem0 credential/raw record를 저장하거나 browser에 노출하지
않고, stable isolated Hermes namespace만 사용한다. fake adapter TDD로
success/failure/retry/idempotency/non-echo/manual fallback을 검증하고 local/test
external call 0, 자동 Apply 금지, 공식 누적 9/22 (40.9%)를 유지한다.`
