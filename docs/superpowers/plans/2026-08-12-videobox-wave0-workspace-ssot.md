# VideoBox Wave 0 Workspace and SSOT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 새 제품 범위를 공식 SSOT에 반영하고, 프로젝트 우선 진입과 단순한 전역·프로젝트 메뉴를 기존 URL 호환성을 유지하며 제공한다.

**Architecture:** 전역 목적지와 프로젝트 제작 단계를 별도 타입으로 분리한다. 기존 프로젝트 URL은 입력 호환 경로로 유지하되 새 canonical location으로 해석하고, 상태는 서버 `ProjectWorkspaceSummary`가 제공해 화면이 실패를 빈 프로젝트로 추정하지 않게 한다.

**Tech Stack:** Markdown SSOT, React 19, TypeScript, Vite, Vitest, Playwright, FastAPI/Pydantic.

---

### Task 0: Reconcile authoritative scope

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/implementation-plan.ko.md`
- Modify: `docs/superpowers/specs/2026-08-12-videobox-creator-workspace-overhaul-design.ko.md`
- Test: `tests/test_documentation_contract.py`

- [ ] **Step 1: Write the failing authority test.** Add assertions that the root guidance identifies VideoBox as a creator-complete lightweight editor, makes CapCut optional, and still excludes advanced grading/masks/keyframes/multicam.

```python
def test_creator_workspace_decision_supersedes_capcut_normal_finish() -> None:
    root = Path("CLAUDE.md").read_text(encoding="utf-8")
    plan = Path("docs/implementation-plan.ko.md").read_text(encoding="utf-8")
    for text in (root, plan):
        assert "VideoBox 내부" in text
        assert "CapCut" in text and "선택" in text
        assert "색보정" in text and "키프레임" in text and "멀티캠" in text
```

- [ ] **Step 2: Run RED.** Run `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_documentation_contract.py -q`. Expected: FAIL because the old CapCut handoff boundary remains.
- [ ] **Step 3: Replace only the conflicting scope paragraphs.** State that cut, captions, B-roll, music, SFX, linked aspect variants, review and MP4 output finish in VideoBox; keep advanced grading, masks, arbitrary keyframes, multicam and advanced motion outside scope. Change the design status to `owner 최종 승인 완료`.
- [ ] **Step 4: Run GREEN and inspect terms.** Repeat the focused pytest command and run `rg -n "풀 자체 편집기|CapCut으로 넘겨도" CLAUDE.md docs/implementation-plan.ko.md`; expected pytest PASS and no stale normative sentence.
- [ ] **Step 5: Commit.** `git add CLAUDE.md docs/implementation-plan.ko.md docs/superpowers/specs/2026-08-12-videobox-creator-workspace-overhaul-design.ko.md tests/test_documentation_contract.py && git commit -m "docs: align creator complete editor scope"`.

### Task 1: Split global destinations from project stages

**Files:**
- Modify: `apps/web/src/app/routeManifest.ts`
- Modify: `apps/web/src/app/routeManifest.test.ts`
- Modify: `apps/web/src/app/AppRouter.tsx`
- Modify: `apps/web/src/app/AppRouter.test.tsx`

- [ ] **Step 1: Add failing route tests.** Define the intended contract in the test.

```ts
expect(resolveGlobalLocation("library")).toBe("/library")
expect(resolveGlobalLocation("footage")).toBe("/footage")
expect(resolveProjectStage("p1", "assets")).toBe("/projects/p1/assets")
expect(parseWorkspaceLocation("/projects/p1/media")).toMatchObject({ projectId: "p1", stage: "assets", legacy: true })
expect(parseWorkspaceLocation("/projects/p1/outputs")).toMatchObject({ projectId: "p1", stage: "output", legacy: true })
```

- [ ] **Step 2: Run RED.** `npm --prefix apps/web test -- src/app/routeManifest.test.ts`; expected FAIL because global locations and stage aliases do not exist.
- [ ] **Step 3: Implement focused types.** Add `GlobalDestination = "projects" | "library" | "footage" | "settings"` and `ProjectStage = "plan" | "assets" | "edit" | "review" | "output"`. Preserve parsing for `home/create/media/editing/review/outputs` and return canonical stage metadata instead of removing routes.
- [ ] **Step 4: Wire routes to existing owners.** Route `plan` to existing creation/home content, `assets` to `MediaWorkspacePage`, `edit` to `CanonicalEditorEntry`, `review` and `output` to their existing pages. Route `/library` and `/footage` to honest Wave-1/Wave-2 준비 상태 with keywords `내 라이브러리`, `촬영본 정리`; do not fake functionality.
- [ ] **Step 5: Run GREEN.** `npm --prefix apps/web test -- src/app/routeManifest.test.ts src/app/AppRouter.test.tsx`; expected PASS.
- [ ] **Step 6: Commit.** `git add apps/web/src/app/routeManifest.ts apps/web/src/app/routeManifest.test.ts apps/web/src/app/AppRouter.tsx apps/web/src/app/AppRouter.test.tsx && git commit -m "feat: separate global and project navigation"`.

### Task 2: Add authoritative project workspace summary

**Files:**
- Modify: `services/api/src/videobox_api/routers/projects.py`
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/app/AppRouter.tsx`
- Test: `tests/test_api.py`
- Test: `apps/web/src/app/AppRouter.test.tsx`

- [ ] **Step 1: Add failing API tests.** Assert `GET /api/projects/{id}/workspace-summary` returns `project_id`, `display_name`, `updated_at`, `current_stage`, `state`, `thumbnail_url`, `finished_video_count`, `next_action`; simulate latest-session lookup failure and assert 503 `workspace_summary_unavailable`, never an empty/create state.
- [ ] **Step 2: Run RED.** Run `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_api.py -q -k workspace_summary`. Expected: FAIL endpoint missing.
- [ ] **Step 3: Implement the DTO and endpoint.** Add a strict response model with `current_stage: Literal["plan","assets","edit","review","output"]`, `state: Literal["ready","attention","blocked"]`, and `next_action` containing creator-language `label` and canonical `href`. Derive only from project/store records; do not swallow database exceptions.
- [ ] **Step 4: Add typed client and card states.** Add `ProjectWorkspaceSummary` and `api.getProjectWorkspaceSummary`. Render thumbnail, updated time, stage, finished count and exactly one action. A failed request renders `상태 확인 필요` and `다시 확인`; it must not navigate to creation.
- [ ] **Step 5: Run GREEN.** Run `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_api.py -q -k workspace_summary` and `npm --prefix apps/web test -- src/app/AppRouter.test.tsx`.
- [ ] **Step 6: Commit.** `git add services/api/src/videobox_api/routers/projects.py services/api/src/videobox_api/models.py apps/web/src/api.ts apps/web/src/app/AppRouter.tsx tests/test_api.py apps/web/src/app/AppRouter.test.tsx && git commit -m "feat: expose truthful project workspace summaries"`.

### Task 3: Implement desktop shell hierarchy and keyword copy

**Files:**
- Modify: `apps/web/src/app/ProductShell.tsx`
- Modify: `apps/web/src/styles/product-shell.css`
- Modify: `apps/web/src/app/ProductShell.test.tsx`
- Modify: `docs/oss/editor-ui-source-map.json`
- Test: `tests/test_editor_ui_source_provenance.py`
- Test: `apps/web/e2e/product-shell.spec.mjs`

- [ ] **Step 1: Add failing DOM tests.** Assert four global destinations, a separate five-stage project rail only when a project is open, one `main`, dynamic collapse names, and no prohibited dashboard words from §10.13.
- [ ] **Step 2: Run RED.** `npm --prefix apps/web test -- src/app/ProductShell.test.tsx`; expected FAIL on current mixed menu.
- [ ] **Step 3: Implement shell hierarchy.** Use the approved white/orange tokens, 40px buttons, 8px related/16px group gaps, internal scroll, and desktop minimum `1280×800`. Keep the project menu/archive controls behind `더보기`.
- [ ] **Step 4: Refresh provenance.** Update both normalized `ProductShell.tsx` hashes in `docs/oss/editor-ui-source-map.json` using the repository verifier convention.
- [ ] **Step 5: Run GREEN and provenance.** Run `npm --prefix apps/web test -- src/app/ProductShell.test.tsx` and `& 'D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility\.venv\Scripts\python.exe' -m pytest tests/test_editor_ui_source_provenance.py -q`.
- [ ] **Step 6: Verify real browser.** Rebuild with `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\owner-ready.ps1 -Mode Start -Rebuild -Json`, then Check. Open projects and one project at all four desktop viewports; capture sidebar, stage rail, button spacing and internal scroll. Prove collapsed → expanded reverse action.
- [ ] **Step 7: Commit.** `git add apps/web/src/app/ProductShell.tsx apps/web/src/styles/product-shell.css apps/web/src/app/ProductShell.test.tsx apps/web/e2e/product-shell.spec.mjs docs/oss/editor-ui-source-map.json && git commit -m "feat: establish desktop creator workspace shell"`.

### Task 4: Wave 0 regression and gate

- [ ] Run `npm --prefix apps/web test -- src/app/routeManifest.test.ts src/app/AppRouter.test.tsx src/app/ProductShell.test.tsx`.
- [ ] Run `npm --prefix apps/web run build` and `npm --prefix apps/web run test:e2e`.
- [ ] Run `git diff --check` and a read-only review for legacy URL loops, stale-response project switches, ARIA names and prohibited copy.
- [ ] Record a gap table covering design §§4–5 and pin screenshots to ignored `artifacts/qa/creator-workspace-overhaul/wave0/`.
- [ ] Commit only the closeout note if needed: `git commit -m "docs: close creator workspace wave 0"`.
