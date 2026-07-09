# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- capcut export mixed-case tts recommendation type closeout

## 1. 이번 turn에서 실제로 끝낸 것

- 장기 우선순위 queue를 유지한 상태에서 `TTS approval/output`에 가장 가까운 가장 작은 출력 경계 1개만 다시 골랐다
- 선택한 경계는 CapCut export adapter가 mixed-case `TTS_REPLACEMENT` recommendation type을 승인된 narration override로 인식하지 못하는 문제였다
- CapCut voiceover track도 preview renderer와 같은 canonical lowercase type 기준을 쓰도록 최소 수정으로 닫았다

## 2. 이번 turn의 핵심 판단

- preview renderer는 이미 mixed-case TTS recommendation type 경계를 닫았지만, CapCut export adapter는 여전히 raw `strip()` 비교를 써 같은 family 안에서 read truth가 갈라질 수 있었다
- timeline builder나 local pipeline 쪽보다 CapCut export adapter가 현재 queue의 `TTS approval/output`에 더 가깝고, exact regression 1개로 좁게 닫을 수 있는 가장 작은 경계였다
- helper backend output-gating override는 이번 test 이름을 lane 수집 범위에 태우지 못했기 때문에, direct focused pytest와 `current-focused-parallel`이 더 직접적인 검증 근거였다

## 3. strict TDD 증거

- RED
  - `py -m pytest tests/test_preview_export.py -q -k "test_capcut_export_adapter_matches_mixed_case_tts_recommendation_type_for_segment_level_narration_sources"`
  - 결과: `1 failed`
  - 실제 실패:
    - voiceover 첫 segment `source_uri`가 generated TTS asset이 아니라 original narration source로 남음
- GREEN
  - `tests/test_preview_export.py`
    - exact regression `test_capcut_export_adapter_matches_mixed_case_tts_recommendation_type_for_segment_level_narration_sources` 추가
  - `packages/capcut-export/src/videobox_capcut_export/adapter.py`
    - recommendation type `strip().lower()` helper를 추가하고 narration override segment 계산에 재사용
  - 같은 exact test 재실행
  - 결과: `1 passed`

## 4. 이번 turn의 verification

- exact regression
  - `1 passed`
- focused adjacency slice
  - `py -m pytest tests/test_preview_export.py -q -k "test_capcut_export_adapter_matches_mixed_case_tts_recommendation_type_for_segment_level_narration_sources or test_capcut_export_adapter_matches_trimmed_tts_recommendation_type_for_segment_level_narration_sources or test_capcut_export_adapter_treats_string_false_tts_review_required_as_false_for_segment_level_narration_sources"`
  - 결과: `3 passed`
- broader fast-path verification
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - 결과:
    - backend output-gating `24 passed`
    - backend preflight `57 passed`
    - frontend preflight `25 passed`
- helper override note
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "matches_mixed_case_tts_recommendation_type_for_segment_level_narration_sources or matches_trimmed_tts_recommendation_type_for_segment_level_narration_sources or string_false_tts_review_required_as_false_for_segment_level_narration_sources"`
  - 결과: `279 deselected`
  - 판단:
    - 이번 경계는 helper backend lane의 기본 수집 집합 밖에 있어 direct file-focused pytest가 더 정확했다
- broader verification
  - 실행하지 않음
  - 판단:
    - CapCut export adapter의 mixed-case type canonicalization 한 점에 국한된 수정이라 exact + adjacency + current-focused-parallel evidence가 충분하다
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
  - `docs/session-context-2026-07-04-capcut-export-mixed-case-tts-recommendation-type-closeout.ko.md`

## 6. 쉽게 말한 현재 개발상황

- 지금은 승인된 TTS 교체가 미리보기뿐 아니라 CapCut export에서도 같은 결과로 나가도록 출력 경계를 하나씩 맞추는 단계다
- 이번 수정으로 recommendation type이 예전 데이터처럼 대문자나 섞인 형태여도, CapCut export가 선택된 TTS 음성을 놓치지 않게 됐다

## 7. 다음 세션 첫 시작점

1. CapCut export mixed-case TTS recommendation type 경계는 현재 기준 닫힌 것으로 본다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개를 고른다
3. exact failing test 1개로만 다시 시작한다

## 8. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
