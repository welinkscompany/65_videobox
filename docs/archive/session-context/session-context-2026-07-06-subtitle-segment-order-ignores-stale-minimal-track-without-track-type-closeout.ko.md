# VideoBox 세션 컨텍스트

작성일:

- 2026-07-06

주제:

- subtitle segment order ignores stale minimal track without track type closeout

## 1. 이번 turn에서 실제로 끝낸 것

- subtitle render의 segment-order read path가 `track_type` 없는 stale minimal-dict track 때문에 잘못된 세그먼트 순서를 잡을 수 있던 경계 1개를 닫았습니다
- exact regression 1개로 RED를 먼저 확인한 뒤, subtitle segment order 수집이 canonical `track_type`가 있는 track만 읽도록 최소 수정만 넣었습니다
- focused verification은 output-gating과 인접 preflight 범위까지만 다시 돌려 subtitle read path 정리가 주변 계약을 깨지 않는지 확인했습니다

## 2. 이번 turn의 핵심 판단

- 이번 경계는 preview/export prompt 쪽에서 이미 닫은 stale minimal track hardening의 바로 옆에 있는 subtitle read path 한 점이어서, Phase A에서 가장 작은 exact regression이라고 판단했습니다
- `_segments_for_timeline(...)`는 `clips` list만 있으면 subtitle source로 읽고 있었기 때문에, `track_type` 없이 남은 junk track도 세그먼트 순서를 흔들 수 있었습니다
- broader 재검증보다 exact RED/GREEN과 output-gating 중심 focused evidence가 이번 수정의 직접 증거라고 판단했습니다

## 3. 이번 turn의 변경 범위

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
  - subtitle segment-order 수집 시 canonical `track_type`가 있는 track만 읽도록 수정
- `tests/test_api.py`
  - `test_segments_for_timeline_ignores_minimal_dict_track_without_track_type` 추가
- SSOT 문서 업데이트
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`

## 4. 이번 turn의 verification

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_segments_for_timeline_ignores_minimal_dict_track_without_track_type" -vv`
  - RED `1 failed` 확인 후 GREEN `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "<output-gating pattern>"` -> exit code `0` 확인
  - `py -m pytest tests/test_api.py -q -k "<preflight-backend pattern>"` -> exit code `0` 확인
  - `./scripts/dev-fast-path.ps1 -Mode preflight-frontend` -> `25 passed`
- helper 메모
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`는 이번 환경에서도 backend `pytest.exe` 표준출력 인코딩 문제로 실패해 신뢰하지 않았고, backend는 `py -m pytest` 표준 명령으로 다시 확인했습니다
- broader verification
  - 실행하지 않음

## 5. 쉽게 말한 현재 개발상황

- 이번에는 subtitle 파일이 세그먼트 순서를 잡을 때, 정식 track이 아닌 찌꺼기 track을 따라가지 않게 막았습니다
- 이제 `track_type` 없는 반쯤 깨진 track이 있어도 subtitle은 정상 track만 기준으로 순서를 잡습니다

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
