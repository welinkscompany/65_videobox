# 2026-07-06 Phase C output operator copy pending row normalization refactor closeout

## 이번 턴에서 한 일

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py` 안에서 pending recommendation prompt row 정규화 코드를 helper 1개로 공통화했습니다.
- 이 helper가 `recommendation_id`, `target_segment_id`, `recommendation_type`, `reason`, `decision_state`, `selected_asset_id`, `created_at`, `payload.selected_asset_uri`를 같은 기준으로 정리하도록 묶었습니다.

## 왜 이 작업을 했는가

- 현재 단계는 새 stale-shape 버그를 여는 것보다, 실제 중복이 눈에 보이는 작은 `Phase C` 정리 리팩터링을 하나씩 닫는 쪽이 맞습니다.
- output operator copy prompt는 blocking pending recommendation 판별과 prompt row canonicalization이 같은 파일 안에서 따로 흩어져 있어, 나중에 trim/lower/default 규칙이 한쪽만 바뀌면 prompt surface 기준이 다시 어긋날 수 있었습니다.

## 변경 범위

- 제품 동작 변경 없음
- output operator copy prompt 내부 helper 공통화만 수행

## 검증

- exact verification
  - `py -m pytest tests/test_api.py -q -k "test_output_operator_copy_builder_trims_pending_recommendation_selected_asset_uri_in_prompt" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_output_operator_copy_builder_ignores_minimal_dict_pending_recommendations_in_prompt" -vv`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - 결과:
    - backend output-gating `24 passed`

## 남은 일

- review guidance prompt 쪽 pending recommendation row normalization 중복을 같은 방식으로 줄일지 판단합니다.
- broader 재검증은 아직 하지 않았고, 최종 closeout 직전에 다시 판단합니다.
