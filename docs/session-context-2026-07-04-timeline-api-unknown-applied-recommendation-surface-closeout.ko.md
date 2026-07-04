# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- timeline API unknown applied recommendation surface closeout

## 1. 이번 turn에서 실제로 끝낸 것

- 장기 우선순위 queue를 유지한 상태에서 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 다시 골랐다
- 선택한 경계는 timeline API read path가 unknown stale recommendation entry를 `applied_recommendations` surface에 그대로 남기는 문제였다
- timeline read path가 canonical supported recommendation type만 applied surface에 남기도록 최소 수정으로 닫았다

## 2. 이번 turn의 핵심 판단

- pending-like legacy recommendation이 applied bucket에 잘못 들어온 경우는 이미 blocked truth와 surface 정리 계약이 닫혀 있었지만, recommendation type 자체가 unknown인 stale entry는 여전히 applied surface에 그대로 남을 수 있었다
- 이 경계는 blocker 판정 자체를 다시 넓히는 작업이 아니라, user-facing timeline read surface를 canonical supported recommendation type 기준으로 clean하게 유지하는 바로 인접 경계였다
- broader보다 exact regression + output-gating focused lane이 이번 범위에는 더 직접적인 증거였다

## 3. strict TDD 증거

- RED
  - `py -m pytest tests/test_api.py -q -k "test_timeline_api_filters_unknown_type_entry_misbucketed_into_applied_recommendations"`
  - 결과: `1 failed`
  - 실제 실패:
    - `payload["applied_recommendations"]`에 `legacy_overlay_pick` stale entry가 그대로 남음
- GREEN
  - `tests/test_api.py`
    - exact regression `test_timeline_api_filters_unknown_type_entry_misbucketed_into_applied_recommendations` 추가
  - `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
    - `_hydrate_timeline_review_status(...)` applied recommendation read path가 canonical supported recommendation type만 surface에 남기고, pending blocker로 재분류되는 항목은 계속 제외하도록 최소 수정
  - 같은 exact test 재실행
  - 결과: `1 passed`

## 4. 이번 turn의 verification

- exact regression
  - `1 passed`
- output-gating focused slice
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - 결과: `24 passed`
- current-focused-parallel
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - 결과:
    - backend output-gating `24 passed`
    - backend preflight `57 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline API applied-surface filtering 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

## 5. 현재 기준 상태

- 브랜치:
  - `codex/tts-approved-runtime`
- 이번 turn의 코드 변경 범위
  - `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
  - `tests/test_api.py`
- 이번 turn의 문서 변경 범위
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- closeout 문서 추가
  - `docs/session-context-2026-07-04-timeline-api-unknown-applied-recommendation-surface-closeout.ko.md`

## 6. 쉽게 말한 현재 개발상황

- 지금은 stale recommendation 흔적 때문에 timeline read surface와 blocker truth가 서로 다른 기준으로 보이지 않도록 작은 경계들을 하나씩 닫는 단계다
- 이번 수정으로 system이 이해하지 못하는 unknown recommendation type이 applied bucket에 남아 있어도, timeline API에서 실제 승인된 canonical recommendation처럼 계속 노출되지는 않게 됐다

## 7. 다음 세션 첫 시작점

1. timeline API unknown applied recommendation surface 경계는 현재 기준 닫힌 것으로 본다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개를 고른다
3. exact failing test 1개로만 다시 시작한다

## 8. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
