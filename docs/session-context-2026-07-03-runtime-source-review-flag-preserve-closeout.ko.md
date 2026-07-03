# VideoBox 세션 컨텍스트

작성일:

- 2026-07-03

주제:

- partial regeneration runtime source review flag preserve closeout

## 1. 이번 turn에서 실제로 끝낸 것

- 장기 우선순위 queue를 유지한 상태에서 `review/output`과 `preflight contract`가 맞닿는 가장 작은 runtime 경계 1개만 다시 골랐다
- 선택한 경계는 partial regeneration runtime이 source timeline의 valid `review_flag` blocker를 candidate 결과에 복원하지 않아 preflight와 다른 상태를 만드는 문제였다
- runtime candidate 결과도 source review flag blocker를 유지해 `review_status=blocked`와 canonical message를 같이 surface하도록 최소 수정으로 닫았다

## 2. 이번 turn의 핵심 판단

- preflight는 source timeline의 valid `review_flags.code/segment_id`를 보면 이미 `blocked` prediction을 내리고 있었다
- 하지만 실제 partial regeneration runtime은 source `pending_recommendations`만 carry-forward하고 source `review_flags`는 버리고 있어서, 같은 입력에서 candidate 결과가 `draft`로 풀리는 비대칭이 있었다
- 이 문제는 output gating보다 한 단계 앞의 truth gap이라서, 다음 큰 기능보다 먼저 닫는 것이 맞았다

## 3. strict TDD 증거

- RED
  - `python -m pytest tests/test_api.py -q -k "test_partial_regeneration_result_marks_review_status_blocked_when_preserved_source_review_flag_remains"`
  - 결과: `1 failed`
  - 실제 실패:
    - candidate result의 `review_status`가 `blocked`가 아니라 `draft`
    - 첫 GREEN 시도 후에는 preserved source review flag의 `message`가 비어 API response validation error도 확인됨
- GREEN
  - `tests/test_api.py`
    - exact regression `test_partial_regeneration_result_marks_review_status_blocked_when_preserved_source_review_flag_remains` 추가
  - `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
    - partial regeneration runtime이 valid source blocker review flag를 `code + segment_id` 기준 dedupe해 candidate timeline payload에 복원
    - legacy shape도 API contract를 깨지 않도록 default review flag message를 함께 채움
  - 같은 exact test 재실행
  - 결과: `1 passed`

## 4. 이번 turn의 verification

- exact regression
  - `1 passed`
- focused adjacency slice
  - `python -m pytest tests/test_api.py -q -k "filters_unknown_code_source_review_flag_entries_from_preflight_prediction or marks_preflight_blocked_when_source_review_flag_has_valid_code_and_segment_without_message or preserved_source_review_flag_remains or preserved_pending_recommendation_remains"`
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - partial regeneration runtime source review flag carry-forward 한 점에 국한된 수정이라 focused evidence가 더 직접적이다
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
  - `docs/session-context-2026-07-03-runtime-source-review-flag-preserve-closeout.ko.md`

## 6. 쉽게 말한 현재 개발상황

- 지금은 부분 재생성(candidate)을 만들었을 때, 원본 timeline에 남아 있던 검수 blocker가 실제 결과에도 똑같이 남아야 하는지 하나씩 맞추는 단계다
- 이번 수정으로 preflight에서는 막힌다고 나오는데 실제 candidate 결과는 멀쩡한 draft처럼 보이던 어긋남이 하나 줄었다

## 7. 다음 세션 첫 시작점

1. runtime source review flag preserve 경계는 현재 기준 닫힌 것으로 본다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개를 고른다
3. exact failing test 1개로만 다시 시작한다

## 8. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
