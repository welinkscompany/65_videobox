# 2026-08-30 인계 — RightDock 3탭 분리, 프로젝트 생성→편집기 직행, 스크롤바/다크 테마 결함 수정

## 배경

owner가 설치된 Tauri 데스크톱 앱을 직접 써 본 뒤 네 가지를 지적했다 (원문 요약):

1. "스크롤이 끝에 있는게 아니던데?"
2. "프로젝트 만들기를 누르면 바로 편집기를 가는게 아니던데."
3. "편집기에서 유진이랑 대화하는 박스 창은 내가 구분해서 탭으로 정리하라고
   했더니, 하나도 안하고 그냥 다 때려박아 넣었구나."
4. "영상 재생이나 스크롤도 컬러가 다크랑 맞지도 않고... 캡컷처럼 바로
   프로젝트 만들기 누르면 편집기 화면으로 나오도록 하라니까"

넷 다 재현·근본 원인 확인 후 고쳤다. 자세한 경위와 코드 위치는
`docs/decisions/2026-08-30-capcut-button-level-parity.ko.md`의 "6단계"에
남겼다 — 이 문서는 턴 종료 보고 형식(§7/§10.9)에 맞춘 요약이다.

## 이번 세션에서 실제로 한 일

### 1. 스크롤바가 창 끝에 안 붙던 버그 (CSS, Tauri 전용 아님)

가운데 정렬·`max-width:1200px`인 `.vb-product-content`가 자기
`overflow-y:auto`를 갖고 있어서, 창이 그 너비보다 넓으면 스크롤바가
콘텐츠 박스 오른쪽 끝(창 끝보다 안쪽)에 붙었다. 순수 크롬 탭에서도
재현 — Tauri WebView 특유의 문제가 아니었다.

**고침**: `overflow-y`를 전체 폭 부모 `.vb-product-main`으로 옮기고,
편집기 경로만 예외로 남겼다(`:not(:has(.vb-editor-workbench))`) — 편집기는
`editor-workbench.css`에서 이미 자기 스크롤을 따로 관리한다.
(`apps/web/src/styles/product-shell.css`)

### 2. "+ 새 프로젝트 만들기"가 편집기로 바로 안 가던 문제

`2026-08-28` 결정이 이 단추를 기획(`plan`/`CreationInterview`) 화면으로
보내게 정했었다. 캡컷은 이름을 물어도 이야기 화면 없이 편집기로 바로
간다는 owner 재지시(2026-08-30)로, **이 단추 하나만** 빈 편집 세션을
만들어 편집기로 바로 가도록 되돌렸다. `2026-08-28` 결정 전체를 뒤집는
것은 아니다 — `빈 편집판으로 바로 시작`·`내 목소리 등록·클론` 두 지름길,
그리고 `/create` 경로·`CreationInterview` 자체는 그대로다(직접 URL로
들어가면 여전히 뜬다).
(`apps/web/src/app/AppRouter.tsx`의 `goToNewProject`)

### 3. 유진 대화창이 탭으로 안 나뉘어 있던 문제 — RightDock 3탭 분리

이전 세션 지시("구분해서 탭으로 정리")가 실제로는 반영되지 않고 배경만
검정으로 바뀌어 있었다. `RightDock.tsx`를 **속성 / 유진 / 추천** 세
탭(`role="tab"`)으로 나눴다 — 캡컷처럼 한 번에 하나만 보인다. 기억
패널은 따로 탭을 만들지 않고 유진 탭 안, 대화 다음 자리에 넣었다(대화와
기억 후보를 같이 봐야 하는 흐름이 잦아서).

탭 전환마다 대화 DOM이 완전히 마운트 해제되므로, 스크롤 복원
`useLayoutEffect`의 의존성 배열에 `pane`을 추가해야 했다 — 안 넣으면
유진 탭을 떠났다 돌아올 때마다 스크롤이 맨 위로 리셋되는 **실제 회귀**가
있었다(테스트로만 잡히는 문제가 아니었다).

### 4. 네이티브 컨트롤이 다크 테마와 안 맞던 문제

`apps/web/src/ui-system.css`의 `:root`에 `color-scheme: dark;` 한 줄
추가. 스크롤바·`<video>` 컨트롤 같은 브라우저/WebView2 네이티브 UI가
이 값 하나로 다크 대응 렌더링이 된다 — 기존 색상 값은 안 건드렸다.

## 검증

- **테스트**: RightDock 탭 분리로 4개 시험 파일(`right-dock.test.tsx`,
  `yujin-memory-panel.test.tsx`, `editor-workbench.test.tsx`,
  `editor-workbench-route.test.tsx`)과 `AppRouter.test.tsx`가 전부
  깨졌다 — 거의 모든 시험이 "세부 정보"를 연 뒤 곧바로 유진 대화창·추천
  후보에 접근했는데, 이제는 탭을 먼저 눌러야 그 안 내용이 DOM에 존재한다.
  전부 고쳐서 **프런트엔드 전체 시험 1,371개 통과**, `tsc -b --force`
  통과. `task22-parity-owners.test.ts`의 증거 문자열 하나도 이름이 바뀐
  시험 제목을 못 찾아서 다른(여전히 유효한) 시험으로 바꿨다.
- **컨테이너 재빌드**: `docker compose build --no-cache videobox-workspace`
  (아래 "감수한 것" 참고 — 캐시 없이 해야 확실하다) 후
  `scripts/owner-ready.ps1 -Mode Start`.
- **브라우저 실측** (`http://127.0.0.1:5173`):
  - `.vb-product-main`의 `getBoundingClientRect().right`가 창 폭과 일치
    (스크롤바가 창 끝에 있음), `.vb-product-content`는 더 이상
    `overflow-y`를 갖지 않음.
  - `getComputedStyle(document.documentElement).colorScheme === "dark"`.
  - "+ 새 프로젝트 만들기" → 이름 입력 → "만들기" → 곧바로
    `/projects/{id}/editor?session_id=...`로 이동 확인.
  - "세부 정보" 도크에서 `속성`·`유진`·`추천` 세 탭이 실제로 존재하고
    각각 클릭 시 해당 내용(편집 항목 / 대화·작성창 / 추천 후보)만 보임.

## 커밋·푸시

- 커밋 `64718624` (`codex/videobox-container-compatibility` 브랜치).
  파일: `AppRouter.tsx`/`.test.tsx`, `RightDock.tsx`,
  `editor-workbench-route.test.tsx`, `editor-workbench.test.tsx`,
  `right-dock.test.tsx`, `yujin-memory-panel.test.tsx`,
  `product-shell.css`, `ui-system.css`, `task22-parity-owners.test.ts`.
- **푸시는 안 했다** — 이 세션에서 push 지시가 없었다.

## 감수한 것 / 남은 것

- **Docker BuildKit 캐시 버그 — 조사했으나 재현 안 됨(같은 세션에서 정정)**:
  처음엔 `docker compose build`가 `--no-cache` 없이는 `COPY apps/web ./`
  레이어를 잘못 캐시한다고 보고 `--no-cache`로 우회했다. 뒤이어 실제로
  재현을 시도했다 — `ui-system.css`에 표식 주석을 붙이고 plain
  `docker compose build videobox-workspace`와 `owner-ready.ps1`이 쓰는
  `... build --pull=false videobox-workspace`를 각각 돌렸는데, **둘 다
  캐시 없이 정상적으로 다시 빌드됐다**(`CACHED` 없음). 원래 증상("재빌드
  해도 화면이 그대로")은 Docker 레이어 캐시가 아니라 이미 알려진
  **브라우저 쪽 번들 캐시**([[videobox-container-rebuild-stale-bundle]])였을
  가능성이 크다. 별도 조사 작업(`task_859f7ea4`)은 취소했다 — 재현이
  안 되는 것을 계속 조사하는 건 낭비다. 같은 증상이 다시 나오면 Docker
  캐시보다 브라우저 번들 해시 비교를 먼저 본다.
- **Smart App Control**: clean Tauri 빌드에서 매 컴파일마다 새로 나오는
  proc-macro DLL을 개별적으로 계속 막는 것을 이전 확인에서 재확인했다.
  owner가 "항목별 예외로 처리하겠다"고 결정한 사안이라 이번엔 추가 조치
  없음 — 시스템 보안 설정이라 내가 건드리지 않는다.
- **RightDock 재설계는 UI/시각 변경**이라 재사용 게이트·승인 기록 확인
  대상이다 — `2026-08-30-capcut-button-level-parity.ko.md`가 이미 이
  버튼 단위 벤치마킹 전체를 승인한 문서이고, 그 문서의 3단계 절 중
  "오른쪽은 탭이 하나뿐이라 전환할 대상이 없다"는 서술이 이번 수정으로
  사실과 달라져서 같은 문서 안에서 정정·6단계 추가로 남겼다(새 승인 문서
  없이, 같은 승인 범위 안에서의 사실 갱신).
- Tauri 데스크톱 셸 자체의 남은 항목(임시 아이콘 등)은 이번 세션 범위
  밖 — `2026-08-30-installed-desktop-shell-tauri.ko.md`가 이미 다룬다.

## 2026-08-30 이어진 세션 — Tailwind 번호 척도 유틸리티 결함, 원인 확정·수정 (커밋 `b5cefd67`)

대표님 지시로 별도 조사 작업(`task_aa8e8c60`)을 이 세션에서 직접
진행했다.

**원인**: `apps/web/src/ui-system.css`가 `@import "tailwindcss/utilities"`만
불러오고 `tailwindcss/theme.css`는 안 불러온다. 그 파일의
`--spacing: 0.25rem` 하나가 `size-*`·`h-*`·`w-*`·`gap-*`·`p-*`·`m-*`
같은 번호 척도 유틸리티 전부의 계산식(`calc(var(--spacing) * N)`)에
쓰인다 — 이 값이 없으면 컴파일러가 그 유틸리티 클래스들을 **아예
만들지 않는다**(계산이 틀리는 게 아니라 없다). 실측: 컴파일된 CSS가
91.96KB에서, 이 값을 추가한 뒤 102.26KB로 늘었고 `size-4`·`h-9`·
`gap-2`·`px-4`가 실제로 나타났다.

**영향 범위**: 거의 모든 버튼이 쓰는 공용 `Button` 컴포넌트
(`src/components/ui/button.tsx`)가 이 유틸리티들로 크기를 정한다 —
그래서 편집기 툴바·첫 화면 카탈로그 두 곳에 이미 개별 우회
(`svg { width:1rem; height:1rem }`)가 있었다. 이 값이 `size-4`와
정확히 같아서(1rem) 고친 뒤에도 충돌하지 않았다.

owner에게 "지금 적용/적용만 하고 나중에/적용 안 함" 세 선택지로 물어
**"지금 적용하고 화면 전체를 훑어서 검증"**을 골랐다. `@theme` 블록에
`--spacing: 0.25rem;` 한 줄 추가 → `tsc -b`·`vitest run`(1,371개)
통과 → 재빌드·재기동 → 브라우저에서 프로젝트 카탈로그·편집기 세 탭
(속성/유진/추천) 전체 훑음: 아이콘 전부 16×16으로 일관, 가로 넘침
0건, 뷰포트 초과 요소 0건. 커밋 `b5cefd67`, push는 안 함.

## 2026-08-30 세 번째 이어진 세션 — 유진 대화창을 캡컷 EditPilot처럼 독립 패널로 (커밋 `21855f21`)

대표님이 캡컷 캡처를 추가로 보내며(§7, `capcut-observed` 문서) 이렇게
지시했다: **"우리 유진 대화창도 캡컷처럼 해도 되"** — 캡컷 EditPilot이
알고 보니 속성 도크의 탭이 아니라 화면 구석에 뜨는 독립 패널이었기
때문이다. 구현 방식 두 가지(구조 변경 / 디자인만) 중 **구조 변경**을
골라 달라고 확인받았다 — 바로 전 세션에 만든 3탭 구조(속성/유진/추천)를
다시 재작업하는 비용을 감수하고서.

**한 일**: `YujinPanel.tsx`를 새로 만들어 유진 대화(로그·작성창·대화
스타터·완료 체크리스트·대본 추출·편집안 다이얼로그·기억 패널)를 통째로
옮겼다. `RightDock`은 다시 속성/추천 두 탭으로 좁아졌다. `EditorWorkbench`가
`YujinPanel`을 화면 구석에 `position: absolute`로 띄우고, 열림 상태를
속성/추천 도크와 완전히 별개로 관리한다 — 도크를 닫아도 유진 대화는
남는다.

**검증**: 5개 시험 파일 재작업 + 유진 전용 시험 21개를 새
`YujinPanel.test.tsx`로 이전. 라우트 시험 하나는 기대값이 정확히
뒤집혔다("도크가 닫히면 유진도 닫힌다" → "도크를 닫아도 유진은 남는다",
새 구조에서 맞는 동작이라 고쳤다). 프런트엔드 전체 1,373개 테스트,
`tsc -b` 통과. 재빌드 후 브라우저에서 직접 확인: 도크는 정확히 두 탭,
화면 구석 "유진" 알약 버튼이 독립적으로 열고 닫히고, 속성 서랍을 닫아도
유진 패널은 그대로 열려 있었다.

**남긴 것 — owner가 바로 뒤집었다**: "추천 카드는 화면 공간이 더 필요해
떠있는 패널에 안 맞는다"고 적었던 판단을 owner가 곧바로 반박했다:
"그니까 내말이 그래서 캡컷도 화면공간이 필요해서 버튼들을 엄청 작게
만들었어. 그래서 나도 캡컷을 벤치마킹하라고 한거잖아." 아래 네 번째
이어진 세션에서 뒤집었다.

## 2026-08-30 네 번째 이어진 세션 — 추천 후보까지 유진 대화 로그 안으로 (커밋 `2a1013ea`)

owner 반박 직후 착수. 카드를 어디에 넣을지 물어 **대화 로그 안에
메시지와 섞어서**로 정했다(캡컷 EditPilot이 실제로 그렇게 한다 — §6,
제안 세 개가 인사말 바로 다음, 대화 안에 있다).

**한 일**: `RightDock`을 다시 좁혀 `속성` 하나뿐으로 만들고(탭이 하나면
탭 줄 자체를 없앴다), `YujinPanel`이 제안 메타·일괄 고르기·후보 카드·
적용 단추·검사 결과까지 전부 흡수해 대화 로그 안, 완료 체크리스트
다음 자리에 뒀다. 카드는 전용 압축 스타일(`.vb-yujin-panel__candidate`)
로 20rem 패널 폭에 맞췄다 — 항목은 안 빼고 글자·여백만 줄였다.

**검증**: `right-dock.test.tsx`를 속성 전용 4개로 줄이고 추천 시험
20개를 `YujinPanel.test.tsx`로 이전, `rightDockWiring.test.ts`의 낡은
손잡이 수 기준도 완화했다. 전체 1,372개 테스트·`tsc -b` 통과. 재빌드
후 브라우저에서 확인: 속성 도크는 탭 없이 바로 보이고, 유진 패널을
열면 제안 메타·후보 카드·적용 단추가 대화 로그 안에 이어져 보였다.
카드 폭 272px가 패널 346px 안에 깔끔히 들어가고 가로 넘침은 0건이었다.

## 2026-08-31 다섯 번째 이어진 세션 — 코드리뷰·갭검증·역방향검증

owner 지시: "코드리뷰 갭검증 역방향 동작검증 하고 커밋 푸쉬하자."

**직전 작업(네 번째 세션의 타임라인 겹침 수정)을 고치다가 새 결함을
냈고, 그걸 코드리뷰 에이전트가 잡았다.** `YujinPanel`을 `.vb-editor-workbench__body`
안으로 옮기면서 원래 자리(export `Dialog` 뒤)의 옛 블록을 안 지웠다 —
`grep -n "<YujinPanel"`이 두 줄(677, 805)을 돌려줬다. 라인바이라인 스캔
에이전트가 잡아냈고, 즉시 옛 블록을 지웠다(`grep`으로 한 곳만 남은 것 확인).

**자기 작업을 결함으로 오진할 뻔한 것도 하나 있었다 — 뒤집었다.** 효율
관점 리뷰 지적("패널이 접혀 있어도 자동 재추천 효과가 로컬 모델을
계속 돌린다")을 그대로 적용해 `open` 가드를 넣었더니, 전체 시험에서
`editor-workbench-route.test.tsx`의 "re-asks by itself..." 시험이 깨졌다.
그 시험은 `속성` 도크만 열고 유진 패널은 안 열어도 재추천이 스스로
도는 것을 **의도적으로 고정한** 계약이었다(YujinPanel이 늘 마운트돼
있는 것 자체가 이 배경 재요청을 지키기 위해서였다). 효율 지적을 그대로
적용하면 이미 테스트로 굳힌 동작을 깬다는 뜻이라, `open` 가드를
되돌리고 그걸 검증하던 새 시험도 지웠다.

**코드리뷰 8개 앵글 실행 → `ReportFindings`로 10건 보고.** 그 중 즉시
고친 것 셋:
- 위 중복 `<YujinPanel>` 렌더 (correctness, CONFIRMED)
- 타임라인 겹침 (correctness, CONFIRMED — 1920px에서 겹침 0px로 실측 확인)
- `editor-workbench.test.tsx`의 `openInspector()`가 이제 없는 `역할="tab", 이름="속성"`을
  누르려던 것(RightDock이 탭을 없앤 뒤 죽은 채로 통과만 하던 시험) — `openDetailDock()`
  재사용으로 교체
- 덤으로 `editorWorkbenchReadOnlyAdapters.tsx`의 죽은 `director` prop 정리(호출부도 같이)

남겨 둔 것(판단이 필요하거나 이번 범위 밖이라 owner에게 넘김):
- `hasSelectedSegment={selectedSegmentId !== null}`이 속성 도크의 실제
  "선택 구간 없음" 판정보다 넓다 — 유진 대화 시작 문구만 영향
- `goToNewProject`에서 `createBlankEditingSession`이 실패하면 프로젝트는
  이미 만들어졌는데 사용자에겐 "프로젝트를 만들지 못했습니다"로 뜬다
- Tailwind `--spacing` 수정은 같은 문제의 일부만 고쳤다 — `--text-*`,
  `--font-weight-*`, `--tracking-*`, `--shadow-xs`/`--shadow-sm`도 같은
  이유(기본 테마 미포함)로 컴파일 안 되는 게 v4.2.2 컴파일러로 직접
  확인됨(15개 이상 파일, shadcn/ui 컴포넌트 전체 포함)
- `mediaKindLabel`의 `broll → "영상"`이 `EditorWorkbench.tsx:805`·
  `inspectorRegistry.ts:120`의 `broll → "B-roll"`과 어긋남
- `rightDockTypes.ts`의 `onRetryMessage`/`retryAfterSeconds`는 죽은 필드
  (이번 세션 전부터 죽어 있었음, 새 회귀 아님)
- `YujinPanel`이 닫혀 있어도 추천 후보 파생 상태를 매 렌더 계산

**검증**: `tsc -b --force`·전체 vitest(1,372개) 두 번 다 통과(위 두 수정
전후로). 워크트리 소스를 직접 서빙하는 vite 개발 서버(`localhost:5199`,
`/api`를 실제 8000 백엔드로 프록시)에서 실제 프로젝트를 열어 실측:
"유진" 버튼·`.vb-yujin-panel__toggle` 정확히 1개, 1920×1080에서 패널
bottom(644.97)이 타임라인 top(757.97)보다 위 — 겹침 0px, 1280×800에서도
겹침 0px. 속성 도크를 닫아도 유진 패널은 그대로 열려 있고, 유진을
닫으면 알약 버튼 하나로 정확히 접혔다.

## 2026-08-31 여섯 번째 이어진 세션 — 남긴 항목까지 전부 근본 해결

owner 지시: "남은부분 모두 문제없이 근본적으로 해결해줘. 완료하면 미구현
부분 설명해줘." 다섯 번째 세션에서 판단만 하고 미룬 항목을 하나씩
실제로 고쳤다.

- **`hasSelectedSegment`**: `selectedSegmentId !== null`(범위가 넓음) 대신
  `selectedNarration !== null`을 쓰게 했다 -- 속성 도크가 "선택 구간이
  없어요"를 판정할 때 쓰는 것과 **같은 계산**(`findNarrationOrCaptionBySegment`)
  이라 이미 `EditorWorkbench.tsx`에 있었다. 새 로직을 만들지 않고 기존
  값을 재사용했다.
- **`goToNewProject` 오류 문구**: `handleCreate`에서 `createProject`와
  `goToNewProject`(세션 생성+이동)의 실패를 이제 각각 잡는다. 프로젝트
  생성 자체가 실패하면 기존 문구 그대로, 그 다음 단계(세션 생성·이동)만
  실패하면 카탈로그를 새로고침해 프로젝트가 목록에서 안 사라지게 하고
  "프로젝트는 만들어졌지만 편집기를 열지 못했어요"로 정확히 말한다.
- **Tailwind 테마 네임스페이스 전체**: `--spacing`만으로 안 끝났던 나머지
  절반(`--text-*`, `--font-weight-*`, `--tracking-*`, `--leading-*`,
  `--shadow-*`)을 Tailwind 자신의 기본값 그대로 `@theme`에 추가했다.
  색은 안 건드렸다(그래서 여전히 전체 `tailwindcss`는 안 불러온다).
  **빌드해서 직접 확인**: 압축 CSS가 102KB → 107.55KB로 늘었고,
  `.text-sm{`·`.font-medium{`·`.font-semibold{`·`.tracking-wide{`·
  `.shadow-xs{`·`.shadow-sm{`가 전부 실제로 컴파일됐다. 브라우저에서도
  버튼 하나의 계산된 스타일이 `font-size:14px`(`text-sm`=0.875rem)·
  `font-weight:500`(`font-medium`)·`box-shadow`에 `rgba(0,0,0,0.05) 0 1px 2px`
  (`shadow-xs`)를 실제로 그리는 것을 확인했다.
- **`mediaKindLabel` 불일치**: `YujinPanel.tsx`의 `broll`/`broll_video`
  이름표를 "영상"에서 "B-roll"로 바꿔 `EditorWorkbench.tsx`의
  `auditionRoleLabel`·`inspectorRegistry.ts`의 `mediaLabels`와 맞췄다(둘 다
  이미 "B-roll"이었고, 실제 화면에도 "B-roll 1 항상 쓰기"로 그 글자가
  떠 있었다 -- 소수 의견이던 "영상" 쪽을 고쳤다). 조사 중 이 값과 원래
  또 disagree한다고 의심했던 `editorWorkbenchReadOnlyAdapters.tsx`의
  `trackRoleLabels`는 **호출하는 곳이 아예 없는 죽은 코드**였다 -- 고치는
  대신 통째로 지웠다.
- **닫힌 도우미 필드 정리**: `rightDockTypes.ts`의 `onRetryMessage`·
  `retryAfterSeconds`(어디서도 값을 채우지 않는 죽은 필드였다) 삭제.
- **닫혀 있을 때 낭비되는 파생 상태**: `open` 확인을 후크(`useLayoutEffect`·
  `useEffect`) 다음, 나머지 파생 상태·후보 계산보다 앞으로 옮겼다.
  Rules of Hooks는 그대로 지킨다(훅 호출은 하나도 건너뛰지 않는다 --
  건너뛰는 건 순수 계산뿐).

**검증**: 위 두 라벨 변경으로 시험 둘이 깨졌다(`editor-workbench-route.test.tsx`의
"calls a b-roll candidate a video, not just media"와 `YujinPanel.test.tsx`의
후보 상세 시험) -- 둘 다 "B-roll"을 기대하도록 고쳤다(회귀 감시 자체는
그대로 유지, 기대값만 새 이름표에 맞춤). `tsc -b --force`·전체
vitest(1,372개) 통과, `vite build` 결과로 컴파일된 클래스 직접 확인,
워크트리 dev 서버(`localhost:5199`)에서 실제 계산된 스타일과 화면 문구
확인.

**owner가 바로 이어 지적한 것**: 여섯 번째 세션 보고에서 "`startBlankProject`·
`startVoiceCloneProject`에도 같은 문제가 있지만 이번엔 안 고쳤다"고
투명하게 남겼더니, owner가 "그 둘도 같은 방식으로 고쳐줘"로 답했다.
두 함수 다 같은 중첩 try/catch로 바꿨다 -- 프로젝트 생성 자체 실패와
그 다음 단계(빈 세션 생성, 또는 카탈로그 새로고침+이동) 실패를 분리하고,
후자면 카탈로그를 새로고침해 orphan으로 안 남게 하고 정확한 문구로
알린다. `AppRouter.test.tsx`에 회귀 시험 3개를 새로 추가했다(named-project
경로는 이번에 처음 커버리지가 생겼고, 두 지름길도 각각 하나씩) -- 전체
1,375개 테스트 통과.

## 2026-08-31 일곱 번째 이어진 세션 — 캡컷 새 캡처 3개, Wbrowser 대신 이미 연결된 claude-in-chrome으로

owner가 "캡컷 새 캡처 어떤 화면 필요한지 알려줘"에 이어 "Wbrowser
(github.com/w-partners/Wbrowser)를 설치해서 네가 조작하면 되"라고
지시했다. 설치 전에 확인해 보니 **claude-in-chrome MCP가 이미 이 세션에
연결돼 있었다** — 목적(로그인된 실제 크롬을 직접 조작)이 완전히
같아서, owner에게 물어 기존 연결을 쓰기로 했다(새 프로세스·새 디버깅
포트를 하나 더 여는 것보다 낫다는 판단).

owner의 CapCut 웹(`capcut.com`) 계정에 실제로 로그인해 세 가지를 직접
확인했다: 상단 도구줄(실행취소·확대비율·내보내기 버튼 순서), 재생줄
(빈 타임라인일 때와 클립을 골랐을 때 왼쪽 아이콘 구성이 다르다는
것까지 새로 확인), `내보내기` 다이얼로그(누르면 공유 메뉴가 먼저 뜨고
`다운로드`를 눌러야 이름·해상도·품질·프레임속도·형식 필드가 있는
실제 설정 화면이 나온다). 전부
`docs/reference/capcut-observed-2026-08-22.ko.md` §8에 기록했다 —
**이 절만 출처가 다르다는 것을 절 안에 명시**했다(§1~7은 owner의
데스크톱 캡처, §8은 AI가 직접 확인한 웹 버전 — 같은 제품이 아니므로
데스크톱 결정의 직접 근거로 쓰지 말라고 절 첫머리에 적어 뒀다).

**확인·정리한 것**: 캡처 중 만든 테스트 프로젝트(아기 사진 1장짜리,
`202608311352`)는 휴지통으로 이동했다(30일 내 복구 가능, 영구 삭제
아님). 열었던 탭도 전부 닫았다. 스크린샷 자체는 저장하지 않았다 —
동영상 커버 썸네일에 아이 얼굴이 나와서, 파일로 남기는 대신 구조만
글로 옮겼다(§8이 그 글이다).

**남은 것**: 이 §8은 웹 버전만 확인한 것이라, **타임라인 위쪽 도구줄**
(줌·실행취소 아이콘의 정확한 간격)과 **데스크톱판과의 차이 대조**는
여전히 owner의 데스크톱 캡처가 있어야 한다. 실제 로고도 그대로 남아
있다.

## 2026-08-31 여덟 번째 이어진 세션 — Tauri clean 빌드 재검증, Smart App Control 재현 확인

owner가 남은 세 항목(Tauri clean 빌드 재검증·실제 로고·캡컷 데스크톱
캡처) 중 owner 입력 없이 바로 할 수 있는 첫 번째를 지목해 "1번 진행하자"고
지시했다.

`apps/desktop/src-tauri/target/`(478.9MB, gitignore 대상이라 삭제 안전)을
전부 지우고 `npm run tauri build`를 처음부터 다시 돌렸다. **막혔다** —
`zmij v1.0.23`의 build script가 `os error 4551`(Smart App Control이
서명 안 된 새 실행 파일 차단)로 실패했다. 2026-08-30 기록의 "재시도에서
재현 안 됐다"는 결과가 **캐시 재사용 때문에 안 걸렸던 것**이었음이
확인됐다 — 정책이 풀린 게 아니었다.

이건 코드로 못 고치는 OS 보안 정책이라(`CLAUDE.md` §6 성격 — 시스템/보안
설정 변경은 이 세션 권한 밖), `apps/desktop/README.md`에 확인된 사실과
owner용 선택지 셋(매번 알림에서 허용·코드 서명 인증서·Smart App Control
평가 모드 해제)을 적어 뒀다. `CLAUDE.md` §2의 해당 줄도 "미확인"에서
"확인함"으로 고쳤다. 메모리에도 남겼다(`videobox-tauri-smart-app-control-blocks-clean-builds`)
— 다음에 또 "재시도했더니 안 막혔다"가 나오면 clean 빌드로 재검증하기
전엔 결론 내리지 말라는 뜻으로.

## 2026-08-31 아홉 번째 이어진 세션 — api.ts 화면에서 안 부르는 메서드 24개 정리

owner가 "1번부터 모두다 진행하자"(첫 번째 조사에서 나온 "화면에서 안 부르는
api.ts 메서드 24개" 항목)로 지시했다. **하나씩 지우기 전에 검증하다가 두 번
크게 틀릴 뻔했다** — 상세 경위는 새 메모리
(`videobox-unwired-api-methods-are-not-automatically-dead`)에 남겼다.

- **8개(`createHermesRun`·`openHermesRunEvents`·`cancelHermesRun`·
  `retryHermesRun`·`applyDirectorProposal`(단수)·`getDirectorProposal`·
  `listDirectorMessages`·`prepareDirectorMessage`)는 지우지 않았다.** 화면에서
  안 부르는 건 맞지만, 백엔드 `hermes_run_service.py`가 실제 스트리밍
  레지스트리를 구현하고 있고 `main.py`가 `hermes_run_service is not None`일
  때만 그 라우터를 마운트한다 -- Hermes 실제 provider 연결 승인(CLAUDE.md §6)을
  기다리는 **진짜 인프라**였다.
- **`getPreview`/`getExport`도 처음엔 지웠다가 되돌렸다.** `task22-parity-owners.test.ts`가
  이름으로 "호환 판독기로 일부러 남김"을 고정하고 있는 걸 테스트 실패로
  알아챘다.
- **나머지 15개는 실제로 지웠다** — 각각 superseding 형제 메서드가 실제
  화면에서 쓰이고 있는 것을 확인한 뒤(`getProjectWorkspaceSummary`가
  `getProject`를, `listJobs`가 개별 job 조회를, 업로드형이 `register*`형을
  대체하는 식): `getProject`, `getFootageProposal`, `listSceneImages`,
  `listPreviewShares`, `registerNarrationAudio`, `registerScriptDocument`,
  `importBrollBatch`, `listMediaLibraryFavorites`, `listRecentMediaLibraryAssetIds`,
  `setMediaLibraryFavorite`, `getLibraryAsset`, `applyFormatTemplate`,
  `approveReviewRecommendation`. 딸려서 완전히 고아가 된 타입 6개
  (`PreviewJob`·`ExportJob`·`PreviewArtifact`·`ExportArtifact`·
  `PreviewShareSummary`·`RegisteredAsset`·`BrollBatchImportRequest`·
  `BrollBatchImportResponse`, `getPreview`/`getExport`를 되돌리면서 그
  타입 넷도 같이 되돌림)도 정리했다.
- **`permanentDeleteLibraryAsset`은 지우지 않고 real gap으로 남겨 뒀다.**
  휴지통에 간 자산 화면(`LibraryPreviewPane.tsx`)엔 "복원"만 있고 "영구
  삭제"가 아예 없다 -- 이건 죽은 코드가 아니라 UI가 없는 진짜 기능이다.
  owner 판단이 필요해 다음 항목으로 남긴다.

**검증**: 지우고 나서 시험 12개가 깨졌다 -- 전부 이제 없는 메서드를
`vi.spyOn`하던 회귀 시험이었다. `not.toHaveBeenCalled()` 가드는 그대로
확인이 됐으니 스파이 줄만 지웠고, `importBrollBatch`의 단독 동작 시험은
메서드와 함께 지웠다. `tsc -b --force`·전체 vitest 1,374개 통과. 워크트리
dev 서버에서 편집기·자료실 화면을 직접 열어 콘솔 에러 없음과 "휴지통으로
이동" 버튼이 여전히 동작하는 것 확인.

## 2026-08-31 열 번째 이어진 세션 — 남은 4항목 마저 처리

owner 지시: "나머지 모두 다 고쳐줘." 아홉 번째 세션이 owner 판단용으로
남겨 뒀거나 발견만 하고 안 고쳤던 것들을 마저 닫았다.

- **자산 휴지통 영구 삭제**: `LibraryPreviewPane.tsx`에 프로젝트 카탈로그와
  같은 2단계 확인(완전 삭제 → 영구 삭제 · 한 번 더 확인할게요)을 추가했다.
  백엔드는 이미 있었다.
- **Mem0 조회 폴백**: owner에게 "빈 결과 유지 vs 로컬 최근/전체 폴백" 중
  골라 달라고 물었더니 "어떤 게 최선이냐"고 되물어, 폴백 쪽을 추천하고
  그대로 구현했다 — 이미 로컬에 있는, owner가 승인한 280자 이내 문구를
  뜻 순위 없이 저장 순서로 돌려준다. 외부로 나가는 건 늘지 않는다.
- **전환 길이 화면 조절**: 속성 패널에 초 단위 칸을 추가했다(0.1~2.0초,
  백엔드와 같은 범위).
- **CapCut 내보내기에 전환 얹기**: `pycapcut_adapter.py`가 이제 실제로
  전환을 붙인다. **테스트하다가 진짜 버그를 하나 잡았다** — pycapcut은
  세그먼트가 트랙에 올라가는 그 순간에만 전환 소재를 자동 등록해서,
  이미 놓인 앞 조각에 나중에 전환을 붙이면 초안 어디에도 그 전환의
  실체가 없는 상태가 됐다(캡컷이 못 열었을 것). 소재 등록을 직접
  하도록 고쳤다. 여덟 개 전환 이름을 캡컷 무료 전환에 **이름으로만**
  대응시켰다 — 실제 캡컷에서 눈으로 확인 안 됨(특히 `slideup`/`slidedown`/
  `circleopen`), 내보낼 때마다 그 사실을 경고로 남긴다.

**남긴 것**: 유진이 전환을 직접 추천하는 것은 이번에도 안 했다 — "어떤
신호로 어느 전환을 고를지" 자체가 설계돼 있지 않아서, 서두르는 대신
다음 사람 몫으로 명시적으로 남긴다.

**검증**: 프론트 전체 1,378개, 백엔드에서 이번에 건드린 항목들 208개
전부 통과. `tsc -b --force` 깨끗. CapCut 전환 테스트에서 위 등록 버그를
직접 잡아냈다(테스트 없이 갔으면 놓쳤을 결함).

## 다음에 이어갈 사람에게

이 문서가 최신 인계다. `CLAUDE.md` §2의 "최신 세션 인계" 줄을 이 파일로
옮겨 두었다. 다섯~아홉 번째 세션이 남겼던 항목은 전부 닫혔다. 남은 건
**owner 입력이 있어야 진행되는** 두 가지 — 실제 로고, 캡컷 데스크톱판
캡처(타임라인 위쪽 도구줄) — 와, **설계가 먼저 필요한** 것 하나 — 유진의
장면 전환 추천(무엇을 신호로 어느 전환을 고를지)뿐이다.
