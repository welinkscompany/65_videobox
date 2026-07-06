# 2026-07-06 Phase C shared canonical review-status helper closeout

## 이번 턴에서 한 일

- `packages/core-engine/src/videobox_core_engine/canonical_review_status.py`를 추가해 shared `canonical_review_status(...)` helper를 만들었습니다.
- `output_operator_copy.py`, `preview_renderer.py`, `review_guidance.py`, `local_pipeline.py`는 이제 같은 review-status helper를 직접 재사용합니다.
- helper 치환 중 `local_pipeline.py` 호출 1곳에 기본값이 빠져 있던 회귀를 exact 1개로 바로 재현하고, 그 호출만 최소 수정해 green으로 복구했습니다.

## 왜 이 작업을 했는가

- preview/output/review-guidance/runtime read-path가 같은 `review_status trim/lower` 규칙을 파일별 local helper로 각각 들고 있으면, 다음 cleanup에서 surface나 gating 기준이 다시 갈라질 위험이 있습니다.
- 지금 공통 helper로 묶어 두면 승인 상태 문자열과 blocked/draft/approved 판단 기준을 더 직접 공유하게 됩니다.

## 변경 범위

- 제품 동작 변경 없음
- canonical review-status helper 공통화와 누락 호출 1곳 복구만 수행

## 검증

- exact verification
  - `py -m pytest tests/test_api.py -q -k "test_preview_renderer_canonicalizes_mixed_case_review_status_surface" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_output_operator_copy_builder_canonicalizes_mixed_case_review_status_in_prompt" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_heuristic_review_guidance_builder_canonicalizes_mixed_case_approved_review_status" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_reuse_key_ignores_stale_unknown_and_minimal_blocker_entries" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_review_snapshot_ignores_persisted_approved_guidance_when_synthetic_segment_blocker_makes_status_blocked" -vv`
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
