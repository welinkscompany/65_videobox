# 2026-07-06 Phase C prompt canonical wrapper removal closeout

## 이번 턴에서 한 일

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`와 `packages/core-engine/src/videobox_core_engine/review_guidance.py`에서 공통 canonical helper를 다시 감싸기만 하던 local wrapper 함수를 제거했습니다.
- 두 파일은 이제 공통 canonical helper를 import alias로 직접 사용합니다.

## 왜 이 작업을 했는가

- canonical string helper 본체는 이미 공통 모듈로 옮겨졌는데, 각 파일 안에 thin wrapper가 남아 있어 탐색 경로만 길어져 있었습니다.
- 지금 정리해 두면 prompt family cleanup의 마지막 작은 중복까지 줄이면서도 동작은 바꾸지 않을 수 있습니다.

## 변경 범위

- 제품 동작 변경 없음
- prompt family local wrapper 제거만 수행

## 검증

- exact verification
  - `py -m pytest tests/test_api.py -q -k "test_output_operator_copy_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_output_operator_copy_builder_ignores_minimal_dict_pending_recommendations_in_prompt" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_ignores_unknown_pending_recommendation_in_prompt_count" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_ignores_minimal_dict_pending_recommendations_in_prompt" -vv`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - 결과:
    - backend output-gating `24 passed`

## 남은 일

- stale-shape helper 중복과 dead helper 후보 중 다음 최소 정리 대상 1개를 다시 좁힙니다.
- broader 재검증은 아직 하지 않았고, 최종 closeout 직전에 다시 판단합니다.
