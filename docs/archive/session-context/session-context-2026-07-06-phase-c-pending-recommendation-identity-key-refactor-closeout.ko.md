# 2026-07-06 Phase C pending recommendation identity key refactor closeout

## 이번 턴에서 한 일

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`에서 pending recommendation의 canonical identity key 생성 로직을 helper 1개로 공통화했습니다.
- 이 helper를 `blocking pending recommendation 판별`, `normalized pending recommendation dedupe`, `partial regeneration source merge dedupe`에 함께 쓰도록 정리했습니다.

## 왜 이 작업을 했는가

- 현재 단계는 새 stale-shape slice를 더 여는 것보다, 실제 중복이 확인된 작은 정리 리팩터링 후보를 안전하게 줄이는 `Phase C`에 가깝습니다.
- pending recommendation key를 여러 군데서 각각 다시 만들고 있어서, 나중에 trim/lower 기준이 한쪽만 바뀌면 output blocker와 partial regeneration dedupe 기준이 다시 어긋날 여지가 있었습니다.

## 변경 범위

- 제품 동작 변경 없음
- dedupe key 생성 중복 제거만 수행

## 검증

- exact verification
  - `py -m pytest tests/test_api.py -q -k "test_output_blockers_deduplicate_repeated_persisted_pending_recommendation_entries" -vv`
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_deduplicates_mixed_case_source_pending_recommendations_when_running_partial_regeneration" -vv`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - 결과:
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`

## 남은 일

- review/output prompt 중복 normalization 규칙과 stale-shape helper 중복 중 실제로 더 줄일 가치가 있는 다음 최소 리팩터링 후보를 다시 고릅니다.
- broad 재검증은 아직 하지 않았고, 최종 closeout 직전에 다시 판단합니다.
