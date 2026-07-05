# VideoBox 세션 컨텍스트

작성일:

- 2026-07-05

주제:

- subtitle render ignore stale non-list track clips closeout

## 1. 이번 turn에서 실제로 끝낸 것

- `output prompt`, `preview`, `CapCut export` 다음 인접 output consumer인 `subtitle render`에서도 stale non-list `tracks[].clips` 경계 1개를 확인하고 닫았습니다
- exact regression 1개로 RED를 먼저 확인한 뒤, subtitle render의 timeline segment ordering read-path가 non-list `clips`를 subtitle segment source처럼 순회하지 않도록 최소 수정만 넣었습니다
- focused verification은 같은 subtitle/output family의 인접 테스트만 다시 돌려 이번 수정이 기존 approved subtitle output 경계를 깨지 않는지 확인했습니다

## 2. 이번 turn의 핵심 판단

- 이번 문제는 표시 차이가 아니라, subtitle render 시작 시 timeline segment ordering helper가 문자열 clip container를 dict처럼 읽다가 실제 예외를 낼 수 있는 runtime gap이었습니다
- 최근 slice들이 output prompt, preview, export에서 같은 stale track shape를 이미 막았기 때문에, 다음 가장 가까운 output consumer인 subtitle render를 같은 기준으로 맞추는 것이 가장 자연스러운 다음 exact regression이라고 판단했습니다
- `_segments_for_timeline(...)`는 다른 read-path에도 쓰이지만, 이번 turn은 subtitle render exact regression 1개만으로 시작했고 수정도 그 공통 helper의 stale track/clip filtering 한 점으로만 제한했습니다

## 3. 이번 turn의 변경 범위

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
  - `_segments_for_timeline(...)`가 non-dict track, non-list `clips`, non-dict clip을 건너뛰도록 수정
- `tests/test_preview_export.py`
  - `test_start_subtitle_render_ignores_stale_non_list_track_clips` 추가
- SSOT 문서 업데이트
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`

## 4. 이번 turn의 verification

- exact regression
  - `py -m pytest tests/test_preview_export.py -q -k "test_start_subtitle_render_ignores_stale_non_list_track_clips" -vv`
  - RED `1 failed` 확인 후 GREEN `1 passed`
- focused verification
  - `py -m pytest tests/test_preview_export.py -q -k "test_start_subtitle_render_ignores_stale_non_list_track_clips or test_start_subtitle_render_uses_only_segments_from_the_approved_timeline or test_start_preview_render_marks_job_failed_when_renderer_errors" -vv`
  - `3 passed`
- broader verification
  - 실행하지 않음

## 5. 쉽게 말한 현재 개발상황

- 이제 subtitle도 이상한 clip 컨테이너를 정상 clip 목록처럼 읽다가 깨지지 않습니다
- output prompt, preview, export, subtitle이 같은 stale track 입력을 더 비슷한 기준으로 무시하게 됐습니다

## 6. 다음 세션 첫 시작점

1. 장기 우선순위 queue는 그대로 유지합니다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 가까운 exact regression 1개만 고릅니다
3. 그 경계는 이번처럼 output consumer parity 잔여 차이나 preflight contract의 작은 read-path 차이부터 우선 닫습니다

## 7. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
