# 자유 대화형 AI 편집 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 자유 문장으로 받은 편집 요청을 안전한 편집안으로 제시하고, 미리보기·명시적 적용·공통 10단계 되돌리기/다시 실행까지 연결한다.

**Architecture:** 로컬 유진은 자유 문장을 구조화된 편집안 후보로 반환하지만 저장하지 않는다. API는 현재 편집 세션과 안정 식별자를 검증한 뒤 편집안을 제공하고, 적용 시 기존 editing-session 명령과 현재성 확인을 재사용한다. 웹은 오른쪽 유진 대화 아래 요약과 상세 트레이를 제공하며, 적용 성공만 기존 undo/redo stack에 남긴다.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, existing local-only Yujin runtime, React, TypeScript, Vitest, pytest, Playwright, FFmpeg materialized timeline verification.

---

## Scope and reuse decision

| Area | Decision |
|---|---|
| Editing engine | Reuse `editing_session.py` mutations and `materialize_editing_session_timeline`; do not create a browser-side timeline source of truth. |
| Undo/redo | Reuse the existing persisted stacks. They already retain 10 undoable mutations (`tests/test_editor_timeline_mutations.py:355-378`); add AI-apply coverage rather than changing their limit. |
| AI request | Extend the existing local-only Yujin request boundary with a separate typed editing-proposal response. Do not make free text mutate a session. |
| Media | Reuse approved-asset proposal/materialize/apply routes. Never invent a media URI from model text. |
| UI | Add creator-language proposal summary/tray inside the current right dock; retain approved shell, colors, and layout. |
| Excluded | New voice generation/cloning, external provider paths, CapCut server effects/filters/stickers, advanced grading/masks/keyframes/multicam. |

## File map

| File | Responsibility |
|---|---|
| `packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py` | Strict request, operation, candidate and result models. |
| `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py` | Pure fail-closed parser and current-session validation. |
| `services/api/src/videobox_api/routers/director_proposals.py` | Typed proposal create, preflight and atomic apply endpoints. |
| `packages/core-engine/src/videobox_core_engine/editing_session.py` | One atomic multi-operation transaction composed from existing mutations. |
| `apps/web/src/api.ts` | API types and request methods for proposal, preview and apply. |
| `apps/web/src/features/editor/workbench/RightDock.tsx` | Summary, three follow-up question buttons, detail entry point. |
| `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx` | Route-owned proposal state, preview/apply ownership and stale handling. |
| `apps/web/src/features/editor/workbench/ConversationalEditProposalTray.tsx` | Detailed before/after review tray. |
| `tests/test_yujin_editing_proposal_adapter.py` | Pure parsing, validation, ambiguity and unsafe-input tests. |
| `tests/test_api_media_director.py` | API preflight/apply/undo/redo and materialized timeline contracts. |
| `apps/web/src/features/editor/workbench/conversational-edit-proposal-tray.test.tsx` | Accessible tray and non-sending question chips. |
| `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx` | Full route state, stale rejection and common-history wiring. |

### Task 1: Type the AI editing proposal contract

**Files:**
- Create: `packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py`
- Test: `tests/test_yujin_editing_proposal_adapter.py`

- [ ] **Step 1: Write failing tests for one valid speed proposal and one ambiguous request.**

```python
def test_speed_proposal_binds_one_current_segment_and_rate() -> None:
    result = interpret_yujin_editing_request(
        _response(intent="set_scene_speed", segment_id="scene-2", rate=2),
        _context(segment_ids=("scene-1", "scene-2")),
    )
    assert result.status == "candidate_only"
    assert result.proposal.operations[0].intent == "set_scene_speed"
    assert result.proposal.operations[0].segment_id == "scene-2"

def test_ambiguous_request_returns_clarification_without_candidate() -> None:
    result = interpret_yujin_editing_request({"reply_text": "이 장면을 더 짧게 해줘"}, _context())
    assert result.status == "clarification"
    assert result.proposal is None
```

- [ ] **Step 2: Run the new test and confirm it fails because the module does not exist.**

Run: `.venv/Scripts/python.exe -m pytest tests/test_yujin_editing_proposal_adapter.py -q`
Expected: import failure for `yujin_editing_proposal_adapter`.

- [ ] **Step 3: Define strict Pydantic models and a closed operation union.**

```python
EditingIntent = Literal[
    "set_scene_speed", "set_segment_bounds", "set_cut_action", "reorder_segments",
    "set_caption_text", "apply_media", "remove_media",
]

class SetSceneSpeedOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Literal["set_scene_speed"]
    segment_id: str
    rate: Literal[1, 1.5, 2]
```

Model each remaining operation with `extra="forbid"`; include only stable segment IDs, existing approved asset/candidate IDs, and values that the existing command ports already support.

- [ ] **Step 4: Implement the pure adapter with fail-closed validation.**

```python
def interpret_yujin_editing_request(payload: str | Mapping[str, object], context: YujinEditingContext) -> YujinEditingResult:
    raw = _decode_bounded_payload(payload)
    if raw is None or _contains_unsafe_instruction(raw):
        return _rejected("invalid_payload_or_unsafe_instruction")
    if raw.get("proposal") is None:
        return _clarification(raw)
    proposal = YujinEditingResponse.model_validate(raw).proposal
    reason = _validate_current_targets(proposal, context)
    return _rejected(reason) if reason else _candidate(proposal, context)
```

Reject unknown operation names, stale session revision, missing segment IDs, unsupported rates, unapproved media candidates, duplicate conflicting operations and model output that contains filesystem/network/provider instructions.

- [ ] **Step 5: Run focused tests and commit.**

Run: `.venv/Scripts/python.exe -m pytest tests/test_yujin_editing_proposal_adapter.py -q`
Expected: PASS.
Commit: `git add packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py tests/test_yujin_editing_proposal_adapter.py && git commit -m "기능: 유진 편집안 형식과 안전 검증 추가"`

### Task 2: Make typed proposal creation and currentness preflight reachable

**Files:**
- Modify: `services/api/src/videobox_api/routers/director_proposals.py`
- Modify: `services/api/src/videobox_api/schemas.py` or the router's existing request/response schema module
- Test: `tests/test_api_media_director.py`

- [ ] **Step 1: Write failing API tests for candidate-only creation, stale refusal and no session mutation.**

```python
response = client.post(
    f"/api/projects/{project_id}/editing-sessions/{session_id}/yujin-editing-proposals",
    json={"instruction": "두 번째 장면을 두 배로 빠르게 하고 자막도 맞춰줘"},
)
assert response.status_code == 201
assert response.json()["status"] == "ready"
assert store.get_editing_session(project_id=project_id, session_id=session_id)["session_revision"] == session["session_revision"]
```

- [ ] **Step 2: Run just that test and confirm the route is absent.**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api_media_director.py::test_yujin_editing_proposal_is_read_only_until_apply -q`
Expected: FAIL with 404.

- [ ] **Step 3: Add create and preflight endpoints.**

The create endpoint must call the local structured-response service, pass only the current session’s stable IDs and approved assets, validate with Task 1, and persist a read-only proposal record tied to `session_id` and `base_session_revision`. The preflight endpoint must reject a changed session or missing target with 409 and return creator-language recovery copy through the web mapping, not internal terms.

- [ ] **Step 4: Add deterministic follow-up suggestions.**

Return zero to three `follow_up_questions` derived from the validated intent and selected segment. Example mapping:

```python
FOLLOW_UPS = {
  "set_scene_speed": ("원래 속도로 되돌려 볼까요?", "앞뒤 장면도 같은 속도로 맞출까요?", "이 구간만 미리 볼까요?"),
  "apply_media": ("다른 분위기로 찾아볼까요?", "이 장면부터만 바꿀까요?", "효과음도 함께 넣을까요?"),
}
```

Do not ask the model to manufacture UI prompts; truncate to three and return no empty values.

- [ ] **Step 5: Run API tests and commit.**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api_media_director.py -q`
Expected: PASS.
Commit: `git add services/api/src/videobox_api tests/test_api_media_director.py && git commit -m "기능: 유진 편집안 생성과 후속 질문 연결"`

### Task 3: Apply one validated proposal through the existing editing-session authority

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/editing_session.py`
- Modify: `services/api/src/videobox_api/routers/director_proposals.py`
- Test: `tests/test_editor_timeline_mutations.py`
- Test: `tests/test_api_media_director.py`

- [ ] **Step 1: Write failing tests proving multi-operation AI apply is one undoable edit and redo is cleared by a later edit.**

```python
applied = client.post(apply_url, json={"expected_revision": proposal_revision}).json()
assert applied["undo_count"] == 1
undone = client.post(undo_url, json={"expected_revision": applied["session_revision"]}).json()
assert undone["redo_count"] == 1
later = client.post(manual_caption_url, json={"expected_revision": undone["session_revision"], "text": "새 자막"}).json()
assert later["redo_count"] == 0
```

- [ ] **Step 2: Verify RED.**

Run: `.venv/Scripts/python.exe -m pytest tests/test_editor_timeline_mutations.py::test_ai_editing_proposal_is_one_undoable_transaction -q`
Expected: FAIL because the apply boundary does not exist.

- [ ] **Step 3: Add a single atomic `apply_yujin_editing_proposal` composition function.**

It must compose existing session mutations on a draft, then call `apply_user_transaction` once. Map speed to `set_segment_ripple_playback_rate`, bounds to existing narration bounds, captions to existing caption mutation, and media only through already materialized approved assets. It must never call a renderer or output endpoint.

- [ ] **Step 4: Keep the existing 10-entry history contract explicit.**

Add a regression assertion that the eleventh applied AI or manual mutation retains only the newest ten undoable entries. Do not alter the established `MAX_UNDO_STACK_EVENTS` behavior unless the test demonstrates it is not 10.

- [ ] **Step 5: Run focused core/API tests and commit.**

Run: `.venv/Scripts/python.exe -m pytest tests/test_editor_timeline_mutations.py tests/test_api_media_director.py -q`
Expected: PASS.
Commit: `git add packages/core-engine/src/videobox_core_engine/editing_session.py services/api/src/videobox_api/routers/director_proposals.py tests/test_editor_timeline_mutations.py tests/test_api_media_director.py && git commit -m "기능: 유진 편집안을 한 번에 적용하고 되돌리기 연결"`

### Task 4: Add typed web API and route-owned proposal state

**Files:**
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/api.test.ts`
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- Test: `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`

- [ ] **Step 1: Write a failing route test.**

```tsx
fireEvent.click(screen.getByRole("button", { name: "요청 보내기" }));
await screen.findByText("2번 장면 · 8초 → 4초");
expect(api.createYujinEditingProposal).toHaveBeenCalledWith(projectId, sessionId, expect.any(Object));
expect(api.applyYujinEditingProposal).not.toHaveBeenCalled();
```

- [ ] **Step 2: Verify RED.**

Run: `cd apps/web && npx vitest run src/features/editor/workbench/editor-workbench-route.test.tsx`
Expected: FAIL because the API method and summary are absent.

- [ ] **Step 3: Add API types and methods.**

Expose `YujinEditingProposal`, `YujinEditingOperation`, `follow_up_questions`, `createYujinEditingProposal`, `preflightYujinEditingProposal`, and `applyYujinEditingProposal`. Validate response shape before giving it to the route; do not expose internal provider/runtime/revision labels in UI copy.

- [ ] **Step 4: Store only current route-owned proposal state.**

After a completed conversation exchange, create a proposal only when the user chooses the existing explicit next action. Abort and discard a late response after route/session change. Before apply, preflight and call the atomic Task 3 endpoint; reload the session only after success.

- [ ] **Step 5: Run web focused tests and commit.**

Run: `cd apps/web && npx vitest run src/api.test.ts src/features/editor/workbench/editor-workbench-route.test.tsx`
Expected: PASS.
Commit: `git add apps/web/src/api.ts apps/web/src/api.test.ts apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx && git commit -m "기능: 편집기에서 유진 편집안 상태를 연결"`

### Task 5: Build the C-hybrid summary, detail tray and follow-up question chips

**Files:**
- Create: `apps/web/src/features/editor/workbench/ConversationalEditProposalTray.tsx`
- Create: `apps/web/src/features/editor/workbench/conversational-edit-proposal-tray.test.tsx`
- Modify: `apps/web/src/features/editor/workbench/RightDock.tsx`
- Modify: `apps/web/src/features/editor/workbench/right-dock.test.tsx`

- [ ] **Step 1: Write failing accessibility tests.**

```tsx
render(<ConversationalEditProposalTray proposal={speedProposal} onApply={vi.fn()} onPreview={vi.fn()} />);
expect(screen.getByRole("dialog", { name: "편집안" })).toHaveTextContent("2번 장면 · 8초 → 4초");
fireEvent.click(screen.getByRole("button", { name: "이 구간만 미리 보기" }));
expect(onPreview).toHaveBeenCalledWith(speedProposal.proposalId);
```

```tsx
fireEvent.click(screen.getByRole("button", { name: "앞뒤 장면도 같은 속도로 맞출까요?" }));
expect(onDraftChange).toHaveBeenCalledWith("앞뒤 장면도 같은 속도로 맞출까요?");
expect(onSendMessage).not.toHaveBeenCalled();
```

- [ ] **Step 2: Verify RED.**

Run: `cd apps/web && npx vitest run src/features/editor/workbench/conversational-edit-proposal-tray.test.tsx src/features/editor/workbench/right-dock.test.tsx`
Expected: FAIL because the tray and follow-up controls are absent.

- [ ] **Step 3: Implement creator-language surfaces.**

Render a compact proposal summary below the assistant answer, no more than three question chips, and a detail dialog/tray with changed scenes, before/after duration, `미리보기`, `적용`, and `닫기`. Chips fill the existing draft only. Hide the chip row for no questions. Use existing compact `Button` variants and title/aria labels rather than new palette or layout primitives.

- [ ] **Step 4: Wire preview and apply controls.**

Preview must route to the existing selected-range/exact-preview authority and must not save. Apply must be disabled while preflight/apply is running and surface a creator-language retry action on stale failure.

- [ ] **Step 5: Run focused tests and commit.**

Run: `cd apps/web && npx vitest run src/features/editor/workbench/conversational-edit-proposal-tray.test.tsx src/features/editor/workbench/right-dock.test.tsx`
Expected: PASS.
Commit: `git add apps/web/src/features/editor/workbench/ConversationalEditProposalTray.tsx apps/web/src/features/editor/workbench/conversational-edit-proposal-tray.test.tsx apps/web/src/features/editor/workbench/RightDock.tsx apps/web/src/features/editor/workbench/right-dock.test.tsx && git commit -m "기능: 유진 편집안 검토 화면과 꼬리 질문 추가"`

### Task 6: Prove command interpretation and the real output path

**Files:**
- Create: `tests/test_yujin_editing_command_evaluation.py`
- Modify: `tests/test_shortform_ripple_speed.py`
- Modify: `apps/web/e2e/editor-workbench.spec.mjs`

- [ ] **Step 1: Write evaluation cases before any prompt change.**

```python
CASES = (
    ("두 번째 장면을 두 배로 빠르게 하고 자막도 맞춰줘", "set_scene_speed", "scene-2"),
    ("여기 말이 길어. 앞을 조금 잘라줘", "set_segment_bounds", "scene-2"),
    ("이 분위기에 맞는 음악으로 바꿔줘", "apply_media", "scene-2"),
    ("짧게 해줘", "clarification", None),
)
```

The harness must validate parsed intent/target/status, not merely assert that a mocked model was called. Keep deterministic schema fixtures separate from an opt-in real-local-model run.

- [ ] **Step 2: Verify RED.**

Run: `.venv/Scripts/python.exe -m pytest tests/test_yujin_editing_command_evaluation.py -q`
Expected: FAIL because the evaluator is absent.

- [ ] **Step 3: Add both deterministic and opt-in local-model evidence.**

The deterministic suite checks parser and product wiring. The opt-in local run uses no external provider, records each case’s accepted/clarified/rejected outcome, and fails if an invalid candidate would be applicable. It must not run by default in the complete pytest suite.

- [ ] **Step 4: Add materialized speed regression.**

Extend `test_shortform_ripple_speed.py` so an AI-applied speed proposal materializes through `materialize_editing_session_timeline` and verifies video, narration, caption and audio timing in both FFmpeg composition and CapCut draft output.

- [ ] **Step 5: Add browser contract and run focused validation.**

The Playwright path must submit a request, open an edit proposal, preview, apply, undo, redo, and verify the screen’s session data after refresh. It must use a fixture project it owns, not a representative’s existing project.

Run:
` .venv/Scripts/python.exe -m pytest tests/test_yujin_editing_proposal_adapter.py tests/test_api_media_director.py tests/test_editor_timeline_mutations.py tests/test_shortform_ripple_speed.py tests/test_yujin_editing_command_evaluation.py -q`

Run: `cd apps/web && npx vitest run src/api.test.ts src/features/editor/workbench/conversational-edit-proposal-tray.test.tsx src/features/editor/workbench/right-dock.test.tsx src/features/editor/workbench/editor-workbench-route.test.tsx`

Expected: PASS.
Commit: `git add tests apps/web/e2e/editor-workbench.spec.mjs && git commit -m "검증: 유진 자연어 편집 적용과 되돌리기 확인"`

### Task 7: Release audit and owner-visible verification

**Files:**
- Create: `docs/handoffs/2026-08-26-videobox-ai-conversational-editing-handoff.ko.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run static and complete regression gates.**

Run: `.venv/Scripts/python.exe -m pytest` alone from repository root.
Run: `cd apps/web && npx vitest run`.
Run: `cd apps/web && npx tsc --noEmit`.

- [ ] **Step 2: Rebuild only through the approved owner script.**

Run: `./scripts/owner-ready.ps1 -Mode Start -Rebuild -WithYujinMemory`.

- [ ] **Step 3: Perform reverse-path browser verification.**

Use the owned fixture project: apply AI speed edit → refresh/read back → undo → refresh/read back → redo → refresh/read back → exact preview → MP4/optional CapCut draft. Record which gates are automated and which require the owner’s visual/video acceptance.

- [ ] **Step 4: Do code review and gap review before closing.**

Compare every design completion criterion against source, tests and browser evidence. Check developer terms are absent from visible/ARIA copy, check no unrelated palette/layout changes, and classify remaining gaps rather than hiding them behind green tests.

- [ ] **Step 5: Write handoff, update `CLAUDE.md` latest-handoff row, commit and request separate push/deploy approval.**

Commit: `git add docs/handoffs CLAUDE.md && git commit -m "문서: AI 대화형 편집 검증 인계 추가"`.

Do not push or deploy in this task unless the owner asks after reviewing the completed release audit.

## Plan self-review

- Spec coverage: Tasks 1–3 cover typed proposal, explicit apply, currentness and shared 10-step history; Tasks 4–5 cover C-hybrid UI and three follow-up questions; Task 6 covers both deterministic command interpretation and materialized output; Task 7 covers runtime, reverse path, review and handoff.
- Scope: no external AI path, automatic editing, new editing engine, palette/layout redesign or excluded CapCut/pro features are introduced.
- Type consistency: `YujinEditingProposal` is created as a read-only candidate, preflighted against session state, then atomically applied once; `follow_up_questions` is a maximum-three array consumed only as draft-fill chips.
