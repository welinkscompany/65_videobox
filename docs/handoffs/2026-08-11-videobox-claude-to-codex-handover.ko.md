# VideoBox 인계 — Claude Code에서 Codex로 개발 주체 전환 (2026-08-11 저녁)

계획서: `docs/superpowers/plans/2026-08-10-videobox-consolidated-priorities.md` (SSOT)
앞 인계: `docs/handoffs/2026-08-11-videobox-p2-1-one-spot-and-api-ts-one-spot.ko.md`

**이 문서의 목적이 다른 인계 문서와 다르다.** 지금까지 인계는 "다음 세션이 이어서 할 일"이었는데,
이번은 **개발 주체 자체가 바뀐다** — Claude Code가 토큰 소진으로 더 못 쓰게 되어 owner가 Codex로
옮겨간다. `CLAUDE.md`가 "2026-08-05부로 개발 주체를 Claude Code로 전환했다"고 못박아 둔 상태라,
Codex가 그 문서를 그대로 읽으면 자기 자신이 이 저장소를 건드리면 안 되는 것처럼 오해할 수 있다.
**그 문장은 이제 틀렸다.** 아래 "읽는 순서"부터 시작할 것.

## 지금 이 순간의 정확한 상태

- 활성 worktree: `.worktrees/videobox-container-compatibility`
- 브랜치: `codex/videobox-container-compatibility` (origin과 동기화됨, 워킹 트리 깨끗)
- 최신 커밋: `6a35da706 fix: stop the icon-collapsed sidebar and filter chips from lying about their own state`
- 백엔드 3,320 통과 / 53 건너뜀 / 실패 0. 프런트 850 통과. 타입체크 통과.
- `main` 브랜치는 컨테이너 마이그레이션 계획 문서만 있는 뒤처진 상태다. **`main`에서 작업 시작하지 말 것.**
- 컨테이너가 지금 켜져 있다: `http://localhost:5173`. `docker compose ps`로 `65_videobox-videobox-workspace-1`,
  `65_videobox-videobox-postgres-1` 둘 다 healthy인지 먼저 확인.

## 읽는 순서 (Codex 세션 시작 시 그대로)

1. `CLAUDE.md` — 최상위 지침. **"2026-08-05부로 Claude Code로 전환"이라는 문장만 무시하고, 나머지
   §0~§8 전부는 지금도 유효한 운영 규칙이다.** 특히 §0 세션 시작 체크리스트, §4 완료의 정의,
   §5 보호 경계, §6 승인이 필요한 변경은 도구가 바뀌어도 그대로 지킨다.
2. `docs/development-fast-path.ko.md` `## 10. 고정 운영 규정` — 운영 규정 SSOT. CLAUDE.md는 이 문서로
   가는 진입점일 뿐이다.
3. `docs/decisions/` — 승인된 시각 결정 세 건. **`2026-08-05-dashboard-white-orange-direction.ko.md`가
   현행 팔레트**(캔버스 `#FAFAFA`, accent `#C2410C`, 텍스트 `#1C1C1E`)다. 앞의 두 결정을 읽고 색을
   판단하면 틀린다.
4. `docs/implementation-plan.ko.md` §4·§8.4 — 제품 범위 경계. VideoBox는 CapCut 대체 경량
   후편집기지 풀 NLE가 아니다.
5. 이 문서 전체.
6. `git status --short`, `git log --oneline -10`, `git worktree list`로 위 상태 요약을 직접 재확인.

## 오늘(2026-08-11 오후~저녁) 세션에서 실제로 한 일

owner가 owner-ready 컨테이너를 직접 크롬으로 열어보고 화면이 깨졌다고 지적한 것에서 시작했다.
**"테스트 통과 = 완료 아니다"(`CLAUDE.md` §4)를 이번에 제일 세게 겪은 세션이다** — 아래 버그
세 개가 850개 프런트 테스트를 전부 통과한 채로 실제 화면에서만 드러났다.

### 커밋 순서와 각각이 드러낸 것

1. `3802b60c1` — P2-1 조용한 곳 1건(자산 캐시 열쇠 계산 실패 시 로그 없이 넘어가던 곳), `api.ts`
   안 쓰는 메서드 1개 정리.
2. `d0e9080c8` — **프로젝트 선택(첫) 화면이 브라우저 기본 폰트·배경으로 나오던 문제.** 원인:
   `.vb-ui`라는 CSS 클래스가 앱 전체 폰트/배경을 입히도록 정의는 돼 있었는데 **어디에도 실제로
   붙어 있지 않았다.** `AppRoot.tsx`에 붙여서 고쳤고, 프로젝트 선택 화면도 카드형으로 다시 짰다.
3. `8a1e291fa` — **사이드바가 화면 크기와 무관하게 항상 `display:none`.** Tailwind가 `md:block`
   유틸리티를 생성하지 못했고, 그걸 대비해 넣어둔 `!important` 안전장치 CSS가 실제 DOM 구조
   (`sidebar-wrapper` 바로 아래가 아니라 `.vb-product-shell`이 한 겹 더 있음)와 안 맞는 direct-child
   선택자를 쓰고 있었다. 같은 커밋에서 편집 작업판이 화면이 넓어도 패널 하나만 보이던 문제도
   고쳤다 — 유진(오른쪽) 패널이 `defaultPersisted.rightOpen: false`로 기본 닫혀 있어서 3분할
   (`desktop-both`) 모드가 첫 진입에 절대 못 뜨는 구조였다.
4. `6a35da706` — **owner가 실제 크롬 스크린샷을 보내줘서 잡은 것.** `8a1e291fa`로 사이드바는
   보이게 됐지만, 실제로는 텍스트가 전부 겹쳐서 나왔다. 진짜 원인 세 개:
   - `ui-system.css`가 `tailwindcss/utilities`만 import하는데 거기엔 breakpoint 토큰이
     없어서 **앱 전체에서 `sm:`/`md:`/`lg:` 반응형 클래스가 하나도 안 만들어지고 있었다**
     (`--breakpoint-*`를 `@theme`에 직접 선언해서 고침. **이 조사 과정에서 내가 grep 이스케이프를
     잘못 써서 "Tailwind 엔진 전체가 고장났다"고 몇 시간 잘못 판단했다 — 실제로는 각 케이스를
     `grep -oF`(고정 문자열)로 재확인하고서야 대부분 멀쩡하다는 게 드러났다.** 다음에 비슷한 걸
     조사할 때 이 함정을 또 밟지 말 것.)
   - 편집 화면은 작업판에 공간을 주려고 사이드바를 의도적으로 아이콘만 남기고 접는데
     (`AppRouter.tsx`의 `forceCollapsed`), **접힌 상태에서 텍스트를 숨기는 처리가 없어서** 48px
     폭 안에 프로젝트 이름·"완전 삭제" 같은 전체 텍스트가 그대로 밀려 나와 옆 콘텐츠와 겹쳤다.
     `group-data-[collapsible=icon]:hidden`을 텍스트 요소들에 붙여서 고침.
   - 자산 필터 칩이 `aria-pressed`는 정확히 계산하면서 Button `variant`는 안 바꿔서 **눌린 것도
     안 눌린 것도 전부 기본(주황) 배경**으로 보였다. `variant="ghost"`로 바꿔 커스텀 CSS의
     `[aria-pressed=true]` 규칙이 실제로 이기게 함. (처음엔 `variant="outline"`으로 바꿨다가
     그 variant 자체가 `bg-background`를 강제해서 또 안 먹혔다 — `ghost`가 배경 클래스를 안 갖고
     있어서 최종 선택.)

### 검증 방법 (이번에 신뢰할 수 있었던 것과 없었던 것)

- **Claude 자체 Browser pane은 이번 세션 내내 compositing이 안 됐다** — `screenshot`이 항상
  타임아웃, `getBoundingClientRect`가 fixed 요소에 0×0을 돌려줬다. computed style만으로는
  겹침·오버플로 같은 시각적 버그를 못 잡는다는 게 이번에 실증됐다(사이드바 width가 DOM
  기준 256px로 "정상"이라고 판단했는데, 실제 크롬에서는 48px에 텍스트가 밀려 나와 겹쳐 있었다).
- **`mcp__claude-in-chrome__*` 도구(진짜 크롬)로 바꾸고 나서야 실제 문제가 보였다.** 화면 검증이
  필요한 작업은 이제 Browser pane보다 이 경로를 먼저 쓸 것.
- 컨테이너 재빌드 → `owner-ready.ps1 -Mode Start` → 크롬에서 `location.reload(true)` 순서를
  매번 지켰다. 캐시 때문에 재빌드 직후 첫 로드가 깨진 채로 보인 적이 있었다(모듈 스크립트
  MIME 에러) — 그냥 새로고침하면 풀렸다.

## 다음 세션(Codex)이 이어서 할 것

1. **owner가 계속 실제 화면에서 직접 찾아주는 게 지금까지 제일 효율적이었다.** 이번 세션에
   드러난 버그 세 개 다 owner의 실제 크롬 스크린샷이 출발점이었다. 다음에도 화면이 이상하면
   스크린샷부터 요청할 것 — computed style 점검만으로 결론 내리지 말 것.
2. P2-1 나머지 63곳 — `docs/handoffs/2026-08-11-videobox-backlog-close-and-local-model-config.ko.md`에
   목록 위치가 있다.
3. `api.ts` 남은 17개 — 계획서 P3-1 표.
4. **홈 화면·검토 화면 등 편집 작업판 이외의 다른 화면도 이번과 비슷한 숨은 표시 버그가
   있을 수 있다.** 오늘 고친 세 개는 전부 "테스트는 통과하지만 실제로는 안 보이거나 겹치는"
   패턴이었다 — 같은 패턴을 다른 화면에서도 의심할 것.

## 검증 방법 요약

- 백엔드 전체: `.venv/Scripts/python.exe -m pytest -q` (약 25분)
- 프런트: `apps/web`에서 `npx tsc --noEmit` 그리고 `npx vitest run`
- 컨테이너: `.\scripts\owner-ready.ps1 -Mode Start`, 주소는 `http://localhost:5173`
- 화면 검증은 `mcp__claude-in-chrome__*` 계열로 실제 크롬 탭을 열어서 할 것. Browser pane
  compositing이 이번처럼 또 막혀 있으면 즉시 이 경로로 전환한다.

## 함정 (이번에 실제로 걸린 것)

- **CSS 겹침·오버플로는 computed style 점검으로 못 잡는다.** 실제 스크린샷이 유일하게
  신뢰할 수 있는 증거였다.
- **grep으로 CSS 안의 `\:`, `\[`, `\]` 같은 이스케이프 문자를 찾을 때는 `grep -oF`(고정 문자열)를
  쓸 것.** 정규식 이스케이프를 잘못 쓰면 실제로 있는 걸 없다고 오판한다 — 이번에 몇 시간을
  이걸로 날렸다.
- **Tailwind v4에서 `@import "tailwindcss/utilities";`만 쓰면 breakpoint 토큰이 없다.**
  `sm:`/`md:`/`lg:` 등 반응형 variant를 쓰는 곳이 있다면 `@theme`에 `--breakpoint-*`를 직접
  선언해야 한다. 이 저장소는 `apps/web/src/ui-system.css`에 이미 선언해 뒀다 — 지우지 말 것.
- **`forceCollapsed` 같은 "의도적으로 축소된 상태"를 만들 때는 안에 든 커스텀 콘텐츠가 그
  상태를 실제로 아는지 항상 확인할 것.** shadcn 프리미티브(`SidebarMenuButton` 등)는 자동으로
  아이콘 모드에 반응하지만, 손으로 짠 `<Button>`/`<div>` 나열은 아무것도 자동으로 안 된다.
- **Button의 `variant`는 그 자체로 배경/테두리 유틸리티 클래스를 갖고 있어서, 커스텀 CSS로
  같은 요소의 배경을 다르게 그리고 싶으면 `variant`가 그 배경 클래스를 아예 안 갖는 걸
  골라야 한다** (`ghost`가 그런 경우다. `outline`은 `bg-background`를 갖고 있어서 안 된다).

## Codex 데스크톱 회복 검증 추가 기록 (2026-08-12)

이번 세션에서 공식 `owner-ready.ps1`로 재빌드한 VideoBox 런타임에 대해 PC 뷰포트와 전용 QA 프로젝트 흐름을 별도 증거로 남겼다. 테스트 통과나 API 응답만으로 화면 완료를 주장하지 않으며, 브라우저 mutation과 owner 미디어 수락은 아직 별도 게이트다.

- 공식 컨테이너 route matrix: 1920×1080, 1440×900, 1366×768, 1280×800에서 `home/media/editor/review/outputs`를 캡처했다. 편집 작업판은 내부 스크롤을 유지하고, 좌우 overflow는 뷰포트 안에 제한됐다. 증거는 저장소에 커밋하지 않고 `artifacts/qa/desktop-owner-ui-recovery/desktop-route-matrix.json`에 보관한다.
- 전용 프로젝트: 표시명 `VideoBox PC QA 20260811153350`, ID `videobox-pc-qa-20260811153350`. 실제 runtime에 프로젝트·입력·timeline·editing session·출력물을 보존 중이며 삭제하지 않았다.
- readiness/bundle: `readiness_f0af1c8fa712`가 `ready`, `draft_bundle_181a4cb8e136`가 `editing_session_draft_df9d45c44366` / `timeline_draft_af114f8dd7c1`을 생성했다.
- 편집/재검토: caption mutation으로 revision 1→2가 됐고, 기존 승인이 `editing_session_mutation`으로 stale 처리됐다. refresh 후 revision 2 검토본이 current가 되었고 `timeline_build_job_draft_122874723df7` 승인이 성공했다.
- 출력: `subtitle_render_job_002`, `final_render_job_003`, `capcut_draft_export_job_004`가 모두 succeeded. MP4는 5초, 1920×1080 H.264/AAC, 48kHz stereo이며 SRT와 대표 프레임을 확인했다. 상세 SHA-256/경로는 무시되는 `artifacts/qa/desktop-owner-ui-recovery/qa-mutation-manifest.json`에 있다.
- 자체 편집기 추가 점검: 실제 QA 편집기에서 미리보기·자산 원본 audition→편집본 복귀·타임라인 선택·캡션 dirty/save·reload 보존·재생을 확인했다. 작은 뷰포트에서 preview 내용이 패널보다 클 때 `place-content:center`가 헤더를 위로 밀던 시각 버그를 발견해 `place-content:start`로 수정했고, 회귀 테스트를 추가했다. 1280×720/1440×900 스크린샷과 재생 수치는 동일 manifest에 기록했다.
- CapCut: export artifact는 생성됐지만 컨테이너 API의 handoff registration은 “CapCut 설치를 확인한 뒤 다시 시도하세요”로 실패했다. 반면 호스트 `owner-ready -Mode Check`는 CapCut 9.1.0.3879 설치를 pass로 보고했다. `owner-ready.ps1 -Mode OpenCapCut`의 `opened=true`는 URI/앱 열기 요청만 뜻하므로 Desktop import/open 성공으로 해석하지 않는다.
- CapCut Desktop 추가 확인(2026-08-12): `OpenCapCut`으로 실제 CapCut 창을 연 뒤 새 프로젝트에서 runtime `output.mp4`를 파일 선택기로 가져왔다. 미디어 패널에 `output.mp4` 00:05가 나타났고, 미리보기에서 영상과 캡션이 표시됐다. 이는 Desktop import/open 증거이지만 전체 시청·청취와 자막 타이밍 owner 승인은 아직 별도 게이트다.
- 제한: 브라우저 파이프가 대용량 업로드 평가 중 끊겨 전용 프로젝트 생성·가져오기 클릭 자체의 live UI 증거는 남기지 못했다. 이후 실제 QA 편집기에서는 편집·reload·재생을 별도로 확인했다. API mutation은 공식 런타임 계약 검증으로 기록하되 생성/가져오기 UI 검증과 합치지 않는다. MP4 전체 시청/청취·자막 타이밍 및 owner 승인도 미완료다.
- 운영 상태: `owner-ready -Mode Check -Json`에서 VideoBox/workspace/upstream/data/model/CapCut check는 통과했고 Hermes dashboard 연결 거부만 별도 blocked 상태다. Hermes를 통과로 꾸미거나 직접 compose를 실행하지 않는다.
- 브라우저 UI mutation 추가 확인(2026-08-12): `/projects`에서 `VideoBox UI QA 20260812ㄱ`을 만들고, 대본 입력·기획 승인·자산 파일 선택기 import·readiness 재준비·초안 만들기·편집 미리보기·검토 승인·자막/MP4/CapCut 출력까지 실제 화면에서 순서대로 실행했다. 첫 파일 선택은 잘못된 worktree 경로라 실패 메시지를 확인했고, 올바른 절대 경로로 재시도해 성공했다. UI 프로젝트 slug는 `videobox-ui-qa-20260812`, session은 `editing_session_draft_f57d568991ff`, timeline은 `timeline_draft_fc6f22b6d311`이다. CapCut 등록은 컨테이너 연결 진단 실패 상태를 화면에 표시했으며, Desktop import/open은 별도 호스트 확인 증거를 유지한다.
- 대시보드 카피 정리(2026-08-12): 승인된 화이트·오렌지 방향 안에서 설명형 문장을 키워드형 상태로 바꿨다. 홈 상단은 `다음 작업` / `대본 · 자산 · 편집 · 출력`, 카드 제목은 `자산`·`편집`·`완성본`, 상태는 `초안 있음`·`부족 N곳`·`준비 완료`·`N개`로 표시한다. 유진 빈 상태도 `유진 대화 · 편집 필요`, 대화 빈 목록은 `질문 입력`으로 단순화했다.
- 현재 런타임 재검증(2026-08-12): 동일 공식 컨테이너에서 `home/media/editor/review/outputs` 5개 경로를 1920×1080·1440×900·1366×768·1280×800으로 다시 열어 총 20개 조합을 확인했다. 전부 오류 없음·가로 overflow 없음이며, 출력 화면의 세로 길이는 출력 목록 자체의 내부 콘텐츠에 따른 것이다. 이 검증은 `artifacts/qa/desktop-owner-ui-recovery/qa-mutation-manifest.json`의 `dashboard_keyword_viewports`와 별도로 현재 소스/런타임 상태를 재확인한 결과다.
