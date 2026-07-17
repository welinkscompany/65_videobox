# VideoBox OSS Dashboard and Editor Adoption Design

**Date:** 2026-07-17
**Status:** proposed design; implementation plan created; production implementation not started
**Research:** `docs/research/2026-07-17-videobox-oss-dashboard-editor-adoption.ko.md`

## 1. 결정

VideoBox의 다음 frontend 단계는 기존 dashboard에 카드를 더 붙이는 작업이 아니다. 검증된 오픈소스의 실제 구조를 선별 이식해 **프로젝트 앱 셸 + 대본부터 시작하는 제작 흐름 + 실제 편집 작업판**으로 재구성한다.

도입 방식은 다음으로 고정한다.

- shadcn/ui: CLI로 생성된 source-owned component system
- shadcn-admin: shell/layout composition의 partial source port
- OpenCut classic: editor layout과 일부 pure interaction의 source-derived port
- Opencast Editor: transcript/subtitle/waveform/cut UX의 attributed behavioral adaptation
- Supabase Studio: SaaS information architecture reference only

VideoBox의 editing-session, revision, asset provenance, FFmpeg preview/final, PyCapCut draft는 대체하지 않는다.

## 2. 사용자 목표

사용자는 기술 작업 상태를 탐색하는 운영자가 아니라 영상을 만드는 사람이다. 기본 흐름은 다음과 같다.

1. `새 영상 만들기`에서 대본을 입력하거나 파일을 올린다.
2. 루미가 영상 목적, 시청자, 길이, 분위기, 화면 비율, 참고 스타일, 반드시 넣을 장면을 짧게 인터뷰한다.
3. 루미가 현재 자산을 점검하고 실제 배치 가능한 B-roll/BGM/SFX와 부족한 `gap slot`을 보여준다.
4. 사용자가 `초안 만들기`를 한 번 승인하면 editing session 생성과 ranked placement bundle이 atomic/idempotent하게 적용된다. 승인 전 editing mutation은 0이고 실패 시 부분 적용은 없다.
5. 편집 작업판에서 중앙 영상을 보면서 하단 timeline, 좌측 자산·대본·자막, 우측 루미·추천·속성을 함께 사용한다.
6. 부족한 자산은 미리보기 후 선택한다. hover는 시각 preview를 준비하고 click/keyboard action은 명시적으로 재생한다. audio는 자동 재생하지 않는다.
7. 모든 변경은 preview/preflight 뒤 한 번의 revisioned mutation으로 적용되고 undo/redo가 가능하다.
8. 자막, 미리보기, 완성본, CapCut draft는 현재 editing-session revision과 source provenance를 사용한다.

초안 완료는 빈 session이나 proposal 목록을 뜻하지 않는다. 실제 timeline에 script/narration 또는 silent-storyboard segment, segment-aligned caption, 사용 가능한 B-roll 배치, 명시적 BGM/SFX 정책, 부족 자산의 gap slot이 존재해야 한다. E2E는 실제 session/segment/asset/clip ID를 확인한다.

초안 승인 전 narration readiness에서 `원본 영상 음성 / 완성된 narration audio / 녹음 또는 파일 업로드를 narration audio로 정규화 / 무음 storyboard` 중 하나를 고른다. TTS 학습용 `voice_sample_audio`는 완성 narration으로 직접 사용할 수 없다. 음성 합성이나 voice cloning은 이 설계의 완료 조건이 아니다.

대본 없이도 `수동 편집`으로 들어갈 수 있다. 자동 proposal이 없을 뿐 자산·timeline·output 기능은 유지한다.

## 3. 정보구조와 route

```text
/
/projects
/projects/$projectId/create
/projects/$projectId/home
/projects/$projectId/editor
/projects/$projectId/media
/projects/$projectId/outputs
/settings/general
/settings/appearance
/settings/ai-privacy
/settings/storage
/settings/output
```

`/`는 마지막 유효 프로젝트 home으로, 없으면 `/projects`로 이동한다. 프로젝트가 0개인 `/projects`는 첫 프로젝트 생성 empty state를 보여주고 생성 뒤 `/projects/$projectId/create`로 이동한다. URL의 `$projectId`가 선택 프로젝트의 canonical truth다.

좌측 메뉴는 화면의 역할을 기준으로 단순화한다.

- 홈
- 새 영상 만들기
- 편집
- 미디어
- 출력
- 설정

기존 `개요 / 타임라인 / 검수 / 편집` 탭은 별도 최상위 메뉴로 유지하지 않는다. 편집 작업판 안에서 preview, timeline, review 상태가 함께 보여야 한다. `전체 job 현황`은 sidebar의 큰 카드가 아니라 topbar의 background-job center로 이동한다.

## 4. 앱 셸

### 4.1 Desktop

- 좌측 256px 기본 sidebar, icon collapse 지원. editor route는 기본 icon collapse다.
- Sidebar header에 VideoBox와 ProjectSwitcher
- Sidebar content에 route navigation
- Sidebar footer에 설정과 local/cloud profile 정보
- 상단 sticky bar에 breadcrumb, 저장 상태, background job, 현재 화면의 primary action
- route content는 `SidebarInset` 안에서 독립 scroll

shadcn-admin의 `authenticated-layout`, `app-sidebar`, `nav-group`, `header`, `main`, `team-switcher`, settings layout을 pinned source에서 port한다. navigation label, route, project API, auth 부분은 VideoBox 용도로 재작성한다.

### 4.2 Narrow viewport

- canonical shadcn Sidebar의 Sheet를 사용한다.
- 편집기는 preview를 우선 노출하고 자산/script/captions/Lumi/Inspector는 focus-managed drawer 또는 bottom sheet로 전환한다.
- 기존 Director bottom sheet의 draft 보존, focus trap, IME Escape 예외를 유지한다.
- 작은 화면에서 frame-level fine trim 전체 기능을 억지로 제공하지 않는다. preview, 선택, 승인, 간단한 split/caption 수정부터 보장한다.

## 5. 편집 작업판

```text
EditorWorkbench
├─ EditorToolbar
├─ horizontal ResizablePanelGroup
│  ├─ LeftDock
│  │  ├─ Assets
│  │  ├─ Script
│  │  └─ Captions
│  ├─ PreviewStage
│  └─ RightDock
│     ├─ LumiConversation (항상 유지)
│     ├─ InlineRecommendations
│     └─ InspectorContext
└─ TimelineDock
   ├─ Ruler + Playhead
   ├─ Narration + Waveform
   ├─ Captions
   ├─ B-roll
   ├─ BGM / SFX
   └─ Overlay
```

기본 폭은 좌측 280–320px, 우측 360–420px, timeline 높이 240–320px로 시작한다. 1600px 이상에서만 두 dock을 동시에 열되 preview 720px 이상을 보장한다. 1280–1599px에서는 한 dock만 열고 preview 640px 또는 content 폭 50% 이상을 보장한다. 1280px 미만은 drawer로 전환한다. panel size는 사용자 UI preference로만 저장하며 editing truth가 아니다.

### 5.1 PreviewStage

- 두 모드를 명시적으로 구분한다. `편집본 미리보기`는 current revision을 authoritative FFmpeg composition path로 만든 exact proxy artifact를 재생한다. `선택한 클립 보기`는 한 source asset audition이다.
- exact proxy는 B-roll/caption/overlay와 narration/BGM/SFX scheduling, gain/fade/ducking, crop/loop/in/out, output canvas/fps를 final renderer와 같은 규칙으로 처리한다.
- revision/range/source SHA/render profile cache key와 freshness를 사용하며 stale artifact를 현재 편집본이라고 표시하지 않는다. `timelineStartSec/timelineEndSec/artifactRevision/generationId`를 반환하고 `timelineTime = timelineStartSec + media.currentTime`으로 매핑한다.
- selected range는 PTS 0부터 시작하고 caption/audio/overlay를 range origin으로 한 번만 이동한다. caption은 exact artifact에 한 번 burn-in하며 browser는 visual caption을 중복 overlay하지 않고 transcript/ARIA sync만 유지한다.
- 같은 session/range의 old generation은 coalesce/supersede하고 late completion은 current pointer를 바꾸지 못한다. exact artifact endpoint도 Range 206, Accept-Ranges, Content-Range, invalid range, MIME, H.264/AAC faststart, project isolation, stale path/path traversal contract를 통과해야 한다.
- review pending draft의 read-only preview는 허용하지만 preview는 review 상태를 변경하거나 final/CapCut approval gate를 우회하지 않는다.
- play/pause, seek, current time, selected range, volume, full-screen을 제공한다.
- OpenCut의 coordinate, zoom, pan, hit-test 수학은 pure module로만 port한다.
- OpenCut renderer, compositor, browser export는 사용하지 않는다.

### 5.2 LeftDock

- Assets: B-roll/BGM/SFX/image/voice filter, search, grid/list, analyzed/review-needed 상태
- Script: 대본 구간, 현재 segment, Lumi interview 결과
- Captions: 자막 text/time/style, 현재 재생 위치와 양방향 동기화
- 자산 preview는 기존 VideoBox candidate/content API를 사용한다.

### 5.3 RightDock

- Lumi: 현재 segment, selected placement, proposal revision, gap slot을 문맥으로 대화하며 composer는 유지
- Recommendations: 대화 속 inline card 또는 인접 context pane에서 B-roll/BGM/SFX candidate 비교와 explicit apply
- Inspector: 선택 type별 registry. VideoBox backend가 지원하는 필드만 노출

루미는 모든 설명 문구를 말하는 mascot이 아니다. 도움이 필요한 empty/error/recommendation 문맥에서만 짧게 안내한다. 버튼과 메뉴는 일반 사용자 용어를 사용한다.

### 5.4 TimelineDock

- fixed role tracks만 사용한다. 임의 track 추가는 이번 범위가 아니다.
- drag 중에는 local transient geometry만 바뀐다.
- pointer-up/keyboard commit 때 한 번만 expected revision을 보낸다.
- split, merge, bounds, reorder, B/M/S/overlay apply, undo/redo는 기존 server command를 호출한다.
- snapping candidate는 playhead, segment boundary, selected range, neighboring clip boundary다.
- min duration, overlap, lineage, revision conflict의 최종 판정은 server가 한다.
- role별 action은 다르다. narration만 segment split/merge/bounds/reorder를 사용하고, B-roll/BGM/SFX는 typed apply/clear/media-controls 명령, overlay는 지원 필드만 사용한다. generic clip trim 명령은 만들지 않는다.
- caption은 segment metadata이며 독립 timing handle이 없다. narration segment bounds가 바뀌면 linked caption과 배치 구간이 함께 바뀐다는 점을 UI에서 설명한다.

## 6. Frontend domain boundary

OpenCut 또는 Opencast DTO를 backend에 전파하지 않는다.

```ts
type TimelineTime = number // canonical unit: seconds at the API boundary

type EditorViewModel = {
  projectId: string
  sessionId: string
  sessionRevision: number
  durationSec: number
  playback: PlaybackManifest
  tracks: DisplayTrack[]
  captions: DisplayCaption[]
  selectedRange: { startSec: number; endSec: number } | null
  selectedItem: EditorSelection | null
}

type RevisionCommand = {
  projectId: string
  sessionId: string
  expectedRevision: number
}

interface EditorCommandPort {
  splitSegment(input: SplitCommand): Promise<EditorViewModel>
  mergeSegments(input: MergeCommand): Promise<EditorViewModel>
  setSegmentBounds(input: BoundsCommand): Promise<EditorViewModel>
  reorderSegments(input: ReorderCommand): Promise<EditorViewModel>
  applyCandidate(input: ApplyCandidateCommand): Promise<EditorViewModel>
  clearBroll(input: ClearBrollCommand): Promise<EditorViewModel>
  updateBrollControls(input: BrollControlsCommand): Promise<EditorViewModel>
  clearMusic(input: ClearMusicCommand): Promise<EditorViewModel>
  updateMusicControls(input: MusicControlsCommand): Promise<EditorViewModel>
  clearSfx(input: ClearSfxCommand): Promise<EditorViewModel>
  updateSfxControls(input: SfxControlsCommand): Promise<EditorViewModel>
  applyOverlay(input: ApplyOverlayCommand): Promise<EditorViewModel>
  clearOverlay(input: ClearOverlayCommand): Promise<EditorViewModel>
  updateCaptionText(input: CaptionTextCommand): Promise<EditorViewModel>
  updateCaptionStyle(input: CaptionStyleCommand): Promise<EditorViewModel>
  undo(input: RevisionCommand): Promise<EditorViewModel>
  redo(input: RevisionCommand): Promise<EditorViewModel>
}
```

`VideoBoxEditorAdapter`가 existing API DTO를 이 view model과 command port로 변환한다. source-derived React view는 `api.ts`의 raw response나 OpenCut EditorCore를 직접 알지 않는다.

## 7. Playback와 waveform 계약

편집기 진입 전에 project/session scoped playback manifest를 읽는다.

필수 필드:

- project/session/timeline/revision
- canonical `timebase: "seconds"`
- rational `fps_num/fps_den`, output canvas, sample aspect ratio, rotation
- total duration
- browser-accessible content URL과 MIME
- track/clip/segment/asset stable ID
- start/end/in/out/crop/loop/gain/ducking
- thumbnails
- captions and style
- source SHA/media revision/freshness
- audition URL과 exact FFmpeg preview job/artifact/freshness를 분리한 상태

기존 asset content endpoint에 대해 Range, MIME, stale path, path traversal, project isolation을 contract test로 먼저 검증한다. 통과하면 재사용하고, 부족할 때만 playback endpoint를 보강한다.

waveform은 FFmpeg job이 versioned peaks artifact를 생성한다. cache key에는 source SHA, stream index, channel mix, sample window, generator version을 포함하고 artifact index를 durable store에 남겨 process restart 뒤 재사용한다. 브라우저 전체 decode는 하지 않는다.

## 8. 대본·자막 흐름

Opencast의 cue/list/player 동기화 동작을 채택하되 state와 DOM은 새로 작성한다.

- current time clamp
- active segment/cue lookup
- deleted range 다음 playable time
- time↔pixel transform
- list selection ↔ timeline selection ↔ playback seek
- keyboard shortcut registry

자막 편집은 text input 중 shortcut을 가로채지 않는다. 이번 범위에서 caption timing은 narration segment와 연결되므로 caption-only drag/resize를 제공하지 않는다. 자막 lane은 linked 상태와 segment time을 표시하고 text/style만 독립 수정한다.

## 9. UI system

- shadcn/ui 4.13.0, Radix base, pinned source commit 사용
- Tailwind 4를 현재 Vite 5에 추가하되 global preflight는 migration 중 제외하고 theme/utilities만 가져온다. Vite/React 대규모 업그레이드는 분리한다.
- Pretendard Variable을 local bundle하고 OFL notice 포함
- neutral surface, 한 개의 accent, status semantic colors 사용
- migrated surface에서는 custom `.action-button`, `.panel`, `.pill`, `.empty-state`를 새로 만들지 않는다.
- `Button`, `Card`, `Badge`, `Alert`, `Empty`, `Skeleton`, `Dialog`, `Sheet`, `Tooltip`, `Tabs`, `ScrollArea`, `Resizable`을 우선 사용한다.
- old styles는 `.legacy-dashboard` 아래 격리하고 route parity 뒤 제거한다.
- migrated route에서 direct native button/input/dialog과 `.panel/.pill/.action-button` 같은 legacy class를 금지하는 AST allowlist verifier를 둔다. generated UI primitive와 접근성·media 예외만 문서화한다.
- Vitest와 browser는 시작부터 loopback allowlist network guard를 사용한다. CSS/HTML 정적 URL 검사만으로 외부 runtime 0을 주장하지 않는다.

## 10. Local과 SaaS 경계

shell은 `DeploymentCapabilities`만 본다.

```ts
type DeploymentCapabilities = {
  mode: "local" | "saas"
  account: boolean
  teams: boolean
  billing: boolean
  remoteStorage: boolean
  aiExecution: "disabled" | "local" | "managed"
}
```

local mode에서 account/team/billing placeholder를 보여주지 않는다. SaaS backend가 생긴 뒤 capability가 켜질 때 같은 shell slot을 사용한다. 이번 범위는 deterministic/fake/local interview driver만 구현하되 provider-neutral port를 유지한다. `external/Gemini call 0`은 local/test profile의 계약이며 미래 managed profile의 전역 금지가 아니다. 이 capability는 presentation gating일 뿐 authorization이 아니다. shadcn-admin auth, Clerk, Supabase auth 코드는 재사용하지 않는다.

## 11. 접근성·성능

- keyboard-only navigation, visible focus, focus return
- sidebar/drawer/dialog focus trap
- timeline scrubber/trim handle의 ARIA value와 keyboard step
- reduced motion
- 색상만으로 상태를 표현하지 않음
- audio autoplay 금지, 동시 preview 하나만 재생
- 60분 영상, 1,000 segment/cue fixture에서 clip DOM 300 이하, transcript row 120 이하, pointer move당 React commit 1회 이하를 구조적 gate로 둔다.
- recorded Chromium/CI profile에서 한 번 warm-up 후 다섯 번 측정하고 drag visual update median 50ms 이하, 기존 browser baseline 대비 20% 초과 회귀 금지를 적용한다.
- virtualization은 측정 결과가 필요할 때 transcript list부터 도입
- timeline redraw는 pointer move마다 React server state를 갱신하지 않음

## 12. Migration 전략

1. 현재 미커밋 Lumi copy 작업을 먼저 검증·closeout한다.
2. 프로젝트 없음, 대본 인터뷰, 자산이 채워진 편집기 세 화면을 네 viewport에서 prototype하고 사용자의 시각 승인을 받는다.
3. 기존 화면을 `LegacyWorkspacePage`로 보존하고 UI foundation/router/app shell을 도입한다.
4. 기존 Director/script draft API를 활용해 `대본→인터뷰→자산 점검→atomic real draft→editor/output handoff` 얇은 수직 Slice를 먼저 완성하고 사용자 승인을 받는다.
5. adapter와 exact FFmpeg preview를 갖춘 workbench를 연결한다.
6. timeline mutation, waveform, linked caption, asset/Lumi 고도화 순서로 이동한다.
7. 각 route parity와 E2E가 통과할 때만 legacy branch를 제거한다.

big-bang rewrite는 금지한다. feature flag는 개발 전환용이며 두 편집 truth를 만들지 않는다.

## 13. Source provenance 규칙

각 source-derived 파일은 다음 정보를 기록한다.

- upstream repository
- commit SHA
- upstream path
- local path
- `port`, `adapt`, `reference`, `reject` 분류
- license
- 주요 변경점
- 검증 test

`THIRD_PARTY_NOTICES.md`와 `docs/oss/editor-ui-source-map.json`을 verifier가 대조한다. reference-only source는 로컬 파일을 가리키면 실패한다.

shadcn registry source는 pinned commit의 upstream path와 normalized file SHA를 별도 lock에 기록한다. 각 registry item이 요구하는 runtime dependency도 package name, exact resolved version, license, package-lock entry로 대조한다. Pretendard는 `v1.3.9` commit `5c41199ea0024a9e0b2cb31735265056e5472d76`의 Variable WOFF2 SHA256 `9599f12fd42fc0bce1cd50b47a0c022e108d7aa64dd0d1bb0ed44f3282d900b4`와 OFL text를 사용한다.

## 14. 비목표

- OpenCut 전체 fork 또는 runtime dependency
- OpenCut EditorCore, browser persistence, renderer/export
- Opencast Redux/MUI/API client/player fork
- Supabase Studio source copy
- 이 계획 안에서 Hermes agent/container 구현
- 실제 SaaS auth/team/billing backend 구현
- keyframe, mask, transition, effect engine
- 모바일에서 desktop과 동일한 frame-level full NLE
- 사용자 승인 없는 Lumi 자동 apply/export
- independent caption timing model/API와 caption-only drag/resize

## 15. 이중 사용자 승인 gate

첫 gate는 production UI 구현 전에 수행한다. 프로젝트 없음, 대본/Lumi 인터뷰, 자산이 채워진 editor 세 화면을 1920/1440/1280/768/390px에서 실제 한국어 문구와 realistic mock data로 확인한다. 1920px populated-editor는 좌우 dock과 중앙 preview를 동시에 보여준다. 두 번째 gate는 실제 responsive workbench가 만들어진 뒤 수행하고 메뉴명, project switch, preview 중심 비율, persistent Lumi/inline recommendations, primary action, drawers를 확인한다. 두 gate 모두 승인 기록과 committed artifact SHA를 남기며, 승인 전 다음 고비용 편집 단계로 진행하지 않는다. 이 gate는 시각 조정만 허용하며 editing-session/FFmpeg/PyCapCut 권한 경계를 변경하지 않는다.

## 16. 인터뷰와 초안 상태 계약

인터뷰는 고정 설문지가 아니다. 대본에서 이미 알 수 있는 답은 건너뛰고 부족하거나 모순된 정보만 질문한다. `모르겠어요 / 추천해줘 / 건너뛰기`, 최대 질문 수, 진행률, 수정 가능한 최종 요약, refresh resume를 제공한다. script file은 UTF-8 `.txt/.md/.srt`, 1 MiB 이하로 제한한다. 이번 범위는 명시적 creation-brief 삭제로 retained input을 지우며 존재하지 않는 project-delete API를 약속하지 않는다.

초안 화면은 `자산 확인 중 → 초안 구성 중 → 준비됨 또는 추가 자산 필요 → 적용 중 → 완료/실패·재시도`를 보여준다. 각 후보는 기존 source preview로 실제 audition할 수 있고, gap slot은 기존 ingest/upload로 이동한 뒤 brief를 보존해 재분석한다. cancel은 atomic apply 전까지 허용한다. approval idempotency key, expected brief/draft-plan revision, apply 직전 source SHA/media revision 재검증을 사용해 session 생성과 bundle apply를 하나의 transaction으로 만든다. filesystem materialization은 per-SHA stage/atomic rename과 failure/restart cleanup을 포함하며 실패 시 partial session을 노출하지 않는다. silent storyboard는 provenance를 가진 deterministic local silence narration source를 배치해 current renderer의 narration contract를 만족한다. gap-only draft는 labeled placeholder로 preview할 수 있지만 unresolved visual gap이 있으면 final/CapCut을 차단한다. 사용자 수직 Slice 승인은 실제 current-revision FFmpeg MP4를 앱 안에서 재생한 뒤에만 가능하다.
