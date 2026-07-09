# VideoBox 세션 컨텍스트

작성일:

- 2026-07-05

주제:

- preview renderer ignore stale non-list track clips closeout

## 1. 이번 turn에서 실제로 끝낸 것

- 코드리뷰와 갭검증으로 `output_operator_copy`와 `preview_renderer`가 stale `tracks[].clips`를 다르게 처리하던 경계 1개를 확인했습니다
- exact regression 1개로 RED를 먼저 확인한 뒤, preview renderer가 non-list `clips`를 track summary와 narration source surface에서 건너뛰도록 최소 수정만 넣었습니다
- focused verification은 `output-gating`까지만 다시 돌려 이번 수정이 출력 경계를 깨지 않는지 확인했습니다

## 2. 이번 turn의 핵심 판단

- 이번 문제는 단순 표시 차이가 아니라, preview HTML 생성 중 문자열 clip container를 dict처럼 읽다가 실제 예외를 낼 수 있는 runtime gap이었습니다
- 이미 output operator copy prompt 쪽은 같은 stale shape를 걸러내고 있었기 때문에, preview visible surface를 같은 기준으로 맞추는 것이 가장 작은 역방향 동작검증 대응이었습니다
- broader 재검증까지 바로 넓히는 것보다, 이번 turn은 exact RED/GREEN과 output-gating focused evidence가 더 직접적이라고 판단했습니다

## 3. 이번 turn의 변경 범위

- `packages/core-engine/src/videobox_core_engine/preview_renderer.py`
  - non-dict track, empty canonical `track_type`, non-list `clips`를 건너뛰는 promptable track filter 추가
  - preview payload `clips` surface와 HTML track summary/narration source loop가 같은 filtered track input을 사용하도록 정리
- `tests/test_api.py`
  - `test_preview_renderer_ignores_non_list_track_clips_in_track_summary_surfaces` 추가
- SSOT 문서 업데이트
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`

## 4. 이번 turn의 verification

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_preview_renderer_ignores_non_list_track_clips_in_track_summary_surfaces" -vv`
  - RED `1 failed` 확인 후 GREEN `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - `24 passed, 325 deselected`
- broader verification
  - 실행하지 않음

## 5. 쉽게 말한 현재 개발상황

- preview가 이상한 clip 컨테이너를 정상 clip 목록처럼 읽다가 깨질 수 있던 부분을 막았습니다
- 이제 preview도 output prompt와 비슷하게, 정상 track 입력만 요약하고 나머지는 조용히 무시합니다

## 6. 다음 세션 첫 시작점

1. 장기 우선순위 queue는 그대로 유지합니다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 가까운 exact regression 1개만 고릅니다
3. 그 경계는 코드리뷰/갭검증에서 확인된 인접 visible surface 또는 consumer surface 차이부터 우선 닫습니다

## 7. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
