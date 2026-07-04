# 2026-07-04 CapCut export trimmed TTS recommendation type closeout

## 이번 세션에서 한 일

- CapCut export adapter가 applied recommendation의 whitespace stale `recommendation_type=" tts_replacement "`를 narration override segment로 인식하지 못해 voiceover 첫 segment를 original narration source로 내보내는 exact regression 1개를 TDD로 닫았다.
- `tests/test_preview_export.py`에 `test_capcut_export_adapter_matches_trimmed_tts_recommendation_type_for_segment_level_narration_sources`를 추가해 RED를 먼저 확인했다.
- `packages/capcut-export/src/videobox_capcut_export/adapter.py`에서 narration override segment 판정을 `str(...).strip() == "tts_replacement"`로 좁게 수정했다.

## 검증

- exact regression
  - `pytest tests/test_preview_export.py -q -k "matches_trimmed_tts_recommendation_type_for_segment_level_narration_sources"`
  - RED 확인 후 GREEN `1 passed`
- focused verification
  - `pytest tests/test_preview_export.py -q -k "matches_trimmed_tts_recommendation_type_for_segment_level_narration_sources or capcut_export_adapter_uses_segment_level_narration_sources_for_approved_tts_replacement"`
  - `2 passed`
  - `pytest tests/test_api.py -q -k "approved_tts_replacement_flows_through_preview_and_export_outputs"`
  - `1 passed`
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "matches_trimmed_tts_recommendation_type_for_segment_level_narration_sources or capcut_export_adapter_uses_segment_level_narration_sources_for_approved_tts_replacement or approved_tts_replacement_flows_through_preview_and_export_outputs"`
  - helper lane `1 passed`
- broader verification
  - 이번 slice에서는 실행하지 않음
  - 직전 baseline은 `full backend regression 346 passed`, `frontend build 성공`

## 남은 맥락

- 장기 queue는 유지하고, 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 exact regression 또는 가장 작은 증거 부족 경계 1개만 고른다.
- preview/export의 trimmed TTS output family는 이제 renderer와 export adapter 모두 canonical type 비교를 사용한다.
