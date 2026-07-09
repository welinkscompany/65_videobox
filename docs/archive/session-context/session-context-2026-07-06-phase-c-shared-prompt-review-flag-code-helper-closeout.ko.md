# 2026-07-06 Phase C shared prompt review-flag code helper closeout

## 이번 턴에서 한 일

- `packages/core-engine/src/videobox_core_engine/prompt_pending_recommendation.py`에 shared review-flag code canonicalizer를 추가했습니다.
- `output_operator_copy.py`와 `review_guidance.py`는 이제 review-flag code 정리도 같은 공통 helper를 직접 사용합니다.

## 왜 이 작업을 했는가

- review-flag identity / row helper는 이미 공통화됐지만, 그 helper에 넘기던 `trim + lower` canonicalizer는 두 prompt 파일 안에 각각 남아 있었습니다.
- 이 마지막 local wrapper까지 정리해 두면 mixed-case review-flag code 기준이 파일별로 다시 갈라질 가능성을 더 줄일 수 있습니다.

## 변경 범위

- 제품 동작 변경 없음
- prompt family review-flag code helper 공통화만 수행

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
