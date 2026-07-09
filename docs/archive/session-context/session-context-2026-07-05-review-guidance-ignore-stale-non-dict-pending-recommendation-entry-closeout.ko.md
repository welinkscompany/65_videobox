# VideoBox 세션 컨텍스트

작성일:

- 2026-07-05

주제:

- review guidance ignore stale non-dict pending recommendation entry closeout

## 1. 이번 turn에서 실제로 끝낸 것

- review guidance prompt가 stale non-dict `pending_recommendations` entry 때문에 예외로 깨지던 경계 1개를 닫았습니다
- exact regression 1개로 RED를 먼저 확인한 뒤, prompt `pending_recommendations` 루프가 dict가 아닌 entry를 건너뛰도록 최소 수정만 넣었습니다
- focused verification은 같은 review guidance pending recommendation prompt surface의 인접 테스트만 다시 돌려 이번 수정이 기존 canonicalization과 trim 경계를 깨지 않는지 확인했습니다

## 2. 이번 turn의 핵심 판단

- 이번 문제는 단순 표시 차이가 아니라, blocked review guidance prompt 생성 중 stale 문자열 pending recommendation 하나 때문에 실제 예외가 나는 runtime gap이었습니다
- output operator copy prompt 쪽은 이미 같은 stale pending recommendation 입력을 걸러내고 있었기 때문에, review guidance prompt도 같은 방향으로 맞추는 것이 `review/output gating`에 가장 가까운 다음 경계라고 판단했습니다
- 범위를 더 넓혀 minimal-dict pending recommendation까지 같이 정리할 수도 있었지만, 이번 turn은 exact RED가 확인된 non-dict 입력 한 점만 막는 쪽이 더 정확했습니다

## 3. 이번 turn의 변경 범위

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`
  - `_prompt_pending_recommendations(...)`가 non-dict pending recommendation entry를 건너뛰도록 수정
- `tests/test_api.py`
  - `test_review_guidance_builder_ignores_non_dict_pending_recommendations_in_prompt` 추가
- SSOT 문서 업데이트
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`

## 4. 이번 turn의 verification

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_ignores_non_dict_pending_recommendations_in_prompt" -vv`
  - RED `1 failed` 확인 후 GREEN `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_ignores_non_dict_pending_recommendations_in_prompt or test_review_guidance_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt or test_review_guidance_builder_trims_pending_recommendation_target_segment_id_in_prompt or test_review_guidance_builder_trims_pending_recommendation_reason_in_prompt" -vv`
  - `4 passed`
- broader verification
  - 실행하지 않음

## 5. 쉽게 말한 현재 개발상황

- 이제 review guidance도 이상한 pending recommendation 문자열 하나 때문에 깨지지 않습니다
- blocked 안내문은 정상 recommendation만 요약하고, 쓰레기 입력은 조용히 무시합니다

## 6. 다음 세션 첫 시작점

1. 장기 우선순위 queue는 그대로 유지합니다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 가까운 exact regression 1개만 고릅니다
3. 그 경계는 이번 review guidance pending recommendation prompt 다음으로 인접한 stale minimal-dict 또는 normalization 잔여 차이부터 우선 닫습니다

## 7. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
