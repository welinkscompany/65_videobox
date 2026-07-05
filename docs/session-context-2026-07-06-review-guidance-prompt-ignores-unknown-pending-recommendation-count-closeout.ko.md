# VideoBox 세션 컨텍스트

작성일:

- 2026-07-06

주제:

- review guidance prompt ignores unknown pending recommendation count closeout

## 1. 이번 turn에서 실제로 끝낸 것

- review guidance prompt가 supported set 밖의 stale unknown `pending_recommendations`를 surface에서는 걸러도 `Pending recommendation count`에는 그대로 세던 경계 1개를 닫았습니다
- exact regression 1개로 RED를 먼저 확인한 뒤, prompt count도 filtered canonical pending recommendation surface와 같은 기준을 쓰도록 최소 수정만 넣었습니다
- focused verification은 review guidance family와 frontend preflight까지만 다시 돌려, 이번 prompt count 정리가 주변 계약을 깨지 않는지 확인했습니다

## 2. 이번 turn의 핵심 판단

- 이번 경계는 직전 heuristic fallback unknown pending-type hardening과 바로 이어지는 prompt surface count 면이라서, Phase A에서 가장 가까운 exact regression이라고 판단했습니다
- prompt row surface는 이미 junk recommendation을 무시해도 count가 raw 리스트 길이를 그대로 쓰면 operator-facing guidance가 여전히 틀어질 수 있기 때문에, count와 surface를 같은 기준으로 맞추는 편이 논리적으로 맞았습니다
- broader 재검증보다 exact RED/GREEN과 review guidance 인접 focused evidence가 이번 수정의 직접 증거라고 판단했습니다

## 3. 이번 turn의 변경 범위

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`
  - review guidance prompt count와 surface가 같은 filtered canonical pending recommendation row를 재사용하도록 수정
- `tests/test_api.py`
  - `test_review_guidance_builder_ignores_unknown_pending_recommendation_in_prompt_count` 추가
- SSOT 문서 업데이트
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`

## 4. 이번 turn의 verification

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_ignores_unknown_pending_recommendation_in_prompt_count" -vv`
  - RED `1 failed` 확인 후 GREEN `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_builder_ignores_unknown_pending_recommendation_in_prompt_count or test_review_guidance_builder_ignores_minimal_dict_pending_recommendations_in_prompt or test_review_guidance_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt or test_heuristic_review_guidance_builder_ignores_unknown_pending_recommendation_type or test_heuristic_review_guidance_builder_defaults_missing_pending_recommendation_reason" -vv`
  - 결과 `5 passed`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-frontend`
  - 결과 `25 passed`
- broader verification
  - 실행하지 않음

## 5. 쉽게 말한 현재 개발상황

- 이번에는 review guidance 문구에서 보이지도 않는 junk recommendation 때문에 blocker 개수만 1개 더 크게 보이던 문제를 막았습니다
- 이제 review guidance prompt는 보이는 목록과 개수를 같은 기준으로 계산합니다

## 6. 다음 세션 첫 시작점

1. 장기 queue는 그대로 유지합니다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 가까운 exact regression 1개만 고릅니다
3. 여전히 페이즈 A 안정화 단계이며, 전체 QA/시스템 검증/정리 페이즈로는 아직 넘어가지 않습니다

## 7. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
