# VideoBox 세션 컨텍스트

작성일:

- 2026-07-06

주제:

- preview renderer trims TTS narration source uri surface closeout

## 1. 이번 turn에서 실제로 끝낸 것

- 장기 우선순위 queue를 유지한 채, `TTS approval/output` 안에서 가장 작은 남은 경계 1개만 다시 골랐다
- 선택한 경계는 preview renderer가 approved TTS narration source URI를 raw 그대로 보여 주는 문제였다
- whitespace가 섞인 stale narration asset uri도 canonical trimmed uri로 preview에 보이도록 최소 수정으로 닫았다

## 2. 이번 turn의 핵심 판단

- 이 문제는 hidden persistence가 아니라 실제 preview visible surface 쪽의 작은 비대칭이었다
- approved TTS source 자체는 맞아도 preview HTML의 narration source 표면이 raw stale URI를 그대로 보여 주면 operator가 오해할 수 있었다
- 범위가 좁아서 exact regression 1개와 `output-gating` focused lane만으로 증거를 닫는 것이 맞았다

## 3. strict TDD 증거

- RED
  - `py -m pytest tests/test_api.py -q -k "test_preview_renderer_trims_tts_narration_source_uri_surface" -vv`
  - 결과: `1 failed`
  - 실제 실패:
    - preview HTML의 narration source surface가 `seg_001:  local://...tts_selected.wav `처럼 padded/raw URI를 노출했다
- GREEN
  - `tests/test_api.py`
    - exact regression `test_preview_renderer_trims_tts_narration_source_uri_surface` 추가
  - `packages/core-engine/src/videobox_core_engine/preview_renderer.py`
    - `_effective_narration_source_uri(...)`가 narration source URI도 trim 기준으로 정리하도록 최소 수정
  - 같은 exact test 재실행
  - 결과: `1 passed`

## 4. 이번 turn의 verification

- exact regression
  - `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - 결과: `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview renderer의 TTS narration source URI surface 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
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
  - `docs/session-context-2026-07-06-preview-renderer-trims-tts-narration-source-uri-surface-closeout.ko.md`

## 6. 쉽게 말한 현재 개발상황

- 지금은 승인된 TTS 결과가 실제로 맞게 붙어 있어도, 화면에 보이는 URI 문자열까지 같은 기준으로 깨끗하게 맞추는 단계다
- 이번 수정으로 preview 화면에 보이는 narration source URI도 공백 섞인 오래된 모양이 아니라 정리된 URI 기준으로 보이게 됐다

## 7. 다음 세션 첫 시작점

1. preview renderer TTS narration source URI surface 경계는 현재 기준 닫힌 것으로 본다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개를 고른다
3. exact failing test 1개로만 다시 시작한다

## 8. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
