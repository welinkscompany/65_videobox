# VideoBox 세션 컨텍스트

작성일:

- 2026-07-06

주제:

- timeline summary ignores unknown pending recommendation count closeout

## 1. 이번 turn에서 실제로 끝낸 것

- timeline summary가 supported set 밖의 stale unknown `pending_recommendations`를 review status나 review snapshot에는 blocker로 쓰지 않아도 `pending_recommendation_count`에는 그대로 세던 경계 1개를 닫았습니다
- exact regression 1개로 RED를 먼저 확인한 뒤, timeline summary의 pending recommendation count도 canonical blocking pending recommendation 기준으로 계산하도록 최소 수정만 넣었습니다
- focused verification은 storage/read 인접 테스트와 frontend preflight까지만 다시 돌려, 이번 persistence count 정리가 주변 계약을 깨지 않는지 확인했습니다

## 2. 이번 turn의 핵심 판단

- 이번 경계는 직전 timeline summary review flag count hardening과 같은 persisted summary family라서, Phase A에서 가장 가까운 exact regression이라고 판단했습니다
- summary count가 raw 리스트 길이를 그대로 쓰면 이후 surface에서 junk recommendation이 실제 blocker보다 크게 보일 수 있어서, count도 canonical blocking pending 기준으로 맞추는 편이 논리적으로 맞았습니다
- broader 재검증보다 exact RED/GREEN과 storage/read 인접 focused evidence가 이번 수정의 직접 증거라고 판단했습니다

## 3. 이번 turn의 변경 범위

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
  - timeline summary의 `pending_recommendation_count`를 canonical blocking pending recommendation 기준으로 계산하도록 `_timeline_summary_json(...)` helper 확장
- `tests/test_storage.py`
  - `test_save_timeline_run_summary_ignores_unknown_pending_recommendation_count` 추가
- SSOT 문서 업데이트
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`

## 4. 이번 turn의 verification

- exact regression
  - `py -m pytest tests/test_storage.py -q -k "test_save_timeline_run_summary_ignores_unknown_pending_recommendation_count" -vv`
  - RED `1 failed` 확인 후 GREEN `1 passed`
- focused verification
  - `py -m pytest tests/test_storage.py tests/test_api.py -q -k "test_save_timeline_run_summary_ignores_unknown_review_flag_count or test_save_timeline_run_summary_ignores_unknown_pending_recommendation_count or test_store_build_review_snapshot_ignores_unknown_pending_recommendation_for_status_when_persisted_approved or test_store_build_review_snapshot_filters_unknown_pending_recommendation_from_surface or test_store_save_timeline_run_ignores_unknown_pending_recommendation_when_setting_initial_status" -vv`
  - 결과 `5 passed`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-frontend`
  - 결과 `25 passed`
- broader verification
  - 실행하지 않음

## 5. 쉽게 말한 현재 개발상황

- 이번에는 timeline summary에서 실제 blocker가 아닌 junk recommendation 때문에 pending count가 1개 더 크게 저장되던 문제를 막았습니다
- 이제 persisted timeline summary도 실제로 막는 pending recommendation만 셉니다

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
