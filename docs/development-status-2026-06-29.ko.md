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
- 최소 수정으로 runtime이 valid source blocker review flag를 `code + segment_id` 기준으로 dedupe해 candidate timeline payload에 복원하고, legacy shape도 API contract를 깨지 않도록 default message를 채우게 맞췄다
- 이번 수정은 review/output rules, TTS approval/output truth, Gemini fallback, provider trace audit, persistence 규칙을 건드리지 않고 runtime source review flag carry-forward 경계만 좁게 수정했다
- exact regression `1 passed`
- focused adjacency slice `4 passed`
- broader verification은 이번 turn에서는 다시 돌리지 않았다
  - 판단:
    - runtime source review flag carry-forward 한 점에 국한된 수정이라 focused evidence가 더 직접적이다
    - latest broader baseline은 직전 closeout 기준 `full backend regression 346 passed`, `frontend build 성공`을 유지한다

이 갱신으로 아래 범위는 현재 기준 안정화됐다.

1. partial regeneration preflight가 valid source review flag blocker를 `blocked` prediction으로 유지함
2. partial regeneration runtime도 같은 source review flag blocker를 candidate result에 복원함
3. candidate result의 `review_status`가 `blocked`로 유지됨
4. preserved source review flag가 legacy message 부재 때문에 API response validation error를 내지 않음

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
