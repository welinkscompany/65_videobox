# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- recommendation store string false review_required closeout

## 1. 이번 turn에서 실제로 끝낸 것

- 장기 우선순위 queue를 유지한 상태에서 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 다시 골랐다
- 선택한 경계는 recommendation 저장 write path가 `review_required="false"` legacy string false shape를 persisted blocker truth로 굳히는 문제였다
- `save_recommendation_run(...)`가 bool-ish false를 canonical false로 저장하도록 최소 수정으로 닫았다

## 2. 이번 turn의 핵심 판단

- 이 경계는 방금 닫은 timeline build truth보다 앞단의 저장소 경계라서, 여기서 잘못 저장되면 downstream build/output 쪽은 이미 오염된 truth를 읽게 된다
- stale pending decision-state family를 더 넓히는 것보다, legacy bool-shape가 persisted truth를 잘못 만드는 더 직접적인 저장소 누수를 먼저 닫는 편이 맞았다
- broader보다 output-gating focused lane과 current-focused-parallel이 이번 범위에는 더 직접적인 증거였다

## 3. strict TDD 증거

- RED
  - `py -m pytest tests/test_api.py -q -k "test_store_save_recommendation_run_treats_string_false_review_required_as_false"`
  - 결과: `1 failed`
  - 실제 실패:
    - returned recommendation payload의 `review_required is True`
- GREEN
  - `tests/test_api.py`
    - exact regression `test_store_save_recommendation_run_treats_string_false_review_required_as_false` 추가
  - `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
    - `save_recommendation_run(...)`에 bool-ish normalization helper를 추가하고 `auto_apply_allowed/review_required`를 canonical bool로 저장하도록 최소 수정
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
    - backend preflight `55 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - recommendation store bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
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
  - `docs/session-context-2026-07-04-recommendation-store-string-false-review-required-closeout.ko.md`

## 6. 쉽게 말한 현재 개발상황

- 지금은 legacy shape 하나 때문에 review/output truth가 저장 단계에서부터 틀어지지 않도록, 앞단부터 작은 경계를 하나씩 닫는 단계다
- 이번 수정으로 `"false"` 같은 문자열 때문에 recommendation이 저장되는 순간부터 blocker로 굳는 누수를 줄였다

## 7. 다음 세션 첫 시작점

1. recommendation store string false review_required 경계는 현재 기준 닫힌 것으로 본다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개를 고른다
3. exact failing test 1개로만 다시 시작한다

## 8. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
