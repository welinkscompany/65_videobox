# VideoBox Yujin Conversation Starters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Add an accessible, design-system-consistent starter-chip area to the editor Right Dock that fills the Yujin composer without sending or mutating anything.

**Architecture:** Keep the feature local to \`RightDock\`. Define four immutable prompt records, render them only for the empty conversation/proposal state, and reuse the controlled \`draft\`/\`onDraftChange\` contract. A Right Dock-local focus target receives focus after a chip click; existing Hermes, proposal, approval, and \`EditorCommandPort\` paths remain unchanged.

**Tech Stack:** React 19, TypeScript, Vitest, Testing Library, existing VideoBox CSS variables and shadcn \`Button\`/\`Textarea\` primitives.

---

### Task 1: Add failing Right Dock behavior tests

**Files:**
- Modify: \`apps/web/src/features/editor/workbench/right-dock.test.tsx\`
- Reference: \`apps/web/src/features/editor/workbench/RightDock.tsx\`

- [x] **Step 1: Add the empty-state interaction test**

Add this test inside the existing \`describe("RightDock", ...)\` block:

~~~tsx
it("shows conversation starters that fill and focus the composer without sending", () => {
  const onDraftChange = vi.fn();
  const onSendMessage = vi.fn();
  render(<RightDock
    draft=""
    onDraftChange={onDraftChange}
    onSendMessage={onSendMessage}
    state="idle"
    runState={{ kind: "idle" }}
  />);

  expect(screen.getByRole("group", { name: "대화 스타터" })).toBeInTheDocument();
  const starter = screen.getByRole("button", { name: "이 장면에 어울리는 B-roll 추천해 줘" });
  expect(starter).toBeVisible();

  fireEvent.click(starter);

  expect(onDraftChange).toHaveBeenCalledWith("이 장면에 어울리는 B-roll 추천해 줘");
  expect(onSendMessage).not.toHaveBeenCalled();
  expect(screen.getByLabelText("유진에게 요청하기")).toHaveFocus();
});
~~~

- [x] **Step 2: Add visibility and disabled-state tests**

Add these tests after the previous test:

~~~tsx
it("hides conversation starters once a conversation or proposal exists", () => {
  const { rerender } = render(<RightDock
    draft=""
    onDraftChange={vi.fn()}
    messages={[{ id: "message-1", role: "user", text: "요청" }]}
  />);

  expect(screen.queryByRole("group", { name: "대화 스타터" })).not.toBeInTheDocument();

  rerender(<RightDock draft="" onDraftChange={vi.fn()} proposal={proposal} />);

  expect(screen.queryByRole("group", { name: "대화 스타터" })).not.toBeInTheDocument();
});

it("disables conversation starters when the composer is disabled", () => {
  render(<RightDock draft="" onDraftChange={vi.fn()} composerDisabled />);

  expect(screen.getByRole("button", { name: "이 장면에 어울리는 B-roll 추천해 줘" })).toBeDisabled();
});
~~~

- [x] **Step 3: Run the focused test file and verify RED**

Run:

~~~powershell
npm --prefix apps/web test -- src/features/editor/workbench/right-dock.test.tsx
~~~

Expected: FAIL because \`RightDock\` does not yet render a \`대화 스타터\` group or starter button.

### Task 2: Implement the minimal starter-chip interaction

**Files:**
- Modify: \`apps/web/src/features/editor/workbench/RightDock.tsx\`
- Modify: \`apps/web/src/styles/editor-workbench.css\`

- [x] **Step 1: Add the prompt records and scoped composer focus target**

After \`staleProposalMessage\`, add:

~~~tsx
const conversationStarters = [
  "이 장면에 어울리는 B-roll 추천해 줘",
  "현재 편집 흐름 점검해 줘",
  "자막을 더 간결하게 다듬어 줘",
  "세로 영상용으로 바꿀 부분 찾아 줘",
] as const;
~~~

Inside \`RightDock\`, alongside \`historyRef\`, add a ref to a wrapper around the existing composer. The wrapper keeps focus local to this Right Dock instance without changing the shared Textarea primitive.

~~~tsx
const composerRef = useRef<HTMLTextAreaElement>(null);
~~~

After \`canSend\`, add:

~~~tsx
const showConversationStarters = messages.length === 0 && !proposal;
const chooseConversationStarter = (starter: string) => {
  onDraftChange(starter);
  composerRef.current?.focus();
};
~~~

- [x] **Step 2: Render the accessible empty-state starter group**

Replace the current empty-history branch with this structure:

~~~tsx
{messages.length
  ? messages.map((message) => <article key={message.id}><p><strong>{message.role === "user" ? "나" : "유진"}</strong> {message.text}</p></article>)
  : <>
      <p>유진 대화는 아직 시작하지 않았어요.</p>
      {showConversationStarters ? <div role="group" aria-label="대화 스타터" className="vb-editor-right-dock__starters">
        <strong>무엇을 도와드릴까요?</strong>
        <span>스타터를 누르면 요청 문장이 입력창에 채워져요.</span>
        <div className="vb-editor-right-dock__starter-list">
          {conversationStarters.map((starter) => <Button
            key={starter}
            type="button"
            variant="outline"
            disabled={composerDisabled}
            onClick={() => chooseConversationStarter(starter)}
          >{starter}</Button>)}
        </div>
      </div> : null}
    </>}
~~~

Wrap the existing \`Textarea\` with the scoped ref and focus its descendant textarea after selection. The click handler must only call \`onDraftChange\` and focus; it must not call \`onSendMessage\`, \`onStart\`, \`onApplyProposal\`, \`onManualEdit\`, or a backend client.

- [x] **Step 3: Add compact chip styling using existing tokens**

Append to \`apps/web/src/styles/editor-workbench.css\`:

~~~css
.vb-editor-right-dock__starters { display: grid; gap: 0.3rem; padding: 0.2rem 0; }
.vb-editor-right-dock__starters strong { font-size: 0.85rem; }
.vb-editor-right-dock__starters > span { color: var(--muted-foreground); font-size: 0.75rem; }
.vb-editor-right-dock__starter-list { display: flex; flex-wrap: wrap; gap: 0.35rem; }
.vb-editor-right-dock__starter-list > button { min-height: 2rem; height: auto; padding: 0.35rem 0.55rem; border-radius: 999px; color: var(--foreground); font-size: 0.75rem; line-height: 1.35; text-align: left; white-space: normal; }
~~~

### Task 3: Run focused verification and inspect the diff

**Files:**
- Verify: \`apps/web/src/features/editor/workbench/right-dock.test.tsx\`
- Verify: \`apps/web/src/features/editor/workbench/RightDock.tsx\`
- Verify: \`apps/web/src/styles/editor-workbench.css\`

- [x] **Step 1: Run the focused Right Dock tests**

~~~powershell
npm --prefix apps/web test -- src/features/editor/workbench/right-dock.test.tsx
~~~

Expected: the full Right Dock test file passes, including the new starter tests.

- [x] **Step 2: Run related editor tests**

~~~powershell
npm --prefix apps/web test -- src/features/editor/workbench/editor-workbench-route.test.tsx src/features/editor/workbench/editor-workbench.test.tsx src/features/editor/workbench/yujin-memory-panel.test.tsx
~~~

Expected: all listed files pass and existing \`유진에게 추천받기\` behavior remains covered.

- [x] **Step 3: Run build and whitespace checks**

~~~powershell
npm --prefix apps/web run build
git diff --check
~~~

Expected: production build succeeds; any existing Vite chunk-size warning is non-failing; \`git diff --check\` emits no errors.

- [x] **Step 4: Review the diff for scope violations**

~~~powershell
git diff --stat
git diff -- apps/web/src/features/editor/workbench/RightDock.tsx apps/web/src/features/editor/workbench/right-dock.test.tsx apps/web/src/styles/editor-workbench.css
~~~

Confirm the diff contains only UI, styling, and tests; no Hermes route, gateway, proposal, store, FFmpeg, filesystem, shell, database, or editor mutation changes are present.

### Task 4: Commit the implementation

**Files:**
- Commit: \`apps/web/src/features/editor/workbench/RightDock.tsx\`
- Commit: \`apps/web/src/features/editor/workbench/right-dock.test.tsx\`
- Commit: \`apps/web/src/styles/editor-workbench.css\`

- [x] **Step 1: Stage only the implementation files**

~~~powershell
git add -- apps/web/src/features/editor/workbench/RightDock.tsx apps/web/src/features/editor/workbench/right-dock.test.tsx apps/web/src/styles/editor-workbench.css
~~~

- [x] **Step 2: Create the implementation commit**

~~~powershell
git commit -m "feat: add Yujin conversation starters"
~~~

- [x] **Step 3: Verify the final worktree state**

~~~powershell
git status -sb
git rev-parse HEAD
~~~

Expected: implementation commit is at HEAD and the worktree contains no unintended tracked changes. Do not claim owner acceptance; live Hermes chat and real-browser owner verification remain separate gates.

## Closeout evidence (status reconciled 2026-08-13)

- Implementation commit: `2a4e28eb7` (`feat: add Yujin conversation starters`).
- Current source renders four immutable starters only for the empty idle conversation/proposal state; click fills and focuses the composer without sending or mutating.
- The implementation uses a Right Dock-local composer wrapper ref and stronger `state === "idle"` / `runState.kind === "idle"` visibility guards than the initial sketch above.
- Fresh focused verification: `right-dock.test.tsx` **15 passed**. The broader editor suite and production build also passed on the current branch before this plan-status update.
- This focused plan is complete. Wave 4 Task 1 remains separate because it additionally requires contextual registries, `다른 예시`, `전체 보기`, and usage-frequency promotion.
