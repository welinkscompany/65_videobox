# 2026-07-06 Phase C shared prompt pending row normalization helper closeout

## 이번 턴에서 한 일

- `packages/core-engine/src/videobox_core_engine/prompt_pending_recommendation.py`를 추가해, output operator copy와 review guidance가 공통으로 쓰는 pending recommendation prompt row 정규화 helper를 분리했습니다.
- `output_operator_copy.py`와 `review_guidance.py`는 이제 각자 같은 row normalization 본문을 들고 있지 않고, 공통 helper를 호출하도록 정리했습니다.

## 왜 이 작업을 했는가

- 바로 앞 두 턴에서 output operator copy와 review guidance 내부 중복은 줄였지만, 두 파일이 거의 같은 helper 본문을 각자 유지하고 있었습니다.
- 이 상태를 그대로 두면 다음에 `selected_asset_uri`, identity, reason, decision_state canonicalization 규칙을 조정할 때 두 파일이 다시 따로 움직일 수 있었습니다.

## 변경 범위

- 제품 동작 변경 없음
- prompt pending recommendation row normalization helper 공통화만 수행

## 검증

- exact verification
  - `py -m pytest tests/test_api.py -q -k "test_output_operator_copy_builder_trims_pending_recommendation_selected_asset_uri_in_prompt" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_output_operator_copy_builder_ignores_minimal_dict_pending_recommendations_in_prompt" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_trims_pending_recommendation_selected_asset_uri_in_prompt" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_ignores_minimal_dict_pending_recommendations_in_prompt" -vv`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - 결과:
    - backend output-gating `24 passed`

## 남은 일

- stale-shape helper 중복이나 dead helper 후보 중 다음 최소 정리 대상 1개를 다시 좁힙니다.
- broader 재검증은 아직 하지 않았고, 최종 closeout 직전에 다시 판단합니다.
