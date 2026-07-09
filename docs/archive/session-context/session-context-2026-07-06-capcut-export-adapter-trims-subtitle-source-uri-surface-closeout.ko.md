# VideoBox 세션 컨텍스트

작성일:

- 2026-07-06

주제:

- capcut export adapter trims subtitle source uri surface closeout

## 1. 이번 turn에서 실제로 끝낸 것

- 장기 우선순위 queue를 유지한 채, output family 안에서 가장 작은 남은 subtitle export surface 경계 1개만 다시 골랐다
- 선택한 경계는 CapCut export adapter가 subtitle `source_uri`를 raw 그대로 export payload에 넣는 문제였다
- whitespace가 섞인 stale subtitle file uri도 canonical trimmed uri로 export payload에 보이도록 최소 수정으로 닫았다

## 2. 이번 turn의 핵심 판단

- 이 문제는 approval logic이나 persistence가 아니라 실제 export payload visible surface 쪽의 작은 비대칭이었다
- narration과 B-roll은 정리됐지만 subtitle file uri는 같은 export payload 안에서 아직 raw 문자열로 남아 있었다
- 범위가 좁아서 exact regression 1개와 `output-gating` focused lane만으로 증거를 닫는 것이 맞았다

## 3. strict TDD 증거

- RED
  - `py -m pytest tests/test_preview_export.py -q -k "test_capcut_export_adapter_trims_subtitle_source_uri_surface" -vv`
  - 결과: `1 failed`
  - 실제 실패:
    - export payload의 subtitle `source_uri` surface가 ` local://...subtitle_001.srt `처럼 padded/raw URI를 노출했다
- GREEN
  - `tests/test_preview_export.py`
    - exact regression `test_capcut_export_adapter_trims_subtitle_source_uri_surface` 추가
  - `packages/capcut-export/src/videobox_capcut_export/adapter.py`
    - subtitle `source_uri`가 trim 기준으로 정리되도록 최소 수정
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
    - CapCut export adapter의 subtitle source URI surface 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
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
  - `docs/session-context-2026-07-06-capcut-export-adapter-trims-subtitle-source-uri-surface-closeout.ko.md`

## 6. 쉽게 말한 현재 개발상황

- 지금은 export로 넘길 때 보이는 문자열 surface를 같은 기준으로 정리하는 단계다
- 이번 수정으로 CapCut export payload의 subtitle `source_uri`도 공백 섞인 오래된 모양이 아니라 정리된 URI 기준으로 보이게 됐다

## 7. 다음 세션 첫 시작점

1. CapCut export adapter subtitle `source_uri` surface 경계는 현재 기준 닫힌 것으로 본다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개를 고른다
3. exact failing test 1개로만 다시 시작한다

## 8. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
