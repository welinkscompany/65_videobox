# VideoBox 세션 컨텍스트

작성일:

- 2026-07-06

주제:

- capcut export ignores unknown track type closeout

## 1. 이번 turn에서 실제로 끝낸 것

- CapCut export adapter가 supported set 밖의 stale unknown `track_type`를 export payload `tracks` surface에 valid runtime track처럼 남기던 경계 1개를 닫았습니다
- exact regression 1개로 RED를 먼저 확인한 뒤, CapCut export adapter도 supported runtime track type `narration/broll/bgm`만 읽도록 최소 수정만 넣었습니다
- focused verification은 export consumer family와 frontend preflight까지만 다시 돌려, 이번 export payload 정리가 주변 계약을 깨지 않는지 확인했습니다

## 2. 이번 turn의 핵심 판단

- 이번 경계는 직전 subtitle render, output operator copy, preview renderer의 unknown-track hardening과 바로 이어지는 export consumer 면이라서, Phase A에서 가장 가까운 exact regression이라고 판단했습니다
- `_promptable_tracks(...)`는 empty `track_type`만 걸러서 unknown legacy track도 export payload `tracks` surface에 남길 수 있었기 때문에, manifest가 실제 runtime track 종류만 기준으로 정렬되게 맞추는 편이 논리적으로 맞았습니다
- broader 재검증보다 exact RED/GREEN과 export 인접 focused evidence가 이번 수정의 직접 증거라고 판단했습니다

## 3. 이번 turn의 변경 범위

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`
  - export payload / track read-path가 supported runtime track type만 읽도록 수정
- `tests/test_preview_export.py`
  - `test_capcut_export_adapter_ignores_unknown_track_type_in_export_payload` 추가
- SSOT 문서 업데이트
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`

## 4. 이번 turn의 verification

- exact regression
  - `py -m pytest tests/test_preview_export.py -q -k "test_capcut_export_adapter_ignores_unknown_track_type_in_export_payload" -vv`
  - RED `1 failed` 확인 후 GREEN `1 passed`
- focused verification
  - `py -m pytest tests/test_preview_export.py -q -k "test_capcut_export_adapter_ignores_unknown_track_type_in_export_payload or test_capcut_export_adapter_builds_structured_track_manifest_from_timeline_schema or test_capcut_export_adapter_matches_mixed_case_narration_track_type_for_voiceover_track or test_capcut_export_adapter_ignores_non_list_track_clips_in_voiceover_surface" -vv`
  - 결과 `4 passed`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-frontend`
  - 결과 `25 passed`
- broader verification
  - 실행하지 않음

## 5. 쉽게 말한 현재 개발상황

- 이번에는 export manifest가 이상한 legacy track을 진짜 runtime track처럼 싣지 않게 막았습니다
- 이제 subtitle, output prompt, preview, export가 모두 실제로 쓰는 track 종류만 기준으로 더 비슷하게 움직입니다

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
