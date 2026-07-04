# 2026-07-04 partial regeneration trimmed stale applied BGM replacement closeout

## 이번 세션에서 한 일

- `partial regeneration`의 `music_refresh`가 source timeline에 남아 있는 whitespace stale applied `recommendation_type=" bgm "`를 제거하지 못해 stale/manual BGM clip이 같이 남는 exact regression 1개를 TDD로 닫았다.
- `tests/test_api.py`에 `test_editing_session_api_replaces_trimmed_stale_applied_bgm_recommendation_when_running_partial_regeneration`를 추가해 RED를 먼저 확인했다.
- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_music_refresh_step(...)`에서 stale applied recommendation 제거 비교를 `str(...).strip() == RecommendationType.BGM.value`로 좁게 수정했다.

## 검증

- exact regression
  - `pytest tests/test_api.py -q -k "replaces_trimmed_stale_applied_bgm_recommendation_when_running_partial_regeneration"`
  - RED 확인 후 GREEN `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "replaces_trimmed_stale_applied_bgm_recommendation_when_running_partial_regeneration or replaces_trimmed_stale_applied_broll_recommendation_when_running_partial_regeneration or replaces_trimmed_stale_applied_tts_recommendation_when_running_partial_regeneration"`
  - `3 passed`
- broader verification
  - 이번 slice에서는 실행하지 않음
  - 직전 baseline은 `full backend regression 346 passed`, `frontend build 성공`

## 남은 맥락

- 장기 queue는 그대로 유지하고, 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 exact regression 또는 가장 작은 증거 부족 경계 1개만 고른다.
- 이번 수정은 partial regeneration output path의 trimmed recommendation-type family 한 점만 닫은 것이므로 broader는 새 고위험 신호가 생길 때만 재판단하면 된다.
