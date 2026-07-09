# VideoBox 세션 컨텍스트

작성일:

- 2026-07-05

주제:

- capcut export ignore stale non-list track clips closeout

## 1. 이번 turn에서 실제로 끝낸 것

- `preview`와 `output prompt` 다음 인접 consumer인 `CapCut export`에서도 stale non-list `tracks[].clips` 경계 1개를 확인하고 닫았습니다
- exact regression 1개로 RED를 먼저 확인한 뒤, export adapter가 non-list `clips`를 voiceover/audio/video segment source처럼 순회하지 않도록 최소 수정만 넣었습니다
- focused verification은 같은 export consumer family의 인접 테스트만 다시 돌려 이번 수정이 TTS approval/output 경계를 깨지 않는지 확인했습니다

## 2. 이번 turn의 핵심 판단

- 이번 문제는 표시 차이가 아니라, export manifest 생성 중 문자열 clip container를 dict처럼 읽다가 실제 예외를 낼 수 있는 runtime gap이었습니다
- 최근 slice들이 output prompt와 preview visible surface에서 같은 stale clip shape를 이미 막았기 때문에, 다음 가장 가까운 consumer인 CapCut export를 같은 기준으로 맞추는 것이 가장 자연스러운 다음 exact regression이라고 판단했습니다
- 이번 slice는 helper의 `output-gating`보다 export consumer 자체가 더 직접적이라, broader 대신 같은 `tests/test_preview_export.py` 인접 세트만 focused verification으로 사용했습니다

## 3. 이번 turn의 변경 범위

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`
  - non-dict track, empty canonical `track_type`, non-list `clips`를 건너뛰는 promptable track filter 추가
  - export consumer가 filtered track input만 사용하도록 정리
- `tests/test_preview_export.py`
  - `test_capcut_export_adapter_ignores_non_list_track_clips_in_voiceover_surface` 추가
- SSOT 문서 업데이트
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`

## 4. 이번 turn의 verification

- exact regression
  - `py -m pytest tests/test_preview_export.py -q -k "test_capcut_export_adapter_ignores_non_list_track_clips_in_voiceover_surface" -vv`
  - RED `1 failed` 확인 후 GREEN `1 passed`
- focused verification
  - `py -m pytest tests/test_preview_export.py -q -k "test_capcut_export_adapter_ignores_non_list_track_clips_in_voiceover_surface or test_capcut_export_adapter_matches_mixed_case_narration_track_type_for_voiceover_track or test_capcut_export_adapter_treats_string_false_tts_review_required_as_false_for_segment_level_narration_sources or test_capcut_export_adapter_matches_trimmed_tts_target_segment_id_for_segment_level_narration_sources or test_capcut_export_adapter_matches_trimmed_narration_clip_segment_id_for_segment_level_narration_sources" -vv`
  - `5 passed`
- broader verification
  - 실행하지 않음

## 5. 쉽게 말한 현재 개발상황

- 이제 export도 이상한 clip 컨테이너를 정상 clip 목록처럼 읽다가 깨지지 않습니다
- output prompt, preview, export가 같은 stale track 입력을 더 비슷한 기준으로 무시하게 됐습니다

## 6. 다음 세션 첫 시작점

1. 장기 우선순위 queue는 그대로 유지합니다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 가까운 exact regression 1개만 고릅니다
3. 그 경계는 이번처럼 output/preview/export 인접 consumer parity나 preflight contract의 작은 잔여 차이부터 우선 닫습니다

## 7. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
