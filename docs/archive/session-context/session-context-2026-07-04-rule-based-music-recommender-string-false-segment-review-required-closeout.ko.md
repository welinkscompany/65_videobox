# 2026-07-04 rule-based music recommender string false segment review_required closeout

## 이번 세션에서 한 일

- `RuleBasedMusicRecommender`가 segment payload의 legacy string false `review_required="false"`를 truthy로 오판해 neutral-bed fallback branch를 잘못 타는 exact regression 1개를 TDD로 닫았다.
- `tests/test_recommendations.py`에 `test_rule_based_music_recommender_ignores_string_false_segment_review_required`를 추가해 RED를 먼저 확인했다.
- `packages/core-engine/src/videobox_core_engine/recommenders.py`에 bool-ish normalization helper를 추가하고, music mood branch 판정이 canonical bool을 쓰도록 좁게 수정했다.

## 검증

- exact regression
  - `pytest tests/test_recommendations.py -q -k "rule_based_music_recommender_ignores_string_false_segment_review_required"`
  - RED 확인 후 GREEN `1 passed`
- focused verification
  - `pytest tests/test_recommendations.py -q`
  - `3 passed`
- broader verification
  - 이번 slice에서는 실행하지 않음
  - 직전 baseline은 `full backend regression 346 passed`, `frontend build 성공`

## 남은 맥락

- queue 1~3의 직접 출력/사전검증 경계는 많이 닫혀 있어, 이번 slice는 계획서 5번의 작은 evidence gap을 정리한 성격이다.
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract`로 돌아가 가장 작은 exact regression 또는 가장 작은 증거 부족 경계 1개를 고르면 된다.
