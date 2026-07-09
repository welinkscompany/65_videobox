# 2026-07-04 partial regeneration trimmed TTS target segment id closeout

## 이번 slice

- 장기 우선순위 queue를 유지한 채, `TTS approval/output`과 바로 이어지는 partial regeneration runtime의 stale whitespace TTS target-segment 경계 1개를 다시 닫았다.
- strict TDD로 `test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_tts_recommendation_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 partial regeneration result narration clip `asset_uri`가 stale generated TTS asset URI 그대로 남는 RED를 확인했다.
- 최소 수정으로 `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_tts_refresh_step(...)`에서 stale applied recommendation 제거 비교도 `target_segment_id.strip()` 기준으로 맞췄다.
- 같은 exact GREEN을 먼저 확인한 뒤, partial regeneration TTS focused 3개를 다시 돌려 인접 회귀가 없는지 확인했다.

## 검증

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_tts_recommendation_when_running_partial_regeneration" -vv`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_replaces_trimmed_stale_applied_tts_recommendation_when_running_partial_regeneration or test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_tts_recommendation_when_running_partial_regeneration or test_editing_session_api_replaces_mixed_case_stale_applied_tts_recommendation_when_running_partial_regeneration" -vv`
  - 결과 `3 passed`

## 남은 판단

- broader는 이번 slice에서 다시 돌리지 않았다. 수정 범위가 partial regeneration TTS refresh 제거 비교 한 점이고 인접 focused 3개가 모두 green이므로, broader는 다음 task-close 시점에만 다시 판단한다.
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다.
