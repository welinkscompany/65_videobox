# 편집기 화면 구역 정리 규칙 (계획 L, 2026-10-10)

> **이 문서를 읽는 사람:** 구현 에이전트입니다. 대표님이 읽는 문서가 아닙니다.
> 대표님께 보여 줄 말은 `§1`의 "한 줄 역할 이름"만 가져다 쓰세요.
>
> **이 문서가 하는 일:** 계획 I(`docs/superpowers/plans/2026-10-08-design-system-and-wiring-i.ko.md`)가 정한
> 토큰·부품 규격·D1~D5를 **편집기 화면의 구역 단위로 구체화**합니다. 새 색·새 글자 크기·새 단추 크기를 만들지 않습니다.
> 계획 I Task 10(편집기 크롬 정리)을 이 문서의 Task L0~L8이 **대신합니다.** I Task 10을 따로 돌리지 마세요.

## 0. 먼저 알아 둘 사실 (확인한 것 / 추정)

| # | 사실 | 근거 | 확인 여부 |
|---|---|---|---|
| 0-1 | 계획 I는 **아직 한 Task도 돌지 않았습니다.** `primitives.css`·`--vb-control-*`·`--vb-weight-*`·`data-primary-action`이 소스에 0개입니다 | `grep -r "--vb-control-\|data-primary-action" apps/web/src` → 0 | 확인 |
| 0-2 | 지금 `ui-system.css`의 글자 토큰 **값은 옛 값**입니다: `xs 10 · sm 12 · md 14 · lg 16 · xl 20 · 2xl 28 · 3xl 40` (`ui-system.css:101-107`). 이 문서의 글자 규칙은 계획 I 새 값(`xs 11 · sm 12 · md 13 · lg 14 · xl 16 · 2xl 20 · 3xl 24`)을 전제로 씁니다 | 파일 읽음 | 확인 |
| 0-3 | 그래서 **선행 조건**이 있습니다: 계획 I **Task 2(토큰)·Task 4(부품 규격 `primitives.css`)** 가 main에 있어야 이 문서 L1 이후를 시작합니다. Task 3(정적 가드)은 권장, 필수 아님 | 0-1, 0-2 | 판단 |
| 0-4 | 계획 I Task 4 목록 중 `dialog.tsx`의 `Close`→`닫기`는 이미 끝났습니다(`615fee8c8`). I Task 4를 돌릴 때 그 줄은 건너뜁니다 | `git log` | 확인 |
| 0-5 | 팔레트: 중립 회색 그대로 + 포인트 `--vb-accent #9EC0F7`, 깔린 면 `--vb-accent-bg #1A2436`, 테두리 `--vb-accent-border #3A4F73`, 채운 단추 글자 `--primary-foreground #0B1020`. 살구색은 "주의" 전용이고 토큰이 아직 없습니다(`docs/decisions/2026-10-10-accent-color-blue.ko.md`). **이 문서는 색 값을 하나도 바꾸지 않습니다** | 결정 문서 | 확인 |
| 0-6 | 편집기의 큰 구역은 이미 "바탕 `--card`(#202024) + 1px `--border` + 모서리 md"로 그려집니다(`editor-workbench.css:19`). 화면 바닥은 `--vb-panel`(#18181B, `product-shell.css:9`) | 파일 읽음 | 확인 |
| 0-7 | 계획 I 기준선(2026-10-08, H 이전) 편집기: 컨트롤 192개, 높이 7종(32×125·36×22·30×15·23×13·25×7·40×6·27×3), 글자 4종+(12·14·10·13.33), Arial 66, 채운 단추 38. **H 이후 값은 아직 아무도 다시 재지 않았습니다** — L0이 잽니다 | 계획 I "실측 기준선" | 옛 값 확인, 지금 값 미측정 |
| 0-8 | `default` 변형(채운 파랑)인 `<Button>`: 편집기 파일 중 `variant`를 적지 않은 것이 한 줄 grep으로 약 40개(YujinPanel 16·InspectorControls 10·EditorAssetBrowser 4 …). 여러 줄로 쓴 태그는 이 셈에 안 잡혀 **실제 수는 다를 수 있습니다** | 한 줄 grep | 추정 |

---

## 1. 편집기 구역 지도와 한 줄 역할 이름

1280×720 그림(`docs/superpowers/audit-evidence/2026-10-10-blue/editor-742.png`) 기준 배치입니다.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ A 상단바  ← VideoBox  프로젝트/…/편집  [프로젝트 이름]  이야기|편집|확인과 내보내기  작업 상태 ≡ │
├──────────────────────────────────────────────────────────────────────────────┤
│ B 편집 도구줄                                          [세부 정보][내보내기][접기] │
├────┬──────────────────┬──────────────────────────────────────┬──────────────┤
│ C  │ D 자산 패널       │ E 미리보기                            │ F 편집 항목   │
│ 레일│ (미디어·오디오…)  │  영상 + 재생줄                         │ (열었을 때만) │
│    │                  │                         [유진] ← I     │              │
├────┴──────────────────┴──────────────────────────────────────┴──────────────┤
│ G 가로·세로 비교 (접힌 띠)                                    [펼치기]        │
├─ 높이 손잡이 ─────────────────────────────────────────────────────────────────┤
│ H 타임라인  H1 머리줄: 제목·요약 · 되돌리기·다시·자르기·붙이기·빼기·복사 ··· − + 전체 │
│            H2 트랙 머리(잠금·숨기기·소리) │ H3 눈금 + 클립                       │
└──────────────────────────────────────────────────────────────────────────────┘
```

| 기호 | 구역 | 한 줄 역할 이름(대표님 말) | 코드 뿌리 |
|---|---|---|---|
| A | 상단바 | **지금 어느 영상의 어느 단계인지 보고, 단계를 옮기는 줄** | `features/shell/TopBar.tsx`, `app/ProductShell.tsx:117-134` |
| B | 편집 도구줄 | **오른쪽 칸을 열고, 다 만든 영상을 내보내는 줄** | `EditorWorkbench.tsx:641-693` |
| C | 도구 레일 | **왼쪽 칸에 무엇을 펼칠지 고르는 세로 띠** | `EditorWorkbench.tsx:709-725` |
| D | 자산 패널 | **영상에 넣을 재료를 찾고 더하는 칸** | `assets/EditorAssetBrowser.tsx` (`dock("left")`, `EditorWorkbench.tsx:585`) |
| E | 미리보기 | **지금까지 편집한 결과를 틀어 보는 칸** | `preview/preview-stage.tsx:403-451` |
| F | 편집 항목 | **고른 장면 하나를 고치는 칸** | `workbench/RightDock.tsx:85-144`, `inspector/InspectorControls.tsx` |
| G | 가로·세로 비교 | **가로 영상과 세로 영상을 맞춰 보는 띠** | `EditorWorkbench.tsx:786-796` |
| H | 타임라인 | **장면 순서와 길이를 자르고 옮기는 판** | `timeline/TimelineDock.tsx:1194-1390` |
| H1 | 타임라인 머리줄 | 편집 도구(되돌리기·자르기 등)와 보기 크기 | `TimelineDock.tsx:1194-1212` + `EditorWorkbench.tsx:471-475` |
| H2 | 트랙 머리 | 트랙마다 잠그기·숨기기·소리 끄기 | `TimelineDock.tsx:1216-1264` |
| I | 유진 | **말로 편집을 시키는 창**(떠 있는 표면) | `workbench/YujinPanel.tsx` |

규칙 적용 단위는 **구역(A~I)** 입니다. H1·H2는 구역 H 안의 "줄"이며 따로 구역이 아닙니다.

---

## 2. 구역 공통 규칙

### 2-1. 구역을 무엇으로 나누나 — **구역 사이는 바탕 단계 + 틈, 구역 안은 선 또는 간격**

| 경계 | 쓰는 것 | 쓰지 않는 것 |
|---|---|---|
| 화면 바닥 ↔ 구역 | 바탕 단계: 바닥 `--vb-panel`(#18181B) 위에 구역 `--card`(#202024). 구역 사이 **틈 8px** | — |
| 구역 바깥 테두리 | **지금 있는 1px `--border` + 모서리 md를 그대로 둡니다** | 테두리를 새로 더 굵게·밝게 |
| 구역 안의 묶음 ↔ 묶음 | 간격 8px, 필요하면 **1px `--border` 가로선 하나** | 묶음마다 상자(테두리+모서리) 두르기 |
| 미리보기 영상 칸 | 한 단계 더 어두운 `--vb-preview`(#0B0B0C) 바탕만 | 영상 칸에 또 테두리 |
| 떠 있는 표면(대화상자·메뉴·유진 창·단축키 안내) | 계획 I 그대로: 고리 그림자 `--vb-surface-ring` + 그림자 | — |

근거:
1. **색이 이미 세 단계로 승인돼 있습니다**(바닥·구역·미리보기). 같은 일을 선으로 또 하면 그림에서 보이듯 "상자 안 상자"가 됩니다(미리보기 구역 테두리 안에 영상 칸 테두리, 자산 패널 테두리 안에 단추마다 고리).
2. **바깥 테두리를 지우지 않는 이유:** #18181B와 #202024는 밝기 차이가 아주 작습니다(대비 약 1.1:1, 손 계산값). 값싼 모니터에서는 바탕 단계만으로 구역이 녹을 수 있습니다. 계획 I 대조표도 "화면 안 카드·패널은 지금처럼 `1px solid var(--vb-border)`"로 정했습니다. 그대로 따릅니다.
3. 구역 **안**에서는 선을 아낍니다. 선이 많으면 대표님 눈에는 전부가 같은 무게의 칸으로 보입니다 — 지금 "구역 구분이 안 된다"는 말의 원인으로 판단합니다(추정, L8 그림 비교로 확인).

### 2-2. 수치 (편집기 전용 별칭, `.vb-editor-workbench`에 정의 — 새 토큰 값이 아니라 기존 토큰의 별칭)

| 별칭 | 값 | 쓰는 자리 |
|---|---|---|
| `--vb-region-gap` | `var(--vb-space-2)` (8px) | 구역과 구역 사이 틈(가로·세로 모두). 지금 세로 12(`editor-workbench.css:18`)·가로 8(`:70`)로 다르다 → 8로 하나 |
| `--vb-region-pad` | `var(--vb-space-2)` (8px) | 구역 안쪽 여백 사방. 지금 8·12·16·20이 섞여 있다(`:20`, `:102`, `:240`, `:461`) |
| `--vb-region-head-h` | `var(--vb-control-md)` (32px) | 구역 제목 줄 높이(최소) |
| 묶음 사이 | `var(--vb-space-2)` (8px) | 구역 안 묶음 간격 |
| 항목 사이 | `var(--vb-space-1)` (4px) | 같은 줄 단추·칩 사이 |

**답답하면 바꿀 손잡이는 `--vb-region-pad` 하나뿐입니다**(8 → 12). 구역마다 예외 값을 만들지 마세요.

### 2-3. 구역 제목 줄 모양

```
[제목 14/600] [메타 11/400 흐림, 한 줄 말줄임 ……………]        [구역 동작들 →]
└──────────────── 높이 32px 이상, 한 줄, 아래 선 없음 ────────────────┘
```

- 제목: `--vb-text-lg`(14) / `--vb-weight-strong`(600) / `--vb-text`. **한 줄**입니다. 눈썹 글자(제목 위 작은 글자)를 두지 않습니다.
- 메타(요약·상태): `--vb-text-xs`(11) / 400 / `--vb-muted`, `min-width:0` + 말줄임. 제목 바로 오른쪽.
- 구역 동작: 오른쪽 끝(`margin-left:auto`). 아이콘 단추면 28, 글자 단추면 보조 28. **이 줄 안 단추 높이는 하나**(§3-3 "한 줄 한 높이").
- 제목 줄과 몸통 사이에는 선을 긋지 않고 간격 4px.
- 제목 줄이 **없는** 구역: B 편집 도구줄, C 레일(띠 자체가 이름표), D 자산 패널(레일에서 고른 이름이 제목 역할 — 대신 종류 탭 줄이 맨 위), A 상단바(위치 줄). B 편집 도구줄은 제목을 숨긴 채 접힌 기본 상태라 같은 취급입니다. 이 넷 말고는 다 제목 줄이 있습니다.

| 구역 | 제목 | 메타 | 오른쪽 동작 |
|---|---|---|---|
| B 편집 도구줄 | (접힘 기본, 제목 숨김 — 지금 동작 유지) | — | 세부 정보 · **내보내기** · 접기 |
| E 미리보기 | `편집 결과` / `원본 보기`(지금 글자 그대로) | `편집본` / `원본`(지금 눈썹 글자를 메타로 내림) | `편집본으로 돌아가기`(원본 볼 때만) |
| F 편집 항목 | `편집 항목` | `2.00–5.00초 구간` / `선택한 구간이 없어요.` | — |
| G 가로·세로 비교 | `가로·세로 비교` | 알림 한 줄(`variantNotice`) | `펼치기`/`접기` |
| H 타임라인 | `타임라인` | `트랙 1개 · 캡션 15개 · …` | 편집 도구 여섯 · 보기 크기 셋 |
| I 유진 | `유진` | — | 닫기 |

---

## 3. 단추 위계 — 세 단계와 "선택 무늬"

### 3-1. 세 단계

| 단계 | 모양(이미 있는 변형) | 크기(계획 I 크기 계약) | 글자 | 쓰는 자리 |
|---|---|---|---|---|
| **주요** | `variant="default"` = 채운 `--vb-accent`, 글자 `--primary-foreground` | 편집기 `size="sm"`(28) · 대시보드 화면 머리 `lg`(32) · 대화상자 바닥 `lg`(32) | `--vb-text-sm`(12)/500 | **편집기 화면 전체에 하나: `내보내기`.** 떠 있는 표면(대화상자·유진 창)은 표면마다 하나 더 허용 |
| **보조** | `variant="outline"` | 기본 `sm`(28), 촘촘한 줄 안에서는 `xs`(24) | 12/500 | 구역의 글자 단추 전부. 구역 대표 행동도 보조입니다 |
| **아이콘** | `variant="ghost"` + `size="icon-*"`, 또는 날 것 `<button data-native-control>`에 같은 모양을 CSS로 | 구역 제목 줄·타임라인 머리줄 `icon-sm`(28) · 트랙 머리·재생줄·눈금 근처 `icon-xs`(24) | 아이콘 `--vb-icon-sm`(14) | 뜻이 그림으로 통하는 동작(재생·되돌리기·자르기·잠금·확대) |

- **아이콘 단추는 반드시 `aria-label` + `title`**(툴팁). 지금 편집기 아이콘 단추는 거의 다 있습니다 — 새로 만드는 것만 지키면 됩니다.
- `ghost`는 이제 안전합니다: `product-shell.css:221`이 Preflight 없는 빌드에서도 바탕을 투명으로 고정합니다. `EditorWorkbench.tsx:648-651` 주석("ghost를 쓰지 않는다")은 **그 고정 이전 기록**이라 낡았습니다. L3에서 주석을 고칩니다(추정: 2026-08-31 이후 고정. L2에서 `getComputedStyle` 바탕이 `rgba(0,0,0,0)`인지 재서 확인).
- **"구역 대표 행동"** 은 채우지 않습니다. 대신 ① 구역 제목 줄 오른쪽 또는 구역 맨 위 첫 자리에 두고 ② 아이콘+글자로 씁니다. 이것이 계획 I Task 10의 시험 `편집기에서 채운 단추는 내보내기 하나다`와 "영역당 핵심 행동 하나"(D2)를 함께 지키는 방법입니다.

### 3-2. 선택 무늬 (단계가 아니라 **상태**)

지금 편집기에서 채운 파랑이 "누르라"는 뜻(주요)과 "지금 여기"라는 뜻(선택)을 같이 하고 있습니다. 그림에서 채운 파랑이 넷(`미디어` 레일, `편집` 단계, `유진`, 열린 `세부 정보`)이고 그중 주요 동작은 하나도 아닙니다. 그래서 선택은 따로 그립니다.

| 상태 | 모양 | 붙이는 속성 |
|---|---|---|
| 선택됨 / 눌림 / 현재 위치 | 바탕 `--vb-accent-bg`, 안쪽 고리 1px `--vb-accent-border`, 글자·아이콘 `--vb-accent` | `aria-selected="true"`(탭) · `aria-pressed="true"`(켜고 끄기) · `aria-current="step"`/`"page"`(위치) |
| 선택 안 됨 | 그 단추의 원래 단계 모양(보통 `ghost`/`outline`) | 같은 속성 `false` |

- 선택을 `variant={active ? "default" : "outline"}`로 그리지 않습니다. **변형은 고정하고 aria 상태가 모양을 바꿉니다.** CSS 한 규칙(`L1`)이 맡습니다.
- **색만으로 구분하지 않는다(검토에서 추가).** `#1A2436`은 구역 바탕 `#202024`와 밝기 차가 작아서(손 계산 약 1.1:1) 선택 상태가 **테두리 1px와 글자색**에만 의존합니다. 세로 레일(`C`)과 단계 띠(`A`)의 선택에는 **굵기 600**을 더하지 말고(폭이 변해 흔들림) 대신 안쪽 고리를 **2px**로 합니다. L1 시험에 "선택 무늬 고리 ≥ 1px" 단언을 두고, L2b·M1 그림에서 레일 선택이 안 보이면 2px로 올립니다(§7-1 같은 줄의 대비책과 같은 조치).
- 대비: `#9EC0F7` 글자 on `#1A2436` = **약 8.4:1**(제 손 계산값 — L1에서 `contrast.test.ts`에 시험으로 고정해 재확인). 계획 I Task 8의 "깔린 면 위 포인트 글자 금지"는 **오렌지 시절 4.27:1** 때문이었고, 파스텔 파랑에서는 그 이유가 없어졌습니다. 시험이 4.5 미만을 내면 글자만 `--vb-text`로 바꾸고 멈추세요.

### 3-3. 줄 규칙 둘

1. **한 줄 한 높이.** 같은 가로줄 안의 단추·칩·입력은 높이가 하나입니다(예: 타임라인 머리줄은 전부 28, 트랙 머리는 전부 24).
2. **같은 성격의 고르기는 같은 무늬.** 서로 배타인 고르기(종류·방향·보기 방식·속도 미리값·가로/세로)는 **분절 무늬**(계획 I 탭 목록 규격: 높이 28, 안쪽 2px, 선택 = 선택 무늬)로 하나입니다. 알약 칩(`border-radius:999px`)은 **지울 수 있는 표지**(예: `유진 추천에서 뺀 것`의 만든이 칩)에만 씁니다.

### 3-4. 지금 화면에서 누가 무엇이 되나 (구체 지정)

| 구역 | 주요 | 구역 대표 행동(보조, 첫 자리) | 선택 무늬로 바꿀 것 | 나머지 |
|---|---|---|---|---|
| A 상단바 | 없음 | 없음 | `이야기·편집·확인과 내보내기` 중 지금 단계(`TopBar.tsx:181`) | `작업 상태`(`ProductShell.tsx:133`)·프로젝트 고르기·뒤로·≡ = 보조 28 / 아이콘 28 |
| B 편집 도구줄 | **`내보내기`**(`EditorWorkbench.tsx:689`) — 아이콘+글자 `내보내기`, `size="sm"`, `data-primary-action` | — | `세부 정보`가 열렸을 때(`:671`) | `접기`(`:692`) 아이콘 28 ghost |
| C 레일 | 없음 | 없음 | 지금 펼친 탭(`:713-723`) — `variant="ghost"` 고정 + `aria-selected` | — |
| D 자산 패널 | 없음 | **`파일 추가`**(`features/media/AddMediaFiles.tsx`가 그림) | 종류 탭(`EditorAssetBrowser.tsx:415-416`), 방향(`:418-419`), 보기 방식(`:425-427`) | `내레이션·촬영본·인포그래픽·모션·자료실에서 가져오기`(`:337-356`) = 보조 28. 두 묶음으로: **가져오기**(파일 추가·촬영본·자료실에서 가져오기) / **만들기**(내레이션·인포그래픽·모션), 묶음 이름표 11px 흐림 |
| E 미리보기 | 없음 | **재생/일시정지** 아이콘 28(가운데) | `반복`·`음소거`·`전체화면`의 켜짐 상태(이미 `aria-pressed` 있음) | 이전/다음 프레임·음소거·반복·전체화면 = 아이콘 24, `단축키` = 보조 24, `재생 빠르기` 선택 상자 24 |
| F 편집 항목 | 없음 | **`선택 구간 미리보기`**(`RightDock.tsx:107-116`) | `영상·소리 / 캡션 / 화면 요소` 바로가기(`:117-125`) → 분절 무늬, 속도 미리값(`InspectorControls.tsx:794`) → 분절 | 안의 글자 단추 전부 보조 28 |
| G 가로·세로 비교 | 없음 | `펼치기`/`접기`(`:787`) 보조 28 | 마스터/가로/세로 고르기(`variants/VariantSelector.tsx:24`) → 분절 | — |
| H 타임라인 | 없음 | 없음(편집 도구는 전부 같은 무게) | 트랙 잠금·숨기기·소리(이미 `aria-pressed`) | H1 편집 도구 여섯 = 아이콘 28 ghost(지금 `outline size="icon"` 32, `EditorWorkbench.tsx:446-458, 472-474`), 보기 크기 `− + 전체` = 아이콘 28 / 보조 28(`TimelineDock.tsx:1208-1210`). H2 = 아이콘 24 |
| I 유진(떠 있는 표면) | **`요청 보내기`**(`YujinPanel.tsx:497`) — 창이 열렸을 때만 보임 | — | — | 닫힌 알약 `유진`(`:253`) = 보조 + 포인트색 아이콘(이미 `editor-workbench.css:135`). 나머지 열두 남짓 채운 단추(`:336, 357, 393, 397, 439, 444, 459, 499, 518, 523, 526, 529`) = 보조 |

> 유진 창 예외는 계획 I Task 10 시험 문장을 **좁힙니다**: "유진 창이 닫힌 편집기에서 채운 단추는 `내보내기` 하나다". 대화상자 안 주요 단추와 같은 이유(떠 있는 표면은 그 자체가 한 영역)입니다. 계획 I와 모순이 아니라 범위를 적은 것으로 판단합니다 — 검토자가 아니라고 보면 `요청 보내기`도 보조로 내리면 됩니다(한 줄).

---

## 4. 글자 규칙 — 어느 요소가 어느 토큰인가

값은 계획 I 새 척도입니다(0-2·0-3). 굵기는 400/500/600 셋뿐(650·700·750 금지).

| 요소 | 토큰 | px/굵기 | 편집기 예 |
|---|---|---|---|
| 구역 제목 | `--vb-text-lg` | 14/600 | `타임라인`, `편집 결과`, `편집 항목`, `가로·세로 비교`, `유진` |
| 항목 이름(카드 제목·고른 장면 이름) | `--vb-text-md` | 13/600 | 자산 카드 제목(`EditorAssetBrowser.tsx:505` `h3`), `고른 장면`(`InspectorControls.tsx:549` `h3`) |
| 본문·단추 글자·입력·선택 상자·탭 | `--vb-text-sm` | 12/400(본문) · 12/500(단추·탭) | 검색칸, `파일 추가`, 종류 탭, 유진 대화 본문 |
| 라벨·메타·도움말·배지·레일 이름·클립 이름·눈금 숫자·트랙 이름·잠긴 이유 | `--vb-text-xs` | 11/400 (레일 이름·트랙 이름 500) | `트랙 1개 · …`, `적용 구간: 0.00–5.00초`, `미디어`, `영상 1`, `10s`, `내레이션` |
| 숫자 칸(시간·길이·배속) | 위 크기 그대로 + `font-variant-numeric: tabular-nums` | — | `타임라인 0.0 / 120.0초`, `1배` |
| 쓰지 않음 | `--vb-text-xl`(16)·`2xl`(20)·`3xl`(24) | — | 편집기 안에는 화면 제목이 없습니다(상단바가 위치를 말함) |

목표: 편집기에서 보이는 글자 크기 종류 **⊆ {11, 12, 13, 14}**(4종 이하), 굵기 **⊆ {400, 500, 600}**, 글꼴 Pretendard만(Arial 0).

---

## 5. 지금 어긋난 곳 (파일:줄, 2026-10-10 main `c514d40b0` 기준)

줄 번호는 이 커밋 기준입니다. 고칠 때는 줄 번호가 아니라 **문자열 앵커**로 찾으세요(계획 I Global 규칙과 같음).

| # | 자리 | 무엇이 어긋났나 | 고칠 방향 | 맡는 Task |
|---|---|---|---|---|
| 1 | `EditorWorkbench.tsx:713-723` | 레일에서 고른 탭이 `variant="default"`(채운 파랑) — 선택이 주요 단추처럼 보임 | `variant="ghost"` 고정 + `aria-selected`가 선택 무늬를 받음 | L3 |
| 2 | `EditorWorkbench.tsx:671` | `세부 정보`가 열리면 채운 파랑 | `outline` 고정 + `aria-pressed` | L3 |
| 3 | `EditorWorkbench.tsx:689` | 편집기 유일의 진짜 주요 동작 `내보내기`가 가장 조용한 아이콘 outline 단추 | 아이콘+글자 `내보내기`, `variant="default" size="sm" data-primary-action` | L3 |
| 4 | `features/shell/TopBar.tsx:181` | 지금 단계(`편집`)가 채운 파랑 — 상단바에 주요 동작이 있는 것처럼 보임 | `outline` 고정 + `aria-current="step"` | L1 |
| 5 | `preview-stage.tsx:447` + `editor-workbench.css:535-536, 556` | 재생줄 날 것 단추에 모양 규칙이 없어 **브라우저 기본 회색 상자**(그림의 `◀ \| 재생 / 일시정지 \| ▶ 음소거 반복 전체화면`). 글자 기호 `◀｜`·`｜▶` | 날 것 단추는 그대로 두고(시험 `task22-parity-owners.test.ts:88-90` 목록 유지) CSS로 아이콘 단추 모양. 글자를 lucide 아이콘(`SkipBack`·`Play`/`Pause`·`SkipForward`·`Volume2`/`VolumeX`·`Repeat`·`Maximize`)으로, `aria-label` 그대로 | L2(CSS)·L5(TSX) |
| 6 | `preview-stage.tsx:404` + `editor-workbench.css:279-280` | 미리보기 머리가 **두 줄**(눈썹 `편집본 미리보기` + 제목 `편집 결과`), 눈썹 굵기 700 | 한 줄 제목 줄(§2-3). 눈썹 글자는 메타로 | L2·L5 |
| 7 | `EditorAssetBrowser.tsx:327-356` + `editor-workbench.css:376-377` | 같은 무게 단추 여섯이 `flex:1 1 auto`로 늘어나 **폭이 제각각**(그림: `파일 추가`·`내레이션`·`촬영본`·`인포그래픽` / `모션`·`자료실에서 가져오기`) | 묶음 둘(가져오기/만들기) + 이름표, 늘리지 않음(`flex:0 0 auto`), 보조 28 | L2·L4 |
| 8 | `EditorAssetBrowser.tsx:415-428` + `editor-workbench.css:364-365` | 한 칸에 고르기 무늬 셋: 밑줄 탭(`전체·영상·그림`), 고리 알약(`모든 방향·가로·세로`), 알약 토글(`격자로 보기·줄로 보기`) | 종류 = line 탭, 방향 = 분절, 보기 방식 = 아이콘 단추 둘(`LayoutGrid`·`List`, 이름 `격자로 보기`·`줄로 보기` 유지 — 프로젝트 목록과 같은 모양) | L2·L4 |
| 9 | `EditorWorkbench.tsx:446-458, 472-474` vs `TimelineDock.tsx:1208-1210` + `editor-workbench.css:568-569` | 타임라인 머리 **한 줄에 단추 체계 둘**: 편집 도구는 shadcn `outline size="icon"`(32), 보기 크기는 날 것 단추에 자체 규칙(`min-width:1.75rem`, 바탕 `--background`) | 한 줄 한 높이 28: 편집 도구 `ghost size="icon-sm"`, 보기 크기 날 것 단추에 같은 모양 CSS. `−`·`+` 글자를 `ZoomOut`·`ZoomIn` 아이콘으로 | L2·L3·L6 |
| 10 | `TimelineDock.tsx:1230-1260` + `editor-workbench.css:684` | 트랙 머리 단추(24, 크기는 맞음)가 브라우저 기본 회색 바탕(그림) | 아이콘 24 ghost 모양, 켜짐 = 선택 무늬 | L2 |
| 11 | `editor-workbench.css:18` vs `:70` | 구역 사이 틈이 세로 12·가로 8로 다름 | `--vb-region-gap` 8 하나 | L2 |
| 12 | `editor-workbench.css:20, 102, 240, 461` | 구역 안쪽 여백이 8/12, 12/16, 12/16, 16/20으로 넷 | `--vb-region-pad` 8 하나 | L2 |
| 13 | `editor-workbench.css:453-462, 472` + `EditorWorkbench.tsx:786-787` | 가로·세로 비교 띠만 여백 16/20·간격 16, 제목 크기 별도. 그림에서 접힌 띠가 약 40px + 그 밑 회색 굵은 막대 | 제목 줄 규칙(32px), 여백 8 | L2 |
| 14 | `editor-workbench.css:577` + `EditorWorkbench.tsx:797-803` | 타임라인 높이 손잡이가 8px 회색 알약 막대 — 그림에서 **구역 하나처럼 보임** | 보이는 선은 2px `--border`(위아래 투명 여백으로 누를 자리 8px 유지), 마우스 올리면 `--vb-border-strong` | L2 |
| 15 | `editor-workbench.css:54-58` | `.vb-product-shell .vb-editor-workbench [data-slot="button"]`(특정도 0,3,0)이 단추 여백·글자·굵기를 덮어씀 — 계획 I `primitives.css` 크기 계약을 이깁니다 | 지움(primitives가 맡음). 지운 뒤 높이 집합을 잼 | L2 |
| 16 | `editor-workbench.css:280, 350, 489, 645` | 굵기 700 넷(척도 밖) | 600 또는 500 | L2 |
| 17 | `editor-workbench.css:100` | 레일 아이콘 20px(`1.25rem`) — 아이콘 척도(12/14/16/24) 밖 | `--vb-icon-md`(16) | L2 |
| 18 | `EditorWorkbench.tsx:709` vs `EditorAssetBrowser.tsx:314` | `aria-label="왼쪽 패널"` 탭 목록이 둘(계획 I Task 10이 이미 지적) | 레일을 `편집 도구`로 | L3 |
| 19 | `RightDock.tsx:117-125`, `InspectorControls.tsx:794`, `variants/VariantSelector.tsx:24` | 배타 고르기가 `outline+aria-pressed` / `default↔outline` / `default↔outline`으로 셋 다 다름 | 분절 무늬 + 선택 무늬 | L7b |
| 20 | `YujinPanel.tsx:253, 336 …529` | 변형을 안 적어 **채운 파랑 13개 안팎**(창 열면 한 화면에 여러 개) | `요청 보내기`만 주요, 나머지 `outline` 명시 | L7a |
| 21 | `InspectorControls.tsx:557-1029`(약 10곳), `TranscriptPanel.tsx`·`ScriptPane.tsx`·`AutoCaptionCard.tsx`·`VariantServerControls.tsx`·`VariantConflictPanel.tsx`·`MotionPanel.tsx`·`InfographicPanel.tsx`·`LibraryPickerDialog.tsx`·`EditorWorkbenchRoute.tsx`·`EditorWorkbench.tsx:589`(서랍 `닫기`) | 변형 없음 → 채운 파랑 | `variant="outline"` 명시(대화상자 바닥의 확정 단추 하나만 `default`) | L7a·L7b·L3 |
| 22 | `ProductShell.tsx:133` | `작업 상태`가 `size` 없음(shadcn 기본 36 → 껍데기 규칙이 32로 누름), 그림에서 글자가 다른 상단바 글자보다 큼 | `size="sm"` | **이 문서 밖**(ProductShell은 SHA-256 고정 — 계획 I Task 9에 넘김) |

---

## 6. 구현 Task

### 6-0. 순서와 동시 실행

```
[선행] 계획 I Task 2 → Task 4  (이 문서 밖, 이미 계획 I에 Step까지 적혀 있음)
L0 측정 도구·'전' 기록
L1 선택 무늬 + 상단바 단계        ┐ 차례로
L2 편집기 CSS 한 파일             ┘ (L2는 컴포넌트 시험 파일의 CSS 단언을 고칠 수 있어서 TSX Task보다 먼저)
L3 · L4 · L5 · L6 · L7a · L7b    ← 서로 파일이 안 겹침, 동시에 돌려도 됨
L8 마감(전체 시험·죽은 단추 전체 점검·'후' 기록·대표님 안내서)
```

**동시에 도는 Task끼리는 파일이 겹치지 않습니다.** 겹치는 파일은 `editor-workbench.css` 하나인데, 그 파일은 L2만 고칩니다. L3~L7이 CSS가 필요하다고 판단하면 고치지 말고 L8 메모에 적습니다.

모든 Task 공통:
- 시작 전 `git status --short`, `git log --oneline -3`, 선행 Task 커밋이 있는지 확인. **앵커 문자열이 없으면 멈추고** `git log -p -- <파일>`로 새 모양 확인.
- RED/GREEN에서는 시험 **하나만**. 넓은 시험은 Task 끝에서.
- 웹 시험은 `apps/web`에서: `npx vitest run <파일>`, `npx tsc --noEmit`.
- 문구 시험 `npx vitest run src/user-copy-policy.test.ts`를 UI Task마다.
- 커밋은 Task마다, 한국어 메시지, 끝줄 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. 푸시는 **닫힌 묶음마다**(M1·M2·L8, 아래 §6-1) 한다. 검증이 끝난 커밋을 쌓아 두면 이번 주 안에 L8까지 못 갔을 때 아무것도 올라가지 않는다(§7-3). 확인 명령과 푸시를 한 줄로 묶지 않는다.
- **닫는 법(공통 5가지)** — 각 Task 절의 "닫기"에 추가 항목만 적습니다:
  1. 그 Task가 건드린 파일의 vitest + `npx tsc --noEmit` 통과
  2. 모의 e2e: `npm run test:e2e` → **49 통과**(2026-10-10 인계 기준). 끝의 `unexpected PNG: product-shell-mobile-menu-open.png` exit 1은 알려진 무관 항목, 보고만. 뒤에 `git status --short apps/web/e2e/snapshots` → 바뀐 PNG는 `git checkout -- apps/web/e2e/snapshots`로 되돌리고 "달라졌다"만 보고
  3. 죽은 단추 빠른 점검: `CENSUS_LIST_ONLY=1 npm run test:e2e:real-flow -- dead-control-sweep.spec.mjs` — 누르지 않고 **이름 목록만** 냅니다. 이전 목록과 비교해 **사라진 이름 0**(이름을 바꾼 것은 표로 대응). 전체 누르기 점검(약 41분)은 L8에서 한 번
  4. 전후 그림: L0의 `layout-census` 명세로 `before/`·`after/` PNG 각 1장(1280×720 + 1440×900)
  5. 개수 세기: 같은 명세 JSON에서 편집기 **글자 크기 종류 수, 단추 높이 종류 수, 채운 단추 수, 구역별 주요 단추 수**를 전후로 표에 적음

### 6-1. 묶음과 대표님 확인 지점 (2026-10-10 검토에서 추가)

한 번에 끝까지 가지 않고, **눈에 띄게 달라지는 첫 묶음을 먼저 닫아 대표님이 보시게** 합니다. 방향이 틀렸으면 L3 이후 토큰을 쓰기 전에 알 수 있습니다.

| 묶음 | Task | 닫으면 | 대표님이 보실 것 |
|---|---|---|---|
| **M1** | 선행(I Task 2·4) + L0 + L1 + L2a + L2b | 푸시 1 | 구역 틈·여백·제목 줄이 하나로, 재생줄·타임라인 줄·트랙 머리의 회색 상자가 사라짐(CSS만으로 되는 것) |
| **M2** | L3 + L4 + L5 | 푸시 2 | 선택 표시가 채운 파랑에서 옅은 면으로, `내보내기`만 채운 단추, 자산 단추 두 묶음 |
| **M3** | L6 + L7a + L7b + L8 | 푸시 3 | 나머지 채운 단추 정리, 전체 점검·안내서 |

- **M1 뒤에 멈추고 대표님께 전후 그림을 보여 드립니다.** "테스트할 곳이 보이는가"가 이 작업의 성공 기준이라 제가 대신 잴 수 없습니다. 대표님이 방향을 바꾸시면 M2 이후를 고칩니다.
- **L2는 둘로 나눕니다**(같은 파일을 차례로 고치므로 동시 실행 이득은 없고 한 Task의 크기만 줄어듭니다). **L2a** = 구역 틀: 틈·여백 별칭(#11·12)·제목 줄(§2-3)·눈썹 굵기(#6·16)·손잡이(#14)·덮어쓰기 지우기(#15)·레일 아이콘(#17)·입력칸 바탕. **L2b** = 컨트롤 모양: 재생줄·보기 크기·트랙 머리 날 것 단추(#5·9·10)·자산 더하기 줄(#7)·분절 무늬(#8·19). 시험은 L2의 RED 목록을 그대로 둘로 나눕니다.
- **선행 I Task 2의 영향 범위를 M1 시작 전에 대표님께 한 줄로 알립니다**: "모든 화면의 글자 크기가 한 번에 줄어듭니다(예: 화면 제목 28→20)."

### L0. 측정 도구와 '전' 기록

- **Files:** Create `apps/web/e2e/support/style-inventory.mjs`(계획 I Task 0 Interfaces의 `collectStyleInventory(page)`를 **그 시그니처 그대로** — 계획 I Task 0이 같은 파일을 만들 예정이므로 두 벌 만들지 않기 위함. 이미 있으면 그대로 씀), Create `apps/web/e2e-real/layout-census.spec.mjs`, Create `docs/superpowers/audit-evidence/2026-10-10-layout/before/`.
- `layout-census.spec.mjs`는 `dead-control-sweep.spec.mjs`처럼 **측정만**(항상 통과, 결과를 JSON+PNG로 씀). 진짜 백엔드 고정 시험 프로젝트에서 편집기를 열고(`readFixture` 재사용), 상태 둘(아무것도 안 고름 / 클립 하나 고름) × 크기 둘(1280×720, 1440×900)로 `collectStyleInventory` + `page.screenshot`. 환경변수 `LAYOUT_LABEL=before|after|L3…`로 저장 폴더를 고릅니다. 대표님 실제 스택(5173)에는 닿지 않습니다.
- JSON 요약 칸(이 문서 목표와 1:1): `fontSizes`(값→개수), `fontWeights`, `fontFamilies`, `controlHeights`(값→개수, 예외 제외), `filledPrimary`(보이는 `[data-slot=button][data-variant=default]` 수, 유진 창 안 제외 칸 따로), `primaryPerRegion`(`[data-region]`별 `[data-primary-action]` 수 — `data-region`이 아직 없으면 `null`), `nestedBorders`(테두리가 있는 요소 안의 테두리 있는 요소 수, 영상 칸·떠 있는 표면 제외), `docScrollWidth − docClientWidth`.
- 높이 예외(이유를 JSON에 적음): 레일 탭(아이콘+이름 두 줄, `data-multiline`), 클립·자르기 손잡이·재생 위치 손잡이(`data-native-control` `timeline-clip-select|timeline-trim-*|placement-*|timeline-reorder|timeline-scrub`), 유진 시작 문장 알약(여러 줄).
- **닫기:** 공통 1(도우미라 RED 없음 — 대신 `node --test`용 작은 단위 시험 `style-inventory.test.mjs`로 요약 함수만 검사), 공통 4·5에서 `before` 값이 나왔는지. 결과 수치를 이 문서 끝 "측정 기록" 표에 붙여 커밋.

### L1. 선택 무늬 한 벌 + 상단바 지금 단계

- **Files:** Modify `apps/web/src/styles/primitives.css`(계획 I Task 4가 만든 파일), `apps/web/src/styles/primitives.test.ts`, `apps/web/src/styles/contrast.test.ts`, `apps/web/src/features/shell/TopBar.tsx`(181행 앵커 `variant={activeStage === target ? "default" : "outline"}`), `apps/web/src/features/shell/top-bar.test.tsx`.
- 규칙(층 밖, 선택자 특정도는 계획 I 표와 같은 방식):
  `[data-slot=button]:is([aria-selected=true],[aria-pressed=true],[aria-current=step],[aria-current=page]), [data-native-control]:is([aria-pressed=true]) { background: var(--vb-accent-bg); box-shadow: inset 0 0 0 1px var(--vb-accent-border); color: var(--vb-accent); }` — `variant=default`인 단추에는 걸리지 않게 `:not([data-variant=default])`.
- **RED 시험:** `primitives.test.ts` `it("선택·눌림·현재 위치는 깔린 면 무늬 하나다")`(선택자 넷이 한 규칙에), `contrast.test.ts` `it("포인트 글자는 깔린 면 위에서 4.5:1을 넘는다")`(`contrastRatio(APPROVED.accent, APPROVED.accentBg) >= 4.5`), `top-bar.test.tsx` `it("지금 단계는 aria-current이고 채운 단추가 아니다")`.
- `editor-workbench.css:556`(재생줄 눌림)·`:365`(필터 눌림)은 **L2가** 이 규칙으로 갈음해 지웁니다(파일 소유 때문에 L1은 손대지 않음).
- **닫기:** 공통 1~5. 추가로 `/projects` 화면 그림에서 상단바가 바뀌지 않았는지(상단 단계 띠는 프로젝트 안에서만 보임) 확인.

### L2. 편집기 CSS — 구역 틀과 컨트롤 모양 (한 파일)

- **Files:** Modify `apps/web/src/styles/editor-workbench.css`만. Create `apps/web/src/styles/editor-regions.test.ts`. CSS 단언이 깨지는 기존 시험(`styles/editor-rail.test.ts`, `styles/theme-tokens.test.ts`, `ui-system.test.tsx`, `features/editor/{assets/EditorAssetBrowser,preview/preview-stage,timeline/timeline-dock,workbench/toolbar-collapse}.test.tsx`)은 **CSS 단언 줄만** 고칩니다(이 Task가 L3~L7보다 먼저 끝나므로 겹치지 않음).
- 바꿀 것(§5 표의 L2 항목 전부): 별칭 셋 정의(§2-2), 구역 틈·여백(#11·12), 제목 줄 규칙(§2-3, 기존 클래스에: `.vb-preview-stage__header`, `.vb-editor-workbench__timeline-head`, `.vb-editor-variants__header`, `.vb-yujin-panel__header`, `.vb-editor-right-dock__inspector > h2`), 눈썹 700 제거(#6·16), 재생줄·보기 크기·트랙 머리 날 것 단추 모양(#5·9·10: 바탕 투명, 테두리 0, 모서리 sm, 크기 24 또는 28, 아이콘 14, 글자색 `--vb-muted`, 마우스 올림 `--vb-panel-alt`), 자산 더하기 줄(#7: `flex:0 0 auto`, 묶음 이름표 클래스 `.vb-editor-assets__group-label` 11px 흐림 — L4가 이 이름으로 마크업), 분절 무늬(#8·19: `.vb-segmented` 한 규칙 — L4·L7b가 이 클래스명을 씀), 알약 칩은 `.vb-editor-assets__taste` 안에서만(#8), 손잡이(#14), 덮어쓰기 지우기(#15), 레일 아이콘(#17), 구역 안 입력칸 바탕(아래 ⚠).
- ⚠ **계획 I Task 4 표와 다른 점 하나:** 계획 I는 입력칸 바탕을 `--vb-panel-alt`(#202024)로 정했는데, 편집기 구역 바탕 `--card`도 #202024라 **입력칸이 구역에 녹아 안 보입니다.** 편집기 구역 안에서만 입력·선택 상자 바탕을 `--vb-panel`(#18181B, 한 단계 들어간 칸)으로 둡니다: `.vb-editor-workbench :where([data-slot=input],[data-slot=textarea],[data-slot=select-trigger],[data-slot=native-select]) { background: var(--vb-panel); }`. 새 색이 아니라 기존 단계입니다.
- **RED 시험(`editor-regions.test.ts`, 정적):** `구역 틈과 안쪽 여백은 별칭 하나씩이다`, `편집기 CSS에 굵기 650·700·750이 없다`, `날 것 재생·보기 크기·트랙 단추에 모양 규칙이 있다`(`.vb-preview-stage__transport > button`, `.vb-editor-workbench__timeline-zoom > button`, `.vb-timeline-lane-headers [role=listitem] > button` 셋이 `background: transparent`), `편집기 단추 덮어쓰기(.vb-product-shell .vb-editor-workbench [data-slot="button"])가 없다`, `알약(999px)은 지울 수 있는 표지에만 쓴다`(허용 선택자 목록 대조).
- **닫기:** 공통 1~5 + `npm run test:e2e:editor-workbench`(도크 끌기 성능 문턱이 흔들리면 두 번 더 돌려 3회 결과를 그대로 보고 — 알려진 불안정) + 진짜 백엔드 `one-screen.spec.mjs`(1280×720에서 트랙 셋이 보이는지 — 여백을 줄였으니 나아져야 정상, 나빠지면 멈춤). 개수 목표: 편집기 글자 크기 종류 ≤ 4, 단추 높이 종류 ≤ 3(예외 제외), Arial 0, `nestedBorders` 전보다 감소.

### L3. 편집 도구줄·레일·가로세로 띠 (`EditorWorkbench.tsx`)

- **Files:** Modify `apps/web/src/features/editor/workbench/EditorWorkbench.tsx`, `apps/web/src/features/editor/workbench/editor-workbench.test.tsx`(필요하면 `toolbar-collapse.test.tsx`).
- 할 일: §5 #1·2·3·18, #9의 편집 도구 쪽(`cutButton`·`editToolbar` → `variant="ghost" size="icon-sm"`), #21의 서랍 `닫기`(`:589`) `variant="outline"`, `:787` `size="sm"`, `data-region="toolbar|rail|variants"` 속성, `:648-651` 낡은 ghost 주석을 사실대로 고침.
- **RED 시험:** `it("유진 창이 닫힌 편집기에서 채운 단추는 내보내기 하나다")`(`[data-slot=button][data-variant=default]` 길이 1, 이름 `내보내기`), `it("레일 탭은 선택돼도 채운 단추가 아니다")`(`aria-selected=true`인 탭의 `data-variant` = `ghost`), `it("레일 탭 목록 이름은 편집 도구이고 왼쪽 패널은 하나다")`.
- **닫기:** 공통 1~5. 공통 3에서 `내보내기` 이름이 그대로인지(죽은 단추 점검 SKIP 규칙 `/내보내기 시작/`과 겹치지 않음 — 확인).

### L4. 자산 패널 (`EditorAssetBrowser.tsx`)

- **Files:** Modify `apps/web/src/features/editor/assets/EditorAssetBrowser.tsx`, `apps/web/src/features/editor/assets/EditorAssetBrowser.test.tsx`. (`features/media/AddMediaFiles.tsx`는 `size`만 받을 수 있으면 prop으로 넘기고, 고쳐야 하면 **이 Task 소유**로 함께 — 다른 Task는 안 건드림.)
- 할 일: §5 #7·8, 변형 없는 단추 4개에 `variant` 명시, 단추 크기 `sm`, 보기 방식 → 아이콘 단추(`aria-label` `격자로 보기`/`줄로 보기` 유지, `aria-pressed` 유지), 방향 → `className="vb-segmented"`, 묶음 둘(`role="group"` `aria-label="가져오기"`/`"만들기"` + 이름표), `data-region="assets"`.
- 단추 **이름은 하나도 바꾸지 않습니다**(`자료실에서 가져오기` 등은 시험 `EditorAssetBrowser.test.tsx:734`과 죽은 단추 점검이 이름으로 찾음).
- **RED 시험:** `it("더하기 단추는 가져오기·만들기 두 묶음이고 첫 자리는 파일 추가다")`, `it("보기 방식은 아이콘 단추 둘이고 이름이 그대로다")`.
- **닫기:** 공통 1~5. 그림에서 여섯 단추 폭이 글자 길이대로(늘어나지 않음)인지.

### L5. 미리보기 머리와 재생줄 (`preview-stage.tsx`)

- **Files:** Modify `apps/web/src/features/editor/preview/preview-stage.tsx`, `apps/web/src/features/editor/preview/preview-stage.test.tsx`, `apps/web/src/features/editor/preview/transport-always-visible.test.tsx`(이름 단언만 있으면 그대로 통과해야 정상).
- 할 일: §5 #5·6의 TSX 쪽. 머리 한 줄(제목 `편집 결과`/`원본 보기` 글자 유지, 눈썹 → 메타), 재생줄 글자 기호 → 아이콘, **날 것 `<button data-native-control>`은 그대로**(→ `task22-parity-owners.test.ts` 목록 변경 없음), `aria-label`·`title` 그대로, `data-region="preview"`, 재생 단추에 `data-size="icon-sm"`(CSS가 28로 그림 — L2에서 이 속성 선택자를 같이 넣어 둡니다).
- **RED 시험:** `it("미리보기 머리는 한 줄이다")`(머리 안 블록 요소 줄 하나 — 정적으로 눈썹 `p` 없음), `it("재생줄 단추는 글자 기호 대신 아이콘이고 이름은 그대로다")`(`◀｜`·`｜▶` 문자가 없음 + `getByRole("button",{name:"재생 또는 일시정지"})`).
- **닫기:** 공통 1~5 + 진짜 백엔드 `playback-smoothness.spec.mjs`·`capcut-shortcuts.spec.mjs` 단독 실행(재생줄을 건드렸으므로).

### L6. 타임라인 머리줄 (`TimelineDock.tsx`)

- **Files:** Modify `apps/web/src/features/editor/timeline/TimelineDock.tsx`, `apps/web/src/features/editor/timeline/timeline-dock.test.tsx`.
- 할 일: 보기 크기 `−`·`+` 글자 → `ZoomOut`·`ZoomIn` 아이콘(`aria-label`·`title`·날 것 단추 유지), `전체`는 글자 유지, 머리줄 `data-region-head`, 바깥 `data-region="timeline"`. 트랙 머리 마크업은 손대지 않음(모양은 L2 CSS).
- **RED 시험:** `it("보기 크기 단추는 아이콘이고 이름이 그대로다")`.
- **닫기:** 공통 1~5 + 진짜 백엔드 `zoom-and-rate-baseline.spec.mjs`·`track-headers.spec.mjs` 단독.

### L7a. 유진 창 (`YujinPanel.tsx`)

- **Files:** Modify `apps/web/src/features/editor/workbench/YujinPanel.tsx` + 그 시험 파일(`grep -rl "YujinPanel" apps/web/src --include=*.test.tsx`로 찾은 것 중 YujinPanel 전용 파일 하나).
- 할 일: §5 #20. `요청 보내기`만 `variant="default"`(창이 한 영역), 나머지 `outline` 명시, 닫힌 알약 `유진`은 `outline`(포인트색 아이콘 유지). 이름·동작 그대로.
- **RED 시험:** `it("유진 창 안 채운 단추는 요청 보내기 하나다")`.
- **닫기:** 공통 1~5(공통 3의 SKIP 규칙 `/추천받기|요청 보내기/` 때문에 이 단추는 점검이 누르지 않음 — 정상).

### L7b. 편집 항목·변형·대본 등 나머지 편집기 파일

- **Files:** Modify `workbench/RightDock.tsx`, `inspector/InspectorControls.tsx`, `variants/VariantSelector.tsx`, `variants/VariantServerControls.tsx`, `variants/VariantConflictPanel.tsx`, `transcript/TranscriptPanel.tsx`, `transcript/AutoCaptionCard.tsx`, `script/ScriptPane.tsx`, `assets/MotionPanel.tsx`, `assets/InfographicPanel.tsx`, `assets/LibraryPickerDialog.tsx`, `workbench/EditorWorkbenchRoute.tsx` (모두 `apps/web/src/features/editor/` 아래) + 각자의 `*.test.tsx`.
- 할 일: §5 #19·21. 변형 없는 단추에 `variant` 명시(대화상자 바닥 확정 단추 하나만 `default`), 배타 고르기 셋 → `className="vb-segmented"` + `aria-pressed`, 변형 고정, `data-region="inspector"`. **InspectorControls의 잠긴 이유 22곳은 이 Task 범위 밖**(§7-3).
- 크기가 커서 Sonnet 한 번에 무리면 **L7b-1(RightDock·InspectorControls·variants/*)** 과 **L7b-2(나머지)** 로 나눕니다(파일이 안 겹침).
- **RED 시험:** `RightDock` 쪽 `it("편집 항목 종류 바로가기는 분절 무늬이고 채운 단추가 없다")`, `VariantSelector` 쪽 `it("고른 변형은 aria-pressed이고 채운 단추가 아니다")`.
- **닫기:** 공통 1~5 + 진짜 백엔드 `real-editing-flow.spec.mjs` 단독(편집 항목 경로).

### L8. 마감 — 전체 시험·죽은 단추 전체 점검·'후' 기록·안내서

- **Files:** Create `docs/superpowers/audit-evidence/2026-10-10-layout/after/`, Modify `docs/owner-test-guide.ko.md`(맨 앞에 §1 구역 지도 표의 **한 줄 역할 이름만** 짧게 — "이 칸에서는 이것을 시험해 보세요" 한 줄씩), Modify 이 문서 끝 "측정 기록".
- 할 일: `cd apps/web && npx vitest run && npx tsc --noEmit && npm run build`(각각 따로 실행해 결과 확인), `npm run test:e2e`(49), `npm run test:e2e:editor-workbench`, 죽은 단추 **전체** 점검 `npm run test:e2e:real-flow -- dead-control-sweep.spec.mjs`(약 41분, 단독, 기준: H 마감 `ok 293 · silent 4 · no-handler 0 · 설명 없는 비활성 0`보다 나빠지지 않음), `LAYOUT_LABEL=after` census, 컨테이너 재빌드는 **사람(컨트롤러)이** `scripts/owner-ready.ps1`로 — 이 Task는 docker를 직접 만지지 않음. 실제 컨테이너 화면(742 프로젝트) 그림은 재빌드 뒤 브라우저에서 `Ctrl+F5` 후.
- 검증 넷: 갭(§5 22줄 각각 됨/안 됨/넘김), 역방향(실제 컨테이너 화면 그림), 동작(§4 목표 수치), 배선(`grep -rn "data-region=" apps/web/src/features/editor --include=*.tsx | grep -v test | wc -l` ≥ 7, `grep -rn "vb-segmented" … ` ≥ 4, `data-primary-action` 편집기 1).
- **닫기:** 위 전부 + 푸시(`git push origin main` 한 줄, 강제 푸시 금지). 앞선 묶음(M1·M2)을 이미 푸시했다면 남은 커밋만 올린다.

---

## 7. 반대 논리·위험·하지 않기로 한 것

### 7-1. 이 규칙이 오히려 답답하게 만들 수 있는 곳

| 자리 | 왜 답답해질 수 있나 | 대비 |
|---|---|---|
| 편집 항목(F)·유진 창(I) | 입력칸과 긴 문장이 많은 폼 구역인데 안쪽 여백을 8로 줄이면 빽빽해 보일 수 있음 | 손잡이 `--vb-region-pad` 하나만 12로 올림. 구역별 예외는 만들지 않음 |
| 채운 단추가 편집기에 하나뿐 | 대표님이 "어디를 눌러야 하는지" 더 못 찾을 수 있음 — 지금은 파랑이 많아서 적어도 눈에 띄긴 함 | 구역 대표 행동은 첫 자리 + 아이콘+글자. L8 뒤 대표님이 실제로 써 보고 "못 찾겠다"가 나오면 구역 대표 행동만 `secondary`(깔린 면 채움)로 한 단계 올리는 안을 결정으로 올림(지금 하지 않음) |
| 선택 무늬(옅은 파랑 면) | 채운 파랑보다 약해서 "지금 어느 탭인지"가 덜 보일 수 있음. #1A2436은 구역 바탕 #202024와 밝기가 거의 같음 | 테두리 `--vb-accent-border` + 포인트 글자색으로 구분. L8 그림에서 레일 선택이 안 보이면 테두리를 2px 안쪽 고리로(색 그대로) |
| 재생줄 글자 → 아이콘 | `재생 / 일시정지`·`음소거`·`반복`은 지금 글자라 처음 보는 사람도 읽힘. 아이콘은 익숙한 사람에게만 빠름 | 누구나 아는 기호(재생·소리·반복·전체화면)만 아이콘. `단축키`·`1배`는 글자 유지. 툴팁(`title`) 필수 |
| 누를 자리 24px | WCAG 2.2 최소치에 딱 붙음. 손 떨림·노트북 터치패드에서는 작다 | 데스크톱 편집기라 수용. 트랙 머리·재생줄 외에는 28 |
| 바깥 테두리 유지 | "선 대신 바탕으로 나눈다"는 원칙과 반쯤 어긋남 | 바탕 단계만으로는 값싼 화면에서 구역이 녹는 위험이 더 큼(§2-1 근거 2). 구역 **안**의 선을 줄이는 것으로 충분하다고 판단 |

### 7-2. 위험

1. **선행 조건이 큼.** 계획 I Task 2(토큰 값 변경)는 편집기만이 아니라 **모든 화면의 글자를 한꺼번에** 줄입니다(예: 화면 제목 28→20은 `--vb-text-2xl` 값 변경만으로 생김). 계획 I가 승인한 범위지만, 이 문서만 보고 "편집기만 바뀐다"고 생각하면 틀립니다.
2. **1280×720 한 화면 회귀.** 여백·틈·제목 줄 높이를 바꾸면 미리보기·타임라인 높이 배분이 바뀝니다. `one-screen.spec.mjs`(트랙 셋 보임)가 지킵니다 — L2·L8에서 반드시 단독 실행.
3. **CSS 우선순위 함정.** 이 저장소에서 같은 함정이 여러 번 있었습니다(`editor-workbench.css:44-49` 주석, 기억 메모 "inline style로 고친 건 규칙이 이긴다는 증명이 아니다"). 값을 바꾼 뒤 **계산값을 브라우저에서 다시 재야** 합니다 — 정적 시험 초록은 증거가 아닙니다.
4. **이름을 바꾸면 죽은 단추 점검·e2e가 깨짐.** 이 문서는 단추 **이름을 하나도 바꾸지 않습니다.** 보이는 글자를 아이콘으로 바꿀 때도 `aria-label`은 그대로입니다.
5. **유진 창 예외의 해석.** 검토자가 "편집기 채운 단추 하나"를 문자 그대로 보면 L7a가 어긋납니다(§3-4 아래 주석). 결정 한 줄로 끝나는 문제입니다.
6. **단추·입력칸 테두리가 약합니다(검토에서 추가, 새 결정 필요).** `--vb-border #2E2E33`은 구역 바탕 `#202024`와 약 1.2:1, 입력칸 안쪽 `#18181B`과는 더 약합니다. 화면 요소의 경계는 3:1을 권하는 기준(WCAG 1.4.11)에 못 미칩니다. 대표님이 "어디를 눌러야 할지 모르겠다"고 하신 것의 일부 원인일 수 있습니다(추정). 이 문서는 색을 못 바꾸므로 **고치지 않고** 결정 항목으로만 올립니다: 보조 단추·입력칸 **테두리 한 단계 밝힘**(예: `#3D3D44` 이상, 기존 `--vb-border-strong`부터)을 L8 뒤에 실제 그림으로 보고 결정합니다. 팔레트 값 변경이므로 재승인이 필요합니다.
7. 내장 브라우저는 전이·애니메이션을 안 그립니다(기억 메모). 그림은 Playwright(`layout-census`)로 찍고, 내장 브라우저로 잴 때는 JS 계산값만 씁니다.

### 7-3. 이번 주 안에 못 끝낼 것 (추정 포함)

- `InspectorControls.tsx` 잠긴 이유 22곳, `YujinPanel.tsx` 9곳 등 **잠긴 단추 이유 문장**(계획 I Task 5·10 몫). 이 문서는 모양만 다룹니다.
- 유진 창 **내부 배치** 재정리(대화·후보·검사 결과가 한 창에 쌓인 구조).
- 좁은 화면(`drawer` 모드)·375px 폭 정리 — 이 문서의 수치는 1280 이상 기준. 375에서는 깨지지 않는지만 봅니다(가로 스크롤 0).
- 계획 I Task 3(정적 가드 기준선) — 권장이지만 이 문서 Task에 넣지 않았습니다.
- 다른 화면 전부(§8).
- 추정: L0~L8 전체는 Sonnet 기준 Task당 1~3시간, 전체 하루 반~이틀. 선행 I Task 2·4가 반나절~하루 더. "이번 주 안"이면 **M1(선행 포함)까지가 현실적**이고 M2는 빠듯, M3는 다음 주로 넘어갈 가능성이 큽니다. 그래서 §6-1로 M1마다 푸시·확인합니다.

### 7-4. 하지 않기로 한 것

- **색 값 변경, 새 색, 살구색 토큰 만들기** — 쓰는 곳이 아직 없음(결정 문서 그대로).
- **글자·컨트롤 척도 값 변경** — 계획 I 값 그대로 씀.
- **편집 도구줄(B)을 상단바(A)로 합치기** — 한 줄(약 40px)을 아끼지만 `ProductShell.tsx`는 SHA-256 고정이고 구조 변경이라 계획 G·결정 몫. 후보로만 남깁니다.
- **자산 패널 여섯 단추를 드롭다운 하나로 숨기기** — 깔끔해 보이지만 대표님이 기능을 못 찾게 되고, `role`이 `menuitem`으로 바뀌어 시험·죽은 단추 점검이 깨짐. 두 묶음으로 나누는 것까지만.
- **조밀/넓게 토글, 본문 최대 폭** — D3·D4로 없앰.
- 패널 폭·타임라인 높이 기본값, 레일 폭(72px) 바꾸기 — 배치는 2026-08-17·08-21 승인 사항.
- 날 것 `<button>`을 shadcn `<Button>`으로 바꾸기 — `task22-parity-owners.test.ts`의 정확한 목록이 바뀌어야 하고 이득이 모양뿐이라 CSS로 갈음.
- 단추 이름(문구) 바꾸기 — 이 문서 범위 밖.

---

## 8. 다른 화면으로 넓힐 때의 순서 (이번 범위 아님)

1. **규칙을 공용 층으로 올림:** 편집기 별칭(`--vb-region-*`)과 `[data-region]`·`.vb-segmented` 규칙을 `editor-workbench.css`에서 `primitives.css`로 옮기고, 대시보드용 값(`--vb-card-pad` 12, `--vb-grid-gap` 12 — 계획 I 밀도 묶음)을 같은 이름 아래 둡니다.
2. **셸(상단바·왼쪽 메뉴):** 계획 I Task 6·9. `작업 상태` `size="sm"`(§5 #22)도 여기서.
3. **`/projects`:** 계획 **G2·G3 뒤에**(`+ 새로 만들기` 80px 막대 `product-shell.css:251` → G3가 카드 격자 첫 칸으로 바꿈). 그다음 계획 I Task 7(카드 제목 24px/700 → 13/600, `product-shell.css:37`). 주요 = `+ 새로 만들기` 하나.
4. **`/library`·`/footage`:** 3칸이 곧 구역 셋(분류 / 결과 / 미리보기). 지금 `파일 추가`·`폴더 추가`가 둘 다 채운 파랑(그림 `library.png`) → `파일 추가`만 주요. 필터 항목 40px → 28(계획 I Task 8).
5. **설정·목소리·기획·검토:** 계획 I Task 9 폼 틀.
6. **대화상자류:** 계획 I Task 4 규격이 이미 덮으므로 마지막에 "대화상자마다 주요 하나"만 셉니다.

---

## 측정 기록 (L0·L8이 채움)

| 값 | 기준선 2026-10-08(계획 I, H 이전) | before (L0) | after (L8) | 목표 |
|---|---|---|---|---|
| 편집기 글자 크기 종류 | 12·14·10·13.33 (4종+) | | | ⊆ {11,12,13,14} |
| 편집기 굵기 종류 | — | | | ⊆ {400,500,600} |
| 단추 높이 종류(예외 제외) | 7종 | | | ⊆ {24,28,32} |
| Arial 컨트롤 | 66 | | | 0 |
| 채운 단추(유진 창 닫힘) | 38(오렌지 시절) | | | 1 (`내보내기`) |
| 구역별 주요 단추 | — | | | 각 ≤ 1 |
| 상자 안 상자(`nestedBorders`) | — | | | before보다 적게 |
| 가로 넘침(`scrollWidth − clientWidth`) | — | | | 0 |
