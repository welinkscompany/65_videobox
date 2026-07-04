# VideoBox 개발 상태 점검 2026-06-29

> 현재 authoritative 상태/next slice 판단은 `## 17. 2026-07-01 시스템 정비 기준 최신 상태`를 우선 적용한다. 그 외 날짜 기반 상태 섹션은 당시 시점 기록을 보존한 historical log다.
> 이 문서의 `## 1`부터 `## 16`까지는 당시 시점 판단과 검증 수치를 보존한 historical snapshot이다. 현재 truth, 현재 검증 수치, 현재 next slice는 `## 17`만 기준으로 본다.
> 단, `2일 내 1차 데모 완성` 실행 레일은 `## 17`의 장기 우선순위를 그대로 넓게 집행하지 않고, `docs/superpowers/plans/2026-07-03-v1-two-day-completion-and-upgrade-plan.ko.md`의 축소된 실행 계획을 우선 적용한다.

## 1. 결론

현재 개발은 계획서에서 크게 새지 않았다.
그리고 `경량 후편집기 UI`가 아니라 `편집 세션 기반`으로 먼저 가야 한다는 방향도 실제 코드로 반영됐다.

현재까지 반영된 핵심은 아래다.

- `editing session` 모델
- 수정 저장 구조
- 수정 API
- 부분 재생성 규칙
- 설명 카드 / 이미지 / 표 편집 mutation
- TTS replacement 선택 / 해제 mutation

## 2. 확인된 사실

현재 기준 아래는 코드와 테스트로 확인됐다.

- 로컬 프로젝트/자산/job 저장 구조 존재
- segment analysis 파이프라인 존재
- transcript alignment 존재
- B-roll 추천과 음악 추천 존재
- timeline 생성과 review approval 존재
- subtitle render, preview render, CapCut export 존재
- Local Qwen 우선 + Gemini fallback runtime 존재
- editing session 생성/조회 존재
- caption / cut / B-roll / visual overlay / music override 수정 API 존재
- explanation card / image overlay / table overlay / TTS replacement 수정 API 존재
- partial regeneration request contract와 explicit downstream rerun mapping 존재
- partial regeneration 실제 backend job 실행 존재
- 전체 테스트 `221 passed`

## 3. 아직 부족한 부분

아래는 다음 단계 전에 필요한 핵심 빈칸이다.

- TTS replacement의 baseline narration asset swap / preview/export 반영은 이미 연결되어 있고, 남은 일은 approval/review contract를 더 세분화하는 단계
- image/table/explanation 편집을 프런트 편집기 UI에서 직접 다루는 단계
- partial regeneration preflight의 비파괴 확인 경로는 이미 API와 UI에 노출되어 있고, 남은 일은 contract 세분화다
- 실제 오디오 치환 이후 review 승인과 export 반영 규칙을 더 세분화하는 단계

## 4. 왜 지금 UI부터 가면 안 되는가

UI부터 만들면 아래 문제가 바로 생긴다.

- 수정 결과를 어디에 저장할지 기준이 없다
- 부분 재생성을 어디까지 다시 돌릴지 합의가 없다
- 자막 수정, 컷 수정, B-roll 교체가 서로 다른 임시 구조로 흩어질 가능성이 크다
- 나중에 오픈소스 편집기 셸을 붙일 때 다시 뜯어고치게 된다

그래서 순서는 `편집 규칙 고정 -> 얇은 UI 검증 -> 필요 시 OSS 셸 반입`이 맞다.

## 5. 다음 구현 범위 고정

다음 goal은 아래 범위로 묶는 것이 맞다.

1. TTS replacement의 연결된 narration replacement baseline 위에 approval/review contract를 더 고정
2. review-required 상태에서 subtitle/preview/export가 어떻게 막히고 안내되는지 추가 경계를 더 고정
3. partial regeneration preflight의 API/UI 노출 이후 read-only contract와 resume/prediction 경계를 더 세분화
4. 얇은 내부 편집 UI에서 새 mutation을 직접 검증
5. 해당 범위 TDD 완료

## 6. 이번 단계에서 의도적으로 안 하는 것

- 풀 편집기 UI
- 오픈소스 편집기 통째 반입
- 고급 오디오 믹싱
- 색보정
- 자유 키프레임
- 프리미어급 멀티트랙 편집 기능

## 7. 구현 시작 조건

현재 브랜치/워킹트리 기준으로 바로 다음 goal 구현 시작 가능하다.
테스트 베이스라인은 안정적이고, 계획서 기준 다음 빈칸도 명확하다.

## 8. 2026-06-29 추가 검증 기록

이번 재검증에서 아래를 다시 확인했다.

- 전체 백엔드 회귀 테스트 `221 passed`
- blank caption 거부 동작 정상
- invalid partial regeneration request 거부 동작 정상
- unknown session segment / unsupported field 거부 동작 정상
- `editing_sessions` 저장/조회와 기존 프로젝트 self-heal 동작 유지
- explanation/image/table/TTS mutation API 정상
- image/table/visual overlay 삭제 경로 정상
- legacy `visual-overlay`가 다른 overlay 타입을 덮어쓰지 않도록 정리됨
- empty visual overlay state가 partial regeneration 결과에서 실제 clear로 반영됨

이번 재검증 기준 신규 치명 버그는 다시 확인되지 않았다.
다만 다음 구현 전 반드시 채워야 할 빈칸은 여전히 아래다.

- TTS replacement의 실제 narration/output 반영 이후 approval/review contract 세분화
- review-required TTS 흐름의 승인 후 적용 규칙
- 새 mutation을 직접 다루는 편집기 UI 검증

## 9. 외부 참고 후보 기록

당장 반입하지 않지만 나중에 다시 볼 가치가 있는 외부 레퍼런스는 아래처럼 기록해 둔다.

- `SamurAIGPT/AI-Youtube-Shorts-Generator`
  - 분류: `exclude for now`, `partial port candidate later`
  - 이유: 현재 VideoBox의 설명형/나레이션 편집 중심 구조와 직접 정합성이 낮고, shorts 추출기 성격이 강하다
  - 현재 판단: 이번 `editing session`/`partial regeneration`/`review` 마일스톤에는 반입하지 않는다
  - 재검토 시점: shorts 파생 기능 milestone
  - 참고 포인트: highlight scoring, vertical reframe/local crop pipeline

## 10. 2026-06-30 상태 갱신

이번 후속 작업으로 `thin internal editor mutation verification` 단계는 계획서 기준 완료로 봐도 된다.

현재 추가로 확인된 사실은 아래와 같다.

- thin editor에서 explanation / image / table / TTS clear/remove 경로가 직접 검증 가능
- clear/remove 이후 active candidate invalidation이 caption 외 mutation에도 회귀 테스트로 고정됨
- incomplete input에 대한 invalid-state visibility가 문구와 접근성 연결까지 포함해 고정됨
- mutation 저장/삭제 중에는 preflight / rerun 버튼이 잠겨 stale session race를 막음
- clear/remove 이후 실제 editor state 제거까지 테스트가 확인함
- frontend focused test `30 passed`
- frontend build 성공
- full backend regression `230 passed`

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. thin editor mutation happy-path save
2. thin editor clear/remove
3. active candidate invalidation
4. preflight-first gating 유지
5. resume/readability 관련 기존 계약 유지

현재 이 단계에서 다음 핵심 빈칸은 다시 아래로 정리된다.

- `latest editing session` 조회 실패를 너무 넓게 `null`로 삼키는 기존 복원 경로 리스크 점검
- 이후 main goal 측면에서는 TTS replacement baseline 연결 여부가 아니라, approval/output hardening과 더 상위 milestone 사이 우선순위 판단

## 11. 2026-06-30 resumed candidate restore visibility 완료 기록

이번 후속 작업으로 `resumed partial-regeneration candidate restore visibility` hardening은 완료로 봐도 된다.

이번에 추가로 확인된 사실은 아래와 같다.

- refresh-resume 중 candidate result fetch 실패와 review snapshot fetch 실패가 더 이상 `그냥 resume candidate 없음`처럼 묻히지 않는다
- resumed preflight fetch 실패는 full editor failure가 아니라 제한된 degraded warning으로 분리된다
- stale restore warning이 target 변경, 새 preflight 요청, approval, reopen 이후 남지 않도록 정리됐다
- valid resume 동작과 기존 freshness gate / preflight-first / multi-segment readability 계약은 유지됐다
- frontend focused test `38 passed`
- frontend build 성공
- full backend regression `230 passed`

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. no resumable candidate / degraded resume / full candidate resume success 구분
2. resumed preflight limited degradation visibility
3. stale restore warning cleanup
4. 기존 refresh-resume 계약 회귀 유지

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 이번 브랜치의 상위 계획서 기준 다음 대형 goal 재선정
- refresh-resume보다 더 큰 제품 milestone로 넘어갈 때 필요한 다음 SSOT 문서 갱신

## 12. 2026-06-30 review snapshot to editing session handoff 기록

이번 후속 작업으로 `review snapshot -> editing session handoff`의 첫 실제 slice는 완료로 봐도 된다.

이번에 추가로 확인된 사실은 아래와 같다.

- review snapshot 세그먼트 카드에서 대상 세그먼트를 editing session으로 바로 열 수 있다
- pending recommendation 카드에서 현재 UI가 지원하는 recommendation type은 해당 rerun field로 바로 좁혀서 editor를 열 수 있다
- unsupported recommendation type은 강제 매핑하지 않고 세그먼트 기본 rerun scope로 fallback 한다
- review flag 카드에서 editor로 이동해도 기본 rerun scope를 덮어쓰지 않는다
- placeholder global review action 버튼은 이 단계에서 의도적으로 그대로 유지됐다
- frontend focused test `42 passed`
- frontend build 성공
- full backend regression `230 passed`

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot segment direct-open
2. pending recommendation -> mapped field narrowing
3. unsupported recommendation -> default rerun fallback
4. review flag -> default rerun preserve

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- thin editor 범위에서 아직 UI parity가 덜 채워진 `music override` 흐름 보강
- review action placeholder를 실제 persistence contract와 연결할지 여부 설계

## 13. 2026-06-30 thin editor music override parity 기록

이번 후속 작업으로 `thin editor music override parity`의 첫 실제 slice는 완료로 봐도 된다.

이번에 추가로 확인된 사실은 아래와 같다.

- thin editor에서 music asset id를 직접 입력하고 저장할 수 있다
- incomplete music draft는 asset id가 들어오기 전까지 로컬 상태로만 남고 저장은 막힌다
- music override 저장 후 active candidate invalidation은 기존 mutation 흐름과 같은 규칙으로 유지된다
- 저장된 music override는 rerun scope에서 `music` field로 바로 보이고 preflight request에도 반영된다
- music override만 있는 후순위 세그먼트도 기본 editor focus 대상으로 잡힌다
- frontend focused test `44 passed`
- frontend build 성공
- full backend regression `230 passed`

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. thin editor music save
2. incomplete music local draft blocking
3. save 후 candidate invalidation
4. rerun scope music visibility
5. music-only later segment default focus

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- review->editor recommendation mapping coverage 중 `broll` happy-path 보강
- review action placeholder를 실제 persistence contract와 연결할지 여부 설계

## 44. 2026-07-04 timeline builder review snapshot legacy string false recommendation fields closeout

이번 후속 작업에서는 이미 닫힌 store fallback 경계를 다시 넓히지 않고, 그 바로 인접면인 `timeline_builder.build_review_snapshot()` direct dict 입력에서 legacy false-like recommendation payload가 applied truth를 pending blocker로 뒤집는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/timeline_builder.py`의 `build_review_snapshot(...)`는 direct dict recommendation 입력의 `auto_apply_allowed="true"` / `review_required="false"` 값을 raw `bool(...)`로 읽어 applied recommendation을 pending recommendation으로 잘못 분류하고 있었다
- strict TDD로 `test_timeline_builder_review_snapshot_treats_string_false_recommendation_fields_as_applied` exact regression을 먼저 추가했고, 실제로 `applied_recommendations == []` RED를 확인했다
- 구현 전에 검토한 `partial regeneration result` 후보 경계는 현재 코드 기준 이미 닫혀 있었고, 실제 runtime 반환 계약에 맞게 test setup을 보정한 뒤 exact regression이 바로 GREEN이었다
- 원인은 builder review snapshot read path가 upstream/store normalization을 재사용하지 않고 recommendation bool fields를 raw truthiness로 다시 판정하던 점이었다
- 최소 수정으로 `build_review_snapshot(...)`도 `_recommendation_payload(...)`를 거쳐 bool-ish normalization을 먼저 적용하도록 맞춰 legacy false-like recommendation fields를 canonical applied/pending truth로 분류하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline builder review snapshot truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline builder review snapshot bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline builder review snapshot direct dict 입력이 legacy recommendation payload의 `auto_apply_allowed="true"` / `review_required="false"` shape를 pending blocker로 오판하지 않음
2. applied recommendation truth가 builder review snapshot에서도 그대로 유지됨
3. builder review snapshot truth와 store fallback / API read truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다

## 112. 2026-07-04 partial regeneration trimmed BGM target segment id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 인접한 partial regeneration runtime applied recommendation refresh family에서 stale whitespace BGM `target_segment_id` 경계 1개만 다시 닫았다.

핵심 변경

- strict TDD로 `test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_bgm_recommendation_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 partial regeneration result bgm track에 stale clip과 manual clip이 함께 남는 RED를 확인했다
- 최소 수정으로 `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_music_refresh_step(...)`가 stale applied recommendation 제거 시 `target_segment_id.strip()` 기준으로 비교하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration BGM refresh 제거 비교 한 점만 좁게 수정했다

검증

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_bgm_recommendation_when_running_partial_regeneration" -vv`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_replaces_trimmed_stale_applied_bgm_recommendation_when_running_partial_regeneration or test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_bgm_recommendation_when_running_partial_regeneration" -vv`
  - 결과 `2 passed`

남은 상태

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다

## 111. 2026-07-04 partial regeneration trimmed B-roll target segment id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 인접한 partial regeneration runtime applied recommendation refresh family에서 stale whitespace B-roll `target_segment_id` 경계 1개만 다시 닫았다.

핵심 변경

- strict TDD로 `test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_broll_recommendation_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 partial regeneration result broll track에 stale clip과 manual clip이 함께 남는 RED를 확인했다
- 최소 수정으로 `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_broll_refresh_step(...)`가 stale applied recommendation 제거 시 `target_segment_id.strip()` 기준으로 비교하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration B-roll refresh 제거 비교 한 점만 좁게 수정했다

검증

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_broll_recommendation_when_running_partial_regeneration" -vv`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_replaces_trimmed_stale_applied_broll_recommendation_when_running_partial_regeneration or test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_broll_recommendation_when_running_partial_regeneration or test_editing_session_api_replaces_mixed_case_stale_applied_broll_recommendation_when_running_partial_regeneration" -vv`
  - 결과 `3 passed`

남은 상태

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다

## 110. 2026-07-04 partial regeneration trimmed TTS target segment id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`과 바로 이어지는 partial regeneration runtime의 stale whitespace TTS `target_segment_id` 경계 1개만 다시 닫았다.

핵심 변경

- strict TDD로 `test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_tts_recommendation_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 partial regeneration result narration clip `asset_uri`가 stale generated TTS asset URI 그대로 남는 RED를 확인했다
- 최소 수정으로 `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_tts_refresh_step(...)`가 stale applied recommendation 제거 시 `target_segment_id.strip()` 기준으로 비교하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration TTS refresh 제거 비교 한 점만 좁게 수정했다

검증

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_tts_recommendation_when_running_partial_regeneration" -vv`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_replaces_trimmed_stale_applied_tts_recommendation_when_running_partial_regeneration or test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_tts_recommendation_when_running_partial_regeneration or test_editing_session_api_replaces_mixed_case_stale_applied_tts_recommendation_when_running_partial_regeneration" -vv`
  - 결과 `3 passed`

남은 상태

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다

## 109. 2026-07-04 timeline builder trimmed TTS target segment id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 timeline builder consumer family에서 approved TTS recommendation의 stale whitespace `target_segment_id` 경계 1개만 다시 닫았다.

핵심 변경

- strict TDD로 `test_timeline_builder_applies_trimmed_tts_target_segment_id_to_narration_clip` exact regression을 먼저 추가했고, 실제로 narration clip `asset_uri`가 generated TTS asset이 아니라 original segment URI로 남는 RED를 확인했다
- 최소 수정으로 `packages/core-engine/src/videobox_core_engine/timeline_builder.py`의 `_recommendation_payload(...)`가 `target_segment_id`를 `strip()` 기준으로 정규화하도록 맞춰, segment bucket lookup과 applied recommendation surface가 같은 canonical id를 쓰게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline builder의 TTS target-segment matching 한 점만 좁게 수정했다

검증

- exact regression
  - `py -m pytest tests/test_review_timeline.py -q -k "test_timeline_builder_applies_trimmed_tts_target_segment_id_to_narration_clip" -vv`
- focused verification
  - `py -m pytest tests/test_review_timeline.py -q -k "test_timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip or test_timeline_builder_applies_mixed_case_tts_replacement_type_to_narration_clip or test_timeline_builder_applies_trimmed_tts_target_segment_id_to_narration_clip" -vv`
  - 결과 `3 passed`

남은 상태

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다

## 108. 2026-07-04 TTS output trimmed target segment id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 output consumer family에서 applied TTS recommendation의 stale whitespace `target_segment_id` 경계 1개만 다시 닫았다.

핵심 변경

- strict TDD로 `test_capcut_export_adapter_matches_trimmed_tts_target_segment_id_for_segment_level_narration_sources` exact regression을 먼저 추가했고, 실제로 voiceover 첫 segment `source_uri`가 generated TTS asset이 아니라 original narration source로 남는 RED를 확인했다
- 최소 수정으로 `packages/capcut-export/src/videobox_capcut_export/adapter.py`의 narration override segment set과 같은 규칙을 쓰는 `packages/core-engine/src/videobox_core_engine/preview_renderer.py`의 TTS segment set 모두 `str(...).strip()` 기준으로 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preview/export TTS target-segment matching 한 점만 좁게 수정했다

검증

- exact regression
  - `py -m pytest tests/test_preview_export.py -q -k "test_capcut_export_adapter_matches_trimmed_tts_target_segment_id_for_segment_level_narration_sources" -vv`
- focused verification
  - `py -m pytest tests/test_preview_export.py -q -k "test_capcut_export_adapter_matches_trimmed_tts_target_segment_id_for_segment_level_narration_sources or test_capcut_export_adapter_uses_segment_level_narration_sources_for_approved_tts_replacement or test_capcut_export_adapter_matches_trimmed_tts_recommendation_type_for_segment_level_narration_sources or test_capcut_export_adapter_matches_mixed_case_tts_recommendation_type_for_segment_level_narration_sources or test_capcut_export_adapter_treats_string_false_tts_review_required_as_false_for_segment_level_narration_sources" -vv`
  - 결과 `5 passed`
  - `py -m pytest tests/test_api.py -q -k "test_preview_renderer_treats_string_false_tts_recommendation_review_required_as_false or test_preview_renderer_matches_trimmed_tts_recommendation_type_for_narration_source or test_preview_renderer_matches_trimmed_tts_target_segment_id_for_narration_source or test_preview_renderer_matches_mixed_case_tts_recommendation_type_for_narration_source" -vv`
  - 결과 `4 passed`

남은 상태

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다

## 107. 2026-07-04 output blocker detail trimmed pending identity closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 output blocker detail surface의 stale whitespace pending recommendation identity 경계 1개만 다시 닫았다.

핵심 변경

- strict TDD로 `test_output_blocker_detail_trims_pending_recommendation_identity_fields` exact regression을 먼저 추가했고, 실제로 preview render 차단 detail이 `tts_replacement: rec_tts_seg_001 @ seg_001 `처럼 raw whitespace를 노출하는 RED를 확인했다
- 최소 수정으로 `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_normalized_runtime_pending_recommendations(...)`가 dedupe key만 trim하던 상태에서 blocker surface에 쓰는 `recommendation_id`, `target_segment_id`도 trim된 값으로 다시 써 주도록 좁혔다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output blocker detail surface 한 점만 좁게 수정했다

검증

- exact regression
  - `py -m pytest tests/test_api.py -q -k "test_output_blocker_detail_trims_pending_recommendation_identity_fields" -vv`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_output_blocker_detail_trims_pending_recommendation_identity_fields or test_output_blocker_detail_canonicalizes_mixed_case_pending_recommendation_type or test_output_blockers_deduplicate_repeated_persisted_pending_recommendation_entries or test_output_gating_blocks_mixed_case_review_flag_code_on_approved_timeline or test_approved_review_state_still_blocks_outputs_when_only_pending_recommendations_remain or test_approving_one_of_multiple_pending_recommendations_keeps_output_blocked_by_remaining_detail" -vv`
  - 결과 `6 passed`

남은 상태

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 154. 2026-07-04 heuristic review guidance default pending recommendation reason closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 heuristic review guidance fallback의 `reason` 없는 `pending_recommendations` default-reason surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `HeuristicReviewGuidanceBuilder`는 valid pending recommendation에 `reason`이 없을 때 local-first prompt family나 API read-path default reason 기준과 달리 canonical default blocker message를 쓰지 않고, 더 약한 generic blocker 문구로 action item을 채우고 있었다
- strict TDD로 `test_heuristic_review_guidance_builder_defaults_missing_pending_recommendation_reason` exact regression을 먼저 추가했고, 실제로 action item이 `Operator review required before approval or output.`가 아니라 `Resolve review blockers before approval.`로 내려오는 RED를 확인했다
- 최소 수정으로 heuristic fallback이 valid `pending_recommendations.recommendation_id/target_segment_id/recommendation_type`가 있고 `reason`만 비어 있는 경우에는 canonical default blocker message를 action item으로 채우도록 맞춰, runtime fallback guidance도 review/output gating과 API response 쪽 default blocker reason 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 heuristic review guidance fallback의 default-reason surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - `316 deselected`
- broader verification
  - 실행하지 않음
  - 판단:
    - heuristic fallback pending-recommendation default-reason canonicalization 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. heuristic review guidance fallback이 `reason` 없는 valid `pending_recommendations`에도 canonical default blocker message를 action item으로 surface한다
2. runtime fallback guidance가 missing reason pending recommendation을 generic blocker 문구로만 뭉개지 않는다
3. heuristic review guidance fallback의 pending-recommendation reason surface가 review/output gating truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 153. 2026-07-04 heuristic review guidance default review flag message closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 heuristic review guidance fallback의 message 없는 `review_flags` default-message surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `HeuristicReviewGuidanceBuilder`는 valid review flag에 `message`가 없을 때 local-first prompt family와 달리 canonical default blocker message를 쓰지 않고, 더 약한 generic blocker 문구로 action item을 채우고 있었다
- strict TDD로 `test_heuristic_review_guidance_builder_defaults_missing_review_flag_message` exact regression을 먼저 추가했고, 실제로 action item이 `Operator review required before approval or output.`가 아니라 `Resolve review blockers before approval.`로 내려오는 RED를 확인했다
- 최소 수정으로 heuristic fallback이 valid `review_flags.code/segment_id`가 있고 `message`만 비어 있는 경우에는 canonical default blocker message를 action item으로 채우도록 맞춰, runtime fallback guidance도 review/output gating과 API response 쪽 default message 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 heuristic review guidance fallback의 default-message surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - `315 deselected`
- broader verification
  - 실행하지 않음
  - 판단:
    - heuristic fallback action-item default-message canonicalization 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. heuristic review guidance fallback이 message 없는 valid `review_flags`에도 canonical default blocker message를 action item으로 surface한다
2. runtime fallback guidance가 missing message review flag를 generic blocker 문구로만 뭉개지 않는다
3. heuristic review guidance fallback의 review-flag message surface가 review/output gating truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 152. 2026-07-04 review guidance review flag default message prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 message 없는 `review_flags` default-message surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_prompt_review_flags(...)`는 직전 slice들로 `code/segment_id/message` trim surface는 정리됐지만, message가 없는 valid review flag는 raw dict 그대로 두고 있어 API/read-path가 채우는 canonical default blocker message가 operator guidance prompt에는 비어 있었다
- strict TDD로 `test_review_guidance_builder_defaults_review_flag_message_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 `'message': 'Operator review required before approval or output.'`를 포함하지 않는 RED를 확인했다
- 최소 수정으로 `_prompt_review_flags(...)`에서 비어 있는 `message`에 canonical default blocker message를 채우도록 맞춰, review guidance prompt의 message 없는 review-flag surface가 review/output gating과 API response 쪽 default message 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 default-message surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt review-flag default-message canonicalization 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 message 없는 valid `review_flags`에도 canonical default blocker message를 surface한다
2. operator guidance prompt가 missing message review flag를 빈 surface로 남기지 않는다
3. review guidance prompt의 review-flag message surface가 review/output gating truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 151. 2026-07-04 output operator copy review flag default message prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 가장 가까운 output operator copy prompt의 message 없는 `review_flags` default-message surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 직전 slice들로 `review_flags.code/segment_id/message` trim surface는 정리됐지만 message가 없는 valid review flag는 그대로 raw dict로 두고 있어, API/read-path가 채우는 canonical default blocker message가 preview/export operator guidance prompt에는 비어 있었다
- strict TDD로 `test_output_operator_copy_builder_defaults_review_flag_message_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 `'message': 'Operator review required before approval or output.'`를 포함하지 않는 RED를 확인했다
- 최소 수정으로 prompt용 `review_flags` summary를 만들 때 `message`가 비어 있으면 canonical default blocker message를 채우도록 맞춰, output operator copy prompt의 message 없는 review-flag surface가 review/output gating과 API response 쪽 default message 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 default-message surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt review-flag default-message canonicalization 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 message 없는 valid `review_flags`에도 canonical default blocker message를 surface한다
2. preview/export guidance prompt가 missing message review flag를 빈 surface로 남기지 않는다
3. output operator copy prompt의 review-flag message surface가 review/output gating truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 150. 2026-07-04 output operator copy review flag message prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 가장 가까운 output operator copy prompt의 `review_flags.message` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 직전 slice에서 `review_flags.code`와 `review_flags.segment_id`는 정리됐지만 `message`는 여전히 raw 문자열 그대로 넣고 있어, whitespace stale review-flag message가 preview/export operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_output_operator_copy_builder_trims_review_flag_message_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'message': ' Review narration replacement '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 prompt용 `review_flags` summary를 만들 때 `message`도 trim하도록 맞춰, output operator copy prompt의 review-flag-message surface가 review/output gating과 API response 쪽 canonical blocker message 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 review-flag-message surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt review-flag-message trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 whitespace stale `review_flags.message`도 trimmed blocker message로 surface한다
2. preview/export guidance prompt가 raw padded review-flag message 문자열을 그대로 노출하지 않는다
3. output operator copy prompt의 review-flag-message surface가 review/output gating truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 149. 2026-07-04 output operator copy review flag segment id prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 가장 가까운 output operator copy prompt의 `review_flags.segment_id` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 직전 slice에서 `review_flags.code`는 canonicalize하게 됐지만 `segment_id`는 여전히 raw 문자열 그대로 넣고 있어, whitespace stale review-flag segment id가 preview/export operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_output_operator_copy_builder_trims_review_flag_segment_id_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'segment_id': ' seg_001 '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 prompt용 `review_flags` summary를 만들 때 `segment_id`도 trim하도록 맞춰, output operator copy prompt의 review-flag-segment-id surface가 review/output gating과 preflight/runtime 쪽 canonical segment id 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 review-flag-segment-id surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt review-flag-segment-id trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 whitespace stale `review_flags.segment_id`도 trimmed segment id로 surface한다
2. preview/export guidance prompt가 raw padded review-flag segment id 문자열을 그대로 노출하지 않는다
3. output operator copy prompt의 review-flag-segment-id surface가 review/output gating truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 148. 2026-07-04 output operator copy review flag code prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 가장 가까운 output operator copy prompt의 `review_flags.code` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 직전 slice들로 `pending_recommendations` 주요 surface는 대부분 정리됐지만 `review_flags`는 여전히 raw list 그대로 prompt에 넣고 있어, mixed-case stale `review_flags.code`가 preview/export operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_output_operator_copy_builder_canonicalizes_review_flag_code_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'code': ' TTS_REPLACEMENT_REVIEW_REQUIRED '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 prompt용 `review_flags` summary를 따로 만들고 `code`만 canonical lowercase로 정리하도록 맞춰, output operator copy prompt의 review-flag-code surface가 review/output gating 쪽 canonical review-flag 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 review-flag-code surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt review-flag-code canonicalization 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 mixed-case stale `review_flags.code`도 canonical lowercase code로 surface한다
2. preview/export guidance prompt가 raw padded review-flag code 문자열을 그대로 노출하지 않는다
3. output operator copy prompt의 review-flag-code surface가 review/output gating truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 147. 2026-07-04 output operator copy pending decision state prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 `TTS approval/output` 사이에서 가장 인접한 output operator copy prompt의 `pending_recommendations.decision_state` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 직전 slice들로 `recommendation_type`, `target_segment_id`, `reason`, `selected_asset_id`, `recommendation_id`, `created_at`, nested `payload.selected_asset_uri`는 정리됐지만 `decision_state`는 여전히 raw 문자열 그대로 넣고 있어, mixed-case stale decision state가 preview/export operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_output_operator_copy_builder_canonicalizes_pending_recommendation_decision_state_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'decision_state': ' Approved '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 prompt용 `pending_recommendations` summary를 만들 때 `decision_state`도 canonical lowercase로 정리하도록 맞춰, output operator copy prompt의 decision-state surface가 approve/read-path 쪽 canonical decision-state 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 decision-state surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt decision-state canonicalization 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 mixed-case stale `pending_recommendations.decision_state`도 canonical lowercase 상태로 surface한다
2. preview/export guidance prompt가 raw padded decision state 문자열을 그대로 노출하지 않는다
3. output operator copy prompt의 decision-state surface가 approve/read-path truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 39. 2026-07-04 rule based music recommender string false segment review_required closeout

이번 후속 작업에서는 queue 1~3의 직접 출력/사전검증 경계가 대부분 닫힌 상태에서, 계획서 5번의 작은 evidence gap에 해당하는 recommendation generation 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/recommenders.py`의 `RuleBasedMusicRecommender`는 segment payload의 `review_required`를 raw truthiness로 읽고 있어, legacy string false shape인 `review_required="false"`를 truthy로 오판해 실제 review blocker가 없는 segment도 `"light neutral bed"` branch로 보내고 있었다
- strict TDD로 `test_rule_based_music_recommender_ignores_string_false_segment_review_required` exact regression을 먼저 추가했고, 실제로 `"Quarterly finance summary"` segment가 기대한 `"focused corporate"`가 아니라 `"light neutral bed"` reason으로 내려가는 RED를 확인했다
- 최소 수정으로 recommender에도 bool-ish normalization helper를 추가해 segment `review_required`를 canonical bool로 해석하도록 맞춰, false-like string shape가 neutral-bed fallback branch를 잘못 타지 않게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 recommendation generation 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused verification
  - `tests/test_recommendations.py` `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - rule-based music recommender의 bool-ish normalization 한 점 수정이라 exact + file-focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. rule-based music recommender가 legacy string false `review_required="false"`를 truthy review blocker로 오판하지 않음
2. review blocker가 없는 일반 segment는 neutral-bed fallback이 아니라 기본 music mood branch를 유지함
3. recommendation generation의 bool-ish false 해석이 다른 read/write normalization 규칙과 더 가까워짐

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 130. 2026-07-04 review guidance trimmed pending recommendation target segment id prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `pending_recommendations.target_segment_id` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 prompt용 pending recommendation surface는 `recommendation_type`은 이미 canonical lowercase 기준으로 정리하고 있었지만, `target_segment_id`는 raw 문자열 그대로 두고 있어 `" seg_001 "` 같은 whitespace stale shape가 operator-facing guidance prompt에 그대로 남고 있었다
- strict TDD로 `test_review_guidance_builder_trims_pending_recommendation_target_segment_id_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 `{'target_segment_id': ' seg_001 '}`를 그대로 담는 RED를 확인했다
- 최소 수정으로 prompt용 pending recommendation surface가 `target_segment_id.strip()` 기준을 사용하도록 맞춰, guidance prompt가 canonical trimmed target segment id를 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 target-segment-id surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance / operator copy 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt의 trimmed target-segment-id canonicalization 한 점 수정이라 exact + 인접 guidance/output surface evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 whitespace stale `target_segment_id`도 canonical trimmed id로 surface한다
2. operator-facing guidance prompt가 raw padded target segment id를 그대로 남기지 않는다
3. review guidance prompt의 target segment id 기준이 TTS/output read-path 쪽 canonical segment id 규칙과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 129. 2026-07-04 review guidance mixed-case pending recommendation type prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `pending_recommendations` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_build_prompt(...)`는 `pending_recommendations`를 raw dict 그대로 prompt에 넣고 있어, legacy `" TTS_REPLACEMENT "` 같은 mixed-case stale `recommendation_type`가 operator-facing guidance prompt에 그대로 남고 있었다
- strict TDD로 `test_review_guidance_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 `{'recommendation_type': ' TTS_REPLACEMENT '}`를 그대로 담는 RED를 확인했다
- 최소 수정으로 review guidance prompt용 pending recommendation surface가 `recommendation_type.strip().lower()` 기준을 사용하도록 맞춰, guidance prompt가 canonical lowercase recommendation type을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 recommendation-type surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance / operator copy 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt의 recommendation-type canonicalization 한 점 수정이라 exact + 인접 guidance/output surface evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 legacy mixed-case `recommendation_type`도 canonical lowercase type으로 surface한다
2. operator-facing guidance prompt가 raw stale recommendation type 문자열을 그대로 남기지 않는다
3. review guidance prompt의 recommendation type 기준이 approved/read-path 쪽 canonical type 규칙과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 128. 2026-07-04 review guidance trimmed segment id prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `Segments needing attention` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_segments_needing_attention(...)`는 `review_required` 판정은 canonical bool-ish 기준으로 하고 있었지만, 반환하는 `segment_id`는 raw 문자열 그대로 두고 있어 `" seg_001 "` 같은 whitespace stale shape가 operator-facing guidance prompt에 그대로 남고 있었다
- strict TDD로 `test_review_guidance_builder_trims_segment_ids_needing_attention_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 `Segments needing attention: [' seg_001 ']`를 그대로 담는 RED를 확인했다
- 최소 수정으로 `_segments_needing_attention(...)`가 `segment_id.strip()` 기준을 사용하도록 맞춰, guidance prompt가 canonical trimmed segment id를 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 segment-id surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance / operator copy 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt의 trimmed segment-id canonicalization 한 점 수정이라 exact + 인접 guidance/output surface evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 whitespace stale `segment_id`도 canonical trimmed id로 surface한다
2. operator-facing guidance prompt가 raw padded segment id를 그대로 남기지 않는다
3. review guidance prompt의 세그먼트 식별 기준이 preflight/runtime 쪽 trimmed segment id 규칙과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 123. 2026-07-04 CapCut export mixed-case narration track type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 CapCut export voiceover track surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`는 track loop에서 `track_type`를 raw 문자열 그대로 `narration`과 비교하고 있어, legacy `" NARRATION "` 같은 mixed-case stale shape가 남으면 voiceover track 자체를 만들지 못하고 있었다
- strict TDD로 `test_capcut_export_adapter_matches_mixed_case_narration_track_type_for_voiceover_track` exact regression을 먼저 추가했고, 실제로 `payload["capcut_tracks"]`에서 `voiceover` track을 찾지 못하는 RED를 확인했다
- 최소 수정으로 CapCut export adapter에 track type canonical helper를 추가해 `strip().lower()` 기준으로 정리하고, mixed-case narration track도 voiceover track으로 정확히 내보내게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 CapCut export narration track type read-path 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - CapCut export voiceover 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - CapCut export narration track-type canonicalization 한 점 수정이라 exact + export 인접 focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. CapCut export adapter가 legacy mixed-case narration `track_type`도 canonical lowercase 기준으로 해석한다
2. stale narration track type 때문에 voiceover track이 통째로 빠지는 문제를 막는다
3. approved narration/TTS output surface가 preview/export 계열에서 더 같은 canonical track type 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 124. 2026-07-04 preview renderer mixed-case narration track type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 preview narration source surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/preview_renderer.py`는 narration sources HTML surface를 만들 때 `track_type`를 raw 문자열 그대로 `narration`과 비교하고 있어, legacy `" NARRATION "` 같은 mixed-case stale shape가 남으면 narration source list가 비어 있었다
- strict TDD로 `test_preview_renderer_matches_mixed_case_narration_track_type_for_narration_source` exact regression을 먼저 추가했고, 실제로 preview HTML의 `Narration sources`가 빈 `<ul></ul>`로 남는 RED를 확인했다
- 최소 수정으로 preview renderer에 track type canonical helper를 추가해 `strip().lower()` 기준으로 정리하고, mixed-case narration track도 narration sources surface에 정확히 반영되게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 preview narration track type read-path 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - preview narration source 인접 exact
  - 결과: `6 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview renderer narration track-type canonicalization 한 점 수정이라 exact + preview 인접 focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preview renderer가 legacy mixed-case narration `track_type`도 canonical lowercase 기준으로 해석한다
2. stale narration track type 때문에 narration sources surface가 비는 문제를 막는다
3. preview visible narration source surface가 CapCut export voiceover surface와 더 같은 canonical track type 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 125. 2026-07-04 preview renderer mixed-case track type surface closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 preview visible track summary surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/preview_renderer.py`는 `Track summary` HTML surface에서 `track_type`를 raw 문자열 그대로 출력하고 있어, legacy `" NARRATION "` 같은 mixed-case stale shape가 visible output surface에 그대로 노출되고 있었다
- strict TDD로 `test_preview_renderer_canonicalizes_mixed_case_track_type_surface` exact regression을 먼저 추가했고, 실제로 preview HTML이 `<strong> NARRATION </strong>`를 그대로 노출하는 RED를 확인했다
- 최소 수정으로 preview renderer의 track summary surface도 기존 `_canonical_track_type(...)` helper를 재사용하도록 맞춰 `strip().lower()` 기준으로 canonical lowercase type을 출력하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 preview visible track-type surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - preview visible surface 인접 exact
  - 결과: `7 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview renderer track-type visible surface canonicalization 한 점 수정이라 exact + preview 인접 focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preview renderer가 legacy mixed-case `track_type`도 canonical lowercase type으로 surface한다
2. preview `Track summary`가 raw stale track type 문자열을 그대로 노출하지 않는다
3. preview narration source read-path와 preview visible track summary surface가 더 같은 canonical track type 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 126. 2026-07-04 review approval mixed-case narration track type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 review recommendation approval mutation 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 `apply_approved_recommendation_to_timeline(...)`는 approved TTS replacement를 narration clip에 반영할 때 `track_type`를 raw 문자열 그대로 `narration`과 비교하고 있어, legacy `" NARRATION "` 같은 mixed-case stale shape가 남으면 target narration clip을 찾지 못하고 실패하고 있었다
- strict TDD로 `test_apply_approved_tts_recommendation_matches_mixed_case_narration_track_type` exact regression을 먼저 추가했고, 실제로 `Approved TTS replacement requires a matching target narration clip.` 예외가 나는 RED를 확인했다
- 최소 수정으로 review action mutation에 track type canonical helper를 추가해 `strip().lower()` 기준으로 narration track을 찾도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 건드리지 않고 approved TTS narration 적용의 track-type read-path 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review approval / TTS output 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - approved TTS narration track-type canonicalization 한 점 수정이라 exact + approval/output 인접 focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review recommendation approval mutation이 legacy mixed-case narration `track_type`도 canonical lowercase 기준으로 해석한다
2. stale narration track type 때문에 approved TTS asset이 target narration clip에 반영되지 않는 문제를 막는다
3. review approval mutation, preview renderer, CapCut export가 narration track type 해석에서 더 같은 canonical 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 118. 2026-07-04 output operator copy mixed-case review status prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 operator copy prompt surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 operator-facing preview/export guidance prompt에 `timeline["review_status"]`를 raw 문자열 그대로 넣고 있어, legacy `" APPROVED "` 같은 mixed-case stale shape가 runtime/operator copy 입력 surface에 그대로 남고 있었다
- strict TDD로 `test_output_operator_copy_builder_canonicalizes_mixed_case_review_status_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 `Review status:  APPROVED `를 그대로 담는 RED를 확인했다
- 최소 수정으로 output operator copy builder에 review status canonical helper를 추가해 `strip().lower()` 기준으로 정리하고, prompt surface가 canonical lowercase status를 유지하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, TTS approval/output truth, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 operator copy prompt surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - operator copy / preview review-status 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - operator copy prompt의 review-status canonicalization 한 점 수정이라 exact + output guidance 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy builder가 legacy mixed-case `review_status`도 canonical lowercase 상태로 prompt에 반영한다
2. preview/export guidance prompt가 raw stale review status 문자열을 그대로 runtime 입력으로 넘기지 않는다
3. operator copy prompt surface가 output gating/readiness와 preview visible status의 canonical status 기준과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 119. 2026-07-04 heuristic review guidance mixed-case approved status closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance approved-status 해석 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `HeuristicReviewGuidanceBuilder.build(...)`는 blocker가 없는 review snapshot에서도 `review_status`를 raw 문자열로 읽고 있어, legacy `" APPROVED "` 같은 mixed-case stale shape를 approved가 아니라 `승인 대기`로 오판하고 있었다
- strict TDD로 `test_heuristic_review_guidance_builder_canonicalizes_mixed_case_approved_review_status` exact regression을 먼저 추가했고, 실제로 guidance summary가 `Timeline is ready for approval before output generation.`으로 잘못 나오는 RED를 확인했다
- 최소 수정으로 review guidance에 review status canonical helper를 추가해 heuristic fallback 분기와 prompt builder가 모두 `strip().lower()` 기준을 사용하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, TTS approval/output truth, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance status 해석 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance / review-status 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - heuristic review guidance의 approved-status canonicalization 한 점 수정이라 exact + review guidance 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. heuristic review guidance가 legacy mixed-case `review_status`도 canonical lowercase 승인 상태로 해석한다
2. blocker가 없는 approved review snapshot은 stale casing 때문에 `승인 대기` 안내로 되돌아가지 않는다
3. review guidance fallback 분기와 prompt surface가 output gating/readiness와 더 같은 review-status 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 127. 2026-07-04 output operator copy mixed-case track type prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 operator copy `track summary` prompt surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 operator-facing preview/export guidance prompt에서 `track_summary`의 `track_type`을 raw 문자열 그대로 넣고 있어, legacy `" NARRATION "` 같은 mixed-case stale shape가 runtime/operator copy 입력 surface에 그대로 남고 있었다
- strict TDD로 `test_output_operator_copy_builder_canonicalizes_mixed_case_track_type_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 `{'track_type': ' NARRATION '}`를 그대로 담는 RED를 확인했다
- 최소 수정으로 output operator copy builder에 track type canonical helper를 추가해 `strip().lower()` 기준으로 정리하고, prompt의 `track_summary` surface가 canonical lowercase track type을 유지하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 operator copy prompt의 track summary surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - operator copy / preview / review guidance 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - operator copy prompt의 track-type canonicalization 한 점 수정이라 exact + 인접 prompt/output surface evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy builder가 legacy mixed-case `track_type`도 canonical lowercase track type으로 prompt에 반영한다
2. preview/export guidance prompt가 raw stale track type 문자열을 그대로 runtime 입력으로 넘기지 않는다
3. operator copy prompt의 track summary surface가 preview visible track summary와 더 같은 canonical track-type 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 120. 2026-07-04 review approval mixed-case review flag cleanup closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review recommendation approve cleanup 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 `should_keep_review_flag(...)`는 stale review flag의 `code`를 `strip()`만 하고 raw casing으로 비교하고 있어, legacy `" BROLL_REVIEW_REQUIRED "` 같은 mixed-case stale flag는 마지막 pending recommendation 승인 뒤에도 같은 blocker로 인식하지 못해 제거하지 못하고 있었다
- strict TDD로 `test_approving_last_pending_recommendation_removes_mixed_case_review_flag_code_for_same_segment` exact regression을 먼저 추가했고, 실제로 approve 응답의 `review_status`가 `draft`가 아니라 `blocked`로 남는 RED를 확인했다
- 최소 수정으로 review action mutation에 review flag code canonical helper를 추가해 lowercase code 기준으로 비교하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 approve cleanup의 mixed-case review flag code 해석 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review flag cleanup / output gating 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - mixed-case review flag cleanup 한 점 수정이라 exact + approve/output 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. 마지막 pending recommendation approve가 mixed-case stale review flag code도 canonical lowercase 기준으로 제거한다
2. blocker가 없는 approve 결과가 stale review flag casing 때문에 `blocked`로 잘못 남지 않는다
3. output gating에서 mixed-case flag code를 blocker로 읽는 경로와 approve cleanup에서 mixed-case flag code를 제거하는 경로가 더 같은 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 121. 2026-07-04 review snapshot persisted guidance mixed-case approved status reuse closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review snapshot persisted guidance 재사용 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `get_review_snapshot(...)`는 timeline 쪽 `review_status`와 persisted review state를 raw 문자열로 직접 비교하고 있어, legacy `" APPROVED "` 같은 mixed-case stale status면 같은 승인 상태여도 persisted operator guidance를 재사용하지 못하고 다시 생성 경로로 빠지고 있었다
- strict TDD로 `test_local_pipeline_review_snapshot_reuses_persisted_guidance_for_mixed_case_approved_status` exact regression을 먼저 추가했고, 실제로 persisted guidance를 바로 돌려주지 않고 review guidance builder를 다시 호출하는 RED를 확인했다
- 최소 수정으로 local pipeline에 runtime review status canonical helper를 추가하고, persisted guidance reuse/save 조건 비교를 `strip().lower()` 기준으로 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, TTS approval/output truth, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot guidance reuse의 status 비교 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - persisted guidance / review-status 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot persisted guidance reuse의 mixed-case approved status 비교 한 점 수정이라 exact + guidance reuse 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot이 legacy mixed-case `review_status`도 canonical lowercase 승인 상태로 비교해 persisted guidance를 재사용한다
2. 같은 승인 상태인데 raw casing 차이 때문에 operator guidance를 불필요하게 다시 만들지 않는다
3. review guidance fallback, operator copy prompt, persisted guidance reuse가 review-status 비교에서 더 같은 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 122. 2026-07-04 timeline builder mixed-case applied recommendation type surface closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 timeline builder applied recommendation surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/timeline_builder.py`는 approved TTS recommendation의 분기 판단에는 canonical type을 쓰고 있었지만, `_recommendation_payload(...)`가 returned surface의 `recommendation_type`을 raw 문자열로 남기고 있어 legacy `" TTS_REPLACEMENT "` 같은 mixed-case stale shape가 `applied_recommendations` surface에 그대로 남고 있었다
- strict TDD로 `test_timeline_builder_canonicalizes_mixed_case_applied_recommendation_type_surface` exact regression을 먼저 추가했고, 실제로 `timeline.applied_recommendations[0]["recommendation_type"] == " TTS_REPLACEMENT "` RED를 확인했다
- 최소 수정으로 timeline builder `_recommendation_payload(...)`도 `recommendation_type`을 canonical lowercase로 정리해 builder output surface가 approved TTS read-path truth와 같은 기준을 사용하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline builder recommendation_type surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - timeline builder / TTS output 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline builder applied recommendation type surface canonicalization 한 점 수정이라 exact + TTS/output 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline builder가 legacy mixed-case `recommendation_type`도 canonical lowercase type으로 surface한다
2. approved TTS recommendation이 builder output surface에서 raw stale casing을 그대로 남기지 않는다
3. builder output surface, preview renderer, output read-path가 recommendation type 해석에서 더 같은 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 82. 2026-07-04 recommendation row trimmed broll provider trace closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 recommendation row read-path의 작은 stale-shape 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `list_recommendation_rows(...)`는 persisted row의 `recommendation_type`을 raw 문자열로 비교하고 있어 whitespace가 섞인 stale `broll` row에서 missing `provider_trace` fallback을 `heuristic_fallback`이 아니라 `rule_based_fallback`으로 잘못 채우고 있었다
- strict TDD로 `test_store_list_recommendation_rows_uses_trimmed_broll_type_for_default_provider_trace` exact regression을 먼저 추가했고, 실제로 `provider_trace.final_provider == "rule_based_fallback"` RED를 확인했다
- 원인은 recommendation row read path의 default provider-trace 분기가 approve/review snapshot 쪽과 달리 canonical trimmed recommendation type을 재사용하지 않던 점이었다
- 최소 수정으로 `list_recommendation_rows(...)`의 fallback provider-trace 분기도 `str(payload["recommendation_type"] or "").strip()` 기준으로 비교하도록 좁혀, stale whitespace `broll` row도 기존 review/output truth와 같은 `heuristic_fallback`을 유지하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 recommendation row read-path의 fallback trace 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused verification
  - `tests/test_api.py`
    - `test_store_list_recommendation_rows_uses_trimmed_broll_type_for_default_provider_trace`
    - `test_store_list_recommendation_rows_treats_legacy_string_false_columns_as_false`
    - 결과: `2 passed`
  - `tests/test_review_timeline.py`
    - `test_review_snapshot_uses_trimmed_broll_type_for_default_provider_trace`
    - 결과: `1 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - recommendation row read-path의 trimmed type comparison 한 점 수정이라 exact + 인접 read-path focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. recommendation row read path가 whitespace가 섞인 stale `broll` recommendation type도 canonical B-roll type으로 인식한다
2. missing `provider_trace` legacy row도 downstream read path에서 `heuristic_fallback` trace를 유지한다
3. recommendation row read truth와 approve/review snapshot provider-trace fallback truth가 같은 trim 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 83. 2026-07-04 preflight prediction targeted-segment string false review_required closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `preflight contract`에 가장 가까운 prediction helper stale-shape 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `_build_preflight_review_prediction(...)`는 targeted segment의 `review_required`를 raw `bool(...)`로 판정하고 있어, legacy string false shape인 `review_required="false"`를 blocker로 오판해 `draft`여야 할 prediction을 `blocked`로 뒤집고 있었다
- strict TDD로 `test_preflight_review_prediction_ignores_string_false_targeted_segment_review_required` exact regression을 먼저 추가했고, 실제로 helper 반환값이 `draft`가 아니라 `blocked`가 되는 RED를 확인했다
- 원인은 preflight prediction helper가 source recommendation/review flag 쪽에는 normalization을 쓰면서도 targeted segment review-required 판정만 raw truthiness를 남겨 두고 있던 점이었다
- 최소 수정으로 targeted segment review-required 판정도 `_normalize_boolish_response(...)` 기준으로 맞춰, legacy false-like shape가 clean rerun scope를 blocker로 뒤집지 않게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preflight prediction helper의 targeted-segment bool 판정 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_preflight_review_prediction_ignores_string_false_targeted_segment_review_required or test_editing_session_api_normalizes_string_false_review_required_in_preflight_targeted_segments or test_editing_session_api_marks_preflight_as_draft_for_clean_rerun_scope"`
  - 결과: `3 passed`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-backend -BackendPattern "normalizes_string_false_review_required_in_preflight_targeted_segments or marks_preflight_as_draft_for_clean_rerun_scope"`
  - 결과: `2 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preflight prediction helper의 targeted segment bool 판정 한 점 수정이라 exact + 인접 preflight focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preflight prediction helper가 targeted segment의 legacy string false `review_required="false"`를 blocker로 오판하지 않는다
2. clean rerun scope prediction이 helper direct call과 API preflight read path 모두에서 같은 `draft` truth를 유지한다
3. targeted segment bool 판정이 source recommendation/review flag normalization과 같은 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 84. 2026-07-04 recommendation response mixed-case decision-state closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 `TTS approval/output`에 같이 닿는 recommendation response helper 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `_normalize_recommendations_for_response(...)`는 `decision_state`를 `strip()`만 하고 raw casing을 그대로 남기고 있어, legacy 또는 mixed-case shape인 `" Approved "`가 API response에서 canonical `"approved"`가 아니라 `"Approved"`로 surface되고 있었다
- strict TDD로 `test_recommendation_response_normalization_canonicalizes_mixed_case_decision_state` exact regression을 먼저 추가했고, 실제로 normalized response의 `decision_state == "Approved"` RED를 확인했다
- 원인은 recommendation response helper가 bool-ish fields와 recommendation type은 canonicalize하면서도 decision-state casing만 정규화하지 않고 있던 점이었다
- 최소 수정으로 response helper의 `decision_state`도 `strip().lower()` 기준으로 정리해, approve/timeline/review snapshot read family가 같은 lowercase surface를 유지하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 recommendation response helper의 decision-state surface 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_recommendation_response_normalization_canonicalizes_mixed_case_decision_state or test_review_snapshot_api_approve_tts_replacement_surfaces_approved_decision_state_in_read_paths or test_timeline_api_normalizes_legacy_string_false_pending_recommendation_fields"`
  - 결과: `3 passed`
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "surfaces_approved_decision_state_in_read_paths or normalizes_legacy_string_false_pending_recommendation_fields"`
  - 결과: `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - recommendation response helper의 decision-state canonicalization 한 점 수정이라 exact + 인접 output-gating focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. recommendation response helper가 mixed-case 또는 whitespace decision-state shape를 canonical lowercase로 정리한다
2. approve/timeline/review snapshot read family가 같은 `approved` surface를 유지한다
3. decision-state surface 정규화가 recommendation type / bool field 정규화와 같은 response helper 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 85. 2026-07-04 recommendation response mixed-case recommendation type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 `TTS approval/output`에 같이 닿는 recommendation response helper의 recommendation type surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `_normalize_recommendations_for_response(...)`는 `recommendation_type`을 `strip()`만 하고 raw casing을 그대로 남기고 있어, legacy 또는 mixed-case shape인 `" TTS_REPLACEMENT "`가 API response에서 canonical `"tts_replacement"`가 아니라 `"TTS_REPLACEMENT"`로 surface되고 있었다
- strict TDD로 `test_recommendation_response_normalization_canonicalizes_mixed_case_recommendation_type` exact regression을 먼저 추가했고, 실제로 normalized response의 `recommendation_type == "TTS_REPLACEMENT"` RED를 확인했다
- 원인은 recommendation response helper가 bool-ish fields와 decision-state는 정리해도 recommendation type casing은 canonicalize하지 않고 있던 점이었다
- 최소 수정으로 response helper의 `recommendation_type`도 `strip().lower()` 기준으로 정리해, approve/timeline/review snapshot/TTS read family가 같은 lowercase surface를 유지하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 recommendation response helper의 type surface 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_recommendation_response_normalization_canonicalizes_mixed_case_recommendation_type or test_recommendation_response_normalization_canonicalizes_mixed_case_decision_state or test_review_snapshot_api_approve_tts_replacement_surfaces_approved_decision_state_in_read_paths"`
  - 결과: `3 passed`
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "surfaces_approved_decision_state_in_read_paths or normalizes_legacy_string_false_pending_recommendation_fields"`
  - 결과: `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - recommendation response helper의 recommendation type canonicalization 한 점 수정이라 exact + 인접 output-gating focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. recommendation response helper가 mixed-case 또는 whitespace recommendation type shape를 canonical lowercase로 정리한다
2. approve/timeline/review snapshot/TTS read family가 같은 lowercase recommendation type surface를 유지한다
3. recommendation type surface 정규화가 decision-state / bool field 정규화와 같은 response helper 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 86. 2026-07-04 approve/read path mixed-case broll recommendation type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 approve mutation과 downstream read path 사이의 mixed-case recommendation type 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`, `packages/core-engine/src/videobox_core_engine/local_pipeline.py`, `packages/storage-abstractions/src/videobox_storage/local_project_store.py`는 mixed-case `recommendation_type`을 raw `strip()` 기준으로만 비교하고 있어, pending `BROLL` approve 뒤 applied recommendation이 review snapshot / refreshed timeline surface에서 빠지거나 fallback `provider_trace`가 `rule_based_fallback`으로 틀어질 수 있었다
- strict TDD로 `test_review_snapshot_api_approve_broll_uses_mixed_case_recommendation_type_for_provider_trace_fallback` exact regression을 먼저 추가했고, 실제로 approve 응답의 `applied_recommendations`가 비어 있는 RED를 확인했다
- 원인은 approve mutation의 fallback trace 선택, runtime timeline hydration의 supported-type 판정, store review snapshot/read path의 supported-type 및 fallback trace 판정이 모두 mixed-case canonicalization 없이 따로 비교하던 점이었다
- 최소 수정으로 세 경로에 recommendation type `strip().lower()` canonicalization helper를 추가해, mixed-case `BROLL`도 approve 이후 canonical B-roll type으로 판정되도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 approve/read path의 mixed-case recommendation type 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_review_snapshot_api_approve_broll_uses_mixed_case_recommendation_type_for_provider_trace_fallback or test_review_snapshot_api_approve_broll_uses_trimmed_recommendation_type_for_provider_trace_fallback or test_recommendation_response_normalization_canonicalizes_mixed_case_recommendation_type"`
  - 결과: `3 passed`
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "approve_broll_uses_mixed_case_recommendation_type_for_provider_trace_fallback or approve_broll_uses_trimmed_recommendation_type_for_provider_trace_fallback or canonicalizes_mixed_case_recommendation_type"`
  - 결과: `3 passed`
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - 결과:
    - backend output-gating `24 passed`
    - backend preflight `57 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - approve mutation + runtime hydration + store read path의 mixed-case canonicalization 경계는 exact + output-focused + current-focused-parallel evidence가 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. pending `BROLL` approve도 mixed-case recommendation type shape를 canonical B-roll type으로 판정한다
2. approve 응답과 refreshed timeline read path가 같은 applied recommendation surface를 유지한다
3. mixed-case type에서도 fallback provider trace가 B-roll 기준 `heuristic_fallback`으로 일관되게 유지된다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 87. 2026-07-04 preview renderer mixed-case tts recommendation type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 preview renderer의 mixed-case recommendation type 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/preview_renderer.py`는 applied recommendation의 `recommendation_type`을 raw `strip()` 기준으로만 비교하고 있어, mixed-case `TTS_REPLACEMENT` shape를 approved TTS override로 인식하지 못하고 preview HTML에 original narration source를 계속 노출하고 있었다
- strict TDD로 `test_preview_renderer_matches_mixed_case_tts_recommendation_type_for_narration_source` exact regression을 먼저 추가했고, 실제로 preview HTML이 `tts_selected.wav`가 아니라 original narration source를 노출하는 RED를 확인했다
- 원인은 preview renderer의 TTS applied-segment 판정이 trimmed whitespace는 처리해도 recommendation type casing canonicalization은 하지 않던 점이었다
- 최소 수정으로 preview renderer에 recommendation type `strip().lower()` canonicalization helper를 추가해, mixed-case `TTS_REPLACEMENT`도 canonical TTS override로 인식하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preview/TTS read truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused verification
  - `py -m pytest tests/test_api.py -q -k "test_preview_renderer_matches_mixed_case_tts_recommendation_type_for_narration_source or test_preview_renderer_matches_trimmed_tts_recommendation_type_for_narration_source or test_preview_renderer_treats_string_false_tts_recommendation_review_required_as_false"`
  - 결과: `3 passed`
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "matches_mixed_case_tts_recommendation_type_for_narration_source or matches_trimmed_tts_recommendation_type_for_narration_source or string_false_tts_recommendation_review_required_as_false"`
  - 결과: `3 passed`
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - 결과:
    - backend output-gating `24 passed`
    - backend preflight `57 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview renderer의 mixed-case TTS type canonicalization 한 점 수정이라 exact + output-focused + current-focused-parallel evidence가 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preview renderer가 mixed-case `TTS_REPLACEMENT` shape도 canonical TTS override로 인식한다
2. preview HTML narration source가 mixed-case type에서도 selected TTS source를 유지한다
3. preview/TTS read truth가 trimmed type / bool-ish normalization 규칙과 같은 canonical lowercase type 기준을 사용한다

## 88. 2026-07-04 capcut export mixed-case tts recommendation type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 바로 닿는 CapCut export adapter의 mixed-case recommendation type 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`는 applied recommendation의 `recommendation_type`을 raw `strip()` 기준으로만 비교하고 있어, mixed-case `TTS_REPLACEMENT` shape를 approved TTS override로 인식하지 못하고 CapCut voiceover track 첫 segment에 original narration source를 계속 남기고 있었다
- strict TDD로 `test_capcut_export_adapter_matches_mixed_case_tts_recommendation_type_for_segment_level_narration_sources` exact regression을 먼저 추가했고, 실제로 voiceover 첫 segment `source_uri`가 generated TTS asset이 아니라 original narration source로 남는 RED를 확인했다
- 원인은 CapCut export adapter의 narration override segment 계산이 trimmed whitespace는 처리해도 recommendation type casing canonicalization은 하지 않던 점이었다
- 최소 수정으로 adapter에 recommendation type `strip().lower()` canonicalization helper를 추가해, mixed-case `TTS_REPLACEMENT`도 canonical TTS override로 인식하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 CapCut export TTS read truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused verification
  - `py -m pytest tests/test_preview_export.py -q -k "test_capcut_export_adapter_matches_mixed_case_tts_recommendation_type_for_segment_level_narration_sources or test_capcut_export_adapter_matches_trimmed_tts_recommendation_type_for_segment_level_narration_sources or test_capcut_export_adapter_treats_string_false_tts_review_required_as_false_for_segment_level_narration_sources"`
  - 결과: `3 passed`
- broader fast-path verification
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - 결과:
    - backend output-gating `24 passed`
    - backend preflight `57 passed`
    - frontend preflight `25 passed`
- helper override note
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "matches_mixed_case_tts_recommendation_type_for_segment_level_narration_sources or matches_trimmed_tts_recommendation_type_for_segment_level_narration_sources or string_false_tts_review_required_as_false_for_segment_level_narration_sources"`
  - 결과: `279 deselected`
  - 판단:
    - 이번 exact 이름들은 현재 helper의 backend lane 수집 범위와 맞지 않아 direct focused pytest가 더 직접적인 evidence였다
- broader verification
  - 실행하지 않음
  - 판단:
    - CapCut export adapter의 mixed-case type canonicalization 한 점 수정이라 exact + family-focused + current-focused-parallel evidence가 직접적이다
    - latest full broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. CapCut export adapter가 mixed-case `TTS_REPLACEMENT` shape도 canonical TTS override로 인식한다
2. CapCut voiceover track source가 mixed-case type에서도 selected narration source를 유지한다
3. CapCut export TTS read truth가 preview renderer / trimmed type / bool-ish normalization 규칙과 같은 canonical lowercase type 기준을 사용한다

## 89. 2026-07-04 development operating rules promoted to top-level plan closeout

이번 후속 작업에서는 기능 slice를 넓히지 않고, 직전에 fast-path SSOT에 저장한 개발 운영 규정을 실제 프로젝트 개발 최상위 문서에도 연결하는 문서 경계 1개만 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `docs/development-fast-path.ko.md`의 `## 10. 고정 운영 규정`에는 운영 규정이 들어갔지만, 최상위 구현 계획서인 `docs/implementation-plan.ko.md` 상단에는 그 규정이 프로젝트 전역 기본값이라는 연결 고리가 아직 직접 적혀 있지 않았다
- 이 상태로 두면 다음 turn에 구현 계획서만 먼저 읽는 흐름에서 운영 규정이 최상위 기준으로 보이지 않을 수 있었다
- 최소 수정으로 `docs/implementation-plan.ko.md` 상단에 `docs/development-fast-path.ko.md ## 10`을 프로젝트 전역 개발 운영 규정으로 적용한다는 문장을 추가해, 계획서 실행 규칙과 운영 규정의 우선순위를 같은 입구에서 바로 확인할 수 있게 맞췄다
- 이번 수정은 기능 동작, 테스트 경로, SSOT 계약을 건드리지 않고 문서 상위 규칙 연결만 좁게 정리했다

이번 turn의 verification은 아래와 같다.

- `git status --short --branch`
  - clean branch 확인
- `git log -5 --oneline`
  - 직전 운영 규정 반영 커밋 확인
- SSOT 확인
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
  - `docs/development-fast-path.ko.md`
- diff 확인
  - 구현 계획서 상단 연결과 상태 문서 기록, closeout 문서 외 불필요한 변경이 없는지 확인

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. 개발 운영 규정이 fast-path 문서뿐 아니라 최상위 구현 계획서 입구에서도 바로 보인다
2. 이후 turn에서 계획서 우선 진입 시에도 운영 규정의 전역 적용 범위를 놓치지 않는다
3. 기능 slice와 운영 규정 SSOT의 문서 우선순위가 더 분명해졌다

## 90. 2026-07-04 timeline builder mixed-case tts recommendation type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 `timeline_builder`의 mixed-case recommendation type 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/timeline_builder.py`는 recommendation type을 raw `strip()` 기준으로만 비교하고 있어, mixed-case `TTS_REPLACEMENT` shape를 supported recommendation으로 유지하면서도 narration clip 반영 분기에서는 승인된 TTS override로 인식하지 못하고 있었다
- strict TDD로 `test_timeline_builder_applies_mixed_case_tts_replacement_type_to_narration_clip` exact regression을 먼저 추가했고, 실제로 narration clip `asset_uri`가 generated TTS asset이 아니라 original segment URI로 남는 RED를 확인했다
- 원인은 supported-type 필터와 narration/B-roll/BGM clip 반영 분기가 whitespace trim까지만 하고 recommendation type casing canonicalization은 하지 않던 점이었다
- 최소 수정으로 `timeline_builder`에 recommendation type `strip().lower()` helper를 추가하고 supported-type 판정과 narration/B-roll/BGM clip 반영 분기에 재사용해, mixed-case `TTS_REPLACEMENT`도 canonical TTS override로 인식하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline builder TTS read truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused verification
  - `py -m pytest tests/test_review_timeline.py -q -k "test_timeline_builder_applies_mixed_case_tts_replacement_type_to_narration_clip or test_timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip or test_review_snapshot_uses_trimmed_broll_type_for_default_provider_trace"`
  - 결과: `3 passed`
- helper override note
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "timeline_builder_applies_mixed_case_tts_replacement_type_to_narration_clip or timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip or review_snapshot_uses_trimmed_broll_type_for_default_provider_trace"`
  - 결과: `279 deselected`
  - 판단:
    - 이번 exact 이름들은 helper backend lane 기본 수집 범위와 맞지 않아 direct focused pytest가 더 직접적인 evidence였다
- broader fast-path verification
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - 첫 실행:
    - backend output-gating `1 failed`
    - backend preflight `1 failed`
    - 같은 `_create_timeline_review_project()` setup에서 `broll-recommendation` 응답이 `job_id`를 주지 못하는 비결정성 실패
  - 단일 exact 재검증:
    - `py -m pytest tests/test_api.py -q -k "test_approving_one_of_multiple_pending_recommendations_keeps_output_blocked_by_remaining_detail" -vv`
    - 결과: `1 passed`
  - 두 번째 `current-focused-parallel` 재실행:
    - backend output-gating `24 passed`
    - backend preflight `57 passed`
    - frontend preflight `25 passed`
  - 판단:
    - 첫 실패는 이번 수정의 직접 회귀라기보다 병렬 helper 실행의 일시적 비결정성으로 봤고, exact 재검증과 helper 재실행으로 현재 slice 기준 green을 다시 확인했다
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline builder mixed-case type canonicalization 한 점 수정이라 exact + 인접 focused + current-focused-parallel evidence가 직접적이다
    - latest full broader baseline은 기존 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline builder가 mixed-case `TTS_REPLACEMENT` shape도 canonical TTS override로 인식한다
2. narration clip `asset_uri`가 mixed-case type에서도 selected TTS source를 유지한다
3. timeline builder의 recommendation type 판정이 preview renderer / CapCut export / trimmed type canonicalization 규칙과 같은 canonical lowercase type 기준을 사용한다

## 91. 2026-07-04 partial regeneration mixed-case stale tts recommendation replacement closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`과 바로 이어지는 partial regeneration runtime의 mixed-case stale TTS recommendation 교체 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_tts_refresh_step(...)`는 source timeline `applied_recommendations` 정리 시 `recommendation_type`을 raw `strip()` 기준으로만 비교하고 있어, mixed-case `TTS_REPLACEMENT` stale recommendation이 남아 있으면 새 manual TTS selection이 기존 stale asset을 교체하지 못하고 있었다
- strict TDD로 `test_editing_session_api_replaces_mixed_case_stale_applied_tts_recommendation_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 partial regeneration result narration clip `asset_uri`가 stale mixed-case TTS asset URI 그대로 남는 RED를 확인했다
- 원인은 runtime `tts_refresh` stale recommendation 제거 분기가 whitespace trim까지만 하고 recommendation type casing canonicalization은 하지 않던 점이었다
- 최소 수정으로 `tts_refresh` stale recommendation 제거 비교도 기존 runtime helper `_canonical_runtime_recommendation_type(...)`를 재사용하게 맞춰, mixed-case `TTS_REPLACEMENT` stale recommendation도 새 manual TTS selection으로 정상 교체되게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration TTS refresh truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused adjacency verification
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_replaces_trimmed_stale_applied_tts_recommendation_when_running_partial_regeneration"`
  - 결과: `1 passed`
  - `py -m pytest tests/test_review_timeline.py -q -k "test_timeline_builder_applies_mixed_case_tts_replacement_type_to_narration_clip"`
  - 결과: `1 passed`
- attempted grouped verification
  - `py -m pytest tests/test_api.py -q -k "test_editing_session_api_replaces_mixed_case_stale_applied_tts_recommendation_when_running_partial_regeneration or test_editing_session_api_replaces_trimmed_stale_applied_tts_recommendation_when_running_partial_regeneration or test_timeline_builder_applies_mixed_case_tts_replacement_type_to_narration_clip"`
  - 결과:
    - mixed-case exact는 pass
    - `_create_timeline_review_project()` setup 안의 `broll-recommendation` 응답이 `job_id`를 주지 못하는 비결정성 failure가 재발
- helper note
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "replaces_mixed_case_stale_applied_tts_recommendation_when_running_partial_regeneration or replaces_trimmed_stale_applied_tts_recommendation_when_running_partial_regeneration or timeline_builder_applies_mixed_case_tts_replacement_type_to_narration_clip"`
  - 결과: 인접 테스트에서 같은 `_create_timeline_review_project()` setup 비결정성 failure가 재발
  - 판단:
    - 이번 slice의 직접 회귀라기보다 existing helper/setup instability로 봤고, exact + 인접 개별 재검증을 현재 근거로 채택했다
- broader fast-path verification
  - `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - 결과:
    - backend output-gating lane와 backend preflight lane에서 같은 `_create_timeline_review_project()` / `broll-recommendation` setup failure가 재현
    - frontend preflight `25 passed`
  - 판단:
    - current-focused helper는 현재 브랜치에 이미 존재하는 setup instability 때문에 이번 turn close 근거로 쓰기 어렵고, 이번 코드 변경의 직접 영향 증거는 exact + 인접 개별 재검증이 더 정확했다
- broader verification
  - 실행하지 않음
  - 판단:
    - partial regeneration runtime mixed-case TTS replacement 한 점 수정이라 exact + adjacency evidence가 직접적이다
    - 다만 helper/setup instability는 별도 리스크로 남긴다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration runtime `tts_refresh`가 mixed-case `TTS_REPLACEMENT` stale recommendation도 canonical lowercase type 기준으로 제거한다
2. partial regeneration result narration clip `asset_uri`가 stale mixed-case TTS asset 대신 새 manual TTS source를 유지한다
3. partial regeneration runtime의 TTS recommendation type 판정이 timeline builder / preview renderer / CapCut export와 같은 canonical lowercase type 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 38. 2026-07-04 capcut export string false tts review_required closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, 방금 닫은 CapCut export trimmed type 경계와 같은 출력 family에서 `TTS approval/output`에 바로 닿는 legacy bool-shape 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`는 applied TTS recommendation의 `auto_apply_allowed` / `review_required`를 raw `bool(...)`로 읽고 있어, legacy string false shape인 `review_required="false"`를 truthy로 오판해 narration override segment를 놓치고 있었다
- strict TDD로 `test_capcut_export_adapter_treats_string_false_tts_review_required_as_false_for_segment_level_narration_sources` exact regression을 먼저 추가했고, 실제로 export manifest의 first `voiceover` segment가 generated TTS source가 아니라 original narration source로 내려가는 RED를 확인했다
- 최소 수정으로 CapCut export adapter에도 bool-ish normalization helper를 추가해 `auto_apply_allowed/review_required`를 canonical bool로 해석하도록 맞춰, legacy string false shape여도 segment-level narration source override truth를 유지하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 export output 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused verification
  - `tests/test_preview_export.py` focused `3 passed`
  - `tests/test_api.py` preview/export flow focused `2 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - CapCut export adapter의 bool-ish normalization 한 점 수정이라 exact + family-focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. CapCut export adapter가 whitespace가 섞인 stale approved `tts_replacement` type도 canonical TTS override로 인식함
2. CapCut export adapter가 legacy string false `review_required="false"`도 canonical false로 해석함
3. preview/export output이 approved TTS selection truth를 같은 기준으로 유지함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 37. 2026-07-04 capcut export trimmed tts recommendation type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, 방금 닫은 preview renderer와 같은 출력 family에서 `TTS approval/output`에 가장 가까운 CapCut export adapter의 trimmed recommendation type regression 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`는 applied recommendation의 `recommendation_type` 비교에 raw equality를 쓰고 있어, `" tts_replacement "`처럼 whitespace가 섞인 stale approved shape를 narration override segment로 인식하지 못하고 CapCut voiceover track 첫 segment를 original narration source로 유지하고 있었다
- strict TDD로 `test_capcut_export_adapter_matches_trimmed_tts_recommendation_type_for_segment_level_narration_sources` exact regression을 먼저 추가했고, 실제로 export manifest의 first `voiceover` segment가 generated TTS source가 아니라 original narration source로 내려가는 RED를 확인했다
- 최소 수정으로 CapCut export adapter의 narration override segment 판정도 `recommendation_type.strip() == "tts_replacement"` 기준을 사용하도록 맞춰, stale whitespace type shape여도 segment-level narration source override truth를 유지하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 export output 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- focused verification
  - `tests/test_preview_export.py` focused `2 passed`
  - `tests/test_api.py` export/preview flow focused `1 passed`
  - helper output-gating override `1 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - CapCut export adapter의 trimmed recommendation-type 한 점 수정이라 exact + family-focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preview renderer가 whitespace가 섞인 stale approved `tts_replacement` type도 canonical TTS override로 인식함
2. CapCut export adapter도 whitespace가 섞인 stale approved `tts_replacement` type을 canonical TTS override로 인식함
3. preview/export output이 approved TTS selection truth를 같은 기준으로 유지함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 36. 2026-07-04 preview renderer trimmed tts recommendation type closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 실제 출력 경계로 남아 있던 preview renderer의 trimmed recommendation type regression 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/preview_renderer.py`는 applied recommendation의 `recommendation_type` 비교에 raw equality를 쓰고 있어, `" tts_replacement "`처럼 whitespace가 섞인 stale approved shape를 TTS override로 인식하지 못하고 preview HTML narration source를 original narration source로 되돌리고 있었다
- strict TDD로 `test_preview_renderer_matches_trimmed_tts_recommendation_type_for_narration_source` exact regression을 먼저 추가했고, 실제로 preview HTML에 `tts_selected.wav` 대신 original narration source가 노출되는 RED를 확인했다
- 최소 수정으로 preview renderer의 TTS segment 판정도 `recommendation_type.strip() == "tts_replacement"` 기준을 사용하도록 맞춰, stale whitespace type shape여도 selected narration source를 계속 유지하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preview output 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview renderer의 trimmed recommendation-type 한 점 수정이라 exact + family-focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preview renderer가 legacy false-like recommendation fields를 canonical bool로 해석함
2. preview renderer가 whitespace가 섞인 stale approved `tts_replacement` type도 canonical TTS override로 인식함
3. preview HTML narration source가 approved TTS selection truth를 유지함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 35. 2026-07-04 partial regeneration trimmed stale applied bgm replacement closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지하되, 이미 닫은 TTS/B-roll trim family와 같은 자리에서 `local_pipeline` partial regeneration output path에 남아 있던 가장 작은 BGM 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- partial regeneration runtime의 `music_refresh`는 source timeline `applied_recommendations`에 whitespace가 섞인 stale approved `recommendation_type=" bgm "`가 남아 있으면 기존 applied recommendation을 제거하지 못해 stale music clip과 새 manual music clip을 함께 남기고 있었다
- strict TDD로 `test_editing_session_api_replaces_trimmed_stale_applied_bgm_recommendation_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 bgm track 첫 clip이 `music_manual_001`이 아니라 stale `music_stale_001`로 남고 manual clip이 뒤에 추가되는 RED를 확인했다
- 원인은 `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_music_refresh_step(...)`가 stale applied recommendation 제거 시 `recommendation_type` 비교에 `strip()`을 쓰지 않던 점이었다
- 최소 수정으로 `music_refresh`도 TTS/B-roll과 같은 canonical trim 비교를 사용하도록 맞춰, manual music override가 stale whitespace recommendation type을 덮어쓰는 runtime truth를 유지하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration music replacement 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - 같은 trim family의 `music_refresh` 한 점 수정이라 exact + family-focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration runtime의 `tts_refresh`가 stale trimmed applied TTS recommendation을 manual selection truth로 교체함
2. partial regeneration runtime의 `broll_refresh`가 stale trimmed applied B-roll recommendation을 manual selection truth로 교체함
3. partial regeneration runtime의 `music_refresh`도 stale trimmed applied BGM recommendation을 manual selection truth로 교체함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 57. 2026-07-04 review snapshot helper unknown pending recommendation surface closeout

이번 후속 작업에서는 direct review-snapshot helper의 stale recommendation family를 한 단계 더 좁혀, unknown legacy pending recommendation이 status는 막지 않더라도 `pending_recommendations` surface에는 blocker처럼 남는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `build_review_snapshot(...)`는 helper status 계산은 이미 canonical blocker만 보도록 좁혀졌지만, `pending_recommendations` surface는 `decision_state="pending"`만 보면 recommendation type validity와 무관하게 그대로 남기고 있었다
- strict TDD로 `test_store_build_review_snapshot_filters_unknown_pending_recommendation_from_surface` exact regression을 먼저 추가했고, 실제로 `pending_recommendations`에 `legacy_overlay_pick` stale entry가 그대로 남는 RED를 확인했다
- 최소 수정으로 direct helper pending surface도 canonical blocking pending recommendation만 유지하도록 좁혀, unknown / non-blocking pending recommendation은 status뿐 아니라 helper surface에서도 blocker처럼 남지 않게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot helper pending-surface truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot helper unknown-pending surface filtering 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot direct helper가 unknown / non-blocking `timeline_pending_recommendations` shape를 `pending_recommendations` surface에 blocker처럼 남기지 않음
2. helper status truth와 pending surface truth가 stale recommendation family에서 같은 기준을 사용함
3. helper pending surface와 runtime output gating / preflight read truth가 같은 canonical blocker 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 58. 2026-07-04 timeline persistence unknown pending recommendation initial status closeout

이번 후속 작업에서는 direct review-snapshot helper와 output gating truth를 다시 넓히지 않고, 그 바로 아래 persistence initial review state가 unknown pending recommendation stale entry 하나 때문에 `blocked`로 저장되는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `save_timeline_run(...)`는 initial review status를 계산할 때 pending/applied bucket 안 recommendation의 normalized `decision_state == "pending"`만 보면 blocker로 세고 있어, `legacy_overlay_pick` 같은 unknown recommendation type도 `blocked` 초기 상태로 저장하고 있었다
- strict TDD로 `test_store_save_timeline_run_ignores_unknown_pending_recommendation_when_setting_initial_status` exact regression을 먼저 추가했고, 실제로 `review_state["status"] == "blocked"` RED를 확인했다
- 최소 수정으로 persistence initial status 계산도 canonical blocking pending recommendation만 blocker로 세도록 좁혀, unknown / non-blocking pending recommendation 하나만으로는 `draft` truth를 유지하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline persistence initial-status truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline persistence initial-status blocker classification 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline persistence initial review state가 unknown / non-blocking `pending_recommendations` shape 하나만으로 `blocked`를 저장하지 않음
2. canonical blocking pending recommendation이 없는 경우 persisted initial review state가 `draft` truth를 유지함
3. persistence initial-status truth와 review snapshot helper / runtime output gating truth가 같은 canonical blocker 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 59. 2026-07-04 timeline API unknown applied recommendation surface closeout

이번 후속 작업에서는 이미 닫힌 pending-like misbucketed applied 경계를 다시 넓히지 않고, timeline API read path에 남아 있던 unknown stale recommendation applied-surface 누수 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_hydrate_timeline_review_status(...)`는 applied recommendation read path에서 pending-like blocker만 제외하고 있어, `legacy_overlay_pick` 같은 unknown recommendation type stale entry는 approved timeline의 `applied_recommendations` surface에 그대로 남기고 있었다
- strict TDD로 `test_timeline_api_filters_unknown_type_entry_misbucketed_into_applied_recommendations` exact regression을 먼저 추가했고, 실제로 `payload["applied_recommendations"]`에 stale unknown recommendation이 그대로 남는 RED를 확인했다
- 최소 수정으로 timeline API applied surface도 canonical supported recommendation type만 유지하도록 좁혀, unknown / non-blocking applied stale entry는 user-facing surface에서 제거되게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline API applied-surface truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline API applied-surface filtering 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline API read path가 unknown / non-blocking `applied_recommendations` stale entry를 applied surface에 남기지 않음
2. canonical supported recommendation type만 user-facing applied surface에 유지됨
3. timeline API applied surface truth와 pending blocker read truth가 stale recommendation family에서 더 일관된 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 60. 2026-07-04 review snapshot helper unknown applied recommendation surface closeout

이번 후속 작업에서는 timeline API applied-surface truth를 다시 넓히지 않고, direct review-snapshot helper override 입력에 남아 있던 unknown applied stale recommendation surface 누수 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `build_review_snapshot(...)`는 applied surface를 만들 때 `decision_state="approved"`만 보면 recommendation type validity와 무관하게 그대로 남기고 있어, `legacy_overlay_pick` 같은 unknown recommendation type stale entry를 applied surface에 계속 노출하고 있었다
- strict TDD로 `test_store_build_review_snapshot_filters_unknown_applied_recommendation_from_surface` exact regression을 먼저 추가했고, 실제로 `snapshot["applied_recommendations"]`에 stale unknown recommendation이 그대로 남는 RED를 확인했다
- 최소 수정으로 direct helper applied surface도 canonical supported recommendation type만 유지하도록 좁혀, unknown / non-blocking applied stale entry는 helper surface에서 제거되게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot helper applied-surface truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot helper applied-surface filtering 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot direct helper가 unknown / non-blocking `timeline_applied_recommendations` stale entry를 applied surface에 남기지 않음
2. canonical supported recommendation type만 helper applied surface에 유지됨
3. review snapshot helper applied surface truth와 timeline API read truth가 stale recommendation family에서 더 일관된 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 61. 2026-07-04 timeline builder unknown applied recommendation surface closeout

이번 후속 작업에서는 helper/API applied-surface truth를 다시 넓히지 않고, partial regeneration runtime이 직접 의존하는 timeline builder source-truth에 남아 있던 unknown applied stale recommendation surface 누수 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/timeline_builder.py`의 `build(...)`는 recommendation을 normalized bool fields만 보고 분류하고 있어, `legacy_overlay_pick` 같은 unknown recommendation type stale entry도 `auto_apply_allowed=true` / `review_required=false`이면 applied surface에 그대로 남기고 있었다
- strict TDD로 `test_timeline_builder_filters_unknown_applied_recommendation_from_surface` exact regression을 먼저 추가했고, 실제로 `timeline.applied_recommendations`에 stale unknown recommendation이 그대로 남는 RED를 확인했다
- 최소 수정으로 builder도 canonical supported recommendation type만 recommendation flow에 반입하도록 좁혀, unknown / non-blocking applied stale entry는 source-truth 단계에서 제거되게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline builder source-truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline builder source-truth filtering 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline builder가 unknown / non-blocking recommendation stale entry를 applied/pending surface에 반입하지 않음
2. canonical supported recommendation type만 builder source-truth에 유지됨
3. builder source-truth와 review snapshot helper / timeline API applied surface truth가 stale recommendation family에서 더 일관된 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 62. 2026-07-04 timeline builder review snapshot unknown applied recommendation surface closeout

이번 후속 작업에서는 timeline builder 본체 applied-surface truth를 다시 넓히지 않고, 같은 파일의 review snapshot direct dict 입력면에 남아 있던 unknown applied stale recommendation surface 누수 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/timeline_builder.py`의 `build_review_snapshot(...)`는 recommendation을 bool fields만 보고 분류하고 있어, `legacy_overlay_pick` 같은 unknown recommendation type stale entry도 `auto_apply_allowed=true` / `review_required=false`이면 applied surface에 그대로 남기고 있었다
- strict TDD로 `test_timeline_builder_review_snapshot_filters_unknown_applied_recommendation_from_surface` exact regression을 먼저 추가했고, 실제로 `snapshot["applied_recommendations"]`에 stale unknown recommendation이 그대로 남는 RED를 확인했다
- 최소 수정으로 builder review snapshot도 canonical supported recommendation type만 recommendation flow에 반입하도록 좁혀, unknown / non-blocking applied stale entry는 source-truth 단계에서 제거되게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline builder review snapshot truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline builder review snapshot source-truth filtering 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline builder review snapshot이 unknown / non-blocking recommendation stale entry를 applied/pending surface에 반입하지 않음
2. canonical supported recommendation type만 builder review snapshot truth에 유지됨
3. timeline builder 본체와 builder review snapshot truth가 stale recommendation family에서 더 일관된 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 81. 2026-07-04 partial regeneration trimmed stale applied broll replacement closeout

이번 후속 작업에서는 방금 닫은 partial regeneration `tts_refresh` trim family를 `broll_refresh`까지 이어, stale approved recommendation 교체 경계 1개만 다시 닫았다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_broll_refresh_step(...)`도 refresh 전에 기존 B-roll recommendation을 걷어낼 때 raw `recommendation_type` 비교를 써 source timeline에 `" broll "` stale approved recommendation이 남아 있으면 제거하지 못하고 carry-forward하고 있었다
- strict TDD로 `test_editing_session_api_replaces_trimmed_stale_applied_broll_recommendation_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 partial regeneration 결과 broll track에 stale clip과 새 manual clip이 함께 남는 RED를 확인했다
- 최소 수정으로 `broll_refresh` 기존 recommendation 제거 분기도 canonical trimmed type 기준으로 비교하게 맞춰, whitespace가 섞인 stale approved B-roll recommendation도 새 manual selection으로 정상 교체되게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration runtime `broll_refresh` trim 경계만 좁게 수정했다

검증:

- exact regression
  - `pytest tests/test_api.py -k "replaces_trimmed_stale_applied_broll_recommendation_when_running_partial_regeneration"` -> `1 passed`
- output-gating focused slice
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "replaces_trimmed_stale_applied_broll_recommendation_when_running_partial_regeneration or replaces_trimmed_stale_applied_tts_recommendation_when_running_partial_regeneration or timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip or trimmed_broll_type_for_default_provider_trace"` -> `2 passed`

남은 판단:

- broader verification은 이번 수정이 partial regeneration runtime `broll_refresh` type 비교 1줄에 국한되고 exact + focused evidence가 직접적이라 아직 재실행하지 않았다
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다

## 80. 2026-07-04 partial regeneration trimmed stale applied tts replacement closeout

이번 후속 작업에서는 timeline builder 쪽에서 막 닫은 trimmed recommendation type family를 partial regeneration runtime의 `tts_refresh` 단계까지 이어, stale approved recommendation 교체 경계 1개만 다시 닫았다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_tts_refresh_step(...)`는 refresh 전에 기존 TTS recommendation을 걷어낼 때 raw `recommendation_type` 비교를 써 source timeline에 `" tts_replacement "` stale approved recommendation이 남아 있으면 제거하지 못하고 carry-forward하고 있었다
- strict TDD로 `test_editing_session_api_replaces_trimmed_stale_applied_tts_recommendation_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 partial regeneration 결과 narration clip이 새 manual TTS asset이 아니라 stale approved asset URI를 계속 쓰는 RED를 확인했다
- 최소 수정으로 `tts_refresh` 기존 recommendation 제거 분기도 canonical trimmed type 기준으로 비교하게 맞춰, whitespace가 섞인 stale approved TTS recommendation도 새 manual selection으로 정상 교체되게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration runtime `tts_refresh` trim 경계만 좁게 수정했다

검증:

- exact regression
  - `pytest tests/test_api.py -k "replaces_trimmed_stale_applied_tts_recommendation_when_running_partial_regeneration"` -> `1 passed`
- output-gating focused slice
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "replaces_trimmed_stale_applied_tts_recommendation_when_running_partial_regeneration or timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip or trimmed_broll_type_for_default_provider_trace or review_snapshot_api_approve_tts_replacement_matches_trimmed_recommendation_type"` -> `2 passed`

남은 판단:

- broader verification은 이번 수정이 partial regeneration runtime `tts_refresh` type 비교 1줄에 국한되고 exact + focused evidence가 직접적이라 아직 재실행하지 않았다
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다

## 79. 2026-07-04 timeline builder trimmed approved recommendation type closeout

이번 후속 작업에서는 방금 닫은 review snapshot helper trim family를 timeline builder 본체까지 이어, approved recommendation clip 반영 분기에 남아 있던 whitespace recommendation type 경계 1개만 다시 닫았다.

- `packages/core-engine/src/videobox_core_engine/timeline_builder.py`는 recommendation type 지원 여부 필터에서는 이미 `strip()`을 쓰고 있었지만, 실제 narration/B-roll/BGM clip 반영 분기에서는 raw `recommendation_type` 비교를 써 `" tts_replacement "` stale shape를 approved recommendation으로 유지하면서도 narration clip 반영은 놓치고 있었다
- strict TDD로 `test_timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip` exact regression을 먼저 추가했고, 실제로 narration clip `asset_uri`가 source segment URI로 남는 RED를 확인했다
- 최소 수정으로 timeline builder 내부의 approved recommendation type 분기도 canonical trimmed type 기준으로 비교하게 맞춰, whitespace가 섞인 approved recommendation도 narration/B-roll/BGM clip 반영 truth를 유지하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline builder approved recommendation type 분기 경계만 좁게 수정했다

검증:

- exact regression
  - `pytest tests/test_review_timeline.py -k "timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip"` -> `1 passed`
- output-gating focused slice
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "timeline_builder_applies_trimmed_tts_replacement_type_to_narration_clip or trimmed_broll_type_for_default_provider_trace or review_snapshot_api_approve_tts_replacement_matches_trimmed_recommendation_type or review_snapshot_api_approve_tts_replacement_surfaces_approved_decision_state_in_read_paths"` -> `2 passed`

남은 판단:

- broader verification은 이번 수정이 timeline builder의 approved recommendation type 비교 2줄에 국한되고 exact + focused evidence가 직접적이라 아직 재실행하지 않았다
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다

## 78. 2026-07-04 review snapshot trimmed provider-trace fallback recommendation type closeout

이번 후속 작업에서는 approve mutation 쪽에서 막 닫은 trimmed provider-trace fallback family를 review snapshot helper read path까지 이어, 같은 stale whitespace recommendation type 경계 1개만 다시 닫았다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `_review_snapshot_recommendation_payload(...)`는 recommendation `provider_trace`가 비어 있으면 recommendation type으로 fallback provider를 고르는데, 여기만 `recommendation_type` trim이 빠져 `" broll "` stale shape가 `rule_based_fallback`으로 잘못 내려가고 있었다
- strict TDD로 `test_review_snapshot_uses_trimmed_broll_type_for_default_provider_trace` exact regression을 먼저 추가했고, 실제로 review snapshot `applied_recommendations[0].provider_trace.final_provider == "rule_based_fallback"` RED를 확인했다
- 최소 수정으로 review snapshot helper fallback provider 선택도 `recommendation_type.strip()` 기준으로 비교하게 맞춰, whitespace가 섞인 persisted B-roll recommendation도 review snapshot applied recommendation에서 `heuristic_fallback` trace를 유지하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot helper provider-trace fallback 경계만 좁게 수정했다

검증:

- exact regression
  - `pytest tests/test_review_timeline.py -k "trimmed_broll_type_for_default_provider_trace"` -> `1 passed`
- output-gating focused slice
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "trimmed_broll_type_for_default_provider_trace or review_snapshot_api_approve_broll_uses_trimmed_recommendation_type_for_provider_trace_fallback or review_snapshot_api_approve_tts_replacement_matches_trimmed_recommendation_type or review_snapshot_api_approve_tts_replacement_surfaces_approved_decision_state_in_read_paths"` -> `3 passed`

남은 판단:

- broader verification은 이번 수정이 review snapshot helper fallback provider 비교 1줄에 국한되고 exact + focused evidence가 직접적이라 아직 재실행하지 않았다
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다

## 77. 2026-07-04 approve trimmed provider-trace fallback recommendation type closeout

이번 후속 작업에서는 이미 닫힌 TTS approve mutation과 output gating 경계를 다시 넓히지 않고, approve mutation fallback trace 선택에 남아 있던 recommendation type trim 경계 1개만 다시 닫았다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 `extract_pending_recommendation_decision(...)`는 approve 시 `provider_trace`가 비어 있으면 recommendation type으로 fallback provider를 고르는데, 여기만 `recommendation_type` trim이 빠져 `" broll "` stale shape가 `rule_based_fallback`으로 잘못 내려가고 있었다
- strict TDD로 `test_review_snapshot_api_approve_broll_uses_trimmed_recommendation_type_for_provider_trace_fallback` exact regression을 먼저 추가했고, 실제로 approve response의 `applied_recommendations[0].provider_trace.final_provider == "rule_based_fallback"` RED를 확인했다
- 최소 수정으로 fallback provider 선택도 `recommendation_type.strip()` 기준으로 비교하게 맞춰, whitespace가 섞인 persisted B-roll recommendation도 approve response와 persisted applied recommendation에서 `heuristic_fallback` trace를 유지하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 approve mutation provider-trace fallback 경계만 좁게 수정했다

검증:

- exact regression
  - `pytest tests/test_api.py -k "approve_broll_uses_trimmed_recommendation_type_for_provider_trace_fallback"` -> `1 passed`
- output-gating focused slice
  - `./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "approve_broll_uses_trimmed_recommendation_type_for_provider_trace_fallback or review_snapshot_api_approve_tts_replacement_matches_trimmed_recommendation_type or review_snapshot_api_can_reject_pending_recommendation_without_leaving_it_pending or approving_one_of_multiple_pending_recommendations_keeps_output_blocked_by_remaining_detail"` -> `4 passed`

남은 판단:

- broader verification은 이번 수정이 approve mutation fallback provider 비교 1줄에 국한되고 exact + focused evidence가 직접적이라 아직 재실행하지 않았다
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다

## 76. 2026-07-04 review snapshot approve trimmed recommendation type closeout

이번 후속 작업에서는 현재 clean baseline을 넓게 흔들지 않고, `TTS approval/output` approve mutation 안에 남아 있던 stale whitespace recommendation-type 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 `apply_approved_recommendation_to_timeline(...)`는 `recommendation_type`만 `strip()` 없이 raw 비교하고 있어, persisted pending recommendation의 type이 `" tts_replacement "`처럼 저장된 stale shape면 approve 성공 뒤에도 narration clip `asset_uri` 반영을 건너뛰고 있었다
- strict TDD로 `test_review_snapshot_api_approve_tts_replacement_matches_trimmed_recommendation_type` exact regression을 먼저 RED로 확인했고, 실제로 approve 뒤 persisted narration clip `asset_uri`가 original source 그대로 남는 실패가 났다
- 원인은 approve mutation이 canonical TTS type인지 판정하는 분기에서 whitespace normalization을 빠뜨린 점이었다
- 최소 수정으로 `recommendation_type` 비교에도 `.strip()`을 적용해, stale whitespace type shape여도 canonical `tts_replacement` 기준으로 narration clip 반영을 계속 수행하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 TTS approve mutation stale-type tolerance 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `16 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - TTS approve recommendation-type trim 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. pending `tts_replacement` approve가 whitespace가 섞인 persisted `recommendation_type` stale shape여도 narration clip 반영을 계속 수행한다
2. approve mutation의 recommendation-type trim tolerance가 기존 segment-id / recommendation-id trim hardening 방향과 맞춰졌다
3. TTS approve persisted truth와 preview/export read path가 type whitespace 때문에 어긋나지 않는다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 75. 2026-07-04 review timeline import-cycle closeout

이번 후속 작업에서는 이미 닫힌 review snapshot split/output gating 경계를 다시 넓히지 않고, 그 검증 자체를 막고 있던 import-cycle collection 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `tests/test_review_timeline.py::test_review_snapshot_splits_applied_and_pending_recommendations`는 현재 worktree에서 `videobox_storage.local_project_store -> videobox_core_engine.provider_trace` import 경로가 package-level eager import chain을 타면서 `LocalProjectStore` circular import collection error로 막히고 있었다
- strict TDD로 위 exact를 그대로 RED로 확인했고, 실제로 assertion failure가 아니라 `ImportError: cannot import name 'LocalProjectStore' from partially initialized module ...` collection error가 났다
- 원인은 `packages/core-engine/src/videobox_core_engine/__init__.py`가 `LocalPipelineRunner` 등 heavy module을 package import 시점에 eager import하고 있어, provider_trace 하나만 읽어도 local pipeline과 gemini runtime까지 같이 올라가던 점이었다
- 최소 수정으로 package root를 lazy export `__getattr__` 기반으로 바꿔 `videobox_core_engine.provider_trace` 같은 direct submodule import가 heavy eager import chain을 타지 않도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 test collection/import boundary만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- direct helper file
  - `2 passed`
- output-gating focused slice
  - `40 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - package import-cycle 한 점에 국한된 수정이라 exact + direct helper file + review-snapshot focused evidence가 더 직접적이다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. `tests/test_review_timeline.py`가 review snapshot helper exact를 다시 collection error 없이 수집하고 실행한다
2. `videobox_core_engine.provider_trace` import가 package root eager import 때문에 local pipeline/gemini runtime circular chain으로 번지지 않는다
3. review snapshot helper exact와 output-gating review-snapshot lane을 현재 worktree에서도 다시 직접 검증할 수 있다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 74. 2026-07-04 review snapshot split without inline recommendation type closeout

이번 후속 작업에서는 이미 닫힌 stale pending/provider-trace/string-false 경계를 다시 넓히지 않고, review snapshot helper의 direct recommendation input applied/pending split 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `tests/test_review_timeline.py::test_review_snapshot_splits_applied_and_pending_recommendations`는 현재 worktree에서 import collection error가 먼저 발생해 exact RED로 쓰기 어려웠고, 실제 경계는 `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `build_review_snapshot(...)` direct recommendations 분기였다
- strict TDD로 같은 helper 로직을 `tests/test_api.py::test_store_build_review_snapshot_splits_applied_and_pending_recommendations_without_inline_type` exact regression으로 먼저 RED로 확인했고, 실제로 `applied_recommendations == []` 실패가 났다
- 원인은 direct recommendation 입력에 inline `recommendation_type`가 빠져 있으면 helper가 canonical recommendation type truth를 잃은 채 supported-type filter에서 그대로 버리던 점이었다
- 최소 수정으로 direct recommendations 분기에서 missing inline type이 있을 때만 persisted recommendation rows를 읽고, target segment / selected asset / reason / score가 유일하게 맞는 경우에만 canonical `recommendation_type`을 복원하도록 좁혀, applied/pending split truth를 다시 유지하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot helper direct-input recommendation type truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `40 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot helper direct-input type hydration 한 점에 국한된 수정이라 exact + review-snapshot focused evidence가 더 직접적이다
    - `tests/test_review_timeline.py` collection error는 별도 next slice에서 다시 다루는 편이 정확하다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot direct helper가 inline `recommendation_type`가 비어 있는 historical recommendation 입력도 persisted truth와 유일하게 매칭되면 applied/pending split을 유지한다
2. direct helper applied/pending surface truth와 persisted recommendation row truth가 다시 어긋나지 않는다
3. missing type 복원은 유일 매칭일 때만 수행돼 unknown stale recommendation surface를 다시 넓히지 않는다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 73. 2026-07-04 approve persists remaining segment review-required blocker closeout

이번 후속 작업에서는 이미 닫힌 whitespace/provider-trace/rollback 경계를 다시 넓히지 않고, broader verification에서 실제로 드러난 `TTS approval/output` persisted blocker 누수 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_persist_pending_recommendation_decision(...)`는 approve mutation timeline을 먼저 저장한 뒤 synthetic blocker를 다시 계산하고 있어, last pending `tts_replacement` approve 뒤 다른 segment의 `review_required=true` truth가 persisted timeline `review_flags`에는 다시 쓰이지 않고 있었다
- strict TDD로 `test_approving_last_pending_tts_replacement_persists_remaining_segment_review_required_blocker` exact regression을 먼저 RED로 확인했고, 실제로 approve 뒤 persisted timeline `review_flags == []` 실패가 났다
- 원인은 normalized blocker 재계산 시점이 timeline persist보다 늦어 최종 `segment_review_required` synthetic flag가 저장 파일에 반영되지 않던 점이었다
- 최소 수정으로 `_persist_pending_recommendation_decision(...)`가 timeline persist 전에 normalized `review_flags` / `pending_recommendations`를 먼저 계산해 payload에 반영하도록 순서를 좁혀, approve 뒤 남아 있는 segment-level blocker truth도 persisted timeline에 그대로 쓰이게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 TTS approve persisted-blocker truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - persisted blocker write-order 한 점에 국한된 수정이라 exact + output-gating focused evidence가 더 직접적이다
    - broader에서 남아 있던 다른 실제 실패는 다음 slice에서 별도로 exact RED부터 다시 다루는 편이 더 정확하다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. last pending `tts_replacement` approve 뒤에도 다른 segment의 `review_required=true` truth가 persisted timeline `review_flags`에 synthetic `segment_review_required` blocker로 다시 남는다
2. approve mutation의 persisted timeline truth와 output gating / review snapshot blocker truth가 다시 어긋나지 않는다
3. TTS approval persistence가 final blocker normalization 순서를 기준으로 같은 저장 진실을 유지한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 72. 2026-07-04 approve rollback raw persisted timeline closeout

이번 후속 작업에서는 새로운 approval/output stale-shape slice를 더 열지 않고, 누적 변경 검증 중 드러난 review-action rollback 회귀 1개를 먼저 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_prepare_pending_recommendation_decision(...)`는 rollback용 `original_timeline`을 raw persisted timeline이 아니라 `get_timeline_result(...)`의 hydrated response shape에서 가져오고 있어, review state 저장 실패 후 rollback이 실행되면 provider trace가 없는 pending recommendation까지 hydrated shape로 다시 저장하고 있었다
- 기존 exact regression `test_review_snapshot_api_approve_rolls_back_timeline_and_recommendation_when_review_state_save_fails`를 다시 RED로 확인했고, 실제로 rollback 뒤 persisted `pending_recommendations`가 original raw timeline과 달라지는 실패가 났다
- 원인은 rollback source timeline이 API read-path hydration을 이미 거친 객체였다는 점이었다
- 최소 수정으로 pending recommendation decision 준비 단계는 job type에 따라 store의 raw timeline payload만 직접 읽어 rollback source로 보관하도록 좁혀, downstream failure 후 timeline rollback이 original persisted shape를 그대로 복구하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review-action rollback raw-timeline restoration 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- paired rollback regression
  - `1 passed`
- review-action backend focused slice
  - `7 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - rollback source timeline 한 점에 국한된 수정이라 exact + paired exact + review-action focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approve rollback이 raw persisted timeline shape를 hydrated response shape로 오염시키지 않는다
2. 같은 rollback source 수정으로 reject rollback도 original pending/applied/review-flag truth를 그대로 복구한다
3. review-action rollback hardening이 response hydration 규칙과 분리된 raw persistence truth를 유지한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 71. 2026-07-04 approve trimmed target segment id blocker cleanup closeout

이번 후속 작업에서는 방금 닫은 approval/output applied recommendation id canonicalization 경계를 다시 넓히지 않고, 같은 helper 안에 남아 있던 `target_segment_id` whitespace stale shape로 인한 blocker cleanup 비대칭 1개만 다시 좁혀 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 review flag cleanup은 `should_keep_review_flag(...)` 내부 비교는 trim 기준으로 맞춰졌지만, 그 앞단 `filtered_review_flags_after_recommendation_decision(...)`가 `decided_recommendation.target_segment_id`를 raw로 유지하고 있어 whitespace가 섞인 stale pending recommendation이면 last pending approve 뒤에도 blocker가 남고 있었다
- strict TDD로 `test_approving_last_pending_recommendation_removes_blocker_with_trimmed_target_segment_id` exact regression을 먼저 추가했고, 실제로 approve 응답의 `review_status`가 `draft`가 아니라 `blocked`로 남는 RED를 확인했다
- 원인은 cleanup helper가 `target_segment_id`를 trim하지 않고 recommendation flag key를 계산하던 점이었다
- 최소 수정으로 review flag cleanup helper의 `target_segment_id`도 trim해서 canonical target segment 기준으로 비교하도록 좁혀, stale whitespace target segment shape여도 blocker cleanup이 같은 기준으로 동작하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 approval/output target-segment blocker-cleanup 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - target segment blocker cleanup trim 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approve/reject review-flag cleanup이 whitespace가 섞인 persisted `target_segment_id`도 canonical target segment로 식별한다
2. stale trimmed target segment id 때문에 last pending approve 뒤 `review_status=blocked`가 남지 않는다
3. approval/output helper의 trim stale-shape family가 selection, decision-map, applied surface, blocker cleanup에서 같은 canonical segment/id 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 70. 2026-07-04 approve trimmed persisted applied recommendation id closeout

이번 후속 작업에서는 방금 닫은 approval/output decision-map stale-key cleanup 경계를 다시 넓히지 않고, 같은 helper 안에 남아 있던 persisted `applied_recommendations` recommendation id canonicalization 1개만 다시 좁혀 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 pending recommendation decision extraction은 route의 canonical id로 대상을 찾더라도, `decided_recommendation` 자체에는 source pending item의 whitespace `recommendation_id`를 그대로 남겨 persisted `applied_recommendations` surface가 stale id를 보존하고 있었다
- strict TDD로 `test_approving_last_pending_recommendation_persists_canonical_trimmed_recommendation_id` exact regression을 먼저 추가했고, 실제로 approve 뒤 persisted `applied_recommendations[0].recommendation_id`가 whitespace id 그대로 남는 RED를 확인했다
- 원인은 `extract_pending_recommendation_decision(...)`가 matched recommendation을 deepcopy한 뒤 canonical route id로 `recommendation_id`를 덮어쓰지 않던 점이었다
- 최소 수정으로 matched `decided_recommendation`의 `recommendation_id`를 route의 canonical id로 즉시 정규화해, persisted applied recommendation surface도 selection truth와 같은 canonical id를 유지하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 approval/output applied-recommendation id canonicalization 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - applied recommendation id canonicalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approve/reject selection이 canonical route id를 찾으면 persisted `applied_recommendations` surface도 같은 canonical id를 유지한다
2. stale trimmed pending recommendation id 때문에 applied recommendation surface가 whitespace id를 다시 노출하지 않는다
3. approval/output helper의 trim stale-shape family가 selection, decision-map, applied surface까지 같은 canonical id 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 69. 2026-07-04 approve trimmed recommendation decision key closeout

이번 후속 작업에서는 방금 닫은 approval/output recommendation-id trim selection 경계를 다시 넓히지 않고, 같은 helper 안에 남아 있던 `recommendation_decisions` stale key cleanup 1개만 다시 좁혀 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 `timeline_recommendation_decisions(...)`는 whitespace가 섞인 persisted decision key를 필터링만 하고 canonical key로 정규화하지 않아, 같은 recommendation approve 뒤에도 stale key와 canonical key가 동시에 남고 있었다
- strict TDD로 `test_approving_last_pending_recommendation_rewrites_trimmed_recommendation_decision_key` exact regression을 먼저 추가했고, 실제로 approve 뒤 `recommendation_decisions`에 stale whitespace key가 그대로 남는 RED를 확인했다
- 원인은 `timeline_recommendation_decisions(...)`가 기존 dict를 복사할 때 `str(key)` / `str(value)`를 그대로 보존하던 점이었다
- 최소 수정으로 decision map normalization도 key/value를 trim해서 보관하도록 좁혀, stale whitespace key가 canonical recommendation id key 하나로 정리되게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 approval/output decision-map stale-key cleanup 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - recommendation decision-key trim 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approve/reject decision map이 whitespace가 섞인 persisted key도 canonical recommendation id key 하나로 정리한다
2. stale trimmed decision key 때문에 같은 recommendation decision이 중복 key로 남지 않는다
3. approval/output helper의 trim stale-shape family가 selection, review-flag cleanup, decision-map cleanup에서 같은 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 68. 2026-07-04 approve trimmed recommendation id closeout

이번 후속 작업에서는 방금 닫은 review-flag cleanup trim family를 다시 넓히지 않고, 같은 approval/output decision-selection helper 안에 남아 있던 `recommendation_id` whitespace stale shape 1개만 다시 좁혀 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 pending recommendation selection은 route에서 받은 canonical `recommendation_id`와 persisted pending entry의 `recommendation_id`를 raw 문자열로 비교하고 있어 whitespace가 섞인 stale pending entry를 같은 recommendation으로 찾지 못하고 있었다
- strict TDD로 `test_approving_last_pending_recommendation_matches_trimmed_recommendation_id` exact regression을 먼저 추가했고, 실제로 approve 응답이 `404`로 떨어지는 RED를 확인했다
- 원인은 `extract_pending_recommendation_decision(...)`가 `item["recommendation_id"]`를 trim하지 않고 route id와 직접 비교하던 점이었다
- 최소 수정으로 pending recommendation selection이 persisted `recommendation_id`도 trim해서 route의 canonical recommendation id와 비교하도록 좁혀, stale whitespace id shape여도 approve/reject mutation이 같은 recommendation에 적용되게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 approval/output recommendation-selection stale-shape 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - approve/reject recommendation-id trim 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approve/reject recommendation selection이 whitespace가 섞인 persisted `recommendation_id`도 같은 recommendation으로 식별한다
2. stale trimmed recommendation id 때문에 approve/reject가 `404`로 떨어지지 않는다
3. approval/output decision-selection helper가 `recommendation_id`, `review_flag.code`, `review_flag.segment_id` 모두 같은 trim 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 67. 2026-07-04 approve trimmed review flag code closeout

이번 후속 작업에서는 방금 닫은 review-flag `segment_id` trim cleanup 경계를 다시 넓히지 않고, 같은 approval/output cleanup helper 안에 남아 있던 `review_flag.code` whitespace stale shape 1개만 다시 좁혀 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 review flag 정리 로직은 `segment_id` trim은 맞춰졌지만 persisted review flag의 `code`는 raw 문자열로 비교하고 있어 whitespace가 섞인 stale canonical flag code를 같은 blocker로 인식하지 못한 채 남기고 있었다
- strict TDD로 `test_approving_last_pending_recommendation_removes_trimmed_review_flag_code_for_same_segment` exact regression을 먼저 추가했고, 실제로 approve 응답의 `review_status`가 `draft`가 아니라 `blocked`로 남는 RED를 확인했다
- 원인은 `should_keep_review_flag(...)`가 `flag.code`를 trim하지 않고 `recommendation_flag_code`와 직접 비교하던 점이었다
- 최소 수정으로 review flag keep 판정이 `code`도 trim해서 비교하도록 좁혀, stale whitespace canonical review flag code가 approve/reject 뒤 blocker로 남지 않게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 approval/output review-flag code cleanup stale-shape 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - approve/reject review-flag code trim 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approve/reject review-flag cleanup이 whitespace가 섞인 persisted canonical `code`도 같은 blocker flag로 식별한다
2. stale trimmed review flag code 때문에 last pending approve 뒤 `review_status=blocked`가 남지 않는다
3. approval/output review-flag cleanup helper가 `code`와 `segment_id` 모두 같은 trim 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 66. 2026-07-04 approve trimmed review flag segment id closeout

이번 후속 작업에서는 방금 닫은 TTS approve clip-match stale shape를 다시 넓히지 않고, 같은 approval/output 경계 안에서 persisted review flag 정리 비대칭 1개만 다시 좁혀 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 review flag 정리 로직은 recommendation 쪽 `target_segment_id`와 달리 persisted review flag의 `segment_id`를 raw 문자열로 비교하고 있어 whitespace가 섞인 stale review flag를 같은 세그먼트 blocker로 인식한 채 남기고 있었다
- strict TDD로 `test_approving_last_pending_recommendation_removes_trimmed_review_flag_for_same_segment` exact regression을 먼저 추가했고, 실제로 approve 응답의 `review_status`가 `draft`가 아니라 `blocked`로 남는 RED를 확인했다
- 원인은 `should_keep_review_flag(...)`가 `flag.segment_id`와 remaining pending recommendation의 `target_segment_id`를 trim하지 않고 비교하던 점이었다
- 최소 수정으로 review flag keep 판정도 양쪽 `segment_id`를 trim해서 비교하도록 좁혀, stale whitespace review flag가 approve/reject 뒤 blocker로 남지 않게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 approval/output review-flag cleanup stale-shape 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - approve/reject review-flag segment-id trim 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approve/reject review-flag cleanup이 whitespace가 섞인 persisted `segment_id`도 같은 세그먼트 flag로 식별한다
2. stale trimmed review flag 때문에 last pending approve 뒤 `review_status=blocked`가 남지 않는다
3. approval/output review-flag cleanup truth가 방금 닫은 clip-match trim truth와 같은 stale-shape 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 65. 2026-07-04 review snapshot approve trimmed target narration clip segment id closeout

이번 후속 작업에서는 just-closed provider-trace/read-contract family를 다시 넓히지 않고, `TTS approval/output` 경계에서 persisted timeline stale shape 1개만 다시 좁혀 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`의 TTS approve mutation은 recommendation 쪽 `target_segment_id`는 trim해서 읽지만, narration clip 쪽 `segment_id`는 raw 문자열로 비교하고 있어 whitespace가 섞인 persisted clip을 target clip으로 찾지 못했다
- strict TDD로 `test_review_snapshot_api_approve_tts_replacement_matches_trimmed_target_narration_clip_segment_id` exact regression을 먼저 추가했고, 실제로 approve 응답이 `400`으로 떨어지는 RED를 확인했다
- 원인은 approve mutation의 target narration clip match가 `str(clip.get("segment_id") or "") == target_segment_id` raw 비교에 머물러 있던 점이었다
- 최소 수정으로 approved TTS replacement가 narration clip `segment_id`도 trim해서 target segment와 비교하도록 좁혀, stale whitespace clip shape여도 기존 approve truth와 같은 clip을 업데이트하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 TTS approve clip-match stale-shape 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - TTS approve clip-match trim 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. TTS approve mutation이 whitespace가 섞인 persisted narration clip `segment_id`도 target clip으로 매칭한다
2. stale clip segment-id shape 때문에 approved `selected_asset_uri` 반영이 `400`으로 막히지 않는다
3. TTS approve mutation truth가 preflight/runtime의 trimmed segment-id handling 방향과 더 이상 어긋나지 않는다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 64. 2026-07-04 review snapshot persisted operator guidance default provider trace closeout

이번 후속 작업에서는 partial regeneration result response fallback 경계를 다시 넓히지 않고, 같은 review/output read-contract 축의 바로 인접면인 persisted `operator_guidance` legacy shape 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 review snapshot 응답은 recommendation/review_flag와 달리 persisted `operator_guidance`를 raw `OperatorGuidanceResponse`에 바로 넣고 있어, legacy guidance에 `provider_trace`가 빠져 있으면 응답 모델 validation error가 났다
- strict TDD로 `test_review_snapshot_fills_default_provider_trace_for_persisted_operator_guidance` exact regression을 먼저 추가했고, 실제로 `operator_guidance.provider_trace Field required` RED를 확인했다
- 첫 최소 수정에서 generic response fallback을 재사용하면 `rule_based_fallback`이 들어가 review guidance truth와 어긋났고, guidance response normalization을 별도로 두어 missing trace일 때 `heuristic_fallback`을 채우는 쪽으로 한 단계 더 좁혀 맞췄다
- 최소 수정으로 review snapshot / approve / reject 응답의 operator guidance response layer만 normalization 하도록 좁혀, persisted legacy guidance shape도 canonical fallback trace를 가진 review snapshot response로 읽히게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot operator-guidance read-contract 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot operator-guidance response normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot read path가 missing `provider_trace` persisted operator guidance shape를 그대로 validation error로 흘리지 않음
2. persisted operator guidance response가 `heuristic_fallback` trace를 채운 canonical shape를 유지함
3. review snapshot guidance read truth와 최근 recommendation/provider-trace fallback read truth가 같은 방향의 canonical response 규칙을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 63. 2026-07-04 partial regeneration result applied recommendation default provider trace closeout

이번 후속 작업에서는 partial regeneration source-truth나 blocker 경계를 다시 넓히지 않고, result read path에서 applied recommendation `provider_trace` 누락이 그대로 API validation error로 이어지는 가장 작은 response-contract 누수 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `GET /api/projects/{project_id}/partial-regenerations/{job_id}`는 raw timeline payload를 그대로 `TimelinePayloadResponse`에 넣고 있어, applied recommendation에 `provider_trace`가 빠진 legacy shape가 있으면 응답 모델 validation error가 났다
- strict TDD로 `test_partial_regeneration_result_fills_default_provider_trace_for_applied_recommendation` exact regression을 먼저 추가했고, 실제로 `applied_recommendations.0.provider_trace Field required` RED를 확인했다
- 응답 normalization 연결 뒤에는 `_normalize_provider_trace_response(...)` fallback helper import가 빠져 있어 `NameError`가 드러났고, 이 import 복구까지 포함한 최소 수정으로 canonical fallback trace response를 유지하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration result read-contract 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - partial regeneration result response normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration result read path가 missing `provider_trace` applied recommendation shape를 그대로 validation error로 흘리지 않음
2. applied recommendation response가 fallback trace를 채운 canonical shape를 유지함
3. partial regeneration result read truth와 timeline/read response truth가 recommendation provider trace fallback에서 더 일관된 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 56. 2026-07-04 review snapshot helper unknown pending recommendation approved-status closeout

이번 후속 작업에서는 direct review-snapshot helper의 stale recommendation family를 다시 좁혀, unknown legacy pending recommendation이 존재해도 persisted approved status를 `blocked`로 다시 뒤집는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `build_review_snapshot(...)`는 normalized pending override가 비어 있지 않기만 하면 recommendation type validity와 무관하게 `review_status="blocked"`를 우선하고 있어, `legacy_overlay_pick` 같은 unknown recommendation type도 persisted approved status를 다시 막고 있었다
- strict TDD로 `test_store_build_review_snapshot_ignores_unknown_pending_recommendation_for_status_when_persisted_approved` exact regression을 먼저 추가했고, 실제로 `snapshot["review_status"] == "blocked"` RED를 확인했다
- 최소 수정으로 direct helper status 계산도 canonical blocking pending recommendation만 blocker로 세도록 좁혀, unknown / non-blocking pending recommendation은 surface에 남더라도 persisted approved truth를 다시 뒤집지 않게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot helper pending-status truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot helper unknown-pending status precedence 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot direct helper가 unknown / non-blocking `timeline_pending_recommendations` shape 하나만으로 persisted approved status를 다시 `blocked`로 뒤집지 않음
2. canonical blocking pending recommendation이 없는 경우 helper `review_status`가 persisted approved truth를 유지함
3. helper status truth와 runtime output gating / preflight read truth가 같은 stale recommendation family에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 55. 2026-07-04 review snapshot helper unknown review flag approved-status closeout

이번 후속 작업에서는 direct review-snapshot helper의 stale review-flag family를 다시 좁혀, unknown legacy review flag가 surface에는 남아 있어도 persisted approved status를 `blocked`로 다시 뒤집는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `build_review_snapshot(...)`는 `timeline_review_flags`가 비어 있지 않기만 하면 code validity와 무관하게 `review_status="blocked"`를 우선하고 있어, `legacy_review_flag` 같은 unknown metadata도 persisted approved status를 다시 막고 있었다
- strict TDD로 `test_store_build_review_snapshot_ignores_unknown_review_flag_for_status_when_persisted_approved` exact regression을 먼저 추가했고, 실제로 `snapshot["review_status"] == "blocked"` RED를 확인했다
- 최소 수정으로 direct helper status 계산도 canonical blocking review flag만 blocker로 세도록 좁혀, unknown / non-blocking review flag는 surface에 남더라도 persisted approved truth를 다시 뒤집지 않게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot helper status truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `58 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot helper unknown-review-flag status precedence 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot direct helper가 unknown / non-blocking `timeline_review_flags` shape 하나만으로 persisted approved status를 다시 `blocked`로 뒤집지 않음
2. canonical blocking review flag가 없는 경우 helper `review_status`가 persisted approved truth를 유지함
3. helper status truth와 runtime output gating / preflight read truth가 같은 stale review-flag family에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 54. 2026-07-04 timeline persistence stale non-list review flags initial status closeout

이번 후속 작업에서는 stale review-flag family를 저장 시점까지 다시 내려가 확인해, non-list `review_flags` shape 하나만으로 timeline persistence가 initial review state를 `blocked`로 저장하는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `save_timeline_run(...)`는 initial review state를 계산할 때 `review_flags`를 raw truthiness로만 보고 있어, `"stale_review_flag_container"` 같은 non-list shape도 `blocked` 근거로 오판하고 있었다
- strict TDD로 `test_store_save_timeline_run_ignores_stale_nonlist_review_flags_when_setting_initial_status` exact regression을 먼저 추가했고, 실제로 persisted review state가 `draft`가 아니라 `blocked`인 RED를 확인했다
- 최소 수정으로 save path도 canonical blocking review flag만 blocker로 세도록 검증을 좁혀, stale non-list / non-blocking `review_flags` shape는 initial review state를 막지 않게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline persistence initial status truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline persistence initial status의 stale review-flag normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline save path가 stale non-list `review_flags` shape 하나만으로 `blocked` review state를 저장하지 않음
2. persisted initial review state가 canonical blocking review flag truth가 없으면 `draft`를 유지함
3. persistence truth와 preflight/read-path truth가 같은 stale review-flag family에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 53. 2026-07-04 review snapshot helper persisted-approved pending-override status closeout

이번 후속 작업에서는 direct store helper의 review status 일관성 경계를 다시 좁혀, pending override나 blocker flag가 이미 존재하는데도 persisted approved status를 그대로 우선하는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `build_review_snapshot(...)`는 `timeline_id`가 있고 persisted review state가 `approved`면, pending recommendation override가 이미 존재해도 `review_status="approved"`를 그대로 반환하고 있었다
- strict TDD로 `test_store_build_review_snapshot_marks_status_blocked_when_pending_override_exists_despite_persisted_approved` exact regression을 먼저 추가했고, 실제로 `snapshot["review_status"] == "approved"` RED를 확인했다
- 최소 수정으로 direct helper도 `timeline_review_flags`나 `pending` recommendation이 이미 계산된 경우 persisted status보다 blocker truth를 우선해 `review_status="blocked"`를 반환하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot helper status truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot helper status precedence 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot direct helper가 pending override나 blocker flag 존재 시 persisted approved status를 그대로 우선하지 않음
2. computed blocker truth와 `review_status`가 helper 수준에서도 일치함
3. helper status truth와 timeline/review snapshot/preflight read truth가 같은 stale bucket family에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 52. 2026-07-04 timeline persistence misbucketed applied pending-like recommendation closeout

이번 후속 작업에서는 stale bucket family를 저장 시점까지 내려가 확인해, pending-like legacy recommendation이 `applied_recommendations` bucket에 잘못 들어 있는 경우 timeline persistence가 initial review state를 `draft`로 저장하는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `save_timeline_run(...)`는 initial review state를 `review_flags`와 `pending_recommendations` 존재 여부만으로 결정하고 있어, `applied_recommendations`에 misbucket된 pending-like recommendation은 무시한 채 `draft`를 저장하고 있었다
- strict TDD로 `test_store_save_timeline_run_marks_misbucketed_applied_pending_like_recommendation_as_blocked` exact regression을 먼저 추가했고, 실제로 persisted review state가 `blocked`가 아니라 `draft`인 RED를 확인했다
- 최소 수정으로 save path도 `pending_recommendations + applied_recommendations` 양쪽에서 recommendation dict를 모은 뒤 `_normalize_recommendation_decision_state(...) == "pending"`인 항목이 있으면 initial review state를 `blocked`로 저장하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline persistence truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline persistence initial review-state normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline save path가 misbucketed pending-like applied recommendation을 무시한 채 `draft` review state를 저장하지 않음
2. persisted initial review state가 source recommendation truth와 맞게 `blocked`를 유지함
3. persistence truth와 timeline/review snapshot/preflight read truth가 같은 stale bucket family에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 51. 2026-07-04 preflight misbucketed applied pending-like recommendation closeout

이번 후속 작업에서는 같은 stale bucket family를 preflight prediction read path로 옮겨, pending-like legacy recommendation이 `applied_recommendations` bucket에 잘못 들어 있는 경우 source blocker truth를 놓치는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `_build_preflight_review_prediction(...)`는 source timeline의 `pending_recommendations`만 blocker source로 보고 있었고, `applied_recommendations`에 misbucket된 pending-like recommendation은 무시해 `draft` prediction을 반환하고 있었다
- strict TDD로 `test_editing_session_api_marks_preflight_blocked_when_source_timeline_has_misbucketed_applied_pending_like_recommendation` exact regression을 먼저 추가했고, 실제로 `predicted_review_status_after_rerun == "draft"` RED를 확인했다
- 최소 수정으로 preflight prediction도 blocker source를 `pending_recommendations + applied_recommendations`로 합쳐 같은 bool-ish normalization 기준으로 필터링하도록 맞춰, misbucketed pending-like recommendation을 unresolved blocker로 다시 복원하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preflight prediction truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- preflight-backend focused slice
  - `57 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `57 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preflight prediction blocker-source normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preflight prediction이 misbucketed pending-like applied recommendation을 unresolved blocker로 다시 복원함
2. source blocker truth와 `predicted_review_status_after_rerun`가 `blocked`로 일치함
3. preflight prediction truth와 timeline/review snapshot read truth가 같은 stale bucket family에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 50. 2026-07-04 timeline API misbucketed applied pending-like recommendation closeout

이번 후속 작업에서는 review snapshot API와 같은 stale bucket family의 바로 옆 read surface인 timeline API에서, pending-like legacy recommendation이 `applied_recommendations` bucket에 남아 있어 review truth와 applied surface가 어긋나는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 timeline hydration은 pending-like recommendation을 blocker로는 복원할 수 있어도 `applied_recommendations` 컬렉션 자체는 그대로 두고 있어 timeline API response에서 stale applied entry가 계속 노출되고 있었다
- strict TDD로 `test_timeline_api_reclassifies_pending_like_entry_misbucketed_into_applied_recommendations` exact regression을 먼저 추가했고, 실제로 `review_status="blocked"`이더라도 `applied_recommendations`에 해당 recommendation이 남는 RED를 확인했다
- 최소 수정으로 hydration 단계가 runtime blocker shape를 `applied_recommendations`에서도 먼저 제외하도록 맞춰 timeline API response의 applied surface와 synthesized pending blocker truth를 일치시켰다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline API read truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline API read truth와 hydration cleanup 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline API가 misbucketed pending-like applied recommendation을 applied surface에서 제거함
2. `review_status`와 pending blocker truth가 timeline response에서도 일관되게 유지됨
3. timeline/read truth와 review snapshot/read truth가 같은 stale bucket family에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 49. 2026-07-04 review snapshot API misbucketed applied pending-like recommendation closeout

이번 후속 작업에서는 direct store helper보다 한 단계 위 read path인 review snapshot API에서, pending-like legacy recommendation이 stale하게 `applied_recommendations` bucket에 들어 있는 경우 pending blocker truth와 `review_status`를 같이 잃는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 timeline hydration은 pending blocker normalization을 `pending_recommendations`만 기준으로 보고 있었고, `applied_recommendations`에 잘못 들어간 pending-like legacy recommendation은 blocker로 보지 않아 `review_status=approved`가 유지됐다
- strict TDD로 `test_review_snapshot_api_reclassifies_pending_like_entry_misbucketed_into_applied_recommendations` exact regression을 먼저 추가했고, 실제로 review snapshot API가 `review_status="approved"`를 반환하는 RED를 확인했다
- 최소 수정으로 timeline hydration의 blocker source에 `applied_recommendations`도 포함해 pending-like recommendation을 다시 blocker로 복원했고, 같은 recommendation이 snapshot에서 duplicate pending blocker로 늘어나지 않도록 review snapshot API applied collection에서도 runtime blocker shape를 먼저 제외했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot API read truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot API read truth와 runtime blocker synthesis 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot API가 misbucketed pending-like applied recommendation을 pending blocker로 다시 복원함
2. `review_status`가 pending blocker truth와 맞게 `blocked`로 유지됨
3. 같은 recommendation이 applied/pending 양쪽에 중복으로 남지 않음

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 48. 2026-07-04 review snapshot applied override legacy pending-like recommendation closeout

이번 후속 작업에서는 직전 pending override 경계의 대칭면인 review snapshot direct applied override 입력을 다시 좁혀, `timeline_applied_recommendations` 안의 legacy pending-like recommendation이 applied로 고정되는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `build_review_snapshot(...)`는 `timeline_applied_recommendations` override 경로에서 모든 항목에 fallback `decision_state="approved"`를 강제로 써서 `auto_apply_allowed="false"` / `review_required="true"` legacy pending-like recommendation까지 applied recommendation으로 고정하고 있었다
- strict TDD로 `test_store_build_review_snapshot_reclassifies_legacy_pending_like_timeline_applied_override` exact regression을 먼저 추가했고, 실제로 `applied_recommendations`에 해당 recommendation이 그대로 남는 RED를 확인했다
- 원인은 direct applied override 경로도 raw item의 recommendation truth를 먼저 판단하지 않고 caller bucket을 그대로 우선시하던 점이었다
- 최소 수정으로 applied override 입력도 raw item 기준 `_normalize_recommendation_decision_state(...)`를 먼저 계산한 뒤 payload fallback에 반영하고, applied/pending 컬렉션을 같은 normalized decision-state 기준으로 다시 나누도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot helper truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot helper decision-state normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot direct applied override 입력이 legacy pending-like recommendation shape를 applied recommendation으로 오판하지 않음
2. `decision_state`가 비어 있어도 pending truth에 해당하는 recommendation shape는 pending recommendation으로 재분류됨
3. review snapshot helper truth와 runtime output gating / preflight prediction / store fallback truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 47. 2026-07-04 review snapshot pending override legacy applied-like recommendation closeout

이번 후속 작업에서는 runtime caller filter에만 의존하던 review snapshot direct helper 경계를 다시 좁혀, `timeline_pending_recommendations` override 입력 안의 legacy applied-like recommendation이 pending blocker로 남는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `build_review_snapshot(...)`는 `timeline_pending_recommendations` override 경로에서 모든 항목에 fallback `decision_state="pending"`를 강제로 써서 `auto_apply_allowed="true"` / `review_required="false"` legacy applied-like recommendation까지 pending recommendation으로 고정하고 있었다
- strict TDD로 `test_store_build_review_snapshot_reclassifies_legacy_applied_like_timeline_pending_override` exact regression을 먼저 추가했고, 실제로 `applied_recommendations == []` RED를 확인했다
- 원인은 direct pending override 경로가 raw item의 recommendation truth를 먼저 판단하지 않고 caller bucket만 그대로 우선시하던 점이었다
- 최소 수정으로 pending override 입력도 raw item 기준 `_normalize_recommendation_decision_state(...)`를 먼저 계산한 뒤 payload fallback에 반영하도록 맞춰 legacy applied-like recommendation은 applied 쪽으로 재분류되게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot helper truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot helper decision-state normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot direct pending override 입력이 legacy applied-like recommendation shape를 pending blocker로 오판하지 않음
2. `decision_state`가 비어 있어도 applied truth에 해당하는 recommendation shape는 applied recommendation으로 재분류됨
3. review snapshot helper truth와 runtime output gating / preflight prediction / store fallback truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 46. 2026-07-04 output gating legacy applied-like pending recommendation closeout

이번 후속 작업에서는 이미 닫힌 `approved/rejected decision_state stale pending recommendation` 경계를 다시 넓히지 않고, 그 바로 인접면인 runtime output gating에서 legacy applied-like pending recommendation shape가 unresolved blocker로 남는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_is_runtime_blocking_pending_recommendation(...)`는 `decision_state`가 비어 있는 `auto_apply_allowed="true"` / `review_required="false"` legacy applied-like recommendation을 subtitle / preview / export blocker로 오판하고 있었다
- strict TDD로 `test_output_jobs_ignore_legacy_applied_like_entries_left_in_pending_recommendations` exact regression을 먼저 추가했고, 실제로 subtitle render start가 `202`가 아니라 `400`으로 막히는 RED를 확인했다
- 원인은 runtime blocker 판정이 explicit `decision_state`만 보고 있었고, applied-like bool-ish truth를 보지 않던 점이었다
- 최소 수정으로 runtime pending recommendation blocker 판정에도 bool-ish normalization을 적용해 `auto_apply_allowed=true`이면서 `review_required=false`인 recommendation shape는 blocker에서 제외하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output gating truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - runtime output gating bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approved timeline output gating이 legacy applied-like pending recommendation shape를 unresolved blocker로 오판하지 않음
2. `decision_state`가 비어 있어도 applied truth에 해당하는 recommendation shape는 subtitle / preview / export를 막지 않음
3. runtime output gating truth와 preflight prediction/API response/store fallback truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 45. 2026-07-04 preflight legacy applied-like pending recommendation prediction closeout

이번 후속 작업에서는 이미 닫힌 approved/rejected `decision_state` stale pending recommendation 경계를 다시 넓히지 않고, 그 바로 인접면인 preflight prediction read path에서 legacy applied-like recommendation payload가 unresolved blocker로 남는 가장 작은 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `_build_preflight_review_prediction(...)`는 source timeline `pending_recommendations`를 필터링할 때 `decision_state`와 식별자만 보고 있었고, `auto_apply_allowed="true"` / `review_required="false"` legacy applied-like shape를 unresolved blocker recommendation으로 오판하고 있었다
- strict TDD로 `test_editing_session_api_filters_legacy_applied_like_source_pending_recommendation_from_preflight_prediction` exact regression을 먼저 추가했고, 실제로 preflight prediction이 `draft`가 아니라 `blocked`가 되는 RED를 확인했다
- 원인은 preflight prediction read path가 API response/runtime/store 쪽에서 이미 쓰는 bool-ish normalization 기준을 재사용하지 않고 raw pending collection shape만 보고 blocker 여부를 결정하던 점이었다
- 최소 수정으로 preflight pending recommendation filter에도 bool-ish normalization을 적용해 `auto_apply_allowed=false` 또는 `review_required=true`인 recommendation만 unresolved blocker로 남도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preflight prediction truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- preflight-backend focused slice
  - `56 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preflight prediction bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration preflight prediction이 source timeline의 legacy applied-like pending recommendation을 unresolved blocker로 오판하지 않음
2. `decision_state`가 비어 있어도 applied truth에 해당하는 recommendation shape는 `draft` prediction을 유지함
3. preflight prediction truth와 runtime/API response/store fallback truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 16. 2026-07-03 Task 2 real-project smoke + evidence freeze 기록

이번 후속 작업으로 `Task 2: 실제 프로젝트 1개 happy-path smoke + evidence freeze`는 완료로 본다.

이번에 추가로 확인된 사실은 아래와 같다.

- 실제 smoke에서 `partial_regeneration_job_*` candidate를 review snapshot / approve / output에 넘길 때 `candidate timeline` 대신 persisted `partial_regeneration_id`를 timeline id처럼 읽어 `404`가 나는 경계가 있었다
- strict TDD로 `test_review_snapshot_api_uses_partial_regeneration_job_id_for_candidate_timeline` exact regression을 추가했고, 실제로 `404` RED를 확인한 뒤 최소 수정으로 닫았다
- `local_pipeline.get_timeline_result()`는 이제 `partial_regeneration` job일 때 persisted run에서 candidate timeline을 읽어 review snapshot / approve / subtitle / preview / export가 같은 truth를 타도록 맞춰졌다
- clean real-project smoke를 다시 수행했고 아래 흐름이 실제로 끝까지 통과했다
  - timeline build
  - review snapshot
  - editing session
  - mutation 1회
  - preflight
  - partial regeneration
  - approve
  - subtitle / preview / export
- smoke evidence 기준 clean project의 candidate approve 이후 output artifact도 정상 확인됐다
  - subtitle file uri `local://projects/task2-smoke-project/subtitles/subtitle_001.srt`
  - preview player uri `local://projects/task2-smoke-project/previews/preview_001.html`
  - CapCut export adapter `capcut_v1_port`
  - export track order `voiceover / broll / subtitle / bgm`
- exact backend regression `1 passed`
- exact frontend regression `1 passed`
- frontend build 성공
- full backend regression `334 passed`

이 갱신으로 아래 범위는 현재 기준 실제 증거로 닫혔다.

1. partial regeneration candidate job id review snapshot read
2. partial regeneration candidate approve routing
3. partial regeneration candidate subtitle / preview / export routing
4. 실제 프로젝트 1개 happy-path smoke
5. Task 2 evidence / closeout / SSOT freeze

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue로 복귀
- `review/output` 또는 `preflight contract` 중 가장 작은 남은 경계 1개만 재선정
- exact failing test 1개로 다음 slice 시작

## 17. 2026-07-03 partial regeneration start prediction symmetry 기록

이번 후속 작업에서는 `partial regeneration start` 응답이 preflight와 같은 review prediction contract를 유지하는지 작은 리스크 관점에서 다시 고정했다.

이번에 새로 확인된 사실은 아래와 같다.

- clean scope partial regeneration start 응답도 `predicted_review_status_after_rerun`를 `unknown`이 아니라 실제 `draft`로 surface해야 한다
- blocked scope partial regeneration start 응답도 preflight와 같은 `prediction_reasons`를 유지해야 한다
- strict TDD로 아래 exact regression을 고정했다
  - `test_editing_session_api_surfaces_draft_prediction_when_starting_partial_regeneration`
  - `test_editing_session_api_surfaces_blocked_prediction_when_starting_partial_regeneration`
- 구현은 `services/api/src/videobox_api/main.py`의 start endpoint에서 source timeline + targeted segments 기준 prediction 계산을 재사용하는 최소 수정으로 닫았다
- exact clean-scope regression `1 passed`
- exact blocked-scope regression `1 passed`
- focused backend verification
  - `4 passed`
  - `./scripts/dev-fast-path.ps1 -Mode preflight-backend` -> `55 passed`

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration preflight 응답 prediction surface
2. partial regeneration start 응답 clean-scope prediction surface
3. partial regeneration start 응답 blocked-scope prediction surface

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue 유지
- 이번에는 `review/output` 쪽에서 가장 작은 남은 경계 1개를 다시 고르는 편이 더 효율적이다

## 19. 2026-07-03 Task 1 회귀 증거 고정

이번 후속 작업에서는 `approved TTS persisted truth gap`을 실제 코드 변경보다 `회귀 증거 강화` 관점에서 다시 확인했다.

이번에 새로 확인된 사실은 아래와 같다.

- 기존 코드 기준으로도 `approve -> persisted timeline 갱신` 계약은 이미 살아 있었다
- 기존 코드 기준으로도 `approved timeline -> preview/export consumer` 계약은 이미 살아 있었다
- 다만 이 둘 사이의 middle link는 단일 회귀로는 약했기 때문에 아래 두 exact regression을 새로 고정했다
  - `test_review_approval_persists_tts_narration_asset_uri_before_preview_and_export_read_timeline`
  - `test_review_approval_duplicate_tts_narration_clips_flow_through_preview_and_export_outputs`
- `scripts/dev-fast-path.ps1`의 `output-gating` 기본 패턴도 위 두 회귀를 포함하도록 갱신했다
- helper regression `6 passed`
- output-gating focused slice `24 passed`
- current-focused-parallel 재검증 결과
  - backend output-gating `24 passed`
  - backend preflight `55 passed`
  - frontend preflight `25 passed`

이 기록의 의미는 아래와 같다.

- Task 1은 이번 시점에서 `새 runtime bug fix`보다 `already-true contract를 stronger regression과 helper rail로 고정`한 slice로 보는 것이 맞다
- 따라서 다음 실제 작업은 Task 2인 `실제 프로젝트 1개 happy-path smoke + evidence freeze`로 넘어가는 편이 더 효율적이다

## 17. 2026-07-01 시스템 정비 기준 최신 상태

이번 정비에서 현재 코드/문서/검증 기준을 다시 맞춰 확인한 결과, 아래는 더 이상 `계획 중`이 아니라 `실제 연결 완료` 상태다.

- review action family
  - `Approve recommendation` 실제 persistence 연결 완료
  - `Reject recommendation` 실제 persistence 연결 완료
  - `Mark for manual edit` 기존 editor flow 재사용 연결 완료
- reject explicit decision-state contract 반영 완료
- review snapshot의 timeline-local truth 보존 완료
- approve/reject mutation의 rollback hardening 완료
- rollback failure warning surface 추가 완료
- review-action mutation helper 일부 분리로 `local_pipeline` 중복 감소
- pending `tts_replacement` approve 시 target narration clip `asset_uri`가 승인된 `selected_asset_uri`로 즉시 동기화되도록 보강 완료
- pending `tts_replacement` approve 시 같은 target segment를 가리키는 duplicate narration clip이 있어도 첫 clip만 갱신하고 멈추지 않고 모든 target narration clip `asset_uri`를 승인된 `selected_asset_uri`로 동기화하도록 보강 완료
- pending `tts_replacement` approve는 `payload.selected_asset_uri`가 비어 있는 stale recommendation shape를 더 이상 승인 상태로 통과시키지 않고 `400`으로 즉시 거부하도록 보강 완료
- pending `tts_replacement` approve는 `target_segment_id`에 대응하는 narration clip이 없는 stale timeline shape도 더 이상 승인 상태로 통과시키지 않고 `400`으로 즉시 거부하도록 보강 완료
- pending `tts_replacement` approve 뒤 `applied_recommendations` read path는 `decision_state=approved`와 `recommendation_type=tts_replacement`를 approve 응답, timeline, review snapshot에서 일관되게 surface하도록 보강 완료
- approved timeline이라도 snapshot `review_flags/pending_recommendations`가 비어 있는 상태에서 segment-level `review_required=true`가 남아 있으면 subtitle/preview/export를 계속 막는 output gating 경계 고정 완료
- approved timeline의 stale non-bool `segment.review_required` shape는 synthetic output blocker로 오판하지 않고 canonical bool/string 값만 review-required blocker로 인정하도록 보강 완료
- 위 segment-level `review_required` blocker는 last pending recommendation approve 이후에도 synthetic `segment_review_required` flag가 API read path와 review snapshot에 반영돼 review_status와 output gating이 어긋나지 않도록 보강 완료
- malformed duplicated segment entry가 같은 `segment_id`로 반복돼도 synthetic `segment_review_required` blocker detail이 중복으로 불어나지 않도록 dedupe 고정 완료
- synthetic blocker 때문에 effective review status가 `approved -> blocked`로 바뀌는 경우에도 persisted approved `operator_guidance`를 재사용하지 않고 blocked snapshot 기준 guidance를 다시 계산하도록 보강 완료
- unknown dict-shaped `review_flag.code`는 approved timeline output gating blocker로 오판하지 않고 canonical review flag code만 blocker로 유지하도록 보강 완료
- approved timeline의 persisted duplicate `review_flags`도 output blocker detail에서 code/segment 기준으로 dedupe되어 같은 blocker가 중복 노출되지 않도록 보강 완료
- approved timeline의 persisted duplicate `pending_recommendations`도 output blocker detail에서 recommendation id / target segment / recommendation type 기준으로 dedupe되어 같은 blocker가 중복 노출되지 않도록 보강 완료
- partial regeneration preflight의 TTS affected-output label을 `narration audio`에서 `narration track`으로 정렬 완료
- partial regeneration preflight의 `prediction_reasons` 조합을 `source only / target only / both` 기준 테스트로 분리 완료
- partial regeneration preflight의 repeated `segment_ids`는 first-seen order를 유지한 채 dedupe되어 read-only scope와 targeted segment preview에 중복이 남지 않도록 고정 완료
- partial regeneration preflight는 editing session 내부에 같은 `segment_id`가 중복 저장된 stale shape여도 targeted segment preview에서 first-seen segment를 유지하고 뒤의 stale duplicate가 canonical 값을 덮어쓰지 않도록 고정 완료
- partial regeneration preflight는 whitespace가 섞인 legacy session `segment_id`도 trimmed request scope와 같은 세그먼트로 맞춰 targeted segment preview를 비우지 않도록 고정 완료
- partial regeneration preflight의 repeated `fields`도 first-seen order를 유지한 채 dedupe되어 read-only scope와 downstream step preview에 중복이 남지 않도록 고정 완료
- partial regeneration preflight의 stale `visual_overlays: null`도 targeted segment preview에서는 빈 리스트로 정규화되도록 고정 완료
- partial regeneration preflight의 stale non-dict `visual_overlays` entry도 targeted segment preview에서는 제거되고 valid overlay만 유지되도록 고정 완료
- partial regeneration preflight의 empty `visual_overlays` dict entry도 targeted segment preview에서는 제거되고 valid overlay만 유지되도록 고정 완료
- partial regeneration preflight의 stale minimal-dict `visual_overlays` entry도 targeted segment preview에서는 제거되고 valid overlay만 유지되도록 고정 완료
- partial regeneration preflight의 `overlay_type`만 있는 stale `visual_overlays` entry도 targeted segment preview에서는 제거되고 valid overlay만 유지되도록 고정 완료
- partial regeneration preflight의 unknown `overlay_type` stale `visual_overlays` entry도 targeted segment preview에서는 제거되고 canonical overlay만 유지되도록 고정 완료
- partial regeneration preflight의 legacy `hook_title` overlay는 targeted segment preview에서 runtime과 어긋나게 사라지지 않고 기존 shape를 유지하도록 고정 완료
- partial regeneration preflight의 stringified falsey `review_required`도 targeted segment preview와 prediction에서는 실제 `False`로 정규화되도록 고정 완료
- partial regeneration preflight의 stale non-dict `broll_override`도 targeted segment preview에서는 `None`으로 정규화되도록 고정 완료
- partial regeneration preflight의 empty `broll_override` dict도 targeted segment preview에서는 `None`으로 정규화되도록 고정 완료
- partial regeneration preflight의 stale non-dict `music_override`도 targeted segment preview에서는 `None`으로 정규화되도록 고정 완료
- partial regeneration preflight의 empty `music_override` dict도 targeted segment preview에서는 `None`으로 정규화되도록 고정 완료
- partial regeneration preflight의 stale non-dict `tts_replacement`도 targeted segment preview에서는 `None`으로 정규화되도록 고정 완료
- partial regeneration preflight의 empty `tts_replacement` dict도 targeted segment preview에서는 `None`으로 정규화되도록 고정 완료
- partial regeneration preflight의 stale non-list source `review_flags`는 read-only prediction에서 blocker list로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정 완료
- partial regeneration preflight의 stale non-dict-only source `review_flags` list는 read-only prediction에서 blocker list로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정 완료
- partial regeneration preflight의 stale minimal-dict source `review_flags` entry는 read-only prediction에서 blocker flag로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정 완료
- partial regeneration preflight의 `code`만 있는 source `review_flags` stale dict는 read-only prediction에서 blocker flag로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정 완료
- partial regeneration preflight의 unknown `review_flags.code` source stale dict는 read-only prediction에서 blocker flag로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정 완료
- partial regeneration preflight의 stale non-dict-only source `pending_recommendations` list는 read-only prediction에서 blocker list로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정 완료
- partial regeneration preflight의 stale minimal-dict source `pending_recommendations` entry는 read-only prediction에서 blocker recommendation으로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정 완료
- partial regeneration preflight의 `recommendation_id`만 있는 source `pending_recommendations` stale dict는 read-only prediction에서 blocker recommendation으로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정 완료
- partial regeneration preflight의 unknown `recommendation_type` source `pending_recommendations` stale dict는 read-only prediction과 runtime carry-forward 모두에서 blocker recommendation으로 취급하지 않고 clean scope면 `draft` prediction/result를 유지하도록 고정 완료
- partial regeneration runtime도 stale minimal-dict source `pending_recommendations` entry를 그대로 blocker로 들고 가지 않고 clean scope rerun result의 `review_status/pending_recommendations/review_flags`를 `draft/[]/[]`로 유지하도록 고정 완료
- partial regeneration runtime fallback은 source timeline 세그먼트가 비어 있을 때 editing-session의 stringified falsey `review_required`를 실제 `False`로 정규화해 clean scope rerun result의 `review_flags/review_status`를 `[]/draft`로 유지하도록 고정 완료
- partial regeneration runtime fallback은 source timeline 세그먼트가 비어 있을 때 editing-session의 stale invalid `cut_action`을 실제 `keep`으로 정규화해 clean scope rerun result의 regenerated segment `cut_action`을 canonical 값으로 유지하도록 고정 완료
- partial regeneration runtime은 `cut_action` field rerun 시에도 target session segment의 stale invalid `cut_action`을 실제 `keep`으로 정규화해 regenerated segment `cut_action`을 canonical 값으로 유지하도록 고정 완료
- partial regeneration runtime은 preflight와 마찬가지로 whitespace가 섞인 legacy session `segment_id`도 trimmed request scope와 같은 세그먼트로 맞춰 actual rerun target lookup과 regenerated segment 반영이 비지 않도록 고정 완료
- partial regeneration runtime은 actual overlay refresh에서도 unknown `overlay_type` session overlay를 persisted timeline `export_overlays`에 싣지 않고 canonical overlay만 반영하도록 고정 완료
- partial regeneration runtime은 targeted overlay rerun에서 target segment의 stale unknown existing overlay도 preserve path로 되살리지 않고 canonical overlay만 남기도록 고정 완료
- partial regeneration runtime은 preflight와 마찬가지로 nested dict `target_segment_id`가 섞인 stale source `pending_recommendations`를 blocker recommendation으로 복원하지 않고 clean scope rerun result의 `review_status/pending_recommendations/review_flags`를 `draft/[]/[]`로 유지하도록 고정 완료
- current-priority helper `scripts/dev-fast-path.ps1`를 추가해 `output gating / preflight backend / preflight frontend / broader` 검증 레일을 분리 완료
- 일반 preflight UI에서도 blocked prediction reason의 combined 문구 두 개가 모두 surface되는지 frontend focused test로 고정 완료
- refresh-resume 시 restored preflight 응답의 scope가 resumed candidate와 다르면 그 interpretation을 재사용하지 않고 degraded warning으로 내려가도록 frontend focused test로 고정 완료
- refresh-resume 시 restored preflight 응답의 `session_id`가 resumed candidate와 다르면 scope가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내려가도록 frontend focused test로 고정 완료
- refresh-resume 시 restored preflight 응답의 `fields`에 duplicate가 섞여 있으면 scope member가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내려가도록 frontend focused test로 고정 완료
- refresh-resume 시 restored preflight 응답의 `targeted_segments`가 resumed candidate scope와 어긋나면 `segment_ids/fields/session_id`가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내려가도록 frontend focused test로 고정 완료
- refresh-resume 시 restored preflight 응답의 `targeted_segments.review_required`가 현재 editing session과 다르면 `segment_ids/fields/session_id`와 target segment id가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내려가도록 frontend focused test로 고정 완료
- refresh-resume 시 restored preflight 응답의 `targeted_segments.tts_replacement`가 현재 editing session과 다르면 `segment_ids/fields/session_id`와 target segment id가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내려가도록 frontend focused test로 고정 완료
- refresh-resume 시 restored preflight 응답의 `targeted_segments.visual_overlays`가 현재 editing session과 다르면 `segment_ids/fields/session_id`와 target segment id가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내려가도록 frontend focused test로 고정 완료
- refresh-resume 시 restored preflight 응답의 `targeted_segments.broll_override`가 현재 editing session과 다르면 `segment_ids/fields/session_id`와 target segment id가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내려가도록 frontend focused test로 고정 완료
- refresh-resume 시 restored preflight 응답의 `targeted_segments.music_override`가 현재 editing session과 다르면 `segment_ids/fields/session_id`와 target segment id가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내려가도록 frontend focused test로 고정 완료
- frontend preflight helper가 blocked-warning만이 아니라 resumed preflight degraded warning, mismatch non-reuse, resumed warning cleanup, resumed multi-segment scope cleanup까지 실제로 포함하도록 정렬 완료
- frontend preflight field inference는 backend canonical `image_card` overlay를 `image_overlay` rerun field로 올바르게 매핑해 saved overlay가 `caption` fallback으로 잘못 좁혀지지 않도록 고정 완료
- pending `tts_replacement` blocker가 남아 있을 때 subtitle-render도 preview/export와 같은 blocker detail surface와 failed job/no-artifact 상태를 유지하는 회귀를 고정 완료
- blocker가 없는 clean timeline이라도 explicit approval이 없으면 subtitle-render도 preview/export와 같은 failed job/no-artifact 상태를 유지하는 회귀를 고정 완료
- approved timeline을 `reopen review`한 뒤에는 subtitle/preview/export가 다시 explicit approval을 요구하며 막히는 전이 경계를 focused regression으로 고정 완료
- approved timeline의 stale truthy `review_flags` / `pending_recommendations` shape는 output gating에서 실제 blocker로 오판하지 않고 유효 blocker만 기준으로 막도록 고정 완료
- approved timeline을 `reopen review`할 때 stale truthy `review_flags` / `pending_recommendations` shape는 residual blocker로 오판하지 않고 `draft` 상태로 되돌린 뒤 explicit approval gating만 다시 요구하도록 고정 완료
- approved timeline을 `reopen review`한 뒤 stale truthy `review_flags` / `pending_recommendations` shape가 timeline/review snapshot read path를 깨뜨리지 않고 빈 blocker 컬렉션으로 정규화돼 직렬화되도록 고정 완료
- last pending recommendation approve 경로는 stale non-dict `review_flags` entry가 섞여 있어도 review action을 500으로 깨뜨리지 않고 blocker 정리 후 `draft`와 explicit approval gating을 유지하도록 고정 완료
- unsupported partial-regeneration field scope는 preflight prediction으로 흘리지 않고 `400`으로 즉시 거부하며 no-job 상태를 유지하는 계약을 고정 완료
- partial regeneration preflight는 source timeline의 valid `review_flags.code/segment_id` 조합이 `message` 없이 저장된 legacy shape여도 runtime blocker 의미를 보존해 `blocked` prediction으로 올바르게 분류하도록 고정 완료
- partial regeneration preflight는 source timeline의 valid `review_flags.code`라도 nested stale `segment_id` shape면 blocker로 오판하지 않고 clean scope `draft` prediction을 유지하도록 고정 완료
- partial regeneration preflight는 source timeline의 valid `pending_recommendations.target_segment_id`라도 nested stale shape면 blocker로 오판하지 않고 clean scope `draft` prediction을 유지하도록 고정 완료

이번 정비 시점의 실제 검증 결과:

- review-action backend focused slice `6 passed`
- current-focused helper backend output-gating slice `18 passed`
- current-focused helper backend preflight slice `55 passed`
- frontend `src/app.test.tsx` 전체 `66 passed`
- helper `frontend-focused` gate `2 passed`
- frontend build 성공
- full backend regression `314 passed`
- full backend regression은 현재 direct 실행 기준으로 다시 확인됐다
- focused output gating regression `2 passed`
- explicit approval gating regression `1 passed`
- reopen-after-approval gating regression `1 passed`
- preflight focused regression `11 passed`
- preflight normalization hardening 추가 후 `current-focused` backend preflight slice `23 passed`
- frontend preflight blocked-warning regression `1 passed`
- resumed multi-segment scope cleanup regression `1 passed`
- resumed multi-segment field-change cleanup regression `1 passed`
- preflight unsupported-field rejection regression `1 passed`
- current-priority helper `./scripts/dev-fast-path.ps1 -Mode current-focused`
  - backend output-gating slice `18 passed`
  - backend preflight slice `55 passed`
  - frontend preflight slice `25 passed`
- speed-up helper `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
  - backend output-gating slice `18 passed`
  - backend preflight slice `55 passed`
  - frontend preflight slice `25 passed`
- frontend preflight field inference는 backend legacy `image` overlay도 `image_overlay` rerun field로 올바르게 매핑해 saved overlay가 `caption` fallback으로 잘못 좁혀지지 않도록 고정했다
- frontend preflight field inference는 backend legacy `hook_title` overlay도 `visual_overlay` rerun field로 올바르게 매핑해 saved overlay가 `caption` fallback으로 잘못 좁혀지지 않도록 고정했다
- frontend preflight field inference는 backend canonical `visual_overlay`도 `visual_overlay` rerun field로 올바르게 매핑해 saved overlay가 `caption` fallback으로 잘못 좁혀지지 않도록 고정했다
- partial regeneration preflight targeted segment preview는 backend canonical `visual_overlay`도 legacy `hook_title`와 같은 visual-overlay 계열로 보존해 read-only scope에서 saved overlay가 unknown 타입처럼 사라지지 않도록 고정했다
- partial regeneration preflight targeted segment preview는 backend canonical `image_overlay`도 legacy `image`/`image_card` 계열과 같은 이미지 오버레이로 보존해 read-only scope에서 saved overlay가 unknown 타입처럼 사라지지 않도록 고정했다
- partial regeneration preflight targeted segment preview는 backend canonical `table_overlay`도 legacy `table_card` 계열과 같은 테이블 오버레이로 보존해 read-only scope에서 saved overlay가 unknown 타입처럼 사라지지 않도록 고정했다
- partial regeneration runtime은 backend canonical `table_overlay`도 legacy `table_card` 계열과 같은 targeted overlay refresh 대상으로 받아 실제 rerun 결과의 `export_overlays`에서 사라지지 않도록 고정했다
- partial regeneration preflight targeted segment preview는 stale non-bool `review_required` shape도 `False`로 정규화해 clean scope prediction이 불필요하게 `blocked`로 기울지 않도록 고정했다
- partial regeneration preflight targeted segment preview는 nested stale `broll_override.asset_id` shape도 `None`으로 정규화해 invalid override object가 read-only scope에 남지 않도록 고정했다
- partial regeneration preflight targeted segment preview는 nested stale `music_override.asset_id` shape도 `None`으로 정규화해 invalid music override object가 read-only scope에 남지 않도록 고정했다
- partial regeneration preflight targeted segment preview는 nested stale `tts_replacement.recommendation_id` shape도 `None`으로 정규화해 invalid replacement object가 read-only scope에 남지 않도록 고정했다
- broader verification 재실행
  - frontend build 성공
  - full backend regression `314 passed`
- output-gating persisted duplicate review-flag dedupe 추가 후 broader verification 재실행
  - frontend build 성공
  - full backend regression `315 passed`
- preflight duplicate session-segment first-seen preserve 추가 후 broader verification 재실행
  - frontend build 성공
  - full backend regression `316 passed`
- TTS duplicate target narration clip propagation 추가 후 broader verification 재실행
  - frontend build 성공
  - full backend regression `317 passed`
- output-gating persisted duplicate pending-recommendation dedupe 추가 후 broader verification 재실행
  - frontend build 성공
  - full backend regression `318 passed`
- TTS approve missing `selected_asset_uri` hardening 추가 후 focused / broader verification 재실행
  - backend output-gating slice `20 passed`
  - backend preflight slice `55 passed`
  - frontend preflight slice `25 passed`
  - frontend build 성공
  - full backend regression `325 passed`
- TTS approve missing target narration clip hardening 추가 후 focused / broader verification 재실행
  - backend output-gating slice `21 passed`
  - backend preflight slice `55 passed`
  - frontend preflight slice `25 passed`
  - frontend build 성공
  - full backend regression `327 passed`
- TTS approve decision-state read-path hardening 추가 후 focused / broader verification 재실행
  - backend output-gating slice `22 passed`
  - backend preflight slice `55 passed`
  - frontend preflight slice `25 passed`
  - frontend build 성공
  - full backend regression `329 passed`
- 이 체크포인트 직전 latest pushed closeout commit
  - `9df0363 Harden preflight pending recommendation prediction`

이 갱신으로 아래 판단은 더 이상 현재 truth가 아니다.

- `review action placeholder를 실제 persistence contract와 연결할지 여부 설계`
- `Approve recommendation`이 아직 첫 slice만 된 상태라는 판단

현재 기준 남은 핵심 범위는 다시 아래다.

- TTS replacement의 실제 narration/output propagation baseline, approve 후 target clip 반영, missing `selected_asset_uri` stale approval 차단, missing target narration clip stale approval 차단, approved decision-state/read-path surface까지 연결되어 있고, 남은 일은 approval/review contract의 추가 경계 보강이다
- review-required 상태의 subtitle/preview/export gating은 기본 경로와 reopen-after-approval 전이까지 고정돼 있고, 남은 일은 다른 승인 후 반영 규칙 세분화와 추가 경계 검증이다
- partial regeneration preflight의 비파괴 조회 경로는 baseline, duplicate-scope normalization, 일반 preflight blocked-warning combined reason surface까지 연결되어 있고, 남은 일은 backend read-only/prediction contract의 추가 경계와 frontend resume 경계 정리다
- TTS replacement approval/output contract의 아직 테스트로 고정되지 않은 추가 경계 보강
- `local_pipeline`의 다음 대형 분리 후보인 partial regeneration / output 경로 정리

아래 이어지는 `## 16` 이하의 낮은 번호 섹션들도 당시 시점 기록을 보존한 historical log다.
현재 truth나 현재 next slice 판단에는 위 `## 17. 2026-07-01 시스템 정비 기준 최신 상태`를 우선 적용한다.

## 18. 2026-07-03 partial regeneration candidate provider-trace upstream audit closeout

이번 후속 작업에서는 `review/output` 장기 queue를 다시 보되, provider trace audit이 partial regeneration candidate timeline까지 같은 truth를 유지하는지 가장 작은 리스크 1개만 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- 기존 `provider-traces?timeline_id=...&include_upstream=true` filter는 `TIMELINE_BUILD` job에만 기대고 있어 partial regeneration candidate timeline에서는 upstream lineage를 비워 버리는 경계가 있었다
- strict TDD로 `test_provider_trace_audit_timeline_filter_include_upstream_supports_partial_regeneration_candidate` exact regression을 먼저 추가했고, 실제로 candidate timeline의 `upstream_entries == []` RED를 확인했다
- 최소 수정으로 timeline filter가 `TIMELINE_BUILD` job 유무와 관계없이 persisted timeline lineage를 직접 읽도록 바꿔 candidate timeline도 source segment analysis / recommendation upstream entry를 같이 보여주게 맞췄다
- 이번 수정은 review/output gating, TTS approve/output truth, editing-session SSOT, Gemini fallback, persistence 규칙을 건드리지 않고 provider trace audit filter 계산 경계만 좁게 수정했다
- exact regression `1 passed`
- provider-trace audit focused slice `30 passed`
- frontend build 성공
- full backend regression `337 passed`

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration candidate review snapshot audit entry 노출
2. partial regeneration candidate timeline filter direct review guidance 유지
3. partial regeneration candidate timeline filter include_upstream lineage 복원

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 19. 2026-07-03 partial regeneration candidate review guidance job lineage closeout

이번 후속 작업에서는 직전 candidate upstream lineage 복원 다음으로 가장 가까운 남은 provider trace audit 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- 기존 candidate timeline의 `review_guidance` audit entry는 `timeline_id`는 맞아도 `job_id/source_job_id`가 비어 있어, 어떤 partial regeneration job에서 나온 guidance인지 바로 추적할 수 없는 경계가 있었다
- strict TDD로 `test_provider_trace_audit_candidate_review_guidance_entry_uses_partial_regeneration_job_id` exact regression을 먼저 추가했고, 실제로 `job_id == None` RED를 확인했다
- 최소 수정으로 provider trace audit이 review guidance용 timeline->source job 매핑을 `TIMELINE_BUILD`뿐 아니라 `PARTIAL_REGENERATION` 결과까지 읽도록 보강해 candidate timeline도 `partial_regeneration_job_*` lineage를 유지하게 맞췄다
- 이번 수정은 review/output gating, TTS approval/output truth, preflight contract, Gemini fallback, persistence 규칙을 건드리지 않고 provider trace audit read path만 좁게 수정했다
- exact regression `1 passed`
- provider-trace audit focused slice `31 passed`
- broader verification은 이번 turn에서 생략
  - 판단:
    - 같은 provider-trace audit lane 내부의 국소 mapping 수정이라 exact + focused evidence가 직접적이다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration candidate review guidance audit entry 노출
2. partial regeneration candidate review guidance direct timeline filter 유지
3. partial regeneration candidate review guidance job/source job lineage 연결

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 20. 2026-07-03 partial regeneration candidate review guidance attempt job truth closeout

이번 후속 작업에서는 같은 provider trace audit 축 안에서 `review_guidance_attempt`의 candidate truth를 가장 작은 남은 경계 1개로 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- candidate timeline의 `review_guidance_attempt` audit entry는 `job_id/source_job_id`는 partial regeneration job을 가리켜도 `job_type`을 `timeline_build`로 고정해서 surface하는 경계가 있었다
- strict TDD로 `test_provider_trace_audit_candidate_review_guidance_attempt_entry_uses_partial_regeneration_job_truth` exact regression을 먼저 추가했고, 실제로 `job_type == "timeline_build"` RED를 확인했다
- 최소 수정으로 attempt audit event writer가 실제 source job type을 같이 저장하고, read path도 persisted `job_type`을 그대로 surface하도록 바꿔 candidate attempt entry가 `partial_regeneration` truth를 유지하게 맞췄다
- 이번 수정은 review/output gating, TTS approval/output truth, preflight contract, Gemini fallback, persistence 규칙을 건드리지 않고 provider trace audit attempt read/write path만 좁게 수정했다
- exact regression `1 passed`
- provider-trace audit focused slice `32 passed`
- broader verification은 이번 turn에서도 생략
  - 판단:
    - provider trace audit attempt path 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration candidate review guidance attempt audit entry 노출
2. partial regeneration candidate review guidance attempt job/source job lineage 유지
3. partial regeneration candidate review guidance attempt job type truth 유지

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 21. 2026-07-03 partial regeneration candidate review guidance attempt finished_at closeout

이번 후속 작업에서는 같은 candidate `review_guidance_attempt` 축 안에서 남아 있던 `finished_at` truth 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- candidate `review_guidance_attempt` audit entry는 `job_type/job_id/source_job_id`는 partial regeneration truth를 가리켜도 `finished_at`은 빈 문자열로 남는 경계가 있었다
- strict TDD로 `test_provider_trace_audit_candidate_review_guidance_attempt_entry_uses_partial_regeneration_finished_at` exact regression을 먼저 추가했고, 실제로 `finished_at == ""` RED를 확인했다
- 최소 수정으로 attempt read path도 candidate review guidance용 job 매핑을 재사용하게 바꿔 `partial_regeneration_job_*`의 `finished_at`을 그대로 surface하도록 맞췄다
- 이번 수정은 review/output gating, TTS approval/output truth, preflight contract, Gemini fallback, persistence 규칙을 건드리지 않고 provider trace audit attempt read path만 좁게 수정했다
- exact regression `1 passed`
- provider-trace audit focused slice `33 passed`
- broader verification은 이번 turn에서도 생략
  - 판단:
    - provider trace audit attempt timestamp truth 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration candidate review guidance attempt audit entry 노출
2. partial regeneration candidate review guidance attempt job/source job lineage 유지
3. partial regeneration candidate review guidance attempt job type truth 유지
4. partial regeneration candidate review guidance attempt finished_at truth 유지

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 22. 2026-07-03 partial regeneration candidate preview provider-trace created_at closeout

이번 후속 작업에서는 candidate output artifact 쪽에서 가장 작은 남은 provider-trace audit 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- candidate `preview_render` audit entry는 `job_id/source_job_id/timeline_id`는 partial regeneration truth를 가리켜도 `created_at`은 `None`으로 비는 경계가 있었다
- strict TDD로 `test_provider_trace_audit_candidate_preview_render_entry_uses_preview_created_at` exact regression을 먼저 추가했고, 실제로 `created_at == None` RED를 확인했다
- 최소 수정으로 preview read path가 persisted preview row의 `created_at`을 payload에 실어 주고, provider trace audit preview entry도 그 값을 그대로 surface하도록 맞췄다
- 이번 수정은 review/output gating, TTS approval/output truth, preflight contract, Gemini fallback, persistence 규칙을 건드리지 않고 preview provider-trace read path만 좁게 수정했다
- exact regression `1 passed`
- provider-trace audit focused slice `34 passed`
- broader verification은 이번 turn에서도 생략
  - 판단:
    - 같은 provider-trace audit lane 내부의 preview artifact timestamp truth 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration candidate review guidance attempt audit entry 노출
2. partial regeneration candidate review guidance attempt job/source job lineage 유지
3. partial regeneration candidate review guidance attempt job type truth 유지
4. partial regeneration candidate review guidance attempt finished_at truth 유지
5. partial regeneration candidate preview_render created_at truth 유지

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 23. 2026-07-03 partial regeneration candidate export provider-trace created_at closeout

이번 후속 작업에서는 candidate output artifact 쪽에서 preview 다음으로 가장 가까운 남은 provider-trace audit 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- candidate `capcut_export` audit entry는 `job_id/source_job_id/timeline_id`는 partial regeneration truth를 가리켜도 `created_at`은 `None`으로 비는 경계가 있었다
- strict TDD로 `test_provider_trace_audit_candidate_capcut_export_entry_uses_export_created_at` exact regression을 먼저 추가했고, 실제로 `created_at == None` RED를 확인했다
- 최소 수정으로 export read path가 persisted export row의 `created_at`을 payload에 실어 주고, provider trace audit export entry도 그 값을 그대로 surface하도록 맞췄다
- 이번 수정은 review/output gating, TTS approval/output truth, preflight contract, Gemini fallback, persistence 규칙을 건드리지 않고 export provider-trace read path만 좁게 수정했다
- exact regression `1 passed`
- provider-trace audit focused slice `35 passed`
- broader verification은 이번 turn에서도 생략
  - 판단:
    - 같은 provider-trace audit lane 내부의 export artifact timestamp truth 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration candidate review guidance attempt audit entry 노출
2. partial regeneration candidate review guidance attempt job/source job lineage 유지
3. partial regeneration candidate review guidance attempt job type truth 유지
4. partial regeneration candidate review guidance attempt finished_at truth 유지
5. partial regeneration candidate preview_render created_at truth 유지
6. partial regeneration candidate capcut_export created_at truth 유지

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 24. 2026-07-03 partial regeneration candidate failed preview trace filter closeout

이번 후속 작업에서는 review/output과 바로 맞닿은 candidate failed output trace 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- approval 없이 막힌 candidate `preview_render` failed job은 jobs 목록에는 남아도 `provider-traces?timeline_id=<candidate>` filter에서는 빠지는 경계가 있었다
- strict TDD로 `test_provider_trace_audit_candidate_timeline_filter_includes_failed_preview_render_without_approval` exact regression을 먼저 추가했고, 실제로 failed preview entry를 찾지 못하는 `StopIteration` RED를 확인했다
- 원인은 2개였다
  - approval gate failure 경로가 failed provider-trace audit event를 남기지 않았다
  - candidate failed entry가 `source_job_id=partial_regeneration_job_*`를 candidate `timeline_id`로 역매핑하지 못했다
- 최소 수정으로 preview approval-gate failure도 failed provider-trace audit event를 저장하게 하고, partial regeneration job id -> candidate timeline id 역매핑을 provider-trace read path에 추가해 candidate timeline filter가 failed preview entry를 계속 보여주도록 맞췄다
- 이번 수정은 review/output rules, TTS approval/output truth, preflight contract, Gemini fallback, persistence 규칙을 건드리지 않고 candidate failed preview provider-trace save/filter 경계만 좁게 수정했다
- exact regression `1 passed`
- provider-trace audit focused slice `36 passed`
- broader verification은 이번 turn에서도 생략
  - 판단:
    - candidate failed preview trace save/filter 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration candidate review guidance attempt audit entry 노출
2. partial regeneration candidate review guidance attempt job/source job lineage 유지
3. partial regeneration candidate review guidance attempt job type truth 유지
4. partial regeneration candidate review guidance attempt finished_at truth 유지
5. partial regeneration candidate preview_render created_at truth 유지
6. partial regeneration candidate capcut_export created_at truth 유지
7. partial regeneration candidate timeline filter가 approval 없이 막힌 failed preview_render output job도 유지

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 25. 2026-07-03 partial regeneration candidate failed export trace filter closeout

이번 후속 작업에서는 직전 candidate failed preview trace 다음으로 가장 가까운 failed output trace 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- approval 없이 막힌 candidate `capcut_export` failed job도 jobs 목록에는 남아도 `provider-traces?timeline_id=<candidate>` filter에서는 빠지는 경계가 있었다
- strict TDD로 `test_provider_trace_audit_candidate_timeline_filter_includes_failed_capcut_export_without_approval` exact regression을 먼저 추가했고, 실제로 failed export entry를 찾지 못하는 `StopIteration` RED를 확인했다
- 원인은 preview와 같은 approval gate failure 경로였다
  - export approval gate failure 경로가 failed provider-trace audit event를 남기지 않았다
- 최소 수정으로 export approval-gate failure도 failed provider-trace audit event를 저장하게 바꿔 candidate timeline filter가 failed export entry를 계속 보여주도록 맞췄다
- 이번 수정은 review/output rules, TTS approval/output truth, preflight contract, Gemini fallback, persistence 규칙을 건드리지 않고 candidate failed export provider-trace save 경계만 좁게 수정했다
- exact regression `1 passed`
- provider-trace audit focused slice `37 passed`
- broader verification은 이번 turn에서도 생략
  - 판단:
    - candidate failed export trace save 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration candidate review guidance attempt audit entry 노출
2. partial regeneration candidate review guidance attempt job/source job lineage 유지
3. partial regeneration candidate review guidance attempt job type truth 유지
4. partial regeneration candidate review guidance attempt finished_at truth 유지
5. partial regeneration candidate preview_render created_at truth 유지
6. partial regeneration candidate capcut_export created_at truth 유지
7. partial regeneration candidate timeline filter가 approval 없이 막힌 failed preview_render output job도 유지
8. partial regeneration candidate timeline filter가 approval 없이 막힌 failed capcut_export output job도 유지

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 26. 2026-07-03 partial regeneration candidate failed subtitle trace filter closeout

이번 후속 작업에서는 candidate failed preview/export trace 다음으로 가장 가까운 failed output trace 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- approval 없이 막힌 candidate `subtitle_render` failed job도 jobs 목록에는 남아도 `provider-traces?timeline_id=<candidate>` filter에서는 빠지는 경계가 있었다
- strict TDD로 `test_provider_trace_audit_candidate_timeline_filter_includes_failed_subtitle_render_without_approval` exact regression을 먼저 추가했고, 실제로 failed subtitle entry를 찾지 못하는 `StopIteration` RED를 확인했다
- 원인은 preview/export와 같은 approval gate failure 경로였다
  - subtitle approval gate failure 경로가 failed provider-trace audit event를 남기지 않았다
- 최소 수정으로 subtitle approval-gate failure도 failed provider-trace audit event를 저장하게 바꿔 candidate timeline filter가 failed subtitle entry를 계속 보여주도록 맞췄다
- 이번 수정은 review/output rules, TTS approval/output truth, preflight contract, Gemini fallback, persistence 규칙을 건드리지 않고 candidate failed subtitle provider-trace save 경계만 좁게 수정했다
- exact regression `1 passed`
- provider-trace audit focused slice `38 passed`
- broader verification은 이번 turn에서도 생략
  - 판단:
    - candidate failed subtitle trace save 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration candidate review guidance attempt audit entry 노출
2. partial regeneration candidate review guidance attempt job/source job lineage 유지
3. partial regeneration candidate review guidance attempt job type truth 유지
4. partial regeneration candidate review guidance attempt finished_at truth 유지
5. partial regeneration candidate preview_render created_at truth 유지
6. partial regeneration candidate capcut_export created_at truth 유지
7. partial regeneration candidate timeline filter가 approval 없이 막힌 failed preview_render output job도 유지
8. partial regeneration candidate timeline filter가 approval 없이 막힌 failed capcut_export output job도 유지
9. partial regeneration candidate timeline filter가 approval 없이 막힌 failed subtitle_render output job도 유지

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 27. 2026-07-03 partial regeneration runtime nested pending recommendation closeout

이번 후속 작업에서는 provider-trace 축이 아니라 `preflight는 통과하지만 runtime 결과 조회는 깨지는` 실제 계약 비대칭 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- source timeline의 `pending_recommendations[].target_segment_id`가 nested dict stale shape여도 preflight prediction은 이미 blocker recommendation으로 취급하지 않고 `draft`를 예측하고 있었다
- 하지만 실제 partial regeneration runtime은 같은 stale entry를 그대로 carry-forward해서 결과 timeline에 남겼고, 그 결과 partial regeneration result API read path가 `target_segment_id string required`와 `provider_trace required` validation error로 깨졌다
- strict TDD로 `test_editing_session_api_ignores_nested_target_segment_id_source_pending_recommendation_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 result 조회 시 Pydantic validation error가 나는 RED를 확인했다
- 원인은 `_is_runtime_blocking_pending_recommendation(...)`가 `target_segment_id`를 string인지 보지 않고 `str(...)` truthy만 확인해서 nested dict stale shape까지 blocker recommendation으로 통과시키는 점이었다
- 최소 수정으로 runtime pending recommendation 판정이 string `recommendation_id`와 string `target_segment_id`만 blocker recommendation으로 인정하게 좁혀, runtime도 preflight와 같은 기준으로 nested stale shape를 버리도록 맞췄다
- 이번 수정은 review/output rules, TTS approval/output truth, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 runtime pending recommendation normalization 경계만 좁게 수정했다
- exact regression `1 passed`
- focused adjacency slice `5 passed`
- full backend regression `346 passed`

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration preflight가 nested stale `pending_recommendation.target_segment_id`를 blocker prediction으로 복원하지 않음
2. partial regeneration runtime도 같은 nested stale source pending recommendation을 blocker result로 복원하지 않음
3. clean scope rerun result의 `review_status/pending_recommendations/review_flags`가 `draft/[]/[]`로 유지됨
4. partial regeneration result API read path가 stale nested pending recommendation 때문에 validation error로 깨지지 않음

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 28. 2026-07-03 partial regeneration candidate subtitle provider-trace created_at closeout

이번 후속 작업에서는 review/output과 맞닿은 provider-trace audit 축에서 가장 작은 남은 subtitle artifact 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- approval 없이 막힌 candidate failed `subtitle_render` trace는 이미 timeline filter에 보였지만, 성공한 candidate `subtitle_render` artifact entry는 `provider-traces?timeline_id=<candidate>&artifact_type=subtitle_render`에서 아예 빠지고 있었다
- strict TDD로 `test_provider_trace_audit_candidate_subtitle_render_entry_uses_subtitle_created_at` exact regression을 먼저 추가했고, 실제로 filtered `entries`가 빈 배열인 RED를 확인했다
- 원인은 provider-trace read path가 성공 artifact backfill에서 `preview_render`와 `capcut_export`만 append하고 `subtitle_render`는 누락하고 있던 점이었다
- 최소 수정으로 성공한 `subtitle_render` job도 provider-trace artifact entry로 backfill하고 persisted subtitle row의 `created_at`을 그대로 surface하도록 맞췄다
- 이번 수정은 review/output rules, TTS approval/output truth, preflight contract, Gemini fallback, persistence 규칙을 건드리지 않고 subtitle provider-trace read path만 좁게 수정했다
- exact regression `1 passed`
- provider-trace audit focused slice `39 passed`
- broader verification은 이번 turn에서는 다시 돌리지 않았다
  - 판단:
    - subtitle provider-trace read path 한 점에 국한된 수정이라 focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration candidate review guidance attempt audit entry 노출
2. partial regeneration candidate review guidance attempt job/source job lineage 유지
3. partial regeneration candidate review guidance attempt job type truth 유지
4. partial regeneration candidate review guidance attempt finished_at truth 유지
5. partial regeneration candidate subtitle_render created_at truth 유지
6. partial regeneration candidate preview_render created_at truth 유지
7. partial regeneration candidate capcut_export created_at truth 유지
8. partial regeneration candidate timeline filter가 approval 없이 막힌 failed preview_render output job도 유지
9. partial regeneration candidate timeline filter가 approval 없이 막힌 failed capcut_export output job도 유지
10. partial regeneration candidate timeline filter가 approval 없이 막힌 failed subtitle_render output job도 유지

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 29. 2026-07-03 partial regeneration runtime source review flag preserve closeout

이번 후속 작업에서는 provider-trace 축이 아니라 `preflight는 blocked인데 runtime candidate 결과는 draft로 풀리는` 실제 계약 비대칭 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- preflight는 source timeline의 valid `review_flags.code/segment_id` blocker를 보면 이미 `blocked` prediction을 내리고 있었다
- 하지만 실제 partial regeneration runtime은 source `pending_recommendations`만 carry-forward하고 source `review_flags`는 버리고 있어서, 같은 입력에서도 candidate result의 `review_status`가 `draft`로 풀렸다
- strict TDD로 `test_partial_regeneration_result_marks_review_status_blocked_when_preserved_source_review_flag_remains` exact regression을 먼저 추가했고, 실제로 `review_status == "draft"` RED를 확인했다
- 첫 GREEN 시도에서는 source review flag를 복원했지만 legacy `message`가 비어 API response validation error가 나왔고, 여기서 `message` canonicalization까지 이 경계에 포함해야 한다는 점을 추가로 확인했다
- 같은 slice의 역방향 검증으로 `test_editing_session_api_ignores_nested_segment_id_source_review_flag_when_running_partial_regeneration`도 추가했고, 실제로 nested dict `segment_id` stale shape가 runtime preserve 경로를 통과해 partial regeneration result API response validation error를 만드는 RED를 확인했다
- 최소 수정으로 runtime이 valid source blocker review flag를 `code + segment_id` 기준으로 dedupe해 candidate timeline payload에 복원하고, legacy shape도 API contract를 깨지 않도록 default message를 채우게 맞췄다
- 동시에 `_is_runtime_blocking_review_flag(...)`를 string `code`와 string `segment_id`만 blocker review flag로 인정하게 축소해 nested stale shape를 runtime preserve에서 다시 살리지 않도록 맞췄다
- 이번 수정은 review/output rules, TTS approval/output truth, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 runtime source review flag carry-forward 경계만 좁게 수정했다
- exact regression `1 passed`
- focused adjacency slice `6 passed`
- broader verification은 이번 turn에서는 다시 돌리지 않았다
  - 판단:
    - runtime source review flag carry-forward 한 점에 국한된 수정이라 focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration preflight가 valid source review flag blocker를 `blocked` prediction으로 유지함
2. partial regeneration runtime도 같은 source review flag blocker를 candidate result에 복원함
3. candidate result의 `review_status`가 `blocked`로 유지됨
4. preserved source review flag가 legacy message 부재 때문에 API response validation error를 내지 않음
5. nested dict `segment_id`가 섞인 stale source review flag는 runtime에서도 blocker review flag로 복원되지 않음

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 30. 2026-07-03 partial regeneration runtime pending recommendation default provider-trace closeout

이번 후속 작업에서는 직전 nested pending recommendation 경계의 인접면에서 남아 있던 `runtime preserve는 되지만 result API read path가 깨지는` 실제 계약 비대칭 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- preflight는 source timeline의 valid `pending_recommendations` blocker를 보면 이미 `blocked` prediction을 유지하고 있었다
- runtime도 같은 valid source pending recommendation을 candidate 결과에 복원하고 있었지만, legacy source shape에 `provider_trace`가 빠져 있으면 partial regeneration result API read path가 `provider_trace Field required` validation error로 깨졌다
- strict TDD로 `test_partial_regeneration_result_preserves_source_pending_recommendation_with_default_provider_trace` exact regression을 먼저 추가했고, 실제로 result 조회 시 Pydantic validation error가 나는 RED를 확인했다
- 원인은 `_normalized_runtime_pending_recommendations(...)`가 valid blocker recommendation 자체는 통과시키면서도 missing `provider_trace`를 canonicalize하지 않아 response model contract를 깨뜨리는 점이었다
- 최소 수정으로 runtime pending recommendation normalization이 valid source blocker를 복원할 때 dict `provider_trace`가 없으면 `build_provider_trace(final_provider="rule_based_fallback")`를 채우도록 맞췄다
- 이번 수정은 review/output rules, TTS approval/output truth, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 runtime pending recommendation canonicalization 경계만 좁게 수정했다
- exact regression `1 passed`
- focused adjacency slice `6 passed`
- broader fast-path verification
  - `backend output-gating 24 passed`
  - `backend preflight 55 passed`
  - `frontend preflight 25 passed`
- full broader baseline은 이번 turn에서 다시 돌리지 않았다
  - 판단:
    - runtime pending recommendation fallback trace 한 점에 국한된 수정이라 exact + focused + current-focused-parallel evidence로 충분하다
    - latest full broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration preflight가 valid source pending recommendation blocker를 `blocked` prediction으로 유지함
2. partial regeneration runtime도 같은 source pending recommendation blocker를 candidate result에 복원함
3. preserved source pending recommendation에 `provider_trace`가 빠져 있어도 default fallback trace로 canonicalize되어 result API validation error를 내지 않음
4. candidate result의 `review_status`가 `blocked`로 유지됨

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 31. 2026-07-03 partial regeneration candidate review guidance job type closeout

이번 후속 작업에서는 review/output 장기 우선순위 queue를 유지한 채 provider-trace audit 인접면의 가장 작은 남은 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- candidate `review_guidance` audit entry는 이미 `job_id/source_job_id`는 `partial_regeneration_job_*`를 가리키고 있었지만, `job_type`은 여전히 `timeline_build`로 잘못 고정돼 있었다
- strict TDD로 `test_provider_trace_audit_candidate_review_guidance_entry_uses_partial_regeneration_job_type` exact regression을 먼저 추가했고, 실제로 `timeline_build != partial_regeneration` RED를 확인했다
- 원인은 provider-trace read path가 candidate `review_guidance` entry를 복원할 때 linked job을 찾고도 `job_type`만은 `timeline_build` 상수로 넣고 있던 점이었다
- 최소 수정으로 candidate/legacy review guidance entry가 linked timeline job이 있으면 그 job의 `job_type`을 그대로 surface하도록 맞췄다
- 이번 수정은 review/output rules, TTS approval/output truth, preflight contract, Gemini fallback, persistence 규칙을 건드리지 않고 candidate review guidance provider-trace read path의 job type truth만 좁게 수정했다
- exact regression `1 passed`
- focused provider-trace audit slice `40 passed`
- broader verification은 이번 turn에서는 다시 돌리지 않았다
  - 판단:
    - provider-trace review guidance read path의 job type truth 한 점에 국한된 수정이라 exact + provider-trace focused evidence가 더 직접적이다
    - latest full broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration candidate review guidance entry가 `partial_regeneration_job_*`의 job id truth를 유지함
2. partial regeneration candidate review guidance entry가 `partial_regeneration_job_*`의 source job truth를 유지함
3. partial regeneration candidate review guidance entry가 `partial_regeneration_job_*`의 job type truth를 유지함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 32. 2026-07-04 approved timeline stale pending decision-state output gating closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채 `review/output gating`과 `TTS approval/output`이 맞닿는 가장 작은 stale pending 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- approved timeline의 `pending_recommendations`에 이미 `decision_state=approved`인 stale recommendation entry가 잘못 남아 있으면, 실제로는 unresolved blocker가 아니어야 하지만 output gating은 그대로 막고 있었다
- strict TDD로 `test_output_jobs_ignore_approved_decision_state_entries_left_in_pending_recommendations` exact regression을 먼저 추가했고, 실제로 subtitle render가 `400`으로 막히는 RED를 확인했다
- 원인은 `_is_runtime_blocking_pending_recommendation(...)`가 `recommendation_id/target_segment_id/recommendation_type`만 보고 blocker 여부를 판정해, 이미 `approved/rejected`로 끝난 stale entry까지 pending blocker로 취급하던 점이었다
- 최소 수정으로 runtime pending blocker 판정이 explicit `decision_state`가 있을 때는 `pending`만 unresolved blocker로 인정하게 좁혀, API read path와 subtitle / preview / export가 stale approved/rejected entry를 무시하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 stale pending blocker normalization 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `55 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - stale pending decision-state blocker normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approved timeline에 stale `decision_state=approved/rejected` pending recommendation entry가 남아 있어도 unresolved blocker로 오판하지 않음
2. subtitle / preview / export output gating이 stale pending decision-state entry 때문에 다시 막히지 않음
3. timeline read path와 review snapshot도 stale pending entry를 canonical pending blocker로 surface하지 않음

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 33. 2026-07-04 partial regeneration preflight stale pending decision-state prediction closeout

이번 후속 작업에서는 방금 닫은 output gating 경계와 같은 stale pending family 안에서, `preflight contract` 쪽에 남아 있던 가장 작은 prediction 비대칭 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- output gating/runtime은 이미 `decision_state=approved/rejected` stale pending recommendation entry를 unresolved blocker로 보지 않게 맞춰졌지만, partial regeneration preflight prediction은 같은 source shape를 여전히 blocker로 취급하고 있었다
- strict TDD로 `test_editing_session_api_filters_approved_decision_state_source_pending_recommendation_from_preflight_prediction` exact regression을 먼저 추가했고, 실제로 `predicted_review_status_after_rerun == blocked` RED를 확인했다
- 원인은 `services/api/src/videobox_api/main.py`의 `_build_preflight_review_prediction(...)`가 source pending recommendation을 필터링할 때 `decision_state`를 보지 않고 `recommendation_id/target_segment_id/recommendation_type`만으로 blocker 후보를 유지하던 점이었다
- 최소 수정으로 preflight source pending recommendation filter도 explicit `decision_state`가 있을 때 `pending`만 unresolved blocker로 인정하도록 좁혀, preflight prediction이 runtime/output truth와 같은 기준을 쓰게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preflight pending blocker normalization 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- preflight-backend focused slice
  - `55 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `55 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preflight source pending decision-state prediction 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration preflight가 source timeline의 stale `decision_state=approved/rejected` pending recommendation entry를 unresolved blocker prediction으로 복원하지 않음
2. clean scope preflight prediction이 stale pending decision-state entry 때문에 `blocked`로 오염되지 않음
3. preflight prediction과 runtime/output gating이 stale pending decision-state family에서 같은 blocker 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 34. 2026-07-04 timeline builder string false recommendation review_required closeout

이번 후속 작업에서는 stale pending decision-state family를 더 넓히지 않고, `review/output` truth에 바로 닿는 timeline build 경계의 가장 작은 legacy bool-shape 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `TimelineBuilder`는 recommendation dict의 `review_required="false"` 같은 legacy string false shape를 그대로 `bool(...)`로 해석해 pending recommendation과 review blocker로 오판하고 있었다
- strict TDD로 `test_timeline_builder_treats_string_false_recommendation_review_required_as_false` exact regression을 먼저 추가했고, 실제로 auto-apply 가능한 B-roll recommendation이 applied로 가지 않고 pending으로 남는 RED를 확인했다
- 원인은 `packages/core-engine/src/videobox_core_engine/timeline_builder.py`가 dict recommendation/segment payload를 그대로 보존한 채 `bool(recommendation.get("review_required"))`를 사용하던 점이었다
- 최소 수정으로 `TimelineBuilder` 내부 bool-ish normalization을 추가해 dict segment/recommendation payload의 false-like string을 canonical bool로 맞추고, build/build-review-snapshot 계열이 같은 기준을 쓰게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline build truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `55 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - timeline builder bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline build가 recommendation의 `review_required="false"` legacy string shape를 review blocker로 오판하지 않음
2. auto-apply 가능한 recommendation이 stale string false 때문에 pending recommendation으로 밀리지 않음
3. timeline build truth와 output gating truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 35. 2026-07-04 recommendation store string false review_required closeout

이번 후속 작업에서는 방금 닫은 timeline build 경계보다 한 단계 앞단인 저장소 write path에서, 같은 legacy bool-shape가 persisted truth를 오염시키는 가장 작은 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `save_recommendation_run(...)`는 incoming recommendation dict의 `review_required="false"` 같은 legacy string false shape를 그대로 `bool(...)`로 해석해 persisted recommendation과 DB row를 blocker truth로 저장하고 있었다
- strict TDD로 `test_store_save_recommendation_run_treats_string_false_review_required_as_false` exact regression을 먼저 추가했고, 실제로 returned payload의 `review_required is True` RED를 확인했다
- 원인은 `packages/storage-abstractions/src/videobox_storage/local_project_store.py`가 recommendation 저장 시 `auto_apply_allowed/review_required`를 그대로 `bool(...)`로 캐스팅하던 점이었다
- 최소 수정으로 저장소 write path에 bool-ish normalization을 추가해 `auto_apply_allowed/review_required`의 false-like string을 canonical bool로 저장하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 recommendation persistence truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `55 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - recommendation store bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. recommendation 저장 write path가 `review_required="false"` legacy string shape를 blocker truth로 저장하지 않음
2. returned recommendation payload와 DB row가 canonical false를 유지함
3. recommendation persistence truth와 downstream timeline build truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 36. 2026-07-04 recommendation read path legacy string false closeout

이번 후속 작업에서는 저장소 write path 다음 단계인 recommendation read path에서, legacy DB text bool-shape가 read truth를 오염시키는 가장 작은 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `list_recommendation_rows(...)`는 legacy DB row의 `auto_apply_allowed="false"` / `review_required="false"` text 값을 그대로 `bool(...)`로 해석해 read path에서 truthy로 뒤집고 있었다
- strict TDD로 `test_store_list_recommendation_rows_treats_legacy_string_false_columns_as_false` exact regression을 먼저 추가했고, 실제로 `auto_apply_allowed is True` RED를 확인했다
- 원인은 `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 recommendation row hydration이 DB 값을 그대로 `bool(...)`로 캐스팅하던 점이었다
- 최소 수정으로 recommendation read path도 같은 bool-ish normalization을 재사용해 legacy string false를 canonical false로 읽도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 recommendation read truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `55 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - recommendation read-path bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. recommendation read path가 legacy DB text `"false"` shape를 truthy blocker로 읽지 않음
2. hydrated recommendation row가 canonical false를 유지함
3. recommendation read truth와 write truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 37. 2026-07-04 editing session legacy string false segment review_required closeout

이번 후속 작업에서는 recommendation bool-ish family를 더 넓히지 않고, editing-session SSOT에 직접 닿는 segment read path의 가장 작은 legacy bool-shape 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `list_segments(...)`와 `build_editing_session(...)`는 legacy segment row의 `review_required="false"` text 값을 그대로 truthy로 취급해 editing session 생성 시 `review_required=True`로 오염시키고 있었다
- strict TDD로 `test_editing_session_api_normalizes_legacy_string_false_segment_review_required_from_store` exact regression을 먼저 추가했고, 실제로 create editing session 응답의 `review_required`가 `True`로 뒤집히는 RED를 확인했다
- 원인은 `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 segment row hydration과 `packages/core-engine/src/videobox_core_engine/editing_session.py`의 session segment 빌드가 모두 `bool(...)` 기반으로 legacy string false를 읽던 점이었다
- 최소 수정으로 두 read path에 같은 bool-ish normalization을 적용해 legacy segment row의 false-like string을 canonical false로 읽도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 editing-session segment truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- preflight-backend focused slice
  - `56 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - editing session segment bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. editing session 생성 read path가 legacy segment row의 `review_required="false"` shape를 truthy review-required로 읽지 않음
2. session segment payload와 downstream preflight targeted segment가 canonical false를 유지함
3. segment read truth와 editing-session SSOT가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 38. 2026-07-04 segment analysis write path string false segment review_required closeout

이번 후속 작업에서는 방금 닫은 editing-session segment read path보다 한 단계 앞단인 persistence write path에서, 같은 legacy bool-shape가 stored segment truth를 오염시키는 가장 작은 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `save_segment_analysis(...)`는 incoming segment dict의 `review_required="false"` 값을 그대로 truthy로 취급해 persisted `segments.review_required`를 `1`로 저장하고 있었다
- strict TDD로 `test_editing_session_api_preserves_string_false_segment_review_required_after_segment_analysis_write` exact regression을 먼저 추가했고, 실제로 segment analysis 저장 이후 create editing session 응답의 `review_required`가 `True`로 오염되는 RED를 확인했다
- 원인은 `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 segment insert path가 `review_required`를 그대로 `bool(...)` 기반 truthiness로 저장하던 점이었다
- 최소 수정으로 segment analysis write path에도 같은 bool-ish normalization을 적용해 false-like string을 canonical false로 저장하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 segment persistence truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- preflight-backend focused slice
  - `56 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - segment analysis write-path bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. segment analysis 저장 write path가 `review_required="false"` legacy string shape를 truthy review-required로 저장하지 않음
2. persisted segment row와 downstream editing session이 canonical false를 유지함
3. segment write truth와 read truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 39. 2026-07-04 timeline response legacy string false recommendation fields closeout

이번 후속 작업에서는 bool-ish false family를 더 넓히지 않고, timeline/read contract에 직접 닿는 API response layer의 가장 작은 legacy recommendation 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `_normalize_recommendations_for_response(...)`는 legacy timeline payload 안의 `auto_apply_allowed="false"` / `review_required="false"` text 값을 그대로 truthy로 취급해 timeline API response에서 `True`로 뒤집고 있었다
- strict TDD로 `test_timeline_api_normalizes_legacy_string_false_pending_recommendation_fields` exact regression을 먼저 추가했고, 실제로 timeline API의 pending recommendation response에서 두 필드가 모두 `True`로 뒤집히는 RED를 확인했다
- 원인은 API response normalization이 recommendation bool 필드를 raw `bool(...)`로 캐스팅하던 점이었다
- 최소 수정으로 response layer에도 bool-ish normalization helper를 추가해 legacy false-like string을 canonical false로 읽도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline/read truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - API response bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline API response가 legacy recommendation payload의 `auto_apply_allowed="false"` / `review_required="false"` shape를 truthy recommendation state로 읽지 않음
2. pending recommendation response가 canonical false를 유지함
3. timeline/read truth와 downstream review snapshot/partial regeneration result response가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 40. 2026-07-04 approve rollback legacy string false recommendation fields closeout

이번 후속 작업에서는 timeline/read response 경계보다 한 단계 아래인 recommendation rollback persistence에서, downstream failure 후 legacy false-like payload가 DB row truth를 다시 오염시키는 가장 작은 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- review state 저장 실패 후 rollback이 실행될 때 `packages/core-engine/src/videobox_core_engine/local_pipeline.py`는 original recommendation payload의 `auto_apply_allowed="false"` / `review_required="false"` 값을 raw `bool(...)`로 다시 써서 DB row를 `(1, 1, "pending")`로 오염시키고 있었다
- strict TDD로 `test_review_snapshot_api_approve_rollback_normalizes_legacy_string_false_recommendation_fields` exact regression을 먼저 추가했고, 실제로 approve rollback 뒤 recommendation row가 `(0, 0, "pending")`이 아니라 `(1, 1, "pending")`가 되는 RED를 확인했다
- 원인은 `_rollback_recommendation_review_mutation(...)`의 recommendation row restore path가 legacy false-like string을 canonicalize하지 않던 점이었다
- 최소 수정으로 rollback persistence path에도 runtime bool-ish normalization을 적용해 legacy false-like recommendation fields를 canonical false DB 값으로 복구하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 recommendation rollback truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - rollback persistence bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approve rollback persistence가 legacy recommendation payload의 `auto_apply_allowed="false"` / `review_required="false"` shape를 truthy DB row로 복구하지 않음
2. downstream failure 뒤 recommendation row가 canonical false와 original decision state를 유지함
3. recommendation rollback truth와 timeline/read truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 41. 2026-07-04 preview renderer string false TTS recommendation review_required closeout

이번 후속 작업에서는 review mutation rollback보다 더 사용자 출력에 가까운 `TTS approval/output` 인접면에서, preview narration source 선택이 legacy false-like recommendation field 때문에 틀어지는 가장 작은 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/preview_renderer.py`는 applied `tts_replacement` recommendation의 `auto_apply_allowed="true"` / `review_required="false"` 값을 raw `bool(...)`로 읽어 실제 selected narration source 대신 original narration source를 preview HTML에 노출하고 있었다
- strict TDD로 `test_preview_renderer_treats_string_false_tts_recommendation_review_required_as_false` exact regression을 먼저 추가했고, 실제로 preview HTML이 selected TTS source를 잃고 original narration source를 계속 노출하는 RED를 확인했다
- 원인은 preview renderer의 TTS applied-segment 판정이 bool-ish false normalization 없이 raw truthiness를 쓰던 점이었다
- 최소 수정으로 preview renderer에도 bool-ish normalization helper를 추가해 legacy false-like recommendation fields를 canonical bool로 해석하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preview/TTS read truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview renderer bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preview renderer가 applied `tts_replacement` recommendation의 `review_required="false"` legacy string shape를 blocker로 오판하지 않음
2. preview HTML narration source가 selected TTS source를 유지함
3. preview/TTS read truth와 timeline/recommendation normalization이 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 42. 2026-07-04 review snapshot fallback legacy string false recommendation decision-state closeout

이번 후속 작업에서는 preview/TTS read path 다음 인접면인 review snapshot fallback classification에서, legacy false-like recommendation payload가 applied recommendation truth를 pending blocker로 뒤집는 가장 작은 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `_derive_recommendation_decision_state(...)`는 legacy recommendation payload의 `auto_apply_allowed="true"` / `review_required="false"` 값을 raw truthiness로 읽어 review snapshot fallback에서 `pending`으로 오판하고 있었다
- strict TDD로 `test_store_build_review_snapshot_treats_legacy_string_false_recommendation_as_approved` exact regression을 먼저 추가했고, 실제로 review snapshot의 `applied_recommendations`가 비고 recommendation이 pending 쪽으로 밀리는 RED를 확인했다
- 원인은 fallback decision-state derivation이 bool-ish false normalization 없이 raw truthiness를 쓰던 점이었다
- 최소 수정으로 `_derive_recommendation_decision_state(...)`도 같은 bool-ish normalization을 사용하도록 맞춰 legacy recommendation payload를 canonical decision-state로 분류하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot fallback truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review snapshot fallback decision-state normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot fallback classification이 legacy recommendation payload의 `review_required="false"` shape를 pending blocker로 오판하지 않음
2. auto-apply 가능한 recommendation이 applied recommendation truth를 유지함
3. review snapshot fallback truth와 recommendation persistence/read truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 43. 2026-07-04 review guidance string false segment review_required closeout

이번 후속 작업에서는 review snapshot fallback 다음 인접면인 operator guidance prompt surface에서, legacy false-like segment payload가 attention-required segment를 잘못 늘리는 가장 작은 경계 1개를 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_segments_needing_attention(...)`는 segment payload의 `review_required="false"` 값을 raw truthiness로 읽어 operator guidance prompt에 실제로는 review가 필요 없는 segment까지 attention 대상으로 포함하고 있었다
- strict TDD로 `test_review_guidance_builder_ignores_string_false_segment_review_required` exact regression을 먼저 추가했고, 실제로 `["seg_001", "seg_002"]`가 나와야 할 자리에 `["seg_002"]`만 남아야 하는 RED를 확인했다
- 원인은 operator guidance의 segment attention 계산이 bool-ish false normalization 없이 raw truthiness를 쓰던 점이었다
- 최소 수정으로 review guidance에도 bool-ish normalization helper를 추가해 legacy false-like segment fields를 canonical bool로 해석하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 operator guidance prompt truth 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 passed`
- output-gating focused slice
  - `24 passed`
- current-focused-parallel
  - backend output-gating `24 passed`
  - backend preflight `56 passed`
  - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - operator guidance bool-ish normalization 한 점에 국한된 수정이라 exact + focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. operator guidance prompt가 legacy segment payload의 `review_required="false"` shape를 attention-required segment로 오판하지 않음
2. `segments needing attention` 계산이 실제 review-required segment만 유지함
3. operator guidance truth와 segment persistence/read truth가 bool-ish false shape에서 같은 기준을 사용함

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 16. 2026-06-30 review recommendation approve persistence 착수 기록

이번 후속 작업으로 `review action placeholder -> first approve persistence`의 최소 slice는 착수 및 focused verification까지는 됐다고 본다.

이번에 추가로 확인된 사실은 아래와 같다.

- review panel의 `Approve recommendation` 버튼이 실제 approve API 호출로 연결됐다
- backend에서 pending recommendation을 applied recommendation으로 이동시키고 관련 review flag를 제거할 수 있다
- recommendation row의 `auto_apply_allowed/review_required` 값이 승인 결과에 맞게 갱신된다
- approve 후 review snapshot과 timeline refresh가 같이 일어나도록 frontend 배선이 연결됐다
- backend focused test `1 passed`
- frontend focused test `1 passed`

다만 이 단계는 아직 완결 milestone로 닫지 않았다.

- 아직 확인하지 않은 것
  - frontend build
  - full backend regression
  - reject/manual-edit persistence
- 따라서 현재 상태는 `작동하는 첫 slice`이지 `완료된 review action family`는 아니다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- approve persistence slice의 broader verification
- non-target recommendation/flag 보존에 대한 역방향 검증 보강
- reject/manual-edit 중 다음 최소 persistence slice 선정

## 15. 2026-06-30 thin editor B-roll override clear 기록

이번 후속 작업으로 `thin editor B-roll override clear/remove` slice는 완료로 봐도 된다.

이번에 추가로 확인된 사실은 아래와 같다.

- editing session 도메인과 API에서 saved B-roll override clear 경로가 실제로 연결됐다
- thin editor에서 `Clear B-roll override`를 직접 실행할 수 있다
- clear 후 active candidate invalidation은 기존 mutation 규칙 그대로 유지된다
- clear 후 rerun scope의 `broll` 선택 상태도 stale하게 남지 않는다
- focused backend regression `143 passed`
- frontend focused test `46 passed`
- frontend build 성공
- full backend regression `234 passed`

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. B-roll override save
2. B-roll override clear/remove
3. clear 후 candidate invalidation
4. clear 후 rerun scope cleanup

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- review->editor recommendation mapping coverage 중 `broll` happy-path 보강
- review action placeholder를 실제 persistence contract와 연결할지 여부 설계

## 14. 2026-06-30 thin editor music override clear 기록

이번 후속 작업으로 `thin editor music override clear/remove` slice는 완료로 봐도 된다.

이번에 추가로 확인된 사실은 아래와 같다.

- editing session 도메인과 API에서 saved music override clear 경로가 실제로 연결됐다
- thin editor에서 `Clear music override`를 직접 실행할 수 있다
- clear 후 active candidate invalidation은 기존 mutation 규칙 그대로 유지된다
- clear 후 rerun scope의 `music` 선택 상태도 stale하게 남지 않는다
- focused backend regression `141 passed`
- frontend focused test `45 passed`
- frontend build 성공
- full backend regression `232 passed`

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. music override save
2. music override clear/remove
3. clear 후 candidate invalidation
4. clear 후 rerun scope cleanup

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- review->editor recommendation mapping coverage 중 `broll` happy-path 보강
- review action placeholder를 실제 persistence contract와 연결할지 여부 설계

## 92. 2026-07-04 preflight mixed-case pending recommendation type prediction closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `preflight contract`에 가장 가까운 source pending recommendation stale-shape 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `_build_preflight_review_prediction(...)`는 source pending recommendation의 `recommendation_type`을 `strip()`만 한 채 `VALID_PREVIEW_RECOMMENDATION_TYPES`와 비교하고 있어, mixed-case stale blocker인 `" TTS_REPLACEMENT "`를 valid unresolved blocker로 복원하지 못하고 `draft` prediction으로 흘리고 있었다
- strict TDD로 `test_editing_session_api_preserves_mixed_case_source_pending_recommendation_type_in_preflight_prediction` exact regression을 먼저 추가했고, 실제로 `predicted_review_status_after_rerun == "blocked"` 기대가 `draft`로 깨지는 RED를 확인했다
- 원인은 preflight prediction helper의 source pending recommendation type 필터가 다른 mixed-case canonicalization 경계들과 달리 lowercase normalization을 재사용하지 않던 점이었다
- 최소 수정으로 type 비교를 `strip().lower()` 기준으로 좁혀, mixed-case stale pending recommendation blocker도 canonical lowercase type 기준으로 `blocked` prediction truth를 유지하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preflight prediction helper의 mixed-case blocker type 판정 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- preflight-backend focused slice
  - `57 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preflight prediction helper의 type canonicalization 한 점 수정이라 exact + preflight focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration preflight가 source timeline의 mixed-case stale pending recommendation type도 valid unresolved blocker로 유지한다
2. clean target segment여도 source blocker가 있으면 `predicted_review_status_after_rerun`가 `draft`로 풀리지 않고 `blocked` truth를 유지한다
3. preflight prediction의 pending recommendation type 판정이 다른 mixed-case recommendation canonicalization 경계와 같은 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 93. 2026-07-04 partial regeneration mixed-case pending recommendation dedupe closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `preflight contract`와 바로 맞닿은 partial regeneration runtime carry-forward 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 runtime pending recommendation dedupe key는 `recommendation_type`을 raw `strip()` 기준으로만 비교하고 있어, source timeline에 `"tts_replacement"`와 `" TTS_REPLACEMENT "`가 함께 남아 있으면 같은 blocker인데도 partial regeneration result의 `pending_recommendations`에 2개가 동시에 남고 있었다
- strict TDD로 `test_editing_session_api_deduplicates_mixed_case_source_pending_recommendations_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 result timeline의 `pending_recommendations` 길이가 기대한 `1`이 아니라 `2`가 되는 RED를 확인했다
- 원인은 runtime carry-forward 초입의 `_normalized_runtime_pending_recommendations(...)`와 persisted timeline merge 직전의 `existing_pending_keys`가 모두 recommendation type canonicalization 없이 dedupe key를 만들고 있던 점이었다
- 최소 수정으로 두 dedupe key 모두 `_canonical_runtime_recommendation_type(...)`를 재사용하게 맞춰, mixed-case stale pending blocker duplicate도 canonical lowercase type 기준으로 한 번만 유지되게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration runtime pending blocker dedupe 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - mixed-case preflight/runtime pending blocker family exact `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - runtime carry-forward pending dedupe key canonicalization 두 군데만 바뀐 좁은 수정이라 exact + 인접 family exact evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration runtime이 source timeline의 mixed-case stale pending recommendation duplicate를 한 번만 유지한다
2. runtime result의 `pending_recommendations`와 `review_flags`가 같은 blocker를 중복 surface하지 않는다
3. preflight prediction의 mixed-case blocker 판단과 runtime carry-forward dedupe가 같은 canonical lowercase recommendation type 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 94. 2026-07-04 recommendation run mixed-case type read closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 recommendation artifact read-path 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `get_recommendation_run(...)`는 saved recommendation run JSON의 top-level `recommendation_type`을 raw 문자열로 비교하고 있어, `" BROLL "` 같은 stale mixed-case shape가 들어오면 artifact read가 바로 `Recommendation run type mismatch`로 실패하고 있었다
- strict TDD로 `test_recommendation_run_accepts_mixed_case_recommendation_type` exact regression을 먼저 추가했고, 실제로 `store.get_recommendation_run(...)`가 `KeyError`를 던지는 RED를 확인했다
- 원인은 recommendation run loader가 row/review snapshot/timeline 쪽에서 이미 맞춘 canonical recommendation type 비교를 file-level recommendation run read path에는 재사용하지 않던 점이었다
- 최소 수정으로 loader의 type 검증도 `_canonical_recommendation_type(...)`를 재사용하게 맞춰, mixed-case stale recommendation run artifact도 canonical lowercase type 기준으로 계속 읽히게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 recommendation run read-path의 mixed-case type 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - recommendation run read family exact `2 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - recommendation run loader의 file-level type 비교 한 줄 수정이라 exact + 인접 read-path exact evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. recommendation run read path가 mixed-case stale top-level `recommendation_type`도 canonical lowercase type 기준으로 허용한다
2. recommendation result/output build 경로가 stale artifact type casing 때문에 바로 끊기지 않는다
3. recommendation run type 허용과 provider-trace backfill read-path가 같은 artifact read 경계에서 함께 유지된다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 95. 2026-07-04 recommendation run mixed-case type surface closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, 방금 닫은 recommendation run read-path 경계와 같은 가족 안에서 returned surface canonicalization 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `get_recommendation_run(...)`는 mixed-case stale top-level `recommendation_type`을 더 이상 read failure로 막지는 않았지만, returned payload에는 `" BROLL "` 같은 raw casing을 그대로 남기고 있었다
- strict TDD로 `test_recommendation_run_accepts_mixed_case_recommendation_type`의 기대값을 canonical `"broll"` surface로 강화했고, 실제로 `loaded_run["recommendation_type"] == " BROLL "` RED를 확인했다
- 원인은 loader가 type validation에서는 canonical comparison을 이미 쓰고 있으면서도, 반환 payload에는 canonicalized type을 다시 쓰지 않던 점이었다
- 최소 수정으로 accepted type을 returned payload에도 `_canonical_recommendation_type(...)` 결과로 다시 넣어, recommendation run read-path의 artifact truth와 surface truth를 같은 lowercase 기준으로 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 recommendation run read family의 type surface 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - recommendation run read family exact `2 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - loader returned surface canonicalization 한 줄 수정이라 exact + 인접 read-path exact evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. recommendation run read path가 mixed-case stale top-level `recommendation_type`도 canonical lowercase type 기준으로 읽는다
2. returned payload surface도 raw casing이 아니라 canonical lowercase type을 유지한다
3. recommendation run type surface와 provider-trace backfill read-path가 같은 artifact read 경계에서 함께 유지된다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 96. 2026-07-04 top-level AGENTS instruction promotion closeout

이번 후속 작업에서는 이미 문서 SSOT에 저장된 운영 규정을 저장소 최상위에서도 바로 보이게 해야 한다는 요구에 맞춰, 중복 없이 연결되는 top-level instruction 경계만 좁게 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- 현재 브랜치의 개발 운영 규정 본문은 `docs/development-fast-path.ko.md`의 `## 10. 고정 운영 규정`에 있지만, 저장소 루트에는 이를 바로 가리키는 `AGENTS.md`가 없어서 최상위 진입점이 비어 있었다
- 사용자가 제시한 `AGENTS.md` 원칙은 기존 운영 규정과 충돌하기보다, 정확성 우선, 리스크 공개, 관련 없는 변경 금지, 검증 전 완료 금지 같은 상위 태도를 더 분명하게 만드는 역할에 가깝다
- 그래서 같은 규정을 여러 문서에 복제하지 않고, 루트 `AGENTS.md`는 최상위 지침 요약과 SSOT 링크 역할만 맡기고 authoritative 운영 본문은 계속 fast-path 문서에 두는 편이 drift를 줄이는 가장 작은 수정이었다
- 구현 계획서 상단과 fast-path 규정 섹션도 루트 `AGENTS.md`를 함께 참조하도록 좁게 연결해, 다음 turn부터는 계획서만 읽어도 최상위 지침이 빠지지 않게 맞췄다

이번 turn의 verification은 아래와 같다.

- 상태 확인
  - `git status --short --branch`
- 최근 closeout 확인
  - `git log -5 --oneline`
- SSOT 재확인
  - `docs/implementation-plan.ko.md`
  - `docs/development-status-2026-06-29.ko.md`
  - `docs/development-fast-path.ko.md`
- diff 확인
  - 루트 `AGENTS.md` 추가와 상위 SSOT 링크 수정만 들어갔는지 확인

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. 저장소 최상위에서도 개발 운영 지침을 바로 읽을 수 있다
2. 운영 규정 본문은 fast-path SSOT에 두고, 루트 `AGENTS.md`는 링크형 상위 진입점으로 유지한다
3. 구현 계획서와 fast-path 문서가 같은 top-level instruction을 함께 참조한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 97. 2026-07-04 output blocker mixed-case pending recommendation detail closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 output blocker detail surface의 mixed-case recommendation type 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_normalized_runtime_pending_recommendations(...)`는 mixed-case stale pending recommendation을 blocker로는 올바르게 복원하고 dedupe key에도 canonical lowercase type을 쓰고 있었지만, normalized item 자체의 `recommendation_type`은 raw casing을 그대로 남기고 있었다
- 그 결과 `_ensure_timeline_has_no_blockers(...)`가 만드는 output gating 에러 detail에는 `" TTS_REPLACEMENT :rec_tts_seg_001@seg_001"` 같은 raw stale type surface가 그대로 노출되고 있었다
- strict TDD로 `test_output_blocker_detail_canonicalizes_mixed_case_pending_recommendation_type` exact regression을 먼저 추가했고, 실제로 preview output gating detail이 canonical `"tts_replacement:rec_tts_seg_001@seg_001"` 대신 raw mixed-case shape를 내보내는 RED를 확인했다
- 최소 수정으로 runtime pending recommendation normalization 단계에서 `recommendation_type`도 `_canonical_runtime_recommendation_type(...)` 결과로 다시 써, blocker 판정 / dedupe / detail surface가 모두 같은 canonical lowercase type 기준을 쓰도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output blocker detail surface 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - 결과: `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - runtime blocker normalization 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approved timeline output gating detail이 mixed-case stale pending recommendation type도 canonical lowercase type 기준으로 surface한다
2. runtime blocker dedupe key와 blocker detail surface가 같은 canonical recommendation type 기준을 사용한다
3. output blocker detail이 stale raw casing 때문에 브랜치 전체 canonicalization 흐름과 어긋나지 않는다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 98. 2026-07-04 output gating mixed-case review flag code closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 mixed-case review flag code blocker 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 runtime output gating은 `review_flags.code`를 `strip()`만 한 채 `VALID_RUNTIME_BLOCKING_REVIEW_FLAG_CODES`와 비교하고 있어, `" TTS_REPLACEMENT_REVIEW_REQUIRED "` 같은 mixed-case stale flag code를 실제 blocker로 복원하지 못하고 있었다
- 그 결과 approved timeline에 unresolved review flag가 남아 있어도 preview output이 `400`이 아니라 `202`로 통과하는 실제 계약 누수가 있었다
- strict TDD로 `test_output_gating_blocks_mixed_case_review_flag_code_on_approved_timeline` exact regression을 먼저 추가했고, 실제로 preview render 시작이 허용되는 RED를 확인했다
- 최소 수정으로 runtime review flag normalization에 `_canonical_runtime_review_flag_code(...)` helper를 추가하고, blocker 판정 / dedupe key / normalized surface 모두 같은 lowercase code 기준을 쓰도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output gating review flag code 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode output-gating`
  - 결과: `24 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - runtime review flag code canonicalization 한 점 수정이라 exact + output-gating focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. approved timeline output gating이 mixed-case stale `review_flags.code`도 canonical lowercase blocker code로 복원한다
2. blocker 판정과 detail surface가 같은 canonical review flag code 기준을 사용한다
3. unresolved review flag가 raw casing 때문에 output approval을 우회하지 못한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 99. 2026-07-04 preflight mixed-case source review flag code closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `preflight contract`에 가장 가까운 source review flag code canonicalization 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `_build_preflight_review_prediction(...)`는 source `review_flags.code`를 `strip()`만 한 채 `VALID_PREVIEW_REVIEW_FLAG_CODES`와 비교하고 있어, `" TTS_REPLACEMENT_REVIEW_REQUIRED "` 같은 mixed-case stale blocker code를 unresolved blocker로 복원하지 못하고 있었다
- 그 결과 source timeline에 review blocker가 남아 있어도 preflight prediction이 `blocked`가 아니라 `draft`로 흘러, rerun 전 read-only prediction contract가 output gating truth와 어긋나고 있었다
- strict TDD로 `test_editing_session_api_marks_preflight_blocked_when_source_review_flag_has_mixed_case_valid_code` exact regression을 먼저 추가했고, 실제로 mixed-case stale source review flag가 있는 preflight response가 `draft`를 반환하는 RED를 확인했다
- 최소 수정으로 preflight helper에 `_canonical_preview_review_flag_code(...)`를 추가하고 source review flag filter가 lowercase code 기준을 쓰도록 맞춰, mixed-case stale blocker code도 canonical preview blocker code 기준으로 `blocked` prediction을 유지하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preflight source review flag code 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - `./scripts/dev-fast-path.ps1 -Mode preflight-backend`
  - 결과: `58 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preflight helper의 review flag code canonicalization 한 점 수정이라 exact + preflight-backend focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration preflight가 mixed-case stale source `review_flags.code`도 canonical lowercase blocker code 기준으로 복원한다
2. source blocker가 남아 있으면 preflight prediction이 `draft`로 풀리지 않고 `blocked` truth를 유지한다
3. preflight prediction의 review flag code 판정이 output gating 쪽 canonical blocker code 규칙과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 100. 2026-07-04 partial regeneration runtime mixed-case source review flag carry-forward closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `preflight contract`와 바로 맞닿은 partial regeneration runtime source review-flag carry-forward 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 partial regeneration runtime은 source `review_flags.code`를 `strip()`만 한 채 `VALID_RUNTIME_BLOCKING_REVIEW_FLAG_CODES`와 비교하고 있어, `" TTS_REPLACEMENT_REVIEW_REQUIRED "` 같은 mixed-case stale blocker code를 candidate timeline 결과에 다시 복원하지 못하고 있었다
- 그 결과 source blocker가 남아 있어도 partial regeneration result timeline의 `review_status`가 `blocked`가 아니라 `draft`로 풀리는 실제 계약 누수가 있었다
- strict TDD로 `test_partial_regeneration_result_marks_review_status_blocked_when_preserved_source_review_flag_has_mixed_case_valid_code` exact regression을 먼저 추가했고, 실제로 result timeline이 `draft`를 반환하는 RED를 확인했다
- 최소 수정으로 runtime source review-flag carry-forward가 `_canonical_runtime_review_flag_code(...)`를 재사용하도록 맞추고, carry-forward dedupe key도 같은 lowercase code 기준을 쓰게 해 mixed-case stale source blocker를 canonical surface로 한 번만 복원하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration runtime source review-flag carry-forward 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - partial regeneration source review-flag family exact
  - 결과: `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - runtime source review-flag carry-forward와 dedupe key 두 지점만 바뀐 좁은 수정이라 exact + 인접 family evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration runtime이 mixed-case stale source `review_flags.code` blocker도 candidate timeline 결과에 다시 복원한다
2. result timeline의 `review_status`와 `review_flags` surface가 canonical lowercase review flag code 기준으로 유지된다
3. source review-flag carry-forward 판정과 dedupe key가 preflight/output canonicalization 흐름과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 101. 2026-07-04 partial regeneration broll refresh mixed-case applied recommendation closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 인접한 partial regeneration runtime applied recommendation refresh 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `broll_refresh`는 source timeline의 stale applied recommendation을 지울 때 `recommendation_type`을 `strip()`만 한 채 `RecommendationType.BROLL.value`와 비교하고 있어, `" BROLL "` 같은 mixed-case stale shape를 기존 B-roll recommendation으로 인식하지 못하고 있었다
- 그 결과 manual B-roll override로 partial regeneration을 다시 돌려도 stale applied B-roll clip이 제거되지 않고 새 manual clip과 함께 중복으로 남는 실제 계약 누수가 있었다
- strict TDD로 `test_editing_session_api_replaces_mixed_case_stale_applied_broll_recommendation_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 stale clip과 manual clip이 함께 남는 RED를 확인했다
- 최소 수정으로 `broll_refresh`와 같은 가족인 `music_refresh`의 stale recommendation 제거 비교도 `_canonical_runtime_recommendation_type(...)`를 재사용하도록 맞춰, mixed-case stale applied recommendation도 canonical lowercase type 기준으로 기존 recommendation을 교체하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration refresh family의 mixed-case stale applied recommendation 제거 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - partial regeneration applied recommendation refresh family exact
  - 결과: `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - `broll_refresh`/`music_refresh`의 stale removal comparison 두 줄만 바뀐 좁은 수정이라 exact + 인접 family evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration runtime의 `broll_refresh`가 mixed-case stale applied `recommendation_type`도 기존 B-roll recommendation으로 인식해 교체한다
2. manual B-roll override rerun 뒤 stale B-roll clip과 새 manual clip이 동시에 남지 않는다
3. refresh family의 stale applied recommendation 제거 기준이 TTS canonicalization 흐름과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 102. 2026-07-04 timeline persistence mixed-case review flag initial status closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 timeline persistence initial review-state 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `_is_store_blocking_review_flag(...)`는 `review_flags.code`를 `strip()`만 한 채 `VALID_STORE_BLOCKING_REVIEW_FLAG_CODES`와 비교하고 있어, `" TTS_REPLACEMENT_REVIEW_REQUIRED "` 같은 mixed-case stale blocker code를 store-level blocker로 인식하지 못하고 있었다
- 그 결과 timeline 저장 시 initial review state가 `blocked`가 아니라 `draft`로 저장되는 실제 계약 누수가 있었다
- strict TDD로 `test_store_save_timeline_run_marks_mixed_case_review_flag_as_blocked_initial_status` exact regression을 먼저 추가했고, 실제로 `review_state["status"] == "draft"` RED를 확인했다
- 최소 수정으로 store helper에 `_canonical_review_flag_code(...)`를 추가하고 blocking review flag 판정이 lowercase code 기준을 쓰도록 맞춰, mixed-case stale review flag code도 canonical blocker로 인식하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 timeline persistence initial review-state 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - timeline persistence initial-status family exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - store-level review flag blocker 판정 helper 한 점 수정이라 exact + 인접 initial-status family evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. timeline persistence initial review state가 mixed-case stale `review_flags.code` blocker도 canonical lowercase code 기준으로 `blocked`로 저장한다
2. 저장 직후 review state truth가 output/preflight 쪽 mixed-case review flag canonicalization 흐름과 더 가까워졌다
3. stale non-list review flag 무시와 unknown pending recommendation 무시 계약은 그대로 유지된다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 103. 2026-07-04 review snapshot mixed-case review flag surface closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 맞닿은 review snapshot direct helper의 mixed-case review flag surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `build_review_snapshot(...)`는 mixed-case stale `review_flags.code`를 blocker로는 인식하게 됐지만, returned `review_flags` surface에는 `" TTS_REPLACEMENT_REVIEW_REQUIRED "` 같은 raw casing과 whitespace를 그대로 남기고 있었다
- 그 결과 direct helper를 바로 쓰는 read path나 테스트 면에서는 `review_status=blocked`와 `review_flags` surface truth가 서로 다른 canonicalization 기준을 갖는 작은 계약 틈이 남아 있었다
- strict TDD로 `test_review_snapshot_canonicalizes_mixed_case_review_flag_code` exact regression을 먼저 추가했고, 실제로 helper 반환 `review_flags`가 raw stale shape를 그대로 내보내는 RED를 확인했다
- 최소 수정으로 store helper에 review flag payload normalization을 추가하고 `build_review_snapshot(...)`가 canonical lowercase code, trimmed segment id, default message 기준의 normalized surface를 반환하도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review snapshot direct helper의 review flag surface 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review snapshot direct helper family exact
  - 결과: `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - helper returned review flag surface 한 점 수정이라 exact + 인접 helper family evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review snapshot direct helper가 mixed-case stale `timeline_review_flags.code` blocker도 canonical lowercase code 기준으로 surface한다
2. helper returned `review_flags`가 trimmed segment id와 default message를 함께 유지한다
3. `review_status=blocked` truth와 `review_flags` surface truth가 같은 review flag canonicalization 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 104. 2026-07-04 API review flag response mixed-case code closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 API review-flag response normalization helper 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `_normalize_review_flags_for_response(...)`는 `review_flags.code`를 `strip()`만 한 채 response surface로 내보내고 있어, `" TTS_REPLACEMENT_REVIEW_REQUIRED "` 같은 mixed-case stale code를 raw casing 그대로 노출하고 있었다
- strict TDD로 `test_review_flag_response_normalization_canonicalizes_mixed_case_code` exact regression을 먼저 추가했고, 실제로 helper 반환 `review_flags[0]["code"] == "TTS_REPLACEMENT_REVIEW_REQUIRED"` RED를 확인했다
- 최소 수정으로 response helper가 `code`를 `strip().lower()` 기준으로 canonicalize하도록 맞춰, timeline/review response 경로가 canonical lowercase review flag code를 일관되게 쓰도록 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 API review-flag response normalization helper 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - API response normalization helper 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - API helper의 lowercase canonicalization 한 줄 수정이라 exact + helper-adjacent focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. API review flag response helper가 mixed-case stale `review_flags.code`를 raw casing 그대로 노출하지 않는다
2. helper returned `review_flags`가 canonical lowercase code / trimmed segment id / default message surface를 함께 유지한다
3. recommendation response helper와 review flag response helper가 timeline/review API normalization에서 같은 canonical surface 규칙을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 105. 2026-07-04 preflight request trimmed segment id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `preflight contract`에 가장 가까운 targeted-segment request normalization 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `services/api/src/videobox_api/main.py`의 `_build_targeted_segments(...)`는 session 쪽 `segment_id`는 trim해서 lookup table을 만들지만, request `segment_ids`는 raw 문자열 그대로 조회하고 response `segment_id` surface에도 raw 값을 다시 쓰고 있었다
- 그 결과 `" seg_001 "` 같은 whitespace stale request segment id를 가진 preflight/partial-regeneration request는 기존 session segment를 놓치고 targeted segment preview를 비우거나 raw id를 그대로 surface할 수 있는 실제 계약 누수가 있었다
- strict TDD로 `test_build_targeted_segments_matches_trimmed_request_segment_ids` exact regression을 먼저 추가했고, 실제로 helper가 `[]`를 반환한 RED를 확인했다
- 첫 최소 수정 뒤 같은 exact test에서 returned `segment_id`가 raw `" seg_001 "`로 남는 두 번째 RED를 확인했고, helper가 request segment id도 `strip()` 기준으로 lookup하고 returned surface에도 canonical trimmed id를 쓰도록 맞춰 GREEN으로 닫았다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preflight targeted-segment helper 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 중간 RED 1회 추가 확인 후 `1 passed`
- focused verification
  - preflight targeted-segment helper 인접 exact
  - 결과: `5 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - request segment id trim과 returned surface canonicalization 두 줄 수정이라 exact + helper-adjacent focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preflight targeted-segment helper가 whitespace가 섞인 request `segment_ids`도 canonical trimmed id 기준으로 session segment와 매칭한다
2. helper returned `targeted_segments[].segment_id`가 raw request id가 아니라 canonical trimmed id를 유지한다
3. preflight scope request surface와 session segment lookup 기준이 같은 trimmed segment id 규칙을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 106. 2026-07-04 partial regeneration source segment lookup trimmed id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`과 `local_pipeline` partial regeneration runtime에 가장 가까운 source segment lookup 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_segments_for_timeline(...)`는 timeline clip 쪽 `segment_id`는 trim해서 읽지만, `store.list_segments(...)`로 받은 source segment row는 raw `segment_id`를 key로 보관하고 있어 `" seg_001 "` 같은 whitespace stale source row를 clip 쪽 canonical id와 매칭하지 못하고 있었다
- strict TDD로 `test_partial_regeneration_helper_matches_trimmed_source_segment_ids` exact regression을 먼저 추가했고, 실제로 helper가 `[]`를 반환하는 RED를 확인했다
- 최소 수정으로 source segment lookup key도 `strip()` 기준으로 canonicalize해, persisted source segment row의 padded id도 clip/timeline 쪽 trimmed id와 매칭되도록 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration runtime source segment lookup helper 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - partial regeneration runtime helper 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - source segment lookup key canonicalization 한 점 수정이라 exact + helper-adjacent focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration runtime helper가 whitespace가 섞인 persisted source segment row id도 canonical trimmed id 기준으로 clip/timeline과 매칭한다
2. source segment lookup이 raw row id 때문에 refresh 대상 segment를 놓치지 않는다
3. partial regeneration runtime의 source segment lookup 기준이 preflight/session 쪽 trimmed segment id 규칙과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 107. 2026-07-04 partial regeneration music refresh trimmed source segment id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`과 `local_pipeline` partial regeneration runtime에 가장 가까운 `music_refresh` source segment id 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_music_refresh_step(...)`는 source segment row가 `" seg_001 "`처럼 whitespace stale `segment_id`를 가지면 targeted `segment_ids=["seg_001"]`와 매칭하지 못해 refreshed music recommendation을 만들지 못하고 있었다
- strict TDD로 `test_editing_session_api_matches_trimmed_source_segment_id_for_music_refresh_partial_regeneration` exact regression을 먼저 추가했고, 실제로 partial regeneration result의 bgm clip이 `['seg_002']`만 남는 RED를 확인했다
- 첫 시도에서는 adjacent `broll_refresh` 줄에 trim이 잘못 들어가 exact가 그대로 RED였고, 실제 누수 지점을 다시 확인한 뒤 `music_refresh` 대상 segment 선택 줄을 `strip()` 기준으로 맞춰 같은 exact test를 GREEN으로 닫았다
- 같은 slice에서 `packages/core-engine/src/videobox_core_engine/timeline_builder.py`의 dict segment payload도 `segment_id`를 trim하도록 맞춰, refreshed recommendation은 canonical id인데 segment payload만 raw padded id를 유지해 timeline track 결합이 어긋나는 인접 누수도 함께 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration music refresh와 timeline build의 segment-id canonicalization 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - partial regeneration music 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - music refresh source segment match와 timeline builder segment payload canonicalization 두 점에 국한된 수정이라 exact + 인접 music family evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration `music_refresh`가 whitespace stale persisted source segment id도 canonical trimmed id 기준으로 다시 선택한다
2. refreshed music recommendation과 timeline builder segment payload가 같은 trimmed segment id 기준으로 결합된다
3. partial regeneration result가 raw padded source segment id 때문에 targeted bgm refresh를 놓치지 않는다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 108. 2026-07-04 partial regeneration overlay refresh trimmed existing segment id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `preflight contract`와 `local_pipeline` partial regeneration runtime에 가장 가까운 `overlay_refresh` existing overlay segment id 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_overlay_refresh_step(...)`는 existing overlay의 `segment_id`를 raw 문자열로 비교하고 있어 `" seg_001 "`처럼 whitespace stale `segment_id`를 가진 overlay가 targeted full overlay refresh에서도 제거되지 않고 그대로 남을 수 있었다
- strict TDD로 `test_editing_session_api_replaces_trimmed_segment_id_existing_overlay_when_running_full_overlay_refresh` exact regression을 먼저 추가했고, 실제로 stale `hook_title` overlay와 새 `image_card` overlay가 같이 남는 RED를 확인했다
- 최소 수정으로 existing overlay preserve path, same-segment preserve path, base overlay lookup path 모두 `strip()` 기준으로 맞춰 targeted full overlay refresh가 canonical segment id 기준으로 동작하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration overlay refresh의 segment-id canonicalization 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - partial regeneration overlay 인접 exact
  - 결과: `5 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - overlay refresh existing overlay segment-id canonicalization 세 점에 국한된 수정이라 exact + 인접 overlay family evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration `overlay_refresh`가 whitespace stale existing overlay segment id도 canonical trimmed id 기준으로 targeted full refresh에서 교체한다
2. same-segment preserve / base overlay lookup / target exclusion이 같은 trimmed segment id 기준을 사용한다
3. partial regeneration result가 raw padded existing overlay id 때문에 stale overlay를 남기지 않는다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 109. 2026-07-04 preview renderer trimmed narration clip segment id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 preview read path 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/preview_renderer.py`의 `_effective_narration_source_uri(...)`는 narration clip `segment_id`를 raw 문자열로 읽고 있어 `" seg_001 "`처럼 whitespace stale clip id를 가진 timeline에서 trimmed TTS recommendation target과 매칭하지 못했다
- strict TDD로 `test_preview_renderer_matches_trimmed_narration_clip_segment_id_for_narration_source` exact regression을 먼저 추가했고, 실제로 preview HTML이 approved TTS asset이 아니라 original narration source URI를 계속 노출하는 RED를 확인했다
- 최소 수정으로 preview renderer의 narration clip `segment_id`도 `strip()` 기준으로 맞춰, preview read path가 trimmed TTS recommendation target과 같은 기준으로 narration source를 고르게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preview renderer narration source selection 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - preview renderer TTS 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview narration source selection의 segment-id canonicalization 한 점 수정이라 exact + preview 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preview renderer가 whitespace stale narration clip segment id도 canonical trimmed id 기준으로 approved TTS recommendation과 매칭한다
2. preview HTML이 raw padded clip id 때문에 original narration source를 잘못 노출하지 않는다
3. preview read path의 narration source selection 기준이 timeline builder / export 쪽 trimmed segment id 규칙과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 110. 2026-07-04 capcut export trimmed narration clip segment id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 export read path 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`의 `_build_clip_track(...)`는 narration clip `segment_id`를 raw 문자열로 비교하고 있어 `" seg_001 "`처럼 whitespace stale clip id를 가진 timeline에서 trimmed TTS recommendation target과 매칭하지 못했다
- strict TDD로 `test_capcut_export_adapter_matches_trimmed_narration_clip_segment_id_for_segment_level_narration_sources` exact regression을 먼저 추가했고, 실제로 voiceover track 첫 segment가 approved TTS asset이 아니라 original narration source URI를 계속 사용하던 RED를 확인했다
- 최소 수정으로 CapCut export adapter의 clip `segment_id`도 `strip()` 기준으로 맞춰, export read path가 trimmed TTS recommendation target과 같은 기준으로 narration source를 고르게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 CapCut export voiceover source selection 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - CapCut export TTS 인접 exact
  - 결과: `5 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - export voiceover source selection의 segment-id canonicalization 한 점 수정이라 exact + export 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. CapCut export adapter가 whitespace stale narration clip segment id도 canonical trimmed id 기준으로 approved TTS recommendation과 매칭한다
2. export payload voiceover source가 raw padded clip id 때문에 original narration source로 잘못 남지 않는다
3. preview renderer와 CapCut export adapter가 approved narration source selection에서 같은 trimmed segment id 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 111. 2026-07-04 capcut export trimmed narration clip segment id surface closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 CapCut export payload surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`의 `_build_clip_track(...)`는 approved TTS voiceover source selection은 이미 trimmed clip id 기준으로 맞췄지만, returned segment payload의 `segment_id`는 raw 문자열 그대로 남겨 `" seg_001 "` 같은 whitespace stale shape를 export surface에 그대로 노출하고 있었다
- strict TDD로 `test_capcut_export_adapter_trims_narration_clip_segment_id_surface_for_segment_level_narration_sources` exact regression을 먼저 추가했고, 실제로 voiceover track segment id가 `[' seg_001 ']`로 남는 RED를 확인했다
- 최소 수정으로 CapCut export adapter의 voiceover segment payload도 `segment_id.strip()` 기준으로 맞춰, export read path가 canonical segment id를 유지하도록 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 CapCut export segment-id surface 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - CapCut export TTS 인접 exact
  - 결과: `6 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - export voiceover segment-id surface canonicalization 한 점 수정이라 exact + export 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. CapCut export adapter가 whitespace stale narration clip segment id를 source selection뿐 아니라 returned payload surface에서도 canonical trimmed id로 유지한다
2. export payload voiceover segment metadata가 raw padded clip id를 그대로 노출하지 않는다
3. preview renderer와 CapCut export adapter가 approved narration source와 segment id surface에서 같은 trimmed 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 112. 2026-07-04 capcut export trimmed broll segment grouping closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`과 export payload 일관성에 가장 가까운 broll sequential-fill grouping 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/capcut-export/src/videobox_capcut_export/adapter.py`의 `_build_broll_track(...)`는 broll clip을 `segment_id` raw 문자열 기준으로 묶고 있어 `" seg_001 "`와 `"seg_001"`처럼 whitespace stale/raw id가 섞인 같은 세그먼트를 서로 다른 window로 취급하고 있었다
- strict TDD로 `test_capcut_export_adapter_groups_trimmed_broll_segment_ids_into_one_window` exact regression을 먼저 추가했고, 실제로 첫 broll segment id가 `[' seg_001 ', 'seg_001']`로 surface되는 RED를 확인했다
- 최소 수정으로 `_build_broll_track(...)`의 grouping key를 `segment_id.strip()` 기준으로 맞춰, 같은 세그먼트의 broll clips가 하나의 sequential-fill window와 canonical segment id surface를 공유하게 했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 CapCut export broll grouping 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - CapCut export broll 인접 exact
  - 결과: `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - broll sequential-fill grouping key canonicalization 한 점 수정이라 exact + export broll 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. CapCut export adapter가 whitespace stale/raw broll segment id가 섞여 있어도 같은 세그먼트를 하나의 sequential-fill window로 묶는다
2. broll export payload의 segment surface가 canonical trimmed id 기준으로 정리된다
3. voiceover와 broll 모두 export payload에서 같은 segment-id canonicalization 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 113. 2026-07-04 preview renderer trimmed narration clip segment id surface closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`에 가장 가까운 preview HTML surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/preview_renderer.py`의 narration sources HTML surface는 approved narration source selection은 이미 trimmed 기준으로 맞춰져 있어도, 목록에 보이는 `segment_id`는 raw 문자열 그대로 노출해 `" seg_001 "` 같은 whitespace stale shape를 preview surface에 남기고 있었다
- strict TDD로 `test_preview_renderer_trims_narration_clip_segment_id_surface_for_narration_source` exact regression을 먼저 추가했고, 실제로 preview HTML이 `<li> seg_001 : ...</li>`를 노출하는 RED를 확인했다
- 최소 수정으로 narration sources HTML surface의 `segment_id`도 `strip()` 기준으로 맞춰, preview read path가 approved narration source와 segment id surface를 같은 canonical 기준으로 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preview renderer HTML surface 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - preview renderer TTS 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview HTML surface segment-id canonicalization 한 점 수정이라 exact + preview 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preview renderer가 whitespace stale narration clip segment id를 approved narration source selection뿐 아니라 HTML surface에서도 canonical trimmed id로 유지한다
2. preview HTML narration sources 목록이 raw padded clip id를 그대로 노출하지 않는다
3. preview renderer의 approved narration source와 visible segment surface가 같은 trimmed 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 114. 2026-07-04 partial regeneration segment refresh trimmed source segment id closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `preflight contract`와 바로 이어지는 partial regeneration `segment_refresh` runtime 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_segment_refresh_step(...)`는 source segment row의 `segment_id`를 raw 문자열로 비교하고 있어 `" seg_001 "`처럼 whitespace stale source row를 trimmed request/session segment id와 매칭하지 못하고 있었다
- strict TDD로 `test_editing_session_api_matches_trimmed_source_segment_ids_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 `result_payload["regenerated_segments"] == []` RED를 확인했다
- 최소 수정으로 `segment_refresh` step의 source segment id도 `strip()` 기준으로 맞추고, regenerated timeline segment surface에도 canonical trimmed id를 다시 써 주어 caption/cut-action rerun 결과가 같은 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration segment refresh의 source segment id canonicalization 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - partial regeneration segment-refresh 인접 exact
  - 결과: `3 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - segment_refresh source segment-id canonicalization 한 점 수정이라 exact + runtime 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration `segment_refresh`가 whitespace stale source segment id도 canonical trimmed id 기준으로 request/session target과 매칭한다
2. caption/cut-action rerun의 `regenerated_segments`와 downstream timeline segment surface가 raw padded source id 때문에 비어 있거나 어긋나지 않는다
3. partial regeneration runtime의 segment-refresh 기준이 source segment helper / session segment / downstream timeline 쪽 trimmed id 규칙과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 115. 2026-07-04 partial regeneration segment refresh stale source cut action closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `preflight contract`와 바로 이어지는 partial regeneration `segment_refresh` runtime의 stale source cut-action 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_execute_partial_regeneration_segment_refresh_step(...)`는 source segment row의 `cleanup_decision`을 raw 문자열로 그대로 읽고 있어, segment DB에 `stale_invalid_value` 같은 legacy 값이 남아 있으면 caption-only rerun에서도 `regenerated_segments[].cut_action`에 그대로 새고 있었다
- strict TDD로 `test_editing_session_api_normalizes_invalid_source_cut_action_when_running_partial_regeneration` exact regression을 먼저 추가했고, 실제로 rerun 결과 `cut_action == "stale_invalid_value"` RED를 확인했다
- 최소 수정으로 `segment_refresh` step의 source cut-action도 `_normalize_runtime_cut_action(...)` 기준으로 맞춰, source stale cut state가 caption-only rerun 결과와 downstream timeline에 그대로 남지 않게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 partial regeneration segment refresh의 source cut-action normalization 경계만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - partial regeneration segment-refresh 인접 exact
  - 결과: `5 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - source cut-action normalization 한 점 수정이라 exact + runtime 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration `segment_refresh`가 stale source `cleanup_decision`을 canonical runtime cut-action 값으로 정리한다
2. caption-only rerun의 `regenerated_segments`와 downstream timeline이 legacy invalid source cut state를 그대로 유지하지 않는다
3. session fallback, target override, source segment runtime이 cut-action 처리에서 더 같은 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 116. 2026-07-04 output gating mixed-case review approval status closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`에 가장 가까운 explicit approval read-path 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `_ensure_timeline_ready_for_output(...)`는 explicit approval 여부를 `store.get_review_state(...)[\"status\"] == \"approved\"`로 직접 비교하고 있는데, `packages/storage-abstractions/src/videobox_storage/local_project_store.py`의 `get_review_state(...)`는 DB의 `review_approvals.status`를 raw 문자열 그대로 반환하고 있었다
- 그래서 review DB에 legacy `" APPROVED "` 같은 mixed-case stale status가 남아 있으면 blocker가 없어도 preview output gating이 `Timeline requires explicit approval...`로 잘못 막히고 있었다
- strict TDD로 `test_preview_render_accepts_mixed_case_review_approval_state_without_blockers` exact regression을 먼저 추가했고, 실제로 preview render가 `400`을 반환하는 RED를 확인했다
- 최소 수정으로 `get_review_state(...)`의 returned `status`를 `strip().lower()` 기준으로 canonicalize해, output readiness read path가 stale approval casing 때문에 subtitle/preview/export를 다시 막지 않게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, TTS approval/output truth, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review approval read path 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - explicit approval / output gating 인접 exact
  - 결과: `4 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review approval status read-path canonicalization 한 점 수정이라 exact + output gating 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output gating이 legacy mixed-case `review_approvals.status`도 canonical lowercase 승인 상태로 해석한다
2. blocker가 없는 timeline은 stale approval casing 때문에 preview/subtitle/export를 다시 막지 않는다
3. explicit approval read truth가 runtime output gating과 더 같은 canonical status 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 117. 2026-07-04 preview renderer mixed-case review status surface closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 preview visible status surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/preview_renderer.py`는 preview HTML의 `Review status:` 문구에 `timeline["review_status"]`를 raw 문자열 그대로 넣고 있어, legacy `" APPROVED "` 같은 mixed-case stale shape가 visible output surface에 그대로 노출되고 있었다
- strict TDD로 `test_preview_renderer_canonicalizes_mixed_case_review_status_surface` exact regression을 먼저 추가했고, 실제로 preview HTML이 `Review status:  APPROVED `를 그대로 노출하는 RED를 확인했다
- 최소 수정으로 preview renderer에 review status canonical helper를 추가해 `strip().lower()` 기준으로 정리하고, preview HTML surface가 canonical lowercase status를 유지하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, TTS approval/output truth, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 preview visible status surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - preview renderer review/output 인접 exact
  - 결과: `7 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - preview review-status surface canonicalization 한 점 수정이라 exact + preview 인접 evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. preview renderer가 legacy mixed-case `review_status`도 canonical lowercase 상태로 surface한다
2. preview HTML의 visible status 문구가 raw stale review status 문자열을 그대로 노출하지 않는다
3. preview visible status surface가 output gating/readiness의 canonical status 기준과 더 가까워졌다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 131. 2026-07-04 review guidance mixed-case review flag code prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `review_flags.code` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `LocalFirstReviewGuidanceBuilder._build_prompt(...)`는 `review_flags`를 raw 리스트 그대로 prompt에 넣고 있어, legacy `" TTS_REPLACEMENT_REVIEW_REQUIRED "` 같은 mixed-case stale `code`가 operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_review_guidance_builder_canonicalizes_mixed_case_review_flag_code_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw mixed-case code를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 review guidance prompt 전용 `_prompt_review_flags(...)`와 `_canonical_review_flag_code(...)`를 추가해 `review_flags.code`를 `strip().lower()` 기준으로 canonicalize하고, prompt surface가 review/output gating 쪽 canonical review-flag truth와 같은 기준을 유지하게 맞췄다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 review-flag code surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance prompt 인접 exact
  - 결과: `5 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt review-flag code canonicalization 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 legacy mixed-case `review_flags.code`도 canonical lowercase code로 surface한다
2. operator guidance prompt가 raw stale review-flag code 문자열을 그대로 노출하지 않는다
3. review guidance prompt의 review-flag code surface가 review/output gating의 canonical blocker truth와 더 같은 기준을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 132. 2026-07-04 review guidance trimmed review flag segment id prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `review_flags.segment_id` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_prompt_review_flags(...)`는 직전 slice에서 `review_flags.code`는 canonicalize했지만 `segment_id`는 raw 문자열 그대로 두고 있어, whitespace stale `segment_id`가 operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_review_guidance_builder_trims_review_flag_segment_id_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'segment_id': ' seg_001 '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 `_prompt_review_flags(...)` 안에서 `segment_id`도 `str(...).strip()` 기준으로 trim하도록 맞춰, review guidance prompt의 review-flag segment surface가 review/output gating과 preflight/runtime 쪽 canonical segment id 기준과 같은 방향을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 review-flag segment-id surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance prompt 인접 exact
  - 결과: `6 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt review-flag segment-id trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 whitespace stale `review_flags.segment_id`도 canonical trimmed segment id로 surface한다
2. operator guidance prompt가 raw padded review-flag segment id 문자열을 그대로 노출하지 않는다
3. review guidance prompt의 review-flag segment-id surface가 review/output gating과 preflight/runtime 쪽 canonical segment id 기준과 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 133. 2026-07-04 review guidance trimmed review flag message prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `review_flags.message` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_prompt_review_flags(...)`는 `code`와 `segment_id`는 이미 canonicalize하고 있었지만 `message`는 raw 문자열 그대로 두고 있어, whitespace stale blocker message가 operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_review_guidance_builder_trims_review_flag_message_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'message': ' Operator review still required. '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 `_prompt_review_flags(...)` 안에서 `message`도 `str(...).strip()` 기준으로 trim하도록 맞춰, review guidance prompt의 review-flag message surface가 API response 쪽 canonical blocker message 기준과 같은 방향을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 review-flag message surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance prompt 인접 exact
  - 결과: `7 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt review-flag message trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 whitespace stale `review_flags.message`도 trimmed message로 surface한다
2. operator guidance prompt가 raw padded blocker message 문자열을 그대로 노출하지 않는다
3. review guidance prompt의 review-flag message surface가 API response 쪽 canonical blocker message 기준과 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 134. 2026-07-04 review guidance trimmed pending recommendation reason prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `pending_recommendations.reason` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_prompt_pending_recommendations(...)`는 `recommendation_type`과 `target_segment_id`는 이미 canonicalize하고 있었지만 `reason`은 raw 문자열 그대로 두고 있어, whitespace stale recommendation reason이 operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_review_guidance_builder_trims_pending_recommendation_reason_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'reason': ' Select narration asset '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 `_prompt_pending_recommendations(...)` 안에서 `reason`도 `str(...).strip()` 기준으로 trim하도록 맞춰, review guidance prompt의 recommendation reason surface가 API response 쪽 canonical recommendation reason 기준과 같은 방향을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 recommendation reason surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance prompt 인접 exact
  - 결과: `8 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt recommendation reason trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 whitespace stale `pending_recommendations.reason`도 trimmed reason으로 surface한다
2. operator guidance prompt가 raw padded recommendation reason 문자열을 그대로 노출하지 않는다
3. review guidance prompt의 recommendation reason surface가 API response 쪽 canonical recommendation reason 기준과 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 135. 2026-07-04 review guidance pending recommendation decision state prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `pending_recommendations.decision_state` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_prompt_pending_recommendations(...)`는 `recommendation_type`, `target_segment_id`, `reason`은 이미 canonicalize하고 있었지만 `decision_state`는 raw 문자열 그대로 두고 있어, legacy `" Approved "` 같은 mixed-case stale decision state가 operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_review_guidance_builder_canonicalizes_pending_recommendation_decision_state_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'decision_state': ' Approved '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 `_prompt_pending_recommendations(...)` 안에서 `decision_state`도 `str(...).strip().lower()` 기준으로 canonicalize하도록 맞춰, review guidance prompt의 decision-state surface가 API response 쪽 canonical decision-state 기준과 같은 방향을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 recommendation decision-state surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance prompt 인접 exact
  - 결과: `9 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt recommendation decision-state canonicalization 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 mixed-case 또는 whitespace stale `pending_recommendations.decision_state`도 canonical lowercase decision state로 surface한다
2. operator guidance prompt가 raw padded decision-state 문자열을 그대로 노출하지 않는다
3. review guidance prompt의 recommendation decision-state surface가 API response 쪽 canonical decision-state 기준과 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 136. 2026-07-04 review guidance pending selected asset id prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `pending_recommendations.selected_asset_id` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_prompt_pending_recommendations(...)`는 `recommendation_type`, `target_segment_id`, `reason`, `decision_state`는 이미 canonicalize하고 있었지만 `selected_asset_id`는 raw 문자열 그대로 두고 있어, whitespace stale asset id가 operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_review_guidance_builder_trims_pending_recommendation_selected_asset_id_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'selected_asset_id': ' asset_tts_001 '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 `_prompt_pending_recommendations(...)` 안에서 `selected_asset_id`도 `str(...).strip()` 기준으로 trim하도록 맞춰, review guidance prompt의 selected-asset-id surface가 API response 쪽 canonical selected asset id 기준과 같은 방향을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 selected-asset-id surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance prompt 인접 exact
  - 결과: `10 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt selected-asset-id trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 whitespace stale `pending_recommendations.selected_asset_id`도 trimmed asset id로 surface한다
2. operator guidance prompt가 raw padded selected asset id 문자열을 그대로 노출하지 않는다
3. review guidance prompt의 selected-asset-id surface가 API response 쪽 canonical selected asset id 기준과 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 137. 2026-07-04 review guidance pending recommendation id prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `pending_recommendations.recommendation_id` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_prompt_pending_recommendations(...)`는 `recommendation_type`, `target_segment_id`, `reason`, `decision_state`, `selected_asset_id`는 이미 canonicalize하고 있었지만 `recommendation_id`는 raw 문자열 그대로 두고 있어, whitespace stale recommendation id가 operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_review_guidance_builder_trims_pending_recommendation_id_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'recommendation_id': ' rec_001 '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 `_prompt_pending_recommendations(...)` 안에서 `recommendation_id`도 `str(...).strip()` 기준으로 trim하도록 맞춰, review guidance prompt의 recommendation-id surface가 approve/output 쪽 canonical recommendation identity 기준과 같은 방향을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 recommendation-id surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance prompt 인접 exact
  - 결과: `11 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt recommendation-id trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 whitespace stale `pending_recommendations.recommendation_id`도 trimmed recommendation id로 surface한다
2. operator guidance prompt가 raw padded recommendation id 문자열을 그대로 노출하지 않는다
3. review guidance prompt의 recommendation-id surface가 approve/output 쪽 canonical recommendation identity 기준과 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 138. 2026-07-04 review guidance pending created_at prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 review guidance prompt의 `pending_recommendations.created_at` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_prompt_pending_recommendations(...)`는 `recommendation_type`, `target_segment_id`, `reason`, `decision_state`, `selected_asset_id`, `recommendation_id`는 이미 canonicalize하고 있었지만 `created_at`는 raw 문자열 그대로 두고 있어, whitespace stale created_at 값이 operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_review_guidance_builder_trims_pending_recommendation_created_at_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'created_at': ' 2026-07-04T00:00:00+00:00 '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 `_prompt_pending_recommendations(...)` 안에서 `created_at`도 `str(...).strip()` 기준으로 trim하도록 맞춰, review guidance prompt의 created-at surface가 approve/output 쪽 recommendation metadata truth와 같은 방향을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 created-at surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance prompt 인접 exact
  - 결과: `12 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt created-at trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 whitespace stale `pending_recommendations.created_at`도 trimmed timestamp로 surface한다
2. operator guidance prompt가 raw padded created_at 문자열을 그대로 노출하지 않는다
3. review guidance prompt의 created-at surface가 approve/output 쪽 recommendation metadata 기준과 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 139. 2026-07-04 review guidance pending selected asset uri prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`과 바로 이어지는 review guidance prompt의 `pending_recommendations.payload.selected_asset_uri` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/review_guidance.py`의 `_prompt_pending_recommendations(...)`는 top-level `recommendation_type`, `target_segment_id`, `reason`, `decision_state`, `selected_asset_id`, `recommendation_id`, `created_at`는 이미 canonicalize하고 있었지만 nested `payload.selected_asset_uri`는 raw 문자열 그대로 두고 있어, whitespace stale asset uri가 operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_review_guidance_builder_trims_pending_recommendation_selected_asset_uri_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'selected_asset_uri': ' local://projects/project_001/assets/generated/asset_tts_001.wav '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 `_prompt_pending_recommendations(...)` 안에서 dict `payload.selected_asset_uri`도 `str(...).strip()` 기준으로 trim하도록 맞춰, review guidance prompt의 selected-asset-uri surface가 TTS approval/output 쪽 canonical selected asset uri 기준과 같은 방향을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 review guidance prompt의 nested selected-asset-uri surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - review guidance prompt 인접 exact
  - 결과: `13 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - review guidance prompt nested selected-asset-uri trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. review guidance prompt가 whitespace stale `pending_recommendations.payload.selected_asset_uri`도 trimmed asset uri로 surface한다
2. operator guidance prompt가 raw padded selected asset uri 문자열을 그대로 노출하지 않는다
3. review guidance prompt의 selected-asset-uri surface가 TTS approval/output 쪽 canonical asset uri 기준과 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 140. 2026-07-04 output operator copy pending recommendation type prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 output operator copy prompt의 `pending_recommendations.recommendation_type` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 `review_status`와 `track_type`는 이미 canonicalize하고 있었지만 `pending_recommendations`는 raw dict list를 그대로 프롬프트에 넣고 있어, legacy `" TTS_REPLACEMENT "` 같은 mixed-case stale recommendation type이 preview/export operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_output_operator_copy_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'recommendation_type': ' TTS_REPLACEMENT '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 `_build_prompt(...)` 안에서 prompt용 `pending_recommendations` summary를 따로 만들고 `recommendation_type`만 canonical lowercase로 정리하도록 맞춰, output operator copy prompt의 recommendation-type surface가 review guidance 및 output truth와 같은 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 recommendation-type surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt recommendation-type canonicalization 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 mixed-case stale `pending_recommendations.recommendation_type`도 canonical lowercase type으로 surface한다
2. preview/export guidance prompt가 raw padded recommendation type 문자열을 그대로 노출하지 않는다
3. output operator copy prompt의 recommendation-type surface가 review guidance 및 output truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 141. 2026-07-04 output operator copy pending target segment prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 output operator copy prompt의 `pending_recommendations.target_segment_id` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 직전 slice에서 `pending_recommendations.recommendation_type`은 canonicalize하게 됐지만 `target_segment_id`는 여전히 raw 문자열 그대로 넣고 있어, whitespace stale segment id가 preview/export operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_output_operator_copy_builder_trims_pending_recommendation_target_segment_id_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'target_segment_id': ' seg_001 '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 prompt용 `pending_recommendations` summary를 만들 때 `target_segment_id`도 `strip()` 기준으로 trim하도록 맞춰, output operator copy prompt의 segment-id surface가 review guidance 및 output truth와 같은 canonical segment id 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 target-segment-id surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt target-segment-id trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 whitespace stale `pending_recommendations.target_segment_id`도 trimmed segment id로 surface한다
2. preview/export guidance prompt가 raw padded target segment id 문자열을 그대로 노출하지 않는다
3. output operator copy prompt의 target-segment-id surface가 review guidance 및 output truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 142. 2026-07-04 output operator copy pending reason prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 output operator copy prompt의 `pending_recommendations.reason` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 직전 slice들로 `recommendation_type`과 `target_segment_id`는 정리됐지만 `reason`은 여전히 raw 문자열 그대로 넣고 있어, whitespace stale recommendation reason이 preview/export operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_output_operator_copy_builder_trims_pending_recommendation_reason_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'reason': ' Select narration asset '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 prompt용 `pending_recommendations` summary를 만들 때 `reason`도 `strip()` 기준으로 trim하도록 맞춰, output operator copy prompt의 recommendation-reason surface가 review guidance 및 output truth와 같은 canonical reason 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 reason surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt reason trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 whitespace stale `pending_recommendations.reason`도 trimmed reason으로 surface한다
2. preview/export guidance prompt가 raw padded recommendation reason 문자열을 그대로 노출하지 않는다
3. output operator copy prompt의 recommendation-reason surface가 review guidance 및 output truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 143. 2026-07-04 output operator copy pending selected asset prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`과 바로 이어지는 output operator copy prompt의 `pending_recommendations.selected_asset_id` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 직전 slice들로 `recommendation_type`, `target_segment_id`, `reason`은 정리됐지만 `selected_asset_id`는 여전히 raw 문자열 그대로 넣고 있어, whitespace stale asset id가 preview/export operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_output_operator_copy_builder_trims_pending_recommendation_selected_asset_id_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'selected_asset_id': ' asset_tts_001 '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 prompt용 `pending_recommendations` summary를 만들 때 `selected_asset_id`도 `strip()` 기준으로 trim하도록 맞춰, output operator copy prompt의 selected-asset-id surface가 review guidance 및 TTS/output truth와 같은 canonical asset id 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 selected-asset-id surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt selected-asset-id trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 whitespace stale `pending_recommendations.selected_asset_id`도 trimmed asset id로 surface한다
2. preview/export guidance prompt가 raw padded selected asset id 문자열을 그대로 노출하지 않는다
3. output operator copy prompt의 selected-asset-id surface가 review guidance 및 TTS/output truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 144. 2026-07-04 output operator copy pending recommendation id prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 output operator copy prompt의 `pending_recommendations.recommendation_id` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 직전 slice들로 `recommendation_type`, `target_segment_id`, `reason`, `selected_asset_id`는 정리됐지만 `recommendation_id`는 여전히 raw 문자열 그대로 넣고 있어, whitespace stale recommendation id가 preview/export operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_output_operator_copy_builder_trims_pending_recommendation_id_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'recommendation_id': ' rec_001 '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 prompt용 `pending_recommendations` summary를 만들 때 `recommendation_id`도 `strip()` 기준으로 trim하도록 맞춰, output operator copy prompt의 recommendation-id surface가 approve/output 쪽 canonical recommendation identity 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 recommendation-id surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt recommendation-id trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 whitespace stale `pending_recommendations.recommendation_id`도 trimmed recommendation id로 surface한다
2. preview/export guidance prompt가 raw padded recommendation id 문자열을 그대로 노출하지 않는다
3. output operator copy prompt의 recommendation-id surface가 approve/output truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 145. 2026-07-04 output operator copy pending created_at prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `review/output gating`과 바로 이어지는 output operator copy prompt의 `pending_recommendations.created_at` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 직전 slice들로 `recommendation_type`, `target_segment_id`, `reason`, `selected_asset_id`, `recommendation_id`는 정리됐지만 `created_at`는 여전히 raw 문자열 그대로 넣고 있어, whitespace stale created_at 값이 preview/export operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_output_operator_copy_builder_trims_pending_recommendation_created_at_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'created_at': ' 2026-07-04T00:00:00+00:00 '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 prompt용 `pending_recommendations` summary를 만들 때 `created_at`도 `strip()` 기준으로 trim하도록 맞춰, output operator copy prompt의 created-at surface가 approve/output 쪽 recommendation metadata truth와 같은 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 created-at surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt created-at trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 whitespace stale `pending_recommendations.created_at`도 trimmed timestamp로 surface한다
2. preview/export guidance prompt가 raw padded created_at 문자열을 그대로 노출하지 않는다
3. output operator copy prompt의 created-at surface가 approve/output metadata truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다

## 146. 2026-07-04 output operator copy pending selected asset uri prompt closeout

이번 후속 작업에서는 장기 우선순위 queue를 유지한 채, `TTS approval/output`과 바로 이어지는 output operator copy prompt의 `pending_recommendations.payload.selected_asset_uri` surface 경계 1개만 다시 닫았다.

이번에 새로 확인된 사실은 아래와 같다.

- `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`의 `_build_prompt(...)`는 직전 slice들로 top-level pending recommendation fields는 대부분 정리됐지만 nested `payload.selected_asset_uri`는 여전히 raw 문자열 그대로 넣고 있어, whitespace stale asset uri가 preview/export operator guidance prompt에 그대로 노출되고 있었다
- strict TDD로 `test_output_operator_copy_builder_trims_pending_recommendation_selected_asset_uri_in_prompt` exact regression을 먼저 추가했고, 실제로 prompt가 raw `'selected_asset_uri': ' local://projects/project_001/assets/generated/asset_tts_001.wav '`를 그대로 포함하는 RED를 확인했다
- 최소 수정으로 prompt용 `pending_recommendations` summary를 만들 때 dict `payload.selected_asset_uri`도 `strip()` 기준으로 trim하도록 맞춰, output operator copy prompt의 selected-asset-uri surface가 TTS approval/output 쪽 canonical selected asset uri 기준을 유지하게 정리했다
- 이번 수정은 editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 output operator copy prompt의 nested selected-asset-uri surface 한 점만 좁게 수정했다

이번 turn의 verification은 아래와 같다.

- exact regression
  - `1 failed` 확인 후 `1 passed`
- focused verification
  - backend output-gating `24 passed`
  - current-focused-parallel
    - backend output-gating `24 passed`
    - backend preflight `59 passed`
    - frontend preflight `25 passed`
- broader verification
  - 실행하지 않음
  - 판단:
    - output operator copy prompt nested selected-asset-uri trim 한 점 수정이라 exact + focused evidence가 가장 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. output operator copy prompt가 whitespace stale `pending_recommendations.payload.selected_asset_uri`도 trimmed asset uri로 surface한다
2. preview/export guidance prompt가 raw padded selected asset uri 문자열을 그대로 노출하지 않는다
3. output operator copy prompt의 selected-asset-uri surface가 TTS approval/output truth와 더 같은 방향을 사용한다

현재 이 단계에서 다음 핵심 남은 일은 다시 아래로 정리된다.

- 장기 우선순위 queue는 유지
- 다음 slice는 다시 `review/output gating`, `TTS approval/output`, `preflight contract` 중 가장 작은 남은 경계 1개만 고른다
- exact failing test 1개로만 다시 시작한다
