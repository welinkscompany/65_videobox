# VideoBox 세션 컨텍스트

작성일:

- 2026-07-05

주제:

- review guidance ignore stale minimal review flag entry closeout

## 1. 이번 turn에서 실제로 끝낸 것

- review guidance prompt가 `segment_id` 없이 남은 stale minimal-dict `review_flags`를 valid blocker처럼 안내문에 섞어 넣던 경계 1개를 닫았습니다
- exact regression 1개로 RED를 먼저 확인한 뒤, canonical blocker `code`와 `segment_id`를 모두 가진 entry만 prompt에 남기도록 최소 수정만 넣었습니다
- focused verification은 같은 `review_guidance` prompt 면의 인접 테스트들까지만 다시 돌려 이번 경계가 기존 blocker prompt 정규화 규칙을 깨지 않는지 확인했습니다

## 2. 이번 turn의 핵심 판단

- 이번 경계는 `review/output gating`에 가장 가까운 blocked operator guidance prompt 입력면 문제였습니다
- 직전 output operator copy prompt에서는 같은 stale minimal review-flag 경계를 이미 닫았기 때문에, review guidance prompt도 같은 canonical blocker identity 기준으로 맞추는 편이 가장 작은 인접 slice였습니다
- broader 재검증보다 exact RED/GREEN과 review guidance prompt 인접 focused evidence가 이번 수정의 직접 증거라고 판단했습니다

## 3. 이번 turn의 변경 범위

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`
  - prompt `review_flags`가 supported blocker `code`와 trimmed `segment_id`를 모두 가진 entry만 유지하도록 수정
  - pending recommendation prompt identity도 supported recommendation type 집합 기준으로 정리
- `tests/test_api.py`
  - `test_review_guidance_builder_ignores_minimal_dict_review_flags_in_prompt` 추가
- SSOT 문서 업데이트
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`

## 4. 이번 turn의 verification

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_ignores_minimal_dict_review_flags_in_prompt" -vv`
  - RED `1 failed` 확인 후 GREEN `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_ignores_non_dict_review_flags_in_prompt or test_review_guidance_builder_ignores_minimal_dict_review_flags_in_prompt or test_review_guidance_builder_canonicalizes_mixed_case_review_flag_code_in_prompt or test_review_guidance_builder_trims_review_flag_segment_id_in_prompt or test_review_guidance_builder_defaults_review_flag_message_in_prompt or test_review_guidance_builder_trims_review_flag_message_in_prompt" -vv`
  - `6 passed`
- broader verification
  - 실행하지 않음

## 5. 쉽게 말한 현재 개발상황

- 이번에는 review guidance 안내문이 `code`만 있고 `segment_id`가 없는 반쯤 깨진 blocker까지 진짜 blocker처럼 보여주던 부분만 작게 막았습니다
- 이제 review guidance도 output 쪽 prompt처럼, 세그먼트까지 제대로 식별되는 blocker만 안내문에 남깁니다

## 6. 다음 세션 첫 시작점

1. 장기 queue는 그대로 유지합니다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 가까운 exact regression 1개만 고릅니다
3. 우선순위는 review guidance/output prompt 또는 인접 consumer surface에서 남아 있는 가장 작은 stale-shape 경계부터 다시 고릅니다

## 7. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
