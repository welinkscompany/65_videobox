# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- approve rollback legacy string false recommendation fields closeout

## 1. 이번 turn에서 실제로 끝낸 것

- 장기 우선순위 queue를 유지한 상태에서 `review/output gating`, `TTS approval/output`, `preflight contract` 중 review mutation rollback persistence에 가장 가까운 작은 경계 1개만 다시 골랐다
- 선택한 경계는 approve downstream failure 후 rollback이 legacy recommendation payload의 `auto_apply_allowed="false"` / `review_required="false"`를 truthy DB row로 복구하는 문제였다
- approve rollback persistence path가 legacy false-like recommendation fields를 canonical false로 복구하도록 최소 수정으로 닫았다

## 2. 이번 turn의 핵심 판단

- response/read 쪽 bool-ish false 경계는 이미 닫혔고, 그 바로 아래 인접면에는 downstream failure 시 recommendation row를 원복하는 rollback persistence가 남아 있었다
- 이 경계는 새 기능 누락이 아니라 failure rollback 하나가 persisted recommendation truth를 다시 오염시키는 상태 계약 누수였다
- broader보다는 exact regression + output-gating focused verification이 이번 범위에는 더 직접적인 증거였다

## 3. strict TDD 증거

- RED
  - `py -m pytest tests/test_api.py -q -k "test_review_snapshot_api_approve_rollback_normalizes_legacy_string_false_recommendation_fields"`
  - 결과: `1 failed`
  - 실제 실패:
    - approve rollback 뒤 recommendation row가 `(0, 0, "pending")`이 아니라 `(1, 1, "pending")`
- GREEN
  - `tests/test_api.py`
    - exact regression `test_review_snapshot_api_approve_rollback_normalizes_legacy_string_false_recommendation_fields` 추가
  - `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
    - `_rollback_recommendation_review_mutation(...)`가 legacy false-like recommendation fields를 canonical false DB 값으로 복구하도록 runtime bool-ish normalization 적용
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
    - rollback persistence bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
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
  - `docs/session-context-2026-07-04-approve-rollback-legacy-string-false-recommendation-fields-closeout.ko.md`

## 6. 쉽게 말한 현재 개발상황

- 지금은 legacy 저장 흔적 하나가 실패 rollback 경로를 타고 recommendation row truth를 다시 망치지 않게 작은 경계들을 하나씩 닫는 단계다
- 이번 수정으로 approve 중간 실패가 나더라도 legacy `"false"` recommendation fields가 DB에서 다시 `1/1`로 잘못 굳지 않게 맞췄다

## 7. 다음 세션 첫 시작점

1. approve rollback legacy string false recommendation fields 경계는 현재 기준 닫힌 것으로 본다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개를 고른다
3. exact failing test 1개로만 다시 시작한다

## 8. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
