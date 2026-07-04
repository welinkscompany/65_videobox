# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- review snapshot applied override legacy pending-like recommendation closeout

## 1. 이번 turn에서 실제로 끝낸 것

- 장기 우선순위 queue를 유지한 상태에서 `review/output gating`, `TTS approval/output`, `preflight contract` 중 review snapshot direct helper의 applied override 대칭 경계 1개만 다시 골랐다
- 선택한 경계는 review snapshot의 `timeline_applied_recommendations` override 입력이 legacy pending-like recommendation을 applied recommendation으로 고정하는 문제였다
- review snapshot direct helper가 pending-like recommendation shape를 applied가 아니라 pending truth로 재분류하도록 최소 수정으로 닫았다

## 2. 이번 turn의 핵심 판단

- 직전 pending override 경계는 이미 닫혔지만, applied override 대칭면은 여전히 caller bucket을 그대로 우선시하고 있었다
- 이 경계는 새 기능 누락이 아니라 direct applied override 경로가 raw recommendation truth를 보지 않아 review snapshot classification을 다시 applied 쪽으로 오염시키는 상태 계약 누수였다
- broader보다는 exact regression + output-gating focused verification이 이번 범위에는 더 직접적인 증거였다

## 3. strict TDD 증거

- RED
  - `py -m pytest tests/test_api.py -q -k "test_store_build_review_snapshot_reclassifies_legacy_pending_like_timeline_applied_override"`
  - 결과: `1 failed`
  - 실제 실패:
    - `applied_recommendations`에 legacy pending-like recommendation이 그대로 남음
- GREEN
  - `tests/test_api.py`
    - exact regression `test_store_build_review_snapshot_reclassifies_legacy_pending_like_timeline_applied_override` 추가
  - `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
    - `build_review_snapshot(...)`의 applied override 경로가 raw item 기준 `_normalize_recommendation_decision_state(...)`를 먼저 계산한 뒤 payload fallback에 반영하고, applied/pending 컬렉션을 normalized decision-state 기준으로 재분류하도록 최소 수정
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
    - review snapshot helper decision-state normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

## 5. 현재 기준 상태

- 브랜치:
  - `codex/tts-approved-runtime`
- 이번 turn의 코드 변경 범위
  - `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
  - `tests/test_api.py`
- 이번 turn의 문서 변경 범위
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- closeout 문서 추가
  - `docs/session-context-2026-07-04-review-snapshot-applied-override-legacy-pending-like-recommendation-closeout.ko.md`

## 6. 쉽게 말한 현재 개발상황

- 지금은 legacy recommendation 흔적 하나가 review snapshot helper에서 applied처럼 굳지 않도록, direct helper 입력 경계를 대칭적으로 하나씩 맞추는 단계다
- 이번 수정으로 `auto_apply_allowed="false"`와 `review_required="true"`가 같이 있는 recommendation이 applied override 입력으로 들어와도, review snapshot이 그걸 실제 applied recommendation처럼 남기지 않게 맞췄다

## 7. 다음 세션 첫 시작점

1. review snapshot applied override legacy pending-like recommendation 경계는 현재 기준 닫힌 것으로 본다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개를 고른다
3. exact failing test 1개로만 다시 시작한다

## 8. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
