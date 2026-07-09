# 2026-07-06 broader rerun recovered nested target_segment_id pending recommendation regression closeout

## 이번 턴에서 한 일

- `current-focused-parallel`과 `broader`를 다시 실행해, 이제 final closeout 단계로 넘어갈 수 있는지 자동 baseline을 최신 상태로 확인했습니다.
- 그 과정에서 `test_editing_session_api_ignores_nested_target_segment_id_source_pending_recommendation_when_running_partial_regeneration` 회귀 1개를 발견했습니다.
- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_runtime_pending_recommendation_identity_key(...)`가 nested dict `target_segment_id`를 string으로 살리던 점만 최소 수정해 exact RED를 GREEN으로 복구했습니다.

## 왜 이 작업을 했는가

- 여러 Phase C cleanup 뒤에는 더 작은 리팩터링을 계속 여는 것보다, 실제로 broad 기준에서 남은 회귀가 있는지 확인하는 편이 더 중요해졌습니다.
- broad에서 실제 회귀가 하나라도 남아 있으면 final closeout, QA, 문서 정리가 다시 흔들릴 수 있기 때문에 먼저 잡아야 했습니다.

## 변경 범위

- 제품 동작 변경 범위는 `partial regeneration` 런타임 pending recommendation identity validation 1곳
- nested stale `target_segment_id` dict를 valid pending recommendation identity로 인정하지 않도록 수정

## 검증

- exact verification
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_ignores_nested_target_segment_id_source_pending_recommendation_when_running_partial_regeneration" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_filters_nested_target_segment_id_source_pending_recommendation_from_preflight_prediction" -vv`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-backend`
- broader verification
  - `npm run build`
  - `pytest -q`

## 남은 일

- final closeout 전 전체 동작 검증, QA, 시스템 검증 순서를 실제로 시작할지 판단합니다.
- historical 문서/찌꺼기 정리 기준을 정리합니다.
