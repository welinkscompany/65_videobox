# 타임라인 클릭 고르기가 두 겹으로 죽어 있었다 -- 컷 편집이 실물로 안 됐다

대표님이 직접 제기한 불만("타임라인에서 잘라내는, 컷편집 조차도 제대로 동작을 안 해") 위에서, 실제
컨테이너를 재빌드하고 브라우저로 실제 프로젝트 `0907-b26195af`("사진 브이로그 실기 0907")를
열어 처음부터 끝까지 확인했다. **결함이 하나가 아니라 세 겹이었다.** 셋 다 고쳤고, 넷째(더
깊은 데이터 문제 둘)는 발견해서 별도 백그라운드 작업으로 넘겼다.

## 결함 1 -- 트랙 헤더 버튼이 클립 클릭을 가로챈다 (고침)

`apps/web/src/features/editor/timeline/TimelineDock.tsx`의 트랙 헤더 행(이름표·잠금·눈·음소거)이
2026-09-03에 "클립이 헤더를 가린다"는 반대 방향 버그를 고치려고 `zIndex: 4` +
`pointerEvents: "auto"`로 클립 위에 뜨게 되어 있었다. 그런데 이 뭉치가 실제로 x:0~108~170px
(레인마다 버튼 개수 다름) 폭을 차지하는데, **컷 편집으로 0초 근처에 이 폭보다 짧은 클립이
남으면** 그 클립을 눌러도 헤더 버튼(주로 음소거)이 클릭을 대신 받았다.

실측(2026-09-18, 실제 프로젝트, 브라우저 `document.elementFromPoint`):
"내레이션 1번째 장면, 0초부터" 클립 select 버튼의 중심점(129, 734 근처)에서 `elementFromPoint`를
부르면 **"내레이션 트랙 음소거" 버튼**이 돌아왔다. 클릭하면 클립이 아니라 트랙이 음소거됐다.

**고친 방법**: 두 가지를 함께 했다.
1. 이름표(`<span>`)는 애초에 클릭 핸들러가 없는데 `pointerEvents: "auto"`가 붙어 있었다 --
   기능 없이 클릭만 가로채고 있어서 지웠다.
2. 트랙 헤더 버튼(잠금·눈·음소거) 뭉치는, **그 레인에 죽은 자리(`LANE_HEADER_DEAD_ZONE_PX
   = 180px`) 안에서 시작하는 클립이 하나라도 있으면** 그 트랙만 한시적으로
   `pointerEvents: "none"`으로 양보한다 -- 마우스 클릭만 넘기고 키보드 접근(Tab+Enter)은
   그대로 둔다. 죽은 자리에 클립이 없으면 2026-09-03 원칙(헤더가 클립 위에 뜬다) 그대로다.

풀 가터(header column을 시간 좌표계 밖으로 완전히 분리하는 설계)도 검토했지만, `viewportWidthPx`가
줌·스크롤·클릭탐색(`timelineNavigation.ts`, `timelineZoomScale.ts`) 전체에 걸쳐 "보이는 폭 =
실제 픽셀 폭"을 전제하고 있어서 건드리면 반경이 너무 넓어졌다. 이 방식은 기존 좌표계·기존
zoom/scroll 수식을 하나도 안 건드리고 최소 수정으로 끝났다.

## 결함 2 -- 오버레이 clipId 중복이 타임라인 전체의 클릭 고르기를 크래시시켰다 (고침)

결함 1을 고친 뒤에도 실제 프로젝트에서 클립을 클릭하면 트림 손잡이가 안 떴다. 처음엔
"결함 1의 부작용(엉뚱한 곳을 눌러서)"이라고 가정했지만, **완전히 정확한 좌표로(`elementFromPoint`가
클립 select 버튼을 돌려주는 것까지 확인한 뒤) 클릭해도 여전히 트림 손잡이가 안 떴다.**

콘솔을 보니 클릭마다 `RangeError: Rect clipIds must be unique`가 던져지고 있었다
(`apps/web/src/features/editor/timeline/hit-testing.ts`의 `classifyTimelineHit` ->
`requireInput`). `selectClip`(`TimelineDock.tsx`)이 클릭을 재확인하려고 **타임라인 전체
클립의 좌표 목록**을 `classifyTimelineHit`에 넘기는데, 이 목록에 clipId가 중복되면 예외를
던지도록 설계돼 있다(프로그래밍 실수를 잡기 위한 의도적 방어).

실제 매니페스트(`GET .../playback-manifest`)를 확인하니 **오버레이 클립 5개가 정확히 같은
`placement_id`(`overlay:export-overlay-timeline_001:001-0`)를 갖고 있었다.** 이 하나의
데이터 흠 때문에 **오버레이 레인과 전혀 무관한 내레이션 클립을 눌러도** 매번 이 예외로
클릭 핸들러 전체가 조용히 실패했다(콘솔에만 남고 화면은 아무 반응 없음) -- **이게 "트림
손잡이가 영영 안 뜬다"의 진짜 원인이었다.**

**고친 방법**: `selectClip` 안에서 `classifyTimelineHit`에 넘기기 직전에 `rects`를 clipId로
dedupe한다(`Array.from(new Map(rects.map(item => [item.clipId, item])).values())`). 이러면
데이터 흠이 있어도 클릭 고르기 자체는 안 죽는다. `classifyTimelineHit`의 "clipId는 유일해야
한다"는 방어 자체는 안 건드렸다(정당한 계약이라 약화시키지 않음) -- 문제 있는 호출부만 방어적으로
고쳤다.

이 결함은 **진짜 원인이 프론트엔드가 아니라 백엔드**다. `task_6f80b621`로 별도 백그라운드
작업에 넘겼다(아래 "다음 세션 백로그" 참고) -- 원인까지 이미 확정했다
(`composition_plan.py:616-634`의 `export_overlays` 재구성 루프가 분할된 세그먼트마다 clip_id를
안 갈라서 생김, 구조적 버그로 판단됨 -- 이 프로젝트 하나만의 문제가 아니라 "세그먼트를 분할한
뒤 그 세그먼트에 걸린 오버레이가 있는" 모든 프로젝트에서 재현 가능).

## 실물 확인 (재빌드 두 번, 브라우저로 직접)

`scripts/owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild`로 **두 번** 재빌드했다
(1차: 결함 1만 반영, 2차: 결함 2 dedupe까지 반영). 재빌드마다 **옛 번들 캐시 문제**를 겪었다
(`videobox-container-rebuild-stale-bundle` 메모와 같은 패턴 -- 이번엔 컨테이너가 아니라
**브라우저 탭이 이전 SPA 세션을 유지**해서, `navigate` 툴로 같은 URL에 다시 가도 `location.reload()`를
명시로 불러야 새 번들(`index-*.js` 해시)을 받았다). 매번 `document.querySelector('script[type=module]').src`로
번들 해시가 실제로 바뀌었는지 먼저 확인한 뒤에 재검증했다.

1차 재빌드 후: `document.elementFromPoint`가 클립 select 버튼을 정확히 돌려주는 것 확인(결함 1
해소). 클릭해도 트림 손잡이가 여전히 안 떠서 결함 2를 새로 찾음.

2차 재빌드 후: `find`로 "내레이션 2번째 장면, 1초부터"(clipId
`clip_narration_001@narration_primary` -- 실제 분할로 생긴 합성 clipId) 버튼을 찾아 `ref` 기반으로
정확히 클릭 -> `data-selected="true"`, **트림 손잡이 두 개("...시작 자르기", "...끝 자르기")가
실제로 나타남을 확인.** 스크린샷으로도 "시작 / 순서 / 끝" 세 단추가 선택된 클립 위에 뜬 것을
직접 봤다.

## 실물 확인에서 새로 찾은, 고치지 않은 문제 (아래 "다음 세션 백로그" 참고)

트림 손잡이가 뜬 뒤, "드래그로 길이 조절 -> API 호출 성공"까지 확인하려고 실제 포인터 드래그를
흉내 냈다(`pointerdown`/`pointermove`/`pointerup` 순서로 정확히 재현, `startTrim`/`moveTrim`
코드가 기대하는 그대로). 콘솔에 **새로운** 예외가 떴다: `RangeError: Narration segments must
not overlap`(`narrationMutation.ts`의 `validateNarration`). 원인은 이 프로젝트의 내레이션 트랙
자체에 **이미 겹치는 구간**이 있어서다(`clip_narration_002`가 4~8초, 같은 트랙의 분할 조각
`clip_narration_001@narration_primary-3`/`-4`가 5.69~8초 -- 겹침). 이 검증은 **트림 대상 클립뿐
아니라 트랙 전체**를 보기 때문에, 이 프로젝트의 이 트랙에서는 **어떤 클립을 얼마나 작게 잘라도
매번 이 예외로 실패한다.**

이건 결함 2와 같은 계열("세그먼트 분할·재구성"이 남긴 데이터 흠)로 보이지만 **다른 코드 경로**다
(오버레이가 아니라 내레이션 세그먼트 목록 자체). `validateNarration`의 "겹치면 안 된다"는
원칙 자체는 정당한 안전장치라 약화시키지 않았다 -- 근본 원인(왜 겹치는 세그먼트가 생겼는가)을
찾아 고쳐야 한다. `task_ecf8eb71`로 넘겼다.

## 검증

- **RED 확인**: 두 결함 모두 실제 프로젝트와 같은 데이터 모양(멀티트랙, 분할로 생긴 합성
  clipId `clip_narration_001@narration_primary` 패턴, clipId가 겹치는 오버레이 두 레인)으로
  fixture를 만들어 재현했다. 코드를 원상복구해서 RED(실패)를 먼저 확인한 뒤 GREEN으로
  되돌렸다 -- 정확히 재현되는 테스트임을 확인.
  - 결함 1: `트랙 이름과 잠금·눈·음소거가 클립에 가리지 않는다 (죽은 자리에 클립이 없을 때)`,
    `컷 편집으로 0초 근처에 짧게 남은 클립이 있으면 그 트랙 버튼이 클릭을 양보한다`
  - 결함 2: `겹치는 clipId을 가진 다른 레인이 있어도 내레이션 클립을 고르고 트림 손잡이를
    볼 수 있다 (2026-09-18 실물 재현)` -- RED 상태에서 정확히 실물과 같은
    `RangeError: Rect clipIds must be unique`가 떴다(콘솔 스택트레이스까지 일치).
- **focused**: `npx vitest run src/features/editor/timeline/timeline-dock.test.tsx` -- 73건
  통과(기존 72 + 신규 3, 기존 1개는 dead-zone 없는 픽스처로 갱신).
- **broader (frontend 전체)**: `npx vitest run`(apps/web, 독립 실행) -- **139개 파일, 1751건
  전부 통과**, 회귀 없음.
- **broader (backend 전체)**: `.venv/Scripts/python.exe -m pytest`(독립 실행, 45분 29초) --
  **5146 passed, 56 skipped, 1 xfailed, 1 failed.** 실패한 1건은
  `tests/test_owner_ready_script.py::test_smoke_dashboard_rejects_cross_host_redirect_without_following[external_host]`
  -- Hermes 대시보드 스모크 시험이 교차 호스트 리다이렉트를 따라가지 않는지 재는
  것으로, 요청 로그가 `['/', '/']`(기대: `['/']`)였다. **이번 세션이 건드린
  파일(타임라인 프론트엔드)과 전혀 무관한 영역**(owner-ready 스크립트의 Hermes
  헬스체크 목업)이고, `videobox-smoke-timeout-test-fails-by-machine-state.md`
  메모가 이미 경고한 것과 같은 계열(기계 상태에 따라 흔들리는 스모크 시험)로
  보인다. 이 세션의 변경으로 발생했다는 근거가 없다. **독립 재실행으로 확인**:
  같은 시험만 단독으로 다시 돌리니 두 파라미터 조합 다 통과했다(`2 passed`) --
  전체 pytest(5000건 이상, 45분) 동시 실행 중의 기계 상태(포트·타이밍)에서만
  흔들리는 시험으로 확인됨. 회귀 아님.
- **역방향(가장 중요, API curl로 대체하지 않음)**: 위 "실물 확인" 절 참고 -- 실제 컨테이너
  재빌드 두 번, 실제 브라우저로 실제 프로젝트를 열어 클릭 -> 선택 -> 트림 손잡이 등장까지
  직접 확인했다. 드래그로 길이를 조절하는 마지막 단계는 **이 프로젝트의 별개 데이터 문제**
  (내레이션 구간 겹침)에 막혀 끝까지 못 봤다 -- 위 "다음 세션 백로그" 참고.
- **갭**: 요청받은 두 결함 각각에 대해 계획된 Step(RED fixture -> 최소 GREEN -> 재빌드 ->
  브라우저 확인 -> 전체 테스트)을 전부 밟았다. 못 한 것은 딱 하나, 드래그 커밋 확인(위 참고).
- **배선**: 두 수정 모두 기존 배선(`selectClip`, 트랙 헤더 렌더링)을 그대로 쓴다 -- 새 API나
  새 prop을 추가하지 않았다.

## 검증하지 못한 채 남은 것

- 드래그로 실제 트림을 커밋해서 API 호출(`onTrimNarration`)이 성공하는 것까지는 못 봤다 --
  이 프로젝트의 내레이션 구간 겹침 때문에 막혔다(`task_ecf8eb71`).
- 오버레이 clipId 중복의 근본 수정(백엔드)은 이번 세션 범위 밖으로 남겼다(`task_6f80b621`) --
  프론트 dedupe는 증상만 막는다.
- `LANE_HEADER_DEAD_ZONE_PX = 180`은 실측(108~170px)에 여유를 둔 상수다. 버튼 스타일이
  크게 바뀌면 다시 재야 한다.

## 다음 세션 백로그

1. `task_6f80b621` -- 오버레이 `placement_id` 중복의 백엔드 근본 원인.
   `composition_plan.py:616-634`의 `export_overlays` 재구성 루프가 원인으로 확정됨(이번 세션
   서브에이전트가 실제 세션 데이터로 재현까지 완료) -- clip_id가 분할 조각별로 안 갈라진다.
   구조적 버그로 판단(이 프로젝트만의 문제가 아님).
2. `task_ecf8eb71` -- 내레이션 세그먼트 겹침이 트림 커밋을 막는 문제. 원인은 아직 확정 안 됨
   (오버레이 쪽과 같은 "분할·재구성" 계열일 가능성 높음, 다음 세션이 추적).
3. `2026-09-18-variant-conflict-resolution-actually-wired-to-chat.ko.md`가 남긴 백로그
   (변형본 충돌 행 13중복, `source_session_revision` 불일치, `task_006f1523`)는 이 세션과
   무관하게 그대로 유효하다.
4. `0907-b26195af`는 실사용 프로젝트인데 데이터 흠이 계속 나온다(오늘만 셋: 변형본 충돌
   13중복, 오버레이 placement_id 5중복, 내레이션 구간 겹침). 반복되는 패턴이라 owner에게
   "이 프로젝트를 정리하거나 새로 시작하는 게 나을 수 있다"고 알릴 필요가 있어 보인다 --
   판단은 owner 몫으로 남긴다.

## 재사용 원칙

- 재사용 후보: 기존 `classifyTimelineHit`/`hit-testing.ts`의 방어적 검증 계약, 기존
  `draftProjection.rects` 계산, 기존 트랙 헤더 렌더링 구조. 새 컴포넌트·새 좌표계를 만들지
  않았다.
- 실제 반영: `TimelineDock.tsx`에 상수 1개(`LANE_HEADER_DEAD_ZONE_PX`), 렌더 로직 수정 2곳
  (이름표 pointerEvents 제거, 트랙 헤더 버튼 pointerEvents 조건부), `selectClip` 안 dedupe
  1줄. 테스트 파일에 fixture 3개 + 테스트 3개(1개는 기존 테스트 갱신).
- 제외: 풀 가터(헤더 전용 고정 컬럼) 설계 -- `viewportWidthPx` 기반 줌·스크롤 수식 전체를
  건드려야 해서 반경이 너무 넓었다. 백엔드 데이터 근본 수정 둘(오버레이 중복, 내레이션 겹침) --
  프론트 작업 범위 밖, 별도 task로 분리.
- 경계 보존: `UI 구조`·`Google Sheets/Drive`·provider 하드코딩 반입 없음. 이 worktree에
  동시에 작업 중이던 다른 세션의 미커밋 변경(`VariantConflictPanel.tsx`,
  `yujinEditingSummary.ts/test.ts`, 백엔드 `yujin_editing_proposal_*`, `director_proposals.py`,
  새 핸드오프 문서, 새 테스트 파일)은 건드리지 않았고 커밋에도 포함하지 않았다.

## 커밋·푸시

커밋 완료(내 파일 둘만: `TimelineDock.tsx`, `timeline-dock.test.tsx`). 이 worktree에 다른
세션의 미커밋 변경이 함께 있어 `git add`를 파일 단위로 했다. 코디네이터가 fast-forward 확인
후 push까지 진행한다.
