# web-design-reviewer·no-ai-design-slop로 화면 점검 → 실제 결함 셋 고침

**대체됨:** `docs/handoffs/2026-09-17-review-output-variant-conflict-resolution.ko.md`

대표님이 skills.sh에서 `github/awesome-copilot@web-design-reviewer`,
`mengto/skills@no-ai-design-slop` 두 스킬을 설치해 이 저장소를 점검해
보자고 하셨다. `/projects` 목록·편집기(`/projects/{id}/editor`) 화면을
데스크톱(1280px)·태블릿(768px)·모바일(375px)에서 실제로 훑었다.

## 찾은 것 넷, 고친 것 셋, 안 고친 것 하나

### [고침] 편집기 미리보기 컨트롤바 겹침 — 모바일

재생 버튼 줄(`◀| 재생/일시정지 |▶ 음소거 반복 전체화면`)과 "타임라인
0.0 / 8.0초" 글자가 좁은 화면에서 겹쳐 보였다. 원인: 버튼 5개는
`flex: 0 0 auto`라 안 줄어드는데, 옆 `<output>`은 기본 `flex-shrink`가
가장 긴 낱말("타임라인") 너비까지만 줄이고 나머지를 세로로 줄바꿈해서
글자가 재생 버튼과 겹쳐 보였다. `apps/web/src/styles/editor-workbench.css`
의 `.vb-preview-stage__playback`에 `flex-wrap: wrap` 한 줄 추가 — 공간이
모자라면 시간 글자가 다음 줄로 깨끗이 내려간다.

### [고침] 타임라인 트랙 이름 글자 뭉개짐 — 태블릿("영상"→"경상")

처음엔 "폭이 좁아 잘린다"고 진단했는데 **틀렸다** — DOM은 글자 전체를
이미 담고 있었다(`scrollWidth`로 확인). 진짜 원인: 재생 위치 선
(`.vb-timeline-playhead`, `z-index: 3`)이 0초일 때 트랙 이름 span
(`z-index: 1`)의 왼쪽 몇 픽셀과 정확히 겹쳐 글자 모양이 뭉개졌다 --
폭과 무관하게 **재생 위치가 0초 근처일 때 어느 화면에서나 나는 문제**였다
(데스크톱에서도 재현, 다만 눈에 덜 띄었을 뿐). `TimelineDock.tsx`의
고정 트랙 목록 `z-index`를 1 → 4로 올려 재생 위치 선보다 위에서 그려지게
했다. 클릭 가능 범위는 그대로다(재생 위치 선은 원래
`pointer-events: none`).

### [고침] 프로젝트 이미지 자산 썸네일 404

`사진 브이로그 실기 0907`(`0907-b26195af`)의 자산 2개가 썸네일을
못 받아 왔다. 원인: `routers/assets.py`의 `get_asset_thumbnail`이
brol(영상) 자산만 들여올 때 미리 만든 썸네일을 서빙하고, 이미지
자산은 애초에 아무도 안 만들었다 -- 파일이 없으면 그냥 404였다.
공유 자료실 쪽(`/api/library/assets/{id}/thumbnail`)은 이미 이미지를
실제로 그려 서빙하고 있었다(`routers/library_assets.py`의
`_render_derivative`, 같은 이름의 시험 `test_an_image_gets_a_thumbnail_
and_never_a_waveform`로 이미 확인돼 있었음). 그 렌더 로직을
`packages/core-engine/src/videobox_core_engine/thumbnail_generator.py`의
`render_thumbnail_bytes`로 옮겨 두 곳(자료실·프로젝트 자산)이 같이 쓰게
했다 -- 같은 렌더를 두 번 짜지 않는다(이 저장소가 반복해서 걸린 함정).
프로젝트 쪽은 첫 요청에서 즉석으로 그려 캐시 경로(`derived/thumbnails/
{asset_id}.jpg`)에 써 둔다. 그 경로 확장자는 `.jpg`(broll 규칙)인데
이미지는 png로 그려서, 서빙할 때 파일 첫 4바이트로 실제 형식을 가려
`Content-Type`을 맞게 붙였다(확장자만 믿지 않음).

### [안 고침] "유진" 채팅 버튼이 미리보기 모서리와 겹침 — 의도된 설계

캡컷 EditPilot처럼 도크와 무관하게 화면 구석에 뜨는 자리다(owner 지시
2026-08-30, 코드 주석에 명시). 타임라인과 275px 겹치던 더 심한 문제는
이미 한 번 고쳐져 있었다(`__body` 기준으로 옮김). 지금 남은 겹침은
미리보기 플레이어 모서리와의 의도된 정도라 **재승인 없이 건드리지
않았다**(§6 UI 팔레트·비주얼 방향 변경 규칙과 같은 결의 판단).

## 검증

**단위·통합**: `tests/test_library_image_assets.py`에 RED→GREEN 시험 1건
추가(이미지 자산이 첫 요청에 썸네일을 200으로 받고, 두 번째 요청은 같은
바이트를 그대로 재사용하는지). 관련 파일(`test_library_image_assets.py`,
`test_broll_thumbnail_generation.py`, `test_api_library_assets.py`) 28건
전부 통과.

**프론트엔드**: `tsc --noEmit` 깨끗함. `timeline-dock.test.tsx`(71건),
`preview-stage.test.tsx`(38건) 통과. 전체 프론트 시험(139개 파일,
1746건) 전부 통과. `npm run build` 정상 빌드(무관한 기존 CSS 경고 1건은
그대로 -- `.vb-editor-assets__narrow` 근처, 이번 변경과 무관).

**역방향(실물)**: 이 수정들로 컨테이너를 재빌드했다. **처음 확인할 때
화면이 옛 번들(`index-Bh9iNKBr.css`)을 계속 보여줘서 안 고쳐진 줄
알았다** -- 서버(`curl`)는 이미 새 번들(`index-Cq-YbcfU.css`)을 주고
있었다, 브라우저 창(Browser pane)의 캐시였다(`[[videobox-container-
rebuild-stale-bundle]]` 메모 그대로). 주소에 캐시 무력화 쿼리를 붙여
새 번들을 받은 뒤 셋 다 실측 확인:
- 모바일(375px): 컨트롤바가 두 줄로 깨끗이 나뉨, 겹침 없음(`getBoundingClientRect`로 재확인).
- 태블릿(768px): "내레이션·영상·배경 음악·효과음·오버레이·캡션" 전부
  정상 표기. 트랙 라벨 `z-index`가 4로 재생 위치 선(3)보다 위임을 확인.
- `0907-b26195af`의 두 자산(`asset_f33e61007e2d`, `asset_408772bb1072`)
  썸네일 요청이 실제 네트워크 로그에서 404 → 200으로 바뀜.

**전체 backend pytest(단독, 40분 50초)**: 5138 passed, 56 skipped,
1 xfailed, 실패 0건. 회귀 없음.

## 재사용 게이트 메모

- 확인한 재사용 후보: 자료실 쪽 이미지 썸네일 렌더(`_render_derivative`)
  -- 이미 있었고 검증도 돼 있었다.
- 실제 반영: 그 함수를 `thumbnail_generator.py`로 옮겨 공개 함수
  (`render_thumbnail_bytes`)로 만들고, 자료실·프로젝트 자산 라우터
  둘 다 그걸 쓰게 배선.
- 제외한 것: 자료실 쪽의 "렌더 실패 시 해시 막대 SVG 대체 그림" 기능은
  프로젝트 자산 쪽에 옮기지 않았다 -- 기존 broll 404 동작(실패하면
  그냥 404)과 일관되게 뒀다, 범위 확대 안 함.
- 경계 보존: 자료실(`LibraryUserAssetStore`, content-hash 캐시)과
  프로젝트 자산(`asset_id` 기준 캐시) 저장 스키마는 손대지 않았다 --
  렌더 로직만 공유.

## 이번 세션 앞 절반 (task_4defd174, 이미 커밋·푸시됨)

참고로 이 세션은 이 문서 전에 `task_4defd174`(변형본 렌더 검토 승인이
매번 새 timeline 때문에 못 이어지던 결함, 원인은 `operator_guidance`
누수)도 고쳤다 -- 커밋 `0da41a54`, 인계 문서
`2026-09-17-variant-render-review-approval-operator-guidance-leak.ko.md`.

## 다음 세션이 할 일

1. `task_acfd8147`(세로 blur 육안 확인) -- `task_4defd174` 고침으로
   막힌 게 풀렸을 가능성이 크다. 장면 수 적은 프로젝트로 시도.
2. `task_3dc11426`(숏폼 만들면 세로영상 출력이 깨짐), `task_006f1523`
   (R1 경계 나누기)은 여전히 대기.

## 서버·환경 상태

- 컨테이너: 이 세션이 이 수정들로 재빌드해서 켜져 있음(healthy).
- worktree: `.worktrees/videobox-container-compatibility`, 브랜치
  `codex/videobox-container-compatibility`.
