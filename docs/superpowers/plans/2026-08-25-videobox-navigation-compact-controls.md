# VideoBox 전역 이동과 조밀한 조작부 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 모든 전역·프로젝트 화면에서 현재 위치, 안전한 이전 이동, 일관된 전역 메뉴를 제공하고 보조 조작부를 작고 설명 가능하게 만든다.

**Architecture:** 순수 라우트 모델이 경로 조각과 이력 없는 경우의 이전 목적지를 계산한다. `TopBar`는 그 모델을 표시하고, `ProductShell`·전역 페이지는 라우터의 실제 뒤로가기와 안전한 대체 목적지를 전달한다. 툴팁은 기존 shadcn/Radix 컴포넌트를 재사용한다.

**Tech Stack:** React, TypeScript, TanStack Router, Vitest, Testing Library, Radix Tooltip, CSS custom properties.

---

## 파일 구조

- 수정: `apps/web/src/app/routeManifest.ts` — 화면 이름·경로·안전한 이전 목적지의 순수 모델
- 수정: `apps/web/src/app/routeManifest.test.ts` — 모델 입력별 단위 시험
- 수정: `apps/web/src/features/shell/TopBar.tsx` — 이전 버튼, 경로, 툴팁, 작은 보조 버튼
- 수정: `apps/web/src/features/shell/top-bar.test.tsx` — 상단 행동과 접근성 시험
- 수정: `apps/web/src/app/ProductShell.tsx` — 라우터가 전달한 이동 문맥을 상단에 연결
- 수정: `apps/web/src/app/AppRouter.tsx` — 전역/프로젝트 화면의 실제 이력 이동과 안전한 대체 이동 연결
- 수정: `apps/web/src/app/AppRouter.test.tsx` — 라우터를 지나는 이동 시험
- 수정: `apps/web/src/styles/product-shell.css` — 승인된 색을 그대로 쓰는 조밀한 보조 조작부와 모바일 규칙
- 수정: `docs/handoffs/...` 및 `CLAUDE.md` — 완료 후 인계 위치 갱신

### Task 1: 순수 이동 모델을 시험으로 고정

**Files:**

- Modify: `apps/web/src/app/routeManifest.ts`
- Test: `apps/web/src/app/routeManifest.test.ts`

- [ ] **Step 1: 실패하는 경로 모델 시험을 쓴다**

```ts
import { resolveNavigationContext } from "./routeManifest";

it("gives library a stable breadcrumb and project-list fallback", () => {
  expect(resolveNavigationContext({ pathname: "/library" })).toMatchObject({
    screenName: "내 라이브러리",
    fallbackHref: "/projects",
    crumbs: [{ label: "프로젝트", href: "/projects" }, { label: "내 라이브러리" }],
  });
});

it("keeps a project stage in its project breadcrumb", () => {
  expect(resolveNavigationContext({ pathname: "/projects/p1/editor", projectName: "첫 영상" })).toMatchObject({
    fallbackHref: "/projects/p1/create",
    crumbs: [{ label: "프로젝트", href: "/projects" }, { label: "첫 영상", href: "/projects/p1/create" }, { label: "편집" }],
  });
});
```

- [ ] **Step 2: 시험이 현재 API 부재로 실패하는지 확인한다**

Run: `npx vitest run src/app/routeManifest.test.ts`

Expected: `resolveNavigationContext is not exported`로 실패한다.

- [ ] **Step 3: 최소 이동 모델을 구현한다**

```ts
export type NavigationContext = {
  screenName: string;
  fallbackHref: string;
  crumbs: ReadonlyArray<{ label: string; href?: string }>;
};

export function resolveNavigationContext(input: { pathname: string; projectName?: string }): NavigationContext {
  // 전역 목적지는 프로젝트 목록을 상위로, 프로젝트 단계는 바로 앞 작업 단계나 시작 화면을 상위로 둔다.
}
```

프로젝트 주소는 `parseWorkspaceLocation`을 재사용하고, 별칭 주소도 같은 단계 이름·안전한 목적지로 귀결한다. 설정의 `project_id`는 화면명만 바꾸지 않고 기존 URL 검색값을 보존한다.

- [ ] **Step 4: 모델 시험을 통과시킨다**

Run: `npx vitest run src/app/routeManifest.test.ts`

Expected: PASS.

- [ ] **Step 5: 작업 단위 커밋을 만든다**

```powershell
git add -- apps/web/src/app/routeManifest.ts apps/web/src/app/routeManifest.test.ts
git commit -m "수정: 화면 이동 경로와 안전한 이전 목적지 추가"
```

### Task 2: 상단에 이전·경로·설명을 추가한다

**Files:**

- Modify: `apps/web/src/features/shell/TopBar.tsx`
- Modify: `apps/web/src/features/shell/top-bar.test.tsx`

- [ ] **Step 1: 실패하는 상단 행동 시험을 쓴다**

```tsx
it("shows the current breadcrumb and uses the supplied safe back action", () => {
  const onBack = vi.fn();
  renderBar({ navigation: { screenName: "편집", fallbackHref: "/projects/a/create", crumbs: [{ label: "프로젝트", href: "/projects" }, { label: "첫 영상", href: "/projects/a/create" }, { label: "편집" }] }, onBack });
  expect(screen.getByRole("navigation", { name: "현재 위치" })).toHaveTextContent("프로젝트첫 영상편집");
  fireEvent.click(screen.getByRole("button", { name: "이전 화면" }));
  expect(onBack).toHaveBeenCalledOnce();
});

it("gives compact icon controls an accessible label and a tooltip", async () => {
  renderBar();
  fireEvent.focus(screen.getByRole("button", { name: "전체 메뉴" }));
  expect(await screen.findByText("프로젝트와 도구 메뉴 열기")).toBeVisible();
});
```

- [ ] **Step 2: 상단 시험이 새 속성·요소 부재로 실패하는지 확인한다**

Run: `npx vitest run src/features/shell/top-bar.test.tsx`

Expected: `현재 위치`와 `이전 화면`을 찾지 못해 실패한다.

- [ ] **Step 3: `TopBar`를 작고 분리된 표시 컴포넌트로 확장한다**

```tsx
type NavigationCrumb = { label: string; href?: string };

function CompactTooltip({ label, children }: { label: string; children: ReactNode }) {
  return <Tooltip><TooltipTrigger asChild>{children}</TooltipTrigger><TooltipContent>{label}</TooltipContent></Tooltip>;
}
```

- `onBack`은 이력 이동 또는 대체 이동을 수행하는 함수로만 받고, `TopBar`가 URL을 조합하지 않게 한다.
- 경로는 `nav aria-label="현재 위치"`에 출력하며 마지막 항목은 링크가 아니다.
- 이전·전체 메뉴·프로젝트 전환에는 `size="sm"` 또는 `size="icon-sm"`을 쓰고, 아이콘 전용이면 `aria-label`과 `CompactTooltip`을 함께 쓴다.
- 단계 버튼은 현재의 아이콘·문구·`aria-current`를 유지한다.

- [ ] **Step 4: 상단 시험을 통과시킨다**

Run: `npx vitest run src/features/shell/top-bar.test.tsx`

Expected: PASS.

- [ ] **Step 5: 작업 단위 커밋을 만든다**

```powershell
git add -- apps/web/src/features/shell/TopBar.tsx apps/web/src/features/shell/top-bar.test.tsx
git commit -m "수정: 상단에 이전 경로와 보조 버튼 설명 추가"
```

### Task 3: 라우터와 셸을 실제 이동에 연결한다

**Files:**

- Modify: `apps/web/src/app/ProductShell.tsx`
- Modify: `apps/web/src/app/AppRouter.tsx`
- Test: `apps/web/src/app/AppRouter.test.tsx`

- [ ] **Step 1: 실패하는 라우터 통합 시험을 쓴다**

```tsx
it("uses history for a visited page and the fallback for a direct URL", async () => {
  const router = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/projects", "/library"], initialIndex: 1 }));
  render(<AppRouter router={router} />);
  fireEvent.click(await screen.findByRole("button", { name: "이전 화면" }));
  await waitFor(() => expect(router.state.location.pathname).toBe("/projects"));

  const direct = createAppRouter(new ProjectCatalog(), createMemoryHistory({ initialEntries: ["/footage"] }));
  render(<AppRouter router={direct} />);
  fireEvent.click(await screen.findByRole("button", { name: "이전 화면" }));
  await waitFor(() => expect(direct.state.location.pathname).toBe("/library"));
});
```

- [ ] **Step 2: 통합 시험이 현재 상단에 행동이 없어 실패하는지 확인한다**

Run: `npx vitest run src/app/AppRouter.test.tsx`

Expected: `이전 화면`을 찾지 못해 실패한다.

- [ ] **Step 3: 셸 연결을 구현한다**

```tsx
const router = useRouter();
const goBack = () => {
  if (router.history.canGoBack()) router.history.back();
  else void navigate({ to: navigation.fallbackHref });
};
```

TanStack history의 실제 API에 맞춰 `canGoBack` 유무를 확인하고, 없는 경우 `window.history.length`만으로 외부 이력을 추정하지 않는다. 프로젝트·전역 셸 모두 같은 이동 문맥을 `ProductShell`로 전달한다. 메뉴 링크는 기존 `resolveGlobalLocation`을 사용해 이름과 주소를 한 곳에 둔다.

- [ ] **Step 4: 라우터 통합 시험을 통과시킨다**

Run: `npx vitest run src/app/AppRouter.test.tsx`

Expected: PASS.

- [ ] **Step 5: 작업 단위 커밋을 만든다**

```powershell
git add -- apps/web/src/app/ProductShell.tsx apps/web/src/app/AppRouter.tsx apps/web/src/app/AppRouter.test.tsx
git commit -m "수정: 모든 화면에서 안전한 이전 이동 연결"
```

### Task 4: 보조 조작부 밀도와 반응형 규칙을 적용한다

**Files:**

- Modify: `apps/web/src/styles/product-shell.css`
- Test: `apps/web/src/styles/product-shell.visual.test.tsx`

- [ ] **Step 1: 실패하는 스타일 계약 시험을 쓴다**

```tsx
it("keeps primary actions standard while compacting shell controls", () => {
  const css = readFileSync(new URL("./product-shell.css", import.meta.url), "utf8");
  expect(css).toContain(".vb-top-bar__compact-control");
  expect(css).toContain("min-height:32px");
  expect(css).toContain("@media (max-width: 767px)");
});
```

- [ ] **Step 2: 시험이 새로운 조작부 클래스 부재로 실패하는지 확인한다**

Run: `npx vitest run src/styles/product-shell.visual.test.tsx`

Expected: 새 클래스 문자열을 찾지 못해 실패한다.

- [ ] **Step 3: 색을 바꾸지 않는 CSS를 추가한다**

```css
.vb-top-bar__compact-control[data-slot=button] { min-height:32px; padding-inline:var(--vb-space-2); }
.vb-top-bar__breadcrumb { min-width:0; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }
@media (max-width:767px) { .vb-top-bar__breadcrumb { order:1; flex-basis:100%; } }
```

주요 본문 버튼, 새 프로젝트, 계속 만들기, 내보내기에는 이 클래스를 붙이지 않는다. 모바일에서는 툴팁만으로 뜻을 전달하지 않고 표시 라벨을 유지하며 기존 최소 터치 영역을 축소하지 않는다.

- [ ] **Step 4: 스타일 계약 시험을 통과시킨다**

Run: `npx vitest run src/styles/product-shell.visual.test.tsx`

Expected: PASS.

- [ ] **Step 5: 작업 단위 커밋을 만든다**

```powershell
git add -- apps/web/src/styles/product-shell.css apps/web/src/styles/product-shell.visual.test.tsx
git commit -m "수정: 상단 보조 버튼 밀도와 반응형 경로 정리"
```

### Task 5: 회귀·컨테이너·브라우저 검증과 인계

**Files:**

- Create: `docs/handoffs/2026-08-25-videobox-navigation-compact-controls-handoff.ko.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: 웹 정적·단위 회귀를 실행한다**

Run: `npx vitest run` and `npx tsc --noEmit` from `apps/web`.

Expected: 모두 성공하며, 실패가 있으면 시험을 되돌리지 않고 원인을 고친다.

- [ ] **Step 2: 컨테이너를 새 빌드로 기동한다**

Run: `./scripts/owner-ready.ps1 -Mode Start -Rebuild -WithYujinMemory`

Expected: 새 웹 번들이 실행된다. 직접 `docker compose` 명령은 쓰지 않는다.

- [ ] **Step 3: 실제 브라우저에서 정방향·역방향을 검증한다**

`/projects → /library → /footage → /settings/general → /projects/:id/editor`을 이동하고, 브라우저 이력 뒤로가기와 직접 `/footage` 진입의 이전 버튼을 따로 확인한다. 데스크톱과 375px 폭에서 경로가 잘리더라도 전체 메뉴·단계·이전 버튼이 조작 가능한지 확인한다.

- [ ] **Step 4: 인계를 작성하고 최신 세션 표를 갱신한다**

인계에는 실제 작업, 검증했지만 못 끝낸 것, 목요일에 화면으로 확인할 것을 분리한다. `CLAUDE.md` §2의 최신 세션 인계 경로를 새 파일로 바꾼다.

- [ ] **Step 5: 최종 문서 커밋과 상태를 확인한다**

```powershell
git add -- CLAUDE.md docs/handoffs/2026-08-25-videobox-navigation-compact-controls-handoff.ko.md
git commit -m "문서: 전역 이동 개선 인계 기록"
git status --short
git log --oneline -1
```

`output/`과 `.superpowers/`의 로컬 감사·시각 동반 산출물은 커밋하지 않는다.
