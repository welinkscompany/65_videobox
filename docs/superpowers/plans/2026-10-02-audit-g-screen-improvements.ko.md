# 묶음 G — 화면 개선 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> 2026-10-10: Task 0·6·13은 계획 H(`2026-10-08-editor-core-repair-h.ko.md`)가 먼저 실행했다 — 건너뛴다. Task 17 갭 점검에 그렇게 적는다.

**Goal:** 대표님이 화면에서 바로 느끼는 불편을 줄인다. 프로젝트 카드에 첫 장면 그림이 보이고, 여러 프로젝트를 한 번에 보관(되돌리기 가능)하고, 검토 화면에서 편집본을 바로 재생하고, `+ 새로 만들기` 큰 막대를 카드 한 칸으로 줄이고, 편집기·설정·검토 화면의 겹치는 안내와 스크롤을 정리한다.

**Architecture:** 새 화면이나 새 재생기를 만들지 않는다. 이미 있는 부품을 다시 쓴다.
- 카드 그림: `GET /api/projects/{id}/workspace-summary`가 이미 `thumbnail_url`을 준다. 지금은 "그림 정보가 붙은 첫 자산"만 보고 있어서 73개 중 64개가 비어 있다. 같은 응답 안에서 **첫 장면(빼지 않은 장면)의 B-roll 자산**을 먼저 고른다. 그림 자체는 이미 있는 `GET /api/projects/{id}/assets/{asset_id}/thumbnail`이 만든다(캐시가 없으면 원본에서 다시 그린다, `routers/assets.py:608-640`). 새 엔드포인트는 만들지 않는다.
- 여러 개 보관: 이미 있는 `api.archiveProject`·`api.restoreProject`를 차례로 부른다. 묶음 엔드포인트를 새로 만들지 않는다.
- 검토 화면 재생기: 편집기의 `PreviewStage`(`features/editor/preview/preview-stage.tsx`)를 그대로 쓴다. 필요한 재생 정보(`playback-manifest`)는 `OutputsPage`가 **이미 읽고 있다**(`OutputsPage.tsx:543-548`) — 상태 판정에만 쓰고 버리던 것을 보관해 재생기에 넘긴다. 요청이 늘지 않는다.
- 접기 상태 기억은 기존 `editorUiState.ts`의 방어적 localStorage 패턴(try/catch)을 그대로 따른다.

**재사용 게이트(§8.1):**
| 후보 | 판단 | 반영 단위 |
|---|---|---|
| `workspace-summary` + 자산 썸네일 엔드포인트 | adopt as-is + 고르는 규칙만 보강 | `routers/projects.py` 함수 하나 |
| `archiveProject`/`restoreProject` | adopt as-is | 화면에서 반복 호출 |
| `PreviewStage` | adopt as-is | 검토 화면에서 그대로 렌더 |
| `VariantConflictPanel` | partial(선택 prop 하나 추가) | 같은 충돌 묶어 그리기 |
| 새 `GET /api/projects/{id}/thumbnail` | **exclude** — 같은 일을 하는 길이 이미 있다 | — |
| 새 일괄 보관 API | **exclude** — 프로젝트 수가 수십 개 수준, 순차 호출로 충분 | — |
| 자료실 썸네일 파일(`_ensure_derivative`가 이미 쓰는 이름 규칙) | partial — 이미 있는 파일을 읽는 함수 하나 | `routers/library_assets.py` (Task 12) |
| 자료실 화면 쪽 lazy·paging | **exclude** — 이미 `loading="lazy"`, 이미 24장 상한 | — |
| B-roll 목록 공유(분석 칸 ↔ 편집기) | **exclude** — 요청 하나(0.03초) 줄이려고 분석 칸을 편집기 상태에 묶지 않는다 | — (Task 13에 기록) |

**Tech Stack:** React 19 + TanStack Router + shadcn `Button`/`Card` + Tailwind utilities, vitest + Testing Library(jsdom), FastAPI + pytest, Docker 컨테이너(nginx 앞문 `http://127.0.0.1:5173`).

**Spec:** docs/superpowers/2026-10-02-audit-follow-up-plan.ko.md + docs/decisions/2026-10-02-audit-follow-up-decisions.ko.md

## 실측 기록 (2026-10-02, 계획 작성 시 실제 화면에서 잼)

| 잰 것 | 값 | 어디서 |
|---|---|---|
| 카드 그림이 있는 프로젝트 | **73개 중 9개**(64개 `thumbnail_url: null`) | `curl /api/projects/*/workspace-summary` |
| 그림 없는 프로젝트의 실제 첫 장면 그림 | 있다 — 예: `2026-09-12-742e1924`의 첫 장면 `asset_b06cecf90977` → `/thumbnail` **200 image/png** | 세션 `segments[0].broll_override.asset_id` |
| (검토자 재측정) 첫 장면 그림이 실제로 나오는 프로젝트 수 | 73개 중 편집 세션 없음 25 · 장면에 자산 없음 31 · 장면 자산 있음 **17**(그중 `/thumbnail` 200은 **15**, 404 둘: `ai-qa-20260826-8a11f547`, `progress-bar-live-test`). 옛 규칙 9개와 합치면 Task 1 뒤 카드 그림은 **약 21/73**이다. "대부분"이 아니다 — 나머지 52장은 빈 16:9 칸(Task 2)으로 보인다 | `editing-sessions/latest` + `/thumbnail` 실제 호출 |
| (검토자 재측정) 카드 그림 비용 | 첫 요청(캐시 없음) 0.02~0.60초, 두 번째부터 0.023~0.045초. 크기 14~196KB(PNG). 응답에 `etag`·`last-modified`는 있고 `Cache-Control`은 없다 → 브라우저가 다시 확인(304)만 한다. 21장 × 최대 196KB ≈ 2MB, `loading="lazy"`라 첫 화면은 12장 이하. **캐시 머리글 추가는 불필요하다고 판단** | `curl` 5건 이상 2회씩 |
| (검토자 재측정) 자료실 썸네일 비용 | `GET /api/library/assets?limit=500` **0.32초**(180KB, 235개). 썸네일은 **이미 만들어진 것도 한 장 평균 0.30초**, 원본 546MB짜리는 **2.9초** — 요청마다 원본 파일 전체 sha256을 다시 재고(`resolve_managed_path`) 썸네일 파일 해시·DB 기록(`upsert_derivative`)까지 다시 한다(`routers/library_assets.py` `get_derivative`). 235장 직렬 합계 70.5초, 6개 병렬 12~16초. 프로젝트 자산 썸네일(같은 크기)은 0.025초 | `curl` 235건 2회 |
| (검토자 재측정) 자료실 화면 | `LibraryResults.tsx`가 이미 `assets.slice(0, 24)`만 그리고 `VideoAssetGrid`의 `<img>`는 이미 `loading="lazy"`다. **화면 쪽은 할 일이 없다** — 느린 것은 위 서버 경로다 | 소스 + 브라우저 `img[loading=lazy]` 24/24 |
| (검토자 재측정) 편집기 첫 로드 중복 요청 | 운영 빌드(5173, `main.tsx`에 StrictMode 없음)에서 `assets/broll-video` ×2(887ms·1137ms), `transition-suggestions` ×2(886ms·1140ms). 원인: 전환 추천은 effect 의존값 `state.session?.expectedRevision`이 `undefined`→`1`로 바뀌며 다시 돈다. B-roll은 **다른 소비자 둘**(`EditorWorkbenchRoute` 자산 effect + `MediaAnalysisStatusPanel`) | `performance.getEntriesByType('resource')` |
| (검토자 재측정) 검토본 장면 0개 | `2026-09-12-742e1924`: 세션 `editing_session_001` 15장면, `timeline_build_job_001`의 타임라인은 broll 15클립인데 `/review-snapshots/timeline_build_job_001`의 `segments`는 **0** — 검토본 장면은 세션이 아니라 **전사 `segments` 표**(`store.list_segments`)에서 온다(`local_pipeline.py` `get_review_snapshot`) | API 3건 |
| (검토자 재측정) Playwright 6개 파일 | main `ca39f2a7f`에서 product-shell·job-recovery·media-recovery·z-script-first-vertical·editor-workbench·exact-preview **35 passed (1.2분)**. 끝에 스냅샷 목록 검사가 남은 파일 하나로 exit 1(Global Constraints 참고) | `npm run test:e2e -- …` |
| 그림 있는 카드 / 없는 카드 높이 | **339px / 195px** — 한 줄에 섞이면 줄 높이가 들쭉날쭉 | 1440×900 `/projects` |
| `+ 새로 만들기` 막대 | **1120×80px**, 카드 한 칸은 **268px** 폭 | 1440×900 |
| 검토 화면 출력 칸, 375px 폭 | **4칸 그대로, 칸당 77px 폭 × 1524px 높이** (`.vb-outputs-grid`가 767px 이하 규칙보다 뒤에 있어서 이김) | 375×812 `/projects/2026-09-12-742e1924/review` |
| 같은 충돌 카드 | `세로 편집과 마스터가 달라요 / 스토리` **2장 동일**(가로 영상·세로 영상) | 같은 화면 |
| 반복 안내 | `검토 승인과 확인할 항목을 모두 마친 뒤 …` **4곳**(숏폼·자막·완성본·CapCut) — 위 `출력 준비 체크리스트`와 같은 말 | `OutputsPage.tsx:1394,1450,1462,1571` |
| 검토 화면 재생 | 없다. `재생은 편집 화면에서 확인해 주세요.` 한 줄뿐 | `OutputsPage.tsx:1406` |
| 편집기 `편집 작업판` 머리 | **58px**, `가로·세로 비교` 띠(접힌 상태) **49px**, 미리보기·도크 줄 **416px**(작업판 783px의 53%) | 1440×900 `/projects/0907-b26195af/editor` |
| 편집기 스크롤 영역 | 왼쪽 도크 414/3616, 오른쪽 도크 414/1468, 타임라인 187/278 — 서로 **겹치지 않음**. **겹치는 것은 유진 패널 하나**: 패널(382/759)이 스크롤되고 그 안의 대화 기록(207/3096)이 또 스크롤된다 | 같은 화면, 유진 열고 |
| 오디오 도크 가로 넘침 | 도크 폭 221px, 내용 252px — `만든이 Zane Little Music 빼기` 단추(167px)가 줄바꿈을 못 해서 | 같은 화면, `오디오` 탭 |
| 검토 승인 문구 | 검토·출력이 한 화면인데 `이제 내보내기 화면에서 자막과 완성본을 만들 수 있어요.` | `TimelineReviewPage.tsx:130` |
| 설정 칸 | 5칸(화면·AI·개인정보·내 목소리·출력·유진 대화) 중 셋이 문장 한 줄짜리 | `ProductShell.tsx:215-219` |

## Global Constraints

- 최상위 지침은 `CLAUDE.md`. 작업은 메인 체크아웃 `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`(브랜치 `main`)에서 한다. 시작 전에 `git status --short`, `git log --oneline -3`으로 다른 묶음(A~F)의 커밋이 끼어 있는지 보고, **이 계획의 앵커 문자열이 그대로 있는지 grep으로 먼저 확인**한다(줄 번호는 계획 작성 시점 기준이라 밀릴 수 있다. 앵커는 문자열로 찾는다).
- **팔레트는 바꾸지 않는다**(`2026-08-29` 결정). 새 CSS는 기존 토큰(`--vb-*`, `--border`, `--card` 등)만 쓴다. 새 색 값(`#…`, `rgb(…)`)을 쓰지 않는다.
- **시작하는 문은 `+ 새로 만들기` 하나**(`2026-09-05`). 칸으로 줄여도 단추는 하나, 접근 이름은 계속 `+ 새로 만들기`.
- **`/`는 `/projects`**. 라우트를 바꾸지 않는다. 옛 설정 주소(`/settings/general`·`/ai-privacy`·`/voice`·`/output`)는 계속 화면을 그려야 한다(복구 화면 금지).
- **영구 삭제는 이 묶음에서 새로 만들지 않는다.** 여러 개 고르기는 **보관**만 한다.
- 유진에게 프로젝트 보관을 여는 일은 **묶음 F**의 몫이다(결정 문서 "그 밖에 유진에게 열 것"). 이 묶음에서 유진 의도·적용기·안내문은 건드리지 않는다. 그 사실을 Task 17 갭 점검에 적는다.
- 웹 시험은 **`apps/web`에서** 돈다: `cd apps/web && npx vitest run <파일>`(저장소 루트에서 돌리면 jsdom이 깨진다). 타입검사 `cd apps/web && npx tsc --noEmit`. 빌드 `npm --prefix apps/web run build`.
- backend 시험은 `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider <파일>::<시험>`(저장소 루트에서). 맨 `pytest` 금지. 전체 pytest는 약 50분이라 Task 17 끝에 **단독으로** 한 번만, `--ignore=tests/test_mcp_server.py`를 붙인다.
- 이미 알려진 실패(고치려 들지 마라): `apps/web/src/features/editor/workbench/editor-workbench.test.tsx`의 "gives the material dock back the same way, without needing a second click", `tests/test_owner_ready_script.py::test_smoke_timeout_kills_the_child_tree_and_returns_bounded_failure`.
- `apps/web/src/app/ProductShell.tsx`는 `docs/oss/editor-ui-source-map.json`에 SHA-256이 **두 곳**(`normalized_sha256`, 101-111행 부근) 박혀 있다. 고치면 두 곳을 같이 바꾸고 `tests/test_editor_ui_source_provenance.py`를 돌린다(Task 7).
- `apps/web/src/task22-parity-owners.test.ts`는 날 것 `<button>`/`<input>`(`data-native-control`)을 파일별로 센다. **이 계획은 날 것 컨트롤을 새로 쓰지 않는다** — 전부 shadcn `Button`이다. 그래서 허용 목록은 안 바뀌어야 한다. 바뀌면 그 Task에서 무엇을 잘못 썼는지 보고 고친다.
- 화면 문구는 §10.13: 명사형 이름표, 필요한 곳만 짧은 해요체. `provider`·`runtime`·`model`·`job`·`revision`·`pipeline`·`시스템`·`모델`·`파이프라인` 금지. `apps/web/src/user-copy-policy.test.ts`가 지킨다 — UI Task마다 마지막에 돌린다.
- 컨테이너는 `.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild`(PowerShell)로만 재빌드한다. `docker compose`를 직접 치지 않는다. 재빌드 뒤 브라우저는 한 번 `Ctrl+F5`.
- 브라우저 확인은 **1440×900과 375×812** 둘 다. 375에서는 `document.documentElement.scrollWidth === document.documentElement.clientWidth`여야 한다.
- 내장 브라우저 창은 전이·애니메이션을 안 그릴 수 있다(기억 메모). 크기·위치는 **JS로 재서** 판단하고, 눈으로 볼 것은 스크린샷으로 확인한다.
- Playwright 스냅샷 PNG(`apps/web/e2e/snapshots/`)는 화면을 바꿔도 **다시 쓰지 않는다**. 다시 쓰는 것은 owner가 차이를 본 뒤의 일이다(`e2e/snapshots/README.ko.md`). 바뀐 화면이 스냅샷과 달라진다는 사실만 Task 17 보고에 적는다.
  **주의(검토자 실측 2026-10-02):** `product-shell.spec.mjs`·`editor-workbench.spec.mjs`의 스냅샷 시험은 비교하지 않고 `page.screenshot`으로 **추적 중인 PNG를 그 자리에 덮어쓴다.** Playwright를 돌린 뒤에는 반드시 `git status --short apps/web/e2e/snapshots`를 보고, 바뀐 PNG가 있으면 그 차이를 보고에 적은 다음 `git checkout -- apps/web/e2e/snapshots/*.png`로 되돌린다(이 Task가 만든 변경만 되돌리는 것이다). 스냅샷 PNG를 커밋에 넣지 않는다.
  또 `npm run test:e2e`는 시험이 다 통과해도 끝에 `unexpected PNG: product-shell-mobile-menu-open.png`로 **exit 1**이 난다 — 2026-07-18부터 있던 gitignore된 남은 파일 때문이고 이 묶음과 무관하다(main `ca39f2a7f`에서 35 passed 후 같은 줄 확인). 지우지 말고 보고만 한다.
- Task마다 커밋한다. 커밋 메시지는 한국어, 끝줄은 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. 푸시는 Task 17 검증이 끝난 뒤 **`git push origin main`** 한 줄로(강제 푸시 금지). 확인 명령과 푸시를 한 명령에 묶지 않는다. 도구 권한이 푸시를 막으면 **우회하지 말고 멈춘다** — owner에게 `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`에서 `git push origin main`을 직접 실행하거나 허용 규칙 `Bash(git push origin main)`을 추가해 달라고 말한다.
- **실행 순서:** Task 0(성능 기준선 — 화면을 바꾸기 **전에**) → Task 1~15 → Task 16(결정 기록, Task 17 측정 뒤 커밋) → Task 17.
- Task마다 닫을 때 검증 넷: **갭**(이 Task의 Step 대조, 안 한 것을 적는다) · **역방향**(Task 17에서 컨테이너+브라우저로 한 번에) · **동작**(px로 잰다) · **배선**(grep으로 화면이 실제로 부르는 자리를 센다).

## Review Focus

행복한 경로 시험이 놓치기 쉬운, 실제로 일어날 입력 다섯. 각각 맡은 Task에 시험을 넣는다.

1. **첫 장면 그림이 지워졌다**(캐시도 원본도 없음 → `/thumbnail` 404). 카드가 깨진 그림 아이콘을 보이거나 높이가 바뀌면 안 된다 → Task 2의 `onError` 시험. 첫 장면을 **뺐거나**(`cut_action: "remove"`) 그 장면의 B-roll 칸에 음악 같은 그림 없는 자산이 걸려 있으면 다음 장면을 본다 → Task 1 시험 둘.
2. **여러 개 보관 중 일부만 실패**(셋 중 하나 네트워크 오류). 성공한 것만 되돌리기 대상이고, 몇 개가 안 됐는지 말해야 한다 → Task 4 부분 실패 시험.
3. **검토 화면 미리보기가 낡았거나 아직 없음**. 재생기 자리에 실패 대신 `미리보기 새로 만들기`가 있고, 누르면 **현재 판수**(`expected_revision`)로 만들기를 요청하고 기다리는 동안 상태 문구가 보여야 한다 → Task 5 시험.
4. **브라우저 저장소가 막힘**(사생활 모드, `localStorage.setItem`이 예외). 접기 단추가 화면을 죽이지 않고 이번 세션에는 동작해야 한다 → Task 6 시험.
5. **유진의 긴 답이 대본이 아닌 경우**(예: "B-roll 추천해 줘"에 대한 긴 설명). 그 아래에 `이 답을 대본으로 쓰기`가 뜨면 안 된다 → Task 8 시험.
6. **(검토 추가) 한 화면에 재생기가 둘**(검토 화면의 편집본 미리보기 + 완성본 `<video controls>`). 완성본에 포커스를 두고 스페이스를 누르면 완성본만 움직여야 한다 → Task 5 `preview-stage.test.tsx` 시험.

---

### Task 0: 편집기 도크 끌기 성능 기준선을 다시 잰다 (먼저 한다, 화면을 바꾸기 전에)

**왜 먼저인가:** `apps/web/e2e/release-gates.spec.mjs`의 "workbench dock drag has fixed warmup and five-sample local performance evidence"가 기계 부하에 따라 128ms 한도(기준 107ms + 20%) 근처에서 오락가락한다. 검토 의뢰자가 main `ca39f2a7f`과 그 앞 커밋에서 둘 다 **120~133ms**를 쟀다 — 코드 회귀가 아니라 기계 상태로 보인다. 이 묶음은 Task 6·10에서 편집기 화면을 바꾼다. 기준선을 **바꾸기 전 코드**로 다시 재 두어야 Task 6·10이 끌기를 느리게 만들면 게이트가 그것을 잡는다. 순서를 거꾸로 하면 내 회귀를 기준선에 묻어 버린다.

**바꾸지 않는 것:** `regression_limit_percent: 20`(20% 규칙)은 **절대 바꾸지 않는다**. 시험 코드(`release-gates.spec.mjs`, `support/release-gates.mjs`)도 바꾸지 않는다. 바꾸는 것은 기준선 파일의 측정값 넷(`captured_on`·`median_ms`·`p95_ms`·`capture_intent`)과, 브라우저 판이 바뀌었을 때만 `browser_version`이다.

**Files:**
- Modify: `apps/web/e2e/support/workbench-performance-baseline.json`(전체 11줄)
- Modify: `apps/web/e2e/support/release-gates.test.mjs:1-5`(import), `:18-48`(성능 보고 단위 시험)

> **검토자가 찾은 기존 결함:** `cd apps/web && node --test e2e/support/release-gates.test.mjs`는 **지금 main에서 실패한다**(`deepStrictEqual` — `baseline_median_ms: 107` ≠ `92`). 2026-09-20 재측정(`717ff6f6d`)이 기준선 파일만 고치고, 그 값을 숫자로 박아 둔 이 단위 시험(`92`·`108`·옛 `capture_intent`, 그리고 `111`ms를 "회귀"로 기대하는 줄)을 안 고쳤다. 이 시험은 vitest가 아니라 `node --test`라서 아무도 안 돌렸다. 기준선을 또 바꾸면 또 깨진다 — 그래서 Step 0에서 **기준선 파일을 읽어 비교하도록** 먼저 고친다. 20% 규칙은 오히려 시험이 직접 지키게 한다(`regression_limit_percent === 20`).

**Interfaces:**
- Consumes: 시험이 쓰는 보고서 `editor-workbench-performance.json`(`testInfo.outputPath`, 키 `measurements_ms`(5개)·`median_ms`·`browser.version`), 기준선 파일의 절차(`capture_intent`: "5회 독립 실행 x 5샘플", 2026-09-20 커밋 `717ff6f6d`).
- Produces: 새 기준선(25샘플의 중앙값·p95), 확인 실행 3회 결과.

- [ ] **Step 0: 단위 시험이 기준선 파일을 읽게 고친다(RED → GREEN)**

RED 확인: `cd apps/web && node --test e2e/support/release-gates.test.mjs`
Expected: 끝 요약에 `ℹ fail 1` — `performance report has a fixed five-sample protocol …`에서 `AssertionError … deepStrictEqual`(`baseline_median_ms: 107` vs `92`).

`apps/web/e2e/support/release-gates.test.mjs` 맨 위:
```js
import assert from "node:assert/strict";
import test from "node:test";

import { assessWorkbenchPerformance, isAllowedBrowserRequest } from "./release-gates.mjs";
```
→
```js
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { assessWorkbenchPerformance, isAllowedBrowserRequest } from "./release-gates.mjs";

// 기준선은 기계에 맞춰 다시 잴 수 있다(2026-09-20, 2026-10-02). 값을 여기 숫자로 박아 두면
// 재측정할 때마다 이 시험이 깨진다 -- 2026-09-20 재측정 뒤 실제로 깨진 채 남아 있었다.
// 기준선 파일을 그대로 읽고, **20% 규칙만은 여기서 직접 지킨다.**
const baseline = JSON.parse(readFileSync(new URL("./workbench-performance-baseline.json", import.meta.url), "utf8"));
```

같은 파일의 세 줄:
```js
    baseline_median_ms: 92,
    baseline_p95_ms: 108,
```
→
```js
    baseline_median_ms: baseline.median_ms,
    baseline_p95_ms: baseline.p95_ms,
```
```js
    baseline_capture_intent: "calibrated reference capture on 2026-07-23",
```
→
```js
    baseline_capture_intent: baseline.capture_intent,
```
그리고 이 줄:
```js
  assert.equal(assessWorkbenchPerformance({ browserVersion: "149.0.7827.55", ciProfile: "chromium-headless-workers-1-1920x1080", warmupMs: 1, measurementsMs: [111, 111, 111, 111, 111] }).regression, true);
```
→
```js
  // 한도는 기준선 중앙값의 120%다. 한도 바로 위는 회귀, 한도 그 자체는 회귀가 아니다.
  assert.equal(baseline.regression_limit_percent, 20);
  const limitMs = baseline.median_ms * 1.2;
  const overLimit = Math.floor(limitMs) + 1;
  assert.equal(assessWorkbenchPerformance({ browserVersion: baseline.browser_version, ciProfile: baseline.capture_profile, warmupMs: 1, measurementsMs: [overLimit, overLimit, overLimit, overLimit, overLimit] }).regression, true);
  assert.equal(assessWorkbenchPerformance({ browserVersion: baseline.browser_version, ciProfile: baseline.capture_profile, warmupMs: 1, measurementsMs: [limitMs, limitMs, limitMs, limitMs, limitMs] }).regression, false);
```
(같은 시험 안의 `browserVersion: "149.0.7827.55"`·`browser: { … version: "149.0.7827.55" … }` 두 곳도 Step 4에서 `browser_version`을 바꾸게 되면 `baseline.browser_version`으로 바꾼다. 안 바꾸면 그대로 둔다.)

GREEN 확인: `cd apps/web && node --test e2e/support/release-gates.test.mjs` → 끝 요약에 `ℹ pass 2`, `ℹ fail 0`(검토자가 저장소 밖 복사본에 이 수정을 적용해 실제로 확인함).

커밋(기준선 판정과 별개로 이 수정은 늘 커밋한다):
```bash
git add apps/web/e2e/support/release-gates.test.mjs
git commit -m "test(e2e): 성능 게이트 단위 시험이 기준선 파일을 읽게

2026-09-20 재측정 뒤 숫자를 박아 둔 단위 시험이 깨진 채였다(node --test라
아무도 안 돌렸다). 기준선 파일을 읽고, 20% 규칙은 시험이 직접 지킨다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 1: 지금 상태를 적는다(측정 — 동작 변경 없음)**

Run: `git log --oneline -1` → `ca39f2a7f`(또는 그 뒤 A~F 묶음 커밋. 그 경우 그 커밋 번호를 적는다).
Run: `git log --oneline 717ff6f6d..HEAD -- apps/web/src/features/editor/workbench/EditorWorkbench.tsx apps/web/src/styles/editor-workbench.css apps/web/src/components/ui/resizable.tsx apps/web/e2e/release-gates.spec.mjs apps/web/e2e/support/release-gates.mjs` → 기준선 이후 끌기 경로를 건드린 커밋 목록(검토 시점 1건). 목록을 그대로 보고에 붙인다.
Run(배경 부하 기록, 읽기만 한다): `docker ps -q | wc -l` → 지금 도는 컨테이너 수(2026-09-20 기록은 25개).

- [ ] **Step 2: 5회 독립 실행 × 5샘플을 모은다**

다른 무거운 일(전체 pytest, 컨테이너 재빌드, 다른 e2e)을 돌리지 않는 상태에서, 평소 배경 부하(컨테이너는 켜 둔 채)로 Git Bash에서:

```bash
cd apps/web
for i in 1 2 3 4 5; do npm run test:e2e -- e2e/release-gates.spec.mjs -g "workbench dock drag" --reporter=line --output "test-results/recal-$i"; done
```
각 실행의 종료 코드는 0이 아닐 수 있다(한도 초과 또는 끝의 `unexpected PNG` — Global Constraints). 상관없다. 보고서는 단언 **앞에서** 쓰인다.

모은다:
```bash
node -e "const fs=require('fs'),path=require('path');const files=[];const walk=d=>{if(!fs.existsSync(d))return;for(const e of fs.readdirSync(d,{withFileTypes:true})){const p=path.join(d,e.name);if(e.isDirectory())walk(p);else if(e.name==='editor-workbench-performance.json')files.push(p);}};for(let i=1;i<=5;i++)walk('test-results/recal-'+i);const reports=files.map(f=>JSON.parse(fs.readFileSync(f,'utf8')));const all=reports.flatMap(r=>r.measurements_ms).sort((a,b)=>a-b);const q=p=>all[Math.min(all.length-1,Math.ceil(p*all.length)-1)];console.log(JSON.stringify({files:files.length,n:all.length,min:+all[0].toFixed(1),median:+q(0.5).toFixed(1),p95:+q(0.95).toFixed(1),max:+all.at(-1).toFixed(1),perRunMedian:reports.map(r=>r.median_ms&&+r.median_ms.toFixed(1)),browser:reports[0].browser.version}))"
```
Expected: `files: 5`, `n: 25`. 5개가 아니면(실행이 중간에 죽음) 모자란 만큼 `recal-6`, `recal-7`…로 더 돌려 5개를 채운다.

- [ ] **Step 3: 판정한다 — 셋 중 하나**

- (가) `median ≤ 128`(=107×1.2): 기준선이 아직 맞다. **기준선을 바꾸지 않는다.** 오락가락은 순간 부하로 적고 이 Task를 끝낸다(커밋 없음).
- (나) `median > 128`이고 Step 1의 끌기 경로 커밋 목록이 **비어 있거나 끌기와 무관**(문구·주석만)하다: 기계 환경 변화로 본다 → Step 4로 간다.
- (다) `median > 128`이고 끌기 경로를 바꾼 커밋이 있다: **기준선을 바꾸지 않는다.** 그 커밋이 원인일 수 있다. 측정값과 커밋 목록을 보고하고 멈춘다(owner 판단).

`browser` 값이 기준선의 `149.0.7827.55`와 다르면 그 자체로 구조 실패(`structural_failure: true`)라 위 판정과 무관하게 Step 4에서 `browser_version`만 같이 고친다(값은 그대로 옮겨 적는다).

- [ ] **Step 4: (나)일 때만 기준선을 고친다**

`apps/web/e2e/support/workbench-performance-baseline.json`에서 네 값만 바꾼다(`<…>`는 Step 2 출력의 숫자를 반올림한 정수, `<containers>`는 Step 1 숫자, `<commits>`는 Step 1 목록 요약):

```json
  "captured_on": "2026-10-02",
  "median_ms": <median 반올림>,
  "p95_ms": <p95 반올림>,
  "capture_intent": "recalibrated on 2026-10-02 -- 2026-09-20 기준선(median 107ms)이 이 기계의 현재 배경 부하(컨테이너 <containers>개)에서 128ms 한도 근처를 오갔다(검토 의뢰자 실측: ca39f2a7f와 그 앞 커밋 모두 120~133ms). 화면 변경(묶음 G Task 6·10) 전에 25회 측정(5회 독립 실행 x 5샘플)을 모아 다시 쟀다(min <min>, median <median>, p95 <p95>, max <max>ms). 2026-09-20 이후 끌기 경로 커밋: <commits>. 20% 규칙은 그대로.",
```
`regression_limit_percent`·`schema`·`capture_profile`·`interaction`은 그대로 둔다.

- [ ] **Step 5: 확인 실행 3회**

```bash
cd apps/web
for i in 1 2 3; do npm run test:e2e -- e2e/release-gates.spec.mjs -g "workbench dock drag" --reporter=line --output "test-results/recal-check-$i"; done
```
Expected: 세 번 모두 시험 자체는 `1 passed`(끝의 `unexpected PNG` exit 1은 무관). 한 번이라도 `regression`이 참이면 **한도를 더 넓히지 않는다** — 다섯 측정값을 보고하고 멈춘다.
Run: `cd apps/web && node --test e2e/support/release-gates.test.mjs` → `ℹ fail 0`(Step 0에서 기준선 파일을 읽게 고쳤으므로 새 값에서도 통과해야 한다).

- [ ] **Step 6: 커밋((나)일 때만)**

```bash
git add apps/web/e2e/support/workbench-performance-baseline.json
git commit -m "test(e2e): 편집기 도크 끌기 성능 기준선을 화면 변경 전에 다시 잰다

128ms 한도 근처를 오가던 게이트를 같은 절차(5회 독립 실행 x 5샘플)로
다시 쟀다. 20% 규칙은 그대로, 측정값과 끌기 경로 커밋 목록을 남긴다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
`test-results/recal-*`는 커밋하지 않는다(`apps/web/.gitignore`의 `test-results/`로 이미 빠진다).

---

### Task 1: 카드 대표 그림을 첫 장면에서 고른다 (G1 백엔드)

**Files:**
- Modify: `services/api/src/videobox_api/routers/projects.py:30-33`(모듈 함수 추가 자리), `:346-364`(썸네일 고르는 자리)
- Create: `tests/test_workspace_summary_scene_thumbnail.py`

**Interfaces:**
- Consumes: `store.get_latest_editing_session(project_id=...) -> dict`(세션: `segments[*].cut_action: "keep"|"remove"`, `segments[*].broll_override: {"asset_id": str, ...} | None`), `store.list_assets(project_id=...) -> list[dict]`(각 dict에 `asset_id`, `asset_type`, `metadata`).
- Produces: 모듈 함수 `_scene_thumbnail_url(project_id: str, session: Any, assets: list[dict[str, Any]]) -> str | None`. 응답 모양(`ProjectWorkspaceSummaryResponse.thumbnail_url: str | None`)은 그대로.

- [ ] **Step 1: 실패하는 시험을 쓴다**

`tests/test_workspace_summary_scene_thumbnail.py`:

```python
"""프로젝트 카드 대표 그림은 **첫 장면의 그림**이다 (2026-10-02 점검 후속 G1).

실측: 프로젝트 73개 중 64개가 카드 그림이 비어 있었다. 요약이 "그림 정보가
붙은 첫 자산"만 찾는데, 대부분의 프로젝트는 장면에 B-roll을 걸어 두고도 그
자산에 그림 정보(metadata)를 적어 두지 않았다. 그림 자체는 썸네일 주소가
원본에서 다시 그린다(`routers/assets.py`의 `get_asset_thumbnail`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app

ASSETS: list[dict[str, Any]] = [
    {"asset_id": "cover", "asset_type": "image", "metadata": {"thumbnail_uri": "local://projects/x/cover.jpg"}},
    {"asset_id": "scene-1", "asset_type": "broll_video", "metadata": {}},
    {"asset_id": "scene-2", "asset_type": "image", "metadata": {}},
    {"asset_id": "music", "asset_type": "bgm", "metadata": {}},
]


def _session(segments: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "session_id": "editing_session_001",
        "timeline_id": "script_draft:asset-1",
        "session_revision": 1,
        "updated_at": "2026-10-02T00:00:00+00:00",
        "segments": segments,
        "history": [],
    }


def _summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, session: dict[str, Any] | None) -> dict[str, Any]:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "장면 그림"}).json()["project_id"]
    store = app.state.store

    def latest(*, project_id: str) -> dict[str, Any]:
        if session is None:
            raise KeyError(f"Editing session not found for project: {project_id}")
        return session

    monkeypatch.setattr(store, "get_latest_editing_session", latest)
    monkeypatch.setattr(store, "list_assets", lambda *, project_id: ASSETS)
    response = client.get(f"/api/projects/{project_id}/workspace-summary")
    assert response.status_code == 200, response.text
    return {"project_id": project_id, **response.json()}


def test_card_picture_is_the_first_kept_scene_picture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _summary(tmp_path, monkeypatch, _session([
        {"segment_id": "s1", "cut_action": "keep", "broll_override": {"asset_id": "scene-1"}},
        {"segment_id": "s2", "cut_action": "keep", "broll_override": {"asset_id": "scene-2"}},
    ]))

    assert payload["thumbnail_url"] == f"/api/projects/{payload['project_id']}/assets/scene-1/thumbnail"


def test_card_picture_skips_a_removed_scene_and_a_scene_without_a_picture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _summary(tmp_path, monkeypatch, _session([
        {"segment_id": "s0", "cut_action": "remove", "broll_override": {"asset_id": "scene-1"}},
        {"segment_id": "s1", "cut_action": "keep", "broll_override": {"asset_id": "music"}},
        {"segment_id": "s2", "cut_action": "keep", "broll_override": None},
        {"segment_id": "s3", "cut_action": "keep", "broll_override": {"asset_id": "scene-2"}},
    ]))

    assert payload["thumbnail_url"] == f"/api/projects/{payload['project_id']}/assets/scene-2/thumbnail"


def test_card_picture_falls_back_to_the_asset_with_a_saved_picture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 장면에 그림이 하나도 없으면 예전 규칙(그림 정보가 붙은 첫 자산)을 그대로 쓴다.
    payload = _summary(tmp_path, monkeypatch, _session([
        {"segment_id": "s1", "cut_action": "keep", "broll_override": {"asset_id": "music"}},
    ]))

    assert payload["thumbnail_url"] == f"/api/projects/{payload['project_id']}/assets/cover/thumbnail"


def test_card_picture_without_any_editing_session_keeps_the_old_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _summary(tmp_path, monkeypatch, None)

    assert payload["thumbnail_url"] == f"/api/projects/{payload['project_id']}/assets/cover/thumbnail"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_workspace_summary_scene_thumbnail.py`
Expected: `2 failed, 2 passed`. 실패 둘은 `test_card_picture_is_the_first_kept_scene_picture`·`test_card_picture_skips_a_removed_scene_and_a_scene_without_a_picture`이고 메시지는 `AssertionError: assert '/api/projects/<id>/assets/cover/thumbnail' == '/api/projects/<id>/assets/scene-1/thumbnail'` 모양. 나머지 둘이 이미 통과하는 것은 정상이다(예전 규칙을 지키는 회귀 시험).

- [ ] **Step 3: 최소 구현**

`services/api/src/videobox_api/routers/projects.py` — `_LOGGER = logging.getLogger(__name__)` 줄과 `def build_projects_router(` 줄 사이에 함수를 넣는다:

```python
_LOGGER = logging.getLogger(__name__)

#: 카드에 그림으로 보일 수 있는 자산 종류. 썸네일 주소가 원본에서 다시 그릴 수
#: 있는 것과 같은 두 가지다(`routers/assets.py`의 `get_asset_thumbnail`).
_PICTURED_ASSET_TYPES = frozenset({"image", "broll_video"})


def _scene_thumbnail_url(project_id: str, session: Any, assets: list[dict[str, Any]]) -> str | None:
    """빼지 않은 장면 중 **처음으로 그림이 걸린 장면**의 그림 주소.

    카드 그림이 73개 중 64개가 비어 있었다(2026-10-02 실측). 장면마다 B-roll을
    걸어 둬도 그 자산에 그림 정보가 적혀 있지 않으면 아래의 옛 규칙이 못 찾는다.
    그림은 썸네일 주소가 원본에서 다시 그리므로 여기서는 고르기만 한다.
    """
    if not isinstance(session, dict):
        return None
    segments = session.get("segments")
    if not isinstance(segments, list):
        return None
    asset_types = {
        str(asset.get("asset_id")): str(asset.get("asset_type") or "")
        for asset in assets
        if isinstance(asset, dict)
    }
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        if str(segment.get("cut_action") or "keep") == "remove":
            continue
        override = segment.get("broll_override")
        asset_id = override.get("asset_id") if isinstance(override, dict) else None
        if not asset_id:
            continue
        if asset_types.get(str(asset_id)) not in _PICTURED_ASSET_TYPES:
            continue
        return f"/api/projects/{project_id}/assets/{asset_id}/thumbnail"
    return None


def build_projects_router(store: LocalProjectStore, user_asset_store: Any | None = None) -> APIRouter:
```

같은 파일 `get_workspace_summary` 안, 바꿀 자리(그대로 찾는다):

```python
        thumbnail_url: str | None = None
        try:
            assets = store.list_assets(project_id=project_id)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="workspace_summary_unavailable",
            ) from exc
        for asset in assets:
```

을 이렇게 바꾼다(그 아래 `for` 몸통은 그대로 둔다):

```python
        try:
            assets = store.list_assets(project_id=project_id)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="workspace_summary_unavailable",
            ) from exc
        # 첫 장면의 그림이 먼저다. 없을 때만 예전 규칙(그림 정보가 붙은 첫 자산)을 본다.
        thumbnail_url: str | None = _scene_thumbnail_url(project_id, session, assets)
        for asset in assets if thumbnail_url is None else []:
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_workspace_summary_scene_thumbnail.py`
Expected: `4 passed`

- [ ] **Step 5: 넓은 검증**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_api.py -k workspace_summary`
Expected: 10개 통과(기존 `test_workspace_summary_exposes_store_backed_thumbnail_url` 포함 — 이 시험은 세션이 없어 옛 규칙 갈래를 탄다).
Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_project_rename.py` → 11개 통과. (`-k`를 두 파일에 같이 걸면 이름 바꾸기 시험이 전부 빠진다 — 따로 돈다.)

배선: `grep -n "_scene_thumbnail_url" services/api/src/videobox_api/routers/projects.py` → 정의 1 + 호출 1 = 2줄.

- [ ] **Step 6: 커밋**

```bash
git add services/api/src/videobox_api/routers/projects.py tests/test_workspace_summary_scene_thumbnail.py
git commit -m "feat(projects): 카드 대표 그림을 첫 장면 그림에서 고른다

73개 중 64개 카드가 그림이 비어 있었다. 빼지 않은 장면 중 처음으로
그림 자산이 걸린 장면을 먼저 고르고, 없을 때만 예전 규칙을 쓴다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 카드 그림 자리를 모든 카드에 같은 크기로 (G1 화면)

**Files:**
- Modify: `apps/web/src/app/AppRouter.tsx:13`(lucide import), `:654-679`(카드 세 갈래의 그림 자리)
- Modify: `apps/web/src/styles/product-shell.css:42`(`.vb-catalog-card img` 규칙), `:58`(줄 보기 img 규칙)
- Create: `apps/web/src/app/catalog-thumbnail.test.tsx`

**Interfaces:**
- Consumes: `ProjectWorkspaceSummary.thumbnail_url: string | null`(`api.ts:116`).
- Produces: 카드 안 `<div className="vb-catalog-card__thumb" data-has-picture="true"|"false">` — 그림이 있으면 `<img alt="{이름} 대표 이미지">`, 없거나 못 불러오면 `<Film aria-hidden data-testid="catalog-card-thumb-placeholder">`.

- [ ] **Step 1: 실패하는 시험을 쓴다**

`apps/web/src/app/catalog-thumbnail.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryHistory } from "@tanstack/react-router";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { api } from "../api";
import { AppRouter, ProjectCatalog, createAppRouter } from "./AppRouter";

beforeEach(() => {
  vi.stubGlobal("scrollTo", vi.fn());
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, onchange: null, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false }));
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); window.localStorage.clear(); });

const projects = [
  { project_id: "with_picture", name: "그림 있는 영상", status: "active", root_storage_uri: "local://a" },
  { project_id: "no_picture", name: "그림 없는 영상", status: "active", root_storage_uri: "local://b" },
];

function summary(projectId: string, displayName: string, thumbnailUrl: string | null) {
  return {
    project_id: projectId, display_name: displayName, updated_at: "2026-10-02T00:00:00Z",
    current_stage: "edit" as const, state: "ready" as const, thumbnail_url: thumbnailUrl,
    finished_video_count: 0, next_action: { label: "계속 편집", href: `/projects/${projectId}/edit` },
  };
}

function renderCatalog() {
  vi.spyOn(api, "listProjects").mockResolvedValue(projects as never);
  vi.spyOn(api, "getProjectWorkspaceSummary").mockImplementation(async (projectId: string) => projectId === "with_picture"
    ? summary(projectId, "그림 있는 영상", "/api/projects/with_picture/assets/a1/thumbnail")
    : summary(projectId, "그림 없는 영상", null));
  const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects"] }));
  render(<AppRouter router={router} />);
}

/** 그림 있는 카드 339px, 없는 카드 195px가 한 줄에 섞여 줄 높이가 들쭉날쭉했다
 *  (2026-10-02, 1440×900 실측). 그림 자리는 늘 있고 크기가 같다. */
describe("프로젝트 카드 대표 그림", () => {
  it("그림이 없는 카드도 같은 그림 자리를 갖는다", async () => {
    renderCatalog();
    const withPicture = await screen.findByRole("article", { name: "그림 있는 영상 프로젝트" });
    const noPicture = await screen.findByRole("article", { name: "그림 없는 영상 프로젝트" });

    await waitFor(() => expect(within(withPicture).getByRole("img", { name: "그림 있는 영상 대표 이미지" })).toBeInTheDocument());
    await waitFor(() => expect(noPicture.querySelector(".vb-catalog-card__thumb")).not.toBeNull());
    expect(withPicture.querySelector(".vb-catalog-card__thumb img")).not.toBeNull();
    expect(noPicture.querySelector('[data-testid="catalog-card-thumb-placeholder"]')).not.toBeNull();
  });

  it("그림 파일을 못 불러오면 깨진 그림 대신 빈 그림 자리로 바뀐다", async () => {
    renderCatalog();
    const withPicture = await screen.findByRole("article", { name: "그림 있는 영상 프로젝트" });
    const image = await within(withPicture).findByRole("img", { name: "그림 있는 영상 대표 이미지" });

    fireEvent.error(image);

    await waitFor(() => expect(withPicture.querySelector('[data-testid="catalog-card-thumb-placeholder"]')).not.toBeNull());
    expect(withPicture.querySelector(".vb-catalog-card__thumb")).toHaveAttribute("data-has-picture", "false");
  });

  it("그림 자리는 16:9로 크기가 정해져 있다", () => {
    const css = readFileSync(resolve(process.cwd(), "src/styles/product-shell.css"), "utf8");
    expect(css).toMatch(/\.vb-catalog-card__thumb\s*\{[^}]*aspect-ratio:\s*16\s*\/\s*9/);
  });
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd apps/web && npx vitest run src/app/catalog-thumbnail.test.tsx`
Expected: 3 failed. 첫째·둘째는 `expected null not to be null`(`.vb-catalog-card__thumb`가 없다), 셋째는 `expected '…' to match /\.vb-catalog-card__thumb…/`.

- [ ] **Step 3: 최소 구현**

`apps/web/src/app/AppRouter.tsx` 13행:

```tsx
import { Archive, LayoutGrid, List, Mic, Scissors } from "lucide-react";
```
→
```tsx
import { Archive, Film, LayoutGrid, List, Mic, Scissors } from "lucide-react";
```

`ProjectCatalogCard` 안, 오류 갈래(그대로 찾는다):

```tsx
    return <article ref={cardRef} className="vb-catalog-card" aria-label={`${project.name} 프로젝트`}>
      <h2>{project.name}</h2>
      <p>상태 확인 필요</p>
```
→
```tsx
    return <article ref={cardRef} className="vb-catalog-card" aria-label={`${project.name} 프로젝트`}>
      <CatalogCardThumb />
      <h2>{project.name}</h2>
      <p>상태 확인 필요</p>
```

불러오는 중 갈래:

```tsx
    return <article ref={cardRef} className="vb-catalog-card" aria-label={`${project.name} 프로젝트`}>
      <h2>{project.name}</h2>
      <p>상태 확인 중</p>
```
→
```tsx
    return <article ref={cardRef} className="vb-catalog-card" aria-label={`${project.name} 프로젝트`}>
      <CatalogCardThumb />
      <h2>{project.name}</h2>
      <p>상태 확인 중</p>
```

준비된 갈래 — 이 블록을 통째로:

```tsx
    {summary.thumbnail_url && !thumbnailFailed
      ? <img
          src={summary.thumbnail_url}
          alt={`${summary.display_name} 대표 이미지`}
          loading="lazy"
          onError={() => setThumbnailFailed(true)}
        />
      // 자산 정리로 캐시 파일만 지워지고 metadata의 thumbnail_url은 남는
      // 경우가 있다(INVEST-04). 404면 깨진 이미지 아이콘 대신 그림 없는
      // 카드로 조용히 넘어간다 -- 백엔드 주석이 말하는 "그림 없으면 문구로
      // 대체" 의도.
      : null}
```
→
```tsx
    {/* 자산 정리로 그림 파일이 지워졌으면 404다. 깨진 그림 아이콘 대신 빈 그림
        자리로 조용히 넘어간다(INVEST-04). 자리는 늘 같은 크기라 카드 줄이
        들쭉날쭉하지 않는다(2026-10-02 실측: 339px / 195px). */}
    <CatalogCardThumb
      url={summary.thumbnail_url && !thumbnailFailed ? summary.thumbnail_url : null}
      alt={`${summary.display_name} 대표 이미지`}
      onError={() => setThumbnailFailed(true)}
    />
```

`function ProjectCatalogCard(` 바로 위에 새 함수를 넣는다:

```tsx
/** 카드 그림 자리. 그림이 없을 때도 같은 크기로 서 있다. */
function CatalogCardThumb({ url = null, alt = "", onError }: { url?: string | null; alt?: string; onError?: () => void }) {
  return <div className="vb-catalog-card__thumb" data-has-picture={url ? "true" : "false"}>
    {url
      ? <img src={url} alt={alt} loading="lazy" onError={onError} />
      : <Film aria-hidden="true" data-testid="catalog-card-thumb-placeholder" />}
  </div>;
}

```

`apps/web/src/styles/product-shell.css` 42행:

```css
.vb-catalog-card img { width:100%; height:9rem; object-fit:cover; border-radius: var(--vb-radius-md); background:color-mix(in srgb, var(--vb-text) 6%, transparent); }
```
→
```css
/* 그림 자리는 그림이 있든 없든 같은 16:9 칸이다(2026-10-02). 268px 카드면 228×128. */
.vb-catalog-card__thumb { display:grid; place-items:center; width:100%; aspect-ratio:16 / 9; overflow:hidden; border-radius: var(--vb-radius-md); background:color-mix(in srgb, var(--vb-text) 6%, transparent); color:var(--vb-muted); }
.vb-catalog-card__thumb img { width:100%; height:100%; object-fit:cover; }
.vb-catalog-card__thumb svg { width:2rem; height:2rem; opacity:.5; }
```

58행:

```css
.vb-catalog-grid--list .vb-catalog-card img { width:3.5rem; height:3.5rem; flex:0 0 auto; }
```
→
```css
.vb-catalog-grid--list .vb-catalog-card__thumb { width:3.5rem; height:3.5rem; aspect-ratio:auto; flex:0 0 auto; }
.vb-catalog-grid--list .vb-catalog-card__thumb svg { width:1.25rem; height:1.25rem; }
```

- [ ] **Step 4: 통과를 확인한다**

Run: `cd apps/web && npx vitest run src/app/catalog-thumbnail.test.tsx`
Expected: `3 passed`

- [ ] **Step 5: 넓은 검증**

Run: `cd apps/web && npx vitest run src/app/AppRouter.test.tsx src/app/catalog-card-quiet.test.tsx src/app/catalog-lazy-summary.test.tsx src/user-copy-policy.test.ts src/task22-parity-owners.test.ts`
Expected: 전부 통과.
Run: `cd apps/web && npx tsc --noEmit` → 오류 0.
배선: `grep -n "CatalogCardThumb" apps/web/src/app/AppRouter.tsx` → 정의 1 + 사용 3 = 4줄.

- [ ] **Step 6: 커밋**

```bash
git add apps/web/src/app/AppRouter.tsx apps/web/src/styles/product-shell.css apps/web/src/app/catalog-thumbnail.test.tsx
git commit -m "feat(projects): 카드마다 같은 크기의 그림 자리, 그림이 없으면 빈 칸

그림 있는 카드 339px, 없는 카드 195px가 섞여 줄이 들쭉날쭉했다.
16:9 그림 자리를 늘 두고, 못 불러오면 빈 칸으로 바꾼다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `+ 새로 만들기`를 카드 격자 첫 칸으로 (G4-a)

**Files:**
- Modify: `apps/web/src/app/AppRouter.tsx:13`(import에 `Plus`), `:386-393`(옛 막대), `:448-460`(격자)
- Modify: `apps/web/src/styles/product-shell.css:100-109`(막대 규칙), `:251`(특정도 덮어쓰기 규칙)
- Create: `apps/web/src/app/catalog-create-tile.test.tsx`

**Interfaces:**
- Consumes: 기존 `startBlankProject()`·`quickStartBusy`·`quickStartError`(`AppRouter.tsx:325-360`).
- Produces: `.vb-catalog-grid`의 **첫 자식**인 `<Button className="vb-catalog-create" aria-label="+ 새로 만들기">`. 접근 이름은 바쁠 때 `편집판을 여는 중`.

- [ ] **Step 1: 실패하는 시험을 쓴다**

`apps/web/src/app/catalog-create-tile.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryHistory } from "@tanstack/react-router";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { api } from "../api";
import { AppRouter, ProjectCatalog, createAppRouter } from "./AppRouter";

beforeEach(() => {
  vi.stubGlobal("scrollTo", vi.fn());
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, onchange: null, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false }));
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); window.localStorage.clear(); });

const project = { project_id: "project_a", name: "첫 영상", status: "active", root_storage_uri: "local://a" };

function renderCatalog(projects: typeof project[]) {
  vi.spyOn(api, "listProjects").mockResolvedValue(projects as never);
  vi.spyOn(api, "getProjectWorkspaceSummary").mockResolvedValue({
    project_id: "project_a", display_name: "첫 영상", updated_at: "2026-10-02T00:00:00Z", current_stage: "edit",
    state: "ready", thumbnail_url: null, finished_video_count: 0, next_action: { label: "계속 편집", href: "/projects/project_a/edit" },
  });
  const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects"] }));
  render(<AppRouter router={router} />);
}

/** owner 결정(2026-10-02): `+ 새로 만들기` 막대(1120×80px)를 카드 한 칸 크기로 줄인다.
 *  시작하는 문은 여전히 하나다(2026-09-05). */
describe("새로 만들기 칸", () => {
  it("카드 격자의 첫 칸이다", async () => {
    renderCatalog([project]);
    const tile = await screen.findByRole("button", { name: "+ 새로 만들기" });
    const grid = tile.closest(".vb-catalog-grid");

    expect(grid).not.toBeNull();
    expect(grid?.firstElementChild).toBe(tile);
    expect(screen.getAllByRole("button", { name: "+ 새로 만들기" })).toHaveLength(1);
  });

  it("프로젝트가 하나도 없어도 첫 칸에 있다", async () => {
    renderCatalog([]);
    const tile = await screen.findByRole("button", { name: "+ 새로 만들기" });

    expect(tile.closest(".vb-catalog-grid")).not.toBeNull();
  });

  it("찾는 이름이 없어도 만들기 칸은 남는다", async () => {
    renderCatalog([project]);
    await screen.findByRole("article", { name: "첫 영상 프로젝트" });

    fireEvent.change(screen.getByPlaceholderText("프로젝트 이름으로 찾기"), { target: { value: "없는 이름" } });

    expect(screen.getByText("\"없는 이름\"과 맞는 프로젝트가 없어요.")).toBeVisible();
    expect(screen.getByRole("button", { name: "+ 새로 만들기" }).closest(".vb-catalog-grid")).not.toBeNull();
  });

  it("가로로 꽉 찬 80px 막대 규칙이 남아 있지 않다", () => {
    const css = readFileSync(resolve(process.cwd(), "src/styles/product-shell.css"), "utf8");
    expect(css).not.toMatch(/\.vb-catalog-create[^{]*\{[^}]*min-height:\s*5rem/);
    expect(css).not.toMatch(/\.vb-catalog-quick-start/);
  });
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd apps/web && npx vitest run src/app/catalog-create-tile.test.tsx`
Expected: 4 failed — `expected null not to be null`(격자 밖에 있다), 셋째는 `.closest(...)`가 null, 넷째는 `min-height: 5rem`이 아직 있어서 `expected … not to match`.

- [ ] **Step 3: 최소 구현**

`AppRouter.tsx` 13행(Task 2 뒤 상태):

```tsx
import { Archive, Film, LayoutGrid, List, Mic, Scissors } from "lucide-react";
```
→
```tsx
import { Archive, Film, LayoutGrid, List, Mic, Plus, Scissors } from "lucide-react";
```

옛 막대를 지운다. 그대로 찾을 블록:

```tsx
      <div className="vb-catalog-quick-start">
        <Button
          type="button"
          className="vb-catalog-create"
          disabled={quickStartBusy !== null}
          onClick={() => void startBlankProject()}
        >{quickStartBusy ? "편집판을 여는 중" : "+ 새로 만들기"}</Button>
      </div>
      {quickStartError ? <p className="text-sm text-destructive" role="alert">{quickStartError}</p> : null}
```
→ (막대만 빼고 오류 문구는 남긴다. 위의 긴 `{/* **시작하는 문은 하나다** … */}` 주석은 그대로 둔다)
```tsx
      {/* 막대는 2026-10-02에 카드 격자의 첫 칸으로 옮겼다(owner 결정). 문은 여전히 하나다. */}
      {quickStartError ? <p className="text-sm text-destructive" role="alert">{quickStartError}</p> : null}
```

격자 블록:

```tsx
      {projectQuery.trim() && filteredProjects.length === 0 ? (
        <p className="vb-catalog-empty">"{projectQuery.trim()}"과 맞는 프로젝트가 없어요.</p>
      ) : (
      <div className={`vb-catalog-grid${viewMode === "list" ? " vb-catalog-grid--list" : ""}`}>
        {filteredProjects.map((project, index) => <ProjectCatalogCard
          index={index}
          key={project.project_id}
          project={project}
          onNavigateHref={(href) => void navigate({ href })}
          onRename={(id, name) => renameProjectAndRefresh(router, id, name)}
        />)}
      </div>
      )}
```
→
```tsx
      {projectQuery.trim() && filteredProjects.length === 0 ? (
        <p className="vb-catalog-empty">"{projectQuery.trim()}"과 맞는 프로젝트가 없어요.</p>
      ) : null}
      <div className={`vb-catalog-grid${viewMode === "list" ? " vb-catalog-grid--list" : ""}`}>
        {/* **시작하는 문은 카드 한 칸이다**(owner 결정 2026-10-02). 1120×80px 막대가
            카드 첫 줄을 아래로 밀고 있었다. 찾는 이름이 없어도 이 칸은 남는다 --
            "없네, 새로 만들자"가 바로 다음 행동이다. */}
        <Button
          type="button"
          className="vb-catalog-create"
          aria-label={quickStartBusy ? "편집판을 여는 중" : "+ 새로 만들기"}
          disabled={quickStartBusy !== null}
          onClick={() => void startBlankProject()}
        ><Plus aria-hidden="true" /><span>{quickStartBusy ? "편집판을 여는 중" : "새로 만들기"}</span></Button>
        {filteredProjects.map((project, index) => <ProjectCatalogCard
          index={index}
          key={project.project_id}
          project={project}
          onNavigateHref={(href) => void navigate({ href })}
          onRename={(id, name) => renameProjectAndRefresh(router, id, name)}
        />)}
      </div>
```

`product-shell.css` 100-109행 블록:

```css
.vb-catalog-create {
  margin-top: var(--vb-space-6);
  width: 100%;
  min-height: 5rem;
  font-size: var(--vb-text-lg);
  font-weight: 600;
  border-radius: var(--vb-radius-md);
}
.vb-catalog-quick-start { display:flex; flex-direction:column; }
```
→
```css
/* **2026-10-02부터 막대가 아니라 카드 한 칸이다**(owner 결정). 격자가 칸 높이를
   카드에 맞춰 늘린다(grid stretch). 위 주석의 캡컷 막대 이야기는 역사 기록이다. */
.vb-catalog-create { display:flex; flex-direction:column; align-items:center; justify-content:center; gap: var(--vb-space-2); width:100%; min-height:12rem; font-size: var(--vb-text-md); font-weight:600; white-space:normal; }
.vb-catalog-grid--list .vb-catalog-create { flex-direction:row; justify-content:flex-start; min-height:3.5rem; padding: var(--vb-space-3) var(--vb-space-4); }
@media (max-width: 767px) { .vb-catalog-create { flex-direction:row; min-height:4rem; } }
```

251행:

```css
.vb-product-shell [data-slot=button].vb-catalog-create { min-height:5rem; border-radius:var(--vb-radius-md); }
```
→
```css
/* 위 `min-height:32px; height:32px` 일반 규칙을 이기려면 같은 무게가 필요하다(2026-08-30 실측). */
.vb-product-shell [data-slot=button].vb-catalog-create { height:auto; min-height:12rem; border-radius:var(--vb-radius-lg); }
.vb-product-shell .vb-catalog-grid--list [data-slot=button].vb-catalog-create { min-height:3.5rem; }
@media (max-width: 767px) { .vb-product-shell [data-slot=button].vb-catalog-create { min-height:4rem; } }
.vb-catalog [data-slot=button].vb-catalog-create svg { width:2rem; height:2rem; }
.vb-catalog .vb-catalog-grid--list [data-slot=button].vb-catalog-create svg { width:1.25rem; height:1.25rem; }
```

- [ ] **Step 4: 통과를 확인한다**

Run: `cd apps/web && npx vitest run src/app/catalog-create-tile.test.tsx`
Expected: `4 passed`

- [ ] **Step 5: 넓은 검증**

Run: `cd apps/web && npx vitest run src/app/AppRouter.test.tsx src/app/catalog-thumbnail.test.tsx src/app/catalog-lazy-summary.test.tsx src/user-copy-policy.test.ts src/task22-parity-owners.test.ts`
Expected: 전부 통과. 특히 `AppRouter.test.tsx`의 "첫 화면에서 새로 시작하는 문은 하나다"·"이름을 묻지 않고 곧바로 편집기로 들어간다"가 초록이어야 한다(접근 이름이 그대로라서).
배선: `grep -rn "vb-catalog-quick-start" apps/web/src` → 0줄. `grep -n "startBlankProject()" apps/web/src/app/AppRouter.tsx` → 1줄(칸 단추).

- [ ] **Step 6: 커밋**

```bash
git add apps/web/src/app/AppRouter.tsx apps/web/src/styles/product-shell.css apps/web/src/app/catalog-create-tile.test.tsx
git commit -m "feat(projects): + 새로 만들기를 카드 격자 첫 칸으로 줄인다

1120×80px 막대가 카드 첫 줄을 밀고 있었다(owner 결정 2026-10-02).
시작하는 문은 그대로 하나, 찾는 이름이 없어도 칸은 남는다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 여러 개 골라 한 번에 보관, 방금 것만 되돌리기 (G2)

**Files:**
- Modify: `apps/web/src/app/AppRouter.tsx` — `ProjectsPage`(283-537), `ProjectCatalogCard`(607-726)
- Modify: `apps/web/src/styles/product-shell.css` — `.vb-catalog-archive-row` 규칙(80행 부근) 바로 아래에 추가
- Create: `apps/web/src/app/catalog-multi-archive.test.tsx`

**Interfaces:**
- Consumes: `api.archiveProject(projectId: string): Promise<Project>`, `api.restoreProject(projectId: string): Promise<Project>`(`api.ts:2416-2417`), `router.options.context.catalog.refresh()`, `router.invalidate()`, `archive.load()`.
- Produces: 목록 위 `여러 개 고르기`/`고르기 끝내기` 단추, `role="toolbar" aria-label="고른 프로젝트"` 막대, 카드마다 `aria-label="{이름} 고르기"`·`aria-pressed` 단추, 결과 `role="status"`(`N개를 보관했어요.` / `N개를 보관했어요. M개는 보관하지 못했어요. 다시 시도해 주세요.`)와 `되돌리기` 단추.

- [ ] **Step 1: 실패하는 시험을 쓴다**

`apps/web/src/app/catalog-multi-archive.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryHistory } from "@tanstack/react-router";

import { api } from "../api";
import { AppRouter, ProjectCatalog, createAppRouter } from "./AppRouter";

beforeEach(() => {
  vi.stubGlobal("scrollTo", vi.fn());
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, onchange: null, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false }));
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); window.localStorage.clear(); });

const all = [
  { project_id: "project_a", name: "첫 영상", status: "active", root_storage_uri: "local://a" },
  { project_id: "project_b", name: "둘째 영상", status: "active", root_storage_uri: "local://b" },
  { project_id: "project_c", name: "셋째 영상", status: "active", root_storage_uri: "local://c" },
];

/** 서버 흉내: 보관한 것은 활성 목록에서 빠지고, 되돌리면 돌아온다. */
function fakeServer({ failArchiveFor = [] as string[] } = {}) {
  const archived = new Set<string>();
  vi.spyOn(api, "listProjects").mockImplementation(async (includeArchived = false) =>
    all.filter((project) => includeArchived || !archived.has(project.project_id))
      .map((project) => ({ ...project, status: archived.has(project.project_id) ? "archived" : "active" })) as never);
  vi.spyOn(api, "getProjectWorkspaceSummary").mockImplementation(async (projectId: string) => ({
    project_id: projectId, display_name: all.find((project) => project.project_id === projectId)!.name,
    updated_at: "2026-10-02T00:00:00Z", current_stage: "edit", state: "ready", thumbnail_url: null,
    finished_video_count: 0, next_action: { label: "계속 편집", href: `/projects/${projectId}/edit` },
  }));
  const archiveProject = vi.spyOn(api, "archiveProject").mockImplementation(async (projectId: string) => {
    if (failArchiveFor.includes(projectId)) throw new Error("network down");
    archived.add(projectId);
    return { ...all.find((project) => project.project_id === projectId)!, status: "archived" } as never;
  });
  const restoreProject = vi.spyOn(api, "restoreProject").mockImplementation(async (projectId: string) => {
    archived.delete(projectId);
    return { ...all.find((project) => project.project_id === projectId)!, status: "active" } as never;
  });
  return { archiveProject, restoreProject };
}

function renderCatalog() {
  const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects"] }));
  render(<AppRouter router={router} />);
}

describe("여러 개 한 번에 보관", () => {
  it("고른 것만 한 번 확인한 뒤 보관하고, 방금 보관한 것을 되돌릴 수 있다", async () => {
    const { archiveProject, restoreProject } = fakeServer();
    renderCatalog();
    await screen.findByRole("article", { name: "셋째 영상 프로젝트" });

    fireEvent.click(screen.getByRole("button", { name: "여러 개 고르기" }));
    fireEvent.click(screen.getByRole("button", { name: "첫 영상 고르기" }));
    fireEvent.click(screen.getByRole("button", { name: "둘째 영상 고르기" }));
    const bar = screen.getByRole("toolbar", { name: "고른 프로젝트" });
    expect(within(bar).getByText("2개 골랐어요")).toBeVisible();

    fireEvent.click(within(bar).getByRole("button", { name: "보관하기" }));
    expect(archiveProject).not.toHaveBeenCalled();
    fireEvent.click(within(bar).getByRole("button", { name: "2개 보관 확인" }));

    await waitFor(() => expect(archiveProject).toHaveBeenCalledTimes(2));
    expect(archiveProject).toHaveBeenCalledWith("project_a");
    expect(archiveProject).toHaveBeenCalledWith("project_b");
    expect(await screen.findByText("2개를 보관했어요.")).toBeVisible();
    await waitFor(() => expect(screen.queryByRole("article", { name: "첫 영상 프로젝트" })).not.toBeInTheDocument());
    expect(screen.getByRole("article", { name: "셋째 영상 프로젝트" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "되돌리기" }));
    await waitFor(() => expect(restoreProject).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("article", { name: "첫 영상 프로젝트" })).toBeInTheDocument();
  });

  it("일부가 실패하면 몇 개가 안 됐는지 말하고, 성공한 것만 되돌린다", async () => {
    const { archiveProject, restoreProject } = fakeServer({ failArchiveFor: ["project_b"] });
    renderCatalog();
    await screen.findByRole("article", { name: "셋째 영상 프로젝트" });

    fireEvent.click(screen.getByRole("button", { name: "여러 개 고르기" }));
    fireEvent.click(screen.getByRole("button", { name: "첫 영상 고르기" }));
    fireEvent.click(screen.getByRole("button", { name: "둘째 영상 고르기" }));
    fireEvent.click(screen.getByRole("button", { name: "보관하기" }));
    fireEvent.click(screen.getByRole("button", { name: "2개 보관 확인" }));

    expect(await screen.findByText("1개를 보관했어요. 1개는 보관하지 못했어요. 다시 시도해 주세요.")).toBeVisible();
    expect(archiveProject).toHaveBeenCalledTimes(2);

    fireEvent.click(screen.getByRole("button", { name: "되돌리기" }));
    await waitFor(() => expect(restoreProject).toHaveBeenCalledTimes(1));
    expect(restoreProject).toHaveBeenCalledWith("project_a");
  });

  it("고르기를 끝내면 카드의 고르기 단추가 사라진다", async () => {
    fakeServer();
    renderCatalog();
    await screen.findByRole("article", { name: "첫 영상 프로젝트" });

    fireEvent.click(screen.getByRole("button", { name: "여러 개 고르기" }));
    expect(screen.getByRole("button", { name: "첫 영상 고르기" })).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(screen.getByRole("button", { name: "고르기 끝내기" }));

    expect(screen.queryByRole("button", { name: "첫 영상 고르기" })).toBeNull();
    expect(screen.queryByRole("toolbar", { name: "고른 프로젝트" })).toBeNull();
  });
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd apps/web && npx vitest run src/app/catalog-multi-archive.test.tsx`
Expected: 3 failed — `Unable to find an accessible element with the role "button" and name "여러 개 고르기"`.

- [ ] **Step 3: 최소 구현**

`AppRouter.tsx`의 `ProjectsPage` 안, 이 줄(그대로 찾는다):

```tsx
  async function deletePermanentlyAndReload(projectId: string) {
```
바로 **앞**에 넣는다:

```tsx
  // **여러 개를 한 번에 보관한다(owner 결정 2026-10-02).** 보관은 되돌릴 수 있어서
  // 확인은 한 번이고, 방금 보관한 것만 되돌리는 단추를 남긴다. 영구 삭제는 여기 없다 --
  // 그건 보관함 패널에서 하나씩, 두 번 확인한다.
  const [selecting, setSelecting] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [bulkConfirm, setBulkConfirm] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkResult, setBulkResult] = useState<{ archived: string[]; failed: number } | null>(null);
  const [bulkUndoFailed, setBulkUndoFailed] = useState(false);
  const startSelecting = () => { setSelecting(true); setSelectedIds([]); setBulkConfirm(false); setBulkResult(null); setBulkUndoFailed(false); };
  const stopSelecting = () => { setSelecting(false); setSelectedIds([]); setBulkConfirm(false); };
  const toggleSelected = (projectId: string) => {
    setBulkConfirm(false);
    setSelectedIds((current) => current.includes(projectId) ? current.filter((id) => id !== projectId) : [...current, projectId]);
  };
  async function reloadCatalogAfterBulk() {
    await router.options.context.catalog.refresh();
    await router.invalidate();
    if (archiveOpen) await archive.load();
  }
  async function archiveSelected() {
    setBulkBusy(true);
    const archived: string[] = [];
    let failed = 0;
    try {
      // 차례로 부른다. 동시에 부르면 같은 저장소에 쓰기가 겹친다.
      for (const projectId of selectedIds) {
        try {
          await api.archiveProject(projectId);
          archived.push(projectId);
        } catch {
          failed += 1;
        }
      }
      await reloadCatalogAfterBulk();
    } catch {
      // 목록 새로고침만 실패했다. 보관 결과는 그대로 말한다.
    } finally {
      setBulkResult({ archived, failed });
      setSelecting(false);
      setSelectedIds([]);
      setBulkConfirm(false);
      setBulkBusy(false);
    }
  }
  async function undoBulkArchive() {
    if (!bulkResult) return;
    setBulkBusy(true);
    let undoFailed = false;
    try {
      for (const projectId of bulkResult.archived) {
        try {
          await api.restoreProject(projectId);
        } catch {
          undoFailed = true;
        }
      }
      await reloadCatalogAfterBulk();
    } catch {
      undoFailed = true;
    } finally {
      setBulkResult(null);
      setBulkUndoFailed(undoFailed);
      setBulkBusy(false);
    }
  }
  const bulkMessage = bulkResult
    ? bulkResult.failed > 0
      ? `${bulkResult.archived.length}개를 보관했어요. ${bulkResult.failed}개는 보관하지 못했어요. 다시 시도해 주세요.`
      : `${bulkResult.archived.length}개를 보관했어요.`
    : null;
```

보기 전환 묶음 바로 뒤에 단추를 넣는다. 그대로 찾을 줄:

```tsx
              <Button type="button" size="icon" variant={viewMode === "list" ? "default" : "outline"} title="줄로 보기" aria-pressed={viewMode === "list"} onClick={() => chooseViewMode("list")}><List aria-hidden="true" /><span className="sr-only">줄로 보기</span></Button>
            </div>
```
→
```tsx
              <Button type="button" size="icon" variant={viewMode === "list" ? "default" : "outline"} title="줄로 보기" aria-pressed={viewMode === "list"} onClick={() => chooseViewMode("list")}><List aria-hidden="true" /><span className="sr-only">줄로 보기</span></Button>
            </div>
            <Button type="button" size="sm" variant={selecting ? "default" : "outline"} className="vb-catalog-select-toggle" aria-pressed={selecting} onClick={() => (selecting ? stopSelecting() : startSelecting())}>{selecting ? "고르기 끝내기" : "여러 개 고르기"}</Button>
```

검색 결과 없음 문구 앞(즉 Task 3 뒤의 `{projectQuery.trim() && filteredProjects.length === 0 ? (` 줄 바로 앞)에 넣는다:

```tsx
      {selecting ? <div className="vb-catalog-select-bar" role="toolbar" aria-label="고른 프로젝트">
        <span>{selectedIds.length}개 골랐어요</span>
        {bulkConfirm
          ? <Button type="button" variant="outline" disabled={bulkBusy || selectedIds.length === 0} onClick={() => void archiveSelected()}>{`${selectedIds.length}개 보관 확인`}</Button>
          : <Button type="button" variant="outline" disabled={selectedIds.length === 0} onClick={() => setBulkConfirm(true)}>보관하기</Button>}
      </div> : null}
      {bulkMessage ? <div className="vb-catalog-select-result" role="status">
        <span>{bulkMessage}</span>
        {bulkResult && bulkResult.archived.length > 0
          ? <Button type="button" size="sm" variant="outline" disabled={bulkBusy} onClick={() => void undoBulkArchive()}>되돌리기</Button>
          : null}
      </div> : null}
      {bulkUndoFailed ? <p className="vb-project-action-error" role="alert">되돌리지 못한 프로젝트가 있어요. 보관함에서 되돌려 주세요.</p> : null}
```

카드에 고르기 상태를 넘긴다. 그대로 찾을 블록:

```tsx
        {filteredProjects.map((project, index) => <ProjectCatalogCard
          index={index}
          key={project.project_id}
          project={project}
          onNavigateHref={(href) => void navigate({ href })}
          onRename={(id, name) => renameProjectAndRefresh(router, id, name)}
        />)}
```
→
```tsx
        {filteredProjects.map((project, index) => <ProjectCatalogCard
          index={index}
          key={project.project_id}
          project={project}
          onNavigateHref={(href) => void navigate({ href })}
          onRename={(id, name) => renameProjectAndRefresh(router, id, name)}
          selecting={selecting}
          selected={selectedIds.includes(project.project_id)}
          onToggleSelected={() => toggleSelected(project.project_id)}
        />)}
```

`ProjectCatalogCard` 시그니처:

```tsx
function ProjectCatalogCard({ project, index = 0, onNavigateHref, onRename }: { project: Project; index?: number; onNavigateHref?: (href: string) => void; onRename?: (projectId: string, name: string) => void | Promise<void> }) {
```
→
```tsx
function ProjectCatalogCard({ project, index = 0, onNavigateHref, onRename, selecting = false, selected = false, onToggleSelected }: { project: Project; index?: number; onNavigateHref?: (href: string) => void; onRename?: (projectId: string, name: string) => void | Promise<void>; selecting?: boolean; selected?: boolean; onToggleSelected?: () => void }) {
```

`if (summaryError) {` 줄 바로 **앞**에:

```tsx
  // 고르는 중일 때만 보인다. 카드 세 갈래(오류·불러오는 중·준비됨) 모두 같은 자리에 둔다.
  const selectToggle = selecting && onToggleSelected
    ? <Button type="button" size="sm" variant={selected ? "default" : "outline"} className="vb-catalog-card__select" aria-pressed={selected} aria-label={`${project.name} 고르기`} onClick={onToggleSelected}>{selected ? "골랐어요" : "고르기"}</Button>
    : null;
```

그리고 세 갈래 각각의 `<CatalogCardThumb` 바로 앞에 `{selectToggle}`를 넣는다(오류 갈래·불러오는 중 갈래의 `<CatalogCardThumb />` 앞, 준비된 갈래의 `<CatalogCardThumb` 주석 블록 앞).

`product-shell.css` — `.vb-catalog-archive-row { … }` 줄 바로 아래에:

```css
/* 여러 개 고르기(2026-10-02). 보관함 줄과 같은 모양을 쓴다 -- 새 모양을 만들지 않는다. */
.vb-catalog-select-bar, .vb-catalog-select-result { display:flex; flex-wrap:wrap; align-items:center; gap: var(--vb-space-3); margin-top: var(--vb-space-3); padding: var(--vb-space-2) var(--vb-space-3); border:1px solid var(--vb-border); border-radius: var(--vb-radius-md); background:var(--vb-panel); }
.vb-catalog-card__select { align-self:flex-start; }
```

- [ ] **Step 4: 통과를 확인한다**

Run: `cd apps/web && npx vitest run src/app/catalog-multi-archive.test.tsx`
Expected: `3 passed`

- [ ] **Step 5: 넓은 검증**

Run: `cd apps/web && npx vitest run src/app/AppRouter.test.tsx src/app/catalog-thumbnail.test.tsx src/app/catalog-create-tile.test.tsx src/app/catalog-lazy-summary.test.tsx src/user-copy-policy.test.ts src/task22-parity-owners.test.ts`
Expected: 전부 통과(기존 보관함 시험 6개 포함).
Run: `cd apps/web && npx tsc --noEmit` → 0.
배선: `grep -n "archiveSelected\|undoBulkArchive\|toggleSelected" apps/web/src/app/AppRouter.tsx` → 각각 정의 1 + 호출 ≥1.

- [ ] **Step 6: 커밋**

```bash
git add apps/web/src/app/AppRouter.tsx apps/web/src/styles/product-shell.css apps/web/src/app/catalog-multi-archive.test.tsx
git commit -m "feat(projects): 여러 개 골라 한 번에 보관, 방금 것만 되돌리기

보관은 한 번 확인 뒤 차례로 부르고, 일부 실패는 개수로 말한다.
영구 삭제는 넣지 않았다(보관함에서 하나씩).

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 검토 화면에서 편집본을 바로 재생한다 (G3)

**Files:**
- Modify: `apps/web/src/app/OutputsPage.tsx:46-66`(`OutputState`), `:330-352`(props), `:404-409`(상태), `:555-562`(`nextState`), `:575-600`(프로젝트 바뀔 때 초기화 effect), `:718-744`(재확인 effect), `:1402-1409`(`편집본 미리보기` 카드)
- Create: `apps/web/src/features/review/ReviewPreviewPlayer.tsx`
- Modify: `apps/web/src/features/review/ReviewAndOutputPage.tsx:20-37`
- Modify: `apps/web/src/app/AppRouter.tsx:834-842`(검토·출력 라우트)
- Modify: `apps/web/src/styles/product-shell.css:130`(`.vb-export-dialog .vb-outputs-grid` 줄 아래)
- Modify: `apps/web/src/features/editor/preview/preview-stage.tsx:240`(창 전체 스페이스 처리기 — 다른 영상 위의 스페이스는 넘긴다)
- Test: `apps/web/src/app/OutputsPage.test.tsx`(파일 끝에 추가), `apps/web/src/features/review/ReviewAndOutputPage.test.tsx`(파일 끝에 추가), `apps/web/src/features/editor/preview/preview-stage.test.tsx`(파일 끝에 추가)

> **스페이스는 한 화면에 한 재생기만 반응해야 한다(검토자 확인 2026-10-02).** `PreviewStage`는 `window`에 `keydown`을 걸어 **어디서 눌러도** 재생/정지한다(`preview-stage.tsx:236-253`). 검토 화면에는 이 재생기 말고도 완성본(`OutputsPage.tsx:1464`)·가로세로 출력(`VariantOutputCard.tsx:32`)의 기본 `<video controls>`가 있다. 그 영상에 포커스를 두고 스페이스를 누르면 지금 코드로는 이 재생기도 같이 움직이고 `preventDefault`로 그 영상의 기본 동작까지 막는다. 이 Task는 (1) 편집기 내보내기 창에서는 재생기를 켜지 않고(`showPlayer` 없음), (2) 다른 `<video>`/`<audio>` 위의 스페이스는 그 영상에 맡긴다.

**Interfaces:**
- Consumes: `EditorPlaybackManifest`(`api.ts:648-678`), `PreviewStage` props(`preview-stage.tsx:12-35`: `expectedRevision`, `exactPreview`, `captions`, `sources`, `onRefresh`, `fps`, `durationSec`, `projectIsEmpty`), `api.startExactPreview(projectId, sessionId, { expected_revision })`(`api.ts:2582`).
- Produces: `ReviewPreviewPlayer({ manifest: EditorPlaybackManifest; onRefresh: () => Promise<void> })`, `OutputsPage`·`ReviewAndOutputPage`의 새 prop `showPlayer?: boolean`(기본 false). **편집기 내보내기 창(`EditorWorkbench.tsx:853`)은 이 prop을 넘기지 않는다** — 편집기 안에 재생기가 둘 생기면 스페이스 키가 둘 다 건드린다.

- [ ] **Step 1: 실패하는 시험을 쓴다**

`apps/web/src/app/OutputsPage.test.tsx` 파일 **맨 끝**에 붙인다(같은 파일의 `stubCanonicalSubtitleApi`·`playbackManifest`를 쓴다):

```tsx
/** 검토 화면에 재생기가 없었다 -- `재생은 편집 화면에서 확인해 주세요.` 한 줄뿐이었다
 *  (2026-10-02 점검). 편집기의 재생기를 그대로 쓴다. 재생 정보는 이 화면이 이미
 *  읽고 있으므로 요청이 늘지 않는다. */
describe("검토 화면 재생기", () => {
  beforeEach(() => {
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
    vi.spyOn(api, "listOutputVariants").mockResolvedValue({ variants: [] } as never);
  });

  const withTracks = (manifest: ReturnType<typeof playbackManifest>) => ({
    ...manifest,
    tracks: [{ track_id: "broll", track_type: "broll", clips: [] }],
  });

  it("최신 미리보기가 있으면 이 화면에서 바로 재생한다", async () => {
    stubCanonicalSubtitleApi();
    vi.mocked(api.getEditorPlaybackManifest).mockResolvedValue(withTracks(playbackManifest()) as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} showPlayer />);

    const video = await screen.findByLabelText("편집본 미리보기");
    expect(video.tagName).toBe("VIDEO");
    expect(video).toHaveAttribute("src", "/api/projects/project_a/exact-previews/exact-a/content");
    expect(screen.queryByText("재생은 편집 화면에서 확인해 주세요.")).not.toBeInTheDocument();
    // 재생기는 이미 읽은 재생 정보를 쓴다. 재생기가 스스로 읽는 자리를 만들지 않는다 --
    // `ReviewPreviewPlayer.tsx`에 `api.` 호출이 없어야 한다(Step 5 배선 grep).
  });

  it("미리보기가 아직 없으면 지금 판수로 만들기를 요청하고 다시 읽는다", async () => {
    stubCanonicalSubtitleApi();
    vi.mocked(api.getEditorPlaybackManifest).mockResolvedValue(withTracks(playbackManifest({
      exactPreview: { status: "unavailable", url: null, source_session_id: "session-a", source_session_revision: 7 },
    })) as never);
    const startExactPreview = vi.spyOn(api, "startExactPreview").mockResolvedValue({
      status: "pending", generation_id: "g1", timeline_start_sec: 0, timeline_end_sec: 1, artifact_revision: 7, fingerprint: "f",
    } as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} showPlayer />);

    fireEvent.click(await screen.findByRole("button", { name: "미리보기 새로 만들기" }));

    await waitFor(() => expect(startExactPreview).toHaveBeenCalledWith("project_a", "session-a", { expected_revision: 7 }));
    await waitFor(() => expect(vi.mocked(api.getEditorPlaybackManifest).mock.calls.length).toBeGreaterThan(1));
  });

  it("재생기를 켜지 않으면 예전처럼 편집 화면으로 안내만 한다", async () => {
    stubCanonicalSubtitleApi();
    vi.mocked(api.getEditorPlaybackManifest).mockResolvedValue(withTracks(playbackManifest()) as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    expect(await screen.findByText("재생은 편집 화면에서 확인해 주세요.")).toBeVisible();
    expect(screen.queryByLabelText("편집본 미리보기")).not.toBeInTheDocument();
  });
});
```

`apps/web/src/features/review/ReviewAndOutputPage.test.tsx` 파일 **맨 끝**에 붙인다:

```tsx
it("검토 주소에서는 재생기를 켜고, 켜지 않은 곳(편집기 내보내기 창)에서는 그리지 않는다", async () => {
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  stubReadyReviewAndRunningFinal();
  vi.mocked(api.getEditorPlaybackManifest).mockResolvedValue({
    project_id: "project-a", session_id: "session-a", timeline_id: "timeline-a", session_revision: 4,
    timeline_version: "v4", timebase: "seconds", fps: { num: 30, den: 1 },
    output: { width: 1920, height: 1080, sample_aspect_ratio: "1:1", rotation: 0, duration_sec: 3 },
    tracks: [{ track_id: "broll", track_type: "broll", clips: [] }], captions: [], gap_slots: [],
    source_status: { status: "current", source_session_id: "session-a", source_session_revision: 4 },
    audition: { asset_urls: {} },
    exact_preview: { status: "succeeded", url: "/api/projects/project-a/exact-previews/e1/content", source_session_id: "session-a", source_session_revision: 4, artifact_revision: 4 },
  } as never);

  const { unmount } = render(<ReviewAndOutputPage projectId="project-a" onOpenEditor={() => {}} showPlayer />);
  expect(await screen.findByLabelText("편집본 미리보기")).toHaveAttribute("src", "/api/projects/project-a/exact-previews/e1/content");
  unmount();

  render(<ReviewAndOutputPage projectId="project-a" onOpenEditor={() => {}} />);
  await waitFor(() => expect(screen.getByTestId("outputs-page")).toBeInTheDocument());
  await waitFor(() => expect(screen.getByText("재생은 편집 화면에서 확인해 주세요.")).toBeVisible());
  expect(screen.queryByLabelText("편집본 미리보기")).not.toBeInTheDocument();
});
```

`apps/web/src/features/editor/preview/preview-stage.test.tsx` 파일 **맨 끝**에 붙인다(같은 파일 위쪽의 `current`를 쓴다):

```tsx
describe("한 화면에 재생기가 둘일 때 스페이스", () => {
  it("다른 영상에 포커스가 있으면 그 영상에 맡기고 이 재생기는 움직이지 않는다", () => {
    // 2026-10-02(G3): 검토 화면에는 이 재생기 말고도 완성본·가로세로 출력의 기본
    // `<video controls>`가 있다. 창 전체에서 스페이스를 듣는 이 재생기가 그 영상 위의
    // 스페이스까지 가로채면 한 번 눌러 두 재생기가 같이 반응한다.
    render(<PreviewStage {...current} />);
    const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    const play = vi.spyOn(media, "play").mockResolvedValue(undefined);
    Object.defineProperty(media, "paused", { configurable: true, value: true });
    const other = document.createElement("video");
    other.setAttribute("controls", "");
    other.tabIndex = 0;
    document.body.append(other);

    const notPrevented = fireEvent.keyDown(other, { key: " " });

    expect(play).not.toHaveBeenCalled();
    // `preventDefault`를 하지 않았다 -- 그 영상의 기본 재생/정지가 그대로 산다.
    expect(notPrevented).toBe(true);
    other.remove();
  });

  it("몸통(어느 컨트롤도 아닌 곳)에서 누른 스페이스는 여전히 이 재생기가 받는다", () => {
    render(<PreviewStage {...current} />);
    const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    const play = vi.spyOn(media, "play").mockResolvedValue(undefined);
    Object.defineProperty(media, "paused", { configurable: true, value: true });

    fireEvent.keyDown(document.body, { key: " " });

    expect(play).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd apps/web && npx vitest run src/features/editor/preview/preview-stage.test.tsx -t "재생기가 둘일 때"`
Expected: 첫째 FAIL `expected "spy" to not be called at all, but actually been called 1 times`. 둘째는 이미 통과(회귀 지킴이).

Run: `cd apps/web && npx vitest run src/app/OutputsPage.test.tsx -t "검토 화면 재생기"`
Expected: 첫째·둘째 실패 — `Unable to find a label with the text of: 편집본 미리보기` / `Unable to find an accessible element with the role "button" and name "미리보기 새로 만들기"`. 셋째는 이미 통과(회귀 지킴이). 그리고 `npx tsc --noEmit`에서 `Property 'showPlayer' does not exist`가 난다.
Run: `cd apps/web && npx vitest run src/features/review/ReviewAndOutputPage.test.tsx -t "검토 주소에서는"`
Expected: FAIL `Unable to find a label with the text of: 편집본 미리보기`.

- [ ] **Step 3: 최소 구현**

새 파일 `apps/web/src/features/review/ReviewPreviewPlayer.tsx`:

```tsx
import type { EditorPlaybackManifest } from "../../api";
import { PreviewStage } from "../editor/preview/preview-stage";

/** 검토 화면의 재생기. **편집기의 `PreviewStage`를 그대로 쓴다** -- 재생기를 하나 더
 *  만들면 재생·프레임 이동·전체화면·음소거가 두 벌이 된다(owner: "재생 조작이 복잡하다").
 *
 *  원본 미리 듣기(`sources`)는 넘기지 않는다. 검토는 편집 **결과**를 보는 자리다. */
export function ReviewPreviewPlayer({ manifest, onRefresh }: { manifest: EditorPlaybackManifest; onRefresh: () => Promise<void> }) {
  return <PreviewStage
    key={`${manifest.project_id}:${manifest.session_id}`}
    expectedRevision={manifest.session_revision}
    exactPreview={{
      status: manifest.exact_preview.status,
      url: manifest.exact_preview.url,
      artifactRevision: manifest.exact_preview.artifact_revision,
      timelineStartSec: manifest.exact_preview.timeline_start_sec,
      timelineEndSec: manifest.exact_preview.timeline_end_sec,
    }}
    captions={manifest.captions.map((caption) => ({ text: caption.text, startSec: caption.start_sec, endSec: caption.end_sec }))}
    sources={[]}
    onRefresh={onRefresh}
    fps={manifest.fps}
    durationSec={manifest.output.duration_sec}
    projectIsEmpty={manifest.tracks.length === 0}
  />;
}
```

`apps/web/src/features/editor/preview/preview-stage.tsx` — 창 전체 스페이스 처리기 안, 이 줄(그대로 찾는다, 파일에 한 번뿐):

```tsx
      if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
```
바로 **아래**에:
```tsx
      // **한 화면에 재생기가 둘이면 스페이스는 포커스를 가진 쪽 것이다(2026-10-02, G3).**
      // 검토 화면에는 이 재생기 밖에 완성본·가로세로 출력의 기본 `<video controls>`가
      // 있다. 그 영상 위에서 누른 스페이스를 여기서 가로채면 두 재생기가 같이 움직이고,
      // `preventDefault` 때문에 그 영상의 기본 재생/정지까지 막힌다.
      if (target?.closest("video, audio") && !stageRef.current?.contains(target)) return;
```
(`stageRef`는 같은 컴포넌트 65행에 이미 있다.)

`OutputsPage.tsx` — import 줄들(1-45행) 끝, `import { isArtifactCurrent, isMasterFinalRenderCurrent, selectMasterFinalJob, selectTimelineJob } from "../features/outputs/masterFinalRender";` 바로 아래에:

```tsx
import { ReviewPreviewPlayer } from "../features/review/ReviewPreviewPlayer";
```

`OutputState` 타입의 마지막 필드:

```tsx
  exactPreviewState: ExactPreviewState;
};
```
→
```tsx
  exactPreviewState: ExactPreviewState;
  /** 판정에만 쓰고 버리던 재생 정보. 검토 화면 재생기가 그대로 쓴다(요청을 늘리지 않는다). */
  playbackManifest: EditorPlaybackManifest | null;
};
```

props(`export function OutputsPage({ projectId, onOpenEditor, shared, onSharedRefresh, reviewInline = false }: {`):

```tsx
export function OutputsPage({ projectId, onOpenEditor, shared, onSharedRefresh, reviewInline = false }: {
```
→
```tsx
export function OutputsPage({ projectId, onOpenEditor, shared, onSharedRefresh, reviewInline = false, showPlayer = false }: {
```
그리고 같은 타입 블록의 `  reviewInline?: boolean;` 줄 바로 아래에:
```tsx
  /** 이 화면에서 편집본을 재생한다. 검토 주소(`/review`·`/output`)만 켠다 --
   *  편집기 내보내기 창에서 켜면 편집기 재생기와 둘이 되어 스페이스 키가 둘 다 건드린다. */
  showPlayer?: boolean;
```

상태(`const [resolvingVariantId, setResolvingVariantId] = useState<string | null>(null);` 바로 아래):

```tsx
  // 미리보기 만들기를 방금 요청했다. 서버가 아직 `unavailable`·`stale`로 답하는 사이에도
  // 계속 다시 읽어야 한다(편집기의 `autoPreviewWaiting`과 같은 이유).
  const [exactPreviewWaiting, setExactPreviewWaiting] = useState(false);
```

`nextState`의:

```tsx
        exactPreviewState: deriveExactPreviewState(refreshProjectId, session, playbackManifest, exactPreviewReadFailed),
      };
```
→
```tsx
        exactPreviewState: deriveExactPreviewState(refreshProjectId, session, playbackManifest, exactPreviewReadFailed),
        playbackManifest: exactPreviewReadFailed ? null : playbackManifest,
      };
```

프로젝트가 바뀔 때 초기화하는 effect 안(587-588행 부근, 이 두 줄 묶음은 파일에 한 번뿐이다):
```tsx
    capcutHandoffInFlightJobKey.current = null;
    setIsRenderingSubtitle(false);
```
→
```tsx
    capcutHandoffInFlightJobKey.current = null;
    setExactPreviewWaiting(false);
    setIsRenderingSubtitle(false);
```

재확인 effect — 그대로 찾을 줄:

```tsx
  const hasPendingFinal = currentState?.finalJobs.some((job) => job.status === "pending" || job.status === "running") === true;
```
바로 아래에:
```tsx
  const exactPreviewBusy = currentState?.exactPreviewState === "pending" || currentState?.exactPreviewState === "running"
    || (exactPreviewWaiting && (currentState?.exactPreviewState === "unavailable" || currentState?.exactPreviewState === "stale"));
  useEffect(() => {
    if (!exactPreviewWaiting) return;
    if (currentState?.exactPreviewState === "current" || currentState?.exactPreviewState === "failed") setExactPreviewWaiting(false);
  }, [exactPreviewWaiting, currentState?.exactPreviewState]);
```
그리고 그 아래 재확인 effect의:
```tsx
    if (!hasPendingFinal) return;
```
→
```tsx
    // 완성본을 만드는 동안 **또는** 미리보기를 만드는 동안 같은 간격으로 다시 읽는다 --
    // 세 번째 기다리는 방식을 만들지 않는다(owner 상시 지시 2026-09-12).
    if (!hasPendingFinal && !exactPreviewBusy) return;
```
와 의존성 배열:
```tsx
  }, [hasPendingFinal, finalPollTick, projectId, refresh]);
```
→
```tsx
  }, [hasPendingFinal, exactPreviewBusy, finalPollTick, projectId, refresh]);
```

카드(그대로 찾는다):

```tsx
      <Card>
        <CardHeader><CardTitle>편집본 미리보기</CardTitle><CardDescription>{exactPreviewDescription(currentState?.exactPreviewState)}</CardDescription></CardHeader>
        <CardContent>
          <p>재생은 편집 화면에서 확인해 주세요.</p>
          <Button onClick={onOpenEditor}>편집에서 미리보기 열기</Button>
        </CardContent>
      </Card>
```
→
```tsx
      <Card className={showPlayer && currentState?.playbackManifest ? "vb-outputs-preview" : undefined}>
        <CardHeader><CardTitle>편집본 미리보기</CardTitle><CardDescription>{exactPreviewDescription(currentState?.exactPreviewState)}</CardDescription></CardHeader>
        <CardContent>
          {showPlayer && currentState?.playbackManifest
            ? <ReviewPreviewPlayer
                manifest={currentState.playbackManifest}
                onRefresh={async () => {
                  const manifest = currentState.playbackManifest;
                  if (!manifest) return;
                  await api.startExactPreview(projectId, manifest.session_id, { expected_revision: manifest.session_revision });
                  setExactPreviewWaiting(true);
                  await refresh({ quiet: true });
                }}
              />
            : <p>재생은 편집 화면에서 확인해 주세요.</p>}
          <Button onClick={onOpenEditor}>편집에서 미리보기 열기</Button>
        </CardContent>
      </Card>
```

`ReviewAndOutputPage.tsx`:

```tsx
export function ReviewAndOutputPage({
  projectId,
  onOpenEditor,
  onOpenSegment,
}: {
  projectId: string;
  onOpenEditor: () => void;
  onOpenSegment?: (input: OpenSegmentInput) => void;
}) {
```
→
```tsx
export function ReviewAndOutputPage({
  projectId,
  onOpenEditor,
  onOpenSegment,
  showPlayer = false,
}: {
  projectId: string;
  onOpenEditor: () => void;
  onOpenSegment?: (input: OpenSegmentInput) => void;
  /** 검토 주소에서만 켠다. 편집기 내보내기 창은 편집기 재생기가 이미 있다. */
  showPlayer?: boolean;
}) {
```
와
```tsx
      <OutputsPage projectId={projectId} onOpenEditor={onOpenEditor} shared={data} onSharedRefresh={refresh} reviewInline />
```
→
```tsx
      <OutputsPage projectId={projectId} onOpenEditor={onOpenEditor} shared={data} onSharedRefresh={refresh} reviewInline showPlayer={showPlayer} />
```

`AppRouter.tsx`의 검토·출력 라우트:

```tsx
      <ReviewAndOutputPage
        projectId={projectId}
        onOpenEditor={() => goToStage(projectId, "edit")}
```
→
```tsx
      <ReviewAndOutputPage
        projectId={projectId}
        showPlayer
        onOpenEditor={() => goToStage(projectId, "edit")}
```

`product-shell.css` — `.vb-export-dialog .vb-outputs-grid { grid-template-columns:1fr; }` 줄 바로 아래에:

```css
/* 검토 화면 재생기(2026-10-02). 한 줄을 통째로 쓰고, 편집기용 높이(100%)를 풀어
   16:9 칸으로 세운다. 너무 커지지 않게 48rem에서 멈춘다. */
.vb-outputs-grid > .vb-outputs-preview { grid-column: 1 / -1; }
.vb-outputs-preview .vb-preview-stage { height:auto; max-width:48rem; }
.vb-outputs-preview .vb-preview-stage__media-shell { height:auto; aspect-ratio:16 / 9; }
.vb-outputs-preview .vb-preview-stage__media-shell video { width:100%; height:100%; object-fit:contain; }
```

- [ ] **Step 4: 통과를 확인한다**

Run: `cd apps/web && npx vitest run src/app/OutputsPage.test.tsx -t "검토 화면 재생기"` → `3 passed`
Run: `cd apps/web && npx vitest run src/features/review/ReviewAndOutputPage.test.tsx` → 전부 통과(새 시험 포함, 기존 "asks for the shared editing state once" 포함).
Run: `cd apps/web && npx vitest run src/features/editor/preview/preview-stage.test.tsx` → 전부 통과(새 둘 + 기존 스페이스 시험 다섯: "plays and pauses from the space bar anywhere"·"still plays when the space bar is pressed on a timeline clip" 등).

- [ ] **Step 5: 넓은 검증**

Run: `cd apps/web && npx vitest run src/app/OutputsPage.test.tsx src/features/review src/features/editor/preview src/user-copy-policy.test.ts src/task22-parity-owners.test.ts`
Expected: 전부 통과.
Run: `cd apps/web && npx tsc --noEmit` → 0.
배선: `grep -rn "showPlayer" apps/web/src --include=*.tsx | grep -v test` → `AppRouter.tsx`(켜는 자리 1), `ReviewAndOutputPage.tsx`(받기·넘기기), `OutputsPage.tsx`(받기·쓰기). `grep -n "api\." apps/web/src/features/review/ReviewPreviewPlayer.tsx` → 0줄(재생기가 따로 읽지 않는다). `grep -n "ReviewAndOutputPage" apps/web/src/features/editor/workbench/EditorWorkbench.tsx` → 그 자리에는 `showPlayer`가 **없어야** 한다. `grep -rn "<PreviewStage" apps/web/src --include=*.tsx | grep -v test` → `EditorWorkbench.tsx` 1 + `ReviewPreviewPlayer.tsx` 1 = 2줄(한 화면에 둘이 동시에 뜨는 자리는 없다: 편집기에는 편집기 것, 검토 주소에는 검토 것).

- [ ] **Step 6: 커밋**

```bash
git add apps/web/src/features/review/ReviewPreviewPlayer.tsx apps/web/src/features/editor/preview/preview-stage.tsx apps/web/src/features/editor/preview/preview-stage.test.tsx apps/web/src/app/OutputsPage.tsx apps/web/src/features/review/ReviewAndOutputPage.tsx apps/web/src/app/AppRouter.tsx apps/web/src/styles/product-shell.css apps/web/src/app/OutputsPage.test.tsx apps/web/src/features/review/ReviewAndOutputPage.test.tsx
git commit -m "feat(review): 검토 화면에서 편집본을 바로 재생한다

편집기 재생기(PreviewStage)를 그대로 쓰고, 이미 읽던 재생 정보를
보관해 넘긴다(요청 증가 없음). 미리보기 만들기는 기존 재확인 간격을 탄다.
편집기 내보내기 창에서는 켜지 않고, 다른 영상 위의 스페이스는
그 영상에 맡긴다(한 번에 한 재생기만 반응).

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 편집기 `편집 작업판` 머리 접기 + 접힌 `가로·세로 비교` 띠 낮추기 (G4-b)

> 정직하게 적는다: `가로·세로 비교` 띠는 **이미 접히고 프로젝트별로 기억된다**(`editorUiState.ts:113-135`, 기본 접힘). 이 Task가 더하는 것은 (1) 머리 접기와 그 기억, (2) 접힌 두 줄의 높이 줄이기다. 버튼 크기 32px(2026-09-04 owner 결정)는 건드리지 않고 **여백만** 줄인다. 예상 이득은 머리 58→≤44px, 띠 49→≤42px, 합쳐 약 20px을 미리보기 줄에 돌려준다. 크지 않다 — Task 17에서 실제로 잰 값을 보고한다.

**Files:**
- Modify: `apps/web/src/features/editor/workbench/editorUiState.ts:113-135`(바로 아래에 함수 둘 추가)
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbench.tsx:4`(lucide import), `:23`(editorUiState import), `:200`(상태), `:515`(토글), `:634`(머리), `:682-683`(머리 끝)
- Modify: `apps/web/src/styles/editor-workbench.css:11-12`(머리 규칙 아래), `:445`(접힌 띠 규칙)
- Create: `apps/web/src/features/editor/workbench/toolbar-collapse.test.tsx`

**Interfaces:**
- Produces: `readToolbarCollapsed(): boolean`, `writeToolbarCollapsed(collapsed: boolean): void`(키 `videobox.editor-workbench.toolbar-collapsed`, 프로젝트와 무관한 기기 설정), 머리의 `data-collapsed`, 단추 접근 이름 `도구줄 접기`/`도구줄 펼치기`(`aria-expanded`).

- [ ] **Step 1: 실패하는 시험을 쓴다**

`apps/web/src/features/editor/workbench/toolbar-collapse.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { EditorWorkbench } from "./EditorWorkbench";
import { readToolbarCollapsed, writeToolbarCollapsed } from "./editorUiState";

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ width: 1000 } as DOMRect);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 1920 });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); window.localStorage.clear(); });

const view = { projectId: "project-a", sessionId: "session-a", timelineId: "timeline-a", timelineVersion: "v1", expectedRevision: 1, timebase: "seconds", fps: { num: 30, den: 1 }, output: { width: 1080, height: 1920, sampleAspectRatio: "1:1", rotation: 0, durationSec: 1 }, tracks: [], captions: [], gaps: [], source: { status: "current" }, playback: { auditionUrls: {}, exactPreview: { status: "unavailable" } }, local: { selectedSegmentId: null, seekSec: 0 } } as const;

/** 편집 작업판 머리(58px)를 접어 미리보기 줄에 높이를 돌려준다(2026-10-02). */
describe("편집 작업판 머리 접기", () => {
  it("접으면 이름표를 숨기고 단추는 남기며, 다시 열어도 기억한다", () => {
    const { unmount } = render(<EditorWorkbench view={view} />);
    const toggle = screen.getByRole("button", { name: "도구줄 접기" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(toggle);

    const header = document.querySelector(".vb-editor-workbench__toolbar");
    expect(header).toHaveAttribute("data-collapsed", "true");
    expect(screen.getByRole("button", { name: "내보내기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "도구줄 펼치기" })).toHaveAttribute("aria-expanded", "false");
    unmount();

    render(<EditorWorkbench view={{ ...view, projectId: "project-b", sessionId: "session-b" }} />);
    expect(screen.getByRole("button", { name: "도구줄 펼치기" })).toBeInTheDocument();
  });

  it("브라우저 저장소가 막혀도 화면이 죽지 않고 이번에는 접힌다", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota exceeded"); });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(readToolbarCollapsed()).toBe(false);
    expect(() => writeToolbarCollapsed(true)).not.toThrow();

    render(<EditorWorkbench view={view} />);
    fireEvent.click(screen.getByRole("button", { name: "도구줄 접기" }));

    expect(document.querySelector(".vb-editor-workbench__toolbar")).toHaveAttribute("data-collapsed", "true");
  });

  it("접힌 머리와 접힌 가로·세로 띠는 위아래 여백이 4px이다", () => {
    const css = readFileSync(resolve(process.cwd(), "src/styles/editor-workbench.css"), "utf8");
    expect(css).toMatch(/\.vb-editor-workbench__toolbar\[data-collapsed="true"\]\s*\{[^}]*padding:\s*var\(--vb-space-1\)/);
    expect(css).toMatch(/\.vb-editor-variants\[data-collapsed="true"\]\s*\{[^}]*padding:\s*var\(--vb-space-1\)/);
  });
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd apps/web && npx vitest run src/features/editor/workbench/toolbar-collapse.test.tsx`
Expected: 모듈 오류 `does not provide an export named 'readToolbarCollapsed'`(또는 `readToolbarCollapsed is not a function`)로 3 failed.

- [ ] **Step 3: 최소 구현**

`editorUiState.ts` 파일 끝(`writeVariantsCollapsed` 함수 뒤)에:

```ts

// 편집 작업판 머리를 접었는지. 화면 크기에 대한 선호라 프로젝트마다가 아니라
// 이 기기에 하나만 둔다(2026-10-02).
const toolbarCollapsedStorageKey = "videobox.editor-workbench.toolbar-collapsed";

export function readToolbarCollapsed(): boolean {
  try {
    return window.localStorage.getItem(toolbarCollapsedStorageKey) === "true";
  } catch {
    return false;
  }
}

export function writeToolbarCollapsed(collapsed: boolean): void {
  try {
    window.localStorage.setItem(toolbarCollapsedStorageKey, String(collapsed));
  } catch {
    // UI persistence is best-effort and never editing-data authority.
  }
}
```

`EditorWorkbench.tsx` 4행:
```tsx
import { ChevronsLeftRight, Copy, PanelRight, Redo2, Scissors, Trash2, Undo2, Upload } from "lucide-react";
```
→
```tsx
import { ChevronDown, ChevronUp, ChevronsLeftRight, Copy, PanelRight, Redo2, Scissors, Trash2, Undo2, Upload } from "lucide-react";
```

23행:
```tsx
import { hasLegacyEditorUiState, readEditorUiState, readVariantsCollapsed, writeEditorUiState, writeVariantsCollapsed } from "./editorUiState";
```
→
```tsx
import { hasLegacyEditorUiState, readEditorUiState, readToolbarCollapsed, readVariantsCollapsed, writeEditorUiState, writeToolbarCollapsed, writeVariantsCollapsed } from "./editorUiState";
```

200행 다음:
```tsx
  const [variantsCollapsed, setVariantsCollapsed] = useState(() => readVariantsCollapsed(view.projectId));
```
→
```tsx
  const [variantsCollapsed, setVariantsCollapsed] = useState(() => readVariantsCollapsed(view.projectId));
  const [toolbarCollapsed, setToolbarCollapsed] = useState(readToolbarCollapsed);
```

515행:
```tsx
  const toggleVariantsCollapsed = () => setVariantsCollapsed((current) => { const next = !current; writeVariantsCollapsed(view.projectId, next); return next; });
```
→
```tsx
  const toggleVariantsCollapsed = () => setVariantsCollapsed((current) => { const next = !current; writeVariantsCollapsed(view.projectId, next); return next; });
  const toggleToolbarCollapsed = () => setToolbarCollapsed((current) => { const next = !current; writeToolbarCollapsed(next); return next; });
```

634행:
```tsx
    <header className="vb-editor-workbench__toolbar"><strong>편집 작업판</strong><div>
```
→
```tsx
    <header className="vb-editor-workbench__toolbar" data-collapsed={toolbarCollapsed}><strong className={toolbarCollapsed ? "sr-only" : undefined}>편집 작업판</strong><div>
```

682-683행(머리 끝):
```tsx
      <Button type="button" variant="outline" size="icon" title="내보내기 — 완성본 만들기" onClick={() => setExportOpen(true)}><Upload aria-hidden="true" /><span className="sr-only">내보내기</span></Button>
    </div></header>
```
→
```tsx
      <Button type="button" variant="outline" size="icon" title="내보내기 — 완성본 만들기" onClick={() => setExportOpen(true)}><Upload aria-hidden="true" /><span className="sr-only">내보내기</span></Button>
      {/* 머리를 접으면 이름표만 숨고 단추는 그대로다(2026-10-02). 58px 머리가
          미리보기 줄 높이를 먹고 있었다. 단추 크기(32px)는 owner 결정이라 안 줄인다. */}
      <Button type="button" variant="outline" size="icon" title={toolbarCollapsed ? "도구줄 펼치기" : "도구줄 접기"} aria-expanded={!toolbarCollapsed} onClick={toggleToolbarCollapsed}>{toolbarCollapsed ? <ChevronDown aria-hidden="true" /> : <ChevronUp aria-hidden="true" />}<span className="sr-only">{toolbarCollapsed ? "도구줄 펼치기" : "도구줄 접기"}</span></Button>
    </div></header>
```

`editor-workbench.css` 12행(`.vb-editor-workbench__toolbar div { display: flex; gap: var(--vb-space-2); }`) 바로 아래에:

```css
/* 접힌 머리(2026-10-02): 위아래 여백만 줄이고 단추는 오른쪽에 둔다. */
.vb-editor-workbench__toolbar[data-collapsed="true"] { padding: var(--vb-space-1) var(--vb-space-3); justify-content: flex-end; }
```

445행:
```css
.vb-editor-variants[data-collapsed="true"] { max-height: none; padding: var(--vb-space-2) var(--vb-space-5); }
```
→
```css
.vb-editor-variants[data-collapsed="true"] { max-height: none; padding: var(--vb-space-1) var(--vb-space-4); }
.vb-editor-variants[data-collapsed="true"] .vb-editor-variants__header h2 { margin: 0; }
```

- [ ] **Step 4: 통과를 확인한다**

Run: `cd apps/web && npx vitest run src/features/editor/workbench/toolbar-collapse.test.tsx` → `3 passed`

- [ ] **Step 5: 넓은 검증**

Run: `cd apps/web && npx vitest run src/features/editor/workbench/editor-workbench.test.tsx src/features/editor/workbench/editor-workbench-containment.test.tsx src/styles src/user-copy-policy.test.ts src/task22-parity-owners.test.ts`
Expected: 이미 알려진 실패 1건("gives the material dock back the same way, without needing a second click") 외 전부 통과.
Run: `cd apps/web && npx tsc --noEmit` → 0.
배선: `grep -n "toggleToolbarCollapsed\|readToolbarCollapsed\|writeToolbarCollapsed" apps/web/src/features/editor/workbench/EditorWorkbench.tsx` → 정의·사용 각각 ≥1.

- [ ] **Step 6: 커밋**

```bash
git add apps/web/src/features/editor/workbench/editorUiState.ts apps/web/src/features/editor/workbench/EditorWorkbench.tsx apps/web/src/styles/editor-workbench.css apps/web/src/features/editor/workbench/toolbar-collapse.test.tsx
git commit -m "feat(editor): 편집 작업판 머리 접기, 접힌 줄 여백 줄이기

머리(58px)를 접으면 이름표만 숨고 단추는 남는다. 접기는 이 기기에
기억하고, 저장소가 막혀도 이번에는 동작한다. 단추 크기는 그대로다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 설정 5칸 → 3칸(화면 · 유진 대화 · 정보) (G4-c)

> **출발 상태(검토자 확인, main `ca39f2a7f`):** 빈 `일반` 칸은 2026-10-01에 이미 없앴다. 지금 칸은 5개(`화면`·`AI·개인정보`·`내 목소리`·`출력`·`유진 대화`, `ProductShell.tsx:215`)이고, `/settings/general`은 `shown = "appearance"`로 **화면 칸**을 그린다(`ProductShell.tsx:214`). 이 Task는 그 매핑을 그대로 두고(`section === "general" || section === "appearance"` → 화면) 셋을 `정보`로 합친다. `e2e/product-shell.spec.mjs:123`(`/settings/general` → `화면` 단추 → `/settings/appearance`)과 `e2e/voice-tts-settings.spec.mjs:331`(`/settings/voice` → `내레이션 열기` 링크)은 바뀐 화면에서도 그대로 통과해야 한다 — Task 15에서 돈다.

**Files:**
- Modify: `apps/web/src/app/ProductShell.tsx:33`(`SettingsSection`), `:212-219`(`SettingsPage` 칸·내용)
- Modify: `apps/web/src/app/AppRouter.tsx` — `SettingsRoutePage`의 `validSections`(957행 부근)
- Modify: `docs/oss/editor-ui-source-map.json:102`, `:110`(`normalized_sha256` 두 곳)
- Modify: `apps/web/src/app/ProductShell.test.tsx:256-265`(기존 시험 하나 바꿈), `apps/web/src/app/AppRouter.test.tsx:1251`(제목 기대값)
- Create: `apps/web/src/app/settings-three-tabs.test.tsx`

**Interfaces:**
- Produces: `SettingsSection`에 `"about"` 추가. 새 주소 `/settings/about`. 칸 단추는 정확히 `화면`·`유진 대화`·`정보`. 옛 주소: `general`→화면, `ai-privacy`·`voice`·`output`→정보(복구 화면이 아니라 정보 칸을 그린다).

- [ ] **Step 1: 실패하는 시험을 쓴다**

`apps/web/src/app/settings-three-tabs.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { createMemoryHistory } from "@tanstack/react-router";

import { api } from "../api";
import { AppRouter, ProjectCatalog, createAppRouter } from "./AppRouter";
import { SettingsPage } from "./ProductShell";

beforeEach(() => {
  vi.stubGlobal("scrollTo", vi.fn());
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, onchange: null, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false }));
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); window.localStorage.clear(); });

/** 설정 다섯 칸 중 셋(AI·개인정보, 내 목소리, 출력)이 문장 한 줄짜리였다(2026-10-02 점검).
 *  `정보` 한 칸으로 모은다. 옛 주소는 막다른 곳이 되면 안 된다. */
describe("설정 세 칸", () => {
  it("칸 단추는 화면 · 유진 대화 · 정보 셋뿐이다", () => {
    render(<SettingsPage section="about" onNavigate={vi.fn()} projectId="project-a" />);
    const nav = screen.getByTestId("settings-page").querySelector(".vb-settings-nav") as HTMLElement;

    expect(within(nav).getAllByRole("button").map((button) => button.textContent)).toEqual(["화면", "유진 대화", "정보"]);
  });

  it("옛 /settings/general 주소는 계속 화면 칸을 그린다(빈 `일반` 칸은 2026-10-01에 이미 없앴다)", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([{ project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" }]);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/settings/general"] }));
    render(<AppRouter router={router} />);

    expect(await screen.findByRole("heading", { level: 1, name: "화면" })).toBeVisible();
    expect(screen.getByRole("button", { name: /조밀한 화면/ })).toBeInTheDocument();
    expect(screen.queryByTestId("project-recovery")).not.toBeInTheDocument();
  });

  it.each(["ai-privacy", "voice", "output", "about"] as const)("%s 주소는 정보 칸에 사실 셋을 함께 보여 준다", (section) => {
    render(<SettingsPage section={section} onNavigate={vi.fn()} projectId="project-a" />);

    expect(screen.getByRole("heading", { level: 1, name: "정보" })).toBeVisible();
    expect(screen.getByText("모든 처리는 이 기기 안에서만 해요.")).toBeVisible();
    expect(screen.getByText("완성본은 MP4(H.264)로 만들어요.")).toBeVisible();
    expect(screen.getByRole("link", { name: "내레이션 열기" })).toHaveAttribute("href", "/projects/project-a/editor");
  });

  it("정보 칸 단추는 새 주소로 보낸다", () => {
    const onNavigate = vi.fn();
    render(<SettingsPage section="appearance" onNavigate={onNavigate} projectId="project-a" />);

    fireEvent.click(screen.getByRole("button", { name: "정보" }));

    expect(onNavigate).toHaveBeenCalledWith("about");
  });

  it("/settings/about 주소가 복구 화면이 아니라 정보 칸을 연다", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([{ project_id: "project_a", name: "A", status: "active", root_storage_uri: "local://a" }]);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/settings/about"] }));
    render(<AppRouter router={router} />);

    expect(await screen.findByRole("heading", { level: 1, name: "정보" })).toBeVisible();
    expect(screen.queryByTestId("project-recovery")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd apps/web && npx vitest run src/app/settings-three-tabs.test.tsx`
Expected: 실패 — 첫째 `expected [ '화면', 'AI·개인정보', '내 목소리', '출력', '유진 대화' ] to deeply equal [ '화면', '유진 대화', '정보' ]`, 둘째 묶음은 `Unable to find an accessible element with the role "heading" and name "정보"`, `/settings/about` 시험은 복구 화면이 떠서 실패. `/settings/general` 시험은 **이미 통과**한다(2026-10-01에 빈 `일반` 칸을 없애고 `general`→`화면`으로 그리게 해 둔 상태를 지키는 회귀 시험). (`section="about"`은 타입 오류지만 vitest는 타입을 안 본다.)

- [ ] **Step 3: 최소 구현**

`ProductShell.tsx` 33행:
```tsx
type SettingsSection = "general" | "appearance" | "ai-privacy" | "voice" | "output" | "conversations";
```
→
```tsx
type SettingsSection = "general" | "appearance" | "ai-privacy" | "voice" | "output" | "conversations" | "about";
```

`SettingsPage` 안, 두 줄(그대로 찾는다):
```tsx
  const shown: Exclude<SettingsSection, "general"> = section === "general" ? "appearance" : section;
  const labels: Record<Exclude<SettingsSection, "general">, string> = { appearance: "화면", "ai-privacy": "AI·개인정보", voice: "내 목소리", output: "출력", conversations: "유진 대화" };
```
→
```tsx
  // **칸은 셋이다(2026-10-02 결정): 화면 · 유진 대화 · 정보.** AI·개인정보, 내 목소리,
  // 출력 세 칸은 문장 한 줄씩이었다 -- `정보` 한 칸에 모은다. 옛 주소는 지우지 않고
  // 맞는 칸을 보여 준다(즐겨찾기·지난 문서로 오는 길이 막다른 곳이 되면 안 된다).
  const shown: "appearance" | "conversations" | "about" = section === "general" || section === "appearance"
    ? "appearance"
    : section === "conversations" ? "conversations" : "about";
  const labels: Record<"appearance" | "conversations" | "about", string> = { appearance: "화면", conversations: "유진 대화", about: "정보" };
```

같은 함수의 칸 단추 부분:
```tsx
{(Object.keys(labels) as Exclude<SettingsSection, "general">[]).map((key) =>
```
→
```tsx
{(Object.keys(labels) as ("appearance" | "conversations" | "about")[]).map((key) =>
```

내용 부분(219행, 그대로 찾는다):
```tsx
      {shown === "ai-privacy" && <div className="vb-setting-control"><span>모든 처리는 이 기기 안에서만 해요.</span></div>}{shown === "voice" && <div className="vb-setting-control"><span>내 목소리 등록과 내레이션 만들기는 편집기의 오디오 탭에서 해요.</span><a className="vb-action-link" href={resolveProjectStage(projectId, "edit")}>내레이션 열기</a></div>}{shown === "output" && <div className="vb-setting-control"><span>완성본은 MP4(H.264)로 만들어요.</span></div>}{shown === "conversations" && <ConversationCleanup key={projectId} projectId={projectId} />}</section>;
```
→
```tsx
      {shown === "about" && <><div className="vb-setting-control"><span>모든 처리는 이 기기 안에서만 해요.</span></div><div className="vb-setting-control"><span>내 목소리 등록과 내레이션 만들기는 편집기의 오디오 탭에서 해요.</span><a className="vb-action-link" href={resolveProjectStage(projectId, "edit")}>내레이션 열기</a></div><div className="vb-setting-control"><span>완성본은 MP4(H.264)로 만들어요.</span></div></>}{shown === "conversations" && <ConversationCleanup key={projectId} projectId={projectId} />}</section>;
```

`AppRouter.tsx`의 `SettingsRoutePage`:
```tsx
  const validSections = ["general", "appearance", "ai-privacy", "voice", "output", "conversations"] as const;
```
→
```tsx
  const validSections = ["general", "appearance", "ai-privacy", "voice", "output", "conversations", "about"] as const;
```

기존 시험 둘을 새 결정에 맞춘다.

`ProductShell.test.tsx`의 이 시험 전체(256-265행):
```tsx
  it("keeps AI privacy separate and opens the canonical voice settings owner", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/settings/ai-privacy"] }));
    render(<AppRouter router={router} />);

    expect(await screen.findByText("모든 처리는 이 기기 안에서만 해요.")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "내 목소리 준비 상태" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "내 목소리" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/settings/voice"));
  });
```
→
```tsx
  // 2026-10-02: AI·개인정보·내 목소리·출력 칸을 `정보` 한 칸으로 합쳤다. 옛 주소는
  // 정보 칸을 그리고, 목소리 일은 여전히 편집기의 오디오 탭으로 안내한다.
  it("opens the merged 정보 tab from the old AI privacy address and keeps voice work in the editor", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue(projects);
    const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/settings/ai-privacy"] }));
    render(<AppRouter router={router} />);

    expect(await screen.findByText("모든 처리는 이 기기 안에서만 해요.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "내레이션 열기" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "내 목소리 준비 상태" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "화면" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/settings/appearance"));
  });
```

`AppRouter.test.tsx` 1251행:
```tsx
    expect(await screen.findByRole("heading", { name: "내 목소리" })).toBeVisible();
```
→
```tsx
    expect(await screen.findByRole("heading", { name: "정보" })).toBeVisible();
```

ProductShell 해시를 다시 박는다. 새 해시를 구한다:
Run: `.venv/Scripts/python.exe -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('apps/web/src/app/ProductShell.tsx').read_bytes()).hexdigest())"`
`docs/oss/editor-ui-source-map.json`에서 `"path": "apps/web/src/app/ProductShell.tsx"` 아래 `normalized_sha256` **두 곳**의 옛 값(`2e3d5e46c85cd15f32d629e77601b43b0fdc56ca90eef1b423b959fbcbe85e36`, 다른 묶음이 먼저 바꿨으면 그 값)을 위에서 나온 새 값으로 바꾼다.

- [ ] **Step 4: 통과를 확인한다**

Run: `cd apps/web && npx vitest run src/app/settings-three-tabs.test.tsx` → 전부 통과(8 passed — `it.each` 4개 포함).

- [ ] **Step 5: 넓은 검증**

Run: `cd apps/web && npx vitest run src/app/ProductShell.test.tsx src/app/AppRouter.test.tsx src/app/routeManifest.test.ts src/app/product-shell-side-nav.test.tsx src/user-copy-policy.test.ts src/task22-parity-owners.test.ts` → 전부 통과.
Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_editor_ui_source_provenance.py tests/test_guard_router_table.py` → 전부 통과.
Run: `cd apps/web && npx tsc --noEmit` → 0.
배선: `grep -rn "settings/about\|\"about\"" apps/web/src/app --include=*.tsx | grep -v test` → `ProductShell.tsx`(타입·칸), `AppRouter.tsx`(validSections).

- [ ] **Step 6: 커밋**

```bash
git add apps/web/src/app/ProductShell.tsx apps/web/src/app/AppRouter.tsx docs/oss/editor-ui-source-map.json apps/web/src/app/ProductShell.test.tsx apps/web/src/app/AppRouter.test.tsx apps/web/src/app/settings-three-tabs.test.tsx
git commit -m "feat(settings): 설정 다섯 칸을 화면 · 유진 대화 · 정보 셋으로

한 줄짜리 세 칸(AI·개인정보, 내 목소리, 출력)을 정보 한 칸에 모았다.
옛 주소는 정보 칸을 그린다. ProductShell 해시 두 곳 갱신.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: `이 답을 대본으로 쓰기`는 대본을 청한 답에만 (G5-a)

**Files:**
- Create: `apps/web/src/features/editor/workbench/scriptReply.ts`, `apps/web/src/features/editor/workbench/scriptReply.test.ts`
- Modify: `apps/web/src/features/editor/workbench/YujinPanel.tsx:26-30`(옛 `looksLikeScript`), `:354-358`(답 아래 단추)
- Modify: `apps/web/src/features/editor/workbench/YujinPanel.test.tsx:375-390`(두 답 구분 시험의 대화에 요청 줄 추가)

**Interfaces:**
- Produces: `looksLikeScript(text: string): boolean`(30자 이상), `isScriptReply(messages: readonly RightDockMessage[], index: number): boolean` — 유진의 답이고 30자 이상이며 **바로 앞 "나"의 말**에 `대본·스크립트·원고·내레이션·나레이션·멘트·대사` 중 하나가 있을 때만 참.

- [ ] **Step 1: 실패하는 시험을 쓴다**

`apps/web/src/features/editor/workbench/scriptReply.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { isScriptReply, looksLikeScript } from "./scriptReply";

const long = "안녕하세요. 오늘은 제주 바다를 소개합니다. 두 번째 문장입니다.";

/** 길기만 하면 모든 답 아래에 단추가 붙었다(2026-10-01 점검). 대본을 청한 답에만 붙인다. */
describe("isScriptReply", () => {
  it("대본을 청한 바로 다음 답이면 참", () => {
    expect(isScriptReply([
      { id: "u1", role: "user", text: "60초 대본 하나 써 줘" },
      { id: "a1", role: "assistant", text: long },
    ], 1)).toBe(true);
  });

  it("다른 것을 물은 긴 답이면 거짓", () => {
    expect(isScriptReply([
      { id: "u1", role: "user", text: "B-roll 추천해 줘" },
      { id: "a1", role: "assistant", text: long },
    ], 1)).toBe(false);
  });

  it("앞에 내 말이 아예 없으면 거짓", () => {
    expect(isScriptReply([{ id: "a1", role: "assistant", text: long }], 0)).toBe(false);
  });

  it("짧은 답이나 내 말 자체는 거짓", () => {
    const messages = [
      { id: "u1", role: "user" as const, text: "내레이션 원고 부탁해" },
      { id: "a1", role: "assistant" as const, text: "네, 알겠습니다." },
    ];
    expect(isScriptReply(messages, 1)).toBe(false);
    expect(isScriptReply(messages, 0)).toBe(false);
  });

  it("길이 기준은 30자다", () => {
    expect(looksLikeScript("가".repeat(29))).toBe(false);
    expect(looksLikeScript("가".repeat(30))).toBe(true);
  });
});
```

`apps/web/src/features/editor/workbench/YujinPanel.test.tsx` — 기존 시험 `"does not offer the script button for a short question"` 바로 앞에 새 시험을 넣는다:

```tsx
  it("does not offer the script button under a long answer to a non-script request", () => {
    // 2026-10-01 점검: B-roll 추천 설명처럼 대본이 아닌 긴 답 아래에도 단추가 떴다.
    renderOpen({
      onUseDraftAsScript: vi.fn(),
      messages: [
        { id: "user-1", role: "user", text: "B-roll 추천해 줘" },
        { id: "assistant-1", role: "assistant", text: "바다 장면에는 파도 소리가 들리는 해변 영상이 잘 어울려요. 두 번째 장면은 노을이 좋아요." },
      ],
    });

    expect(screen.queryByRole("button", { name: /이 답을 대본으로 쓰기/ })).toBeNull();
  });
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd apps/web && npx vitest run src/features/editor/workbench/scriptReply.test.ts`
Expected: FAIL `Failed to resolve import "./scriptReply"`.
Run: `cd apps/web && npx vitest run src/features/editor/workbench/YujinPanel.test.tsx -t "non-script request"`
Expected: FAIL `expected <button …>이 답을 대본으로 쓰기</button> to be null`.

- [ ] **Step 3: 최소 구현**

새 파일 `apps/web/src/features/editor/workbench/scriptReply.ts`:

```ts
import type { RightDockMessage } from "./rightDockTypes";

const SCRIPT_MINIMUM_CHARACTERS = 30;

/** 한 줄 요청이 아니라 대본으로 쓸 만한 길이인가. 입력칸 글에도 같은 기준을 쓴다. */
export function looksLikeScript(text: string): boolean {
  return text.trim().length >= SCRIPT_MINIMUM_CHARACTERS;
}

const SCRIPT_REQUEST_WORDS = ["대본", "스크립트", "원고", "내레이션", "나레이션", "멘트", "대사"] as const;

/** 유진의 답이 **대본을 청한 말에 대한 답**인가(2026-10-02).
 *
 *  길이만 보면 B-roll 추천 설명 같은 긴 답에도 `이 답을 대본으로 쓰기`가 붙었다.
 *  바로 앞 "나"의 말에 대본을 뜻하는 낱말이 있을 때만 참이다. 확정은 여전히
 *  사람이 단추로 한다(2026-08-16). */
export function isScriptReply(messages: readonly RightDockMessage[], index: number): boolean {
  const message = messages[index];
  if (!message || message.role !== "assistant" || !looksLikeScript(message.text)) return false;
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
    const previous = messages[cursor];
    if (previous.role === "user") return SCRIPT_REQUEST_WORDS.some((word) => previous.text.includes(word));
  }
  return false;
}
```

`YujinPanel.tsx` — 옛 정의를 지운다(그대로 찾는다):
```tsx
const SCRIPT_MINIMUM_CHARACTERS = 30;
function looksLikeScript(draft: string): boolean {
  return draft.trim().length >= SCRIPT_MINIMUM_CHARACTERS;
}

```
→ (빈 문자열로 지운다) 그리고 13행 `import { frameFitLabel } from "../inspector/frameFits";` 바로 아래에:
```tsx
import { isScriptReply, looksLikeScript } from "./scriptReply";
```

답 목록(그대로 찾는다):
```tsx
        ? messages.map((message) => <article key={message.id}>
          <p><strong>{message.role === "user" ? "나" : "유진"}</strong> {message.text}</p>
          {onUseDraftAsScript && message.role === "assistant" && looksLikeScript(message.text)
```
→
```tsx
        ? messages.map((message, index) => <article key={message.id}>
          <p><strong>{message.role === "user" ? "나" : "유진"}</strong> {message.text}</p>
          {onUseDraftAsScript && isScriptReply(messages, index)
```
(입력칸 쪽 `looksLikeScript(draft)`는 그대로 둔다 — 내가 붙여 넣은 글은 요청 문맥이 없다.)

`YujinPanel.test.tsx`의 `"tells two Yujin answers apart, so the button can be reached by voice"` 시험 안 `messages`를:
```tsx
      messages: [
        { id: "assistant-1", role: "assistant", text: first },
        { id: "assistant-2", role: "assistant", text: second },
      ],
```
→
```tsx
      messages: [
        { id: "user-1", role: "user", text: "제주 대본 하나 써 줘" },
        { id: "assistant-1", role: "assistant", text: first },
        { id: "user-2", role: "user", text: "다른 대본도 써 줘" },
        { id: "assistant-2", role: "assistant", text: second },
      ],
```

- [ ] **Step 4: 통과를 확인한다**

Run: `cd apps/web && npx vitest run src/features/editor/workbench/scriptReply.test.ts src/features/editor/workbench/YujinPanel.test.tsx` → 전부 통과.

- [ ] **Step 5: 넓은 검증**

Run: `cd apps/web && npx vitest run src/features/editor/workbench/editor-workbench-route.test.tsx src/user-copy-policy.test.ts` → 통과.
Run: `cd apps/web && npx tsc --noEmit` → 0.
배선: `grep -rn "isScriptReply\|looksLikeScript" apps/web/src --include=*.tsx --include=*.ts | grep -v test` → `scriptReply.ts`(정의 2) + `YujinPanel.tsx`(import 1, 사용 2).

- [ ] **Step 6: 커밋**

```bash
git add apps/web/src/features/editor/workbench/scriptReply.ts apps/web/src/features/editor/workbench/scriptReply.test.ts apps/web/src/features/editor/workbench/YujinPanel.tsx apps/web/src/features/editor/workbench/YujinPanel.test.tsx
git commit -m "fix(yujin): 이 답을 대본으로 쓰기는 대본을 청한 답에만

길이만 보던 탓에 B-roll 추천 같은 긴 답에도 단추가 붙었다.
바로 앞 내 말에 대본·원고·내레이션 같은 낱말이 있을 때만 띄운다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: 검토 화면 반복 안내 하나로, 같은 충돌 카드 묶기 (G5-b, G5-c)

**Files:**
- Modify: `apps/web/src/app/OutputsPage.tsx:1354-1375`(체크리스트), `:1394`, `:1450`, `:1462`, `:1571`(반복 문장 넷), `:1428-1435`(충돌 패널), `:792-810`(`resolveVariantConflict` 뒤에 묶음 함수)
- Create: `apps/web/src/features/outputs/variantConflictGroups.ts`
- Modify: `apps/web/src/features/editor/variants/VariantConflictPanel.tsx:44-60`
- Test: `apps/web/src/app/OutputsPage.test.tsx`(파일 끝에 추가)

**Interfaces:**
- Produces: `groupVariantConflicts<T extends ConflictedVariantOption>(options: readonly T[]): { conflicts: readonly VariantConflict[]; options: T[] }[]`(필드+사유 집합이 같은 변형본끼리 묶음), `VariantConflictPanel`의 선택 prop `targetLabel?: string`(주면 제목이 `가로·세로 출력이 마스터와 달라요`, 그 아래 `가로 영상 · 세로 영상` 같은 대상 줄). 편집기 쪽(prop 없음)은 그대로 `세로 편집과 마스터가 달라요`.

- [ ] **Step 1: 실패하는 시험을 쓴다**

`apps/web/src/app/OutputsPage.test.tsx` 파일 **맨 끝**에:

```tsx
/** 2026-10-02 점검: 같은 안내 `검토 승인과 확인할 항목을 모두 마친 뒤 …`가 카드
 *  넷에 반복됐고(위 체크리스트와 같은 말), 같은 충돌 카드가 변형본마다 한 장씩
 *  똑같이 쌓였다(실측 2장). 안내는 체크리스트 한 곳, 충돌은 한 장으로. */
describe("검토 화면 정리", () => {
  beforeEach(() => {
    vi.spyOn(api, "listOutputVariants").mockResolvedValue({ variants: [] } as never);
  });

  it("막힌 이유는 체크리스트에서 한 번만 말한다", async () => {
    stubCanonicalSubtitleApi({ reviewFlags: [{ code: "review_required", segment_id: "segment-a", message: "확인이 필요해요." }] });

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    const checklist = await screen.findByRole("region", { name: "출력 준비 체크리스트" });
    expect(within(checklist).getByText("검토 승인과 확인할 항목을 모두 마치면 숏폼·자막·완성본·CapCut 초안을 만들 수 있어요.")).toBeVisible();
    expect(screen.queryAllByText(/모두 마친 뒤/)).toHaveLength(0);
  });

  it("변형본 둘의 같은 충돌은 한 장으로 묶고, 한 번 누르면 둘 다 푼다", async () => {
    stubCanonicalSubtitleApi();
    const conflict = { field: "story", reason: "master_changed_while_locked", base_master_revision: 5, current_master_revision: 7 };
    const base = {
      source_session_id: "session-a", source_session_revision: 7,
      overrides: { crop: null, focal: null, caption: null, safe_area: null, audio: null },
      locks: [], selected_segment_ids: null, master_segment_ids: ["segment-a"],
    };
    const horizontal = { ...base, variant_id: "variant-h1", kind: "horizontal", variant_revision: 2, conflicts: [conflict] };
    const vertical = { ...base, variant_id: "variant-v1", kind: "vertical_full", variant_revision: 4, conflicts: [conflict] };
    vi.mocked(api.listOutputVariants).mockResolvedValue({ variants: [horizontal, vertical] } as never);
    const patchOutputVariant = vi.spyOn(api, "patchOutputVariant").mockImplementation(async (_projectId: string, variantId: string) => ({
      variant: { ...(variantId === "variant-h1" ? horizontal : vertical), conflicts: [], variant_revision: 9 },
    }) as never);

    render(<OutputsPage projectId="project_a" onOpenEditor={vi.fn()} />);

    await screen.findByText(/마스터가 바뀌었는데 이 항목은 고정돼 있어요/);
    expect(screen.getAllByText(/마스터가 바뀌었는데 이 항목은 고정돼 있어요/)).toHaveLength(1);
    expect(screen.getByText("가로 영상 · 세로 영상")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "마스터 기준 다시 맞추기" }));

    await waitFor(() => expect(patchOutputVariant).toHaveBeenCalledTimes(2));
    expect(patchOutputVariant).toHaveBeenCalledWith("project_a", "variant-h1", { expected_variant_revision: 2, patch: { resolve_conflicts: { story: "rebase_master" } } });
    expect(patchOutputVariant).toHaveBeenCalledWith("project_a", "variant-v1", { expected_variant_revision: 4, patch: { resolve_conflicts: { story: "rebase_master" } } });
    await waitFor(() => expect(screen.queryByText(/마스터가 바뀌었는데 이 항목은 고정돼 있어요/)).not.toBeInTheDocument());
  });
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd apps/web && npx vitest run src/app/OutputsPage.test.tsx -t "검토 화면 정리"`
Expected: 2 failed — 첫째 `Unable to find an element with the text: 검토 승인과 확인할 항목을 모두 마치면 …`, 둘째 `expected [ …, … ] to have a length of 1 but got 2`.

- [ ] **Step 3: 최소 구현**

새 파일 `apps/web/src/features/outputs/variantConflictGroups.ts`:

```ts
import type { VariantConflict } from "../editor/variants/variantProjection";

export type ConflictedVariantOption = Readonly<{
  variant_id: string;
  kind: string;
  variant_revision: number;
  conflicts: readonly VariantConflict[];
}>;

export type VariantConflictGroup<T extends ConflictedVariantOption> = Readonly<{
  conflicts: readonly VariantConflict[];
  options: T[];
}>;

/** 충돌 내용(필드+사유)이 같은 변형본끼리 묶는다(2026-10-02).
 *
 *  마스터가 바뀌면 가로·세로 변형본에 **같은** "스토리" 충돌이 함께 쌓인다. 변형본마다
 *  한 장씩 그리면 똑같은 카드가 줄줄이 선다(실측 2장). 고를 것은 하나이므로 한 장으로. */
export function groupVariantConflicts<T extends ConflictedVariantOption>(options: readonly T[]): VariantConflictGroup<T>[] {
  const groups = new Map<string, { conflicts: readonly VariantConflict[]; options: T[] }>();
  for (const option of options) {
    if (!option.conflicts.length) continue;
    const signature = option.conflicts.map((conflict) => `${conflict.field}:${conflict.reason}`).sort().join("|");
    const existing = groups.get(signature);
    if (existing) existing.options.push(option);
    else groups.set(signature, { conflicts: option.conflicts, options: [option] });
  }
  return [...groups.values()];
}
```

`VariantConflictPanel.tsx`:
```tsx
export function VariantConflictPanel({
  conflicts,
  onKeep,
  onRebase,
}: Readonly<{
  conflicts: readonly VariantConflict[];
  onKeep: (field: string) => void;
  onRebase: (field: string) => void;
}>) {
  if (!conflicts.length) return null;
  return <section className="vb-editor-variants__conflicts" aria-label="세로 변형 충돌">
    <h3>세로 편집과 마스터가 달라요</h3>
```
→
```tsx
export function VariantConflictPanel({
  conflicts,
  onKeep,
  onRebase,
  targetLabel,
}: Readonly<{
  conflicts: readonly VariantConflict[];
  onKeep: (field: string) => void;
  onRebase: (field: string) => void;
  /** 이 카드가 어느 출력에 해당하는지(예: `가로 영상 · 세로 영상`). 확인과 내보내기
   *  화면이 같은 충돌을 묶어 그릴 때 준다. 편집기는 지금 보는 하나라 주지 않는다. */
  targetLabel?: string;
}>) {
  if (!conflicts.length) return null;
  return <section className="vb-editor-variants__conflicts" aria-label="세로 변형 충돌">
    <h3>{targetLabel ? "가로·세로 출력이 마스터와 달라요" : "세로 편집과 마스터가 달라요"}</h3>
    {targetLabel ? <p className="vb-editor-variants__conflict-targets">{targetLabel}</p> : null}
```

`OutputsPage.tsx` import(`import { mergeVariantRenderItems, variantLabel, variantRenderSummary } from "../features/outputs/variantOutputState";` 바로 아래):
```tsx
import { groupVariantConflicts } from "../features/outputs/variantConflictGroups";
```

`resolveVariantConflict` 함수 끝(`      setResolvingVariantId(null);\n    }\n  };`) 바로 아래에:
```tsx
  /** 묶인 충돌 한 장을 누르면 그 묶음의 변형본을 차례로 모두 푼다. */
  const resolveVariantConflictGroup = async (
    options: readonly { variant_id: string; variant_revision: number }[],
    field: string,
    decision: "keep_local" | "rebase_master",
  ) => {
    for (const option of options) await resolveVariantConflict(option, field, decision);
  };
```

충돌 패널 자리(그대로 찾는다):
```tsx
          {variantOptions.filter((option) => option.conflicts.length > 0).map((option) => (
            <VariantConflictPanel
              key={`${option.variant_id}-conflicts`}
              conflicts={option.conflicts}
              onKeep={(field) => void resolveVariantConflict(option, field, "keep_local")}
              onRebase={(field) => void resolveVariantConflict(option, field, "rebase_master")}
            />
          ))}
```
→
```tsx
          {groupVariantConflicts(variantOptions).map((group) => (
            <VariantConflictPanel
              key={`${group.options.map((option) => option.variant_id).join("+")}-conflicts`}
              conflicts={group.conflicts}
              targetLabel={group.options.map((option) => variantLabel(option.kind)).join(" · ")}
              onKeep={(field) => void resolveVariantConflictGroup(group.options, field, "keep_local")}
              onRebase={(field) => void resolveVariantConflictGroup(group.options, field, "rebase_master")}
            />
          ))}
```

반복 문장 넷을 지운다. 아래 네 줄을 **각각 통째로** 지운다:
```tsx
          {timelineJob && !canRenderSubtitle ? <p>검토 승인과 확인할 항목을 모두 마친 뒤 숏폼을 만들 수 있어요.</p> : null}
```
```tsx
          {timelineJob && !canRenderSubtitle ? <p>검토 승인과 확인할 항목을 모두 마친 뒤 자막을 만들 수 있어요.</p> : null}
```
```tsx
          {timelineJob && !canRenderSubtitle ? <p>검토 승인과 확인할 항목을 모두 마친 뒤 완성본을 만들 수 있어요.</p> : null}
```
```tsx
          {timelineJob && !canRenderSubtitle ? <p>검토 승인과 확인할 항목을 모두 마친 뒤 CapCut 초안을 만들 수 있어요.</p> : null}
```

체크리스트 `출력` 줄(그대로 찾는다):
```tsx
        <li>
          <strong>출력</strong>
          <span>{canRenderSubtitle ? "준비됨" : "앞 단계 완료 필요"}</span>
        </li>
      </ol>
```
→
```tsx
        <li>
          <strong>출력</strong>
          <span>{canRenderSubtitle ? "준비됨" : "앞 단계 완료 필요"}</span>
        </li>
      </ol>
      {/* 예전엔 아래 카드 넷이 같은 말을 한 번씩 했다(2026-10-02 점검). 여기서 한 번만. */}
      {timelineJob ? <p>검토 승인과 확인할 항목을 모두 마치면 숏폼·자막·완성본·CapCut 초안을 만들 수 있어요.</p> : null}
```

`apps/web/src/styles/editor-workbench.css`의 `.vb-editor-variants__conflicts h3, .vb-editor-variants__conflicts p { margin: 0; }` 줄 바로 아래에:
```css
.vb-editor-variants__conflict-targets { color: var(--muted-foreground); font-size: var(--vb-text-sm); }
```

- [ ] **Step 4: 통과를 확인한다**

Run: `cd apps/web && npx vitest run src/app/OutputsPage.test.tsx -t "검토 화면 정리"` → `2 passed`

- [ ] **Step 5: 넓은 검증**

Run: `cd apps/web && npx vitest run src/app/OutputsPage.test.tsx src/features/editor/variants src/features/review src/user-copy-policy.test.ts src/task22-parity-owners.test.ts` → 전부 통과(기존 "가로세로 출력에 마스터 충돌이 있으면 이 화면에서 바로 풀 수 있다"·"한 변형본에 같은 필드 충돌이 여러 개 쌓여도 안내는 한 번만" 포함, `VariantConflictPanel.test.tsx` 포함).
Run: `cd apps/web && npx tsc --noEmit` → 0.
배선: `grep -rn "모두 마친 뒤" apps/web/src --include=*.tsx | grep -v test` → 0줄. `grep -rn "groupVariantConflicts" apps/web/src | grep -v test` → 정의 1 + 사용 1.

- [ ] **Step 6: 커밋**

```bash
git add apps/web/src/app/OutputsPage.tsx apps/web/src/features/outputs/variantConflictGroups.ts apps/web/src/features/editor/variants/VariantConflictPanel.tsx apps/web/src/styles/editor-workbench.css apps/web/src/app/OutputsPage.test.tsx
git commit -m "fix(review): 반복 안내를 체크리스트 한 곳으로, 같은 충돌은 한 장으로

카드 넷이 같은 문장을 되풀이했고, 변형본마다 똑같은 충돌 카드가 섰다.
묶은 카드 하나를 누르면 묶음 전체를 차례로 푼다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 10: 유진 패널의 겹친 스크롤을 하나로 (G5-d)

**측정(계획 작성 시):** 1440×900, `/projects/0907-b26195af/editor`, 유진 열고. 편집기에서 **겹친 스크롤은 유진 패널 하나뿐**이다 — 패널 `.vb-yujin-panel`(382/759)이 스크롤되고, 그 안의 대화 기록 `.vb-editor-right-dock__history`(207/3096)가 또 스크롤된다. 패널 자식은 머리 32px · 기록 224px · 이름표 16px · 입력 64px · 단추 32px×2 · `유진 기억` 칸(`YujinMemoryPanel`, 클래스 `.vb-editor-workbench__summary`) 287px. 이 기억 칸이 패널을 넘치게 만든다. (검토자 정정: 처음 초안은 이것을 "완료 목록"이라 적었는데, 패널의 직접 자식으로 이 클래스를 쓰는 것은 `YujinMemoryPanel.tsx:28`의 기억 칸이다.) 왼쪽·오른쪽 도크와 타임라인 스크롤은 서로 겹치지 않으므로 손대지 않는다.

**고치는 방법:** 패널을 세로 flex로 바꿔 **대화 기록이 남는 높이를 갖고 혼자 스크롤**하게 한다. 기억 칸은 높이 상한(6rem)을 두고 따로 스크롤(형제, 겹치지 않음). **주의:** 기억 칸 안에는 기억 종류 고르기·5rem 글칸·승인 단추(owner 승인 게이트)가 있다. 6rem 상자 안에서 스크롤해야 닿는다 — 단추가 **잘려서 못 누르는** 것이 아니라 **스크롤로 닿는지**를 Task 17에서 확인한다. 382px 패널에 고정 부분 약 232px + 기록 최소 4rem이라 기억 칸에 남는 높이가 약 6rem이다(더 키우면 다시 겹친 스크롤이 된다). 패널 자체 `overflow:auto`는 **남겨 둔다** — 다른 갈래(추천 카드 등)가 한꺼번에 떠서 고정 부분만으로 넘칠 때 단추가 잘려 못 누르게 되는 것보다 겹친 스크롤이 낫다.

**Files:**
- Modify: `apps/web/src/styles/editor-workbench.css:99`(기록 규칙), `:125-140`(`.vb-yujin-panel`)
- Create: `apps/web/src/styles/yujin-panel-scroll.test.ts`

**Interfaces:**
- Consumes/Produces: CSS만. 대화 기록의 스크롤 위치 기억(`onConversationScrollChange`, `YujinPanel.tsx:340-347`)은 여전히 `.vb-editor-right-dock__history`가 스크롤 주인이라 그대로 동작한다.

- [ ] **Step 1: 실패하는 시험을 쓴다**

`apps/web/src/styles/yujin-panel-scroll.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const css = readFileSync(resolve(process.cwd(), "src/styles/editor-workbench.css"), "utf8");

/** 유진 패널(382/759)이 스크롤되고 그 안의 대화 기록(207/3096)이 또 스크롤됐다
 *  (2026-10-02, 1440×900 실측). 대화 기록이 남는 높이를 갖고 혼자 스크롤한다. */
describe("유진 패널 스크롤", () => {
  it("패널은 세로 flex다", () => {
    const rule = css.match(/^\.vb-yujin-panel\s*\{[^}]*\}/m)?.[0] ?? "";
    expect(rule).toMatch(/display:\s*flex/);
    expect(rule).toMatch(/flex-direction:\s*column/);
  });

  it("대화 기록이 남는 높이를 갖고, 14rem 상한을 패널 안에서는 푼다", () => {
    expect(css).toMatch(/\.vb-yujin-panel\s*>\s*\.vb-editor-right-dock__history\s*\{[^}]*flex:\s*1 1 6rem[^}]*max-height:\s*none/);
  });

  it("기억 칸은 상한을 두고 따로 스크롤한다", () => {
    expect(css).toMatch(/\.vb-yujin-panel\s*>\s*\.vb-editor-workbench__summary\s*\{[^}]*max-height:\s*6rem[^}]*overflow:\s*auto/);
  });
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd apps/web && npx vitest run src/styles/yujin-panel-scroll.test.ts`
Expected: 3 failed — 첫째 `expected '….vb-yujin-panel {…display: grid…}' to match /display:\s*flex/`, 나머지는 해당 규칙이 없어서 match 실패.

- [ ] **Step 3: 최소 구현**

`editor-workbench.css`의 `.vb-yujin-panel` 블록 안 두 줄:
```css
  overflow: auto;
  display: grid;
  gap: var(--vb-space-2);
```
→
```css
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: var(--vb-space-2);
```

`.vb-yujin-panel__header h2 { … }` 줄 바로 아래에:
```css
/* **스크롤 주인은 대화 기록 하나다(2026-10-02).** 패널(382/759)과 그 안의 기록
   (207/3096)이 겹쳐 스크롤됐다. 기록이 남는 높이를 갖고, 기억 칸은 상한을 둬
   따로 스크롤한다(형제라 겹치지 않는다). 나머지는 제 높이를 지킨다. 패널의
   `overflow:auto`는 남긴다 -- 고정 부분만으로 넘칠 때 단추가 잘리는 것보다 낫다. */
.vb-yujin-panel > * { flex: 0 0 auto; }
.vb-yujin-panel > .vb-editor-right-dock__history { flex: 1 1 6rem; min-height: 4rem; max-height: none; }
.vb-yujin-panel > .vb-editor-workbench__summary { flex: 0 1 auto; min-height: 0; max-height: 6rem; overflow: auto; }
```

- [ ] **Step 4: 통과를 확인한다**

Run: `cd apps/web && npx vitest run src/styles/yujin-panel-scroll.test.ts` → `3 passed`

- [ ] **Step 5: 넓은 검증**

Run: `cd apps/web && npx vitest run src/styles src/features/editor/workbench/YujinPanel.test.tsx src/features/editor/workbench/yujin-memory-panel.test.tsx src/features/editor/workbench/editor-workbench-route.test.tsx`
Expected: 통과(대화 기록 `scrollTop` 기억 시험 포함 — jsdom이라 CSS 영향 없음).
동작 확인은 Task 17 브라우저 단계에서 한다(목표: 1440×900에서 기록의 "스크롤되는 조상" 수 0).

- [ ] **Step 6: 커밋**

```bash
git add apps/web/src/styles/editor-workbench.css apps/web/src/styles/yujin-panel-scroll.test.ts
git commit -m "fix(editor): 유진 패널 겹친 스크롤을 대화 기록 하나로

패널과 대화 기록이 겹쳐 스크롤됐다(382/759 안에 207/3096).
기록이 남는 높이를 갖고 기억 칸은 상한을 둬 따로 스크롤한다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 11: 그 밖에 필요한 것 셋 (G6)

화면을 직접 걸으며 찾은 것 중 **작고 값이 큰 것 셋만** 고친다. 근거는 위 "실측 기록".

1. **검토 화면 출력 칸이 휴대폰 폭에서 4칸 그대로** — 375px에서 칸당 **77px 폭 × 1524px 높이**. `.vb-outputs-grid { repeat(4,…) }`(product-shell.css 125행)가 767px 이하 규칙(111행)보다 **뒤에** 있어서 이긴다. 767px 이하 1칸, 768~1199px 2칸으로.
2. **같은 화면인데 "내보내기 화면에서"** — 검토와 출력은 한 화면(2026-08-16 결정)인데 승인 문구가 `이제 내보내기 화면에서 자막과 완성본을 만들 수 있어요.`라고 다른 화면을 가리킨다. `아래에서`로.
3. **오디오 도크 가로 넘침** — 221px 도크에 252px 내용. `만든이 … 빼기` 단추가 줄바꿈을 못 해 가로 스크롤 막대가 생긴다(세로 15px도 먹는다). 단추 글을 줄바꿈 허용.

**Files:**
- Modify: `apps/web/src/styles/product-shell.css:130`(Task 5에서 붙인 재생기 규칙들 바로 아래)
- Modify: `apps/web/src/features/review/TimelineReviewPage.tsx:130`, `:138`
- Modify: `apps/web/src/styles/editor-workbench.css:346`(`.vb-editor-assets__taste { align-items: center; }` 아래)
- Create: `apps/web/src/styles/screen-small-fixes.test.ts`
- Test: `apps/web/src/features/review/TimelineReviewPage.test.tsx`(`describe("TimelineReviewPage"` 블록 안 마지막에 추가)

- [ ] **Step 1: 실패하는 시험을 쓴다**

`apps/web/src/styles/screen-small-fixes.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const shell = readFileSync(resolve(process.cwd(), "src/styles/product-shell.css"), "utf8");
const editor = readFileSync(resolve(process.cwd(), "src/styles/editor-workbench.css"), "utf8");

describe("화면 작은 결함(2026-10-02 걸어 보며 찾음)", () => {
  it("검토 화면 출력 칸은 767px 이하에서 한 칸이다(실측 77px×4칸)", () => {
    expect(shell).toMatch(/@media \(max-width:\s*767px\)\s*\{\s*\.vb-outputs-grid\s*\{\s*grid-template-columns:\s*1fr/);
  });

  it("768~1199px에서는 두 칸이다", () => {
    expect(shell).toMatch(/@media \(min-width:\s*768px\) and \(max-width:\s*1199px\)\s*\{\s*\.vb-outputs-grid\s*\{\s*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/);
  });

  it("자료 도크의 취향 단추는 줄바꿈해서 도크 폭을 넘지 않는다", () => {
    expect(editor).toMatch(/\.vb-product-shell \.vb-editor-assets__taste\s*>\s*\[data-slot="button"\]\s*\{[^}]*white-space:\s*normal[^}]*max-width:\s*100%[^}]*height:\s*auto/);
  });
});
```

`TimelineReviewPage.test.tsx`의 `describe("TimelineReviewPage", () => {` 블록 **마지막 `});` 바로 앞**에:

```tsx
  it("검토와 출력이 한 화면이라 승인 뒤에는 '아래에서' 만들라고 말한다", async () => {
    // 2026-10-02: "이제 내보내기 화면에서 …"는 다른 화면을 가리켰다. 출력은 바로 아래다.
    vi.mocked(api.getReviewApproval).mockResolvedValue(approval("project-a", "timeline-a", "approved"));
    render(<TimelineReviewPage projectId="project-a" />);

    expect(await screen.findByText("이제 아래에서 자막과 완성본을 만들 수 있어요.")).toBeVisible();
    expect(screen.queryByText(/내보내기 화면에서/)).toBeNull();
  });
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd apps/web && npx vitest run src/styles/screen-small-fixes.test.ts` → 3 failed(`expected '…' to match /@media …/`).
Run: `cd apps/web && npx vitest run src/features/review/TimelineReviewPage.test.tsx -t "아래에서"` → FAIL `Unable to find an element with the text: 이제 아래에서 자막과 완성본을 만들 수 있어요.`

- [ ] **Step 3: 최소 구현**

`product-shell.css` — Task 5에서 넣은 `.vb-outputs-preview .vb-preview-stage__media-shell video { … }` 줄 바로 아래에:
```css
/* **휴대폰 폭에서 출력 칸이 4칸 그대로였다**(2026-10-02, 375px에서 칸당 77×1524px).
   위 4칸 규칙이 767px 이하 규칙(111행)보다 뒤에 있어서 이긴다. 여기서 다시 건다. */
@media (max-width: 767px) { .vb-outputs-grid { grid-template-columns: 1fr; } }
@media (min-width: 768px) and (max-width: 1199px) { .vb-outputs-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
```

`TimelineReviewPage.tsx`:
```tsx
          <p>이제 내보내기 화면에서 자막과 완성본을 만들 수 있어요.</p>
```
→
```tsx
          <p>이제 아래에서 자막과 완성본을 만들 수 있어요.</p>
```
와
```tsx
            ? "승인하면 내보내기 화면에서 자막과 완성본을 만들 수 있어요."
```
→
```tsx
            ? "승인하면 아래에서 자막과 완성본을 만들 수 있어요."
```

`editor-workbench.css` — `.vb-editor-assets__taste { align-items: center; }` 줄 바로 아래에:
```css
/* 만든이 이름이 길면 단추가 도크 폭(221px)을 넘어 가로 스크롤이 생겼다(2026-10-02 실측 252px).
   **무게를 맞춰야 이긴다**: `product-shell.css`의 `.vb-product-shell [data-slot=button]
   { height:32px }`(0,2,0)와 위 `.vb-product-shell .vb-editor-workbench [data-slot="button"]`
   (0,3,0)보다 뒤에, 같은 (0,3,0)으로 둔다. 높이를 안 풀면 두 줄 글이 32px 안에서 잘린다.
   Tailwind `whitespace-nowrap`(0,1,0)은 이 무게에 진다. */
.vb-product-shell .vb-editor-assets__taste > [data-slot="button"] { white-space: normal; max-width: 100%; height: auto; min-height: 32px; text-align: left; }
```

- [ ] **Step 4: 통과를 확인한다**

Run: `cd apps/web && npx vitest run src/styles/screen-small-fixes.test.ts src/features/review/TimelineReviewPage.test.tsx` → 전부 통과.

- [ ] **Step 5: 넓은 검증**

Run: `cd apps/web && npx vitest run src/styles src/features/review src/features/editor/assets src/app/OutputsPage.test.tsx src/user-copy-policy.test.ts` → 통과.
배선: `grep -rn "내보내기 화면에서" apps/web/src --include=*.tsx | grep -v test` → 0줄.

- [ ] **Step 6: 커밋**

```bash
git add apps/web/src/styles/product-shell.css apps/web/src/styles/editor-workbench.css apps/web/src/features/review/TimelineReviewPage.tsx apps/web/src/features/review/TimelineReviewPage.test.tsx apps/web/src/styles/screen-small-fixes.test.ts
git commit -m "fix(screens): 휴대폰 폭 출력 칸, 같은 화면을 가리키는 문구, 도크 가로 넘침

375px에서 출력 칸이 77px 폭 4칸이었다 -> 1칸(768~1199px 2칸).
검토 승인 문구는 '아래에서'로. 긴 만든이 단추는 줄바꿈한다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 12: 자료실 썸네일 — 이미 만든 것은 원본을 다시 재지 않고 보낸다

**측정(검토자, 2026-10-02, 컨테이너 앞문 5173):** `GET /api/library/assets?limit=500`은 **0.32초**(235개, 180KB)로 빠르다. 느린 것은 썸네일이다 — **이미 만들어진 썸네일도** 한 장 평균 0.30초, 원본이 546MB인 영상은 **2.9초**. 235장 직렬 합계 70.5초, 6개 병렬(브라우저 한 호스트 동시 연결 수)로 12~16초. 같은 크기의 프로젝트 자산 썸네일은 0.025초다. 원인은 `routers/library_assets.py`의 `get_derivative`가 요청마다 (1) `source_for_user` → `resolve_managed_path`로 **원본 파일 전체를 sha256** 하고, (2) `_ensure_derivative`에서 썸네일 파일을 또 해시하고 DB에 `upsert_derivative`를 쓰기 때문이다.

**화면 쪽은 할 일이 없다(확인함):** `LibraryResults.tsx`는 이미 `assets.slice(0, 24)`만 그리고, `VideoAssetGrid.tsx`의 `<img>`는 이미 `loading="lazy"`다. 음악·효과음 줄(`AudioAssetRows.tsx`)은 썸네일을 부르지 않는다. 그래서 `loading="lazy"`를 새로 붙일 자리도, 쪽 나누기(paging)를 넣을 근거도 없다 — 한 화면 24장 상한이 이미 있다. **paging은 넣지 않는다.**

**재사용 게이트:** 새 캐시 계층·새 엔드포인트를 만들지 않는다(exclude). `_ensure_derivative`가 이미 정한 파일 이름 규칙(`derivatives/<content_sha256>/<DERIVATIVE_VERSION>-<kind>.png|.svg`)을 그대로 읽기만 한다(partial — 함수 하나).

**Files:**
- Modify: `services/api/src/videobox_api/routers/library_assets.py:756-758`(`get_derivative`의 `builtin` 갈래 뒤), `:840`(`_ensure_derivative` 바로 위에 함수 하나)
- Create: `tests/test_library_thumbnail_cache_hit.py`

**Interfaces:**
- Consumes: 자산 행의 `content_sha256: str`, 모듈 상수 `DERIVATIVE_VERSION = "v2"`, `managed_root: Path`.
- Produces: 모듈 함수 `_cached_derivative_path(root: Path, asset: Any, kind: str) -> Path | None`. 응답 모양·주소는 그대로.

- [ ] **Step 1: 실패하는 시험을 쓴다**

`tests/test_library_thumbnail_cache_hit.py`:

```python
"""자료실 썸네일은 이미 만든 것을 다시 보낼 때 원본을 다시 재지 않는다 (2026-10-02 점검 후속 G).

실측: 이미 만들어진 썸네일도 한 장 평균 0.30초, 546MB 원본은 2.9초였다(프로젝트 자산
썸네일은 0.025초). 요청마다 원본 전체의 sha256(`resolve_managed_path`)과 썸네일 파일
해시·DB 기록(`upsert_derivative`)을 다시 했기 때문이다. 썸네일 파일은 원본 해시
(`content_sha256`) 이름의 폴더에 있으므로, 있으면 그대로 보낸다.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_api.routers import library_assets as library_assets_router
from videobox_storage.media_library_store import MediaLibraryStore


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(projects_root=tmp_path / "projects", media_library_store=MediaLibraryStore(tmp_path / "library")))


def _ingest_music(client: TestClient) -> str:
    response = client.post(
        "/api/library/ingest",
        data={"media_type": "music", "idempotency_key": "thumbnail-cache"},
        files=[("files", ("song.mp3", b"fake audio bytes", "audio/mpeg"))],
    )
    assert response.status_code == 201, response.text
    return str(response.json()["items"][0]["library_asset_id"])


def test_a_cached_thumbnail_is_served_without_rehashing_the_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(tmp_path)
    asset_id = _ingest_music(client)
    first = client.get(f"/api/library/assets/{asset_id}/thumbnail")
    assert first.status_code == 200, first.text

    def must_not_rehash_source(**_kwargs: Any) -> Any:
        raise AssertionError("cached thumbnail must not re-hash the source file")

    def must_not_rehash_derivative(_path: Path) -> str:
        raise AssertionError("cached thumbnail must not re-hash the derivative file")

    monkeypatch.setattr(library_assets_router, "resolve_managed_path", must_not_rehash_source)
    monkeypatch.setattr(library_assets_router, "_sha256", must_not_rehash_derivative)

    second = client.get(f"/api/library/assets/{asset_id}/thumbnail")

    assert second.status_code == 200
    assert second.content == first.content
    assert second.headers["content-type"] == first.headers["content-type"]


def test_a_missing_thumbnail_is_still_made_from_the_verified_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(tmp_path)
    asset_id = _ingest_music(client)
    shutil.rmtree(tmp_path / "library" / "derivatives", ignore_errors=True)
    seen: list[str] = []
    original = library_assets_router.resolve_managed_path

    def counting(**kwargs: Any) -> Any:
        seen.append(str(kwargs["relative_path"]))
        return original(**kwargs)

    monkeypatch.setattr(library_assets_router, "resolve_managed_path", counting)

    response = client.get(f"/api/library/assets/{asset_id}/thumbnail")

    assert response.status_code == 200, response.text
    assert len(seen) == 1
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_library_thumbnail_cache_hit.py`
Expected: `1 failed, 1 passed` — `AssertionError: cached thumbnail must not re-hash the source file`. 둘째(처음 만들 때는 원본을 확인한다)는 이미 통과하는 회귀 지킴이다. (검토자가 저장소 밖 복사본에서 이 결과를 실제로 확인했다.)

- [ ] **Step 3: 최소 구현**

`services/api/src/videobox_api/routers/library_assets.py`의 `get_derivative` 안(그대로 찾는다, 파일에 한 번뿐):

```python
        if builtin is not None:
            return {"library_asset_id": asset_id, "kind": derivative_kind, "source_hash": builtin.get("sha256"), "version": DERIVATIVE_VERSION}
        source = source_for_user(asset)
```
→
```python
        if builtin is not None:
            return {"library_asset_id": asset_id, "kind": derivative_kind, "source_hash": builtin.get("sha256"), "version": DERIVATIVE_VERSION}
        # **이미 만든 썸네일·파형은 그대로 보낸다(2026-10-02 실측).** 예전에는 요청마다
        # 원본 파일 전체의 sha256(`source_for_user` -> `resolve_managed_path`)과 썸네일 파일
        # 해시·DB 기록(`_ensure_derivative`)을 다시 해서, 이미 있는 썸네일도 한 장 평균
        # 0.30초, 546MB 원본은 2.9초가 걸렸다(프로젝트 자산 썸네일은 0.025초). 썸네일은
        # 원본 해시 이름의 폴더(`derivatives/<content_sha256>/`)에 있어서, 원본이 바뀌면
        # 자산 행의 해시도 바뀌어 다른 폴더를 본다 -- 여기서 원본을 다시 잴 이유가 없다.
        # 처음 만드는 길(아래)은 그대로 원본을 확인한다.
        cached = _cached_derivative_path(managed_root, asset, derivative_kind)
        if cached is not None:
            return FileResponse(cached, media_type="image/svg+xml" if cached.suffix == ".svg" else "image/png")
        source = source_for_user(asset)
```

같은 파일, 이 줄(그대로 찾는다) 바로 **위**에:
```python
def _ensure_derivative(store: LibraryUserAssetStore, root: Path, asset: Any, kind: str, source: Path) -> dict[str, Any]:
```
넣는다:
```python
def _cached_derivative_path(root: Path, asset: Any, kind: str) -> Path | None:
    """`_ensure_derivative`가 이미 써 둔 파일이 있으면 그 경로. 이름 규칙은 그 함수와 같다
    (`derivatives/<content_sha256>/<DERIVATIVE_VERSION>-<kind>.png`, 그림을 못 그렸으면 `.svg`)."""
    content_sha256 = str(asset.content_sha256 or "")
    if not re.fullmatch(r"[0-9a-f]{64}", content_sha256):
        return None
    folder = root / "derivatives" / content_sha256
    for extension in (".png", ".svg"):
        candidate = folder / f"{DERIVATIVE_VERSION}-{kind}{extension}"
        if candidate.is_file():
            return candidate
    return None


```
(`re`는 이 파일 13행에서 이미 import한다. 해시 모양 검사는 경로가 `derivatives` 밖으로 새지 않게 하는 방어선이다.)

덤으로 고쳐지는 것: 그림을 못 그린 소리 자산은 `.svg`로 떨어지는데, 예전 코드는 `.png`만 확인해서 **요청마다 ffmpeg를 다시 불렀다**. 이제는 `.svg`도 찾아 그대로 보낸다.

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_library_thumbnail_cache_hit.py` → `2 passed`

- [ ] **Step 5: 넓은 검증**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_api_library_assets.py tests/test_library_image_assets.py tests/test_library_thumbnail_cache_hit.py` → 전부 통과(검토자 사전 확인: 같은 수정을 복사본에 넣고 26+2 통과).
배선: `grep -n "_cached_derivative_path" services/api/src/videobox_api/routers/library_assets.py` → 정의 1 + 호출 1 = 2줄.
동작(실물)은 Task 17 Step 3 (g)에서 컨테이너를 다시 지은 뒤 잰다.

- [ ] **Step 6: 커밋**

```bash
git add services/api/src/videobox_api/routers/library_assets.py tests/test_library_thumbnail_cache_hit.py
git commit -m "perf(library): 이미 만든 자료실 썸네일은 원본을 다시 재지 않고 보낸다

요청마다 원본 전체 sha256과 썸네일 해시·DB 기록을 다시 해서 한 장 0.3초,
546MB 원본은 2.9초였다. 원본 해시 폴더에 파일이 있으면 그대로 보낸다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 13: 편집기 첫 로드에서 전환 추천을 두 번 묻지 않는다

**측정(검토자, 2026-10-02, 운영 빌드 5173 — `main.tsx`에 `StrictMode` 없음, `/assets/index-*.js` 번들):** `/projects/0907-b26195af/editor` 첫 로드에서 `GET …/transition-suggestions`가 886ms·1140ms **두 번**, `GET …/assets/broll-video`가 887ms·1137ms **두 번** 나갔다. 개발 모드 전용 이중 실행이 아니라 운영에서 실제로 일어난다.

원인 둘은 다르다.
1. **전환 추천(고친다):** `EditorWorkbenchRoute.tsx`의 추천 effect가 의존값으로 `state.session?.expectedRevision`을 쓴다. 세션을 읽기 전(`undefined`)에 한 번 묻고, 세션이 도착해 `1`이 되면 또 묻는다. 첫 물음은 쓸모가 없다 — 같은 판수의 같은 답이다.
2. **B-roll 목록(고치지 않는다, 기록만):** 서로 다른 소비자 둘이다 — 편집기 자산 effect(`EditorWorkbenchRoute.tsx:612`)와 왼쪽 도크의 분석 칸 `MediaAnalysisStatusPanel.tsx:49`(분석 목록과 짝으로 다시 읽고, 자기 단추를 누른 뒤에도 다시 읽는다). 한 번으로 줄이려면 분석 칸이 편집기 상태에 묶이는 배선을 새로 만들어야 하는데, 이득은 0.026~0.043초짜리 요청 하나다. **경계를 섞는 비용이 이득보다 크다고 판단해 남긴다.** Task 17 보고의 갭에 적는다.

**Files:**
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx:479-496`(전환 추천 effect)
- Test: `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`(`describe("EditorWorkbenchRoute"` 안)

**Interfaces:**
- Consumes: `state.key`, `state.session?.expectedRevision`(`EditorSessionSnapshot.expectedRevision: number`), `api.getSceneTransitionSuggestions(projectId, sessionId)`.
- Produces: 로컬 값 `loadedSessionRevision: number | undefined`. 화면 모양은 그대로.

- [ ] **Step 1: 실패하는 시험을 쓴다**

`editor-workbench-route.test.tsx`에서 이 줄(그대로 찾는다, 한 번뿐):
```tsx
  it("accepts a local-first exchange as a memory source", async () => {
```
바로 **앞**에:
```tsx
  it("asks for transition suggestions once on first open, not again when the session arrives", async () => {
    // 2026-10-02 운영 빌드 실측: 첫 화면에서 transition-suggestions가 두 번(886ms·1140ms)
    // 나갔다. 세션을 읽기 전에 한 번, 읽은 뒤에 같은 판수로 또 한 번이었다.
    const suggestions = vi.spyOn(api, "getSceneTransitionSuggestions").mockResolvedValue({ suggestions: [] });

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });

    expect(suggestions).toHaveBeenCalledTimes(1);
    expect(suggestions).toHaveBeenCalledWith("project-a", "session-a");
  });

```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd apps/web && npx vitest run src/features/editor/workbench/editor-workbench-route.test.tsx -t "asks for transition suggestions once"`
Expected: FAIL `expected "spy" to be called 1 times, but got 2 times`.

- [ ] **Step 3: 최소 구현**

`EditorWorkbenchRoute.tsx`, 그대로 찾을 블록(파일에 한 번뿐 — 바로 아래에 `// \`session_revision\`을 의존값으로 쓴다` 주석이 온다):
```tsx
  useEffect(() => {
    if (!sessionId) {
      setTransitionSuggestions({ key: requestKey, items: [] });
      return;
    }
    let active = true;
```
→
```tsx
  // 세션을 다 읽은 뒤의 판수. 세션을 읽기 전(`undefined`)에 한 번, 읽은 뒤에 같은 판수로
  // 또 한 번 추천을 물어 첫 화면에서 같은 요청이 두 번 나갔다(2026-10-02 운영 빌드 실측).
  const loadedSessionRevision = state.key === requestKey ? state.session?.expectedRevision : undefined;
  useEffect(() => {
    if (!sessionId) {
      setTransitionSuggestions({ key: requestKey, items: [] });
      return;
    }
    if (loadedSessionRevision === undefined) return;
    let active = true;
```
그리고 같은 effect의 의존값 줄(파일에 한 번뿐):
```tsx
  }, [projectId, requestKey, sessionId, state.session?.expectedRevision]);
```
→
```tsx
  }, [projectId, requestKey, sessionId, loadedSessionRevision]);
```
(편집할 때마다 판수가 바뀌어 다시 묻는 동작은 그대로다 — 위 주석이 말하는 이유 그대로.)

- [ ] **Step 4: 통과를 확인한다**

Run: `cd apps/web && npx vitest run src/features/editor/workbench/editor-workbench-route.test.tsx -t "asks for transition suggestions once"` → `1 passed`

- [ ] **Step 5: 넓은 검증**

Run: `cd apps/web && npx vitest run src/features/editor/workbench/editor-workbench-route.test.tsx src/features/editor/workbench/editor-workbench.test.tsx` → 이미 알려진 실패 1건("gives the material dock back the same way, without needing a second click") 외 전부 통과.
Run: `cd apps/web && npx tsc --noEmit` → 0.
배선: `grep -n "loadedSessionRevision" apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx` → 정의 1 + 사용 2 = 3줄.
동작(실물)은 Task 17 Step 3 (h)에서 잰다.

- [ ] **Step 6: 커밋**

```bash
git add apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx
git commit -m "perf(editor): 첫 로드에서 전환 추천을 두 번 묻지 않는다

세션을 읽기 전에 한 번, 읽은 뒤 같은 판수로 또 한 번 물었다(운영 빌드
실측 886ms·1140ms). B-roll 목록 두 번은 소비자가 둘이라 남긴다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 14: 검토본 장면이 0개로 나오는 원인을 확정한다 (`2026-09-12-742e1924`)

**조사 Task다 — 코드를 고치기 전에 원인을 확정하고, 이 묶음에서 고칠지 기록만 할지를 아래 규칙으로 정한다.**

**검토자가 이미 확인한 것(2026-10-02, API 실물):**
- 세션 `editing_session_001`: `timeline_id: timeline_001`, `session_revision: 16`, 장면 **15**.
- 작업 `timeline_build_job_001`(→ `timeline_001`, 성공): 타임라인 `broll` 트랙 **15클립**, `review_status: approved`.
- `GET /api/projects/2026-09-12-742e1924/review-snapshots/timeline_build_job_001` → `segments` **0**, `review_flags` 0.
- 검토본의 `segments`는 세션도 타임라인도 아니고 **전사 `segments` 표**에서 온다: `packages/core-engine/src/videobox_core_engine/local_pipeline.py`의 `get_review_snapshot`이 `segments=self.store.list_segments(project_id=project_id)`를 넘기고, `list_segments`(`local_project_store.py:7516`)는 `SELECT … FROM segments WHERE project_id = ?`다(`PostgresProjectStore`는 이 메서드를 물려받는다).
- **가설:** 대본으로 시작하거나 `+ 새로 만들기`(빈 편집판)로 시작한 프로젝트는 전사(음성 인식)를 거치지 않아 `segments` 표가 비어 있다 → 검토 화면의 장면 목록이 빈다.

**Files:**
- Create(조사 스크립트, 커밋하지 않는다): 스크래치 디렉터리의 `review_segment_gap.py`
- Modify(기록): Task 16 결정 문서의 `## 따로 남긴 것` 칸(아래 Step 4), 또는 (규칙 A일 때) 해당 코드 파일

**Interfaces:**
- Consumes: `GET /api/projects`, `GET /api/projects/{id}/editing-sessions/latest`, `GET /api/projects/{id}/jobs`, `GET /api/projects/{id}/review-snapshots/{job_id}`, `GET /api/projects/{id}/timelines/{job_id}`.
- Produces: 프로젝트별 (세션 장면 수, 타임라인 클립 수, 검토본 장면 수) 표와 원인 판정.

- [ ] **Step 1: 재현한다(컨테이너가 켜져 있을 때)**

```bash
P=2026-09-12-742e1924; B=http://127.0.0.1:5173
curl -s $B/api/projects/$P/editing-sessions/latest | .venv/Scripts/python.exe -c "import json,sys; s=json.load(sys.stdin); print('session', s['timeline_id'], s['session_revision'], len(s['segments']))"
curl -s $B/api/projects/$P/review-snapshots/timeline_build_job_001 | .venv/Scripts/python.exe -c "import json,sys; d=json.load(sys.stdin); print('review', d.get('timeline_id'), len(d.get('segments') or []))"
```
Expected: `session timeline_001 16 15`(판수는 늘었을 수 있다), `review timeline_001 0`.

- [ ] **Step 2: 몇 프로젝트가 같은지 센다**

스크래치 디렉터리에 `review_segment_gap.py`를 만든다(저장소 안에 두지 않는다):
```python
import json, urllib.request, urllib.error
B = "http://127.0.0.1:5173"
def j(path):
    try:
        with urllib.request.urlopen(B + path, timeout=60) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError:
        return None
rows = []
for project in j("/api/projects")["projects"]:
    pid = project["project_id"]
    session = j(f"/api/projects/{pid}/editing-sessions/latest")
    if not session:
        continue
    jobs = j(f"/api/projects/{pid}/jobs") or []
    jobs = jobs.get("jobs", jobs) if isinstance(jobs, dict) else jobs
    timeline_jobs = [job for job in jobs if job.get("job_type") == "timeline_build" and job.get("status") == "succeeded" and job.get("output_ref") == session["timeline_id"]]
    if not timeline_jobs:
        continue
    job_id = timeline_jobs[-1]["job_id"]
    review = j(f"/api/projects/{pid}/review-snapshots/{job_id}") or {}
    rows.append((pid, project["name"], len(session.get("segments") or []), len(review.get("segments") or [])))
gap = [row for row in rows if row[2] > 0 and row[3] == 0]
print("검토본이 있는 프로젝트", len(rows), "/ 장면 있는데 검토본 0개", len(gap))
for row in gap:
    print(row)
```
Run: `.venv/Scripts/python.exe <스크래치 경로>/review_segment_gap.py`
결과 줄을 그대로 보고에 붙인다.

- [ ] **Step 3: 원인을 확정한다**

1. `grep -n "segments=self.store.list_segments" packages/core-engine/src/videobox_core_engine/local_pipeline.py` → `get_review_snapshot` 안의 1줄인지 확인.
2. `grep -rn "def save_segments\|INSERT INTO segments" packages/storage-abstractions/src/videobox_storage/local_project_store.py` → `segments` 표에 쓰는 자리를 찾고, 그 자리를 부르는 곳을 `grep -rn "<찾은 메서드 이름>(" packages services --include=*.py | grep -v test`로 센다. 전사(음성 인식)·분석 경로에서만 부르면 가설이 맞다.
3. Step 2의 0개 프로젝트가 **전부** 대본·빈 편집판으로 시작한 것인지 이름·만든 길로 확인한다(예: `내 목소리 오후 …`, `새 영상 오후 …`는 빈 편집판).
4. 프런트가 무엇을 그리는지: `grep -n "review.segments\|\.segments\.map\|segments.length" apps/web/src/features/review/TimelineReviewPage.tsx` → 장면 목록이 검토본 `segments`만 보는지 확인.

- [ ] **Step 4: 고칠지 기록만 할지 정한다(규칙)**

- **규칙 A — 이 묶음에서 고친다:** 원인이 **화면 쪽 표시만의 문제**(예: 검토본에 장면이 있는데 화면이 다른 필드를 읽는다)일 때. 그때는 TDD로 고친다: `apps/web/src/features/review/TimelineReviewPage.test.tsx`에 "장면이 N개면 N줄을 그린다" 시험을 먼저 쓰고(RED), 최소 수정, 같은 파일 전체 통과, 커밋 메시지 `fix(review): …` + 공통 꼬리줄.
- **규칙 B — 기록만 한다(가설이 맞으면 이쪽):** 원인이 **검토본을 만드는 자료원**(`list_segments` = 전사 표)이면 이 묶음(화면 정리) 밖이다. 검토본에 무엇을 담을지는 검토 승인(사람이 확인하는 자리)과 승인 무효화 규칙에 닿는 백엔드 계약 변경이라 owner 판단이 먼저다. 코드를 고치지 않는다. Task 16 결정 문서 끝에 아래 칸을 더한다:

```markdown
## 따로 남긴 것 — 검토본 장면 0개 (Task 14 조사)

- 증상: 장면이 있는 프로젝트의 검토 화면 장면 목록이 비어 있다. 예: `2026-09-12-742e1924` 세션 15장면, 타임라인 15클립, 검토본 0장면.
- 원인: 검토본 장면은 전사 `segments` 표(`store.list_segments`)에서 온다(`local_pipeline.py` `get_review_snapshot`). 대본·빈 편집판으로 시작한 프로젝트는 전사를 거치지 않아 표가 비어 있다.
- 범위: <Step 2 숫자> 프로젝트 중 <N>개.
- 고치는 방향(owner 결정 필요): 검토본 장면을 편집 세션의 장면에서 만들지, 전사 표가 비면 세션 장면으로 채울지. 승인 무효화(`source_session_revision`)와 함께 정해야 한다.
```
그리고 Task 17 Step 5의 갭에 "검토본 장면 0개 — 원인 확정, 수정은 owner 결정 대기"로 적는다.

- [ ] **Step 5: 커밋(규칙 A일 때만 이 Task에서 커밋한다. 규칙 B의 기록은 Task 16 커밋에 함께 들어간다)**

---

### Task 15: 2026-10-01에 문구가 바뀐 Playwright 여섯 파일을 이 묶음 뒤에 다시 돈다

**기준(검토자 실측):** main `ca39f2a7f`에서 `product-shell`·`job-recovery`·`media-recovery`·`z-script-first-vertical`·`editor-workbench`·`exact-preview` **35 passed (1.2분)**. 즉 2026-10-01 문구 변경(`b46a8a7e5`)으로 깨진 단언은 지금은 없다. 이 Task는 **이 묶음(Task 1~13)의 화면 변경 뒤에** 같은 여섯 파일 + 설정 주소를 밟는 `voice-tts-settings`를 돌려, 문구가 바뀐 자리만 단언을 고친다.

**Files:**
- Modify(필요할 때만): `apps/web/e2e/<실패한 파일>.spec.mjs`의 단언 문자열
- 고치지 않는다: 제품 코드, `apps/web/e2e/snapshots/*.png`, `playwright-snapshot-manifest.json`

**Interfaces:**
- Consumes: `npm run test:e2e`(`e2e/run-isolated.mjs` — 빈 포트를 골라 vite dev + 가짜 API로 돈다. 컨테이너와 무관).
- Produces: 통과 수, 고친 단언 목록(파일:줄, 전 문구 → 후 문구, 어느 커밋/Task가 바꿨는지).

- [ ] **Step 1: 돌린다**

Run(Git Bash):
```bash
cd apps/web && npm run test:e2e -- e2e/product-shell.spec.mjs e2e/job-recovery.spec.mjs e2e/media-recovery.spec.mjs e2e/z-script-first-vertical.spec.mjs e2e/editor-workbench.spec.mjs e2e/exact-preview.spec.mjs e2e/voice-tts-settings.spec.mjs --reporter=line
```
Expected: 시험은 전부 통과(기준 35 + voice-tts-settings). 끝의 `unexpected PNG: product-shell-mobile-menu-open.png` exit 1은 Global Constraints대로 무관.

- [ ] **Step 2: 스냅샷 PNG를 되돌린다(늘 한다)**

Run: `git status --short apps/web/e2e/snapshots`
바뀐 PNG가 있으면(Task 6의 접기 단추·Task 2·3의 카드 모양 때문에 `editor-workbench-*.png`·`product-shell-*.png`가 바뀌는 것이 정상이다) 파일 이름을 보고에 적고:
Run: `git checkout -- apps/web/e2e/snapshots/*.png`
Run: `git status --short apps/web/e2e/snapshots` → 0줄.

- [ ] **Step 3: 실패가 있으면 하나씩 가른다**

실패한 시험마다:
1. 실패 메시지에서 찾던 문구(예: `getByRole("button", { name: "…" })`, `getByText("…")`)를 뽑는다.
2. 그 문구가 어디서 바뀌었는지 찾는다: `git log -S "<옛 문구>" --oneline -- apps/web/src` → 2026-10-01 `b46a8a7e5` 또는 이 묶음의 Task 커밋이면 **문구 변경**이다.
3. 문구 변경이면 단언 문자열만 새 문구로 고친다. 그 외(요소가 없음·위치·시간 초과)는 **단언을 고치지 않는다** — 이 묶음이 동작을 깨뜨린 것이다. 그 Task로 돌아가 제품 코드를 고치고, 고친 뒤 이 Step 1부터 다시 돈다.
4. 시간 초과가 의심되면(기계 부하) 그 시험 하나만 `-g "<시험 이름>"`으로 두 번 더 돌려 셋 중 둘 이상 통과하면 기계 탓으로 적는다(기억: 포트 4173 점거자, 2026-09-21).

- [ ] **Step 4: 다시 돌린다**

Step 1을 다시 돌려 시험 전부 통과, Step 2를 다시 해 PNG 변경 0.

- [ ] **Step 5: 커밋(단언을 고쳤을 때만)**

```bash
git add apps/web/e2e/<고친 파일들>.spec.mjs
git commit -m "test(e2e): 바뀐 화면 문구에 단언을 맞춘다

<파일:줄 — 옛 문구 → 새 문구 — 바꾼 커밋> 목록. 동작 단언은 건드리지 않았다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
`git status --short`에 스냅샷 PNG가 없어야 한다.

---

### Task 16: 배치 변경 결정 기록 남기기

**Files:**
- Create: `docs/decisions/2026-10-02-screen-tidy-layout.ko.md`

**Interfaces:** 문서만. 동작 변경 없음(TDD 생략 — 문서 정리라 §1.1 예외).

- [ ] **Step 1: 문서를 쓴다**

`docs/decisions/2026-10-02-screen-tidy-layout.ko.md`(Task 17에서 잰 값을 `측정` 칸에 채운 뒤 커밋한다. 아직 못 쟀으면 그 칸에 "Task 17 측정 전"이라고 적지 말고 Task 17 뒤로 이 커밋을 미룬다):

```markdown
# 화면 정리 — 배치·크기·정보 구조 (2026-10-02, owner 승인)

승인 근거: `2026-10-02-audit-follow-up-decisions.ko.md`의 "화면 개선" 답
("프로젝트 카드 썸네일 · 여러 개 한 번에 보관 · 검토 화면 재생기 · `+ 새로 만들기`
막대 줄이기 + 편집기·설정 정리 · 그 밖에 필요하다고 판단되는 것도 모두").
실행 계획: `docs/superpowers/plans/2026-10-02-audit-g-screen-improvements.ko.md`.

## 바뀌지 않은 것

- **팔레트는 그대로다**(`2026-08-29`). 새 색 값을 하나도 쓰지 않았다 — 기존 토큰만.
- **시작하는 문은 하나**(`2026-09-05`). 막대가 카드 한 칸이 됐을 뿐, 단추는 하나이고
  접근 이름도 `+ 새로 만들기` 그대로다.
- **`/`는 `/projects`**. 주소는 하나도 지우지 않았다. 옛 설정 주소는 새 칸을 그린다.
- **영구 삭제는 늘지 않았다.** 여러 개 고르기는 보관만 한다.
- 단추 크기 32px(`2026-09-04` 캡컷 실측)는 그대로다. 줄인 것은 여백이다.

## 바뀐 것

| 화면 | 전 | 후 | 측정 |
|---|---|---|---|
| 프로젝트 카드 그림 | 73개 중 9개만 그림 | 첫 장면 그림, 없으면 빈 16:9 칸 | 그림 있는 카드 수, 카드 그림 칸 높이 종류 수 |
| `+ 새로 만들기` | 1120×80px 막대 | 카드 격자 첫 칸 | 칸 폭 = 카드 폭 |
| 여러 개 보관 | 하나씩 보관함 패널에서 | `여러 개 고르기` → 한 번 확인 → `되돌리기` | — |
| 검토 화면 재생 | `재생은 편집 화면에서 확인해 주세요.` | 편집기 재생기(`PreviewStage`) 그대로 | 영상 칸 크기 |
| 편집 작업판 머리 | 58px 고정 | 접기(이 기기에 기억) | 접힌 높이 |
| `가로·세로 비교` 띠(접힘) | 49px | 여백 축소 | 접힌 높이 |
| 설정 | 5칸 | 화면 · 유진 대화 · 정보 | — |
| 검토 반복 안내 | 카드 넷에 같은 문장 | 체크리스트 한 줄 | 문장 수 |
| 같은 충돌 카드 | 변형본마다 한 장 | 한 장(대상 표시) | 카드 수 |
| 유진 패널 스크롤 | 패널·기록 겹침 | 기록 하나 | 겹친 스크롤 수 |
| 출력 칸(375px) | 4칸 × 77px | 1칸 | 칸 폭 |
| 오디오 도크 | 가로 넘침 252/221px | 줄바꿈 | scrollWidth − clientWidth |
| 자료실 썸네일(이미 만든 것) | 장당 평균 0.30초, 546MB 원본 2.9초 | 원본을 다시 재지 않고 보냄 | 24장 두 번째 돌림 합계 |
| 편집기 첫 로드 | 전환 추천 요청 2번 | 1번(B-roll 2번은 소비자 둘이라 남김) | 요청 수 |
| 도크 끌기 성능 기준선 | median 107ms(2026-09-20) | Task 0 결과(바꿨으면 새 값, 안 바꿨으면 "유지") | 25샘플 중앙값·p95 |

## 함께 감수하는 것

- Playwright 스냅샷 PNG(`apps/web/e2e/snapshots/`)는 이 변경 뒤의 화면과 다르다. 다시
  쓰는 것은 owner가 차이를 본 뒤의 일이다(`e2e/snapshots/README.ko.md`).
- `이 답을 대본으로 쓰기`는 이제 바로 앞 내 말에 `대본·원고·내레이션…` 낱말이 있어야
  뜬다. 낱말 없이 "그거 다시 써 줘"라고 하면 안 뜬다 — 입력칸에 붙여 넣는 길
  (`이 글을 대본으로 쓰기`)은 그대로 있다.
- 유진이 프로젝트를 보관하는 길은 묶음 F에서 연다(이 묶음 범위 밖).
```

- [ ] **Step 2: 커밋(Task 17의 측정값을 채운 뒤)**

```bash
git add docs/decisions/2026-10-02-screen-tidy-layout.ko.md
git commit -m "docs(decisions): 2026-10-02 화면 정리 배치 변경 기록

팔레트·시작 문·주소는 그대로, 배치·크기·정보 구조만 바꿨다.
전후 측정값을 함께 남긴다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 17: 마지막 검증 — 실제 화면에서 재고, 넓게 돌리고, 푸시

**Files:** 없음(측정·보고). 측정값은 Task 16 문서의 `측정` 칸에 적는다.

- [ ] **Step 1: 넓은 자동 검증**

Run: `cd apps/web && npx tsc --noEmit` → 0.
Run: `cd apps/web && npx vitest run` → 이미 알려진 실패 1건 외 전부 통과. 실패가 더 있으면 그 시험이 이 묶음의 변경 때문인지 `git stash`로 비교하지 말고 **이전 커밋에서 같은 시험을 돌려** 가린다(기억 메모: 기계 상태로 실패하는 시험이 있다).
Run: `npm --prefix apps/web run build` → 성공.
Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_workspace_summary_scene_thumbnail.py tests/test_api.py -k "workspace_summary or thumbnail" tests/test_editor_ui_source_provenance.py tests/test_project_rename.py` → 통과.
Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_library_thumbnail_cache_hit.py tests/test_api_library_assets.py tests/test_library_image_assets.py` → 통과.
Run: `cd apps/web && node --test e2e/support/release-gates.test.mjs` → `ℹ fail 0`.

- [ ] **Step 2: 컨테이너 재빌드**

Run(PowerShell): `.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild`
Expected: 끝에 준비 완료(FAIL 없음). 브라우저에서 `http://127.0.0.1:5173/projects`를 열고 `Ctrl+F5` 한 번.

- [ ] **Step 3: 1440×900에서 잰다**

브라우저 창을 1440×900으로 맞추고 각 화면에서 아래 JS를 콘솔(또는 브라우저 도구의 JS 실행)로 돌려 값을 적는다.

(a) `/projects` — 카드 그림·만들기 칸:
```js
const main = document.querySelector('.vb-product-main');
for (let y = 0; y < main.scrollHeight; y += 400) { main.scrollTo(0, y); await new Promise(r => setTimeout(r, 250)); }
await new Promise(r => setTimeout(r, 2000));
const thumbs = [...document.querySelectorAll('.vb-catalog-card__thumb')];
const tile = document.querySelector('.vb-catalog-create').getBoundingClientRect();
const card = document.querySelector('.vb-catalog-card').getBoundingClientRect();
({ cards: thumbs.length, withPicture: thumbs.filter(t => t.dataset.hasPicture === 'true').length,
   thumbHeights: [...new Set(thumbs.map(t => Math.round(t.getBoundingClientRect().height)))],
   tile: [Math.round(tile.width), Math.round(tile.height)], card: [Math.round(card.width), Math.round(card.height)],
   tileIsFirst: document.querySelector('.vb-catalog-grid').firstElementChild.classList.contains('vb-catalog-create'),
   noHScroll: document.documentElement.scrollWidth === document.documentElement.clientWidth })
```
기대: `withPicture`가 **19 이상**(검토자 재측정 기준 약 21 — 옛 9 + 첫 장면 그림 15 − 겹침 3; 프로젝트 수가 바뀌었으면 그 차이를 함께 적는다), `thumbHeights` 값 **하나**, `tile[0] === card[0]`, `tileIsFirst: true`, `noHScroll: true`. 화면을 눈으로도 본다(스크린샷).

(b) `/projects` — 여러 개 보관을 실제로 밟는다: `여러 개 고르기` → 시험용 프로젝트 둘(예: `씽킹확인 1789092292`, `씽킹확인 1789092305`) `고르기` → `보관하기` → `2개 보관 확인` → `2개를 보관했어요.` 확인 → `되돌리기` → 둘이 목록에 돌아왔는지 확인. **대표님 실제 프로젝트(`셀러 교육 …`, `노마드…`)는 고르지 않는다.** 마지막에 보관함을 열어 두 개가 남아 있지 않은지 본다.

(c) `/projects/0907-b26195af/review` — 재생기:
```js
await new Promise(r => setTimeout(r, 4000));
const v = document.querySelector('.vb-outputs-preview video');
const stage = document.querySelector('.vb-outputs-preview .vb-preview-stage');
({ hasStage: !!stage, video: v ? [Math.round(v.getBoundingClientRect().width), Math.round(v.getBoundingClientRect().height), v.src.slice(-40)] : null,
   status: document.querySelector('.vb-outputs-preview .vb-preview-stage__status')?.textContent,
   repeats: (document.querySelector('.vb-product-main').innerText.match(/모두 마친 뒤/g) || []).length,
   conflictCards: document.querySelectorAll('.vb-editor-variants__conflicts').length })
```
기대: `hasStage: true`. 미리보기가 있으면 `video` 폭 ≤ 768(48rem)·높이 > 0이고 `재생 / 일시정지`를 눌러 실제로 재생되는지(재생 위치 숫자가 늘어나는지) 본다. 없으면 `미리보기 새로 만들기`를 누르고 상태 문구가 `미리보기를 준비하고 있어요.`로 바뀐 뒤 몇 초~수십 초 안에 영상이 뜨는지 본다(화면이 침묵하면 안 된다). `repeats: 0`. `/projects/2026-09-12-742e1924/review`에서 `conflictCards`가 **1**이고 `가로 영상 · 세로 영상`이 보이는지.
스페이스 하나에 재생기 하나: 완성본이 있는 프로젝트의 검토 화면에서 (1) 빈 곳을 한 번 누르고 스페이스 → 편집본 미리보기만 재생/정지, (2) `완성본 재생` 영상을 한 번 눌러 포커스를 준 뒤 스페이스 → 그 영상만 재생/정지하고 편집본 미리보기의 `paused`는 그대로인지 JS로 잰다:
```js
const preview = document.querySelector('.vb-outputs-preview video'); const final = document.querySelector('video[aria-label="완성본 재생"]');
final?.focus(); const before = preview?.paused; final?.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true }));
await new Promise(r => setTimeout(r, 300)); ({ previewUnchanged: preview?.paused === before, hasFinal: !!final })
```
기대: `previewUnchanged: true`. 완성본이 있는 프로젝트가 없으면 "검증 못 함"으로 적는다(시험은 Task 5에서 초록).

(d) `/projects/0907-b26195af/editor` — 머리·띠·유진 스크롤·오디오 도크:
```js
await new Promise(r => setTimeout(r, 5000));
const h = el => Math.round(document.querySelector(el).getBoundingClientRect().height);
const before = { toolbar: h('.vb-editor-workbench__toolbar'), variants: h('.vb-editor-variants'), body: h('.vb-editor-workbench__body') };
[...document.querySelectorAll('button')].find(b => b.textContent.includes('도구줄 접기'))?.click();
await new Promise(r => setTimeout(r, 800));
const after = { toolbar: h('.vb-editor-workbench__toolbar'), variants: h('.vb-editor-variants'), body: h('.vb-editor-workbench__body') };
const audioTab = [...document.querySelectorAll('.vb-editor-workbench__rail [role=tab]')].find(t => t.textContent.includes('오디오'));
audioTab.click(); await new Promise(r => setTimeout(r, 1500));
const dock = document.querySelector('.vb-editor-workbench__dock--left');
[...document.querySelectorAll('button')].find(b => b.textContent.trim() === '유진')?.click();
await new Promise(r => setTimeout(r, 1500));
const scrolling = e => /(auto|scroll)/.test(getComputedStyle(e).overflowY) && e.scrollHeight > e.clientHeight + 4;
const history = document.querySelector('.vb-yujin-panel .vb-editor-right-dock__history');
let nested = 0; for (let p = history?.parentElement; p; p = p.parentElement) if (scrolling(p)) nested++;
({ before, after, audioDockOverflow: dock.scrollWidth - dock.clientWidth, yujinHistoryScrollingAncestors: nested,
   panel: [document.querySelector('.vb-yujin-panel').clientHeight, document.querySelector('.vb-yujin-panel').scrollHeight] })
```
기억 칸 단추가 닿는지도 본다: `const mem=document.querySelector('.vb-yujin-panel > .vb-editor-workbench__summary'); mem.scrollTop=mem.scrollHeight;` 뒤 기억 칸의 마지막 단추가 `mem.getBoundingClientRect()` 안에 들어오는지(잘리지 않는지) 잰다.
기대: `after.toolbar ≤ 44`(전 58), `after.variants ≤ 42`(전 49), `after.body`가 `before.body`보다 큼. `audioDockOverflow ≤ 1`(전 31). `yujinHistoryScrollingAncestors: 0`(전 1). 0이 아니면 **보고하고 멈춘다** — Task 10의 기억 칸 상한(6rem)을 4rem으로 낮추는 것이 다음 후보지만, 그건 측정값을 owner 보고에 붙인 뒤 판단한다. 다시 열었을 때(새로고침) 머리가 접힌 채인지도 본다. 끝나면 `도구줄 펼치기`로 원래대로 돌려 둔다.

(e) `/settings/appearance` — 칸 셋(`화면`·`유진 대화`·`정보`). `/settings/voice`·`/settings/ai-privacy`·`/settings/output`·`/settings/general`을 차례로 열어 복구 화면이 아닌지 본다.

(f) 유진 대화(편집기, **새 세션 프로젝트**에서): "B-roll 추천해 줘"를 보내 긴 답 아래 `이 답을 대본으로 쓰기`가 **없고**, "30초짜리 대본 하나 써 줘"를 보내 답 아래에 **있는지** 본다. 유진 답이 오지 않으면 `lms ps`로 GPU 경합부터 확인한다(기억 메모). 유진이 안 되는 상태면 이 항목은 "검증 못 함"으로 적는다 — 시험(Task 8)은 초록이다.

(g) 자료실 썸네일(Task 12) — 컨테이너를 다시 지은 뒤, 저장소 루트에서:
```bash
curl -s "http://127.0.0.1:5173/api/library/assets?limit=24" | .venv/Scripts/python.exe -c "import json,sys,time,urllib.request as u; a=[x for x in json.load(sys.stdin)['assets'] if x.get('thumbnail_url')]; [u.urlopen('http://127.0.0.1:5173'+x['thumbnail_url']).read() for x in a]; t=time.perf_counter(); [u.urlopen('http://127.0.0.1:5173'+x['thumbnail_url']).read() for x in a]; print(len(a), 'thumbs, second pass', round(time.perf_counter()-t,2), 's')"
```
(첫 번째 돌림은 아직 없는 썸네일을 만들게 두고, 두 번째 돌림을 잰다.) 기대: 두 번째 돌림 24장 합계 **1.5초 이하**(전: 장당 평균 0.30초 → 약 7초). 브라우저 `/library`에서 첫 화면 그림이 다 뜨는지 스크린샷으로 본다.

(h) 편집기 첫 로드 요청 수(Task 13) — `/projects/0907-b26195af/editor`를 새로 열고 10초 뒤:
```js
const e = performance.getEntriesByType('resource').filter(x => x.name.includes('/api/'));
const count = s => e.filter(x => x.name.includes(s)).length;
({ transitionSuggestions: count('/transition-suggestions'), brollVideo: count('/assets/broll-video') })
```
기대: `transitionSuggestions: 1`(전 2), `brollVideo: 2`(소비자 둘 — 의도적으로 남김, Task 13 참고).

- [ ] **Step 4: 375×812에서 잰다**

창을 375×812로 바꾸고 `/projects`, `/projects/2026-09-12-742e1924/review`, `/settings/about`, `/projects/0907-b26195af/editor`에서:
```js
await new Promise(r => setTimeout(r, 3500));
({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,
   outputCols: document.querySelector('.vb-outputs-grid') ? getComputedStyle(document.querySelector('.vb-outputs-grid')).gridTemplateColumns : null,
   tile: document.querySelector('.vb-catalog-create') ? Math.round(document.querySelector('.vb-catalog-create').getBoundingClientRect().height) : null })
```
기대: 모든 화면에서 `sw === cw`. 검토 화면 `outputCols`가 **한 값**(예: `"343px"`). `/projects`의 `tile`이 64 안팎(4rem). 스크린샷을 남긴다.

- [ ] **Step 5: 검증 넷과 갭을 적는다(owner 보고용, 한국어 쉬운 말)**

- **갭**: 요약 계획서 G1~G5 각 줄과 이 계획 Task 1~11을 대조한다. 안 한 것을 적는다. 최소한 다음은 **안 했다**고 적는다: 유진의 프로젝트 보관(묶음 F), 검토 장면 목록이 0개로 나오는 문제의 **수정**(Task 14에서 원인을 확정하고 기록만 했으면 그 기록 위치), Playwright 스냅샷 재생성(owner 검토 필요), 편집 작업판 머리 접기의 실제 이득이 작다는 사실(측정값).
- **역방향**: Step 2~4에서 컨테이너+브라우저로 밟은 것과 결과.
- **동작**: Step 3·4의 숫자 그대로(전/후).
- **배선**: 아래 grep 결과 줄 수를 그대로 적는다.
  - `grep -n "_scene_thumbnail_url" services/api/src/videobox_api/routers/projects.py`
  - `grep -n "CatalogCardThumb\|archiveSelected\|undoBulkArchive" apps/web/src/app/AppRouter.tsx`
  - `grep -rn "showPlayer" apps/web/src --include=*.tsx | grep -v test`
  - `grep -n "toggleToolbarCollapsed" apps/web/src/features/editor/workbench/EditorWorkbench.tsx`
  - `grep -rn "isScriptReply\|groupVariantConflicts" apps/web/src | grep -v test`
  - `grep -n "_cached_derivative_path" services/api/src/videobox_api/routers/library_assets.py`
  - `grep -n "loadedSessionRevision" apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- §10.13 문구 점검: `cd apps/web && npx vitest run src/user-copy-policy.test.ts` 결과.

Task 16 문서의 `측정` 칸을 Step 3·4 값으로 채우고 Task 16 Step 2 커밋을 한다.

- [ ] **Step 6: 전체 backend 시험(단독, 약 50분)**

Run(다른 무거운 일을 돌리지 않는 상태에서): `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --ignore=tests/test_mcp_server.py`
Expected: 이미 알려진 실패 1건(`test_owner_ready_script.py::test_smoke_timeout_kills_the_child_tree_and_returns_bounded_failure`) 외 통과. 다른 실패가 있으면 트레이스백을 남기고 그 시험을 단독으로 다시 돌려 이 묶음 탓인지 가린다.

- [ ] **Step 7: 푸시**

먼저 확인만 한다:
Run: `git status --short` → 이 묶음 파일이 다 커밋됐는지(남은 것은 `.anchor/` 같은 원래 있던 미추적 파일뿐).
Run: `git log --oneline origin/main..HEAD` → 이 묶음 커밋 17개 안팎(Task 0·12·13·14·15 포함, 기록만 한 Task는 문서 커밋).
결과를 본 **다음에**, 따로:
Run: `git push origin main`
(강제 푸시 금지. 거절되면 `git pull --rebase` 후 충돌을 풀고 Step 1을 다시 돈 뒤 푸시. **도구 권한이 푸시를 막으면 우회하지 말고 멈춘다** — 다른 명령·다른 셸로 돌려 보지 않는다. owner에게 "`D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`에서 `git push origin main`을 실행해 주시거나, 허용 규칙 `Bash(git push origin main)`을 추가해 주세요"라고 보고한다.)

---

## 계획서 자체 점검 메모

- 요약 계획(`2026-10-02-audit-follow-up-plan.ko.md`) 묶음 G 다섯 줄 → G1: Task 1·2, G2: Task 4, G3: Task 5, G4: Task 3·6·7, G5: Task 8·9·10, "그 밖에": Task 11. 결정 기록: Task 16. 검증: Task 17.
- 검토(2026-10-02)에서 더한 것: Task 0(성능 게이트 기준선 재측정 + 깨진 채 남아 있던 단위 시험), Task 12(자료실 썸네일 — 서버가 느린 원인, 화면은 이미 lazy·24장 상한), Task 13(편집기 첫 로드 중복 요청 — 전환 추천만 고치고 B-roll은 남김), Task 14(검토본 장면 0개 원인 확정·고칠지 규칙), Task 15(Playwright 여섯 파일 + voice-tts-settings 재실행, 스냅샷 PNG 되돌리기). 옛 Task 12·13은 Task 16·17로 번호만 바뀌었다.
- 요청된 `GET /api/projects/{id}/thumbnail` 신설은 **하지 않는다** — 같은 일을 하는 길(`workspace-summary.thumbnail_url` + 자산 썸네일 재생성)이 이미 있어서다(재사용 게이트 표).
- `가로·세로 비교` 띠 접기·기억은 **이미 있다**. 이 계획은 그 사실을 적고, 접힌 높이만 줄인다.
