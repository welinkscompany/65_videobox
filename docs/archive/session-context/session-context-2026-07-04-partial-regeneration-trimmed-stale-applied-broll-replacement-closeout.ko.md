# 2026-07-04 partial regeneration trimmed stale applied broll replacement closeout

## 이번 세션에서 한 일
- `tests/test_api.py`에 `test_editing_session_api_replaces_trimmed_stale_applied_broll_recommendation_when_running_partial_regeneration` exact regression을 추가했다.
- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 partial regeneration `broll_refresh` 기존 recommendation 제거 분기에서 `recommendation_type.strip()` 비교를 적용했다.
- partial regeneration runtime이 whitespace가 섞인 `" broll "` stale approved recommendation보다 새 manual B-roll selection을 우선 반영하도록 맞췄다.

## 왜 이 작업을 했는가
- 직전 closeout으로 partial regeneration `tts_refresh`의 trimmed recommendation type family는 닫혔지만, `broll_refresh`에는 같은 family의 raw comparison이 남아 있었다.
- 그 결과 source timeline에 `" broll "` stale approved recommendation이 남아 있으면 refresh가 기존 recommendation을 제거하지 못하고 carry-forward해서, 새 manual B-roll selection을 했어도 결과 broll track에 예전 clip과 새 clip이 함께 남을 수 있었다.

## 검증
- exact regression
  - `pytest tests/test_api.py -k "replaces_trimmed_stale_applied_broll_recommendation_when_running_partial_regeneration"` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "replaces_trimmed_stale_applied_broll_recommendation_when_running_partial_regeneration or replaces_trimmed_stale_applied_tts_recommendation_when_running_partial_regeneration or timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip or trimmed_broll_type_for_default_provider_trace"` -> `2 passed`

## 남은 일
- broader verification은 아직 재실행하지 않았다. 이번 수정 범위가 partial regeneration runtime `broll_refresh` 비교 1줄이라 exact + focused evidence를 우선 채택했다.
- 다음 slice는 다시 장기 우선순위 queue로 돌아가 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 exact regression 1개를 고른다.
