# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- review snapshot API misbucketed applied pending-like recommendation closeout

## 1. 이번 turn에서 실제로 끝낸 것

- 장기 우선순위 queue를 유지한 상태에서 `review/output gating`, `TTS approval/output`, `preflight contract` 중 review snapshot API read path에 가장 가까운 작은 경계 1개만 다시 골랐다
- 선택한 경계는 pending-like legacy recommendation이 stale하게 `applied_recommendations` bucket에 들어 있는 경우 review snapshot API가 blocker truth와 `review_status`를 잃는 문제였다
- review snapshot API가 misbucketed pending-like recommendation을 pending blocker truth로 다시 복원하고 duplicate blocker를 만들지 않도록 최소 수정으로 닫았다

## 2. 이번 turn의 핵심 판단

- direct store helper applied/pending override 경계는 이미 닫혔지만, 그 위 runtime hydration/read path는 `pending_recommendations` 컬렉션만 blocker source로 보고 있었다
- 이 경계는 새 기능 누락이 아니라 stale applied bucket 오염이 review snapshot API의 blocker truth와 review_status를 다시 approved 쪽으로 오염시키는 상태 계약 누수였다
- broader보다는 exact regression + output-gating focused verification이 이번 범위에는 더 직접적인 증거였다

## 3. strict TDD 증거

- RED
  - `py -m pytest tests/test_api.py -q -k "test_review_snapshot_api_reclassifies_pending_like_entry_misbucketed_into_applied_recommendations"`
  - 결과: `1 failed`
  - 실제 실패:
    - `review_status == "approved"`
- GREEN
  - `tests/test_api.py`
    - exact regression `test_review_snapshot_api_reclassifies_pending_like_entry_misbucketed_into_applied_recommendations` 추가
  - `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
    - timeline hydration의 blocker source에 `applied_recommendations`도 포함해 pending-like recommendation을 blocker로 복원
    - review snapshot API의 applied collection에서 runtime blocker shape를 먼저 제외해 duplicate pending blocker를 막음
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
    - review snapshot API read truth와 runtime blocker synthesis 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
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
  - `docs/session-context-2026-07-04-review-snapshot-api-misbucketed-applied-pending-like-recommendation-closeout.ko.md`

## 6. 쉽게 말한 현재 개발상황

- 지금은 stale recommendation이 잘못된 bucket에 저장돼 있어도 review snapshot API가 실제 blocker truth를 놓치지 않도록, runtime read surface를 하나씩 좁게 맞추는 단계다
- 이번 수정으로 pending-like recommendation이 applied bucket에 잘못 들어 있어도, review snapshot API는 그걸 실제 blocker로 다시 보고 `blocked` 상태와 pending recommendation 목록을 맞춰 보여주게 됐다

## 7. 다음 세션 첫 시작점

1. review snapshot API misbucketed applied pending-like recommendation 경계는 현재 기준 닫힌 것으로 본다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개를 고른다
3. exact failing test 1개로만 다시 시작한다

## 8. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
