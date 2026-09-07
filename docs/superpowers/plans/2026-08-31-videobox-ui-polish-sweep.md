# VideoBox 화면 정리 전수 점검 (2026-08-31)

## 배경

owner 지적: "지금 너가 만든 편집기 프로그램에 화면 시작하는 부분부터 화면에
기능구성, 편집기안에 기능 배치 이런것들이 완전 엉망이라서 내가 캡컷을
벤치마킹하라고 한거잖아. 너가 그냥 다 때려박은게 아니라 탭으로 정렬하거나
기능 버튼들을 체계적으로 만들었으면 벌써 끝났을 일이야" — 이어서 "다른
부분들도 모두 세부적으로 자세히 체크해. 게다가 편집기외에 다른 페이지에
있는 부분들도 정리가 안되어 있어."

실제로 컨테이너를 띄워 화면을 하나씩 열어보니 지적이 맞았다. 아래에 확인
방법, 지금까지 고친 것, 아직 확인 안 된 후보를 전부 남긴다.

## 확인 방법 — 왜 이 패턴이 반복되는지

화면마다 열어서 눈으로 보는 방법과 별도로, **기계적으로 찾는 방법**을
하나 확립했다: 실제 코드에 정말 스타일이 빠진 곳이 있는지 클래스명 기준으로
전수 대조한다.

```bash
# JSX에서 실제 쓰는 vb- 클래스 전부
grep -rhoE 'className="[^"]*vb-[^"]*"' --include='*.tsx' apps/web/src \
  | grep -oE 'vb-[a-zA-Z0-9_-]+' | sort -u > used.txt
# CSS 어딘가에 정의된 vb- 클래스 전부
grep -rhoE '\.vb-[a-zA-Z0-9_-]+' --include='*.css' apps/web/src \
  | sed 's/^\.//' | sort -u > styled.txt
# 쓰는데 스타일이 아예 없는 것
comm -23 used.txt styled.txt
```

**왜 이게 반복되는가**: 오늘 고친 것 전부 같은 모양이었다 — 기능 로직은
맞고 테스트(RTL `getByText`/`getByRole`)도 통과하는데, 실제 CSS가 한 줄도
없어서 브라우저 기본 흐름(블록 쌓임)대로 그냥 쌓였다. RTL은 텍스트가
있는지만 보지 간격·정렬을 보지 않아서 이런 결함을 못 잡는다
([[videobox-green-tests-were-not-guarding]]와 같은 종류의 함정). 이번
점검·수정에서 발견한 5건이 전부 이 패턴이었다.

## 오늘 확인·수정 완료 (5건, 전부 커밋됨)

1. **편집기 오른쪽 패널 — 글꼴 목록** (`CaptionFontPicker.tsx` /
   `editor-workbench.css`). CSS가 아예 없어서 글꼴 15개가 항목당 3줄씩
   쌓여 1,350px, 패널 전체 스크롤이 3,736px였다. `__history`와 같은
   14rem 박스+자체 스크롤로 가뒀다. 실측: 3,736px → 2,670px. 커밋
   `141b180e`.
2. **"자료실" 이름 변경이 반쪽만 반영** (`LibrarySidebar.tsx` /
   `LibraryPickerDialog.tsx`). 2026-08-29 결정은 breadcrumb·라우트만
   바꿨고, 실제 화면 제목(`<h1>미디어</h1>`)과 가져오기 대화상자 제목·
   설명은 그대로 "미디어"/"라이브러리"였다. 커밋 `d04c6857`.
3. **같은 이름 문제가 7개 파일에 더** — 미디어 단계의 음악·효과음 탭
   제목, 촬영본 정리 화면 링크, 자료실·가져오기 대화상자 에러 메시지가
   전부 옛 이름 "라이브러리"였다. 전부 "자료실"로 통일. 커밋 `9db0a96f`.
   - **주의**: `미디어`라는 단어 자체(장르 뜻: 영상·음악·그림)는 안 건드렸다.
     예: "전체 미디어", "미디어를 불러오는 중", "미디어 분류" — 이건
     페이지 정체성이 아니라 파일 종류를 가리키는 일반 명사라 이름 충돌
     문제와 무관하다.
4. **출력 준비 체크리스트 줄 붙음** (`OutputsPage.tsx` /
   `product-shell.css`). `<strong>편집본</strong><span>준비 필요</span>`에
   CSS가 없어서 "편집본준비 필요"처럼 붙어 읽혔다. `검토승인 필요`,
   `출력앞 단계 완료 필요`도 같은 증상. `<ol>`/`<li>`에 grid/flex 간격을
   줬다. 커밋 `c3d03511`.
5. **검토 화면 장면 목록의 편집 링크가 문장을 통째로 반복** —
   `TimelineReviewPage.tsx`. 장면 설명이 `<p>`로 이미 한 번 나오는데,
   바로 아래 "편집하기" 링크의 **보이는 텍스트**가 같은 문장 전체를
   반복하고 그 위에 강조색(`.vb-action-link`: 굵게·밑줄·강조색)까지
   입어서, 화면에 큰 주황색 경고문처럼 보였다. 문장은 `aria-label`로
   옮기고 보이는 텍스트는 "편집하기"만 남겼다(접근성 이름은 그대로라
   테스트 안 깨짐). 커밋 `c3d03511`.

6. **완성본 화면의 버튼 두 개가 서로 겹침** — `OutputsPage.tsx`. 홈 카드
   3장 전용 3열 grid(`vb-home-grid`, `minmax(0,1fr)`)를 좁은 카드 안
   버튼 두 개 줄에도 그대로 재사용해서, 칸이 버튼 글자 폭보다 좁아져
   "가로·세로 출력 만들기"와 "출력 상태 다시 확인"이 겹쳐 보였다("가로
   ·세로 출력 만들기력 상태 다시 확인"으로 읽힘). `my-project`(완성본
   14개)에서 실제로 봤다. 전용 flex-wrap 클래스(`vb-output-actions`)로
   뗐다. 커밋 `68a77c6f`.

각 건 관련 vitest 스위트 전부 통과 확인(스타일 30 + 인스펙터 77 + 라이브러리/
미디어/촬영본/에디터자산 178 + 검토 22 + 출력 91). 1·4·5·6은 컨테이너
재빌드 후 실제 브라우저에서도 재확인했다.

## 확인 중 아니라고 판정한 것 (오탐)

- `/settings/*`에 프로젝트 이름·단계 탭이 계속 보이는 것 — 버그 아님.
  `AppRouter.tsx`가 설정을 프로젝트 스코프로 의도적으로 설계했다
  (`?project_id=`를 달아 이동, 돌아갈 자리를 유지하려는 목적).
- 홈 화면의 "유진에게 물어보기"가 섹션 제목과 입력창 라벨에 각각 한 번씩,
  두 번 보이는 것 — 중복처럼 보이지만 하나는 섹션 heading, 하나는
  textarea의 접근성 label이라 기능상 문제는 아니다. 시각적으로는 약간
  거슬리지만 우선순위 낮음(아래 후보 목록에 남겨 둠).
- `vb-project-title-suggest`/`__list` (제목 추천 대화상자) — 실제로
  열어서 "유진에게 제목 추천받기"를 눌러 확인. 추천 5개가 pill 버튼으로
  깔끔하게 줄바꿈됐다. CSS가 없어도 Button의 `inline-flex` 기본값만으로
  충분했다. 오탐.
- `vb-final-verdict`, `vb-final-format` (완성본 평가·포맷 저장 영역,
  `OutputsPage.tsx`) — `my-project`(완성본 14개)에서 실제로 열어서 확인.
  shadcn `Card`/`CardContent`의 기본 Tailwind 간격만으로 이미 깔끔했다.
  오탐.

## 위 스크립트로 나온 나머지 후보 (35개 중 확인한 8개 제외 27개)

기계적으로 걸러진 "쓰는데 스타일이 없는" 클래스 목록이다. **클래스가
없다고 전부 버그는 아니다** — 부모 규칙이 자식 전체를 이미 처리하거나
(`.vb-outputs section`처럼), 같은 요소가 두 클래스를 갖고 있어 다른
쪽에서 이미 스타일을 받거나, shadcn `Button`/`Input`의 Tailwind 유틸리티만
으로 이미 충분한 경우가 있다. **실제로 열어서 확인해야 확정된다.**

**"먼저 볼 것" 전부 실제로 열어서 확인 완료 — 전부 오탐**

- `vb-footage-source-row`, `vb-footage-selection-count` — 실제 자산
  (`library_asset_id=user_14a...`)으로 촬영본 정리 화면을 열어서 확인.
  왼쪽 원본 목록·오른쪽 "할 일" 패널 다 정상 렬레이아웃. `vb-footage-
  sequence__preview-status`는 가상 묶음을 만들어야 나오는 자리라 이번엔
  못 봤음(우선순위 낮게 재분류).
- `vb-inbox-import__list`, `vb-inbox-import__sequence-list`
  (`ImportFromFootageInbox.tsx`) — 미디어 단계 "가져오기" 탭을 직접
  열어서 확인. CSS가 코드 어디에도 없는데도 카드형 grid로 깔끔하게
  나왔다 — 부모(`.vb-media-library` 계열)의 일반 규칙을 받는 것으로
  보인다. 정확한 상속 경로는 못 짚었지만 화면은 정상.
- `vb-catalog-card__rename` — "제목 바꾸기" 버튼과 그 대화상자(제목
  추천 목록 포함)까지 직접 열어서 확인, 정상.

**낮은 우선순위 — 오늘 화면에서 이미 정상으로 보였거나 구조상 안전
(코드만 보고 판단, 직접 열어보진 않음)**
- `vb-footage-sequence__preview-status`, `vb-catalog-archive-toggle`
- `vb-media-workspace__tabs`, `vb-timeline-scale`, `vb-start-chooser*` —
  오늘 스크린샷에서 이미 정상 레이아웃으로 보였다
- `vb-editor-workbench__panes`, `vb-editor-workbench__stage-panel` —
  `react-resizable-panels`가 자체 레이아웃을 준다
- `vb-editor-assets__more`, `vb-editor-assets__pane-tab` — 단일 Button
- `vb-ui`, `vb-app-loading`, `vb-preview-stage__caption-transcript`
  (sr-only 짝 클래스 있음), `vb-review-output` — 구조적 wrapper,
  위험 낮음
- `vb-preview-share` — 외부 공유 페이지, 거의 안 열림
- `vb-media-library__pagination`, `vb-add-media` — 단순 구조 추정

## 다음에 할 일

1. ~~"낮은 우선순위" 나머지 항목도 시간 되는 대로 한 번씩은 실제로 열어서
   확인한다~~ — 2026-09-01에 전부 확인 완료. 아래 절 참고.
2. 이 스캔은 **CSS 존재 여부만** 본다 — 스타일이 있어도 배치가 이상하거나
   (`vb-home-grid`를 좁은 카드에 재사용해 버튼이 겹친 6번 건처럼) 문구가
   겹치는 경우는 못 잡는다. 그런 문제는 계속 실제 화면을 열어서 봐야
   한다([[videobox-capture-the-screen-to-see-it]]).
3. **오늘 결론**: 기계적 스캔이 걸러낸 35개 후보를 전부 판정했다 —
   실제 버그 6건(고침), 오탐 10건(직접 열어서 확인), 나머지 19건은
   구조상 위험이 낮아 코드만 보고 보류. 편집기·자료실·미디어·촬영본·
   완성본·검토·프로젝트 목록·제목 대화상자까지 오늘 열어본 화면 기준으로는
   "완전히 엉망"이라기보다 **군데군데 스타일이 빠지거나 이름 정리가
   덜 된 부분**이 있는 상태였다.

## 2026-09-01 — "낮은 우선순위" 19개 전부 확인 완료

owner 지시로 남은 19개 후보를 실제 화면(컨테이너, `http://127.0.0.1:5173`)과
코드를 대조해 하나씩 판정했다. **1건은 진짜 결함으로 확인해 고쳤고, 18건은
오탐(CSS 없이도 정상 동작) 확인.**

**실제 결함 1건 (고침)**

- `vb-preview-share` (`AppRouter.tsx`, 공유 링크 공개 페이지) — CSS가
  전혀 없어서 `<video>`가 원본 해상도(1920×1080) 그대로 그려지고, 뷰포트
  (1280px)보다 커서 페이지가 가로로 밀렸다. `my-project`의 실제 완성본으로
  공유 링크를 만들어 직접 열어서 확인(`docScrollWidth` 1928 vs 뷰포트
  1280). `.vb-preview-stage__media-shell`이 이미 쓰는 것과 같은
  `object-fit: contain` 방식으로 맞췄다. 컨테이너 재빌드 후 재확인 완료
  (밀림 없음, 영상이 뷰포트 안에 비율 유지하며 들어감).

**오탐 18건 (코드·실측으로 안전 확인, 수정 안 함)**

- `vb-start-chooser`/`__paths`/`__more` — 프로젝트 홈에서 실측. `hasDraft`
  분기에 따라 버튼 1개 또는 2개가 정상 폭으로 나옴.
- `vb-catalog-archive-toggle` — 32×36 아이콘 버튼, 정상.
- `vb-media-workspace__tabs` — 탭 5개가 겹침·줄바꿈 없이 한 줄.
- `vb-timeline-scale` — 편집기 타임라인 눈금·트랙 정상 배치.
- `vb-editor-workbench__panes`, `__stage-panel` — 상단 탭 정상, 미리보기
  패널은 `react-resizable-panels`가 자체 레이아웃을 준다.
- `vb-editor-assets__more`, `__pane-tab` — 코드로 확인: `more`는 단일
  Button(항목이 `FIRST_PAGE`를 넘을 때만 등장), `pane-tab`은
  `renderPaneTabs={false}`로 편집기에서 의도적으로 안 그려서(위 탭과 중복
  방지, 2026-08-30 결정) 지금 이 배치에서는 애초에 안 나오는 게 정상.
- `vb-ui` — 실제로는 CSS가 있다(`ui-system.css:214`). 원래 스캔이 잘못
  걸렀거나 그 뒤에 추가된 것으로 보임.
- `vb-app-loading` — 라우트 전환 중 잠깐 뜨는 로딩 문구 한 줄
  (`<main><p>...</p></main>`). 구조상 줄바꿈·겹침이 날 수 없음.
- `vb-preview-stage__caption-transcript` — 항상 짝 클래스
  `vb-preview-stage__visually-hidden`(CSS 있음)과 같이 붙어서 그 클래스가
  이미 전부 스타일한다.
- `vb-review-output` — 검토·출력 화면 최상위 wrapper. 실측 1123×1377,
  내부 카드들은 각자 스타일이 있어 정상 흐름.
- `vb-media-library__pagination` — 프로젝트 미디어 화면 "음악" 탭(30개,
  페이지 크기 24)에서 실제로 페이지네이션이 뜨는 것까지 확인. 버튼 두
  개와 "1/2페이지" 텍스트가 겹치거나 밀리지 않고 한 줄로 읽힘(9px 정도
  기준선 오차는 있으나 읽기에 지장 없음 — 필요하면 나중에
  `align-items: center` 한 줄 추가 가능한 수준, 지금은 결함 아님).
- `vb-add-media` — 편집기 도크의 "파일 추가" 버튼, 단일 Button.
- `vb-footage-sequence__preview-status` — 실제 가상 묶음을 만들어 보진
  못했지만(다단계 Yujin 흐름), 코드 확인 결과 `<small role="status">` 안에
  텍스트 한 줄만 들어가는 구조라 CSS 없이도 깨질 수 없음.

vitest 99파일·1,382건 전부 통과(회귀 없음). 컨테이너
재빌드(`owner-ready.ps1 -Mode Start -Rebuild`) 후 고친 화면 재확인 완료.
