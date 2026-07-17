# VideoBox OSS Dashboard/Editor Adoption Slice 0 Task 1 Closeout

**Date:** 2026-07-17  
**State:** Task 1 complete; Task 2 visual approval is next.

## Closed scope

- Existing Lumi copy was preserved. The historical dirty Lumi UI scope was already included in upstream `main` before this task began; it was neither reset nor separated.
- Added an accessible selected state to existing project and workspace-section buttons.
- Added a legacy baseline for project switching, section/settings navigation, blocked Director manual fallback, and current-artifact availability versus stale preview/final regeneration guidance.
- Retained the AST-based Lumi copy policy (12 AST/forbidden-jargon assertions). The independent wording review separately applied three qualitative criteria: ordinary user verbs, an immediate next action, and no implementation identifiers.

## TDD and verification evidence

- The planning-time five TypeScript errors did not reproduce because they had already been resolved in current `HEAD`.
- RED: `npm --prefix apps/web test -- src/legacy-baseline.test.tsx` failed with expected project-selection assertion (`aria-pressed="true"` expected, attribute absent).
- GREEN: `npm --prefix apps/web test -- src/legacy-baseline.test.tsx src/user-copy-policy.test.ts src/features/director/DirectorContextBar.test.tsx src/features/director/director-history-controls.test.tsx` passed 21 tests.
- Full frontend: `npm --prefix apps/web test` passed 200 tests.
- Production build: `npm --prefix apps/web run build` succeeded.
- `git diff --check` succeeded. Independent spec compliance and code-quality reviews found no P0/P1/P2. Source-to-runtime reverse check traced the new `aria-pressed` source attributes through rendered role assertions; no Task 1 diff added a provider call or forbidden framework/runtime import.

## Boundaries retained

- No Hermes/container/Compose/host bridge implementation.
- No Tailwind, shadcn, router, OpenCut, or source-port work.
- No external/Gemini provider call was added; the local/test zero-call contract is unchanged.

## SSOT and next action

- Plan checkbox and top-level cumulative progress are updated to 1/22 (4.5%).
- Status SSOT `## 253` is the authoritative closeout pointer.
- AK-Wiki promotion was not performed: this is VideoBox-specific implementation evidence, not a general operating rule.

## Next-session goal prompt

```text
goal 명령으로 다음 목표를 시작해줘.

VideoBox OSS Dashboard/Editor Adoption Plan의 Slice 0 Task 2를 수행하라.

먼저 current HEAD/upstream/worktree와 다음 SSOT를 확인하라.
- docs/superpowers/plans/2026-07-17-videobox-oss-dashboard-editor-adoption.md
- docs/superpowers/specs/2026-07-17-videobox-oss-dashboard-editor-adoption-design.md
- docs/development-status-2026-06-29.ko.md
- docs/handoffs/2026-07-17-videobox-oss-dashboard-editor-adoption-slice-0-task-1-closeout.ko.md

Task 2의 세 화면/다섯 viewport(1920/1440/1280/768/390) visual prototype, artifact SHA/manifest verifier, 사용자 명시 승인 기록만 다뤄라. production shell/Tailwind/shadcn/router/OpenCut 구현과 Hermes/container 구현은 시작하지 말고, external/Gemini provider call 0을 유지하라.
```
