# Lumi Dashboard Copy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace system-oriented copy on every user-facing VideoBox dashboard page with concise, action-oriented Korean copy led by the video assistant Lumi where help is needed.

**Architecture:** Keep backend contracts, state values, test fixtures, and `data-*` selectors unchanged. Add a small UI-only copy policy test, then replace rendered strings in feature components and the existing `App.tsx` sections without changing mutation or loading flows. Lumi is the visible name for the Director, while internal names remain only in source/API boundaries.

**Tech Stack:** React 18, TypeScript, Vitest + Testing Library, Vite.

---

## File map

| File | Responsibility |
| --- | --- |
| `apps/web/src/user-copy-policy.test.ts` | Guards user-facing component source against forbidden implementation words and proves the agreed Lumi wording is present. |
| `apps/web/src/features/director/DirectorWorkspace.tsx` | Converts the Director panel title, labels, states, apply/retry notices, and accessible names to Lumi language. |
| `apps/web/src/features/director/ProposalComparisonTray.tsx` | Hides revision/raw preflight JSON and gives an action-focused recommendation summary. |
| `apps/web/src/features/director/DirectorHistoryControls.tsx` | Replaces stale revision diagnostics with understandable output-update messaging. |
| `apps/web/src/features/director/MediaReferenceBadge.tsx` | Uses recommendation/timeline labels without exposing implementation phrasing. |
| `apps/web/src/features/director/ProposalCandidateCard.tsx` | Makes preference controls and rights warnings user-readable. |
| `apps/web/src/features/media/ManualMediaLibrary.tsx` | Explains manual editing independently from Lumi’s recommendation availability. |
| `apps/web/src/features/media/MediaAnalysisPanel.tsx` | Turns analysis progress, empty states, and errors into user actions. |
| `apps/web/src/ProjectOnboarding.tsx` | Makes new-project steps and empty states concise and creator-focused. |
| `apps/web/src/App.tsx` | Applies the same language to sidebar, overview, timeline, review, editing, settings, voice, and output status messages. |
| Existing `*.test.tsx` files and `apps/web/src/app.test.tsx` | Assert visible wording while retaining existing behavior and selectors. |

### Task 1: Add the UI copy policy guard

**Files:**
- Create: `apps/web/src/user-copy-policy.test.ts`

- [ ] **Step 1: Write the failing policy test**

```ts
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const uiFiles = [
  "App.tsx",
  "ProjectOnboarding.tsx",
  "features/director/DirectorWorkspace.tsx",
  "features/director/ProposalComparisonTray.tsx",
  "features/director/DirectorHistoryControls.tsx",
  "features/media/ManualMediaLibrary.tsx",
  "features/media/MediaAnalysisPanel.tsx",
];

describe("user-facing dashboard copy", () => {
  it("uses Lumi and does not expose implementation terms in rendered UI", () => {
    const source = uiFiles.map((file) => readFileSync(resolve(import.meta.dirname, file), "utf8")).join("\n");
    expect(source).toContain("루미");
    expect(source).not.toMatch(/>[^<]*(?:Local Media Director|immutable preflight diff|revision)\b[^<]*</i);
  });
});
```

- [ ] **Step 2: Run the policy test and verify RED**

Run: `npm --prefix apps/web test -- src/user-copy-policy.test.ts`

Expected: FAIL because the current rendered Director UI contains `Local Media Director`, `revision`, and `immutable preflight diff`.

- [ ] **Step 3: Keep the guard scoped to rendered copy**

Do not forbid type names, API routes, comments, `aria` selectors used only by existing tests, or backend/API source. The regex must only inspect the curated UI files and literal rendered text.

- [ ] **Step 4: Commit the RED test only if the repository policy permits incremental commits**

```powershell
git add apps/web/src/user-copy-policy.test.ts
git commit -m "test: guard dashboard user copy"
```

### Task 2: Make the Director experience visibly Lumi

**Files:**
- Modify: `apps/web/src/features/director/DirectorWorkspace.tsx`
- Modify: `apps/web/src/features/director/ProposalComparisonTray.tsx`
- Modify: `apps/web/src/features/director/DirectorHistoryControls.tsx`
- Modify: `apps/web/src/features/director/MediaReferenceBadge.tsx`
- Modify: `apps/web/src/features/director/ProposalCandidateCard.tsx`
- Test: `apps/web/src/features/director/director-workspace.test.tsx`
- Test: `apps/web/src/features/director/proposal-comparison-tray.test.tsx`
- Test: `apps/web/src/features/director/director-history-controls.test.tsx`
- Test: `apps/web/src/features/director/media-reference-badge.test.tsx`
- Test: `apps/web/src/features/director/ProposalCandidateCard.test.tsx`

- [ ] **Step 1: Add failing behavior assertions**

Add assertions that render the current components and require these exact visible strings:

```tsx
expect(screen.getByRole("heading", { name: "루미" })).toBeInTheDocument();
expect(screen.getByRole("button", { name: "루미에게 추천받기" })).toBeInTheDocument();
expect(screen.getByText("루미가 지금 추천을 만들 수 없어요. 직접 골라 계속 편집할 수 있어요.")).toBeInTheDocument();
expect(screen.getByText("추천을 적용하기 전에 변경된 내용이 있는지 확인하고 있어요.")).toBeInTheDocument();
expect(screen.queryByText(/revision \d+/i)).not.toBeInTheDocument();
```

Use the existing component fixtures and callbacks; do not change the state-machine values (`idle`, `blocked`, `error`, `stale_proposal`) or API payloads.

- [ ] **Step 2: Run the Director tests and verify RED**

Run: `npm --prefix apps/web test -- src/features/director/director-workspace.test.tsx src/features/director/proposal-comparison-tray.test.tsx src/features/director/director-history-controls.test.tsx src/features/director/media-reference-badge.test.tsx src/features/director/ProposalCandidateCard.test.tsx`

Expected: FAIL because existing labels include `Local Media Director`, `디렉터 시작`, `revision`, raw preflight JSON, and internal-style controls.

- [ ] **Step 3: Replace only rendered strings with the approved copy**

Apply this mapping while preserving event handlers and roles:

```tsx
// DirectorWorkspace visible UI
"Local Media Director" -> "루미"
"디렉터 열기" -> "루미 열기"
"디렉터 시작" -> "루미에게 추천받기"
"디렉터 메시지" -> "루미에게 요청하기"
"상태: {effectiveState}" -> "루미가 추천을 준비하고 있어요."
"스크립트가 필요합니다." -> "먼저 대본을 만들거나 불러와 주세요."
"수동 편집 계속" -> "직접 편집하기"
"변경 적용" -> "이 추천 적용"
"제안 새로고침" -> "추천 다시 만들기"

// ProposalComparisonTray
"제안 비교와 사전 확인" -> "루미 추천 비교"
`{proposal.revision_code} · revision ...` -> `추천 ${selectedIds.length}개를 골랐어요.`
<pre aria-label="immutable preflight diff">...</pre> -> <p>추천을 적용하기 전에 변경된 내용이 있는지 확인하고 있어요.</p>
```

For blocked/error, stale, apply failure, and retry notices use the exact approved action-oriented messages. Keep machine-state `data-state`, callback order, and selection logic untouched.

- [ ] **Step 4: Run the Director tests and policy test to verify GREEN**

Run: `npm --prefix apps/web test -- src/user-copy-policy.test.ts src/features/director`

Expected: PASS.

- [ ] **Step 5: Commit the Director copy slice**

```powershell
git add apps/web/src/features/director apps/web/src/user-copy-policy.test.ts
git commit -m "feat: present Lumi in director workspace"
```

### Task 3: Clarify manual media, analysis, and onboarding copy

**Files:**
- Modify: `apps/web/src/features/media/ManualMediaLibrary.tsx`
- Modify: `apps/web/src/features/media/MediaAnalysisPanel.tsx`
- Modify: `apps/web/src/ProjectOnboarding.tsx`
- Test: `apps/web/src/features/media/manual-media-library.test.tsx`
- Test: `apps/web/src/features/media/media-analysis-panel.test.tsx`
- Test: `apps/web/src/project-onboarding.test.tsx`

- [ ] **Step 1: Write failing user-copy assertions**

```tsx
expect(screen.getByText("루미의 추천을 사용할 수 없어도 직접 미디어를 골라 계속 편집할 수 있어요.")).toBeInTheDocument();
expect(screen.getByText("미리보기는 현재 편집본을 바꾸지 않아요. 마음에 들면 프로젝트에 추가해 주세요.")).toBeInTheDocument();
expect(screen.getByRole("heading", { name: "영상 만들기 시작" })).toBeInTheDocument();
```

Also assert the absence of literal `Director blocked`, `세션`, `파이프라인`, and `job` in each rendered screen.

- [ ] **Step 2: Run media/onboarding tests and verify RED**

Run: `npm --prefix apps/web test -- src/features/media/manual-media-library.test.tsx src/features/media/media-analysis-panel.test.tsx src/project-onboarding.test.tsx`

Expected: FAIL because the existing messages mention Director state, editing session, and system processing terms.

- [ ] **Step 3: Replace rendered explanations without changing media behavior**

Use this minimum mapping:

```tsx
"Director 차단 상태입니다. 수동 라이브러리는 계속 사용할 수 있습니다."
  -> "루미의 추천을 사용할 수 없어도 직접 미디어를 골라 계속 편집할 수 있어요."
"미리보기는 편집 세션을 변경하지 않습니다. 배치는 아래 ‘적용’으로만 수행합니다."
  -> "미리보기는 현재 편집본을 바꾸지 않아요. 마음에 들면 프로젝트에 추가해 주세요."
"파이프라인" -> "제작 흐름"
"job 현황" -> "작업 진행 상황"
```

For analysis failures, describe the recoverable action (`다시 분석하기`, `직접 선택하기`) rather than provider, queue, or runtime cause. Preserve all `onClick`, disabled, and loading conditions.

- [ ] **Step 4: Run media/onboarding tests and policy test to verify GREEN**

Run: `npm --prefix apps/web test -- src/user-copy-policy.test.ts src/features/media/manual-media-library.test.tsx src/features/media/media-analysis-panel.test.tsx src/project-onboarding.test.tsx`

Expected: PASS.

- [ ] **Step 5: Commit the media/onboarding copy slice**

```powershell
git add apps/web/src/features/media apps/web/src/ProjectOnboarding.tsx apps/web/src/project-onboarding.test.tsx
git commit -m "feat: simplify media creation copy"
```

### Task 4: Rewrite all App dashboard page explanations

**Files:**
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/app.test.tsx`
- Test: `apps/web/src/user-copy-policy.test.ts`

- [ ] **Step 1: Add failing App integration assertions for every navigation page**

Extend existing App fixtures so that overview, timeline, review, editing, and settings each prove one user-facing sentence:

```tsx
expect(screen.getByText("영상, 음악, 자막을 한곳에서 편집하세요.")).toBeInTheDocument();
expect(screen.getByText("작업 진행 상황")).toBeInTheDocument();
expect(screen.getByText("루미는 이 컴퓨터에서 준비된 기능만 사용해요.")).toBeInTheDocument();
expect(screen.queryByText(/자동 런타임|loopback|fallback|API 키 설정/i)).not.toBeInTheDocument();
```

Add a focused test for each dashboard section rather than one brittle full-page text snapshot. Keep test requests and fake API behavior unchanged.

- [ ] **Step 2: Run the App copy tests and verify RED**

Run: `npm --prefix apps/web test -- src/app.test.tsx src/user-copy-policy.test.ts`

Expected: FAIL because the sidebar, settings, review/output notices, and editing page still display `job`, runtime/loopback/fallback, pipeline, session/revision, or raw system explanations.

- [ ] **Step 3: Convert every visible App explanation using the approved copy rules**

Use the following representative replacements and apply the same rule to every branch rendered by `selectedSection`:

```tsx
"로컬 검수" -> "내 영상 작업"
"job 현황" -> "작업 진행 상황"
"전체 job 현황 보기" -> "진행 상황 보기"
"등록된 job 없음" -> "진행 중인 작업이 없어요."
"로컬 프로젝트 없음" -> "아직 만든 영상이 없어요. 새 프로젝트를 시작해 보세요."
"자동 런타임은 이 컴퓨터의 LM Studio loopback 기능만 사용합니다. 외부 자동 fallback과 API 키 설정은 기본 화면에 노출하지 않습니다."
  -> "루미는 이 컴퓨터에서 준비된 기능만 사용해요."
```

For timeline/review/editing/export/voice error branches, retain meaningful product nouns (`미리보기`, `완성본`, `CapCut`, `자막`) but replace implementation nouns (`job`, `session`, `revision`, `pipeline`, `runtime`, `provider`, `fallback`) with current-edit/result/action wording. Do not change API calls, state variables, section IDs, or visual layout.

- [ ] **Step 4: Run focused App tests and the forbidden-copy guard to verify GREEN**

Run: `npm --prefix apps/web test -- src/app.test.tsx src/user-copy-policy.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit the App copy slice**

```powershell
git add apps/web/src/App.tsx apps/web/src/app.test.tsx apps/web/src/user-copy-policy.test.ts
git commit -m "feat: make dashboard copy creator-friendly"
```

### Task 5: Final copy audit and release verification

**Files:**
- Modify only if required by a discovered wording gap: files listed in Tasks 2–4
- Modify: `docs/development-status-2026-06-29.ko.md`

- [ ] **Step 1: Run a rendered-copy inventory and classify findings**

Run:

```powershell
rg -n --glob '*.tsx' --glob '!**/*.test.tsx' 'Local Media Director|immutable preflight diff|\brevision\b|\bjob\b|파이프라인|런타임|loopback|fallback|provider' apps/web/src
```

Expected: no user-visible occurrences. Type names, comments, API functions, test fixtures, and non-rendered technical diagnostics may remain only when they cannot appear in the dashboard.

- [ ] **Step 2: Run focused and full frontend verification**

Run:

```powershell
npm --prefix apps/web test -- src/user-copy-policy.test.ts src/app.test.tsx src/features/director src/features/media src/project-onboarding.test.tsx
npm --prefix apps/web test
npm --prefix apps/web run build
git diff --check
git status --short
```

Expected: all tests and build PASS; only intended source/test/status changes are present; no whitespace errors.

- [ ] **Step 3: Perform independent spec and quality review**

Spec review must verify all user-facing pages listed in the design are covered and that no behavior/API contract changed. Quality review must verify accessible labels remain meaningful, no brittle global replacement changed source-only strings, and the copy guard has no false positives.

- [ ] **Step 4: Update closeout status**

Add a dated top section to `docs/development-status-2026-06-29.ko.md` recording the user-copy scope, exact test/build totals, review outcome, commit SHA, push state, and any explicitly retained technical detail.

- [ ] **Step 5: Commit and push the closed copy change**

```powershell
git add apps/web docs/development-status-2026-06-29.ko.md
git commit -m "feat: present Lumi dashboard copy"
git push origin codex/production-readiness-blocker-slice-1
git rev-list --left-right --count '@{upstream}...HEAD'
```

Expected: upstream count is `0 0`.
