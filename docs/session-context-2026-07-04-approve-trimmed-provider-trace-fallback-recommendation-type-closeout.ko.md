# 2026-07-04 approve trimmed provider-trace fallback recommendation type closeout

## 이번 세션에서 한 일
- `tests/test_api.py`에 `test_review_snapshot_api_approve_broll_uses_trimmed_recommendation_type_for_provider_trace_fallback` exact regression을 추가했다.
- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 approve mutation fallback provider 선택에서 `recommendation_type.strip()` 비교를 적용했다.
- approve response와 persisted applied recommendation trace가 whitespace가 섞인 `" broll "` stale shape에서도 `heuristic_fallback`을 유지하도록 맞췄다.

## 왜 이 작업을 했는가
- 최근 approve trim hardening은 주로 TTS clip 반영과 recommendation id / review flag cleanup 축을 닫았지만, `provider_trace` fallback 선택에는 같은 trim 규칙이 남아 있지 않았다.
- 그 결과 persisted recommendation에 whitespace가 섞인 `" broll "` type과 missing `provider_trace`가 함께 들어오면 approve 응답과 persisted applied recommendation trace가 `rule_based_fallback`으로 잘못 기록됐다.

## 검증
- exact regression
  - `pytest tests/test_api.py -k "approve_broll_uses_trimmed_recommendation_type_for_provider_trace_fallback"` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "approve_broll_uses_trimmed_recommendation_type_for_provider_trace_fallback or review_snapshot_api_approve_tts_replacement_matches_trimmed_recommendation_type or review_snapshot_api_can_reject_pending_recommendation_without_leaving_it_pending or approving_one_of_multiple_pending_recommendations_keeps_output_blocked_by_remaining_detail"` -> `4 passed`

## 남은 일
- broader verification은 아직 재실행하지 않았다. 이번 수정 범위가 approve mutation fallback provider 비교 1줄이라 exact + focused evidence를 우선 채택했다.
- 다음 slice는 다시 장기 우선순위 queue로 돌아가 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 exact regression 1개를 고른다.
