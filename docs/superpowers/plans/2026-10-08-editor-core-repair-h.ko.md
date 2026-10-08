# 계획 H — 편집기 핵심 수리 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> 실행 모델은 **Claude Sonnet**. Task 하나씩, 앞 Task 커밋 위에서. 이 문서의 Global Constraints가 모든 Task에 걸린다.

**Goal:** 대표님이 편집기에서 "누른 것이 그대로 된다"를 믿을 수 있게 한다 — 클립을 누르면 그 장면이 잡히고, 트랙 단추가 마우스로 눌리고, 가장자리를 끌어 자르고, 0907에서도 자르기·옮기기가 저장되고, 편집 중에 화면이 비거나 멈추지 않고, 모든 단추가 바로 반응한다.

**Architecture:** 새 편집기·새 재생기를 들이지 않는다(채택 스파이크 판정: 우리 순수 함수는 이미 맞고, 결함은 **화면이 그것을 부르는 방식**에 있다). 고치는 곳은 셋이다. (1) 화면 배선 — `EditorWorkbench.tsx`의 "재생 시각 → 고르기", `TimelineDock.tsx`의 트랙 머리·손잡이·붙기·눈금, `EditorWorkbenchRoute.tsx`의 미리보기 기다리기. (2) 서버 생성기 — `materialize_editing_session_timeline`이 저장된 편집판 속 **세션 투영 클립**(`session-…`)을 원본으로 다시 투영해 오버레이가 18~22개로 불어나는 근본 원인. (3) 공정 — 가짜 API가 아니라 **진짜 백엔드 + 고정 시험 프로젝트**로 도는 e2e 묶음을 만들어, 이번 결함들이 모든 시험을 통과하고 새어 나간 길을 막는다.

**Tech Stack:** React 19 + TanStack Router + shadcn `Button` + Tailwind utilities, vitest + Testing Library(jsdom), Playwright(chromium), FastAPI + pytest(`.venv`), ffmpeg(시험 매체 생성), Docker 컨테이너(nginx 앞문 `http://127.0.0.1:5173`).

**Spec:** `docs/superpowers/2026-10-08-editor-ui-audit.ko.md`(실사용 점검, 증거 그림 `docs/superpowers/audit-evidence/2026-10-08-editor-ui/`) + `docs/superpowers/2026-10-08-timeline-adoption-spike.ko.md`(채택 스파이크 — Task 3·7·8·9·10·12에 접어 넣었다).

---

## 실측 기록 (2026-10-08, 계획 작성 중 코드·서버를 읽어 확정한 원인)

| 결함(점검 번호) | 확정한 원인 | 근거 |
|---|---|---|
| 클립 클릭 → 앞 장면(3-1) | 클립을 누르면 `onPlaybackSeek(장면 시작)` → 재생기가 `seeked/timeupdate`로 `1.899064`(백만분의 1초 버림)를 올려 보내고 → `seekPlayback`이 **고른 것을 버리고** `activeSegmentIdAt`(`start <= t`)로 다시 찾는다 → 시작 `1.8990646`보다 작아 앞 장면. 스파이크 실측: 0907 7장면 중 **5개**(프레임 버림 모형 6개) 오선택, id 우선 규칙으로 0 | `EditorWorkbench.tsx` `const seekPlayback`, `preview-stage.tsx` `updateTimeline`, 스파이크 §3(나) |
| 0907 오버레이 중복 → 자르기·옮기기 422(3-3) | **저장된 편집판 `timeline_002.json`에 세션 투영 클립이 박혀 있다** — 오버레이 트랙 8개(`session-overlay-…`, 같은 id 두 번씩) + B-roll 7개(`session-broll-…`). 2026-09-20 되돌린 커밋 `2183eec0`이 materialize 결과로 `tracks`를 덮어쓴 흔적이다(인계 `2026-09-20-timeline-manual-editing-bug-hunt.ko.md` "부수 피해"). materialize는 그 클립을 **원본 클립처럼** 다시 투영한다: 일반 트랙 고리가 부모 장면(`timeline_001:001`)의 오버레이를 그 부모를 가리키는 **모든 자식 조각**(장면 5~7 포함)에 통째로 깔고(`covered=[]` — 오버레이는 덮어쓰기 칸이 없다), 이름이 겹치면 `@track_overlay-N`을 붙이고, 그 다음 세션 오버레이 고리가 같은 `session-overlay-…-0-0`을 **충돌 검사 없이** 또 붙인다 → 같은 id 2개 → `collect_timeline_placements`가 `timeline_placement_duplicate` | 런타임 파일 직접 읽기(읽기만): 59개 프로젝트 중 `session-` 클립을 품은 편집판은 **0907의 `timeline_002.json` 하나**, 중복 id 파일도 그 하나. `GET …/playback-manifest` 오버레이 18개 |
| 편집 대상 3,581개(3-6) | 위 중복 id가 `inspectorRegistry.projectInspectorTargets`의 `overlay:${clip.clipId}`로 그대로 가서 `<option key>`가 겹친다. 캡션은 계보(`segmentId`)로 걸러 형제 자막 5개가 `연결 캡션`으로 같이 뜬다 | `inspectorRegistry.ts` `projectInspectorTargets`, `RightDock.tsx` `<option key={target.id}` |
| 영어 오류 화면(3-6) | `Something went wrong! / Show Error`는 TanStack Router 기본 `CatchBoundary`다. `createRouter`에 `defaultErrorComponent`가 없다. 우리 `ErrorBoundary`(한국어)는 그 바깥이라 닿지 않는다 | `node_modules/@tanstack/react-router/dist/esm/CatchBoundary.js`, `AppRouter.tsx` `createAppRouter` |
| 트랙 단추 마우스로 죽음(3-4) | 머리 뭉치가 클립 층 위에 떠 있고, 0초 근처 클립이 있으면 `pointer-events:none`으로 양보(`LANE_HEADER_DEAD_ZONE_PX=180`) | `TimelineDock.tsx` `laneNeedsClipAccess`, 스파이크 §3(가) 3/3 |
| 미리보기 2분 멈춤·CPU 78%(3-2) | `pending/running`이면 1.2초마다 `refreshToken`을 올리고, `refreshToken`이 **세션(830KB — 그중 `history` 817KB)+매니페스트+변형본** 세 요청을 다시 부른다. 다음 틱은 응답을 **기다리지 않고** 1.2초 뒤 또 온다 → 응답이 1.2초보다 느리면 겹치고, 뒤 요청이 앞 응답을 무효로 만들어(`manifestOperationId`) **영영 화면이 안 바뀐다**. 가벼운 상태 길 `GET /api/projects/{id}/exact-previews/{generation_id}`가 이미 있는데 안 쓴다. 화면은 세션 `history`를 읽지도 않는다 | `EditorWorkbenchRoute.tsx` `const poll = window.setTimeout`, `routers/outputs.py` `get_exact_preview`, 0907 세션 응답 키별 크기 실측 |
| 빼기 1.7초 구멍 + `빈 구간 0개`(3-5) | `update_segment_cut_action`은 표시만 바꾸고 뒤 장면을 안 당긴다. 매니페스트 `gap_slots`는 "자산 빈칸"만 담아 뺀 자리를 세지 않는다 | `editing_session.py` `def update_segment_cut_action`, `editor_playback_manifest.py` `_gap_contract` |
| 열면 500인 두 프로젝트(§5) | `EditingSessionSegmentResponse`의 `cut_action: str`·`review_required: bool`이 **기본값 없는 필수**라, 옛 모양 장면(키 자체가 없음)에서 검증 실패. 그 뒤에도 두 세션은 **없는 편집판**(`timeline-longform` 등)을 가리킨다 — `timelines/` 폴더가 비어 있다(시험 스크립트가 세션만 쓴 흔적). 매니페스트는 404 `Timeline not found` | 런타임 파일, `curl` 500/404 |
| 단추가 반응 없음(owner 2026-10-08 입력) | 편집 결과 문장은 타임라인 맨 아래 작은 글씨(`편집 저장 상태`) 한 곳뿐이고, `sonner` `Toaster`는 **어디에도 마운트되지 않았다** | `grep -rn "Toaster" apps/web/src` → 정의 1곳, 사용 0곳 |
| 자료 카드 `자료 N`·`확인 중`(3-10) | 6799f952b 이후 **새로** 가져온 자산은 `metadata.title`이 붙는다(0907의 마지막 2개 확인). 그 전에 가져온 3개는 `source_library_asset_id`만 있고 이름이 없다. `brollStatus`는 분석 정보가 없으면 `확인 중 · 검토 상태 확인 중`을 지어낸다 | `GET …/assets/broll-video` 실측, `editorAssetProjection.ts` `function brollStatus` |

---

## 계획 G·B–F·I와의 경계 (중복 실행·충돌 방지)

### 점검 항목 → 담당

| 점검 항목 | G에 있었나 | H에서 |
|---|---|---|
| 3-1 클립 → 앞 장면 | 없음 | **Task 3** |
| 3-2 미리보기 폴링·빈 화면 | 없음(G Task 13은 첫 로드 전환 추천 두 번만) | **Task 11** — G Task 13을 **흡수**한다 |
| 3-2 실시간 재생 | 없음 | **제외**(큰 기능, 따로 결정) |
| 3-3 0907 중복 → 422 | 없음 | **Task 4**(생성기) + **Task 5**(저장 데이터 도구, 적용은 owner 결정) |
| 3-4 트랙 머리 | 없음 | **Task 7** |
| 3-5 빼기 구멍 | 없음 | **Task 12**(두 정책, 당기기는 owner 결정 뒤) |
| 3-6 목록 폭증·#185·영어 오류 | 없음 | **Task 6** |
| 3-7 기본 단추 모양·Arial | 없음 | **제외 → 계획 I**(디자인 토큰·글꼴·크기) |
| 3-8 손잡이 | 없음 | **Task 8**(+붙기 Task 9) |
| 3-9 1280×720 | **G Task 6**(머리 접기)이 일부 | **Task 13** — G Task 6을 **흡수**한다 |
| 3-9 눈금 붙음 | 없음 | **Task 10** |
| 3-10 자료 이름·상태 | 없음 | **Task 14** |
| 작은 문구(백틱·Clean/Highlight·Close·영어 오류) | 없음 | **Task 14**(영어 오류는 Task 6) |
| 열면 500인 두 프로젝트 | 없음 | **Task 15** |
| 죽은 단추·반응 없음(owner 입력) | 없음 | **Task 2**(재고 조사) + **Task 16**(고치기·지우기·즉시 반응) |
| G Task 0(도크 끌기 성능 기준선) | G가 "화면을 바꾸기 **전에**" 하라고 못박음 | H가 편집기를 먼저 바꾸므로 **Task 0에서 G Task 0을 그대로 실행**(흡수) |
| G Task 11-3(오디오 도크 가로 넘침) | G | 그대로 G(또는 I) |
| G Task 15(문구 바뀐 Playwright 재실행) | G | 그대로 G. H는 자기 Task마다 e2e를 돈다 |

**H가 흡수하는 G Task: 0, 6, 13.** Task 18이 G 계획서 머리와 총괄 문서에 그 사실을 적는다 — G 실행자는 그 셋을 건너뛴다.

### 실행 순서

H → B–F(유진) → G(남은 것) — 총괄(`2026-10-02-audit-00-master.ko.md`)의 "B–F → G" 앞에 H가 끼어든다. B–F는 H가 바꾼 파일을 **문자열 앵커**로 따라온다.

### 같이 고치는 파일 (앵커는 줄 번호가 아니라 **문자열**로 찾는다 — 총괄 §2 규칙)

| 파일 | H의 Task | 다른 계획 |
|---|---|---|
| `apps/web/src/features/editor/workbench/EditorWorkbench.tsx` | 3, 13 | B–F, G6(흡수) |
| `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx` | 11, 14, 15, 16 | B–F, G13(흡수) |
| `apps/web/src/features/editor/workbench/editor-workbench.test.tsx` | 3 | B–F |
| `apps/web/src/api.ts` | 11, 15 | A(끝남), B–F |
| `apps/web/src/lib/pollJob.ts` | 11 | B–F |
| `packages/core-engine/src/videobox_core_engine/editing_session.py` | 12 | B–F(유진 적용기 `SetCutActionOperation` 자리) |
| `services/api/src/videobox_api/models.py` | 15 | B–F |
| `services/api/src/videobox_api/routers/editing_session.py` | 11 | B–F |
| `packages/storage-abstractions/src/videobox_storage/local_project_store.py` | 4 | B–F |
| `apps/web/src/styles/editor-workbench.css` | 7, 8, 10, 13 | G6(흡수)·G11, **I** |
| `apps/web/src/user-copy-policy.test.ts` / `task22-parity-owners.test.ts` | (돌리기만) | B–F, G |
| `docs/oss/editor-ui-source-map.json` | 10, 14 | A·G(ProductShell 해시) |

**H는 `YujinPanel.tsx`·`OutputsPage.tsx`·`routers/library_assets.py`·`rightDockTypes.ts`를 건드리지 않는다**(B–F 몫). 유진 쪽 배선이 필요한 곳(빼기 정책)은 **서버 기본값 한 곳**으로 풀어 유진 코드가 그대로 같은 정책을 탄다(Task 12).

### 계획 I(`docs/superpowers/plans/2026-10-08-design-system-and-wiring-i.ko.md`, 작성 예정)와의 경계

- **I의 것(H는 손대지 않는다):** 글꼴(`button { font: inherit }` 포함), 글자 크기 척도, 단추 높이·모서리 통일, 색조(tone), 공용 컴포넌트 정리, 전반적 밀도(캡컷처럼 작게), 공용 "반응(feedback)" 표현의 최종 모양.
- **H의 것:** 동작과, 컨트롤을 **쓸 수 있게 하는 최소 배치**뿐 — 트랙 머리 칸, 가장자리 손잡이의 잡는 자리, 눈금 간격, 작업판이 뷰포트 안에 들어가기.
- **I가 H의 로직을 안 건드리고 촘촘하게 만들 수 있게**, H가 새로 만드는 크기는 전부 CSS 변수로 둔다(기본값은 `editor-workbench.css`의 `.vb-editor-workbench` 규칙에): `--vb-timeline-header-w`(머리 칸 폭), `--vb-timeline-lane-h`(트랙 높이), `--vb-trim-handle-w`(손잡이 보이는 폭), `--vb-trim-hit-w`(손잡이 잡는 폭), `--vb-ruler-label-min-gap`(눈금 글자 최소 간격). JS가 필요한 값(트랙 높이·눈금 간격)은 `readCssPixels`로 **계산값을 읽어** 쓴다 — I가 CSS 값만 바꿔도 좌표가 따라간다.
- **반응 표시:** H는 `features/editor/workbench/editorFeedback.ts` 한 파일(이음매)로만 알린다. 지금은 기존 `sonner` 토스트를 쓰고, I가 공용 반응 모양을 정하면 **이 파일 하나**만 바꾼다.

---

## Global Constraints

- 최상위 지침은 `CLAUDE.md`. 작업은 메인 체크아웃 `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`(브랜치 `main`)에서 한다. Task 시작마다 `git status --short`가 깨끗한지(`?? .anchor/`는 무관), `git log -1`이 앞 Task 커밋인지 본다. 아니면 멈추고 보고.
- **앵커는 문자열로 찾는다.** 이 계획이 인용한 옛 코드 문자열이 그대로 있으면 진행, 없으면 **멈추고 보고**(짐작해서 고치지 않는다). 줄 번호는 참고일 뿐이다.
- **RED를 실제로 본다.** RED 시험이 처음부터 통과하면 멈추고 보고. RED/GREEN 단계에서는 그 시험 하나만 돈다(`CLAUDE.md` §3).
- 시험 명령: 백엔드 `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider <파일>::<시험>`(저장소 루트). 맨 `pytest` 금지. 웹 `cd apps/web && npx vitest run <파일>`(저장소 루트에서 돌리면 jsdom이 깨진다). 타입 `cd apps/web && npx tsc --noEmit`. 빌드 `npm --prefix apps/web run build`.
- 전체 pytest는 약 45분이라 **Task 18에서 단독으로 한 번**: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --ignore=tests/test_mcp_server.py`(맨 실행은 수집 오류로 0건 — 기억 메모).
- **팔레트는 바꾸지 않는다**(`2026-08-29`). 새 CSS는 기존 토큰(`--vb-*`, `--border`, `--card`, `--vb-accent` …)만. 새 색 값(`#…`, `rgb(…)`) 금지.
- **없는 기능의 단추는 만들지 않는다**(`2026-08-30`). 죽은 단추는 이어 주거나 **지운다**.
- 화면 문구 §10.13: 명사형 이름표, 필요한 곳만 짧은 해요체. `provider`·`runtime`·`model`·`job`·`revision`·`pipeline`·`시스템`·`모델`·`파이프라인` 금지, 영어 단어 금지. UI Task마다 `cd apps/web && npx vitest run src/user-copy-policy.test.ts`.
- **유진 대화 기능·모션은 범위 밖.** `YujinPanel.tsx`·유진 의도·적용기·프로필 안내문을 고치지 않는다. 다만 서버 편집 함수의 기본 동작이 바뀌면(Task 12) 유진도 같은 함수를 타므로 그 사실을 보고에 적는다.
- **owner 실제 프로젝트의 저장 데이터를 기본 경로에서 고치지 않는다.** 0907 `timeline_002.json` 수리는 Task 5의 도구가 **미리보기(dry-run)만** 하고, `--apply`는 owner 승인 뒤 별도로 한다. 브라우저 확인에서 owner 프로젝트를 편집했다면 **같은 편집기 되돌리기로 원상복구**하고 서버 값을 대조한다(점검 §7 방식).
- 웹에서 날 것 `<button>`(`data-native-control`)을 **새 이름으로** 만들지 않는다. 기존 이름(`timeline-trim-start` 등)을 그대로 쓰면 `task22-parity-owners.test.ts` 허용 목록이 안 바뀐다. 바뀌면 무엇을 잘못 썼는지 보고 고친다.
- 컨테이너는 `.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild`(PowerShell)로만 재빌드. `docker compose`를 직접 치지 않는다. 재빌드 뒤 브라우저는 `Ctrl+F5`.
- 내장 브라우저 창은 전이·rAF·영상 프레임을 안 그린다(기억 메모 2026-09-04). 크기·위치·서버 값은 **JS·API로 재고**, 눈으로 볼 것은 스크린샷으로.
- Playwright 스냅샷 PNG(`apps/web/e2e/snapshots/`)는 다시 쓰지 않는다. e2e를 돈 뒤 `git status --short apps/web/e2e/snapshots`를 보고 바뀐 PNG는 차이를 보고에 적고 `git checkout -- apps/web/e2e/snapshots/*.png`. `npm run test:e2e` 끝의 `unexpected PNG: product-shell-mobile-menu-open.png` exit 1은 무관(G 계획 실측).
- 이미 알려진 실패(고치려 들지 마라): `editor-workbench.test.tsx` "gives the material dock back the same way, without needing a second click", `tests/test_owner_ready_script.py::test_smoke_timeout_kills_the_child_tree_and_returns_bounded_failure`.
- 커밋은 Task마다, 한국어, 끝줄 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. 확인 명령과 커밋·푸시를 한 명령에 묶지 않는다. 푸시는 Task 18에서 `git push origin main` 한 줄(강제 금지). 도구 권한이 막으면 **우회하지 말고** owner에게 직접 실행 또는 허용 규칙 `Bash(git push origin main)`을 요청.
- **검증 넷(Task마다 고정):** 갭(이 Task Step 대조, 안 한 것을 적는다) · 역방향(진짜 백엔드 e2e 또는 Task 18 실기) · 동작(px·초·서버 값으로 잰다) · 배선(`grep`으로 화면이 실제로 부르는 자리를 센다).

## Review Focus

행복한 경로 시험이 놓치기 쉬운, 실제로 일어날 입력 다섯. 각각 맡은 Task에 시험을 넣었다.

1. **재생 중 자연스럽게 다음 장면으로 넘어갈 때** — "방금 누른 장면을 지킨다"가 재생을 붙잡아 다음 장면으로 안 넘어가면 안 된다 → Task 3 `resolvePlaybackSelection` 시험 "재생이 고른 장면 끝을 지나면 다음 장면".
2. **변형본(가로·세로)을 오염된 원본 편집판에서 새로 만들 때** — `build_variant_timeline_payload`가 원본 `tracks`를 그대로 복사하므로 0907의 `session-` 클립이 새 편집판으로 번진다 → Task 4 `test_variant_payload_drops_session_projection_clips`.
3. **당겨서 뺀 장면을 나중에 되살릴 때**(되돌리기가 아니라 `되살리기`) — 뒤 장면이 다시 밀려나야 겹치지 않는다 → Task 12 `test_restoring_a_ripple_removed_scene_pushes_later_scenes_back`.
4. **미리보기 상태를 묻는 요청이 실패하거나 그 생성분이 사라졌을 때**(404·네트워크) — 기다리기가 무한 반복하거나 "만드는 중"에 영영 멈추면 안 된다. 한 번 새로 읽고 멈춘다 → Task 11 `exactPreviewWatch` 시험 "상태를 못 읽으면 한 번 새로 읽고 멈춘다".
5. **폭 24px보다 좁은 클립**(120초 전체 보기에서 742e1924에 2~4개, 스파이크 §3(가)) — 손잡이 둘이 몸통을 다 덮어 옮길 자리가 없다 → Task 8 시험 "좁은 클립은 손잡이만, 옮기기는 확대 안내".

---

## 재사용 게이트 (`implementation-plan.ko.md` §8.1)

| 후보 | 판단 | 반영 단위 |
|---|---|---|
| `classifyTimelineHit`·`findTimelineSnap`·`derivePlacement*`·`deriveNarrationTrim`(우리 순수 함수) | **adopt as-is** — 스파이크 실측 31/31·43/43 | 화면이 실제 포인터 좌표로 부르게 배선만(Task 8·9) |
| opencut-classic `ruler-utils.ts` | **reference only → 독립 구현** | `timeline/rulerScale.ts` 한 파일 + 출처 기록(Task 10) |
| openreel-video | **reference only**(`oss-adoption-map`의 `partial port`를 내린다) | 양 끝 8px 띠·클립 끝도 붙기 — 동작만, 코드 없음 |
| react-timeline-editor / freecut / Clypra / OpenCut 재작성판 | **exclude** | 키보드·aria 상실, 저장소 결합, 코드 없음(스파이크 §4) |
| `pollJobUntilTerminal`(`lib/pollJob.ts`) | **adopt + 선택 인자 하나**(`backoff`) | 미리보기 기다리기(Task 11) — 세 번째 폴링 방식을 만들지 않는다 |
| `GET /exact-previews/{generation_id}` | **adopt as-is** | 기다리는 동안 이것만 묻는다 |
| `sonner` `Toaster`(이미 의존) | **adopt as-is** | 마운트 1곳 + 이음매 파일(Task 16) |
| `repair_mojibake_library_filenames.py`의 미리보기/`--apply`/`--undo` 형식 | **partial**(형식만) | Task 5 수리 도구 |
| 새 ETag/캐시 계층 | **exclude** — 상태 길이 이미 가볍다(수백 바이트). 문제는 무거운 세 요청을 매초 부른 것 | — |
| 서버가 낡은 미리보기 파일을 계속 내주기 | **exclude** — 낡은 판 차단(fence)은 의도된 안전장치다. 대신 화면이 마지막 장면을 그림으로 잡아 둔다 | Task 11 |

---

## 파일 구조 (새로 만드는 것)

| 파일 | 책임 |
|---|---|
| `scripts/e2e_editor_fixture.py` | 고정 시험 프로젝트 둘(깨끗한 것·0907 모양 오염)을 만드는 순수 시드 함수 |
| `scripts/e2e_real_editor_api.py` | 임시 데이터 폴더에 시드하고 진짜 API를 띄우는 실행기 |
| `apps/web/playwright.real-flow.config.mjs`, `apps/web/e2e-real/*` | 진짜 백엔드 e2e 묶음(죽은 단추 조사·실사용 흐름) |
| `apps/web/e2e-real/support/controlCensus.mjs` | 단추 하나의 관찰값 → 분류(순수, `node --test`) |
| `apps/web/src/features/editor/timeline/rulerScale.ts` | 눈금 간격 고르기(순수, opencut 참고 독립 구현) |
| `apps/web/src/features/editor/timeline/dragSnap.ts` | 끌기·자르기 제안값에 붙기 적용(순수) |
| `apps/web/src/features/editor/timeline/timelineCssMetrics.ts` | CSS 변수 계산값 읽기 |
| `apps/web/src/features/editor/preview/exactPreviewWatch.ts` | 미리보기 상태 → 기다리기 결과 변환(순수) |
| `apps/web/src/features/editor/preview/previewStill.ts` | 재생기 현재 장면을 그림으로 잡기 |
| `apps/web/src/features/editor/workbench/editorFeedback.ts` | 편집 반응 알리기 이음매(계획 I가 바꿀 자리) |
| `apps/web/src/features/editor/workbench/editFailureMessage.ts` | 서버 거절 이유 → 창작자 말 |
| `apps/web/src/app/RouteErrorFallback.tsx` | 라우트 오류 한국어 화면 |
| `scripts/repair_session_projection_timelines.py` | 오염된 편집판 찾기(기본)·고치기(`--apply`, owner 승인 뒤)·되돌리기 |

---

### Task 0: 착수 확인 + 도크 끌기 성능 기준선(G Task 0 흡수) — 약 1시간

**왜 먼저인가:** G Task 0은 "편집기 화면을 바꾸기 **전에**" 기준선을 다시 재라고 못박았다. H가 편집기를 먼저 바꾸므로 그 일을 여기서 한다. 순서를 거꾸로 하면 H의 회귀가 기준선에 묻힌다.

**Files:** G 계획 Task 0과 같음(`apps/web/e2e/support/workbench-performance-baseline.json`, `apps/web/e2e/support/release-gates.test.mjs`).

**Interfaces:** Produces: 새 기준선(또는 "그대로" 판정) — Task 13·18의 끌기 게이트가 쓴다.

- [ ] **Step 1: 착수 상태를 적는다**

Run: `git status --short` → `?? .anchor/`만. `git log --oneline -3` → 첫 줄이 이 계획서 커밋 또는 그 뒤. `git worktree list` → 메인 + `.claude/worktrees/hopeful-pasteur-64b08e`(남의 낡은 것, 건드리지 않는다).
Run: `git diff --check` → 출력 없음.

- [ ] **Step 2: G 계획 Task 0을 그대로 실행한다**

`docs/superpowers/plans/2026-10-02-audit-g-screen-improvements.ko.md`의 `### Task 0:` Step 0~6을 **문자 그대로** 따른다(단위 시험이 기준선 파일을 읽게 고치기 → 5회×5샘플 → 판정 (가)/(나)/(다) → (나)일 때만 기준선 갱신 → 확인 3회). 커밋 메시지·판정 규칙도 그 문서 것을 쓴다. 기준선 파일의 `capture_intent` 문장 안 "묶음 G Task 6·10"은 "계획 H Task 7·8·13"으로 바꿔 적는다.

- [ ] **Step 3: 검증 넷**

갭: G Task 0 Step 0~6 중 건너뛴 것(판정 (가)면 Step 4·6 없음)을 적는다. 동작: 25샘플 median·p95 숫자를 보고에 붙인다. 역방향·배선: 해당 없음(측정 Task).

---

### Task 1: 진짜 백엔드 e2e 하네스 + 고정 시험 프로젝트 둘 — 약 3시간

**왜:** 이번 결함 여섯이 전부 시험을 통과했다. 기존 e2e는 `fake-api-server.mjs`(가짜 API)만 밟아서 materialize·되돌리기·placement 검증을 **한 번도** 지나지 않는다. 대표님 실제 프로젝트 대신 **결정적으로 다시 만들 수 있는** 시험 프로젝트로, 진짜 FastAPI + 진짜 저장소를 밟는 Playwright 묶음을 만든다. 뒤 Task들이 여기에 시험을 하나씩 더한다.

**Files:**
- Create: `scripts/e2e_editor_fixture.py`
- Create: `scripts/e2e_real_editor_api.py`
- Create: `tests/test_e2e_editor_fixture.py`
- Create: `apps/web/playwright.real-flow.config.mjs`
- Create: `apps/web/e2e-real/run-real-flow.mjs`
- Create: `apps/web/e2e-real/support/realFlow.mjs`
- Create: `apps/web/e2e-real/editor-opens.spec.mjs`
- Modify: `apps/web/package.json`(`"test:e2e:editor-workbench"` 줄 바로 아래에 스크립트 한 줄)

**Interfaces:**
- Produces(Python): `seed_editor_fixtures(*, projects_root: Path, media_dir: Path) -> dict[str, dict[str, str]]` — 반환 `{"clean": {"project_id", "session_id", "timeline_id"}, "duplicated_overlays": {...}}`. 상수 `CLEAN_SCENE_BOUNDS: tuple[tuple[str, float, float], ...]`.
- Produces(JS): `readFixture(): { clean: Fixture, duplicatedOverlays: Fixture }`(`Fixture = { projectId, sessionId, timelineId }`), `openEditor(page, fixture, viewport?)`, `serverSession(request, fixture)`(`include_history=false`로 부른다 — Task 11 전에는 서버가 그 인자를 무시한다), `serverManifest(request, fixture)`.
- 실행: `cd apps/web && npm run test:e2e:real-flow`(모든 `e2e-real/*.spec.mjs`), 파일 하나만은 `npm run test:e2e:real-flow -- e2e-real/<파일>`.

- [ ] **Step 1: 시드가 만드는 모양을 먼저 시험으로 쓴다(RED)**

`tests/test_e2e_editor_fixture.py`:

```python
"""e2e 고정 시험 프로젝트가 의도한 모양인지 (2026-10-08 계획 H Task 1).

깨끗한 것: 0907에서 실측한 경계(1.8990646 등)를 그대로 가진 네 장면.
오염된 것: 2026-09-20 되돌린 커밋이 남긴 모양 -- 저장된 편집판 트랙에 세션 투영
클립(`session-…`)이 박혀 있다. 이 시드가 그 모양을 잃으면 Task 4의 회귀 시험이
아무것도 지키지 않게 된다.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.e2e_editor_fixture import CLEAN_SCENE_BOUNDS, seed_editor_fixtures
from videobox_storage.local_project_store import LocalProjectStore

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg가 있어야 진짜 매체를 만든다")


def test_clean_fixture_has_the_0907_float_boundaries(tmp_path: Path) -> None:
    ids = seed_editor_fixtures(projects_root=tmp_path / "projects", media_dir=tmp_path / "media")
    store = LocalProjectStore(tmp_path / "projects")
    session = store.get_editing_session(project_id=ids["clean"]["project_id"], session_id=ids["clean"]["session_id"])
    assert [(s["segment_id"], s["start_sec"], s["end_sec"]) for s in session["segments"]] == list(CLEAN_SCENE_BOUNDS)
    assert CLEAN_SCENE_BOUNDS[2][1] == 1.8990646
    assert [bool(s.get("visual_overlays")) for s in session["segments"]] == [True, True, True, False]


def test_duplicated_fixture_keeps_session_projection_clips_in_its_stored_timeline(tmp_path: Path) -> None:
    ids = seed_editor_fixtures(projects_root=tmp_path / "projects", media_dir=tmp_path / "media")
    store = LocalProjectStore(tmp_path / "projects")
    fixture = ids["duplicated_overlays"]
    timeline = store.get_timeline_run(project_id=fixture["project_id"], timeline_id=fixture["timeline_id"])
    overlay_ids = [clip["clip_id"] for track in timeline["tracks"] if track["track_type"] == "overlay" for clip in track["clips"]]
    assert overlay_ids and all(clip_id.startswith("session-overlay-") for clip_id in overlay_ids)
    assert len(overlay_ids) != len(set(overlay_ids)), "0907처럼 같은 id가 두 번 있어야 한다"
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_e2e_editor_fixture.py`
Expected: FAIL `ModuleNotFoundError: No module named 'scripts.e2e_editor_fixture'`. (`scripts`가 import 경로에 없다고 나오면 `tests/conftest.py`가 저장소 루트를 넣는지 확인하고, 없으면 시험 머리에서 `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))`를 쓴다 — `tests/test_repair_mojibake_library_filenames.py`가 `scripts`의 모듈을 어떻게 불러오는지 그대로 따른다.)

- [ ] **Step 2: `scripts/e2e_editor_fixture.py`를 만든다**

머리 docstring에 위 시험 docstring의 두 문장을 그대로. 경로 준비는 `scripts/run_api.py`의 `sys.path.insert` 묶음을 그대로 복사한다. 정해 둔 값:

```python
#: 0907-b26195af 실측 경계(2026-10-08 점검 §3-1). 셋째 장면 시작 1.8990646 -- 재생기는 1.899064를 알려 온다.
CLEAN_SCENE_BOUNDS: tuple[tuple[str, float, float], ...] = (
    ("scene-1", 0.0, 1.3324),
    ("scene-2", 1.3324, 1.8990646),
    ("scene-3", 1.8990646, 2.9281),
    ("scene-4", 2.9281, 3.7512),
)
CLEAN_PROJECT_NAME = "편집 실사용 시험"
DUPLICATED_PROJECT_NAME = "겹친 오버레이 재현"
PARENT = "timeline_001:001"
```

`seed_editor_fixtures(*, projects_root, media_dir)`가 할 일:
1. ffmpeg로 매체를 만든다(없으면 `RuntimeError("ffmpeg가 필요합니다")`): 내레이션 `narration.wav`(`-f lavfi -i sine=frequency=330:duration=4`), 장면 영상 넷 `broll-1..4.mp4`(`-f lavfi -i color=c=<blue|green|orange|purple>:s=640x360:r=30:d=2 -f lavfi -i sine=frequency=550:duration=2 -shortest -c:v libx264 -pix_fmt yuv420p -c:a aac`), 얹을 그림 `overlay.png`(`color=c=white:s=320x180`, `-frames:v 1`).
2. `LocalProjectStore(projects_root)`의 `bootstrap_project(name=...)`로 두 프로젝트를 만들고, `register_asset(asset_type=AssetType.NARRATION_AUDIO|BROLL_VIDEO|IMAGE, source_path=...)`로 매체를 넣는다.
3. **깨끗한 것:** `save_timeline_run(output_mode="landscape", timeline_payload=…)` — `output: {"width":1280,"height":720}`, `fps_num:30`, `fps_den:1`, 내레이션 트랙 하나(`track_id:"narration_primary"`, 장면마다 클립 `clip_narration_00N`, `segment_id`=장면 id, `start/end`=경계, `source_in_sec/source_out_sec`=같은 값, `asset_id`/`asset_uri`=내레이션 자산). 그 다음 `save_editing_session(project_id, timeline_id, session_payload={"segments": [...], "history": []})` — 장면마다 `caption_text`("첫 장면"…"넷째 장면"), `cut_action:"keep"`, `review_required: False`, `broll_override: {"asset_id", "asset_uri"(저장된 storage_uri), "media_controls": {}}`, 장면 1~3에 `visual_overlays: [{"overlay_type":"image_overlay","asset_id":<그림>,"asset_uri":<그림 uri>,"text":""}]`, 장면 4는 `[]`.
4. **오염된 것(0907 모양):** 깨끗한 편집판을 같은 방식으로 저장하되 내레이션은 부모 하나(`PARENT`, 0~4초). 세션은 세 조각 — `PARENT`(0~1.5, 오버레이 있음, `source_slices=[{"segment_id":PARENT,"source_offset_sec":0,"duration_sec":1.5}]`), `f"{PARENT}__split_3"`(1.5~2.5, 오버레이 있음, offset 1.5), `f"{PARENT}__split_2"`(2.5~4.0, 오버레이 **없음**, offset 2.5). 저장 뒤 편집판 JSON 파일에 **직접** 오버레이 트랙을 써 넣는다(Task 4 이후엔 `save_timeline_run`이 이런 트랙을 거절하므로, 2026-09-20의 옛 데이터를 흉내 내려면 파일에 직접 쓸 수밖에 없다 — 주석으로 그 사실을 남긴다): 파일 경로는 `store.resolve_storage_uri(project_id=…, storage_uri=store.get_timeline_run(...)["file_uri"])`, 트랙은 `{"track_id":"track_overlay","track_type":"overlay","clips":[ <PARENT 0~1.5 session-overlay-PARENT-0-0>, <split_3 1.5~2.5 session-overlay-…__split_3-0-0>, <PARENT 0~1.5 session-overlay-PARENT-0-0 (같은 id 다시)> ]}`(각 클립 `overlay_type:"image_overlay"`, `asset_id`/`asset_uri`=그림).
5. `{"clean": {...}, "duplicated_overlays": {...}}`를 돌려준다(`project_id`는 `ProjectRecord.project_id`).

- [ ] **Step 3: GREEN**

Run: Step 1 명령 → `2 passed`.

- [ ] **Step 4: 실행기 `scripts/e2e_real_editor_api.py`**

`main(argv=None) -> int`. 인자 `--port`(필수), `--fixture-file`(필수), `--data-root`(기본 `apps/web/test-results/real-flow-data/<UTC yyyymmddHHMMSS>`). 할 일:
1. **실제 데이터에 닿지 않게** 환경을 비운다: `os.environ.pop("VIDEOBOX_DATABASE_URL", None)`, `os.environ.pop("VIDEOBOX_SNAPSHOT_ROOT", None)`, `os.environ["VIDEOBOX_DATA_ROOT"] = str(data_root)`. 그리고 `data_root`가 `resolve_projects_root()` 기본값(`D:\…\65_videobox-project`) 아래면 `SystemExit("실제 데이터 폴더에는 시드하지 않습니다")`.
2. `seed_editor_fixtures(projects_root=data_root/"projects", media_dir=data_root/"media")` → 결과를 `--fixture-file`에 JSON으로 쓴다(`camelCase` 키: `{"clean":{"projectId","sessionId","timelineId"},"duplicatedOverlays":{...}}`).
3. `create_app(projects_root=data_root/"projects", media_library_store=MediaLibraryStore(data_root/"library"), media_analysis_poll_interval_seconds=3600)`을 `uvicorn.run(app, host="127.0.0.1", port=port)`로 띄운다(`tests/test_library_materialize_carries_title.py`가 앱을 만드는 방식과 같다).

- [ ] **Step 5: Playwright 설정과 실행기**

`apps/web/playwright.real-flow.config.mjs` — `playwright.config.*`를 본떠, 다른 점만:
```js
const python = process.platform === "win32" ? "..\\..\\.venv\\Scripts\\python.exe" : "../../.venv/bin/python";
const fixtureFile = process.env.VIDEOBOX_E2E_FIXTURE_FILE ?? "test-results/real-flow-fixture.json";
// testDir: "./e2e-real", timeout: 120_000, workers: 1
// webServer[0]: { command: `${python} ../../scripts/e2e_real_editor_api.py --port ${apiPort} --fixture-file ${fixtureFile}`, url: `http://127.0.0.1:${apiPort}/health`, timeout: 120_000, reuseExistingServer: false }
// webServer[1]: 기존 설정의 vite dev 줄 그대로(env에 PLAYWRIGHT_FAKE_API_PORT=apiPort — vite 프록시가 그 포트로 간다)
```
`apiPort`는 `process.env.PLAYWRIGHT_FAKE_API_PORT`(실행기가 빈 포트를 넣는다).
`apps/web/e2e-real/run-real-flow.mjs` — `e2e/run-isolated.mjs`를 복사하고 `runE2eCommand` 대신: `isolatedE2eEnvironment(process.env)`로 포트를 받고 `node ./node_modules/@playwright/test/cli.js test --config playwright.real-flow.config.mjs ...args`를 돈다(스냅샷 목록 검사는 하지 않는다 — 이 묶음은 스냅샷을 안 쓴다).
`package.json`의 `"test:e2e:editor-workbench": …,` 줄 바로 아래: `"test:e2e:real-flow": "node ./e2e-real/run-real-flow.mjs",`

`apps/web/e2e-real/support/realFlow.mjs`는 위 Interfaces 넷. `openEditor`는 `page.setViewportSize(viewport ?? {width:1440,height:900})` → `page.goto(`/projects/${projectId}/editor?session_id=${sessionId}`)` → `page.getByRole("region", { name: "타임라인" })`가 보일 때까지.

- [ ] **Step 6: 첫 e2e — 편집기가 열린다**

`apps/web/e2e-real/editor-opens.spec.mjs`:
```js
import { expect, test } from "@playwright/test";
import { openEditor, readFixture, serverManifest } from "./support/realFlow.mjs";

test("진짜 백엔드의 고정 시험 프로젝트가 편집기로 열린다", async ({ page, request }) => {
  const { clean } = readFixture();
  await openEditor(page, clean);
  const manifest = await serverManifest(request, clean);
  const narration = manifest.tracks.find((track) => track.track_type === "narration");
  expect(narration.clips.map((clip) => clip.start_sec)).toEqual([0, 1.3324, 1.8990646, 2.9281]);
  await expect(page.getByTestId("timeline-clip")).not.toHaveCount(0);
});
```
Run: `cd apps/web && npm run test:e2e:real-flow -- e2e-real/editor-opens.spec.mjs` → `1 passed`. (매니페스트 트랙 키가 `track_type`이 아니면 `editorViewModel.ts`가 읽는 키를 보고 맞춘다.)

- [ ] **Step 7: 검증 넷 + 커밋**

갭: 시드 두 모양·실행기 격리 셋(DB·스냅샷 변수 제거, 실제 폴더 거부)을 대조. 역방향: Step 6이 진짜 API를 밟았는지 `test-results/real-flow-data/*/projects`에 두 프로젝트 폴더가 생겼는지 본다. 배선: `grep -n "e2e_real_editor_api" apps/web/playwright.real-flow.config.mjs` 1줄.
```bash
git add scripts/e2e_editor_fixture.py scripts/e2e_real_editor_api.py tests/test_e2e_editor_fixture.py apps/web/playwright.real-flow.config.mjs apps/web/e2e-real apps/web/package.json
git commit -m "test(e2e): 진짜 백엔드와 고정 시험 프로젝트 둘로 도는 편집기 e2e 하네스

가짜 API만 밟던 e2e로는 materialize·되돌리기·placement 검증을 한 번도
지나지 않았다. 0907 실측 경계와 2026-09-20 오염 모양을 결정적으로 만든다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 편집기 죽은 단추 재고 조사(대표님: "단추가 반응이 없다") — 약 2.5시간

**왜:** 대표님 2026-10-08: "버튼을 눌러도 반응이 없고, 어떤 건 아예 안 된다. 아무것도 시험할 수가 없다." 짐작으로 몇 개 고치지 않고 **편집기의 눈에 보이는 모든 조작**(단추·탭·메뉴·선택 상자·링크)을 기계로 센다. 이 Task는 **제품 코드를 바꾸지 않는다** — 목록만 만든다. 고치기는 Task 16(그 사이 Task 3~15가 상당수를 먼저 고친다).

**Files:**
- Create: `apps/web/e2e-real/support/controlCensus.mjs`, `apps/web/e2e-real/support/controlCensus.test.mjs`
- Create: `apps/web/e2e-real/dead-control-sweep.spec.mjs`
- Create(산출물, 커밋함): `docs/superpowers/audit-evidence/2026-10-08-editor-ui/dead-controls.json`

**Interfaces:**
- Produces: `classifyControl(observation) -> "ok" | "no-handler" | "silent" | "always-disabled" | "skipped-side-effect"`. `observation = { role, name, disabledInAllStates: boolean, hasHandler: boolean, isLink: boolean, isFormSubmit: boolean, skipped: boolean, reaction: { domMutations: number, requests: number, focusMoved: boolean, ariaChanged: boolean, dialogOpened: boolean, urlChanged: boolean } }`.
- Produces: `dead-controls.json` — `{ "generated_at", "fixture": "clean", "viewport": "1440x900", "controls": [{ "name", "role", "nativeControl", "states": ["no-selection","clip-selected"], "class", "evidence" }] }`. Task 16이 읽는다.

- [ ] **Step 1: 분류 규칙 시험(RED)**

`controlCensus.test.mjs`(`node --test`):
```js
import assert from "node:assert/strict";
import test from "node:test";
import { classifyControl } from "./controlCensus.mjs";

const quiet = { domMutations: 0, requests: 0, focusMoved: false, ariaChanged: false, dialogOpened: false, urlChanged: false };
const base = { role: "button", name: "x", disabledInAllStates: false, hasHandler: true, isLink: false, isFormSubmit: false, skipped: false, reaction: quiet };

test("손잡이가 없는 단추는 no-handler", () => assert.equal(classifyControl({ ...base, hasHandler: false }), "no-handler"));
test("링크·폼 제출은 손잡이가 없어도 살아 있다", () => {
  assert.equal(classifyControl({ ...base, hasHandler: false, isLink: true, reaction: { ...quiet, urlChanged: true } }), "ok");
  assert.equal(classifyControl({ ...base, hasHandler: false, isFormSubmit: true, reaction: { ...quiet, requests: 1 } }), "ok");
});
test("눌렀는데 화면·요청·초점·aria 어느 것도 안 바뀌면 silent", () => assert.equal(classifyControl(base), "silent"));
test("무엇이든 바뀌면 ok", () => {
  for (const key of ["domMutations", "requests"]) assert.equal(classifyControl({ ...base, reaction: { ...quiet, [key]: 1 } }), "ok");
  for (const key of ["focusMoved", "ariaChanged", "dialogOpened", "urlChanged"]) assert.equal(classifyControl({ ...base, reaction: { ...quiet, [key]: true } }), "ok");
});
test("모든 상태에서 꺼져 있으면 always-disabled", () => assert.equal(classifyControl({ ...base, disabledInAllStates: true }), "always-disabled"));
test("부작용이 큰 단추는 누르지 않고 skipped-side-effect", () => assert.equal(classifyControl({ ...base, skipped: true }), "skipped-side-effect"));
```
Run: `cd apps/web && node --test e2e-real/support/controlCensus.test.mjs` → FAIL `Cannot find module`.

- [ ] **Step 2: `classifyControl` 구현 → GREEN**

순서: `skipped` → `disabledInAllStates` → (`!hasHandler && !isLink && !isFormSubmit`) → 반응 여섯 중 하나라도 → `ok`, 아니면 `silent`. Run 같은 명령 → `ℹ fail 0`.

- [ ] **Step 3: 훑기 시험 `dead-control-sweep.spec.mjs`**

깨끗한 고정 프로젝트를 1440×900으로 연다. 두 상태 `no-selection`(막 연 화면), `clip-selected`(영상 1번째 클립 선택 버튼 클릭 뒤)에서 각각:
1. 후보를 모은다: `.vb-editor-workbench` 안과 열린 `[role=dialog]` 안의 보이는 `button, [role=button], [role=tab], [role=menuitem], select, a[href]`. 이름은 `aria-label ?? textContent.trim()`.
2. 손잡이 유무: `page.evaluate`로 요소의 React props(`Object.keys(el).find((k) => k.startsWith("__reactProps$"))`)에서 `onClick|onPointerDown|onMouseDown|onChange|onKeyDown|onSelect` 중 하나라도 있으면 `hasHandler=true`. Radix 트리거는 `asChild`라 props가 합쳐져 있다 — 그대로 센다.
3. **누르지 않는 목록**(`skipped`): 이름이 `/완성본 만들기|업로드|올리기|지우기|삭제|보관|내보내기 시작|캡컷/`에 맞는 것. 나머지는 하나씩: 누르기 직전 `MutationObserver`(subtree·attributes·childList) 시작 + `page.on("request")` 세기 + `document.activeElement`·`aria-pressed/expanded/selected` 기록 → 클릭 → 800ms → 수집. 그 뒤 `Escape` 한 번, URL이 바뀌었으면 편집기로 다시 열기. 10개마다 페이지를 새로 연다(상태 누적 방지).
4. 서버를 바꾸는 편집이 일어났으면(세션 rev 증가 — `serverSession`으로 확인) 고정 프로젝트라 그대로 둔다(되돌리지 않아도 된다 — 시드는 매 실행 새로 만든다).
5. 같은 이름·역할을 한 줄로 합치고, `disabledInAllStates`는 두 상태 모두 `disabled`일 때만 참.
6. `classifyControl`로 분류해 위 JSON 모양으로 `../../docs/superpowers/audit-evidence/2026-10-08-editor-ui/dead-controls.json`에 쓴다(`node:fs`). 시험은 **항상 통과**한다 — 이것은 측정이다. 끝에 분류별 개수를 `console.log`.

Run: `cd apps/web && npm run test:e2e:real-flow -- e2e-real/dead-control-sweep.spec.mjs` → `1 passed`, 콘솔에 `{"ok":…,"silent":…,"no-handler":…,"always-disabled":…,"skipped-side-effect":…}`.

- [ ] **Step 4: 사람 눈으로 한 번 대조**

`silent`·`no-handler` 각 줄을 점검 §5 표와 맞춰 본다. **이 시점의 기대(점검 실측):** 트랙 잠금·숨기기·음소거는 jsdom이 아니라 실제 클릭이라 클립이 대신 눌려 `ok`로 잘못 셀 수 있다 — 그래서 각 줄의 `evidence`에 "클릭 지점의 `elementFromPoint`가 그 단추 자신인가"(`hitSelf: boolean`)를 같이 적고, `hitSelf=false`면 분류를 `silent`로 덮어쓴다(가려진 단추). 이 규칙을 Step 1 시험에 하나 더한다: `classifyControl({ ...base, hitSelf: false, reaction: { ...quiet, domMutations: 3 } }) === "silent"`(RED→GREEN 한 번 더).

- [ ] **Step 5: 검증 넷 + 커밋**

갭: 두 상태 외(드로어 열린 상태, 375 폭)는 안 쟀다 — 보고에 적는다. 동작: 분류별 개수. 배선: 해당 없음.
```bash
git add apps/web/e2e-real/support/controlCensus.mjs apps/web/e2e-real/support/controlCensus.test.mjs apps/web/e2e-real/dead-control-sweep.spec.mjs docs/superpowers/audit-evidence/2026-10-08-editor-ui/dead-controls.json
git commit -m "test(e2e): 편집기 조작 전부를 진짜 백엔드에서 눌러 죽은 단추를 센다

손잡이 유무, 클릭 지점이 자기 자신인지, 눌렀을 때 화면·요청·초점이
바뀌는지로 나눈다. 고치기는 계획 H Task 16.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 클립을 누르면 그 장면이 잡힌다 — 고르기 id 우선 규칙(스파이크 H-a) — 약 2시간

**Files:**
- Modify: `apps/web/src/features/editor/transcript/playbackNavigation.ts`(파일 끝에 함수 둘)
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbench.tsx` — 앵커 `import { activeSegmentIdAt, clampPlaybackSeconds } from "../transcript/playbackNavigation";`, `const selectSegment = (segmentId: string) => setSelectedSegmentId(segmentId);`, `const activeSegmentId = activeSegmentIdAt(narrationSpans.length > 1 ? narrationSpans : view.captions.length ? view.captions : narrationSpans, nextSeconds);` + 바로 다음 줄 `setSelectedSegmentId(activeSegmentId);`
- Test: `apps/web/src/features/editor/transcript/playbackNavigation.test.ts`, `apps/web/src/features/editor/workbench/editor-workbench.test.tsx`

**Interfaces:**
- Produces: `frameDurationSec(fps: Readonly<{ num: number; den: number }>): number`(= `den / num`), `resolvePlaybackSelection(segments: readonly TimedSegment[], seconds: number, options: Readonly<{ pinnedSegmentId: string | null; frameSec: number }>): string | null`.
- 규칙(스파이크 §3(나), 23줄): **방금 누른 장면(pinned)은 재생 시각이 `[그 장면 시작 − 1프레임, 그 장면 끝)` 안이면 그대로 둔다. 아니면 반 프레임 여유로 찾는다(`start − frame/2 ≤ t < end − frame/2`). 그것도 없으면 옛 `activeSegmentIdAt`.**

- [ ] **Step 1: 순수 시험(RED)** — `playbackNavigation.test.ts` 맨 아래에:

```ts
import { frameDurationSec, resolvePlaybackSelection } from "./playbackNavigation";

// 0907-b26195af 실측(2026-10-08 점검 §3-1, 스파이크 §3(나)): 경계와 재생기가 알려 온 시각.
const scenes0907 = [
  { segmentId: "scene-1", startSec: 0, endSec: 1.3324 },
  { segmentId: "scene-2", startSec: 1.3324, endSec: 1.8990646 },
  { segmentId: "scene-3", startSec: 1.8990646, endSec: 2.9281 },
  { segmentId: "scene-4", startSec: 2.9281, endSec: 3.7512 },
];
const playerReported = 1.899064;
const frame = frameDurationSec({ num: 30, den: 1 });

describe("재생 시각으로 장면 고르기 -- 누른 장면이 먼저 (2026-10-08)", () => {
  it("옛 규칙은 재생기가 알려 온 시각에서 앞 장면을 고른다 -- 결함의 정체", () => {
    expect(activeSegmentIdAt(scenes0907, playerReported)).toBe("scene-2");
  });
  it("방금 누른 장면은 재생기가 시작 바로 앞을 알려 와도 그대로다", () => {
    expect(resolvePlaybackSelection(scenes0907, playerReported, { pinnedSegmentId: "scene-3", frameSec: frame })).toBe("scene-3");
  });
  it("누른 장면이 없어도 경계 반 프레임 안은 뒤 장면이다", () => {
    expect(resolvePlaybackSelection(scenes0907, playerReported, { pinnedSegmentId: null, frameSec: frame })).toBe("scene-3");
  });
  it("재생이 누른 장면 끝을 지나면 다음 장면으로 넘어간다", () => {
    expect(resolvePlaybackSelection(scenes0907, 2.9281 + 0.001, { pinnedSegmentId: "scene-3", frameSec: frame })).toBe("scene-4");
  });
  it("다른 곳으로 크게 옮기면 그 자리 장면이다", () => {
    expect(resolvePlaybackSelection(scenes0907, 0.5, { pinnedSegmentId: "scene-3", frameSec: frame })).toBe("scene-1");
  });
  it("마지막 장면 끝 반 프레임 안도 마지막 장면이고, 그 뒤는 없다", () => {
    expect(resolvePlaybackSelection(scenes0907, 3.7512 - frame / 4, { pinnedSegmentId: null, frameSec: frame })).toBe("scene-4");
    expect(resolvePlaybackSelection(scenes0907, 3.9, { pinnedSegmentId: null, frameSec: frame })).toBeNull();
  });
});
```
(파일 첫 줄 import에 이미 `activeSegmentIdAt`이 있다 — 새 import는 같은 줄에 합쳐도 된다.)

Run: `cd apps/web && npx vitest run src/features/editor/transcript/playbackNavigation.test.ts` → FAIL `does not provide an export named 'frameDurationSec'`.

- [ ] **Step 2: 구현 → GREEN**

```ts
/** 한 프레임의 길이(초). */
export function frameDurationSec(fps: Readonly<{ num: number; den: number }>): number {
  if (!(fps.num > 0) || !(fps.den > 0)) throw new RangeError("fps must be positive");
  return fps.den / fps.num;
}

/**
 * 재생 시각에서 고를 장면. **방금 누른 장면이 먼저다**(2026-10-08 점검 §3-1).
 * 재생기는 장면 시작으로 옮겨도 그보다 아주 조금 작은 시각(백만분의 1초·프레임 버림)을
 * 알려 온다. 그 시각으로 다시 찾으면 앞 장면이 잡혀 속도가 엉뚱한 장면에 들어갔다.
 */
export function resolvePlaybackSelection(
  segments: readonly TimedSegment[],
  seconds: number,
  options: Readonly<{ pinnedSegmentId: string | null; frameSec: number }>,
): string | null {
  finite(seconds, "Playback seconds");
  const { pinnedSegmentId, frameSec } = options;
  const pinned = pinnedSegmentId === null ? undefined : segments.find((segment) => segment.segmentId === pinnedSegmentId);
  if (pinned && pinned.startSec - frameSec <= seconds && seconds < pinned.endSec) return pinned.segmentId;
  const half = frameSec / 2;
  return segments.find((segment) => segment.startSec - half <= seconds && seconds < segment.endSec - half)?.segmentId
    ?? activeSegmentIdAt(segments, seconds);
}
```
Run Step 1 명령 → 통과.

- [ ] **Step 3: 화면 시험(RED)** — `editor-workbench.test.tsx`의 `it("전환 탭이 두 번째 장면을 고른 직후 미리보기 플레이어의 낡은 재생 위치 신호로` 시험 **바로 앞**에:

```tsx
  it("클립을 누르면 재생기가 경계 바로 앞 시각을 알려 와도 오른쪽 편집 항목은 그 장면이다 (2026-10-08 실사용 점검 §3-1)", () => {
    const scenes = [[0, 1.3324], [1.3324, 1.8990646], [1.8990646, 2.9281]] as const;
    const threeSceneView = {
      ...view,
      output: { ...view.output, durationSec: 2.9281 },
      playback: { auditionUrls: {}, exactPreview: { status: "current" as const, url: "/api/exact.mp4", artifactRevision: 1, timelineStartSec: 0, timelineEndSec: 2.9281 } },
      tracks: [{ trackId: "narration", role: "narration", clips: scenes.map(([startSec, endSec], index) => ({ clipId: `n-${index + 1}`, segmentId: `segment-${index + 1}`, type: "narration", assetId: null, assetUri: null, startSec, endSec, controls: {} })) }],
      captions: [],
    } as const;
    const session = {
      projectId: "project-a", sessionId: "session-a", timelineId: "timeline-a", expectedRevision: 1,
      undoCount: 0, redoCount: 0, updatedAt: null, captionLanguage: null, translatedLanguages: [],
      segments: scenes.map((_, index) => ({ segmentId: `segment-${index + 1}`, cutAction: "keep", bgm: null, sfx: null, transitionIn: null, ttsReplacement: null })),
    } as const;
    render(<EditorWorkbench view={threeSceneView} session={session as never} />);
    openInspector();

    const player = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
    fireEvent.click(clipSelectionButton("n-3"));
    // 재생기는 1.8990646으로 옮겨 달라는 말에 1.899064를 알려 왔다(점검 실측).
    Object.defineProperty(player, "currentTime", { configurable: true, writable: true, value: 1.899064 });
    fireEvent.timeUpdate(player);

    const inspector = screen.getByRole("region", { name: "편집 항목" });
    expect(within(inspector).getByText("1.90–2.93초 구간")).toBeInTheDocument();
    expect(within(inspector).queryByText("1.33–1.90초 구간")).toBeNull();
  });

```
Run: `cd apps/web && npx vitest run src/features/editor/workbench/editor-workbench.test.tsx -t "경계 바로 앞 시각"` → FAIL(`Unable to find … 1.90–2.93초 구간`, 화면은 `1.33–1.90초 구간`).

- [ ] **Step 4: 배선 → GREEN**

`EditorWorkbench.tsx`:
1. import 줄 → `import { clampPlaybackSeconds, frameDurationSec, resolvePlaybackSelection } from "../transcript/playbackNavigation";`(다른 곳에서 `activeSegmentIdAt`을 쓰면 남긴다 — `grep -n "activeSegmentIdAt" EditorWorkbench.tsx`).
2. `const selectSegment = (segmentId: string) => setSelectedSegmentId(segmentId);` →
```tsx
  // 사람이 **직접 누른** 장면. 재생 시각으로 다시 고를 때 이 장면을 먼저 지킨다(2026-10-08 §3-1).
  const pinnedSegmentIdRef = useRef<string | null>(null);
  const selectSegment = (segmentId: string) => { pinnedSegmentIdRef.current = segmentId; setSelectedSegmentId(segmentId); };
```
3. `const activeSegmentId = activeSegmentIdAt(…);` + `setSelectedSegmentId(activeSegmentId);` 두 줄 →
```tsx
    const spans = narrationSpans.length > 1 ? narrationSpans : view.captions.length ? view.captions : narrationSpans;
    setSelectedSegmentId(resolvePlaybackSelection(spans, nextSeconds, { pinnedSegmentId: pinnedSegmentIdRef.current, frameSec: frameDurationSec(view.fps) }));
```
(클립 클릭은 `onPlaybackSeek` → `onSelectSegment` 순서다. 첫 `onPlaybackSeek` 때 pinned는 아직 옛 장면이지만 그 시각은 새 장면 시작 그 자체라 반 프레임 규칙이 새 장면을 고르고, 곧 `onSelectSegment`가 pinned를 바꾼다.)
Run Step 3 명령 → 통과.

- [ ] **Step 5: 넓은 검증**

Run: `cd apps/web && npx vitest run src/features/editor/transcript src/features/editor/workbench/editor-workbench.test.tsx src/features/editor/workbench/cut-toolbar.test.tsx src/features/editor/timeline` → 이미 알려진 실패 1건 외 통과. `npx tsc --noEmit` → 0.
배선: `grep -n "resolvePlaybackSelection\|pinnedSegmentIdRef" apps/web/src/features/editor/workbench/EditorWorkbench.tsx` → 정의 1 + 사용 ≥3.

- [ ] **Step 6: 진짜 백엔드 시험 하나 더** — `apps/web/e2e-real/clip-selection.spec.mjs`:
```js
import { expect, test } from "@playwright/test";
import { openEditor, readFixture } from "./support/realFlow.mjs";

test("영상 3번째 클립을 누르면 오른쪽 편집 항목은 셋째 장면이다", async ({ page }) => {
  await openEditor(page, readFixture().clean);
  await page.getByRole("button", { name: /^영상 3번째 장면/ }).click();
  await page.waitForTimeout(500); // 재생기가 seeked/timeupdate를 올려 보낼 시간
  await expect(page.getByRole("region", { name: "편집 항목" })).toContainText("1.90–2.93초 구간");
});
```
Run: `cd apps/web && npm run test:e2e:real-flow -- e2e-real/clip-selection.spec.mjs` → `1 passed`. (클립 이름이 다르면 `TimelineDock.tsx` `formatClipDisplayName`이 만드는 이름을 보고 맞춘다. 미리보기가 아직 없으면 재생기 신호가 없어 결함이 안 드러난다 — 그때는 `page.getByLabel("편집본 미리보기")`가 보일 때까지 최대 90초 기다린 뒤 누른다.)

- [ ] **Step 7: 검증 넷 + 커밋**

갭: 점검 #2(속도가 장면 5로 감)는 이 규칙의 결과라 Task 17 e2e에서 서버 값으로 다시 잰다 — 보고에 적는다. 역방향: Step 6. 동작: 오른쪽 구간 숫자. 배선: Step 5.
```bash
git add apps/web/src/features/editor/transcript/playbackNavigation.ts apps/web/src/features/editor/transcript/playbackNavigation.test.ts apps/web/src/features/editor/workbench/EditorWorkbench.tsx apps/web/src/features/editor/workbench/editor-workbench.test.tsx apps/web/e2e-real/clip-selection.spec.mjs
git commit -m "fix(editor): 클립을 누르면 재생기가 경계 바로 앞을 알려 와도 그 장면을 지킨다

재생기는 1.8990646으로 옮기라는 말에 1.899064를 알려 왔고, 그 시각으로
다시 찾느라 앞 장면이 잡혀 속도가 엉뚱한 장면에 들어갔다. 누른 장면을 먼저
지키고, 아니면 반 프레임 여유로 찾는다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 오버레이가 18~22개로 불어나는 근본 원인 — 생성기가 세션 투영 클립을 다시 투영하지 않게 — 약 3시간

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/composition_plan.py` — 앵커 `_SUPPORTED_TRACKS = frozenset({"narration", "broll", "bgm", "sfx", "overlay"})`(바로 아래에 상수·함수), 일반 트랙 고리의 `            if track_type == "narration" and raw is global_narration_clip:`(바로 **앞**에 건너뛰기 두 줄), 세션 오버레이의 `                    tracks.setdefault(("overlay", materialized_track_id("overlay")), []).append(clip)`(이름 충돌 처리)
- Modify: `packages/core-engine/src/videobox_core_engine/output_variants.py` — 앵커 `                master_timeline.get("tracks", []), variant_kind=variant_kind,`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py` — `def save_timeline_run(`의 `        timeline_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")` 바로 앞, `def update_timeline_run(`의 `        file_path = self._timeline_file_path(project_id=project_id, timeline_id=timeline_id)` 바로 앞(이 줄은 파일에 5번 있다 — **`def update_timeline_run(` 함수 안의 것**만, 바로 위 줄이 `        payload["created_at"] = str(existing.get("created_at"))`인 자리)
- Create: `tests/test_session_projection_never_reprojected.py`

**Interfaces:**
- Produces(`composition_plan`): `SESSION_PROJECTION_CLIP_PREFIX = "session-"`, `is_session_projection_clip(clip: Mapping[str, Any]) -> bool`, `without_session_projection_clips(tracks: object) -> list[dict[str, Any]]`(트랙은 남기고 그 안의 투영 클립만 뺀 깊은 사본). Task 5가 쓴다.
- Produces(store): 저장 문지기 — `save_timeline_run`은 투영 클립이 하나라도 있으면, `update_timeline_run`은 **이미 있던 것보다 새로 늘어나면** `ValueError("timeline_contains_session_projection")`.
- 불변식: `materialize_editing_session_timeline(timeline=T, editing_session=S)`의 결과를 다시 `T'`로 저장해도 `materialize(T', S)`의 오버레이·B-roll 목록이 같다(멱등).

- [ ] **Step 1: 실패 시험(RED)** — `tests/test_session_projection_never_reprojected.py`:

```python
"""세션 투영 클립은 원본이 아니다 (2026-10-08 계획 H Task 4, 점검 §3-3).

0907의 저장된 편집판(`timeline_002.json`)에는 materialize가 만든 `session-overlay-…`·
`session-broll-…` 클립이 박혀 있다(2026-09-20 되돌린 커밋의 흔적). 생성기가 그것을
원본으로 다시 투영해, 부모 장면을 가리키는 모든 조각에 오버레이를 깔고 같은 id를
두 번 붙였다 -> 자르기·옮기기가 전부 `timeline_placement_duplicate` 422.
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from videobox_core_engine.composition_plan import materialize_editing_session_timeline
from videobox_core_engine.output_variants import MaterializedVariant, build_variant_timeline_payload
from videobox_core_engine.timeline_placements import collect_timeline_placements
from videobox_storage.local_project_store import LocalProjectStore

PARENT = "timeline_001:001"
CHILD = f"{PARENT}__split_2"
IMAGE = {"overlay_type": "image_overlay", "asset_id": "asset_img", "asset_uri": "local://projects/p/assets/image/a.png"}


def _session() -> dict:
    return {
        "session_id": "editing_session_001", "project_id": "p", "timeline_id": "timeline_002", "session_revision": 3,
        "segments": [
            {"segment_id": PARENT, "caption_text": "앞", "start_sec": 0.0, "end_sec": 2.0, "cut_action": "keep", "visual_overlays": [dict(IMAGE)],
             "source_slices": [{"segment_id": PARENT, "source_offset_sec": 0.0, "duration_sec": 2.0}]},
            {"segment_id": CHILD, "caption_text": "뒤", "start_sec": 2.0, "end_sec": 4.0, "cut_action": "keep", "visual_overlays": [],
             "source_slices": [{"segment_id": PARENT, "source_offset_sec": 2.0, "duration_sec": 2.0}]},
        ],
    }


def _base(*, with_projection: bool) -> dict:
    tracks = [{"track_id": "narration_primary", "track_type": "narration", "clips": [
        {"clip_id": "clip_narration_001", "segment_id": PARENT, "clip_type": "narration", "asset_uri": "local://n.wav", "start_sec": 0.0, "end_sec": 4.0},
    ]}]
    if with_projection:
        tracks.append({"track_id": "track_overlay", "track_type": "overlay", "clips": [
            {**IMAGE, "clip_id": f"session-overlay-{PARENT}-0-0", "segment_id": PARENT, "start_sec": 0.0, "end_sec": 2.0},
        ]})
    return {"timeline_id": "timeline_002", "project_id": "p", "output": {"width": 1280, "height": 720}, "tracks": tracks}


def _overlays(materialized: dict) -> list[tuple[str, str, float, float]]:
    return [
        (clip["clip_id"], clip["segment_id"], clip["start_sec"], clip["end_sec"])
        for track in materialized["tracks"] if track["track_type"] == "overlay" for clip in track["clips"]
    ]


def test_a_baked_session_overlay_is_not_projected_onto_other_scenes_or_duplicated() -> None:
    materialized = materialize_editing_session_timeline(timeline=_base(with_projection=True), editing_session=_session())
    assert _overlays(materialized) == [(f"session-overlay-{PARENT}-0-0", PARENT, 0.0, 2.0)]
    collect_timeline_placements(timeline=materialized)  # 같은 id가 있으면 여기서 ValueError


def test_materializing_its_own_output_again_gives_the_same_overlays() -> None:
    once = materialize_editing_session_timeline(timeline=_base(with_projection=False), editing_session=_session())
    again = materialize_editing_session_timeline(timeline={**_base(with_projection=False), "tracks": deepcopy(once["tracks"])}, editing_session=_session())
    assert _overlays(again) == _overlays(once)


def test_variant_payload_drops_session_projection_clips() -> None:
    payload = build_variant_timeline_payload(
        master_timeline=_base(with_projection=True), variant_kind="horizontal",
        derived=MaterializedVariant(source_session_id="editing_session_001", source_session_revision=3,
                                    source_variant_id="variant-h", source_variant_revision=1,
                                    segments=({"segment_id": PARENT, "start_sec": 0.0, "end_sec": 2.0},)),
        overrides=None,
    )
    assert all(not str(clip.get("clip_id")).startswith("session-") for track in payload["tracks"] for clip in track["clips"])


def test_storing_a_timeline_with_session_projection_clips_is_refused(tmp_path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="문지기")
    with pytest.raises(ValueError, match="timeline_contains_session_projection"):
        store.save_timeline_run(project_id=project.project_id, output_mode="review", timeline_payload=_base(with_projection=True))


def test_an_already_contaminated_timeline_can_still_be_updated_but_cannot_grow(tmp_path) -> None:
    """0907처럼 이미 오염된 파일은 매 편집마다 `update_timeline_run`(판 번호 옮기기)을 탄다.
    그것까지 막으면 0907이 통째로 편집 불가가 된다 -- 늘어나는 것만 막는다."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="옛 데이터")
    saved = store.save_timeline_run(project_id=project.project_id, output_mode="review", timeline_payload=_base(with_projection=False))
    contaminated = {**store.get_timeline_run(project_id=project.project_id, timeline_id=saved["timeline_id"]), "tracks": _base(with_projection=True)["tracks"]}
    contaminated.pop("summary", None)
    path = store.resolve_storage_uri(project_id=project.project_id, storage_uri=str(contaminated["file_uri"]))
    import json
    path.write_text(json.dumps(contaminated), encoding="utf-8")  # 2026-09-20 옛 데이터 흉내
    store.update_timeline_run(project_id=project.project_id, timeline_id=saved["timeline_id"], timeline_payload={**contaminated, "source_session_revision": 4})
    grown = deepcopy(contaminated)
    grown["tracks"][1]["clips"].append({**IMAGE, "clip_id": f"session-overlay-{CHILD}-0-0", "segment_id": CHILD, "start_sec": 2.0, "end_sec": 4.0})
    with pytest.raises(ValueError, match="timeline_contains_session_projection"):
        store.update_timeline_run(project_id=project.project_id, timeline_id=saved["timeline_id"], timeline_payload=grown)
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_session_projection_never_reprojected.py`
Expected: 첫 시험 FAIL — 오버레이가 `[(…-0-0, PARENT…), (…@track_overlay, CHILD, 2.0, 4.0), (…-0-0, PARENT…)]`(부모 오버레이가 자식에 깔리고 같은 id 둘). 둘째도 FAIL(자기 결과를 원본으로 다시 넣으면 같은 id가 둘 — 멱등이 깨진 것이 바로 0907의 정체다). 셋째·넷째·다섯째도 FAIL(아직 걸러 내기·문지기 없음).

- [ ] **Step 2: 생성기 고치기**

`composition_plan.py`, `_SUPPORTED_TRACKS = …` 줄 바로 아래(그 아래 주석 덩어리보다 위)에:
```python
#: materialize가 **세션에서 만들어 낸** 클립의 이름 머리(`session-{종류}-…`).
#: 이런 클립은 저장된 편집판의 원본이 아니다 -- 세션이 있으면 언제든 다시 만들어진다.
#: 2026-09-20 되돌린 커밋이 이 클립들을 0907의 `timeline_002.json`에 박아 넣었고,
#: 생성기가 그것을 원본으로 다시 투영해 오버레이가 18~22개로 불었다(2026-10-08 점검 §3-3).
SESSION_PROJECTION_CLIP_PREFIX = "session-"


def is_session_projection_clip(clip: Mapping[str, Any]) -> bool:
    return str(clip.get("clip_id") or "").startswith(SESSION_PROJECTION_CLIP_PREFIX)


def without_session_projection_clips(tracks: object) -> list[dict[str, Any]]:
    """트랙은 그대로 두고 투영 클립만 뺀 깊은 사본. 트랙 수(`summary.track_count`)는 안 바뀐다."""
    return [
        {**deepcopy(track), "clips": [deepcopy(clip) for clip in track.get("clips", []) if isinstance(clip, dict) and not is_session_projection_clip(clip)]}
        for track in (tracks if isinstance(tracks, list) else []) if isinstance(track, dict)
    ]
```
(`Mapping`이 import돼 있지 않으면 `from typing import Any, Mapping`으로 넓힌다.)
일반 트랙 고리에서 `            if track_type == "narration" and raw is global_narration_clip:` **바로 앞**에:
```python
            # 세션이 만든 클립은 원본이 아니다 -- 아래 세션 고리가 다시 만든다.
            if track_type != "narration" and is_session_projection_clip(raw):
                continue
```
세션 오버레이 붙이는 줄 `                    tracks.setdefault(("overlay", materialized_track_id("overlay")), []).append(clip)` →
```python
                    # 이름이 겹치면 렌더러가 하나를 가리고 화면 고르기가 죽는다. 일반 트랙
                    # 고리와 **같은 규칙**(`@트랙`·`-2`)으로 겹치지 않게 한다.
                    overlay_ids = {str(item.get("clip_id")) for (kind, _), bucket in tracks.items() if kind == "overlay" for item in bucket}
                    if clip["clip_id"] in overlay_ids:
                        base_id, suffix = f"{clip['clip_id']}@session", 2
                        candidate = base_id
                        while candidate in overlay_ids:
                            candidate, suffix = f"{base_id}-{suffix}", suffix + 1
                        clip["clip_id"] = candidate
                    tracks.setdefault(("overlay", materialized_track_id("overlay")), []).append(clip)
```
`output_variants.py` `master_timeline.get("tracks", []), variant_kind=variant_kind,` → `without_session_projection_clips(master_timeline.get("tracks", [])), variant_kind=variant_kind,` 그리고 파일 import에 `from videobox_core_engine.composition_plan import without_session_projection_clips`(이미 그 모듈에서 무엇을 가져오고 있으면 같은 줄에 합친다. 순환 import가 나면 함수 안에서 import).

- [ ] **Step 3: 저장 문지기**

`local_project_store.py` 모듈 함수(파일 위 `_timeline_summary_json` 근처, 클래스 밖)로:
```python
def _session_projection_clip_ids(tracks: object) -> list[str]:
    from videobox_core_engine.composition_plan import is_session_projection_clip
    return [str(clip.get("clip_id")) for track in (tracks if isinstance(tracks, list) else []) if isinstance(track, dict)
            for clip in track.get("clips", []) if isinstance(clip, dict) and is_session_projection_clip(clip)]


def _refuse_new_session_projection_clips(*, previous_tracks: object, next_tracks: object) -> None:
    """세션 투영 클립을 편집판 원본에 **새로** 쓰지 못하게 한다(2026-10-08 점검 §3-3).
    이미 있던 옛 데이터(0907)는 그대로 지나가야 매 편집의 판 번호 옮기기가 산다."""
    previous = sorted(_session_projection_clip_ids(previous_tracks))
    following = sorted(_session_projection_clip_ids(next_tracks))
    if len(following) > len(previous) or not set(following) <= set(previous):
        raise ValueError("timeline_contains_session_projection")
```
`save_timeline_run`의 `timeline_path.write_text(...)` 바로 앞: `_refuse_new_session_projection_clips(previous_tracks=[], next_tracks=payload.get("tracks"))`.
`update_timeline_run`의 `file_path = self._timeline_file_path(...)` 바로 앞: `_refuse_new_session_projection_clips(previous_tracks=existing.get("tracks"), next_tracks=payload.get("tracks"))`.

- [ ] **Step 4: GREEN**

Run Step 1 명령 → `5 passed`.

- [ ] **Step 5: 넓은 검증(렌더·변형본·placement를 지나는 시험)**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_timeline_placements.py tests/test_image_overlay_presets_reach_the_render.py tests/test_overlay_presets_are_not_erased.py tests/test_shorts_layout.py tests/test_api_output_variants.py tests/test_api_exact_preview.py tests/test_vertical_composition.py tests/test_e2e_editor_fixture.py`
Expected: 통과. **실패하면** 그 시험이 `session-` 이름의 클립을 손으로 만든 원본 편집판에 넣고 있는지 본다(예: `test_image_overlay_presets_reach_the_render.py`의 `clip_id="session-overlay-s1-0-0"`은 **렌더 계획** 입력이라 materialize를 안 지나면 무관). 원본 편집판에 넣는 시험이면 그 시험의 의도를 읽고, 의도가 "세션 오버레이가 렌더에 닿는다"면 원본 대신 세션 `visual_overlays`로 바꾼다. 같은 땜질을 두 번 하게 되면 멈추고 보고.

- [ ] **Step 6: 진짜 백엔드 시험** — `apps/web/e2e-real/duplicated-overlays.spec.mjs`:
```js
import { expect, test } from "@playwright/test";
import { readFixture, serverManifest, serverSession } from "./support/realFlow.mjs";

test("오염된 편집판에서도 오버레이 id가 겹치지 않고 자리 옮기기가 저장된다", async ({ request }) => {
  const fixture = readFixture().duplicatedOverlays;
  const manifest = await serverManifest(request, fixture);
  const overlays = manifest.tracks.filter((track) => track.track_type === "overlay").flatMap((track) => track.clips);
  const ids = overlays.map((clip) => clip.placement_id ?? clip.clip_id);
  expect(new Set(ids).size).toBe(ids.length);
  expect(overlays.map((clip) => clip.segment_id).sort()).toEqual(["timeline_001:001", "timeline_001:001__split_3"]);
  const before = await serverSession(request, fixture);
  const target = overlays[0];
  const response = await request.patch(`/api/projects/${fixture.projectId}/editing-sessions/${fixture.sessionId}/timeline-placements`, {
    data: { expected_revision: before.session_revision, changes: [{ placement_id: target.placement_id, kind: "overlay", start_sec: target.start_sec, end_sec: target.end_sec - 0.1 }] },
  });
  expect(response.status()).toBe(200);
});
```
(요청 본문 키는 `routers/editing_session.py`의 timeline-placements 요청 모델을 보고 맞춘다.) Run: `cd apps/web && npm run test:e2e:real-flow -- e2e-real/duplicated-overlays.spec.mjs` → `1 passed`.

- [ ] **Step 7: 검증 넷 + 커밋**

갭: 0907 저장 데이터는 **고치지 않았다**(Task 5, owner 결정). 동작: 0907을 **읽기만** 해서 잰다 — 컨테이너 재빌드는 Task 18에서 하므로 여기서는 저장소 코드로 직접: `.venv/Scripts/python.exe -c` 한 줄로 런타임 `timeline_002.json` + `editing_sessions/editing_session_001.json`을 읽어 `materialize_editing_session_timeline` → 오버레이 수(기대 **4**, 장면 1~4) + `collect_timeline_placements` 예외 없음을 출력해 보고에 붙인다. 배선: `grep -n "is_session_projection_clip\|without_session_projection_clips" -r packages` → 정의 1 + 사용 ≥3.
```bash
git add packages/core-engine/src/videobox_core_engine/composition_plan.py packages/core-engine/src/videobox_core_engine/output_variants.py packages/storage-abstractions/src/videobox_storage/local_project_store.py tests/test_session_projection_never_reprojected.py apps/web/e2e-real/duplicated-overlays.spec.mjs
git commit -m "fix(timeline): 저장된 편집판의 세션 투영 클립을 원본으로 다시 투영하지 않는다

0907 timeline_002에 박힌 session-overlay 클립을 생성기가 부모를 가리키는 모든
조각에 깔고 같은 id를 두 번 붙여 자르기·옮기기가 전부 422였다. 투영 클립은
건너뛰고, 세션 오버레이 이름 충돌을 막고, 변형본 복사와 저장에서 새로 박히지
않게 한다. 이미 있는 옛 데이터는 그대로 지나간다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 오염된 편집판 찾기·고치기·되돌리기 도구(기본은 미리보기만) — 약 1.5시간

**왜 따로인가:** Task 4 뒤로 0907은 **고치지 않아도** 동작한다(읽을 때 건너뛴다). 남은 것은 파일 속 쓰레기 15줄이다. 지우는 것은 대표님 실제 프로젝트 데이터를 바꾸는 일이라 **owner 결정 뒤에만** 한다. 이 Task는 도구와 미리보기까지만.

**Files:**
- Create: `scripts/repair_session_projection_timelines.py`
- Create: `tests/test_repair_session_projection_timelines.py`

**Interfaces:**
- Consumes: `without_session_projection_clips`, `is_session_projection_clip`(Task 4).
- Produces: `find_contaminated_timelines(projects_dir: Path) -> list[dict]`(각 `{"project_id","timeline_file","projection_clip_count","duplicate_clip_ids"}`), `strip_projection_clips(payload: dict) -> tuple[dict, int]`, `main(argv: Sequence[str] | None = None, *, now: datetime | None = None) -> int`.
- 명령: 미리보기 `… repair_session_projection_timelines.py`(기본), 적용 `--apply --project <id>`(**`--project` 없으면 거절**), 되돌리기 `--undo <목록.json>`(`--force-undo` 없이는 지금 파일 해시가 고친 직후 해시와 같을 때만). 기본 폴더 `--projects-dir`=`resolve_projects_root()/"runtime"/"projects"`. 되돌릴 목록은 `artifacts/timeline-projection-repair/<UTC>.json`(지우지 않는다 — 원래 내용은 다시 만들 수 없다, §10.16).
- 쓰기는 **파일만**: 같은 폴더에 `<이름>.bak-h-<UTC>` 복사 → 임시 파일에 쓰고 `os.replace`(원자적). 트랙 수는 그대로(빈 `clips` 허용)라 DB `summary_json`은 안 바뀐다. 실행 중인 컨테이너가 같은 파일을 읽는다 — DB를 호스트에서 열지 않는다.

- [ ] **Step 1: 시험(RED)** — `tests/test_repair_session_projection_timelines.py`: `tmp_path/"p1/timelines/timeline_002.json"`에 Task 4 시험의 `_base(with_projection=True)` 모양(+같은 id 한 번 더)을, `tmp_path/"p2/timelines/timeline_001.json"`에 깨끗한 것을 쓰고:
  - `find_contaminated_timelines(tmp_path)` → p1 하나, `projection_clip_count == 2`, `duplicate_clip_ids == ["session-overlay-timeline_001:001-0-0"]`.
  - `main([..."--projects-dir", str(tmp_path)])`(미리보기) → 0, 파일 해시 그대로.
  - `main(["--projects-dir", str(tmp_path), "--apply"])` → 2(거절, `--project` 필요), 파일 그대로.
  - `main(["--projects-dir", str(tmp_path), "--apply", "--project", "p1"], now=fixed)` → 0, p1 파일의 오버레이 트랙 `clips == []`, 내레이션 클립 그대로, `.bak-h-…` 존재, 되돌릴 목록에 `before_sha256`·`after_sha256`.
  - `main(["--projects-dir", str(tmp_path), "--undo", <목록>])` → 0, 파일 해시가 원래와 같다.
  - 고친 뒤 파일을 손으로 바꾸고 `--undo` → 0이 아닌 값, 파일 그대로(`--force-undo`면 복원).
  `scripts` 모듈 불러오기는 Task 1과 같은 방식.
Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_repair_session_projection_timelines.py` → FAIL(모듈 없음).

- [ ] **Step 2: 구현 → GREEN** — 머리 docstring은 `repair_mojibake_library_filenames.py`의 형식(무엇을·언제 고치는가·세 명령·되돌릴 목록을 왜 안 지우나)을 따른다. 미리보기 출력은 한국어 표(프로젝트·파일·투영 클립 수·겹친 id). Run → 통과.

- [ ] **Step 3: 실제 데이터에 미리보기만** — Run: `.venv/Scripts/python.exe scripts/repair_session_projection_timelines.py` → 기대 `0907-b26195af timeline_002.json 투영 15 · 겹친 id 4` 한 줄(다른 프로젝트 0). **`--apply`는 실행하지 않는다.** 출력을 보고에 붙인다.

- [ ] **Step 4: 검증 넷 + 커밋**

갭: 적용 안 함(owner 결정 1). 배선: `grep -n "without_session_projection_clips" scripts/repair_session_projection_timelines.py` ≥1.
```bash
git add scripts/repair_session_projection_timelines.py tests/test_repair_session_projection_timelines.py
git commit -m "feat(scripts): 세션 투영 클립이 박힌 편집판을 찾고, 승인 뒤 백업과 함께 걷어 내는 도구

기본은 미리보기만 한다. --apply는 --project가 있어야 하고 .bak과 되돌릴 목록을
남긴다. 0907 적용은 owner 결정 뒤.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 편집 대상 목록 폭증·React #185·영어 오류 화면 — 약 2.5시간

**Files:**
- Modify: `apps/web/src/features/editor/inspector/inspectorRegistry.ts` — 앵커 `export function projectInspectorTargets(`, `    .filter((caption) => caption.segmentId === selectedSegmentId)`
- Modify: `apps/web/src/features/editor/workbench/RightDock.tsx` — 앵커 `  }, [inspectorTargetIdentity, inspectorTargets]);`
- Create: `apps/web/src/app/RouteErrorFallback.tsx`, `apps/web/src/app/RouteErrorFallback.test.tsx`
- Modify: `apps/web/src/app/AppRouter.tsx` — 앵커 `  return createRouter({ routeTree, context: { catalog }, history });`
- Test: `apps/web/src/features/editor/inspector/inspectorRegistry.test.ts`, `apps/web/src/features/editor/workbench/right-dock.test.tsx`

**Interfaces:**
- Produces: `projectInspectorTargets`가 **id가 겹치지 않고**, 같은 이름이 둘 이상이면 `이미지 1`·`이미지 2`처럼 번호를 붙이고, 캡션은 `owningSegmentId ?? segmentId`로 거른 목록을 돌려준다.
- Produces: `RouteErrorFallback({ error, reset }: { error: unknown; reset: () => void })` — 제목 `화면을 그리다 멈췄어요`, 본문 `다시 그려 볼게요. 그래도 안 되면 프로젝트 목록으로 돌아가 주세요.`, 단추 `다시 그리기`(reset) · 링크 `프로젝트 목록으로`(`/projects`). 영어 없음. 오류 원문은 `<details><summary>자세한 내용</summary>`에만.

- [ ] **Step 1: 재현부터(측정, 제품 변경 없음)** — 개발 빌드는 React 오류를 풀어서 보여 준다. 진짜 백엔드 하네스(개발 서버라 이미 개발 빌드)에서 **오염된** 고정 프로젝트를 1440×900으로 열고 Playwright로: 클립 고르기·분할(`Ctrl+B`)·되돌리기(`Ctrl+Z`)를 섞어 12번 → `내보내기` 클릭. `page.on("console")`과 `page.on("pageerror")`를 모두 모은다. 이 스크립트는 `apps/web/e2e-real/react-185-repro.spec.mjs`로 남기고(시험은 "편집기 영역이 `Something went wrong`을 그리지 않는다" + "편집 대상 옵션 수 ≤ 고유 값 수"를 단언), **Task 4 커밋 앞에서**(`git stash` 없이 `git worktree add ../h-repro <Task 3 커밋>` 임시 작업 폴더로) 한 번, 지금 커밋에서 한 번 돈다.
  - 앞 커밋에서 `Maximum update depth exceeded`(#185)가 나오면 **컴포넌트 스택**을 보고에 붙이고, 그 스택이 가리키는 effect를 Step 3에서 고친다.
  - 안 나오면 "재현 안 됨(2회)"이라 적는다. **고쳤다고 말하지 않는다** — Step 4의 오류 화면이 안전망이다.
  - 임시 작업 폴더는 끝나면 `git worktree remove ../h-repro`.

- [ ] **Step 2: 목록 시험(RED)** — `inspectorRegistry.test.ts`에(파일의 기존 `view` 모양을 따른다):
```ts
it("같은 오버레이 id가 두 번 와도 편집 대상은 하나이고, 같은 이름은 번호로 구분한다 (2026-10-08 §3-6)", () => {
  const overlay = (clipId: string) => ({ clipId, segmentId: "segment-1", type: "overlay", assetId: "img", assetUri: "local://a.png", startSec: 0, endSec: 1, controls: {}, overlayType: "image_overlay", overlayPayload: {} });
  const targets = projectInspectorTargets({
    view: { ...view, tracks: [{ trackId: "o", role: "overlay", clips: [overlay("dup"), overlay("dup"), overlay("other")] }], captions: [] } as never,
    selectedSegmentId: "segment-1",
  });
  expect(targets.map((target) => target.id)).toEqual(["overlay:dup", "overlay:other"]);
  expect(targets.map((target) => target.label)).toEqual(["이미지 1", "이미지 2"]);
});

it("캡션은 그 장면에 실제로 놓인 것만 -- 계보가 같은 형제 자막은 빼고", () => {
  const caption = (captionId: string, owningSegmentId: string) => ({ captionId, segmentId: "segment-1", owningSegmentId, text: "t", startSec: 0, endSec: 1, style: {} });
  const targets = projectInspectorTargets({
    view: { ...view, tracks: [], captions: [caption("c-1", "segment-1"), caption("c-2", "segment-1__split_2")] } as never,
    selectedSegmentId: "segment-1",
  });
  expect(targets.filter((target) => target.kind === "caption").map((target) => target.id)).toEqual(["caption:c-1"]);
});
```
`right-dock.test.tsx`에: 같은 `id` 둘을 가진 `inspectorTargets`로 `RightDock`을 그리고 `rerender`를 5번(매번 새 배열) → `screen.getByRole("combobox", { name: "편집 대상" })`의 `option` 수가 **고유 id 수와 같다**.
Run: `cd apps/web && npx vitest run src/features/editor/inspector/inspectorRegistry.test.ts src/features/editor/workbench/right-dock.test.tsx` → 새 시험 FAIL(옵션이 쌓이거나 id 중복, 라벨 번호 없음, 캡션 2개).

- [ ] **Step 3: 구현 → GREEN**
  - `projectInspectorTargets`의 캡션 거르기 `caption.segmentId === selectedSegmentId` → `(caption.owningSegmentId ?? caption.segmentId) === selectedSegmentId`.
  - 함수가 돌려주기 직전에 같은 파일의 새 내부 함수 `distinctTargets(targets: readonly InspectorTarget[]): readonly InspectorTarget[]`를 거친다: id 첫 번째만 남기고, 같은 `label`이 2개 이상인 것들에 등장 순서대로 ` 1`, ` 2`를 붙인다.
  - `RightDock.tsx` effect 의존값 `[inspectorTargetIdentity, inspectorTargets]` → `[inspectorTargetIdentity]` + effect 안에서 쓰는 배열은 `inspectorTargetsRef.current`(렌더마다 `useRef`에 최신값을 넣는다). 매 렌더 새 배열로 effect가 도는 것을 끊는다.
  - Step 1에서 컴포넌트 스택을 얻었다면 그 effect를 같은 방식(의존값을 내용 기준 식별자로)으로 고치고, 그 재현을 시험으로 하나 더 쓴다.
  Run Step 2 명령 → 통과.

- [ ] **Step 4: 영어 오류 화면(RED→GREEN)** — `RouteErrorFallback.test.tsx`:
```tsx
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { RouteErrorFallback } from "./RouteErrorFallback";
import { createAppRouter } from "./AppRouter";

describe("라우트 오류 화면", () => {
  it("영어 대신 한국어로 말하고 다시 그리기를 준다 (2026-10-08 §3-6 React #185)", () => {
    const reset = vi.fn();
    render(<RouteErrorFallback error={new Error("Minified React error #185")} reset={reset} />);
    expect(screen.getByRole("heading", { name: "화면을 그리다 멈췄어요" })).toBeVisible();
    expect(screen.queryByText(/Something went wrong|Show Error/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "다시 그리기" }));
    expect(reset).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("link", { name: "프로젝트 목록으로" })).toHaveAttribute("href", "/projects");
  });
  it("라우터 기본 오류 화면으로 걸려 있다", () => {
    expect(createAppRouter().options.defaultErrorComponent).toBe(RouteErrorFallback);
  });
});
```
RED: 모듈 없음. 구현: `RouteErrorFallback.tsx`(공용 `Button`, 링크는 `<a href="/projects">` — 라우터 밖에서도 그려질 수 있다), `AppRouter.tsx` `createRouter({ routeTree, context: { catalog }, history })` → `createRouter({ routeTree, context: { catalog }, history, defaultErrorComponent: RouteErrorFallback })`. GREEN.

- [ ] **Step 5: 넓은 검증 + 검증 넷 + 커밋**

Run: `cd apps/web && npx vitest run src/features/editor/inspector src/features/editor/workbench/right-dock.test.tsx src/app src/user-copy-policy.test.ts` → 통과. `npx tsc --noEmit` → 0. Run: `npm run test:e2e:real-flow -- e2e-real/react-185-repro.spec.mjs` → `1 passed`.
갭: #185 재현 여부·스택(Step 1). 배선: `grep -n "defaultErrorComponent" apps/web/src/app/AppRouter.tsx` 1줄, `grep -n "distinctTargets" apps/web/src/features/editor/inspector/inspectorRegistry.ts` 정의 1 + 사용 1.
```bash
git add apps/web/src/features/editor/inspector/inspectorRegistry.ts apps/web/src/features/editor/inspector/inspectorRegistry.test.ts apps/web/src/features/editor/workbench/RightDock.tsx apps/web/src/features/editor/workbench/right-dock.test.tsx apps/web/src/app/RouteErrorFallback.tsx apps/web/src/app/RouteErrorFallback.test.tsx apps/web/src/app/AppRouter.tsx apps/web/e2e-real/react-185-repro.spec.mjs
git commit -m "fix(editor): 편집 대상이 겹친 id로 수천 개 쌓이지 않고, 라우트 오류는 한국어로

같은 오버레이 id를 하나로, 같은 이름은 번호로 구분하고, 캡션은 그 장면에
실제로 놓인 것만 보인다. 라우터 기본 오류 화면(영어)을 한국어 화면으로 바꾼다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 트랙 머리를 클립과 겹치지 않는 고정 칸으로(스파이크 H-b) — 약 4시간

**Files:**
- Create: `apps/web/src/features/editor/timeline/timelineCssMetrics.ts`, `…/timelineCssMetrics.test.ts`
- Modify: `apps/web/src/features/editor/timeline/TimelineDock.tsx` — 앵커 `const LANE_HEIGHT_PX = 32;`, `const LANE_HEADER_DEAD_ZONE_PX = 180;`(정의와 그 위 주석 덩어리 삭제), `<div className="vb-timeline-scale" style={{ position: "relative" }}>`, `      <div aria-label="고정 트랙" role="list">`, `          const laneNeedsClipAccess = draftProjection.rects.some(`, `          const clusterPointerEvents: "auto" | "none" = laneNeedsClipAccess ? "none" : "auto";`, 단추 셋의 `style={{ pointerEvents: clusterPointerEvents }}`
- Modify: `apps/web/src/styles/editor-workbench.css`(파일 끝에 블록 하나)
- Test: `apps/web/src/features/editor/timeline/timeline-dock.test.tsx` — 시험 둘 교체(`it("트랙 이름과 잠금·눈·음소거가 클립에 가리지 않는다 (죽은 자리에 클립이 없을 때)"`, `it("컷 편집으로 0초 근처에 짧게 남은 클립이 있으면 그 트랙 버튼이 클릭을 양보한다"`)

**Interfaces:**
- Produces: `readCssPixels(element: Element | null, name: string, fallbackPx: number): number`(계산값이 `NNpx`면 그 수, 비었거나 숫자가 아니면 fallback — jsdom은 늘 fallback).
- 화면 구조(바뀐 뒤):
```
section.vb-editor-workbench__timeline
  div.vb-editor-workbench__timeline-head            (그대로)
  div.vb-timeline-body                               display:grid; grid-template-columns: var(--vb-timeline-header-w) minmax(0,1fr)
    div[role=list][aria-label="고정 트랙"].vb-timeline-lane-headers   (왼쪽 고정 칸, 눈금 높이만큼 위 여백 + 트랙마다 한 줄)
    div.vb-timeline-lanes-viewport                   (오른쪽, overflow:hidden — 클립 좌표의 원점)
      div.vb-timeline-scale (눈금)
      div[data-timeline-track][data-testid=timeline-track]
        div[role=group][aria-label="타임라인 클립"]   (그대로)
      div.vb-timeline-playhead                        (그대로 — 원점이 같은 칸이라 x 식 그대로)
  div.vb-editor-workbench__timeline-foot            (그대로)
```
- 좌표 원점: 클립·재생줄·클릭 seek·바퀴 기준·끌어 놓기가 **모두 `[data-timeline-track]` 왼쪽**을 원점으로 쓴다(지금도 `handleClick`·`pointerTimelineX`·`handleWheel`이 그 요소를 찾는다). 재생줄은 `data-timeline-track`과 같은 부모(`.vb-timeline-lanes-viewport`) 안에 있어야 한다 — 바깥에 두면 머리 칸 폭만큼 어긋난다(스파이크 §7 위험).
- 트랙 높이: `LANE_HEIGHT_PX` 상수 → 컴포넌트 안 `const laneHeightPx = readCssPixels(surfaceRef.current, "--vb-timeline-lane-h", 32)`(첫 렌더는 32, 마운트 뒤 한 번 다시 읽어 `useState`에 둔다). 클립 줄과 머리 줄이 **같은 값**을 쓴다.
- 클립 칸 폭: `viewportWidthPx` 그대로 받되, `.vb-timeline-lanes-viewport`를 `ResizeObserver`로 재서 0보다 크면 그 값을 쓴다(jsdom은 관찰 콜백이 없어 기존 시험의 400px이 그대로 간다). 점검의 가로 넘침 29px이 이것으로 사라진다.

- [ ] **Step 1: `readCssPixels` 시험·구현(RED→GREEN)** — `timelineCssMetrics.test.ts`: (1) 요소 `null` → fallback, (2) `style.setProperty("--x","44px")` 후 `readCssPixels(el,"--x",32)`은 jsdom이 `getComputedStyle`에 사용자 변수를 반영하면 44, 아니면 32 — 둘 다 허용하지 말고 `vi.spyOn(window, "getComputedStyle").mockReturnValue({ getPropertyValue: () => " 44px" } as never)`로 44를 단언, (3) `"abc"` → fallback. 구현은 `parseFloat` + `Number.isFinite` + `> 0`.

- [ ] **Step 2: 머리 칸 시험(RED)** — 두 시험을 지우고 같은 자리에:
```tsx
  it("트랙 머리는 클립 층 밖의 고정 칸이라 0초 클립이 있어도 마우스로 눌린다 (2026-10-08 §3-4)", () => {
    const onUpdateTrackStates = vi.fn();
    render(<TimelineDock view={cutEditedBrollView} viewportWidthPx={400} onUpdateTrackStates={onUpdateTrackStates} />);

    const headers = screen.getByRole("list", { name: "고정 트랙" });
    const track = screen.getByTestId("timeline-track");
    expect(track.contains(headers)).toBe(false);
    expect(headers.contains(track)).toBe(false);
    expect(headers.closest(".vb-timeline-body")).toBe(track.closest(".vb-timeline-body"));
    for (const name of ["내레이션 트랙 잠금", "내레이션 트랙 음소거", "영상 트랙 잠금", "영상 트랙 숨기기", "영상 트랙 음소거"]) {
      expect(screen.getByRole("button", { name }).style.pointerEvents).toBe("");
    }
    fireEvent.click(screen.getByRole("button", { name: "영상 트랙 음소거" }));
    expect(onUpdateTrackStates).toHaveBeenCalledWith({ broll: { muted: true } });
    // 0초 자투리 클립도 그대로 고를 수 있다.
    selectTimelineClip("b-cut-1");
    expect(timelineClipSelection("b-cut-1")).toHaveAttribute("aria-pressed", "true");
  });

  it("재생줄과 클립은 같은 원점(클립 칸 왼쪽)에 놓인다", () => {
    render(<TimelineDock view={view} viewportWidthPx={400} playbackSec={5} />);
    const playhead = screen.getByTestId("timeline-playhead");
    expect(playhead.parentElement).toBe(screen.getByTestId("timeline-track").parentElement);
    const n1 = screen.getAllByTestId("timeline-clip").find((clip) => clip.getAttribute("data-clip-id") === "b-1")!;
    expect(playhead.style.left).toBe(n1.style.left); // b-1은 5초에 시작한다
  });
```
Run: `cd apps/web && npx vitest run src/features/editor/timeline/timeline-dock.test.tsx -t "고정 칸|같은 원점"` → FAIL.

- [ ] **Step 3: 구현 → GREEN**
  1. `LANE_HEADER_DEAD_ZONE_PX` 상수·주석, `laneNeedsClipAccess`·`clusterPointerEvents` 두 줄, 단추 셋의 `style={{ pointerEvents: clusterPointerEvents }}`, 머리 줄 `listitem`의 `zIndex: 4, pointerEvents: "none"`을 지운다. 그 자리 주석에 "2026-10-08: 머리를 별도 칸으로 빼서 양보 규칙이 필요 없어졌다(점검 §3-4, 스파이크 §3(가))" 한 줄.
  2. 위 구조로 JSX를 옮긴다. `<div aria-label="고정 트랙" role="list">` 블록 전체를 `.vb-timeline-body`의 첫 칸으로, `.vb-timeline-scale`·`[data-timeline-track]`·재생줄을 `.vb-timeline-lanes-viewport` 안으로. 머리 칸 첫 자식 앞에 눈금 높이만큼 빈 자리(`<div aria-hidden="true" className="vb-timeline-lane-headers__ruler-spacer" />`)를 둔다 — `role=list`의 직계 자식은 `listitem`만이어야 하므로(`keeps the fixed lane list free of non-listitem direct children` 시험) spacer는 **list 바깥 감싸개**에 둔다: `div.vb-timeline-lane-headers > (spacer, div[role=list])`.
  3. CSS(파일 끝):
```css
/* 트랙 머리 고정 칸(2026-10-08 점검 §3-4, 스파이크 H-b). 크기는 변수로만 -- 계획 I가 밀도를 바꾼다. */
.vb-editor-workbench { --vb-timeline-header-w: 7.5rem; --vb-timeline-lane-h: 32px; --vb-trim-handle-w: 8px; --vb-trim-hit-w: 14px; --vb-ruler-label-min-gap: 120px; }
.vb-timeline-body { display: grid; grid-template-columns: var(--vb-timeline-header-w) minmax(0, 1fr); min-width: 0; }
.vb-timeline-lane-headers { min-width: 0; border-right: 1px solid var(--border); }
.vb-timeline-lane-headers__ruler-spacer { height: 1.5rem; }
.vb-timeline-lane-headers [role="listitem"] { display: flex; align-items: center; gap: var(--vb-space-1); height: var(--vb-timeline-lane-h); padding-inline: var(--vb-space-1); border-top: 1px solid var(--border); overflow: hidden; }
.vb-timeline-lane-headers [role="listitem"] > span { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.vb-timeline-lanes-viewport { position: relative; min-width: 0; overflow: hidden; }
```
  (단추 글꼴·모양은 계획 I. 머리 줄의 인라인 `height: ${LANE_HEIGHT_PX}px`는 지우고 위 변수로.)
  4. `ResizeObserver`로 `.vb-timeline-lanes-viewport` 폭을 재는 `const [measuredTrackWidthPx, setMeasuredTrackWidthPx] = useState(0)` + effect, `const trackWidthPx = measuredTrackWidthPx > 0 ? measuredTrackWidthPx : viewportWidthPx`. 이 컴포넌트에서 `viewportWidthPx`를 쓰던 곳(`zoomBounds`·`options`·`resolveViewportEnd`·`fitPixelsPerSecond`) 전부를 `trackWidthPx`로.
  Run Step 2 명령 → 통과.

- [ ] **Step 4: 넓은 검증** — Run: `cd apps/web && npx vitest run src/features/editor/timeline src/features/editor/workbench src/styles src/task22-parity-owners.test.ts src/user-copy-policy.test.ts` → 이미 알려진 1건 외 통과. 좌표 시험이 깨지면 원점을 하나만 옮긴 것이다 — 재생줄·클릭·바퀴·끌어 놓기 넷의 원점이 모두 `[data-timeline-track]`인지 본다. `npx tsc --noEmit` → 0.

- [ ] **Step 5: 진짜 포인터 e2e** — `apps/web/e2e-real/track-headers.spec.mjs`: 깨끗한 고정 프로젝트, 1440×900. `영상 트랙 음소거` 단추의 중심 좌표를 `boundingBox()`로 얻어 `page.mouse.click(x, y)` → (1) 클릭 전 `document.elementFromPoint(x,y)?.closest("button")?.getAttribute("aria-label") === "영상 트랙 음소거"`, (2) 3초 안에 `serverManifest(...).track_states.broll.muted === true`, (3) `Control+Z` → 다시 `track_states`에 broll 없음. 같은 방식으로 `내레이션 트랙 음소거`·`오버레이 트랙 숨기기`·`캡션 트랙 숨기기`의 `elementFromPoint`가 자기 자신. 그리고 타임라인 섹션 `scrollWidth - clientWidth <= 1`(가로 넘침 0). Run → `1 passed`.

- [ ] **Step 6: 검증 넷 + 커밋**

갭: 세로 스크롤 동기(트랙이 많아져 세로로 넘칠 때)는 지금 트랙 6개 고정이라 안 만들었다 — 적는다. 동작: Step 5 `elementFromPoint` 넷·넘침 px. 배선: `grep -n "LANE_HEADER_DEAD_ZONE_PX\|clusterPointerEvents" apps/web/src/features/editor/timeline/TimelineDock.tsx` → **0줄**, `grep -n "vb-timeline-body" apps/web/src` → TSX 1 + CSS ≥1.
```bash
git add apps/web/src/features/editor/timeline/timelineCssMetrics.ts apps/web/src/features/editor/timeline/timelineCssMetrics.test.ts apps/web/src/features/editor/timeline/TimelineDock.tsx apps/web/src/features/editor/timeline/timeline-dock.test.tsx apps/web/src/styles/editor-workbench.css apps/web/e2e-real/track-headers.spec.mjs
git commit -m "fix(timeline): 트랙 머리를 클립 옆 고정 칸으로 -- 잠금·숨기기·음소거가 마우스로 눌린다

머리 뭉치가 클립 위에 떠 있다가 0초 클립이 있으면 클릭을 양보해 13개 중
9개가 영영 안 눌렸다. 머리를 별도 칸으로 빼고 양보 규칙을 지운다. 크기는
CSS 변수라 계획 I가 로직을 안 건드리고 촘촘하게 만들 수 있다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: 자르기 손잡이를 클립 가장자리로, 몸통을 끌면 옮기기(스파이크 H-c) — 약 5시간

**Files:**
- Modify: `apps/web/src/features/editor/timeline/TimelineDock.tsx` — 앵커 `{narrationClip && isSelected ? <span data-mutation-controls="true"`(내레이션 셋)와 `{placement && isSelected ? <span data-placement-controls="true"`(배치 셋)
- Modify: `apps/web/src/styles/editor-workbench.css`(Task 7 블록 아래)
- Test: `apps/web/src/features/editor/timeline/timeline-dock.test.tsx`(`describe` 안 끝에 추가)

**Interfaces:**
- 바뀌지 않는 것: 단추 이름(`… 시작 자르기`·`… 끝 자르기`·`… 이동`·`… 순서 바꾸기`), `data-native-control` 이름 여섯, 키보드 손잡이(`keyboardTrim`·`keyboardReorder`·`keyboardPlacementTrim`·`keyboardPlacementMove`) — **키보드 조작은 그대로 산다**.
- 바뀌는 것: 보이는 글자(`시작`·`이동`·`끝`·`순서`)는 `<span className="sr-only">`로만. 자리 — 시작 손잡이 `left:0`, 끝 손잡이 `right:0`, 둘 다 `width: var(--vb-trim-hit-w)`(잡는 폭 14px), 안쪽 보이는 띠 `::before`가 `var(--vb-trim-handle-w)`(8px). 이동/순서 단추는 두 손잡이 **사이 전체**(`left/right: var(--vb-trim-hit-w)`)를 투명하게 덮고 `cursor: grab`. 손잡이 `cursor: ew-resize`.
- 좁은 클립 정책(Review Focus 5): 클립 폭 `< 3 × 14px`(=42px)이면 이동 단추를 **그리지 않고**(키보드로는 Task 기존 `keyboardPlacementMove`가 클립 선택 단추… 가 아니라 이동 단추에 붙어 있으므로) — 대신 이동 단추를 `sr-only` 크기로 남겨 **초점·키보드는 산다**, 마우스 몸통 끌기만 없다. 그 클립의 `title`에 `확대하면 끌어서 옮길 수 있어요`. 손잡이는 각각 클립 폭의 절반까지만(`max-width: 50%`).

- [ ] **Step 1: 시험(RED)** — `timeline-dock.test.tsx`에(`selectTimelineClip`으로 배치 클립 `b-1`(5~9초, 400px/20초=20px/초 → 80px 폭)과 내레이션 `n-1`(0~5초 100px)을 고른다):
```tsx
  it("자르기 손잡이는 클립 양 끝의 얇은 띠이고 글자를 보이지 않는다 (2026-10-08 §3-8)", () => {
    render(<TimelineDock view={view} viewportWidthPx={400} onUpdatePlacements={vi.fn()} />);
    selectTimelineClip("b-1");
    const start = screen.getByRole("button", { name: /영상 1.* 시작 자르기$/ });
    const end = screen.getByRole("button", { name: /영상 1.* 끝 자르기$/ });
    const move = screen.getByRole("button", { name: /영상 1.* 이동$/ });
    expect(start).toHaveClass("vb-trim-handle", "vb-trim-handle--start");
    expect(end).toHaveClass("vb-trim-handle", "vb-trim-handle--end");
    expect(move).toHaveClass("vb-clip-body-drag");
    for (const control of [start, end, move]) expect(control.querySelector(".sr-only")).not.toBeNull();
    expect(start.closest("[data-placement-controls]")).not.toBeNull();
  });

  it("손잡이는 키보드로 한 프레임씩 그대로 움직인다", () => {
    const onUpdatePlacements = vi.fn();
    render(<TimelineDock view={view} viewportWidthPx={400} onUpdatePlacements={onUpdatePlacements} />);
    selectTimelineClip("b-1");
    fireEvent.keyDown(screen.getByRole("button", { name: /영상 1.* 끝 자르기$/ }), { key: "ArrowLeft" });
    expect(onUpdatePlacements).toHaveBeenCalledTimes(1);
    expect(onUpdatePlacements.mock.calls[0][0].changes[0].endSec).toBeCloseTo(9 - 1 / 25, 6);
  });

  it("좁은 클립은 손잡이만 그리고 몸통 끌기는 확대 안내로 바꾼다", () => {
    render(<TimelineDock view={cutEditedBrollView} viewportWidthPx={400} onUpdatePlacements={vi.fn()} />);
    selectTimelineClip("b-cut-1"); // 0.3초 -- 몇 px짜리 자투리
    const move = screen.getByRole("button", { name: /이동$/ });
    expect(move).toHaveClass("sr-only");
    expect(move.closest("[data-testid=timeline-clip]")).toHaveAttribute("title", "확대하면 끌어서 옮길 수 있어요");
  });
```
(배치 클립이 `placementId`를 가져야 배치 손잡이가 그려진다. 시험 `view`의 `b-1`에 `placementId`가 없으면 그 시험 안에서 `{ ...view, tracks: view.tracks.map(...) }`로 `placementId: "broll:b-1"`을 붙인다. 이름 정규식은 `formatClipDisplayName` 결과에 맞춘다.)
Run: `cd apps/web && npx vitest run src/features/editor/timeline/timeline-dock.test.tsx -t "손잡이|좁은 클립"` → FAIL(클래스 없음).

- [ ] **Step 2: 구현 → GREEN** — 두 덩어리의 단추 여섯을 위 Interfaces대로: 인라인 `style`의 3등분(`width: "33.333%"`·`left: "33.333%"`)과 배치 쪽 `display:flex` 줄을 지우고 클래스로. 클립 폭은 `rect.width`로 판단(`const narrow = rect.width < 42`). CSS:
```css
/* 가장자리 손잡이(2026-10-08 점검 §3-8, 스파이크 H-c). 잡는 폭은 넓게, 보이는 띠는 얇게. */
.vb-trim-handle { position: absolute; top: 0; bottom: 0; width: var(--vb-trim-hit-w); max-width: 50%; padding: 0; border: 0; background: transparent; cursor: ew-resize; pointer-events: auto; }
.vb-trim-handle::before { content: ""; position: absolute; top: 0; bottom: 0; width: var(--vb-trim-handle-w); background: var(--vb-accent); border-radius: var(--vb-radius-sm); }
.vb-trim-handle--start { left: 0; } .vb-trim-handle--start::before { left: 0; }
.vb-trim-handle--end { right: 0; } .vb-trim-handle--end::before { right: 0; }
.vb-clip-body-drag { position: absolute; top: 0; bottom: 0; left: var(--vb-trim-hit-w); right: var(--vb-trim-hit-w); padding: 0; border: 0; background: transparent; cursor: grab; pointer-events: auto; }
.vb-clip-body-drag:active { cursor: grabbing; }
.vb-trim-handle:focus-visible, .vb-clip-body-drag:focus-visible { outline: 2px solid var(--vb-accent); outline-offset: -2px; }
```
Run Step 1 명령 → 통과.

- [ ] **Step 3: 넓은 검증** — `cd apps/web && npx vitest run src/features/editor/timeline src/task22-parity-owners.test.ts src/user-copy-policy.test.ts` → 통과(허용 목록 그대로여야 한다). `npx tsc --noEmit` → 0.

- [ ] **Step 4: 진짜 포인터 e2e** — `apps/web/e2e-real/edge-trim.spec.mjs`: 깨끗한 고정 프로젝트에서 `영상 2번째` 클립을 고르고, 끝 손잡이 `boundingBox()`의 가운데에서 `page.mouse.down()` → 왼쪽으로 20px 이동 → `up()`. 3초 안에 서버 세션의 그 장면 B-roll 배치(또는 매니페스트 그 클립 `end_sec`)가 줄었고, `Control+Z` 뒤 원래 값. 그리고 몸통(`이동`) 가운데를 잡고 오른쪽 15px → 서버 `start_sec`이 늘었는지, 되돌리기. Run → `1 passed`.

- [ ] **Step 5: 검증 넷 + 커밋** — 동작: e2e 서버 값 전후. 배선: `grep -c "vb-trim-handle" apps/web/src/features/editor/timeline/TimelineDock.tsx` ≥4.
```bash
git add apps/web/src/features/editor/timeline/TimelineDock.tsx apps/web/src/features/editor/timeline/timeline-dock.test.tsx apps/web/src/styles/editor-workbench.css apps/web/e2e-real/edge-trim.spec.mjs
git commit -m "fix(timeline): 자르기 손잡이를 클립 양 끝 띠로, 몸통을 끌면 옮기기

가운데 모인 '시작·이동·끝' 글자 단추를 캡컷처럼 가장자리 손잡이로 바꾼다.
단추 이름과 키보드 한 프레임 조작은 그대로다. 좁은 클립은 손잡이만 그린다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: 끌기·자르기 중에 붙기(스냅) 배선(스파이크 H-d) — 약 3시간

**왜:** `findTimelineSnap`은 맞게 동작하는데(스파이크 실측: 24초 끝에 붙음), 화면은 재생줄 옆 "스냅: …" 글자 표시에만 쓴다. 끌기·자르기 중에는 한 번도 안 부른다.

**Files:**
- Create: `apps/web/src/features/editor/timeline/dragSnap.ts`, `…/dragSnap.test.ts`
- Modify: `TimelineDock.tsx` — 앵커 `  const placementBoundsAtPointer = (draft: PlacementMoveDraft | PlacementTrimDraft, event: PointerEvent<HTMLElement>) => {`, `  const trimSecondsAtPointer = (draft: Extract<PointerDraft, { kind: "trim" }>, event: PointerEvent<HTMLElement>): number => {`
- Modify: `apps/web/src/styles/editor-workbench.css`(안내선 한 줄)

**Interfaces:**
- Consumes: `findTimelineSnap(request: TimelineSnapRequest): TimelineSnap | null`, `SnapCandidate`(`snapping.ts`).
- Produces:
```ts
export type DragSnapInput = Readonly<{
  mode: "move" | "start" | "end";
  proposedSec: number;          // move면 새 시작, start/end면 그 가장자리
  durationSec: number;          // move에서만 씀(클립 길이)
  candidates: readonly SnapCandidate[];
  excludeIdPrefix: string;      // 끄는 클립 자신의 후보(`clip:${clipId}:`)를 뺀다
  scale: Readonly<{ pixelsPerSecond: number; originSec: number }>;
  fps: Readonly<{ num: number; den: number }>;
  thresholdPx: number;
}>;
export function snapDragProposal(input: DragSnapInput): Readonly<{ proposedSec: number; snap: TimelineSnap | null }>;
```
move는 **시작과 끝 둘 다** 붙여 보고(openreel처럼 클립 끝도) 더 가까운 쪽으로 시작을 옮긴다. 붙지 않으면 그대로.

- [ ] **Step 1: 시험(RED)** — `dragSnap.test.ts`: 후보 `[{kind:"neighbor-end", id:"clip:a:end", timeSec:24}, {kind:"neighbor-start", id:"clip:self:start", timeSec:10}]`, 20px/초, 임계 8px, 30fps:
  - move, 제안 시작 24.2(5px 오른쪽), 길이 9.93 → `proposedSec === 24`, `snap.id === "clip:a:end"`.
  - move, 시작은 멀고 **끝**이 24.1 근처(제안 시작 14.17, 길이 9.93 → 끝 24.1) → 시작이 `24 - 9.93`으로 당겨진다.
  - end 모드 제안 23.8 → 24.
  - 자기 자신 후보(`excludeIdPrefix:"clip:self:"`)에는 안 붙는다: start 모드 제안 10.1 → 그대로 10.1, `snap === null`.
  - 임계 밖(25.0) → 그대로.
  Run → FAIL(모듈 없음).

- [ ] **Step 2: 구현 → GREEN** — `findTimelineSnap`을 후보에서 `excludeIdPrefix`를 거른 목록으로 부른다. move는 시작·끝 각각 부르고 `Math.abs(snap.timeSec - 제안)`이 작은 쪽.

- [ ] **Step 3: 배선(RED→GREEN)** — `timeline-dock.test.tsx`에: 배치 클립 둘(`b-1` 5~9초, `b-2` 12~14초, 각 `placementId`)과 20px/초에서 `b-2`의 이동 단추를 `pointerDown(clientX:300)` → `pointerMove(clientX:240)`(−3초 → 시작 9초 근처, 끝이 `b-1` 끝 9초에서 0.0x초) → `pointerUp` → `onUpdatePlacements`의 `startSec`이 **정확히 9**. 또 끄는 동안 `.vb-timeline-snap-guide`가 9초 x에 있다. RED 확인 뒤:
  - `placementBoundsAtPointer`와 `trimSecondsAtPointer`가 계산한 제안값을 `snapDragProposal`(후보는 이미 있는 `snapCandidates`, 임계 `SNAP_THRESHOLD_PX`, 배율 `state.pixelsPerSecond`·`state.viewportStartSec`, 자기 클립 접두사는 `view.tracks`에서 그 placement의 `clipId`를 찾아 `clip:${clipId}:`)에 통과시킨 뒤 `derivePlacement*`/`deriveNarrationTrim`에 넘긴다.
  - draft에 `snap: TimelineSnap | null`을 더하고, 있으면 `[data-timeline-track]` 안에 `<div aria-hidden="true" className="vb-timeline-snap-guide" style={{ left: `${timeToPixels(snap.timeSec, …)}px` }} />`.
  - CSS: `.vb-timeline-snap-guide { position: absolute; top: 0; bottom: 0; width: 1px; background: var(--vb-accent); pointer-events: none; z-index: 2; }`
  - 키보드 한 프레임 조작에는 붙기를 **걸지 않는다**(한 프레임씩 가는 것이 목적).

- [ ] **Step 4: 넓은 검증 + 진짜 백엔드** — vitest `src/features/editor/timeline` 통과, tsc 0. `apps/web/e2e-real/snap-drag.spec.mjs`: 깨끗한 고정 프로젝트(장면 3 B-roll을 끝 손잡이로 장면 4 시작 근처 5px 밖까지 끌기) → 서버 값이 장면 4 시작 `2.9281`의 프레임 반올림 값과 같다 → 되돌리기. Run → `1 passed`.

- [ ] **Step 5: 검증 넷 + 커밋** — 배선: `grep -n "snapDragProposal" apps/web/src/features/editor/timeline/TimelineDock.tsx` ≥2(옮기기·자르기). 갭: 내레이션 순서 바꾸기(reorder)에는 안 걸었다(장면 단위 칸 이동이라 붙기 개념이 없다) — 적는다.
```bash
git add apps/web/src/features/editor/timeline/dragSnap.ts apps/web/src/features/editor/timeline/dragSnap.test.ts apps/web/src/features/editor/timeline/TimelineDock.tsx apps/web/src/features/editor/timeline/timeline-dock.test.tsx apps/web/src/styles/editor-workbench.css apps/web/e2e-real/snap-drag.spec.mjs
git commit -m "feat(timeline): 끌어 옮기기·자르기 중에 옆 클립 시작·끝과 재생줄에 붙는다

붙기 계산은 있었지만 재생줄 옆 글자에만 쓰였다. 옮길 때는 시작과 끝을 둘 다
대어 보고, 붙은 자리에 세로 안내선을 그린다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 10: 눈금 간격 — 120초 전체 보기에서 121개 대신 9개(스파이크 H-e) + 출처 기록 — 약 2시간

**Files:**
- Create: `apps/web/src/features/editor/timeline/rulerScale.ts`, `…/rulerScale.test.ts`
- Modify: `TimelineDock.tsx` — 앵커 `  const rulerMarks = useMemo(() => {`(그 useMemo 전체), `        {rulerMarks.map((seconds) => <span key={seconds} aria-label={`눈금 ${seconds}초`} role="listitem" style={{ minWidth: `${state.pixelsPerSecond}px` }}>{seconds}s</span>)}`
- Modify: `docs/oss/editor-ui-source-map.json`(`"task": "Task 14 timeline geometry"` 항목), `tests/test_editor_ui_source_provenance.py`(`def test_task14_timeline_math_is_reference_only`의 기대 dict), `docs/oss-adoption-map.ko.md`(`Augani/openreel-video` 줄 둘, `OpenCut-app/opencut-classic` 줄, 새 줄 셋)

**Interfaces:**
- Produces: `rulerIntervals(pixelsPerSecond: number, fps: Readonly<{num:number;den:number}>, minLabelGapPx: number): Readonly<{ majorSec: number; minorSec: number }>`, `rulerMarks(input: { startSec: number; endSec: number; majorSec: number }): readonly number[]`, `formatRulerLabel(seconds: number, majorSec: number): string`(1초 미만 간격이면 `0.5s`, 60초 이상이면 `1:30`, 그 밖은 `15s`).
- 후보 간격(opencut-classic `ruler-utils.ts`를 **보고 독립 구현** — 코드 복사 금지): 프레임 단위 `2·3·5·10·15프레임`, 초 단위 `1·2·3·5·10·15·30·60·120·300·600초`. 큰 눈금은 **글자 사이가 `minLabelGapPx` 이상인 가장 작은 간격**, 잔눈금은 그 간격의 약수 중 `minLabelGapPx/5` 이상인 가장 작은 것(15초 → 3초).
- 글자 최소 간격은 `readCssPixels(surface, "--vb-ruler-label-min-gap", 120)`(Task 7 변수).
- **금지 낱말(출처 시험이 검사):** 새 파일에는 주석에도 `document`·`window`·`canvas`·`EditorCore`·`EditorCommandPort`·`renderer`·`database`·`IndexedDB`·`OPFS`·`browser-export`·`next/`가 들어가면 안 된다.

- [ ] **Step 1: 시험(RED)** — `rulerScale.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { formatRulerLabel, rulerIntervals, rulerMarks } from "./rulerScale";
const fps30 = { num: 30, den: 1 };
describe("눈금 간격 (2026-10-08 점검 그림 10, 스파이크 §3(라))", () => {
  it("742e1924 전체 보기 11.2px/초는 15초마다(168px), 잔눈금 3초", () => {
    expect(rulerIntervals(11.2, fps30, 120)).toEqual({ majorSec: 15, minorSec: 3 });
    expect(rulerMarks({ startSec: 0, endSec: 120, majorSec: 15 })).toHaveLength(9);
  });
  it("50px/초는 3초마다", () => expect(rulerIntervals(50, fps30, 120).majorSec).toBe(3));
  it("0907 전체 보기 173px/초는 1초마다(그대로 8개)", () => {
    expect(rulerIntervals(173, fps30, 120).majorSec).toBe(1);
    expect(rulerMarks({ startSec: 0, endSec: 7.75, majorSec: 1 })).toHaveLength(8);
  });
  it("아주 크게 늘리면 프레임 단위로 내려간다(2프레임 = 133px)", () => expect(rulerIntervals(2000, fps30, 120).majorSec).toBeCloseTo(2 / 30, 9));
  it("글자는 간격에 맞춰 읽기 좋게", () => {
    expect(formatRulerLabel(15, 15)).toBe("15s");
    expect(formatRulerLabel(90, 30)).toBe("1:30");
    expect(formatRulerLabel(0.1, 0.1)).toBe("0.1s");
  });
});
```
(손계산: 11.2px/초에서 10초=112px<120, 15초=168px → 15, 잔눈금은 15의 약수 중 24px 이상인 3초. 2000px/초에서 2프레임=133px.)
Run: `cd apps/web && npx vitest run src/features/editor/timeline/rulerScale.test.ts` → FAIL(모듈 없음).

- [ ] **Step 2: 구현 → GREEN** — 파일 머리 주석: `opencut-classic(cf5e79e9) apps/web/src/timeline/ruler-utils.ts의 "확대 정도에 따라 간격을 고른다"는 생각만 보고 다시 썼다. 코드는 옮기지 않았다(2026-10-08 채택 스파이크).`

- [ ] **Step 3: 화면 배선(RED→GREEN)** — `timeline-dock.test.tsx`에: `durationSec:120`인 view, `viewportWidthPx={1343}`(전체 보기 ≈11.2px/초) → `screen.getAllByRole("listitem", { name: /^눈금/ })` 길이 9, 이름 `눈금 15초`가 있다. 기존 시험 `expect(screen.getByLabelText("눈금 0초"))`는 그대로 통과해야 한다. 구현: `rulerMarks` useMemo를 새 함수로, 각 눈금을 `position:absolute; left: timeToPixels(sec, …)`로(지금의 flex·`minWidth`는 위치가 어긋난다), 잔눈금은 글자 없는 `<span aria-hidden="true" className="vb-ruler-minor" />`.

- [ ] **Step 4: 출처 기록(RED→GREEN)** — 먼저 `tests/test_editor_ui_source_provenance.py`의 기대 dict를 고친다: `local_paths` 끝에 `"apps/web/src/features/editor/timeline/rulerScale.ts",`, `inspected_upstream_paths` 끝에 `{"path": "apps/web/src/timeline/ruler-utils.ts", "sha256": "8acde0c6a49be27d9517fcabfc9239bcaeb8ae24586aeb05e08338b8b140ce57"},`. Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_editor_ui_source_provenance.py::test_task14_timeline_math_is_reference_only` → FAIL(JSON이 아직 옛것). 그 다음 `docs/oss/editor-ui-source-map.json` 같은 항목에 같은 두 줄 → PASS. 같은 파일 전체 Run → 통과. `powershell -ExecutionPolicy Bypass -File .\scripts\verify-editor-ui-source-provenance.ps1` → 성공.
  `docs/oss-adoption-map.ko.md`: `Augani/openreel-video` 두 줄의 `partial port` → `reference only`(이유: "클립이 프로젝트 저장소에 직접 쓰고 브라우저가 렌더를 가진다. 배운 것은 양 끝 띠 손잡이·클립 끝 붙기 동작뿐 — 2026-10-08 스파이크"), `opencut-classic` 줄 끝에 "2026-10-08: 눈금 간격 계산도 보고 다시 씀(`rulerScale.ts`)", 표 끝에 `xzdarcy/react-timeline-editor`(MIT, 797★, 2026-01-25, exclude — 시험 0·aria 0·키보드 없음), `walterlow/freecut`(MIT, 2,239★, 2026-09-29, reference only), `AIEraDev/Clypra`(MIT, 3,311★, 2026-10-07, reference only — 리플 규칙 참고) 세 줄. `THIRD_PARTY_NOTICES.md`는 **바꾸지 않는다**(reference only, OpenCut classic MIT 줄이 이미 있다).

- [ ] **Step 5: 검증 넷 + 커밋** — 동작: Task 18에서 742e1924 120초 전체 보기 눈금 수를 JS로 잰다(기대 9). 배선: `grep -n "rulerIntervals" apps/web/src/features/editor/timeline/TimelineDock.tsx` ≥1.
```bash
git add apps/web/src/features/editor/timeline/rulerScale.ts apps/web/src/features/editor/timeline/rulerScale.test.ts apps/web/src/features/editor/timeline/TimelineDock.tsx apps/web/src/features/editor/timeline/timeline-dock.test.tsx docs/oss/editor-ui-source-map.json tests/test_editor_ui_source_provenance.py docs/oss-adoption-map.ko.md
git commit -m "feat(timeline): 확대 정도에 따라 눈금 간격을 고른다 -- 120초 전체 보기 121개 대신 9개

1초마다 고정이라 11px 간격에 글자가 붙어 읽을 수 없었다. opencut-classic의
방식을 보고 다시 썼다(reference only, 출처 기록 갱신).

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 11: 미리보기 기다리기 — 가벼운 상태만 묻고, 겹치지 않고, 끝나면 멈추고, 앞 화면을 남긴다(+G Task 13 흡수) — 약 3시간

**Files:**
- Modify: `apps/web/src/lib/pollJob.ts` — 앵커 `    isStillRelevant?: () => boolean;`(그 아래 선택 인자 하나), `    if (!delayFirst) await delay(intervalMs);`
- Create: `apps/web/src/features/editor/preview/exactPreviewWatch.ts`, `…/exactPreviewWatch.test.ts`
- Create: `apps/web/src/features/editor/preview/previewStill.ts`
- Modify: `apps/web/src/features/editor/preview/preview-stage.tsx` — 앵커 `onSeeked={(event) => updateTimeline(event.currentTarget)} />)}`(video 줄), `<div className="vb-preview-stage__empty"><strong>{exact.label}</strong>`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx` — 앵커: 옛 기다리기 effect 전체(`    const status = state.view?.playback.exactPreview.status;`부터 `  }, [autoPreviewWaiting, refreshToken, requestKey, state.view?.playback.exactPreview.status, state.view?.playback.exactPreview.generationId]);`까지), `api.startExactPreview(` 네 곳
- Modify: `apps/web/src/api.ts` — 앵커 `  getEditingSession: (projectId: string, sessionId: string) =>`, `    const response = await fetch(`/api/projects/${projectId}/editing-sessions/latest`, undefined);`, `  startExactPreview: (projectId: string, sessionId: string, payload:`
- Modify: `services/api/src/videobox_api/routers/editing_session.py` — 앵커 `    def get_latest_editing_session(project_id: str) -> EditingSessionResponse:`, `    def get_editing_session(project_id: str, session_id: str) -> EditingSessionResponse:`
- Create: `tests/test_editing_session_history_is_optional.py`
- 그리고 **G Task 13**(첫 로드 전환 추천 두 번) Step 1~6을 이 Task 끝에서 그 문서 그대로 실행한다.

**Interfaces:**
- Produces(서버): `GET …/editing-sessions/latest?include_history=false`, `GET …/editing-sessions/{sid}?include_history=false` → `history: []`(기본은 지금처럼 전부 — 유진·MCP 등 다른 소비자 보호).
- Produces(api.ts): `getExactPreviewStatus(projectId: string, generationId: string): Promise<ExactPreviewResponse>`(`GET /api/projects/{p}/exact-previews/{g}`). `getEditingSession`·`getLatestEditingSession`은 `?include_history=false`를 붙인다(화면은 `history`를 안 읽는다 — `grep -rn "\.history\b" apps/web/src` 로 확인됨).
- Produces(pollJob): `options.backoff?: Readonly<{ factor: number; maxMs: number }>` — 시도마다 `intervalMs × factor^n`, 최대 `maxMs`. 없으면 지금 그대로.
- Produces: `exactPreviewPollStatus(response: ExactPreviewResponse): JobStatusPayload<ExactPreviewResponse>` — `pending/running → processing`, `succeeded → succeeded(result=response)`, `failed/stale/unavailable → failed(error_detail=status)`.
- Produces: `capturePreviewStill(video: HTMLVideoElement): string | null`(캔버스에 지금 장면을 그려 `image/jpeg` 0.7 데이터 주소, 그리기 불가면 `null`).
- 화면 규칙: 기다리는 동안 **`GET exact-previews/{g}`만** 1초→1.5배→최대 5초 간격으로, **응답을 받은 뒤에만** 다음을 묻는다(겹침 0). 끝나면(성공·실패·낡음·못 읽음) **세션+매니페스트를 한 번만** 다시 읽고 멈춘다. 최대 240회(약 18분).
- 앞 화면: 재생기가 `pause`·`seeked`·`loadeddata` 때 지금 장면을 그림으로 잡아 두고, 편집 뒤 재생기가 사라진 동안 그 그림 + `새 미리보기를 만드는 중이에요 · 바뀌기 전 화면`을 보여 준다. 새 미리보기가 오면 그림은 버린다.

- [ ] **Step 1: 서버(RED→GREEN)** — `tests/test_editing_session_history_is_optional.py`: `create_app(projects_root=tmp_path/"projects")` + `_seed_session`(`tests/test_scene_transition_suggestions_api.py` 방식)에 `history: [{"mutation_type":"x","segment_id":"s1","inverse_payload":{"segments":[]}}]` → `GET …/{sid}`는 `len(history)==1`, `…?include_history=false`는 `history == []`, `latest?include_history=false`도 `[]`. RED 확인 뒤 두 라우트에 `include_history: bool = True` 쿼리 인자, `False`면 `EditingSessionResponse(**{**result, "history": []})`. GREEN.

- [ ] **Step 2: pollJob backoff(RED→GREEN)** — `apps/web/src/lib/pollJob.test.ts`(없으면 만든다): 가짜 시계(`vi.useFakeTimers()`)로 `fetchStatus`가 `processing` 다섯 번 후 `succeeded` — `backoff:{factor:1.5,maxMs:5000}`, `intervalMs:1000`에서 각 호출 사이 경과가 `[1000,1500,2250,3375,5000]`. 그리고 `fetchStatus`가 3초 걸려도 동시 진행 최대 1(카운터로 잰다). RED → `if (!delayFirst) await delay(intervalMs);`를 `if (!delayFirst) await delay(nextDelay(attempt));`로, `delayFirst` 쪽도 같은 함수 — `const nextDelay = (attempt: number) => backoff ? Math.min(backoff.maxMs, intervalMs * backoff.factor ** attempt) : intervalMs;`. GREEN.

- [ ] **Step 3: 변환·그림 잡기(RED→GREEN)** — `exactPreviewWatch.test.ts`: 상태 일곱 가지 → 위 표대로. `previewStill`은 jsdom에 캔버스가 없어 `null`을 돌려주는지 + `HTMLCanvasElement.prototype.getContext`·`toDataURL`을 흉내 내면 `data:image/jpeg`로 시작하는지.

- [ ] **Step 4: 화면 배선(RED)** — `editor-workbench-route.test.tsx`의 `it("accepts a local-first exchange as a memory source", async () => {` **앞**에(G Task 13 시험과 같은 자리, 그 Task가 같은 앞자리를 쓰므로 G 시험을 먼저 넣었다면 그 **앞**):
```tsx
  it("미리보기를 기다리는 동안 무거운 세션은 다시 안 읽고, 끝나면 한 번만 읽는다 (2026-10-08 §3-2)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const session = vi.spyOn(api, "getEditingSession");
    vi.spyOn(api, "startExactPreview").mockResolvedValue({ status: "running", generation_id: "g-2", timeline_start_sec: 0, timeline_end_sec: 1, artifact_revision: 1, fingerprint: "f" });
    const status = vi.spyOn(api, "getExactPreviewStatus")
      .mockResolvedValueOnce({ status: "running", generation_id: "g-2", timeline_start_sec: 0, timeline_end_sec: 1, artifact_revision: 1, fingerprint: "f" })
      .mockResolvedValueOnce({ status: "running", generation_id: "g-2", timeline_start_sec: 0, timeline_end_sec: 1, artifact_revision: 1, fingerprint: "f" })
      .mockResolvedValue({ status: "succeeded", generation_id: "g-2", timeline_start_sec: 0, timeline_end_sec: 1, artifact_revision: 1, fingerprint: "f", content_url: "/x.mp4" });

    render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
    await expectEditorRevision(1);
    const afterOpen = session.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });

    expect(status).toHaveBeenCalledTimes(3);
    expect(status).toHaveBeenCalledWith("project-a", "g-2");
    expect(session.mock.calls.length - afterOpen).toBe(1);
    vi.useRealTimers();
  });
```
(이 파일의 기본 가짜 API 준비(`beforeEach`)가 매니페스트를 `unavailable`로 주면 자동 미리보기가 `startExactPreview`를 부른다 — 그 경로를 그대로 쓴다. 기본 준비가 다르면 그 시험 파일의 다른 미리보기 시험이 쓰는 준비를 따른다.)
Run: `cd apps/web && npx vitest run src/features/editor/workbench/editor-workbench-route.test.tsx -t "무거운 세션"` → FAIL(`getExactPreviewStatus is not a function` 또는 세션 호출이 여러 번).

- [ ] **Step 5: 화면 배선 → GREEN**
  - 라우트에 `const [watchedPreview, setWatchedPreview] = useState<{ key: string; generationId: string } | null>(null);`와 helper `const requestExactPreview = (payload: Parameters<typeof api.startExactPreview>[2]) => api.startExactPreview(projectId, sessionId!, payload).then((started) => { setWatchedPreview({ key: requestKey, generationId: started.generation_id }); return started; });`. `api.startExactPreview(` 네 곳을 이것으로(auto·`refreshPreview`·`previewSelectedRange`·편집 뒤). 편집 뒤 경로의 `.then(() => { if (isCurrentRefresh()) setRefreshToken(...) })`는 지운다(이제 기다리기가 끝에 한 번 올린다).
  - 옛 기다리기 effect(앵커 범위)를 지우고 새 effect: 감시할 생성분 = `watchedPreview?.key === requestKey ? watchedPreview.generationId : (view 상태가 pending/running이면 view.playback.exactPreview.generationId)`. 있으면 `pollJobUntilTerminal(() => api.getExactPreviewStatus(projectId, id).then(exactPreviewPollStatus), { intervalMs: 1000, backoff: { factor: 1.5, maxMs: 5000 }, maxAttempts: 240, delayFirst: true, isStillRelevant: () => active })` → 무엇으로 끝나든(예외 포함 `.catch`) `active`면 `setWatchedPreview(null); setRefreshToken((c) => c + 1);` 한 번. 정리 함수에서 `active = false`.
  - `autoPreviewWaiting` 상태는 이제 쓰는 곳이 없으면 지운다(`grep`으로 확인).
  - `preview-stage.tsx`: `stillRef = useRef<string | null>(null)`, video에 `onPause`·`onLoadedData` 추가 + 기존 `onSeeked` 안에서 `stillRef.current = capturePreviewStill(event.currentTarget) ?? stillRef.current`. 빈 상태(`vb-preview-stage__empty`)를 그릴 때 `exact.kind`가 `pending|running`이고 `stillRef.current`가 있으면 그 앞에 `<img className="vb-preview-stage__still" src={stillRef.current} alt="" />`와 `<p role="status">새 미리보기를 만드는 중이에요 · 바뀌기 전 화면</p>`. `exact.kind === "current"`가 되면 `stillRef.current = null`.
  Run Step 4 명령 → 통과.

- [ ] **Step 6: G Task 13 실행** — G 계획 `### Task 13:` Step 1~6을 문자 그대로(시험·`loadedSessionRevision`·커밋). 앵커(`}, [projectId, requestKey, sessionId, state.session?.expectedRevision]);`)가 이 Task 뒤에도 한 번뿐인지 먼저 `grep -c`.

- [ ] **Step 7: 넓은 검증 + 진짜 백엔드** — vitest `src/features/editor src/lib` 통과(알려진 1건 외), tsc 0, pytest Step 1 파일 + `tests/test_api_exact_preview.py` 통과. `apps/web/e2e-real/preview-wait.spec.mjs`: 깨끗한 고정 프로젝트에서 장면 2를 고르고 `Control+B`(분할) → 그때부터 `page.on("request")`로 `editing-sessions/`(`playback-manifest` 제외)·`playback-manifest`·`exact-previews/` 요청을 센다 → 편집본 미리보기 `<video>`가 다시 보일 때까지(최대 120초) 기다린 뒤: 세션 요청 ≤2, 매니페스트 ≤2, 상태 요청 ≥1, **같은 경로 요청이 동시에 둘 이상 진행된 순간 0**(요청 시작·끝 시각으로 계산). 기다리는 동안 `.vb-preview-stage__still` 또는 `만드는 중` 문구가 보였다. 분할은 `Control+Z`로 되돌린다. Run → `1 passed`.

- [ ] **Step 8: 검증 넷 + 커밋**

갭: 실시간 재생은 범위 밖. 동작: e2e 요청 수·겹침 0, Task 18에서 컨테이너 CPU(편집 직후 1분 `docker stats --no-stream` 3회)를 잰다. 배선: `grep -n "getExactPreviewStatus" apps/web/src --include=*.tsx -r` ≥1, `grep -n "include_history=false" apps/web/src/api.ts` 2줄.
```bash
git add apps/web/src/lib/pollJob.ts apps/web/src/lib/pollJob.test.ts apps/web/src/features/editor/preview apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx apps/web/src/api.ts services/api/src/videobox_api/routers/editing_session.py tests/test_editing_session_history_is_optional.py apps/web/e2e-real/preview-wait.spec.mjs
git commit -m "fix(editor): 미리보기를 기다릴 때 가벼운 상태만 묻고, 겹치지 않고, 끝나면 멈춘다

1.2초마다 830KB 세션·매니페스트·변형본을 겹쳐 불러 응답이 14~23초로 늘고
뒤 요청이 앞 응답을 무효로 만들어 화면이 '만드는 중'에 멈췄다. 상태 길만
점점 길게 묻고, 끝나면 한 번 읽는다. 기다리는 동안 앞 화면을 그림으로 남긴다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
(G Task 13은 자기 커밋을 따로 남긴다.)

---

### Task 12: 빼기 정책 둘 — 구멍을 보여 주기(지금 기본) / 당기기(owner 결정 뒤) + `빈 구간` 수 바로잡기(스파이크 H-g) — 약 4시간

**결정 상태:** `docs/decisions/`에 빼기 정책이 **없다**(grep `리플|당겨|자석`: 속도 결정 하나만). 그래서 이 Task는 **두 길을 다 만들고**, 출하 기본값은 지금 동작 그대로 `leave_gap`(구멍을 남기되 화면이 그 사실을 보여 준다)으로 둔다. `ripple`(캡컷 주 트랙 자석과 같은 당기기)은 **추천안**이고, owner가 고르면 상수 한 줄 + 시험 기대 한 줄을 바꾼다(owner 결정 2).

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/editing_session.py` — 앵커 `MIN_SEGMENT_DURATION_SEC = 0.2`(아래에 상수), `def _validate_segment_bounds(*, segments: list[dict[str, Any]]) -> None:`, `def update_segment_cut_action(`(함수 전체)
- Modify: `packages/core-engine/src/videobox_core_engine/editor_playback_manifest.py` — 앵커 `        "gap_slots": [_gap_contract(gap) for gap in materialized.get("gap_slots", []) if isinstance(gap, dict)],`
- Modify: `apps/web/src/features/editor/timeline/TimelineDock.tsx` — 앵커 `  "장면을 보여 줄 영상이 없어요.": "영상 없음",`
- Create: `tests/test_remove_scene_policy.py`
- Test: `apps/web/src/features/editor/timeline/timeline-dock.test.tsx`

**Interfaces:**
- Produces: `RemoveMode = Literal["leave_gap", "ripple"]`, `DEFAULT_REMOVE_MODE: RemoveMode = "leave_gap"`, `update_segment_cut_action(*, session, segment_id, cut_action, remove_mode: RemoveMode | None = None)` — `None`이면 `DEFAULT_REMOVE_MODE`. **유진(`SetCutActionOperation`)과 화면(`PATCH …/cut-action`)이 모두 이 함수를 지나므로 정책은 서버 한 곳에서 정해진다** — 유진 코드는 안 바꾼다.
- ripple 규칙: 뺀 장면 길이 `D` 만큼 **목록에서 그 뒤에 있는** 장면 전부 `start/end −D`, `timeline_placement_overrides` 중 `start_sec >= 뺀 장면 end`인 것도 `−D`(겹친 것은 그대로 — 보고에 적는다), 뺀 장면에 `ripple_removed_sec = D`를 적는다. 되돌리기 1칸(한 번의 `_apply_manual_mutation`). 되살리기(`keep`)에서 `ripple_removed_sec`가 있으면 반대로 — 목록에서 그 뒤 장면 전부와 `start_sec >= 그 장면 start`인 override를 `+D` — 하고 그 칸을 지운다.
- `_validate_segment_bounds`는 `cut_action == "remove"`인 장면을 겹침 검사에서 뺀다(당기면 뒤 장면이 그 자리에 들어온다).
- 매니페스트: 뺀 장면 자리 중 **남은 장면이 덮지 않은 구간**을 `gap_slots`에 `{gap_id: "removed:<id>", segment_id, start_sec, end_sec, reason: "removed_scene"}`로 더한다(출력 끝 뒤는 자른다). 화면 이름 `뺀 장면 자리`. ripple이면 덮여서 0개, leave_gap이면 1개.

- [ ] **Step 1: 서버 시험(RED)** — `tests/test_remove_scene_policy.py`:
```python
"""빼기 정책 (2026-10-08 계획 H Task 12, 점검 §3-5). 기본은 구멍을 남기고 보여 준다."""
from __future__ import annotations

import pytest

from videobox_core_engine import editing_session as es
from videobox_core_engine.editing_session import DEFAULT_REMOVE_MODE, update_segment_cut_action


def _session() -> dict:
    segments = [("s1", 0.0, 2.0), ("s2", 2.0, 3.7), ("s3", 3.7, 5.0)]
    return {"session_id": "e1", "project_id": "p", "timeline_id": "t", "session_revision": 1, "history": [],
            "segments": [{"segment_id": i, "caption_text": i, "start_sec": a, "end_sec": b, "cut_action": "keep"} for i, a, b in segments],
            "timeline_placement_overrides": {"broll:x": {"placement_id": "broll:x", "kind": "broll", "start_sec": 4.0, "end_sec": 4.5}}}


def _bounds(session: dict) -> list[tuple[str, float, float, str]]:
    return [(s["segment_id"], round(s["start_sec"], 6), round(s["end_sec"], 6), s["cut_action"]) for s in session["segments"]]


def test_the_shipped_default_is_leave_gap_until_the_owner_decides() -> None:
    assert DEFAULT_REMOVE_MODE == "leave_gap"


def test_leave_gap_keeps_later_scenes_in_place() -> None:
    updated = update_segment_cut_action(session=_session(), segment_id="s2", cut_action="remove", remove_mode="leave_gap")
    assert _bounds(updated) == [("s1", 0.0, 2.0, "keep"), ("s2", 2.0, 3.7, "remove"), ("s3", 3.7, 5.0, "keep")]


def test_ripple_pulls_later_scenes_and_placements_in_one_undo_step() -> None:
    updated = update_segment_cut_action(session=_session(), segment_id="s2", cut_action="remove", remove_mode="ripple")
    assert _bounds(updated) == [("s1", 0.0, 2.0, "keep"), ("s2", 2.0, 3.7, "remove"), ("s3", 2.0, 3.3, "keep")]
    assert updated["timeline_placement_overrides"]["broll:x"]["start_sec"] == pytest.approx(2.3)
    assert len(updated["history"]) == 1


def test_restoring_a_ripple_removed_scene_pushes_later_scenes_back() -> None:
    removed = update_segment_cut_action(session=_session(), segment_id="s2", cut_action="remove", remove_mode="ripple")
    restored = update_segment_cut_action(session=removed, segment_id="s2", cut_action="keep")
    assert _bounds(restored) == _bounds(_session())
    assert restored["timeline_placement_overrides"]["broll:x"]["start_sec"] == pytest.approx(4.0)
    assert "ripple_removed_sec" not in restored["segments"][1]
```
그리고 매니페스트 시험 둘(같은 파일, `build_editor_playback_manifest`에 위 세션의 leave_gap/ripple 결과와 장면마다 내레이션 클립이 있는 최소 편집판을 넣는다 — `tests/` 안 기존 매니페스트 시험이 편집판을 만드는 방식을 `grep -ln "build_editor_playback_manifest" tests`로 찾아 따른다): leave_gap → `gap_slots`에 `{"gap_id":"removed:s2","start_sec":2.0,"end_sec":3.7,"reason":"removed_scene"}` 하나, ripple → `removed:` 0개.
Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_remove_scene_policy.py` → FAIL(`cannot import name 'DEFAULT_REMOVE_MODE'`).

- [ ] **Step 2: 구현 → GREEN** — 위 Interfaces대로. `_apply_manual_mutation`의 `extra`에 `"remove_mode": mode`. 매니페스트 함수 `_removed_scene_gaps(session: dict, output_end_sec: float) -> list[dict]`(남은 장면 구간을 빼는 계산은 `composition_plan._uncovered_intervals`를 import해 쓴다).

- [ ] **Step 3: 영향받는 기존 시험** — Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider $(grep -rl "cut_action" tests --include=*.py | tr '\n' ' ')`(Git Bash). 기본값이 그대로 `leave_gap`이라 **바뀌는 시험이 없어야 한다**. 깨지면 `_validate_segment_bounds`의 뺀 장면 제외가 원인인지(그 시험이 "뺀 장면과 겹치면 거절"을 기대했는지) 읽고, 기대가 맞으면 멈추고 보고.

- [ ] **Step 4: 화면 이름(RED→GREEN)** — `timeline-dock.test.tsx`: `expect(gapReasonLabel("removed_scene")).toBe("뺀 장면 자리")`, 그리고 `gaps: [{ gapId: "removed:s2", segmentId: "s2", startSec: 2, endSec: 3.7, reason: "removed_scene" }]`인 view에서 머리 문장에 `빈 구간 1개`. 구현: `gapReasonLabels`에 `removed_scene: "뺀 장면 자리",`.

- [ ] **Step 5: 진짜 백엔드** — `apps/web/e2e-real/remove-scene.spec.mjs`: 깨끗한 고정 프로젝트에서 장면 2를 고르고 `Delete` → 서버 세션 장면 2 `cut_action:"remove"`, 장면 3 시작 그대로(leave_gap), 매니페스트 `gap_slots`에 `removed:scene-2` 하나, 화면 머리 `빈 구간 1개`, 발 `빈 구간: 뺀 장면 자리` → `Control+Z` → 원래. Run → `1 passed`.

- [ ] **Step 6: 검증 넷 + 커밋** — 갭: ripple은 만들었지만 **꺼져 있다**(owner 결정 2). 겹친 배치 override는 당기지 않는다 — 보고. 유진 경로가 같은 기본값을 탄다는 것을 `grep -n "update_segment_cut_action(" packages/core-engine/src/videobox_core_engine/editing_session.py`로 보이고 적는다. 배선: `grep -rn "removed_scene" apps/web/src packages` ≥2.
```bash
git add packages/core-engine/src/videobox_core_engine/editing_session.py packages/core-engine/src/videobox_core_engine/editor_playback_manifest.py apps/web/src/features/editor/timeline/TimelineDock.tsx apps/web/src/features/editor/timeline/timeline-dock.test.tsx tests/test_remove_scene_policy.py apps/web/e2e-real/remove-scene.spec.mjs
git commit -m "feat(editor): 장면 빼기 정책 둘 -- 구멍은 '뺀 장면 자리'로 보여 주고, 당기기는 준비만

빼면 1.7초 구멍이 남는데 화면은 빈 구간 0개라고 했다. 뺀 자리를 빈 구간으로
센다. 캡컷처럼 당기는 길(되돌리기 1칸, 되살리면 다시 밀림)도 서버 한 곳에
만들었지만 기본은 owner 결정 전까지 꺼 둔다. 유진도 같은 함수를 탄다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 13: 1280×720에서 작업판이 한 화면에(+G Task 6 흡수) — 약 2시간

**Files:**
- G Task 6의 Files 전부(`editorUiState.ts`, `EditorWorkbench.tsx`, `editor-workbench.css`, `toolbar-collapse.test.tsx`)
- Modify: `apps/web/src/styles/editor-workbench.css` — 앵커 `  .vb-editor-workbench__timeline { height: var(--vb-timeline-height, auto); max-height: var(--vb-timeline-height, clamp(4rem, calc(66vh - 390px), 26rem)); }`
- Test: `apps/web/e2e/exact-preview.spec.mjs`(가짜 API — 배치만 재면 된다), 끝에 시험 하나

**Interfaces:** Consumes: G Task 6이 만드는 `readToolbarCollapsed`·`writeToolbarCollapsed`·`도구줄 접기/펼치기`.

- [ ] **Step 1: G Task 6 실행** — G 계획 `### Task 6:` Step 1~6을 문자 그대로(시험·구현·커밋). 앵커(`<header className="vb-editor-workbench__toolbar"><strong>편집 작업판</strong><div>` 등)가 Task 3 뒤에도 그대로인지 먼저 `grep -c`(각 1).

- [ ] **Step 2: 지금을 잰다(측정)** — 가짜 API e2e 서버로 1280×720: `document.documentElement.scrollHeight`, `.vb-editor-workbench__timeline`의 `getBoundingClientRect()`(top·height), 그리고 `innerHeight`보다 아래로 나간 요소 목록(`[...document.querySelectorAll("*")].filter((el) => el.getBoundingClientRect().bottom > innerHeight + 1)`의 가장 바깥 몇 개 클래스). 점검 실측은 타임라인 높이 85px·보이는 37px·문서 800px. 결과를 보고에 적고 Step 3의 원인으로 삼는다.

- [ ] **Step 3: 시험(RED)** — `exact-preview.spec.mjs` 끝에:
```js
test("1280x720에서도 타임라인이 한 화면 안에서 트랙 셋 이상을 보여 준다 (2026-10-08 §3-9)", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/projects/local-draft/editor?session_id=exact-preview-e2e");
  await expect(page.getByRole("region", { name: "타임라인" })).toBeVisible();
  const seen = await page.evaluate(() => {
    const timeline = document.querySelector(".vb-editor-workbench__timeline").getBoundingClientRect();
    return { docOverflow: document.documentElement.scrollHeight - window.innerHeight, bottom: timeline.bottom, height: timeline.height };
  });
  expect(seen.docOverflow).toBeLessThanOrEqual(1);
  expect(seen.bottom).toBeLessThanOrEqual(720);
  expect(seen.height).toBeGreaterThanOrEqual(130); // 눈금 + 32px 트랙 셋
});
```
Run: `cd apps/web && npm run test:e2e -- e2e/exact-preview.spec.mjs -g "1280x720"` → FAIL.

- [ ] **Step 4: 구현 → GREEN** — Step 2에서 찾은 원인을 고친다. 계획 시점의 가설과 첫 수: (1) 타임라인 바닥을 `clamp(4rem, …)`에서 `clamp(8.5rem, calc(66vh - 390px), 26rem)`으로(눈금+트랙 셋), (2) 작업판 첫 행(머리)과 변형 띠가 `auto`라 넘칠 때 `.vb-editor-workbench`의 `grid-template-rows: auto minmax(8rem, 1fr) auto`가 화면보다 커진다 → 미리보기 행 바닥을 `minmax(6rem, 1fr)`로 낮추고 `@media (max-height: 760px)`에서 G Task 6의 머리를 **기본 접힘**으로(저장된 사용자 선택이 있으면 그것이 이긴다 — `readToolbarCollapsed`가 `null`이면 높이로 판단하도록 그 함수의 기본값만 바꾸지 말고, 라우트에서 처음 값만 `window.innerHeight < 760`으로). 고친 뒤 **1920×1080 미리보기 면적 20.8% 시험**(`a Full HD screen shows the whole timeline …`)과 `a bigger screen never shrinks the preview …`가 그대로 통과해야 한다.
  Run: `cd apps/web && npm run test:e2e -- e2e/exact-preview.spec.mjs` → 전부 통과(끝의 `unexpected PNG` exit 1 무관). 스냅샷 PNG 변경 확인·되돌리기(Global Constraints).

- [ ] **Step 5: 검증 넷 + 커밋** — 동작: 1280×720·1440×900·1920×1080의 타임라인 높이·보이는 트랙 수·미리보기 면적을 표로. 배선: 해당 CSS 줄 grep.
```bash
git add apps/web/src/styles/editor-workbench.css apps/web/e2e/exact-preview.spec.mjs apps/web/src/features/editor/workbench/EditorWorkbench.tsx
git commit -m "fix(editor): 1280x720에서 작업판이 한 화면에 들어오고 타임라인이 트랙 셋을 보여 준다

타임라인이 85px(보이는 것 37px)이고 페이지가 아래로 밀렸다. 바닥 높이를
트랙 셋 기준으로 올리고, 낮은 화면은 머리를 접은 채 시작한다. Full HD
미리보기 면적 20.8% 조건은 그대로다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 14: 자료 카드 이름·상태, 작은 문구 결함 — 약 2시간

**Files:**
- Modify: `services/api/src/videobox_api/routers/assets.py` — 앵커 `def build_assets_router(`(인자 하나), `    def list_broll_assets(project_id: str) -> AssetListResponse:` 함수 안의 `        return AssetListResponse(assets=[_repaired_asset_response(asset) for asset in assets])`(이 return 줄은 파일에 3번 있다 — 그 함수 안의 것만)
- Modify: `services/api/src/videobox_api/main.py` — 앵커 `        build_assets_router(` 블록의 `            app.state.asset_browser_preview_service,` 다음 줄에 인자
- Modify: `apps/web/src/features/editor/assets/editorAssetProjection.ts` — 앵커 `function brollStatus(metadata: Readonly<Record<string, unknown>>): string {`(함수 전체)
- Modify: `apps/web/src/features/editor/assets/EditorAssetBrowser.tsx` — 앵커 `          <p className="vb-editor-assets__detail vb-editor-assets__status">{card.status}</p>`, `function isChipTag(tag: string): boolean {`
- Modify: `apps/web/src/features/editor/script/ScriptPane.tsx` — 앵커 `      <p>붙여넣은 글이 이 프로젝트의 대본이 돼요. 장면 나누기는 \`이야기\`에서 해요.</p>`
- Modify: `packages/storage-abstractions/src/videobox_storage/user_library_store.py` — `"name": "Clean",` → `"name": "깔끔하게",`, `"name": "Highlight",` → `"name": "강조",`
- Modify: `apps/web/src/components/ui/dialog.tsx`·`sheet.tsx`(`<span className="sr-only">Close</span>` → `닫기`, footer `>Close</Button>` → `>닫기</Button>`) + 두 파일의 `normalized_sha256`(`docs/oss/editor-ui-source-map.json`·`docs/oss/shadcn-registry-lock.json` 각 두 곳)
- Modify(시험 기대): `apps/web/src/app/ProductShell.test.tsx`, `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`, `apps/web/src/styles/product-shell.visual.test.tsx`, `apps/web/e2e/job-recovery.spec.mjs`, `apps/web/src/features/editor/inspector/caption-preset-picker.test.tsx` — `"Close"` → `"닫기"`, `Clean/Highlight` → 새 이름
- Create: `apps/web/src/features/editor/workbench/editFailureMessage.ts`, `…/editFailureMessage.test.ts`
- Modify: `EditorWorkbenchRoute.tsx` — 앵커 `          ?? "변경 내용을 저장하지 못했어요. 최신 내용을 확인한 뒤 다시 시도해 주세요.";`
- Create: `tests/test_project_broll_card_name_from_library.py`

**Interfaces:**
- Produces(서버): `build_assets_router(..., library_filename_lookup: Callable[[str], str | None] | None = None)` — broll 목록에서 `metadata.title`이 없고 `metadata.source_library_asset_id`가 있으면 그 자료실 파일 이름의 확장자 뗀 앞 60자를 **응답에만** `title`로 싣는다(저장 데이터는 안 바꾼다). `main.py`가 `lambda library_asset_id: (lambda asset: str(asset.user_metadata.get("filename") or "") or None if asset else None)(resolved_media_library_store.user_asset_store.get_asset(library_asset_id))`를 넘긴다(읽기 쉬운 지역 함수로 써도 된다).
- Produces(화면): `brollStatus`는 분석 정보(`analysis_status`)도 검토 표시(`review_required`)도 **없으면 빈 문자열**, 카드는 빈 상태 줄을 그리지 않는다. 있는 쪽만 말한다(`준비됨`, `검토 필요` …).
- Produces: `isChipTag`는 자산 종류 낱말(`music`·`sfx`·`bgm`·`broll`·`image`·`video`)을 분위기 단추로 만들지 않는다.
- Produces: `editFailureMessage(error: unknown): string | null` — `ApiRequestError`의 `detail`이 `timeline_placement_out_of_range` → `영상 길이 밖으로는 옮길 수 없어요.`, `timeline_placement_frame_span_invalid` → `한 프레임보다 짧게는 자를 수 없어요.`, 그 밖의 `timeline_placement_` → `이 자리는 지금 저장할 수 없어요. 되돌리기를 누른 뒤 다시 해 주세요.`, 아니면 `null`(그때만 옛 문장). "최신 내용을 확인한 뒤 다시 시도"는 **충돌(409)에서만** 남는다.

- [ ] **Step 1: 서버 이름(RED→GREEN)** — `tests/test_project_broll_card_name_from_library.py`: `tests/test_library_materialize_carries_title.py`의 앱·자료실 준비를 그대로 쓰되, 가져온 뒤 그 자산의 `metadata.title`을 **지운 옛 모양**을 흉내 내기 어려우면 `build_assets_router`를 직접 만들어(가짜 `orchestrator.list_broll_assets`가 `metadata={"source_library_asset_id":"lib-1"}` 하나를 돌려주고 `library_filename_lookup=lambda i: "월 수익 비교.png" if i == "lib-1" else None`) `TestClient`로 `GET …/assets/broll-video` → `assets[0].metadata.title == "월 수익 비교"`. 제목이 이미 있으면 그대로. RED → 구현 → GREEN.

- [ ] **Step 2: 화면 카드(RED→GREEN)** — `editorAssetProjection.test.ts`: 메타데이터 `{}`인 broll → `status === ""`; `{analysis_status:"succeeded"}` → `"준비됨"`; `{review_required:true}` → `"검토 필요"`; 둘 다 → `"준비됨 · 검토 필요"`. `EditorAssetBrowser.test.tsx`: `status:""` 카드에 `.vb-editor-assets__status`가 없다; 태그 `["music","잔잔한"]` 카드에 `분위기 music` 단추가 없고 `분위기 잔잔한`은 있다(단추 이름은 그 파일의 기존 시험을 보고 맞춘다).

- [ ] **Step 3: 문구 넷(RED→GREEN)** — `editFailureMessage.test.ts`(위 표 넷 + `null`), `script-pane.test.tsx`에 "백틱이 화면에 안 나온다"(`expect(screen.queryByText(/`/)).toBeNull()`), `caption-preset-picker.test.tsx` 기대 이름 교체, `tests/test_user_library_store.py`에 `built_in[0]["name"] == "깔끔하게"` 한 줄. 구현: ScriptPane 문장 → `붙여넣은 글이 이 프로젝트의 대본이 돼요. 장면 나누기는 이야기 화면에서 해요.`, 라우트의 `?? "변경 내용을 저장하지 못했어요. …"` 앞에 `?? editFailureMessage(error)`.

- [ ] **Step 4: `Close` → `닫기` + 출처 해시** — 두 파일 수정 → `.venv/Scripts/python.exe -c "import hashlib,pathlib;[print(p, hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()) for p in ('apps/web/src/components/ui/dialog.tsx','apps/web/src/components/ui/sheet.tsx')]"` → 출력 해시로 두 JSON의 `normalized_sha256`(dialog 2곳·sheet 2곳)을 바꾼다. Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_editor_ui_source_provenance.py` → 통과. 시험 기대 `"Close"` 다섯 파일 교체. Run: `cd apps/web && npx vitest run src/app/ProductShell.test.tsx src/styles/product-shell.visual.test.tsx src/ui-system.test.tsx` → 통과.

- [ ] **Step 5: 넓은 검증 + 검증 넷 + 커밋** — vitest `src/features/editor src/app src/styles src/user-copy-policy.test.ts`, tsc 0, `npm run test:e2e -- e2e/job-recovery.spec.mjs` 통과. 배선: `grep -rn "editFailureMessage" apps/web/src --include=*.tsx` ≥1, `grep -n "library_filename_lookup" services/api/src/videobox_api/main.py` 1. 동작: Task 18에서 0907 카드 다섯 장 이름 실측.
```bash
git add services/api/src/videobox_api/routers/assets.py services/api/src/videobox_api/main.py tests/test_project_broll_card_name_from_library.py apps/web/src/features/editor/assets apps/web/src/features/editor/script/ScriptPane.tsx apps/web/src/features/editor/script/script-pane.test.tsx packages/storage-abstractions/src/videobox_storage/user_library_store.py tests/test_user_library_store.py apps/web/src/components/ui/dialog.tsx apps/web/src/components/ui/sheet.tsx docs/oss/editor-ui-source-map.json docs/oss/shadcn-registry-lock.json apps/web/src/app/ProductShell.test.tsx apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx apps/web/src/styles/product-shell.visual.test.tsx apps/web/e2e/job-recovery.spec.mjs apps/web/src/features/editor/inspector/caption-preset-picker.test.tsx apps/web/src/features/editor/workbench/editFailureMessage.ts apps/web/src/features/editor/workbench/editFailureMessage.test.ts apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx
git commit -m "fix(editor): 자료 카드에 자료실 이름을, 확인하지 않는 '확인 중'은 빼고, 영어·백틱 문구를 고친다

예전에 가져온 영상은 자료실 파일 이름을 응답에만 실어 '자료 N' 대신 이름이
보인다. Close/Clean/Highlight를 한국어로, 저장 거절 이유를 창작자 말로.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 15: 열면 500이던 두 시험 프로젝트 — 옛 모양은 읽고, 없는 편집판은 한국어로 — 약 1시간

**Files:**
- Modify: `services/api/src/videobox_api/models.py` — 앵커 `    cut_action: str\n    review_required: bool\n`(`class EditingSessionSegmentResponse` 안, 파일에 한 번뿐인 연속 두 줄)
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx` — 앵커 `          : "재생 내용을 불러오지 못했어요. 새로고침 후 다시 확인해 주세요.";`
- Modify: `apps/web/src/app/AppRouter.tsx` — 앵커 `      if (!cancelled) setMessage("초안을 불러오지 못했어요. 다시 시도해 주세요.");`
- Create: `tests/test_legacy_session_segments_open.py`

**Interfaces:**
- `cut_action: str = "keep"`, `review_required: bool = False`(저장 계층의 관용 `str(segment.get("cut_action") or "keep")`과 같게 — 그 위 validator 주석 2026-09-28과 같은 이유).
- 매니페스트가 `ApiRequestError`(404, detail에 `Timeline not found`)면 편집기 문구: `이 편집본에 연결된 타임라인을 찾지 못했어요. 이 편집본은 열 수 없어요.` + `프로젝트 목록으로` 링크. 다른 오류는 옛 문구.
- 편집기 입구(`CanonicalEditorEntry`)가 5xx면: `편집본을 읽지 못했어요. 다시 해도 같으면 빈 편집판으로 시작할 수 있어요.` + 기존 `빈 편집판으로 시작` 단추를 같이 보인다(그 단추는 이미 있는 길 — `openBlankBoard`).

- [ ] **Step 1: 서버(RED→GREEN)** — `tests/test_legacy_session_segments_open.py`: `_seed_session`으로 `{"segment_id":"seg-000","caption_text":"a","start_sec":0.0,"end_sec":5.0}`(키 넷만) → `GET …/editing-sessions/latest` 200, `segments[0].cut_action == "keep"`, `review_required is False`. RED(500) → 모델 기본값 → GREEN.
- [ ] **Step 2: 화면(RED→GREEN)** — `editor-workbench-route.test.tsx`: `getEditorPlaybackManifest`가 `new ApiRequestError("'Timeline not found: timeline-longform'", 404, "/x")`로 거절 → 위 문구와 링크. `AppRouter.test.tsx`: `getLatestEditingSession`이 `Error("Request failed: … (500)")`로 거절 → 위 문구 + `빈 편집판으로 시작` 단추 보임(현재 `setMessage` 경로에서 `setHasNoDraft(true)`처럼 단추를 켜는 상태를 하나 더 둔다 — `setCanStartBlank(true)`).
- [ ] **Step 3: 실물(읽기만)** — 컨테이너는 Task 18에서 재빌드하므로 여기서는 시험만. Task 18에서 두 프로젝트를 열어 문구를 확인한다.
- [ ] **Step 4: 검증 넷 + 커밋** — 갭: 두 프로젝트의 데이터(없는 편집판)는 고치지 않는다 — 보관/삭제는 owner 결정 4.
```bash
git add services/api/src/videobox_api/models.py tests/test_legacy_session_segments_open.py apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx apps/web/src/app/AppRouter.tsx apps/web/src/app/AppRouter.test.tsx
git commit -m "fix(editor): 옛 모양 장면이 있는 편집본도 열리고, 편집판이 없으면 한국어로 말한다

cut_action·review_required가 없는 옛 장면에서 응답 검증이 500이었다. 저장
계층과 같은 기본값을 쓴다. 연결된 타임라인이 없으면 다시 시도하라는 대신
열 수 없다고 말하고 빈 편집판 길을 보여 준다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 16: 죽은 단추 고치기·지우기 + 누르면 바로 반응 — 약 3시간

**Files:**
- Create: `apps/web/src/features/editor/workbench/editorFeedback.ts`, `…/editorFeedback.test.ts`
- Modify: `apps/web/src/app/AppRoot.tsx` — 앵커 `      <AppRouter />`(바로 아래 `<Toaster position="bottom-center" />`, import `../components/ui/sonner`)
- Modify: `EditorWorkbenchRoute.tsx` — 앵커 `    setMutation({ isSaving: true, message: "변경 내용을 저장하고 있어요." });`, `        setMutation({ isSaving: false, message: resultMessage });`
- Modify: `apps/web/src/features/editor/export/ExportPopover.tsx` — 앵커 `  if (!ready) return null;`
- Modify: Task 2 목록이 가리키는 파일들(아래 규칙)
- Modify: `docs/superpowers/audit-evidence/2026-10-08-editor-ui/dead-controls.json`(다시 생성)

**Interfaces:**
- Produces: `announceEditorFeedback(feedback: Readonly<{ kind: "working" | "done" | "failed"; message: string; id?: string }>): void` — 지금 구현은 `sonner`의 `toast.loading/success/error(message, { id: id ?? "editor-feedback", duration: kind === "working" ? Infinity : 2000 })`. **계획 I가 공용 반응 모양을 정하면 이 파일 하나만 바꾼다**(파일 머리 주석에 그 사실과 I 계획 경로).
- 편집 하나 = 토스트 하나(`id` 같음): 시작 `working`("변경 내용을 저장하고 있어요."), 끝 `done`/`failed`(기존 `resultMessage`). 기존 타임라인 발 `편집 저장 상태` 문장은 **그대로 둔다**(화면 읽기 프로그램 경로).

- [ ] **Step 1: 이음매(RED→GREEN)** — `editorFeedback.test.ts`: `vi.mock("sonner")`로 `toast.loading`·`toast.success`·`toast.error`를 감시 → 세 종류가 같은 `id`로 불리고 `working`의 `duration`이 `Infinity`. 라우트 시험(`editor-workbench-route.test.tsx`): 분할 한 번에 `announceEditorFeedback`이 `working` → `done` 순서로 두 번(모듈 감시).
- [ ] **Step 2: 내보내기 첫 1초(RED→GREEN)** — `export-popover.test.tsx`: 목록이 아직 안 왔을 때 `내보낼 곳을 확인하고 있어요.`(`role="status"`)가 보인다. `if (!ready) return null;` → 그 문장을 그린다.
- [ ] **Step 3: 재고 다시 세기** — Run: `cd apps/web && npm run test:e2e:real-flow -- e2e-real/dead-control-sweep.spec.mjs` → 새 `dead-controls.json`. `silent`·`no-handler`·`always-disabled` 줄마다 아래 규칙으로 하나씩 처리하고, **처리마다 vitest 시험 하나**(그 단추를 누르면 무엇이 보이는가)를 그 컴포넌트 시험 파일에 더한다(RED를 본 뒤 고친다):
  1. 손잡이가 있고 서버 길도 있는데 화면이 침묵 → 결과를 `announceEditorFeedback`으로 알린다(예: 저장 단추류).
  2. 서버 길이 있는데 화면이 안 부름 → 이어 준다(`grep`으로 `api.ts` 메서드·라우터를 먼저 찾는다 — 기억 메모 "부품은 있는데 부르는 자리가 없다").
  3. 서버 길이 없는 기능의 단추 → **지운다**(`2026-08-30`). 그 단추를 찾는 시험이 있으면 그 시험의 의도를 읽고 같이 지운다. 지운 목록을 보고에 적는다(owner 결정 5).
  4. 항상 꺼진 단추 → 왜 꺼졌는지 `title`로 말하거나(조건이 있는 경우), 조건이 영영 안 오면 3번.
  5. 가려진 단추(`hitSelf=false`) → Task 7 뒤에도 남았으면 그 자리의 층(z-index·pointer-events)을 고친다.
  같은 땜질을 두 번 하게 되면 멈추고 보고.
- [ ] **Step 4: 기준** — 마지막 재생성한 `dead-controls.json`에서 `silent + no-handler + always-disabled == 0`(문서화한 예외만 남는다 — 예외는 JSON 각 줄의 `"exception"` 칸에 이유를 적는다). Run → 숫자를 보고에 붙인다.
- [ ] **Step 5: 넓은 검증 + 커밋** — vitest 전부(`cd apps/web && npx vitest run`) 알려진 1건 외 통과, tsc 0, `task22-parity-owners.test.ts`·`user-copy-policy.test.ts` 통과.
```bash
git add apps/web/src/features/editor apps/web/src/app/AppRoot.tsx docs/superpowers/audit-evidence/2026-10-08-editor-ui/dead-controls.json
git commit -m "fix(editor): 누르면 바로 반응하고, 죽은 단추는 이어 주거나 지운다

편집마다 '저장하고 있어요 -> 저장했어요' 알림이 바로 뜬다(sonner, 계획 I가
바꿀 이음매 한 곳). 진짜 백엔드에서 전부 눌러 본 목록으로 침묵·손잡이 없음·
항상 꺼짐을 0으로 만든다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 17: 실사용 편집 흐름 e2e 묶음 — 이 결함들이 시험을 통과해 새어 나간 길을 막는다 — 약 3시간

**Files:**
- Create: `apps/web/e2e-real/real-editing-flow.spec.mjs`
- Modify: `apps/web/e2e-real/support/realFlow.mjs`(필요한 helper만)

**Interfaces:** Consumes: Task 1 helper, Task 3·7·8·11·12 동작.

- [ ] **Step 1: 흐름 시험을 쓴다** — 한 파일, `test.describe.serial`, 깨끗한 고정 프로젝트(매 실행 새로 시드), 1440×900:
  1. **클릭 → 그 장면:** `영상 3번째` 클릭 → 오른쪽 `편집 항목`이 `1.90–2.93초 구간`.
  2. **속도 → 그 장면만:** `편집 항목`의 `속도` 칸에 `2` + `Enter` → 서버 세션: `scene-3`의 `ripple_playback_rate == 2`(또는 `end_sec`가 `1.8990646 + (2.9281-1.8990646)/2`), **다른 장면의 rate·경계 중 `scene-1`·`scene-2`는 그대로**, `scene-4`는 delta만큼 당겨짐(속도의 리플 — 2026-09-04 결정). 그리고 `announceEditorFeedback` 토스트(`[data-sonner-toast]`)가 1초 안에 보였다.
  3. **되돌리기 → 원래대로:** `Control+Z` → 서버 세그먼트 JSON이 1의 직전 스냅샷과 **같다**(`segment_id·start_sec·end_sec·cut_action·ripple_playback_rate` 비교).
  4. **트랙 머리를 마우스로:** `영상 트랙 음소거` 좌표 클릭 → 서버 `track_states.broll.muted` → `Control+Z` → 없음.
  5. **분할·빼기:** 재생 위치를 장면 2 가운데로(타임라인 클릭) → `Control+B` → 장면 5개 → 새 장면 고르고 `Delete` → `cut_action:"remove"` + 매니페스트 `removed:` 빈 구간 1 + 머리 `빈 구간 1개` → `Control+Z` 두 번 → 장면 4개, 원래 경계.
  6. **가장자리 끌기:** Task 8 e2e와 같은 동작을 한 번 → 저장 → 되돌리기.
  7. **내보내기 창:** 위 편집 10여 번 뒤 `내보내기` → 대화창이 열리고 `내보낼 곳` 목록 또는 `내보낼 곳을 확인하고 있어요.`, 페이지 어디에도 `Something went wrong`·`화면을 그리다 멈췄어요` 없음, 콘솔 `pageerror` 0.
  8. **오염된 고정 프로젝트로 한 번 더:** 3·6(자르기 저장 200)을 `duplicatedOverlays`로.
- [ ] **Step 2: 돈다** — Run: `cd apps/web && npm run test:e2e:real-flow` → **전부** 통과(Task 1~16이 만든 파일 포함). 실패하면 원인이 이 Task의 시험 코드인지(선택자·기다림) 제품인지 먼저 가르고(`CLAUDE.md` §1-8), 제품이면 해당 Task의 파일을 고치되 그 사실을 보고에 적는다.
- [ ] **Step 3: 이 묶음을 표준 검증에 넣는다** — `docs/development-fast-path.ko.md` `## 11`(명령·주소)의 e2e 줄 아래에 `cd apps/web && npm run test:e2e:real-flow` — "진짜 백엔드·고정 시험 프로젝트로 편집 흐름을 밟는다(2026-10-08 계획 H). 가짜 API e2e가 못 잡는 materialize·되돌리기·placement 결함을 잡는다" 한 줄.
- [ ] **Step 4: 커밋**
```bash
git add apps/web/e2e-real docs/development-fast-path.ko.md
git commit -m "test(e2e): 고르기·속도·되돌리기·트랙 단추·분할·빼기·끌기·내보내기를 진짜 백엔드로 밟는다

이번 점검 결함은 가짜 API만 밟는 시험을 전부 통과했다. 서버 값으로 잰다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 18: 마지막 실기 검증·인계·푸시 — 약 4시간(전체 pytest 45분 포함)

- [ ] **Step 1: 넓은 검증(한 번씩, 다른 무거운 일 없이)**
  - 백엔드 **단독**: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --ignore=tests/test_mcp_server.py` → 알려진 1건 외 통과. 실패는 트레이스백을 남기고 같은 명령을 한 번 더(기억 메모: 단독 실행).
  - 웹: `cd apps/web && npx vitest run` → 알려진 1건 외. `npx tsc --noEmit` → 0. `npm --prefix apps/web run build` → 성공.
  - e2e: `cd apps/web && npm run test:e2e`(가짜 API, 48건 내외 — 포트 4173 점거자 주의, 기억 메모) → 시험 통과(끝 `unexpected PNG` 무관), 스냅샷 PNG 차이 기록 후 되돌림. `npm run test:e2e:real-flow` → 전부. `node --test e2e/support/release-gates.test.mjs e2e-real/support/controlCensus.test.mjs` → fail 0. 도크 끌기 게이트 3회(Task 0의 기준선).
- [ ] **Step 2: 컨테이너 재빌드** — PowerShell: `.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild`. 실패하면 멈춘다. 브라우저 `Ctrl+F5`.
- [ ] **Step 3: 실제 화면 — 1440×900·1280×720·375×812**(owner 프로젝트는 바꾼 것을 전부 편집기 되돌리기로 원복하고 서버 값을 대조한다)
  - **0907:** 영상 2~5번째 클립을 차례로 눌러 오른쪽 구간이 그 클립과 같다(스파이크 기준 5/7 → **0** 오선택). 속도 2 → 서버에서 그 장면만 → 되돌리기. 트랙 머리 9개를 마우스로(`elementFromPoint` 자기 자신). 클립 3 끝 손잡이 끌기 → **200**(점검 때 422) → 되돌리기. `편집 대상` 옵션 수 = 고유 값 수(점검 17→3,581). 매니페스트 오버레이 수 **4**(점검 18). 분할 직후 1분: 요청 수·겹침 0·API 컨테이너 CPU(`docker stats --no-stream` 3회, 점검 78%)·화면이 "만드는 중"에서 미리보기로 돌아온 시각(서버 `succeeded` 시각과 차이). 자료 카드 다섯 장 이름.
  - **742e1924:** 120초 전체 보기 눈금 글자 수(기대 9), 끌어 옮기기 붙기 → 되돌리기.
  - **1280×720:** 타임라인 높이·보이는 트랙 수·문서 넘침. **375:** 가로 넘침 0(`scrollWidth === clientWidth`), 트랙 머리가 타임라인을 다 먹지 않는다(머리 칸 ≤ 화면 폭의 35%).
  - **두 시험 프로젝트**(`project-de4b6405`, `243-ab10834c`): 영어·500 대신 Task 15 문구.
  - 내보내기 창: 0907에서 편집 10번 뒤 열기 — 크래시 없음.
  - 스크린샷(1440·1280·375)을 `docs/superpowers/audit-evidence/2026-10-08-editor-ui/after-h/`에.
- [ ] **Step 4: 갭 점검표** — 이 계획 Task 0~17의 Step을 하나씩 대조해 **안 한 것**을 적는다(예: 세로 스크롤 동기, 실시간 재생, ripple 기본값 꺼짐, 0907 데이터 수리 미적용, #185 재현 여부, 겹친 배치 override는 안 당김). 재사용 후보·실제 반영·제외와 이유·경계 보존(§8.3).
- [ ] **Step 5: 다른 계획서에 흔적** — `docs/superpowers/plans/2026-10-02-audit-g-screen-improvements.ko.md` 맨 위 머리 아래에 `> 2026-10-0X: Task 0·6·13은 계획 H(2026-10-08-editor-core-repair-h.ko.md)가 먼저 실행했다 — 건너뛴다. Task 17 갭 점검에 그렇게 적는다.` 한 줄. `docs/superpowers/plans/2026-10-02-audit-00-master.ko.md` §1 표 아래 `> 2026-10-0X: 계획 H(편집기 핵심 수리)가 B–F보다 먼저 들어왔다. 바뀐 공유 파일: … (H 문서 "같이 고치는 파일" 표)` 한 줄.
- [ ] **Step 6: 인계** — `docs/handoffs/2026-10-0X-editor-core-repair-h.ko.md`(실제 날짜): 한 일·잰 값(Step 3 표)·검증하지 못한 것·owner 결정 다섯·다음 계획(B–F). `CLAUDE.md` §2 표의 `최신 세션 인계` 줄을 이 파일로 옮긴다(`tests/test_handoff_entry_point.py`가 지킨다 — 돌린다).
- [ ] **Step 7: 커밋 → 푸시** — `git add` 인계·두 계획서·`CLAUDE.md`·증거 그림 → 커밋. 그 다음 **따로** `git push origin main`(강제 금지). 권한이 막으면 우회하지 말고 owner에게 요청.

---

## owner 결정이 필요한 것 (기본값과 비용)

| # | 결정 | 추천 기본값 | 고르면 드는 것 |
|---|---|---|---|
| 1 | **0907 저장 데이터 정리** — `timeline_002.json`의 세션 투영 클립 15개를 걷어 낼까? | **걷어 낸다**(Task 5 도구 `--apply --project 0907-b26195af`) | 파일 하나 재작성, `.bak-h-…`와 되돌릴 목록이 남고 `--undo`로 되돌린다. 안 해도 Task 4 뒤 0907은 동작한다 — 안 하면 "읽을 때 건너뛰기"에 계속 기대고, 그 파일에서 새 변형본을 만들 때마다 걸러 내는 일이 반복된다 |
| 2 | **빼기 정책** — 빼면 뒤 장면을 당길까(캡컷), 구멍을 보여 줄까? | **당기기 추천**(캡컷 기본·"캡컷 껍데기" 방향), 단 출하 기본은 결정 전까지 `leave_gap` | 당기기: 상수 한 줄(`DEFAULT_REMOVE_MODE = "ripple"`) + 시험 기대 한 줄. 유진의 "이 장면 빼 줘"도 같이 당겨진다. 따로 옮겨 둔 B-roll·오버레이 중 뺀 구간과 겹친 것은 안 당겨진다(뒤에 있는 것만). 구멍: 지금처럼 검은 구간이 남고 화면이 `뺀 장면 자리`로 보여 준다 |
| 3 | **e2e 스냅샷 그림 갱신** — 트랙 머리 칸·손잡이·눈금으로 편집기 스냅샷이 달라진다 | 차이를 보고 승인 | 승인 전까지 `product-shell`·`editor-workbench` 스냅샷 비교가 다르다고 보고된다 |
| 4 | **시험 프로젝트 둘**(`project-de4b6405`, `243-ab10834c`) — 편집판이 없는 세션 | **보관**(되돌릴 수 있음) | 지금은 한국어로 "열 수 없어요"만 말한다. 영구 삭제는 유진에게도 화면 일괄에도 열지 않는다(2026-10-02 결정) |
| 5 | **죽은 단추 중 "없는 기능"이라 지울 것** | `2026-08-30` 규칙대로 지운다 | Task 16 보고의 목록을 보고 남길 것이 있으면 그 기능을 만드는 별도 결정이 필요하다 |

## 확인하지 못한 채 남는 것 (계획 시점)

- React #185는 점검에서 1회 관찰·재현 안 됨. 원인은 추정(겹친 id 상태). Task 6 Step 1이 재현을 시도하지만 못 하면 **오류 화면이 안전망일 뿐 원인은 미확정**으로 남는다.
- 재생기가 실제로 돌려주는 시각은 점검의 한 숫자(`1.899064`)뿐이다. 1프레임 길이 장면에서 규칙이 맞는지는 실물이 없다(스파이크 §7).
- 이 창(내장 브라우저)은 영상 프레임을 그리지 않는다 — 빼기 구멍이 실제로 검은 화면인지, 앞 화면 그림이 실제로 그 장면인지는 Task 18에서 Wbrowser 또는 실제 Chrome 스크린샷으로만 확인된다.
- 컨테이너에서 Postgres 저장소 + 파일 편집판 조합으로 Task 4 문지기가 도는지는 단위 시험(파일 저장소)으로만 봤다 — Task 18 실기가 첫 확인이다(기억 메모: 시험은 윈도우, 제품은 리눅스).

## 계획서 자체 점검 메모 (작성자)

- 모든 앵커 문자열은 작성 시점(`6755bfe04`)에 `grep`으로 존재·유일성을 확인했다. 이름 일관성: `resolvePlaybackSelection`·`frameDurationSec`(Task 3), `is_session_projection_clip`·`without_session_projection_clips`·`timeline_contains_session_projection`(Task 4·5), `readCssPixels`(Task 7·10), `snapDragProposal`(Task 9), `rulerIntervals`·`rulerMarks`·`formatRulerLabel`(Task 10), `getExactPreviewStatus`·`exactPreviewPollStatus`·`capturePreviewStill`(Task 11), `DEFAULT_REMOVE_MODE`·`removed_scene`(Task 12), `editFailureMessage`(Task 14), `announceEditorFeedback`(Task 16).
- Task 19개(0~18), 합계 약 **51시간**(0:1 · 1:3 · 2:2.5 · 3:2 · 4:3 · 5:1.5 · 6:2.5 · 7:4 · 8:5 · 9:3 · 10:2 · 11:3 · 12:4 · 13:2 · 14:2 · 15:1 · 16:3 · 17:3 · 18:4). 스파이크 추정(19시간 + 리플 5)은 타임라인 조작층만이었다 — H는 폴링·생성기·e2e 하네스·죽은 단추·500을 더한다.
