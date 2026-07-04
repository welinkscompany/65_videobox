# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- partial regeneration runtime mixed-case source review flag carry-forward closeout

## 1. 이번 turn에서 실제로 끝낸 것

- partial regeneration runtime이 source timeline의 mixed-case stale `review_flags.code` blocker를 놓치던 경계 1개를 닫았습니다
- exact regression 1개로 RED를 먼저 확인한 뒤, runtime carry-forward와 dedupe key만 canonical lowercase review flag code 기준으로 맞췄습니다
- 구현 계획서와 상태 문서에도 이번 계약과 검증 결과를 최소 범위로 반영했습니다

## 2. 이번 turn의 핵심 판단

- 이번 slice는 `preflight contract`와 바로 맞닿아 있지만, 실제 누수 지점은 API prediction이 아니라 runtime result timeline carry-forward였습니다
- helper lane을 억지로 넓게 돌리는 것보다, 이 경계를 직접 때리는 exact test와 인접 family exact를 다시 돌리는 편이 더 짧고 정확했습니다
- 수정 범위는 `local_pipeline.py`의 source review flag filter와 dedupe key로 제한해 persistence나 provider trace 규칙에는 손대지 않았습니다

## 3. 이번 turn의 변경 범위

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
  - source review-flag carry-forward가 mixed-case stale code도 canonical lowercase 기준으로 복원하도록 수정
  - source review-flag dedupe key도 같은 canonical code 기준으로 통일
- `tests/test_api.py`
  - exact regression 추가
- `docs/implementation-plan.ko.md`
  - partial regeneration runtime mixed-case source review-flag carry-forward 계약 1줄 추가
- `docs/development-status-2026-06-29.ko.md`
  - closeout section 100 추가

## 4. 이번 turn의 verification

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_partial_regeneration_result_marks_review_status_blocked_when_preserved_source_review_flag_has_mixed_case_valid_code"`
  - RED: `1 failed`
  - GREEN: `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "preserved_source_review_flag or deduplicates_preserved_source_review_flags_for_partial_regeneration_candidate"`
  - 결과: `3 passed`

## 5. 쉽게 말한 현재 개발상황

- rerun 전에 blocker를 알아보는 preflight는 이미 mixed-case review flag를 막고 있었지만, 실제 rerun 결과 timeline은 같은 blocker를 다시 실어오지 못하고 있었습니다
- 이번 수정으로 이제 source에 남아 있는 mixed-case stale review flag도 rerun 결과에서 다시 `blocked`로 유지됩니다

## 6. 다음 세션 첫 시작점

1. 장기 우선순위 queue는 그대로 유지합니다
2. 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 exact regression 1개만 고릅니다
3. 후보는 `local_pipeline.py`의 남은 raw stale comparison 또는 동일 가족의 returned surface canonicalization부터 다시 좁힙니다

## 7. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
