# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- preview renderer mixed-case track type surface closeout

## 1. 이번 turn에서 실제로 끝낸 것

- 장기 queue를 유지한 상태에서 `review/output gating`과 바로 붙어 있는 preview visible track summary surface 경계 1개만 다시 골랐다
- legacy `" NARRATION "` 같은 mixed-case stale `track_type`가 preview `Track summary`에 그대로 노출되지 않도록 최소 수정으로 닫았다
- exact regression 1개만 RED로 확인하고, 같은 test를 GREEN으로 먼저 되돌린 뒤 preview 인접 focused verification까지만 확인했다

## 2. 이번 turn의 핵심 판단

- 이 경계는 실제 operator visible surface에 raw stale 값을 그대로 보여주는 작은 output surface 누수였다
- 이미 read-path 쪽에서는 canonical track type을 쓰고 있었는데 visible summary만 raw 값을 남기는 것은 같은 family 안의 작은 일관성 누수라서 먼저 닫는 것이 맞았다
- 서브에이전트보다 메인 에이전트가 직접 exact TDD로 닫는 편이 더 짧고 검증 가능했다

## 3. strict TDD 증거

- RED
  - `py -m pytest tests/test_api.py -q -k "test_preview_renderer_canonicalizes_mixed_case_track_type_surface" -vv`
  - 결과: `1 failed`
  - 실제 실패:
    - preview HTML의 `Track summary`가 `<strong> NARRATION </strong>`를 그대로 노출했다
- GREEN
  - `tests/test_api.py`
    - exact regression `test_preview_renderer_canonicalizes_mixed_case_track_type_surface` 추가
  - `packages/core-engine/src/videobox_core_engine/preview_renderer.py`
    - `Track summary` surface도 `_canonical_track_type(...)` helper를 재사용하도록 수정
  - 같은 exact test 재실행
  - 결과: `1 passed`

## 4. 이번 turn의 verification

- exact regression
  - `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_preview_renderer_matches_trimmed_tts_recommendation_type_for_narration_source or test_preview_renderer_matches_trimmed_tts_target_segment_id_for_narration_source or test_preview_renderer_matches_trimmed_narration_clip_segment_id_for_narration_source or test_preview_renderer_matches_mixed_case_tts_recommendation_type_for_narration_source or test_preview_renderer_canonicalizes_mixed_case_review_status_surface or test_preview_renderer_matches_mixed_case_narration_track_type_for_narration_source or test_preview_renderer_canonicalizes_mixed_case_track_type_surface" -vv`
  - 결과: `7 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview renderer visible `track_type` surface canonicalization 한 점 수정이라 exact + 인접 focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

## 5. 현재 기준 상태

- 브랜치:
  - `codex/tts-approved-runtime`
- 이번 turn의 코드 변경 범위
  - `packages/core-engine/src/videobox_core_engine/preview_renderer.py`
  - `tests/test_api.py`
- 이번 turn의 문서 변경 범위
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- closeout 문서 추가
  - `docs/session-context-2026-07-04-preview-renderer-mixed-case-track-type-surface-closeout.ko.md`

## 6. 쉽게 말한 현재 개발상황

- preview는 실제로 narration 트랙을 제대로 읽고 있어도, 화면에 보여주는 트랙 이름은 예전 값 그대로 보여줄 수 있었다
- 이번 수정으로 preview 화면도 그 값을 정리해서 보여주기 때문에, visible surface와 실제 read-path 기준이 더 맞게 됐다

## 7. 다음 세션 첫 시작점

1. preview renderer mixed-case track type surface 경계는 현재 기준 닫힌 것으로 본다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개를 고른다
3. exact failing test 1개로만 다시 시작한다

## 8. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
