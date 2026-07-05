# VideoBox 세션 컨텍스트

작성일:

- 2026-07-05

주제:

- pending recommendation decision ignore stale non-dict entry closeout

## 1. 이번 turn에서 실제로 끝낸 것

- 직전 `approved TTS apply` 경계 다음으로, 같은 approval mutation family 안에 남아 있던 stale non-dict `pending_recommendations` 경계 1개를 확인하고 닫았습니다
- exact regression 1개로 RED를 먼저 확인한 뒤, pending recommendation decision extraction path가 stale 문자열 pending entry를 valid recommendation row처럼 읽지 않도록 최소 수정만 넣었습니다
- focused verification은 같은 TTS approval/output family의 인접 테스트만 다시 돌려 이번 수정이 기존 approval apply 경계를 깨지 않는지 확인했습니다

## 2. 이번 turn의 핵심 판단

- 이번 문제는 표시 차이가 아니라, recommendation decision extraction 시 `pending_recommendations` list 안의 stale 문자열 entry를 dict처럼 읽다가 실제 예외를 낼 수 있는 runtime gap이었습니다
- 최근 slice가 같은 approval mutation family 안의 non-dict track/clip 경계를 막았기 때문에, 가장 가까운 다음 exact regression은 pending recommendation decision extraction의 non-dict entry라고 판단했습니다
- 이번 turn은 decision extraction exact regression 1개만으로 시작했고 수정도 그 함수의 non-dict pending-entry filtering 한 점으로만 제한했습니다

## 3. 이번 turn의 변경 범위

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`
  - `extract_pending_recommendation_decision(...)`가 non-dict pending entry를 건너뛰도록 수정
- `tests/test_api.py`
  - `test_extract_pending_recommendation_decision_ignores_non_dict_entries` 추가
- SSOT 문서 업데이트
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`

## 4. 이번 turn의 verification

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_extract_pending_recommendation_decision_ignores_non_dict_entries" -vv`
  - RED `1 failed` 확인 후 GREEN `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_extract_pending_recommendation_decision_ignores_non_dict_entries or test_apply_approved_tts_recommendation_ignores_non_dict_clips or test_apply_approved_tts_recommendation_ignores_non_dict_tracks" -vv`
  - `3 passed`
- broader verification
  - 실행하지 않음

## 5. 쉽게 말한 현재 개발상황

- 이제 recommendation 승인/거절 추출도 이상한 pending entry 하나 때문에 깨지지 않습니다
- 같은 approval mutation 경로 안에서 recommendation row 입력도 더 안전하게 무시하게 됐습니다

## 6. 다음 세션 첫 시작점

1. 장기 우선순위 queue는 그대로 유지합니다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 가까운 exact regression 1개만 고릅니다
3. 그 경계는 이번처럼 approval/output 인접 read-path parity 잔여 차이나 preflight contract의 작은 normalization 차이부터 우선 닫습니다

## 7. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
