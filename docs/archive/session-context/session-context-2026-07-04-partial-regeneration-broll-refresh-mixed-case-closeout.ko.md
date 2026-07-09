# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- partial regeneration broll refresh mixed-case applied recommendation closeout

## 1. 이번 turn에서 실제로 끝낸 것

- partial regeneration runtime의 `broll_refresh`가 mixed-case stale applied recommendation을 기존 B-roll recommendation으로 지우지 못하던 경계 1개를 닫았습니다
- exact regression 1개로 RED를 먼저 확인한 뒤, refresh stale-removal 비교를 canonical lowercase recommendation type 기준으로 맞췄습니다
- 구현 계획서와 상태 문서에도 이번 계약과 검증 결과를 최소 범위로 반영했습니다

## 2. 이번 turn의 핵심 판단

- 이번 slice는 `review/output gating`보다 `TTS approval/output`과 더 가까운 runtime applied recommendation refresh 경계였습니다
- 이미 같은 family에서 `tts_refresh` canonicalization이 닫혀 있었기 때문에, 그와 같은 기준으로 `broll_refresh` stale removal comparison만 맞추는 편이 가장 작고 논리적인 수정이었습니다
- `music_refresh`도 같은 raw comparison을 쓰고 있어, 같은 helper 재사용으로 같이 정리하는 편이 diff는 작고 drift는 줄이는 선택이었습니다

## 3. 이번 turn의 변경 범위

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
  - `broll_refresh` stale recommendation 제거 비교를 canonical lowercase type 기준으로 수정
  - 같은 family인 `music_refresh`도 같은 helper 기준으로 정리
- `tests/test_api.py`
  - exact regression 추가
- `docs/implementation-plan.ko.md`
  - mixed-case stale applied B-roll refresh 계약 1줄 추가
- `docs/development-status-2026-06-29.ko.md`
  - closeout section 101 추가

## 4. 이번 turn의 verification

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_replaces_mixed_case_stale_applied_broll_recommendation_when_running_partial_regeneration"`
  - RED: `1 failed`
  - GREEN: `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "trimmed_stale_applied_broll_recommendation_when_running_partial_regeneration or mixed_case_stale_applied_broll_recommendation_when_running_partial_regeneration or trimmed_stale_applied_bgm_recommendation_when_running_partial_regeneration"`
  - 결과: `3 passed`

## 5. 쉽게 말한 현재 개발상황

- 이전에는 예전 B-roll 추천이 `" BROLL "`처럼 저장돼 있으면 rerun이 그걸 예전 추천으로 못 알아봐서 새 manual B-roll과 같이 남았습니다
- 이번 수정으로 이제 mixed-case stale B-roll recommendation도 제대로 지우고 새 manual 선택만 남깁니다

## 6. 다음 세션 첫 시작점

1. 장기 우선순위 queue는 그대로 유지합니다
2. 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 exact regression 1개만 고릅니다
3. 같은 refresh family를 잇는다면 `music_refresh` mixed-case dedicated evidence 보강 또는 store/read 계층의 mixed-case blocker 판정 경계를 다시 좁히는 순서가 자연스럽습니다

## 7. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
