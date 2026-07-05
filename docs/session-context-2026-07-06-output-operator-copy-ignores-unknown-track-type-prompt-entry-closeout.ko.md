# VideoBox 세션 컨텍스트

작성일:

- 2026-07-06

주제:

- output operator copy ignores unknown track type prompt entry closeout

## 1. 이번 turn에서 실제로 끝낸 것

- output operator copy prompt가 supported set 밖의 stale unknown `track_type`를 valid runtime track summary처럼 노출하던 경계 1개를 닫았습니다
- exact regression 1개로 RED를 먼저 확인한 뒤, prompt track summary가 supported runtime track type만 읽도록 최소 수정만 넣었습니다
- focused verification은 output-gating과 인접 preflight 범위까지만 다시 돌려 prompt 정리가 주변 계약을 깨지 않는지 확인했습니다

## 2. 이번 turn의 핵심 판단

- 이번 경계는 직전 subtitle read path의 unknown-track hardening과 바로 맞닿은 output prompt 한 점이어서, Phase A에서 가장 가까운 exact regression이라고 판단했습니다
- `_build_prompt(...)`는 `track_type`이 비어 있지 않으면 모두 summary에 올리고 있었기 때문에, legacy unknown track도 operator-facing runtime summary를 흔들 수 있었습니다
- broader 재검증보다 exact RED/GREEN과 focused evidence가 이번 수정의 직접 증거라고 판단했습니다

## 3. 이번 turn의 변경 범위

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`
  - prompt track summary가 supported runtime track type `narration/broll/bgm`만 읽도록 수정
- `tests/test_api.py`
  - `test_output_operator_copy_builder_ignores_unknown_track_type_in_prompt` 추가
- SSOT 문서 업데이트
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`

## 4. 이번 turn의 verification

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_output_operator_copy_builder_ignores_unknown_track_type_in_prompt" -vv`
  - RED `1 failed` 확인 후 GREEN `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "<output-gating pattern>"` -> `24 passed`
  - `py -m pytest tests/test_api.py -q -k "<preflight-backend pattern>"` -> `59 passed`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-frontend` -> exit code `0` 확인
- broader verification
  - 실행하지 않음

## 5. 쉽게 말한 현재 개발상황

- 이번에는 preview/export 안내문이 이상한 legacy track을 진짜 runtime track처럼 요약하지 않게 막았습니다
- 이제 operator-facing track summary도 프로젝트가 실제로 쓰는 track 종류만 기준으로 보여줍니다

## 6. 다음 세션 첫 시작점

1. 장기 queue는 그대로 유지합니다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 가까운 exact regression 1개만 고릅니다
3. 여전히 페이즈 A 안정화 단계이며, 전체 QA/시스템 검증/정리 페이즈로는 아직 넘어가지 않습니다

## 7. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
