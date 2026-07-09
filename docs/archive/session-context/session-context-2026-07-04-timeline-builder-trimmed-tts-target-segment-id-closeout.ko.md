# 2026-07-04 timeline builder trimmed TTS target segment id closeout

## 이번 slice

- 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 timeline builder consumer family에서 approved TTS recommendation의 stale whitespace `target_segment_id` 경계 1개를 다시 닫았다.
- strict TDD로 `test_timeline_builder_applies_trimmed_tts_target_segment_id_to_narration_clip` exact regression을 먼저 추가했고, 실제로 narration clip `asset_uri`가 generated TTS asset이 아니라 original segment URI로 남는 RED를 확인했다.
- 최소 수정으로 `packages/core-engine/src/videobox_core_engine/timeline_builder.py`의 `_recommendation_payload(...)`에서 `target_segment_id`를 trim해 segment bucket key와 returned applied surface가 같은 canonical id 기준을 쓰도록 맞췄다.
- 같은 exact GREEN을 먼저 확인한 뒤, timeline builder TTS focused 3개를 다시 돌려 인접 회귀가 없는지 확인했다.

## 검증

- exact regression
  - `py -m pytest tests/test_review_timeline.py -q -k "test_timeline_builder_applies_trimmed_tts_target_segment_id_to_narration_clip" -vv`
- focused verification
  - `py -m pytest tests/test_review_timeline.py -q -k "test_timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip or test_timeline_builder_applies_mixed_case_tts_replacement_type_to_narration_clip or test_timeline_builder_applies_trimmed_tts_target_segment_id_to_narration_clip" -vv`
  - 결과 `3 passed`

## 남은 판단

- broader는 이번 slice에서 다시 돌리지 않았다. 수정 범위가 timeline builder의 TTS target-segment matching 한 점이고 인접 focused 3개가 모두 green이므로, broader는 다음 task-close 시점에만 다시 판단한다.
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다.
