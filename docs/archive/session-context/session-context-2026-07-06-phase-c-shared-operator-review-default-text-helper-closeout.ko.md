# 2026-07-06 Phase C shared operator review default text helper closeout

## 이번 턴에서 한 일

- `packages/core-engine/src/videobox_core_engine/canonical_operator_review_text.py`를 추가해 shared `canonical_operator_review_text(...)` helper와 `DEFAULT_OPERATOR_REVIEW_TEXT`를 만들었습니다.
- `prompt_pending_recommendation.py`, `review_guidance.py`, `local_pipeline.py`는 이제 같은 기본 operator review 문구 helper를 직접 재사용합니다.
- review flag message, pending recommendation reason, source timeline restore path에 흩어져 있던 같은 fallback 문구를 한 기준으로 모았습니다.

## 왜 이 작업을 했는가

- prompt/guidance/runtime read-path가 같은 기본 blocker 안내 문구를 파일별 helper와 inline literal로 각각 들고 있으면, 다음 cleanup에서 문구 fallback 기준이 다시 갈라질 위험이 있습니다.
- 지금 공통 helper로 묶어 두면 기본 operator review 안내 truth를 더 직접 공유하게 됩니다.

## 변경 범위

- 제품 동작 변경 없음
- 기본 operator review 문구 helper 공통화만 수행

## 검증

- exact verification
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_reuse_key_fills_default_review_flag_message or test_review_guidance_reuse_key_fills_default_pending_recommendation_reason or test_heuristic_review_guidance_builder_defaults_missing_pending_recommendation_reason" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_heuristic_review_guidance_builder_defaults_missing_review_flag_message" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_defaults_missing_pending_recommendation_reason_in_prompt" -vv`
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
