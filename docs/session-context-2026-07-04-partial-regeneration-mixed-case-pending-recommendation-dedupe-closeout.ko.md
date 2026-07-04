# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- partial regeneration mixed-case pending recommendation dedupe closeout

## 1. 이번 turn에서 실제로 끝낸 것

- `preflight contract`와 바로 맞닿은 partial regeneration runtime carry-forward 경계에서, mixed-case stale pending recommendation duplicate가 결과 timeline에 두 번 남는 문제를 막았습니다
- exact regression 1개로 RED를 먼저 확인했고, runtime pending recommendation dedupe key의 type 비교만 최소 수정해 같은 exact test를 GREEN으로 되돌렸습니다
- focused verification은 같은 family exact 3개만 묶어 다시 돌려, preflight prediction과 runtime dedupe가 같은 mixed-case blocker 기준을 유지하는지 확인했습니다

## 2. 이번 turn의 핵심 판단

- 장기 queue 후보는 `review/output gating`, `TTS approval/output`, `preflight contract`로 좁혔고, 그중 이번 턴에는 `preflight contract`와 가장 가까운 runtime symmetry 경계를 골랐습니다
- 이미 닫혀 있던 exact인 `repeated source pending recommendation dedupe` 축에서 mixed-case `recommendation_type`만 빠져 있었고, 이 경우 source timeline의 `"tts_replacement"`와 `" TTS_REPLACEMENT "`가 같은 blocker인데도 결과 timeline에 2개가 동시에 남을 수 있었습니다
- 이 문제는 broader를 건드릴 필요 없이 runtime pending-key canonicalization 두 군데만 맞추면 닫히는 작은 경계였습니다

## 3. 이번 turn의 변경 범위

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
  - runtime pending recommendation dedupe key의 `recommendation_type` 비교를 canonical lowercase로 수정
- `tests/test_api.py`
  - `test_editing_session_api_deduplicates_mixed_case_source_pending_recommendations_when_running_partial_regeneration` exact regression 추가
- `docs/implementation-plan.ko.md`
  - runtime mixed-case pending recommendation dedupe 계약 1줄 추가
- closeout 문서 추가
  - `docs/session-context-2026-07-04-partial-regeneration-mixed-case-pending-recommendation-dedupe-closeout.ko.md`

## 4. 이번 turn의 verification

- RED exact
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_deduplicates_mixed_case_source_pending_recommendations_when_running_partial_regeneration"`
  - 결과: `1 failed`
  - 핵심 실패: `pending_recommendations` 길이가 기대한 `1`이 아니라 `2`
- GREEN exact
  - 같은 명령 재실행
  - 결과: `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_deduplicates_repeated_source_pending_recommendations_when_running_partial_regeneration or test_editing_session_api_deduplicates_mixed_case_source_pending_recommendations_when_running_partial_regeneration or test_editing_session_api_preserves_mixed_case_source_pending_recommendation_type_in_preflight_prediction"`
  - 결과: `3 passed`

## 5. 쉽게 말한 현재 개발상황

- source timeline에 같은 pending blocker가 소문자/대문자만 다르게 두 번 들어 있어도, partial regeneration 결과에서는 이제 한 번만 남습니다
- 그래서 preflight는 blocker를 한 번으로 보고, runtime 결과도 같은 blocker를 한 번만 유지하게 맞춰졌습니다

## 6. 다음 세션 첫 시작점

1. 장기 queue는 유지합니다
2. 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 가까운 작은 경계 1개만 고릅니다
3. exact failing test 1개로만 다시 RED를 시작합니다

## 7. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
- AK-Wiki promotion judgment: 보류
