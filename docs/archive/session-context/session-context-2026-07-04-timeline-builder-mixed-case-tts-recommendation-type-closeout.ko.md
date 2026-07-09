# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- timeline builder mixed-case tts recommendation type closeout

## 1. 이번 turn에서 실제로 끝낸 것

- 장기 우선순위 queue를 유지한 상태에서 `TTS approval/output`에 가장 가까운 `timeline_builder`의 mixed-case recommendation type 경계 1개만 다시 골랐다
- 선택한 경계는 `timeline_builder`가 mixed-case `TTS_REPLACEMENT`를 승인된 narration override로 인식하지 못하는 문제였다
- `timeline_builder`도 preview renderer와 CapCut export처럼 canonical lowercase recommendation type 기준을 쓰도록 최소 수정으로 닫았다

## 2. 이번 turn의 핵심 판단

- preview renderer와 CapCut export adapter는 이미 mixed-case TTS type 경계를 닫았지만, `timeline_builder`는 아직 raw `strip()` 비교가 남아 있어 같은 출력 family 안에서 truth가 갈라질 수 있었다
- `local_pipeline`이나 더 넓은 read-path보다 `timeline_builder`가 지금 queue의 `TTS approval/output`에 더 가깝고, exact regression 1개로 가장 좁게 닫을 수 있는 경계였다
- helper override backend lane은 이번 테스트 이름을 직접 수집하지 못해서, direct focused pytest와 `current-focused-parallel` 재검증이 더 직접적인 검증 근거가 됐다

## 3. strict TDD 증거

- RED
  - `py -m pytest tests/test_review_timeline.py -q -k "test_timeline_builder_applies_mixed_case_tts_replacement_type_to_narration_clip"`
  - 결과: `1 failed`
  - 실제 실패:
    - narration clip `asset_uri`가 generated TTS asset이 아니라 original segment URI로 남음
- GREEN
  - `tests/test_review_timeline.py`
    - exact regression `test_timeline_builder_applies_mixed_case_tts_replacement_type_to_narration_clip` 추가
  - `packages/core-engine/src/videobox_core_engine/timeline_builder.py`
    - recommendation type `strip().lower()` helper를 추가하고 supported-type 판정과 narration/B-roll/BGM clip 반영 분기에 재사용
  - 같은 exact test 재실행
  - 결과: `1 passed`

## 4. 이번 turn의 verification

- exact regression
  - `1 passed`
- focused adjacency slice
  - `py -m pytest tests/test_review_timeline.py -q -k "test_timeline_builder_applies_mixed_case_tts_replacement_type_to_narration_clip or test_timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip or test_review_snapshot_uses_trimmed_broll_type_for_default_provider_trace"`
  - 결과: `3 passed`
- helper override note
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "timeline_builder_applies_mixed_case_tts_replacement_type_to_narration_clip or timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip or review_snapshot_uses_trimmed_broll_type_for_default_provider_trace"`
  - 결과: `279 deselected`
  - 판단:
    - 이번 경계는 helper backend lane의 기본 수집 집합 밖에 있어 direct file-focused pytest가 더 정확했다
- broader fast-path verification
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - 첫 실행:
    - backend output-gating `1 failed`
    - backend preflight `1 failed`
    - 공통 실패 지점: `_create_timeline_review_project()` setup 안의 `broll-recommendation` 응답이 `job_id`를 주지 못하는 비결정성 실패
  - exact spot-check:
    - `py -m pytest tests/test_api.py -q -k "test_approving_one_of_multiple_pending_recommendations_keeps_output_blocked_by_remaining_detail" -vv`
    - 결과: `1 passed`
  - 두 번째 `current-focused-parallel` 재실행:
    - backend output-gating `24 passed`
    - backend preflight `57 passed`
    - frontend preflight `25 passed`
  - 판단:
    - 첫 실패는 이번 수정의 직접 회귀보다 helper 병렬 실행의 일시적 흔들림으로 보고, exact 재검증과 helper 재실행으로 green을 다시 확인했다
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline builder mixed-case type canonicalization 한 점에 국한된 수정이라 exact + adjacency + current-focused-parallel evidence가 충분하다
    - latest broader baseline은 기존 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

## 5. 현재 기준 상태

- 브랜치:
  - `codex/tts-approved-runtime`
- 이번 turn의 코드 변경 범위
  - `packages/core-engine/src/videobox_core_engine/timeline_builder.py`
  - `tests/test_review_timeline.py`
- 이번 turn의 문서 변경 범위
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- closeout 문서 추가
  - `docs/session-context-2026-07-04-timeline-builder-mixed-case-tts-recommendation-type-closeout.ko.md`

## 6. 쉽게 말한 현재 개발상황

- 지금은 승인된 TTS 교체가 timeline을 만드는 중간 단계에서도 대소문자 섞인 예전 recommendation type 때문에 빠지지 않도록 출력 family를 맞추는 단계다
- 이번 수정으로 recommendation type이 예전 데이터처럼 대문자 섞인 형태여도, `timeline_builder`가 선택된 TTS 음성을 놓치지 않게 됐다

## 7. 다음 세션 첫 시작점

1. `timeline_builder` mixed-case TTS recommendation type 경계는 현재 기준 닫힌 것으로 본다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개를 고른다
3. exact failing test 1개로만 다시 시작한다

## 8. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
