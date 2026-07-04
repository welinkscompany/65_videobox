# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- review guidance mixed-case pending recommendation type prompt closeout

## 1. 이번 turn에서 실제로 끝낸 것

- `review_guidance.py`의 operator-facing guidance prompt에서 pending recommendation type이 mixed-case stale shape로 남는 경계 1개를 닫았다
- strict TDD로 exact failing test 1개를 먼저 추가하고 RED를 확인한 뒤, minimal GREEN만 넣고 같은 exact test로 다시 검증했다
- 구현 계획서 최신 메모와 상태 문서에 이번 slice를 반영해 다음 턴 SSOT가 이어지도록 맞췄다

## 2. 이번 turn의 핵심 판단

- 장기 queue 후보는 다시 `review/output gating`, `TTS approval/output`, `preflight contract`로 좁혔고, 그중 가장 작은 남은 경계는 `review_guidance` prompt의 `pending_recommendations` surface라고 판단했다
- 직전 `review_guidance` prompt `segment_id` surface 정리와 같은 읽기 경계라서, 같은 canonicalization 기준을 recommendation type에도 맞추는 것이 가장 작고 직접적인 보강이었다
- helper 전체 focused lane보다 인접 exact regressions를 좁게 다시 돌리는 편이 이번 slice의 증거를 더 짧고 정확하게 남길 수 있다고 판단했다

## 3. 이번 turn의 변경 범위

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`
  - prompt용 pending recommendation surface에서 `recommendation_type`을 `strip().lower()` 기준으로 정리
- `tests/test_api.py`
  - `test_review_guidance_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt` 추가
- 문서 반영
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
  - `docs/session-context-2026-07-04-review-guidance-mixed-case-pending-recommendation-type-prompt-closeout.ko.md`

## 4. 이번 turn의 verification

- exact RED
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt" -vv`
  - 결과: `1 failed`
- exact GREEN
  - 같은 명령 재실행
  - 결과: `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_trims_segment_ids_needing_attention_in_prompt or test_review_guidance_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt or test_heuristic_review_guidance_builder_canonicalizes_mixed_case_approved_review_status or test_output_operator_copy_builder_canonicalizes_mixed_case_track_type_in_prompt" -vv`
  - 결과: `4 passed`

## 5. 쉽게 말한 현재 개발상황

- guidance prompt는 어떤 추천이 막혀 있는지 LLM/운영자에게 넘기는 입력인데, 여기만 `TTS_REPLACEMENT` 같은 오래된 대문자 타입을 그대로 들고 있었습니다
- 이번에 그 부분도 같은 기준으로 맞춰서, guidance 쪽 recommendation type 표기가 다른 read-path와 어긋나지 않게 정리했습니다

## 6. 다음 세션 첫 시작점

1. 이번 slice는 `review_guidance` prompt `pending_recommendations` surface까지 닫힌 상태로 본다
2. 다음 작업은 다시 `docs/implementation-plan.ko.md`의 `## 13. 다음 실제 작업` 기준으로 장기 queue 후보를 2~3개로 좁힌다
3. 그중 `review/output gating`, `TTS approval/output`, `preflight contract`에 가장 가까운 exact regression 1개를 골라 strict TDD로 다시 시작한다

## 7. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
