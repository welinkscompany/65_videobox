# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- capcut export mixed-case narration track type closeout

## 1. 이번 turn에서 실제로 끝낸 것

- 장기 queue를 유지한 상태에서 `TTS approval/output`에 가장 가까운 CapCut export voiceover track surface 경계 1개만 다시 골랐다
- legacy `" NARRATION "` 같은 mixed-case stale `track_type`를 가진 narration track도 CapCut export가 voiceover track으로 읽도록 최소 수정으로 닫았다
- exact regression 1개만 RED로 확인하고, 같은 test를 GREEN으로 먼저 되돌린 뒤 인접 focused verification까지만 확인했다

## 2. 이번 turn의 핵심 판단

- 이 경계는 preview/export family 안에서 실제 export payload 생성에 직접 영향을 주는 작은 read-path 누수였다
- `track_type` raw 비교는 stale persisted timeline shape 하나만으로 voiceover track 전체를 잃게 만들 수 있어서, 현재 queue에서 작고 위험 대비 효율이 높은 수정이었다
- 서브에이전트나 추가 리뷰보다 메인 에이전트가 직접 exact TDD로 닫는 편이 더 짧고 검증 가능했다

## 3. strict TDD 증거

- RED
  - `py -m pytest tests/test_preview_export.py -q -k "test_capcut_export_adapter_matches_mixed_case_narration_track_type_for_voiceover_track" -vv`
  - 결과: `1 failed`
  - 실제 실패:
    - `payload["capcut_tracks"]`에서 `track_name == "voiceover"`를 찾지 못했다
- GREEN
  - `tests/test_preview_export.py`
    - exact regression `test_capcut_export_adapter_matches_mixed_case_narration_track_type_for_voiceover_track` 추가
  - `packages/capcut-export/src/videobox_capcut_export/adapter.py`
    - `_canonical_track_type(...)` helper 추가
    - narration track 판정이 `strip().lower()` 기준을 쓰도록 수정
  - 같은 exact test 재실행
  - 결과: `1 passed`

## 4. 이번 turn의 verification

- exact regression
  - `1 passed`
- focused verification
  - `py -m pytest tests/test_preview_export.py -q -k "test_capcut_export_adapter_builds_structured_track_manifest_from_timeline_schema or test_capcut_export_adapter_uses_segment_level_narration_sources_for_approved_tts_replacement or test_capcut_export_adapter_matches_mixed_case_tts_recommendation_type_for_segment_level_narration_sources or test_capcut_export_adapter_matches_mixed_case_narration_track_type_for_voiceover_track" -vv`
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - CapCut export narration `track_type` canonicalization 한 점 수정이라 exact + 인접 focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

## 5. 현재 기준 상태

- 브랜치:
  - `codex/tts-approved-runtime`
- 이번 turn의 코드 변경 범위
  - `packages/capcut-export/src/videobox_capcut_export/adapter.py`
  - `tests/test_preview_export.py`
- 이번 turn의 문서 변경 범위
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- closeout 문서 추가
  - `docs/session-context-2026-07-04-capcut-export-mixed-case-narration-track-type-closeout.ko.md`

## 6. 쉽게 말한 현재 개발상황

- export를 만들 때 narration 트랙 이름이 예전 데이터처럼 대문자나 공백이 섞여 있으면, voiceover 트랙이 아예 빠질 수 있었다
- 이번 수정으로 CapCut export도 그 값을 정리해서 읽기 때문에, 승인된 narration/TTS 출력 트랙을 놓치지 않게 됐다

## 7. 다음 세션 첫 시작점

1. CapCut export mixed-case narration track type 경계는 현재 기준 닫힌 것으로 본다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개를 고른다
3. exact failing test 1개로만 다시 시작한다

## 8. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
