# VideoBox 세션 컨텍스트

작성일:

- 2026-07-05

주제:

- review guidance reuse key ignores stale unknown and minimal blocker entries closeout

## 1. 이번 turn에서 실제로 끝낸 것

- blocked review guidance persistence가 stale unknown/minimal blocker dict 때문에 같은 blocker truth를 다른 reuse key로 취급하던 경계 1개를 닫았습니다
- exact regression 1개로 RED를 먼저 확인한 뒤, blocked guidance reuse key가 canonical supported blocker entry만 반영하도록 최소 수정만 넣었습니다
- focused verification은 review/output gating과 인접 preflight 범위까지만 다시 돌려 persistence key 정리가 주변 계약을 깨지 않는지 확인했습니다

## 2. 이번 turn의 핵심 판단

- 이번 경계는 output prompt나 approval mutation보다 더 작은 `persistence behavior` 한 점이었고, 기존 blocked guidance reuse logic과 직접 맞닿아 있어서 Phase A에서 가장 가까운 exact regression이라고 판단했습니다
- stale unknown/minimal blocker dict는 이미 다른 read path에서 많이 걸러지고 있었지만, reuse key만은 그대로 반영하고 있어 같은 blocker truth에서도 guidance를 불필요하게 다시 생성할 수 있었습니다
- broader 재검증보다 exact RED/GREEN과 output-gating 중심 focused evidence가 이번 수정의 직접 증거라고 판단했습니다

## 3. 이번 turn의 변경 범위

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
  - blocked review guidance reuse key 생성 시 supported review-flag code와 canonical recommendation identity/type/segment를 가진 blocker만 반영하도록 수정
- `tests/test_api.py`
  - `test_review_guidance_reuse_key_ignores_stale_unknown_and_minimal_blocker_entries` 추가
- SSOT 문서 업데이트
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`

## 4. 이번 turn의 verification

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_review_guidance_reuse_key_ignores_stale_unknown_and_minimal_blocker_entries" -vv`
  - RED `1 failed` 확인 후 GREEN `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "<output-gating pattern>"` -> `24 passed`
  - `py -m pytest tests/test_api.py -q -k "<preflight-backend pattern>"` -> exit code `0` 확인
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
    - frontend preflight `25 passed`
    - backend helper의 직접 출력은 환경의 `uv trampoline` 오류 때문에 신뢰하지 않고, backend는 위 `py -m pytest` 표준 명령으로 다시 확인함
- broader verification
  - 실행하지 않음

## 5. 쉽게 말한 현재 개발상황

- 이번에는 화면에 보이는 기능을 바꾼 것이 아니라, blocked 상태에서 예전에 저장한 안내문을 재사용할지 판단하는 기준을 더 정확하게 다듬었습니다
- 이제 낡은 쓰레기 blocker 조각이 섞여 있어도 실제 막고 있는 내용이 같으면 같은 guidance로 보고, 쓸데없이 다시 계산하는 일이 줄어듭니다

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
