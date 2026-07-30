# VideoBox Hermes Yujin D3 closeout handoff

작성일: 2026-07-30

worktree: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility`

branch: `codex/videobox-container-compatibility`

## 완료 범위

- Editor RightDock에서 현재 project와 현재 Director conversation에 이미
  존재하는 memory candidate를 조회한다.
- 한 번의 명시적 `승인하고 저장` 클릭은 approve 성공 뒤에만 새 request
  ID로 store를 호출한다. 실패하거나 stale한 approve는 store `0`이다.
- approved/not-requested, failed, ambiguous, expired claimed는 사용자 클릭으로
  다시 저장할 수 있다. 살아 있는 claimed는 비클릭 상태다.
- 저장된 기억 삭제도 명시적 클릭만 허용한다.
- candidate/action/error와 conversation scroll을 Route가 소유하므로
  Inspector/RightDock close-open 뒤에도 보존한다.
- route 이동 뒤 늦게 끝난 list/approve/store/delete는 새 route를 변경하지
  않는다.
- 공개 DTO는 `storage_status`와 `retryable`만 노출하고 provider ref, claim
  timestamp, raw provider record는 노출하지 않는다.

## 중요한 범위 제한

D3는 기존 또는 테스트에서 seed한 candidate를 관리하는 UI다. 실제 유진
대화가 production candidate를 만드는 경로는 아직 없다. D4에서 분모를
늘리지 않고 현재 RightDock의 명시적 `기억 후보 만들기` 한 경로만 추가해야
한다. page load, message/run 완료, provider 응답, approve, store, retry는
자동 candidate 생성·승인·저장·provider call을 만들면 안 된다.

## 검증

- memory store/API backend: `49 passed`
- typed API memory: `20 passed`
- focused frontend: `4 files / 178 passed`
  - memory panel: `3 passed`
  - EditorWorkbenchRoute 전체: `114 passed`
- disposable PostgreSQL current-conversation-before-limit:
  `1 passed, 40 deselected`
- disposable PostgreSQL expired-claim add/reconcile parity:
  `1 passed, 41 deselected`
- Hermes Yujin 20-ID plan-state verifier: PASS
- `git diff --check`: PASS
- independent spec/quality/gap/reverse review:
  `Critical 0 / Important 0 / Minor 0`, PASS

기존 Starlette multipart warning 1건은 비실패 출력이다.

## 실행하지 않은 검증

- 전체 Python regression
- 전체 frontend suite
- production build와 provenance verifier
- 실제 Mem0/provider call
- 브라우저 사람 E2E
- 사용자 원본 영상 재생·청취와 CapCut Desktop 사람 검증
- Task 9 사람/환경 acceptance

위 항목은 통과로 주장하지 않는다.

## 다음 goal

D4만 진행한다.

1. 현재 RightDock에서 한 번의 명시적 동작으로만 현재 owned
   conversation의 완료 message ID와 typed policy-safe 짧은 후보를 기존
   memory-candidates POST에 보낸다.
2. 자동 create/approve/store/provider call은 `0`으로 유지한다.
3. approved+stored 기억만 bounded retrieval로 creator context에 넣는다.
4. pending/rejected/deleted/failed/unrelated는 retrieval `0`이다.
5. unavailable/empty/malformed/timeout이면 기억 없이 유진 대화와 수동
   편집을 계속한다.
6. 실제 Mem0 live canary는 별도 명시 실행 전까지 미실행으로 남긴다.

Hermes Yujin initiative는 `18/20 (90.0%)`, 잔여 `10.0%`다. 기존 VideoBox
공식 누적은 `9/22 (40.9%)`, 잔여 `59.1%`로 유지한다.
