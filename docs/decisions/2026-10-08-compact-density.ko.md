# 조밀한 화면 — 캡컷처럼 넓게 쓰기 (2026-10-08, owner 승인)

- 결정 상태: **approved** (대표님 말이 승인이다)
- 갱신하는 것: `2026-08-19-spacing-and-type-scale.ko.md`의 글자 **값**, `2026-09-04-capcut-shell-with-my-assets.ko.md` 캡컷 실측 척도의 글자 **값**과 "단추 32px 하나" 규칙
- 바꾸지 않는 것: **색 전부**(`2026-08-29-capcut-full-structure-and-dark-theme.ko.md` 다크 팔레트), 모서리 세 단계(`2026-08-27-editor-centered-shell-direction.ko.md`), 간격 토큰 값(`--vb-space-1..8`), 토큰 이름
- 색에 대한 덧붙임(2026-10-10): 이 결정을 쓴 뒤 **포인트색만** 오렌지에서 파스텔 파랑 `#9EC0F7`로 바뀌었다. 그 결정은 `2026-10-10-accent-color-blue.ko.md`에 이미 있고 이 문서는 되풀이하지 않는다. 아래 글에서 "주황"은 이제 "포인트색(파랑)"으로 읽는다. 이 문서의 밀도 값은 색과 무관하다.

## 대표님이 말한 것
> "검은 배경은 좋다. 캡컷처럼 화면을 넓게 쓰려면 글자를 줄이고 컴포넌트·카드를 줄여야 한다."

## 무엇이 바뀌나

출처: 계획 I(`docs/superpowers/plans/2026-10-08-design-system-and-wiring-i.ko.md`)의 "토큰 한 벌"과 "무엇이 얼마나 줄어드나". 숫자는 Task 2가 `ui-system.css`에 넣고 Task 12가 잰다.

## 토큰 한 벌 (Task 2가 `apps/web/src/ui-system.css` `:root`에 넣는 값)

| 묶음 | 토큰 = 값 | 쓰는 자리 |
|---|---|---|
| 글자 | `--vb-text-xs: 0.6875rem`(11) · `--vb-text-sm: 0.75rem`(12) · `--vb-text-md: 0.8125rem`(13) · `--vb-text-lg: 0.875rem`(14) · `--vb-text-xl: 1rem`(16) · `--vb-text-2xl: 1.25rem`(20) · `--vb-text-3xl: 1.5rem`(24) | xs 라벨·메타·배지·클립 이름, **sm 본문 기본**, md 항목·카드 제목, lg 패널 제목, xl 구역 제목, 2xl 화면 제목, 3xl 빈 화면 큰 문장 |
| 줄 높이 | `--vb-leading-xs: 1rem` · `-sm: 1rem` · `-md: 1.125rem` · `-lg: 1.25rem` · `-xl: 1.375rem` · `-2xl: 1.75rem` · `-3xl: 2rem` | Tailwind `--text-*--line-height` 별칭 |
| 굵기 | `--vb-weight-regular: 400` · `--vb-weight-medium: 500` · `--vb-weight-strong: 600` | 본문 / 이름표·탭·단추 / 제목·숫자 |
| 컨트롤 | `--vb-control-xs: 1.5rem`(24) · `--vb-control-sm: 1.75rem`(28) · `--vb-control-md: 2rem`(32) | 아이콘·트랙 단추·칩 / 기본 단추·입력·탭·메뉴 항목 / 주 동작·대화상자 바닥·검색 |
| 모서리 | `--radius: .625rem`(그대로) · `--vb-radius-sm: calc(var(--radius) * 0.6)` · `--vb-radius-md: var(--radius)` · `--vb-radius-lg: calc(var(--radius) * 1.6)` | 6 / 10 / 16px |
| 간격 | `--vb-space-1..8` **값 그대로**(4·8·12·16·20·24·32·40) | 조밀함은 "한 단계 아래 토큰을 쓰는 것"으로 만든다(아래 표) |
| 밀도 묶음 | `--vb-page-pad-y: var(--vb-space-4)` · `--vb-page-pad-x: var(--vb-space-6)` · `--vb-card-pad: var(--vb-space-3)` · `--vb-grid-gap: var(--vb-space-3)` · `--vb-top-bar-h: 2.75rem`(44) · `--vb-side-nav-w: 11rem`(176) | 셸·카드·격자 |
| 아이콘 | `--vb-icon-xs: 0.75rem` · `-sm: 0.875rem` · `-md: 1rem` · `-lg: 1.5rem` | 배지 안 / 단추 안 / 제목 옆 / 빈 상태 |
| 층 | `--vb-z-sticky: 10` · `--vb-z-dock: 20` · `--vb-z-overlay: 40` · `--vb-z-popover: 50` · `--vb-z-toast: 60` | 지금 2·3·20·40·10·50이 흩어져 있다 |
| 초점 | `--vb-focus-outline: 2px solid var(--ring)` · `--vb-focus-offset: 2px` | 모든 `:focus-visible` |
| 글꼴 | `--vb-font: "Pretendard", "Noto Sans KR", sans-serif`(그대로, `assets/fonts/PretendardVariable.woff2` 하나만 실린다) + `--vb-font-numeric: tabular-nums` | 숫자 칸(시간·길이·개수)은 `font-variant-numeric: tabular-nums` |

Tailwind 별칭(`@theme inline`, Task 2): `--text-xs→--vb-text-xs` · `--text-sm→--vb-text-sm` · `--text-base→--vb-text-md` · `--text-lg→--vb-text-lg` · `--text-xl→--vb-text-xl` · `--text-2xl→--vb-text-2xl` · `--text-3xl→--vb-text-3xl`(4xl 이상은 지운다), `--font-weight-semibold: 600` · `--font-weight-bold: 600`, `--radius-xs/sm→--vb-radius-sm` · `--radius-md/lg→--vb-radius-md` · `--radius-xl/2xl→--vb-radius-lg`.

### 무엇이 얼마나 줄어드나 (목표 수치, Task 12 게이트가 잰다)

| 대상 | 지금(실측) | 목표 |
|---|---|---|
| 본문 기본 글자 | 14px(`.vb-product-shell` = `--vb-text-md` 14) | **12px**(`--vb-text-sm`) |
| 라벨·메타 | 10px(자료실 56곳·편집기 40곳·촬영본 158곳) | **11px**(최소) |
| 화면 제목 | 40px/700 | 20px/600 |
| 카드 제목(프로젝트) | 24px/700 | 13px/600, 한 줄 말줄임 |
| 콘텐츠 영역 | 최대폭 1200(1600px 이상 화면 1600), 패딩 32/40 | 최대폭 없음, 패딩 16/24 |
| 위 띠 | 53px | 44px |
| 왼쪽 메뉴 항목 | 36px·14px | 28px·12px |
| 프로젝트 카드 | 268×195, 패딩 20, 모서리 16, 1440에서 4열 | 열 최소 12.5rem(200px), 패딩 12, 모서리 10, 1440에서 **6열** |
| 자료실 영상 카드 | 161×160, 3열, 이름 14, 메타 10 | 열 최소 8.5rem(136px), **5열 이상**, 이름 12, 메타 11, 몸통 패딩 8 |
| 자료실 필터 항목 | 40px·14px | 28px·12px |
| 단추 | 대시보드 32·36·40·80, 편집기 23·25·27·30·32·36·40 | **24·28·32** 세 단계(`+ 새로 만들기` 칸은 G3 결과 그대로, 게이트 예외 목록에 이유 기록) |
| 입력·선택 | 32~40, 글자 10~14 | 28, 글자 12(375px 미만 16) |
| 탭 | 단추 묶음·Arial 섞임 | 분절 28px / line 28px, 글자 12/500 |
| 대화상자 | 폭 35rem, 패딩 24, 최대 70vh | 폭 32rem, 패딩 16, 간격 12, 최대 88vh |
| 편집기 컨트롤 | Arial 66, 모서리 0 ×50 | Arial 0, 모서리 0 0개(재생줄 포함) |
| 파랑(포인트색) 채운 단추 | 편집기 38개(주황 시절 실측, 2026-10-10 재측정 26개) | 화면(영역)마다 **1개**(D2) |

## 앞 승인과 어디서 부딪치나
- 2026-09-04 척도는 본문 14px였다(캡컷 실측 "항목 이름 14px 83곳"). 이번엔 본문 12px — 캡컷 패널에서 **더 많이** 쓰인 크기(12px 176곳)를 본문으로 삼는다.
- 2026-09-04 "단추 32px 하나"는 세 단계(24·28·32)로 바뀐다. 기본은 28.
- 10px(세로 띠 라벨·배지)은 없어진다. 최소 글자는 11px.
- 콘텐츠 최대폭 1200px(2026-08-19 "껍데기가 정한다")은 없어진다. 껍데기가 정한다는 원칙은 그대로.
- `설정 > 화면 > 조밀한 화면` 토글은 (D3 결정에 따라) 없어진다 — 조밀함이 기본이다.

## 지키는 바닥
누를 자리 24px 이상, 글자 11px 이상, 작은 글자 대비 4.5:1 이상. 포인트색 글자를 포인트색 깔린 면 위에 쓸 때도 이 대비를 지킨다(파랑 `#9EC0F7` 위 `#1A2436`은 약 8.4:1이라 지금은 넘는다. 주황 시절에는 4.27이라 못 썼다 — `contrast.test.ts`가 지킨다). 흐린 글자(`--vb-faint`)는 깔린 면 위에 쓰지 않는다.

## 검증
`apps/web/e2e/design-tokens.spec.mjs`(계산 스타일 게이트, Task 12), `apps/web/src/styles/design-guard.test.ts`(정적 가드, Task 3). 고치기 전 수치: `docs/superpowers/audit-evidence/2026-10-08-design-baseline.json`.
