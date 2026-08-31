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

## 다음에 이어갈 사람에게

이 문서가 최신 인계다. `CLAUDE.md` §2의 "최신 세션 인계" 줄을 이 파일로
옮겨 두었다. 남은 우선순위는 위 "감수한 것/남은 것" 목록의 캡컷 새
캡처·실제 로고 두 가지뿐이다(Tailwind 결함·Docker 캐시 오진은 이번
세션에 전부 닫혔다).
