# 2026-07-06 Phase C shared strict boolish helper closeout

## 이번 턴에서 한 일

- `packages/core-engine/src/videobox_core_engine/canonical_boolish.py`를 추가해 shared `normalize_strict_boolish(...)` helper를 만들었습니다.
- `preview_renderer.py`, `review_guidance.py`, `local_pipeline.py`는 이제 같은 strict boolish helper를 직접 재사용합니다.
- permissive `bool(value)` 의미를 쓰는 다른 helper와는 일부 의미가 달라, 이번 턴에서는 같은 strict semantics를 쓰는 경로만 묶었습니다.

## 왜 이 작업을 했는가

- preview/output gating/review-guidance read-path가 같은 string false / stale non-bool 처리 규칙을 파일별 local helper로 각각 들고 있으면, 다음 cleanup에서 `review_required` 해석 기준이 다시 갈라질 위험이 있습니다.
- 지금 공통 helper로 묶어 두면 strict boolish truth를 더 직접 공유하게 됩니다.

## 변경 범위

- 제품 동작 변경 없음
- strict boolish helper 공통화만 수행

## 검증

- exact verification
  - `py -m pytest tests/test_api.py -q -k "test_preview_renderer_treats_string_false_tts_recommendation_review_required_as_false" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_ignores_string_false_segment_review_required" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_normalizes_stale_non_bool_review_required_to_false_in_preflight_targeted_segments" -vv`
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
