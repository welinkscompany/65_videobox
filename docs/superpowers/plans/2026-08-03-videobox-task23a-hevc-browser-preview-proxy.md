# Task 23A HEVC Browser Preview Proxy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 프로젝트의 HEVC 등 브라우저 비호환 영상을 원본 변경 없이 클릭 시점에만 H.264 MP4 프록시로 준비하여 편집기 `PreviewStage`에서 재생한다.

**Architecture:** API가 프로젝트 자산의 경량 ffprobe 결과와 원본 지문을 확인하고, 호환 자산은 원본 content URL을 즉시 반환한다. 비호환 자산은 `ASSET_PREVIEW_PROXY` durable job을 원본 지문 단위로 하나만 claim하여 프로젝트 내부 캐시에 원자적으로 게시한다. `EditorWorkbenchRoute`가 시작과 polling을 담당하고 `EditorWorkbench`가 요청 순서와 카드별 상태를 소유하며, 재생은 기존 단일 `PreviewStage`만 담당한다.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLite/PostgreSQL project store, ffprobe/ffmpeg subprocess, React 19, TypeScript, Vitest, Testing Library

---

## 고정 경계

- 사용자 원본 파일과 등록된 원본 자산을 수정하지 않는다.
- ingest 시점 변환, source copy, 외부 provider/API, Hermes, Mem0, 자동 apply를 추가하지 않는다.
- 오디오와 이미지는 현재 direct preview를 유지한다.
- 브라우저 호환 영상은 변환 job 없이 현재 asset content URL을 반환한다.
- API 응답에는 로컬 경로, ffmpeg 명령, raw stderr를 노출하지 않는다.
- local/test의 외부 네트워크 호출은 0건을 유지한다.

### Task 1: 경량 호환성 probe와 안전한 프록시 renderer

**Files:**
- Create: `packages/core-engine/src/videobox_core_engine/asset_browser_preview.py`
- Create: `tests/test_asset_browser_preview_core.py`

- [ ] `FFprobeBrowserPreviewProbe`가 한 번의 `ffprobe -show_streams -show_format -of json` 호출로 container, video codec, pixel format, audio codec, width, height를 반환하는 실패 테스트를 작성한다.
- [ ] MP4/MOV container + H.264 + yuv420p + AAC 또는 무음만 `browser_compatible=True`인 테스트를 작성한다. HEVC, VP9, 비-yuv420p, 비-AAC 오디오는 false여야 한다.
- [ ] `FFmpegBrowserPreviewRenderer`가 shell 없이 첫 video stream과 optional audio를 선택하고 H.264/yuv420p/AAC/faststart, 긴 변 1280 이하, 3600초 timeout으로 임시 MP4를 만드는 명령 계약 테스트를 작성한다.
- [ ] probe/renderer의 stderr와 로컬 경로를 예외 메시지로 그대로 내보내지 않고 bounded domain error code로 바꾸는 테스트를 작성한다.
- [ ] 실패 테스트를 실행한다.

Run: `.venv\Scripts\python.exe -m pytest tests/test_asset_browser_preview_core.py -q`

- [ ] 최소 구현으로 테스트를 통과시킨다. 생성자는 subprocess를 실행하지 않고 실제 preview 요청 때만 실행한다.
- [ ] renderer 출력은 최종 경로 옆 `*.tmp.mp4`에 쓰고, publish 책임은 service에 남긴다.
- [ ] 테스트를 다시 실행한다.

### Task 2: 지문·캐시·durable job 저장소 계약

**Files:**
- Modify: `packages/domain-models/src/videobox_domain_models/jobs.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/postgres_project_store.py` only if the shared SQL wrapper needs adaptation
- Create: `tests/test_asset_browser_preview_store.py`
- Create or Modify: the existing PostgreSQL project-store integration test file selected by `rg -n "PostgresProjectStore" tests`

- [ ] `JobType.ASSET_PREVIEW_PROXY` enum 테스트를 작성한다.
- [ ] `create_or_reuse_active_asset_preview_job(project_id, input_ref)`가 같은 지문의 pending/running job을 원자적으로 재사용하고 terminal job 뒤에는 새 시도를 만드는 SQLite 테스트를 작성한다.
- [ ] `get_latest_asset_preview_job`가 동일 input_ref의 최신 job을 반환하고, `recover_orphaned_asset_preview_jobs`가 pending/running만 bounded failure로 전환하는 테스트를 작성한다.
- [ ] PostgreSQL에서 동시 claim 결과가 한 개의 active job인 통합 테스트를 작성한다. 테스트 DB가 구성되지 않은 환경에서는 명시적 skip으로 남기고 통과로 과장하지 않는다.
- [ ] 실패 테스트를 실행한다.

Run: `.venv\Scripts\python.exe -m pytest tests/test_asset_browser_preview_store.py -q`

- [ ] 기존 `_create_or_reuse_active_output_job`의 SQLite `BEGIN IMMEDIATE`와 PostgreSQL table lock 방식을 재사용하도록 helper를 일반화한다.
- [ ] 일반 jobs table을 사용하고 별도 DB schema나 migration을 추가하지 않는다.
- [ ] 테스트를 다시 실행한다.

### Task 3: 프록시 서비스와 API

**Files:**
- Create: `services/api/src/videobox_api/asset_browser_preview_service.py`
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `services/api/src/videobox_api/routers/assets.py`
- Modify: `services/api/src/videobox_api/main.py`
- Create: `tests/test_asset_browser_preview_api.py`

- [ ] 허용 자산 유형이 `raw_video`, `broll_video`뿐이고 다른 유형은 bounded 409/422 오류가 되는 API 테스트를 작성한다.
- [ ] POST `/api/projects/{project_id}/assets/{asset_id}/browser-preview`가 호환 영상에는 `ready`와 원본 content URL을 200으로 반환하며 job/renderer를 호출하지 않는 테스트를 작성한다.
- [ ] 비호환 영상 첫 요청은 같은 지문 active job을 claim하고 `preparing`을 202로 반환하며, 동시 요청은 같은 job id를 받는 테스트를 작성한다.
- [ ] worker 성공 후 GET status가 `ready`, 새 `/content` URL, `source_sha256`, profile을 반환하고 content endpoint가 200/206/416 Range 계약을 지키는 테스트를 작성한다.
- [ ] 동일 stat/hash/profile은 cache hit, 원본 size/mtime 또는 publish 직전 hash가 달라지면 낡은 결과를 게시하지 않는 revision-fence 테스트를 작성한다.
- [ ] renderer 실패는 `failed`와 bounded `error_code`만 반환하고 raw stderr/경로를 숨기며, 명시적 POST retry는 terminal job 뒤 새 job을 만드는 테스트를 작성한다.
- [ ] 앱 시작 시 orphan pending/running preview job이 failed로 복구되며 subprocess나 외부 네트워크가 시작되지 않는 테스트를 작성한다.
- [ ] 실패 테스트를 실행한다.

Run: `.venv\Scripts\python.exe -m pytest tests/test_asset_browser_preview_api.py -q`

- [ ] `BrowserPreviewResponse(status, job_id, content_url, source_sha256, profile, error_code)` 모델을 추가한다.
- [ ] 원본 지문은 project id + asset id + asset created_at + size + mtime_ns + SHA-256 + profile로 구성하고 SHA 계산은 동일 path/size/mtime_ns 동안 process-local cache한다.
- [ ] 출력은 프로젝트 내부 `artifacts/browser-previews/<asset-id>/<fingerprint>.mp4`로 한정한다. renderer가 만든 임시 파일을 경량 probe로 재검사하고 원본 stat/hash를 다시 확인한 뒤 `os.replace`로 게시한다.
- [ ] `create_app`에 별도 injectable preview probe/renderer를 추가하고 기본 객체는 요청 전 subprocess를 실행하지 않는다.
- [ ] 새로 생성된 job만 daemon worker thread를 시작한다. route는 service의 bounded DTO만 반환한다.
- [ ] lifespan 첫 maintenance pass에서 orphan preview job을 복구한다.
- [ ] 테스트를 다시 실행한다.

### Task 4: Editor route/workbench/browser 연결

**Files:**
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/api.test.ts`
- Modify: `apps/web/src/features/editor/assets/editorAssetProjection.ts`
- Modify: `apps/web/src/features/editor/assets/EditorAssetBrowser.tsx`
- Modify: `apps/web/src/features/editor/assets/EditorAssetBrowser.test.tsx`
- Modify: `apps/web/src/features/editor/workbench/editorWorkbenchReadOnlyAdapters.tsx`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbench.tsx`
- Modify: `apps/web/src/features/editor/workbench/editor-workbench.test.tsx`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Modify: `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`
- Modify: `apps/web/src/features/jobs/JobRecovery.tsx`
- Modify: the existing JobRecovery test found with `rg -n "JobRecovery" apps/web/src`

- [ ] API client의 start/status/content URL과 AbortSignal 전달 테스트를 작성한다.
- [ ] project video card에만 `requiresBrowserPreviewPreparation=true`가 투영되고 project image/audio 및 library audio는 false인 테스트를 작성한다.
- [ ] 영상 카드 클릭 시 카드별 `preparing` 상태와 “원본 미리보기를 준비하고 있어요” 문구가 표시되고 중복 클릭이 비활성화되는 Workbench/Browser 테스트를 작성한다.
- [ ] 준비 성공 시 반환 URL만 기존 `AuditionRequest`로 전달되고 `PreviewStage`가 계속 유일한 video/audio element owner인 테스트를 작성한다.
- [ ] 같은 route의 더 늦은 요청이 이전 응답을 무시하고, route key 변경 뒤 이전 polling 응답이 새 프로젝트 상태를 바꾸지 못하는 테스트를 작성한다.
- [ ] 실패 시 “다시 준비”와 현재 exact-preview 갱신 fallback이 보이며 수동 적용 버튼은 계속 사용할 수 있는 테스트를 작성한다.
- [ ] audio/image/library 미리보기는 준비 API 없이 현재 URL로 즉시 재생되는 회귀 테스트를 작성한다.
- [ ] generic job type 표시가 `asset_preview_proxy -> 원본 미리보기 준비`이고 generic retry 정책은 넓히지 않는 테스트를 작성한다.
- [ ] 실패 테스트를 실행한다.

Run: `npm --prefix apps/web test -- --run src/api.test.ts src/features/editor/assets/editorAssetProjection.test.ts src/features/editor/assets/EditorAssetBrowser.test.tsx src/features/editor/workbench/editor-workbench.test.tsx src/features/editor/workbench/editor-workbench-route.test.tsx`

- [ ] route에 bounded polling helper(즉시 시작, 100/200/400/800ms backoff, 최대 60초, AbortSignal)를 구현한다.
- [ ] Workbench의 request sequence ref와 route-keyed state가 stale success/failure를 무시하도록 구현한다.
- [ ] Browser에는 상태 표시와 재시도만 추가하고 apply 동작은 변경하지 않는다.
- [ ] 테스트를 다시 실행한다.

### Task 5: 실제 HEVC smoke와 closeout

**Files:**
- Create: `scripts/verify-task23a-browser-preview.ps1`
- Create or Modify: `tests/test_task23a_browser_preview_verifier.py`
- Modify: `docs/development-status-2026-06-29.ko.md`
- Modify: `docs/implementation-plan.ko.md`
- Create: `docs/handoffs/2026-08-03-videobox-task23a-browser-preview-proxy-closeout.ko.md`

- [ ] verifier가 짧은 임시 HEVC fixture를 생성하거나 명시된 read-only 샘플을 등록하여 POST→poll→Range GET을 검사하고, 원본 size/mtime/hash 불변을 확인하는 실패 테스트를 작성한다.
- [ ] verifier는 임시 프로젝트 root만 쓰며 사용자 샘플 폴더와 보호된 untracked 폴더를 stage/remove/delete하지 않는다.
- [ ] verifier와 테스트를 통과시킨다. 로컬 ffmpeg에 HEVC encoder가 없으면 synthetic HEVC 생성만 명시적 skip하고, 실제 사용자 샘플 smoke를 별도 보고한다.
- [ ] 독립 관점의 spec review, code quality review, gap review, reverse runtime trace를 수행한다. Critical/Important finding은 고친 후 관련 테스트를 재실행한다.
- [ ] backend focused, frontend focused, full frontend, production build, Editor UI OSS provenance verifier를 실행한다.
- [ ] Task 23A 관련 전체 Python 회귀를 실행할 수 있으면 실행하되, 실행하지 않은 전체 Python 회귀를 통과했다고 주장하지 않는다.
- [ ] `git diff --check`와 보호된 untracked 상태를 확인한다.
- [ ] SSOT에 Task 23A 완료와 실제 검증 수치를 기록하고 Task 23 누적을 `1/4 (25.0%)`, 잔여 `75.0%`로 갱신한다.
- [ ] 논리적으로 닫힌 변경을 커밋하고 `origin/codex/videobox-container-compatibility`에 push한다.

## Reverse runtime trace

1. 사용자가 프로젝트 영상 카드의 `원본 미리보기`를 누른다.
2. `EditorWorkbench`가 카드별 request sequence를 올리고 `EditorWorkbenchRoute`의 prepare callback을 호출한다.
3. route가 POST를 보내며 호환 영상이면 즉시 원본 URL, 비호환 영상이면 durable job id를 받는다.
4. 비호환 job은 같은 원본 지문당 하나만 실행되어 임시 MP4를 만들고 결과 codec과 원본 revision을 다시 확인한 뒤 원자 게시한다.
5. route polling은 ready URL만 현재 route/request에 반환한다. route 변경 또는 더 늦은 클릭 뒤의 응답은 폐기한다.
6. Workbench는 ready URL로 하나의 `AuditionRequest`를 만들고 기존 `PreviewStage`만 재생한다.
7. 실패해도 원본과 timeline은 불변이며, 사용자는 다시 준비하거나 exact preview를 갱신하고 수동 편집·적용을 계속할 수 있다.

## Acceptance matrix

| 경로 | 기대 결과 | 자동 검증 |
|---|---|---|
| 호환 H.264 MP4 | job/변환 없이 원본 content URL | core/API tests |
| HEVC 또는 비호환 stream | H.264/yuv420p/AAC-or-none 프록시 | core/API/verifier |
| 같은 지문 동시 클릭 | active job 1개 | SQLite/PostgreSQL store tests |
| 서버 재시작 중 active job | bounded failed, 명시적 retry 가능 | lifespan/API tests |
| 원본 변경 중 render | 낡은 프록시 publish 거부 | service fence test |
| Range 요청 | 200/206/416 유지 | API test/verifier |
| route 변경/연속 클릭 | stale 응답 UI 반영 금지 | route/workbench tests |
| renderer 실패 | 경로/stderr 비노출, manual fallback 유지 | API/UI tests |
| audio/image/library | 기존 direct preview 유지 | projection/workbench tests |
| local/test 네트워크 | external provider call 0 | injected fake tests + verifier |

## Self-review result

- 설계의 lazy/no-copy/no-provider/no-auto-apply 경계를 각 구현 task와 acceptance test에 연결했다.
- cache hit, concurrent claim, restart recovery, source revision fence, Range 전달, route/request fence를 모두 실패 테스트로 먼저 고정했다.
- 기존 `PreviewStage` one-player ownership과 manual apply fallback을 보존했다.
- PostgreSQL 실증이 환경상 skip될 수 있는 점과 전체 Python 회귀 미실행 가능성을 완료 주장과 분리했다.
