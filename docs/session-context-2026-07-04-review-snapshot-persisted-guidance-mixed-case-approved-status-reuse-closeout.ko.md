# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- review snapshot persisted guidance mixed-case approved status reuse closeout

## 1. 이번 turn에서 실제로 끝낸 것

- `review/output gating`에 가장 가까운 review snapshot persisted guidance 재사용 경계 1개를 닫았다
- mixed-case stale approved review status여도 persisted operator guidance를 같은 승인 상태로 보고 재사용하도록 local pipeline 비교 기준을 canonical lowercase로 맞췄다
- exact regression 1개와 review guidance 인접 focused verification만 다시 돌려 현재 slice를 닫았다

## 2. 이번 turn의 핵심 판단

- 이번 turn의 후보는 `review/output gating`, `TTS approval/output`, `preflight contract`였다
- 그중 가장 작은 실제 빈칸은 review snapshot의 persisted guidance 재사용 조건이었다
- output/read surface는 이미 review status를 canonicalize하고 있었지만, persisted guidance reuse는 raw 비교를 쓰고 있어 stale `" APPROVED "` shape면 같은 승인 상태인데도 guidance를 불필요하게 다시 만드는 비일관성이 남아 있었다

## 3. 이번 turn의 변경 범위

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
  - runtime review status canonical helper 추가
  - `get_review_snapshot(...)`의 persisted guidance reuse/save 조건 비교 수정
- `tests/test_api.py`
  - exact regression 추가
    - `test_local_pipeline_review_snapshot_reuses_persisted_guidance_for_mixed_case_approved_status`
- SSOT/closeout 문서 업데이트
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
  - 이 closeout 문서

## 4. 이번 turn의 verification

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_local_pipeline_review_snapshot_reuses_persisted_guidance_for_mixed_case_approved_status" -vv`
  - RED: `1 failed`
  - GREEN: `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_local_pipeline_review_snapshot_reuses_persisted_guidance_for_mixed_case_approved_status or test_review_snapshot_persists_operator_guidance_for_repeated_reads or test_heuristic_review_guidance_builder_canonicalizes_mixed_case_approved_review_status or test_output_operator_copy_builder_canonicalizes_mixed_case_review_status_in_prompt" -vv`
  - 결과: `4 passed`

## 5. 쉽게 말한 현재 개발상황

- review status를 보여주거나 안내문을 만드는 쪽은 이미 정리되고 있었는데, 저장된 guidance를 다시 쓰는 조건만 예전 `" APPROVED "` 같은 값을 raw 비교하고 있었습니다
- 이번에 그 비교도 같은 기준으로 맞춰서, 같은 승인 상태라면 기존 guidance를 괜히 다시 만들지 않게 됐습니다

## 6. 다음 세션 첫 시작점

1. 이번 slice는 review snapshot persisted guidance reuse의 mixed-case approved status 경계까지 닫은 것으로 본다
2. 다음 작업은 다시 `docs/implementation-plan.ko.md`의 `## 13. 다음 실제 작업` 기준으로 장기 queue 후보를 2~3개로 좁힌다
3. 그중 `review/output gating`, `TTS approval/output`, `preflight contract`에 가장 가까운 exact regression 1개를 다시 골라 strict TDD로 시작한다

## 7. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
