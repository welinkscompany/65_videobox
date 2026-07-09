# 2026-07-06 Phase C shared canonical source-uri helper closeout

## 이번 턴에서 한 일

- `packages/core-engine/src/videobox_core_engine/canonical_source_uri.py`를 추가해 shared `canonical_source_uri(...)` helper를 만들었습니다.
- `preview_renderer.py`, `review_action_mutations.py`, `timeline_builder.py`, `local_pipeline.py`는 이제 같은 source-uri helper를 직접 재사용합니다.
- `selected_asset_uri`와 narration source surface에서 쓰이던 inline `str(...).strip()` 중복을 같은 기준으로 모았습니다.

## 왜 이 작업을 했는가

- preview surface와 TTS approval/runtime read-path가 같은 URI trim 규칙을 파일별 helper나 inline 코드로 각각 들고 있으면, 다음 cleanup에서 `selected_asset_uri` 해석 기준이 다시 갈라질 위험이 있습니다.
- 지금 공통 helper로 묶어 두면 source-uri canonicalization truth를 더 직접 공유하게 됩니다.

## 변경 범위

- 제품 동작 변경 없음
- canonical source-uri helper 공통화만 수행

## 검증

- exact verification
  - `py -m pytest tests/test_api.py -q -k "test_recommendation_response_normalization_trims_payload_selected_asset_uri" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_preview_renderer_trims_tts_narration_source_uri_surface" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_review_snapshot_api_rejects_tts_approval_without_selected_asset_uri" -vv`
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
