# 2026-07-06 Phase C shared prompt canonical string helpers closeout

## 이번 턴에서 한 일

- `packages/core-engine/src/videobox_core_engine/prompt_pending_recommendation.py`에 prompt family가 공유하는 `canonical_prompt_recommendation_type`, `canonical_prompt_decision_state`, `canonical_prompt_review_flag_message` helper를 추가했습니다.
- `output_operator_copy.py`와 `review_guidance.py`는 이제 같은 canonical string helper를 공통 모듈에서 가져옵니다.

## 왜 이 작업을 했는가

- valid set과 identity helper까지 공통화한 뒤에도, canonical string helper 3개는 두 파일 안에 같은 본문으로 각각 남아 있었습니다.
- 이 상태를 그대로 두면 mixed-case recommendation type, pending decision_state, default review message 기준이 나중에 파일별로 다시 갈라질 수 있었습니다.

## 변경 범위

- 제품 동작 변경 없음
- prompt family canonical string helper 공통화만 수행

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
