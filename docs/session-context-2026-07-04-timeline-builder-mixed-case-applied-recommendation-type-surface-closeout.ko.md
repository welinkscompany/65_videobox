# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- timeline builder mixed-case applied recommendation type surface closeout

## 1. 이번 turn에서 실제로 끝낸 것

- `TTS approval/output`에 가장 가까운 timeline builder applied recommendation type surface 경계 1개를 닫았다
- approved TTS recommendation이 mixed-case stale type으로 들어와도 builder output surface에서는 canonical lowercase type을 유지하도록 맞췄다
- exact regression 1개와 TTS/output 인접 focused verification만 다시 돌려 현재 slice를 닫았다

## 2. 이번 turn의 핵심 판단

- 이번 turn의 후보는 `review/output gating`, `TTS approval/output`, `preflight contract`였다
- 그중 가장 작은 실제 빈칸은 timeline builder applied recommendation surface의 mixed-case `recommendation_type` 누수였다
- builder 내부 분기 자체는 canonical type 기준으로 이미 동작하고 있었지만, surface는 raw stale casing을 그대로 남기고 있어서 approved TTS read-path truth와 output surface가 어긋나는 작은 비일관성이 남아 있었다

## 3. 이번 turn의 변경 범위

- `packages/core-engine/src/videobox_core_engine/timeline_builder.py`
  - `_recommendation_payload(...)`의 `recommendation_type` canonicalization 추가
- `tests/test_api.py`
  - exact regression 추가
    - `test_timeline_builder_canonicalizes_mixed_case_applied_recommendation_type_surface`
- SSOT/closeout 문서 업데이트
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
  - 이 closeout 문서

## 4. 이번 turn의 verification

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_timeline_builder_canonicalizes_mixed_case_applied_recommendation_type_surface" -vv`
  - RED: `1 failed`
  - GREEN: `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_timeline_builder_canonicalizes_mixed_case_applied_recommendation_type_surface or test_timeline_builder_treats_string_false_recommendation_review_required_as_false or test_preview_renderer_matches_mixed_case_tts_recommendation_type_for_narration_source or test_output_operator_copy_builder_canonicalizes_mixed_case_review_status_in_prompt" -vv`
  - 결과: `4 passed`

## 5. 쉽게 말한 현재 개발상황

- approved TTS recommendation은 내부적으로는 이미 제대로 적용되고 있었지만, timeline builder가 바깥으로 돌려주는 recommendation type 값은 예전 `" TTS_REPLACEMENT "` 같은 형식을 그대로 남기고 있었습니다
- 이번에 output surface도 같은 기준으로 맞춰서, builder가 내보내는 recommendation type도 다른 read-path들과 같은 lowercase 형태를 유지하게 됐습니다

## 6. 다음 세션 첫 시작점

1. 이번 slice는 timeline builder applied recommendation type surface의 mixed-case stale 경계까지 닫은 것으로 본다
2. 다음 작업은 다시 `docs/implementation-plan.ko.md`의 `## 13. 다음 실제 작업` 기준으로 장기 queue 후보를 2~3개로 좁힌다
3. 그중 `review/output gating`, `TTS approval/output`, `preflight contract`에 가장 가까운 exact regression 1개를 다시 골라 strict TDD로 시작한다

## 7. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
