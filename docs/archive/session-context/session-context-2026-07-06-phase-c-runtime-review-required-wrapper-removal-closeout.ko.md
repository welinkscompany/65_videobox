# 2026-07-06 Phase C runtime review-required wrapper removal closeout

## 이번 턴에서 한 일

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`에서 `_normalize_runtime_review_required(...)` dead wrapper를 제거했습니다.
- 기존 사용처는 `_normalize_runtime_boolish(...)`를 직접 사용하도록 정리했습니다.

## 왜 이 작업을 했는가

- 이 wrapper는 별도 규칙이 없이 boolish helper를 그대로 한 번 더 호출하기만 했습니다.
- 사용처도 아주 좁아서, 지금 정리해 두면 runtime normalization 경로를 더 직접적으로 유지할 수 있습니다.

## 변경 범위

- 제품 동작 변경 없음
- runtime review_required dead wrapper 제거만 수행

## 검증

- exact verification
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_normalizes_legacy_string_false_segment_review_required_from_store" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_normalizes_string_false_review_required_when_running_partial_regeneration" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_output_jobs_ignore_stale_non_bool_segment_review_required_on_approved_timeline" -vv`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - 결과:
    - backend output-gating `24 passed`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-backend`
  - 결과:
    - exit code `0`

## 남은 일

- stale-shape helper 중복과 dead helper 후보 중 다음 최소 정리 대상 1개를 다시 좁힙니다.
- broader 재검증은 아직 하지 않았고, 최종 closeout 직전에 다시 판단합니다.
