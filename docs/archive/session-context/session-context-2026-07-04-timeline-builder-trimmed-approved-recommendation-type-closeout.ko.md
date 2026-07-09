# 2026-07-04 timeline builder trimmed approved recommendation type closeout

## 이번 세션에서 한 일
- `tests/test_review_timeline.py`에 `test_timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip` exact regression을 추가했다.
- `packages/core-engine/src/videobox_core_engine/timeline_builder.py`의 approved recommendation type 분기에서 `recommendation_type.strip()` 비교를 적용했다.
- timeline builder가 whitespace가 섞인 `" tts_replacement "` approved recommendation도 narration clip 반영에 놓치지 않도록 맞췄다.

## 왜 이 작업을 했는가
- 직전 closeout들로 review snapshot helper와 approve mutation의 trimmed recommendation type family는 닫혔지만, timeline builder 본체에는 같은 family의 raw comparison이 남아 있었다.
- 그 결과 supported recommendation type 필터는 통과한 `" tts_replacement "` stale shape가 실제 narration clip 반영 단계에서는 매칭되지 않아, approved recommendation truth와 output clip truth가 어긋날 수 있었다.

## 검증
- exact regression
  - `pytest tests/test_review_timeline.py -k "timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip"` -> `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip or trimmed_broll_type_for_default_provider_trace or review_snapshot_api_approve_tts_replacement_matches_trimmed_recommendation_type or review_snapshot_api_approve_tts_replacement_surfaces_approved_decision_state_in_read_paths"` -> `2 passed`

## 남은 일
- broader verification은 아직 재실행하지 않았다. 이번 수정 범위가 timeline builder 내부 recommendation type 비교 2줄이라 exact + focused evidence를 우선 채택했다.
- 다음 slice는 다시 장기 우선순위 queue로 돌아가 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 exact regression 1개를 고른다.
