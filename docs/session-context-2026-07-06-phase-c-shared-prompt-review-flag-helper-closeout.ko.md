# 2026-07-06 Phase C shared prompt review-flag helper closeout

## 이번 턴에서 한 일

- `packages/core-engine/src/videobox_core_engine/prompt_pending_recommendation.py`에 review-flag identity helper와 prompt-row normalization helper를 추가했습니다.
- `output_operator_copy.py`와 `review_guidance.py`는 이제 review flag 쪽 prompt 정리도 같은 공통 helper를 재사용합니다.

## 왜 이 작업을 했는가

- pending recommendation 쪽 helper는 이미 공통화됐지만, review flag 쪽은 두 prompt 파일이 같은 identity 판정과 row 정리 로직을 각각 따로 들고 있었습니다.
- 이 상태를 그대로 두면 valid blocker code, trimmed segment id, default blocker message 기준이 나중에 파일별로 다시 갈라질 수 있었습니다.

## 변경 범위

- 제품 동작 변경 없음
- prompt family review-flag helper 공통화만 수행

## 검증

- exact verification
  - `py -m pytest tests/test_api.py -q -k "test_output_operator_copy_builder_canonicalizes_review_flag_code_in_prompt" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_output_operator_copy_builder_ignores_minimal_dict_review_flags_in_prompt" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_canonicalizes_mixed_case_review_flag_code_in_prompt" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_ignores_minimal_dict_review_flags_in_prompt" -vv`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - 결과:
    - backend output-gating `24 passed`

## 남은 일

- stale-shape helper 중복과 dead helper 후보 중 다음 최소 정리 대상 1개를 다시 좁힙니다.
- broader 재검증은 아직 하지 않았고, 최종 closeout 직전에 다시 판단합니다.
