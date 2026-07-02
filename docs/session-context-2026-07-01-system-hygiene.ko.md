# VideoBox 세션 컨텍스트

작성일:

- 2026-07-01

주제:

- 현재 프로젝트 기준 전체 시스템 정비
- 문서 SSOT와 실제 코드/검증 결과의 불일치 정리
- review-action family 완료 상태와 남은 리스크 재정렬

## 1. 이번 세션에서 실제로 확인한 것

- 현재 worktree 기준 backend full regression은 `312 passed`다
- frontend build는 성공한다
- frontend `src/app.test.tsx` 전체는 `66 passed`다
- helper `frontend-focused` gate는 `2 passed`다
- current-priority helper `scripts/dev-fast-path.ps1`를 추가해 `output gating / preflight backend / preflight frontend / broader` 검증 레일을 분리했다
- review-action backend focused slice는 `6 passed`다
- backend full regression은 현재 direct 실행 기준으로 `312 passed`까지 다시 확인됐다
- 세션 후반 재검증에서도 review-action backend focused `6 passed`, helper `frontend-focused` gate `2 passed`, frontend `src/app.test.tsx` 전체 `66 passed`, frontend build 성공을 다시 확인했다
- 이후 fresh `pytest -q` 전체 회귀를 다시 캡처해 `312 passed in 817.19s`를 확인했고, 최신 full-backend baseline을 그 수치로 갱신했다
- 세부 focused gate도 이후 다시 확인했다
  - output gating 묶음 `2 passed`
  - reopen-after-approval gating `1 passed`
  - preflight focused regression `11 passed`
  - frontend blocked-warning + resumed multi-segment cleanup 묶음 `3 passed`
- current-priority helper `./scripts/dev-fast-path.ps1 -Mode current-focused`도 바로 검증했다
  - backend output-gating slice `16 passed`
  - backend preflight slice `55 passed`
  - frontend preflight slice `25 passed`
- helper 추가 후 broader verification도 다시 확인했다
  - frontend build 성공
  - full backend regression `312 passed in 817.19s`
- `approved` review_state가 남아 있더라도 timeline에 residual blocker가 있으면 output은 blocker detail로 다시 막혀야 한다는 backend regression `1 passed`도 추가로 확인했다
- `reopen review` 후 residual blocker가 남아 있는 경우 review 상태가 `draft`가 아니라 `blocked`로 돌아가고 output도 blocker detail로 다시 막히는 backend regression `1 passed`도 추가로 확인했다
- `approved + review_flag only` 조합에서도 output이 blocker detail로 계속 막히는 backend regression `1 passed`를 추가로 확인해 output gating 매트릭스를 더 촘촘히 고정했다
- `approved + pending_recommendation only` 조합에서도 output이 blocker detail로 계속 막히는 backend regression `1 passed`를 추가로 확인해 output gating의 단일 blocker 매트릭스를 더 닫았다
- approved timeline이라도 snapshot `review_flags/pending_recommendations`가 비어 있는 상태에서 segment-level `review_required=true`가 남아 있으면 output이 계속 blocker detail로 막히는 backend regression `1 passed`를 추가로 확인했다
- last pending recommendation approve 이후에도 남아 있는 segment-level `review_required=true`는 synthetic `segment_review_required` flag가 API timeline/read snapshot 경로에 반영돼 output gating과 read path가 어긋나지 않도록 하는 backend regression `1 passed`를 추가로 확인했다
- malformed duplicated segment entry가 같은 `segment_id`로 반복돼도 synthetic `segment_review_required` blocker detail이 중복으로 불어나지 않는 backend regression `1 passed`를 추가로 확인했다
- synthetic blocker 때문에 effective review status가 `approved -> blocked`로 바뀌는 경우 persisted approved `operator_guidance`를 재사용하지 않고 blocked snapshot 기준 guidance를 다시 계산하는 backend regression `1 passed`를 추가로 확인했다
- approved timeline을 `reopen review`할 때 stale truthy blocker shape가 residual blocker로 오판되지 않고 `draft`로 돌아간 뒤 explicit approval gating만 다시 요구하는 backend regression `1 passed`를 추가로 확인했다
- approved timeline을 `reopen review`한 뒤 stale truthy `review_flags` / `pending_recommendations` shape가 timeline/review snapshot read path를 깨뜨리지 않고 빈 blocker 컬렉션으로 정규화돼 직렬화되도록 하는 backend regression `1 passed`를 추가로 확인했다
- last pending recommendation approve 경로에서 stale non-dict `review_flags` entry가 섞여 있어도 review action이 500으로 깨지지 않고 blocker 정리 후 `draft`로 돌아간 뒤 explicit approval gating만 다시 요구하는 backend regression `1 passed`를 추가로 확인했다
- partial regeneration preflight는 source timeline의 valid `review_flags.code`라도 nested stale `segment_id` shape면 blocker로 오판하지 않고 clean scope `draft` prediction을 유지하는 backend regression `1 passed`를 추가로 확인했다
- partial regeneration preflight는 source timeline의 valid `pending_recommendations.target_segment_id`라도 nested stale shape면 blocker로 오판하지 않고 clean scope `draft` prediction을 유지하는 backend regression `1 passed`를 추가로 확인했다
- ignored generated artifact 정리 후보 중 repo 내부 build/cache 산출물은 안전 범위에서 실제로 정리했다
  - `.pytest_cache`
  - `apps/web/dist`
  - repo 내부 각 패키지/서비스/테스트 경로의 `__pycache__`
- partial regeneration preflight의 TTS affected-output label은 operator-facing `narration track` 기준으로 다시 고정됐다
- partial regeneration preflight의 `prediction_reasons`는 `source only / target only / both` 조합 기준으로 테스트가 분리됐다
- partial regeneration preflight의 repeated `segment_ids`는 first-seen order를 유지한 채 dedupe되어 read-only scope와 targeted segment preview에 중복이 남지 않도록 고정됐다
- partial regeneration preflight는 whitespace가 섞인 legacy session `segment_id`도 trimmed request scope와 같은 세그먼트로 맞춰 targeted segment preview를 비우지 않도록 고정됐다
- partial regeneration preflight의 repeated `fields`도 first-seen order를 유지한 채 dedupe되어 read-only scope와 downstream step preview에 중복이 남지 않도록 고정됐다
- partial regeneration preflight의 stale `visual_overlays: null`도 targeted segment preview에서는 빈 리스트로 정규화되도록 고정됐다
- partial regeneration preflight의 stale non-dict `visual_overlays` entry도 targeted segment preview에서는 제거되고 valid overlay만 유지되도록 고정됐다
- partial regeneration preflight의 empty `visual_overlays` dict entry도 targeted segment preview에서는 제거되고 valid overlay만 유지되도록 고정됐다
- partial regeneration preflight의 stale minimal-dict `visual_overlays` entry도 targeted segment preview에서는 제거되고 valid overlay만 유지되도록 고정됐다
- partial regeneration preflight의 `overlay_type`만 있는 stale `visual_overlays` entry도 targeted segment preview에서는 제거되고 valid overlay만 유지되도록 고정됐다
- partial regeneration preflight의 unknown `overlay_type` stale `visual_overlays` entry도 targeted segment preview에서는 제거되고 canonical overlay만 유지되도록 고정됐다
- partial regeneration preflight의 legacy `hook_title` overlay는 targeted segment preview에서 runtime과 어긋나게 사라지지 않고 기존 shape를 유지하도록 고정됐다
- partial regeneration preflight의 stringified falsey `review_required`도 targeted segment preview와 prediction에서는 실제 `False`로 정규화되도록 고정됐다
- partial regeneration preflight의 stale non-dict `broll_override`도 targeted segment preview에서는 `None`으로 정규화되도록 고정됐다
- partial regeneration preflight의 empty `broll_override` dict도 targeted segment preview에서는 `None`으로 정규화되도록 고정됐다
- partial regeneration preflight의 stale non-dict `music_override`도 targeted segment preview에서는 `None`으로 정규화되도록 고정됐다
- partial regeneration preflight의 empty `music_override` dict도 targeted segment preview에서는 `None`으로 정규화되도록 고정됐다
- partial regeneration preflight의 stale non-dict `tts_replacement`도 targeted segment preview에서는 `None`으로 정규화되도록 고정됐다
- partial regeneration preflight의 empty `tts_replacement` dict도 targeted segment preview에서는 `None`으로 정규화되도록 고정됐다
- partial regeneration preflight의 stale non-list source `review_flags`는 read-only prediction에서 blocker list로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정됐다
- partial regeneration preflight의 stale non-dict-only source `review_flags` list는 read-only prediction에서 blocker list로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정됐다
- partial regeneration preflight의 stale minimal-dict source `review_flags` entry는 read-only prediction에서 blocker flag로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정됐다
- partial regeneration preflight의 `code`만 있는 source `review_flags` stale dict는 read-only prediction에서 blocker flag로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정됐다
- partial regeneration preflight의 unknown `review_flags.code` source stale dict는 read-only prediction에서 blocker flag로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정됐다
- partial regeneration preflight의 valid `review_flags.code/segment_id` source legacy dict는 `message`가 비어 있어도 runtime blocker 의미를 보존해 `blocked` prediction으로 유지하도록 고정됐다
- partial regeneration preflight의 stale non-dict-only source `pending_recommendations` list는 read-only prediction에서 blocker list로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정됐다
- partial regeneration preflight의 stale minimal-dict source `pending_recommendations` entry는 read-only prediction에서 blocker recommendation으로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정됐다
- partial regeneration preflight의 `recommendation_id`만 있는 source `pending_recommendations` stale dict는 read-only prediction에서 blocker recommendation으로 취급하지 않고 clean scope면 `draft` prediction을 유지하도록 고정됐다
- partial regeneration preflight의 unknown `recommendation_type` source `pending_recommendations` stale dict는 read-only prediction과 runtime carry-forward 모두에서 blocker recommendation으로 취급하지 않고 clean scope면 `draft` prediction/result를 유지하도록 고정됐다
- partial regeneration runtime도 stale minimal-dict source `pending_recommendations` entry를 그대로 blocker로 들고 가지 않고 clean scope rerun result의 `review_status/pending_recommendations/review_flags`를 `draft/[]/[]`로 유지하도록 고정됐다
- partial regeneration runtime fallback은 source timeline 세그먼트가 비어 있을 때 editing-session의 stringified falsey `review_required`를 실제 `False`로 정규화해 clean scope rerun result의 `review_flags/review_status`를 `[]/draft`로 유지하도록 고정됐다
- partial regeneration runtime fallback은 source timeline 세그먼트가 비어 있을 때 editing-session의 stale invalid `cut_action`을 실제 `keep`으로 정규화해 clean scope rerun result의 regenerated segment `cut_action`을 canonical 값으로 유지하도록 고정됐다
- partial regeneration runtime은 `cut_action` field rerun 시에도 target session segment의 stale invalid `cut_action`을 실제 `keep`으로 정규화해 regenerated segment `cut_action`을 canonical 값으로 유지하도록 고정됐다
- partial regeneration runtime은 preflight와 마찬가지로 whitespace가 섞인 legacy session `segment_id`도 trimmed request scope와 같은 세그먼트로 맞춰 actual rerun target lookup과 regenerated segment 반영이 비지 않도록 고정됐다
- partial regeneration runtime은 actual overlay refresh에서도 unknown `overlay_type` session overlay를 persisted timeline `export_overlays`에 싣지 않고 canonical overlay만 반영하도록 고정됐다
- partial regeneration runtime은 targeted overlay rerun에서 target segment의 stale unknown existing overlay도 preserve path로 되살리지 않고 canonical overlay만 남기도록 고정됐다
- approved timeline의 stale truthy `review_flags` / `pending_recommendations` shape는 output gating에서 실제 blocker로 오판하지 않고 유효 blocker만 기준으로 막도록 고정됐다
- 일반 preflight UI에서도 blocked prediction reason의 combined 문구 두 개가 모두 surface되는지 frontend focused test로 고정했다
- refresh-resume 시 restored preflight 응답의 scope가 resumed candidate와 다르면 그 interpretation을 재사용하지 않고 degraded warning으로 내리는 frontend focused test를 고정했다
- refresh-resume 시 restored preflight 응답의 `session_id`가 resumed candidate와 다르면 scope가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내리는 frontend focused test를 고정했다
- refresh-resume 시 restored preflight 응답의 `fields`에 duplicate가 섞여 있으면 scope member가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내리는 frontend focused test를 고정했다
- refresh-resume 시 restored preflight 응답의 `targeted_segments`가 resumed candidate scope와 어긋나면 `segment_ids/fields/session_id`가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내리는 frontend focused test를 고정했다
- refresh-resume 시 restored preflight 응답의 `targeted_segments.review_required`가 현재 editing session과 다르면 `segment_ids/fields/session_id`와 target segment id가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내리는 frontend focused test를 고정했다
- refresh-resume 시 restored preflight 응답의 `targeted_segments.tts_replacement`가 현재 editing session과 다르면 `segment_ids/fields/session_id`와 target segment id가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내리는 frontend focused test를 고정했다
- refresh-resume 시 restored preflight 응답의 `targeted_segments.visual_overlays`가 현재 editing session과 다르면 `segment_ids/fields/session_id`와 target segment id가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내리는 frontend focused test를 고정했다
- refresh-resume 시 restored preflight 응답의 `targeted_segments.broll_override`가 현재 editing session과 다르면 `segment_ids/fields/session_id`와 target segment id가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내리는 frontend focused test를 고정했다
- refresh-resume 시 restored preflight 응답의 `targeted_segments.music_override`가 현재 editing session과 다르면 `segment_ids/fields/session_id`와 target segment id가 같아도 그 interpretation을 재사용하지 않고 degraded warning으로 내리는 frontend focused test를 고정했다
- frontend preflight helper가 blocked-warning만이 아니라 resumed preflight degraded warning, mismatch non-reuse, resumed warning cleanup, resumed multi-segment scope cleanup까지 실제로 포함하도록 정렬했다
- frontend preflight field inference는 backend canonical `image_card` overlay를 `image_overlay` rerun field로 올바르게 매핑해 saved overlay가 `caption` fallback으로 잘못 좁혀지지 않도록 고정했다
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
- current-focused helper 재검증 기준으로 backend preflight slice는 현재 `55 passed`다
- current-focused helper 재검증 기준으로 frontend preflight slice는 현재 `25 passed`다
- current-focused helper 재검증 기준으로 backend output-gating slice는 현재 `16 passed`다
- resumed multi-segment candidate의 stale scope card가 target 변경 시 내려가는지 frontend focused test로 고정했다
- resumed multi-segment candidate의 stale scope card가 field 변경 시에도 내려가는지 frontend focused test로 고정했다
- pending `tts_replacement` approve 시 target narration track clip `asset_uri`가 승인된 `selected_asset_uri`로 즉시 동기화되는지 backend focused test로 고정했다
- pending `tts_replacement` blocker가 남아 있을 때 subtitle-render도 preview/export와 같은 blocker detail과 failed job/no-artifact 상태를 surface하는지 focused test로 고정했다
- blocker가 없는 clean timeline이라도 explicit approval이 없으면 subtitle-render도 preview/export와 같은 failed job/no-artifact 상태를 surface하는지 focused test로 고정했다
- approved timeline을 `reopen review`한 뒤 subtitle/preview/export가 다시 explicit approval을 요구하며 막히는지 focused test로 고정했다
- unsupported partial-regeneration field scope는 preflight prediction으로 흘리지 않고 `400`과 no-job 상태로 즉시 거부되는지 focused test로 고정했다
- 현재 브랜치의 review-action family는 실제로 닫혀 있다
  - approve persistence
  - reject persistence
  - mark-for-manual-edit routing
  - rollback hardening
  - timeline-local truth 보존

## 2. 이번 세션에서 찾은 불일치

- `docs/development-status-2026-06-29.ko.md` 일부 최신 상태가 뒤처져 있었다
  - review action이 아직 placeholder/설계 단계처럼 읽히는 구간 존재
  - 현재 test/build 수치가 낮은 예전 값으로 남아 있었다
- `docs/implementation-plan.ko.md`의 `다음 실제 작업`이 이미 끝난 editing-session 기초 단계에 머물러 있었다

## 3. 이번 세션에서 실제로 수정한 것

- `docs/development-status-2026-06-29.ko.md`
  - 2026-07-01 기준 최신 상태 섹션 추가
  - `## 1`부터 `## 16`까지는 historical snapshot이고 `## 17`만 current truth라는 점을 더 명시
- `docs/implementation-plan.ko.md`
  - 현재 구현 체크포인트와 다음 실제 작업 재정렬
  - `## 12`와 `## 13`이 current implementation checkpoint/next slice 기준이라는 점을 상단에 명시
- `docs/development-context.ko.md`
  - 현재 브랜치의 next-priority 순서와 검증 베이스라인 수치 정렬
  - branch context 보조 문서이며 authoritative 상태/next slice는 최신 SSOT와 함께 읽어야 한다는 점을 상단에 명시
- `docs/initial-architecture-and-folder-plan.ko.md`
  - 초기 폴더 계획 기록이며 현재 `apps/web` 역할 판단은 최신 아키텍처/컨텍스트 문서를 우선 적용하도록 historical plan note 추가
- `docs/initial-architecture-and-folder-plan.md`
  - 영문 초기 폴더 계획 문서에도 같은 historical plan note 추가
- `docs/saas-expansion-design-notes.ko.md`
  - 초기 `기본 review UI` 표현을 현재 operator dashboard / lightweight editing UI 용어로 정렬
- `docs/saas-expansion-design-notes.md`
  - 영문 문서에도 같은 용어 정렬 반영
- `docs/brollbox-reuse-audit.ko.md`
  - 현재 UI 방향을 `operator dashboard / lightweight editing UI` 기준으로 표현 정렬
- `docs/videobox-mcp-scope.ko.md`
  - MCP와 UI 역할 분리 문구를 현재 operator dashboard / lightweight editing UI 용어로 정렬
- `docs/development-fast-path.ko.md`
  - current-priority helper와 review-action maintenance helper의 역할 분리
  - helper 적용 범위와 historical prompt 참조 범위 축소
  - preflight backend helper가 targeted-segment normalization 경계도 포함하도록 정렬
- `scripts/dev-fast-path.ps1`
  - 현재 next-priority slice용 focused verification helper 추가
  - `output-gating`, `preflight-backend`, `preflight-frontend`, `current-focused`, `broader` 모드 제공
- `docs/provider-trace-audit-filter-closeout.ko.md`
  - closeout 기록이 current truth처럼 읽히지 않도록 historical closeout note 추가
- `docs/phase-6-preview-export-closeout.ko.md`
  - phase closeout 기록이 current truth처럼 읽히지 않도록 historical closeout note 추가
- `docs/superpowers/goals/review-action-next-slice-subagent-prompt.ko.md`
  - current goal 기본값이 아니라 historical prompt임을 명시
- `docs/superpowers/plans/2026-06-30-review-action-family-acceleration.md`
  - current next-priority plan이 아니라 닫힌 review-action rollout evidence임을 명시
- `services/api/src/videobox_api/main.py`
  - partial regeneration preflight의 TTS affected-output label을 `narration track` 기준으로 정렬
  - partial regeneration preflight targeted segment preview에서 stale `visual_overlays: null`을 빈 리스트로 정규화
  - partial regeneration preflight targeted segment preview에서 stringified falsey `review_required`를 `False`로 정규화
  - partial regeneration preflight targeted segment preview에서 stale non-dict `broll_override`를 `None`으로 정규화
  - partial regeneration preflight targeted segment preview에서 stale non-dict `music_override`를 `None`으로 정규화
  - partial regeneration preflight targeted segment preview에서 stale non-dict `tts_replacement`를 `None`으로 정규화
- `apps/web/src/app.test.tsx`
  - resumed candidate restore warning cleanup과 blocked preflight fixture/prediction reason 정렬
  - 일반 preflight blocked-warning 경로에서도 combined prediction reason 두 개를 모두 확인하도록 assertion 보강
  - resumed multi-segment scope card cleanup 경계 추가
  - resumed multi-segment scope card field-change cleanup 경계 추가
- `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`
  - approved `tts_replacement`의 target narration clip patch helper 추가
- `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
  - approve persistence 경로에서 위 helper를 호출하도록 연결
- `tests/test_api.py`
  - approve 후 target narration clip 반영 + non-target blocker 보존 focused regression 추가
  - pending TTS blocker 시 subtitle-render blocker detail + failed job/no-artifact regression 추가
  - explicit approval 부재 시 subtitle-render failed job/no-artifact regression 추가
  - reopen-after-approval 시 subtitle/preview/export reblock regression 추가
  - preflight duplicate segment scope dedupe regression 추가
  - unsupported partial-regeneration field scope rejection + no-job regression 추가
- `scripts/review-action-fast-path.ps1`
  - backend focused 기본 패턴에 위 TTS approve propagation 회귀를 포함
- ignored generated artifacts
  - repo 내부 build/cache 산출물만 정리하고, `.venv`와 `apps/web/node_modules`는 환경 경계로 남겨 두었다

## 4. 이번 세션에서 의도적으로 안 건드린 것

- 과거 session-context 문서 자체의 역사 기록
- review/output 계약
- editing-session SSOT
- Gemini fallback
- provider trace audit

과거 문서는 당시 시점 기록으로 남겨 두고, 최신 truth는 최신 상태 섹션과 이 문서로 덮는 방식이 더 안전하다고 판단했다.

## 5. 현재 기준 남은 핵심 리스크

- TTS replacement의 baseline narration/output propagation과 approve 후 target clip 반영은 연결되어 있고, 남은 일은 approval/review contract의 추가 경계 보강이다
- review-required 상태의 subtitle/preview/export gating은 기본 경로와 reopen-after-approval 전이까지 고정돼 있고, 남은 일은 다른 승인 후 반영 규칙 세분화와 추가 경계 검증이다
- partial regeneration preflight의 비파괴 조회 경로는 API와 UI에 이미 노출되어 있고, duplicate-scope normalization과 일반 preflight blocked-warning combined reason surface까지 고정됐다. 남은 일은 backend read-only/prediction contract의 추가 경계와 frontend resume 경계 세분화다
- `local_pipeline`은 review-action 쪽은 줄었지만 partial regeneration / output 경로가 여전히 크다

## 6. 다음 세션 첫 시작점

1. review-required 상태에서 subtitle/preview/export gating의 추가 경계를 명시적 테스트로 더 고정
2. partial regeneration preflight의 backend read-only/prediction contract와 frontend resume 경계를 현재 증거 기준으로 더 좁게 고정
3. frontend preflight/resume 경계 중 아직 helper 기본 레일에 없는 가장 작은 field-inference 또는 restore-warning 케이스를 failing test 1개로 선별
4. TTS replacement approval/output contract에서 아직 테스트로 고정되지 않은 추가 경계를 선별 보강
5. 그 다음 `local_pipeline`의 partial regeneration / output 경로 분리 가능 범위를 최소 단위로 자르기
