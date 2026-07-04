# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- preview renderer string false TTS recommendation review_required closeout

## 1. 이번 turn에서 실제로 끝낸 것

- 장기 우선순위 queue를 유지한 상태에서 `review/output gating`, `TTS approval/output`, `preflight contract` 중 preview/TTS output read path에 가장 가까운 작은 경계 1개만 다시 골랐다
- 선택한 경계는 applied `tts_replacement` recommendation의 `review_required="false"`가 preview narration source 선택에서 blocker처럼 오판되는 문제였다
- preview renderer가 legacy false-like TTS recommendation fields를 canonical false로 읽도록 최소 수정으로 닫았다

## 2. 이번 turn의 핵심 판단

- response/read 및 rollback persistence 쪽 bool-ish false 경계는 이미 닫혔고, 그 다음 인접면은 실제 preview output에서 narration source를 고르는 `TTS approval/output` read path였다
- 이 경계는 새 기능 누락이 아니라 legacy recommendation payload 하나가 preview에서 selected TTS source를 잃게 만드는 상태 계약 누수였다
- broader보다는 exact regression + output-gating focused verification이 이번 범위에는 더 직접적인 증거였다

## 3. strict TDD 증거

- RED
  - `py -m pytest tests/test_api.py -q -k "test_preview_renderer_treats_string_false_tts_recommendation_review_required_as_false"`
  - 결과: `1 failed`
  - 실제 실패:
    - preview HTML이 selected TTS source 대신 original narration source를 노출
- GREEN
  - `tests/test_api.py`
    - exact regression `test_preview_renderer_treats_string_false_tts_recommendation_review_required_as_false` 추가
  - `packages/core-engine/src/videobox_core_engine/preview_renderer.py`
    - applied `tts_replacement` recommendation의 bool-ish fields를 canonical bool로 읽도록 normalization helper 적용
  - 같은 exact test 재실행
  - 결과: `1 passed`

## 4. 이번 turn의 verification

- exact regression
  - `1 passed`
- focused output-gating slice
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - 결과: `24 passed`
- current-focused-parallel
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - 결과:
    - backend output-gating `24 passed`
    - backend preflight `56 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview renderer bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
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
  - `docs/session-context-2026-07-04-preview-renderer-string-false-tts-recommendation-review-required-closeout.ko.md`

## 6. 쉽게 말한 현재 개발상황

- 지금은 legacy recommendation 흔적 하나가 실제 preview output에서 selected TTS source를 잃게 만들지 않도록 작은 경계들을 하나씩 닫는 단계다
- 이번 수정으로 applied TTS recommendation에 `"false"`가 문자열로 남아 있어도 preview가 원본 나레이션으로 되돌아가지 않게 맞췄다

## 7. 다음 세션 첫 시작점

1. preview renderer string false TTS recommendation review_required 경계는 현재 기준 닫힌 것으로 본다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개를 고른다
3. exact failing test 1개로만 다시 시작한다

## 8. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
