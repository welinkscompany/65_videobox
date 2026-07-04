# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- recommendation read path legacy string false closeout

## 1. 이번 turn에서 실제로 끝낸 것

- 장기 우선순위 queue를 유지한 상태에서 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 다시 골랐다
- 선택한 경계는 recommendation read path가 legacy DB text `"false"`를 truthy bool로 읽는 문제였다
- `list_recommendation_rows(...)`가 bool-ish false를 canonical false로 hydrate하도록 최소 수정으로 닫았다

## 2. 이번 turn의 핵심 판단

- write path를 바로 앞 turn에서 고쳤더라도, legacy DB row를 읽는 경계가 남아 있으면 review/output truth는 여전히 과거 저장 흔적으로 오염될 수 있다
- 이 경계는 새 기능 추가가 아니라 read truth 정합성 보정에 가깝고, bool-ish persistence family 안에서 가장 직접적인 다음 누수였다
- broader보다 output-gating focused lane과 current-focused-parallel이 이번 범위에는 더 직접적인 증거였다

## 3. strict TDD 증거

- RED
  - `py -m pytest tests/test_api.py -q -k "test_store_list_recommendation_rows_treats_legacy_string_false_columns_as_false"`
  - 결과: `1 failed`
  - 실제 실패:
    - hydrated row의 `auto_apply_allowed is True`
- GREEN
  - `tests/test_api.py`
    - exact regression `test_store_list_recommendation_rows_treats_legacy_string_false_columns_as_false` 추가
  - `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
    - `list_recommendation_rows(...)`가 DB 값 hydrate 시 bool-ish normalization을 재사용하도록 최소 수정
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
    - recommendation read-path bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
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
  - `docs/session-context-2026-07-04-recommendation-read-path-legacy-string-false-closeout.ko.md`

## 6. 쉽게 말한 현재 개발상황

- 지금은 legacy bool-shape가 저장될 때뿐 아니라 다시 읽힐 때도 review/output truth를 흔들지 않도록 앞단과 read path를 같이 맞추는 단계다
- 이번 수정으로 과거 DB row에 `"false"`가 text로 남아 있어도, 읽는 순간 다시 blocker처럼 부풀어 오르는 누수를 줄였다

## 7. 다음 세션 첫 시작점

1. recommendation read path legacy string false 경계는 현재 기준 닫힌 것으로 본다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개를 고른다
3. exact failing test 1개로만 다시 시작한다

## 8. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
