# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- output gating legacy applied-like pending recommendation closeout

## 1. 이번 turn에서 실제로 끝낸 것

- 장기 우선순위 queue를 유지한 상태에서 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 다시 골랐다
- 선택한 경계는 runtime output gating이 legacy applied-like pending recommendation을 unresolved blocker로 오판하는 문제였다
- subtitle / preview / export가 applied-like recommendation shape를 blocker로 세지 않도록 최소 수정으로 닫았다

## 2. 이번 turn의 핵심 판단

- 이미 닫힌 경계는 `decision_state=approved/rejected` stale pending recommendation 누수였고, 이번 경계는 그보다 한 단계 더 좁은 `decision_state`가 비어 있는 legacy applied-like shape였다
- 이 경계는 새 기능 누락이 아니라 runtime blocker 판정이 applied-like bool-ish truth를 보지 않아 output gating을 다시 blocked 상태로 오염시키는 상태 계약 누수였다
- broader보다는 exact regression + output-gating focused verification이 이번 범위에는 더 직접적인 증거였다

## 3. strict TDD 증거

- RED
  - `py -m pytest tests/test_api.py -q -k "test_output_jobs_ignore_legacy_applied_like_entries_left_in_pending_recommendations"`
  - 결과: `1 failed`
  - 실제 실패:
    - subtitle render start가 `202`가 아니라 `400`
- GREEN
  - `tests/test_api.py`
    - exact regression `test_output_jobs_ignore_legacy_applied_like_entries_left_in_pending_recommendations` 추가
  - `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
    - `_is_runtime_blocking_pending_recommendation(...)`가 bool-ish normalization 기준으로 applied-like recommendation shape를 blocker에서 제외하도록 최소 수정
  - 같은 exact test 재실행
  - 결과: `1 passed`

## 4. 이번 turn의 verification

- exact regression
  - `1 passed`
- focused output-gating slice
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - 결과: `24 passed`
- current-focused-parallel
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - 결과:
    - backend output-gating `24 passed`
    - backend preflight `56 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - runtime output gating bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

## 5. 현재 기준 상태

- 브랜치:
  - `codex/tts-approved-runtime`
- 이번 turn의 코드 변경 범위
  - `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
  - `tests/test_api.py`
- 이번 turn의 문서 변경 범위
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- closeout 문서 추가
  - `docs/session-context-2026-07-04-output-gating-legacy-applied-like-pending-recommendation-closeout.ko.md`

## 6. 쉽게 말한 현재 개발상황

- 지금은 approved timeline에 남은 legacy recommendation 흔적 하나가 output을 다시 blocked처럼 보이게 만들지 않도록, runtime read surface를 하나씩 좁게 맞추는 단계다
- 이번 수정으로 `auto_apply_allowed="true"`와 `review_required="false"`가 같이 있는 recommendation이 pending 컬렉션에 남아 있어도, subtitle / preview / export가 그걸 실제 blocker처럼 세지 않게 맞췄다

## 7. 다음 세션 첫 시작점

1. output gating legacy applied-like pending recommendation 경계는 현재 기준 닫힌 것으로 본다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개를 고른다
3. exact failing test 1개로만 다시 시작한다

## 8. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
