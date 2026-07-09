# 2026-07-06 Phase C shared canonical review-flag helper closeout

## 이번 턴에서 한 일

- `packages/core-engine/src/videobox_core_engine/canonical_review_flag.py`를 추가해 shared `canonical_review_flag_code`와 `VALID_CANONICAL_REVIEW_FLAG_CODES`를 만들었습니다.
- `prompt_pending_recommendation.py`, `review_action_mutations.py`, `local_pipeline.py`는 이제 같은 review-flag helper를 직접 재사용합니다.

## 왜 이 작업을 했는가

- mixed-case review-flag code와 valid blocker code 경계는 이미 테스트로 닫혀 있었지만, 구현은 여러 파일이 같은 `trim/lower` 함수와 같은 set 상수를 각각 따로 들고 있었습니다.
- 지금 공통 helper로 묶어 두면 prompt/output/runtime/review-action이 같은 review-flag truth를 더 직접 공유하게 됩니다.

## 변경 범위

- 제품 동작 변경 없음
- canonical review-flag helper 공통화만 수행

## 검증

- exact verification
  - `py -m pytest tests/test_api.py -q -k "test_output_operator_copy_builder_canonicalizes_review_flag_code_in_prompt" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_canonicalizes_mixed_case_review_flag_code_in_prompt" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_output_gating_blocks_mixed_case_review_flag_code_on_approved_timeline" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_approving_last_pending_recommendation_removes_mixed_case_review_flag_code_for_same_segment" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_reuse_key_ignores_stale_unknown_and_minimal_blocker_entries" -vv`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - 결과:
    - backend output-gating `24 passed`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-backend`
  - 결과:
    - backend preflight `59 passed`

## 남은 일

- stale-shape helper 중복과 dead helper 후보 중 다음 최소 정리 대상 1개를 다시 좁힙니다.
- broader 재검증은 아직 하지 않았고, 최종 closeout 직전에 다시 판단합니다.
