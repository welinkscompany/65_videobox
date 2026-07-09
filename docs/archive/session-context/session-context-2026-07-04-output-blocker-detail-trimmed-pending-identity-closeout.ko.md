# 2026-07-04 output blocker detail trimmed pending identity closeout

## 이번 slice

- 장기 우선순위 queue는 유지한 채, `review/output gating`에 가장 가까운 output blocker detail surface의 stale whitespace pending recommendation identity 경계 1개만 다시 닫았다.
- exact regression `test_output_blocker_detail_trims_pending_recommendation_identity_fields`를 먼저 추가했고, 실제로 preview render 차단 detail이 `tts_replacement: rec_tts_seg_001 @ seg_001 `처럼 raw whitespace를 노출하는 RED를 확인했다.
- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_normalized_runtime_pending_recommendations(...)`에서 blocker surface에 쓰이는 `recommendation_id`, `target_segment_id`도 trim된 값으로 정규화하도록 최소 수정했다.
- 같은 exact test GREEN을 먼저 확인한 뒤, output-gating 인접 focused 6개만 다시 돌려 회귀가 없는지 확인했다.

## 검증

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_output_blocker_detail_trims_pending_recommendation_identity_fields" -vv`
- focused output-gating slice
  - `py -m pytest tests/test_api.py -q -k "test_output_blocker_detail_trims_pending_recommendation_identity_fields or test_output_blocker_detail_canonicalizes_mixed_case_pending_recommendation_type or test_output_blockers_deduplicate_repeated_persisted_pending_recommendation_entries or test_output_gating_blocks_mixed_case_review_flag_code_on_approved_timeline or test_approved_review_state_still_blocks_outputs_when_only_pending_recommendations_remain or test_approving_one_of_multiple_pending_recommendations_keeps_output_blocked_by_remaining_detail" -vv`
  - 결과 `6 passed`

## 남은 판단

- broader는 이번 slice에서 다시 돌리지 않았다. 현재 작업은 output-gating detail surface 한 점만 좁게 수정했고, focused 인접 회귀가 모두 green이므로 broader는 다음 task-close 시점에만 다시 판단한다.
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다.
