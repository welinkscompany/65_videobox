# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- review guidance pending created_at prompt closeout

## 1. 이번 turn에서 실제로 끝낸 것

- `review guidance` prompt의 `pending_recommendations.created_at` surface가 whitespace stale 값을 raw 문자열 그대로 노출하던 작은 경계 1개를 닫았습니다
- `packages/core-engine/src/videobox_core_engine/review_guidance.py`에서 prompt 전용 pending recommendation row를 만들 때 `created_at`도 `strip()` 기준으로 정리하도록 맞췄습니다
- exact regression 1개로 RED를 확인한 뒤, 같은 exact test로 GREEN을 먼저 확인하고 review-guidance 인접 focused verification까지만 수행했습니다

## 2. 이번 turn의 핵심 판단

- 장기 queue 후보는 `review/output gating`, `TTS approval/output`, `preflight contract`로 그대로 유지했습니다
- 그중 이번 slice는 이미 진행 중인 `review guidance` prompt canonicalization family와 직접 이어지고, 변경 범위가 가장 작은 `pending_recommendations.created_at` surface를 선택했습니다
- 이 경계는 approve/output 쪽 recommendation metadata를 prompt surface에 그대로 비추는 지점이라, 같은 family 안에서도 가장 작고 검증 비용이 낮은 slice라고 판단했습니다

## 3. 이번 turn의 변경 범위

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`
  - `_prompt_pending_recommendations(...)`에서 `created_at` trim 추가
- `tests/test_api.py`
  - `test_review_guidance_builder_trims_pending_recommendation_created_at_in_prompt` exact regression 추가
- SSOT 문서
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- closeout 문서 추가
  - `docs/session-context-2026-07-04-review-guidance-pending-created-at-prompt-closeout.ko.md`

## 4. 이번 turn의 verification

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_trims_pending_recommendation_created_at_in_prompt" -vv`
  - RED `1 failed` 확인 후 GREEN `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_trims_segment_ids_needing_attention_in_prompt or test_review_guidance_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt or test_review_guidance_builder_trims_pending_recommendation_target_segment_id_in_prompt or test_review_guidance_builder_canonicalizes_mixed_case_review_flag_code_in_prompt or test_review_guidance_builder_trims_review_flag_segment_id_in_prompt or test_review_guidance_builder_trims_review_flag_message_in_prompt or test_review_guidance_builder_trims_pending_recommendation_reason_in_prompt or test_review_guidance_builder_canonicalizes_pending_recommendation_decision_state_in_prompt or test_review_guidance_builder_trims_pending_recommendation_selected_asset_id_in_prompt or test_review_guidance_builder_trims_pending_recommendation_id_in_prompt or test_review_guidance_builder_trims_pending_recommendation_created_at_in_prompt or test_heuristic_review_guidance_builder_canonicalizes_mixed_case_approved_review_status" -vv`
  - 결과 `12 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review-guidance prompt metadata trim 한 점만 수정한 slice라 exact + prompt-family focused evidence가 가장 직접적입니다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지합니다

## 5. 쉽게 말한 현재 개발상황

- review guidance 문구 안에 recommendation 생성 시각이 공백 섞인 옛 값으로 보이던 작은 흔들림을 정리했습니다
- 이제 operator guidance prompt도 approve/output 쪽 recommendation metadata 기준과 더 같은 방향으로 맞춰졌습니다

## 6. 다음 세션 첫 시작점

1. 장기 queue는 유지합니다
2. 다음 작업은 다시 `docs/implementation-plan.ko.md`의 `## 13. 다음 실제 작업` 기준으로 후보를 2~3개만 좁힙니다
3. 그중 `review/output gating`, `TTS approval/output`, `preflight contract`에 가장 가까운 exact regression 또는 가장 작은 증거 부족 경계 1개만 골라 같은 방식으로 시작합니다

## 7. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
