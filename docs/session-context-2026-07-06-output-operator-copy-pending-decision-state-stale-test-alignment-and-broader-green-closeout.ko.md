# 2026-07-06 output operator copy pending decision-state stale test alignment and broader green closeout

## 이번에 한 일

- `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`를 다시 실행해 현재 focused gate가 모두 green인지 확인했다.
- 이어서 `frontend build`와 `full backend regression`을 다시 실행했다.
- 그 과정에서 `tests/test_api.py::test_output_operator_copy_builder_canonicalizes_pending_recommendation_decision_state_in_prompt` 1건이 실패했는데, 원인은 현재 SSOT와 어긋난 stale test expectation이었다.
- 현재 동작은 `decision_state="approved"` stale pending recommendation을 prompt에서 제외하는 것이 맞으므로, 해당 테스트를 mixed-case `pending` canonicalization 검증으로 좁혀 `test_output_operator_copy_builder_canonicalizes_pending_decision_state_in_prompt`로 정리했다.

## 왜 이 작업을 했는가

- 최근 slice들로 output operator copy prompt는 approved/applied-like pending entry를 blocker prompt에서 제외하도록 이미 정리돼 있었다.
- 그런데 예전 exact test 하나가 아직 `approved` entry가 prompt 안에 남아야 한다고 기대하고 있어, full backend regression을 불필요하게 막고 있었다.
- 이 mismatch를 정리해야 현재 SSOT와 전체 자동 검증 baseline이 다시 일치한다.

## 변경 파일

- `tests/test_api.py`
- `docs/development-status-2026-06-29.ko.md`

## 검증

- focused lane
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - 결과:
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_output_operator_copy_builder_canonicalizes_pending_decision_state_in_prompt" -vv`
  - 결과: `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_output_operator_copy_builder_canonicalizes_pending_decision_state_in_prompt or test_output_operator_copy_builder_ignores_approved_decision_state_pending_recommendations_in_prompt or test_output_operator_copy_builder_defaults_missing_pending_recommendation_reason_in_prompt or test_output_operator_copy_builder_trims_pending_recommendation_reason_in_prompt" -vv`
  - 결과: `4 passed`
- broader verification
  - `npm run build`
  - 결과: 성공
  - `pytest -q`
  - 결과: `543 passed`

## 현재 판단

- 현재 worktree 기준으로 `current-focused-parallel`, `frontend build`, `full backend regression`이 모두 green이다.
- 따라서 더 작은 stale-shape exact regression을 억지로 찾기보다, 이제는 전체 동작 검증 / QA / 시스템 검증 쪽 Phase B 마감 작업으로 넘어갈 근거가 충분해졌다.
