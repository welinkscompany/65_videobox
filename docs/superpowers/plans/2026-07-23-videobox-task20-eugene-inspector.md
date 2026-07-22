# VideoBox Task 20 Eugene conversation, recommendations, and Inspector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use \`subagent-driven-development\` (recommended) or \`executing-plans\` to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Add a persistent, manual-fallback-safe Eugene RightDock with inline recommendations and a typed Inspector without adding provider/API scope or a second media player.

**Architecture:** \`EditorWorkbenchRoute\` owns existing Director API reads, explicit proposal apply, route epoch, and revisioned Inspector mutations. New RightDock and Inspector modules are presentation/pure-projection layers receiving DTOs and callbacks only; \`EditorWorkbench\` continues to own dock lifetime and the sole \`PreviewStage\` audition request.

**Tech Stack:** React, TypeScript, Vitest, Testing Library, existing VideoBox API client and \`EditorCommandPort\`.

---

## File map

- Create: \`apps/web/src/features/editor/inspector/inspectorRegistry.ts\` — pure selection-to-supported-fields projection.
- Create: \`apps/web/src/features/editor/inspector/inspectorRegistry.test.ts\` — supported/absent controls tests.
- Create: \`apps/web/src/features/editor/workbench/RightDock.tsx\` — callback-only Eugene history, inline cards, Inspector disclosure.
- Create: \`apps/web/src/features/editor/workbench/right-dock.test.tsx\` — preservation, fallback, and no-player tests.
- Modify: \`apps/web/src/features/editor/workbench/EditorWorkbench.tsx\` — selected segment, audition request, and RightDock callback wiring.
- Modify: \`apps/web/src/features/editor/workbench/editorWorkbenchReadOnlyAdapters.tsx\` — replace right placeholders.
- Modify: \`apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx\` — route-owned Director lifecycle and Inspector command fence.
- Modify: \`apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx\` — epoch/current-revision/zero-retry contract.
- Modify: \`apps/web/src/features/editor/workbench/editor-workbench.test.tsx\` — right-dock one-stage integration.
- Modify: \`apps/web/src/styles/editor-workbench.css\` — scoped dock styles.

## Task 1: Build the pure Inspector registry

**Files:**
- Create: \`apps/web/src/features/editor/inspector/inspectorRegistry.ts\`
- Test: \`apps/web/src/features/editor/inspector/inspectorRegistry.test.ts\`

- [ ] **Step 1: Write the failing supported-selection test.**

\`\`\`ts
it("projects only current command-port fields for a BGM clip", () => {
  expect(projectInspectorTargets({ view, selectedSegmentId: "segment-1" })).toContainEqual({
    id: "clip:bgm-1", kind: "media", label: "배경 음악", segmentId: "segment-1",
    fields: ["fadeInSec", "fadeOutSec"],
  });
});

it("never projects voice, effects, or independent caption timing", () => {
  const fields = projectInspectorTargets({ view, selectedSegmentId: "segment-1" }).flatMap((target) => target.fields);
  expect(fields).not.toEqual(expect.arrayContaining(["voice", "keyframe", "mask", "transition", "captionStartSec", "captionEndSec"]));
});
\`\`\`

- [ ] **Step 2: Run test to verify it fails.**

Run: \`npm --prefix apps/web run test -- --run src/features/editor/inspector/inspectorRegistry.test.ts\`

Expected: FAIL because \`./inspectorRegistry\` does not exist.

- [ ] **Step 3: Write the minimal pure implementation.**

\`\`\`ts
export type InspectorTarget =
  | Readonly<{ id: string; kind: "media"; label: string; segmentId: string; mediaKind: "bgm" | "sfx"; fields: readonly ["fadeInSec", "fadeOutSec"] }>
  | Readonly<{ id: string; kind: "caption"; label: string; segmentId: string; fields: readonly ["text", "style"] }>
  | Readonly<{ id: string; kind: "overlay"; label: string; segmentId: string; overlayKind: "explanation-card" | "image" | "table"; fields: readonly string[] }>;

export function projectInspectorTargets({ view, selectedSegmentId }: { view: EditorViewModel; selectedSegmentId: string | null }): readonly InspectorTarget[] {
  if (!selectedSegmentId) return [];
  // Reduce only this segment's broll/bgm/sfx clips, linked caption, and exact supported overlay variants.
}
\`\`\`

Use only \`EditorViewModel\`; do not import React, \`api\`, \`EditorCommandPort\`, browser globals, or OpenCut terms. B-roll renderer controls stay absent because the current manifest response rejects their stored fields; unsupported selection returns an empty array.

- [ ] **Step 4: Run test to verify it passes.**

Run: \`npm --prefix apps/web run test -- --run src/features/editor/inspector/inspectorRegistry.test.ts\`

Expected: PASS.

- [ ] **Step 5: Commit.**

\`\`\`powershell
git add apps/web/src/features/editor/inspector/inspectorRegistry.ts apps/web/src/features/editor/inspector/inspectorRegistry.test.ts
git commit -m "feat: project supported editor Inspector controls"
\`\`\`

## Task 2: Implement callback-only state-preserving RightDock

**Files:**
- Create: \`apps/web/src/features/editor/workbench/RightDock.tsx\`
- Test: \`apps/web/src/features/editor/workbench/right-dock.test.tsx\`
- Modify: \`apps/web/src/features/editor/workbench/editorWorkbenchReadOnlyAdapters.tsx\`
- Modify: \`apps/web/src/styles/editor-workbench.css\`

- [ ] **Step 1: Write the failing preservation and manual-fallback tests.**

\`\`\`tsx
it("keeps draft, chosen recommendation, scroll, and audition request when Inspector toggles", () => {
  const onPreview = vi.fn();
  render(<RightDock {...readyProps} onPreviewCandidate={onPreview} />);
  const history = screen.getByRole("log", { name: "유진 대화" });
  history.scrollTop = 41;
  fireEvent.change(screen.getByLabelText("유진에게 요청하기"), { target: { value: "음악을 더 차분하게" } });
  fireEvent.click(screen.getByRole("checkbox", { name: "추천 1 고르기" }));
  fireEvent.click(screen.getByRole("button", { name: "추천 1 원본 미리보기" }));
  fireEvent.click(screen.getByRole("button", { name: "편집 항목 열기" }));
  fireEvent.click(screen.getByRole("button", { name: "편집 항목 닫기" }));
  expect(screen.getByLabelText("유진에게 요청하기")).toHaveValue("음악을 더 차분하게");
  expect(screen.getByRole("checkbox", { name: "추천 1 고르기" })).toBeChecked();
  expect(history.scrollTop).toBe(41);
  expect(onPreview).toHaveBeenCalledTimes(1);
});

it("keeps manual controls available and makes zero apply calls when Eugene is blocked", () => {
  const onApply = vi.fn();
  render(<RightDock {...blockedProps} onApplyProposal={onApply} />);
  expect(screen.getByText("직접 미디어를 고르거나 자막을 고쳐 계속 편집할 수 있어요.")).toBeVisible();
  expect(screen.queryByRole("button", { name: "추천 적용" })).toBeNull();
  expect(onApply).not.toHaveBeenCalled();
});
\`\`\`

- [ ] **Step 2: Run test to verify it fails.**

Run: \`npm --prefix apps/web run test -- --run src/features/editor/workbench/right-dock.test.tsx\`

Expected: FAIL because \`RightDock\` does not exist.

- [ ] **Step 3: Write the minimal callback-only component.**

\`\`\`tsx
export function RightDock({ state, messages, proposal, selectedSegment, inspectorTargets, onSend, onRetry, onPreviewCandidate, onApplyProposal, onInspectorSave }: Props) {
  const [draft, setDraft] = useState("");
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<string[]>([]);
  return <><section aria-label="유진"><div role="log" aria-label="유진 대화">{messages.map(renderMessage)}</div>{renderComposer()}</section><section aria-label="추천">{renderCandidates()}</section><section aria-label="편집 항목"><button aria-expanded={inspectorOpen} onClick={() => setInspectorOpen((open) => !open)}>{inspectorOpen ? "편집 항목 닫기" : "편집 항목 열기"}</button>{inspectorOpen ? renderInspector(inspectorTargets) : null}</section></>;
}
\`\`\`

Keep the three sections mounted below the dock; do not key/recreate it on Inspector state. Cards must call callbacks only: no \`api\` import, media element, materialization, direct mutation, or second player. Keep the workbench narrow drawer as the only modal/focus owner.

- [ ] **Step 4: Run tests to verify green.**

Run: \`npm --prefix apps/web run test -- --run src/features/editor/workbench/right-dock.test.tsx src/features/editor/workbench/editor-workbench.test.tsx\`

Expected: PASS, including zero \`audio\` or \`video\` elements in RightDock.

- [ ] **Step 5: Commit.**

\`\`\`powershell
git add apps/web/src/features/editor/workbench/RightDock.tsx apps/web/src/features/editor/workbench/right-dock.test.tsx apps/web/src/features/editor/workbench/editorWorkbenchReadOnlyAdapters.tsx apps/web/src/styles/editor-workbench.css
git commit -m "feat: add persistent Eugene editor dock"
\`\`\`

## Task 3: Connect existing Director DTO/API and Inspector commands through route fences

**Files:**
- Modify: \`apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx\`
- Modify: \`apps/web/src/features/editor/workbench/EditorWorkbench.tsx\`
- Test: \`apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx\`
- Test: \`apps/web/src/features/editor/workbench/editor-workbench.test.tsx\`

- [ ] **Step 1: Write the failing old-route and explicit-apply test.**

\`\`\`tsx
it("ignores old A Director completion and applies only current B proposal", async () => {
  const reloadA = deferred<DirectorReloadState>();
  vi.spyOn(api, "reloadDirectorSession").mockImplementation((projectId) => projectId === "project-a" ? reloadA.promise : Promise.resolve(reloadedB) as never);
  const batchApply = vi.spyOn(api, "batchApplyDirectorProposal").mockResolvedValue({} as never);
  const { rerender } = render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
  rerender(<EditorWorkbenchRoute projectId="project-b" sessionId="session-b" />);
  reloadA.resolve(reloadedA);
  await screen.findByText("B 추천");
  fireEvent.click(screen.getByRole("button", { name: "추천 적용" }));
  await waitFor(() => expect(batchApply).toHaveBeenCalledWith("project-b", "proposal-b", { candidate_ids: ["candidate-b"], expected_revision: 3 }));
  expect(screen.queryByText("A 추천")).toBeNull();
});
\`\`\`

- [ ] **Step 2: Run test to verify it fails.**

Run: \`npm --prefix apps/web run test -- --run src/features/editor/workbench/editor-workbench-route.test.tsx -t "ignores old A Director completion"\`

Expected: FAIL because the route supplies no Director state or callbacks.

- [ ] **Step 3: Write the minimal route adapter.**

\`\`\`ts
const loadDirector = async () => {
  const recovered = await api.reloadDirectorSession(projectId, sessionId);
  if (!isCurrentDirector()) return;
  setDirector({ conversation: recovered.conversation, messages: recovered.messages, proposal: recovered.proposal, state: "ready" });
};

const applyProposal = (proposalId: string, candidateIds: string[]) =>
  commitTimelineMutation(async (_port, isCurrent) => {
    const preflight = await api.preflightDirectorProposal(projectId, proposalId);
    if (!isCurrent() || preflight.code === "stale_proposal" || preflight.status === "stale") return;
    await api.batchApplyDirectorProposal(projectId, proposalId, { candidate_ids: candidateIds, expected_revision: state.view!.expectedRevision });
  });
\`\`\`

Add a Director operation ID alongside route epoch. Send through \`api.prepareDirectorMessage\`, retain its client ID until exchange success, and append only returned messages. Inspector callbacks call exactly one existing \`EditorCommandPort\` method: \`updateMediaControls\`, \`setCaptionText\`, \`setCaptionStyle\`, or the matching typed overlay method. There is no voice callback and no conflict retry.

- [ ] **Step 4: Run focused green suite.**

Run: \`npm --prefix apps/web run test -- --run src/features/editor/inspector/inspectorRegistry.test.ts src/features/editor/workbench/right-dock.test.tsx src/features/editor/workbench/editor-workbench.test.tsx src/features/editor/workbench/editor-workbench-route.test.tsx src/features/editor/preview/preview-stage.test.tsx src/features/editor/editorCommandPort.test.ts\`

Expected: PASS. Conflict/failure refreshes once and retries no Director or Inspector command.

- [ ] **Step 5: Commit.**

\`\`\`powershell
git add apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx apps/web/src/features/editor/workbench/EditorWorkbench.tsx apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx apps/web/src/features/editor/workbench/editor-workbench.test.tsx
git commit -m "feat: connect Eugene recommendations to editor inspector"
\`\`\`

## Task 4: Verify, review, close, and push

**Files:**
- Create: \`docs/handoffs/2026-07-23-videobox-task20-eugene-inspector-closeout.ko.md\`
- Modify: \`docs/development-status-2026-06-29.ko.md\`
- Modify: \`docs/implementation-plan.ko.md\`

- [ ] **Step 1: Run final gates.**

\`\`\`powershell
npm --prefix apps/web run test -- --run src/features/editor/inspector/inspectorRegistry.test.ts src/features/editor/workbench/right-dock.test.tsx src/features/editor/workbench/editor-workbench.test.tsx src/features/editor/workbench/editor-workbench-route.test.tsx src/features/editor/preview/preview-stage.test.tsx src/features/editor/editorCommandPort.test.ts
npm --prefix apps/web test
npm --prefix apps/web run build
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-editor-ui-source-provenance.ps1
git diff --check
git status --short
\`\`\`

Record exact results. Do not claim Python full regression. Existing React \`act(...)\`, jsdom navigation, intentional ErrorBoundary stderr, and 500 kB bundle warning are non-failures only with successful exit status.

- [ ] **Step 2: Perform risk-based independent reviews.**

1. Compare every acceptance row with tests and reject direct RightDock API/player/mutation, missing manual fallback, automatic apply, or unsupported Inspector field.
2. Inspect state preservation, route epoch, stable retry ID, explicit apply conflict path, local URL guard, and creator copy.
3. Trace Director DTO → route → workbench → RightDock → PreviewStage/command port and confirm external provider requests and second players are zero.

- [ ] **Step 3: Update SSOT/handoff after no Critical or Important finding remains.**

Record focused/full/build/provenance/diff results, preserve \`?? .tmp-final-fence-debug/\`, retain Task 9 human/CapCut boundary, and preserve user-fixed cumulative **9/22 (40.9%)** with **59.1%** remaining. Name Task 21 as next goal.

- [ ] **Step 4: Commit and push.**

\`\`\`powershell
git add docs/superpowers/specs/2026-07-23-videobox-task20-eugene-inspector-design.md docs/superpowers/plans/2026-07-23-videobox-task20-eugene-inspector.md docs/development-status-2026-06-29.ko.md docs/implementation-plan.ko.md docs/handoffs/2026-07-23-videobox-task20-eugene-inspector-closeout.ko.md
git commit -m "docs: close Task 20 Eugene editor integration"
git push origin codex/videobox-container-compatibility
\`\`\`

## Plan self-review

- Spec coverage: Task 1 restricts Inspector fields; Task 2 supplies persistent RightDock state and manual fallback; Task 3 enforces API/route/revision/player boundaries; Task 4 verifies and records closeout.
- Placeholder scan: no TBD/TODO, generic testing instruction, or unspecified API/command path remains.
- Type consistency: only \`broll | bgm | sfx\` reach media controls; captions and overlay variants use existing port discriminants; proposal apply uses the existing batch endpoint with \`expected_revision\`.
