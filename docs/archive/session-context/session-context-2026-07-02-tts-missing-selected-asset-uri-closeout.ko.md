# VideoBox 세션 컨텍스트

작성일:

- 2026-07-02

주제:

- TTS approval missing `selected_asset_uri` hardening

## 1. 이번 turn에서 실제로 끝낸 것

- TTS replacement approval/output contract의 작은 남은 경계 1개를 strict TDD로 닫았다
- pending `tts_replacement` approve가 `payload.selected_asset_uri` 없이 승인 상태로 통과해 실제 narration output과 어긋날 수 있던 경로를 `400`으로 차단했다
- `output-gating` fast-path helper 기본 패턴에 이 회귀를 포함시켰다

## 2. 이번 turn의 strict TDD 증거

- RED
  - `pytest tests/test_api.py -q -k "test_review_snapshot_api_rejects_tts_approval_without_selected_asset_uri"`
  - 결과: 실패
  - 실패 이유: `selected_asset_uri`가 없는 TTS recommendation approve가 `200`으로 통과했다
- GREEN
  - 같은 exact test 재실행
  - 결과: `1 passed`

## 3. 이번 turn의 fresh verification

- exact regression
  - `pytest tests/test_api.py -q -k "test_review_snapshot_api_rejects_tts_approval_without_selected_asset_uri"`
  - 결과: `1 passed`
- fast-path helper test
  - `pytest tests/test_dev_fast_path.py -q`
  - 결과: `2 passed`
- output gating lane close
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - 결과: `20 passed`
- current-focused 병렬 검증
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - 결과
    - backend output-gating `20 passed`
    - backend preflight `55 passed`
    - frontend preflight `25 passed`
- broader verification
  - `./scripts/dev-fast-path.ps1 -Mode broader`
  - 결과
    - frontend build 성공
    - full backend regression `325 passed`

## 4. 현재 기준 상태

- 브랜치: `codex/tts-approved-runtime`
- 이번 turn의 코드 변경 범위
  - `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`
  - `tests/test_api.py`
  - `scripts/dev-fast-path.ps1`
  - `tests/test_dev_fast_path.py`
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- closeout 문서 추가
  - `docs/session-context-2026-07-02-tts-missing-selected-asset-uri-closeout.ko.md`

## 5. 다음 세션 첫 시작점

1. TTS replacement approval/output contract에서 아직 안 닫힌 가장 작은 추가 경계를 1개만 다시 고른다
2. 후보는 승인 후 read path / persisted applied recommendation shape / output payload 정합성 중 하나로 좁힌다
3. exact failing test 1개로만 다시 RED를 시작한다

## 6. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
