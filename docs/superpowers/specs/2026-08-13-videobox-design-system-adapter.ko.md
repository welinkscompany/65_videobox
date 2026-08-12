# VideoBox 디자인 시스템 어댑터 명세

- 상태: 승인된 방향을 구현 계약으로 번역한 문서 (production UI 미변경)
- 작성일: 2026-08-13
- 기준 worktree/브랜치: `videobox-container-compatibility` / `codex/videobox-container-compatibility`
- 범위: VideoBox 데스크톱 제작 작업실의 shell, 자산·촬영본 화면, 편집기, 상태 화면과 시각 QA
- 비범위: Wave 2 semantic backend, 데이터 모델·API·렌더러, 기존 production 컴포넌트의 즉시 수정

이 문서는 Lean-AX intranet-style 정본을 VideoBox에 적용하기 위한 **어댑터 계약**이다. 값이 정본에 없으면 임의로 만들지 않고 `미확인`으로 남긴다. 이 문서 자체는 구현 계획이 아니며, 다음 UI 변경 때의 판단 기준과 검증 항목을 고정한다.

## 1. 근거와 현재 기준선

다음 승인 문서를 함께 읽고 이 계약을 해석한다.

- `docs/superpowers/specs/2026-08-12-videobox-creator-workspace-overhaul-design.ko.md`
- `docs/decisions/2026-08-12-creator-workspace-overhaul-direction.ko.md`
- `docs/decisions/2026-08-05-dashboard-white-orange-direction.ko.md`
- `docs/decisions/creator-workspace-visual-approval.ko.md`
- `docs/superpowers/plans/2026-08-12-videobox-wave2-footage-organizer.md`

현재 shell의 관찰 사실(어댑터가 이후 정리해야 할 drift 포함)은 다음과 같다.

- `apps/web/src/styles/product-shell.css`는 데스크톱 `[data-vb-desktop-shell]`을 최소 `1280×800`, `height:100vh`, `overflow:hidden`으로 제한한다.
- global nav, project switcher, stage navigation과 일반 버튼은 `min-height:40px`이다. 아이콘·접기·project-more만 `32px` 예외다.
- shell header는 `4.25rem`, sidebar는 펼침 `16rem`·접힘 `4rem`, 콘텐츠는 내부 `overflow-y:auto`다.
- `apps/web/src/styles/editor-workbench.css`는 toolbar/preview/timeline/dock를 viewport 안에 고정하고 각 영역을 내부 스크롤한다.
- 현재 구현은 `border:1px solid var(--vb-border)`와 여러 임의 rem radius를 사용한다. 이는 intranet 정본의 `ring`·radius 스케일과의 **확인된 drift**이며 이번 문서에서는 수정하지 않는다.
- `apps/web/src/ui-system.css`의 실제 색 값은 `:root`에만 있고 나머지는 semantic alias로 연결된다. 색 값을 다른 선택자에 복제하지 않는다.

## 2. 인트라넷 스타일 상속

| 정본 규칙 | VideoBox 적용 계약 |
|---|---|
| 페이지 루트는 `space-y-4` | 프로젝트/라이브러리/설정 등 일반 페이지의 루트 rhythm으로 상속한다. 편집기처럼 viewport 고정이 필요한 route는 아래 오버라이드를 따른다. |
| 기본 컨트롤 `h-8` | compact primitive의 기본값으로 상속한다. 셸과 편집기에는 전역으로 강제하지 않는다. 역할별 높이는 §3 참조. |
| 입력은 채워진 스타일 `rounded-2xl h-8 border-transparent bg-input/50` | **채워진 입력**을 검색·필터·대화 입력의 compact 변형에 상속한다. 흰 배경의 desktop 필드는 의미상 필요한 경우에도 `input` 토큰과 focus 링을 유지한다. |
| 표면 경계는 `ring-1 ring-foreground/5` | 카드·패널·행의 기본 표면으로 상속한다. 현재 `border` 구현은 drift로 기록하고 후속 UI 작업에서만 바꾼다. |
| 색은 `:root`/`.dark`의 실제 값, 그 외 `var()` alias | `--vb-*`와 shadcn semantic token을 매핑해 사용한다. `bg-red-500`, hex, 직접 `rgb()`를 화면 CSS에 쓰지 않는다. |
| radius는 `--radius` 하나에서 파생한 스케일 | `rounded-sm`부터 `rounded-4xl`까지 스케일만 사용한다. 32px 이하 요소의 pill 느낌은 의도된 결과다. |
| focus `ring-3 ring-ring/30` | 키보드 focus의 공통 시각 언어로 상속한다. 색만 바꾼 outline을 새로 만들지 않는다. |
| 배지 `h-4 min-w-4 text-[10px] bg-destructive` | 알림·카운트의 compact 기본으로 상속한다. 상태 의미는 색과 텍스트/아이콘을 함께 표현한다. |
| Dialog/AlertDialog는 grid + `[&>*]:min-w-0` | 긴 URL, 표, 에디터 콘텐츠를 담는 모든 dialog에 적용한다. 직계 자식 안전망과 중첩 wide-content의 명시적 `min-w-0`을 모두 점검한다. |
| dialog 최대 높이 `max-h-[88vh]`, 말줄임 `…`, 속성 라벨 `w-28` | 신규 primitive와 화면 템플릿의 정본으로 상속한다. 현재 `vb-dialog-content`의 `70vh`는 구현 관찰값이며 후속 drift 수정 대상이다. |

상속은 시각 언어와 semantic contract에 대한 것이다. Lean-AX의 모든 화면을 복사하거나 VideoBox의 MP4/타임라인 권한 모델을 변경한다는 뜻은 아니다.

## 3. VideoBox 오버라이드: 역할별 밀도

Creator 작업실은 일반 CRUD 인트라넷보다 재생·편집 조작이 많다. 따라서 `h-8`을 전역 규칙으로 밀어붙이지 않고 다음 역할별 높이를 사용한다.

| 역할 | 높이 계약 | 적용 예 | 이유/금지사항 |
|---|---:|---|---|
| 셸 40px | `40px` 이상 (`h-10` 상당) | global nav, 프로젝트 선택, 5단계 stage, header 주요 action, 일반 primary/secondary button | 승인 설계의 desktop 작업실 조작성. 셸을 `h-8`로 일괄 축소하지 않는다. |
| 조밀한 자산 행 | `32–36px` | 음악·효과음 waveform row, 촬영본 목록의 metadata row, import progress row, 작은 filter chip | 수천 개 자산 밀도 확보. 행 전체가 클릭 대상이면 텍스트 label·focus target을 보존하고 아이콘만 32px로 줄이지 않는다. |
| 에디터 컨트롤 40px 이상 | `40px+` | playback, timeline toolbar, mode tabs, inspector field/action, preview transport | 손가락/키보드 조작과 재생 위치의 정확성. timeline ruler/track의 시각 높이는 콘텐츠에 따라 별도이며 이 계약을 무시한 `h-8` 강제는 금지한다. |
| compact primitive | `h-8` | 입력, 작은 필터, badge 주변 action, table-level utility | intranet 상속값. 실제 클릭 대상이 40px이어야 하는 경우 wrapper/row hit-area를 사용한다. |
| icon-only/접기 | `32px` 이상 | sidebar collapse, overflow, transport icon | 반드시 accessible name과 tooltip을 제공한다. |

높이는 CSS selector의 이름보다 **사용자 역할**로 결정한다. 같은 `Button`도 셸은 40px, 자산 행의 utility는 32px, 에디터는 40px 이상일 수 있다.

추가 VideoBox 오버라이드:

- 데스크톱 작업실은 viewport 고정 + 영역별 스크롤을 우선한다. 페이지 전체가 자산 수만큼 길어지지 않는다.
- 정보 구조는 승인된 `프로젝트 → 기획 → 자산 → 편집 → 검토 → 출력`과 전역 `프로젝트/내 라이브러리/촬영본 정리/설정`을 유지한다.
- 자산 표현은 종류별로 다르게 한다: 영상은 썸네일 격자, 음악·효과음은 파형 목록, 가져오기는 진행 표, 촬영본 정리는 미리보기·파형·구간 타임라인이다.
- 흰색·주황색 제품 팔레트는 semantic token으로 유지한다. 장식용 gradient나 새 accent 색을 추가하지 않는다.
- 유진의 제안·미리보기·명시적 적용 경계는 UI 어댑터에서도 바꾸지 않는다. UI가 backend mutation을 직접 수행하지 않는다.

## 4. 토큰 계약

### 4.1 색

실제 색은 `:root`와 `.dark` 두 층에만 둔다. `--vb-canvas`, `--vb-panel`, `--vb-text`, `--vb-muted`, `--vb-accent`, `--vb-preview`, `--vb-success`와 `--background`/`--foreground`/`--primary` 계열을 semantic role로 사용한다. 컴포넌트 CSS는 `var(--vb-panel)` 또는 `var(--card)`처럼 alias만 참조한다.

금지:

- 화면 선택자 안의 hex, `rgb()`/`rgba()`, `bg-red-*`·`text-green-*` 같은 palette 직접 사용
- 상태를 색 하나로만 구분
- 기존 흰색·주황색 결정을 무시한 새 테마/gradient 추가

### 4.2 radius·surface·focus

- 기준 `--radius: .625rem`; sm~4xl 파생 스케일만 사용한다. rem 값을 selector마다 새로 발명하지 않는다.
- 표면은 `ring-1 ring-foreground/5`를 기본으로 하고, 선택·경고·오류는 semantic ring/배경을 추가한다.
- 입력은 채워진 `rounded-2xl h-8 border-transparent bg-input/50`가 기본이다. placeholder·disabled·error 상태도 배경/텍스트 대비를 유지한다.
- focus는 `ring-3 ring-ring/30` + 명확한 keyboard focus. `outline:none`만 남기는 규칙은 허용하지 않는다.

### 4.3 spacing·typography

- 페이지 기본 rhythm은 `space-y-4`; 관련 control gap은 8px, 기능 묶음 사이 gap은 16px 이상으로 둔다.
- shell의 현재 `1rem`/`1.5rem`/`2rem` padding과 `4.25rem` header는 baseline으로 기록하되, 새 값은 기존 token 또는 승인된 역할 token으로만 추가한다.
- 기본 글꼴은 현재 `Pretendard` stack을 유지한다. 제목·본문·metadata의 계층은 크기보다 weight/line-height와 label 명확성을 우선한다.

## 5. 프리미티브 계약

| primitive | 필수 규칙 | 상태/접근성 |
|---|---|---|
| Shell/Nav | 셸 40px row, active는 배경+텍스트/아이콘, sidebar collapse는 32px icon control | `nav` landmark, 현재 위치 `aria-current`, icon-only accessible name |
| Project switcher | 선택 row 40px, 이름 truncation은 `…`, overflow menu는 별도 32px control | 선택 상태를 `aria-pressed`/텍스트로 중복 표현 |
| Stage stepper | 5단계 고정, 현재 단계·다음 행동·차단을 텍스트와 아이콘으로 표시 | 색만으로 완료/주의/차단을 구분하지 않음 |
| Button/action | 역할별 높이(§3), 주 강조는 화면당 하나 | Enter/Space, disabled 이유, destructive 확인 |
| Filled Input | 위의 채워진 class contract, 오류는 label/help text와 연결 | `label`/`aria-describedby`, 검색 중 상태 표시 |
| Surface/Card | `ring-1 ring-foreground/5`, radius scale, `min-w-0` | 제목/설명 계층, 긴 텍스트 wrap |
| Asset row/grid | audio rows 32–36px, video card는 고정 preview ratio와 `min-w-0` | keyboard selection, 재생 상태와 라이선스/분석 상태 text |
| Toolbar/transport | editor controls 40px+, action order `미리보기 → 적용 → 취소` 일관 | tab order가 시각 순서와 일치, 재생 위치 announce |
| Timeline/track | 내부 scroll, playhead·boundary는 focusable, source truth 변경은 명시적 apply | frame-step 키보드 조작, 현재 시각/선택 구간 text 제공 |
| Inspector/dock | 오른쪽 dock는 제안·속성·이력을 분리, wide content에 `min-w-0` | 제안은 근거·영향·불확실성·적용 버튼을 포함 |
| Badge/status | compact badge 기본, 상태는 text/icon+semantic color | `aria-label`에 색 이름만 쓰지 않음 |
| Dialog | `grid`, `[&>*]:min-w-0`, `max-h-[88vh]`, viewport-safe width | 제목·description 연결, Escape/return focus, 긴 URL wrap |
| Empty/loading/error | §7의 독립 상태 컴포넌트 | 상태별 action과 재시도 가능 여부 명시 |

현재 CSS의 `border`/임의 radius는 이 표를 충족하지 않는 기존 구현으로 분류한다. 이 문서만으로 production CSS를 바꾸지 않는다.

## 6. 페이지 템플릿

| 템플릿 | 구성 | 고정 계약 |
|---|---|---|
| 프로젝트 목록/홈 | 프로젝트 카드, 최근 결과, `계속 만들기` 하나 | 목록은 `space-y-4`, 실패 프로젝트는 상태 확인으로 복구 |
| 프로젝트 작업실 | shell + 5단계 + 단계별 main | header와 주요 영역은 viewport 안, 긴 내용만 내부 scroll |
| 내 라이브러리 | 왼쪽 filter/collection, 가운데 검색 결과, 오른쪽 preview/meta | 영상 grid·오디오 waveform row·import table 분리 |
| 촬영본 정리 | 왼쪽 source list, 가운데 preview+파형/장면 timeline, 오른쪽 유진 제안 | 분할/결합은 preview 후 명시적 승인, 원본 불변 |
| 자체 편집기 | 왼쪽 script/assets, 가운데 preview, 오른쪽 inspector/history, 아래 timeline | 한 master timeline, preview surface 단일성, controls 40px+ |
| 검토/출력 | 내용·자막·화면·소리·자산 issue, 가로/세로 output card | 현재 revision freshness, 출력별 독립 성공/실패 |
| 설정 | 저장소·모델·출력·연결 상태 | 위험 변경은 대상명·확인·복구 안내 |

모든 템플릿은 성공 데이터만 전제하지 않는다. 첫 진입에서 empty, 진행 중 loading, 실패/error, 일부 완료/재시도 상태가 같은 구조 안에서 전환되어야 한다.

## 7. 상태 계약

### 빈 상태

무엇이 비어 있는지, 왜 비어 있는지, 다음 행동 하나를 짧게 보여준다. 예: `아직 등록한 음악이 없어요` + `음악 추가`. 빈 상태를 오류처럼 표현하거나 가짜 자산으로 채우지 않는다.

### 로딩/일부 완료

등록·분석·렌더의 현재 단계, 진행률/개수, 취소 가능 여부를 표시한다. 다중 작업은 완료·분석 중·중복·실패 수를 분리한다. 전체 페이지 spinner로 조작 가능한 영역을 가리지 않는다.

### 오류/재시도

오류에는 작업명, 데이터 안전 여부, 다음 행동을 함께 쓴다. 재시도는 실패 항목만 대상으로 하며 멱등성 키/중복 방지 상태를 숨기지 않는다. 원본 누락·지원하지 않는 형식·저장 공간 부족·renderer 연결 실패·stale revision은 각각 구체적인 해결 행동을 가진다.

### 저장/승인

`저장됨`·`저장 중`·`저장 실패`, `제안`·`미리보기`·`적용됨`을 서로 다른 상태로 렌더한다. 채팅의 동의 표현은 적용 승인이 아니다.

## 8. 접근성·반응형

- 모든 icon-only button은 accessible name과 tooltip을 가진다. keyboard focus가 보이지 않으면 완료로 보지 않는다.
- 선택/완료/주의/차단은 색상 외에 텍스트, 아이콘, ring 또는 shape 차이를 함께 제공한다.
- heading/landmark/label 순서를 유지하고, metadata는 화면 낭독에서도 대상과 값이 연결된다.
- 긴 한글·URL·파일명은 `overflow-wrap:anywhere` 또는 명시적 `min-w-0`으로 잘린 채 사라지지 않는다.
- desktop canonical viewport는 1280×800 이상이다. 1024px 미만은 mobile menu·내부 scroll로 축소하며, 모바일을 전문 편집기의 동등한 목표로 확장하지 않는다.
- `prefers-reduced-motion` 또는 shell의 reduced-motion 상태에서는 transition/scroll animation을 최소화한다.
- 키보드로 stage 이동, 자산 선택, playhead 이동, dialog Escape/return focus를 완료해야 한다.

## 9. ui-inspector/browser 시각 QA 루프

Lean-AX/control-room 성격의 화면은 코드만 보고 완료하지 않는다. 다음 루프를 화면 변경마다 수행한다.

1. 로컬 preview를 `preview_attach`/`preview_start` 또는 기존 Vite Browser/Playwright 세션으로 연다.
2. ui-inspector의 `enable_inspector`를 켜고 shell, stage row, asset row, editor toolbar, preview, dock, dialog를 실제로 선택한다.
3. 선택 결과의 `sourceLocation`, `computedStyles`, bounding rect, parent chain을 기록한다. source가 없으면 class/DOM으로 위치를 역추적한다.
4. 다음 축을 확인한다: panel weight, row height, icon baseline, label truncation, metadata wrapping, spacing rhythm, focus ring, internal scroll, dialog overflow, empty/loading/error action.
5. 변경 후 동일 viewport를 다시 렌더하고 `preview_screenshot` 또는 Playwright snapshot으로 전후를 비교한다.
6. `preview_errors`/browser console, API/network, build와 focused test를 확인한다. 시각 확인 없이 snapshot hash나 computed style만으로 완료 선언하지 않는다.

기준 viewport는 현재 E2E와 일치시킨다: `1920×1080`, `1440×960`, `1280×800`, `768×1024`, `390×844`. 이번 문서 작성에서는 live preview를 실행하지 않았으므로 브라우저 결과는 **미검증**이다.

## 10. 향후 자동화 설계 계약

이 절의 규칙은 후속 구현에서 지켜야 할 **자동화 계약**이다. 문서 계약, 토큰 정적 검사, 렌더·접근성·브라우저 검증을 서로 대체하지 않고 함께 사용한다.

다음 검사를 production UI를 수정하는 후속 작업에서 점진적으로 추가한다.

- **문서 계약**: 이 파일의 상속/오버라이드, `h-8` 전역 강제 금지, 역할별 높이, 네 가지 상태, ui-inspector QA 용어를 읽기 전용 pytest로 확인한다. 현재 `tests/test_videobox_design_system_adapter_contract.py`가 이 최소 계약을 고정한다.
- **토큰 정적 검사**: `:root`/`.dark` 밖의 literal color를 거부하고, 화면 CSS가 semantic `var()`만 참조하는지 검사한다. product-shell/editor-workbench의 기존 border/radius drift는 별도 allowlist로 추적한 뒤 migration 때 제거한다.
- **primitive contract test**: rendered shell control이 40px, dense asset row가 32–36px, editor control이 40px 이상인지 role/data attribute 기준으로 확인한다. 모든 filled input, focus ring, surface ring, dialog `[&>*]:min-w-0`도 함께 확인한다.
- **state/accessibility test**: 템플릿별 empty/loading/error/retry와 landmark, accessible name, keyboard focus/return focus, reduced-motion을 Vitest/Testing Library로 확인한다.
- **browser visual gate**: 고정 clock과 위 five viewport Playwright snapshot, console/network 오류 0, internal scroll/overflow assertions를 함께 실행한다. snapshot만 초록이어도 ui-inspector/browser 수동 확인 gate는 남는다.
- **ui-inspector ontology**: `query_ontology`/`validate_design`로 row/card rhythm, hierarchy, focus, target size를 점검하고 annotation이 생기면 `annotation_list → 수정 → annotation_resolve` 순서를 지킨다.

자동화는 디자인 토큰과 렌더 계약을 검증할 뿐, owner가 프로젝트 생성부터 등록·정리·편집·검토·가로/세로 출력·재생을 끝냈다는 뜻이 아니다. 실제 owner acceptance는 Wave별 별도 gate다.

## 11. 적용 체크리스트와 금지선

- [ ] 현재 화면 유형과 템플릿을 먼저 선택했는가
- [ ] `h-8`을 기본으로 삼되 셸 40px·자산 행 32–36px·에디터 컨트롤 40px+ 예외를 역할로 설명했는가
- [ ] 입력이 채워진 스타일이고 surface가 ring 기반인가
- [ ] 색이 root/dark token과 semantic alias만 사용하는가
- [ ] radius가 `--radius` 스케일인가
- [ ] dialog가 grid + `[&>*]:min-w-0` + 88vh 계약을 가지는가
- [ ] empty/loading/error/retry와 keyboard focus를 확인했는가
- [ ] ui-inspector/browser 전후 시각 QA와 자동 검증 결과를 분리해 기록했는가

다음 변경은 이 어댑터 범위를 벗어나므로 별도 승인 없이 하지 않는다.

- Wave 2 semantic backend/API/DB/schema 변경
- 유진 권한 경계, 자동 적용, 파일/DB/셸/renderer 접근 확대
- CapCut을 정상 제작의 필수 종착점으로 되돌리는 UI 흐름
- 모바일 전문 편집기, 새 브랜드 색, 장식용 gradient, global `h-8` 강제
- 시각 QA 없이 production CSS를 일괄 치환하는 작업
