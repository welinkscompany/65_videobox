# VideoBox 개발 상태 점검 2026-06-29

> 현재 authoritative 상태/next slice 판단은 `## 17. 2026-07-01 시스템 정비 기준 최신 상태`를 우선 적용한다. 그 외 날짜 기반 상태 섹션은 당시 시점 기록을 보존한 historical log다.
> 이 문서의 `## 1`부터 `## 16`까지는 당시 시점 판단과 검증 수치를 보존한 historical snapshot이다. 현재 truth, 현재 검증 수치, 현재 next slice는 `## 17`만 기준으로 본다.

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
- 이 체크포인트 직전 latest pushed closeout commit
  - `9df0363 Harden preflight pending recommendation prediction`

이 갱신으로 아래 판단은 더 이상 현재 truth가 아니다.

- `review action placeholder를 실제 persistence contract와 연결할지 여부 설계`
- `Approve recommendation`이 아직 첫 slice만 된 상태라는 판단

현재 기준 남은 핵심 범위는 다시 아래다.

- TTS replacement의 실제 narration/output propagation baseline과 approve 후 target clip 반영은 연결되어 있고, 남은 일은 approval/review contract의 추가 경계 보강이다
- review-required 상태의 subtitle/preview/export gating은 기본 경로와 reopen-after-approval 전이까지 고정돼 있고, 남은 일은 다른 승인 후 반영 규칙 세분화와 추가 경계 검증이다
- partial regeneration preflight의 비파괴 조회 경로는 baseline, duplicate-scope normalization, 일반 preflight blocked-warning combined reason surface까지 연결되어 있고, 남은 일은 backend read-only/prediction contract의 추가 경계와 frontend resume 경계 정리다
- TTS replacement approval/output contract의 아직 테스트로 고정되지 않은 추가 경계 보강
- `local_pipeline`의 다음 대형 분리 후보인 partial regeneration / output 경로 정리

아래 이어지는 `## 16` 이하의 낮은 번호 섹션들도 당시 시점 기록을 보존한 historical log다.
현재 truth나 현재 next slice 판단에는 위 `## 17. 2026-07-01 시스템 정비 기준 최신 상태`를 우선 적용한다.

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
