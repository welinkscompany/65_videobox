# 타임라인 조작층 — 오픈소스를 가져올까, 우리 것을 고칠까 (채택 스파이크, 2026-10-08)

- 질문: 편집기 **타임라인 조작층**(끌어 옮기기·순서 바꾸기, 가장자리 자르기, 붙기(스냅), 당기기(리플), 재생줄 끌기, 확대, 트랙 머리 칸, 고르기)을 성숙한 오픈소스 편집기에서 **가져오거나 일부 이식**하는 게 우리 코드를 고치는 것보다 나은가?
- 범위: 조사 + 버리는 시제품(저장소 밖 스크래치 폴더). **저장소 파일은 이 문서 하나만 새로 만들었다.**
- 근거 문서: `docs/superpowers/2026-10-08-editor-ui-audit.ko.md`(점검 결과), `CLAUDE.md` §3 재사용 게이트, `docs/implementation-plan.ko.md` §8.1, `docs/oss-adoption-map.ko.md` §5.1, `docs/oss/editor-ui-source-map.json`, `tests/test_editor_ui_source_provenance.py`.
- 공식 Task 여부: 계획서 밖의 **조사 스파이크**다. 결과는 계획 H(`docs/superpowers/plans/2026-10-08-editor-core-repair-h.ko.md`, 이 문서를 쓰는 시점에 아직 없음)에 넣을 수 있게 Task 초안으로 정리했다.

---

## 0. 한 줄 결론

**가져올 가치가 있는 건 "눈금 간격 계산" 하나뿐이고, 나머지는 우리 코드를 고치는 게 맞다.**
대표님이 겪은 결함 넷(엉뚱한 장면이 잡힘·트랙 단추가 안 눌림·자르기 손잡이가 가운데 글자 단추·120초에서 눈금이 붙음)은
**계산 부품이 모자라서가 아니라, 이미 있는 부품을 화면이 잘못 쓰거나 안 쓰고 있어서** 생겼다.
우리 저장소에는 가장자리 판정·붙기·좌표 계산 순수 함수가 이미 있고 시험도 붙어 있다 — 화면(`TimelineDock.tsx`)이
그 함수를 **가짜 좌표로 한 번** 부르거나(가장자리 판정), **재생줄 표시용으로만** 부른다(붙기).
남의 타임라인을 통째로 들이면 오히려 키보드 조작·한국어 이름표·우리 서버 명령 구조를 잃는다.

판정: **우리 코드 수리(rewrite in place) + opencut-classic 눈금 계산만 "참고 후 독립 구현"**. 약 **19시간**(리플 정책을 고르면 +5시간).

---

## 1. 무엇을 어떻게 쟀나

1. 후보 여섯을 스크래치 폴더에 `git clone --depth 1` 해서 **코드를 직접 읽었다**(별 수·라이선스·최근 push는 `gh api`로 대조).
2. 우리 타임라인 코드(`apps/web/src/features/editor/timeline/*`, `workbench/EditorWorkbench.tsx`)에서 결함이 **어느 줄에서** 나는지 찾았다.
3. **버리는 시제품**: 실제 서버에서 두 프로젝트의 재생 목록(`GET …/editing-sessions/editing_session_001/playback-manifest`, 읽기만)을 받아,
   - 우리 순수 함수(`hit-testing.ts`·`snapping.ts`·`timeline-geometry.ts`·`placementMutation.ts`)를 **저장소에서 고치지 않고 그대로** 불러오고,
   - 후보에서 옮겨 온 작은 조각(눈금 간격·리플 이동·고르기 규칙, 합계 98줄)을 붙여
   - 실제 숫자로 돌렸다(esbuild로 묶어 node 실행).
   - 위치: `%TEMP%\claude\…\scratchpad\adoption-spike\proto\spike.ts` (+ `ported/*.ts`). 저장소 밖, 버려도 된다.
4. 대상 프로젝트: `2026-09-12-742e1924`(120초, 장면 15개, 지금 rev 21) · `0907-b26195af`(7.75초, 장면 7개, rev 48).

---

## 2. 후보 비교표

| | ① openreel-video | ② opencut-classic | ③ OpenCut(재작성판) | ④ react-timeline-editor | ⑤ freecut | ⑥ Clypra |
|---|---|---|---|---|---|---|
| 저장소 | Augani/openreel-video | OpenCut-app/opencut-classic | OpenCut-app/OpenCut | xzdarcy/react-timeline-editor | walterlow/freecut | AIEraDev/Clypra |
| 라이선스 | MIT | MIT | MIT | MIT | MIT | MIT |
| 별 / 최근 push | 5,312 / 2026-10-03 | 266 / 2026-05-17 **보관됨(archived)** | 93,146 / 2026-09-24 | 797 / 2026-01-25 | 2,239 / 2026-09-29 | 3,311 / 2026-10-07 |
| 본 커밋 | `c9340465` | `cf5e79e9` (우리 고정값과 같음) | `e6680107` | `4148f4a8` | `4d62e808` | `bbc61a53` |
| 타임라인 코드 크기 | 약 14,900줄(이름에 timeline/snap/trim 들어간 파일) · `Timeline.tsx` 1,748줄 · `ClipComponent.tsx` 1,025줄 | 약 21,400줄 · `timeline-element.tsx` 1,298줄 · `timeline-manager.ts` 935줄 | **타임라인 없음**(TS 66파일, Rust 15파일, README가 "처음부터 재작성 중") | 약 3,000줄(`packages/timeline/src`) | 약 88,000줄(타임라인 기능 폴더) | 약 19,100줄 · `timelineStore.ts` 2,307줄 |
| 상태 주인 | zustand 프로젝트 저장소 + `@openreel/core` ClipManager(브라우저가 프로젝트를 가짐) | `EditorCore` + 타임라인 매니저 + IndexedDB/OPFS 저장 + WASM 시간형(`MediaTime`, 초당 120,000틱) | — | 컴포넌트가 `editorData`(행·액션 배열)를 받음 — 비교적 얇음 | zustand + zundo(되돌리기) + OPFS | zustand + Tauri 파일 + 자체 엔진 패키지 |
| 끌기·자르기 구현 | React 마우스 이벤트, 클립 양 끝 **8px 띠**(`w-2`)가 자르기 손잡이 | 컨트롤러 클래스(`resize-controller`·`element-interaction-controller`) + 순수 계산 일부 | — | `interactjs` 라이브러리가 끌기·크기 조절을 다 함 | 거대한 훅(`use-timeline-drag.ts` 1,553줄, `use-timeline-trim.ts` 950줄) | 훅(`useTimelineDrag.ts` 1,244줄) + 명령 객체 |
| 붙기(스냅) | `calculateSnap` 순수 함수(클립 **끝**도 붙임) | `snapping/` 93줄 순수(가장 가까운 점) | — | `gridSnap`·`dragLine` 옵션 | `timeline-snap-utils.ts` 184줄 순수 + 시험 304줄 | `snapTargets.ts` + 워커 |
| 리플 | `rippleDeleteClip`(코어, 프로젝트 저장소 결합) | `ripple/` 순수(전후 비교로 빈 구간 계산) | — | 없음 | 저장소 액션 안 | `gapEngine.ts` 332줄(거의 순수) |
| 눈금 | 고정 단계 표 | **`ruler-utils.ts` 257줄 순수** — 확대 정도에 따라 2·3·5·10·15프레임 / 1·2·3·5·10·15·30초… 간격 고름 | — | 고정 `scale` | 고정 단계 표(`timeline-markers.tsx`) | 자체 |
| 트랙 머리 | **별도 고정 칸**(폭 170/108px) | **별도 칸**(`TrackLabelsPanel`, 세로 스크롤 동기) | — | 없음(옆에 따로 그리라고 안내) | **별도 칸** | 별도 칸 |
| 시험 | 타임라인 관련 약 29개 파일 | 타임라인은 `update-pipeline.test.ts` 1개 | 없음 | **0개** | 185개 파일 | 약 35개 파일 |
| 접근성·키보드 | 클립·손잡이에 영어 aria-label, 클립 키 입력 일부 | 단축키 체계 있음 | — | **aria 0개, 키보드 없음** | 일부 | 일부 |
| 무거운 의존 | WebCodecs·자체 렌더러·자체 UI 패키지 | Next.js·WASM·IndexedDB | Rust 코어 | `interactjs`(28.7KB gzip, bundlephobia 측정) + `react-virtualized`(측정 못 함) | mediabunny·onnxruntime·transformers 등 | Tauri·Capacitor·자체 엔진 |
| 우리 명령 포트에 붙이는 비용 | 클립 컴포넌트가 저장소에 직접 씀 → **끊어 내기 어려움** | 컨트롤러가 EditorCore에 씀 → 순수 함수만 가능 | — | 이벤트 두 개(`onActionMoveEnd`·`onActionResizeEnd`)로 붙일 수 있음. 대신 그리기·스타일·키보드를 다 내줘야 함 | 훅이 저장소에 결합 | 저장소에 결합 |

**공통 관찰**: 성숙한 편집기 넷(①②⑤⑥) 모두 **트랙 머리를 클립과 겹치지 않는 별도 칸**에 두고, **고른 것을 id로 저장**하며 재생 시각에서 다시 유도하지 않는다. 이건 코드가 아니라 **배치 원칙**이라 가져올 코드가 필요 없다.

---

## 3. 실측 증거 (실제 서버 데이터로 돌린 결과)

타임라인 폭은 점검 때 잰 1,343px, 트랙 높이 32px, 손잡이 폭 8px로 계산했다.

### (가) 트랙 머리와 가장자리 손잡이

| 프로젝트·확대 | 지금(머리가 클립 위에 얹힘): 단추가 죽는 트랙 | 별도 머리 칸(160px)일 때 클립이 머리 밑으로 들어가는 수 | 우리 `classifyTimelineHit`에 **실제 손가락 위치**를 넣었을 때 시작끝/몸통 판정 정답 | 오늘 `시작·이동·끝` 글자가 잘리는 클립(110px 미만) |
|---|---|---|---|---|
| 742e1924 전체 보기(11.2px/초) | 3/3 | **0** | **31/31** | 19 |
| 742e1924 50px/초 | 1/3 | 0 | 31/31 | 2 |
| 0907 전체 보기(173px/초) | 3/3 | **0** | **43/43** | 12 |
| 0907 50px/초 | 3/3 | 0 | 43/43 | 43 |

→ 가장자리 판정 함수는 **이미 맞게 동작한다**. 문제는 화면이 이 함수를 클립 **한가운데 좌표·손잡이 폭 1px**로 한 번 부르고(`TimelineDock.tsx:541`), 실제 손잡이는 클립을 3등분한 글자 단추로 그린다는 것(`:1093-1099`). 트랙 단추는 클립이 0초 근처에 있으면 `pointer-events:none`으로 비켜 주는 규칙(`:961-962`, `LANE_HEADER_DEAD_ZONE_PX=180`) 때문에 죽는다 — 머리를 별도 칸으로 빼면 이 규칙 자체가 필요 없다.
→ 전체 보기에서 폭 24px 미만인 클립이 742e1924에 2~4개 있다. 이런 클립은 몸통을 잡을 자리가 없으니 "확대해서 잡으세요" 처리나 손잡이 최소 폭 정책이 필요하다(어느 후보도 이걸 따로 풀지 않았다).

### (나) 고르기를 id로 — "앞 장면이 잡힌다" 결함

클립을 누르면 화면은 그 장면 **시작 시각으로 재생기를 옮기고**, 재생기가 알려 주는 시각으로 장면을 **다시 찾는다**(`EditorWorkbench.tsx:598` `onPlaybackTimeChange={seekPlayback}` → `:396-409` → `activeSegmentIdAt`). 재생기 시각은 반올림돼서 장면 시작보다 아주 조금 작다.

| 재생기 시각 반올림 모형 | 프로젝트 | 장면 수 | **지금 엉뚱한 장면** | id 우선 규칙(시제품) |
|---|---|---|---|---|
| 백만분의 1초 버림(점검에서 본 `1.899064`) | 0907 | 7 | **5** | 0 |
| 백만분의 1초 버림 | 742e1924 | 15 | 0 | 0 |
| 프레임 단위 버림 | 0907 | 7 | **6** | 0 |
| 프레임 단위 버림 | 742e1924 | 15 | **5** | 0 |

- 예: 0907에서 `1.8990646…`초에 시작하는 장면을 누름 → 재생기 `1.899064` → 지금 규칙은 **앞 장면**을 고름. 점검 3-1과 같은 숫자다.
- id 우선 규칙(23줄): "방금 누른 장면은 재생기 시각이 그 장면 시작 1프레임 안쪽이면 그대로 둔다, 아니면 반 프레임 여유를 두고 시각으로 찾는다."
- 재생 중 회귀 확인: 장면 가운데 시각에서 기존 규칙과 일치 15/15·7/7, 재생줄이 다음 장면으로 넘어가면 고른 장면도 따라감 13/14·6/6(나머지 1쌍은 실제 데이터에서 붙어 있지 않은 경계라 셈에서 빠짐).
- **어느 후보도 이 결함을 고쳐 주지 못한다** — 결함은 타임라인 부품이 아니라 우리 편집기의 "재생 시각 → 고르기" 배선에 있다.

### (다) 붙기·리플을 우리 장면 모델에서

- **붙기**: 742e1924에서 두 번째 영상 클립을 옆 클립 끝(24초)에서 5px 오른쪽에 놓으면 → 우리 `findTimelineSnap`이 24초에 붙임 → `derivePlacementMove` → 명령 포트 `setTimelinePlacements` 값 `{"placementId":"broll:session-broll-timeline_001:001__split_2__split_2-0","kind":"broll","startSec":24,"endSec":33.933…}`. **함수는 된다. 그런데 화면은 끌기·자르기 중에 이 함수를 부르지 않는다**(소비자 grep: `TimelineDock.tsx:385` 한 곳, 재생줄 옆 "스냅: …" 글자 표시용). openreel처럼 **클립 끝도 붙게** 하는 건 어댑터 몇 줄이면 된다(시제품에서 확인).
- **리플(빼면 당기기)**: 순수 계산은 간단하다(0907 장면 5 빼기 → 뒤 장면 −1.697초, 끝 7.75 → 6.05초, 겹침 없음; 742e1924 → 120 → 111.02초). **문제는 서버다**: 지금 명령 포트에 "빼고 당기기" 한 번짜리 명령이 없다. `setCutAction(remove)` + `reorderNarration(boundsById)` 두 번으로 흉내 내면 **되돌리기가 두 칸**이 되고(한도 10칸), `reorder_segments`는 빠진 장면까지 **모든 장면의 겹치지 않는 자리**를 요구한다(`editing_session.py:946-958`) — 빠진 장면 자리를 어디에 둘지 서버 규칙이 없다(검증 안 함). 그리고 B-roll·오버레이 배치(`timeline_placement_overrides`)가 같이 당겨지는지도 서버 쪽 결정이다. → **리플은 어느 후보를 가져와도 서버 명령 1개가 먼저다.** 점검 3-5의 "당길지, 구멍을 보여 줄지"는 대표님 결정이 먼저다.

### (라) 눈금

| 확대 | 지금 | opencut-classic 방식(옮긴 계산) |
|---|---|---|
| 742e1924 전체 보기 11.2px/초 | 눈금 글자 **121개, 11px 간격**(붙어서 못 읽음, 점검 그림 10) | **9개, 15초마다(168px)**, 잔눈금 3초 |
| 742e1924 50px/초 | 121개, 50px | 41개, 3초마다(150px) |
| 0907 전체 보기 173px/초 | 8개, 173px | 8개, 1초마다(같음) |

→ 이게 이번 조사에서 **유일하게 남의 계산이 우리 것보다 나은 곳**이다. 계산은 53줄 정도로 작다.

### (마) 묶음 크기

- 옮긴 조각 셋(눈금·리플·고르기, 98줄) esbuild 압축: **1,983바이트, gzip 918바이트**. 지금 웹 번들 `index-*.js` 약 1.0MB에 비하면 없는 수준.
- react-timeline-editor를 통째로 들이면: `interactjs` 하나만 gzip **28.7KB**(bundlephobia), `react-virtualized`는 측정 못 함(요청 한도 429) + 본체 약 3,000줄.

### (바) 남는 데이터 흠

0907 재생 목록에 **같은 clip_id가 4개** 겹쳐 있다(점검 3-3). react-timeline-editor도 액션 id가 겹치면 안 되므로 **어느 쪽을 택하든 서버 데이터 정리가 따로 필요하다.**

---

## 4. 후보별 판정 (재사용 게이트)

| 후보 | 판정 | 이유 |
|---|---|---|
| ① openreel-video | **reference only** (`docs/oss-adoption-map.ko.md`의 기존 `partial port`를 내린다) | 클립 컴포넌트가 프로젝트 저장소에 직접 쓰고, 브라우저가 프로젝트·렌더를 가진다(우리 원칙 정반대). 배울 것은 "양 끝 8px 띠 손잡이"와 "클립 끝도 붙기" 두 가지 **동작**뿐이고 둘 다 코드 없이 다시 짜는 게 짧다 |
| ② opencut-classic | **눈금 간격 계산만 reference → 독립 구현**, 나머지 exclude | 보관된 저장소. 타임라인 본체는 EditorCore·WASM 시간형에 묶임. `ruler-utils.ts`는 순수하고 우리 결함(3번 눈금)을 정확히 푼다. 우리 Task 14가 이미 같은 방식(보고 다시 쓰기)으로 기하·붙기를 만들었다 — 그 기록에 한 줄 더하는 셈. 이미 이식한 것: 작업판 배치(Task 11), 좌표·확대·붙기·판정 계산(Task 14, 독립 구현). **이식 안 한 것**: 컨트롤러(끌기·크기·재생줄), 리플 diff, 눈금, 트랙 머리 칸, 그룹 이동 |
| ③ OpenCut 재작성판 | **exclude** | 여전히 편집기·타임라인 코드가 없다(README "처음부터 재작성 중", 이번 클론에서 확인) |
| ④ react-timeline-editor | **exclude** | 시험 0개, aria 0개, 키보드 없음 → 지금 있는 **키보드 자르기·옮기기를 잃는다**. 그리기를 통째로 가져가 우리 다크 팔레트·한국어 이름표·썸네일을 다시 덮어써야 한다. 붙이는 코드 약 550줄 + 의존 둘. 얻는 건 끌기 동작 하나 |
| ⑤ freecut | **reference only** | 품질(시험 185파일)은 가장 좋지만 타임라인이 8만 줄 규모이고 손질 함수도 저장소를 import한다(`trim-utils.ts` → `useCompositionsStore`). 붙기 계산은 우리 것과 같은 수준이라 가져올 이유가 없다 |
| ⑥ Clypra | **reference only** | `gapEngine.ts`(리플·빈 구간)는 거의 순수하고 시험도 있어 **서버 리플 규칙을 정할 때 참고**할 만하다. 하지만 리플은 서버 몫이라 웹에 옮길 코드가 아니다. Tauri·자체 엔진 결합 |
| 기존 우리 코드 | **rewrite in place(배선 수리)** | 순수 함수는 이미 맞다(실측 31/31·43/43). 고칠 곳은 `TimelineDock.tsx`의 그리기·포인터 배선과 `EditorWorkbench.tsx`의 고르기 규칙 |

제외 이유 공통: `UI 구조 통째`, 브라우저가 프로젝트·렌더를 가지는 구조는 반입 금지(`CLAUDE.md` §3). GPL·AGPL·라이선스 불명 후보(MasterSelects AGPL, twick·react-video-editor NOASSERTION 등)는 보지 않았다.

---

## 5. 추천 경로 — 계획 H에 넣을 Task 초안 (7개, 약 19시간 + 결정 시 5시간)

| # | 일 | 고치는 점검 항목 | 시간 | 비고 |
|---|---|---|---|---|
| H-a | **고르기 id 우선 규칙**: `resolvePlaybackSelection`(순수, 시험 먼저: 0907 실제 경계 `1.8990646…`/`1.899064`) → `EditorWorkbench.seekPlayback`가 "방금 누른 장면"을 기억 | 3-1, 속도가 엉뚱한 장면에 들어감 | 2 | 가장 싸고 가장 위험한 결함. 다른 Task와 독립 |
| H-b | **트랙 머리 고정 칸**: 머리 칸(약 160px) + 클립 면을 그 오른쪽에서 시작, 세로 스크롤 동기. `LANE_HEADER_DEAD_ZONE_PX`·`clusterPointerEvents` 규칙 삭제 | 3-4, 단추 9개 부활·첫 클립 이름 가림·가로 넘침 29px | 4 | 클립 x 좌표 기준이 바뀌므로 재생줄·클릭 seek 좌표도 같이(같은 원점 함수 하나로) |
| H-c | **가장자리 손잡이**: `시작·이동·끝` 글자 단추 → 클립 양 끝 8px 띠(커서 `ew-resize`) + 몸통 끌기 = 옮기기. 판정은 기존 `classifyTimelineHit`에 **실제 포인터 좌표** 전달. 키보드 조작은 손잡이에 초점·aria-label 유지 | 3-8, 그림 03·04 | 5 | 폭 24px 미만 클립 정책(손잡이 최소 폭 또는 확대 안내) 같이 정함 |
| H-d | **끌기·자르기 중 붙기 배선**: 기존 `findTimelineSnap`을 이동(시작·끝 둘 다)과 자르기 가장자리에 연결, 붙은 자리에 세로 안내선 | 점검 §8 "스냅 미시험" + 이번 소비자 0건 발견 | 3 | 후보 계산 반입 없음 |
| H-e | **눈금 간격**: opencut-classic `ruler-utils.ts` 방식을 **보고 독립 구현**(`timeline/rulerScale.ts`), 라벨 최소 간격 120px | 3번 표의 눈금 붙음(그림 10) | 2 | 아래 §6 기록 의무 |
| H-f | **실기 검증 넷**(갭·역방향·동작·배선): 0907·742e1924에서 클릭→오른쪽 편집 항목 장면 일치, 트랙 단추 마우스로 눌림, 가장자리 끌기 저장, 붙기, 120초 눈금. 서버 `GET editing-sessions`로 rev·값 확인, 되돌리기로 원복 | 전부 | 3 | `CLAUDE.md` §4 — 화면에서 밟아야 완료 |
| H-g *(결정 후)* | **빼고 당기기(리플) 서버 명령 1개** + 포트 메서드 + `빼기` 옆 선택. B-roll·오버레이 배치 동반 이동 규칙 포함, 되돌리기 1칸 | 3-5 | 5 | **대표님 결정 필요**(당길지/구멍을 보여 줄지). Clypra `gapEngine`은 참고만 |

순서: H-a → H-b → H-c → H-d → H-e → H-f (H-g는 결정이 나면). H-a·H-e는 서로 독립이라 병렬 가능.
고칠 줄 수 추정: 화면·순수 함수 합쳐 약 250줄 변경, 새 의존 **0개**, 번들 증가 약 1KB(gzip).
비교: react-timeline-editor를 들이는 길은 붙이는 코드 약 550줄 + 의존 2개 + CSS 덮어쓰기 + 키보드 재구현으로 **30~40시간**에, 위 H-a(고르기)·H-g(리플)는 그대로 따로 해야 한다.

---

## 6. 라이선스·기록 의무 (H-e를 할 때)

H-e는 **보고 다시 쓰기(reference only)** 로 하는 게 맞다 — 우리 Task 14가 이미 같은 길을 갔고, 시험이 그 형식을 고정하고 있다.

1. `docs/oss/editor-ui-source-map.json` → `reference_only_decisions`의 `"Task 14 timeline geometry"` 항목:
   - `local_paths`에 `apps/web/src/features/editor/timeline/rulerScale.ts`(새 파일 이름은 예시) 추가
   - `inspected_upstream_paths`에 `{"path": "apps/web/src/timeline/ruler-utils.ts", "sha256": "8acde0c6a49be27d9517fcabfc9239bcaeb8ae24586aeb05e08338b8b140ce57"}` 추가
     (리플 동작을 참고했다면 `apps/web/src/ripple/shift.ts` `490974a1df132729fc8f53f585d77becb8ccdea0cbb199f91f459cbcdb43b951`도)
2. `tests/test_editor_ui_source_provenance.py` `test_task14_timeline_math_is_reference_only` — 이 시험은 위 항목을 **dict 전체 일치**로 검사하므로 **같이 고쳐야 한다**. 새 파일에는 `forbidden_import_terms`(`document`·`window`·`canvas`·`EditorCommandPort` 등) 낱말이 주석에도 들어가면 안 된다.
3. `THIRD_PARTY_NOTICES.md` — OpenCut classic MIT 줄(81행)이 이미 있다. reference only면 **추가 없음**. 만약 코드를 그대로 옮기면(권하지 않음) `materialized_files`에 upstream/normalized sha256·test_path를 넣고 원본 MIT 고지를 파일 머리에 남겨야 한다.
4. `docs/oss-adoption-map.ko.md` — `Augani/openreel-video` 줄을 `partial port` → `reference only`로, ②의 "이식 안 한 것" 목록, ⑤ freecut·⑥ Clypra·④ react-timeline-editor 줄(라이선스·별·최근 push·판정)을 추가.
5. `scripts/verify-editor-ui-source-provenance.ps1`로 확인. 백엔드 시험은 `.venv/Scripts/python.exe -m pytest tests/test_editor_ui_source_provenance.py`.

H-a~H-d·H-g는 남의 코드를 옮기지 않으므로 기록 의무 없음.

---

## 7. 위험

- **H-b(머리 칸)는 좌표 원점을 바꾼다.** 클립·재생줄·클릭 seek·끌어다 놓기 자리가 한 원점을 써야 한다(`TimelineDock.tsx`에 "같은 좌표계" 경고 주석이 이미 셋). 하나만 옮기면 화면이 어긋난다 — 시험은 초록일 수 있으니 화면 캡처로 확인.
- **H-c는 키보드 조작을 지켜야 한다.** 지금 손잡이 단추는 화살표로 한 프레임씩 움직인다. 얇은 띠로 바꿀 때 초점·이름이 사라지면 접근성 퇴보다.
- **H-a 규칙의 1프레임 여유**가 아주 짧은 장면(1프레임 길이)에서 맞는지는 실물이 없어 못 쟀다.
- 0907의 **중복 clip_id**(점검 3-3)는 이 경로와 별개로 남는다. 고치지 않으면 손잡이를 아무리 잘 그려도 0907에서 저장은 422다.
- 이 조사는 데스크톱 마우스 기준이다. 터치(openreel은 터치 제스처가 있음)는 범위 밖.

---

## 8. 이 길로 **얻지 못하는 것** (정직하게)

- **실시간 미리보기**(점검 3-2, 편집마다 44초 다시 굽기) — 타임라인 조작층과 무관. 후보 중 ①⑤⑥은 브라우저 렌더러로 이걸 풀지만, 그건 서버가 렌더를 가지는 우리 구조와 정면으로 충돌하므로 가져올 수 없다.
- 여러 클립 동시 끌기(그룹 이동)·끌어 놓을 때 다른 트랙으로 옮기기·잔물결 편집 종류(slip/slide/roll)·파형 그리기 — 이번 Task에는 없다. opencut-classic `group-move/`, freecut `use-timeline-slip-slide.ts`가 참고 대상이지만 지금 결함 목록에 없다.
- 리플은 서버 명령과 대표님 결정 없이는 안 된다(H-g).
- J/K/L 재생 단축키(점검 #15)는 이 범위가 아니다.

---

## 9. 확인하지 못한 것

- **화면에서는 아무것도 바꾸거나 눌러 보지 않았다.** 시제품은 서버 재생 목록을 읽어 계산만 했다. "id 우선 규칙"이 실제 재생기와 함께 결함을 없애는지는 H-f에서 브라우저로 밟아야 안다.
- 재생기 시각 반올림은 두 모형(백만분의 1초 버림·프레임 버림)으로만 쟀다. 브라우저가 실제로 돌려주는 값은 점검의 한 숫자(`1.899064`)뿐이다.
- `reorder_segments`로 리플을 흉내 낼 수 있는지(빠진 장면 자리 처리)는 서버를 부르지 않아 **검증 안 함**.
- `react-virtualized` 묶음 크기(측정 요청 한도), 후보들의 시험을 직접 돌려 보지는 않았다(파일 수만 셈).
- 742e1924의 rev가 점검 때 18에서 지금 21로 바뀌어 있었다(영상 클립 하나가 90~102초로 옮겨져 겹침). 이 조사에서 바꾼 것이 아니다 — 누가 언제 바꿨는지는 확인하지 않았다.
- 계획 H 문서는 이 문서를 쓸 때 아직 없어서 Task 번호를 맞추지 못했다(H-a~H-g는 임시 이름).
