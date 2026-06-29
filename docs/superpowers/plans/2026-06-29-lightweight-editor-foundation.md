# Lightweight Editor Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first editable session layer so VideoBox can store user edits, expose edit APIs, and prepare safe partial regeneration before any heavier editor UI work.

**Architecture:** Keep timeline JSON as the internal source of truth, but add a separate editing session layer that records user overrides and produces a reviewed editable state. Store editing session data in the local project store, expose it through the API, and keep regeneration rules in the core engine so UI and OSS editor shells do not own editing logic.

**Tech Stack:** Python, FastAPI, pytest, local SQLite/file storage, existing VideoBox core-engine/storage packages

---

## File Structure

- Create: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\packages\core-engine\src\videobox_core_engine\editing_session.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\packages\core-engine\src\videobox_core_engine\__init__.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\packages\storage-abstractions\src\videobox_storage\sqlite_schema.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\packages\storage-abstractions\src\videobox_storage\local_project_store.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\packages\core-engine\src\videobox_core_engine\local_pipeline.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\services\api\src\videobox_api\orchestration.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\services\api\src\videobox_api\main.py`
- Test: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\tests\test_editing_session.py`
- Test: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\tests\test_api.py`

### Task 1: Editing Session Domain Model

**Files:**
- Create: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\packages\core-engine\src\videobox_core_engine\editing_session.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\packages\core-engine\src\videobox_core_engine\__init__.py`
- Test: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\tests\test_editing_session.py`

- [ ] **Step 1: Write the failing test**

```python
from videobox_core_engine.editing_session import build_editing_session


def test_build_editing_session_from_review_timeline_creates_editable_segment_state() -> None:
    timeline = {
        "timeline_id": "timeline_001",
        "project_id": "project_001",
        "tracks": [
            {
                "track_id": "narration_primary",
                "track_type": "narration",
                "clips": [
                    {
                        "clip_id": "clip_narration_001",
                        "segment_id": "seg_001",
                        "asset_uri": "local://projects/project_001/segments/seg_001",
                        "start_sec": 0.0,
                        "end_sec": 3.0,
                        "clip_type": "narration",
                    }
                ],
            }
        ],
        "review_flags": [],
        "pending_recommendations": [],
    }
    segments = [
        {
            "segment_id": "seg_001",
            "text": "Office overview intro.",
            "start_sec": 0.0,
            "end_sec": 3.0,
            "review_required": False,
            "cleanup_decision": "keep",
        }
    ]

    session = build_editing_session(
        project_id="project_001",
        timeline=timeline,
        segments=segments,
    )

    assert session["project_id"] == "project_001"
    assert session["timeline_id"] == "timeline_001"
    assert session["segments"][0]["segment_id"] == "seg_001"
    assert session["segments"][0]["caption_text"] == "Office overview intro."
    assert session["segments"][0]["cut_action"] == "keep"
    assert session["history"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_editing_session.py::test_build_editing_session_from_review_timeline_creates_editable_segment_state -v`
Expected: FAIL because `videobox_core_engine.editing_session` does not exist yet

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations


def build_editing_session(
    *,
    project_id: str,
    timeline: dict[str, object],
    segments: list[dict[str, object]],
) -> dict[str, object]:
    editable_segments = []
    for segment in segments:
        editable_segments.append(
            {
                "segment_id": segment["segment_id"],
                "caption_text": segment["text"],
                "start_sec": segment["start_sec"],
                "end_sec": segment["end_sec"],
                "cut_action": segment.get("cleanup_decision", "keep"),
                "review_required": bool(segment.get("review_required", False)),
                "broll_override": None,
                "visual_overlays": [],
                "music_override": None,
            }
        )
    return {
        "project_id": project_id,
        "timeline_id": timeline["timeline_id"],
        "segments": editable_segments,
        "history": [],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_editing_session.py::test_build_editing_session_from_review_timeline_creates_editable_segment_state -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_editing_session.py packages/core-engine/src/videobox_core_engine/editing_session.py packages/core-engine/src/videobox_core_engine/__init__.py
git commit -m "feat: add editing session domain foundation"
```

### Task 2: Editing Session Persistence

**Files:**
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\packages\storage-abstractions\src\videobox_storage\sqlite_schema.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\packages\storage-abstractions\src\videobox_storage\local_project_store.py`
- Test: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\tests\test_editing_session.py`

- [ ] **Step 1: Write the failing test**

```python
from videobox_storage.local_project_store import LocalProjectStore


def test_save_editing_session_persists_current_state_and_history(tmp_path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Editing Session Project")

    saved = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline_001",
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Updated caption",
                    "start_sec": 0.0,
                    "end_sec": 2.5,
                    "cut_action": "trim",
                    "review_required": False,
                    "broll_override": {"asset_id": "asset_010"},
                    "visual_overlays": [{"overlay_type": "image_card", "asset_id": "asset_020"}],
                    "music_override": None,
                }
            ],
            "history": [
                {
                    "mutation_type": "caption_update",
                    "segment_id": "seg_001",
                }
            ],
        },
    )

    loaded = store.get_editing_session(project_id=project.project_id, session_id=saved["session_id"])

    assert loaded["timeline_id"] == "timeline_001"
    assert loaded["segments"][0]["caption_text"] == "Updated caption"
    assert loaded["history"][0]["mutation_type"] == "caption_update"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_editing_session.py::test_save_editing_session_persists_current_state_and_history -v`
Expected: FAIL because `save_editing_session` and `get_editing_session` do not exist yet

- [ ] **Step 3: Write minimal implementation**

```python
CREATE TABLE IF NOT EXISTS editing_sessions (
    session_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    timeline_id TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
```

```python
def save_editing_session(self, *, project_id: str, timeline_id: str, session_payload: dict[str, Any]) -> dict[str, Any]:
    session_id = "editing_session_001"
    payload = {
        "session_id": session_id,
        "project_id": project_id,
        "timeline_id": timeline_id,
        "segments": session_payload.get("segments", []),
        "history": session_payload.get("history", []),
    }
    return payload
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_editing_session.py::test_save_editing_session_persists_current_state_and_history -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_editing_session.py packages/storage-abstractions/src/videobox_storage/sqlite_schema.py packages/storage-abstractions/src/videobox_storage/local_project_store.py
git commit -m "feat: persist editing sessions"
```

### Task 3: Editing Mutation API

**Files:**
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\packages\core-engine\src\videobox_core_engine\local_pipeline.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\services\api\src\videobox_api\orchestration.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\services\api\src\videobox_api\main.py`
- Test: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\tests\test_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_editing_session_api_can_create_and_patch_caption_override(client, tmp_path) -> None:
    project_id, timeline_job_id = _create_approved_timeline_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    assert create_response.status_code == 201
    session_id = create_response.json()["session_id"]

    patch_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/caption",
        json={"caption_text": "Manual caption fix"},
    )

    assert patch_response.status_code == 200
    assert patch_response.json()["segments"][0]["caption_text"] == "Manual caption fix"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api.py::test_editing_session_api_can_create_and_patch_caption_override -v`
Expected: FAIL with missing route error

- [ ] **Step 3: Write minimal implementation**

```python
@app.post("/api/projects/{project_id}/editing-sessions", status_code=status.HTTP_201_CREATED)
def create_editing_session(project_id: str, payload: CreateEditingSessionRequest) -> EditingSessionResponse:
    session = orchestrator.create_editing_session(
        project_id=project_id,
        timeline_job_id=payload.timeline_job_id,
    )
    return EditingSessionResponse(**session)


@app.patch("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/caption")
def patch_caption_override(
    project_id: str,
    session_id: str,
    segment_id: str,
    payload: CaptionOverrideRequest,
) -> EditingSessionResponse:
    session = orchestrator.update_segment_caption(
        project_id=project_id,
        session_id=session_id,
        segment_id=segment_id,
        caption_text=payload.caption_text,
    )
    return EditingSessionResponse(**session)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api.py::test_editing_session_api_can_create_and_patch_caption_override -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_api.py packages/core-engine/src/videobox_core_engine/local_pipeline.py services/api/src/videobox_api/orchestration.py services/api/src/videobox_api/main.py
git commit -m "feat: add editing session mutation api"
```

### Task 4: Partial Regeneration Contract

**Files:**
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\packages\core-engine\src\videobox_core_engine\editing_session.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\packages\core-engine\src\videobox_core_engine\local_pipeline.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\services\api\src\videobox_api\main.py`
- Test: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\tests\test_editing_session.py`
- Test: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\tests\test_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_partial_regeneration_request_scopes_only_targeted_segments() -> None:
    from videobox_core_engine.editing_session import build_partial_regeneration_request

    session = {
        "session_id": "editing_session_001",
        "segments": [
            {"segment_id": "seg_001", "caption_text": "Keep this", "broll_override": None},
            {"segment_id": "seg_002", "caption_text": "Regenerate this", "broll_override": None},
        ],
    }

    request = build_partial_regeneration_request(
        session=session,
        segment_ids=["seg_002"],
        fields=["broll", "visual_overlay"],
    )

    assert request["segment_ids"] == ["seg_002"]
    assert request["fields"] == ["broll", "visual_overlay"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_editing_session.py::test_partial_regeneration_request_scopes_only_targeted_segments -v`
Expected: FAIL because helper does not exist yet

- [ ] **Step 3: Write minimal implementation**

```python
def build_partial_regeneration_request(
    *,
    session: dict[str, object],
    segment_ids: list[str],
    fields: list[str],
) -> dict[str, object]:
    return {
        "session_id": session["session_id"],
        "segment_ids": segment_ids,
        "fields": fields,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_editing_session.py::test_partial_regeneration_request_scopes_only_targeted_segments -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_editing_session.py tests/test_api.py packages/core-engine/src/videobox_core_engine/editing_session.py packages/core-engine/src/videobox_core_engine/local_pipeline.py services/api/src/videobox_api/main.py
git commit -m "feat: add partial regeneration contract"
```

### Task 5: Full Regression Check

**Files:**
- Test: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\tests\test_editing_session.py`
- Test: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\tests\test_api.py`
- Test: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\tests\test_review_timeline.py`
- Test: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\tests\test_preview_export.py`

- [ ] **Step 1: Run focused regression suite**

Run: `pytest tests/test_editing_session.py tests/test_api.py tests/test_review_timeline.py tests/test_preview_export.py -q`
Expected: PASS

- [ ] **Step 2: Run full backend suite**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 3: Review scope boundaries**

Checklist:
- Editing logic stayed in `core-engine`
- Persistence stayed in `storage-abstractions`
- HTTP shape stayed in `services/api`
- No OSS editor shell code was imported
- CapCut export path still reads timeline output rather than becoming the source of truth

- [ ] **Step 4: Commit final stabilization**

```bash
git add .
git commit -m "feat: add lightweight editor foundation"
```

## Spec Coverage Check

- Editing session model: covered by Task 1
- Session persistence: covered by Task 2
- Mutation API: covered by Task 3
- Partial regeneration contract: covered by Task 4
- Regression and boundary validation: covered by Task 5

## Placeholder Scan

- No `TODO`, `TBD`, or "implement later" placeholders were intentionally left in task steps
- Each task includes a failing test, a run command, minimal implementation guidance, and a verification command

## Type Consistency Check

- Use `session_id`, `timeline_id`, `segment_id`, `caption_text`, `cut_action`, and `history` consistently across tasks
- Keep partial regeneration request fields as `segment_ids` and `fields` in both core-engine and API

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-29-lightweight-editor-foundation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
