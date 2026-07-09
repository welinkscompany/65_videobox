# VideoBox 세션 컨텍스트

작성일:

- 2026-07-04

주제:

- partial regeneration mixed-case stale tts recommendation closeout

## 1. 이번 turn에서 실제로 끝낸 것

- 장기 우선순위 queue를 유지한 상태에서 `TTS approval/output`과 바로 이어지는 partial regeneration runtime의 mixed-case stale TTS recommendation 교체 경계 1개만 다시 골랐다
- 선택한 경계는 `tts_refresh`가 mixed-case `TTS_REPLACEMENT` stale recommendation을 기존 recommendation 제거 단계에서 놓쳐 새 manual TTS selection이 교체되지 않는 문제였다
- partial regeneration runtime도 canonical lowercase recommendation type 기준을 쓰도록 최소 수정으로 닫았다

## 2. 이번 turn의 핵심 판단

- `timeline_builder`, preview renderer, CapCut export adapter는 mixed-case TTS type 경계를 닫았지만, partial regeneration runtime의 `tts_refresh` stale recommendation 제거는 아직 raw `strip()` 비교가 남아 있었다
- 이 경계는 같은 `TTS approval/output` family 안에서 바로 다음으로 작은 런타임 truth 누수였고, exact regression 1개로 가장 좁게 닫을 수 있었다
- helper lane과 grouped verification에서는 `_create_timeline_review_project()` 안의 `broll-recommendation` setup 비결정성이 반복돼, 이번 수정의 직접 영향은 exact + 인접 개별 재검증으로 확인하는 편이 더 정확했다

## 3. strict TDD 증거

- RED
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_replaces_mixed_case_stale_applied_tts_recommendation_when_running_partial_regeneration"`
  - 결과: `1 failed`
  - 실제 실패:
    - partial regeneration result narration clip `asset_uri`가 stale mixed-case TTS asset URI로 남음
- GREEN
  - `tests/test_api.py`
    - exact regression `test_editing_session_api_replaces_mixed_case_stale_applied_tts_recommendation_when_running_partial_regeneration` 추가
  - `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
    - `_execute_partial_regeneration_tts_refresh_step(...)`의 stale recommendation 제거 비교가 `_canonical_runtime_recommendation_type(...)`를 재사용하도록 수정
  - 같은 exact test 재실행
  - 결과: `1 passed`

## 4. 이번 turn의 verification

- exact regression
  - `1 passed`
- focused adjacency verification
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_replaces_trimmed_stale_applied_tts_recommendation_when_running_partial_regeneration"`
  - 결과: `1 passed`
  - `py -m pytest tests/test_review_timeline.py -q -k "test_timeline_builder_applies_mixed_case_tts_replacement_type_to_narration_clip"`
  - 결과: `1 passed`
- grouped verification note
  - grouped pytest와 `current-focused-parallel`에서는 `_create_timeline_review_project()` setup 안의 `broll-recommendation` 응답이 `job_id`를 주지 못하는 비결정성 failure가 재발
  - 판단:
    - 이번 slice의 직접 회귀라기보다 existing helper/setup instability로 보며, exact + 인접 개별 재검증을 현재 close 근거로 채택
- broader verification
  - 실행하지 않음
  - 판단:
    - partial regeneration runtime mixed-case TTS replacement 한 점 수정이라 exact + adjacency evidence가 더 직접적이다

## 5. 현재 기준 상태

- 브랜치:
  - `codex/tts-approved-runtime`
- 이번 turn의 코드 변경 범위
  - `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
  - `tests/test_api.py`
- 이번 turn의 문서 변경 범위
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- closeout 문서 추가
  - `docs/session-context-2026-07-04-partial-regeneration-mixed-case-stale-tts-recommendation-closeout.ko.md`

## 6. 쉽게 말한 현재 개발상황

- 지금은 예전 데이터처럼 recommendation type이 대문자 섞인 상태로 timeline에 남아 있어도, partial regeneration이 새로 고른 TTS 음성으로 제대로 갈아끼우는지 하나씩 맞추는 단계다
- 이번 수정으로 mixed-case stale TTS recommendation이 남아 있어도 partial regeneration 결과가 예전 음성을 계속 쓰지 않게 됐다

## 7. 다음 세션 첫 시작점

1. partial regeneration runtime mixed-case stale TTS recommendation 교체 경계는 현재 기준 닫힌 것으로 본다
2. 다음 작업은 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개를 고른다
3. exact failing test 1개로만 다시 시작한다

## 8. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
- AK-Wiki promotion judgment: 보류
