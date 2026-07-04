# 2026-07-04 review snapshot trimmed provider-trace fallback recommendation type closeout

## 이번 세션에서 한 일
- `tests/test_review_timeline.py`에 `test_review_snapshot_uses_trimmed_broll_type_for_default_provider_trace` exact regression을 추가했다.
- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 review snapshot helper fallback provider 선택에서 `recommendation_type.strip()` 비교를 적용했다.
- review snapshot applied recommendation read path가 whitespace가 섞인 `" broll "` stale shape에서도 `heuristic_fallback` trace를 유지하도록 맞췄다.

## 왜 이 작업을 했는가
- 직전 closeout으로 approve mutation의 trimmed provider-trace fallback은 닫혔지만, review snapshot helper read path에는 같은 family의 raw comparison이 남아 있었다.
- 그 결과 persisted/applied recommendation에 whitespace가 섞인 `" broll "` type과 missing `provider_trace`가 함께 들어오면 review snapshot applied recommendation trace가 `rule_based_fallback`으로 잘못 기록됐다.

## 검증
- exact regression
  - `pytest tests/test_review_timeline.py -k "trimmed_broll_type_for_default_provider_trace"` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "trimmed_broll_type_for_default_provider_trace or review_snapshot_api_approve_broll_uses_trimmed_recommendation_type_for_provider_trace_fallback or review_snapshot_api_approve_tts_replacement_matches_trimmed_recommendation_type or review_snapshot_api_approve_tts_replacement_surfaces_approved_decision_state_in_read_paths"` -> `3 passed`

## 남은 일
- broader verification은 아직 재실행하지 않았다. 이번 수정 범위가 review snapshot helper fallback provider 비교 1줄이라 exact + focused evidence를 우선 채택했다.
- 다음 slice는 다시 장기 우선순위 queue로 돌아가 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 exact regression 1개를 고른다.
