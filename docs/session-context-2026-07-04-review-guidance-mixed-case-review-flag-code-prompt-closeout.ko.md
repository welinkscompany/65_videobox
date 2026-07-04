# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- review guidance mixed-case review flag code prompt closeout

## 1. 이번 turn에서 실제로 끝낸 것

- `review_guidance` prompt가 mixed-case stale `review_flags.code`를 raw로 그대로 노출하던 가장 작은 경계 1개를 닫았다
- `LocalFirstReviewGuidanceBuilder._build_prompt(...)`가 prompt 전용 review-flag 정리 helper를 거쳐 canonical lowercase code를 쓰도록 맞췄다
- exact regression 1개와 review guidance focused verification만으로 이번 slice를 닫았다

## 2. 이번 turn의 핵심 판단

- 장기 queue 후보는 `review_guidance`의 `review_flags.code`, 같은 surface의 `segment_id`, 그리고 더 먼 `preflight contract` 경계로 좁혔다
- 이 중 가장 가까운 경계는 `review/output gating`과 바로 붙어 있는 `review_guidance` prompt의 raw review-flag code surface였다
- 이미 `pending_recommendations`와 `segments needing attention` prompt surface를 같은 family에서 정리해 둔 상태라, 이번에는 `review_flags.code`만 최소 수정으로 맞추는 편이 가장 작고 직접적이었다

## 3. 이번 turn의 변경 범위

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`
  - `_canonical_review_flag_code(...)` 추가
  - `_prompt_review_flags(...)` 추가
  - `_build_prompt(...)`가 raw `review_flags` 대신 canonicalized prompt rows를 사용하도록 변경
- `tests/test_api.py`
  - `test_review_guidance_builder_canonicalizes_mixed_case_review_flag_code_in_prompt` 추가
- SSOT 문서 업데이트
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`

## 4. 이번 turn의 verification

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_canonicalizes_mixed_case_review_flag_code_in_prompt" -vv`
  - 결과: `1 failed` 확인 후 `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_trims_segment_ids_needing_attention_in_prompt or test_review_guidance_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt or test_review_guidance_builder_trims_pending_recommendation_target_segment_id_in_prompt or test_review_guidance_builder_canonicalizes_mixed_case_review_flag_code_in_prompt or test_heuristic_review_guidance_builder_canonicalizes_mixed_case_approved_review_status" -vv`
  - 결과: `5 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt code surface 한 점만 바뀌었고 exact + family-focused evidence가 더 직접적이다

## 5. 쉽게 말한 현재 개발상황

- 이제 review guidance prompt도 review flag code를 raw 대문자/공백 섞인 값으로 보여주지 않는다
- 즉, operator guidance를 만드는 prompt가 review/output gating이 이미 쓰는 canonical blocker 기준과 더 같은 방향으로 맞춰졌다

## 6. 다음 세션 첫 시작점

1. 이번 slice는 `review_guidance` prompt의 `review_flags.code` surface closeout으로 본다
2. 다음 작업은 다시 `docs/implementation-plan.ko.md`의 `## 13. 다음 실제 작업` 기준으로 후보를 2~3개로만 좁힌다
3. 그중 `review/output gating`, `TTS approval/output`, `preflight contract`에 가장 가까운 exact regression 1개를 골라 strict TDD로 다시 시작한다

## 7. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
