# Review Action Family Acceleration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining review-action family gaps with the fastest safe order: approve hardening, manual-edit routing, then explicit reject semantics without breaking existing editing-session, review/output, Gemini fallback, provider trace, or persistence contracts.

**Architecture:** Reuse the existing review snapshot, timeline, and editing-session flows wherever possible. Treat `Mark for manual edit` as a routing action into the existing editor flow, and treat `Reject recommendation` as a separate persistence-contract task that must introduce an explicit resolved-but-not-applied decision state instead of overloading the current pending/applicable booleans.

**Tech Stack:** Python, FastAPI, React, TypeScript, Vitest, pytest, SQLite-backed local project store

---

## File Structure

- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\tests\test_api.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\apps\web\src\app.test.tsx`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\apps\web\src\App.tsx`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\packages\storage-abstractions\src\videobox_storage\sqlite_schema.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\packages\storage-abstractions\src\videobox_storage\local_project_store.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\packages\core-engine\src\videobox_core_engine\local_pipeline.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\services\api\src\videobox_api\orchestration.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\services\api\src\videobox_api\main.py`

### Task 1: Lock Approve Reverse Verification

**Files:**
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\tests\test_api.py`

- [x] **Step 1: Write the failing test**

```python
def test_review_snapshot_api_approve_preserves_non_target_review_items_and_blocked_status(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    target_candidate = {
        "recommendation_id": "rec_broll_review_002",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_002",
        "score": 0.88,
        "reason": "Operator approved the suggested B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-06-30T00:00:00+00:00",
        "provider_trace": build_provider_trace(final_provider="heuristic_fallback"),
    }
    non_target_candidate = {
        "recommendation_id": "rec_tts_review_003",
        "target_segment_id": "seg_003",
        "recommendation_type": "tts_replacement",
        "selected_asset_id": "asset_tts_review_003",
        "score": 0.91,
        "reason": "Operator still needs to review the regenerated narration.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"voice_sample_id": "voice_003"},
        "created_at": "2026-06-30T00:00:01+00:00",
        "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
    }

    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [target_candidate, non_target_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "broll_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        },
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_003",
            "message": "Operator must confirm the TTS replacement before approval.",
        },
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_broll_review_002/approve"
    )

    payload = approve_response.json()
    assert payload["review_status"] == "blocked"
    assert [item["recommendation_id"] for item in payload["pending_recommendations"]] == [
        "rec_tts_review_003"
    ]
    assert payload["review_flags"] == [
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_003",
            "message": "Operator must confirm the TTS replacement before approval.",
        }
    ]
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api.py -k "approve_pending_recommendation or approve_preserves_non_target_review_items_and_blocked_status" -q`
Expected: FAIL because non-target review items or review status handling are not yet proven

- [x] **Step 3: Write minimal implementation**

```python
status = "blocked" if timeline.get("review_flags") or timeline.get("pending_recommendations") else "draft"
```

```python
timeline["review_flags"] = [
    flag
    for flag in deepcopy(timeline.get("review_flags", []))
    if not (
        str(flag.get("code") or "") == recommendation_flag_code
        and str(flag.get("segment_id") or "") == target_segment_id
    )
]
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api.py -k "approve_pending_recommendation or approve_preserves_non_target_review_items_and_blocked_status" -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_api.py
git commit -m "test: harden approve recommendation reverse verification"
```

### Task 2: Route Manual Edit Through Existing Editor Flow

**Files:**
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\apps\web\src\app.test.tsx`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\apps\web\src\App.tsx`

- [x] **Step 1: Write the failing test**

```tsx
it("opens the actionable pending recommendation in the editing session when marked for manual edit", async () => {
  const actionableTimeline: TimelineJob = {
    ...timelineResponse,
    timeline: {
      ...timelineResponse.timeline,
      review_status: "blocked",
      applied_recommendations: [],
      pending_recommendations: [
        {
          recommendation_id: "rec_broll_review_002",
          target_segment_id: "seg_002",
          recommendation_type: "broll",
          selected_asset_id: "asset_broll_review_002",
          score: 0.88,
          reason: "Operator should confirm the suggested B-roll pick.",
          auto_apply_allowed: false,
          review_required: true,
          payload: { tags: ["team", "meeting"] },
          created_at: "2026-06-30T00:00:00Z",
        },
      ],
      review_flags: [
        {
          code: "broll_review_required",
          segment_id: "seg_002",
          message: "Operator must confirm the B-roll pick before approval.",
        },
      ],
    },
  };
  const actionableReviewSnapshot: ReviewSnapshot = {
    ...reviewSnapshotResponse,
    review_status: "blocked",
    applied_recommendations: [],
    pending_recommendations: actionableTimeline.timeline.pending_recommendations,
    review_flags: actionableTimeline.timeline.review_flags,
  };
  const fetchMock = createFetchMock({
    timeline: actionableTimeline,
    reviewSnapshot: actionableReviewSnapshot,
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);

  fireEvent.click(await screen.findByRole("button", { name: /review snapshot/i }));
  fireEvent.click(await screen.findByRole("button", { name: /mark for manual edit/i }));

  expect(await screen.findByRole("heading", { name: /timeline-centered editor shell/i })).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: /target segment/i })).toHaveValue("seg_002");
  expect(screen.getByRole("checkbox", { name: /broll/i })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: /tts replacement/i })).not.toBeChecked();
});
```

- [x] **Step 2: Run test to verify it fails**

Run: `npm test -- --run src/app.test.tsx -t "opens the actionable pending recommendation in the editing session when marked for manual edit"`
Expected: FAIL because the global button is still a placeholder

- [x] **Step 3: Write minimal implementation**

```tsx
function handleMarkRecommendationForManualEdit() {
  if (!actionablePendingRecommendation) {
    return;
  }
  const mappedField = mapRecommendationTypeToEditingField(
    actionablePendingRecommendation.recommendation_type,
  );
  openSegmentInEditor(
    actionablePendingRecommendation.target_segment_id,
    mappedField ? [mappedField] : undefined,
  );
}
```

```tsx
if (action === "Mark for manual edit") {
  return (
    <button
      className="action-button"
      disabled={!actionablePendingRecommendation}
      key={action}
      onClick={handleMarkRecommendationForManualEdit}
      type="button"
    >
      {action}
    </button>
  );
}
```

- [x] **Step 4: Run test to verify it passes**

Run: `npm test -- --run src/app.test.tsx -t "opens the actionable pending recommendation in the editing session when marked for manual edit"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/App.tsx apps/web/src/app.test.tsx
git commit -m "feat: route manual edit review action into editor flow"
```

### Task 3: Add Explicit Reject Decision State

**Files:**
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\packages\storage-abstractions\src\videobox_storage\sqlite_schema.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\packages\storage-abstractions\src\videobox_storage\local_project_store.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\packages\core-engine\src\videobox_core_engine\local_pipeline.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\services\api\src\videobox_api\orchestration.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\services\api\src\videobox_api\main.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\tests\test_api.py`

- [x] **Step 1: Write the failing test**

```python
def test_review_snapshot_api_can_reject_pending_recommendation_without_leaving_it_pending(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    reject_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_broll_review_002/reject"
    )

    assert reject_response.status_code == 200
    payload = reject_response.json()
    assert payload["pending_recommendations"] == []
    assert payload["applied_recommendations"] == []
    assert payload["review_flags"] == []
    assert payload["review_status"] == "draft"
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api.py -k "reject_pending_recommendation" -q`
Expected: FAIL with missing route or missing persistence support

- [x] **Step 3: Write minimal implementation**

```python
decision_state = str(item.get("decision_state") or "pending")
applied = [
    item for item in recommendations
    if decision_state == "approved"
]
pending = [
    item for item in recommendations
    if decision_state == "pending"
]
```

```python
UPDATE recommendations
SET auto_apply_allowed = ?, review_required = ?, decision_state = ?
WHERE recommendation_id = ? AND project_id = ?
```

```python
def reject_pending_recommendation(...):
    rejected_recommendation["decision_state"] = "rejected"
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api.py -k "reject_pending_recommendation" -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_api.py packages/storage-abstractions/src/videobox_storage/sqlite_schema.py packages/storage-abstractions/src/videobox_storage/local_project_store.py packages/core-engine/src/videobox_core_engine/local_pipeline.py services/api/src/videobox_api/orchestration.py services/api/src/videobox_api/main.py
git commit -m "feat: add reject recommendation persistence"
```

### Task 4: Focused and Broader Verification

**Files:**
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\tests\test_api.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\apps\web\src\app.test.tsx`

- [x] **Step 1: Run backend focused verification**

Run: `pytest tests/test_api.py -k "approve_pending_recommendation or approve_preserves_non_target_review_items_and_blocked_status or reject_pending_recommendation" -q`
Expected: PASS

- [x] **Step 2: Run frontend focused verification**

Run: `npm test -- --run src/app.test.tsx`
Expected: PASS

- [x] **Step 3: Run frontend build**

Run: `npm run build`
Expected: PASS

- [x] **Step 4: Run full backend regression**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "test: verify review action family acceleration slice"
```

## Spec Coverage Check

- Approve reverse verification hardening: covered by Task 1
- Manual edit minimal slice through existing flow reuse: covered by Task 2
- Reject recommendation explicit persistence contract: covered by Task 3
- Focused tests, build, and full regression closeout: covered by Task 4

## Placeholder Scan

- No `TODO`, `TBD`, or "implement later" placeholders were intentionally left in task steps
- Each task includes a failing test, run command, minimal implementation guidance, and a verification command

## Type Consistency Check

- Use `review_status`, `pending_recommendations`, `applied_recommendations`, and `review_flags` consistently across API, store, and UI
- Introduce `decision_state` only for the reject-capable persistence contract and keep `Mark for manual edit` as a routing-only action

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-30-review-action-family-acceleration.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
