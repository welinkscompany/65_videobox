# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- preflight mixed-case pending recommendation type prediction closeout

## 1. 이번 turn에서 실제로 끝낸 것

- `preflight contract`에서 가장 작은 남은 경계 1개만 골라, mixed-case stale pending recommendation type도 blocker prediction으로 유지되게 고정했습니다
- exact regression 1개로 RED를 먼저 확인했고, preflight prediction helper 비교 한 줄만 최소 수정해 같은 exact test를 GREEN으로 되돌렸습니다
- focused verification은 `preflight-backend` lane만 다시 돌려 이번 수정이 인접 prediction/read-only 계약을 깨지 않는지 확인했습니다

## 2. 이번 turn의 핵심 판단

- 장기 queue 후보는 `review/output gating`, `TTS approval/output`, `preflight contract`로 좁혔고, 실제 raw 비교가 남아 있는 가장 작은 경계는 preflight prediction helper의 mixed-case `recommendation_type` 필터였습니다
- `services/api/src/videobox_api/main.py`의 `_build_preflight_review_prediction(...)`는 `recommendation_type`을 `strip()`만 하고 `VALID_PREVIEW_RECOMMENDATION_TYPES`와 비교하고 있어, `" TTS_REPLACEMENT "` 같은 stale blocker를 valid blocker로 복원하지 못했습니다
- 이 문제는 broader 실행이나 다른 레이어 수정 없이, canonical lowercase 비교 1줄로 바로 닫히는 경계라 이번 turn 범위로 적절했습니다

## 3. 이번 turn의 변경 범위

- `services/api/src/videobox_api/main.py`
  - preflight prediction helper의 source pending recommendation type 필터를 lowercase canonical 비교로 수정
- `tests/test_api.py`
  - `test_editing_session_api_preserves_mixed_case_source_pending_recommendation_type_in_preflight_prediction` exact regression 추가
- `docs/implementation-plan.ko.md`
  - preflight mixed-case blocker prediction 계약 1줄 추가
- closeout 문서 추가
  - `docs/session-context-2026-07-04-preflight-mixed-case-pending-recommendation-type-prediction-closeout.ko.md`

## 4. 이번 turn의 verification

- RED exact
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_preserves_mixed_case_source_pending_recommendation_type_in_preflight_prediction"`
  - 결과: `1 failed`
  - 핵심 실패: `predicted_review_status_after_rerun`가 기대한 `blocked`가 아니라 `draft`
- GREEN exact
  - 같은 명령 재실행
  - 결과: `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode preflight-backend`
  - 결과: `57 passed`

## 5. 쉽게 말한 현재 개발상황

- preflight가 예전 형식의 대문자 추천 타입을 못 알아보고 "막혀 있어야 할 rerun"을 `draft`로 잘못 예측하던 작은 구멍을 막았습니다
- 이제 source timeline에 mixed-case pending recommendation blocker가 남아 있어도 preflight prediction이 그 blocker를 계속 보존합니다

## 6. 다음 세션 첫 시작점

1. 장기 queue는 유지합니다
2. 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 가까운 작은 경계 1개만 고릅니다
3. exact failing test 1개로만 다시 RED를 시작합니다

## 7. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
- AK-Wiki promotion judgment: 보류
