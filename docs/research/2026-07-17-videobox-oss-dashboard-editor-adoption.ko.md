# VideoBox OSS 대시보드·편집기 도입 조사

**조사일:** 2026-07-17
**상태:** 조사 완료, 구현 미착수
**대상:** shadcn-admin, shadcn/ui, OpenCut, OpenCut classic, Opencast Editor, Supabase Studio
**판단 기준:** 실제 공식 소스, 고정 commit, 라이선스, 현재 VideoBox 계약과의 적합성

## 1. 결론

도입 가치는 충분하다. 다만 하나의 오픈소스를 통째로 가져오는 방식은 맞지 않는다. 가장 안전하고 효과적인 조합은 다음과 같다.

1. **shadcn/ui:** 공식 CLI가 생성한 소스를 VideoBox가 직접 소유한다.
2. **shadcn-admin:** 앱 셸의 레이아웃 조합만 source port한다.
3. **OpenCut classic:** 편집 작업판 배치와 일부 순수 timeline/preview 계산만 adapter 뒤로 선별 이식한다.
4. **Opencast Editor:** 대본·자막·waveform·컷 편집 UX와 순수 계산을 Apache-2.0 고지와 함께 source-derived behavioral adaptation한다.
5. **Supabase Studio:** 프로젝트 전환, 설정, 모바일 탐색의 정보구조만 참고한다. 소스는 직접 복사하지 않는다.

OpenCut의 최신 rewrite를 현재 편집기 기반으로 쓰는 안은 기각한다. 최신 공식 저장소에는 아직 실제 editor route, timeline, preview compositor, asset browser, inspector가 없다. 공식 README도 현재는 classic을 쓰라고 안내한다. [OpenCut rewrite README](https://github.com/OpenCut-app/OpenCut/blob/bab8af831b354a0b5a98a4a6e818ab7d633b94df/README.md)

## 2. 현재 VideoBox에서 확인한 사실

- `apps/web/src/App.tsx`는 4,190줄, `styles.css`는 962줄, `app.test.tsx`는 5,787줄 수준이다. 프로젝트 선택, job, 편집, 검수, 설정, 출력이 한 컴포넌트에 집중돼 있다.
- 현재 앱은 React 19.1, Vite 5.4, TypeScript 5.8만 사용한다. router, Tailwind, 공통 UI kit가 없다.
- 현재 편집 화면은 카드와 폼 중심이다. 중앙 영상 stage, 실제 playhead, waveform, drag/trim 가능한 timeline이 없다.
- backend에는 editing-session revision, split/merge/bounds/reorder, fixed track, caption, B-roll/BGM/SFX/overlay, selected-range preview, undo/redo, output freshness, FFmpeg/PyCapCut 경계가 이미 있다.
- 현재 `PreviewRenderer`는 최종 미디어가 아니라 timing/caption을 설명하는 placeholder HTML을 만든다. 실제 editor playback 계약은 별도로 보강해야 한다.
- 자산 content endpoint는 존재한다. 브라우저 편집기에 필요한 HTTP Range, MIME, stale source, 접근 제어를 새 contract test로 먼저 증명하고 부족한 부분만 보강해야 한다.

따라서 문제는 편집 엔진 부재보다 **강한 서버 계약을 사람이 이해할 수 있는 작업판으로 번역하지 못한 frontend 구조**에 가깝다.

## 3. 조사 기준점과 라이선스

| 대상 | 고정 기준 | 라이선스 | 판단 |
|---|---|---|---|
| shadcn-admin | `e16c87f213a5ba5e45964e9b67c792105ec74d26` | [MIT](https://github.com/satnaing/shadcn-admin/blob/e16c87f213a5ba5e45964e9b67c792105ec74d26/LICENSE) | shell source port |
| shadcn/ui | `4396d5b2a5ee4e2ad5705e9b2522f92112f811a0`, CLI 4.13.0 | [MIT](https://github.com/shadcn-ui/ui/blob/4396d5b2a5ee4e2ad5705e9b2522f92112f811a0/LICENSE.md) | pinned registry source ownership |
| OpenCut rewrite | `bab8af831b354a0b5a98a4a6e818ab7d633b94df` | [MIT](https://github.com/OpenCut-app/OpenCut/blob/bab8af831b354a0b5a98a4a6e818ab7d633b94df/LICENSE) | 현재 editor 기반으로는 제외 |
| OpenCut classic | `cf5e79e919144200294fb9fed22a222592a0aeea` | [MIT](https://github.com/OpenCut-app/opencut-classic/blob/cf5e79e919144200294fb9fed22a222592a0aeea/LICENSE), archived | selective source port/adaptation |
| Opencast Editor | `1208afb64d9de0ab50b321f84f9dd2695780db87` | [Apache-2.0](https://github.com/opencast/editor/blob/1208afb64d9de0ab50b321f84f9dd2695780db87/LICENSE) | attributed behavioral adaptation |
| Supabase | `1c827c5cbb29cacc6e9052adff2e1659e3cb05fb` | [root Apache-2.0](https://github.com/supabase/supabase/blob/1c827c5cbb29cacc6e9052adff2e1659e3cb05fb/LICENSE) | reference only |
| Pretendard | `v1.3.9`, `5c41199ea0024a9e0b2cb31735265056e5472d76` | [SIL OFL 1.1](https://github.com/orioncactus/pretendard/blob/5c41199ea0024a9e0b2cb31735265056e5472d76/LICENSE) | local bundled Korean font |

실제 코드를 복사·변형하는 파일은 원본 repo, commit, path, license, 변경 내용을 `THIRD_PARTY_NOTICES.md`와 machine-readable source map에 남겨야 한다. shadcn generated source는 pinned registry path와 normalized file SHA를 기록한다. Pretendard Variable WOFF2는 upstream path `packages/pretendard/dist/web/variable/woff2/PretendardVariable.woff2`, SHA256 `9599f12fd42fc0bce1cd50b47a0c022e108d7aa64dd0d1bb0ed44f3282d900b4`로 고정한다. 상표·로고·브랜드 자산은 라이선스와 별개이므로 반입하지 않는다.

## 4. 프로젝트별 전수조사

### 4.1 shadcn-admin

가져올 가치가 높은 실제 경로는 다음과 같다.

- [`authenticated-layout.tsx`](https://github.com/satnaing/shadcn-admin/blob/e16c87f213a5ba5e45964e9b67c792105ec74d26/src/components/layout/authenticated-layout.tsx): `SidebarProvider + AppSidebar + SidebarInset`
- [`app-sidebar.tsx`](https://github.com/satnaing/shadcn-admin/blob/e16c87f213a5ba5e45964e9b67c792105ec74d26/src/components/layout/app-sidebar.tsx): header/content/footer/rail
- [`nav-group.tsx`](https://github.com/satnaing/shadcn-admin/blob/e16c87f213a5ba5e45964e9b67c792105ec74d26/src/components/layout/nav-group.tsx): 활성·중첩 메뉴
- [`header.tsx`](https://github.com/satnaing/shadcn-admin/blob/e16c87f213a5ba5e45964e9b67c792105ec74d26/src/components/layout/header.tsx): sticky header와 sidebar trigger
- [`main.tsx`](https://github.com/satnaing/shadcn-admin/blob/e16c87f213a5ba5e45964e9b67c792105ec74d26/src/components/layout/main.tsx): fixed/fluid content frame
- [`team-switcher.tsx`](https://github.com/satnaing/shadcn-admin/blob/e16c87f213a5ba5e45964e9b67c792105ec74d26/src/components/layout/team-switcher.tsx): `ProjectSwitcher` 외형
- [`settings`](https://github.com/satnaing/shadcn-admin/tree/e16c87f213a5ba5e45964e9b67c792105ec74d26/src/features/settings): desktop sidebar + mobile select

그러나 공식 README가 이 프로젝트를 starter template라고 보지 말라고 명시한다. auth store, Clerk partial auth, dashboard 샘플 데이터, route tree, Google Fonts는 가져오지 않는다. ProjectSwitcher는 VideoBox project API와 URL을 사용하도록 새로 연결한다.

### 4.2 shadcn/ui

shadcn/ui는 일반 component package가 아니라 CLI로 소스 코드를 배포하는 방식이다. VideoBox에 생성된 코드는 우리 코드가 된다. 다만 live registry의 현재 결과를 pinned commit으로 오해하면 안 되므로, 승인된 registry source path와 file SHA를 별도 lock에 기록하고 생성 결과의 normalized diff를 검증한다. [공식 소개](https://ui.shadcn.com/docs), [Sidebar 문서](https://ui.shadcn.com/docs/components/radix/sidebar)

초기 도입 대상은 다음으로 제한한다.

```text
button card input textarea dialog sheet dropdown-menu
sidebar empty badge tooltip skeleton tabs select
scroll-area separator sonner resizable
```

Tailwind 4.2.2의 Vite plugin은 Vite `^5.2` 이상을 허용하므로 현재 Vite 5.4를 유지할 수 있다. React/Vite/TypeScript 대규모 업그레이드를 UI 개편과 섞지 않는다.

공식 dashboard example은 작은 화면에서 실제 dashboard 대신 정적 이미지를 보여주는 구간이 있으므로 그대로 복사하지 않는다. canonical Sidebar의 mobile Sheet 동작을 사용한다.

### 4.3 OpenCut rewrite와 classic

최신 rewrite는 editor가 아직 없다. UI primitive도 shadcn/ui를 직접 받는 편이 출처가 더 명확하므로 현재 rewrite source를 VideoBox에 반입할 이유가 없다.

classic에는 실제 작업판이 있다.

```text
EditorHeader
└─ vertical resizable group
   ├─ horizontal resizable group
   │  ├─ AssetsPanel
   │  ├─ PreviewPanel
   │  └─ PropertiesPanel
   └─ Timeline
```

핵심 source:

- [editor page](https://github.com/OpenCut-app/opencut-classic/blob/cf5e79e919144200294fb9fed22a222592a0aeea/apps/web/src/app/editor/%5Bproject_id%5D/page.tsx)
- [asset panel](https://github.com/OpenCut-app/opencut-classic/tree/cf5e79e919144200294fb9fed22a222592a0aeea/apps/web/src/components/editor/panels/assets)
- [properties registry](https://github.com/OpenCut-app/opencut-classic/blob/cf5e79e919144200294fb9fed22a222592a0aeea/apps/web/src/components/editor/panels/properties/registry.tsx)
- [timeline components](https://github.com/OpenCut-app/opencut-classic/tree/cf5e79e919144200294fb9fed22a222592a0aeea/apps/web/src/timeline/components)
- [timeline controllers](https://github.com/OpenCut-app/opencut-classic/tree/cf5e79e919144200294fb9fed22a222592a0aeea/apps/web/src/timeline/controllers)
- [timeline snapping](https://github.com/OpenCut-app/opencut-classic/tree/cf5e79e919144200294fb9fed22a222592a0aeea/apps/web/src/timeline/snapping)
- [preview coordinates](https://github.com/OpenCut-app/opencut-classic/blob/cf5e79e919144200294fb9fed22a222592a0aeea/apps/web/src/preview/preview-coords.ts)

가져올 수 있는 것은 panel composition, asset tabs, inspector registry, pixel/ruler/zoom 계산, snapping·hit-test의 순수 부분이다. Timeline root와 manager는 각각 약 900줄 이상이며 EditorCore와 강하게 결합돼 있어 통째로 복사하지 않는다.

강제 제외:

- EditorCore singleton과 managers
- IndexedDB/OPFS project truth
- browser command history
- Rust/WASM compositor
- Mediabunny browser export
- Next.js/auth/Cloudflare 경로
- browser Whisper worker
- OpenCut branding

OpenCut의 `MediaTime`은 초당 120,000 tick을 사용하지만 VideoBox API는 seconds를 사용한다. 첫 단계에서는 서버 seconds를 canonical로 유지하고 UI geometry 변환을 한 모듈에 격리한다. frame-rate/timebase contract가 생기기 전에 OpenCut time type을 그대로 들여오지 않는다.

### 4.4 Opencast Editor

Opencast는 강의 영상의 cut/subtitle 편집기다. VideoBox의 다중 레이어 소셜 영상 편집기를 대신할 수는 없지만 대본·자막 중심 흐름은 매우 유용하다.

핵심 source:

- [`videoSlice.ts`](https://github.com/opencast/editor/blob/1208afb64d9de0ab50b321f84f9dd2695780db87/src/redux/videoSlice.ts): current time, cut, merge, deleted-range skip, zoom
- [`subtitleSlice.ts`](https://github.com/opencast/editor/blob/1208afb64d9de0ab50b321f84f9dd2695780db87/src/redux/subtitleSlice.ts): cue CRUD, sort, focus sync
- [`Timeline.tsx`](https://github.com/opencast/editor/blob/1208afb64d9de0ab50b321f84f9dd2695780db87/src/main/Timeline.tsx): scrubber, cut marks, waveform
- [`SubtitleTimeline.tsx`](https://github.com/opencast/editor/blob/1208afb64d9de0ab50b321f84f9dd2695780db87/src/main/SubtitleTimeline.tsx): cue drag/resize와 pixel↔time
- [`SubtitleEditor.tsx`](https://github.com/opencast/editor/blob/1208afb64d9de0ab50b321f84f9dd2695780db87/src/main/SubtitleEditor.tsx): list + video + subtitle timeline
- [`globalKeys.ts`](https://github.com/opencast/editor/blob/1208afb64d9de0ab50b321f84f9dd2695780db87/src/globalKeys.ts): shortcut registry

이번 계획에서 채택할 동작은 current-time clamp, active segment lookup, next playable time, time-to-pixel, list/player/timeline focus sync다. Opencast의 cue drag/resize source는 조사했지만 VideoBox에는 독립 caption timing authority가 없으므로 후속 모델/API가 생기기 전에는 이식하지 않는다. 채택 동작은 Redux mutation을 제거한 pure function과 VideoBox command adapter로 재작성한다.

제외:

- Redux client-authoritative state
- MUI/Emotion design system
- `/edit.json` 전체 snapshot POST
- 개인 fork `react-player`
- 전체 미디어를 브라우저에서 decode하는 waveform
- 접근성 없는 drag handle DOM

waveform은 FFmpeg로 peaks artifact를 생성·cache하고 브라우저는 SVG/canvas로 표시한다. pointer move 중에는 임시 상태만 보여주고 pointer-up 한 번에 `expected_revision`과 함께 서버 mutation을 보낸다. 자막은 현재 backend에서 narration segment metadata이므로 독립 cue timing은 이번 범위에서 제외하고 text/style과 segment-linked selection만 adaptation한다.

### 4.5 Supabase Studio

가져올 것은 제품 구조다.

- [`LayoutHeader`](https://github.com/supabase/supabase/blob/1c827c5cbb29cacc6e9052adff2e1659e3cb05fb/apps/studio/components/layouts/Navigation/LayoutHeader/LayoutHeader.tsx): 프로젝트 계층과 현재 위치
- [`MobileNavigationBar`](https://github.com/supabase/supabase/blob/1c827c5cbb29cacc6e9052adff2e1659e3cb05fb/apps/studio/components/layouts/Navigation/NavigationBar/MobileNavigationBar.tsx): mobile bar/sheet/selector
- [`ProjectLayout`](https://github.com/supabase/supabase/blob/1c827c5cbb29cacc6e9052adff2e1659e3cb05fb/apps/studio/components/layouts/ProjectLayout/index.tsx): product menu + main panel
- [`SettingsLayout`](https://github.com/supabase/supabase/blob/1c827c5cbb29cacc6e9052adff2e1659e3cb05fb/apps/studio/components/layouts/ProjectSettingsLayout/SettingsLayout.tsx): 설정 IA
- [`EmptyStates`](https://github.com/supabase/supabase/blob/1c827c5cbb29cacc6e9052adff2e1659e3cb05fb/apps/studio/components/interfaces/Home/ProjectList/EmptyStates.tsx): 제목 + 한 문장 + CTA

Studio는 Next와 TanStack/Vite 전환이 공존하고 내부 workspace package, data hook, feature flag, telemetry에 깊게 결합돼 있다. root Apache-2.0과 `packages/ui`의 package metadata도 provenance 검토가 더 필요하다. 따라서 layout source를 복사하지 않고 IA와 interaction만 참고한다.

## 5. 최종 도입 매트릭스

| 영역 | 직접 source port | adapter/attributed adaptation | reference only | 제외 |
|---|---|---|---|---|
| 앱 셸 | shadcn-admin shell composition | VideoBox router/project API 연결 | Supabase hierarchy | auth/demo data |
| UI primitive | shadcn/ui CLI source | VideoBox variants/tokens | dashboard block | 외부 font/CDN |
| 편집 배치 | OpenCut classic panel ratios/resizer | VideoBox Workbench | current OpenCut roadmap | current rewrite dependency |
| 자산함 | asset tabs/card skeleton | VideoBox preview API/drag commands | OpenCut grid | browser-owned File truth |
| Inspector | registry pattern | supported VideoBox fields | OpenCut property grouping | unsupported effects/keyframes |
| Timeline | ruler/pixel/zoom pure math | fixed tracks, drag/trim/snap adapters | OpenCut visuals | EditorCore/command history |
| Preview | coordinate/zoom/hit-test math | server media player + overlay | OpenCut viewport | browser renderer/export |
| 대본·자막 | 없음 | Opencast cue/list/time math | Opencast layout | Redux/MUI/player fork |
| Waveform | 없음 | FFmpeg peaks + local render | Opencast/OpenCut visuals | full browser decode |
| SaaS settings | 없음 | local/cloud capability slots | Supabase IA | fake billing/auth pages |

## 6. 목표 사용자 구조

```text
AppShell
├─ Sidebar
│  ├─ ProjectSwitcher
│  ├─ 홈
│  ├─ 새 영상 만들기
│  ├─ 미디어
│  ├─ 편집
│  ├─ 출력
│  └─ 설정
├─ Topbar
│  ├─ 프로젝트 / 현재 화면
│  ├─ 저장·job 상태
│  └─ 현재 화면의 주요 행동 1개
└─ EditorWorkbench
   ├─ 좌측: 자산 / 대본 / 자막
   ├─ 중앙: 영상 미리보기
   ├─ 우측: 루미 / 추천 / 속성
   └─ 하단: narration / B-roll / BGM / SFX / overlay timeline
```

루미는 모든 페이지를 덮는 챗봇이 아니라 편집 문맥 안에서 질문·추천·적용을 돕는 우측 패널이어야 한다. 프로젝트 생성 전에는 대본 인터뷰를 진행하고, 편집기에서는 선택 구간과 proposal revision을 아는 assistant로 전환한다.

## 7. 핵심 아키텍처 결정

1. editing-session과 revision은 계속 유일한 편집 truth다.
2. OpenCut/Opencast 컴포넌트는 `EditorViewModel`과 `EditorCommandPort`만 본다.
3. drag 중 local preview state와 server committed state를 분리한다.
4. preview, FFmpeg final, PyCapCut draft는 같은 source controls와 provenance를 소비한다.
5. App route는 TanStack Router code-based route tree로 분리하되 TanStack router plugin, Query, Zustand, Redux는 이 작업의 필수 조건이 아니다.
6. local mode에서는 account/team/billing을 보이지 않는다. SaaS mode에서만 capability slot을 연다.
7. Pretendard는 로컬 번들로만 사용하고 외부 runtime font 요청을 금지한다.
8. 기존 화면은 route 단위 parity가 확인될 때까지 `LegacyWorkspacePage`로 보존한다.
9. browser clip audition은 선택 source 하나를 확인하는 기능이고, 실제 편집본 preview는 current revision을 기존 FFmpeg final composition 경로로 만든 exact proxy artifact다.
10. 핵심 수직 Slice는 shell 직후 `대본→루미 인터뷰→자산 점검→한 번 승인→atomic real draft→editor/output handoff`를 먼저 검증한다.

## 8. 가장 큰 리스크

- Tailwind preflight와 기존 global CSS의 충돌
- monolithic App을 shell과 동시에 분해할 때 생기는 회귀
- OpenCut의 120,000-tick time과 VideoBox seconds 혼용
- 실제 media playback manifest와 Range contract 부족
- 긴 영상 waveform/수천 cue 성능
- upstream drag UI의 접근성 공백
- archived classic source의 낮은 direct test coverage
- local 제품 화면에 아직 없는 SaaS account/billing을 성급히 노출하는 문제
- 빈 editing session 또는 proposal 목록을 자동 편집 초안으로 잘못 완료 처리하는 문제
- 단일 `<video>` source playback을 B-roll/BGM/SFX가 합성된 실제 preview로 오인하는 문제

완화책은 legacy CSS 격리, route-by-route migration, pure geometry TDD, backend playback contract 선행, keyboard/a11y 테스트, source provenance verifier다.

## 9. 최종 판단

이번 재분석으로 기존의 “OpenCut은 후속 판단” gate는 열 수 있다. 그러나 gate를 연다는 뜻은 OpenCut을 dependency로 넣는 것이 아니다. **시각 prototype을 먼저 승인하고, shadcn 기반 VideoBox shell과 얇은 script-first 수직 Slice를 만든 뒤, OpenCut classic과 Opencast의 검증 가능한 상호작용만 VideoBox 도메인 위에 이식하는 것**이 최종 결정이다.

구현은 별도 계획서 `docs/superpowers/plans/2026-07-17-videobox-oss-dashboard-editor-adoption.md`의 22개 Task로 수행한다. 독립 계획/UX/source→runtime 리뷰에서 실제 합성 preview, atomic real draft, caption timing authority, network/preflight/provenance 재현성 문제를 발견해 초안의 17개 Task를 실행 전에 재배치·분할했다.

수정본은 다시 세 방향으로 검토했다. exact preview artifact의 Range/H.264 faststart와 generation fencing, actual composited draft playback, narration/silent/gap-only output boundary, Playwright 하네스 순서, 22개 Task의 focused RED/GREEN command matrix까지 보강한 뒤 미폐쇄 P0/P1은 0건으로 판정됐다. 이 판정은 구현 결과가 아니라 실행 계획의 정합성 검토 결과다.
