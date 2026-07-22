# Task 19 editor asset browser implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a revision-safe editor asset browser for project B-roll and verified Starter Pack BGM/SFX that uses the existing one-player preview stage and requires an explicit selected-segment apply.

**Architecture:** `EditorAssetBrowser` is a presentational feature built from a pure asset projector. `EditorWorkbench` owns selected-segment targeting and a monotonic audition request for `PreviewStage`; `EditorWorkbenchRoute` owns asset loading, materialization, and the existing revision-bound command port. No card owns API data, media playback, or editing-session mutation.

**Tech Stack:** React 19, TypeScript 5.8, Vitest, Testing Library, existing `api`, `EditorCommandPort`, `PreviewStage`, and `editor-workbench.css`.

---

## File map

- Create `apps/web/src/features/editor/assets/editorAssetProjection.ts`: pure normalization, type/query filter, status/range copy.
- Create `apps/web/src/features/editor/assets/editorAssetProjection.test.ts`: pure filter/status/target tests.
- Create `apps/web/src/features/editor/assets/EditorAssetBrowser.tsx`: accessible presentational browser/cards and callback-only controls.
- Create `apps/web/src/features/editor/assets/EditorAssetBrowser.test.tsx`: interaction/no-player tests.
- Modify `apps/web/src/features/editor/workbench/EditorWorkbench.tsx`: selected narration target, one audition request, browser callbacks.
- Modify `apps/web/src/features/editor/workbench/editorWorkbenchReadOnlyAdapters.tsx`: mount browser in the left dock through typed props.
- Modify `apps/web/src/features/editor/preview/preview-stage.tsx` and `preview-stage.test.tsx`: receive a request ID and switch the existing one player.
- Modify `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx` and `editor-workbench-route.test.tsx`: independent asset load, materialize-before-command, route-epoch safety.
- Modify `apps/web/src/styles/editor-workbench.css`: compact browser/card layout using existing theme variables.
- Create `docs/handoffs/2026-07-23-videobox-task19-editor-asset-browser-closeout.ko.md`; modify status/implementation plan only after all gates pass.

## Task 1: Pure editor asset projection

**Files:**
- Create: `apps/web/src/features/editor/assets/editorAssetProjection.ts`
- Test: `apps/web/src/features/editor/assets/editorAssetProjection.test.ts`

- [x] **Step 1: Write the failing pure-contract tests.**

```ts
import { describe, expect, it } from "vitest";
import { filterEditorAssets, projectEditorAssets } from "./editorAssetProjection";

it("projects B-roll image metadata and a verified BGM into honest cards", () => {
  const cards = projectEditorAssets({
    projectId: "p",
    brollAssets: [{ asset_id: "image-1", asset_type: "broll_image", storage_uri: "x", created_at: "now", metadata: { title: "제품 사진", duration_seconds: 4, analysis_status: "succeeded", review_required: false } }],
    libraryAssets: [{ library_asset_id: "bgm-1", asset_id: "starter-bgm", media_type: "music", duration_seconds: 12, version: "v1", verified: true, available: true, tags: [], source: "Starter", creator: "Creator", official_license_url: "https://license.invalid", attribution_required: false, attribution_text: "" }],
  });
  expect(cards.map((card) => [card.kind, card.label, card.canApply])).toEqual([["broll", "이미지 B-roll", true], ["bgm", "BGM", true]]);
  expect(cards[0].status).toContain("준비됨");
});

it("filters a normalized list by type and query without losing unavailable license truth", () => {
  const cards = projectEditorAssets({ projectId: "p", brollAssets: [], libraryAssets: [{ library_asset_id: "sfx-1", asset_id: "sfx", media_type: "sfx", duration_seconds: 2, version: "v1", verified: false, available: false, tags: ["license"], source: "Starter", creator: "Creator", official_license_url: "", attribution_required: false, attribution_text: "" }] });
  expect(filterEditorAssets(cards, { type: "sfx", query: "license" })).toEqual([expect.objectContaining({ canApply: false, license: "검증 또는 이용 가능 상태 확인 필요" })]);
});
```

- [x] **Step 2: Run the focused test and verify RED.**

Run: `npm --prefix apps/web run test -- --run src/features/editor/assets/editorAssetProjection.test.ts`

Expected: FAIL because `editorAssetProjection` does not exist.

- [x] **Step 3: Implement the smallest pure projector.**

```ts
export type EditorAssetKind = "broll" | "bgm" | "sfx";
export type EditorAssetCard = Readonly<{
  id: string; kind: EditorAssetKind; assetId: string; label: string; title: string;
  durationLabel: string; status: string; license: string; canApply: boolean;
  previewUrl: string;
}>;

export function filterEditorAssets(cards: readonly EditorAssetCard[], filter: { type: "all" | EditorAssetKind; query: string }) {
  const term = filter.query.trim().toLowerCase();
  return cards.filter((card) => (filter.type === "all" || card.kind === filter.type)
    && (!term || `${card.title} ${card.label} ${card.status} ${card.license}`.toLowerCase().includes(term)));
}
```

Use `api.assetContentUrl(projectId, assetId)` for B-roll and `api.mediaLibraryPreviewUrl(libraryAssetId)` for library cards. Keep metadata conversion in this module; no React or API request belongs here.

- [x] **Step 4: Run the focused test and verify GREEN.**

Run: `npm --prefix apps/web run test -- --run src/features/editor/assets/editorAssetProjection.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit the pure unit.**

```powershell
git add apps/web/src/features/editor/assets/editorAssetProjection.ts apps/web/src/features/editor/assets/editorAssetProjection.test.ts
git commit -m "feat: project editor asset cards"
```

### Task 1 execution evidence (2026-07-23)

- Initial RED: `npm --prefix apps/web run test -- --run src/features/editor/assets/editorAssetProjection.test.ts` failed because `editorAssetProjection` did not exist.
- Review-gap RED: the same command failed because the implementation marked `review_required` false, missing, and nonboolean values as `검토 완료`.
- Review-gap GREEN: the same command passed with `4 tests passed`.
- Licence/source-gap RED: the same command failed because B-roll output still contained the invented `manual source` label.
- Licence/source GREEN: the same command passed with `5 tests passed`.
- `git diff --check` passed; no stage or commit was made; protected `?? .tmp-final-fence-debug/` was preserved.

## Task 2: Accessible callback-only asset browser

**Files:**
- Create: `apps/web/src/features/editor/assets/EditorAssetBrowser.tsx`
- Test: `apps/web/src/features/editor/assets/EditorAssetBrowser.test.tsx`
- Modify: `apps/web/src/styles/editor-workbench.css`

- [x] **Step 1: Write failing browser tests.**

```tsx
it("filters cards, describes the selected range, and requests preview without a media node", () => {
  const onPreview = vi.fn();
  const { container } = render(<EditorAssetBrowser cards={cards} target={{ segmentId: "seg-1", startSec: 3, endSec: 7 }} isSaving={false} onPreview={onPreview} onApply={vi.fn()} />);
  fireEvent.change(screen.getByRole("searchbox", { name: "자산 검색" }), { target: { value: "제품" } });
  fireEvent.click(screen.getByRole("button", { name: "제품 사진 원본 미리보기" }));
  expect(onPreview).toHaveBeenCalledWith(expect.objectContaining({ id: "broll:image-1" }));
  expect(screen.getByText("적용 구간: 3.00–7.00초")).toBeVisible();
  expect(container.querySelectorAll("audio, video")).toHaveLength(0);
});

it("requires a target and a verified available card before explicit apply", () => {
  const onApply = vi.fn();
  const { rerender } = render(<EditorAssetBrowser cards={cards} target={null} isSaving={false} onPreview={vi.fn()} onApply={onApply} />);
  expect(screen.getByRole("button", { name: "제품 사진 적용" })).toBeDisabled();
  rerender(<EditorAssetBrowser cards={cards} target={{ segmentId: "seg-1", startSec: 0, endSec: 1 }} isSaving onPreview={vi.fn()} onApply={onApply} />);
  expect(screen.getByRole("button", { name: "제품 사진 적용" })).toBeDisabled();
});
```

- [x] **Step 2: Run RED.**

Run: `npm --prefix apps/web run test -- --run src/features/editor/assets/EditorAssetBrowser.test.tsx`

Expected: FAIL because `EditorAssetBrowser` does not exist.

- [x] **Step 3: Implement cards as presentational controls only.**

```tsx
export function EditorAssetBrowser({ cards, target, isSaving, onPreview, onApply }: Props) {
  const [query, setQuery] = useState("");
  const [type, setType] = useState<"all" | EditorAssetKind>("all");
  const visible = filterEditorAssets(cards, { type, query });
  return <section aria-label="편집기 자산">
    <label>자산 검색<input type="search" aria-label="자산 검색" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
    <p>{target ? `적용 구간: ${target.startSec.toFixed(2)}–${target.endSec.toFixed(2)}초` : "적용할 나레이션 구간을 먼저 선택하세요."}</p>
    {visible.map((card) => <article key={card.id}><h3>{card.title}</h3><p>{card.label} · {card.durationLabel}</p><p>{card.status} · {card.license}</p><p>직접 선택한 자산</p><button type="button" onClick={() => onPreview(card)}>원본 미리보기</button><button type="button" disabled={!target || isSaving || !card.canApply} onClick={() => target && onApply(card, target.segmentId)}>적용</button></article>)}
  </section>;
}
```

Use card-specific accessible button names, `aria-pressed` on the type filter, and CSS classes beginning `vb-editor-assets`. Do not render `<audio>`, `<video>`, `draggable`, or a direct `api` call.

- [x] **Step 4: Run GREEN.**

Run: `npm --prefix apps/web run test -- --run src/features/editor/assets/EditorAssetBrowser.test.tsx src/features/editor/assets/editorAssetProjection.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit the browser.**

```powershell
git add apps/web/src/features/editor/assets/EditorAssetBrowser.tsx apps/web/src/features/editor/assets/EditorAssetBrowser.test.tsx apps/web/src/styles/editor-workbench.css
git commit -m "feat: add accessible editor asset browser"
```

### Task 2 execution evidence (2026-07-23)

- Initial RED: `npm --prefix apps/web run test -- --run src/features/editor/assets/EditorAssetBrowser.test.tsx` failed because `./EditorAssetBrowser` did not exist.
- GREEN: `npm --prefix apps/web run test -- --run src/features/editor/assets/EditorAssetBrowser.test.tsx src/features/editor/assets/editorAssetProjection.test.ts` passed with `2 files / 8 tests`.
- The browser owns only query and type-filter state. It renders no `audio`, `video`, draggable card, API call, or persistence behavior; preview and apply remain callback-only.
- Step 5 remains open because this delegated task explicitly forbids staging and committing.
- Card-target review RED: the focused browser test failed because the selected range and no-target guidance were outside each asset card.
- Card-target review GREEN: `npm --prefix apps/web run test -- --run src/features/editor/assets/EditorAssetBrowser.test.tsx src/features/editor/assets/editorAssetProjection.test.ts` passed with `2 files / 8 tests` after each card rendered the selected range or no-target guidance.
- Quality-review RED: after correcting the CSS fixture's Vite file-path setup, `npm --prefix apps/web run test -- --run src/features/editor/assets/editorAssetProjection.test.ts src/features/editor/assets/EditorAssetBrowser.test.tsx` failed with four expected assertions: absent projected audio presence, absent accessible filter group, absent card audio text, and missing wrap-safe CSS rule.
- Quality-review GREEN: the same focused Task 1+2 command passed with `2 files / 12 tests`. B-roll audio status now requires explicit consistent `audio_present` or `has_audio` booleans; missing or conflicting metadata stays `오디오 정보 확인 중`, while supported BGM/SFX cards state `오디오 있음`.

## Task 3: Connect browser requests to the sole preview stage

**Files:**
- Modify: `apps/web/src/features/editor/preview/preview-stage.tsx`
- Test: `apps/web/src/features/editor/preview/preview-stage.test.tsx`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbench.tsx`
- Modify: `apps/web/src/features/editor/workbench/editorWorkbenchReadOnlyAdapters.tsx`
- Test: `apps/web/src/features/editor/workbench/editor-workbench.test.tsx`

- [ ] **Step 1: Write failing one-player request tests.**

```tsx
it("consumes a newer card audition request in its existing player", () => {
  const { container, rerender } = render(<PreviewStage {...current} auditionRequest={null} />);
  rerender(<PreviewStage {...current} auditionRequest={{ requestId: 1, source: { id: "broll:image-1", label: "제품 사진", url: "/api/projects/p/assets/image-1/content", mediaKind: "video", timelineRange: { startSec: 3, endSec: 7 } } }} />);
  expect(screen.getByLabelText("제품 사진 소스 미리보기")).toBeInTheDocument();
  expect(container.querySelectorAll("audio, video")).toHaveLength(1);
});

it("sends an asset-card preview through the workbench stage in the narrow left drawer", async () => {
  Object.defineProperty(window, "innerWidth", { value: 390 });
  render(<EditorWorkbench view={assetView} assetCards={cards} />);
  fireEvent.click(screen.getByRole("button", { name: "자산과 대본" }));
  fireEvent.click(await screen.findByRole("button", { name: "제품 사진 원본 미리보기" }));
  expect(screen.getByLabelText("제품 사진 소스 미리보기")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run RED.**

Run: `npm --prefix apps/web run test -- --run src/features/editor/preview/preview-stage.test.tsx src/features/editor/workbench/editor-workbench.test.tsx`

Expected: FAIL because `auditionRequest` and workbench asset props do not exist.

- [ ] **Step 3: Add a monotonic request input, not a second player.**

```ts
export type AuditionRequest = Readonly<{ requestId: number; source: AuditionSource }>;
// PreviewStage prop: auditionRequest?: AuditionRequest | null
useEffect(() => {
  if (!auditionRequest || !isAllowedLocalUrl(auditionRequest.source.url)) return;
  showAudition(auditionRequest.source);
  // requestId intentionally permits replaying the same source after returning to exact preview.
}, [auditionRequest?.requestId]);
```

In `EditorWorkbench`, derive the selected narration clip `{ segmentId, startSec, endSec }`, keep `requestId` in state, and pass browser props through the left adapter. A preview callback makes `{ requestId: current + 1, source }`; apply callbacks only travel upward. Do not let `EditorWorkbenchReadOnlyAdapters` import `api` or mount media.

- [ ] **Step 4: Run GREEN.**

Run: `npm --prefix apps/web run test -- --run src/features/editor/preview/preview-stage.test.tsx src/features/editor/workbench/editor-workbench.test.tsx src/features/editor/assets/EditorAssetBrowser.test.tsx`

Expected: PASS and every test that counts `audio, video` observes one element.

- [ ] **Step 5: Commit the one-player integration.**

```powershell
git add apps/web/src/features/editor/preview/preview-stage.tsx apps/web/src/features/editor/preview/preview-stage.test.tsx apps/web/src/features/editor/workbench/EditorWorkbench.tsx apps/web/src/features/editor/workbench/editorWorkbenchReadOnlyAdapters.tsx apps/web/src/features/editor/workbench/editor-workbench.test.tsx
git commit -m "feat: preview editor assets in one stage"
```

## Task 4: Route-owned asset truth and revision-safe application

**Files:**
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Test: `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbench.tsx`
- Test: `apps/web/src/features/editor/workbench/editor-workbench.test.tsx`

- [ ] **Step 1: Write failing route integration tests.**

```tsx
it("materializes verified BGM before exactly one current-revision music command", async () => {
  vi.spyOn(api, "listBrollAssets").mockResolvedValue([broll] as never);
  vi.spyOn(api, "listMediaLibraryAssets").mockResolvedValue({ assets: [music] } as never);
  vi.spyOn(api, "materializeMediaLibraryAsset").mockResolvedValue({ asset_id: "materialized-bgm" } as never);
  const apply = vi.spyOn(api, "updateEditingSessionMusicOverride").mockResolvedValue({} as never);
  render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
  await screen.findByRole("button", { name: "BGM 1 적용" });
  fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
  fireEvent.click(screen.getByRole("button", { name: "BGM 1 적용" }));
  await waitFor(() => expect(apply).toHaveBeenCalledWith("project-a", "session-a", "segment-1", { asset_id: "materialized-bgm", expected_revision: 1 }));
});

it("does not call an editing command when library materialization fails", async () => {
  vi.spyOn(api, "getEditorPlaybackManifest")
    .mockResolvedValueOnce(narrationManifest(1) as never)
    .mockResolvedValueOnce(narrationManifest(1) as never);
  vi.spyOn(api, "listBrollAssets").mockResolvedValue([] as never);
  vi.spyOn(api, "listMediaLibraryAssets").mockResolvedValue({ assets: [music] } as never);
  vi.spyOn(api, "materializeMediaLibraryAsset").mockRejectedValue(new Error("disk full"));
  const apply = vi.spyOn(api, "updateEditingSessionMusicOverride");
  render(<EditorWorkbenchRoute projectId="project-a" sessionId="session-a" />);
  await screen.findByRole("button", { name: "BGM 1 적용" });
  fireEvent.click(screen.getByRole("button", { name: "n-1 클립 선택" }));
  fireEvent.click(screen.getByRole("button", { name: "BGM 1 적용" }));
  await waitFor(() => expect(apply).not.toHaveBeenCalled());
  expect(await screen.findByText("변경 내용을 저장하지 못했어요. 최신 내용을 확인한 뒤 다시 시도해 주세요.")).toBeVisible();
});
```

- [ ] **Step 2: Run RED.**

Run: `npm --prefix apps/web run test -- --run src/features/editor/workbench/editor-workbench-route.test.tsx`

Expected: FAIL because route asset state/callbacks are absent.

- [ ] **Step 3: Implement independent load and atomic route callbacks.**

```ts
type AssetState = Readonly<{ key: string; brollAssets: BrollAsset[]; libraryAssets: MediaLibraryAsset[]; error: string | null }>;

const applyLibraryAsset = (card: EditorAssetCard, segmentId: string) =>
  commitTimelineMutation(async (port) => {
    const materialized = await api.materializeMediaLibraryAsset(card.id, projectId);
    return port.applyMedia({ kind: card.kind, segmentId, assetId: materialized.asset_id });
  });
```

Load `listBrollAssets(projectId)` and `listMediaLibraryAssets()` independently in an effect keyed by `requestKey`. Capture its route epoch and ignore stale completions. Project raw results with `projectEditorAssets`, pass only cards/error/callbacks to the workbench, and use the existing `commitTimelineMutation` for all applies. For B-roll skip materialization and call `port.applyMedia({ kind: "broll", segmentId, assetId: card.assetId })`. Never call the port if `materializeMediaLibraryAsset` rejects.

- [ ] **Step 4: Run GREEN and affected regression tests.**

Run: `npm --prefix apps/web run test -- --run src/features/editor/assets src/features/editor/preview/preview-stage.test.tsx src/features/editor/workbench/editor-workbench.test.tsx src/features/editor/workbench/editor-workbench-route.test.tsx src/features/editor/editorCommandPort.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit the route integration.**

```powershell
git add apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx apps/web/src/features/editor/workbench/EditorWorkbench.tsx apps/web/src/features/editor/workbench/editor-workbench.test.tsx
git commit -m "feat: apply editor assets through revision fence"
```

## Task 5: Independent closeout and documentation

**Files:**
- Create: `docs/handoffs/2026-07-23-videobox-task19-editor-asset-browser-closeout.ko.md`
- Modify: `docs/development-status-2026-06-29.ko.md`
- Modify: `docs/implementation-plan.ko.md`

- [ ] **Step 1: Run quality gates without a full Python regression.**

```powershell
npm --prefix apps/web run test -- --run src/features/editor/assets src/features/editor/preview/preview-stage.test.tsx src/features/editor/workbench/editor-workbench.test.tsx src/features/editor/workbench/editor-workbench-route.test.tsx src/features/editor/editorCommandPort.test.ts
npm --prefix apps/web test
npm --prefix apps/web run build
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-editor-ui-source-provenance.ps1
git diff --check
git status --short
```

Record exact pass/fail output and any pre-existing frontend stderr/build-size warnings. Do not invoke `.venv\\Scripts\\python.exe -m pytest` for the whole suite and do not claim a full Python regression.

- [ ] **Step 2: Perform independent reviews in this order.**

1. Spec review: compare every acceptance-matrix row with tests and code; reject direct card API/player/mutation, unsupported voice/image-overlay apply, or missing failure fence.
2. Quality review: inspect callback types, effect dependencies, route-epoch checks, button disabled semantics, local URL gating, and CSS narrow-drawer behavior.
3. Gap review: test no target, unavailable library item, materialize failure, conflict, asset load failure, same asset re-audition, and stale route completion.
4. Source-to-runtime reverse review: trace each card URL/API from route to `PreviewStage`/command port and confirm no external URL/player/import reaches runtime.

- [ ] **Step 3: Write SSOT/handoff only after all review blockers are closed.**

Document the actual commit SHA(s), exact verifications, source-map decision, protected `?? .tmp-final-fence-debug/` status, Task 9 cumulative **9/22 (40.9%)**, remaining **59.1%**, and the next goal: Task 20 needs its own written spec/approval. Do not mark Task 19 complete or alter progress until the implementation/reviews pass.

- [ ] **Step 4: Commit and push the verified closeout.**

```powershell
git add docs/superpowers/specs/2026-07-23-videobox-task19-editor-asset-browser-design.md docs/superpowers/plans/2026-07-23-videobox-task19-editor-asset-browser.md docs/handoffs/2026-07-23-videobox-task19-editor-asset-browser-closeout.ko.md docs/development-status-2026-06-29.ko.md docs/implementation-plan.ko.md
git commit -m "docs: close Task 19 editor asset browser"
git push origin codex/videobox-container-compatibility
```

## Plan self-review

- Spec coverage: Task 1 covers asset truth/statuses; Task 2 covers search/filter/a11y/explicit apply; Task 3 covers one-player preview and responsive dock; Task 4 covers actual API/revision/materialize/failure/stale route behavior; Task 5 covers quality, reverse review, provenance, SSOT, and closeout.
- Placeholder scan: no incomplete-work marker, abbreviated fixture comment, unspecified test step, or open-ended implementation marker remains.
- Type consistency: `EditorAssetCard.kind` is exactly `broll | bgm | sfx`; route materializes only library cards and passes project B-roll IDs directly; selected target uses the existing narration `segmentId`.
