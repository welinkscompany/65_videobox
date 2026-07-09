# VideoBox 세션 컨텍스트

작성일:

- 2026-07-05

주제:

- output operator copy ignore stale non-list track clips closeout

## 1. 이번 turn에서 실제로 끝낸 것

- output operator copy prompt가 stale non-list `tracks[].clips` 값을 실제 clip count처럼 안내문에 섞어 넣던 경계 1개를 닫았습니다
- exact regression 1개로 RED를 먼저 확인한 뒤, `clips`가 list인 track만 summary에 남기도록 최소 수정만 넣었습니다
- focused verification은 `output-gating`까지만 다시 돌려 이번 경계가 review/output gating 기준을 깨지 않는지 확인했습니다

## 2. 이번 turn의 핵심 판단

- 이번 경계는 preview/export용 operator prompt가 실제 track summary truth보다 더 넓은 junk clip container를 노출하는 문제라, `review/output gating`에 가장 가까운 작은 남은 경계로 판단했습니다
- 직전 slice들이 non-dict/minimal-dict track junk를 막았으므로, 이번에는 같은 track summary surface의 non-list `clips` junk를 맞춰 주는 편이 가장 자연스러웠습니다
- 범위를 더 넓혀 clip payload 전체 규칙을 다시 잡을 수도 있었지만, 이번 turn은 exact RED가 나온 non-list stale clip container만 막는 쪽이 더 정확했습니다

## 3. 이번 turn의 변경 범위

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`
  - track summary loop에서 `clips`가 list가 아닌 track entry를 건너뛰도록 수정
- `tests/test_api.py`
  - `test_output_operator_copy_builder_ignores_non_list_track_clips_in_prompt` 추가
- SSOT 문서 업데이트
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`

## 4. 이번 turn의 verification

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_output_operator_copy_builder_ignores_non_list_track_clips_in_prompt" -vv`
  - RED `1 failed` 확인 후 GREEN `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
    - `24 passed, 324 deselected`
- broader verification
  - 실행하지 않음

## 5. 쉽게 말한 현재 개발상황

- 이번에는 output 안내문이 문자열 같은 이상한 clip container를 진짜 clip 개수처럼 세던 부분만 작게 막았습니다
- 이제 정상 list clip만 개수로 세고, 이상한 clip 값은 조용히 건너뜁니다

## 6. 다음 세션 첫 시작점

1. 장기 queue는 그대로 유지합니다
2. 다음 작업은 다시 `docs/implementation-plan.ko.md`의 `## 13. 다음 실제 작업` 기준으로 후보를 2~3개로 좁힙니다
3. 그중 `review/output gating`, `TTS approval/output`, `preflight contract`에 가장 가까운 exact regression 1개만 골라 RED 1개로 시작합니다

## 7. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
