# CapCut Gap Follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 캡컷 비교에서 확인한 승인 가능한 VideoBox 잔여 작업을 기존 편집 셸 안에서 구현한다.

**Architecture:** B-roll의 `fit`은 이미 `EditorControls`와 명령 포트가 지원하므로 inspector 필드만 정본에 추가한다. 선택 구간은 기존 exact-preview 생성 경로를 재사용하고, 백엔드의 selected-range read model을 먼저 확인한 뒤 현재 revision에 맞는 미리보기를 요청한다. 자막 스타일 저장은 기존 저장 경로 앞에 영향 범위 사전 확인을 두며, 색·배치는 변경하지 않는다.

**Tech Stack:** React, TypeScript, Vitest, Testing Library, 기존 VideoBox API/FFmpeg exact-preview 경로.

---

### Task 1: B-roll 화면 맞춤/채우기 조작

**Files:**
- Modify: `apps/web/src/features/editor/inspector/inspectorRegistry.ts`
- Modify: `apps/web/src/features/editor/inspector/InspectorControls.tsx`
- Test: `apps/web/src/features/editor/inspector/inspectorRegistry.test.ts`
- Test: `apps/web/src/features/editor/inspector/InspectorControls.test.tsx`

- [ ] **Step 1: RED — B-roll registry가 `fit`을 노출해야 한다는 시험을 추가한다.**

```ts
it("includes fit in the editable B-roll fields", () => {
  const target = projectInspectorTargets({ view: brollView, selectedSegmentId: "seg-1" })
    .find((item) => item.kind === "media" && item.mediaKind === "broll");
  expect(target?.fields).toContain("fit");
});
```

- [ ] **Step 2: RED 검증 — 해당 시험이 `fit` 누락으로 실패하는지 확인한다.**

Run: `npm --prefix apps/web exec vitest run src/features/editor/inspector/inspectorRegistry.test.ts -t "includes fit"`

Expected: FAIL because `brollFields` excludes `fit`.

- [ ] **Step 3: RED — inspector가 현재 값과 저장 payload를 보여 주는 시험을 추가한다.**

```tsx
it("shows and saves B-roll fit mode", () => {
  const onAction = vi.fn();
  render(<InspectorControls onAction={onAction} selectedSegment={segment} target={{ ...brollTarget, controls: { ...brollTarget.controls, fit: "crop" }, fields: [...brollTarget.fields, "fit"] }} />);
  expect(screen.getByRole("combobox", { name: "B-roll 화면 맞춤" })).toHaveValue("crop");
  fireEvent.change(screen.getByRole("combobox", { name: "B-roll 화면 맞춤" }), { target: { value: "fit" } });
  fireEvent.click(screen.getByRole("button", { name: "B-roll 설정 저장" }));
  expect(onAction).toHaveBeenCalledWith(expect.objectContaining({ kind: "save-media", controls: expect.objectContaining({ fit: "fit" }) }));
});
```

- [ ] **Step 4: RED 검증 — UI 시험이 화면 손잡이 누락으로 실패하는지 확인한다.**

Run: `npm --prefix apps/web exec vitest run src/features/editor/inspector/InspectorControls.test.tsx -t "shows and saves B-roll fit mode"`

- [ ] **Step 5: GREEN — `MediaField`, `brollFields`, inspector state와 저장 payload에 `fit`을 추가하고 한글 키워드 선택지를 렌더한다.**

선택지는 `화면 안에 맞추기`(`fit`)와 `화면 채우기`(`crop`) 두 개만 제공한다. 기존 색·배치·다른 미디어 필드는 변경하지 않는다.

- [ ] **Step 6: GREEN 검증 — 두 시험을 다시 실행해 통과시킨다.**

Run: `npm --prefix apps/web exec vitest run src/features/editor/inspector/inspectorRegistry.test.ts src/features/editor/inspector/InspectorControls.test.tsx -t "fit|B-roll fit"`

- [ ] **Step 7: 커밋 — 기능 단위로 커밋한다.**

```powershell
git add apps/web/src/features/editor/inspector/inspectorRegistry.ts apps/web/src/features/editor/inspector/InspectorControls.tsx apps/web/src/features/editor/inspector/inspectorRegistry.test.ts apps/web/src/features/editor/inspector/InspectorControls.test.tsx
git commit -m "기능: B-roll 화면 맞춤과 채우기 조작 추가"
```

### Task 2: 선택 구간 미리보기와 자막 영향 범위 확인

**Files:**
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbench.tsx`
- Modify: `apps/web/src/features/editor/workbench/editorWorkbenchReadOnlyAdapters.tsx`
- Modify: `apps/web/src/features/editor/workbench/RightDock.tsx`
- Test: `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`
- Test: `apps/web/src/features/editor/workbench/right-dock.test.tsx`

- [ ] **Step 1: RED — 선택 구간 미리보기 버튼이 selected-range API와 exact-preview를 순서대로 호출한다는 route 시험을 추가한다.**

```tsx
it("preflights and renders the selected scene range", async () => {
  vi.spyOn(api.previewEditingSessionSelectedRange).mockResolvedValue(selectedRangeFixture);
  vi.spyOn(api.startExactPreview).mockResolvedValue(exactPreviewFixture);
  renderRoute({ selectedSegmentId: "seg-1" });
  fireEvent.click(await screen.findByRole("button", { name: "선택 구간 미리보기" }));
  await waitFor(() => expect(api.previewEditingSessionSelectedRange).toHaveBeenCalledWith("project-a", "session-a", { start_sec: 0, end_sec: 2 }));
  expect(api.startExactPreview).toHaveBeenCalledWith("project-a", "session-a", { expected_revision: 1, start_sec: 0, end_sec: 2 });
});
```

- [ ] **Step 2: RED 검증 — 버튼과 callback이 없어 실패하는지 확인한다.**

Run: `npm --prefix apps/web exec vitest run src/features/editor/workbench/editor-workbench-route.test.tsx -t "selected scene range"`

- [ ] **Step 3: RED — 자막 스타일 저장 전 영향 범위 확인 UI 시험을 추가한다.**

```tsx
it("shows caption style impact before saving", async () => {
  const onAction = vi.fn();
  render(<InspectorControls onAction={onAction} target={captionTarget} selectedSegment={segment} projectId="project-a" />);
  fireEvent.click(screen.getByRole("button", { name: "자막 스타일 저장" }));
  expect(onAction).toHaveBeenCalledWith(expect.objectContaining({ kind: "preflight-caption-style" }));
});
```

- [ ] **Step 4: RED 검증 — 현재 저장 action만 발생하므로 실패하는지 확인한다.**

Run: `npm --prefix apps/web exec vitest run src/features/editor/inspector/InspectorControls.test.tsx -t "impact before saving"`

- [ ] **Step 5: GREEN — route callback과 RightDock 전달 경로를 추가하고, 선택 구간 preflight 후 exact-preview를 현재 revision으로 요청한다.**

미리보기 실패 시 기존 수동 새로 만들기 상태를 유지하고, 성공 시 `refreshToken`으로 manifest를 다시 읽는다. 자막 스타일은 기존 저장 payload를 그대로 사용하되 preflight 결과의 영향 장면 수를 확인 문구로 표시한 뒤 저장한다.

- [ ] **Step 6: GREEN 검증 — route·dock·preview 관련 focused 시험을 통과시킨다.**

Run: `npm --prefix apps/web exec vitest run src/features/editor/workbench/editor-workbench-route.test.tsx src/features/editor/workbench/right-dock.test.tsx src/features/editor/inspector/InspectorControls.test.tsx -t "selected scene range|impact before saving"`

- [ ] **Step 7: 커밋 — 미리보기/영향 범위 연결을 커밋한다.**

```powershell
git add apps/web/src/features/editor/workbench apps/web/src/features/editor/inspector/InspectorControls.tsx apps/web/src/features/editor/inspector/InspectorControls.test.tsx
git commit -m "기능: 선택 구간 미리보기와 자막 영향 확인 연결"
```

### Task 3: 자막·화면 요소 진입점 개선

**Files:**
- Modify: `apps/web/src/features/editor/workbench/RightDock.tsx`
- Modify: `apps/web/src/features/editor/inspector/inspectorRegistry.ts`
- Test: `apps/web/src/features/editor/workbench/right-dock.test.tsx`
- Test: `apps/web/src/features/editor/inspector/inspectorRegistry.test.ts`

- [ ] **Step 1: RED — 여러 편집 대상이 있을 때 키워드형 빠른 선택 버튼이 보인다는 시험을 추가한다.**

```tsx
it("exposes keyword shortcuts for caption and screen elements", () => {
  render(<RightDock {...propsWithMultipleInspectorTargets} />);
  expect(screen.getByRole("tab", { name: "자막" })).toBeVisible();
  expect(screen.getByRole("tab", { name: "화면 요소" })).toBeVisible();
});
```

- [ ] **Step 2: RED 검증 — 현재는 combobox만 있어 실패하는지 확인한다.**

Run: `npm --prefix apps/web exec vitest run src/features/editor/workbench/right-dock.test.tsx -t "keyword shortcuts"`

- [ ] **Step 3: GREEN — 기존 오른쪽 도크 안에만 `자막`, `화면 요소`, `영상·소리` 탭을 추가하고 선택한 target id만 바꾼다.**

탭은 기존 흰색 셸·오른쪽 도크 위치를 유지하며, 효과·필터·스티커 라이브러리는 만들지 않는다. 대상이 없는 탭은 disabled 처리한다.

- [ ] **Step 4: GREEN 검증 — focused dock 시험을 통과시킨다.**

Run: `npm --prefix apps/web exec vitest run src/features/editor/workbench/right-dock.test.tsx src/features/editor/inspector/inspectorRegistry.test.ts`

- [ ] **Step 5: 커밋 — 진입점 개선을 커밋한다.**

```powershell
git add apps/web/src/features/editor/workbench/RightDock.tsx apps/web/src/features/editor/inspector/inspectorRegistry.ts apps/web/src/features/editor/workbench/right-dock.test.tsx apps/web/src/features/editor/inspector/inspectorRegistry.test.ts
git commit -m "개선: 자막과 화면 요소 편집 진입점 정리"
```

### Task 4: 통합 검증과 역방향 확인

**Files:**
- No production files; verification only.

- [ ] **Step 1: 웹 focused 시험과 타입 검사를 실행한다.**

Run from `apps/web`: `npx vitest run` and `npx tsc --noEmit`.

- [ ] **Step 2: 백엔드 전체 시험을 표준 Python으로 단독 실행한다.**

Run: `.venv/Scripts/python.exe -m pytest`.

- [ ] **Step 3: rebuild 컨테이너를 시작하고 `/health`를 확인한다.**

Run: `./scripts/owner-ready.ps1 -Mode Start -Rebuild -WithYujinMemory`.

- [ ] **Step 4: 실제 브라우저에서 B-roll 맞춤/채우기, 선택 구간 미리보기, 자막·화면 요소 탭을 역방향 확인한다.**

확인할 것은 버튼이 존재하는지뿐 아니라 저장 후 다시 읽었을 때 값이 유지되는지, 미리보기 요청이 선택 구간으로 나가는지, 빈 대상 탭이 눌리지 않는지다.

- [ ] **Step 5: 코드리뷰 후 발견 사항을 반영하고 마지막 검증을 다시 실행한다.**

- [ ] **Step 6: 한글 커밋·푸시와 새 인계 문서를 작성한다.**

