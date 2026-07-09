# VideoBox 세션 컨텍스트

작성일:

- 2026-07-03

주제:

- partial regeneration runtime nested pending recommendation closeout

## 1. 이번 turn에서 실제로 끝낸 것

- 장기 우선순위 queue를 유지한 상태에서 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 다시 골랐다
- 선택한 경계는 `partial regeneration runtime`이 stale nested `pending_recommendation.target_segment_id`를 preflight와 다르게 그대로 복원하는 비대칭이었다
- runtime carry-forward가 nested target shape를 blocker recommendation으로 살리지 않도록 최소 수정으로 닫았다

## 2. 이번 turn의 핵심 판단

- 이미 preflight prediction은 nested `target_segment_id` source pending recommendation을 무시하고 있었지만, 실제 partial regeneration runtime은 같은 stale shape를 그대로 들고 가며 API read path를 깨뜨렸다
- 이 문제는 새 기능 추가보다 `preflight와 runtime이 같은 입력을 같은 기준으로 정규화해야 한다`는 기본 계약 위반에 가까웠다
- 따라서 provider trace나 UI polish보다 먼저 닫는 것이 맞았고, 수정 범위도 runtime pending recommendation 판정 함수 1개로 제한했다

## 3. strict TDD 증거

- RED
  - `python -m pytest tests/test_api.py -q -k "test_editing_session_api_ignores_nested_target_segment_id_source_pending_recommendation_when_running_partial_regeneration"`
  - 결과: `1 failed`
  - 실제 실패:
    - partial regeneration 결과 조회 시 `pending_recommendations.0.target_segment_id`가 string이 아니어서 Pydantic validation error
    - 같은 stale entry에 `provider_trace`도 없어 API response serialization이 깨짐
- GREEN
  - `tests/test_api.py`
    - exact regression `test_editing_session_api_ignores_nested_target_segment_id_source_pending_recommendation_when_running_partial_regeneration` 추가
  - `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
    - `_is_runtime_blocking_pending_recommendation(...)`가 string `recommendation_id`와 string `target_segment_id`만 blocker recommendation으로 인정하도록 축소
  - 같은 exact test 재실행
  - 결과: `1 passed`

## 4. 이번 turn의 verification

- exact regression
  - `1 passed`
- focused runtime/preflight adjacency slice
  - `python -m pytest tests/test_api.py -q -k "nested_target_segment_id_source_pending_recommendation or stale_minimal_dict_source_pending_recommendation_entries_when_running_partial_regeneration or deduplicates_repeated_source_pending_recommendations_when_running_partial_regeneration or marks_review_status_blocked_when_preserved_pending_recommendation_remains"`
  - 결과: `5 passed`
- broader verification
  - `python -m pytest tests -q`
  - 결과: `346 passed`

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
  - `docs/session-context-2026-07-03-runtime-nested-pending-recommendation-closeout.ko.md`

## 6. 쉽게 말한 현재 개발상황

- 지금은 partial regeneration이 이전 timeline의 review blocker를 다시 들고 갈 때, 진짜 blocker만 남기고 오래된 찌꺼기 데이터는 버리도록 다듬는 단계다
- 이번 수정으로 preflight에서는 괜찮았는데 실제 rerun 결과 조회에서만 터지던 stale pending recommendation 누수가 사라져, `미리보기는 정상인데 실제 실행 결과는 깨지는` 비대칭이 하나 줄었다

## 7. 다음 세션 첫 시작점

1. runtime nested pending recommendation 비대칭은 현재 기준 닫힌 것으로 본다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개를 고른다
3. exact failing test 1개로만 다시 시작한다

## 8. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
