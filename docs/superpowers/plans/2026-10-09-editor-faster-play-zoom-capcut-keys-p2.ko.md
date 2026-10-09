# 계획 P2 — 더 빠른 재생·타임라인 줌·캡컷 단축키 맞춤 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> 실행 모델은 **Claude Sonnet**. Task 하나씩, 앞 Task 커밋 위에서. 이 문서의 Global Constraints가 모든 Task에 걸린다.

**Goal:** 대표님이 (1) 스페이스·L 키로 영상을 **3~4배까지 빠르게** 훑어보고, (2) 짧은 프로젝트도 타임라인이 **1초에 화면 절반을 쓰지 않고** 여러 초를 한눈에 보여 주며 키·단추로 쉽게 늘이고 줄이고 되돌아오고, (3) 컷 편집 단축키가 **캡컷 PC와 같은 키**로 동작한다(편집기에 있는 명령만).

**Architecture:** 새 명령은 만들지 않는다. (A) `playbackRate.ts`의 빠르기 단계를 위로 늘리고 첫 사용 안내를 붙인다. (B) `timelineZoomScale.ts`의 처음 배율·줄이기 바닥 규칙을 "짧은 영상은 영상 전체" → "적어도 20초 창"으로 바꾸고, 눈금을 영상 끝 뒤 빈 자리까지 그린다. (C) 지금 세 곳(미리보기·작업판·타임라인)에 흩어진 키 판정을 **표 하나 + 문지기 함수 하나**(`editorShortcuts.ts`)로 모으고, 그 표에 캡컷 키(Q·W·↑·↓·Home·End·Shift+Z)를 더해 이미 있는 명령(`onTrimNarration`·`onUpdatePlacements`·`seek`·`runZoom`)으로 보낸다. `단축키` 안내 글은 그 표에서 만든다.

**Tech Stack:** React 19, vitest + Testing Library(jsdom), Playwright 1.61(번들 Chromium), 진짜 백엔드 e2e 묶음(`npm run test:e2e:real-flow`), FastAPI + pytest(`.venv`, 시드 스크립트만), ffmpeg.

**Spec:** 대표님 말(2026-10-09, 아래 "대표님 말과 해석"), 앞 계획 `docs/superpowers/plans/2026-10-09-editor-playback-p.ko.md`(재생 시계·문지기·빠르기 0.25~2배·단축키 안내 — 전부 출하됨, 인계 `docs/handoffs/2026-10-09-editor-playback-p.ko.md`), 진단 `docs/superpowers/2026-10-09-playback-diagnosis.ko.md`, 이 문서의 "캡컷 단축키 조사" 절.

---

## 대표님 말과 해석 (이 계획의 기준)

| 대표님 말(2026-10-09) | 해석 | 근거·남는 모호함 |
|---|---|---|
| "스페이스바를 누르면 **더 빠르게** 재생되길 바랐다. 1초·2초·3초가 지나가는 속도가 너무 느리다" | 훑어보기용 **보는 속도를 1배보다 빠르게**(3~4배). 앞 계획은 "더 느리게"로 읽었다 — **틀린 해석이었다**, 이번에 바로잡는다 | 재생 자체가 다시 느려진 것(0.65배 결함 재발)일 가능성도 Task 0에서 742로 1배=1.00을 다시 재서 배제한다. 대표님 체감은 못 잰다 |
| "초당 프레임이 그렇게 길어지면 수동 편집 자체가 힘들다" | 짧은 프로젝트의 처음 배율이 너무 크다(7.75초 → 약 153px/초, 1초 눈금). 그리고 **줄이기 바닥이 "영상 전체"라 더 줄일 수도 없다** | 코드: `initialPixelsPerSecond`가 60초보다 짧으면 영상 전체를 칸 폭에 맞추고, `pixelsPerSecondBounds`의 `min`이 그 값이다 |
| "컷 편집 단축키를 캡컷과 똑같이" | 캡컷 PC(Windows) 키를 **편집기에 있는 명령에만** 붙인다. 없는 기능의 키는 만들지 않는다(`2026-08-30`, `2026-08-17` 승인 기록 §"없는 기능의 버튼 자리를 만들지 않는다") | 캡컷 공식 단축키 표는 찾지 못했다 — 아래 조사 절의 등급을 따른다 |

---

## 캡컷 단축키 조사 (2026-10-09 조회)

### 출처

| 표시 | 출처 | 성격 |
|---|---|---|
| O1 | https://www.capcut.com/resource/pc-professional-video-editor | **캡컷 공식 사이트**. 원문 인용(짧게): "Use Ctrl + B (Windows) … to quickly cut", "spacebar to start and stop the video, and the arrow keys to move frame by frame" |
| O2 | https://www.capcut.com/resource/split-video-into-parts | **캡컷 공식**. 되돌리기 `Ctrl + Z` |
| T1 | https://gist.github.com/natthasath/cbcfad46ab260007b009d0b6889d5109 | 제3자 표(51줄). T2와 거의 같은 표 — **같은 뿌리로 보고 한 묶음으로 센다** |
| T2 | https://defkey.com/capcut-video-editor-shortcuts | 제3자, "Based on: Reddit post", 2025-01-28 |
| T3 | https://fastshortcuts.com/shortcuts/capcut/ | 제3자, 2026-09-27 확인이라고 적힘 |
| T4 | https://shortcuts.kstanchev.com/apps/capcut/ | 제3자, 19개 |
| X | https://www.meowtool.com/en/capcut-keyboard-shortcuts/ | 제3자. **O1과 어긋난다**(한 프레임 이동을 `Alt+←/→`로 적음, Q를 "끼워 넣기"로 적음) → 신뢰하지 않고 반대 근거로도 쓰지 않는다 |

캡컷 도움말 센터(`capcut.com/help/interface-and-settings`)에는 단축키 글이 없었고 `capcut.com/help/keyboard-shortcuts`, `capcut.com/resource/capcut-keyboard-shortcuts`는 404였다. 캡컷 앱 안 단축키 목록(메뉴 → 단축키)은 이 기계에 캡컷이 없어 **못 봤다** → owner 결정 4.

**등급:** `공식` = O1·O2에 있음. `교차` = 공식에는 없지만 서로 다른 묶음 둘 이상({T1,T2}·T3·T4)이 **같은 키**를 적고 믿을 만한 반대가 없음. `미확인` = 한 묶음만 적었거나 서로 다름 → **만들지 않는다.** 안내 글의 `캡컷과 같아요`는 `공식`·`교차`에만 붙인다(owner 결정 4로 확인받는다).

### 캡컷 키 → VideoBox 명령 (만드는 것)

| 동작 | 캡컷 키(Windows) | 등급(출처) | VideoBox에서 부르는 것 | 지금 상태 |
|---|---|---|---|---|
| 재생/일시정지 | `Space` | 공식(O1) | `PreviewStage` `togglePlayback` | 있음 |
| 한 프레임 앞/뒤 | `→` / `←` | 공식(O1) | `stepFrame`(타임라인 면 안이면 `navigationKeyAction`) | 있음 |
| 나누기 | `Ctrl+B` | 공식(O1) | `cutToolbarState().split.action` → `onInspectorAction`(`split-narration`) | 있음 |
| 되돌리기 | `Ctrl+Z` | 공식(O2) | `onUndo` | 있음 |
| 다시 하기 | `Ctrl+Shift+Z` | 교차(T3·T4) | `onRedo` (+우리 쪽 `Ctrl+Y`도 그대로) | 있음 |
| 고른 것 지우기 | `Delete` / `Backspace` | 교차(T3 Backspace·T4 Delete) | `cutToolbarState().drop.action`(`set-cut-action remove`, 출하 정책 `leave_gap`) | 있음 |
| 재생 위치 왼쪽 지우기 | `Q` | 교차(T1/T2·T3·T4) | 고른 장면(또는 고른 배치 하나)의 **시작을 재생 위치로** 자르기 → `onTrimNarration` / `onUpdatePlacements` | **새 키**(명령은 있음) |
| 재생 위치 오른쪽 지우기 | `W` | 교차(T1/T2·T3·T4) | 같은 것, **끝을** 재생 위치로 | **새 키** |
| 이전/다음 자른 자리 | `↑` / `↓` | 교차(T1/T2·T3) | 타임라인 `seek` — 클립·빈 구간·캡션 경계(`sourceSnapCandidates`) 중 바로 앞/뒤 | **새 키**(이동 명령은 있음) |
| 처음/끝으로 | `Home` / `End` | 교차(T1/T2·T3) | `seek` `bound: start/end` | 타임라인에 초점 있을 때만 → **어디서나** |
| 타임라인 늘리기/줄이기 | `Ctrl+=`(`Ctrl++`) / `Ctrl+-` | 교차(T1/T2·T3·T4) | `runZoom("in"/"out")` | 있음 |
| 타임라인 맞춤 | `Shift+Z` | 교차(T1/T2·T3) | `runZoom("fit")` (+우리 쪽 `Ctrl+0` 그대로) | **새 키** |
| 멈춤 | `K` | 교차(T1/T2) | `pause` | 있음 |
| 빠르게(누를수록) | `L` | 교차(T1/T2) | `faster` | 있음(단계만 늘림) |
| 느리게 | `J` | **캡컷과 다름** — 캡컷은 "거꾸로 재생"(T1/T2). 브라우저 `<video>`는 거꾸로 못 튼다 | `slower`(앞 계획 결정 유지) | 있음, 안내에 `캡컷과 달라요` |

### 만들지 않는 것 (짝이 없거나 확인 못 함)

| 캡컷 키 | 이유 |
|---|---|
| `Ctrl+Shift+B` 모든 트랙 나누기 | 따로 된 명령이 없다(우리 나누기는 늘 장면 단위). **지금 코드는 Shift를 안 봐서 이 키도 나누기를 한다 — 그대로 둔다**(회귀 금지), 안내에는 안 적는다 |
| `B`/`A` 나누기·고르기 모드, `[`/`]` 왼쪽/오른쪽 모두 고르기, `Ctrl+A` | 모드·여러 장면 고르기 없음 |
| `M`·`Alt+M`·`Shift+M` 표시(마커) | 마커 기능 없음 |
| `N` 자동 붙기 켜고 끄기, `P` 주 트랙 자석, `~` 연결 | 끄고 켜는 스위치 없음(붙기는 늘 켜짐). 자석 = 빼기 정책 `ripple`, owner 결정 대기(`editing_session.py` `DEFAULT_REMOVE_MODE`) |
| `V` 클립 켜고 끄기 | 우리 `빼기`는 자리를 비우고 사라진다 — 같지 않다 |
| `Ctrl+C/V/X`, `Ctrl+D` 복제, 정지 화면 | 복사·붙여넣기 없음. `Ctrl+D`는 출처끼리 다르다(T4 복제 / X 당겨 지우기) → 미확인 |
| `Ctrl+G` 묶기, `Alt+G` 합친 클립, `Ctrl+R` 속도 창, `Shift+B` 곡선 속도, `Alt+K` 키프레임, `Ctrl+Shift+S` 소리 분리, `I`/`O`/`Shift+X` 구간, `Ctrl+.`/`,` 음량 | 기능 없음·범위 밖(`CLAUDE.md` §2.1 임의 키프레임 제외). `Ctrl+R`은 브라우저 새로고침이라 가로채면 안 된다 |
| `Shift+←/→` 여러 프레임 | 몇 프레임인지 출처에 없다 → 미확인 |

### 지금 쓰는 키와 부딪힘 정리

| 키 | 지금 | 캡컷 | 결정 |
|---|---|---|---|
| `J` | 느리게 | 거꾸로 재생 | 느리게 유지, 안내 `캡컷과 달라요` |
| `Ctrl+0` | 맞춤 | (없음) | 그대로 + `Shift+Z` 추가 |
| `Ctrl+Y` | 다시 하기 | (출처에 없음) | 그대로 |
| `↑`/`↓` | 타임라인 높이 손잡이(`role="separator"`)·캡션 글칸이 씀, 타임라인 칸 세로 스크롤 | 자른 자리 | 손잡이·글칸 위에서는 비킨다(문지기 규칙). 타임라인 면 안에서는 **자른 자리로 간다**(칸의 키보드 세로 스크롤은 잃는다 — 바퀴·끌기로 된다) |
| `Home`/`End` | 타임라인 면 안에서만 | 처음/끝 | 어디서나. 타임라인 면 안은 지금처럼 타임라인이 받는다(두 번 안 받게) |
| `Delete`/`Backspace`·`Q`·`W` | Delete만 있음 | 지우기 | 셋 다 **출하 정책 `leave_gap`을 따른다**: 뒤 장면은 제자리, 빈자리가 남는다. 캡컷 주 트랙 자석은 당긴다 — **정책은 바꾸지 않는다**(owner 결정 대기, 안내에 "빈자리는 그대로 둬요") |

---

## 다른 계획과의 경계

| 계획 | 관계 |
|---|---|
| P(재생 수리, 끝남) | `playbackClock`·되감기 고리 제거·스페이스 문지기 규칙 1~7을 **바꾸지 않는다**. P의 `playbackShortcutFor`는 이번에 표 하나를 거치는 얇은 포장이 되고 **기존 시험은 그대로 통과해야 한다** |
| H(편집기 핵심 수리) | H Task 3의 처음 배율 다시 맞추기(`lastFittedRef` — 열쇠 (폭, 길이)), `deriveClipRect`가 안 던지는 것을 **회귀시키지 않는다**. Task 2가 H 시험을 다시 돈다 |
| I(디자인 시스템) | 새 UI(안내 한 줄·단축키 표)는 기존 토큰·`@/components/ui`만 |
| 유진(B–F) | 단축키는 **이미 있는 명령의 다른 입력 방법**이다 — 상시 지시(2026-09-11 "화면으로 되는 건 유진에게도")의 대상인 *명령*은 그대로이고 유진은 이미 나누기·빼기·자르기·줌(`zoomCommand`)을 부른다. **유진 배선 없음.** 빠르기 3~4배는 보는 방식(앞 계획 결정 2 그대로) |

### 같이 고치는 파일 (앵커는 줄 번호가 아니라 **문자열**)

| 파일 | Task |
|---|---|
| `apps/web/src/features/editor/preview/playbackRate.ts`(+시험) | 1 |
| `apps/web/src/features/editor/preview/preview-stage.tsx`(+시험) | 1, 3, 5 |
| `apps/web/src/features/editor/timeline/timelineZoomScale.ts`(+시험) | 2 |
| `apps/web/src/features/editor/timeline/TimelineDock.tsx`, `timeline-dock.test.tsx` | 2, 3, 4 |
| `apps/web/src/features/editor/timeline/timelineNavigation.ts`(+시험) | 4 |
| `apps/web/src/features/editor/preview/playbackShortcuts.ts`, `timeline/timelineZoomShortcuts.ts`, `workbench/cutShortcuts.ts`(+각 시험) | 3 |
| `apps/web/src/features/editor/workbench/EditorWorkbench.tsx` | 3 |
| `apps/web/src/styles/editor-workbench.css` | 1, 2, 4, 5 |
| `scripts/e2e_editor_fixture.py`, `scripts/e2e_real_editor_api.py`, `tests/test_e2e_editor_fixture.py`, `apps/web/e2e-real/support/realFlow.mjs` | 0 |

## 새로 만드는 파일

| 파일 | 책임 |
|---|---|
| `apps/web/src/features/editor/editorShortcuts.ts` (+`.test.ts`) | 단축키 **표 하나**(`EDITOR_SHORTCUTS`)와 **문지기 하나**(`editorShortcutFor`). 키 이름·화면 글·캡컷 같음 여부가 여기만 있다 |
| `apps/web/e2e-real/capcut-shortcuts.spec.mjs` | 표의 모든 키를 진짜 Chromium·진짜 백엔드에서 밟고 서버 상태·되돌리기까지 확인 |
| `apps/web/e2e-real/zoom-and-rate-baseline.spec.mjs` | Task 0 측정(배율·보이는 초·빠르기 상한) — 측정값을 출력하고, Task 1·2 뒤 문턱을 단다 |

---

## Global Constraints

- 최상위 지침은 `CLAUDE.md`. 메인 체크아웃 `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`(브랜치 `main`). Task 시작마다 `git status --short`(`?? .anchor/`만), `git log -1`이 앞 Task 커밋인지. 아니면 멈추고 보고. 계획 작성 시점 HEAD `4594fe34d`(요청서의 `a5d52e6c7`보다 둘 앞 — 둘 다 레이아웃·재생 미리받기, 이 계획 앵커와 무관함을 확인함).
- **앵커는 문자열로 찾는다.** 인용한 옛 코드가 그대로 있으면 진행, 없으면 **멈추고 보고**(짐작해서 고치지 않는다).
- **RED를 실제로 본다.** RED 시험이 처음부터 통과하면 멈추고 보고. RED/GREEN 단계에서는 그 시험 하나만(`CLAUDE.md` §3).
- 명령: 웹 `cd apps/web && npx vitest run <파일> -t "<시험 이름>"`(저장소 루트에서 돌리면 jsdom이 깨진다), 타입 `cd apps/web && npx tsc --noEmit`, 빌드 `npm --prefix apps/web run build`, 백엔드 `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider <파일>::<시험>`(맨 `pytest` 금지), 진짜 백엔드 e2e `cd apps/web && npm run test:e2e:real-flow -- e2e-real/<파일>`, 가짜 API e2e `cd apps/web && npm run test:e2e`(**단독으로** 돌린다 — 48/49 통과 기대, 포트 4173 점거자 주의, 끝의 `unexpected PNG: product-shell-mobile-menu-open.png` exit 1은 무관).
- **팔레트는 바꾸지 않는다**(`2026-08-29`). 새 CSS는 기존 토큰(`--vb-*`, `--border`, `--muted-foreground` …)만. 새 색 값 금지.
- **없는 기능의 키·단추를 만들지 않는다**(`2026-08-30`). 위 "만들지 않는 것" 표에 있는 키는 문지기가 `null`을 돌려야 한다(시험으로 지킨다).
- **빼기 정책을 바꾸지 않는다.** `DEFAULT_REMOVE_MODE = "leave_gap"`(`editing_session.py`). Delete·Q·W 모두 빈자리를 남긴다.
- 화면 문구 §10.13: 명사형 이름표 + 짧은 해요체. `provider`·`runtime`·`job`·`revision`·`pipeline`·`model` 금지. 키 이름은 자판 글자 그대로(`Ctrl + B`, `Shift + Z`, `Delete 키`, `Home 키`, `스페이스바`, `J 키`, `← →`, `↑ ↓`) — 이것 말고 영어 단어 금지. UI Task마다 `cd apps/web && npx vitest run src/user-copy-policy.test.ts`. **표 글은 `.ts` 파일이라 그 정책 시험이 못 읽는다** → `editorShortcuts.test.ts`가 같은 금지어를 따로 검사한다(Task 3).
- 날 것 `<button data-native-control=…>`를 **새로 만들지 않는다**(`task22-parity-owners.test.ts`). 새 조작이 필요하면 `@/components/ui`의 `Button`·`NativeSelect`.
- **대표님 프로젝트는 읽기만.** 742 등 실물은 열기·재생·일시정지·탐색·빠르기·줌(보기 상태, 저장 안 됨)까지. **편집 키(Ctrl+B·Delete·Q·W·되돌리기)는 시험 고정 프로젝트에서만** 밟는다.
- 재생 측정은 **같은 측정 3회 중앙값**, 결정적인 값(앱의 `currentTime` 쓰기 0·역행 0)은 매회. 내장 브라우저 창은 영상·rAF를 안 그린다 — 재생·화면 확인은 Playwright.
- 이미 알려진 실패(고치려 들지 마라): `editor-workbench.test.tsx` "gives the material dock back the same way, without needing a second click", `tests/test_owner_ready_script.py::test_smoke_timeout_kills_the_child_tree_and_returns_bounded_failure`.
- 커밋은 Task마다, 한국어, 끝줄 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. 확인 명령과 커밋·푸시를 한 명령에 묶지 않는다. 푸시는 Task 6에서 `git push origin main`(owner 상시 승인, **강제 금지**). 권한이 막으면 우회하지 말고 owner에게 알린다.
- **검증 넷(Task마다 고정):** 갭(Step 대조, **안 한 것**을 적는다) · 역방향(진짜 백엔드 e2e — 진짜 Chromium) · 동작(px/초·보이는 초·배속·서버 값으로 잰다) · 배선(`grep`으로 화면이 실제로 부르는 자리를 센다).

## Review Focus

행복한 경로 시험이 놓치기 쉬운 실제 입력 다섯. 각각 맡은 Task에 시험을 넣었다.

1. **편집 키가 글칸·서랍 안에서 눌릴 때**(캡션 고치는 중 `Q`·`W`·`Delete`·`↑`, 유진 입력칸, 미디어 서랍) — 표를 하나로 모으다 문지기 규칙이 하나라도 빠지면 글을 쓰다 장면이 잘린다 → Task 3 시험 "글칸·aria-modal 안에서는 편집 키가 null" + Task 4 e2e "캡션 글칸에 q·w를 쳐도 서버 장면은 그대로".
2. **재생 위치가 고른 장면 밖이거나 경계에 딱 있을 때 Q·W** — 길이 0 장면이나 반대쪽 자르기가 생기면 안 된다 → Task 4 시험 "재생 위치가 장면 안(반 프레임 여유)일 때만 자른다, 아니면 안내만".
3. **영상보다 넓은 창(짧은 프로젝트를 20초 창으로 볼 때) 뒤쪽 빈 자리를 누르거나 재생 머리가 끝에 있을 때** — 시간 계산이 길이를 넘거나 `deriveClipRect`가 던지면 편집기가 통째로 죽는다(H 사고) → Task 2 시험 "빈 자리 클릭은 끝으로", "보이는 끝이 길이를 넘어도 클립 사각형은 유한".
4. **4배로 틀다가 미리보기가 새로 만들어지거나(소스 교체) 끝에 닿을 때** — 소스가 바뀌면 브라우저가 빠르기를 되돌린다(P Review Focus 3) → Task 1 시험 "소스가 바뀌어도 4배", e2e "끝에서 멈추고 4배 유지".
5. **키를 꾹 누를 때**(`Ctrl+=` 꾹 → 계속 늘림은 정상, `Q`·`Delete`·`Ctrl+B` 꾹 → 한 번만) — 반복 이벤트마다 편집이 나가면 저장 중 겹침·되돌리기 여러 칸이 생긴다 → Task 3 시험 "`repeat`는 줌·되돌리기·한 프레임 이동만 받는다".

---

## 재사용 게이트 (`implementation-plan.ko.md` §8.1)

| 후보 | 판단 | 반영 단위 |
|---|---|---|
| `playbackShortcuts.ts`의 문지기 규칙(조합 중·반복·글칸·`aria-modal`·타임라인 면·스스로 키를 쓰는 조작) | **partial port → 승격** | `editorShortcuts.ts`로 옮기고 `playbackShortcutFor`·`cutShortcutFor`·`timelineZoomShortcutFor`는 그 위의 얇은 포장(이름·시그니처 유지, 기존 시험 그대로) |
| `cutToolbarState`(나누기·빼기 가능 여부) | **adopt as-is** | 키는 단추가 정한 것을 그대로(`cutShortcuts.ts` 규약) |
| `deriveNarrationTrim`·`derivePlacementTrim`·`keyboardTrim`/`updatePlacement` | **adopt as-is** | Q·W = `proposedSec`가 재생 위치인 자르기 |
| `sourceSnapCandidates`(클립·빈 구간·캡션 경계) | **adopt as-is** | ↑·↓의 "자른 자리" 목록 |
| `zoomControls`/`runZoom`(단추·키·바퀴·유진이 한 표) | **adopt as-is** | Shift+Z도 `runZoom("fit")` |
| 진단 스크립트 `.superpowers/sdd/playback-diagnosis-2026-10-09/scripts/measure-playback.mjs`·`playbackProbe.mjs` | **adopt** | 빠르기 상한 측정·742 1배 재확인 |
| `ruler-scale.spec.mjs`의 `stretchTo120`(재생 목록 길이만 바꿔 받기) | **adopt pattern** | 길이 7.75·30·120·600초 배율 측정 |
| 캡컷 앱의 단축키 사용자 지정, 마커, 모드 전환 | **exclude** | 기능 없음·범위 밖 |
| 타임라인 줌 **슬라이더** | **exclude(이번)** | `@/components/ui`에 슬라이더가 없다 — 새 부품 반입은 I 계획 몫. owner 결정 6 |

---

### Task 0: 착수 확인 + 기준 측정 + 시험 고정 프로젝트 + 첫 RED — 약 3.5시간

**Files:**
- Modify: `scripts/e2e_editor_fixture.py` — 앵커 `def _seed_playback(store: LocalProjectStore, media: dict[str, Any]) -> dict[str, str]:`, `    project = store.bootstrap_project(name=PLAYBACK_PROJECT_NAME)`, `        "playback": _seed_playback(store, media),`
- Modify: `scripts/e2e_real_editor_api.py` — 앵커 `"playback": _camel(ids["playback"])}, indent=2),`
- Modify: `tests/test_e2e_editor_fixture.py` — 앵커 `def test_playback_fixture_is_thirty_seconds_in_four_scenes(tmp_path: Path) -> None:`
- Modify: `apps/web/e2e-real/support/realFlow.mjs` — 앵커 `/** @returns {{ clean: Fixture, duplicatedOverlays: Fixture, noNarration: Fixture, playback: Fixture }} Fixture = { projectId, sessionId, timelineId } */`
- Create: `apps/web/e2e-real/zoom-and-rate-baseline.spec.mjs`, `apps/web/e2e-real/capcut-shortcuts.spec.mjs`

**Interfaces:**
- Produces(Python): `SHORTCUTS_PROJECT_NAME = "단축키 시험"`; `_seed_playback(store, media, *, name: str = PLAYBACK_PROJECT_NAME)`; `seed_editor_fixtures` 반환에 `"shortcuts"`(장면은 `PLAYBACK_SCENES` 그대로: 7.5초 넷, 30초).
- Produces(JS): `readFixture().shortcuts`; 스펙 머리에 `// covers: <id>` 주석(Task 3의 표 시험이 읽는다).

- [ ] **Step 0: 착수 상태** — `git status --short` → `?? .anchor/`만. `git log --oneline -3`, `git worktree list`, `git diff --check` → 없음. `docs/handoffs/2026-10-09-editor-playback-p.ko.md`와 이 계획의 "캡컷 단축키 조사"를 읽는다.

- [ ] **Step 1: 단축키 고정 프로젝트(RED→GREEN)** — 시험 `test_shortcuts_fixture_is_a_separate_thirty_second_project`: `ids["shortcuts"]["project_id"] != ids["playback"]["project_id"]`, 장면 `(id, start, end)`가 `list(PLAYBACK_SCENES)`, 프로젝트 이름 `"단축키 시험"`. RED(`KeyError: 'shortcuts'`) → `_seed_playback`에 `name` 인자, 반환 dict에 `"shortcuts": _seed_playback(store, media, name=SHORTCUTS_PROJECT_NAME)`, API 스크립트 `json.dumps`에 `"shortcuts": _camel(ids["shortcuts"])`, `realFlow.mjs` 반환형 주석에 `shortcuts: Fixture` → GREEN. 같은 파일 다른 시험도 한 번.
  왜 따로: 편집 키 시험이 재생 측정 프로젝트(`playback`)를 바꾸면 그 시험과 서로 밟는다.

- [ ] **Step 2: 기준 측정(지금 코드)** — `zoom-and-rate-baseline.spec.mjs`. 측정만 하고 출력한다(문턱은 Task 1·2에서 단다):
  - **배율:** `ruler-scale.spec.mjs`의 `stretchTo120` 모양으로 재생 목록 `output.duration_sec`를 7.75·30·120·600으로 바꿔 받아 `clean` 고정 프로젝트를 1440×900·1280×720에서 열고, `[data-pixels-per-second]`, 클립 칸(`.vb-timeline-lanes-viewport`) 폭, 보이는 초(= 폭 ÷ 배율), 눈금 큰 간격(`.vb-ruler-major` 첫 두 글자)을 `ZOOM_BASELINE` JSON으로 출력. `타임라인 축소` 단추가 잠겼는지(`disabled`)도.
  - **빠르기 상한:** `playback` 고정 프로젝트 + `withLongPreview`. 재생기에 직접(`window.__pb.harness = true` 아래) `playbackRate`를 1·2·3·4·6·8로 걸고 각 8초 `measurePlayback`(시작 0·10초 2회): `effectiveRate`, `rvfcFps`, `getVideoPlaybackQuality()`의 버린 프레임 비율, **소리**: `new AudioContext()` + `createMediaElementSource(video)` + `AnalyserNode` RMS(무음 장치라 0이면 "못 잼"으로 적는다 — 시험 영상에 440Hz 사인이 들어 있다). `RATE_CEILING` JSON 출력.
  - **742 1배 재확인(읽기만):** 컨테이너 `127.0.0.1:5173`이 떠 있으면 진단 스크립트를 그대로 `ONLY=742 STARTS=0,30 PLAY_SEC=20 RUN=1 node .superpowers/sdd/playback-diagnosis-2026-10-09/scripts/measure-playback.mjs editor` → `effectiveRate` 0.95 미만이면 **멈추고 보고**(대표님의 "느리다"가 결함 재발일 수 있다). 컨테이너가 안 떠 있으면 Task 6에서 하고 그 사실을 적는다.
  Run: `cd apps/web && npm run test:e2e:real-flow -- e2e-real/zoom-and-rate-baseline.spec.mjs` → 통과(측정만). 출력 둘을 `.superpowers/sdd/2026-10-09-p2/baseline.md`에 표로 옮긴다.
  계산으로 미리 본 값(1440, 클립 칸 ≈1188px — 진단의 742 19.8px/초에서 역산, **측정으로 바꿔 적는다**):

  | 길이 | 지금 배율 | 지금 보이는 초 | 줄이기 바닥 |
  |---|---|---|---|
  | 7.75초 | ≈153px/초 | 7.75 | 153(더 못 줄임) |
  | 30초 | ≈39.6 | 30 | 39.6 |
  | 120초 | ≈19.8 | 60 | ≈9.9 |
  | 600초 | ≈19.8 | 60 | ≈2.0 |

- [ ] **Step 3: 빠르기 상한 정하기** — `RATE_CEILING`에서 **세 조건을 모두 지키는 가장 큰 값**: `effectiveRate`가 목표의 ±5% 안, `rvfcFps ≥ 25`, 버린 프레임 비율 ≤ 10%. 소리는 잴 수 있으면 RMS > 0도 조건. 결과를 `baseline.md`에 `MAX_RATE = 4`(또는 8 / 3)처럼 적는다. 4가 안 되면 **멈추고 보고**. 8이 되면 Task 1에서 8을 넣을지는 owner 결정 2(기본: 4까지).

- [ ] **Step 4: 첫 RED — Q 키** — `capcut-shortcuts.spec.mjs`(머리에 `test.describe.configure({ mode: "serial" })`, `withLongPreview` 사용):
```js
// covers: trim-left
test("Q 키는 고른 장면의 재생 위치 왼쪽을 잘라 내고, Ctrl+Z로 돌아온다", async ({ page, request }) => {
  const { shortcuts } = readFixture();
  await withLongPreview(page);
  await openEditor(page, shortcuts);
  const before = sceneOf(await serverSession(request, shortcuts), "scene-2");   // 7.5~15
  await page.getByRole("button", { name: /^영상 2번째 장면, \d+초부터$/ }).click();  // 고르고 7.5초로
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  for (let i = 0; i < 30; i += 1) await page.keyboard.press("ArrowRight");          // 30프레임 = 8.5초
  await page.keyboard.press("q");
  await expect.poll(async () => sceneOf(await serverSession(request, shortcuts), "scene-2").start_sec, { timeout: 8000 }).toBeCloseTo(8.5, 2);
  expect(sceneOf(await serverSession(request, shortcuts), "scene-2").end_sec).toBeCloseTo(before.end_sec, 6);
  await page.keyboard.press("Control+Z");
  await expect.poll(async () => sceneOf(await serverSession(request, shortcuts), "scene-2").start_sec, { timeout: 8000 }).toBeCloseTo(before.start_sec, 6);
});
```
  (`sceneOf`는 `remove-scene.spec.mjs`와 같은 한 줄 도우미. 클립 단추 이름은 그 스펙의 `CLIP` 정규식 모양 — 다르면 `clip-selection.spec.mjs`에서 실제 이름을 확인해 맞춘다.)
  Run: `cd apps/web && npm run test:e2e:real-flow -- e2e-real/capcut-shortcuts.spec.mjs` → **FAIL**(`start_sec` 7.5 그대로). 다른 이유로 실패하면(클릭·화살표가 재생 위치를 안 옮김 등) 멈추고 원인부터 본다.

- [ ] **Step 5: 검증 넷 + 커밋** — 갭: 줌·빠르기 문턱은 Task 1·2가 단다. 역방향: 이 Task가 진짜 백엔드. 동작: 측정표. 배선: 해당 없음. 가짜 API e2e `npm run test:e2e` 48/49 그대로. **Task 4 커밋 전까지 real-flow에서 Q 시험 하나가 빨갛다.**
```bash
git add scripts/e2e_editor_fixture.py scripts/e2e_real_editor_api.py tests/test_e2e_editor_fixture.py apps/web/e2e-real/support/realFlow.mjs apps/web/e2e-real/zoom-and-rate-baseline.spec.mjs apps/web/e2e-real/capcut-shortcuts.spec.mjs
git commit -m "test(e2e): 타임라인 배율·빠르기 상한을 재고, 캡컷 Q 키 시험을 먼저 빨갛게 세운다

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 1 (A): 더 빠른 재생 — 3·4배, L 단계, 첫 사용 안내 — 약 3시간

**Files:**
- Modify: `apps/web/src/features/editor/preview/playbackRate.ts`(+`playbackRate.test.ts`) — 앵커 `export const PLAYBACK_RATES = [0.25, 0.5, 0.75, 1, 1.5, 2] as const;`
- Modify: `apps/web/src/features/editor/preview/preview-stage.tsx`(+시험) — 앵커 `  const changeRate = (next: PlaybackRate) => {`, `<label className="vb-preview-stage__rate" title="보는 속도만 바뀌어요. 영상은 바뀌지 않아요 · J 키 느리게 · L 키 빠르게 · K 키 멈춤">`, `<li>L 키 — 재생, 누를수록 빠르게(최대 2배)</li>`
- Modify: `apps/web/src/styles/editor-workbench.css` — 앵커 `.vb-preview-stage__rate`
- Modify: `apps/web/e2e-real/playback-smoothness.spec.mjs`, `zoom-and-rate-baseline.spec.mjs`

**Interfaces:**
```ts
export const PLAYBACK_RATES = [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4] as const;   // Task 0 Step 3이 8을 통과시키고 owner가 고르면 끝에 8
export const PLAYBACK_RATE_HINT_STORAGE_KEY = "videobox.editor.playback-rate-hint-seen";
export function readRateHintSeen(storage?: Pick<Storage, "getItem"> | null): boolean;   // 던지면 true(안내를 못 지우는 창에서 계속 뜨지 않게)
export function markRateHintSeen(storage?: Pick<Storage, "setItem"> | null): void;      // 던져도 조용히
export function maxPlaybackRate(): PlaybackRate;                                          // PLAYBACK_RATES의 끝
```
기본 빠르기는 **1배 그대로**(미리보기가 완성본과 같은 속도여야 컷 길이 판단이 맞다 — owner 결정 1). 고른 값 기억(`PLAYBACK_RATE_STORAGE_KEY`)은 그대로. L 단계는 배열이 정한다: 1 → 1.5 → 2 → 3 → 4, J는 거꾸로.

- [ ] **Step 1: 단계(RED→GREEN)** — `playbackRate.test.ts`: `stepPlaybackRate(2, 1) === 3`, `stepPlaybackRate(3, 1) === 4`, `stepPlaybackRate(4, 1) === 4`, `stepPlaybackRate(4, -1) === 3`, `readPlaybackRate`가 `"4"` → 4·`"5"` → 1, `formatPlaybackRate(4) === "4배"`, `maxPlaybackRate() === 4`. RED → 배열 바꿈 → GREEN.
- [ ] **Step 2: 안내 저장(RED→GREEN)** — `readRateHintSeen`: 없으면 false, `"1"`이면 true, `getItem`이 던지면 true; `markRateHintSeen`이 던지는 저장소에서 안 던진다.
- [ ] **Step 3: 화면(RED→GREEN)** — `preview-stage.test.tsx`: (가) 저장소 비었고 빠르기 1이면 재생줄에 `빠르게 보려면 L 키를 눌러요`(`getByText`); (나) `l`을 재생 중에 눌러 1.5가 되면 안내가 사라지고 `localStorage.getItem(PLAYBACK_RATE_HINT_STORAGE_KEY) === "1"`; (다) 고르기에서 바꿔도 같음; (라) 다시 그려도 안 뜬다; (마) **Review Focus 4**: 4배로 바꾼 뒤 `exactPreview.url`이 바뀌고 `loadedMetadata` → `playbackRate` 4; (바) 고르기 `option` 8개(또는 9개), 마지막 `"4배"`. 구현: `const [hintSeen, setHintSeen] = useState(() => readRateHintSeen());`, `changeRate` 안에서 `markRateHintSeen(); setHintSeen(true);`. 안내는 `<label className="vb-preview-stage__rate" …>` 바로 뒤 `{currentMedia && !hintSeen && rate === 1 && <span className="vb-preview-stage__rate-hint">빠르게 보려면 L 키를 눌러요</span>}`. 고르기 `title`의 `L 키 빠르게`를 `` `L 키 빠르게(최대 ${formatPlaybackRate(maxPlaybackRate())})` ``로. 안내 글의 `(최대 2배)`도 같은 식(Task 5에서 표로 옮겨지지만 이 Task 사이 거짓말을 남기지 않는다). CSS: `.vb-preview-stage__rate-hint { color: var(--muted-foreground); font-size: var(--vb-text-xs, 0.75rem); }` — 이미 있는 토큰 이름은 `editor-workbench.css`에서 `grep`해 쓰고, 없으면 옆 규칙이 쓰는 것을 쓴다(새 색 값 금지).
- [ ] **Step 4: 진짜 Chromium(동작을 잰다)** — `playback-smoothness.spec.mjs`에 시험 `L을 눌러 4배까지 올리면 실제로 4배로 흐르고, 끝에 닿아도 4배를 지킨다`(`// covers: faster`): 저장소 지우고 시작 → 재생 → `l` 네 번(1.5·2·3·4) → `video.playbackRate === 4` → `measurePlayback(…, seconds: 5)` 3회(시작 0·8·16초) → `effectiveRate` 중앙값 3.8~4.2, `appSeeksWhilePlaying` 0, `rvfcFps` 중앙값 ≥ 25 → 28초로 옮겨 끝까지 재생(`ended`) → `playbackRate` 여전히 4, 고르기 `"4"`. 기존 0.5·2배 시험의 "L 두 번 → 2" 기대는 그대로 맞는지(1 → 1.5 → 2) 확인. `zoom-and-rate-baseline.spec.mjs`의 빠르기 측정에 문턱 추가: 1배 `effectiveRate` ≥ 0.95.
- [ ] **Step 5: 넓은 검증 + 검증 넷 + 커밋** — vitest `src/features/editor/preview`, `user-copy-policy`, `task22-parity-owners`, tsc, 빌드. 배선: `grep -rn "markRateHintSeen\|readRateHintSeen\|maxPlaybackRate" apps/web/src --include=*.tsx` → preview-stage만. 갭: 소리(headless에서 못 쟀으면 적는다), 대표님 체감.
```bash
git add apps/web/src/features/editor/preview apps/web/src/styles/editor-workbench.css apps/web/e2e-real/playback-smoothness.spec.mjs apps/web/e2e-real/zoom-and-rate-baseline.spec.mjs
git commit -m "feat(editor): 재생 빠르기를 3배·4배까지 -- L 키로 1->1.5->2->3->4, 처음엔 'L 키' 안내

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2 (B): 타임라인이 한 화면에 더 많은 초를 — 처음 배율·줄이기 바닥·눈금 — 약 4.5시간

**규칙(바뀌는 것 한 줄):** 처음 보이는 초 = `clamp(영상 길이, 20, 60)`, 줄이기 바닥 = `칸 폭 ÷ max(영상 길이, 20)`. 짧은 영상은 **20초 창**으로 열리고 뒤쪽은 빈 자리(눈금은 있다). 60초 넘는 영상은 지금과 같다. `전체 보기`(맞춤)는 **영상 전체가 칸을 채우는 배율** — 긴 영상에선 바닥과 같고, 20초보다 짧은 영상에선 바닥보다 크다(늘어난다). 20은 owner 결정 3의 추천값.

예상(1440, 칸 ≈1188px — Task 0 측정값으로 바꿔 적는다):

| 길이 | 새 처음 배율 | 보이는 초 | 눈금 큰 간격(기존 `rulerIntervals`, 글자 간격 120px) |
|---|---|---|---|
| 7.75초 | ≈59.4px/초 | 20 | 약 2~5초 |
| 30초 | ≈39.6 | 30 | 약 5초 |
| 120초 | ≈19.8 | 60 | 약 10초 |
| 600초 | ≈19.8 | 60 | 약 10초 |

**Files:**
- Modify: `apps/web/src/features/editor/timeline/timelineZoomScale.ts`(+`timelineZoomScale.test.ts`) — 앵커 `export const TIMELINE_INITIAL_VISIBLE_SECONDS = 60;`, `  return { min: Math.min(max, Math.max(ABSOLUTE_MIN_PIXELS_PER_SECOND, fit)), max };`, `  const visibleSec = Math.min(input.durationSec, TIMELINE_INITIAL_VISIBLE_SECONDS);`
- Modify: `apps/web/src/features/editor/timeline/TimelineDock.tsx`(+`timeline-dock.test.tsx`) — 앵커 `  const fitTarget = fitPixelsPerSecond({ durationSec: view.output.durationSec, viewportWidthPx: trackWidthPx }) === null`, `      enabled: fitTarget !== null,`, `    const range = { startSec: state.viewportStartSec, endSec: viewportEndSec };`, `    const endAligned = new Set(majors.filter((seconds) => rulerLabelAlignsEnd({ seconds, viewportEndSec, pixelsPerSecond: state.pixelsPerSecond, labelRoomPx: rulerLabelRoomPx })));`
- Modify: `apps/web/e2e-real/zoom-and-rate-baseline.spec.mjs`, 필요하면 기하에 기대는 e2e(아래 Step 6)

**Interfaces:**
```ts
export const TIMELINE_MIN_VISIBLE_SECONDS = 20;            // 새
export const TIMELINE_INITIAL_VISIBLE_SECONDS = 60;        // 그대로
export function pixelsPerSecondBounds(input): TimelineZoomBounds;   // min = width / max(duration, 20), max 그대로 400
export function initialPixelsPerSecond(input): number;            // width / clamp(duration, 20, 60), bounds 안
export function fitPixelsPerSecond(input): number | null;         // 그대로(영상 전체 = 칸)
```
TimelineDock 안: `fitTarget`은 `fitPixelsPerSecond(…)`를 `[zoomBounds.min, zoomBounds.max]`로 접은 값(지금은 `zoomBounds.min`). `fit.enabled`는 지금처럼 `fitTarget !== null`만(이미 맞춤이어도 누르면 0초로 스크롤하는 동작을 바꾸지 않는다). 눈금만 `visibleEndSec = pixelsToTime(trackWidthPx, { pixelsPerSecond, originSec: viewportStartSec })`(길이로 자르지 않음)까지 그린다. 클립 투영·따라가기·`resolveViewportEnd`는 **그대로**(길이로 자른다).

- [ ] **Step 1: 배율 규칙(RED→GREEN)** — `timelineZoomScale.test.ts`에 새 시험 `짧은 영상도 적어도 20초 창으로 연다 -- 1초가 화면 절반을 쓰지 않게(2026-10-09 대표님)`: `initialPixelsPerSecond({ durationSec: 7.75, viewportWidthPx: 1200 })` ≈ 60, `durationSec: 15` → 60, `30` → 40, `494.837` → 20(그대로); `pixelsPerSecondBounds({ durationSec: 7.75, viewportWidthPx: 1200 }).min` ≈ 60, `494.837` → 1200/494.837(그대로); `TIMELINE_MIN_VISIBLE_SECONDS === 20`. RED 확인 → 구현 → GREEN. **의도적으로 바뀌는 옛 기대**(이것만 고친다, 줄마다 이유 주석): 이름 `"긴 영상과 짧은 영상에 같은 규칙을 쓴다 -- 한 화면에 60초, 영상이 더 짧으면 영상 전체"`의 `durationSec: 15` → 80 기대, `"줄이기는 영상 전체가 …"`의 `short.min` 80 기대, `"아주 짧은 영상은 한계를 넘지 않는다"`의 `durationSec: 1`이 400이던 기대(이제 60), `"길이가 틀리게 와도 …"`의 `toBeCloseTo(240, 9)`(입력을 보고 새 값 계산 — 이 시험의 요지 "유한하고 양수"는 그대로). 이 넷 밖의 기대가 바뀌면 **멈추고 보고**.
- [ ] **Step 2: 맞춤·한계 잠김(RED→GREEN)** — `timeline-dock.test.tsx`: 길이 7.75·칸 1200으로 렌더 → `data-pixels-per-second` ≈ `"60"`(파일의 `formatSeconds` 반올림을 따른다), `타임라인 축소` 잠김(바닥), `타임라인 전체 보기` 누르면 ≈ `"154.84"`이고 `data-viewport-start-seconds` `"0"`, 다시 `축소`가 열린다. 긴 영상(120초)에선 `전체 보기` = 바닥(지금과 같음). 기존 배율 시험(`"125"`·`"100"`·`"2.5"` 기대 줄)이 바뀌면 그 시험의 길이·폭이 20초 아래인지 보고 이유를 적어 고친다 — 20초 이상이면 바뀌면 안 된다(멈추고 보고).
- [ ] **Step 3: 눈금이 영상 끝 뒤까지(RED→GREEN)** — 시험: 길이 7.75·20초 창 → `aria-label="눈금 10초"`가 있다(지금은 길이에서 끊긴다). 구현: 앵커의 `range` 끝과 `rulerLabelAlignsEnd`의 `viewportEndSec`을 `visibleEndSec`로. **H 회귀**: 120초를 `전체 보기`로 보면 마지막 큰 눈금이 `2:00`이고 끝에 붙는다(`ruler-scale.spec.mjs` 기대) — 보이는 끝 = 길이라 그대로여야 한다.
- [ ] **Step 4: Review Focus 3(RED→GREEN)** — 시험 둘: (가) 20초 창에서 15초 자리(빈 자리)를 누르면 재생 위치 = 7.75(길이로 접힘), 편집기 안 죽음; (나) `projectVisibleTimelineClips`에 보이는 끝이 길이보다 큰 창을 줘도 모든 사각형 `width`·`x`가 유한(`timelineNavigation.test.ts`). 둘 다 처음부터 통과할 수 있다 — 그러면 "회귀 지킴"으로 적고 넘어간다.
- [ ] **Step 5: H 처음 배율 다시 맞추기 회귀** — `cd apps/web && npx vitest run src/features/editor/timeline` 전부. 특히 `lastFittedRef`(폭·길이가 늦게 와도 다시 맞춤) 시험 이름을 출력에서 찾아 통과 확인. 줌 기준점: 단추·키는 재생 머리, 바퀴는 손가락 자리 — 기존 시험이 통과하는지(코드 안 바꿈). 붙기 문턱은 px(`SNAP_THRESHOLD_PX = 8`) 그대로 — 20px/초에서 0.4초라는 것을 보고에 적는다.
- [ ] **Step 6: e2e 기하 확인** — real-flow 전부(`npm run test:e2e:real-flow`)와 가짜 API e2e(`npm run test:e2e`, 단독). `clean` 고정 프로젝트(3.75초)는 처음 배율이 ≈317 → ≈59px/초로 바뀐다 — 끌기 거리를 px로 재는 `edge-trim`·`snap-drag`·`track-headers`·`dead-control-sweep`, 가짜 쪽 `e2e/editor-workbench.spec.mjs`·`e2e/release-gates.spec.mjs`가 깨질 수 있다. 깨지면 **제품을 되돌리지 말고** 그 스펙의 열기 직후에 `await page.getByRole("button", { name: "타임라인 전체 보기" }).click();`(옛 배율과 같은 자리)를 넣고 주석 `// P2(2026-10-09): 짧은 프로젝트의 처음 창이 20초가 됐다. 이 시험은 옛 배율(영상 전체)의 기하를 쓴다.`. 스냅샷 PNG가 바뀌면 차이를 기록하고 되돌린다(`git checkout -- apps/web/e2e/snapshots/*.png`) → owner 결정 7.
- [ ] **Step 7: 문턱 + 검증 넷 + 커밋** — `zoom-and-rate-baseline.spec.mjs`에 문턱: 7.75초·1440에서 보이는 초 ≥ 19.5, `타임라인 축소` 잠김, 120초·600초에서 배율이 Task 0 값 ±1%. 배선: `grep -n "TIMELINE_MIN_VISIBLE_SECONDS\|visibleEndSec" apps/web/src -r` → 배율 모듈 + TimelineDock 눈금 두 자리. 갭: 줌 저장 안 함(owner 결정 5), 슬라이더 없음(결정 6).
```bash
git add apps/web/src/features/editor/timeline apps/web/e2e-real apps/web/e2e
git commit -m "feat(timeline): 짧은 영상도 적어도 20초 창으로 열고 더 줄일 수 있다 -- 1초가 화면 절반을 쓰지 않게

처음 보이는 초는 영상 길이를 20~60초로 접은 값, 줄이기 바닥은 max(길이, 20초).
전체 보기는 영상 전체가 칸을 채우는 배율. 눈금은 영상 끝 뒤 빈 자리까지 그린다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3 (C1): 단축키 표 하나·문지기 하나 — 지금 키를 옮기기만(동작 그대로) — 약 3.5시간

**Files:**
- Create: `apps/web/src/features/editor/editorShortcuts.ts`, `editorShortcuts.test.ts`
- Modify: `apps/web/src/features/editor/preview/playbackShortcuts.ts` — 앵커 `export function playbackShortcutFor(event: PlaybackKeyEvent): PlaybackCommand | null {`, `export function isTypingTarget(target: EventTarget | null): boolean {`
- Modify: `apps/web/src/features/editor/workbench/cutShortcuts.ts` — 앵커 `export function cutShortcutFor(event: Chord, tools: CutToolbarState): InspectorAction | null {`
- Modify: `apps/web/src/features/editor/timeline/timelineZoomShortcuts.ts` — 앵커 `export function timelineZoomShortcutFor(event: Chord, targetIsEditable: boolean): TimelineZoomCommand | null {`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbench.tsx` — 앵커 `      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;`, `      const cutAction = cutShortcutFor(event, cutToolsRef.current);`, `      if (key !== "z" && key !== "y") return;`

**Interfaces:**
```ts
// editorShortcuts.ts
export type EditorShortcutId =
  | "toggle-play" | "pause" | "faster" | "slower" | "frame-back" | "frame-forward"
  | "prev-cut" | "next-cut" | "go-start" | "go-end"
  | "split" | "delete" | "trim-left" | "trim-right" | "undo" | "redo"
  | "zoom-in" | "zoom-out" | "zoom-fit";
export type EditorKeyEvent = Readonly<{ key: string; ctrlKey: boolean; metaKey: boolean; altKey: boolean; shiftKey: boolean; repeat: boolean; isComposing: boolean; defaultPrevented: boolean; target: EventTarget | null }>;
export type ShortcutOwner = "preview" | "workbench" | "timeline";   // 누가 실행하나
export type CapcutParity = "same" | "differs";
export type EditorShortcut = Readonly<{
  id: EditorShortcutId; owner: ShortcutOwner; group: "재생" | "이동" | "자르기" | "되돌리기" | "타임라인 보기";
  keys: string;            // 화면 글: "Ctrl + B", "Q 키", "↑ ↓" …
  label: string;           // 화면 글: "재생 위치 왼쪽 잘라 내기" …
  capcut: CapcutParity; note?: string;   // differs·빈자리 안내
  samples: readonly Readonly<Partial<EditorKeyEvent> & { key: string }>[];   // 이 줄을 부르는 키(시험이 전부 밟는다)
}>;
export const EDITOR_SHORTCUTS: readonly EditorShortcut[];
export function editorShortcutFor(event: EditorKeyEvent): EditorShortcutId | null;
export function isTypingTarget(target: EventTarget | null): boolean;      // playbackShortcuts.ts에서 옮김(거기선 다시 내보냄)
export function isSwallowedRepeat(event: EditorKeyEvent): boolean;        // 옮김
```
`PlaybackKeyEvent`는 `EditorKeyEvent`의 별칭으로 남긴다. `playbackShortcutFor`·`cutShortcutFor`·`timelineZoomShortcutFor`는 **이름·시그니처 그대로** `editorShortcutFor` 위의 포장이 된다(`cutShortcutFor`·`timelineZoomShortcutFor`는 받은 `Chord`에 `target: null, repeat: false, isComposing: false, defaultPrevented: false`를 채워 부른다; `timelineZoomShortcutFor`는 `targetIsEditable`이 참이면 먼저 null).

**문지기 규칙(위에서부터 먼저 걸리는 것이 이긴다).** P의 규칙 1~7을 그대로 품고 넓힌다:
1. `isComposing`·`defaultPrevented`·`altKey` → null.
2. 글을 쓰는 자리(`isTypingTarget`) → null(조합 키 포함 — 지금 되돌리기·줌 규칙과 같다).
3. `ctrlKey||metaKey`(조합): 글자는 `key.toLowerCase()`. `z`+Shift 또는 `y` → redo, `z` → undo, `b` → split(**Shift 무시 — 지금 그대로**), `=`·`+` → zoom-in, `-`·`_` → zoom-out, `0` → zoom-fit, 그 밖 → null. `repeat`는 split만 null(줌·되돌리기는 꾹 누르면 반복 — 지금 그대로). `aria-modal` 안이어도 받는다(지금 그대로).
4. 조합 아님: `repeat` → null. `[aria-modal='true']` 안 → null.
5. `Delete`·`Backspace` → delete. (지금은 서랍 안에서도 지웠다 — 규칙 4 때문에 이제 안 지운다. **의도된 변경**, Review Focus 1.)
6. 화살표 `←`·`→`: Shift면 null; 타임라인 면 안 또는 스스로 화살표를 쓰는 조작(P의 `SELF_ARROWS`) 위면 null; 아니면 frame-back/forward.
7. `Space`: P 규칙 5~7 그대로(타임라인 면 안 → toggle, 스스로 스페이스를 쓰는 조작 위 → null, 나머지 toggle).
8. `j`·`k`·`l`(Shift 무시): slower/pause/faster. **(Task 4에서 Q·W·↑·↓·Home·End·Shift+Z가 이 자리에 더해진다.)**

이 Task의 표에는 **지금 있는 키만** 넣는다(`toggle-play`·`pause`·`faster`·`slower`·`frame-back`·`frame-forward`·`split`·`delete`·`undo`·`redo`·`zoom-in`·`zoom-out`·`zoom-fit`). Q·W 등은 Task 4.

- [ ] **Step 1: 표·문지기(RED→GREEN)** — `editorShortcuts.test.ts`:
  - `it.each(EDITOR_SHORTCUTS.flatMap((row) => row.samples.map((sample) => [row.id, sample])))("%s 키가 그 줄을 부른다", …)` — 본문(`document.body`) 대상, 기본값 false로 채운 사건 → `editorShortcutFor(...) === id`.
  - 규칙 표 `it.each`: 글칸(`input`·`textarea`)에서 `delete`·`b`+Ctrl·`z`+Ctrl·`l` → null; `[aria-modal='true'] div`에서 `Delete` → null, `z`+Ctrl → undo; `repeat:true`에서 `Delete`·`b`+Ctrl → null, `=`+Ctrl → zoom-in, `z`+Ctrl → undo; `altKey` → null; `isComposing` → null; `b`+Ctrl+Shift → split(지금 그대로); 캡컷에 있지만 짝이 없는 키 `m`·`n`·`p`·`v`·`a`·`[`·`]`·`c`+Ctrl·`v`+Ctrl·`d`+Ctrl·`r`+Ctrl·`g`+Ctrl·`k`+Alt → null(`2026-08-30` 규칙을 시험이 지킨다).
  - 표 모양: `id` 겹침 없음, 모든 `EditorShortcutId`가 정확히 한 줄, `owner`가 셋 중 하나.
  - **문구 금지어**(`user-copy-policy`가 `.ts`를 못 읽어서): 모든 `keys`·`label`·`note`에 `revision`·`provider`·`runtime`·`job`·`pipeline`·`model`·`fallback`이 없다(대소문자 무시), 그리고 한글 아닌 낱말은 키 이름 목록 `["Ctrl","Shift","Delete","Backspace","Home","End","Q","W","J","K","L","Z","B","Y","0"]`에만 있다.
  RED(모듈 없음) → 구현 → GREEN.
- [ ] **Step 2: 옛 포장 셋을 표 위로(동작 그대로)** — `playbackShortcutFor`: `editorShortcutFor` 결과 중 owner `preview`인 id를 `PlaybackCommand`로(`toggle-play`→toggle, `pause`, `faster`, `slower`, `frame-back`→step −1, `frame-forward`→step +1), 나머지 null. `isTypingTarget`·`isSwallowedRepeat`는 다시 내보내기. `cutShortcutFor`: id `split`이면 `tools.split.enabled ? tools.split.action : null`, `delete`면 drop 같은 식. `timelineZoomShortcutFor`: id `zoom-*` → `"in"|"out"|"fit"`. Run: `cd apps/web && npx vitest run src/features/editor/preview/playbackShortcuts.test.ts src/features/editor/workbench/cut-shortcuts.test.tsx src/features/editor/timeline/timelineZoomShortcuts.test.ts` → **전부 그대로 통과**. 기대를 바꿔야 하는 시험이 나오면 멈추고 보고(규칙 5의 서랍 Delete만 예외 — 그 시험이 있으면 이유를 적고 고친다).
- [ ] **Step 3: 작업판 키 처리기를 문지기 하나로** — `EditorWorkbench.tsx`의 처리기 몸통: 글칸 판정 세 줄(`isContentEditable`·`tag ===`)과 `key !== "z" && key !== "y"` 분기를 지우고 `const id = editorShortcutFor(event);` → `split`/`delete`는 `cutShortcutFor` 대신 `cutToolsRef.current`의 `split`/`drop`(enabled일 때 action)로, `undo`/`redo`는 지금 조건(`isSavingTimeline`·`onUndo`·`session?.undoCount` …) 그대로. 시험: `cut-shortcuts.test.tsx`·`editor-workbench.test.tsx` 전부(알려진 1건 외) 통과 — Ctrl+B·Delete·Ctrl+Z·Ctrl+Shift+Z·Ctrl+Y 시험 이름을 출력에서 찾는다.
- [ ] **Step 4: 넓은 검증 + 검증 넷 + 커밋** — vitest `src/features/editor` 전부, tsc, 빌드, `npm run test:e2e`(단독, 48/49), real-flow `playback-smoothness`·`remove-scene`·`react-185-repro`·`edge-trim`. 배선: `grep -rn "editorShortcutFor" apps/web/src --include=*.ts --include=*.tsx | grep -v test` → editorShortcuts(정의), playbackShortcuts·cutShortcuts·timelineZoomShortcuts(포장), EditorWorkbench(1). `grep -rn "tag === \"INPUT\"" apps/web/src/features/editor` → 0(판정이 한 곳). 갭: 새 키 없음(Task 4).
```bash
git add apps/web/src/features/editor
git commit -m "refactor(editor): 단축키를 표 하나와 문지기 하나로 모은다 -- 키 동작은 그대로

재생(미리보기)·자르기/되돌리기(작업판)·줌(타임라인)이 따로 판정하던 것을
editorShortcuts 한 곳으로. 서랍 안에서 Delete가 장면을 지우던 것만 막는다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4 (C2): 캡컷 키 더하기 — Q·W·↑·↓·Home·End·Shift+Z — 약 4.5시간

**Files:**
- Modify: `apps/web/src/features/editor/editorShortcuts.ts`(+시험) — 표에 일곱 키
- Modify: `apps/web/src/features/editor/timeline/timelineNavigation.ts`(+시험) — 끝(`export function projectVisibleTimelineClips(` 앞)에 새 함수
- Modify: `apps/web/src/features/editor/timeline/TimelineDock.tsx`(+`timeline-dock.test.tsx`) — 앵커 `      const command = timelineZoomShortcutFor(event, isEditableTarget(event.target));`, `  const keyboardTrim = (event: KeyboardEvent<HTMLButtonElement>, clip: NarrationSegment, edge: "start" | "end") => {`, `title="영상 전체가 한 화면에 들어오게 (Ctrl과 0 키)"`
- Modify: `apps/web/src/styles/editor-workbench.css`(안내 한 줄)
- Modify: `apps/web/e2e-real/capcut-shortcuts.spec.mjs`

**Interfaces:**
```ts
// timelineNavigation.ts
/** 재생 위치 바로 앞/뒤의 자른 자리. 반 프레임 안은 "지금 자리"로 보고 건너뛴다. 없으면 null. */
export function adjacentCutPoint(times: readonly number[], playheadSec: number, direction: -1 | 1, fps: RationalFps): number | null;
```
표에 더하는 줄(문지기 규칙 8 자리에, 조합 아님·`repeat` 아님·`aria-modal` 밖·글칸 밖):

| id | owner | keys(화면) | label(화면) | capcut | samples | 비키는 자리 |
|---|---|---|---|---|---|---|
| trim-left | timeline | `Q 키` | 재생 위치 왼쪽 잘라 내기 | same, note `빈자리는 그대로 둬요` | `q`, `Q`(Shift 없을 때만) | — |
| trim-right | timeline | `W 키` | 재생 위치 오른쪽 잘라 내기 | same, 같은 note | `w` | — |
| prev-cut / next-cut | timeline | `↑ ↓` | 앞/뒤 자른 자리로 | same | `ArrowUp`/`ArrowDown` | Shift, `SELF_ARROWS`(높이 손잡이 `role="separator"` 포함) |
| go-start / go-end | timeline | `Home 키` / `End 키` | 처음/끝으로 | same | `Home`/`End` | 타임라인 면 안(거기선 `navigationKeyAction`이 이미 받는다), `SELF_ARROWS` |
| zoom-fit | timeline | `Shift + Z` (또는 `Ctrl + 0`) | 영상 전체 보기 | same | 기존 `0`+Ctrl에 `Z`+Shift 추가 | — |

Q·W 대상(정확히): 타임라인에서 고른 배치가 **하나**(`selectedPlacementIds.length === 1`)면 그 배치(`derivePlacementTrim` → `updatePlacement`), 아니면 `selectedSegmentId`의 내레이션 클립(`narration`에서 찾음, `deriveNarrationTrim` → `onTrimNarration`). 재생 위치 `p`가 대상의 `start + 반 프레임 < p < end − 반 프레임`일 때만. 잠긴 트랙(`lockedLanes`)·`isSaving`이면 하지 않는다. 아무것도 못 하면 타임라인 머리에 `role="status"` 한 줄(4초 뒤 사라짐): 고른 것 없음 `장면을 먼저 골라 주세요.`, 재생 위치가 밖 `재생 위치를 고른 장면 안으로 옮겨 주세요.`, 잠김 `잠긴 트랙이에요.`. ↑·↓의 자른 자리: `sourceSnapCandidates(view)`의 `timeSec` + 0 + 길이, 정렬·중복 제거 → `adjacentCutPoint` → `dispatch({ type: "seek", seconds })`(따라가기 효과가 화면을 넘긴다).

- [ ] **Step 1: 자른 자리 함수(RED→GREEN)** — `timelineNavigation.test.ts`: 자리 `[0, 7.5, 15, 22.5, 30]`, 30fps — `(…, 8, 1)` → 15, `(…, 8, -1)` → 7.5, `(…, 7.5, 1)` → 15(지금 자리 건너뜀), `(…, 7.51, -1)` → 0(7.5와 0.01초 차이는 반 프레임 0.0167초 안이라 "지금 자리"로 보고 건너뛴다), `(…, 30, 1)` → null, `(…, 0, -1)` → null, 빈 배열 → null.
- [ ] **Step 2: 표 줄(RED→GREEN)** — `editorShortcuts.test.ts`의 표 `it.each`가 새 줄을 자동으로 밟는다(RED: id 없음). 규칙 시험 추가: `ArrowUp`이 `[role='separator']` 위 → null, 타임라인 면 안 → prev-cut; `Home`이 타임라인 면 안 → null, 본문 → go-start; `q`가 `textarea` 안 → null(Review Focus 1), `[aria-modal='true']` 안 → null, `repeat` → null; `Z`+Shift → zoom-fit, `z`(맨) → null; `Q`+Shift → null.
- [ ] **Step 3: 타임라인이 실행한다(RED→GREEN)** — `timeline-dock.test.tsx`(그 파일의 기존 준비 — 내레이션 장면 둘 이상인 view — 를 따른다):
  - 장면 하나 고르고(`selectedSegmentId`) 재생 위치를 그 장면 가운데로(`playbackSec`) → `fireEvent.keyDown(window, { key: "q" })` → `onTrimNarration`이 `{ segmentId, startSec: 재생 위치(프레임 반올림), endSec: 원래 끝 }` 1회. `w` → 끝이 재생 위치.
  - **Review Focus 2:** 재생 위치가 장면 시작에서 반 프레임 안 → `onTrimNarration` 안 불림, `getByRole("status")`에 `재생 위치를 고른 장면 안으로 옮겨 주세요.`; 고른 것 없음 → `장면을 먼저 골라 주세요.`; 내레이션 잠금 → 안 불림.
  - 배치 하나 고름(클릭 — 파일의 배치 고르기 준비) → `q` → `onUpdatePlacements` `{ changes: [{ placementId, kind, startSec: 재생 위치, endSec }] }`.
  - `ArrowDown` → `data-` 재생 위치 출력(`<output aria-label="재생 위치">`)이 다음 경계, `End`(본문에서) → 길이, `Home` → 0. `Shift+Z` → `data-pixels-per-second`가 맞춤 값.
  구현: `TimelineDock`의 창 키 처리기(앵커의 `timelineZoomShortcutFor` 줄)를 `const id = editorShortcutFor(event); if (!id || ownerOf(id) !== "timeline") return;`로 바꾸고 `runShortcutRef.current(id)`(`runZoomRef`와 같은 ref 패턴 — 최신 상태·`lockedLanes`·`selectedSegmentId`를 본다). 기존 `runZoomRef`·바퀴·유진 `zoomCommand`는 그대로. `keyboardTrim` 옆에 `trimSelectedToPlayhead(edge: "start" | "end"): void`.
  `전체` 단추 `title`을 `영상 전체가 한 화면에 들어오게 (Shift와 Z 키, Ctrl과 0 키)`로.
- [ ] **Step 4: 진짜 Chromium(GREEN + 나머지 키)** — Task 0의 Q 시험이 통과. `capcut-shortcuts.spec.mjs`에 같은 모양(서버 상태 + 되돌리기)으로, 각 시험 머리에 `// covers: <id>`:
  - `trim-right`: W → `end_sec` ≈ 재생 위치, Ctrl+Z → 원래.
  - `split`·`undo`·`redo`: 장면 2 고르고 →×30 → `Control+b` → 서버 장면 5개(`scene-2`가 7.5~8.5와 8.5~15로) → `Control+z` → 4개 → `Control+Shift+z` → 5개 → `Control+z` → `Control+y` → 5개 → `Control+z` → 4개.
  - `delete`: 장면 3 고르고 `Delete` → `cut_action === "remove"`, 뒤 장면 제자리(`leave_gap`) → `Control+z` → `keep`.
  - `prev-cut`·`next-cut`·`go-start`·`go-end`: 본문 클릭 후 `End` → 재생 위치 출력 `30`, `ArrowUp` → `22.5`, `ArrowUp` → `15`, `ArrowDown` → `22.5`, `Home` → `0`(서버는 안 바뀜을 확인 — 세션 `revision` 그대로).
  - `zoom-in`·`zoom-out`·`zoom-fit`: `Control+=` → 배율 ×1.25, `Control+-` → 되돌아옴, `Shift+Z` → 맞춤(칸 폭 ÷ 30), `Control+0` → 같은 값.
  - **Review Focus 1(실물):** 장면 2를 고르고 재생 위치를 그 안에 둔 채, 유진 입력칸(`#vb-eugene-request` — 글을 쳐도 저장하지 않는 칸. 캡션 글칸은 바꾸면 저장하므로 쓰지 않는다. 안 보이면 오른쪽 도크에서 유진 칸을 연다 — 여는 단추 이름은 `editor-workbench.test.tsx`에서 확인)에 초점 → `q`·`w`·`Delete` → 서버 세션 `revision`·장면 경계·`cut_action` 그대로, 입력칸에 `qw`가 들어 있다.
  재생 키(`toggle-play`·`pause`·`slower`·`frame-back`·`frame-forward`)는 `playback-smoothness.spec.mjs`에 `// covers:` 주석을 단다(이미 밟는다).
- [ ] **Step 5: 덮개 시험** — `editorShortcuts.test.ts`에 `모든 단축키 줄이 진짜 Chromium 시험을 가진다`: `node:fs`로 `e2e-real/capcut-shortcuts.spec.mjs`·`e2e-real/playback-smoothness.spec.mjs`를 읽어 `// covers: ([a-z-]+)`를 모은 집합 ⊇ 모든 `EDITOR_SHORTCUTS[].id`. (경로는 `import.meta.dirname` 기준 `../../../e2e-real/`.)
- [ ] **Step 6: 넓은 검증 + 검증 넷 + 커밋** — vitest `src/features/editor`, `user-copy-policy`, tsc, 빌드, `npm run test:e2e`(단독), real-flow 전부. 배선: `grep -rn "trimSelectedToPlayhead\|adjacentCutPoint" apps/web/src --include=*.tsx` → TimelineDock(정의·호출). 동작: e2e 서버 값. 갭: Q·W·Delete가 빈자리를 남긴다(캡컷 자석과 다름 — 결정 대기), `Shift+←/→`·마커 등은 안 만듦.
```bash
git add apps/web/src/features/editor apps/web/src/styles/editor-workbench.css apps/web/e2e-real/capcut-shortcuts.spec.mjs apps/web/e2e-real/playback-smoothness.spec.mjs
git commit -m "feat(editor): 캡컷처럼 Q·W로 재생 위치 왼쪽·오른쪽 잘라 내기, 위아래 화살표로 자른 자리 이동, Home·End, Shift+Z 맞춤

이미 있는 자르기·이동·줌 명령에 키만 붙인다. 고른 장면(또는 고른 배치 하나)만
자르고, 재생 위치가 밖이면 이유를 한 줄로 알린다. 빈자리는 그대로 둔다(빼기 정책 그대로).

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5 (C3): `단축키` 안내를 표에서 만든다 + `캡컷과 같아요` — 약 2시간

**Files:**
- Modify: `apps/web/src/features/editor/preview/preview-stage.tsx`(+`preview-stage.test.tsx`) — 앵커 `{shortcutsOpen && <div ref={shortcutsNoteRef} id="vb-playback-shortcuts" role="note" aria-label="재생 단축키" className="vb-preview-stage__shortcuts">`
- Modify: `apps/web/src/styles/editor-workbench.css` — 앵커 `.vb-preview-stage__shortcuts`

**Interfaces:** 안내 글은 `EDITOR_SHORTCUTS`를 `group` 순(`재생`·`이동`·`자르기`·`되돌리기`·`타임라인 보기`)으로 묶어 그린다. 줄: `{keys} — {label}` + 꼬리표 `캡컷과 같아요`(capcut `same`) 또는 `캡컷과 달라요`(differs, `note` 함께). 맨 아래 한 줄: `빠르기는 보는 속도예요. 영상은 바뀌지 않아요.`(그대로) + `빈자리는 그대로 둬요. 되돌리기로 원래대로 돌아와요.`. `aria-label`을 `재생 단축키` → `편집 단축키`로(내용이 넓어졌다 — 의도된 변경). 높이가 커지므로 `.vb-preview-stage__shortcuts`에 `max-height: min(60vh, 28rem); overflow-y: auto;`.

- [ ] **Step 1: RED→GREEN** — 시험: `단축키` 단추 → `getByRole("note", { name: "편집 단축키" })` 안에 `EDITOR_SHORTCUTS`의 모든 `keys` 글자가 있다(표에서 읽어 반복 — 손으로 적은 목록과 표가 갈라지면 잡는다), `Q 키` 줄에 `캡컷과 같아요`, `J 키` 줄에 `캡컷과 달라요`, `Escape`로 닫힘(기존 시험 `const note = () => screen.queryByRole("note", { name: "재생 단축키" });`는 이름을 바꿔 그대로 돈다). 하드코딩 `<li>` 다섯 줄을 지운다.
- [ ] **Step 2: 문구 정책** — `user-copy-policy`, `editorShortcuts.test.ts` 금지어 시험 통과.
- [ ] **Step 3: 화면 확인** — Task 6 실기에서 1440×900·1280×720·375×812로 안내를 열어 스크린샷, 가로 넘침 0(`scrollWidth === clientWidth`), 375에서 안내가 화면 안.
- [ ] **Step 4: 검증 넷 + 커밋** — 배선: `grep -rn "EDITOR_SHORTCUTS" apps/web/src --include=*.tsx | grep -v test` → preview-stage 1. 갭: 캡컷 앱 안 목록과 대조는 owner 결정 4.
```bash
git add apps/web/src/features/editor/preview apps/web/src/styles/editor-workbench.css
git commit -m "feat(editor): 단축키 안내를 단축키 표 하나에서 그리고 캡컷과 같은 키를 표시한다

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 마지막 실기 검증·인계·푸시 — 약 3시간

- [ ] **Step 1: 넓은 검증(한 번씩, 각각 단독)** — `cd apps/web && npx vitest run`(알려진 1건 외), `npx tsc --noEmit` 0, `npm --prefix apps/web run build`. 가짜 API e2e `npm run test:e2e` **단독** → 48/49 통과(PNG 차이는 기록 후 되돌림 → 결정 7). real-flow `npm run test:e2e:real-flow` **단독** 전부. 백엔드는 Task 0의 `tests/test_e2e_editor_fixture.py`만(제품 백엔드를 안 바꿨으니 전체 pytest는 생략 — 생략 사실을 인계에 적는다).
- [ ] **Step 2: 컨테이너 재빌드** — PowerShell `.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild`. 실패하면 멈춘다.
- [ ] **Step 3: 실제 화면(742·0907 읽기만, headless Chromium)** — (가) 742 1배 20초 진단 스크립트 그대로 → 1.00·되감기 0(회귀 없음), 4배 20초 → `effectiveRate` 3.8~4.2·`rvfcFps`; (나) 742·0907을 1440·1280에서 열어 배율·보이는 초·눈금 간격을 Task 0 표 옆에 적고, 0907(짧은 영상)에서 `Ctrl+-` 잠김·`Shift+Z` 맞춤·`Ctrl+=` 열 번 → 최대(400px/초) → `Shift+Z`로 돌아오기; (다) 편집 키는 **고정 프로젝트(`shortcuts`)에서만**(Task 4 e2e가 이미 밟았다 — 재빌드한 컨테이너에선 대표님 프로젝트에 편집 키를 누르지 않는다). 스크린샷(1440·1280·375, 단축키 안내 열림, 0907 처음 화면)을 `docs/superpowers/audit-evidence/2026-10-09-p2/`에.
- [ ] **Step 4: 갭 점검표** — Task 0~5 Step 대조, **안 한 것**: 대표님 실제 창 체감, 소리(headless), 캡컷 앱 안 목록 대조(결정 4), Q·W·Delete 빈자리(정책 결정), 줌 저장·슬라이더(결정 5·6), `Shift+←/→`·마커 등 만들지 않은 키. §8.3: 재사용·반영·제외와 이유·경계 보존.
- [ ] **Step 5: 인계** — `docs/handoffs/2026-10-0X-editor-p2-faster-zoom-capcut-keys.ko.md`(실제 날짜): 한 일·잰 값(전·후 표)·키 표·못 한 것·owner 결정·다음. `CLAUDE.md` §2 표 `최신 세션 인계` 줄을 이 파일로 → `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_handoff_entry_point.py`.
- [ ] **Step 6: 커밋 → 따로 푸시** — 인계·`CLAUDE.md`·증거 그림 커밋. 그 다음 **따로** `git push origin main`(강제 금지). 막히면 우회하지 말고 owner에게.

---

## owner 결정이 필요한 것 (추천 기본값과 비용)

| # | 결정 | 추천 기본값 | 다르게 고르면 |
|---|---|---|---|
| 1 | 처음 쓰는 사람의 기본 빠르기 | **1배**(컷 길이·말 빠르기 판단이 완성본과 같아야 한다). 대신 첫 화면에 `빠르게 보려면 L 키를 눌러요`, 고른 값은 기억 | 1.5배로 시작: 상수 하나. 처음 본 컷 길이가 실제보다 짧게 느껴진다 |
| 2 | 가장 빠른 빠르기 | **4배**(Task 0이 4배를 통과시킬 때) | 8배: Task 0이 8배도 통과시켜야 하고, 소리가 끊기거나 무음일 수 있다(못 잼) |
| 3 | 짧은 영상의 처음 창 | **20초**(7.75초 영상 ≈59px/초, 1초 눈금 대신 2~5초 눈금) | 30초: 더 많이 보이지만 1.5초 장면이 ≈60px로 잡기 어렵다. 지금처럼 "영상 전체": 대표님 말과 반대 |
| 4 | `교차` 등급 키(Q·W·↑·↓·Home·End·Shift+Z·Ctrl+Shift+Z·Ctrl+=/-·K·L·Delete)를 `캡컷과 같아요`로 표시 | **표시**. 대표님이 캡컷 PC 메뉴의 단축키 목록과 2분 대조해 주시면 확정 | 공식(Space·Ctrl+B·←→·Ctrl+Z)만 표시 |
| 5 | 타임라인 배율 저장 | **안 함**(처음 배율 다시 맞추기(H)와 세 번째 상태가 얽힌다) | 프로젝트별 저장: `editorUiState`에 한 칸 + 처음 맞춤과의 우선순위 규칙, 약 2시간 |
| 6 | 캡컷식 줌 슬라이더 | **이번엔 안 함**(공용 슬라이더 부품이 없다 — I 계획) | 약 3시간(부품 + 로그 눈금 + 시험) |
| 7 | 가짜 API e2e 스냅샷 그림(재생줄 안내 한 줄·처음 배율) | 차이를 보고 승인 | 승인 전까지 스냅샷 비교가 다르다고 보고된다 |
| (대기) | 빼기·Q·W를 캡컷 자석처럼 당기기(`ripple`) | 이 계획은 **안 바꿈**(`leave_gap`) | 이미 서버에 길이 있다(`DEFAULT_REMOVE_MODE`) — 별도 결정 |

## 확인하지 못한 채 남는 것 (계획 시점)

- **캡컷 공식 단축키 표**를 못 찾았다. 공식 사이트에 있는 것은 Space·Ctrl+B·화살표 한 프레임·Ctrl+Z뿐이다. 나머지는 제3자 목록의 교차 확인이다(결정 4).
- 캡컷의 **처음 타임라인 배율**·줌 단계·Q/W가 주 트랙에서 당기는지 — 공개 문서에서 확인 못 했다. 20초는 대표님 말과 실측 배율에서 고른 값이다.
- 브라우저가 몇 배부터 소리를 끄거나 프레임을 버리는지 — 기억으로는 Chromium이 0.0625~16배 밖에서 소리를 끈다고 알지만 **확인 안 함**. Task 0이 잰다(headless 무음 장치면 소리는 못 잰다).
- 대표님의 "느리다"가 재생 결함 재발인지 — 계획 시점 측정 없음. Task 0 Step 2가 742로 다시 잰다.
- 클립 칸 폭(1440·1280)과 배율 표는 계산값이다 — Task 0에서 측정값으로 바꾼다.

## 계획서 자체 점검 메모 (작성자)

- 앵커 문자열은 작성 시점(`4594fe34d`)에 `grep -F`로 존재를 확인했다: `PLAYBACK_RATES = [0.25, 0.5, 0.75, 1, 1.5, 2]`, `<li>L 키 — 재생, 누를수록 빠르게(최대 2배)</li>`, `aria-label="재생 단축키"`, `TIMELINE_INITIAL_VISIBLE_SECONDS = 60`, `Math.min(input.durationSec, TIMELINE_INITIAL_VISIBLE_SECONDS)`, `const fitTarget = fitPixelsPerSecond(`, `const range = { startSec: state.viewportStartSec, endSec: viewportEndSec };`, `timelineZoomShortcutFor(event, isEditableTarget(event.target))`, `const keyboardTrim = (`, `title="영상 전체가 한 화면에 들어오게 (Ctrl과 0 키)"`, `cutShortcutFor(event, cutToolsRef.current)`, `tag === "INPUT"`, `key !== "z" && key !== "y"`, `def _seed_playback(`, `"playback": _camel(ids["playback"])}`.
- 이름 일관성: `editorShortcutFor`·`EDITOR_SHORTCUTS`·`EditorShortcutId`·`EditorKeyEvent`·`ShortcutOwner`(Task 3·4·5), `adjacentCutPoint`·`trimSelectedToPlayhead`(Task 4), `TIMELINE_MIN_VISIBLE_SECONDS`·`visibleEndSec`(Task 2), `readRateHintSeen`·`markRateHintSeen`·`maxPlaybackRate`·`PLAYBACK_RATE_HINT_STORAGE_KEY`(Task 1), 고정 프로젝트 `shortcuts`·`SHORTCUTS_PROJECT_NAME`(Task 0), e2e `// covers: <id>`(Task 0·1·4, 덮개 시험 Task 4 Step 5).
- Task 7개(0~6), 합계 약 **24시간**(0:3.5 · 1:3 · 2:4.5 · 3:3.5 · 4:4.5 · 5:2 · 6:3).
