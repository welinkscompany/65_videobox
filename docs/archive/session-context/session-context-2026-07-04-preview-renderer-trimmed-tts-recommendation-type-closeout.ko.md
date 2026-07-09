# 2026-07-04 preview renderer trimmed TTS recommendation type closeout

## 이번 세션에서 한 일

- preview renderer가 applied recommendation의 whitespace stale `recommendation_type=" tts_replacement "`를 TTS override로 인식하지 못해 preview HTML narration source를 original source로 되돌리는 exact regression 1개를 TDD로 닫았다.
- `tests/test_api.py`에 `test_preview_renderer_matches_trimmed_tts_recommendation_type_for_narration_source`를 추가해 RED를 먼저 확인했다.
- `packages/core-engine/src/videobox_core_engine/preview_renderer.py`에서 TTS applied segment 판정을 `str(...).strip() == "tts_replacement"`로 좁게 수정했다.

## 검증

- exact regression
  - `pytest tests/test_api.py -q -k "preview_renderer_matches_trimmed_tts_recommendation_type_for_narration_source"`
  - RED 확인 후 GREEN `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "preview_renderer_matches_trimmed_tts_recommendation_type_for_narration_source or preview_renderer_treats_string_false_tts_recommendation_review_required_as_false or approved_tts_replacement_flows_through_preview_and_export_outputs"`
  - `3 passed`
- broader verification
  - 이번 slice에서는 실행하지 않음
  - 직전 baseline은 `full backend regression 346 passed`, `frontend build 성공`

## 남은 맥락

- 장기 queue는 유지하고, 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 exact regression 또는 가장 작은 증거 부족 경계 1개만 고른다.
- 같은 출력 family에서 아직 남아 있을 가능성이 높은 후보는 CapCut export의 trimmed TTS recommendation type 처리다.
