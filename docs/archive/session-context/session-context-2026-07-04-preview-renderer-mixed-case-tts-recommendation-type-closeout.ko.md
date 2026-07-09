# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- preview renderer mixed-case tts recommendation type closeout

## 1. 이번 turn에서 실제로 끝낸 것

- 장기 우선순위 queue를 유지한 상태에서 `TTS approval/output`에 가장 가까운 preview renderer의 mixed-case recommendation type 경계 1개만 다시 골랐다
- 선택한 경계는 applied `TTS_REPLACEMENT`가 mixed-case로 저장돼 있을 때 preview HTML narration source가 original source로 되돌아가는 문제였다
- preview renderer가 mixed-case recommendation type도 canonical TTS type으로 읽도록 최소 수정으로 닫았다

## 2. 이번 turn의 핵심 판단

- 직전 closeout들로 approve/read path와 trimmed TTS type 경계는 닫혔지만, preview renderer는 여전히 raw `strip()` 비교만 써서 mixed-case `TTS_REPLACEMENT`를 승인된 narration override로 인식하지 못하고 있었다
- 이 경계는 `TTS approval/output` 우선순위 안에서 가장 작은 exact regression이었고, preview HTML source 문자열 하나로 바로 RED/GREEN을 확인할 수 있었다
- broader보다 exact + output-focused + current-focused-parallel evidence가 이번 범위에는 더 직접적이었다

## 3. strict TDD 증거

- RED
  - `py -m pytest tests/test_api.py -q -k "test_preview_renderer_matches_mixed_case_tts_recommendation_type_for_narration_source"`
  - 결과: `1 failed`
  - 실제 실패:
    - preview HTML이 selected TTS source가 아니라 original narration source를 계속 노출했다
- GREEN
  - `tests/test_api.py`
    - exact regression `test_preview_renderer_matches_mixed_case_tts_recommendation_type_for_narration_source` 추가
  - `packages/core-engine/src/videobox_core_engine/preview_renderer.py`
    - recommendation type canonicalization helper를 추가하고 TTS applied-segment 판정이 `strip().lower()` 기준을 쓰도록 수정
  - 같은 exact test 재실행
  - 결과: `1 passed`

## 4. 이번 turn의 verification

- exact regression
  - `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_preview_renderer_matches_mixed_case_tts_recommendation_type_for_narration_source or test_preview_renderer_matches_trimmed_tts_recommendation_type_for_narration_source or test_preview_renderer_treats_string_false_tts_recommendation_review_required_as_false"`
  - 결과: `3 passed`
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "matches_mixed_case_tts_recommendation_type_for_narration_source or matches_trimmed_tts_recommendation_type_for_narration_source or string_false_tts_recommendation_review_required_as_false"`
  - 결과: `3 passed`
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - 결과:
    - backend output-gating `24 passed`
    - backend preflight `57 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview renderer mixed-case TTS type canonicalization 한 점 수정이라 exact + focused evidence가 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

## 5. 현재 기준 상태

- 브랜치:
  - `codex/tts-approved-runtime`
- 이번 turn의 코드 변경 범위
  - `tests/test_api.py`
  - `packages/core-engine/src/videobox_core_engine/preview_renderer.py`
- 이번 turn의 문서 변경 범위
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- closeout 문서 추가
  - `docs/session-context-2026-07-04-preview-renderer-mixed-case-tts-recommendation-type-closeout.ko.md`

## 6. 쉽게 말한 현재 개발상황

- 이제 TTS 추천 타입이 대문자 섞인 형태로 남아 있어도 preview 화면에서 원본 목소리로 되돌아가지 않는다
- preview가 approved TTS replacement를 더 일관되게 따라가도록 맞춘 상태다

## 7. 다음 세션 첫 시작점

1. preview renderer mixed-case TTS recommendation type 경계는 현재 기준 닫힌 것으로 본다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개를 고른다
3. exact failing test 1개로만 다시 시작한다

## 8. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
