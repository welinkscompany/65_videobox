# VideoBox 세션 컨텍스트

작성일:

- 2026-07-05

주제:

- pending recommendation decision reject stale minimal dict entry closeout

## 1. 이번 turn에서 실제로 끝낸 것

- approval decision extraction이 `recommendation_id`만 남은 stale minimal-dict pending recommendation을 valid row처럼 승인하던 경계 1개를 닫았습니다
- exact regression 1개로 RED를 먼저 확인한 뒤, canonical `recommendation_id + target_segment_id + recommendation_type`가 없는 pending entry는 decision 대상으로 채택하지 않도록 최소 수정만 넣었습니다
- focused verification은 같은 TTS approval/output family의 인접 테스트만 다시 돌려 이번 수정이 직전 non-dict 방어와 approved TTS apply 경계를 깨지 않는지 확인했습니다

## 2. 이번 turn의 핵심 판단

- 이번 문제는 단순 문구 차이가 아니라, approval decision extraction이 최소 필드도 없는 stale recommendation row를 실제 승인 대상으로 받아들이는 runtime gap이었습니다
- 직전 slice가 같은 함수의 non-dict pending entry를 걸러냈기 때문에, 다음 가장 작은 exact regression은 minimal-dict pending entry 유효성 체크라고 판단했습니다
- 범위를 더 넓혀 payload 전체를 검증할 수도 있었지만, 이번 turn은 decision extraction이 의존하는 최소 identity/type/segment만 요구하는 편이 더 정확했습니다

## 3. 이번 turn의 변경 범위

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`
  - `extract_pending_recommendation_decision(...)`에 stale minimal-dict pending entry 유효성 체크 추가
- `tests/test_api.py`
  - `test_extract_pending_recommendation_decision_rejects_stale_minimal_dict_entry` 추가
- SSOT 문서 업데이트
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`

## 4. 이번 turn의 verification

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_extract_pending_recommendation_decision_rejects_stale_minimal_dict_entry" -vv`
  - RED `1 failed` 확인 후 GREEN `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_extract_pending_recommendation_decision_ignores_non_dict_entries or test_extract_pending_recommendation_decision_rejects_stale_minimal_dict_entry or test_apply_approved_tts_recommendation_ignores_non_dict_clips or test_apply_approved_tts_recommendation_ignores_non_dict_tracks" -vv`
  - `4 passed`
- broader verification
  - 실행하지 않음

## 5. 쉽게 말한 현재 개발상황

- 이제 recommendation 승인/거절 추출은 `id`만 있는 찌꺼기 row를 진짜 추천처럼 승인하지 않습니다
- 승인 대상은 최소한 어떤 세그먼트의 어떤 추천 타입인지 식별 가능한 row로만 제한됐습니다

## 6. 다음 세션 첫 시작점

1. 장기 우선순위 queue는 그대로 유지합니다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 가까운 exact regression 1개만 고릅니다
3. 그 경계는 이번 approval decision extraction 다음으로 인접한 stale minimal-dict 또는 normalization 잔여 차이부터 우선 닫습니다

## 7. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
