# VideoBox OSS Dashboard and Editor Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILLS: use `subagent-driven-development`, `test-driven-development`, `requesting-code-review`, and `verification-before-completion`. Execute one Task at a time. Every production Task starts with an observed RED, closes with GREEN verification, an independent review, SSOT progress update, one logical commit, and push.

**Goal:** shadcn 기반 앱 셸과 OpenCut/Opencast에서 검증 가능한 편집 UX를 선별 이식해, 대본 입력·유진 인터뷰부터 실제 자산이 배치된 초안, 정확한 합성 미리보기, 타임라인, 자산 추천, 자막, 출력까지 한 작업판에서 사용할 수 있게 한다.

**Architecture:** shadcn/ui source와 shadcn-admin shell composition을 frontend foundation으로 사용한다. OpenCut classic/Opencast의 view와 interaction은 `EditorViewModel`/typed command adapter 뒤로만 들어온다. FastAPI editing-session revision, source provenance, FFmpeg, PyCapCut은 계속 authoritative하다. 브라우저의 선택 클립 재생은 audition일 뿐이며, 현재 revision의 정확한 편집본 미리보기는 FFmpeg proxy artifact가 담당한다.

**Tech Stack:** React 19.1, TypeScript 5.8, Vite 5.4, Tailwind 4.2 without global preflight, shadcn/ui CLI/source 4.13 Radix base, TanStack Router code-based routes, Vitest/Testing Library, Playwright, Python 3.12, FastAPI/Pydantic, SQLite, FFmpeg.

**Design:** `docs/superpowers/specs/2026-07-17-videobox-oss-dashboard-editor-adoption-design.md`
**Research:** `docs/research/2026-07-17-videobox-oss-dashboard-editor-adoption.ko.md`

---

## 0. 고정 결정

- shadcn-admin whole repository를 clone/template/dependency로 사용하지 않는다.
- shadcn/ui component는 live registry 결과를 신뢰하지 않고 pinned registry source와 file SHA를 기록한 source-owned code로 저장한다.
- current OpenCut rewrite는 editor implementation source로 사용하지 않는다.
- OpenCut classic의 EditorCore, IndexedDB/OPFS, renderer/export, WASM, browser STT는 반입하지 않는다.
- Opencast의 Redux, MUI/Emotion, full snapshot API, player fork, browser waveform decode는 반입하지 않는다.
- Opencast 동작은 true clean-room이라고 부르지 않는다. Apache-2.0 source-derived behavioral adaptation으로 기록하고 LICENSE/NOTICE/변경 고지를 남긴다.
- Supabase Studio는 reference-only다. source copy를 하지 않는다.
- React 19.2, Vite 8, TypeScript 6 업그레이드는 이 계획에 섞지 않는다.
- routing은 `@tanstack/react-router@1.168.22`의 code-based route tree만 사용한다. router plugin이나 생성 route tree는 넣지 않는다.
- URL의 `projectId`가 선택 프로젝트의 canonical truth다. ProjectWorkspaceProvider는 route param에서 파생하고 switch는 navigate만 한다.
- local/test profile에서 외부 font/CDN/analytics/provider HTTP(S) 요청은 0이어야 한다. 미래 managed SaaS profile의 정책까지 전역 금지하지 않는다.
- `DeploymentCapabilities`는 UI 표시 제어일 뿐 authorization이 아니다.
- 유진 conversation/composer는 우측에 유지하고 추천은 대화 안의 inline card 또는 옆 context pane으로 보여준다. 추천과 대화를 상호 배타적 탭으로 만들지 않는다. 사용자 노출/접근성 이름은 `유진`(첫 소개는 `유진 영상 도우미`)으로 통일하며 `director` API·route·state·test ID 및 Hermes/provider profile ID는 유지한다.
- 사용자가 `초안 만들기`를 한 번 승인하기 전 editing mutation은 0이다. 승인 뒤 session 생성과 ranked placement bundle apply는 atomic/idempotent하다.
- caption timing은 이번 계획에서 narration segment bounds에 종속한다. 독립 cue start/end API가 생기기 전 caption-only drag/resize UI를 제공하지 않는다.
- 선택 자산/클립 audition과 정확한 편집본 preview를 명확히 구분한다. exact preview는 current revision을 FFmpeg로 합성한 freshness-bound artifact다.
- implementation 중 source를 복사·변형하면 upstream commit/path/license/header, source map, notice, 검증 test를 같은 commit에 추가한다.

## 1. 조사 시점 현재 갭

- `App.tsx` 4,190줄, `styles.css` 962줄, `app.test.tsx` 5,787줄로 shell, data orchestration, page view가 결합돼 있다.
- router, Tailwind, 공통 UI primitive가 없다. 실제 TypeScript 설정은 `apps/web/tsconfig.json`이며 `@/*` alias도 없다.
- 타임라인은 track/clip 카드 목록이고 실제 ruler, playhead, zoom, drag, trim, waveform이 없다.
- current `PreviewRenderer`는 timing/caption placeholder HTML이며 B-roll/BGM/SFX/overlay를 합성한 편집본이 아니다.
- asset content endpoint는 있으나 editor audition에 필요한 Range/MIME/project isolation contract가 없다.
- current editing-session API는 split/merge/bounds/reorder/caption text/style/B-roll/BGM/SFX/overlay/undo/redo를 이미 제공한다.
- caption은 narration segment metadata다. 독립 cue timing model/API는 없다.
- `ManualMediaLibrary`와 `AssetPreviewPlayer`가 각각 media state를 소유해 동시에 재생될 수 있다.
- current dirty worktree에는 Lumi copy implementation과 production build blocker가 남아 있다. 새 shell 작업 전에 해당 범위를 closeout해야 한다.

## 2. 모든 Task 공통 closeout 계약

Task별 `Files`에는 기능 파일만 쓴다. 다음 closeout 파일은 모든 Task에 암묵적으로 포함한다.

- `docs/superpowers/plans/2026-07-17-videobox-oss-dashboard-editor-adoption.md`
- `docs/implementation-plan.ko.md`
- `docs/development-status-2026-06-29.ko.md`
- 해당 Task handoff 또는 slice closeout 문서

각 Task의 마지막 step은 반드시 다음을 수행한다.

1. focused RED 명령과 예상 failure를 작업 로그에 남긴다.
2. 동일 focused 명령의 GREEN, 영향받은 full suite, production build를 실행한다.
3. source-derived 작업이면 provenance verifier와 UI-system verifier를 실행한다.
4. 독립 코드리뷰, 계획 gap, source→runtime 역방향 검증을 수행하고 P0/P1을 닫는다.
5. `git diff --check`, scoped diff, `git status --short`를 확인한다.
6. Task-level checkbox와 누적 `완료/22`, 백분율을 observed commit 기준으로 갱신한다.
7. Task 하나만 논리적 commit으로 만들고 upstream branch에 push한다. push 실패는 숨기지 않고 보고한다.

Prototype/문서 Task는 production TDD 예외지만 artifact verifier, 사용자 승인 기록, diff/status 검사는 동일하게 적용한다.

### 2.1 Focused RED/GREEN command matrix

아래 명령은 repo root에서 RED와 GREEN에 동일하게 실행한다. RED는 표의 named contract assertion이 최소 1개 실패해야 한다. 단순 module-not-found, snapshot 생성, test syntax error만으로는 의미 있는 RED가 아니다. 각 Task 착수 시 agent는 이 matrix를 실제 파일/함수명까지 확장한 한 페이지 executable task sub-plan을 먼저 작성하고 독립 리뷰를 받아야 하며, command/scope를 바꾸면 본 계획과 함께 갱신한다.

| Task | exact focused command | required RED assertion |
|---:|---|---|
| 1 | `npm --prefix apps/web test -- src/legacy-baseline.test.tsx src/user-copy-policy.test.ts src/features/director/DirectorContextBar.test.tsx src/features/director/director-history-controls.test.tsx` + `npm --prefix apps/web run build` | 현재 5개 TypeScript blocker 또는 legacy baseline 미보존 |
| 2 | `.venv\Scripts\python.exe -m pytest -q tests/test_ui_prototype_artifacts.py` + `npm --prefix apps/web test -- src/app.test.tsx src/user-copy-policy.test.ts src/legacy-baseline.test.tsx src/features/director/DirectorWorkspacePanel.test.tsx src/features/director/director-workspace.test.tsx src/features/director/responsive-director.test.tsx src/features/director/asset-preview-player.test.tsx src/features/director/media-reference-badge.test.tsx src/features/director/proposal-comparison-tray.test.tsx src/features/director/ProposalCandidateCard.test.tsx src/features/media/manual-media-library.test.tsx` + `npm --prefix apps/web run build` | viewport/artifact SHA/approval record 누락 또는 dashboard user-copy contract 위반 |
| 3 | `.venv\Scripts\python.exe -m pytest -q tests/test_editor_ui_source_provenance.py` + `./scripts/verify-editor-ui-source-provenance.ps1` | pin/path/hash/license/dependency lock 누락 |
| 4 | `npm --prefix apps/web test -- src/ui-system.test.tsx src/external-runtime-assets.test.ts src/test/network-guard.test.ts` | primitive/alias/preflight/network boundary 누락 |
| 5 | `npm --prefix apps/web test -- src/app/app-router.test.tsx src/app/project-workspace-provider.test.tsx src/legacy-baseline.test.tsx` | URL truth/redirect/dedupe/parity 위반 |
| 6 | `npm --prefix apps/web test -- src/components/layout/app-shell.test.tsx src/features/settings/settings-layout.test.tsx src/app/deployment-capabilities.test.ts` + `npm --prefix apps/web run test:e2e -- e2e/app-shell.spec.ts` | shell/focus/capability/viewport/network 위반 |
| 7 | `.venv\Scripts\python.exe -m pytest -q tests/test_creation_brief.py tests/test_api_creation_brief.py` + `npm --prefix apps/web test -- src/features/create/lumi-interview.test.tsx` | persisted adaptive interview/idempotency/delete 위반 |
| 8 | `.venv\Scripts\python.exe -m pytest -q tests/test_draft_readiness.py tests/test_api_draft_readiness.py` + `npm --prefix apps/web test -- src/features/create/draft-readiness.test.tsx` | narration/asset/gap recovery 또는 no-mutation 위반 |
| 9 | `.venv\Scripts\python.exe -m pytest -q tests/test_atomic_draft_bundle.py tests/test_api_atomic_draft_bundle.py` + `npm --prefix apps/web run test:e2e -- e2e/script-first-vertical.spec.ts` | atomicity/source recheck/real placement/composited playback 위반 |
| 10 | `.venv\Scripts\python.exe -m pytest -q tests/test_editor_playback.py tests/test_api_editor_playback.py` + `npm --prefix apps/web test -- src/features/editor/adapter/video-box-editor-adapter.test.ts` | manifest/frame/role-action/source delivery 위반 |
| 11 | `npm --prefix apps/web test -- src/features/editor/workbench/editor-workbench.test.tsx` + `npm --prefix apps/web run test:e2e -- e2e/editor-workbench-layout.spec.ts` | dock/preview density/유진 persistence/a11y 위반 |
| 12 | `.venv\Scripts\python.exe -m pytest -q tests/test_exact_preview_artifact.py tests/test_api_exact_preview.py` | FFmpeg parity/freshness/range/full-session/fencing 위반 |
| 13 | `npm --prefix apps/web test -- src/features/editor/preview/preview-stage.test.tsx src/features/editor/preview/preview-coordinator.test.tsx src/features/editor/preview/preview-coordinates.test.ts` | exact-vs-audition/one-player/time-origin/caption 위반 |
| 14 | `npm --prefix apps/web test -- src/features/editor/timeline/time-scale.test.ts src/features/editor/timeline/timeline-geometry.test.ts src/features/editor/timeline/snapping.test.ts src/features/editor/timeline/hit-testing.test.ts` | rational frame/geometry deterministic property 위반 |
| 15 | `npm --prefix apps/web test -- src/features/editor/timeline/timeline-navigation.test.tsx src/features/editor/editor-performance.test.tsx` | read-only seek/render structural budget 위반 |
| 16 | `npm --prefix apps/web test -- src/features/editor/timeline/timeline-mutations.test.tsx` + `.venv\Scripts\python.exe -m pytest -q tests/test_editor_timeline_mutations.py` | typed command/one-commit/revision recovery 위반 |
| 17 | `.venv\Scripts\python.exe -m pytest -q tests/test_waveform_artifact.py tests/test_api_waveform.py` + `npm --prefix apps/web test -- src/features/editor/timeline/waveform-lane.test.tsx` | deterministic cache/restart/visible buckets 위반 |
| 18 | `npm --prefix apps/web test -- src/features/editor/transcript/transcript-panel.test.tsx src/features/editor/transcript/caption-lane.test.tsx` + `.venv\Scripts\python.exe -m pytest -q tests/test_api_caption_text.py` | linked caption sync/text/style/performance 위반 |
| 19 | `npm --prefix apps/web test -- src/features/editor/assets/editor-asset-browser.test.tsx` + `.venv\Scripts\python.exe -m pytest -q tests/test_api_media_library.py` | preview/apply/provenance/session invariance 위반 |
| 20 | `npm --prefix apps/web test -- src/features/editor/inspector/inspector-panel.test.tsx src/features/editor/workbench/right-dock.test.tsx` + `npm --prefix apps/web run test:e2e -- e2e/lumi-recommendations.spec.ts` | persistent conversation/inline candidate/typed Inspector 위반 |
| 21 | `npm --prefix apps/web run test:e2e -- e2e/app-shell.spec.ts e2e/editor-workbench.spec.ts e2e/script-first.spec.ts` + `npm --prefix apps/web test -- src/features/editor/editor-accessibility.test.tsx src/features/editor/editor-performance.test.tsx` | responsive/a11y/visual/perf/network 회귀 |
| 22 | `./scripts/dev-fast-path.ps1 -Mode current-focused` + `npm --prefix apps/web test` + `npm --prefix apps/web run build` + `npm --prefix apps/web run test:e2e` + `.venv\Scripts\python.exe -m pytest -q` | legacy parity 또는 release gate 실패 |

---

## Slice 0 — Baseline, visual direction, and provenance

### Task 1: Close the current Lumi copy work and freeze the legacy baseline

- [x] **Task 1 완료**

**Files:** already-dirty Lumi copy files only; `apps/web/src/user-copy-policy.test.ts`; `apps/web/src/features/director/DirectorContextBar.test.tsx`; create `apps/web/src/legacy-baseline.test.tsx`.

- [x] **RED:** planning-time five TypeScript failures were already resolved in the merged upstream Lumi copy. A missing legacy selection-state contract was observed instead: the new project-selection assertion failed because `aria-pressed` was absent.
- [x] **GREEN:** add selected-state semantics for project/section buttons and lock project select, section select, Director manual fallback, preview/export, and settings behavior without weakening the copy policy.
- [x] **Verify:** focused Task 1 suite 21 passed, full frontend suite 200 passed, and production build passed; independent spec/quality reviews and source-to-runtime reverse checks found no open P0/P1.

Commit: `feat: finish Lumi dashboard copy`

### Task 2: Approve three source-grounded visual prototypes before production UI code

- [x] **Task 2 완료**

**Files:** create `docs/prototypes/2026-07-17-creator-workspace/README.ko.md`; create committed 1920/1440/1280/768/390 artifacts and `manifest.json`; create `docs/decisions/creator-workspace-visual-approval.ko.md`; create artifact-link/hash verifier test.

**허용된 pre-approval production copy 범위:** 현재 렌더되는 default dashboard 전체의 사용자 노출 문자열·접근성 이름·placeholder·status/error copy와 그 테스트만 바꾼다. 여기에는 `App.tsx`의 sidebar/tab/project/output/onboarding/error copy, Director/추천, 직접 미디어 선택 surface가 포함된다. layout, API, state, provider 호출, dependency는 바꾸지 않는다. 별도 관리/diagnostic 설정은 default dashboard가 아니면 이 Task에서 삭제·rename하지 않되 dashboard로 새로 노출하지 않는다. 이 예외는 `유진` 표시명과 아래 creator-language policy를 정합시키기 위한 것으로, Task 3 이후의 production shell 구현을 앞당기지 않는다.

- [x] Build realistic Korean prototypes for zero-project Home, script/유진 interview, and asset-populated editor. 모든 prototype의 사용자 노출/접근성 assistant name은 `유진`이며, 기존 runtime identifier는 바꾸지 않는다.
- [x] Use a warm-white `#FAFAF9` canvas, white panels, soft warm-gray `#E7E5E4` borders, charcoal `#292524` primary text, `#57534E` secondary text, and one muted indigo `#4F46E5` action accent; retain only the video preview stage as dark `#18181B`. Use the local Noto Sans KR Variable font for approval artifacts; no CDN/font request. Body text contrast targets 4.5:1 or better, non-text focus/border contrast 3:1 or better, and state is never color-only.
- [x] In Home/Interview/Editor, retain simple action-copy: `새 영상 만들기`; `유진의 질문` with `모르겠어요`/`추천해줘`/`건너뛰기`; and `추천 적용` with `적용 전에는 편집본이 바뀌지 않습니다`. Narrow drawers visibly expose assets/script/captions/Inspector actions.
- [x] Default dashboard 전체와 유진/추천 surface의 copy는 사용자가 만드는 결과와 행동만 말한다: `영상`, `프로젝트`, `대본`, `장면`, `미디어`, `음악`, `자막`, `미리보기`, `추천`, `고르기`, `적용`, `내보내기`. visible text와 accessible name에 `provider`, `runtime`, `fallback`, `loopback`, `API key`, `model`, `context`, `revision`, `pipeline`, `job` 및 `시스템`, `개발`, `런타임`, `공급자`, `제공자`, `모델`, `API 키`, `루프백`, `폴백`, `컨텍스트`, `리비전`, `파이프라인`, `job`을 쓰지 않는다. `App.tsx`의 `로컬 검수`, `job 현황`, `파이프라인`, `로컬 AI 기능`, `LM Studio`, `자동 런타임`, `loopback`, `fallback`, `API 키` 같은 기본 dashboard copy도 사용자 결과/행동 언어로 교체하거나 default dashboard에서 제거한다. 실패/차단 안내는 `추천을 준비하지 못했어요. 직접 미디어를 고르거나 다시 시도해 주세요.`처럼 다음 행동을 말한다.
- [x] Provider/모델 설정은 default dashboard에 노출하지 않는다. 별도 관리 설정의 기술적 label/API contract는 이 Task에서 삭제·rename하지 않으며, dashboard로 새로 노출하지 않는다.
- [x] Annotate which structure comes from shadcn-admin, OpenCut classic, Opencast, or Supabase reference; do not place those annotations in production UI.
- [x] Prove editor density rules: collapsed sidebar; one dock open by default at 1280–1599; preview at least 50% of content or 640px; 1920px populated-editor shows both docks while preview remains at least 720px; drawers below 1280.
- [x] Record explicit user approval before Task 4. A rejection keeps this Task unchecked and blocks production shell styling.
- [x] Verify artifact dimensions, SHA manifest, links, diff/status; commit and push.

Commit: `docs: approve VideoBox creator workspace direction`

### Task 3: Add deterministic OSS source, license, and generated-file provenance gates

- [ ] **Task 3 완료**

**Files:** create `docs/oss/editor-ui-source-map.json`; `docs/oss/shadcn-registry-lock.json`; `THIRD_PARTY_NOTICES.md`; `tests/test_editor_ui_source_provenance.py`; `scripts/verify-editor-ui-source-provenance.ps1`; modify `docs/oss-adoption-map.ko.md`.

- [ ] **RED:** fail on missing 40-char commit/upstream path/local path/license/test/file SHA; reference-only local copy; missing notice; rejected runtime import; generated-file hash drift.
- [ ] Pin shadcn-admin `e16c87f213a5ba5e45964e9b67c792105ec74d26`, shadcn/ui `4396d5b2a5ee4e2ad5705e9b2522f92112f811a0`, OpenCut current `bab8af831b354a0b5a98a4a6e818ab7d633b94df` reject, classic `cf5e79e919144200294fb9fed22a222592a0aeea`, Opencast `1208afb64d9de0ab50b321f84f9dd2695780db87`, Supabase `1c827c5cbb29cacc6e9052adff2e1659e3cb05fb` reference-only.
- [ ] Pin Pretendard release `v1.3.9`, commit `5c41199ea0024a9e0b2cb31735265056e5472d76`, path `packages/pretendard/dist/web/variable/woff2/PretendardVariable.woff2`, SHA256 `9599f12fd42fc0bce1cd50b47a0c022e108d7aa64dd0d1bb0ed44f3282d900b4`, and OFL text before copying the binary.
- [ ] Lock every approved shadcn registry item to the pinned GitHub source path and SHA256. Record each generated item’s runtime dependency name, exact resolved version, license, and package-lock entry; verifier fails source-lock/dependency-lock drift. Do not accept live `npx shadcn add` output without normalized diff/hash verification.
- [ ] Include direct LICENSE/NOTICE links and Apache-2.0 modified-source attribution.
- [ ] **GREEN:** `.venv\Scripts\python.exe -m pytest -q tests/test_editor_ui_source_provenance.py`; `./scripts/verify-editor-ui-source-provenance.ps1`; common closeout.

Commit: `docs: govern editor OSS source adoption`

---

## Slice 1 — UI foundation, routing, and product shell

### Task 4: Introduce locked shadcn/ui source, tokens, local font, and deterministic network guards

- [ ] **Task 4 완료**

**Files:** modify `apps/web/package.json`, lockfile, `vite.config.ts`, real `tsconfig.json`, `vitest.setup.ts`; create `components.json`, `src/lib/utils.ts`, `src/styles/{index,theme,legacy}.css`, local font files, approved `src/components/ui/*`, `src/test/networkGuard.ts`, UI/network tests, `scripts/verify-editor-ui-system.ps1`; update source map/notices.

- [ ] **RED:** component semantics, `@/*` alias build, legacy computed-style fixtures, external fetch/XHR/WebSocket/EventSource deny, remote URL scan, and migrated-surface native-control/custom-class allowlist must fail first.
- [ ] Install Tailwind 4.2.2 and `@tailwindcss/vite` without React/Vite/TS upgrades. Add `baseUrl/paths` and Vite resolve alias.
- [ ] Omit Tailwind global preflight during migration; import theme/utilities explicitly and keep legacy reset isolated. A wrapper class alone is not accepted as isolation.
- [ ] Materialize shadcn Button/Card/Input/Textarea/Dialog/Sheet/Dropdown/Sidebar/Empty/Badge/Tooltip/Skeleton/Tabs/Select/ScrollArea/Separator/Sonner/Resizable only from the locked sources and record normalized hashes.
- [ ] Bundle pinned Pretendard locally; runtime CDN/font/provider calls remain 0.
- [ ] **GREEN:** focused UI/network tests; full frontend; build; provenance/UI-system verifiers; common closeout.

Commit: `feat: establish the VideoBox UI foundation`

### Task 5: Extract URL-owned workspace state and add code-based typed routing

- [ ] **Task 5 완료**

**Files:** create `src/app/{AppRoot,AppRouter,routeManifest,ProjectWorkspaceProvider,LegacyWorkspacePage}.tsx` and tests; modify `main.tsx`, `App.tsx`, package/lockfile.

- [ ] **RED:** direct URL, refresh restoration, zero/unknown project, redirects, project switch, active route, and request dedupe.
- [ ] Install only `@tanstack/react-router@1.168.22`; do not add router plugin, Query, Redux, or Zustand.
- [ ] Canonical redirects: `/` → last valid project home or `/projects`; `/projects` with zero projects → onboarding empty state; project create success → `/projects/$projectId/create`; invalid project → recovery page.
- [ ] Provider derives project from route param. Project switch only navigates; it does not hold a second selected-project truth.
- [ ] **GREEN:** router/provider/legacy baseline tests; full frontend; build; network guard; common closeout.

Commit: `refactor: route the VideoBox workspace`

### Task 6: Port the app shell and ship useful Home/settings/empty-state routes

- [ ] **Task 6 완료**

**Files:** create layout components/tests, Home/Projects pages, `deploymentCapabilities.ts`, minimal functional Settings layout/pages, initial `playwright.config.ts`, loopback-only fake API/provider webServer harness, and shell E2E; update package scripts, route manifest, source map, notices.

- [ ] **RED:** sidebar header/content/footer/rail, ProjectSwitcher with fake API, active route, collapse/mobile Sheet/focus return, job center, one-action empty states, local/SaaS capability visibility, and no admin-demo/auth labels.
- [ ] Port shadcn-admin layout composition only. Use `홈 / 새 영상 만들기 / 편집 / 자산 / 출력 / 설정`.
- [ ] Install exact `@playwright/test@1.61.1`, record its lockfile/browser revision, add `test:e2e`, and create the loopback-only webServer/fake API/provider harness before the first shell E2E. Task 21 extends this harness rather than introducing it late.
- [ ] Home shows only: 새 영상 만들기, 작업 중인 초안 계속하기, 최근 완성본, 자산 준비가 필요한 프로젝트. Raw job/provider metrics stay out of default Home.
- [ ] `DeploymentCapabilities` adds `aiExecution: "disabled" | "local" | "managed"`; local implementation exposes local/disabled only. Account/team/billing remain hidden until real backend authorization exists.
- [ ] Settings initially expose only working 일반/화면/AI·개인정보/저장공간/출력 controls; no fake SaaS screens.
- [ ] Commit 1920/1440/1280/768/390 deterministic shell snapshots using fake local data; run browser loopback-only interception from this Task onward.
- [ ] **GREEN:** shell/settings/full frontend/build/E2E smoke; network/provenance/UI verifiers; common closeout.

Commit: `feat: port the VideoBox product shell`

---

## Slice 2 — Early script-first vertical slice

### Task 7: Persist a provider-neutral Eugene creation brief and adaptive interview

- [ ] **Task 7 완료**

**Files:** create creation-brief domain/core/API/UI modules/tests; modify SQLite schema, `LocalProjectStore`, API models/main/orchestration, `local_pipeline.py`, `api.ts`, route manifest.

- [ ] **RED:** bounded `.txt/.md/.srt` UTF-8 input up to 1 MiB, paste, persisted answers/current step, refresh resume, idempotency key, concurrent duplicate request, project isolation, retention/delete, manual bypass.
- [ ] Interview skips facts already clear from the script, asks only missing/contradictory follow-ups, supports `모르겠어요 / 추천해줘 / 건너뛰기`, has a maximum question count/progress, and ends with an editable summary requiring approval.
- [ ] Define a provider-neutral `CreationInterviewRuntime`. Implement deterministic/fake/local drivers only; `managed` remains an extension point. Local/test external and Gemini calls remain 0.
- [ ] Store brief, answers, script asset reference, question state, capability profile, and idempotency key durably. Provide an explicit creation-brief delete endpoint/action that removes the retained input; do not invent a project-delete API in this Task.
- [ ] **GREEN:** focused backend/frontend, network guard, full affected suites/build; common closeout.

Commit: `feat: interview creators with a persisted Eugene brief`

### Task 8: Resolve narration and asset readiness into an explicit draft plan

- [ ] **Task 8 완료**

**Files:** create draft-readiness domain/core/API/UI modules/tests; modify creation brief storage/orchestration and existing asset APIs only through adapters.

- [ ] **RED:** narration choices—source video audio, existing finished `narration_audio`, microphone recording/upload normalized to `narration_audio`, or silent storyboard—and their permission/error/retry states. A `voice_sample_audio` used only for TTS is not directly selectable as finished narration.
- [ ] Scan existing local assets and produce a deterministic draft plan containing script segments, caption text, ranked B-roll placements, BGM/SFX policy or explicit none, and unresolved `gap_slot` records with reason/target range/media type.
- [ ] Show `자산 확인 중 → 초안 구성 중 → 준비됨/추가 자산 필요 → 실패/재시도`; refresh resumes the exact state. Cancel is allowed before atomic apply.
- [ ] Readiness preview does not mutate the editing session. It reuses the current AssetPreviewPlayer adapter so each ranked candidate can be played by click/keyboard before approval and lets the user edit/skip each choice.
- [ ] Every gap slot offers `자산 추가`: deep-link to existing ingest/upload with a return URL, preserve the brief, show analysis progress, rerun readiness, and replace or retain the gap deterministically. The polished editor asset browser remains Task 19.
- [ ] **GREEN:** focused backend/frontend, fake-provider E2E, external calls 0, full affected suites/build; common closeout.

Commit: `feat: prepare a playable draft plan`

### Task 9: Materialize one real draft atomically and prove the end-to-end value

- [ ] **Task 9 완료**

**Files:** create atomic draft-bundle service/tests and script-first E2E; modify SQLite schema/store transaction, `local_pipeline.py`, API orchestration/router/models, Director proposal transaction adapter, create flow.

- [ ] **RED:** approval-before-mutation, one atomic session+placement bundle, expected `brief_revision` and `draft_plan_revision`, idempotency key, concurrent duplicate submit, source SHA/media revision change after readiness, Nth asset materialization failure, per-SHA staging+atomic rename, staged-file cleanup, restart orphan cleanup, rollback on any failure, same-session retry, and no partial applied session.
- [ ] One `초안 만들기` approval creates/reuses an editing session whose real timeline contains script/narration or silent-storyboard segments, segment-aligned captions, available B-roll placements, explicit BGM/SFX policy, and persisted gap slots. Silent storyboard materializes a project-local deterministic silence narration source/track with provenance so FFmpeg/PyCapCut do not receive an empty narration track. Test source-audio, finished narration, recorded upload, and silence paths through both renderers; reject `voice_sample_audio` as direct narration.
- [ ] A gap-only draft uses a clearly labeled deterministic placeholder visual for in-app draft playback, preserves the unresolved gap, and remains blocked from final/CapCut output until a real visual asset is supplied or the user explicitly accepts a supported placeholder policy. The ready-assets fixture must prove final/CapCut success; the gap-only fixture must prove the block.
- [ ] E2E asserts real session/segment/asset/clip IDs and placements, then opens `/projects/$projectId/editor`. A proposal list or empty provisional session alone is not completion.
- [ ] The vertical slice must also reach existing output ownership: current revision FFmpeg render start, progress, stale warning, retry, final download, in-app playback of the actual composited MP4, and CapCut handoff smoke. A placeholder HTML or download-only assertion cannot satisfy user acceptance. Reuse legacy route adapters until the new Output page is migrated.
- [ ] Record user acceptance after candidate audition and actual current-revision composited playback before investing in precision timeline/waveform work.
- [ ] **GREEN:** atomicity/concurrency tests, fake-provider browser E2E, full affected backend/frontend/build, real local fixture smoke; common closeout.

Commit: `feat: create an edited draft from one approval`

---

## Slice 3 — Editor contract, workbench, and exact preview

### Task 10: Define the editor view model, role-action matrix, and playback manifest

- [ ] **Task 10 완료**

**Files:** create backend playback domain/core/router/tests; create frontend adapter types/adapter/tests; modify API models/main/orchestration/local pipeline and `api.ts`.

- [ ] **RED:** project/session/revision, `timebase=seconds`, rational `fps_num/fps_den`, output width/height, SAR, rotation, duration, stable IDs, typed tracks, source controls/SHA/media revision, captions/style/gap slots, stale source, isolation/path traversal/HTTP Range/MIME.
- [ ] Keep seconds canonical at API boundary. Use rational frame conversion with one documented half-up quantization point; no cumulative float rounding in geometry/export parity fixtures.
- [ ] Publish a role-action matrix: narration supports segment split/merge/bounds/reorder; B-roll/BGM/SFX use typed apply/clear/update-media-controls commands; overlay uses supported apply/clear fields; caption supports select/seek/text/style and inherits segment timing. Unsupported actions are absent.
- [ ] `EditorCommandPort` maps each role to the current specific endpoint and never sends a generic trim with ambiguous meaning.
- [ ] Manifest separates `audition_url` from exact preview artifact/status. Reuse asset FileResponse only if Range/MIME/isolation tests prove it.
- [ ] **GREEN:** focused API/adapter/network tests, full affected suites/build; common closeout.

Commit: `feat: expose an authoritative editor view model`

### Task 11: Build and approve the source-derived responsive editor workbench

- [ ] **Task 11 완료**

**Files:** create toolbar/workbench/left/right/timeline dock components/tests; update route manifest, source map, notices.

- [ ] **RED:** left 자산/대본/자막, center PreviewStage slot, persistent Eugene composer plus inline recommendation area and Inspector, bottom timeline, keyboard resizers, focus, UI-only panel persistence, and viewport density rules.
- [ ] Port OpenCut classic panel composition only through shadcn Resizable. No EditorCore, DB, renderer, or Next code.
- [ ] Editor route auto-collapses sidebar. At 1600+ both docks may open only with preview ≥720px; 1280–1599 opens one dock and keeps preview ≥640px/50%; below 1280 docks become focus-managed drawers.
- [ ] Existing Director/media panels enter through adapters in read-only mode; no duplicate editing truth.
- [ ] Commit deterministic 1920/1440/1280/768/390 populated-workbench snapshots, including the 1920px both-docks state, and obtain the second explicit user visual approval before Task 14 interaction work.
- [ ] **GREEN:** component/full frontend/build/browser density/a11y smoke, provenance/UI/network verifiers; common closeout.

Commit: `feat: compose the VideoBox editor workbench`

### Task 12: Render revision-bound exact FFmpeg proxy previews

- [ ] **Task 12 완료**

**Files:** create exact-preview artifact domain/core/API modules/tests; modify FFmpeg renderer adapter, SQLite schema/store, job domain/store/recovery, local pipeline/orchestration/models/main.

- [ ] **RED:** revision+range+source SHA+render profile cache key, `timelineStartSec/timelineEndSec/artifactRevision/generationId`, B-roll visibility, exactly-once burned captions/overlays, narration/BGM/SFX scheduling, gain/fade/ducking, crop/loop/in/out, output canvas/fps, PTS normalized to zero for a selected range, stale artifact rejection, obsolete-job supersession/late-completion fencing, failure rollback, restart reuse, project isolation/stale path/path traversal, HTTP Range `206`/`Accept-Ranges`/`Content-Range`/invalid range/MIME, H.264/AAC `faststart` browser profile, bounded retention.
- [ ] Reuse the authoritative FFmpeg final composition path through a low-resolution proxy profile; do not create a second composition truth.
- [ ] Return persisted `pending/running/succeeded/failed` state and artifact freshness. A source/revision change invalidates exact preview immediately; same session/range jobs coalesce or supersede; late old completion cannot become current.
- [ ] Selected-range and full-session proxies are both completion gates. Artifact playback maps `timelineTime = timelineStartSec + media.currentTime`; captions are burned exactly once while transcript/ARIA metadata remains synchronized separately.
- [ ] On the recorded local acceptance profile, a standard 10-second 720p selected range must cold-render within 20 seconds and a valid warm-cache lookup must become playable within 500ms. Record actual values; a miss is a failed gate, not an undocumented tolerance.
- [ ] Draft/unapproved editing sessions may request a read-only proxy, but preview creation never sets review approval and cannot bypass final/CapCut output gates.
- [ ] **GREEN:** focused artifact/API/job-restart tests, real FFmpeg fixture, full affected backend; common closeout.

Commit: `feat: render exact revision previews`

### Task 13: Implement PreviewStage and one global preview coordinator

- [ ] **Task 13 완료**

**Files:** create PreviewStage, PreviewCoordinator/context, preview coordinate modules/tests; modify workbench and existing `ManualMediaLibrary`/`AssetPreviewPlayer` adapters; update source map/notices.

- [ ] **RED:** exact proxy play/pause/seek/timeline-origin/range/freshness, full-session playback, selected clip audition, one active media globally, no autoplay, no duplicate visual caption over burned proxy, transcript/ARIA caption sync, recovery, zoom/pan clamp, coordinate/hit-test, focus/scroll/unmount stop.
- [ ] Label two modes plainly: `편집본 미리보기` consumes exact FFmpeg artifact; `선택한 클립 보기` consumes one source audition URL. Source audition never claims to be the composite output.
- [ ] Hover may preload poster/metadata only. Playback requires click/keyboard. On touch: first tap previews, explicit `사용` action applies; moving focus/scrolling away stops playback. Audio never starts on hover.
- [ ] Adapt only OpenCut pure coordinate/zoom/hit-test math with provenance. Preserve server authority for applied crop/controls.
- [ ] **GREEN:** focused/full frontend/build, browser media smoke, network/provenance/UI verifiers; common closeout.

Commit: `feat: preview exact edits and assets safely`

---

## Slice 4 — Timeline, waveform, and captions

### Task 14: Adapt pure timeline geometry and frame-safe scaling

- [ ] **Task 14 완료**

**Files:** create timeScale/timelineGeometry/snapping/hitTesting and property tests; update source map/notices.

- [ ] **RED:** seconds↔pixels round trip, rational 29.97 fixtures, frame-step half-up quantization, zoom anchor, clamp, neighbors, snap deterministic tie, hit priority, rotation/canvas independence, no cumulative drift.
- [ ] Adapt only approved OpenCut classic pure math; keep API seconds and isolate rational/frame rounding in `timeScale.ts`.
- [ ] **GREEN:** focused property tests, full frontend/build, provenance verifier; common closeout.

Commit: `feat: adapt frame-safe timeline geometry`

### Task 15: Add read-only timeline navigation before mutation

- [ ] **Task 15 완료**

**Files:** create viewport/ruler/tracks/clips/playhead/navigation hooks/tests; modify TimelineDock.

- [ ] **RED:** render fixed roles, seek, zoom, scroll, select, playhead keyboard step, snap indicator, gap slot, current caption highlight, and visible-range rendering.
- [ ] Do not expose trim handles yet. Prove a 60-minute/1,000-item structural fixture keeps rendered clip DOM ≤300 and pointer-move React commits ≤1 per animation frame.
- [ ] **GREEN:** focused component/performance structure tests, full frontend/build, browser interaction smoke; common closeout.

Commit: `feat: navigate the fixed-track timeline`

### Task 16: Connect typed revisioned timeline mutations

- [ ] **Task 16 완료**

**Files:** create role-specific handles/drag hooks/tests; modify command adapter and timeline components.

- [ ] **RED:** narration split/merge/bounds/reorder; B-roll/BGM/SFX apply/clear/media-control update; overlay supported actions; undo/redo; Escape cancel; keyboard step; IME/input guard; stale revision recovery; exactly one request on commit.
- [ ] Pointer move changes transient local geometry only. Pointer-up/keyboard commit sends the role-specific command once with base revision.
- [ ] Caption has no independent timing handle. Segment bounds visibly explain that linked narration/caption/placements share the segment boundary.
- [ ] Measure Chrome Playwright drag on the standard fixture after one warm-up and five runs; median input-to-visual update ≤50ms on the recorded CI profile, with the structural budgets from Task 15 as stable gates.
- [ ] **GREEN:** focused interaction/API contract tests, full frontend/backend affected suites/build/E2E; common closeout.

Commit: `feat: edit fixed tracks with revisioned commands`

### Task 17: Generate and render deterministic FFmpeg waveform artifacts

- [ ] **Task 17 완료**

**Files:** create waveform domain/core/API/UI modules/tests; modify SQLite schema/store artifact index, local pipeline/orchestration/main/api client.

- [ ] **RED:** source SHA/stream/channel mix/window/generator-version cache key, finite normalized peaks, deterministic output, invalidation, missing audio, failed retry, process restart reuse, project isolation, no external dependency.
- [ ] Generate versioned peaks through bounded FFmpeg work; persist only artifact index/state. Do not decode full media in browser.
- [ ] Render visible buckets only and reuse timeline seek surface. Cancellation is not claimed in this Task; failure/retry and restart reuse are required.
- [ ] **GREEN:** waveform/API/store-restart tests, real FFmpeg fixture, frontend visible-range tests, full affected suites/build; common closeout.

Commit: `feat: add cached editor waveforms`

### Task 18: Add synchronized transcript and segment-aligned caption editing

- [ ] **Task 18 완료**

**Files:** create TranscriptPanel/CaptionLane/playbackNavigation/shortcutRegistry/tests; modify LeftDock and adapter; update source map/notices.

- [ ] **RED:** current-time clamp, active segment, deleted-range skip, list↔player↔timeline sync, caption text/style, stable sort, input/IME guard, revision conflict, keyboard navigation, and caption timing inherited from segment.
- [ ] Adapt attributed Opencast behavior without Redux/MUI/player fork. Do not implement caption-only drag/resize.
- [ ] Caption lane IDs derive deterministically from persisted segment IDs and are labeled as linked. Timing changes happen only through the narration segment-bound command.
- [ ] For 1,000 captions, keep mounted transcript rows ≤120 with virtualization when needed; screen-reader position and focus restoration remain correct.
- [ ] **GREEN:** focused/full frontend/backend affected suites/build, 1,000-caption browser check, provenance/UI verifiers; common closeout.

Commit: `feat: edit segment-aligned captions in sync`

---

## Slice 5 — Assets, recommendations, Eugene, and Inspector

### Task 19: Migrate the editor asset browser and safe preview/apply flow

- [ ] **Task 19 완료**

**Files:** create EditorAssetBrowser/Card/tests; modify LeftDock and existing media adapters; update source map/notices.

- [ ] **RED:** search/filter, B-roll/BGM/SFX/image/voice types, poster preload, click/keyboard preview, touch behavior, one global preview, selected-range target, explicit apply, failed materialization/session unchanged, license/review/analysis states.
- [ ] Reuse current media APIs and PreviewCoordinator. Do not fork asset truth or preview state.
- [ ] Recommendation/asset card displays target scene, reason, duration, audio presence, analysis/license state, and intended apply range.
- [ ] **GREEN:** focused/full frontend/backend affected tests/build/E2E, network/UI/provenance verifiers; common closeout.

Commit: `feat: browse and apply editor assets`

### Task 20: Integrate persistent Eugene conversation, inline recommendations, and typed Inspector

- [ ] **Task 20 완료**

**Files:** create Inspector registry/context-pane tests; modify RightDock and existing Director components only through adapters; update source map/notices.

- [ ] **RED:** Eugene context includes selected segment/range/placement/proposal revision/gap slot; inline candidate compare/preview/preflight/explicit apply; conversation/candidate/player/scroll state survives Inspector open/close; manual fallback when Eugene is blocked.
- [ ] Keep Eugene composer visible. Recommendations appear inline or adjacent; Inspector opens for selection without destroying conversation state.
- [ ] Registry exposes only backend-supported B-roll/BGM/SFX/caption/voice/overlay controls. Unsupported OpenCut effects are absent.
- [ ] Local/test fake provider and network guards prove external/Gemini calls 0.
- [ ] **GREEN:** focused/full frontend/backend affected tests/build/E2E, source→runtime review; common closeout.

Commit: `feat: join Eugene recommendations and Inspector`

---

## Slice 6 — Hardening, parity, and release

### Task 21: Add deterministic responsive, accessibility, visual, performance, and network gates

- [ ] **Task 21 완료**

**Files:** extend the Task 6 Playwright config/webServer/fake-provider harness; create the full E2E/snapshot/accessibility/performance suites; modify package scripts and `scripts/dev-fast-path.ps1` only if adding a tested mode.

- [ ] **RED:** 390/768/1280/1440/1920 journeys, including the populated 1920px both-docks editor; offcanvas/drawers/focus trap-return; reduced motion; keyboard timeline; screen-reader labels; no autoplay; error recovery; fake API/provider isolation.
- [ ] Commit deterministic snapshots under a documented Playwright snapshot path. Fixed clock/animation/local fixture and manifest SHA make diffs reproducible.
- [ ] Browser network interception permits only loopback origins. Vitest socket/fetch guard remains active. External/Gemini calls are 0 in local/test profile.
- [ ] Performance protocol: recorded Chromium version and CI hardware profile, one warm-up/five measured runs, median and p95 report. Structural budgets from Tasks 15/18 are hard gates; browser mount/seek/drag budgets are baseline-regression gates with ≤20% allowed drift.
- [ ] If `dev-fast-path` gets a new `focused` mode, add script self-test; otherwise release uses the existing `-Mode current-focused` exactly.
- [ ] **GREEN:** full E2E/a11y/visual/perf/network suites, full frontend/build; common closeout.

Commit: `test: harden the VideoBox creator workspace`

### Task 22: Complete parity, remove the legacy shell, and run the release audit

- [ ] **Task 22 완료**

**Files:** modify/delete legacy App/styles only after parity; migrate remaining route pages; update notices/source map/SSOT; conditionally modify `development-fast-path.ko.md` only for an observed regulation gap; create final closeout handoff.

- [ ] **RED parity checklist:** project create/select, ingest, job recovery, script draft, editor preview/timeline/Director/assets, settings/voice, subtitle/exact preview/final/CapCut output, errors, refresh recovery each have a route/component/E2E owner.
- [ ] Remove legacy route/custom classes only after parity. `App.tsx` becomes root composition; persisted-data compatibility adapters remain while used.
- [ ] Run UI-system AST inventory so migrated features cannot keep direct native buttons/inputs/dialogs or legacy `.panel/.pill/.action-button` except documented accessibility/media allowlist.
- [ ] Run provenance/license inventory/SBOM/external-network scan and prove no rejected runtime import.
- [ ] Run `./scripts/dev-fast-path.ps1 -Mode current-focused`, full frontend/build/E2E, full pytest, provenance/UI verifiers, `git diff --check`, `git status --short`, real local FFmpeg/PyCapCut acceptance gates, and six-gate independent release audit.
- [ ] Update all 22 Task checkboxes and cumulative progress only from observed commits/tests. Human CapCut Desktop/listening approval remains a reported human gate.
- [ ] Commit, push, and write the next operational handoff.

Commit: `feat: release the VideoBox creator workspace`

---

## 3. Slice gates and cumulative progress

| Slice | Tasks | Exit gate |
|---|---:|---|
| 0. Baseline/direction/provenance | 1–3 | dirty work closed, three-screen visual approval, reproducible source locks |
| 1. Foundation/shell | 4–6 | real project shell at four viewports, local network 0, full frontend/build green |
| 2. Script-first vertical | 7–9 | one approval creates an actual asset-placed draft and reaches output handoff |
| 3. Workbench/exact preview | 10–13 | authoritative adapter, approved workbench, revision-bound FFmpeg preview |
| 4. Timeline/captions | 14–18 | frame-safe timeline, typed mutations, waveform, linked caption sync |
| 5. Assets/Eugene | 19–20 | previewable assets and inline recommendations apply explicitly |
| 6. Release | 21–22 | responsive/a11y/visual/perf/parity/provenance gates and full release audit |

Initial production progress is **0/22 Tasks (0%)**. Research/design/plan creation does not count as production implementation.

## 4. Explicitly deferred work

- Hermes agent/container and Telegram ingestion
- SaaS auth, organization, team, billing backend and managed AI driver implementation
- OpenCut future Editor API/MCP/headless integration
- independent caption cue timing model/API and caption-only drag/resize
- keyframe/effect/transition/mask engine
- voice cloning policy and cloud provider routing
- destructive original-media editing

These may use the new shell extension points later, but must not enter the 22-Task denominator.
