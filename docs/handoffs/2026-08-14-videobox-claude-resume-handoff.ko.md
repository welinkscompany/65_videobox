# VideoBox Claude 재개 핸드오프

작성일: 2026-08-14 (2026-08-15 세션 결과 추가)
canonical worktree: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility`
branch: `codex/videobox-container-compatibility`
작업 시작 기준 HEAD: `92067f234a1abcf0038a5fed9575ef8babe899e3`

> **다음 세션은 이 문서 맨 아래 `## 다음 세션 시작점` 절만 읽으면 된다.** 그 위의
> 본문(2026-08-14, 2026-08-15 세션 기록)은 어떻게 여기까지 왔는지의 근거이며,
> 수치와 HEAD가 다르면 항상 가장 아래 절이 우선한다.

## 결론

Wave2 footage organizer 계획의 Task 1~5와 이후 creator workspace/editor 보강은 구현 상태다. 이번 세션은 남은 전체 회귀와 인계 진입점을 점검했고, Chromium E2E가 실제로 잡은 편집 미리보기 가시성 회귀를 수정했다.

자동화와 실제 브라우저 증거는 owner acceptance와 구분한다. owner가 직접 전체 결과물을 시청·청취하고 취향과 업무 적합성을 승인한 상태는 아니다.

## Claude가 반드시 시작할 순서

1. 이 worktree에서 `git status -sb`와 `git rev-parse HEAD`를 실행한다.
2. `CLAUDE.md` 전체와 `docs/development-fast-path.ko.md`의 `## 10. 고정 운영 규정`을 읽는다.
3. 이 문서와 `docs/superpowers/plans/2026-08-12-videobox-wave2-footage-organizer.md`를 읽는다.
4. `git rev-list --left-right --count HEAD...@{upstream}`과 원격 SHA를 확인한다.
5. 9119를 무조건 재시작하지 말고 TCP/HTTP를 먼저 확인한다. 필요할 때만 compose 포트 9130을 확인한다.
6. 제품 코드 변경 전 현재 컨테이너 image와 HEAD가 일치하는지 확인한다.

다른 worktree, owner runtime 데이터, ignored QA 산출물은 정리 대상으로 추정하지 않는다. stage/삭제/stash/reset하지 않는다.

## 이번 세션에서 발견하고 수정한 회귀

`npm --prefix apps/web run test:e2e`의 exact-preview 테스트가 편집 영상 높이 120px 이상을 요구했지만 16px만 렌더링되어 RED가 됐다.

원인은 preview shell 높이가 아니라 비디오 자체였다.

- preview shell: 약 243px
- 비디오: 16×16px
- CSS가 `width:auto; height:auto`여서 작은 소스의 intrinsic 크기를 그대로 사용했다.
- `max-width/max-height:100%`와 `object-fit:contain`만으로는 작은 영상을 작업 가능한 크기로 확대하지 못했다.

수정 범위:

- `apps/web/src/styles/editor-workbench.css`
  - preview video를 `width:100%; height:100%; object-fit:contain`으로 제한한다.
  - grid row가 작아질 때는 `min-width/min-height:0`과 max bounds로 shell을 넘지 않는다.
- `apps/web/src/features/editor/preview/preview-stage.test.tsx`
  - 고정 preview viewport가 가용 영역을 사용하는 계약을 확인한다.

테스트의 120px 기준을 낮추거나 제거하지 않았다. 실제 사용자에게 영상이 한눈에 보여야 한다는 제품 요구를 유지했다.

첫 수정본을 실제 1920×1080 owner runtime에서 확인하자 두 번째 레이아웃 회귀가 드러났다. 1500px 이상에서는 출력 변형과 타임라인의 높이 상한이 충분히 작지 않아 중앙 preview media row가 0px까지 줄었다. 출력 변형을 스크롤 가능한 `max-height: 10rem`, 타임라인을 `max-height: 12rem`으로 제한하고 Full HD 회귀 테스트를 추가했다. 최종 실제 브라우저에서 media shell 154px, video 154px를 확보했다.

## 검증 증거

### Python

최초 전체 실행:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

- 제품/계약 테스트 `3521 passed`
- `53 skipped`
- `1 failed`
- 실패는 제품 코드가 아니라 `CLAUDE.md`가 2026-08-12 핸드오프를 가리키던 진입점 불일치였다.
- 이 문서를 추가하고 `CLAUDE.md` 최신 세션 인계 포인터를 함께 갱신했다.

포인터 수정 후 최종 전체 재실행은 `3522 passed, 53 skipped, 1 warning`으로 통과했다. warning은 기존 Starlette `python_multipart` PendingDeprecationWarning이다.

### Frontend 및 Chromium

- PreviewStage focused Vitest: `19 passed`
- frontend 전체 Vitest: `75 files / 953 passed`
- production build: 성공
- isolated Chromium E2E: `41 passed`, snapshot manifest verified
- editor-workbench Chromium E2E: `10 passed`, snapshot manifest verified
- `git diff --check`: 통과

Vitest의 기존 React `act(...)` 경고, jsdom navigation 미구현 로그, 의도된 error-boundary 콘솔과 Vite 500kB chunk warning은 exit 0인 기존 test/build hygiene 항목이다.

## 런타임과 브라우저 경계

기준 owner runtime 주소는 `http://127.0.0.1:5173`이다. VideoBox workspace는 PostgreSQL store를 사용한다. Hermes dashboard 9119/9130의 HTTP reachability는 Hermes live provider/chat 성공 증거가 아니다.

2026-08-14 실제 Chromium을 1920×1080으로 열어 확인한 결과:

- `/`, `/library`, `/footage`, `/projects/my-project/plan`은 모두 HTTP 200이고 horizontal overflow가 없다.
- 네 경로 순회 중 console error, request failure, HTTP 4xx/5xx와 `TODO`/`Coming soon`/`준비 중`/`placeholder` 표시는 0건이다.
- `my-project` 편집기 session `editing_session_draft_5ee4d7c4b924`에서 document 1920/1920, video 1127×154px, readyState 4를 확인했다.
- 실제 재생 버튼으로 currentTime이 0초에서 2.64초까지 진행했고 다시 일시정지했다. 해당 편집기 console error/warning은 0건이다.
- playback manifest의 session/source/artifact revision은 모두 10이며 exact preview status는 `succeeded`다.
- exact preview content의 `Range: bytes=0-1023` 요청은 `206`, `Accept-Ranges: bytes`, `Content-Range: bytes 0-1023/257944`로 응답했다.
- workspace container는 이 수정 커밋으로 rebuild/restart했고 `/health`는 PostgreSQL store와 함께 HTTP 200이다. `/api/health`는 존재하지 않는 경로이므로 readiness 점검에 사용하지 않는다.
- Hermes 9119와 compose 대체 포트 9130은 launcher 재실행 없이 TCP/HTTP 200을 확인했다.

이번 세션의 실제 runtime 확인 결과는 아래 `최종 상태` 절을 우선한다. owner가 직접 시청하지 않은 범위를 owner acceptance로 표현하지 않는다.

## 기존 계획서 상태

`docs/superpowers/plans/2026-08-12-videobox-wave2-footage-organizer.md`의 Task 1~5는 모두 `[x]`다. 새 계획서를 만들지 않는다.

현재 구현된 주요 경계:

- folder picker와 drag-and-drop ingest
- Full HD desktop library/editor layout
- footage proposal과 virtual sequence
- Yujin bounded proposal adapter와 explicit preview → approval
- editor timeline, caption, B-roll, variants, undo/redo
- exact preview revision/source identity fail-closed
- stale preview를 mutation 전에 제거하는 frontend/backend 경계

## 남은 실제 작업

자동 테스트가 대신할 수 없는 항목만 남는다.

1. owner가 실제 긴 원본으로 전체 편집·출력 결과를 처음부터 끝까지 시청·청취한다.
2. 자막 타이밍, 음량, B-roll 선택과 화면 밀도를 owner가 승인한다.
3. Hermes gateway/provider가 실제 활성 상태일 때 Yujin live chat을 다시 확인한다.
4. 필요하면 owner 전용 새 QA 프로젝트에서 ingest → edit → review → output을 반복한다.

이 항목이 없으면 제품 완료 또는 owner 승인으로 보고하지 않는다.

## 최종 상태

이 문서를 커밋하기 전에는 아래 명령으로 현재 사실을 다시 확인한다.

```powershell
git status -sb
git rev-parse HEAD
git rev-list --left-right --count HEAD...@{upstream}
.\.venv\Scripts\python.exe -m pytest -q
npm --prefix apps/web test
npm --prefix apps/web run build
npm --prefix apps/web run test:e2e
npm --prefix apps/web run test:e2e:editor-workbench
.\scripts\owner-ready.ps1 -Mode Check -Json -TimeoutSec 8
```

완료 시점의 authoritative SHA는 이 문서 내용에 하드코딩된 추정값이 아니라 `git rev-parse HEAD`와 원격 branch SHA다.

이 문서를 작성한 상태의 최종 자동 검증은 다음과 같다.

- Python 전체: `3522 passed, 53 skipped, 1 warning`
- frontend 전체: `75 files / 953 passed`
- Chromium E2E: `41 passed`
- editor-workbench Chromium E2E: `10 passed`
- production build와 `git diff --check`: 통과
- 실제 1920×1080 브라우저 route/preview/playback/Range 점검: 통과
- `owner-ready Check`: 브라우저 임시 파일 제거 후 `overall_status: pass`, working tree `other_change_count: 0`으로 통과했다. 이 Check는 owner acceptance가 아니다.

## Claude용 복사 프롬프트

```text
VideoBox Creator Workspace 개발을 이어간다.

canonical worktree:
D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility

branch:
codex/videobox-container-compatibility

먼저 반드시 실행:
1. git status -sb
2. git rev-parse HEAD
3. git rev-list --left-right --count HEAD...@{upstream}
4. CLAUDE.md 전체 읽기
5. docs/handoffs/2026-08-14-videobox-claude-resume-handoff.ko.md 읽기
6. docs/superpowers/plans/2026-08-12-videobox-wave2-footage-organizer.md 상태 확인

다른 worktree나 owner runtime 데이터를 정리하지 마라. 9119 launcher를 무조건 재실행하지 말고 TCP/HTTP를 먼저 확인해라. owner-ready Check, 자동 E2E, 실제 브라우저 검증, owner acceptance를 서로 구분해라.

계획 Task 1~5는 구현 완료 상태다. 새 계획서를 만들지 말고 현재 코드와 최신 핸드오프를 기준으로 진행해라. 남은 핵심은 owner의 전체 시청·청취 승인과 Hermes gateway/provider가 활성일 때의 live chat 증거다. 사람 검증이 없으면 owner acceptance 완료라고 표현하지 마라.
```

---

## 2026-08-15 세션

시작 HEAD `a861acd23` (원격과 일치, working tree 깨끗). 이 절이 현재 사실이다.

### 이번 세션에서 고친 것 두 가지

**1. 촬영본 화면에 개발 계획 이름이 노출되고 있었다 — `65d38a8b5`**

`/footage` 머리말이 `VIDEObox / Wave-2`였다. `Wave-2`는 구현 계획서의 단계 이름이고,
`§10.13.3`은 개발·시스템 내부 용어를 사용자 화면에 쓰지 못하게 한다. 제품 이름 표기도
다른 화면(`VideoBox`)과 달랐다.

- `apps/web/src/features/footage/FootageOrganizerPage.tsx:123` → `VideoBox`
- `apps/web/src/app/AppRouter.test.tsx` — 이 테스트가 `getByText(/Wave-2/)`로 **위반을
  고정하고 있었다.** 반대를 확인하도록 바꿨다.
- 코드에 남은 `VIDEObox`/`Wave-2` 참조는 0건. `/footage`의 자산 파일명
  (`wave2-long-qa.mp4` 등)은 owner 데이터라 건드리지 않았다.

**2. 큰 화면일수록 미리보기가 작아지고 있었다 — `5f968ee8f`**

측정으로 확인한 실제 결함이다. 화면이 **더 큰데 영상이 더 작게** 보였다.

| viewport | media shell | 실제 보이는 그림 |
|---|---|---|
| 1440×900 | 269px | 476×267 |
| 1920×1080 (수정 전) | 156px | 275×154 |
| 1920×1080 (수정 후) | 316px | **560×314** |

원인은 side panel 압축 규칙이 `@media (min-width: 768px) and (max-width: 1499px)`로
묶여 있던 것이다. 1500px 이상에서는 그 블록이 빠지고 base 규칙(`variants 10rem`,
`timeline 12rem`)으로 되돌아가, 남는 세로 공간을 미리보기가 아니라 옆 패널이 가져갔다.

- `apps/web/src/styles/editor-workbench.css` — `@media (min-width: 1500px)` 블록 추가
  (`variants 6rem`, `timeline 6rem`, `sources 5rem`)
- `apps/web/src/features/editor/preview/preview-stage.test.tsx` — 그 블록 존재 확인
- `apps/web/e2e/exact-preview.spec.mjs` — **1440×900과 1920×1080을 직접 비교**하는
  E2E 가드. 절대값 하나가 아니라 순서를 고정하므로 다시 뒤집히면 잡힌다.
  media query를 꺼서 **실제로 RED가 되는 것까지 확인**했다.

1440×900은 수정 전후가 동일(476×267)하다. 1500px 미만은 영향받지 않는다.

축소한 패널은 전부 안쪽 스크롤로 접근 가능하다: 타임라인 clip 9개(가시 105px/전체
595px), 변형 tab 4개+버튼 9개, 소스 버튼 5개(스크롤 불필요). 타임라인 가시 높이가
201px→105px로 줄어든 것은 이 교환의 대가다. 참고로 medium layout(1440×900)의
타임라인은 82px이므로 여전히 그보다 넉넉하다.

### 재생 버튼 — 결함이 아니었다

브라우저 창이 화면에 표시되지 않은 상태(`visibilityState: hidden`)에서는 클릭으로
재생이 시작되지 않았다. 원인을 끝까지 확인한 결과 **제품 결함이 아니다.**

- 직접 `play()`는 정상 동작(2.14초 진행)
- 재생 중에 버튼을 누르니 **정확히 멈췄다** → 핸들러는 정상 연결돼 있다
- `preview-stage.tsx:101`이 `play()` 거부를 삼키므로 화면에는 아무 표시가 없다
- **이미 자동 검증이 있다**: `exact-preview.spec.mjs:147-154`가 실제 user gesture로
  버튼을 눌러 `!paused && currentTime > 0.05`를 확인하고, 다시 눌러 `paused`를 확인한다.
  이 테스트는 통과한다.

즉 hidden pane에서의 브라우저 autoplay 차단이었고, 손댈 것이 없다.

### 검증 결과

| 검증 | 결과 |
|---|---|
| Python 전체 | `3522 passed, 53 skipped` (아래 주의 참고) |
| frontend Vitest | `75 files / 954 passed` |
| production build | 통과 (기존 chunk-size 경고만) |
| Chromium E2E | `42 passed` (신규 Full HD 가드 1개 포함) |
| editor-workbench E2E | `10 passed` |
| `git diff --check` | 통과 |
| owner-ready Check | `overall_status: pass` |

**Python 전체 실행 주의.** 앞선 두 번의 전체 실행에서 각각 다른 테스트 1개가 실패했다
(`test_owner_ready_script.py::test_smoke_timeout_...`,
`test_api_footage_organizer.py::test_yujin_footage_interpretation_...`).
둘 다 **동시에 docker rebuild와 E2E를 돌리던 중**이었고, 각각 격리 재실행에서
`116 passed`, `15 passed`로 통과했다. 시간에 민감한 테스트가 부하를 탄 것이지 제품
결함이 아니다. **전체 실행은 다른 작업과 겹치지 않게 단독으로 돌릴 것.**

### 실제 브라우저 확인 (1920×1080, 컨테이너 배포본)

`/`(→`/projects`), `/library`, `/footage`, `/projects/my-project/plan`, 편집기
(`editing_session_draft_5ee4d7c4b924`)를 전부 열었다.

- 모든 요청 200, **console error 0건, 실패 요청 0건, 4xx/5xx 0건**
- 가로 overflow 없음. 페이지 자체는 스크롤하지 않고 안쪽 판 5개가 스크롤을 소유한다
- 자막 0/6/12/18초에서 각각 정확히 전환, 타임라인 표시와 일치
- playback manifest: `session_revision 10`, exact preview `source_session_revision 10`,
  `artifact_revision 10`, status `succeeded` — 일치
- exact preview content `Range: bytes=0-1023` → **HTTP 206**,
  `Content-Range: bytes 0-1023/257944`, `Accept-Ranges: bytes`
- `TODO`/`Coming soon`/`준비 중`/`placeholder` 잔여 문구 0건 (위 `Wave-2` 수정 후)

컨테이너는 이번 수정 커밋으로 rebuild/restart했고 `/health` 200이다. 배포 확인은
시각만 비교하지 말고 **실제로 내려오는 번들 내용을 확인할 것** — 이번에도 브라우저가
옛 번들을 캐시해 잠시 옛 화면을 보여줬다.

### 다음 사람이 알아야 할 미해결 사항

**1. 승인된 스냅샷 5장이 현재 코드와 어긋나 있다.**
`VIDEOBOX_WRITE_PLAYWRIGHT_SNAPSHOTS=1`로 다시 만들어 보니 **5개 viewport 전부**
sha256이 달랐다. 1920×1080만이 아니라 1440×900·1280×800·390×844·768×1024도 달랐고,
이들은 이번 수정(`min-width:1500px`)이 닿지 않는 크기다. 즉 **이번 세션 이전부터
스냅샷이 낡아 있었다.** 승인 기록(`docs/decisions/2026-07-20-editor-workbench-visual-approval.ko.md`)
에 해당하므로 **임의로 갱신하지 않고 원복했다.** 다시 만드는 것은 owner 재승인 사항이다.
참고로 스냅샷은 pixel 비교 게이트가 아니다(`fixed-clock.mjs:29`, 환경변수 있을 때만 기록).

**2. 라이브러리의 옛 자산 4개가 영원히 "길이 확인 중"으로 보인다.**
`wave2-long-qa.mp4`, `wave2-short-a/b/c.mp4`(2026-08-12 23:12 ingest)는 duration이 없다.
같은 날 23:17에 넣은 `-v2` 4개는 24초/4초가 정상 표시되므로 **현재 ingest 경로는 정상**이고,
probe slice 이전에 들어온 데이터만 남은 것이다. 음악 30·효과음 100은 전부 정상
표시된다(builtin은 top-level `duration_seconds`를 쓴다).
다만 `VideoAssetGrid.tsx:4`/`AudioAssetRows.tsx:4`는 duration이 없으면 무조건
"길이 확인 중"이라 **아무것도 확인하고 있지 않은데 확인 중이라고 말한다.**
`editorAssetProjection.ts:70-76`은 `analysis_status`를 보고 구분하므로, 맞추려면
그쪽 방식을 따르는 것이 맞다. 화면 문구 결정이라 owner 판단이 필요하다.

**3. `owner-ready.ps1 -Mode Start -Rebuild`의 준비 확인이 이르다.**
`-TimeoutSec 20`과 `90` 모두에서 `[FAIL] 연결 준비를 확인하지 못했습니다`가 났지만,
직후 컨테이너는 `healthy`였고 HTTP 200이었다. 이미지 빌드는 매번 성공했다.
rebuild 뒤에는 Check를 한 번 더 돌려 판단할 것.

### 남은 사람 검증 (그대로)

1. owner가 실제 긴 원본으로 전체 결과를 처음부터 끝까지 시청·청취
2. 자막 타이밍, 음량, B-roll 선택과 화면 밀도 승인
3. Hermes gateway/provider가 실제 활성일 때 Yujin live chat 확인
4. 위 미해결 1(스냅샷 재승인)·2(길이 문구) 결정

**이번 세션 결과는 owner acceptance가 아니다.** owner가 완성 영상을 직접 보고 들은
적이 없다. 자동 검증·owner-ready Check·실제 브라우저 확인은 서로 다른 것이며, 셋 다
사람의 취향 판단을 대신하지 않는다.

### 디자인 스킬 관련

`intranet-style` 스킬은 **이 환경에 있다** (`~/.claude/skills/intranet-style`).
세션 중반까지 스킬 목록에 안 보여 "없다"고 판단했으나 오판이었고, 확인 후 읽었다.
저장소 안에는 `.claude/skills`가 없다 — 스킬은 사용자 홈에 있다.

이 저장소는 그 계약을 **VideoBox CSS 변수로 번역해서 이미 강제하고 있다**
(`apps/web/src/features/footage/footage-design-system.test.ts`):

| intranet 정본 | 이 저장소의 표현 |
|---|---|
| 컨트롤 `h-8` | `min-height:32px` |
| radius 스케일 | `var(--radius-2xl)` (px/rem 직접 지정 금지) |
| 채워진 입력 `bg-input/50` | `color-mix(in srgb,var(--input) 50%,transparent)` |
| 표면 경계 `ring-1 ring-foreground/5` | `var(--vb-surface-ring)` |
| 하드코딩 색 금지 | 리터럴 색 정규식으로 0건 강제 |

이번 변경은 이 계약을 건드리지 않는다. 추가한 것은 `max-height`/`overflow`/`min-height`
뿐이고 **색·radius·컨트롤 높이를 새로 정하지 않았다.** `6rem`/`5rem`은 기존
768–1499px 블록의 표기(`6rem`/`4rem`)와 같은 방식이다. 머리말 문구 수정도
`vb-eyebrow` 규약(`AppRouter.tsx:186`)을 그대로 따랐다.

### 다음 세션 진입점 (2026-08-15 저녁 추가)

owner가 UX/UI 전면 개선을 확정했다. 실행 계획은
`docs/superpowers/plans/2026-08-15-videobox-dashboard-ux-recovery.md`다.

- 핵심 실측: 편집기 그림이 화면의 8.5%(1920×1080)·9.8%(1440×900)이고 **세로 제약**이다.
  side dock을 닫아도 그림은 안 커진다. 세로 회수(출력 변형 접기, 소스 확인 이동)가 주 수단이다.
- HEAD `565582c96`(편집기 기본 preview-only)은 **유지 판정**, 아직 미배포. Task 3에서 배포한다.
- 구현 세션 주의: 전체 pytest는 단독으로만. frontend-only Task에는 돌리지 않는다.
  배포 후 번들 해시로 실배포를 확인한다(브라우저 캐시에 두 번 속았다).

## 2026-08-15 UX 개편 구현 완료 (Task 1~7, HEAD `8e99a308e`)

위 진입점에서 시작한 `docs/superpowers/plans/2026-08-15-videobox-dashboard-ux-recovery.md`의
Task 1~7을 전부 구현·검증·배포·커밋·푸시했다. 각 Task의 실측값과 커밋 SHA는 그
계획서의 "실행 기록" 절에 있다. 여기서는 다음 세션이 알아야 할 결론과 미해결
사항만 남긴다.

### 결과 요약

편집기 미리보기 그림이 1920×1080 기준 **8.5% → 20.8%**(약 2.4배 면적)로 커졌다.
가로 확장이 아니라 세로 회수(출력 변형 접기·소스 확인 이동·자막 안내 통합)와
"미리보기 단독 시작" 기본값이 실제로 적용되도록 고친 것이 원인이다. 홈 화면의
"초안 있음"류 문구 중복(3회→1회)을 없앴고, 사이드바 세 구획(전체 메뉴·프로젝트
전환·프로젝트 단계)에 시각적 구분을 넣었고, 라이브러리↔촬영본 정리 사이에 자산이
선택된 채 여닫는 교차 진입을 추가했다.

### 발견하고 고친 두 가지 숨은 결함

1. **이전 세션이 "완료"로 판정한 `565582c96`이 실제로는 죽은 코드였다.**
   `resolveEditorWorkbenchLayout`의 fallback 기본값만 고쳤는데, 실제 앱은
   `editorUiState.ts`의 `defaultEditorUiState`를 항상 완전한 값으로 채워 넘겨서 그
   fallback에 절대 도달하지 않았다. Task 3에서 진짜 기본값(`editorUiState.ts`)을
   고쳐서 실제로 적용되게 만들었다. **테스트가 통과한다고 실제 코드 경로를
   지나간다는 뜻은 아니다** — 이번에도 CLAUDE.md §4가 옳았다.
2. **Task 4·5가 `ProductShell.tsx`를 두 번 고치면서 OSS provenance 해시 갱신을
   빠뜨렸다.** 그 파일 헤더가 "내용 바꾸면 `docs/oss/editor-ui-source-map.json`의
   `normalized_sha256` 두 곳을 같이 갱신하라, 이 검증은 프론트엔드 스위트가 아니라
   전체 백엔드 스위트에서만 돈다"고 명시했는데, 매 Task마다 frontend-only 검증만
   돌리다 보니 Task 7의 최종 전체 pytest에서야 5건 실패로 드러났다. 실제 해시로
   갱신해 고쳤다(`8e99a308e`). **다음에 `apps/web/src/app/ProductShell.tsx`를 고칠
   때는 이 파일 헤더를 먼저 읽어라.**

### 미해결 — owner 결정 필요

**승인된 편집 작업판 스냅샷 5장이 코드보다 낡아 있다.** 2026-08-15 세션 초반에
이미 그랬고(재승인 없이 원복함, 위 절 참고), 이번 UX 개편으로 레이아웃이 더 바뀌어서
지금은 그때보다도 더 벌어져 있다. 재생성·재승인은 owner 판단이다.

**나머지 후속 항목은 계획서의 "하지 않을 것" 절에 이미 기록돼 있다** — 재료 전면
통합(라이브러리+촬영본+프로젝트 자산)과 5단계 단일 작업판은 이번 범위에서 의도적으로
제외했다. Task 1~6을 owner가 써본 뒤 별도 결정으로 진행한다.

### 검증 상태

자동 검증(pytest 3522 passed/53 skipped, Vitest 973 passed, build 통과, E2E 42+10
passed)과 실제 브라우저 6개 경로×2 해상도 순회(console error 0, overflow 0, 임시
문구 0)를 전부 닫았다. **owner acceptance는 아직 없다** — owner가 긴 원본으로 만든
완성본을 처음부터 끝까지 직접 보고 들은 적이 없고, 자막 타이밍·음량·B-roll 밀도도
owner 승인이 없다. 자동 검증과 실제 브라우저 확인은 owner acceptance를 대신하지
않는다.

### 2026-08-15 추가 — 스냅샷 두 번째 재승인, Start 모드 실검증 (HEAD `b4910f738`)

**스냅샷 재승인 범위가 처음 생각보다 컸다.** owner 승인을 받고 재생성해 보니
`editor-workbench-*.png` 5장뿐 아니라 `product-shell-*.png` 5장까지 **총 10장 전부**
sha256이 달랐다. Task 1~3이 편집기 레이아웃을 더 바꿨고, Task 4~5가
`ProductShell.tsx`를 두 번 바꿔서 그 스냅샷도 함께 낡아 있었다. 10장 전부
재생성하고 manifest를 갱신했고(`b4910f738`), 새 스냅샷 2장(1920px 편집기·대시보드)을
직접 열어 Task 4·5 결과(사이드바 세 구획 라벨, 홈 단일 문구)가 실제로 담겼는지
육안 확인했다. `docs/decisions/2026-07-20-editor-workbench-visual-approval.ko.md`에
"2026-08-15 두 번째 재승인" 절로 기록했다.

**`owner-ready.ps1 -Mode Start`를 실제로 돌려서 확인했다.** 결과: "바로 사용할
준비가 됐습니다", "VideoBox가 시작됐고 화면 연결 준비가 끝났습니다" — 깨끗하게
통과했다. **이번 세션 내내 `-Mode Start -Rebuild` 뒤에 나왔던
"[FAIL] 연결 준비를 확인하지 못했습니다"는 전부 타임아웃이 너무 짧았던 것이지
실제 시작 실패가 아니었다.** `-TimeoutSec 8~20`으로는 FAIL이 났지만
`-TimeoutSec 30`으로는 한 번에 통과했다. **다음 세션 참고: rebuild 뒤 준비 확인은
`-TimeoutSec 30` 이상으로 주고, 그래도 FAIL이면 그때 실제 문제로 조사한다.**
컨테이너 4개 전부 healthy, workspace는 재시작 없이 계속 떠 있었다. 실제 브라우저로
`/projects/my-project/home`을 열어 console error 0건, Task 4 결과 유지를 확인했다.

---

## 다음 세션 시작점 (2026-08-15 세션 종료 시점)

**이 절만 읽으면 이어서 작업할 수 있다.** 위 본문은 어떻게 여기까지 왔는지의
기록이고, 지금 당장 필요한 건 이 절이다.

### 현재 사실

- HEAD `382abe3b5`, `codex/videobox-container-compatibility`, 원격과 완전히 동기화(0/0)
- working tree 깨끗. main worktree는 이번 세션 내내 건드리지 않았다(그대로 `main`)
- `docs/superpowers/plans/2026-08-15-videobox-dashboard-ux-recovery.md`의 Task 1~7
  전부 `[x]`, 각 Task 실행 기록에 실측값·커밋 SHA 있음
- 편집 작업판·대시보드 스냅샷 10장 재생성·재승인 완료(owner 승인, `b4910f738`)
- `owner-ready.ps1 -Mode Check`와 `-Mode Start` 둘 다 실제로 돌려서 통과 확인
- 컨테이너는 현재 HEAD 소스로 떠 있다(workspace 포함 4개 전부 healthy)

### 이번 세션에서 배운 것 중 다음 세션이 반드시 지켜야 할 것

1. **전체 pytest는 절대 다른 무거운 작업과 동시에 돌리지 않는다.** 이번 세션에
   두 번 겪었다 — 시간에 민감한 테스트가 부하로 오탐 실패한다. 실패가 나오면
   그 테스트 파일만 격리 재실행해서 진짜 결함인지 먼저 확인한다.
2. **`-Mode Start -Rebuild` 뒤 준비 확인은 `-TimeoutSec 30` 이상**으로 준다.
   짧은 타임아웃의 FAIL을 실제 실패로 보고하지 않는다.
3. **`apps/web/src/app/ProductShell.tsx`를 고칠 때는 파일 맨 위 헤더를 먼저 읽는다.**
   내용을 바꾸면 `docs/oss/editor-ui-source-map.json`의 `normalized_sha256` 두 곳을
   같이 갱신해야 하고, 그 검증은 전체 백엔드 pytest에서만 돈다 — frontend 테스트만
   돌리면 놓친다.
4. **스냅샷 재생성은 owner 승인 없이 하지 않는다.** 승인받으면
   `VIDEOBOX_WRITE_PLAYWRIGHT_SNAPSHOTS=1`로 재생성하고, `apps/web/e2e/snapshots/`
   전부(편집기 5장 + 대시보드 5장)를 한 번에 확인한다 — 한쪽만 바뀐 줄 알았다가
   둘 다 바뀐 적이 있었다.

### 다음에 할 만한 것 (아직 시작 안 함)

1. **owner acceptance** — 대표님이 긴 원본으로 만든 완성본을 처음부터 끝까지
   직접 시청·청취, 자막 타이밍·음량·B-roll 밀도 승인, Hermes 실제 provider
   활성 상태에서 유진 라이브 대화 확인. 전부 사람만 할 수 있다.
2. **대표님이 요청한 "전체 시스템 점검 계획서"** — 완료됐다. 아래 2026-08-16 절 참고.
3. **UX 개편 계획서의 "하지 않을 것" 절** — 재료 전면 통합(라이브러리+촬영본+
   프로젝트 자산), 5단계 단일 작업판. Task 1~6을 대표님이 써보신 뒤 별도 결정.

---

## 다음 세션 시작점 (2026-08-16 갱신 — 이 절이 위 2026-08-15 절보다 최신이다)

**이 절만 읽으면 이어서 작업할 수 있다.**

### 현재 사실

- HEAD `2cf8a2bb0`, `codex/videobox-container-compatibility`, 원격과 완전히 동기화(0/0)
- working tree 깨끗
- `docs/superpowers/plans/2026-08-16-videobox-full-system-inspection.md` — 전체 점검
  완료. 자동 검증(pytest 3521+973+42+10, 오탐 1건 격리 판정 완료)·owner-ready
  Check/Start·실제 브라우저 6경로·스냅샷 10장 바이트 단위 일치까지 전부 초록.
- 스냅샷 재생성 재확인: `VIDEOBOX_WRITE_PLAYWRIGHT_SNAPSHOTS=1`로 다시 만들어 봐도
  `git status` 변경 0건 — 승인된 10장과 코드가 정확히 일치한다.
- 문서 낡음 2건(이 절의 이전 버전 HEAD 표기, UX 계획서 Task 7 체크박스)은 이번에
  발견 즉시 고쳤다.

### 남은 것 — 전부 사람만 할 수 있다

자동화·문서 정리로 닫을 수 있는 항목은 이제 없다.

1. **owner acceptance** — 대표님이 긴 원본으로 만든 완성본을 처음부터 끝까지 직접
   시청·청취, 자막 타이밍·음량·B-roll 밀도 승인.
2. **Hermes live chat** — gateway/provider가 실제 활성 상태일 때 유진 라이브 대화
   확인. 9119/9130 HTTP 200은 reachability일 뿐 live 증거가 아니다. provider 로그인은
   CLAUDE.md §6 승인 필요 항목이라 Claude가 임의로 진행하지 않는다.
3. **UX 개편 "하지 않을 것" 절의 보류 2건** — 재료 전면 통합, 5단계 단일 작업판.
   대표님이 Task 1~6을 써보신 뒤 결정.
4. **옛 자산 4개(`wave2-long-qa`, `wave2-short-a/b/c`) duration 재분석 여부** — 화면
   문구는 정직해졌으나(길이 정보 없음) 재분석까지 할지는 대표님 판단.

이 넷은 다음 세션이 코드로 대신 완료할 수 없다. Claude가 할 수 있는 일은 이미
2026-08-15·2026-08-16 두 세션에 걸쳐 전부 닫았다.

---

## 2026-08-16 후속 구현 — duration backfill + 라이브러리↔촬영본 카드 교차 진입

위 미해결 항목 3·4 중 대표님이 실제로 진행을 지시한 두 건을 구현했다. 계획서는
`C:\Users\atgro\.claude\plans\giggly-yawning-lightning.md`(로컬 plan 파일, 저장소 밖).
3개 탐색 에이전트로 실제 코드를 조사해 범위를 좁혔다 — 프로젝트 "자산" 단계까지
포함한 전면 통합과 5단계 단일 작업판 병합은 조사 결과 위험이 커서 **이번엔 하지
않기로** 대표님께 확인받았다(편집기 렌더링 파이프라인·4,173줄 테스트 파급,
세션 상태 공유 계층 부재·dock 2슬롯 한계가 각각의 이유).

### Task 1: 라이브러리 duration backfill (`d2213582`)

`library_ingest.py`의 `probe_metadata`는 ingest 시점 1회만 불렸고 실패하면 영구히
비었다 — 프로젝트 b-roll에는 있던 재시도 루프(`_backfill_broll_media_facts`)가
라이브러리 쪽엔 없었다. 같은 패턴으로 `_backfill_library_media_facts`를 추가하고
같은 60초 유지보수 루프 자리에 연결했다.

- 신규: `packages/core-engine/src/videobox_core_engine/library_media_facts.py`
- 신규 store 메서드: `LibraryUserAssetStore.update_technical_metadata`
- 신규 테스트: `tests/test_library_media_facts_backfill.py` (8개, 실제 ffmpeg로
  end-to-end 검증)
- 실제 컨테이너 재배포 후 유지보수 루프 1바퀴 확인: `wave2-long-qa.mp4`(18초),
  `wave2-short-a/b/c.mp4`(각 3초) 전부 실제 길이로 채워짐. "길이 확인 중"/"길이
  정보 없음" 0건.

### Task 2: 라이브러리↔촬영본 카드 레벨 교차 진입 (`73a61d30`)

기존 Task 6(2026-08-15) 링크는 자산을 **선택한 뒤** 미리보기 패널에만 보였다.
P3의 "이 일은 어느 화면이지?"는 선택 전, 그리드를 보는 시점에 이미 생기는 고민이라
링크를 카드/소스 항목 단위로 앞당겼다.

- `VideoAssetGrid.tsx` 각 카드에 "구간 정리하기" 추가(`stopPropagation`으로 카드
  선택과 분리), `FootageSourceList.tsx` 각 소스 항목에 "라이브러리에서 보기" 추가
  (`<Button>` 안에 `<a>`를 중첩할 수 없어 형제 요소로 재구성)
- 미리보기 패널의 기존 링크는 카드가 항상 보여주므로 중복이 되어 **제거**
  (`LibraryPreviewPane.tsx`, `FootagePreview.tsx`)
- 신규: `apps/web/e2e/library-footage-crosslink.spec.mjs` — `/footage`와 이
  교차 링크에 처음 생긴 E2E(3개)
- 실제 브라우저(1920×1080) 왕복 확인: 선택 없이 카드 링크 클릭 → 해당 자산이
  선택된 채 `/footage` 로드 → 그 소스의 링크 클릭 → 같은 자산이 선택된 채
  `/library`로 복귀. console error 0, 가로 overflow 0, 링크 키보드 포커스 가능.
- 라이브러리/촬영본 화면 자체의 Playwright 스냅샷은 없어 재승인 불필요했다(확인
  완료 — `apps/web/e2e/snapshots/`에 `editor-workbench-*`/`product-shell-*`뿐).

### 검증 결과 (두 Task 공통 게이트)

| 검증 | 결과 |
|---|---|
| Python 전체 (단독, Task 1 반영 후) | `3530 passed, 53 skipped` |
| Python 전체 (단독, 최종 게이트) | `3530 passed, 53 skipped` |
| frontend Vitest | `76 files / 975 passed` |
| production build | 통과 |
| Chromium E2E (`test:e2e`) | `45 passed` (신규 3개 포함) |
| editor-workbench E2E | `10 passed` |
| `git diff --check` | 통과 |
| 실제 컨테이너 재배포·브라우저 확인 | Task별로 각각 완료(위 참고) |

### 남은 것 — 이번에도 전부 사람 몫

1. **owner acceptance** — 여전히 미완료.
2. **Hermes 실제 provider(9119) 활성 상태에서 라이브 대화** — 여전히 미완료.
   화면이 실제로 쓰는 로컬 qwen 경로는 2026-08-16 앞선 절에서 실제 대화로 확인됨.
3. **UX "하지 않을 것" 남은 2건**(프로젝트 자산까지 포함한 전면 통합, 5단계 병합)
   — 이번 세션에서 조사 후 대표님이 명시적으로 보류 결정. 재론의는 owner 판단.
4. ~~옛 자산 4개 duration~~ — **이번 세션에서 해결.**

### 2026-08-16 코드리뷰 + 수정 (`0c7acc636`)

대표님 지시로 위 두 Task(`d2213582`, `73a61d30c`)를 8각도 코드리뷰(medium effort)했다.
실제 결함 6건을 찾았고 전부 이 세션에서 고쳤다. 전체 목록은
`C:\Users\atgro\.claude\plans\giggly-yawning-lightning.md`의 "실행 기록" 절 참고.
핵심 3건:

1. 카드의 "구간 정리하기" 링크에서 키보드 Enter를 누르면 이동 대신 카드가
   다시 선택됐다(부모 카드의 onKeyDown이 버블링된 keydown을 가로챔). RTL로
   재현 확인 후 링크에 `stopPropagation` 추가.
2. 영상을 선택한 채 음악/효과음 탭으로 바꾸면 그 카드가 안 보여 교차 링크
   자체가 사라졌다. 미리보기 패널의 링크를 복원해 해결.
3. 카드마다 링크 접근성 이름이 전부 "구간 정리하기"로 동일해 화면 리더로
   구분이 안 됐다 — 파일명을 포함하도록 `aria-label` 추가.

나머지 3건(backend): probe-실패 사이 자산 삭제 시 예외가 새는 문제,
컨테이너 심볼릭 마운트에서 root를 resolve 안 해 파일을 영원히 못 찾을 수
있던 문제, 0초 duration이 falsy라 무한 재시도되던 문제. 전부 수정하고
회귀 테스트 추가.

검증: 전체 pytest 단독 `3533 passed, 53 skipped`(오탐 없음), frontend
`977 passed`, build·E2E(`45 passed`) 통과, 실제 컨테이너 재배포 후 브라우저로
세 프론트엔드 수정 전부 재확인(키보드 Enter가 더 이상 선택을 안 바꿈, 음악
탭에서도 링크 생존, 카드 8개 링크 이름 전부 고유). console error 0건.

리뷰가 찾은 reuse 지적 1건(`_resolve_verified_path`와 router의
`source_for_user`가 같은 경로-검증 로직을 중복 구현)은 router 파일까지
건드리는 별도 범위라 이번엔 고치지 않고 계획 파일에 후속 항목으로 남겼다.

---

## 2026-08-16 근본 해결 작업 — 재료 통합 · 경로 검증 일원화 · 검토+출력 병합(부분)

대표님이 남은 항목을 "한 번에 완벽하게 근본적으로" 해결하라고 지시했다.
계획서는 `C:\Users\atgro\.claude\plans\giggly-yawning-lightning.md`(로컬, 저장소 밖).

### 조사에서 뒤집힌 전제 둘 — 이게 방향을 바꿨다

**1. "프로젝트 복사(materialize)를 없애는 게 근본 해결이다": 틀렸다.**
음악·효과음도 타임라인에 적용하는 순간 영상과 **똑같이** 프로젝트로 복사된다
(같은 `ProjectAssetMaterializer`, 같은 `local://projects/{id}/assets/{id}` 스킴).
복사는 예외가 아니라 모든 자산 유형에 일관된 의도적 안전장치다 —
`output_source_verifier.py`가 렌더 직전 `path.relative_to(project_root)`로 프로젝트
밖 파일을 fail-closed로 거부하고 sha256으로 바이트를 고정한다. 걷어내는 건 근본
해결이 아니라 안전장치 제거다. **복사는 유지하기로 확정.**

**2. "통합하려면 큰 재설계가 필요하다": 틀렸다. 원인이 훨씬 작았다.**
`MediaLibraryBrowser`는 처음부터 영상을 완전히 지원한다(`broll` 필터, `<video>`
미리보기, 개인 라이브러리 조회, 프로젝트 추가). 그런데 `MediaWorkspacePage`가 그걸
음악·효과음 탭에만 붙여놨다. **그래서 라이브러리에 이미 있는 영상을 프로젝트에 넣는
화면이 아예 없었고, 같은 파일을 다시 업로드해야 했다.** P3("이 일은 어느 화면이지?")의
진짜 원인은 데이터 모델이 아니라 이 빠진 연결이었다.

### 완료

**경로 검증 일원화 (`b34e8fe5f`)** — `videobox_storage/managed_path_resolution.py`
신설, 세 곳 위임, 중복 `_sha256` 세 벌 정리. 실패 사유를 구분해 돌려주므로 라우터의
422/404 구분이 유지된다. 커버리지가 없던 두 실패 분기를 테스트로 고정했다.
발견: 라우터의 422 분기는 정상 등록 경로로는 도달 불가능하다(도메인 모델이 `..`를
등록 단계에서 거부). 심볼릭 링크·옛 행을 위한 2차 방어선이다.

**재료 통합 (`525d5e1cc`, `f41afe661`)** — 영상 탭에 라이브러리 브라우저 연결,
"사용 중인 위치"를 링크로. 실제 컨테이너에서 왕복 확인(추가하면 자산 목록 5→6 자동
갱신, 라이브러리→프로젝트 이동). console error 0.

**검토 조회 훅 추출 (`6c55f6960`)** — `useTimelineReviewState`. 테스트 수정 0건으로
18개 통과 = 동작 보존 증명.

### 되돌린 것 — 검토+출력 화면 병합과 사이드바 5→4

만들어서 돌려봤더니 **E2E가 실제 회귀를 잡았다**: 두 컴포넌트를 조합하니 `listJobs`가
화면당 두 번 호출된다(`review-to-editor.spec.mjs`가 2회 기대, 실제 3회). 조합만으로는
병합이 성립하지 않는다.

제대로 하려면 `OutputsPage.refresh`를 공유 훅 위로 옮겨야 한다. 그 함수는 공통 5개와
출력 전용 5개를 한 `Promise.all`로 묶고 mutation 이후 경로에서 `options`로 값을
주입받는다. 걸린 테스트가 1,956줄이고 상당수가 프로젝트 A/B 누수 방지 경합 계약이다.
**렌더·승인 게이팅 경로라 반쯤 고친 상태가 안 한 것보다 나쁘다**고 판단해 되돌렸다.
훅은 남겼으므로 다음 작업은 `OutputsPage`를 그 위로 옮기는 것부터 시작한다.

### 검증

pytest 전체 단독 `3542 passed, 53 skipped`(오탐 없음), frontend `980 passed`,
build 통과, E2E `46 passed`, `git diff --check` 통과, 실제 컨테이너 배포 후 브라우저 확인.

### 2026-08-16 이어서 — 검토+출력 병합 완료 (`e4c18228e`)

앞 절에서 되돌렸던 병합을 제대로 끝냈다. 되돌린 이유였던 중복 조회를 실제로 없앤 것이
차이다.

**한 번만 읽는다.** `useTimelineReviewState`가 판정(`state`)과 원본(`data`)을 나눠서
내보내고, `refresh()`가 읽은 값을 **돌려준다**. 출력 화면은 `shared`/`onSharedRefresh`를
**선택적 prop**으로 받아 -- 안 주면 지금까지처럼 스스로 읽으므로 그쪽 테스트 80개는
한 줄도 안 바뀌었다. 합쳐진 화면에서만 공유 읽기를 쓴다.

구현하며 두 번 걸렸고 둘 다 테스트가 잡았다.
1. `shared` 객체를 `refresh`의 의존성에 뒀더니 새 값이 올 때마다 `refresh`가 다시
   만들어지고 그 effect가 또 읽어서 **끝없이 돌았다**. ref로 끊었다.
2. 처음 그릴 때도 공유 읽기를 불러서 여전히 두 번 읽혔다. 첫 렌더는 이미 온 값을
   쓰도록(`reuseShared`) 고쳤다. `ReviewAndOutputPage.test.tsx`가 "화면당 한 번"을
   고정한다.

**판정은 합치지 않았다.** 검토 쪽은 변형 일치까지 보고, 출력 쪽은 거기에 더해
"승인됨 + 확인할 항목 0건"을 요구한다. 비슷해 보이지만 다르고, 합치면 무엇을 언제
내보낼 수 있는지가 조용히 바뀐다.

**사이드바 5개 → 4개**(기획·자산·편집·검토와 출력). `docs/decisions/2026-08-16-review-and-output-single-stage.ko.md`에
결정 기록(§6). `/review`와 `/output` 두 주소 모두 살아 있다 -- 한쪽을 리다이렉트로
접으면 그 주소로 직접 들어오는 기존 E2E 세 개가 끊긴다.

`ProductShell.tsx`를 고쳤으므로 `docs/oss/editor-ui-source-map.json`의
`normalized_sha256` 두 곳도 함께 갱신했다(그 검증은 전체 백엔드 스위트에서만 돈다).

**검증:** frontend `982 passed`, build 통과, E2E `46 passed`(중복 조회를 잡았던
`review-to-editor` 포함), 전체 pytest 단독 `3537 passed / 5 failed` → 실패 5건 전부
격리 재실행 `40 passed`로 부하 오탐 확인. 실제 컨테이너 배포 후 브라우저로
`/review`·`/output` 양쪽 확인: 단계 단추 4개, 헤더 "검토와 출력", 두 영역 한 화면,
다섯 호출이 화면당 한 번씩, console error 0, 가로 overflow 0.

**남은 것 (그대로):** owner acceptance(완성본 시청·승인), Hermes egress provider 로그인.
`product-shell-*.png` 스냅샷 5장은 사이드바가 바뀌어 낡았고, 재생성은 owner 승인 사항이라
하지 않았다.
