# VideoBox 세션 컨텍스트

작성일:

- 2026-07-05

주제:

- review snapshot legacy blocked guidance reuse closeout

## 1. 이번 turn에서 실제로 끝낸 것

- review snapshot이 `blocked` 상태에서 예전 operator guidance를 너무 넓게 재사용하던 경계 1개를 닫았습니다
- exact regression 1개로 RED를 먼저 확인한 뒤, blocked guidance 재사용을 blocker surface까지 비교하는 최소 수정만 넣었습니다
- focused verification은 `output-gating`과 `current-focused-parallel`까지만 다시 돌려 인접 review/output·preflight 경계가 유지되는지 확인했습니다

## 2. 이번 turn의 핵심 판단

- 이번 경계는 `review/output gating`과 직접 붙어 있고 stale blocked guidance가 현재 blocker truth를 덮어쓰는 문제라 우선순위가 높았습니다
- `approved`나 `draft` guidance 재사용까지 넓게 건드리면 이미 닫힌 경계를 흔들 수 있어, 이번 수정은 blocked 상태에서만 hidden reuse key를 추가하는 방식으로 범위를 제한했습니다
- legacy blocked guidance에는 reuse key가 없으므로, 같은 `blocked` 상태라도 blocker surface가 바뀌면 guidance를 다시 계산하도록 두는 편이 더 안전했습니다

## 3. 이번 turn의 변경 범위

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
  - blocked review snapshot용 canonical blocker-surface reuse key 추가
  - blocked persisted guidance 재사용 조건을 status-only에서 status + blocker surface로 축소
- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
  - hidden `_operator_guidance_reuse_key` 저장/조회 추가
  - guidance clear 시 reuse key도 함께 정리
- `tests/test_api.py`
  - `test_review_snapshot_ignores_legacy_blocked_persisted_guidance_when_blocker_surface_changes` 추가
- SSOT 문서 업데이트
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`

## 4. 이번 turn의 verification

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_review_snapshot_ignores_legacy_blocked_persisted_guidance_when_blocker_surface_changes" -vv`
  - RED `1 failed` 확인 후 GREEN `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
    - `24 passed, 317 deselected`
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음

## 5. 쉽게 말한 현재 개발상황

- 이번에는 review가 막힌 상태인데도 예전에 저장된 안내문을 그대로 보여주던 부분만 아주 작게 고쳤습니다
- 이제 blocked guidance는 단순히 상태가 같다는 이유만으로 재사용하지 않고, 실제로 막고 있는 항목이 같은지까지 보고 재사용합니다

## 6. 다음 세션 첫 시작점

1. 장기 queue는 그대로 유지합니다
2. 다음 작업은 다시 `docs/implementation-plan.ko.md`의 `## 13. 다음 실제 작업` 기준으로 후보를 2~3개로 좁힙니다
3. 그중 `review/output gating`, `TTS approval/output`, `preflight contract`에 가장 가까운 exact regression 1개만 골라 RED 1개로 시작합니다

## 7. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
