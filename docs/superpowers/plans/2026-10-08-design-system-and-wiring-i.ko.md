# 계획 I — 디자인 시스템 정리와 배선 점검 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 루이스 대표님이 화면을 **보고 바로 쓸 수 있게** 만든다. 글자·크기·모서리·간격·탭·메뉴를 **한 벌의 토큰**에서만 꺼내 쓰게 정리하고, 화면을 캡컷처럼 **조밀하게**(본문 12px·라벨 11px·컨트롤 24/28/32px) 줄이고, 눌러도 반응이 없는 자리·이유 없이 잠긴 자리·뒤에 기능이 없는 자리를 찾아 **고치거나 없앤다**. 끝나면 대표님이 따라 누를 수 있는 **클릭 지도**를 남긴다.

**Architecture:** 색은 그대로 둔다. `ui-system.css`의 `:root` 한 곳에 밀도·글자·컨트롤·모서리·아이콘·층·초점 토큰을 모으고, Tailwind 유틸리티(`text-sm`·`rounded-md`…)는 그 토큰의 **별칭**으로 만든다. shadcn 부품 파일(`components/ui/*.tsx`)은 SHA-256으로 고정돼 있어 **거의 건드리지 않고**, 새 `styles/primitives.css`가 `[data-slot=…]`·`[data-size=…]`·`[data-native-control]` 선택자로 규격을 입힌다. 드리프트는 정적 가드(vitest, 줄어들기만 하는 기준선)와 계산 스타일 게이트(Playwright, 픽셀 비교 아님)가 막는다. 배선은 Task 0의 인벤토리 문서가 출발점이고, 무반응 스모크(e2e)가 "눌렀는데 아무 일도 없음"을 잡는다.

**Tech Stack:** React 19 + TanStack Router + shadcn(radix-ui) + Tailwind v4(`tailwindcss/utilities`만 불러옴, Preflight 없음) + sonner, vitest + Testing Library(jsdom), Playwright(가짜 API `e2e/support/fake-api-server.mjs`), FastAPI + pytest, Docker(nginx 앞문 `http://127.0.0.1:5173`).

**Spec:**
- 대표님 요구(2026-10-08, 원문 취지): "폰트·디자인·글자 크기·컴포넌트 크기·레이아웃이 전혀 정리가 안 돼 있다. 탭·드롭다운·클릭이 쉽고 이해되게. 배선이 안 된 곳이 많다. 예전에 요청한 톤앤매너가 일관되지 않다." + "메뉴를 모르겠고 뭘 눌러야 할지 모르겠고 눌러도 반응이 없어서 **테스트 자체를 못 한다**." + "검은 배경은 좋다. 캡컷처럼 화면을 넓게 쓰려면 **글자를 줄이고 컴포넌트·카드를 줄여야** 한다."
- 측정 근거: `docs/superpowers/2026-10-08-editor-ui-audit.ko.md`(편집기 실측), 이 계획의 "실측 기준선"(2026-10-08 계획 작성 시 대시보드 화면 실측)
- 디자인 시스템 근거: `~/.claude/skills/intranet-style/reference/{README,01-tokens,02-primitives,03-shell-layout,04-page-templates}.md`(Lean-AX Intranet DS)
- 승인 기록: `docs/decisions/` 2026-07-20 · 08-17 · 08-19 · 08-21 · 08-27(모서리 셋) · 08-29(다크) · 08-30(버튼 단위 패리티) · 09-04(캡컷 척도·자산) · 09-05(시작 문 하나) · 10-02(후속 결정)

---

## 실행 위치와 순서 (반드시 먼저 읽는다)

| 순서 | 계획 | 이유 |
|---|---|---|
| 1 | **H** `docs/superpowers/plans/2026-10-08-editor-core-repair-h.ko.md` | 편집기 **동작**(클립 고르기·트랙 머리 누르기·자르기 손잡이·폴링·중복 데이터)을 먼저 고친다. I는 그 위에 **모양**만 입힌다 |
| 2 | **G** `docs/superpowers/plans/2026-10-02-audit-g-screen-improvements.ko.md` | 아직 실행 전(2026-10-08 감사 기준 G 커밋 0). 카드 그림·`+ 새로 만들기` 칸·설정 3칸·편집기 머리 접기가 **구조**를 바꾼다. I는 바뀐 구조를 조밀하게 정리한다(소유자 결정 D5) |
| 3 | **I (이 계획)** | 토큰·부품 규격·글자·간격·탭/메뉴 무늬·문구 톤·대시보드 화면·배선 |
| 4 | **B–F** `docs/superpowers/plans/2026-10-02-audit-bf-yujin-capabilities.ko.md` | 유진 기능 열기. I의 Task 0이 만든 "화면엔 있는데 유진은 못 하는 것" 목록을 넘긴다 |

**H와 I가 같이 만지는 파일**(H가 먼저, I는 줄 번호가 아니라 **문자열 앵커**로 찾는다. 앵커가 없으면 H가 바꾼 것이니 멈추고 `git log -p -- <파일>`로 새 모양을 확인한 뒤 같은 의미의 자리에 적용한다):

| 파일 | H가 맡는 것(동작) | I가 맡는 것(모양) |
|---|---|---|
| `apps/web/src/features/editor/timeline/TimelineDock.tsx` | 트랙 머리 고정 칸, 자르기 손잡이, 클릭 판정 | 트랙 단추 크기(24px)·글자(11px)·`aria-label` 문구 |
| `apps/web/src/features/editor/workbench/RightDock.tsx` | 편집 대상 중복 id·key | 대상 이름 문구 |
| `apps/web/src/features/editor/inspector/InspectorControls.tsx` | (H가 값 저장 경로를 만지면 그것) | 하위 탭 무늬(line 탭)·잠긴 이유 22곳 |
| `apps/web/src/features/editor/workbench/EditorWorkbench.tsx` | 선택 동기화·미리보기 유지 | 주황 단추 정리, 단추 크기 |
| `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx` | 폴링 겹침, 세션 응답 | (손대지 않음) |
| `apps/web/src/features/editor/preview/preview-stage.tsx` | 옛 미리보기 유지 | 재생줄 단추 규격·잠긴 이유 |
| `apps/web/src/styles/editor-workbench.css` | 트랙 머리·손잡이 배치 규칙 | 글자·높이·모서리 리터럴 → 토큰 |

G와 겹치는 것(중복 구현 금지):

| G Task | I에서의 처리 |
|---|---|
| G2 카드 그림 자리 같은 크기 | I Task 7은 G2가 만든 그림 자리 **크기만** 조밀 토큰으로 바꾼다 |
| G3 `+ 새로 만들기`를 카드 격자 첫 칸으로 | I는 다시 만들지 않는다. 그 칸의 글자·간격만 토큰으로 |
| G6 편집기 머리 접기·비교 띠 낮추기 | I는 건드리지 않는다(G가 끝낸 높이를 그대로 측정만) |
| G7 설정 5칸 → 3칸 | I Task 9는 G7 결과(3칸)를 **탭 무늬**로 바꾼다. G가 안 돌았으면 5칸 그대로 탭으로 |
| G11-3 오디오 도크 가로 넘침 | I는 건드리지 않는다 |
| G13 첫 로드 중복 요청 | I는 건드리지 않는다 |

**G를 아직 안 돌렸는데 I를 먼저 하라는 결정(D5 반대 선택)이 나오면**: I Task 7·9에서 G2·G3·G7이 바꿀 자리를 건드리지 말고(문자열 앵커가 G 이전 모양이면 그대로 둔다) 글자·간격 토큰만 적용한다. 구조 변경은 G가 한다.

---

## Global Constraints

- 최상위 지침은 `CLAUDE.md`. 메인 체크아웃 `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`(브랜치 `main`)에서 한다. 시작 전에 `git status --short`, `git log --oneline -5`, `git worktree list`, `git diff --check`.
- **색은 바꾸지 않는다**(`2026-08-29` 다크 팔레트, `CLAUDE.md` §6). `ui-system.css` `:root`의 `--vb-canvas`·`--vb-panel`·`--vb-panel-alt`·`--vb-border`·`--vb-border-strong`·`--vb-text`·`--vb-muted`·`--vb-faint`·`--vb-accent`·`--vb-accent-bg`·`--vb-accent-border`·`--vb-preview`·`--vb-success`·`--vb-success-bg`와 shadcn 색 별칭(`--background`…`--ring`)의 **값**을 고치지 않는다. 새 `#hex`·`rgb(` 를 쓰지 않는다. `apps/web/src/styles/contrast.test.ts`가 지킨다. "주황을 어디에 쓰는가"(쓰는 자리 규칙)는 색 변경이 아니지만 소유자 결정 D2로 받는다.
- 옛 결정(흰·주황 2026-08-05, 밝은 편집기 2026-08-21, 편집기만 어둡게 2026-08-20)을 **다시 열지 않는다.** 이 계획의 어떤 문구도 "색을 다시 고르자"로 읽히면 안 된다.
- **밀도는 바꾼다**: 대표님 2026-10-08 요청이 승인이다(`docs/decisions/2026-10-08-compact-density.ko.md`, Task 1). 이 승인은 2026-08-19 척도와 2026-09-04 캡컷 척도의 **값**을 대체한다. 이름(`--vb-text-xs`…`--vb-text-3xl`, `--vb-space-1..8`, `--vb-radius-sm/md/lg`)은 그대로 둔다.
- **모서리는 셋**(`2026-08-27`): `--vb-radius-sm`·`--vb-radius-md`·`--vb-radius-lg` 세 개만. 알약(999px)은 칩·배지에만. 넷째 값을 만들지 않는다.
- **없는 기능의 단추는 만들지 않는다**(`2026-08-30`). 뒤에 동작이 없는 단추는 이 계획에서 **없앤다**(Task 11).
- **시작하는 문은 `+ 새로 만들기` 하나**(`2026-09-05`). `/`는 `/projects`. 라우트를 바꾸지 않는다.
- `apps/web/src/components/ui/*.tsx`와 `apps/web/src/app/ProductShell.tsx`는 `docs/oss/editor-ui-source-map.json`(그리고 일부는 `docs/oss/shadcn-registry-lock.json`)에 **SHA-256이 박혀 있다.** 고치면 옛 해시 문자열을 두 JSON에서 모두 찾아 새 해시로 바꾸고 `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_editor_ui_source_provenance.py`를 돈다. 해시 계산: `.venv/Scripts/python.exe -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" <파일>`. 옛 해시 찾기: `grep -rn <옛해시> docs/oss`. 이 계획에서 고정 파일을 고치는 Task는 **4(dialog.tsx), 5(button.tsx), 9(ProductShell.tsx)** 셋뿐이다.
- 크기는 **`size` prop(=`data-size`)으로만** 고른다. `<Button className="h-…">`로 높이를 주지 않는다(Task 3 가드가 센다). Tailwind 유틸리티는 `@layer utilities` 안에 있고 우리 CSS는 층 밖이라 **층 밖 규칙이 이긴다** — 그래서 규격은 `primitives.css`가 정하고 className으로는 못 바꾼다. 이것이 의도다.
- 웹 시험은 `apps/web`에서: `cd apps/web && npx vitest run <파일>`, 타입 `cd apps/web && npx tsc --noEmit`, 빌드 `npm --prefix apps/web run build`, e2e `cd apps/web && npm run test:e2e -- <spec 파일 이름>`.
- 백엔드 시험은 저장소 루트에서 `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider <파일>`. 맨 `pytest` 금지. 전체 pytest는 Task 15에서 **단독으로** 한 번(`--ignore=tests/test_mcp_server.py`, 약 40~50분).
- RED/GREEN 단계에서는 **시험 하나만** 돈다. 넓은 시험은 Task 끝과 Task 15에서.
- 알려진 불안정(고치려 들지 말고 보고만): e2e `editor-workbench.spec.mjs`의 도크 끌기 성능 게이트, `apps/web/src/features/editor/workbench/editor-workbench.test.tsx`의 "gives the material dock back the same way, without needing a second click", `tests/test_owner_ready_script.py::test_smoke_timeout_kills_the_child_tree_and_returns_bounded_failure`.
- `apps/web/src/task22-parity-owners.test.ts`는 날 것 `<button>`/`<input>`(`data-native-control`)을 **파일별로 센다.** 이 계획은 날 것 컨트롤을 새로 만들지 않는다. 하나를 없애면(Task 11 W-01) 그 파일 허용 수를 1 줄인다.
- Playwright 스냅샷 PNG(`apps/web/e2e/snapshots/`)는 **다시 쓰지 않는다.** `product-shell.spec.mjs`·`editor-workbench.spec.mjs`는 추적 중인 PNG를 덮어쓰므로 e2e 뒤에 `git status --short apps/web/e2e/snapshots`를 보고 바뀐 PNG는 `git checkout -- apps/web/e2e/snapshots`로 되돌린 뒤 "스냅샷이 달라졌다"는 사실만 보고한다. `npm run test:e2e` 끝의 `unexpected PNG: product-shell-mobile-menu-open.png` exit 1은 옛 남은 파일 탓이다(G 계획 실측) — 지우지 말고 보고만.
- **화면 문구**(`docs/development-fast-path.ko.md` §10.13 + design:ux-copy): 이름표는 명사형(`분석 시작`, `파일 추가`), 안내는 짧은 해요체 한 문장(`촬영본을 하나 이상 고르면 눌러져요.`), 실패는 다음 행동(`…하지 못했어요. …해 주세요.`). 금지어: `provider`·`runtime`·`fallback`·`model`·`job`·`revision`·`pipeline`·`context`·`API`·`시스템`·`모델`·`런타임`·`파이프라인`·`리비전`·`개발`. 영어 문구(`Close`·`Clean`·`Something went wrong`) 금지. 말줄임은 `…`(U+2026). `apps/web/src/user-copy-policy.test.ts`를 UI Task 끝마다 돈다.
- 접근성 바닥(design:accessibility-review, web-design-guidelines): 누를 자리 **24×24px 이상**, 글자 **11px 이상**, 14px 이하 글자의 대비 **4.5:1 이상**(그래서 `--vb-accent`·`--vb-faint` 글자를 `--vb-accent-bg` 위에 쓰지 않는다 — 실측 4.27·4.44), 아이콘만 있는 단추는 `aria-label` + 툴팁, `outline:none`은 초점 링 대체와 함께만, `transition: all` 금지.
- 컨테이너는 `.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild`(PowerShell)로만. `docker compose`를 직접 치지 않는다. 재빌드 뒤 브라우저 `Ctrl+F5`.
- 내장 브라우저(`mcp__Claude_Browser__*`)는 **다른 세션과 같은 창을 쓸 수 있다**(계획 작성 중 실측: 내가 열지 않은 편집기로 주소가 바뀐 적이 있다). 잴 때마다 `location.pathname`을 같이 기록하고 다르면 다시 연다. 전이·애니메이션을 안 그리므로 크기는 JS로 잰다.
- Task마다 커밋한다. 메시지는 한국어, 끝줄 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. 푸시는 Task 15에서 `git push origin main` 한 줄(강제 푸시 금지, 확인 명령과 한 줄에 묶지 않는다, 권한이 막으면 우회하지 말고 보고).
- 조각마다 검증 넷(owner 상시 지시): **갭**(Step 대조, 안 한 것을 적는다) · **역방향**(실제 런타임 — Task 15에서 컨테이너+브라우저로 한 번에, 그 전엔 Vite 개발 서버) · **동작**(px·개수로 잰다) · **배선**(grep으로 화면이 실제로 부르는 자리를 센다).
- **유진에게 열 것**: 이 계획이 새 화면 기능을 열지는 않는다(모양·배선 정리). 화면에만 있고 유진은 못 하는 기능은 Task 0 인벤토리 (e)절에 **목록만** 남기고 B–F로 넘긴다. 구현하지 않는다.

## Review Focus

행복한 경로 시험이 놓치기 쉬운, 실제로 일어날 다섯. 각각 맡은 Task에 시험을 넣는다.

1. **포털로 뜨는 표면**(대화상자·드롭다운·툴팁·선택 목록)은 `.vb-product-shell` 조상이 없다. 규격을 `.vb-product-shell …`에만 걸면 그쪽만 브라우저 기본 글꼴·크기로 샌다(2026-09-04에 실제로 그랬다) → Task 4 시험 `포털 표면 규칙은 .vb-product-shell 조상을 요구하지 않는다`.
2. **긴 한국어 이름**(촬영본 `화면 녹화 중 2026-02-07 164438.mp4`, 프로젝트 `사진 브이로그 실기 0907`)이 조밀한 카드에서 줄을 넘쳐 카드 높이를 흔든다 → Task 7·8 시험 `긴 이름은 한 줄 말줄임이고 카드 높이가 같다`(`min-width:0` + `text-overflow: ellipsis`).
3. **비활성 단추**: 이유 없이 회색이면 대표님은 "고장"으로 읽는다. 잠깐 바쁜 것(`busy`)과 조건이 안 맞는 것(`선택 없음`)은 다르다 → Task 3 가드가 둘을 구분하고, Task 5 시험 `조건 때문에 잠긴 단추는 이유 문장과 연결된다`.
4. **375px 폭**: 조밀하게 줄인 뒤에도 가로 스크롤이 생기면 안 된다(`scrollWidth === clientWidth`) → Task 12 게이트가 모든 화면에서 잰다.
5. **같은 화면의 두 번째 클릭**: 무반응 스모크가 한 번 눌러 대화상자를 연 뒤 다음 단추를 누르면 대화상자 뒤를 누르게 된다 → Task 13 시험이 단추마다 `Escape` 후 상태를 확인하고, 주소가 바뀌었거나 대화상자가 남았으면 새로 연다.

---

## 실측 기준선 (2026-10-08, 계획 작성 시 1440×900, 컨테이너 운영 빌드)

| 화면 | 컨트롤 수 | 컨트롤 높이(px×개) | 컨트롤 글꼴 | 글자 크기·굵기 | 모서리 | 기타 |
|---|---|---|---|---|---|---|
| `/projects` | 44 | 32×다수 · 36 · 29(카드 제목 링크) · **80**(`+ 새로 만들기` 1120×80) | Pretendard 다수, **Arial**: `편집기로 돌아가기`·`작업 상태`·`설정`·`보관함 보기`·카드 `···` 전부 | 페이지 제목 **40px/700**, 카드 제목 **24px/700**(h2 브라우저 기본), 카드 단추 **16px/700**, 메타 12px/700 | 6·8·10·0 | 콘텐츠 **최대폭 1200px**(1440에서 240px 버림), 카드 268×195 패딩 20 모서리 16, 4열 |
| `/library` | 15+ | 필터 **40**, 상단 32·36 | 상단 4개 Arial | 본문 10px/400 **56곳**, 12/650·700, 14/650 | 10·6 | 검색 입력 글자 **10px**, 영상 카드 161×160 **3열**(결과 칸 560px), 패딩 18.4/10.4(척도 밖), 주황 글자를 주황 바탕(`--vb-accent-bg`)에 씀(대비 4.27) |
| `/footage` | 105 | 32×23, 촬영본 행 76~99 | Arial 6 | 14/650 ×82, **10/700 ×79**, 10/500 ×79 | 8·10·6·0 | 비활성 7개 이유 없음, 이름에 `derived:footage_render_job_…` 노출, `−1f`·`+1f`·`fps` |
| `/settings/appearance` | 7 | 32 | Pretendard | 제목 40/700 | 10 | 섹션이 **탭이 아니라 단추 묶음**(`role=tab` 없음), `조밀한 화면` 토글은 `.vb-home-grid`(홈·출력)만 바꿈 |
| 편집기 `/projects/2026-09-12-742e1924/editor` | 192 | 32×125 · 36×22 · 30×15 · 23×13 · 25×7 · 40×6 · 27×3 | **Arial 66** | 12 ×191 · 14 ×110 · **10 ×40** · 13.33 ×7 | 10 ×111 · **0 ×50** · 8 ×17 · 6 ×9 · 999 ×5 | 주황(기본) 단추 **38개**, 이유 없는 비활성 8개(재생줄 5 포함), 탭 목록 3개 중 왼쪽 레일 탭 이름 빈칸(감사 §4) |

정적 집계(소스, 2026-10-08):
- `apps/web/src/api.ts`의 `api` 메서드 224개 중 **화면 호출 0개 9개**(아래 인벤토리 W-02).
- 백엔드 라우트 중 프런트 경로 조각이 안 보이는 것 **30개**(휴리스틱, W-03).
- `<Button>`/`<button>` 중 조건 때문에 `disabled`인데 `title`·`aria-describedby`가 없는 자리 **138개 / 33파일**(잠깐 바쁜 상태 제외, W-04).
- 손잡이 없는 날 것 단추 **1개**(`features/footage/SceneTimeline.tsx`의 `data-native-control="footage-playhead"`, W-01).
- `sonner` `Toaster`는 부품만 있고 **어디에도 걸려 있지 않다**(W-09). 결과 알림이 화면마다 다르다.
- CSS `font-weight` 값 650 ×9, 750 ×1, 700 ×12(척도 밖). 픽셀 높이 40px ×8, 36px ×3(새 컨트롤 척도 밖).

## 디자인 시스템 대조 — 받아들임·고쳐 받아들임·안 받아들임

Intranet DS는 **밝은 기업 테마**(채운 알약 입력·`ring-1` 경계·`h-8` 기본·`--radius` 하나에서 7단계·사이드바 셸·6가지 페이지 틀)이고 "**색 토큰만 갈아끼워 브랜드를 입힌다**"가 설계 의도다. VideoBox는 승인된 **캡컷식 다크 편집기**다. 그래서 규칙마다 판정한다. 색은 언제나 VideoBox 승인값을 DS의 토큰 층에 그대로 넣는다(DS 방식 그대로: 색은 `:root` 한 층에만).

| DS 규칙 (근거) | 판정 | VideoBox에서의 모습 | 근거·이유 |
|---|---|---|---|
| 색 값은 `:root`(+`.dark`) 한 층, 나머지는 `var()` 별칭 (01 §0) | **받아들임**(이미 그렇다) | `:root` 한 벌, `@theme inline`이 별칭 | 2026-08-29 "한 벌뿐" |
| radius 하나(`--radius`)에서 파생 (01 §2) | **고쳐 받아들임** | 파생 방식은 받되 **세 단계만**: sm=`calc(var(--radius)*0.6)`(6px)·md=`var(--radius)`(10px)·lg=`calc(var(--radius)*1.6)`(16px). Tailwind `rounded-xs/sm`→sm, `rounded-md/lg`→md, `rounded-xl/2xl`→lg | 2026-08-27 "셋뿐". 지금 `rounded-md`가 8px로 넷째 값을 만든다(실측 8px ×17) |
| 컨트롤 기본 `h-8`, 주 동작 `h-9` (01 §4.8, 04 §8-3) | **고쳐 받아들임** | 조밀 척도 **24·28·32px** 세 단계. 기본 28, 주 동작·대화상자 바닥 32, 아이콘·트랙 단추 24 | 대표님 2026-10-08 밀도 요청. 캡컷 실측 버튼 28·32·36(`docs/references/capcut/2026-09-04-panel-inventory.json`) |
| 입력은 **채운 알약** `rounded-2xl bg-input/50` (02 §2) | **채움은 받아들임, 알약은 안 받아들임** | 채운 사각: 바탕 `--vb-panel-alt`, 테두리 투명, 모서리 sm(6px), 높이 28 | 캡컷 숫자칸·검색칸이 사각(2026-09-04 실측, `capcut-patterns.css` 숫자칸 30·검색 34). 편집기 속성 칸이 알약이면 캡컷 패리티(2026-08-30)를 깬다 |
| 표면 경계는 `ring-1 ring-foreground/5` (01 §5.3) | **떠 있는 표면만 받아들임** | 대화상자·드롭다운·선택 목록·툴팁·시트: `box-shadow: 0 0 0 1px var(--vb-surface-ring)` + 그림자. 화면 안 카드·패널은 지금처럼 `1px solid var(--vb-border)` | `--vb-surface-ring` 토큰이 이미 있다. 화면 안 카드 테두리를 바꾸면 승인된 다크 화면 인상이 바뀐다 → 바꾸지 않는다 |
| 초점 링 `ring-3 ring-ring/30` (README 정규화) | **안 받아들임 → 대체** | `outline: 2px solid var(--ring); outline-offset: 2px` | 주황 30%를 어두운 바탕에 깔면 대비 약 1.6:1로 WCAG 2.2 초점 표시(3:1)에 못 미친다. 주황 원색은 패널 위 4.98:1 |
| Dialog `grid` + `[&>*]:min-w-0` 안전망, `max-h-[88vh]` (02 §7) | **받아들임** | `[data-slot=dialog-content]{display:grid} … > *{min-width:0}`, 최대 높이 88vh(지금 70vh), 패딩 16, 간격 12, 제목 14/600 | 긴 파일명·URL이 대화상자를 밀어내는 결함을 근본에서 막는다 |
| 탭: 기본(분절)·`line` 두 변형, 세로 지원 (02 §13) | **받아들임** | 화면 섹션 고르기 = 분절 탭(설정 섹션·자료실 갈래가 아닌 곳), 패널 안 하위 탭 = `line`(밑줄), 편집기 왼쪽 레일 = 세로 아이콘 탭(캡컷 그대로) | 지금은 설정이 단추 묶음, 편집기 하위 탭은 비선택 Arial(감사 3-7) |
| 드롭다운 항목 `min-h-7` `rounded-xl` `p-1.5` (02 §12) | **고쳐 받아들임** | 항목 28px, 모서리 sm, 글자 12px, 목록 안쪽 4px, 강조 바탕 `--accent` | 모서리 셋 규칙 |
| 툴팁 반전색 `bg-foreground text-background`, 지연 0 (02 §24) | **고쳐 받아들임** | 반전색 그대로(대비 17:1), 글자 11px, 모서리 sm, **지연 350ms**(TopBar가 이미 씀) | 편집기는 단추가 촘촘해 지연 0이면 마우스를 지날 때마다 툴팁이 깜빡인다 |
| 아이콘 `size-3.5`(버튼 안)·`size-4`(제목 옆)·`size-6`(빈 상태) (04 §8-2) | **받아들임** | `--vb-icon-xs 12`·`sm 14`·`md 16`·`lg 24` | — |
| 글자 2단 지배(14 본문·12 보조), 제목은 16/500 (01 §3.2) | **고쳐 받아들임** | 조밀: 본문 12·보조 11·항목 이름 13·패널 제목 14·구역 16·화면 제목 20. 굵기 400/500/600 셋 | 대표님 밀도 요청 |
| 굵기 500 기본 강조, 700은 숫자만 (01 §3.3) | **고쳐 받아들임** | 400·500·600만. 650·700·750 금지(Tailwind `font-bold`도 600) | 지금 650·700·750이 섞여 같은 급의 글자가 다르게 보인다 |
| 페이지 루트 `space-y-4`, H1은 헤더바 (04 §0, §8-1) | **고쳐 받아들임** | 화면 제목은 본문 첫 줄 `h1`(20px/600) + 설명 한 줄(12px 흐림) + 주 동작 하나 오른쪽. 루트 간격 `--vb-space-4` | VideoBox 위 띠는 위치(빵부스러기)를 그리므로 제목은 본문에 둔다 |
| 페이지 틀 6가지 (04) | **대시보드 화면만 받아들임** | `/projects`=유형 3(목록, 카드 격자), `/library`·`/footage`=유형 2(목록+상세, 3칸), `/settings`·`/voices`·`/projects/:id/create`=유형 5(폼·설정), `/projects/:id/review`=유형 6(리포트 카드). 편집기는 **틀 밖**(캡컷 작업판) | 편집기 배치는 2026-08-17·08-21 승인 |
| 사이드바 셸(폭 토큰·헤더 48px·콘텐츠 패딩) (03) | **고쳐 받아들임** | 왼쪽 메뉴 176px 유지, 항목 32→28px·글자 12, 위 띠 53→44px, 콘텐츠 패딩 16/24, **최대폭 없음**(D4) | 2026-09-05 상시 왼쪽 메뉴 승인. 캡컷처럼 화면을 넓게 |
| 빈 상태·로딩·오류 틀 (04 §7-7~7-9) | **받아들임** | 빈 상태 = 아이콘 24 + 한 줄 + **다음 행동 단추 하나**, 로딩 = `…하는 중…`, 오류 = 무엇이 안 됐는지 + 다음 행동 | 대표님 "뭘 눌러야 할지 모르겠다" |
| 배지 `h-4 text-[10px]` (README 정규화) | **안 받아들임** | 배지 20px·11px | 최소 글자 11px(접근성 바닥) |
| 카드 radius `min(4xl,24px)` (01 §2) | **안 받아들임** | 카드 md(10px), 큰 패널 lg(16px) | 모서리 셋 |
| 입력 `md:text-sm` 모바일 16px(iOS 확대 방지) | **받아들임** | 375px 미만에서 입력 글자 16px | iOS 사파리 확대 방지 |

## 토큰 한 벌 (Task 2가 `apps/web/src/ui-system.css` `:root`에 넣는 값)

| 묶음 | 토큰 = 값 | 쓰는 자리 |
|---|---|---|
| 글자 | `--vb-text-xs: 0.6875rem`(11) · `--vb-text-sm: 0.75rem`(12) · `--vb-text-md: 0.8125rem`(13) · `--vb-text-lg: 0.875rem`(14) · `--vb-text-xl: 1rem`(16) · `--vb-text-2xl: 1.25rem`(20) · `--vb-text-3xl: 1.5rem`(24) | xs 라벨·메타·배지·클립 이름, **sm 본문 기본**, md 항목·카드 제목, lg 패널 제목, xl 구역 제목, 2xl 화면 제목, 3xl 빈 화면 큰 문장 |
| 줄 높이 | `--vb-leading-xs: 1rem` · `-sm: 1rem` · `-md: 1.125rem` · `-lg: 1.25rem` · `-xl: 1.375rem` · `-2xl: 1.75rem` · `-3xl: 2rem` | Tailwind `--text-*--line-height` 별칭 |
| 굵기 | `--vb-weight-regular: 400` · `--vb-weight-medium: 500` · `--vb-weight-strong: 600` | 본문 / 이름표·탭·단추 / 제목·숫자 |
| 컨트롤 | `--vb-control-xs: 1.5rem`(24) · `--vb-control-sm: 1.75rem`(28) · `--vb-control-md: 2rem`(32) | 아이콘·트랙 단추·칩 / 기본 단추·입력·탭·메뉴 항목 / 주 동작·대화상자 바닥·검색 |
| 모서리 | `--radius: .625rem`(그대로) · `--vb-radius-sm: calc(var(--radius) * 0.6)` · `--vb-radius-md: var(--radius)` · `--vb-radius-lg: calc(var(--radius) * 1.6)` | 6 / 10 / 16px |
| 간격 | `--vb-space-1..8` **값 그대로**(4·8·12·16·20·24·32·40) | 조밀함은 "한 단계 아래 토큰을 쓰는 것"으로 만든다(아래 표) |
| 밀도 묶음 | `--vb-page-pad-y: var(--vb-space-4)` · `--vb-page-pad-x: var(--vb-space-6)` · `--vb-card-pad: var(--vb-space-3)` · `--vb-grid-gap: var(--vb-space-3)` · `--vb-top-bar-h: 2.75rem`(44) · `--vb-side-nav-w: 11rem`(176) | 셸·카드·격자 |
| 아이콘 | `--vb-icon-xs: 0.75rem` · `-sm: 0.875rem` · `-md: 1rem` · `-lg: 1.5rem` | 배지 안 / 단추 안 / 제목 옆 / 빈 상태 |
| 층 | `--vb-z-sticky: 10` · `--vb-z-dock: 20` · `--vb-z-overlay: 40` · `--vb-z-popover: 50` · `--vb-z-toast: 60` | 지금 2·3·20·40·10·50이 흩어져 있다 |
| 초점 | `--vb-focus-outline: 2px solid var(--ring)` · `--vb-focus-offset: 2px` | 모든 `:focus-visible` |
| 글꼴 | `--vb-font: "Pretendard", "Noto Sans KR", sans-serif`(그대로, `assets/fonts/PretendardVariable.woff2` 하나만 실린다) + `--vb-font-numeric: tabular-nums` | 숫자 칸(시간·길이·개수)은 `font-variant-numeric: tabular-nums` |

Tailwind 별칭(`@theme inline`, Task 2): `--text-xs→--vb-text-xs` · `--text-sm→--vb-text-sm` · `--text-base→--vb-text-md` · `--text-lg→--vb-text-lg` · `--text-xl→--vb-text-xl` · `--text-2xl→--vb-text-2xl` · `--text-3xl→--vb-text-3xl`(4xl 이상은 지운다), `--font-weight-semibold: 600` · `--font-weight-bold: 600`, `--radius-xs/sm→--vb-radius-sm` · `--radius-md/lg→--vb-radius-md` · `--radius-xl/2xl→--vb-radius-lg`.

### 무엇이 얼마나 줄어드나 (목표 수치, Task 12 게이트가 잰다)

| 대상 | 지금(실측) | 목표 |
|---|---|---|
| 본문 기본 글자 | 14px(`.vb-product-shell` = `--vb-text-md` 14) | **12px**(`--vb-text-sm`) |
| 라벨·메타 | 10px(자료실 56곳·편집기 40곳·촬영본 158곳) | **11px**(최소) |
| 화면 제목 | 40px/700 | 20px/600 |
| 카드 제목(프로젝트) | 24px/700 | 13px/600, 한 줄 말줄임 |
| 콘텐츠 영역 | 최대폭 1200(1600px 이상 화면 1600), 패딩 32/40 | 최대폭 없음, 패딩 16/24 |
| 위 띠 | 53px | 44px |
| 왼쪽 메뉴 항목 | 36px·14px | 28px·12px |
| 프로젝트 카드 | 268×195, 패딩 20, 모서리 16, 1440에서 4열 | 열 최소 12.5rem(200px), 패딩 12, 모서리 10, 1440에서 **6열** |
| 자료실 영상 카드 | 161×160, 3열, 이름 14, 메타 10 | 열 최소 8.5rem(136px), **5열 이상**, 이름 12, 메타 11, 몸통 패딩 8 |
| 자료실 필터 항목 | 40px·14px | 28px·12px |
| 단추 | 대시보드 32·36·40·80, 편집기 23·25·27·30·32·36·40 | **24·28·32** 세 단계(`+ 새로 만들기` 칸은 G3 결과 그대로, 게이트 예외 목록에 이유 기록) |
| 입력·선택 | 32~40, 글자 10~14 | 28, 글자 12(375px 미만 16) |
| 탭 | 단추 묶음·Arial 섞임 | 분절 28px / line 28px, 글자 12/500 |
| 대화상자 | 폭 35rem, 패딩 24, 최대 70vh | 폭 32rem, 패딩 16, 간격 12, 최대 88vh |
| 편집기 컨트롤 | Arial 66, 모서리 0 ×50 | Arial 0, 모서리 0 0개(재생줄 포함) |
| 주황 채운 단추 | 편집기 38개 | 화면(영역)마다 **1개**(D2) |

---

## 파일 구조

| 파일 | 새로/수정 | 맡는 것 |
|---|---|---|
| `docs/superpowers/2026-10-08-wiring-inventory.ko.md` | 새로(Task 0) | 배선 인벤토리 — 무엇이 안 이어졌고 누가 고치나 |
| `apps/web/e2e/support/style-inventory.mjs` | 새로(Task 0) | 계산 스타일 수집 함수(기준선·게이트 공용) |
| `docs/superpowers/audit-evidence/2026-10-08-design-baseline.json` | 새로(Task 0) | 고치기 전 수치 |
| `docs/decisions/2026-10-08-compact-density.ko.md` | 새로(Task 1) | 밀도 결정(승인됨) |
| `docs/decisions/2026-10-08-design-system-normalization.ko.md` | 새로(Task 1) | 색 아닌 모양 통일(owner 승인 필요 표시) |
| `apps/web/src/ui-system.css` | 수정(Task 2) | 토큰 한 벌, Tailwind 별칭, 폼 컨트롤 글꼴 상속 |
| `apps/web/src/styles/theme-tokens.test.ts` | 수정(Task 2·4) | 새 척도 값 고정 |
| `apps/web/src/styles/design-guard.test.ts` + `design-guard.baseline.json` + `design-guard.allow.json` | 새로(Task 3) | 줄어들기만 하는 정적 가드 |
| `apps/web/src/styles/primitives.css` + `primitives.test.ts` | 새로(Task 4) | 부품 규격 층 |
| `apps/web/src/styles/index.css` | 수정(Task 4) | 불러오는 순서 |
| `apps/web/src/features/shell/useActionFeedback.ts`, `DisabledReason.tsx`, `feedback.test.tsx` | 새로(Task 5) | 누름 → 진행 → 결과 한 가지 무늬, 잠긴 이유 |
| `apps/web/src/app/AppRoot.tsx` | 수정(Task 5) | `Toaster` 한 번 걸기 |
| `apps/web/src/styles/product-shell.css` | 수정(Task 6~9) | 셸·대시보드 화면 조밀화 |
| `apps/web/src/features/library/library.css`, `features/footage/footage.css`, `components/ui/capcut-patterns.css` | 수정(Task 4·8) | 화면별 리터럴 → 토큰 |
| `apps/web/src/styles/editor-workbench.css` + 편집기 TSX | 수정(Task 10, **H 뒤**) | 편집기 크롬 |
| `apps/web/e2e/design-tokens.spec.mjs` + `support/design-targets.mjs` | 새로(Task 12) | 계산 스타일 게이트 |
| `apps/web/e2e/no-dead-clicks.spec.mjs` + `support/no-reaction-allowlist.mjs` | 새로(Task 13) | 무반응 스모크 |
| `docs/owner-test-guide.ko.md` | 새로(Task 14) | 대표님 클릭 지도 |
| `docs/design-rules.ko.md` | 새로(Task 14) | 다음 세션이 흔들리지 않게 하는 규칙 한 장 |
| `CLAUDE.md` | 수정(Task 14·15) | §2 표에 디자인 규칙 줄, 최신 인계 줄 |

---

### Task 0: 착수 확인 · 고치기 전 기준선 · 배선 인벤토리

**적용 스킬:** design:design-system(`audit` 출력 틀: 토큰 커버리지·하드코딩 수), web-design-guidelines(아이콘 단추 이름·비활성·초점), intranet-style 재현 체크리스트(전 항목을 기준선 열로).

**Files:**
- Create: `apps/web/e2e/support/style-inventory.mjs`
- Create: `docs/superpowers/audit-evidence/2026-10-08-design-baseline.json`
- Create: `docs/superpowers/2026-10-08-wiring-inventory.ko.md`

**Interfaces:**
- Produces: `export async function collectStyleInventory(page: import("@playwright/test").Page): Promise<StyleInventory>` — `StyleInventory = { path: string; viewport: {w:number,h:number}; docScrollWidth: number; docClientWidth: number; controls: Array<{ name: string; tag: string; role: string|null; h: number; w: number; fontFamily: string; fontSize: number; fontWeight: number; radius: string; variant: string|null; size: string|null; disabled: boolean; hasReason: boolean; primary: boolean; selector: string }>; texts: Array<{ fontSize: number; fontWeight: number; fontFamily: string; sample: string }> }`. 컨트롤 선택자: `button, [role=tab], [role=menuitem], [role=option], select, input:not([type=hidden]):not([type=range]):not([type=checkbox]):not([type=radio]):not([type=file]), textarea`, 보이는 것만(`getBoundingClientRect` 폭·높이 > 0). `hasReason` = `title` 또는 `aria-describedby`가 있음. `primary` = `data-primary-action` 속성. `fontFamily`는 계산값의 첫 글꼴 이름(따옴표 제거). Task 12·13·14가 같은 함수를 쓴다.

- [ ] **Step 1: 착수 확인**

```powershell
git status --short; git log --oneline -8; git worktree list; git diff --check
Select-String -Path docs/superpowers/plans/2026-10-08-editor-core-repair-h.ko.md -Pattern "^### Task" | Measure-Object
git log --oneline --since=2026-10-02 -- apps/web/src/app/ProductShell.tsx apps/web/src/features/editor/timeline/TimelineDock.tsx
```
기대: H 계획이 있고 그 커밋들이 main에 있다(없으면 **멈추고** "H 먼저"를 보고). G의 Task 2·3·6·7 커밋 여부를 기록한다(D5).

- [ ] **Step 2: `style-inventory.mjs` 작성** — 위 Interfaces 그대로. 이 파일은 시험이 아니라 도우미이므로 RED가 없다. 대신 Step 3에서 실제로 돌려 값이 나오는지 본다.

- [ ] **Step 3: 기준선 기록(실제 컨테이너, 읽기만)**

게이트 spec(Task 12)은 아직 없으므로 **내장 브라우저**(`mcp__Claude_Browser__javascript_tool`)로 잰다: 실제 컨테이너(`http://127.0.0.1:5173`)에서 `/projects`, `/library`, `/library?kind=audio`, `/footage`, `/voices`, `/settings/appearance`, `/projects/2026-09-12-742e1924/editor`, `/projects/2026-09-12-742e1924/review` 를 1440×900으로 열고 `style-inventory.mjs`와 같은 수집 코드를 붙여 넣어 결과를 JSON 배열로 모은 뒤 위 경로에 저장한다. 읽기만 한다(아무것도 누르지 않는다). 기대: 8개 화면 항목, 각 화면 `controls` 길이가 위 "실측 기준선" 표와 ±10% 안.

- [ ] **Step 4: 배선 인벤토리 명령 실행** — 아래 명령을 그대로 돌리고 출력으로 인벤토리 표를 채운다(이미 찾은 값은 아래 "미리 채운 내용"에 있다. 다르면 **새 값으로 고치고 차이를 적는다**).

```bash
# (a) 손잡이 없는 단추·조건 비활성·이름 없는 아이콘 단추 — TypeScript AST
cd apps/web && node ../../docs/superpowers/audit-evidence/scan-controls.cjs src
# (b) 화면 호출 0개인 api 메서드
cd apps/web/src && sed -n '/^export const api = {/,$p' api.ts | grep -oE "^  [a-zA-Z0-9_]+:" | tr -d ' :' | sort -u | while read m; do n=$(grep -rlE "\b$m\b" --include=*.ts --include=*.tsx . | grep -v "^./api.ts$" | grep -vE "\.test\.tsx?$" | wc -l); [ "$n" = 0 ] && echo "$m tests=$(grep -rlE "\b$m\b" --include=*.test.ts --include=*.test.tsx . | wc -l)"; done
# (c) 라우트와 메뉴 — 정의된 경로 vs 메뉴에서 닿는 경로
grep -n 'path: "' apps/web/src/app/AppRouter.tsx; grep -n 'globalDestinations\|const STAGES\|const ITEMS\|ASSET_ITEMS' apps/web/src/app/routeManifest.ts apps/web/src/features/shell/*.tsx
# (d) 백엔드 경로 중 프런트가 안 부르는 것(휴리스틱: 마지막 고정 조각이 프런트 소스에 없음)
.venv/Scripts/python.exe docs/superpowers/audit-evidence/scan-unrouted.py
# (e) 유진 명령 목록
grep -rhoE '"(set|apply|add|remove|split|merge|undo|redo|render|export|translate|dub|create|request)_[a-z_]+"' packages/core-engine/src/videobox_core_engine/yujin_*.py services/api/src/videobox_api/*.py | sort -u
# (f) 탭·선택 목록 — role=tab 수, tabpanel 짝, 선택 옵션 수(내장 브라우저에서)
```
`scan-controls.cjs`와 `scan-unrouted.py`는 이 Step에서 `docs/superpowers/audit-evidence/`에 만든다. 내용: `scan-controls.cjs`는 TypeScript 컴파일러 API로 `.tsx`(시험 제외)의 `<Button>`/`<button>` 여는 태그를 훑어 (1) `onClick|onPointerDown|onMouseDown|onKeyDown|onSelect|asChild|form` 도 펼침(`{...props}`)도 `type="submit"`도 없는 것, (2) `disabled`가 있고 `title`·`aria-describedby`가 없으며 식이 `/busy|pending|saving|loading|starting|submitting|running|sending|uploading|recording/i` **한 낱말만**이 아닌 것, (3) `size="icon…"`인데 `aria-label`·`title`이 없는 것을 `파일:줄`로 낸다. `scan-unrouted.py`는 `services/api/src/videobox_api/routers/*.py`의 `APIRouter(prefix=…)`+`@router.<method>("…")`를 읽어, 경로의 마지막 고정 조각이 `apps/web/src/**/*.ts(x)`(시험 제외)에 `/<조각>`으로 나오지 않는 것을 낸다.

- [ ] **Step 5: 인벤토리 문서 작성** — `docs/superpowers/2026-10-08-wiring-inventory.ko.md`. 머리에 "만든 명령(위 Step 4)·날짜·커밋"을 적고, 아래 "미리 채운 내용"을 옮긴 뒤 Step 4 출력으로 확인·보충한다. 각 줄의 **처리** 열은 `고침(Task N)` / `없앰(Task 11)` / `그대로 — 이유` / `H에 넘김` / `B–F에 넘김` / `owner 결정` 중 하나다.

미리 채운 내용(계획 작성 시 확인한 것):

| ID | 종류 | 자리 | 무엇 | 처리 |
|---|---|---|---|---|
| W-01 | (a) 손잡이 없음 | `features/footage/SceneTimeline.tsx` `data-native-control="footage-playhead"` | 재생 위치 표시가 **단추**인데 누를 손잡이·키 처리 없음, `aria-valuenow`만 있고 `role=slider` 없음 | 없앰 → 꾸밈 `<span aria-hidden="true">`로 바꾸고 `task22-parity-owners` 허용 수 1 감소(Task 11) |
| W-02 | (b) 화면 호출 0 | `api.ts` `createHermesRun`·`openHermesRunEvents`·`cancelHermesRun`·`retryHermesRun` | 유진 실시간 실행 길. 시험(`hermesSseClient.test.ts`)만 부른다 | 조사(Task 11): 백엔드 라우트를 유진·MCP가 쓰는지, B–F·H가 쓸 계획인지. 셋 다 아니면 없앰, 하나라도면 `그대로 — 이유` 주석 |
| W-02 | (b) | `getExport`·`getPreview` | `AppRouter.test.tsx`가 "**부르지 않는다**"를 단언한다 = 일부러 남긴 것 | 그대로 — 그 시험이 이유. 인벤토리에 시험 줄 번호를 적는다 |
| W-02 | (b) | `getDirectorProposal`·`listDirectorMessages`·`prepareDirectorMessage` | `api.test.ts`만 부른다 | 조사 후 W-02 규칙(Task 11) |
| W-03 | (d) 화면 없음 후보 30 | `editing-sessions/{sid}/tracks`(GET/POST/DELETE/PATCH order), `segments/{id}/visual-overlay`(PATCH/DELETE), `narration-alignment`(+from-recording), `editing-sessions/from-script`, `jobs/segment-analysis`·`broll-recommendation`·`music-recommendation`(+GET), `jobs/auto-cut-plan`·`auto-cut-detect`, `assets/script-document`·`raw-video`, `library/ingest-path`, `media-library/install(-state)`, `exact-previews/{gid}`, `jobs/preview-render`, `jobs/capcut-export`, `jobs/build-timeline`, `provider-traces`, `media-analysis/{id}/provenance`, `review-snapshots/…/reject`, `/internal/live-smoke/…` | 휴리스틱이라 템플릿 문자열로 부르는 것이 섞였을 수 있다 | 줄마다 분류: **유진·MCP 전용**(정상) / **내부 점검**(정상) / **계획이 화면에 약속했는데 없음**(→ owner 결정 목록, 이 계획에서 만들지 않음) / **아무도 안 씀**(→ 별도 정리 후보, 지우지 않음) |
| W-04 | (a) 이유 없는 비활성 | 138곳/33파일. 많은 순: `editor/inspector/InspectorControls.tsx` 22 · `app/OutputsPage.tsx` 11 · `editor/assets/EditorAssetBrowser.tsx` 9 · `editor/workbench/YujinPanel.tsx` 9 · `footage/FootageOrganizerPage.tsx` 8 · `creation/CreationInterview.tsx` 7 · `editor/preview/preview-stage.tsx` 6 · `settings/VoiceTtsSettings.tsx` 6 · … | 실측: `/footage` 7개(`유진에게 제안 요청`·`분석 시작`·`제안 미리보기`·`제안 취소`·`제안 적용`·`선택 장면으로 가상 묶음 만들기`·`새 클립 파일로 만들기`), 편집기 8개(`◀｜`·`재생 / 일시정지`·`｜▶`·`음소거`·`전체화면`·`승인한 음성 적용`·`부분 재생성 실행`·`이전 결과 열기`) | 고침: 편집기 밖 → Task 5, 편집기 → Task 10. 끝에 0 |
| W-05 | 문구 | `/footage` 촬영본 이름 `derived:footage_render_job_7e19…`, `앞 경계 −1f`·`뒤 경계 +1f`, `fps`·`프레임 간격`; 대화상자 닫기 `Close`; 라우터 오류 화면 `Something went wrong!`(감사 3-6); 캡션 모양 `Clean`·`Highlight`(감사 §4); `대본` 탭 백틱 노출 | 내부 id·영어·기호 | 고침(Task 8·4·11·10) |
| W-06 | 설정 | `ProductShell.tsx` `SettingToggle label="조밀한 화면"` | 켜도 `.vb-home-grid`(홈 카드·출력 격자)와 콘텐츠 패딩만 바뀜 — 대부분 화면에서 **눌러도 변화 없음** | owner 결정 D3(기본: 없앰, 조밀이 하나뿐인 기본값이 된다) |
| W-07 | (f) 탭 | 설정 섹션이 `Button` 묶음(`role=tab` 없음), 편집기 왼쪽 레일 탭 이름 빈칸·`tabpanel` 짝 없음(감사 §4) | 탭처럼 보이고 탭처럼 안 읽힘 | 고침(Task 9·10) |
| W-08 | (c) 라우트 | `/`→`/projects`, `/projects/`, `/preview/$token`(공유, 셸 없음 — 정상), `/library(?kind=broll|audio)`, `/voices`, `/footage`, `/projects/$id/{home,create,editor,review,outputs,media→editor}`, `/settings/{general→appearance,appearance,ai-privacy,voice,output,conversations}` | 메뉴에서 닿는지: 왼쪽 메뉴(프로젝트·자료실·촬영본 정리·내 영상·음악·효과음·내 목소리·설정), 위 띠 단계(이야기·편집·확인과 내보내기) | 닿지 않는 화면 없음(확인됨). 빈 화면으로 가는 메뉴: 설정 `AI·개인정보`·`출력`이 문장 한 줄(G7이 3칸으로 줄임) |
| W-09 | 피드백 | `components/ui/sonner.tsx` `Toaster` 미장착 | 결과 알림 방식이 화면마다 다르다(`role=status` 63곳) | 고침(Task 5) |
| W-10 | (e) 유진 격차 | 아래 (e)절 | — | B–F에 넘김(목록만) |
| W-11 | (f) 죽은 선택지 | 편집기 `편집 대상` 선택 상자 17→3,581개(감사 3-6, 중복 id) | — | H에 넘김. I는 이름 문구만(Task 10) |
| W-12 | 무반응 | 편집기 트랙 잠금·숨기기·음소거 9개 마우스로 안 눌림(감사 3-4) | — | H에 넘김 |

(e)절 — 화면에 있고 유진은 아직 못 하는 것(구현하지 않는다. B–F 담당 Task를 적는다): 장면 나누기 B-Task2 · 앞과 붙이기 B-Task3 · 되돌리기/다시 하기 B-Task4 · 배속 0.25~4 B-Task5 · 트랙 숨기기·소리 끄기 B-Task6 · 완성본 만들기 C-Task9 · 캡컷 초안·미리보기 링크 C-Task10 · 업로드 승인 **요청** C-Task11 · 설명 카드·표·도형 D-Task13 · 자막 모양 D-Task14 · 저장한 포맷 D-Task15 · 자막 번역·언어 E-Task17 · 더빙 E-Task18 · TTS 교체·받아쓰기 캡션·부분 다시 만들기 E-Task19 · 프로젝트 보관 F(2026-10-02 결정). **B–F에 없는 후보**(Step 4 (e) 출력과 대조해 확정, F-Task21 후보로 넘김): 자료실 이름 바꾸기·즐겨찾기·휴지통, 촬영본 정리(분석 시작·제안 적용·가상 묶음), 모션 만들기(2026-10-08 새 기능), 화면 변형(크기·위치·기울이기·화면 맞춤), 색감·흔들림·노이즈, 소리 크기·서서히, 전환 적용.

- [ ] **Step 6: 커밋**

```bash
git add apps/web/e2e/support/style-inventory.mjs docs/superpowers/audit-evidence/2026-10-08-design-baseline.json docs/superpowers/audit-evidence/scan-controls.cjs docs/superpowers/audit-evidence/scan-unrouted.py docs/superpowers/2026-10-08-wiring-inventory.ko.md
git commit -m "docs: 계획 I 착수 — 디자인 기준선과 배선 인벤토리(W-01~W-12)"
```

**검증 넷:** 갭 = Step 4의 (a)~(f) 여섯 갈래가 인벤토리에 각각 절로 있는가 · 역방향 = 기준선이 실제 컨테이너 화면에서 잰 값인가(`path` 기록) · 동작 = 화면별 컨트롤 수·Arial 수·10px 수가 숫자로 있는가 · 배선 = W-02의 "0 호출"을 grep 출력 그대로 붙였는가.

---

### Task 1: 결정 기록 두 장 (토큰을 바꾸기 전에)

**적용 스킬:** design:design-system(`Version and migrate` — 바뀌는 값과 옮기는 길을 적는다), design:ux-copy(결정 문서도 대표님이 읽는 글: 짧게).

**Files:**
- Create: `docs/decisions/2026-10-08-compact-density.ko.md`
- Create: `docs/decisions/2026-10-08-design-system-normalization.ko.md`

**Interfaces:** Produces: 두 문서의 경로(Task 2·4·6·14가 주석과 시험 설명에서 인용).

- [ ] **Step 1: `2026-10-08-compact-density.ko.md` 작성** — 아래 본문 그대로(표 수치는 이 계획의 "토큰 한 벌"·"무엇이 얼마나 줄어드나" 표를 복사한다):

```markdown
# 조밀한 화면 — 캡컷처럼 넓게 쓰기 (2026-10-08, owner 승인)

- 결정 상태: **approved** (대표님 말이 승인이다)
- 갱신하는 것: `2026-08-19-spacing-and-type-scale.ko.md`의 글자 **값**, `2026-09-04` 캡컷 실측 척도의 글자 **값**과 "단추 32px 하나" 규칙
- 바꾸지 않는 것: **색 전부**(`2026-08-29` 다크 팔레트), 모서리 세 단계(`2026-08-27`), 간격 토큰 값(`--vb-space-1..8`), 토큰 이름

## 대표님이 말한 것
> "검은 배경은 좋다. 캡컷처럼 화면을 넓게 쓰려면 글자를 줄이고 컴포넌트·카드를 줄여야 한다."

## 무엇이 바뀌나
(토큰 표 · 줄어드는 대상 표)

## 앞 승인과 어디서 부딪치나
- 2026-09-04 척도는 본문 14px였다(캡컷 실측 "항목 이름 14px 83곳"). 이번엔 본문 12px — 캡컷 패널에서 **더 많이** 쓰인 크기(12px 176곳)를 본문으로 삼는다.
- 2026-09-04 "단추 32px 하나"는 세 단계(24·28·32)로 바뀐다. 기본은 28.
- 10px(세로 띠 라벨·배지)은 없어진다. 최소 글자는 11px.
- 콘텐츠 최대폭 1200px(2026-08-19 "껍데기가 정한다")은 없어진다. 껍데기가 정한다는 원칙은 그대로.
- `설정 > 화면 > 조밀한 화면` 토글은 (D3 결정에 따라) 없어진다 — 조밀함이 기본이다.

## 지키는 바닥
누를 자리 24px 이상, 글자 11px 이상, 작은 글자 대비 4.5:1 이상. 주황·흐린 글자를 주황 바탕에 쓰지 않는다.

## 검증
`apps/web/e2e/design-tokens.spec.mjs`(계산 스타일 게이트), `apps/web/src/styles/design-guard.test.ts`(정적 가드).
```

- [ ] **Step 2: `2026-10-08-design-system-normalization.ko.md` 작성** — 첫 줄에 상태를 이렇게 적는다: `- 결정 상태: **needs owner approval** — 색이 아닌 모양 통일. 색은 바꾸지 않는다.` 본문은 이 계획의 "디자인 시스템 대조" 표 전체 + 아래 다섯 항목(각각 "지금 / 바뀐 뒤 / 왜")을 적는다: (1) 모서리 8px 없애기(`rounded-md` 8→10), (2) 초점 링을 2px 주황 외곽선으로, (3) 탭 무늬 둘(분절·밑줄)로 통일·설정 섹션을 탭으로, (4) **주황 채운 단추는 영역마다 하나**(`Button` 기본 변형을 `outline`으로, 주 동작만 `variant="default"` + `data-primary-action`), (5) 대화상자 격자·최대 88vh·패딩 16. 끝에 "승인되면 상태를 approved로 바꾸고 날짜를 적는다. 승인 전에는 계획 I의 Task 0~3과 밀도 관련 부분만 진행한다(Task 4의 (1)(2)(5), Task 5의 (4), Task 9의 (3)은 대기)."

- [ ] **Step 3: 커밋**

```bash
git add docs/decisions/2026-10-08-compact-density.ko.md docs/decisions/2026-10-08-design-system-normalization.ko.md
git commit -m "docs(decisions): 조밀한 화면(승인)과 모양 통일(승인 대기) 결정 기록"
```

**검증 넷:** 갭 = 두 문서가 "바꾸지 않는 것: 색"을 첫 화면에 적었는가 · 역방향 = 해당 없음(문서) · 동작 = 수치 표가 Task 2 토큰과 같은가(Task 2 끝에 다시 대조) · 배선 = `docs/decisions/`에서 가장 나중 문서가 이 둘인가(`ls docs/decisions | sort | tail -3`).

---

### Task 2: 토큰 한 벌 — 글자·컨트롤·모서리·아이콘·층·초점, Tailwind 별칭, 글꼴 상속

**적용 스킬:** intranet-style 01-tokens(§0 3층 구조, §2 radius 파생, §3 타이포 계층, §4.8 컨트롤 스케일), design:design-system(토큰 정의), web-design-guidelines(`tabular-nums`, `color-scheme: dark` 유지).

**Files:**
- Modify: `apps/web/src/ui-system.css` (앵커: `--vb-radius-sm: 0.375rem;`, `--vb-text-xs: 0.625rem;`, `--text-xs: 0.75rem;`, `--radius-sm: calc(var(--radius) - 4px);`, `.vb-button { font: inherit; }`)
- Modify: `apps/web/src/styles/product-shell.css` (앵커: `.vb-product-shell { --vb-top-bar-h: 4.25rem;` 의 `font-size: var(--vb-text-md);`)
- Test: `apps/web/src/styles/theme-tokens.test.ts`

**Interfaces:**
- Produces: CSS 사용자 속성 — 위 "토큰 한 벌" 표의 이름 전부(`--vb-text-xs..3xl`, `--vb-leading-*`, `--vb-weight-regular|medium|strong`, `--vb-control-xs|sm|md`, `--vb-radius-sm|md|lg`, `--vb-page-pad-x|y`, `--vb-card-pad`, `--vb-grid-gap`, `--vb-top-bar-h`, `--vb-side-nav-w`, `--vb-icon-xs|sm|md|lg`, `--vb-z-sticky|dock|overlay|popover|toast`, `--vb-focus-outline`, `--vb-focus-offset`). 이후 모든 Task가 이 이름만 쓴다.

- [ ] **Step 1: 실패하는 시험으로 바꾼다** — `theme-tokens.test.ts`의 `describe("글자·단추 척도를 캡컷 실측값에 맞춘다")` 를 `describe("조밀한 척도(2026-10-08 대표님 승인)")`로 바꾸고:

```ts
const scale: ReadonlyArray<readonly [string, string]> = [
  ["--vb-text-xs", "0.6875rem"], ["--vb-text-sm", "0.75rem"], ["--vb-text-md", "0.8125rem"],
  ["--vb-text-lg", "0.875rem"], ["--vb-text-xl", "1rem"], ["--vb-text-2xl", "1.25rem"], ["--vb-text-3xl", "1.5rem"],
  ["--vb-control-xs", "1.5rem"], ["--vb-control-sm", "1.75rem"], ["--vb-control-md", "2rem"],
  ["--vb-weight-regular", "400"], ["--vb-weight-medium", "500"], ["--vb-weight-strong", "600"],
  ["--vb-top-bar-h", "2.75rem"], ["--vb-side-nav-w", "11rem"],
]
for (const [token, value] of scale) it(`${token}가 ${value}다`, () => expect(uiSystemCss).toContain(`${token}: ${value};`))

it("모서리 셋은 --radius 하나에서 나온다", () => {
  expect(uiSystemCss).toContain("--vb-radius-sm: calc(var(--radius) * 0.6);")
  expect(uiSystemCss).toContain("--vb-radius-md: var(--radius);")
  expect(uiSystemCss).toContain("--vb-radius-lg: calc(var(--radius) * 1.6);")
})
it("Tailwind 글자·모서리 유틸리티는 토큰의 별칭이다", () => {
  const inline = uiSystemCss.match(/@theme inline\s*\{[\s\S]*?\n\}/)?.[0] ?? ""
  for (const [tw, vb] of [["--text-xs","--vb-text-xs"],["--text-sm","--vb-text-sm"],["--text-base","--vb-text-md"],["--text-lg","--vb-text-lg"],["--radius-md","--vb-radius-md"],["--radius-lg","--vb-radius-md"],["--radius-xl","--vb-radius-lg"]])
    expect(inline).toContain(`${tw}: var(${vb});`)
  expect(uiSystemCss).not.toMatch(/--text-4xl:/)
})
it("폼 컨트롤은 화면 글꼴을 물려받는다(Arial 방지)", () => {
  expect(uiSystemCss).toMatch(/:where\(button,\s*input,\s*select,\s*textarea\)\s*\{[^}]*font:\s*inherit/)
})
it("화면 기본 글자가 본문 척도(12px)다", () => {
  const rule = productShellCss.match(/\.vb-product-shell\s*\{[^}]*\}/)?.[0]
  expect(rule).toMatch(/font-size:\s*var\(--vb-text-sm\)/)
})
```
기존 `"화면 기본 글자가 본문 척도(14px)다"` 시험은 지운다(위 것이 대체). `"단추 높이가 32px 하나로 통일된다"`는 **Task 4가** 바꾸므로 여기서는 두고, `"척도는 셋뿐이다"`·`"기준 글자를 rem 척도째로 줄이지 않는다"`는 그대로 둔다.

- [ ] **Step 2: 돌려서 실패를 본다**

Run: `cd apps/web && npx vitest run src/styles/theme-tokens.test.ts -t "조밀한 척도"`
Expected: FAIL — `--vb-text-xs가 0.6875rem다`가 `0.625rem`을 찾음.

- [ ] **Step 3: `ui-system.css` 고치기**
  - `:root`의 글자 척도 7줄 값을 표대로 바꾸고 주석을 "2026-10-08 조밀한 화면(`docs/decisions/2026-10-08-compact-density.ko.md`) — 앞 값은 2026-09-04 캡컷 척도"로 고친다.
  - `--vb-radius-*` 세 줄을 `calc` 파생식으로(값은 6/10/16px 그대로).
  - 표의 나머지 토큰(줄 높이·굵기·컨트롤·밀도 묶음·아이콘·층·초점)을 `:root`에 더한다. `--vb-top-bar-h`는 `product-shell.css`의 `.vb-product-shell { --vb-top-bar-h: 4.25rem;` 에서 지우고 `:root`로 옮긴다(값 2.75rem).
  - `@theme { … }`의 `--text-xs`~`--text-9xl`과 그 `--line-height` 줄을 지우고, `@theme inline { … }`에 별칭을 넣는다: 글자 7개 + 줄 높이 7개(`--text-xs--line-height: var(--vb-leading-xs);` …) + `--font-weight-semibold: 600; --font-weight-bold: 600;`(`@theme`의 bold 700 줄은 지운다) + 모서리 별칭 6개(`--radius-xs/sm → --vb-radius-sm`, `--radius-md/lg → --vb-radius-md`, `--radius-xl/2xl → --vb-radius-lg`; 기존 `calc(var(--radius) - 4px)`·`- 2px` 두 줄은 지운다).
  - `.vb-button { font: inherit; }` 아래에 `:where(button, input, select, textarea) { font: inherit; letter-spacing: inherit; color: inherit; }` 를 더한다(특정도 0 — Tailwind `text-*` 유틸리티와 모든 기능 규칙이 이긴다. 브라우저 기본 Arial 13.33px만 막는다). 주석: 감사 3-7, 실측 Arial 44(편집기)·5(`/projects`).
  - `:where(time, [data-numeric]) { font-variant-numeric: tabular-nums; }`
- `product-shell.css` `.vb-product-shell` 규칙의 `font-size: var(--vb-text-md)` → `var(--vb-text-sm)`.

- [ ] **Step 4: 통과 확인**

Run: `cd apps/web && npx vitest run src/styles/theme-tokens.test.ts`
Expected: PASS(파일 전체 — 위에서 남겨 둔 32px 시험 포함). 이어서 `npx vitest run src/styles/contrast.test.ts src/components/ui/capcut-patterns.design-system.test.ts src/features/footage/footage-design-system.test.ts` PASS.

- [ ] **Step 5: 넓은 확인** — `cd apps/web && npx tsc --noEmit && npx vitest run src/styles src/app/ProductShell.test.tsx src/ui-system.test.tsx`. 글자 값만 바뀌었으므로 jsdom 시험은 그대로여야 한다. 실패하면 그 시험이 **px 값을 단언**하는지 본다 — 단언하면 새 값으로 고치고 고친 이유를 커밋 본문에 적는다.

- [ ] **Step 6: 커밋**

```bash
git add apps/web/src/ui-system.css apps/web/src/styles/product-shell.css apps/web/src/styles/theme-tokens.test.ts
git commit -m "feat(web): 조밀한 토큰 한 벌 — 본문 12·라벨 11·컨트롤 24/28/32, Tailwind 별칭, 폼 글꼴 상속"
```

**검증 넷:** 갭 = 표의 토큰 이름이 전부 `:root`에 있는가(`grep -c "\-\-vb-" src/ui-system.css` 전후 비교) · 역방향 = Vite 개발 서버(`npm --prefix apps/web run dev`)에서 `/projects` 단추 글꼴 Arial 0개(JS로 잼) · 동작 = 본문 계산 글자 12px · 배선 = `grep -rn "var(--vb-text-" apps/web/src --include=*.css | wc -l`이 줄지 않았는가(이름을 지키면 소비자가 그대로다).

---

### Task 3: 정적 가드 — 줄어들기만 하는 기준선

**적용 스킬:** design:design-system(토큰 커버리지·하드코딩 수 = 감사 표의 열), no-ai-design-slop(임의 값·임의 굵기 금지), web-design-guidelines(비활성에는 이유, 아이콘 단추 이름).

**Files:**
- Create: `apps/web/src/styles/design-guard.test.ts`
- Create: `apps/web/src/styles/design-guard.baseline.json`
- Create: `apps/web/src/styles/design-guard.allow.json`

**Interfaces:**
- Produces: `export function collectDesignViolations(srcRoot: string): Record<RuleId, Record<string /*파일 상대 경로*/, number>>` (같은 파일에서 export, Task 15가 "전부 0"을 단언할 때 다시 씀). `type RuleId = "css-font-size" | "css-font-weight" | "css-px-height" | "css-color" | "css-radius" | "tsx-arbitrary" | "tsx-palette-color" | "tsx-button-height" | "tsx-disabled-no-reason" | "tsx-icon-no-label"`.
- 기준선 파일 모양: `{ "<RuleId>": { "<파일>": <개수> } }`. 허용 파일 모양: `[{ "rule": RuleId, "file": string, "match": string, "reason": string }]` — 이유가 있는 예외(예: `ui-system.css` `:root` 팔레트, `.vb-preview-share{background:#000}`, `InspectorControls.tsx`의 자막 기본색 `#ffffff`/`#000000`은 **데이터 값**).

규칙(주석은 걷어내고 잰다):

| RuleId | 대상 | 위반 |
|---|---|---|
| css-font-size | `src/**/*.css` | `font-size:` 값이 `var(--vb-text-`·`inherit`·`1em`이 아님 |
| css-font-weight | 〃 | 값이 `400|500|600|inherit|var(--vb-weight-…)`가 아님 |
| css-px-height | 〃 | `(min-|max-)?height:\s*(\d+)px` 에서 수가 `0,1,2,24,28,32` 밖(rem 배치 높이는 허용) |
| css-color | 〃 | `#[0-9a-fA-F]{3,8}\b|rgba?\(\s*\d` (허용 파일 제외) |
| css-radius | 〃 | `border-radius:` 값이 `var(…)`·`0`·`999px`·`9999px`·`50%`·`inherit`가 아님 |
| tsx-arbitrary | `src/**/*.tsx`(시험 제외) | className 문자열에 `text-\[`·`h-\[\d+px\]`·`rounded-\[`·`font-(extrabold|black)` |
| tsx-palette-color | 〃 | `(bg|text|border|ring|from|to|fill|stroke)-(red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|gray|zinc|slate|neutral|stone)-\d{2,3}` 또는 `bg-white|text-white|bg-black` |
| tsx-button-height | 〃 | `<Button`의 className에 `\b(h|min-h|size)-\d` |
| tsx-disabled-no-reason | 〃 | Task 0 `scan-controls.cjs` (2)와 같은 판정 |
| tsx-icon-no-label | 〃 | `size="icon…"`인데 `aria-label`·`title`·`aria-labelledby` 없음 |

- [ ] **Step 1: 시험 작성**

```ts
describe("디자인 가드 — 위반 수는 줄어들기만 한다", () => {
  const current = collectDesignViolations(resolve(process.cwd(), "src"))
  const baseline = JSON.parse(readFileSync(resolve(process.cwd(), "src/styles/design-guard.baseline.json"), "utf8"))
  for (const rule of RULE_IDS) {
    it(`${rule}: 어느 파일도 기준선보다 늘지 않는다`, () => {
      for (const [file, count] of Object.entries(current[rule])) {
        expect(count, `${file}에서 ${rule}가 늘었다 — 토큰으로 바꾸거나 design-guard.allow.json에 이유를 적어라`).toBeLessThanOrEqual(baseline[rule]?.[file] ?? 0)
      }
    })
  }
  it("허용 목록의 모든 줄에 이유가 있다", () => { for (const e of allow) expect(e.reason.trim().length).toBeGreaterThan(5) })
  it.runIf(process.env.VB_WRITE_DESIGN_BASELINE === "1")("기준선 쓰기", () => { writeFileSync(baselinePath, JSON.stringify(current, null, 2) + "\n") })
})
```

- [ ] **Step 2: RED 확인** — 기준선 파일을 `{}`로 두고 `cd apps/web && npx vitest run src/styles/design-guard.test.ts` → FAIL(위반이 기준선 0보다 많다). 이것이 가드가 실제로 위반을 **센다**는 증거다. 출력의 `css-font-weight` 위반에 `product-shell.css`가 있는지 본다(650·700이 있으므로 있어야 한다).

- [ ] **Step 3: 기준선 쓰기** — `cd apps/web; $env:VB_WRITE_DESIGN_BASELINE="1"; npx vitest run src/styles/design-guard.test.ts -t "기준선 쓰기"; Remove-Item Env:VB_WRITE_DESIGN_BASELINE`. 허용 파일에 위 세 예외를 넣는다. 기준선 합계를 인벤토리 문서 끝에 "가드 시작 수"로 적는다(`tsx-disabled-no-reason`은 Task 0 수 138과 ±5 안이어야 한다 — 크게 다르면 판정 식이 다르니 고친다).

- [ ] **Step 4: GREEN** — `npx vitest run src/styles/design-guard.test.ts` PASS.

- [ ] **Step 5: 커밋** — `git add apps/web/src/styles/design-guard.* && git commit -m "test(web): 디자인 가드 — 글자·굵기·높이·색·모서리·비활성 이유 위반이 늘지 않게"`

이후 Task마다: 고친 파일의 기준선 수를 **내린다**(같은 명령으로 다시 쓰고 `git diff`에 증가가 없는지 본다). 증가가 보이면 그 Task가 새 위반을 만든 것이다.

**검증 넷:** 갭 = 표의 10규칙이 전부 `RULE_IDS`에 있는가 · 역방향 = 해당 없음 · 동작 = 시작 수를 숫자로 기록 · 배선 = 가드가 `src` 전체를 훑는가(파일 수 출력 ≥ 98 tsx + 8 css).

---

### Task 4: 부품 규격 층 `primitives.css` — 단추·입력·탭·메뉴·툴팁·대화상자·배지·날 것 컨트롤

**적용 스킬:** intranet-style 02-primitives(§0 공통 규약 `data-slot`·`data-size`, §1 Button, §2 Input, §7 Dialog, §11 Select, §12 DropdownMenu, §13 Tabs, §24 Tooltip), web-design-guidelines(Focus States 전 항목, `transition: all` 금지, `overscroll-behavior: contain` 대화상자), design:accessibility-review(초점 링·24px).

**Files:**
- Create: `apps/web/src/styles/primitives.css`, `apps/web/src/styles/primitives.test.ts`
- Modify: `apps/web/src/styles/index.css` — `@import "./theme.css";` 다음 줄에 `@import "./primitives.css";`
- Modify: `apps/web/src/ui-system.test.tsx` — "composes only canonical…" 시험에 `expect(styles).toContain("./primitives.css")` 추가
- Modify: `apps/web/src/styles/product-shell.css` — 앵커 `.vb-product-shell [data-slot=button] { min-height:32px; height:32px; }`, `.vb-product-shell [data-slot=button][data-size="icon"],`, `.vb-product-shell [data-slot=button][data-size="icon-sm"] { width:32px; height:32px; padding:0; }`, `.vb-top-bar__compact-control[data-slot=button] { min-width:2rem; min-height:2rem;`, `.vb-dialog-content { width:min(35rem, calc(100vw - 2rem)); max-width:calc(100vw - 2rem); max-height:70vh;`
- Modify: `apps/web/src/components/ui/capcut-patterns.css`(px 높이 넷을 토큰으로: `▸` 24→`var(--vb-control-xs)`, 칩 28→`var(--vb-control-sm)`, 숫자칸 30→`var(--vb-control-sm)`, 검색 34→`var(--vb-control-md)`) + `capcut-patterns.design-system.test.ts`(시험 `"여기서 쓰는 px 높이는 캡컷 실측 컨트롤 높이뿐이다"`를 `"px 높이를 쓰지 않는다 — 컨트롤 토큰만"`으로: 기대 집합 `[]`, 그리고 `height:\s*var\(--vb-control-(xs|sm|md)\)`가 4번 이상)
- Modify: `apps/web/src/components/ui/dialog.tsx` — 앵커 `<span className="sr-only">Close</span>` → `닫기` (+ 해시 두 곳: `docs/oss/editor-ui-source-map.json`, `docs/oss/shadcn-registry-lock.json`)
- Modify(문구 따라 바꿈): `apps/web/src/app/ProductShell.test.tsx`(191·199행 `name: "Close"`), `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`(4735행), `apps/web/src/styles/product-shell.visual.test.tsx`(53행), `apps/web/e2e/job-recovery.spec.mjs`(25·34행)
- Test: `apps/web/src/styles/theme-tokens.test.ts`("단추 높이가 32px 하나로 통일된다" 교체)

**Interfaces:**
- Consumes: Task 2 토큰.
- Produces: 크기 계약 — `Button size` → 높이: `xs`=24, `sm`=28, `default`=28, `lg`=32, `icon-xs`=24×24, `icon-sm`=28×28, `icon`=28×28, `icon-lg`=32×32. 입력·선택 트리거 28, 탭 목록 28(트리거 24), 메뉴 항목 28, 날 것 컨트롤(`[data-native-control]`) 24. 이후 Task는 이 계약으로 `size`만 고른다.

`primitives.css` 규칙(전부 층 밖, 기본 규칙은 `:where()`로 특정도 0, 크기 규칙은 `[data-slot][data-size]` 속성 선택자 — **`.vb-product-shell` 조상을 쓰지 않는다**):

| 선택자 | 값 |
|---|---|
| `:where([data-slot=button])` | `font: inherit; font-size: var(--vb-text-sm); font-weight: var(--vb-weight-medium); border-radius: var(--vb-radius-sm); gap: var(--vb-space-1); padding-inline: var(--vb-space-3); transition-property: color, background-color, box-shadow, opacity; transition-duration: 120ms;` |
| `[data-slot=button][data-size=xs], [data-size=icon-xs]` / `[data-size=sm], [data-size=default], [data-size=icon], [data-size=icon-sm]` / `[data-size=lg], [data-size=icon-lg]` | `height`·`min-height` = `--vb-control-xs` / `-sm` / `-md`; `icon*`은 `width`도 같게, `padding: 0` |
| `[data-slot=button][data-multiline=true]` | `height: auto` (기존 예외 유지) |
| `[data-slot=button] svg:not([class*=size-])` | `width/height: var(--vb-icon-sm)` |
| `:where([data-slot=input], [data-slot=textarea], [data-slot=select-trigger], [data-slot=native-select])` | `height: var(--vb-control-sm)`(textarea는 `min-height: 4.5rem`), `font-size: var(--vb-text-sm)`, `background: var(--vb-panel-alt)`, `border: 1px solid transparent`, `border-radius: var(--vb-radius-sm)`, `padding-inline: var(--vb-space-2)`, `color: var(--vb-text)`; `::placeholder{color: var(--vb-faint)}`; `@media (max-width: 374px){font-size:1rem}` |
| `[data-slot=tabs-list]` | `height: var(--vb-control-sm); padding: 2px; gap: 2px; border-radius: var(--vb-radius-sm); background: color-mix(in srgb, var(--foreground) 6%, transparent)` |
| `[data-slot=tabs-list][data-variant=line]` | `background: transparent; padding: 0; border-bottom: 1px solid var(--vb-border); border-radius: 0` |
| `[data-slot=tabs-trigger]` | `height: 100%; font-size: var(--vb-text-sm); font-weight: var(--vb-weight-medium); color: var(--vb-muted); border-radius: var(--vb-radius-sm); padding-inline: var(--vb-space-3)` ; `[data-state=active]` → `color: var(--vb-text); background: var(--vb-panel-alt)`; line 변형 active → `background: transparent; box-shadow: inset 0 -2px 0 var(--vb-text)` |
| `[data-slot=dropdown-menu-content], [data-slot=select-content], [data-slot=popover-content]` | `background: var(--popover); color: var(--popover-foreground); padding: var(--vb-space-1); border-radius: var(--vb-radius-md); box-shadow: 0 0 0 1px var(--vb-surface-ring), var(--shadow-lg); z-index: var(--vb-z-popover); min-width: 8rem` |
| `[data-slot=dropdown-menu-item], [data-slot=select-item], [data-slot=dropdown-menu-checkbox-item], [data-slot=dropdown-menu-radio-item]` | `min-height: var(--vb-control-sm); font-size: var(--vb-text-sm); border-radius: var(--vb-radius-sm); padding-inline: var(--vb-space-2)`; `[data-highlighted]` → `background: var(--accent); color: var(--accent-foreground)` |
| `[data-slot=dropdown-menu-label], [data-slot=select-label]` | `font-size: var(--vb-text-xs); color: var(--vb-muted)` |
| `[data-slot=tooltip-content]` | `background: var(--foreground); color: var(--background); font-size: var(--vb-text-xs); padding: var(--vb-space-1) var(--vb-space-2); border-radius: var(--vb-radius-sm); max-width: 20rem; z-index: var(--vb-z-popover)` |
| `[data-slot=dialog-content], [data-slot=sheet-content]` | `display: grid; gap: var(--vb-space-3); padding: var(--vb-space-4); border-radius: var(--vb-radius-lg)`(시트는 0); `max-height: 88vh; overflow-y: auto; overscroll-behavior: contain; box-shadow: 0 0 0 1px var(--vb-surface-ring), var(--shadow-xl); z-index: var(--vb-z-popover)`; `> * { min-width: 0 }`; 대화상자 `width: min(32rem, calc(100vw - 2rem))` |
| `[data-slot=dialog-title], [data-slot=sheet-title]` / `[data-slot=dialog-description]` | `font-size: var(--vb-text-lg); font-weight: var(--vb-weight-strong)` / `font-size: var(--vb-text-sm); color: var(--vb-muted)` |
| `[data-slot=dialog-footer]` | `display: flex; justify-content: flex-end; gap: var(--vb-space-2)`; 그 안 단추는 `lg`(32) |
| `[data-slot=badge]` | `height: 1.25rem; font-size: var(--vb-text-xs); padding-inline: var(--vb-space-2); border-radius: 999px` |
| `:where([data-native-control])` | `font: inherit; font-size: var(--vb-text-xs); min-height: var(--vb-control-xs); min-width: var(--vb-control-xs); border: 0; border-radius: var(--vb-radius-sm); background: transparent; color: var(--vb-text); cursor: pointer` (재생줄·트랙 단추·자르기 손잡이의 `2px outset`·회색·모서리 0을 없앤다 — 감사 3-7. 배치는 H 몫) |
| `:where(button, [role=tab], a, input, select, textarea, [tabindex]):focus-visible` | `outline: var(--vb-focus-outline); outline-offset: var(--vb-focus-offset)` |
| `:where([data-slot=button]):disabled, [aria-disabled=true]` | `opacity: .5; cursor: not-allowed` |

- [ ] **Step 1: 실패하는 시험** — `primitives.test.ts`(파일을 읽고 주석을 걷어 낸 뒤):

```ts
it.each([
  ["xs","--vb-control-xs"],["sm","--vb-control-sm"],["default","--vb-control-sm"],["lg","--vb-control-md"],
  ["icon-xs","--vb-control-xs"],["icon-sm","--vb-control-sm"],["icon","--vb-control-sm"],["icon-lg","--vb-control-md"],
])("Button size=%s 높이는 %s", (size, token) => {
  const rule = css.match(new RegExp(`[^}]*\\[data-size=["']?${size}["']?\\][^{]*\\{[^}]*\\}`))?.[0] ?? ""
  expect(rule).toContain(`height: var(${token})`)
})
it("포털 표면 규칙은 .vb-product-shell 조상을 요구하지 않는다", () => expect(css).not.toContain(".vb-product-shell"))
it("대화상자는 격자이고 자식이 줄어들 수 있고 최대 88vh다", () => {
  expect(css).toMatch(/\[data-slot=dialog-content\][^{]*\{[^}]*display:\s*grid[^}]*max-height:\s*88vh/)
  expect(css).toMatch(/\[data-slot=dialog-content\]\s*>\s*\*\s*\{[^}]*min-width:\s*0/)
})
it("날 것 컨트롤이 글꼴을 물려받고 테두리가 없다", () => expect(css).toMatch(/:where\(\[data-native-control\]\)\s*\{[^}]*font:\s*inherit[^}]*border:\s*0/))
it("초점은 2px 주황 외곽선이다", () => expect(css).toMatch(/:focus-visible\s*\{[^}]*outline:\s*var\(--vb-focus-outline\)/))
it("transition: all을 쓰지 않는다", () => expect(css).not.toMatch(/transition:\s*all/))
```
그리고 `theme-tokens.test.ts`의 `"단추 높이가 32px 하나로 통일된다"`를 `"단추 높이는 size별 세 단계다 — product-shell.css에 32px 못박이가 없다"`로 바꿔 `expect(productShellCss).not.toMatch(/\[data-slot=button\]\s*\{[^}]*height:\s*32px/)`.

- [ ] **Step 2: RED** — `cd apps/web && npx vitest run src/styles/primitives.test.ts` → FAIL(파일 없음 → ENOENT). `npx vitest run src/styles/theme-tokens.test.ts -t "세 단계"` → FAIL(32px 규칙이 아직 있음).

- [ ] **Step 3: 구현** — 위 표대로 `primitives.css`. `index.css`에 import. `product-shell.css`의 위 앵커 규칙 넷을 지우고(`.vb-top-bar__compact-control`은 `min-width/min-height`를 `var(--vb-control-sm)`로, 768px 미만 규칙의 `2.25rem`도 `var(--vb-control-md)`로), `.vb-dialog-content`의 폭·최대 높이·패딩은 지운다(primitives가 맡는다. 클래스는 남겨 둔다 — 시험이 이름을 본다). `capcut-patterns.css` 두 높이를 토큰으로. `dialog.tsx` `Close`→`닫기`, 해시 두 곳 교체, 문구 단언 다섯 곳 `"닫기"`로.

- [ ] **Step 4: GREEN** — `npx vitest run src/styles/primitives.test.ts src/styles/theme-tokens.test.ts src/components/ui/capcut-patterns.design-system.test.ts src/styles/product-shell.visual.test.tsx src/app/ProductShell.test.tsx` PASS, `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_editor_ui_source_provenance.py` PASS, `powershell -File scripts/verify-editor-ui-source-provenance.ps1` exit 0.

- [ ] **Step 5: 넓게** — `cd apps/web && npx vitest run && npx tsc --noEmit`(약 4~6분). 실패가 "높이·크기 px 단언"이면 새 계약 값으로, 문구면 `닫기`로 고친다. 그 밖은 멈추고 원인부터.

- [ ] **Step 6: 가드 기준선 내리기**(Task 3 Step 3 명령) + 커밋

```bash
git add apps/web/src/styles apps/web/src/ui-system.test.tsx apps/web/src/components/ui/capcut-patterns.* apps/web/src/components/ui/dialog.tsx docs/oss/editor-ui-source-map.json docs/oss/shadcn-registry-lock.json apps/web/src/app/ProductShell.test.tsx apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx apps/web/e2e/job-recovery.spec.mjs
git commit -m "feat(web): 부품 규격 층 — 단추 24/28/32·입력·탭·메뉴·툴팁·대화상자 격자, 날 것 컨트롤 글꼴, 닫기 한국어"
```

**검증 넷:** 갭 = 표의 선택자 전부가 파일에 있는가, 안 한 것(시트 세부·배지 변형)을 적는다 · 역방향 = Vite 개발 서버에서 `작업 상태` 대화상자를 열어 `getComputedStyle(dialog).display === "grid"`, 닫기 단추 이름 `닫기` · 동작 = 편집기 재생줄 단추 `font-family` Pretendard·`border-top-style` none(JS) · 배선 = `grep -c "data-slot=" apps/web/src/styles/primitives.css` ≥ 20, `grep -rn "primitives.css" apps/web/src/styles/index.css` 1.

---

### Task 5: 누르면 반드시 반응 — 피드백 한 가지와 잠긴 이유

**적용 스킬:** design:ux-copy(진행·완료·실패 문구 틀), web-design-guidelines(Forms: "Submit button stays enabled until request starts; spinner during request", Async updates `aria-live="polite"`, Error messages include fix/next step), intranet-style 04 §8-7(로딩 중 `disabled` + 아이콘 회전, 토스트 `toast.success/error`), design:accessibility-review.

**무늬(이 저장소에서 하나뿐이다 — 새 방식을 만들지 않는다):**
1. **누르는 순간**: 단추가 즉시 `aria-busy="true"`·`disabled`가 되고 이름이 `…하는 중…`으로 바뀐다(예: `분석 시작` → `분석하는 중…`).
2. **1초 넘게 걸리는 일**: 이미 있는 작업+폴링 표시(`role=status` 줄, 진행 막대)를 그대로 쓴다(기억 메모 "기다림에는 항상 표시": 세 번째 방식을 만들지 않는다).
3. **끝남**: 결과가 **같은 화면에 보이면** 알림 없음(목록이 바뀌는 것이 알림이다). 결과가 **안 보이는 곳**에 생기면(다른 화면, 파일 저장, 백그라운드) 토스트 `…했어요` 3초.
4. **실패**: 토스트 `…하지 못했어요. <다음 행동>` + 단추는 다시 눌러지는 상태로 돌아온다. 같은 문장을 `role=status` 줄에도 남긴다(토스트가 사라져도 남게).
5. **조건 때문에 못 누름**: 회색으로만 두지 않는다. 단추 아래(또는 묶음 아래) 11px 흐린 글자로 이유 한 문장(`…하면 눌러져요.`) + `aria-describedby` 연결.

**Files:**
- Create: `apps/web/src/features/shell/useActionFeedback.ts`, `apps/web/src/features/shell/DisabledReason.tsx`, `apps/web/src/features/shell/feedback.test.tsx`
- Modify: `apps/web/src/app/AppRoot.tsx` — 앵커 `<AppRouter />` 뒤에 `<Toaster theme="dark" position="bottom-right" richColors={false} closeButton={false} duration={3000} />` (`components/ui/sonner.tsx`는 고치지 않는다 — prop으로만)
- Modify: `apps/web/src/components/ui/button.tsx` — 앵커 `defaultVariants: {\n      variant: "default",` → `variant: "outline",` (+ 해시 두 곳) — **D2 승인 시에만**
- Modify(이유 문장 달기, 편집기 밖 소유 화면): `features/footage/FootageOrganizerPage.tsx`, `features/footage/SceneTimeline.tsx`, `features/library/LibraryPreviewPane.tsx`, `app/OutputsPage.tsx`, `features/creation/CreationInterview.tsx`, `features/creation/{VoiceRecordStart,SourceVideoStart,YujinScriptStart}.tsx`, `features/settings/VoiceTtsSettings.tsx`, `features/media/{MediaAnalysisStatusPanel,SceneImageStudio,ImportFromFootageInbox}.tsx`, `features/review/TimelineReviewPage.tsx`, `features/yujin/YujinStarters.tsx`, `features/voices/MyVoicesPage.tsx`, `features/projects/ProjectTitleDialog.tsx`, `features/jobs/JobRecovery.tsx`, `features/footage/FootageSuggestions.tsx`, `app/AppRouter.tsx` (편집기 파일은 Task 10)
- CSS: `primitives.css`에 `.vb-disabled-reason { font-size: var(--vb-text-xs); color: var(--vb-muted); margin: var(--vb-space-1) 0 0; }`

**Interfaces:**
- Produces:
  - `export function useActionFeedback(): { busy: boolean; run<T>(copy: { pending: string; done?: string; failed: string }, action: () => Promise<T>): Promise<T | undefined>; label(idle: string): string; lastError: string | null }` — `done`이 없으면 토스트를 띄우지 않는다(결과가 화면에 보이는 경우). `label(idle)`은 바쁠 때 `copy.pending`을 돌려준다. 실패는 `toast.error(copy.failed)` + `lastError` 설정. 예외는 삼키고 `undefined`를 돌려준다(화면이 죽지 않게).
  - `export function DisabledReason({ id, reason }: { id: string; reason: string | null }): JSX.Element | null` — `reason`이 `null`이면 아무것도 안 그린다. 그리면 `<p id={id} className="vb-disabled-reason">{reason}</p>`.
  - 사용 규칙: `<Button disabled={!!reason} aria-describedby={reason ? id : undefined}>…</Button><DisabledReason id={id} reason={reason} />` — `reason`은 조건마다 한 문장. `useId()`로 id.

- [ ] **Step 1: 실패하는 시험** — `feedback.test.tsx`:

```tsx
it("누르는 순간 바쁨 표시로 바뀌고 끝나면 돌아온다", async () => { /* run 중 label("분석 시작") === "분석하는 중…", 끝나면 "분석 시작" */ })
it("결과가 화면 밖이면 완료 토스트를 띄운다", async () => { /* done:"저장했어요" → toast.success 호출(vi.mock("sonner")) */ })
it("결과가 화면에 보이면 완료 토스트를 띄우지 않는다", async () => { /* done 없음 → toast.success 미호출 */ })
it("실패하면 다음 행동이 담긴 토스트를 띄우고 다시 누를 수 있다", async () => { /* failed:"분석하지 못했어요. 잠시 뒤 다시 눌러 주세요." → toast.error 그 문장, busy false */ })
it("조건 때문에 잠긴 단추는 이유 문장과 연결된다", () => {
  render(<><Button disabled aria-describedby="r1">분석 시작</Button><DisabledReason id="r1" reason="촬영본을 하나 이상 고르면 눌러져요." /></>)
  expect(screen.getByRole("button", { name: "분석 시작" })).toHaveAccessibleDescription("촬영본을 하나 이상 고르면 눌러져요.")
})
```
그리고 `apps/web/src/features/footage/FootageOrganizerPage.test.tsx`에 `it("아무것도 고르지 않았을 때 잠긴 단추 일곱이 모두 이유를 말한다")` — 화면을 그린 뒤 위 W-04의 `/footage` 일곱 단추 각각 `toHaveAccessibleDescription(/눌러져요\.$/)`.

- [ ] **Step 2: RED** — `cd apps/web && npx vitest run src/features/shell/feedback.test.tsx` → FAIL(모듈 없음). `npx vitest run src/features/footage/FootageOrganizerPage.test.tsx -t "일곱"` → FAIL(설명 없음).

- [ ] **Step 3: 구현** — 훅·부품·Toaster 장착. 그다음 위 파일 목록의 `tsx-disabled-no-reason` 위반을 하나씩: 조건식을 읽고 `reason`을 만든다. 문구 틀: `<무엇을> 하면 눌러져요.` / `<무엇이> 끝나면 눌러져요.` / `<무엇이> 없어서 지금은 못 해요. <대신 할 일>`. 계획 작성 시 확인된 문장: `분석 시작` = `촬영본을 하나 이상 고르면 눌러져요.`; `유진에게 제안 요청` = `무엇을 할지 적으면 눌러져요.`; `제안 미리보기`·`제안 취소`·`제안 적용` = `유진에게 제안을 받으면 눌러져요.`; `선택 장면으로 가상 묶음 만들기`·`새 클립 파일로 만들기` = `장면을 하나 이상 고르면 눌러져요.`; `앞 경계 −1f`류(Task 8이 이름을 바꾼다) = `장면을 고르면 눌러져요.` — 실제 조건식이 다르면 **조건식이 맞다**(문장을 고친다). 결과가 다른 곳에 생기는 단추(예: `새 클립 파일로 만들기` → 자료실에 생김)는 `run({pending:"만드는 중…", done:"자료실에 새 클립을 넣었어요", failed:"클립을 만들지 못했어요. 잠시 뒤 다시 눌러 주세요."}, …)`로 감싼다.
  D2가 승인됐으면 `button.tsx` 기본 변형을 `outline`으로 바꾸고 해시를 고친 뒤, 각 화면의 주 동작 하나에 `variant="default" data-primary-action`을 단다(Task 6이 화면 목록을 정한다 — 이 Task에서는 기본값만).

- [ ] **Step 4: GREEN** — 위 두 시험 PASS. 가드 `tsx-disabled-no-reason`에서 이 Task 파일들이 0인지: `npx vitest run src/styles/design-guard.test.ts` 후 기준선 다시 쓰기, `git diff src/styles/design-guard.baseline.json`에서 해당 파일 줄이 **사라졌는지**.

- [ ] **Step 5: 넓게** — `npx vitest run src/features src/app` + `npx vitest run src/user-copy-policy.test.ts`. D2로 기본 변형을 바꿨다면 `variant` 단언 시험이 깨질 수 있다 — 화면 의미가 "주 동작"이면 `variant="default"`를 명시하고, 아니면 단언을 `outline`으로.

- [ ] **Step 6: 커밋** — `git commit -m "feat(web): 누름→진행→결과 한 가지 무늬, 잠긴 단추는 이유를 말한다(편집기 밖 N곳)"` (N은 실제 수)

**검증 넷:** 갭 = 무늬 5단계가 훅·부품·문서(Task 14 규칙)로 다 갔는가 · 역방향 = 개발 서버 `/footage`에서 일곱 단추의 `aria-describedby` 대상 글자를 JS로 읽음 · 동작 = 이유 없는 비활성 수(편집기 밖) 0 · 배선 = `grep -rn "useActionFeedback\|DisabledReason" apps/web/src --include=*.tsx | grep -v test | wc -l` 이 고친 파일 수 이상, `grep -n "Toaster" apps/web/src/app/AppRoot.tsx` 1.

---

### Task 6: 셸과 화면 머리 — 넓게, 낮게, 주 동작 하나

**적용 스킬:** intranet-style 03-shell-layout(§3 헤더, §4-1 콘텐츠 패딩 표, §7 반응형), 04-page-templates(§0 루트 `space-y-4`, §8-1 레이아웃 do/don't, §8-6 타이포 역할표, §8-6a 설명 `<p>` 정본), design:ux-copy(화면 설명 한 줄), no-ai-design-slop(제목 크기로 위계를 만들지 않는다).

**Files:**
- Modify: `apps/web/src/styles/product-shell.css` — 앵커 `.vb-product-content { width:100%; max-width:1200px; min-height:0; margin: 0 auto; padding: var(--vb-space-7) clamp(var(--vb-space-4),3vw,var(--vb-space-8)); }`, `@media (min-width:1600px) { .vb-product-content { max-width:1600px; } }`, `.vb-home h1, .vb-settings h1 {`, `.vb-catalog h1 {`, `.vb-eyebrow {`, 그리고 `vb-side-nav`·`vb-top-bar` 규칙들(`grep -n "vb-side-nav\|vb-top-bar" apps/web/src/styles/product-shell.css`)
- Modify(주 동작 표시 `data-primary-action`, `variant="default"`): `app/AppRouter.tsx`(`+ 새로 만들기`, 392행 부근 앵커 `{quickStartBusy ? "편집판을 여는 중" : "+ 새로 만들기"}`), `features/library/AssetIngestDropzone.tsx`(`파일 추가`), `features/footage/FootageOrganizerPage.tsx`(`분석 시작`), `features/voices/MyVoicesPage.tsx`(새 목소리 녹음/추가 단추 — 파일을 읽고 "새로 만드는" 단추 하나), `features/creation/CreationInterview.tsx`(`유진과 기획 시작`), `app/OutputsPage.tsx`(앵커 `"완성본 만들기"` 를 그리는 `<Button disabled={!canRenderFinal`), `features/editor/workbench/EditorWorkbench.tsx`(앵커 `title="내보내기 — 완성`) — 설정 화면은 주 동작 **없음**
- Test: `apps/web/src/app/product-shell-layout.test.tsx`(새로)

**Interfaces:**
- Consumes: Task 2 `--vb-page-pad-*`, `--vb-top-bar-h`, `--vb-side-nav-w`; Task 4 크기 계약.
- Produces: 화면 머리 계약 — 화면마다 `h1`(20px/600) 하나 + 바로 아래 설명 `<p>`(12px, `--vb-muted`, 최대 40rem) + 주 동작 단추 0~1개(`data-primary-action`). Task 12 게이트가 "보이는 `[data-primary-action]` 수 = 1(설정 0)"을 잰다.

- [ ] **Step 1: 실패하는 시험** — `product-shell-layout.test.tsx`(CSS 정적 + 렌더):

```tsx
it("콘텐츠에 최대폭이 없고 패딩이 밀도 토큰이다", () => {
  const rule = css.match(/\.vb-product-content\s*\{[^}]*\}/)?.[0] ?? ""
  expect(rule).not.toMatch(/max-width:\s*1200px/); expect(rule).toContain("padding: var(--vb-page-pad-y) var(--vb-page-pad-x)")
  expect(css).not.toMatch(/max-width:\s*1600px/)
})
it("화면 제목은 20px/600 한 규칙이다", () => {
  expect(css).toMatch(/\.vb-product-content h1\s*\{[^}]*font-size:\s*var\(--vb-text-2xl\)[^}]*font-weight:\s*var\(--vb-weight-strong\)/)
  expect(css).not.toMatch(/clamp\(var\(--vb-text-2xl\),3vw,var\(--vb-text-3xl\)\)/)
})
it.each([
  ["app/AppRouter.tsx", 2],              // `+ 새로 만들기`, 라우터 오류 화면(Task 11이 하나 더한다 → Task 11에서 2로 올린다; 이 Task에서는 1)
  ["features/library/AssetIngestDropzone.tsx", 1], ["features/footage/FootageOrganizerPage.tsx", 1],
  ["features/voices/MyVoicesPage.tsx", 1], ["features/creation/CreationInterview.tsx", 1],
  ["app/OutputsPage.tsx", 1], ["features/editor/workbench/EditorWorkbench.tsx", 1],
])("%s에 주 동작 표시가 %i개다", (file, count) => {
  const src = readFileSync(resolve(process.cwd(), "src", file), "utf8")
  expect(src.match(/data-primary-action/g) ?? []).toHaveLength(count)
})
```
(화면에 **보이는** 수가 1인지는 Task 12 게이트가 실제 브라우저에서 잰다. 여기서는 소스에 표시가 붙었는지만 본다. 이 Task에서는 `AppRouter.tsx` 기대를 1로 두고, Task 11이 오류 화면 단추를 더할 때 2로 올린다.)

- [ ] **Step 2: RED** — `npx vitest run src/app/product-shell-layout.test.tsx` → FAIL(1200px 있음).

- [ ] **Step 3: 구현**
  - `.vb-product-content`: `max-width:none; padding: var(--vb-page-pad-y) var(--vb-page-pad-x);` 1600 미디어 규칙 삭제. 긴 문단만 `max-width: 40rem`(기존 `.vb-catalog > p` 규칙 유지).
  - 제목: `.vb-home h1, .vb-settings h1`·`.vb-catalog h1`의 `clamp(...)`를 지우고 공용 `.vb-product-content h1 { margin: 0 0 var(--vb-space-1); font-size: var(--vb-text-2xl); line-height: var(--vb-leading-2xl); font-weight: var(--vb-weight-strong); letter-spacing: -0.01em; }`, `.vb-product-content h2 { font-size: var(--vb-text-xl); font-weight: var(--vb-weight-strong); margin: 0; }`, `h3 { font-size: var(--vb-text-lg); … }`(브라우저 기본 24px h2가 카드 제목으로 새던 원인 — 기준선 `/projects` 24px/700 ×73).
  - `.vb-eyebrow`: `font-size: var(--vb-text-xs); font-weight: var(--vb-weight-medium); color: var(--vb-muted)` — **주황을 뺀다**(D2와 같은 "주황은 주 동작·선택 표시에만" 규칙; D2가 거절되면 이 한 줄은 `--vb-accent` 그대로 둔다).
  - 위 띠: 높이 `var(--vb-top-bar-h)`, 안 단추 `size="sm"`(28). 왼쪽 메뉴: 폭 `var(--vb-side-nav-w)`, 항목 `min-height: var(--vb-control-sm); font-size: var(--vb-text-sm)`, 구역 이름 `--vb-text-xs`.
  - 화면별 주 동작에 `data-primary-action`(+D2면 `variant="default"`, 같은 화면의 다른 `default` 단추는 `outline`). 설명 `<p>`가 없는 화면(촬영본 정리는 있음, 자료실은 사이드 제목 아래 `모든 프로젝트 공용` eyebrow뿐)에 한 줄을 더한다: 자료실 `한 번 넣은 영상·음악·그림을 모든 프로젝트에서 다시 써요.`, 프로젝트 `만들던 영상을 이어서 편집하거나 새로 시작해요.`, 내 목소리 `녹음한 내 목소리로 내레이션을 읽어요.`.

- [ ] **Step 4: GREEN** — 위 시험 PASS, `npx vitest run src/styles src/app src/features/shell`.

- [ ] **Step 5: 가드 기준선 내리기 + 커밋** — `git commit -m "feat(web): 셸을 넓고 낮게 — 최대폭 없앰·위 띠 44·메뉴 28, 화면 제목 20/600, 화면마다 주 동작 하나"`

**검증 넷:** 갭 = 주 동작 표가 화면 7개(설정 제외) 다 됐는가 · 역방향 = 개발 서버 1440×900 `/projects`에서 `.vb-product-content` 폭 = 창 폭 − 메뉴 폭(1264±2) · 동작 = 위 띠 높이 44, 제목 20px · 배선 = `grep -rn "data-primary-action" apps/web/src --include=*.tsx | grep -v test | wc -l` = 7.

---

### Task 7: `/projects` — 조밀한 카드 격자

**적용 스킬:** intranet-style 04 유형 3(목록형, §3-4 검색, §3-6 상태 화면, §7-7 빈 상태 L), 01 §3.5(`truncate` + `min-w-0`), design:ux-copy(카드 메타 한 줄), no-ai-design-slop(카드마다 큰 단추 금지 — 캡컷 "버튼 없는 카드", `docs/capcut-full-adoption-plan-2026-09-04.ko.md` §7-7).

**전제:** G Task 2(그림 자리)·G Task 3(`+ 새로 만들기` 칸)이 main에 있다(Task 0 Step 1 기록). 없으면 그 두 자리는 건드리지 않는다.

**Files:**
- Modify: `apps/web/src/styles/product-shell.css` — 앵커 `.vb-catalog-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(14rem,1fr)); gap: var(--vb-space-4); margin-top: var(--vb-space-7); }`, `.vb-catalog-card { height:auto; min-height:6rem; padding: var(--vb-space-5);`, `.vb-catalog-card__manage [data-slot=button] {`, `.vb-catalog-card__meta`(grep), `font-weight:650`(카탈로그 블록 안)
- Test: `apps/web/src/app/catalog-card-quiet.test.tsx`(기존 파일에 시험 추가)

**Interfaces:** Consumes: Task 2·4·6 토큰과 계약.

목표 값: 격자 `grid-template-columns: repeat(auto-fill, minmax(12.5rem, 1fr)); gap: var(--vb-grid-gap); margin-top: var(--vb-space-4)`; 카드 `padding: var(--vb-card-pad); border-radius: var(--vb-radius-md); font-size: var(--vb-text-sm); font-weight: var(--vb-weight-regular)`; 카드 제목(그 안 `h2`/링크) `font-size: var(--vb-text-md); font-weight: var(--vb-weight-strong); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0`; 메타 `font-size: var(--vb-text-xs); font-weight: var(--vb-weight-regular); color: var(--vb-muted)`; 카드 안 `검토하기`·`계속 만들기` 단추 `size="sm"`(28), `···` `size="icon-sm"` + `aria-label="프로젝트 관리"`(기존 이름 확인 후 유지); 그림 자리(G2) `aspect-ratio: 16 / 9`.

- [ ] **Step 1: 실패하는 시험** — `it("카드 격자 열 최소는 12.5rem이고 카드 패딩은 밀도 토큰이다")`(CSS 정적), `it("긴 이름은 한 줄 말줄임이다")`(`.vb-catalog-card` 제목 규칙에 `text-overflow: ellipsis` + `min-width: 0`), `it("카드 글자에 650·700 굵기가 없다")`.
- [ ] **Step 2: RED** — `npx vitest run src/app/catalog-card-quiet.test.tsx -t "12.5rem"` → FAIL(14rem).
- [ ] **Step 3: 구현** — 위 목표 값. 보관함 보기·격자/줄 보기 토글은 `size="icon-sm"` + 기존 `aria-label`. 빈 목록 문구(`아직 만든 영상이 없어요. + 새로 만들기로 시작해 보세요.`)는 유지하고 빈 상태 L 틀(아이콘 24 + 한 줄)로.
- [ ] **Step 4: GREEN** — 그 파일 + `src/app/catalog-lazy-summary.test.tsx` + `src/app/AppRouter.test.tsx`.
- [ ] **Step 5: 기준선 내리기 + 커밋** — `git commit -m "feat(web): 프로젝트 카드 조밀하게 — 1440에서 6열, 제목 13/600 한 줄, 메타 11"`

**검증 넷:** 갭 = 목표 값 표 대조 · 역방향 = 개발 서버 1440×900에서 첫 줄 카드 수 ≥ 6, 카드 높이 차이 0(같은 줄) · 동작 = 카드 제목 13px·한 줄, `+ 새로 만들기` 칸 높이 = 카드 높이(G3 뒤) · 배선 = 카드 클릭이 여전히 편집기로 간다(기존 `AppRouter.test.tsx` 해당 시험 PASS).

---

### Task 8: `/library`·`/footage` — 3칸 작업 화면 조밀화, 대비, 내부 이름 감추기

**적용 스킬:** intranet-style 04 유형 2(2패널 §2-1~2-5: 좌 고정폭·우 `min-w-0`·슬림 스크롤·상태 4분기), 01 §3.5, design:ux-copy(`fps`·`−1f`·내부 id를 대표님 말로), design:accessibility-review(대비 4.5:1).

**Files:**
- Modify: `apps/web/src/features/library/library.css`, `apps/web/src/features/footage/footage.css` (가드 기준선의 두 파일 위반 전부)
- Modify: `apps/web/src/features/library/LibraryResults.tsx`(검색 `data-native-control="library-search"` 입력은 날 것 그대로 두고 규격은 Task 4 `[data-native-control]`·이 Task CSS가 맡는다), `features/library/LibrarySidebar.tsx`(필터 항목)
- Modify: `apps/web/src/features/footage/FootageSourceList.tsx`(촬영본 이름 표시), `features/footage/SceneTimeline.tsx`(앵커 `앞 경계 −1f`·`뒤 경계 +1f`), `features/footage/FootagePreview.tsx`(앵커 `fps`·`프레임 간격`·`−1f`·`+1f`)
- Test: `apps/web/src/features/library/LibraryPage.test.tsx`, `apps/web/src/features/footage/FootageOrganizerPage.test.tsx`, `apps/web/src/styles/contrast.test.ts`

**Interfaces:**
- Produces: `export function displayFootageName(name: string): string` in `apps/web/src/features/footage/displayFootageName.ts` — `derived:`로 시작하거나 `_job_`/32자 이상 16진수가 들어간 이름이면 `정리해서 만든 클립`(+ 같은 이름이 여럿이면 ` 2`, ` 3`은 호출부가 붙이지 않는다 — 한 함수는 이름만), 아니면 원래 이름.

목표 값: 자료실 3칸 `grid-template-columns: var(--vb-side-nav-w) minmax(0,1fr) 18rem; gap: var(--vb-grid-gap)`; 영상 격자 `repeat(auto-fill, minmax(8.5rem, 1fr))`; 영상 카드 몸통 `padding: var(--vb-space-2)`, 이름 `--vb-text-sm` 한 줄 말줄임, 길이 배지 `--vb-text-xs` `tabular-nums`; 필터 항목 `min-height: var(--vb-control-sm); font-size: var(--vb-text-sm)`; 검색 입력 `height: var(--vb-control-sm); font-size: var(--vb-text-sm)`(지금 10px); 촬영본 행 이름 `--vb-text-sm`/500, 메타 `--vb-text-xs`; 650·700 굵기 → 500/600; 18.4px·10.4px 패딩 → `--vb-space-3`/`--vb-space-2`.
대비: `--vb-accent-bg` 바탕 위 글자는 `--vb-text`만(지금 주황·흐림 글자 — 실측 4.27·4.44). 문구: `앞 경계 −1f`→`시작 1프레임 앞으로`, `뒤 경계 +1f`→`끝 1프레임 뒤로`, `fps`→`초당 장면 수`, `−1f`/`+1f` 단추 → `이전 프레임`/`다음 프레임`(아이콘 단추면 `aria-label`로).

- [ ] **Step 1: 실패하는 시험**
  - `contrast.test.ts`: `it("주황 바탕(--vb-accent-bg) 위 글자는 본문색만 4.5:1을 넘는다 — 주황·흐림 글자는 쓰지 않는다")` → `expect(contrastRatio(APPROVED.accent, APPROVED.accentBg)).toBeLessThan(4.5)`(사실 고정) + CSS 정적: 세 스타일시트에서 `background(-color)?:\s*var\(--vb-accent-bg\)`가 있는 규칙 블록 안에 `color:\s*var\(--vb-(accent|faint)\)`가 없다.
  - `displayFootageName.test.ts`: `derived:footage_render_job_7e195e9e4a2e45a19a01a34cbb17d134` → `정리해서 만든 클립`, `20241208_121938.mp4` → 그대로, `화면 녹화 중 2026-02-07 164438.mp4` → 그대로.
  - `FootageOrganizerPage.test.tsx`: `it("화면에 fps·−1f·derived: 가 보이지 않는다")`(`container.textContent`와 모든 `aria-label`).
  - `LibraryPage.test.tsx`: `it("영상 카드 이름은 한 줄 말줄임이다")`(CSS 정적: `.vb-library-video-card__body` 이름 규칙).
- [ ] **Step 2: RED** — 각 시험 하나씩 돌려 FAIL 확인(contrast 정적 규칙은 `library.css`에서 걸려야 한다 — 안 걸리면 실제 주황 글자가 어느 파일 규칙인지 기준선 JSON(Task 0)에서 찾아 시험 대상을 고친다).
- [ ] **Step 3: 구현** — 목표 값 + 문구 + `displayFootageName`을 `FootageSourceList.tsx`가 이름을 그리는 자리에서 호출(원래 이름은 `title` 속성으로 남긴다 — 무엇인지 확인할 길).
- [ ] **Step 4: GREEN** — 위 시험 + `src/features/library` + `src/features/footage` + `src/user-copy-policy.test.ts`.
- [ ] **Step 5: 기준선 내리기 + 커밋** — `git commit -m "feat(web): 자료실·촬영본 정리 조밀하게 — 5열 카드·28px 필터·12px 검색, 주황 바탕 글자 대비, 내부 이름·fps 감춤"`

**검증 넷:** 갭 = 목표 값·문구 표 대조 · 역방향 = 개발 서버 1440×900 `/library` 영상 카드 열 수 ≥ 5, `/footage` 본문에 `derived:` 0 · 동작 = 검색 입력 글자 12px, 필터 높이 28 · 배선 = `grep -rn "displayFootageName" apps/web/src --include=*.tsx | grep -v test` ≥ 1.

---

### Task 9: `/settings`·`/voices`·`/projects/:id/create`·`/projects/:id/review` — 탭과 폼 틀

**적용 스킬:** intranet-style 04 유형 5(§5-1 설정 = 카드 하나에 설정 하나, §5-2 상태 배지, §5-4a 대화상자 바닥), 02 §13 Tabs(세로 지원), 유형 6(리포트 카드), design:ux-copy, design:accessibility-review(`role=tab`·`tabpanel` 짝).

**Files:**
- Modify: `apps/web/src/app/ProductShell.tsx` — 앵커 `<div className="vb-settings-nav">{(Object.keys(labels)`(설정 섹션 단추 묶음) → `Tabs`/`TabsList`/`TabsTrigger`(세로, `onValueChange`가 기존 `onNavigate` 호출), 앵커 `<SettingToggle label="조밀한 화면"` (D3: 없앰 — `SettingsState`의 `compact`와 `data-compact` 속성·`product-shell.css`의 `.vb-product-shell[data-compact="true"]` 규칙 넷도 같이), **해시 두 곳**(`docs/oss/editor-ui-source-map.json` `normalized_sha256` 2회)
- Modify: `apps/web/src/app/ProductShell.test.tsx`(249·402~426·467~471행 `조밀한 화면` 시험 — D3 없앰이면 "조밀한 화면 토글이 없다"로 바꾸고, `localStorage`에 옛 `compact:true`가 있어도 화면이 깨지지 않는다를 단언), `apps/web/src/features/voices/MyVoicesPage.tsx`(폼 틀: 카드 하나에 목소리 하나, 단추 `size="sm"`), `apps/web/src/features/creation/CreationInterview.tsx`(질문 화면 폭 40rem, 입력 28, 단추 줄 오른쪽), `apps/web/src/app/OutputsPage.tsx`(앵커 `vb-home-grid vb-outputs-grid` — 카드 격자 `minmax(16rem,1fr)`, 카드 제목 `--vb-text-lg`/600, 반복 안내는 G9 결과 유지)
- Test: `apps/web/src/app/ProductShell.test.tsx`, `apps/web/src/app/OutputsPage.test.tsx`

**Interfaces:** Consumes: Task 4 탭 규격(`[data-slot=tabs-list][data-orientation=vertical]`은 이 Task에서 primitives.css에 더한다: `flex-direction: column; height: auto; align-items: stretch;` 트리거 `justify-content: flex-start; height: var(--vb-control-sm)`).

- [ ] **Step 1: 실패하는 시험** — `it("설정 섹션은 탭이고 지금 섹션이 선택돼 있다")`: `getByRole("tablist", { name: "설정 섹션" })`, `getByRole("tab", { name: "화면", selected: true })`, 탭을 누르면 `onNavigate("conversations")` 호출, `getByRole("tabpanel")`이 선택된 탭과 `aria-labelledby`로 이어짐. D3면 `it("조밀한 화면 토글이 없다")` + `it("옛 compact 설정이 저장돼 있어도 화면이 그려진다")`.
- [ ] **Step 2: RED** — `npx vitest run src/app/ProductShell.test.tsx -t "탭이고"` → FAIL(tablist 없음).
- [ ] **Step 3: 구현** — 위 목록. G7이 이미 3칸으로 줄였으면 그 셋으로, 아니면 5칸 그대로. 옛 주소(`/settings/general`·`/ai-privacy`·`/voice`·`/output`)가 계속 화면을 그리는지 그대로 둔다(G 경계). 해시 두 곳 교체 후 provenance 시험.
- [ ] **Step 4: GREEN** — 위 시험 + `src/app` 전체 + `tests/test_editor_ui_source_provenance.py` + `src/user-copy-policy.test.ts`.
- [ ] **Step 5: 기준선 내리기 + 커밋** — `git commit -m "feat(web): 설정 섹션을 세로 탭으로, 조밀한 화면 토글 정리, 목소리·기획·검토 화면을 폼·카드 틀로"`

**검증 넷:** 갭 = 네 화면 각각 바꾼 것/안 바꾼 것 · 역방향 = 개발 서버에서 `/settings/appearance` 탭을 키보드(↑↓)로 옮겨 주소가 바뀜 · 동작 = 탭 트리거 높이 28, 화면 제목 20px · 배선 = `grep -n "조밀한 화면\|data-compact" -r apps/web/src --include=*.tsx --include=*.css | grep -v test` = 0(D3 없앰일 때).

---

### Task 10: 편집기 크롬 정리 (H 다음)

**적용 스킬:** intranet-style 02 §13(세로 탭·line 탭), 04 §8-2(아이콘 크기), web-design-guidelines(아이콘 단추 `aria-label`, 탭에 `tabpanel`), design:accessibility-review, design:ux-copy(`Clean`·`Highlight`·백틱), no-ai-design-slop(한 화면 주황 38개 → 하나).

**전제:** H가 main에 있다. 앵커가 없으면 Global 규칙대로 멈추고 H의 새 모양을 확인한다.

**Files:**
- Modify: `apps/web/src/styles/editor-workbench.css`(가드 기준선의 이 파일 위반 전부: 픽셀 높이 23·25·27·30·36·40 → 컨트롤 토큰, `font-size`·굵기·모서리 리터럴)
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbench.tsx`(왼쪽 레일 탭 이름·`tabpanel` 짝 — 앵커 `aria-label="왼쪽 패널"`), `features/editor/inspector/InspectorControls.tsx`(하위 탭 `화면`·`소리`·`속도`·`보정`·캡션 탭은 Radix가 아니라 손으로 만든 `role="tablist"` — 앵커 `className="vb-inspector-tabs" role="tablist"` 두 곳(698행 `` aria-label={`${target.label} 조정 항목`} ``, 1035행 `aria-label="캡션 조정 항목"`). 마크업은 그대로 두고 목록 `div`에 `data-slot="tabs-list" data-variant="line"`, 각 탭 단추에 `data-slot="tabs-trigger"`와 `data-state={selected ? "active" : "inactive"}`를 달아 Task 4 규격을 받게 한다. 탭마다 `aria-controls`↔`role="tabpanel"` 짝도 여기서), `features/editor/workbench/RightDock.tsx`(편집 대상 옵션 이름에 장면 번호 — H가 바꾼 모양 위에서 `연결 캡션` → `장면 N 캡션`), `features/editor/assets/EditorAssetBrowser.tsx`(미디어 종류 탭 `aria-label="미디어 종류"` → line 탭, 카드 안 `원본 미리보기`·`적용`·`화면에 얹기`·`화면으로 깔기` → `size="sm"` `variant="outline"`/`ghost`, 카드마다 주 동작 없음), `features/editor/inspector/InspectorControls.tsx`(이유 없는 비활성 22), `features/editor/workbench/YujinPanel.tsx`(9), `features/editor/assets/{MotionPanel,InfographicPanel,LibraryPickerDialog}.tsx`, `features/editor/preview/preview-stage.tsx`(재생줄 비활성 이유: `미리보기를 만드는 중이에요. 다 되면 눌러져요.` 하나를 묶음 아래에), `features/editor/timeline/TimelineDock.tsx`(트랙 단추 `size="icon-xs"`·`aria-label` 문구만), `features/editor/transcript/{TranscriptPanel,AutoCaptionCard}.tsx`(대본 탭 문구 백틱 제거), `features/editor/inspector/CaptionFontPicker.tsx`, 캡션 모양 이름(`grep -rn "\"Clean\"\|\"Highlight\"\|>Clean<\|>Highlight<" apps/web/src --include=*.ts --include=*.tsx` 로 찾아 `깔끔하게`·`강조`)
- Test: `apps/web/src/features/editor/workbench/editor-workbench.test.tsx`, `apps/web/src/features/editor/inspector/InspectorControls.test.tsx`, `apps/web/src/features/editor/preview/preview-stage.test.tsx`

**Interfaces:** Consumes: Task 4 크기 계약·탭 규격, Task 5 `DisabledReason`. 편집기 크기 배정: 도구줄·속성 칸 단추 `sm`(28), 트랙 머리·재생줄·작은 아이콘 `icon-xs`(24), 내보내기 `icon`(28) + 주 동작.

- [ ] **Step 1: 실패하는 시험**
  - `editor-workbench.test.tsx`: `it("왼쪽 레일 탭은 이름이 있고 탭 패널과 짝이다")` — 모든 `getAllByRole("tab")` (레일 목록 안)이 비지 않은 이름, 선택된 탭의 `aria-controls`가 존재하는 `tabpanel`.
  - `apps/web/src/features/editor/inspector/InspectorControls.test.tsx`: `it("조정 하위 탭은 밑줄 탭이고 패널과 짝이다")` — `getByRole("tablist", { name: /조정 항목$/ })`의 `data-variant` = `line`, 선택된 탭의 `aria-controls` 대상이 `tabpanel`.
  - `EditorAssetBrowser`의 `aria-label="왼쪽 패널"`(311행)과 `EditorWorkbench`의 레일 `aria-label="왼쪽 패널"`(699행)이 **같은 이름 둘**이다 — 레일은 `편집 도구`로 바꾸고(`getAllByRole("tablist", { name: "왼쪽 패널" })` 길이 1을 단언) 기존 시험의 이름 단언을 따라 고친다.
  - `preview-stage.test.tsx`: `it("미리보기가 없을 때 재생줄 단추가 잠긴 이유를 말한다")`.
  - `editor-workbench.test.tsx`: `it("편집기에서 주황 채운 단추는 내보내기 하나다")` — `container.querySelectorAll('[data-slot=button][data-variant=default]').length === 1` (D2 승인 시. 거절 시 이 시험은 쓰지 않는다).
- [ ] **Step 2: RED** — 시험 하나씩.
- [ ] **Step 3: 구현** — 위 파일 목록. CSS 리터럴은 가드 기준선 `editor-workbench.css` 항목이 0이 될 때까지. `vb-preview-stage`는 2026-08-19 예외(척도 한 단계 아래)가 있다 — 그 블록의 간격 토큰은 그대로 둔다.
- [ ] **Step 4: GREEN** — 위 시험 + `src/features/editor` 전체(알려진 불안정 하나는 보고만) + `src/task22-parity-owners.test.ts` + `src/user-copy-policy.test.ts`.
- [ ] **Step 5: e2e 편집기** — `cd apps/web && npm run test:e2e:editor-workbench`. 도크 끌기 성능 게이트가 흔들리면 두 번 더 돌려 3회 중 결과를 그대로 보고. 스냅샷 PNG 되돌리기.
- [ ] **Step 6: 기준선 내리기 + 커밋** — `git commit -m "feat(web): 편집기 크롬 — 컨트롤 24/28·탭 이름과 패널 짝·line 하위 탭·주황 하나·잠긴 이유, Clean/Highlight 한국어"`

**검증 넷:** 갭 = 감사 §4의 디자인 행(단추 글꼴·높이·모서리·10px·접근성 이름·문구)별로 됨/안 됨 · 역방향 = Task 15 · 동작 = 개발 서버 편집기에서 Arial 0, 모서리 0px 컨트롤 0, 높이 집합 ⊆ {24,28,32} · 배선 = `grep -c "variant=\"default\"" apps/web/src/features/editor -r` 전후 비교.

---

### Task 11: 배선 수리 — 인벤토리의 고칠 줄과 없앨 줄

**적용 스킬:** 저장소 교훈(기억 메모 "화면에서 안 부르는 api.ts 메서드는 자동으로 죽은 게 아니다", "부품은 있는데 부르는 자리가 없다"), web-design-guidelines(`<button>`은 동작, `<a>`는 이동), design:ux-copy(오류 화면).

**Files:**
- Modify: `apps/web/src/features/footage/SceneTimeline.tsx`(W-01: 앵커 `data-native-control="footage-playhead"` 의 `<button …/>` → `<span className="vb-footage-playhead" aria-hidden="true" />`), `apps/web/src/task22-parity-owners.test.ts`(그 파일 허용 수 −1)
- Modify: `apps/web/src/app/AppRouter.tsx` — 루트 라우트에 `errorComponent: RouteErrorPage`(새 함수, 같은 파일): `<main className="vb-route-error" role="alert"><h1>화면을 그리지 못했어요</h1><p>잠깐 문제가 생겼어요. 아래 단추로 다시 열어 주세요.</p><Button data-primary-action variant="default" onClick={() => window.location.reload()}>다시 열기</Button><Button variant="outline" onClick={() => navigate({ to: "/projects" })}>프로젝트 목록으로</Button></main>` (감사 3-6의 `Something went wrong!` 대체; 오류 원인 고치기는 H 몫)
- Modify: `apps/web/src/ErrorBoundary.tsx` — 앵커 `<p>{this.state.error.message}</p>`: 원문은 `<details><summary>자세히</summary>…</details>` 안으로(영어 오류가 첫 화면에 그대로 나오지 않게)
- Modify: `apps/web/src/api.ts` — W-02 규칙에 따라(아래)
- Modify: `docs/superpowers/2026-10-08-wiring-inventory.ko.md` — 처리 결과 열 채움
- Modify: `apps/web/src/app/product-shell-layout.test.tsx` — `app/AppRouter.tsx` 주 동작 표시 기대 1 → 2(오류 화면의 `다시 열기`)
- Test: `apps/web/src/features/footage/SceneTimeline` 시험(없으면 `FootageOrganizerPage.test.tsx`에), `apps/web/src/app/AppRouter.test.tsx`, `apps/web/src/error-boundary.test.tsx`

**Interfaces:** Produces: 인벤토리 문서의 모든 줄에 처리 결과(`고침 커밋 <해시>` / `없앰 커밋 <해시>` / `그대로 — 이유` / `넘김 → 계획·Task`).

W-02 규칙(메서드마다 이 순서로 판정하고 근거 명령 출력을 인벤토리에 붙인다):
1. `grep -rn "<메서드 이름>" apps/web/src --include=*.test.*` 에 "부르지 않는다"류 단언이 있으면 → **그대로**(일부러 남김).
2. 그 메서드가 부르는 백엔드 경로를 `services/api`·`packages`·`apps/mcp`(있으면)·`docs/superpowers/plans/2026-10-0[28]-*.md`에서 grep — 유진·MCP가 쓰거나 계획이 쓸 예정이면 → **그대로**, `api.ts` 메서드 위에 `// 화면 호출 없음: <누가 왜> (2026-10-08 배선 인벤토리 W-02)` 한 줄.
3. 둘 다 아니면 → **없앰**: 메서드와 그 메서드만 쓰는 타입·시험을 지운다. 백엔드 라우트는 지우지 않는다(인벤토리에 "백엔드 정리 후보"로).

W-03 30경로: 이 Task에서 **분류만** 한다(코드 변경 없음). "계획이 화면에 약속했는데 없음"으로 분류된 줄은 owner 결정 목록(Task 15 보고)에 올린다.

- [ ] **Step 1: 실패하는 시험** — `it("장면 타임라인의 재생 위치 표시는 누르는 자리가 아니다")`(`queryByRole("button", { name: "현재 재생 위치" })` null), `it("라우터 오류 화면은 한국어이고 다시 여는 길이 있다")`(라우트 하나가 던지게 만든 뒤 `getByRole("heading", { name: "화면을 그리지 못했어요" })`, `getByRole("button", { name: "다시 열기" })`), `it("오류 원문은 접힌 자세히 안에 있다")`.
- [ ] **Step 2: RED** — 시험 하나씩.
- [ ] **Step 3: 구현** — 위 파일들. W-02 판정·처리.
- [ ] **Step 4: GREEN** — 위 시험 + `src/api.test.ts` + `src/task22-parity-owners.test.ts` + `npx tsc --noEmit`(지운 메서드를 누가 부르면 여기서 걸린다).
- [ ] **Step 5: 커밋** — `git commit -m "fix(web): 배선 인벤토리 처리 — 죽은 재생 위치 단추 없앰, 라우터 오류 화면 한국어, 화면 호출 없는 api 메서드 판정"`

**검증 넷:** 갭 = 인벤토리 W-01~W-12 줄마다 처리 결과가 있는가 · 역방향 = 개발 서버 `/footage`에서 촬영본을 하나 골라 분석 전 화면의 재생 위치가 `span` · 동작 = 해당 없음 · 배선 = 지운 메서드 이름 grep 0, 남긴 메서드 위 주석 수 = "그대로" 판정 수.

---

### Task 12: 계산 스타일 게이트 (Playwright, 픽셀 비교 아님)

**적용 스킬:** intranet-style 재현 체크리스트(컨트롤 높이·radius 스케일·아이콘·focus·빈 상태), web-design-guidelines(가로 스크롤 없음), design:accessibility-review(24px·11px).

**Files:**
- Create: `apps/web/e2e/support/design-targets.mjs`, `apps/web/e2e/design-tokens.spec.mjs`

**Interfaces:**
- Consumes: Task 0 `collectStyleInventory(page)`.
- Produces: `export const CONTROL_HEIGHTS = [24, 28, 32]`, `export const FONT_SIZES = [11, 12, 13, 14, 16, 20, 24]`, `export const FONT_WEIGHTS = [400, 500, 600]`, `export const RADII = ["0px", "6px", "10px", "16px", "999px", "9999px", "50%"]`, `export const PAGES = [{ path: "/projects", primary: 1 }, { path: "/library", primary: 1 }, { path: "/library?kind=audio", primary: 1 }, { path: "/footage", primary: 1 }, { path: "/voices", primary: 1 }, { path: "/settings/appearance", primary: 0 }, { path: "/projects/local-draft/create", primary: 1 }, { path: "/projects/local-draft/editor", primary: 1 }, { path: "/projects/local-draft/review", primary: 1 }]`(가짜 API 프로젝트 `local-draft`), `export const EXEMPT = [{ selector: string, reason: string }]` — 처음 내용: 타임라인 클립(`.vb-timeline-clip` 류 — H가 정한 클래스 이름을 grep으로 확인), `+ 새로 만들기` 칸(G3 — 카드 높이와 같게 늘어나는 것이 승인 사항), 프로젝트·자료실 카드 전체가 링크/단추인 경우(카드 높이). 이유 없는 줄은 시험이 실패한다.

시험(뷰포트 1440×900, 1280×720, 375×812 각각, 화면마다):
1. 보이는 컨트롤 높이 ∈ `CONTROL_HEIGHTS`(EXEMPT 제외) — 실패 메시지에 이름·높이·선택자.
2. 컨트롤·글자 `fontFamily` 첫 이름 = `Pretendard`(Arial·Times 0).
3. 글자 크기 ∈ `FONT_SIZES`(375px 미만 입력의 16px 예외), 굵기 ∈ `FONT_WEIGHTS`.
4. 컨트롤 모서리 ∈ `RADII`.
5. `[data-primary-action]` 보이는 수 = `primary`.
6. `docScrollWidth <= docClientWidth`.
7. 1440×900에서만: `/projects` 첫 줄 카드 ≥ 6, `/library` 영상 카드 첫 줄 ≥ 5.
8. 비활성 컨트롤은 `hasReason`이거나 `aria-busy="true"`.
9. 카드가 다시 커지지 않게: `.vb-catalog-card`의 계산 `padding-top` ≤ 12px·카드 제목 글자 13px·한 줄(`scrollHeight`가 줄 높이 이하), `.vb-library-video-card` 폭 ≤ 200px(1440×900)·이름 12px.

- [ ] **Step 1: 시험 작성** — 위 아홉.
- [ ] **Step 2: 실패를 본다(가드가 진짜인지)** — `git stash`로 이 계획의 CSS를 잠깐 되돌릴 수 없으므로(이미 커밋됨) 대신 `CONTROL_HEIGHTS`를 `[28]`로 바꿔 돌려 FAIL이 24·32를 실제로 보고하는지 확인하고 되돌린다. Run: `cd apps/web && npm run test:e2e -- design-tokens.spec.mjs`.
- [ ] **Step 3: GREEN** — 원래 값으로 PASS. 실패 항목이 남으면 **화면을 고친다**(EXEMPT에 넣는 것은 승인 사항·배치 높이일 때만, 이유와 함께).
- [ ] **Step 4: 스냅샷 PNG 되돌리기 확인 + 커밋** — `git commit -m "test(e2e): 계산 스타일 게이트 — 컨트롤 24/28/32·Pretendard·글자 척도·주 동작 하나·가로 넘침 없음"`

**검증 넷:** 갭 = 여덟 단언 · 역방향 = 가짜 API지만 실제 브라우저(chromium)·실제 CSS · 동작 = 실패 메시지가 px로 말한다 · 배선 = `PAGES`가 Task 0 W-08 라우트 목록의 사용자 화면을 다 덮는가(공유 미리보기 제외).

---

### Task 13: 무반응 스모크 — 눌렀는데 아무 일도 없으면 실패

**적용 스킬:** 대표님 요구("버튼이 반응이 없다"), web-design-guidelines(Hover & Interactive States), webapp-testing.

**Files:**
- Create: `apps/web/e2e/no-dead-clicks.spec.mjs`, `apps/web/e2e/support/no-reaction-allowlist.mjs`

**Interfaces:**
- Consumes: Task 12 `PAGES`.
- Produces: `export const NO_REACTION_ALLOWED = [{ page: string, name: RegExp | string, reason: string }]` — 처음 비어 있다. 이유 없는 줄 금지.

반응 판정(클릭 뒤 1000ms 안에 하나라도): (a) `document.body` MutationObserver 기록 ≥ 1 — 단, 더해진 노드가 `[data-slot=tooltip-content]`이거나 그 안인 기록은 뺀다(마우스가 올라가 뜬 툴팁은 반응이 아니다), (b) `page.on("request")` 새 요청 ≥ 1, (c) 주소 변경, (d) `filechooser`·`dialog`·`download` 사건, (e) 초점이 다른 요소로 옮겨지고 그 요소가 클릭한 요소가 아님(메뉴 열림 등).
절차: 화면을 열고 컨트롤 목록(Task 0 선택자, 보이고 `disabled` 아님)을 `이름#순번` 열쇠로 만든다. 열쇠마다: 관찰 시작 → `locator.click({ timeout: 2000 })` → 1000ms 기다림 → 판정 → `Escape` 두 번 → 주소가 바뀌었거나 `[role=dialog]`가 남았으면 그 화면을 다시 연다. 편집기는 컨트롤이 많아 시험 제한 시간을 `test.setTimeout(20 * 60_000)`.

- [ ] **Step 1: 시험 작성.**
- [ ] **Step 2: 판정이 진짜인지** — 가짜 화면 하나(`page.setContent('<button>죽은 단추</button>')`)에서 FAIL, `<button onclick="this.textContent='눌림'">` 에서 PASS 하는 자체 시험 두 개를 같은 파일에 둔다. Run: `cd apps/web && npm run test:e2e -- no-dead-clicks.spec.mjs -g "판정"`.
- [ ] **Step 3: 전체 화면 실행** — `npm run test:e2e -- no-dead-clicks.spec.mjs`. 무반응으로 나온 것마다: (1) 진짜 죽은 단추 → Task 11 규칙으로 고치거나 없앤다(같은 Task 안에서, 커밋 분리), (2) 가짜 API가 응답을 안 줘서 그런 것 → `fake-api-server.mjs`에 그 경로 응답을 더한다, (3) 의도된 무반응(예: 이미 선택된 탭을 다시 누름) → 허용 목록 + 이유.
- [ ] **Step 4: GREEN + 커밋** — `git commit -m "test(e2e): 무반응 스모크 — 화면 9곳의 모든 보이는 컨트롤이 1초 안에 반응한다"`

**검증 넷:** 갭 = 화면 9곳 전부 돌았는가(실행 로그의 화면별 컨트롤 수) · 역방향 = 실제 chromium 클릭 · 동작 = 무반응 수 0(허용 목록 제외) · 배선 = Step 3에서 나온 진짜 죽은 단추 목록을 인벤토리에 더했는가.

---

### Task 14: 대표님 클릭 지도 · 디자인 규칙 한 장 · CLAUDE.md 링크

**적용 스킬:** design:ux-copy(대표님이 읽는 말), intranet-style README "신규 화면 만드는 순서·재현 체크리스트"(규칙 문서 틀), design:design-system `document`(부품별 쓰는 때·상태·접근성), humanize-korean(문장 다듬기는 선택).

**Files:**
- Create: `docs/owner-test-guide.ko.md`
- Create: `docs/design-rules.ko.md`
- Modify: `CLAUDE.md` §2 표

**Interfaces:** Consumes: 인벤토리(Task 0·11·13), 토큰 표(Task 2), 크기 계약(Task 4), 피드백 무늬(Task 5).

- [ ] **Step 1: 클릭 지도 만들기(실제 화면에서 눌러 확인)** — 컨테이너를 이 시점 코드로 다시 짓는다(`.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild`, `Ctrl+F5`). 내장 브라우저로 화면마다 **되돌릴 수 있는 것만** 누른다: 이동(메뉴·탭·링크), 열고 닫기(드롭다운·대화상자 → `취소`/`Escape`), 검색 입력(저장 없음), 설정 토글(누른 뒤 되돌림). **누르지 않는 것**: 완성본 만들기·업로드·삭제·보관·적용·저장·유진에게 보내기·자료 넣기. 누르지 않은 것은 지도에 `직접 눌러 보세요(되돌리기: …)`로 적는다.
  문서 구조:
  1. **처음 10분 — 이 순서로 눌러 보세요** (10가지 흐름: ① `/projects`에서 `+ 새로 만들기` → 시작 방법 고르기 ② 프로젝트 카드 → 편집기 ③ 자료실 → `내 영상` → 검색 `바다` → 미리보기 ④ `음악·효과음` → 재생 ⑤ `촬영본 정리` → 촬영본 고르기 → `분석 시작` ⑥ 편집기에서 장면 고르기 → `나누기`(Ctrl+B) → `되돌리기`(Ctrl+Z) ⑦ 자막 모양 바꾸기 ⑧ 유진에게 "3번 장면 빼 줘" → 되돌리기 ⑨ 미리보기 재생(스페이스) ⑩ `확인과 내보내기` → `완성본 만들기`). 흐름마다: 누를 것 / 기대 결과 / 안 되면 무엇을 보는지.
  2. **화면별 지도** — 화면마다 표: `자리 | 이름 | 누르면 | 기대 결과 | 상태`. 상태 = `됨(확인 2026-10-…)` / `고치는 중 — 계획 H Task N` / `잠김: <이유 문장>` / `없앰(Task 11)`.
  3. **알려진 고장과 고치는 계획** — 감사 §3 열 가지와 W 목록 중 남은 것, 각각 담당 계획·Task.
  4. **눌렀는데 반응이 없으면** — 위 띠 `작업 상태`를 열어 보기, 화면 아래 알림(토스트) 확인, 그래도 없으면 화면 이름·단추 이름을 알려 주기.
- [ ] **Step 2: `docs/design-rules.ko.md` 작성** — 한 장(약 150줄 이내): ① 색은 바꾸지 않는다(승인 문서 링크) ② 토큰 표(Task 2) ③ 크기 계약(`size`만, className 높이 금지) ④ 모서리 셋 ⑤ 글자 7단·굵기 셋·최소 11px ⑥ 주황은 주 동작·선택 표시에만, 화면마다 주 동작 하나 ⑦ 탭 두 무늬 + 편집기 세로 레일 ⑧ 피드백 다섯 단계 ⑨ 잠긴 단추는 이유 ⑩ 화면 문구 규칙(§10.13 요약) ⑪ 새 화면 만드는 순서(유형 고르기 → 머리 → 부품 → 상태 화면 → 가드·게이트 돌리기) ⑫ 가드·게이트 명령 ⑬ DS 대조표 요약(받아들임/고쳐/안 받아들임).
- [ ] **Step 3: `CLAUDE.md` 수정** — §2 표에서 `| 디자인 승인 기록 | \`docs/decisions/\` |` 줄 **바로 아래**에 한 줄을 더한다:
  `| **디자인 규칙(토큰·크기·피드백)** | \`docs/design-rules.ko.md\` |`
  그리고 "### 지금 유효한 결정" 목록의 `- **팔레트는 다크다**…` 줄 아래에 한 줄: `- **화면은 조밀하다**(\`2026-10-08\`). 본문 12px·라벨 11px·컨트롤 24/28/32px. 값은 \`docs/design-rules.ko.md\`. 색은 그대로.` (`최신 세션 인계` 줄은 Task 15에서 바꾼다 — `tests/test_handoff_entry_point.py`가 지키는 줄은 그것뿐이다.)
- [ ] **Step 4: 확인** — `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_handoff_entry_point.py` PASS(아직 인계 줄은 안 바꿨으므로 그대로 초록이어야 한다).
- [ ] **Step 5: 커밋** — `git commit -m "docs: 대표님 클릭 지도, 디자인 규칙 한 장, CLAUDE.md에서 링크"`

**검증 넷:** 갭 = 10가지 흐름·화면 9곳이 다 있는가, 직접 누르지 않은 항목 수를 문서 머리에 적었는가 · 역방향 = 지도의 "됨"은 이번에 실제로 눌러 본 것만 · 동작 = 해당 없음 · 배선 = 지도의 단추 이름이 화면의 접근 이름과 글자 그대로 같은가(내장 브라우저 `find`로 이름마다 1개 이상).

---

### Task 15: 실기 검증 · 인계 · 푸시

**Files:**
- Create: `docs/handoffs/<실행한 날짜 YYYY-MM-DD>-design-system-and-wiring-i.ko.md`(같은 날 다른 인계가 있으면 옛 것에 `**대체됨:**` 줄 — `tests/test_handoff_entry_point.py` 규칙)
- Modify: `CLAUDE.md`(`최신 세션 인계` 줄), `apps/web/src/styles/design-guard.test.ts`(마지막 단언), `docs/decisions/2026-10-08-compact-density.ko.md`(검증 결과 절)

- [ ] **Step 1: 가드를 0으로 잠근다** — 기준선 JSON의 모든 수가 0인지 본다. 0이 아닌 것은 (1) 고친다 또는 (2) `design-guard.allow.json`에 이유와 함께. 그다음 시험에 `it("모든 규칙이 0이다(허용 목록 제외)")`를 더하고 `design-guard.baseline.json`을 지운다(줄어들기 단계 끝).
- [ ] **Step 2: 컨테이너 재빌드** — `.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild`. 거짓 FAIL(시작 30초·502 대기)이면 로그를 보고 한 번 더.
- [ ] **Step 3: 실제 화면 측정(1440×900, 1280×720, 375×812)** — 내장 브라우저로 Task 0 Step 3의 화면 8곳을 같은 수집 코드로 다시 잰다. 결과를 `docs/superpowers/audit-evidence/2026-10-08-design-after.json`에 저장하고 인계 문서에 **전/후 표**(컨트롤 높이 종류 수·Arial 수·10px 수·모서리 종류·주황 단추 수·카드 열 수·가로 넘침)를 넣는다. 목표 표와 다르면 그 Task로 돌아간다. 1280×720에서 편집기 타임라인이 보이는 높이도 적는다(H·G6 결과 확인용).
- [ ] **Step 4: 클릭 지도 다시 밟기** — `docs/owner-test-guide.ko.md`의 10가지 흐름 중 되돌릴 수 있는 것을 실제 컨테이너에서 다시 밟는다. 다른 결과는 지도를 고친다.
- [ ] **Step 5: 넓은 검증(각각 단독 실행)**
  - `cd apps/web && npx tsc --noEmit && npx vitest run`
  - `npm --prefix apps/web run build`
  - `cd apps/web && npm run test:e2e` (알려진 `unexpected PNG` exit 1·도크 끌기 성능 흔들림은 보고만) → `git status --short apps/web/e2e/snapshots` → 바뀐 PNG 되돌림 + "스냅샷이 달라졌다(owner가 본 뒤 재승인)" 보고
  - `cd apps/web && npm run test:e2e -- design-tokens.spec.mjs no-dead-clicks.spec.mjs`
  - 저장소 루트: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --ignore=tests/test_mcp_server.py` (**단독**, 약 40~50분. 알려진 `smoke_timeout` 실패는 그 커밋 이전에서도 나는지 `git stash` 없이 판단: 실패하면 트레이스백을 남기고 한 번 더 단독 실행)
- [ ] **Step 6: 인계 문서** — 이번에 한 일(쉬운 말), 검증과 **검증 못 한 것**, 전/후 표, 인벤토리 처리 결과 요약, 재사용 게이트(§8.3: 재사용 후보 — Intranet DS 규격·`--vb-surface-ring`·sonner·Radix Tabs·기존 작업+폴링 표시 / 실제 반영과 방식 — 토큰 별칭·`data-slot` 규격 층·`partial port` / 제외와 이유 — DS 알약 입력·`ring-3/30` 초점·배지 10px·카드 24px 모서리 / 경계 보존 — 색 그대로·모서리 셋·시작 문 하나·없는 기능 단추 없음), owner 결정 남은 것. `CLAUDE.md` §2 `최신 세션 인계` 줄을 이 문서로 바꾸고 `tests/test_handoff_entry_point.py` PASS.
- [ ] **Step 7: 커밋 → 푸시** — 커밋 후 **따로** `git push origin main`.

**검증 넷:** 이 Task 자체가 역방향·동작 검증이다. 갭 = Task 0~14의 "안 한 것"을 인계에 모은다 · 배선 = `grep -rn "data-primary-action" apps/web/src --include=*.tsx | grep -v test | wc -l`, `useActionFeedback`·`DisabledReason` 소비자 수, 지운 api 메서드 0 호출을 다시 센다.

---

## 소유자 결정 (최대 다섯, 기본값 = 추천)

| # | 결정 | 추천 기본값 | 비용·위험 |
|---|---|---|---|
| D1 | 모양 통일 결정(`2026-10-08-design-system-normalization`) 승인 — 모서리 8px 없앰, 초점 링 2px 주황, 탭 두 무늬, 대화상자 격자·88vh | **승인**(이 계획 승인과 함께) | 거절 시 Task 4의 해당 줄·Task 9 탭 전환이 빠지고 "들쭉날쭉"의 절반이 남는다 |
| D2 | **주황 채운 단추는 영역마다 하나**(`Button` 기본 변형 → `outline`, 주 동작만 주황) + 작은 제목(eyebrow) 주황 빼기 | **승인** | 색 값은 그대로지만 화면 인상이 차분해진다(편집기 주황 38→1). 거절 시 Task 5 Step 3 일부·Task 10 마지막 시험 생략 |
| D3 | `설정 > 화면 > 조밀한 화면` 토글 없앰(조밀이 유일한 기본) | **없앰** | 대안 "넓게 보기"로 바꾸면 척도를 두 벌 유지해야 한다(가드·게이트도 두 벌). 지금 토글은 대부분 화면에서 눌러도 변화가 없다(W-06) |
| D4 | 콘텐츠 최대폭 없앰(캡컷처럼 창 폭 전체) | **없앰**, 긴 문단만 40rem | 2560px 같은 아주 넓은 창에서 카드가 한 줄에 12개 이상 — 문제가 되면 `max-width: 2400px` 한 줄로 막을 수 있다 |
| D5 | 실행 순서 | **H → G → I → B–F** | I를 G보다 먼저 하면 G2·G3·G7이 바꿀 자리를 I가 두 번 만진다(약 3~4시간 재작업) |

## 계획서 자체 점검 (작성 후 다시 잼)

- 앵커 재확인(2026-10-08): `ui-system.css`의 `--vb-radius-sm: 0.375rem;`·`--vb-text-xs: 0.625rem;`·`--radius-sm: calc(var(--radius) - 4px);`·`.vb-button { font: inherit; }` 있음 / `product-shell.css`의 `max-width:1200px`·`@media (min-width:1600px)`·`[data-slot=button] { min-height:32px; height:32px; }`·`.vb-catalog-card { height:auto; min-height:6rem; padding: var(--vb-space-5);`·`.vb-dialog-content { … max-height:70vh` 있음 / `dialog.tsx` `<span className="sr-only">Close</span>` 있음 / `SceneTimeline.tsx` `data-native-control="footage-playhead"` 있음 / `ProductShell.tsx` `SettingToggle label="조밀한 화면"`·`vb-settings-nav` 있음 / `AppRoot.tsx` `<AppRouter />` 있음 / `AppRouter.tsx` `"+ 새로 만들기"` 392행 / `OutputsPage.tsx` `vb-home-grid vb-outputs-grid` 1376행 / `capcut-patterns.design-system.test.ts` `["24", "28", "30", "34"]` 있음. H 계획 파일은 작성 시점에 **아직 없다** — H 앵커는 Task 10 실행 시 확인.
- 이름 일관성: `collectStyleInventory`(T0→T12·13·14), `collectDesignViolations`(T3→T15), `useActionFeedback`·`DisabledReason`(T5→T10), `displayFootageName`(T8), `CONTROL_HEIGHTS`·`PAGES`·`EXEMPT`(T12→T13), `NO_REACTION_ALLOWED`(T13), 토큰 이름(T2 표 = T4·6·7·8·10 사용).
- Task 16개(0~15). 예상 시간: T0 3 · T1 1 · T2 2.5 · T3 3 · T4 4 · T5 4 · T6 3 · T7 2 · T8 3.5 · T9 3 · T10 5 · T11 4 · T12 3 · T13 4 · T14 3 · T15 6(전체 pytest 45분 포함) = **약 54시간**.
- 대표님 새 요구 두 가지의 자리: (1) **테스트할 수 있게** — 화면마다 주 동작 하나·설명 한 줄(T6), 누름→진행→결과 한 무늬·잠긴 이유(T5·T10), 아이콘 단추 이름(T3 가드·T12 게이트), 뒤에 기능 없는 단추 없앰(T11·T13), 무반응 스모크(T13), 클릭 지도(T14). (2) **조밀하게** — 토큰(T2)·부품 크기(T4)·셸 폭(T6)·카드(T7·T8)·편집기(T10), 결정 기록(T1), 다시 커지지 못하게 가드(T3)·게이트 7·9번(T12).
