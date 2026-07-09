# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- approve rollback raw persisted timeline closeout

## 1. 이번 turn에서 실제로 끝낸 것

- 새로운 stale-shape slice를 더 열지 않고, 누적 변경 검증 중 실제로 드러난 review-action rollback 회귀 1개를 먼저 닫았다
- 선택한 경계는 review state 저장 실패 후 rollback이 raw persisted timeline이 아니라 hydrated response timeline을 다시 저장해 pending recommendation shape를 오염시키는 문제였다
- rollback source timeline이 store의 raw persisted payload를 직접 보관하도록 최소 수정으로 닫았다

## 2. 이번 turn의 핵심 판단

- 이 문제는 새 가설이 아니라 실제 focused-near-broader 검증에서 드러난 회귀였고, 현재 worktree에서 가장 우선순위가 높은 실제 실패였다
- 회귀 원인은 review-action rollback source가 API read-path hydration을 거친 timeline을 재사용한 점이어서, rollback source만 raw payload로 바꾸는 최소 수정이 가장 정확했다

## 3. strict TDD 증거

- RED
  - `py -m pytest tests/test_api.py -q -k "test_review_snapshot_api_approve_rolls_back_timeline_and_recommendation_when_review_state_save_fails"`
  - 결과: `1 failed`
  - 실제 실패:
    - rollback 뒤 persisted `pending_recommendations`가 original raw timeline과 달라짐
- GREEN
  - `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
    - `_prepare_pending_recommendation_decision(...)`가 rollback source `original_timeline`을 `get_timeline_result(...)`의 hydrated timeline 대신 store의 raw timeline payload에서 직접 읽도록 최소 수정
  - 같은 exact test 재실행
  - 결과: `1 passed`

## 4. 이번 turn의 verification

- exact regression
  - `1 passed`
- paired rollback regression
  - `py -m pytest tests/test_api.py -q -k "test_review_snapshot_api_reject_rolls_back_timeline_and_recommendation_when_review_state_save_fails"`
  - 결과: `1 passed`
- review-action backend focused slice
  - `./scripts/dev-fast-path.ps1 -Mode review-action-backend`
  - 결과: `7 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - rollback source timeline 한 점에 국한된 수정이라 exact + paired exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

## 5. 현재 기준 상태

- 브랜치:
  - `codex/tts-approved-runtime`
- 이번 turn의 코드 변경 범위
  - `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
- 이번 turn의 문서 변경 범위
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- closeout 문서 추가
  - `docs/session-context-2026-07-04-approve-rollback-raw-persisted-timeline-closeout.ko.md`

## 6. 쉽게 말한 현재 개발상황

- 지금은 approval/output helper에 쌓인 변경을 검증하면서 실제 회귀가 나오면 새 slice보다 그 회귀를 먼저 닫는 단계다
- 이번 수정으로 review state 저장 실패 후 approve/reject rollback이 original persisted timeline shape를 그대로 복구한다

## 7. 다음 세션 첫 시작점

1. approve rollback raw persisted timeline 경계는 현재 기준 닫힌 것으로 본다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개를 고른다
3. exact failing test 1개로만 다시 시작한다

## 8. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
