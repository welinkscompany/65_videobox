# 2026-07-06 recommendation response normalization filters missing recommendation type closeout

## 이번에 한 일

- `services/api/src/videobox_api/main.py`의 `_normalize_recommendations_for_response(...)`가 `recommendation_id`와 `target_segment_id`만 있으면 `recommendation_type`이 비어 있는 stale recommendation row도 API response surface에 그대로 남기던 문제를 정리했다.
- strict TDD로 `test_recommendation_response_normalization_filters_missing_recommendation_type` exact regression을 먼저 추가해 RED를 확인했다.
- 최소 수정으로 canonical lowercase `recommendation_type`가 supported recommendation type 집합에 없으면 row 자체를 건너뛰도록 바꿨다.
- 직전 탐색 중 추가했던 `test_preview_renderer_ignores_non_dict_tracks_in_track_summary_surfaces`는 즉시 통과해서 strict TDD slice가 아니었으므로 이번 closeout 범위에 포함하지 않고 제거했다.

## 왜 이 작업을 했는가

- 최근 prompt, decision extraction, preflight/runtime 경계는 모두 valid recommendation 기준을 `recommendation_id + target_segment_id + supported recommendation_type`로 맞추고 있었다.
- 하지만 API response normalization만 `recommendation_type`이 비어 있는 stale row를 그대로 남기고 있어, review/output read surface가 다른 경로와 어긋날 수 있었다.
- 이 경계를 닫아야 review snapshot / timeline / direct normalization helper가 같은 recommendation validity 기준을 공유한다.

## 변경 파일

- `services/api/src/videobox_api/main.py`
- `tests/test_api.py`
- `docs/implementation-plan.ko.md`
- `docs/development-status-2026-06-29.ko.md`

## 검증

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_recommendation_response_normalization_filters_missing_recommendation_type" -vv`
  - RED: `1 failed`
  - GREEN: `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_recommendation_response_normalization_canonicalizes_mixed_case_recommendation_type or test_recommendation_response_normalization_trims_payload_selected_asset_uri or test_recommendation_response_normalization_filters_missing_recommendation_type or test_timeline_api_filters_unknown_type_entry_misbucketed_into_applied_recommendations" -vv`
  - 결과: `4 passed`

## 남은 판단

- 장기 우선순위 queue는 유지한다.
- 다음 slice도 `review/output gating` -> `TTS approval/output` -> `preflight contract` 순서 안에서 가장 작은 exact failing regression 1개만 다시 고른다.
- broader verification은 아직 실행하지 않았고, latest baseline은 기존 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`이다.
