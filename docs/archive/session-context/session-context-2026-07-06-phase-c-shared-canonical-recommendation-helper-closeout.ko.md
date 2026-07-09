# 2026-07-06 Phase C shared canonical recommendation helper closeout

## 이번 턴에서 한 일

- `packages/core-engine/src/videobox_core_engine/canonical_recommendation.py`를 추가해 shared `canonical_recommendation_type`과 `VALID_CANONICAL_RECOMMENDATION_TYPES`를 만들었습니다.
- `prompt_pending_recommendation.py`, `preview_renderer.py`, `review_action_mutations.py`, `timeline_builder.py`, `local_pipeline.py`는 이제 같은 recommendation helper를 직접 재사용합니다.

## 왜 이 작업을 했는가

- mixed-case recommendation type과 valid recommendation set 경계는 이미 테스트로 닫혀 있었지만, 구현은 여러 파일이 같은 `trim/lower` 함수와 같은 set 상수를 각각 따로 들고 있었습니다.
- 지금 공통 helper로 묶어 두면 prompt/output/runtime/timeline/TTS approval이 같은 recommendation truth를 더 직접 공유하게 됩니다.

## 변경 범위

- 제품 동작 변경 없음
- canonical recommendation helper 공통화만 수행

## 검증

- exact verification
  - `py -m pytest tests/test_api.py -q -k "test_output_operator_copy_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_ignores_unknown_pending_recommendation_in_prompt_count" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_preview_renderer_matches_mixed_case_narration_track_type_for_narration_source" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_apply_approved_tts_recommendation_matches_mixed_case_narration_track_type or test_segments_for_timeline_ignores_unknown_track_type" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_review_snapshot_api_approve_tts_replacement_surfaces_approved_decision_state_in_read_paths" -vv`
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
