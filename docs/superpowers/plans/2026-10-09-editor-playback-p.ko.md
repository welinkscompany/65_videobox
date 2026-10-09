# 계획 P — 편집기 재생 수리(매끄러운 재생·스페이스·재생 빠르기·단축키) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> 실행 모델은 **Claude Sonnet**. Task 하나씩, 앞 Task 커밋 위에서. 이 문서의 Global Constraints가 모든 Task에 걸린다.

**Goal:** 대표님이 편집기에서 스페이스를 누르면 영상이 **실제 속도로, 흔들림 없이** 재생되고, 재생 머리가 매끄럽게 흐르고, 미리보기 밖을 눌러도 재생 위치가 0초로 튀지 않으며, 짧은 장면은 **보는 속도만** 0.25~2배로 늦추거나 빠르게(완성 영상은 그대로) 단추와 J/K/L 키로 쉽게 바꿀 수 있고, 그 속도가 다음에 열어도 그대로다.

**Architecture:** 새 재생기를 들이지 않는다. 결함은 **우리 코드가 재생기를 붙잡는 방식**에 있다(맨 `<video>`는 같은 파일을 30fps·1.00배로 완벽하게 튼다 — 실측). 고치는 곳은 넷이다. (1) `preview-stage.tsx`의 "재생 위치 → 재생기 옮기기" 효과가 **자기가 올려보낸 위치를 되받아 되감는 고리**를 끊는다. (2) 재생 중 화면(재생 머리·시간 글자)은 React 상태 대신 작은 **재생 시계**(`playbackClock.ts`, rAF가 재생기 시각을 읽어 알림)를 구독해 DOM을 직접 고친다 — React 상태는 지금처럼 `timeupdate` 빈도로만 바뀐다. (3) 키보드: 스페이스 이중 처리·초점 이탈 시 0초 되돌림을 고치고, J/K/L·화살표를 같은 문지기 함수 하나(`playbackShortcuts.ts`)로 받는다. (4) 미리보기 인코드에 1초 키프레임(`-g fps`)을 넣어 탐색을 4~7배 빠르게.

**Tech Stack:** React 19, vitest + Testing Library(jsdom), Playwright 1.61(번들 Chromium 149 — H.264·`requestVideoFrameCallback` 지원 실측), 진짜 백엔드 e2e 묶음(`npm run test:e2e:real-flow`, 계획 H Task 1), FastAPI + pytest(`.venv`), ffmpeg/ffprobe.

**Spec:** 실측 보고 `.superpowers/sdd/playback-diagnosis-2026-10-09.md`(원자료·스크립트 `.superpowers/sdd/playback-diagnosis-2026-10-09/`). 대표님 제보(2026-10-08 실사용): "스페이스바로 재생돼야 한다 / 초 단위로 만들면 너무 빨리 재생 — 더 느리게, 단축키로 쉽게 / 1초 단위로 지나가고 화면이 흔들리고 제대로 재생이 안 되고 너무 불안정".

---

## 실측 기록 (2026-10-09, 컨테이너 `127.0.0.1:5173`, 실제 Chrome 154 headless, 1440×900, 742e1924 20초 재생 × 6구간)

| 원인(순위) | 확정 근거 | 숫자 |
|---|---|---|
| 1. **재생 중 미리보기가 자기를 되감는다** | `preview-stage.tsx` 효과 `}, [mode, onPlaybackTimeChange, playbackSec]);` — `timeupdate`가 올린 시각 t가 `playbackSec`로 돌아오면 그 사이 재생기는 t+2~19ms라 `Math.abs(media.currentTime - mediaSeconds) > 0.001` → `media.currentTime = mediaSeconds`(뒤로). `onPlaybackTimeChange`가 매 렌더 새 함수라 무관한 렌더에도 돈다. 번들 호출 자리·setter 스택으로 확인. **이 쓰기만 막으면 맨 `<video>`와 같아진다** | 재생 중 앱의 `currentTime` 쓰기 **67~74회/20초**(전부 뒤로) · 영상 시각 뒤로 **52~59회** · 실제 진행 **0.62~0.70배** · 그린 프레임 24.9~27.5fps · 해독/그림 **3.1~6.6배** → 막으면 0회·0회·**1.00배**·30fps·1.0배 |
| 2. 재생 머리·시간 글자가 0.3~0.4초마다 뛴다 | 재생 머리 `style={{ left: \`${playheadX}px\` }}`가 React 상태(`timeupdate` 빈도)만 따른다 | 갱신 간격 p50 **300ms**·p95 400ms·최대 507ms. 첫 배율 0907 **153.5px/초**(눈금 1초) → 한 번에 ≈46px, 742 19.8px/초 → ≈6px. 재생 3초 뒤 머리가 영상보다 0.2초 뒤 |
| 3. 스페이스가 안 먹는 자리 | 영상 그림을 누르면 초점이 `미리보기` 판(`tabIndex={0}`)에 가고 `onStageKeyDown`과 창 처리기가 **둘 다** 뒤집어 상쇄 | 그림 클릭 → 스페이스 1회·2회 모두 정지 그대로. 아무것도 안 누름·재생 단추·타임라인 안 → 됨. 타임라인 밖 단추(음소거 등) → 그 단추가 눌림(의도) |
| 4. 미리보기 밖을 누르면 정지 + **0초로** | `onStageBlur` → `stopActiveMedia()`(=`pause()` + `currentTime = 0`). 창 `scroll`도 같은 함수 | 재생 중 타임라인 제목 클릭 → 영상 2.2초 → **0초·정지**, 재생 머리도 0. 그 뒤 타임라인 → 화살표 한 번에 0 → 1.6초로 뜀(타임라인 상태는 옛 위치) |
| 5. 키프레임 8.3초(증폭) | 미리보기 인코드에 `-g` 없음 → libx264 기본 keyint 250 | 742 키프레임 19개, 간격 중앙 7.5·최대 8.33초. 탐색 p50/p95 **18/48ms → `-g 30` 4/7ms**(크기 +10.7%). 되감기 고리 흉내에서 GOP만 줄이면 0.65 → 0.80배(고리를 없애야 1.00) |
| 6. 재생 빠르기 없음 | `grep -rn playbackRate apps/web/src` 0건, J/K/L 처리 없음 | `L` → 정지 그대로, `playbackRate` 1 |

배제: 무거운 다시 그리기(긴 작업 0건, CPU 6~10%, 커밋 7/초), 폴링(재생 중 요청 0~1), 파일 이상(고정 30/1, 단조 DTS, faststart, 206 범위 정상).

### 대표님 말의 해석 (이 계획의 기준)

- "흔들리고·제대로 안 되고·불안정" = 원인 1 + 4. "1초 단위로 지나간다" = 원인 2(+1의 멈칫) — 대표님 화면의 멈칫 길이는 **못 쟀다**.
- "더 느리게, 단축키로" = **보는 속도**(완성 영상은 그대로)로 읽었다. 기본은 **실제 속도 1배**가 맞다 — 미리보기 속도가 다르면 컷 길이·말 빠르기 판단이 틀린다. 대신 고른 빠르기를 **기억**해서, 0.5배로 바꿔 두면 다음에 열어도 0.5배로 시작한다(= "기본을 느리게"를 대표님이 한 번의 선택으로 얻는다).
- 오른쪽 `편집 항목`의 `속도` 칸(장면 속도 — 바꾸면 완성 영상 길이가 바뀜, 2026-09-04 결정)과 **헷갈리지 않게** 이름을 `재생 빠르기`로 하고 "영상은 바뀌지 않아요"를 안내한다. 남는 질문은 owner 결정 1.

---

## 다른 계획과의 경계

| 계획 | 관계 |
|---|---|
| H(편집기 핵심 수리, `2026-10-08-editor-core-repair-h.ko.md`) | H Task 3의 `pinnedSegmentIdRef`·`resolvePlaybackSelection`·`staleSeekBaselineRef`(2026-09-20)를 **건드리지 않는다**. P Task 1은 그 옆 효과 하나의 조건만 바꾼다. H Review Focus 1("재생이 고른 장면 끝을 지나면 다음 장면")은 P Task 1·2 뒤에도 돌아야 한다 — 같은 시험을 다시 돈다 |
| I(디자인 시스템) | P가 새로 그리는 것(재생 빠르기 고르기·`단축키` 안내)은 shadcn `NativeSelect`·`Button`과 기존 토큰만 쓴다. 크기는 I가 바꾼다 |
| B–F(유진) | P는 유진 코드를 안 고친다. 배선 판단은 owner 결정 2 |
| 실시간 타임라인 재생(H "제외") | P도 제외. P는 **만들어 둔 미리보기 mp4**를 매끄럽게 트는 것까지 |

### 같이 고치는 파일 (앵커는 줄 번호가 아니라 **문자열**)

| 파일 | P Task | 다른 계획 |
|---|---|---|
| `apps/web/src/features/editor/preview/preview-stage.tsx` | 1, 2, 3, 4, 5 | H(끝남), G |
| `apps/web/src/features/editor/preview/preview-stage.test.tsx` | 1, 2, 3, 4, 5 | — |
| `apps/web/src/features/editor/timeline/TimelineDock.tsx` | 2, 4 | H, G, I |
| `apps/web/src/features/editor/workbench/EditorWorkbench.tsx` | 2 | H, B–F |
| `apps/web/src/styles/editor-workbench.css` | 4, 5 | H, I |
| `packages/core-engine/src/videobox_core_engine/ffmpeg_final_renderer.py` | 6 | — |
| `scripts/e2e_editor_fixture.py`, `scripts/e2e_real_editor_api.py`, `apps/web/e2e-real/support/realFlow.mjs` | 0 | H |

---

## Global Constraints

- 최상위 지침은 `CLAUDE.md`. 메인 체크아웃 `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`(브랜치 `main`). Task 시작마다 `git status --short`(`?? .anchor/`만), `git log -1`이 앞 Task 커밋인지. 아니면 멈추고 보고.
- **앵커는 문자열로 찾는다.** 인용한 옛 코드가 그대로 있으면 진행, 없으면 **멈추고 보고**(짐작해서 고치지 않는다).
- **RED를 실제로 본다.** RED 시험이 처음부터 통과하면 멈추고 보고. RED/GREEN 단계에서는 그 시험 하나만(`CLAUDE.md` §3).
- 명령: 웹 `cd apps/web && npx vitest run <파일> -t "<시험 이름>"`(저장소 루트에서 돌리면 jsdom이 깨진다), 타입 `cd apps/web && npx tsc --noEmit`, 빌드 `npm --prefix apps/web run build`, 백엔드 `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider <파일>::<시험>`(맨 `pytest` 금지), 진짜 백엔드 e2e `cd apps/web && npm run test:e2e:real-flow -- e2e-real/<파일>`, 가짜 API e2e `cd apps/web && npm run test:e2e`(stop hook이 도는 것 — **48건 통과 유지**, 포트 4173 점거자 주의(기억 메모), 끝의 `unexpected PNG: product-shell-mobile-menu-open.png` exit 1은 무관).
- **팔레트는 바꾸지 않는다**(`2026-08-29`). 새 CSS는 기존 토큰(`--vb-*`, `--border`, `--vb-accent` …)만. 새 색 값 금지.
- **없는 기능의 단추는 만들지 않는다**(`2026-08-30`). 거꾸로 재생(J로 뒤로 감기)은 만들지 않는다 — 브라우저 `<video>`가 음수 빠르기를 못 튼다. J는 "느리게"다.
- 화면 문구 §10.13: 명사형 이름표 + 짧은 해요체. `provider`·`runtime`·`job`·`revision`·`pipeline` 금지, 영어 단어 금지. 키 이름은 `스페이스바`·`J 키`처럼 쓴다. UI Task마다 `cd apps/web && npx vitest run src/user-copy-policy.test.ts`.
- 날 것 `<button data-native-control=…>`를 **새로 만들지 않는다**(`task22-parity-owners.test.ts` 허용 목록). 새 조작은 `@/components/ui`의 `NativeSelect`·`Button`으로. 그 시험이 바뀌면 무엇을 잘못 썼는지 보고 고친다.
- **대표님 프로젝트는 읽기만.** 실기 확인은 열기·재생·일시정지·탐색·재생 빠르기까지(편집·되돌리기·트랙 잠금·미리보기 새로 만들기 금지). 미리보기가 낡은 프로젝트(측정 시점 0907)는 재생 확인 대상에서 빼고 보고에 적는다.
- 재생 측정 숫자는 **기계가 바쁠 수 있다**(대표님의 다른 python 작업). 판정은 같은 측정 3회의 **중앙값**, 결정적인 값(되감기 0회·뒤로 0회)은 매회. 실패하면 한 번 다시 재고, 두 번 다 실패면 결함으로 본다.
- 내장 브라우저 창은 영상·rAF를 안 그린다(기억 메모 2026-09-04) — 재생 확인은 Playwright(번들 Chromium 또는 `channel:"chrome"`).
- 이미 알려진 실패(고치려 들지 마라): `editor-workbench.test.tsx` "gives the material dock back the same way, without needing a second click", `tests/test_owner_ready_script.py::test_smoke_timeout_kills_the_child_tree_and_returns_bounded_failure`.
- 커밋은 Task마다, 한국어, 끝줄 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. 확인 명령과 커밋·푸시를 한 명령에 묶지 않는다. 푸시는 Task 7에서 `git push origin main`(강제 금지). 권한이 막으면 우회하지 말고 owner에게 요청.
- **검증 넷(Task마다 고정):** 갭(이 Task Step 대조, **안 한 것**을 적는다) · 역방향(진짜 백엔드 e2e 또는 Task 7 실기 — 실제 Chromium) · 동작(fps·배속·ms·횟수로 잰다) · 배선(`grep`으로 화면이 실제로 부르는 자리를 센다).

## Review Focus

행복한 경로 시험이 놓치기 쉬운 실제 입력 다섯. 각각 맡은 Task에 시험을 넣었다.

1. **재생 중에 타임라인을 눌러 다른 자리로 옮길 때** — 되감기 고리를 끊다가 "바깥에서 온 진짜 탐색"까지 무시하면 클릭이 안 먹는다 → Task 1 시험 "재생 중 바깥에서 옮기라고 하면 옮긴다".
2. **재생이 고른 장면 끝을 넘어 다음 장면으로 갈 때**(H Review Focus 1) — 매끄러운 재생 머리를 React 밖으로 뺐어도 장면 고르기는 계속 따라가야 한다 → Task 2 Step 4에서 H의 `resolvePlaybackSelection` 시험과 진짜 백엔드 `clip-selection.spec.mjs`를 다시 돈다.
3. **미리보기가 새로 만들어져 재생기 소스가 바뀔 때·원본 보기로 갔다 돌아올 때** — 브라우저는 새 소스를 열 때 `playbackRate`를 `defaultPlaybackRate`로 되돌린다 → Task 4 시험 "소스가 바뀌어도 고른 빠르기".
4. **스페이스를 꾹 누르고 있을 때(키 반복)·한글 입력 중(조합)** — 반복 이벤트마다 뒤집히면 깜빡이며 멈춘다 → Task 3 시험 "`repeat`·`isComposing`은 무시".
5. **창이 좁아 재생 머리가 보이는 구간 끝을 지날 때** — 재생 머리를 DOM으로 직접 움직이면 React 상태가 따라오기 전(최대 ≈270ms) 머리가 칸 밖으로 나간다 → Task 2 시험 "시계가 보이는 구간을 넘으면 그 자리로 넘긴다".

---

## 재사용 게이트 (`implementation-plan.ko.md` §8.1)

| 후보 | 판단 | 반영 단위 |
|---|---|---|
| 브라우저 `<video>` 자체 재생(`play/pause/playbackRate/defaultPlaybackRate`) | **adopt as-is** — 맨 재생 30fps·1.00배 실측 | 우리는 붙잡지만 않는다(Task 1) |
| `requestVideoFrameCallback` | **adopt**(측정 전용) | e2e 측정 도우미. 화면 재생 머리는 `requestAnimationFrame`(rVFC가 없는 브라우저도 돈다) |
| TimelineDock의 `reportedPlayheadRef` "내가 올려보낸 값이면 다시 옮기지 않는다" 패턴 | **partial port**(같은 생각을 미리보기에) | `lastReportedTimelineSecRef`(Task 1) |
| `timelineZoomShortcuts.ts`·`cutShortcuts.ts`의 "순수 함수가 키 → 명령" 모양 | **adopt pattern** | `playbackShortcuts.ts`(Task 3·4) |
| `isEditableTarget`(TimelineDock) | **partial**(편집 칸 판정만) | `playbackShortcuts.ts` 안에 키 문지기 하나로 모은다 — 세 번째 판정 함수를 만들지 않도록 기존 둘(preview-stage 스페이스·TimelineDock)도 이것을 부르게 한다 |
| `@/components/ui/native-select`·`button` | **adopt as-is** | 재생 빠르기·단축키 안내 |
| `editorUiState` 저장(프로젝트별) | **exclude** — 재생 빠르기는 **사람별 취향**이라 프로젝트를 넘어 같아야 한다 | 별도 localStorage 키 하나(Task 4) |
| Video.js·Plyr·media-chrome 같은 재생기 부품 | **exclude** — 결함은 재생기가 아니라 우리 고리. 새 의존성·UI 구조 반입 금지(§8.1) | — |
| 계획 H의 진짜 백엔드 e2e 하네스(`e2e-real`, 고정 시험 프로젝트, `withPreviewPlayer` 경로 가로채기) | **adopt + 확장** | 30초 고정 프로젝트 + 범위 요청을 받는 mp4 가로채기(Task 0) |

---

## 파일 구조 (새로 만드는 것)

| 파일 | 책임 |
|---|---|
| `apps/web/e2e-real/support/playbackProbe.mjs` | 재생 측정 도우미(rVFC·되감기 감시·longtask·커밋·재생 머리 간격) — 재사용 |
| `apps/web/e2e-real/playback-smoothness.spec.mjs` | 재생 매끄러움·스페이스·빠르기 진짜 Chromium 시험 |
| `apps/web/src/features/editor/preview/playbackClock.ts` (+`.test.ts`) | 재생 시각 알림(구독형, React 상태 아님) |
| `apps/web/src/features/editor/preview/playbackShortcuts.ts` (+`.test.ts`) | 키 → 재생 명령(스페이스·J/K/L·화살표), 문지기 하나 |
| `apps/web/src/features/editor/preview/playbackRate.ts` (+`.test.ts`) | 빠르기 단계·읽기/쓰기(localStorage, try/catch)·재생기에 걸기 |

---

### Task 0: 착수 확인 + 재생 측정 하네스(지금 코드에서 빨갛게) — 약 3.5시간

**왜 먼저인가:** 이번 결함은 단위 시험(jsdom — 영상이 실제로 안 흐른다)으로는 영영 안 보인다. 진짜 Chromium에서 프레임을 세는 시험이 먼저 있어야 Task 1~4의 "고쳤다"가 숫자가 된다.

**Files:**
- Modify: `scripts/e2e_editor_fixture.py` — 앵커 `def seed_editor_fixtures(*, projects_root: Path, media_dir: Path) -> dict[str, dict[str, str]]:`, `        "no_narration": _seed_no_narration(store, media),`
- Modify: `scripts/e2e_real_editor_api.py` — 앵커 `json.dumps({"clean": _camel(ids["clean"]), "duplicatedOverlays": _camel(ids["duplicated_overlays"]), "noNarration": _camel(ids["no_narration"])}, indent=2),`
- Modify: `tests/test_e2e_editor_fixture.py`(시험 하나 추가)
- Modify: `apps/web/e2e-real/support/realFlow.mjs` — 앵커 `/** @returns {{ clean: Fixture, duplicatedOverlays: Fixture, noNarration: Fixture }} Fixture = { projectId, sessionId, timelineId } */`
- Create: `apps/web/e2e-real/support/playbackProbe.mjs`, `apps/web/e2e-real/playback-smoothness.spec.mjs`

**Interfaces:**
- Produces(Python): 상수 `PLAYBACK_SCENES: tuple[tuple[str, float, float], ...]`(30초, 7.5초 장면 넷), `seed_editor_fixtures` 반환에 `"playback"` 키.
- Produces(JS): `readFixture().playback`; `withLongPreview(page, mp4Path)` — 매니페스트 `exact_preview`를 `succeeded`(0~30초)로 얹고 `**/__e2e/long-preview.mp4`를 **범위 요청(206)까지** 내준다; `installPlaybackProbe(page)`(addInitScript); `measurePlayback(page, { startSec, seconds, start: "space" | "button" }) → PlaybackSample`; `median(values)`.
- `PlaybackSample = { appSeeksWhilePlaying, mediaTimeBackwardSteps, effectiveRate, rvfcFps, rvfcGapMax, decodedPerPresented, longTasksOver100, playheadGapP95, readoutGapP95, reactCommitsPerSec }`.

- [ ] **Step 0: 착수 상태** — `git status --short` → `?? .anchor/`만. `git log --oneline -3`. `git worktree list`. `git diff --check` → 없음. 진단 보고 `.superpowers/sdd/playback-diagnosis-2026-10-09.md`를 읽는다(숫자의 출처).

- [ ] **Step 1: 30초 고정 프로젝트(RED→GREEN)** — `tests/test_e2e_editor_fixture.py` 끝에:

```python
def test_playback_fixture_is_thirty_seconds_in_four_scenes(tmp_path: Path) -> None:
    """재생 매끄러움 시험(계획 P Task 0)은 20초 넘게 틀 수 있는 편집본이 있어야 잰다."""
    from scripts.e2e_editor_fixture import PLAYBACK_SCENES
    ids = seed_editor_fixtures(projects_root=tmp_path / "projects", media_dir=tmp_path / "media")
    store = LocalProjectStore(tmp_path / "projects")
    session = store.get_editing_session(project_id=ids["playback"]["project_id"], session_id=ids["playback"]["session_id"])
    assert [(s["segment_id"], s["start_sec"], s["end_sec"]) for s in session["segments"]] == list(PLAYBACK_SCENES)
    assert PLAYBACK_SCENES[-1][2] == 30.0
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_e2e_editor_fixture.py::test_playback_fixture_is_thirty_seconds_in_four_scenes` → FAIL(`ImportError: PLAYBACK_SCENES`). 그 다음 `scripts/e2e_editor_fixture.py`에 `_seed_clean`을 그대로 본뜬 `_seed_playback(store, media)`: 내레이션은 `_make_media`에 `narration-30.wav`(`sine=frequency=330:duration=30`)를 하나 더 만들어 쓰고, 장면 넷 `("scene-1", 0.0, 7.5) … ("scene-4", 22.5, 30.0)`, 캡션 `"재생 시험 1"`~`"재생 시험 4"`, 오버레이·B-roll 없음. 반환 dict에 `"playback": _seed_playback(store, media)`. `e2e_real_editor_api.py`의 `json.dumps({...})`에 `"playback": _camel(ids["playback"])`. → GREEN. 같은 파일 다른 시험도 한 번 돈다(시드 모양 회귀).

- [ ] **Step 2: 측정 도우미** — `apps/web/e2e-real/support/playbackProbe.mjs`. 진단 스크립트 `.superpowers/sdd/playback-diagnosis-2026-10-09/scripts/measure-playback.mjs`의 `INIT`·`measureOne`을 **옮겨 다듬는다**(새로 발명하지 않는다). 지켜야 할 것:
  - `installPlaybackProbe(page)`: `page.addInitScript`로 `HTMLMediaElement.prototype.currentTime` setter를 감싸 `{ t, to, from, paused, harness }`를 쌓는다(시험이 스스로 옮길 때는 `window.__pb.harness = true`). React DevTools 훅 흉내(`__REACT_DEVTOOLS_GLOBAL_HOOK__`의 `onCommitFiberRoot`로 커밋 수). `PerformanceObserver({ type: "longtask" })`.
  - `measurePlayback`: 시작 위치는 `harness` 표시 아래 `video.currentTime = startSec` → `seeked` 기다림 → 1.5초 쉼 → 카운터 초기화 → rVFC 고리(`now`, `metadata.mediaTime`) + `getVideoPlaybackQuality()` 시작값 → **재생 머리 간격은 rAF마다** `[data-testid='timeline-playhead']`의 `getBoundingClientRect().left`가 바뀐 시각을 모은다(100ms 표본으로는 100ms 아래를 못 잰다) → 시간 글자(`.vb-preview-stage__playback output`)도 rAF마다 `textContent` 변화 시각 → `start === "space"`면 `document.activeElement.blur()` 후 `page.keyboard.press("Space")`, 아니면 `재생 또는 일시정지` 단추 → `seconds`초 → 모은다 → `harness` 아래 `pause()`.
  - 계산: `effectiveRate = (마지막 mediaTime − 처음) ÷ (마지막 now − 처음)/1000`, `mediaTimeBackwardSteps` = 앞보다 1ms 넘게 작은 mediaTime 수, `decodedPerPresented = Δ totalVideoFrames ÷ rVFC 수`, `appSeeksWhilePlaying` = `!paused && !harness`인 setter 기록 수, 간격들은 p95(정렬 후 `floor(0.95·n)`).
  - `withLongPreview(page, mp4Path)`: `clip-selection.spec.mjs`의 `withPreviewPlayer`와 같은 모양으로 매니페스트에 `exact_preview = { status: "current", url: "/__e2e/long-preview.mp4", …, timeline_start_sec: 0, timeline_end_sec: body.output.duration_sec, artifact_revision: 1 }`를 얹는다. **mp4 경로는 `range` 머리를 읽어** `bytes=a-b`면 `status: 206`, `headers: { "content-range": \`bytes ${a}-${b}/${size}\`, "accept-ranges": "bytes", "content-type": "video/mp4" }`, `body: buffer.subarray(a, b + 1)`로, 없으면 200 전체(+`accept-ranges`). 범위 없이 200만 주면 탐색이 실제와 다르게 돈다.

- [ ] **Step 3: 시험 영상 만들기** — 스펙 `test.beforeAll`에서 `test-results/long-preview.mp4`가 없을 때만 ffmpeg로 만든다(제품 미리보기와 같은 모양 — 크기 720×404, 30fps, libx264 기본 keyint, `-bf 0`, yuv420p, faststart, aac):
  `ffmpeg -y -v error -f lavfi -i testsrc2=s=720x404:r=30:d=30 -f lavfi -i sine=frequency=440:duration=30 -c:v libx264 -bf 0 -pix_fmt yuv420p -c:a aac -shortest -movflags +faststart test-results/long-preview.mp4`(`child_process.execFileSync`). ffmpeg가 없으면 `test.skip(true, "ffmpeg가 있어야 시험 영상을 만든다")`.

- [ ] **Step 4: 첫 시험(RED)** — `apps/web/e2e-real/playback-smoothness.spec.mjs`:

```js
import { expect, test } from "@playwright/test";
import { openEditor, readFixture } from "./support/realFlow.mjs";
import { installPlaybackProbe, measurePlayback, median, withLongPreview, ensureLongPreviewMp4 } from "./support/playbackProbe.mjs";

// 2026-10-09 실측(.superpowers/sdd/playback-diagnosis-2026-10-09.md): 재생 중 미리보기가 자기를 20초에 67~74번 되감아
// 실제 0.62~0.70배로 흔들리며 돌았다. 맨 <video>는 같은 파일을 30fps·1.00배로 튼다.
test.describe.configure({ mode: "serial" });
test.beforeAll(() => ensureLongPreviewMp4());

test("1배로 틀면 미리보기가 스스로 되감지 않고 실제 속도로 흐른다", async ({ page }) => {
  test.setTimeout(240_000);
  await installPlaybackProbe(page);
  await withLongPreview(page);
  await openEditor(page, readFixture().playback);
  await expect(page.getByLabel("편집본 미리보기")).toBeVisible({ timeout: 90_000 });
  const runs = [];
  for (const startSec of [0, 8, 17]) runs.push(await measurePlayback(page, { startSec, seconds: 10, start: "button" }));
  console.log("PLAYBACK_1X", JSON.stringify(runs));
  for (const run of runs) {
    expect(run.appSeeksWhilePlaying).toBe(0);          // 실측 고장 67~74/20초, 고친 뒤 0
    expect(run.mediaTimeBackwardSteps).toBe(0);         // 실측 고장 52~59/20초
  }
  expect(median(runs.map((r) => r.effectiveRate))).toBeGreaterThanOrEqual(0.93);   // 고장 0.62~0.70, 정상 1.00
  expect(median(runs.map((r) => r.decodedPerPresented))).toBeLessThanOrEqual(1.3); // 고장 3.1~6.6, 정상 1.0
  expect(median(runs.map((r) => r.rvfcFps))).toBeGreaterThanOrEqual(25);           // 정상 30.0(바쁜 기계 여유)
  expect(median(runs.map((r) => r.rvfcGapMax))).toBeLessThanOrEqual(250);          // 눈에 보이는 멈춤 없음(정상 50)
  for (const run of runs) expect(run.longTasksOver100).toBeLessThanOrEqual(1);      // 실측 0
  expect(median(runs.map((r) => r.reactCommitsPerSec))).toBeLessThanOrEqual(12);   // 실측 7 — 프레임마다 그리기로 바뀌면 잡는다
});
```

Run: `cd apps/web && npm run test:e2e:real-flow -- e2e-real/playback-smoothness.spec.mjs` → **FAIL**(`appSeeksWhilePlaying` 0이 아님). 실패 출력의 `PLAYBACK_1X` 숫자를 보고에 붙인다 — 진단 표와 같은 범위(되감기 수십 회, 0.6~0.7배)가 아니면 **멈추고 보고**(하네스가 결함을 못 밟는 것이다). 범위 요청 가로채기가 안 돼 `effectiveRate`가 0 근처면 Step 2의 206 처리부터 본다.

- [ ] **Step 5: 검증 넷 + 커밋** — 갭: 재생 머리·스페이스·빠르기 시험은 Task 2·3·4가 더한다. 역방향: 이 Task 자체가 진짜 백엔드 + 진짜 Chromium. 동작: RED 숫자. 배선: 해당 없음. **이 커밋 뒤 Task 1 커밋 전까지 real-flow 묶음에서 이 한 건이 빨갛다**(stop hook은 가짜 API e2e만 돈다 — `npm run test:e2e` 48건이 그대로인지 확인).

```bash
git add scripts/e2e_editor_fixture.py scripts/e2e_real_editor_api.py tests/test_e2e_editor_fixture.py apps/web/e2e-real/support/realFlow.mjs apps/web/e2e-real/support/playbackProbe.mjs apps/web/e2e-real/playback-smoothness.spec.mjs
git commit -m "test(e2e): 편집기 재생을 진짜 Chromium에서 프레임으로 잰다 -- 지금은 되감기 고리 때문에 빨갛다

30초 고정 프로젝트와 범위 요청을 받는 시험 영상으로, 재생 중 앱의 currentTime 쓰기·
영상 시각 역행·실제 진행 속도·해독 배수·긴 작업·React 커밋을 센다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 1: 재생 중 되감기 고리를 끊는다(원인 1) — 약 2시간

**Files:**
- Modify: `apps/web/src/features/editor/preview/preview-stage.tsx` — 앵커 `  const staleSeekBaselineRef = useRef<number | null>(null);`, `    if (media && Math.abs(media.currentTime - mediaSeconds) > 0.001) {`, `  }, [mode, onPlaybackTimeChange, playbackSec]);`, `    const nextSeconds = coordinatorRef.current.timelineTime(node.currentTime);`, `    try { media.currentTime = clamped - range.startSec; } catch { return; }`
- Modify: `apps/web/src/features/editor/preview/preview-stage.test.tsx`

**Interfaces:** 바깥 계약(props)은 그대로. 안쪽에 `lastReportedTimelineSecRef: MutableRefObject<number | null>` — "이 미리보기가 마지막으로 위로 올려보낸 타임라인 시각".

규칙(한 줄): **`playbackSec`가 내가 방금 올려보낸 값이면 그건 메아리다 — 재생기를 옮기지 않는다.** 다른 값이면(타임라인 클릭·장면 고르기·화살표) 재생 중이어도 옮긴다.

- [ ] **Step 1: RED — 메아리로 되감지 않는다** — `preview-stage.test.tsx`의 `describe("PreviewStage"` 안에:

```tsx
it("재생 중 자기가 올려보낸 위치가 되돌아와도 재생기를 되감지 않는다(2026-10-09 실측: 20초에 67~74번)", () => {
  let reported = 0;
  const onPlaybackTimeChange = vi.fn((seconds: number) => { reported = seconds; });
  const { rerender } = render(<PreviewStage {...current} playbackSec={2} onPlaybackTimeChange={onPlaybackTimeChange} />);
  const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
  let time = 2.5;
  const writes: number[] = [];
  Object.defineProperty(media, "currentTime", { configurable: true, get: () => time, set: (value: number) => { writes.push(value); time = value; } });
  Object.defineProperty(media, "paused", { configurable: true, value: false });
  Object.defineProperty(media, "seeking", { configurable: true, value: false });

  fireEvent.timeUpdate(media);        // 재생기: 2.5초
  expect(reported).toBe(2.5);
  time = 2.517;                       // 다시 그리는 사이 재생기는 앞으로 갔다
  rerender(<PreviewStage {...current} playbackSec={reported} onPlaybackTimeChange={onPlaybackTimeChange} />);

  expect(writes).toEqual([]);
});
```

Run: `cd apps/web && npx vitest run src/features/editor/preview/preview-stage.test.tsx -t "되감지 않는다"` → FAIL(`writes`에 `2.5`). (처음 render의 `playbackSec={2}` 때문에 `writes`가 먼저 `[2]`로 시작하면, `Object.defineProperty`를 첫 render **뒤**에 하므로 그 쓰기는 jsdom 기본 setter로 갔다 — `writes`는 `[2.5]`여야 한다. 다르면 멈추고 보고.)

- [ ] **Step 2: GREEN — 최소 수정**
  1. `  const staleSeekBaselineRef = useRef<number | null>(null);` 바로 아래에 `  const lastReportedTimelineSecRef = useRef<number | null>(null);`와 주석 두 줄(왜: 메아리 되감기, 실측 숫자, 진단 보고 경로).
  2. `updateTimeline`의 `    const nextSeconds = coordinatorRef.current.timelineTime(node.currentTime);` 다음 줄에 `    lastReportedTimelineSecRef.current = nextSeconds;`. `seekTimelineTo`의 `    setTimelineTime(clamped);` 앞에도 `    lastReportedTimelineSecRef.current = clamped;`.
  3. 효과 안 `const timelineSeconds = …` 줄과 `setTimelineTime(timelineSeconds);` 다음에:
     ```tsx
     // 메아리: 내가 방금 올려보낸 위치가 그대로 돌아온 것이다. 재생기는 그새 앞으로 갔으니 옮기면 되감는다.
     if (lastReportedTimelineSecRef.current !== null && Math.abs(timelineSeconds - lastReportedTimelineSecRef.current) <= 1e-6) return;
     ```
  4. deps `}, [mode, onPlaybackTimeChange, playbackSec]);` → `}, [mode, playbackSec]);`(바로 위에 `// onPlaybackTimeChange는 매 렌더 새 함수다 -- deps에 두면 무관한 렌더마다 이 효과가 다시 돌아 되감았다(2026-10-09).` + `// eslint-disable-next-line react-hooks/exhaustive-deps`).
  5. 소스가 바뀌면(`showExact`·`showAudition`·`stopActiveMedia`) `lastReportedTimelineSecRef.current = null`.
  Run 같은 시험 → PASS.

- [ ] **Step 3: 짝 시험 — 진짜 탐색은 그대로 옮긴다(Review Focus 1)** — 같은 준비에서 `rerender(… playbackSec={7.25} …)` → `writes`가 `[7.25]`(구간 0~12, 시작 0이라 그대로). 하나 더: 메아리 뒤 사용자가 **같은 장면을 다시 눌러** `playbackSec`가 2.5 → 1.0 → 2.5로 오면 1.0과 2.5 둘 다 쓰인다(1.0이 오면서 메아리 표식이 무효가 되는지 — 무효가 안 되면 두 번째 2.5가 메아리로 오인된다. 그때는 효과에서 메아리가 아닌 값으로 옮긴 직후 `lastReportedTimelineSecRef.current = null`로 지운다). 두 시험 RED를 먼저 본다(둘째는 처음부터 통과할 수 있다 — 그러면 그 사실을 적고 넘어간다: 회귀 지킴용).

- [ ] **Step 4: 넓은 단위 검증** — `cd apps/web && npx vitest run src/features/editor/preview src/features/editor/workbench src/features/editor/timeline` → 알려진 1건 외 통과. 특히 `staleSeekBaselineRef`(2026-09-20) 시험과 H Task 3의 `resolvePlaybackSelection`·"재생이 고른 장면 끝을 지나면 다음 장면" 시험 이름을 출력에서 찾아 통과를 확인한다. `npx tsc --noEmit` 0.

- [ ] **Step 5: 진짜 Chromium(GREEN)** — `cd apps/web && npm run test:e2e:real-flow -- e2e-real/playback-smoothness.spec.mjs` → PASS. 3회 돌려 `PLAYBACK_1X`의 `effectiveRate`·`rvfcFps`·`decodedPerPresented` 중앙값을 보고에 붙인다(진단 기대: 1.00·30·1.0). `npm run test:e2e:real-flow -- e2e-real/clip-selection.spec.mjs e2e-real/no-narration-selection.spec.mjs` → PASS(고르기가 안 깨졌다).

- [ ] **Step 6: 검증 넷 + 커밋** — 갭: 재생 머리 간격(원인 2)은 아직 300ms다(Task 2). 배선: `grep -n "lastReportedTimelineSecRef" apps/web/src/features/editor/preview/preview-stage.tsx` → 선언 1 + 쓰기 2(올려보낼 때) + 읽기 1 + 지우기(소스 전환). 가짜 API e2e `npm run test:e2e` 48.

```bash
git add apps/web/src/features/editor/preview/preview-stage.tsx apps/web/src/features/editor/preview/preview-stage.test.tsx
git commit -m "fix(editor): 재생 중 미리보기가 자기가 알린 위치를 되받아 되감던 고리를 끊는다

timeupdate로 올린 시각이 재생 위치로 돌아오면 그새 앞으로 간 재생기를 뒤로 옮겼다
(20초에 67~74번, 실제 0.62~0.70배, 화면이 앞뒤로 흔들림). 내가 올려보낸 값이면
옮기지 않는다. 타임라인 클릭 같은 진짜 탐색은 그대로 옮긴다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 재생 머리·시간 글자를 매끄럽게 — 재생 시계(원인 2) — 약 4시간

**Files:**
- Create: `apps/web/src/features/editor/preview/playbackClock.ts`, `…/playbackClock.test.ts`
- Modify: `preview-stage.tsx` — 앵커 `export function PreviewStage({ expectedRevision, exactPreview, captions = [], sources, auditionRequest, onRefresh, playbackSec, onPlaybackTimeChange, fps, loopRange, durationSec, projectIsEmpty = false }: {`, `{currentMedia ? <output aria-live="off">타임라인 {timelineTime.toFixed(1)}{timelineTimeSuffix}</output>`
- Modify: `apps/web/src/features/editor/timeline/TimelineDock.tsx` — 앵커 `        className="vb-timeline-playhead"`, `  const reportedPlayheadRef = useRef<number | null>(null);`, `    dispatch({ type: "scroll", seconds: state.playheadSec });`, `<output aria-label="재생 위치" data-seconds={formatSeconds(state.playheadSec)}>{formatSeconds(state.playheadSec)}초</output>`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbench.tsx` — 앵커 `  const stage = <PreviewStage key={`, `      onPlaybackSeek={seekPlayback}`
- Modify: 각 시험 파일, `apps/web/e2e-real/playback-smoothness.spec.mjs`

**Interfaces:**
```ts
export type PlaybackClockReading = Readonly<{ seconds: number; playing: boolean }>;
export type PlaybackClock = Readonly<{
  publish(seconds: number, playing: boolean): void;   // 같은 값이면 알리지 않는다
  read(): PlaybackClockReading;
  subscribe(listener: (reading: PlaybackClockReading) => void): () => void;
}>;
export function createPlaybackClock(initialSeconds?: number): PlaybackClock;
```
- `PreviewStage`·`TimelineDock`에 선택 prop `playbackClock?: PlaybackClock`(없으면 지금과 똑같이 동작 — 기존 시험이 그대로 돈다). `EditorWorkbench`가 `const [playbackClock] = useState(() => createPlaybackClock(view.local.seekSec));`로 하나 만들어 둘에 준다.

**설계(왜 이 모양인가):** React 상태(`playbackSec`)는 지금처럼 `timeupdate`(≈4Hz)로만 바뀐다 — 장면 고르기·컷 도구가 그 값을 쓴다. 재생 중 눈에 보이는 것만 시계가 움직인다. 시계 구독은 **React를 다시 그리지 않고** DOM을 직접 고친다: 재생 머리는 React가 쓰는 `left`는 그대로 두고 **React가 안 쓰는 `transform: translateX(Δpx)`**(Δ = (시계 − 상태) × 배율)만, 시간 글자는 React가 **자식 없이** 그리는 `<span>`의 `textContent`만. 그래서 React 커밋이 늘지 않고(Task 0 시험의 ≤12/초), React가 옛 값을 덮어써 뒤로 깜빡이는 일도 없다.

- [ ] **Step 1: 시계(RED→GREEN)** — `playbackClock.test.ts`: (가) `publish(1, true)` → 구독자 1회, `read()` `{1,true}`; (나) 같은 값 다시 → 알리지 않음; (다) 구독 해제 뒤 알리지 않음; (라) 구독자 하나가 던져도 다른 구독자는 받는다. RED(모듈 없음) → 구현(배열 + `Set`, 30줄 안) → GREEN.

- [ ] **Step 2: 미리보기가 시계를 민다(RED→GREEN)** — `preview-stage.test.tsx`: `vi.spyOn(window, "requestAnimationFrame")`으로 콜백을 잡아 직접 부르는 방식. 재생 중(`paused=false`, `currentTime` 3.2)에 `play` 이벤트 → rAF 콜백 1회 실행 → `clock.read()`가 `{ seconds: 3.2, playing: true }`; `pause` 이벤트 → `{ …, playing: false }`이고 rAF 고리 멈춤(다음 콜백 예약 없음). 구현: `<video>`·`<audio>`에 `onPlay`로 고리 시작, `onPause`·`onEnded`·`onSeeked`·언마운트에서 멈추고 `publish(…, false)`. 고리 안에서는 `media.seeking`이면 건너뛴다. 시각은 `coordinatorRef.current.timelineTime(media.currentTime)`(이미 있는 변환 — 새 계산 금지).

- [ ] **Step 3: 시간 글자(RED→GREEN)** — 시험: 시계를 주고 `publish(4.26, true)` → `미리보기` 판의 재생줄 `output` 글자가 `타임라인 4.3 / 12.0초`(React 다시 그리기 없이 — `render` 횟수를 세지 말고 결과 글자만 본다). 구현: 앵커의 `<output aria-live="off">타임라인 {timelineTime.toFixed(1)}{timelineTimeSuffix}</output>` → `<output aria-live="off">타임라인 <span ref={readoutRef} />{timelineTimeSuffix}</output>`, `useLayoutEffect`가 렌더마다 `readoutRef.current.textContent = timelineTime.toFixed(1)`(멈춤 상태의 정답), 시계 구독이 재생 중 `seconds.toFixed(1)`로 덮는다. 시계가 없으면 `useLayoutEffect`만 돈다 → 기존 시험 그대로. **`user-copy-policy`가 이 글자를 계속 읽는지** `npx vitest run src/user-copy-policy.test.ts`로 확인.

- [ ] **Step 4: 타임라인 재생 머리(RED→GREEN)** — `timeline-dock.test.tsx`: 시계를 주고 렌더(배율은 그 파일의 기존 준비를 따른다, `playbackSec` 2) → `publish(2.5, true)` → `[data-testid='timeline-playhead']`의 `style.transform`이 `translateX(${0.5 × pxPerSec}px)`(배율은 그 요소가 속한 `section`의 `data-pixels-per-second`에서 읽는다); `publish(2.5, false)` 뒤 React가 `playbackSec` 2.5로 다시 그리면 `transform`은 `""`이고 `left`가 새 값. 아래쪽 `<output aria-label="재생 위치">`도 Step 3과 같은 방식(자식 없는 `<span ref>`)으로. 구현은 `TimelineDock` 안 `useEffect`에서 `playbackClock?.subscribe`; 계산에 쓰는 `state.playheadSec`·`state.pixelsPerSecond`·보이는 구간 끝은 **ref로 최신값을 들고**(`runZoomRef` 패턴 — 구독을 렌더마다 다시 붙이지 않는다). `useLayoutEffect`(deps 없이)로 렌더마다 `transform`을 지운다(상태가 따라왔으니).

- [ ] **Step 5: 따라가기(Review Focus 5, RED→GREEN)** — 시험: 보이는 구간 0~10초, `publish(10.2, true)` → 타임라인 `data-viewport-start-seconds`가 바뀐다(지금 `scroll` 동작과 같은 자리로). 구현: 구독에서 시계 값이 `resolveViewportEnd(…)`를 넘으면 `dispatch({ type: "scroll", seconds })` — **넘은 순간 한 번만**(같은 쪽 넘김을 ref로 기억). 기존 따라가기 효과(`    const followEndSec = resolveViewportEnd(state, view.output.durationSec, trackWidthPx);`로 시작하는 것)는 그대로 둔다(멈춘 상태·화살표용).

- [ ] **Step 6: 배선** — `EditorWorkbench.tsx`: 시계 하나 만들어 `const stage = <PreviewStage …`와 `TimelineDock`(`onPlaybackSeek={seekPlayback}` 옆)에 `playbackClock={playbackClock}`. 프로젝트·세션이 바뀌면(앵커 `      viewRouteKeyRef.current = viewRouteKey;` 바로 아래) `playbackClock.publish(clampPlaybackSeconds(view.local.seekSec, view.output.durationSec), false)`.

- [ ] **Step 7: 진짜 Chromium** — `playback-smoothness.spec.mjs` 첫 시험에 두 줄 추가(RED를 먼저 본다 — Step 6 전 커밋 상태에서 돌리거나, 추가 후 `git stash`로 Task 2 변경을 빼고 한 번):
```js
  expect(median(runs.map((r) => r.playheadGapP95))).toBeLessThanOrEqual(100); // 실측 고장 p50 300·p95 400
  expect(median(runs.map((r) => r.readoutGapP95))).toBeLessThanOrEqual(250);  // 0.1초 글자라 100ms 단위로 바뀜
```
GREEN 3회 중앙값을 보고에. `reactCommitsPerSec`가 Task 1 때보다 늘지 않았는지(≤12) 확인.

- [ ] **Step 8: 넓은 검증 + 검증 넷 + 커밋** — vitest `src/features/editor` 전부(알려진 1건 외), tsc 0, 빌드, `npm run test:e2e`(48), real-flow `clip-selection`·`no-narration-selection`·`ruler-scale`·`playback-smoothness`. 배선: `grep -rn "playbackClock" apps/web/src --include=*.tsx | grep -v test` → EditorWorkbench(만들기 1·넘기기 2), PreviewStage(publish), TimelineDock(subscribe). 갭: 원본 보기(audition) 재생도 같은 시계를 미는지 — Step 2 구현이 `<audio>`·`<video>` 둘 다에 붙었는지 적는다.

```bash
git add apps/web/src/features/editor apps/web/e2e-real/playback-smoothness.spec.mjs
git commit -m "fix(editor): 재생 머리와 시간 글자가 0.3초마다 뛰지 않고 화면 프레임마다 흐른다

재생 중에는 작은 재생 시계가 재생기 시각을 rAF로 읽어 알리고, 재생 머리는 transform,
시간 글자는 글자만 직접 고친다. React 상태는 지금처럼 timeupdate 빈도로만 바뀐다.
머리가 보이는 구간을 넘으면 그 순간 넘긴다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 스페이스는 늘 재생/정지, 밖을 눌러도 0초로 튀지 않는다(원인 3·4) — 약 2.5시간

**Files:**
- Create: `apps/web/src/features/editor/preview/playbackShortcuts.ts`, `…/playbackShortcuts.test.ts`
- Modify: `preview-stage.tsx` — 앵커 `  const onStageKeyDown = (event: KeyboardEvent<HTMLElement>) => {`, `    if (event.key !== " " && event.key !== "Enter") return;`, `      if (event.key !== " " || event.ctrlKey || event.metaKey || event.altKey) return;`, `  const onStageBlur = (event: FocusEvent<HTMLElement>) => {`, `    const stopForScroll = () => stopActiveMedia();`
- Modify: `preview-stage.test.tsx` — 앵커 `  it("maps media time to timeline time, supports keyboard play/pause, and stops on scroll-away and unmount", () => {`
- Modify: `apps/web/e2e-real/playback-smoothness.spec.mjs`

**Interfaces:**
```ts
export type PlaybackCommand =
  | Readonly<{ type: "toggle" }>
  | Readonly<{ type: "pause" }>
  | Readonly<{ type: "faster" }>      // Task 4
  | Readonly<{ type: "slower" }>      // Task 4
  | Readonly<{ type: "step"; frames: -1 | 1 }>; // Task 4
export type PlaybackKeyEvent = Readonly<{ key: string; ctrlKey: boolean; metaKey: boolean; altKey: boolean; shiftKey: boolean; repeat: boolean; isComposing: boolean; defaultPrevented: boolean; target: EventTarget | null }>;
/** 키 하나 → 재생 명령. 가로채면 안 되는 자리면 null. */
export function playbackShortcutFor(event: PlaybackKeyEvent): PlaybackCommand | null;
export function isTypingTarget(target: EventTarget | null): boolean; // input·textarea·select·contenteditable
```

**스페이스 규칙(정확히, 위에서부터 먼저 걸리는 것이 이긴다):**
1. `ctrl/meta/alt`가 눌렸거나 `isComposing`(한글 조합 중)이거나 `defaultPrevented`이면 → null.
2. `repeat`(꾹 누름) → null. **단 `preventDefault`는 한다**(아래 4·5 자리일 때만 — 꾹 누르는 동안 페이지가 굴러가지 않게). 이 판단은 호출하는 쪽에서: 명령이 null이고 `event.repeat && 첫 키라면 가로챌 자리`면 preventDefault만.
3. 대상이 글을 쓰는 자리(`isTypingTarget`: `input, textarea, select, [contenteditable='true']`, `isContentEditable`) → null(띄어쓰기).
4. 대상이 `[aria-modal='true']` 안(도크 서랍 등) → null.
5. 대상이 **타임라인 면**(`[data-timeline-surface='true']`) 안 → toggle(장면 칸이 단추여도 — 2026-09-04 owner 지적, 그대로).
6. 대상이 스페이스를 스스로 쓰는 조작(`button, [role='button'], [role='menuitem'], [role='menuitemradio'], [role='option'], [role='slider'], [role='checkbox'], [role='switch'], [role='tab'], [role='radio'], summary, a[href]`) 안 → null(그 조작이 눌린다 — 접근성. 재생 단추 위면 그 단추가 재생/정지를 한다 = 같은 결과).
7. 나머지(빈 곳·`body`·`미리보기` 판 자체·타임라인 밖 글자) → toggle.

- [ ] **Step 1: 규칙 표 시험(RED→GREEN)** — `playbackShortcuts.test.ts`에 위 1~7을 `it.each`로(각 줄: 만든 DOM 대상, 키 옵션, 기대). 반드시 넣을 줄: `section[tabindex=0]`(미리보기 판) → toggle, `timeline 안 button` → toggle, `음소거 button`(타임라인 밖) → null, `input` → null, `repeat:true` → null, `isComposing:true` → null, `[aria-modal='true'] div` → null, `ctrlKey` → null. RED(모듈 없음) → 구현 → GREEN. `TimelineDock.tsx`의 `function isEditableTarget(`은 이 파일의 `isTypingTarget`을 부르게 바꾼다(같은 판정이 세 곳에 있지 않게 — 동작 같음, 그 파일 시험 통과로 확인).

- [ ] **Step 2: 미리보기 판에서 스페이스가 두 번 뒤집히지 않는다(RED→GREEN)** — `preview-stage.test.tsx`:
```tsx
it("미리보기 판(영상 그림을 누른 뒤)에서 스페이스를 누르면 한 번만 재생된다(2026-10-09 실측: 둘이 상쇄)", () => {
  render(<PreviewStage {...current} />);
  const media = screen.getByLabelText("편집본 미리보기") as HTMLVideoElement;
  const play = vi.spyOn(media, "play").mockResolvedValue(undefined);
  let paused = true;
  Object.defineProperty(media, "paused", { configurable: true, get: () => paused });
  play.mockImplementation(async () => { paused = false; });
  const stage = screen.getByRole("region", { name: "미리보기" });
  stage.focus();
  fireEvent.keyDown(stage, { key: " " });
  expect(play).toHaveBeenCalledTimes(1);
  expect(paused).toBe(false);
});
```
RED(지금은 판 처리기가 `play` → 창 처리기가 `pause` — `paused`가 다시… jsdom에서 `pause`는 `beforeEach`가 막아 두었으므로 `play` 1회·`pause` 1회로 보인다: 기대를 `expect(HTMLMediaElement.prototype.pause).not.toHaveBeenCalled()`도 함께 둔다). 구현: `onStageKeyDown`은 **Enter만** 처리(`if (event.key !== "Enter") return;`), 스페이스는 창 처리기 하나만. 창 처리기 몸통은 `playbackShortcutFor(event)`가 `toggle`이면 `preventDefault()` + `togglePlayback()`.

- [ ] **Step 3: 밖을 눌러도 멈추거나 0초로 가지 않는다(RED→GREEN)** — 기존 시험 `"maps media time to timeline time, supports keyboard play/pause, and stops on scroll-away and unmount"`를 **의도를 바꿔** 고친다(이름 `"…, keeps playing in place when focus or the page moves, and stops on unmount"`): `blur` 뒤 `pause` 안 불림 + `currentTime` 그대로, `scroll` 뒤도 같음, `unmount` 뒤 `pause` 불림. RED → 구현: `onStageBlur`와 `stopForScroll` 리스너를 지운다(`onBlur={onStageBlur}` 속성 포함). 언마운트 정리는 `useLayoutEffect`의 반환 `stopActiveMedia()`가 이미 한다 — 그 함수는 남긴다(소스 전환용). 이것이 **행동 변경**이라는 것과 이유(2026-10-09 실측: 재생 중 타임라인 제목 클릭 → 2.2초 → 0초·정지)를 주석과 커밋에 적는다. 캡컷도 다른 곳을 눌러도 재생이 이어진다.

- [ ] **Step 4: 기존 스페이스 시험 다섯** — `"plays and pauses from the space bar anywhere…"`, `"pauses in place…"`, `"still plays when the space bar is pressed on a timeline clip…"`, 입력칸·`다음 프레임` 단추·`미리보기 새로 만들기` 단추 시험(파일의 `fireEvent.keyDown(…, { key: " " })` 7곳)이 그대로 통과하는지 — 기대를 바꿔야 하면 멈추고 보고(규칙 6·3이 지켜야 하는 것들이다). `timeline-dock.test.tsx`의 `fireEvent.keyDown(secondClip, { key: " " })`도.

- [ ] **Step 5: 진짜 Chromium** — `playback-smoothness.spec.mjs`에 시험 추가: `스페이스는 영상 그림을 누른 뒤에도·타임라인을 누른 뒤에도 재생/정지이고, 미리보기 밖을 눌러도 위치가 그대로다` — (가) `page.getByLabel("편집본 미리보기").click()` → `Space` → 0.7초 뒤 `paused === false` → `Space` → `true`; (나) 재생 단추로 재생 2초 → 타임라인 제목(`.vb-editor-workbench__timeline-head h2`) 클릭 → 0.6초 뒤 `paused === false`이고 `currentTime > 2`; (다) 음소거 단추에 초점 → `Space` → 재생 상태 그대로·음소거가 바뀜(접근성 규칙). 진단 `focus2.mjs`가 같은 동작으로 RED를 냈다 — 먼저 RED 확인.

- [ ] **Step 6: 넓은 검증 + 검증 넷 + 커밋** — vitest editor 전부, tsc, `user-copy-policy`, `task22-parity-owners`, `npm run test:e2e`(48), real-flow `playback-smoothness`. 배선: `grep -rn "playbackShortcutFor\|isTypingTarget" apps/web/src --include=*.tsx` → preview-stage(1), TimelineDock(1).

```bash
git add apps/web/src/features/editor apps/web/e2e-real/playback-smoothness.spec.mjs
git commit -m "fix(editor): 영상을 누른 뒤에도 스페이스로 재생되고, 다른 곳을 눌러도 0초로 튀지 않는다

미리보기 판과 창 전체가 스페이스를 둘 다 받아 서로 상쇄했다. 창 한 곳에서만 받고,
키 문지기는 playbackShortcuts 한 함수로 모은다(꾹 누름·한글 조합·서랍 안은 무시).
미리보기 밖을 누르거나 창이 구르면 멈추고 0초로 되감던 동작을 없앤다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 재생 빠르기 0.25~2배 + 기억 + J/K/L + 화살표 한 프레임(원인 6) — 약 4시간

**Files:**
- Create: `apps/web/src/features/editor/preview/playbackRate.ts`, `…/playbackRate.test.ts`
- Modify: `playbackShortcuts.ts`(+시험), `preview-stage.tsx` — 앵커 `<button data-native-control="toggle-fullscreen"`, `  const togglePlayback = () => {`, `onLoadedMetadata={(event) => checkAuditionVideo(event.currentTarget)}`
- Modify: `apps/web/src/features/editor/timeline/TimelineDock.tsx` — 앵커 `  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {`(화살표 이중 처리 방지 확인만)
- Modify: `apps/web/src/styles/editor-workbench.css` — 앵커 `.vb-preview-stage__transport > button { flex: 0 0 auto; }`
- Modify: `apps/web/e2e-real/playback-smoothness.spec.mjs`

**Interfaces:**
```ts
export const PLAYBACK_RATES = [0.25, 0.5, 0.75, 1, 1.5, 2] as const;
export type PlaybackRate = (typeof PLAYBACK_RATES)[number];
export const PLAYBACK_RATE_STORAGE_KEY = "videobox.editor.playback-rate";
export function readPlaybackRate(storage?: Pick<Storage, "getItem"> | null): PlaybackRate;   // 없거나 이상하면 1, 던지면 1
export function writePlaybackRate(rate: PlaybackRate, storage?: Pick<Storage, "setItem"> | null): void; // 던져도 조용히
export function stepPlaybackRate(rate: PlaybackRate, direction: 1 | -1): PlaybackRate;          // 끝에서 멈춘다
export function applyPlaybackRate(media: HTMLMediaElement, rate: PlaybackRate): void;           // defaultPlaybackRate와 playbackRate 둘 다
export function formatPlaybackRate(rate: PlaybackRate): string;                                  // "0.5배", "1배"
```
기본 저장소 인자는 `typeof window === "undefined" ? null : window.localStorage`를 **함수 안 try에서** 읽는다(사생활 창에서 접근 자체가 던진다).

**키(위 Task 3 문지기 규칙 1~4를 그대로 거친 뒤, 글자 키는 단추 위에서도 받는다 — 단추는 글자를 안 쓴다):**

| 키 | 동작 |
|---|---|
| `K` | 일시정지(빠르기 그대로) |
| `L` | 멈춰 있으면 지금 빠르기로 재생, 재생 중이면 한 단계 빠르게(… 1 → 1.5 → 2, 2에서 그대로) |
| `J` | 한 단계 느리게(1 → 0.75 → 0.5 → 0.25, 0.25에서 그대로) + 멈춰 있으면 재생. **뒤로 재생은 없다** |
| `←` / `→` | 멈추고 한 프레임 뒤/앞(지금 `◀｜`·`｜▶` 단추와 같은 `stepFrame`). **타임라인 면 안이면 null** — 타임라인의 `navigationKeyAction`이 이미 받는다(이중 이동 방지). 화살표를 스스로 쓰는 조작 위에서도 null: `select`, `[role='slider']`, `[role='spinbutton']`, `[role='radio']`, `[role='tab']`, `[role='menuitem']`, `[role='option']`, `[role='separator']`(도크 크기 손잡이 `ResizableHandle`이 화살표로 폭을 바꾼다 — `EditorWorkbench.tsx` `onKeyDown={(event) => handleKey(event, "left")}`) |
| 대문자(`Shift`) | `j`/`J` 모두 같은 뜻(`key.toLowerCase()`). `Shift+←/→`는 이번 범위 밖 → null |

- [ ] **Step 1: `playbackRate.ts`(RED→GREEN)** — 시험: 단계 오르내림·끝 멈춤, `readPlaybackRate`가 `"0.5"` → 0.5, `"3"`·`"abc"`·`null` → 1, `getItem`이 던지면 1, `writePlaybackRate`가 던지는 저장소에서도 안 던진다, `applyPlaybackRate`가 `defaultPlaybackRate`·`playbackRate`를 둘 다 바꾼다, `formatPlaybackRate(0.25) === "0.25배"`.

- [ ] **Step 2: 키 표(RED→GREEN)** — `playbackShortcuts.test.ts`에 위 표를 `it.each`로: `k`→pause, `l`→faster, `j`→slower, `ArrowRight`(본문)→step +1, `ArrowRight`(타임라인 면 안)→null, `ArrowLeft`(`role=slider` 위)→null, `ArrowRight`(`role=separator` 위)→null, `l`(입력칸)→null, `L`(`shiftKey`)→faster, `l`(`ctrlKey`)→null. `faster`의 "멈춰 있으면 단계 없이 재생"은 명령이 아니라 **실행하는 쪽**(preview-stage)이 정한다 — 시험은 Step 4에서.

- [ ] **Step 3: 재생 빠르기 고르기(RED→GREEN)** — `preview-stage.test.tsx`: (가) 처음 그리면 `재생 빠르기` 고르기(`getByLabelText("재생 빠르기")`) 값이 `"1"`이고 재생기 `playbackRate` 1; (나) `0.5`를 고르면 재생기 `playbackRate`·`defaultPlaybackRate` 0.5, `localStorage.getItem(PLAYBACK_RATE_STORAGE_KEY) === "0.5"`; (다) 저장소에 `"0.75"`가 있으면 처음부터 0.75; (라) **Review Focus 3**: 0.5로 바꾼 뒤 `rerender`로 `exactPreview.url`을 바꾸고(새 소스) `fireEvent.loadedMetadata(media)` → `playbackRate` 0.5. 구현: `const [rate, setRate] = useState(() => readPlaybackRate());`, 재생기 `onLoadedMetadata`에서 기존 `checkAuditionVideo`와 함께 `applyPlaybackRate(event.currentTarget, rate)`(audio에도 `onLoadedMetadata` 추가), `rate`가 바뀌면 `useEffect`로 `mediaRef.current`에 적용 + `writePlaybackRate`. 고르기는 `<button data-native-control="toggle-fullscreen"` 단추 **바로 뒤**에:
```tsx
<label className="vb-preview-stage__rate" title="보는 속도만 바뀌어요. 영상은 바뀌지 않아요 · J 키 느리게 · L 키 빠르게 · K 키 멈춤">
  <span>재생 빠르기</span>
  <NativeSelect aria-label="재생 빠르기" value={String(rate)} disabled={!currentMedia} onChange={(event) => setRate(Number(event.target.value) as PlaybackRate)}>
    {PLAYBACK_RATES.map((value) => <option key={value} value={String(value)}>{formatPlaybackRate(value)}</option>)}
  </NativeSelect>
</label>
```
(`NativeSelect`는 `@/components/ui/native-select` — `task22-parity-owners` 허용 목록을 안 건드린다. 시험 파일이 그것을 통과로 확인한다.) CSS: `.vb-preview-stage__transport > button { flex: 0 0 auto; }` 아래에 `.vb-preview-stage__rate { display: inline-flex; align-items: center; gap: var(--vb-space-1); }`·`.vb-preview-stage__rate select { width: auto; }` — 색 값 없이.

- [ ] **Step 4: 키가 빠르기를 움직인다(RED→GREEN)** — `preview-stage.test.tsx`: 멈춘 상태에서 `l` → `play` 1회·빠르기 1 그대로; 재생 중(`paused=false`) `l` → 1.5 → `l` → 2 → `l` → 2; `j` 넷 → 1.5 → 1 → 0.75 → 0.5(시작 2에서); 멈춘 상태 `j` → 한 단계 느리게 + `play`; `k` → `pause`; `ArrowRight`(본문) → `pause` + `currentTime`이 한 프레임(1/30) 앞. 고르기 값도 같이 바뀐다. 구현: 창 처리기에서 `playbackShortcutFor` 명령별로 실행(`step`은 기존 `stepFrame(direction)` 재사용).

- [ ] **Step 5: 진짜 Chromium(동작을 잰다)** — `playback-smoothness.spec.mjs`에 시험 `재생 빠르기 0.5배·2배가 실제로 그만큼 흐르고, 다시 열어도 기억한다`: 고르기로 0.5 → `measurePlayback(…, seconds: 8)` 3회 → `effectiveRate` 중앙값 0.45~0.55, `appSeeksWhilePlaying` 0; `L` 두 번(재생 중) → 2배 → 중앙값 1.8~2.1; `page.reload()` 뒤 고르기 값 `"2"`이고 `video.playbackRate === 2`; `J`로 1까지 내려 놓고 끝(다음 시험이 1배로 시작하게 — 순서 의존을 없애려면 각 시험 처음에 `localStorage.removeItem`).

- [ ] **Step 6: 넓은 검증 + 검증 넷 + 커밋** — vitest editor·`user-copy-policy`·`task22-parity-owners`, tsc, 빌드, `npm run test:e2e`(48), real-flow 전부. 배선: `grep -rn "applyPlaybackRate\|readPlaybackRate\|writePlaybackRate" apps/web/src --include=*.tsx` → preview-stage만(적용 2: 소스 열림·값 바뀜). 갭: 원본 보기(audition) 재생기에도 걸리는지 시험 하나(소스 전환) — 없으면 적는다.

```bash
git add apps/web/src/features/editor apps/web/src/styles/editor-workbench.css apps/web/e2e-real/playback-smoothness.spec.mjs
git commit -m "feat(editor): 재생 빠르기 0.25~2배를 고르고 J·K·L 키로 바꾸며, 고른 빠르기를 기억한다

보는 속도만 바뀌고 완성 영상은 그대로다(장면 속도와 다름을 안내). 새 미리보기가
열려도 같은 빠르기를 다시 건다. 화살표는 어디서나 한 프레임(타임라인 안은 타임라인이
받는다).

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 단축키를 화면에서 알 수 있게 — 약 1.5시간

**Files:** Modify `preview-stage.tsx`(재생줄), `preview-stage.test.tsx`, `apps/web/src/styles/editor-workbench.css`

**Interfaces:** 재생줄 끝에 `@/components/ui/button`의 `Button`(variant `ghost`, size `sm`) `단축키` — `aria-expanded`, `aria-controls="vb-playback-shortcuts"`. 누르면 바로 아래 `<div id="vb-playback-shortcuts" role="note" aria-label="재생 단축키">`가 열린다(드롭다운 메뉴가 아니다 — 메뉴 항목은 누를 수 있는 것처럼 보인다). 내용(명사형 + 짧은 해요체):

```
스페이스바 — 재생 / 일시정지
K 키 — 멈춤
L 키 — 재생, 누를수록 빠르게(최대 2배)
J 키 — 느리게(최소 0.25배)
← → — 한 프레임씩
빠르기는 보는 속도예요. 영상은 바뀌지 않아요.
```
`Escape`·바깥 클릭·다시 누르기로 닫힌다. 기존 단추의 `aria-label`은 그대로 두고 **`title`에 키를 더한다**: `재생 또는 일시정지` → `title="스페이스바"`, `이전 프레임`/`다음 프레임` → `title="← 키"`/`title="→ 키"`.

- [ ] **Step 1: RED→GREEN** — 시험: `단축키` 단추 → `getByRole("note", { name: "재생 단축키" })`에 `스페이스바`·`J 키`·`L 키`·`K 키` 글자, `Escape` → 사라짐, 단추 `aria-expanded` 참/거짓. 재생 단추 `title` `스페이스바`.
- [ ] **Step 2: 문구 정책** — `cd apps/web && npx vitest run src/user-copy-policy.test.ts` 통과. 영어 단어 없음(키 이름 `J`·`K`·`L`은 글자 하나 — 정책의 금지 목록 대조 결과를 보고에).
- [ ] **Step 3: 화면 확인** — Task 7 실기에서 1440×900·1280×720·375×812 스크린샷으로 재생줄이 넘치지 않는지(375에서 줄바꿈 허용, 가로 넘침 0 — `scrollWidth === clientWidth`).
- [ ] **Step 4: 검증 넷 + 커밋** — 배선: `grep -n "vb-playback-shortcuts" apps/web/src -r` → 컴포넌트 1·CSS 1.

```bash
git add apps/web/src/features/editor/preview apps/web/src/styles/editor-workbench.css
git commit -m "feat(editor): 재생줄의 단축키 안내 -- 스페이스바·J·K·L·화살표

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 미리보기 인코드에 1초 키프레임(원인 5) — 약 2시간

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/ffmpeg_final_renderer.py` — 앵커 `            "-bf", "0", "-pix_fmt", "yuv420p",`(합성 인코드, `_render_composition_plan_to_mp4` 안), `                "-c:v", "libx264" if (subtitle_ass_path is not None or proxy_profile) else "copy",`, `                command += ["-pix_fmt", "yuv420p", "-movflags", "+faststart", "-metadata:s:v:0", f"rotate={inputs.composition_plan.rotation}"]`(마무리 인코드, `render_timeline_to_mp4` 안)
- Modify: `tests/test_exact_preview_artifact.py`

**Interfaces:** 렌더러 메서드 `def _keyframe_interval_frames(self) -> int`(= `round(fps)`, 최소 1 — `video_fps`가 `"30000/1001"`일 수 있다: 이미 있는 `def _frame_seconds(self) -> float:`(한 프레임 길이)를 재사용해 `max(1, round(1 / self._frame_seconds()))`). **미리보기(`proxy_profile=True`)에만** `"-g", str(n), "-keyint_min", str(n)`을 더한다. 완성본(최종 출력)은 이번에 안 바꾼다(크기·화질 판단은 별개 — owner 결정 3).

- [ ] **Step 1: RED(진짜 ffmpeg)** — `tests/test_exact_preview_artifact.py`의 `test_plan_renderer_real_fixture_preserves_leading_gap_and_later_overlap` 준비를 그대로 본떠 `test_exact_preview_has_a_keyframe_every_second`(5초 파랑 + 무음 5초, 320×240, `render_exact_preview_to_mp4`) → `ffprobe -v error -select_streams v:0 -skip_frame nokey -show_entries frame=pts_time -of csv=p=0 <out>` → 키프레임 시각들의 최대 간격 `<= 1.0 + 1/30`. `@pytest.mark.skipif(shutil.which("ffmpeg") is None …)`. Run → FAIL(키프레임 1개 — 단색은 장면 전환도 없다).
- [ ] **Step 2: GREEN** — 두 인코드 자리에 `if proxy_profile:`로 인자 추가(마무리 인코드는 `if proxy_profile:` 블록이 이미 있다 — 그 리스트에 넣는다; 합성 인코드는 `"-bf", "0"` 앞에 조건부로). Run → PASS.
- [ ] **Step 3: 회귀** — `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_exact_preview_artifact.py tests/test_ffmpeg_final_renderer.py tests/test_exact_preview_remediation.py tests/test_final_render_publish_fence.py` → 통과(명령 모양을 문자열로 대조하는 시험이 있으면 그 기대에 `-g`를 넣는 것이 맞는지 판단해 보고 — 완성본 쪽 기대가 바뀌면 잘못 넣은 것이다).
- [ ] **Step 4: `EXACT_PREVIEW_PROFILE`은 올리지 않는다** — 올리면 대표님의 모든 프로젝트 미리보기가 낡음이 되어 한꺼번에 다시 만들어야 한다. 새로 만들어지는 미리보기부터 1초 키프레임이 된다(커밋 메시지·인계에 적는다).
- [ ] **Step 5: 동작** — 컨테이너 재빌드는 Task 7. 여기서는 Step 1 파일의 크기·키프레임 수를 보고에.

```bash
git add packages/core-engine/src/videobox_core_engine/ffmpeg_final_renderer.py tests/test_exact_preview_artifact.py
git commit -m "perf(preview): 미리보기 영상에 1초마다 키프레임 -- 탐색·한 프레임 이동이 4~7배 빠르다

기본 keyint 250(30fps에서 8.3초)이라 탐색마다 최대 8초를 다시 풀었다(실측 p95 48ms -> 7ms,
크기 +10.7%). 완성본은 그대로. 이미 만든 미리보기는 낡음으로 바꾸지 않는다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 마지막 실기 검증·인계·푸시 — 약 3시간

- [ ] **Step 1: 넓은 검증(한 번씩)** — 웹 `cd apps/web && npx vitest run`(알려진 1건 외), `npx tsc --noEmit` 0, `npm --prefix apps/web run build`. e2e `npm run test:e2e` → **48 통과**(끝 PNG exit 무관, 스냅샷 PNG 바뀌면 차이 기록 후 `git checkout -- apps/web/e2e/snapshots/*.png` — 재생줄에 고르기·단추가 늘어 편집기 스냅샷이 다를 수 있다 → owner 결정 4). `npm run test:e2e:real-flow` 전부. 백엔드는 Task 6 파일들만(전체 pytest는 이 계획이 백엔드 한 함수만 바꿔 생략 — 생략 사실을 인계에 적는다).
- [ ] **Step 2: 컨테이너 재빌드** — PowerShell `.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild`. 실패하면 멈춘다.
- [ ] **Step 3: 실제 화면(대표님 프로젝트는 읽기만)** — 진단 스크립트 `.superpowers/sdd/playback-diagnosis-2026-10-09/scripts/measure-playback.mjs editor`(`ONLY=742 STARTS=0,30,60,95 PLAY_SEC=20`)를 **그대로** 다시 돌려 진단 표와 나란히 놓는다: 되감기 0·역행 0·1.00배·30fps·해독 1.0배·재생 머리 간격. `focus2.mjs`로 그림 클릭 → 스페이스, 재생 중 밖 클릭. 재생 빠르기 0.5·2배를 고르고 20초씩 `effectiveRate`. 0907은 미리보기가 최신일 때만(낡았으면 재생 확인 제외라고 적는다 — 미리보기를 새로 만들지 않는다). 스크린샷(1440·1280·375, 재생줄·단축키 안내 열림)을 `docs/superpowers/audit-evidence/2026-10-09-playback/`에.
- [ ] **Step 4: 갭 점검표** — Task 0~6 Step 대조, **안 한 것**: 대표님 실제 창(headful·GPU 경합)에서의 체감, 소리 끊김(headless 무음 장치라 못 잼), 실시간 타임라인 재생(범위 밖), 거꾸로 재생(없는 기능), 완성본 GOP(결정 3), 유진 배선(결정 2). §8.3: 재사용·반영·제외와 이유·경계 보존.
- [ ] **Step 5: 인계** — `docs/handoffs/2026-10-0X-editor-playback-p.ko.md`(실제 날짜): 한 일·잰 값(진단 대비 표)·못 한 것·owner 결정·다음. `CLAUDE.md` §2 표 `최신 세션 인계` 줄을 이 파일로(`tests/test_handoff_entry_point.py` 돈다).
- [ ] **Step 6: 커밋 → 따로 푸시** — 인계·`CLAUDE.md`·증거 그림 커밋. 그 다음 **따로** `git push origin main`(강제 금지). 권한이 막으면 우회하지 말고 owner에게 요청.

---

## 유진 배선 (상시 지시 점검)

**이번 범위: 없음.** 재생 빠르기·단축키는 편집이 아니라 **보는 방식**이고, 유진의 적용기는 편집을 바꾼다. 다만 상시 지시(2026-09-11 "화면으로 되는 건 전부 유진에게도")와 **선례(타임라인 확대·축소는 유진 채팅 `zoomCommand`로도 된다)**가 있어 owner 결정 2로 올린다. 하기로 하면 `zoomCommand`와 같은 모양(`requestId` + 값, 같은 표를 거침)으로 약 2시간.

## owner 결정이 필요한 것 (기본값과 비용)

| # | 결정 | 추천 기본값 | 고르면 드는 것 |
|---|---|---|---|
| 1 | **(질문)** "더 느리게"는 **확인할 때 보는 속도**(완성 영상 그대로)인가요, **장면 자체 속도**(오른쪽 `속도` 칸 — 완성 영상이 길어짐)인가요? | 보는 속도(이 계획). 기본 1배, 고른 값 기억 | 장면 속도라면 이미 있는 `속도` 칸(2026-09-04 결정)으로 되고, 이 계획의 빠르기는 확인용으로 그대로 쓸모 있다. 둘 다면 추가 비용 없음 |
| 2 | 유진에게 "천천히 보여 줘 / 0.5배로 틀어 줘" 배선 | 하지 않는다(보는 방식) | 약 2시간(`zoomCommand` 모양 재사용). 상시 지시를 문자 그대로 따르면 해야 한다 |
| 3 | 완성본(최종 mp4)에도 1초 키프레임 | 하지 않는다 | 완성본 크기 약 +10%, 유튜브 업로드엔 이득 없음. 캡컷 넘김 파일 탐색은 빨라진다 |
| 4 | e2e 스냅샷 그림 갱신(재생줄에 `재생 빠르기`·`단축키`) | 차이를 보고 승인 | 승인 전까지 편집기 스냅샷 비교가 다르다고 보고된다 |

## 확인하지 못한 채 남는 것 (계획 시점)

- 대표님 실제 창(일반 Chrome, GPU를 다른 모델과 나눠 씀)에서 멈칫이 1초까지 길었는지 — headless는 최대 133ms였다. "1초 단위"가 원인 2(머리 걸음)인지 멈칫인지 갈리지 않았다. Task 7 뒤 대표님 체감으로만 닫힌다.
- 소리: 탐색마다 소리가 다시 시작되므로 끊겼을 가능성이 크지만 headless에서 재지 않았다.
- 0907 편집기 재생(측정 시점 미리보기 낡음), 원본 보기(audition) 재생 — 같은 효과를 타므로 같은 결함으로 추정.
- 시험 영상(testsrc2)은 대표님 실제 영상보다 단순하다(기억 메모: 단색 시험 영상이 결함을 숨긴다) — 그래서 Task 7은 742 실물로 같은 측정을 다시 돈다.

## 계획서 자체 점검 메모 (작성자)

- 앵커 문자열은 작성 시점(`6697adfdb`)에 `grep -F`로 존재·유일성을 확인했다(아래 목록). 이름 일관성: `lastReportedTimelineSecRef`(Task 1), `createPlaybackClock`·`PlaybackClock`·`playbackClock` prop(Task 2), `playbackShortcutFor`·`isTypingTarget`·`PlaybackCommand`(Task 3·4), `PLAYBACK_RATES`·`readPlaybackRate`·`writePlaybackRate`·`stepPlaybackRate`·`applyPlaybackRate`·`formatPlaybackRate`·`PLAYBACK_RATE_STORAGE_KEY`(Task 4), `_keyframe_interval_frames`(Task 6), e2e `installPlaybackProbe`·`measurePlayback`·`withLongPreview`·`ensureLongPreviewMp4`·`median`(Task 0).
- e2e 문턱은 진단 실측(고장/정상)에서 골랐다: 결정적인 둘(되감기·역행 0)은 매회, 시간 지표는 3회 중앙값 + 여유(정상 1.00 → ≥0.93, 정상 30fps → ≥25, 정상 해독 1.0 → ≤1.3, 정상 간격 50ms → 최대 ≤250, 재생 머리 p95 ≤100 — 고장 300/400).
- Task 8개(0~7), 합계 약 **22.5시간**(0:3.5 · 1:2 · 2:4 · 3:2.5 · 4:4 · 5:1.5 · 6:2 · 7:3).
