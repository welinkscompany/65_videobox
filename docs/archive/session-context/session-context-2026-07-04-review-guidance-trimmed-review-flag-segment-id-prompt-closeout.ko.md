# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- review guidance trimmed review flag segment id prompt closeout

## 1. 이번 turn에서 실제로 끝낸 것

- `review_guidance` prompt가 whitespace stale `review_flags.segment_id`를 raw로 그대로 노출하던 가장 작은 경계 1개를 닫았다
- `LocalFirstReviewGuidanceBuilder._prompt_review_flags(...)`가 review flag의 `segment_id`도 trim해서 prompt에 넣도록 맞췄다
- exact regression 1개와 review guidance focused verification만으로 이번 slice를 닫았다

## 2. 이번 turn의 핵심 판단

- 장기 queue 후보는 같은 `review_guidance` family의 `review_flags.segment_id`, 더 먼 `preflight contract`, 그리고 `TTS approval/output` 인접 잔여 경계로 좁혔다
- 이 중 가장 가까운 경계는 직전 `review_flags.code` slice와 바로 이어지는 prompt의 raw review-flag `segment_id` surface였다
- 이미 같은 helper 안에서 `code` canonicalization을 추가한 상태라, 이번에는 `segment_id` trim 한 줄만 더 맞추는 편이 가장 작고 직접적이었다

## 3. 이번 turn의 변경 범위

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`
  - `_prompt_review_flags(...)`가 `segment_id`도 `strip()` 기준으로 trim하도록 변경
- `tests/test_api.py`
  - `test_review_guidance_builder_trims_review_flag_segment_id_in_prompt` 추가
- SSOT 문서 업데이트
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`

## 4. 이번 turn의 verification

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_trims_review_flag_segment_id_in_prompt" -vv`
  - 결과: `1 failed` 확인 후 `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_trims_segment_ids_needing_attention_in_prompt or test_review_guidance_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt or test_review_guidance_builder_trims_pending_recommendation_target_segment_id_in_prompt or test_review_guidance_builder_canonicalizes_mixed_case_review_flag_code_in_prompt or test_review_guidance_builder_trims_review_flag_segment_id_in_prompt or test_heuristic_review_guidance_builder_canonicalizes_mixed_case_approved_review_status" -vv`
  - 결과: `6 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt의 review-flag segment-id surface 한 점만 바뀌었고 exact + family-focused evidence가 더 직접적이다

## 5. 쉽게 말한 현재 개발상황

- 이제 review guidance prompt도 review flag 안의 segment id를 공백 섞인 raw 값으로 보여주지 않는다
- 즉, operator guidance prompt가 review/output gating과 preflight/runtime이 이미 쓰는 canonical segment id 기준에 더 가까워졌다

## 6. 다음 세션 첫 시작점

1. 이번 slice는 `review_guidance` prompt의 `review_flags.segment_id` surface closeout으로 본다
2. 다음 작업은 다시 `docs/implementation-plan.ko.md`의 `## 13. 다음 실제 작업` 기준으로 후보를 2~3개로만 좁힌다
3. 그중 `review/output gating`, `TTS approval/output`, `preflight contract`에 가장 가까운 exact regression 1개를 골라 strict TDD로 다시 시작한다

## 7. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
