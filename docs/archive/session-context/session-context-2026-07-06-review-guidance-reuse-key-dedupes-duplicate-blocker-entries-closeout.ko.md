# VideoBox 세션 컨텍스트

작성일:

- 2026-07-06

주제:

- review guidance reuse key duplicate blocker dedupe closeout

## 1. 이번 turn에서 실제로 끝낸 것

- 장기 우선순위 queue를 유지한 채, `review/output gating` 안에서 가장 작은 남은 경계 1개만 다시 골랐다
- 선택한 경계는 blocked review guidance persisted reuse key가 duplicate blocker entry를 그대로 hidden key에 넣는 문제였다
- blocker truth가 같으면 duplicate stale entry가 있어도 같은 reuse key를 만들도록 최소 수정으로 닫았다

## 2. 이번 turn의 핵심 판단

- 이 문제는 visible review/output surface가 아니라 blocked guidance persistence의 hidden mismatch였다
- 실제 blocker가 같은데 duplicate `review_flags`나 `pending_recommendations`가 섞이면 guidance를 불필요하게 다시 생성할 수 있었다
- 범위가 매우 좁아서 exact regression 1개와 `output-gating` focused lane만으로 증거를 닫는 것이 맞았다

## 3. strict TDD 증거

- RED
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_reuse_key_dedupes_duplicate_blocker_entries" -vv`
  - 결과: `1 failed`
  - 실제 실패:
    - duplicate stale blocker entry가 canonical snapshot과 다른 reuse key를 만들었다
- GREEN
  - `tests/test_api.py`
    - exact regression `test_review_guidance_reuse_key_dedupes_duplicate_blocker_entries` 추가
  - `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
    - `_build_review_guidance_reuse_key(...)`가 canonicalized duplicate `review_flags`와 `pending_recommendations`를 hidden key에서 dedupe하도록 최소 수정
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
    - blocked guidance persistence key dedupe 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
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
  - `docs/session-context-2026-07-06-review-guidance-reuse-key-dedupes-duplicate-blocker-entries-closeout.ko.md`

## 6. 쉽게 말한 현재 개발상황

- 지금은 막아야 할 항목이 같으면 검수 가이드도 같은 것으로 재사용되게 맞추는 마지막 정리 단계다
- 이번 수정으로 blocker가 중복 저장돼 있어도 다른 문제처럼 오해해서 가이드를 새로 만드는 누수를 줄였다

## 7. 다음 세션 첫 시작점

1. review guidance reuse key duplicate blocker dedupe 경계는 현재 기준 닫힌 것으로 본다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개를 고른다
3. exact failing test 1개로만 다시 시작한다

## 8. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
