# 2026-07-04 TTS output trimmed target segment id closeout

## 이번 slice

- 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 output consumer family에서 applied TTS recommendation의 stale whitespace `target_segment_id` 경계 1개를 다시 닫았다.
- strict TDD로 `test_capcut_export_adapter_matches_trimmed_tts_target_segment_id_for_segment_level_narration_sources` exact regression을 먼저 추가했고, 실제로 voiceover 첫 segment `source_uri`가 generated TTS asset이 아니라 original narration source로 남는 RED를 확인했다.
- 최소 수정으로 `packages/capcut-export/src/videobox_capcut_export/adapter.py`와 같은 규칙을 쓰는 `packages/core-engine/src/videobox_core_engine/preview_renderer.py`에서 applied TTS recommendation의 `target_segment_id`를 trim해 override segment set을 만들도록 맞췄다.
- exact GREEN을 먼저 확인한 뒤, CapCut export TTS focused 5개와 preview renderer TTS focused 4개를 다시 돌려 인접 회귀가 없는지 확인했다.

## 검증

- exact regression
  - `py -m pytest tests/test_preview_export.py -q -k "test_capcut_export_adapter_matches_trimmed_tts_target_segment_id_for_segment_level_narration_sources" -vv`
- focused verification
  - `py -m pytest tests/test_preview_export.py -q -k "test_capcut_export_adapter_matches_trimmed_tts_target_segment_id_for_segment_level_narration_sources or test_capcut_export_adapter_uses_segment_level_narration_sources_for_approved_tts_replacement or test_capcut_export_adapter_matches_trimmed_tts_recommendation_type_for_segment_level_narration_sources or test_capcut_export_adapter_matches_mixed_case_tts_recommendation_type_for_segment_level_narration_sources or test_capcut_export_adapter_treats_string_false_tts_review_required_as_false_for_segment_level_narration_sources" -vv`
  - 결과 `5 passed`
  - `py -m pytest tests/test_api.py -q -k "test_preview_renderer_treats_string_false_tts_recommendation_review_required_as_false or test_preview_renderer_matches_trimmed_tts_recommendation_type_for_narration_source or test_preview_renderer_matches_trimmed_tts_target_segment_id_for_narration_source or test_preview_renderer_matches_mixed_case_tts_recommendation_type_for_narration_source" -vv`
  - 결과 `4 passed`

## 남은 판단

- broader는 이번 slice에서 다시 돌리지 않았다. 수정 범위가 preview/export TTS override segment matching 한 점이고 인접 focused 9개가 모두 green이므로, broader는 다음 task-close 시점에만 다시 판단한다.
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다.
