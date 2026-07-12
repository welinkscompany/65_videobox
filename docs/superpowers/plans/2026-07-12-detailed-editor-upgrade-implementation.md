# VideoBox Detailed Editor Upgrade Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deliver a fixed-track hybrid editor whose caption style and edits survive browser preview, SRT, styled MP4, and a real CapCut draft.

**Architecture:** The editing session remains the only editable truth. A canonical caption-style model is persisted with revisioned mutations; SRT and ASS are separate derived artifacts; FFmpeg burns ASS into YouTube MP4; pycapcut creates styled TextSegment records for its proven subset. This remains segment/fixed-role-track editing, not a general NLE.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, SQLite, FFmpeg/libass, pycapcut, React 19, TypeScript, Vitest, pytest.

---

## Decision locks

- SRT contains text and timing only. ASS is the canonical styled subtitle artifact.
- YouTube MP4 burns ASS into video and does not also mux selectable SRT; SRT is a separate accessibility delivery.
- CapCut uses per-caption TextSegment, not import_srt. Supported: font registry ID, size, bold/italic, color, alignment, outline, background, position, width. Shadow initially emits a warning.
- The first vertical slice proves one caption in persisted session JSON, ASS, rendered MP4, and draft_content.json before broad UI work.
- Every mutation has expected_revision; stale writes return 409 plus latest session.

## File structure

- Create: packages/domain-models/src/videobox_domain_models/caption_style.py — immutable model, validation, compatibility result.
- Create: packages/core-engine/src/videobox_core_engine/ass_subtitles.py — deterministic ASS serializer.
- Modify: packages/core-engine/src/videobox_core_engine/editing_session_and_regeneration.py — style/timeline mutations, revision/history.
- Modify: packages/core-engine/src/videobox_core_engine/ffmpeg_final_renderer.py — ASS burn-in, selected preview.
- Modify: packages/capcut-export/src/videobox_capcut_export/pycapcut_adapter.py — styled TextSegment and warnings.
- Modify: packages/storage-abstractions/src/videobox_storage/local_project_store.py — revision migration/transaction.
- Modify: services/api/src/videobox_api/models.py and main.py — contracts/409.
- Modify: apps/web/src/api.ts, App.tsx, styles.css — panel, timeline, recovery.
- Create: tests/test_caption_style.py, tests/test_ass_subtitles.py, tests/test_editor_timeline_mutations.py, tests/test_api_caption_style_endpoint.py.

### Task 1: Styled output vertical slice

**Files:** caption_style.py, ass_subtitles.py, test_caption_style.py, test_ass_subtitles.py, test_ffmpeg_final_renderer.py, test_pycapcut_adapter.py.

- [x] Step 1 — Write failing contracts.

~~~
def test_caption_style_rejects_invalid_rgba_and_clamps_safe_area() -> None:
    with pytest.raises(ValueError, match="text_color"):
        CaptionStyle(text_color="#fff")
    assert CaptionStyle(position_y_percent=100, safe_area_enabled=True).position_y_percent < 100

def test_ass_contains_style_and_caption_timing() -> None:
    ass = render_ass([{"caption_text": "테스트", "start_sec": 1, "end_sec": 3}], CaptionStyle())
    assert "Dialogue:" in ass and "테스트" in ass and "Style: Default" in ass
~~~

- [x] Step 2 — Run RED.

Run: .venv\Scripts\python.exe -m pytest tests/test_caption_style.py tests/test_ass_subtitles.py -q
Expected: import failure.

- [x] Step 3 — Implement canonical model and serializer. Validate RGBA, size, safe area, width/alignment. Convert CSS RRGGBBAA to ASS AABBGGRR with inverted alpha; escape ASS text; format seconds as H:MM:SS.cc.

- [x] Step 4 — Extend RED tests for actual output. Assert FFmpeg has subtitles=<caption.ass>; inspect draft_content.json for text style color, size, outline, background.

- [x] Step 5 — Implement adapters. Add subtitle_ass_path and FFmpeg libass burn-in. Create pycapcut TextStyle, TextBorder, TextBackground and TextSegment per caption. Non-default shadow returns capcut_compatibility_warnings.

- [x] Step 6 — Verify and commit.

Run: .venv\Scripts\python.exe -m pytest tests/test_caption_style.py tests/test_ass_subtitles.py tests/test_ffmpeg_final_renderer.py tests/test_pycapcut_adapter.py -q
Expected: PASS.

~~~
git add packages/domain-models packages/core-engine packages/capcut-export tests
git commit -m "feat: render caption style through mp4 and capcut"
~~~

### Task 2: Revisioned persistence and scoped style API

**Files:** local_project_store.py, editing_session_and_regeneration.py, models.py, main.py, test_api_caption_style_endpoint.py, test_editing_session.py, test_api.py.

- [x] Step 1 — Write RED API tests: PATCH caption-style accepts style, scope, segment_ids, expected_revision; increments revision; stale repeat returns 409 plus latest_session.
- [x] Step 2 — Run RED: .venv\Scripts\python.exe -m pytest tests/test_api_caption_style_endpoint.py -q. Expected: 404 or request-model failure.
- [x] Step 3 — Add session_revision INTEGER NOT NULL DEFAULT 1. Write payload, DB row, history in one transaction using revision compare-and-swap; zero updated rows raises EditingSessionConflict.
- [x] Step 4 — Add preflight/mutation scopes: current_caption, selected_captions, from_current, whole_project, project_default. Persist resolved snapshots.
- [x] Step 5 — Test 422 preserves revision, restart preserves style/revision, partial regeneration retains manual text/style.
- [x] Step 6 — Verify and commit.

Run: .venv\Scripts\python.exe -m pytest tests/test_api_caption_style_endpoint.py tests/test_editing_session.py tests/test_api.py -q
Expected: PASS.

~~~
git add packages/storage-abstractions packages/core-engine services/api tests
git commit -m "feat: persist revisioned caption styles"
~~~

### Task 3: Presets, favorites, and browser recovery

**Files:** user_library_store.py, API files, apps/web/src/api.ts, App.tsx, styles.css, app.test.tsx, test_user_library_store.py, test_api_editor_favorites.py.

- [x] Step 1 — Write RED tests for immutable built-ins, project/global snapshots, idempotent favorite toggle, missing display, and 409 UI recovery without loss.
- [x] Step 2 — Run RED: .venv\Scripts\python.exe -m pytest tests/test_user_library_store.py tests/test_api_editor_favorites.py -q; npm --prefix apps/web test -- --run src/app.test.tsx. Expected: FAIL.
- [x] Step 3 — Implement UserLibraryStore at <projects_root>/../videobox-user-library. Use IDs project:<project_id>:<preset_id> and pack:<pack_id>:<asset_id>.
- [x] Step 4 — Add panel, scope preflight confirmation, favorite/recent, 800ms debounce, retry, stale compare/reload, restored selection, approximate preview label.
- [x] Step 5 — Verify and commit.

Run: .venv\Scripts\python.exe -m pytest tests/test_user_library_store.py tests/test_api_editor_favorites.py -q; npm --prefix apps/web test; npm --prefix apps/web run build
Expected: PASS.

### Task 4: Fixed-track timeline and selected-range preview

**Files:** test_editor_timeline_mutations.py; editing_session_and_regeneration.py; ffmpeg_final_renderer.py; API files; apps/web API/App/styles/tests.

- [x] Step 1 — Write RED tests for 0.2-second split bounds, adjacent-only merge, no overlap, lineage, 100-event undo/redo, styled selected-range preview.
- [x] Step 2 — Implement split_segment, merge_adjacent_segments, reorder_segments, set_segment_bounds, undo, redo. Carry caption/B-roll/music/SFX/TTS/overlay identity; reject arbitrary tracks/overlap.
- [x] Step 3 — Add API/UI after domain tests green. Events contain inverse payload; render/import is not undoable; render only five fixed role tracks.
- [x] Step 4 — Verify and commit.

Run: .venv\Scripts\python.exe -m pytest tests/test_editor_timeline_mutations.py tests/test_editing_session.py tests/test_api.py -q; npm --prefix apps/web test; npm --prefix apps/web run build
Expected: PASS.

### Task 5: Media controls, error recovery, release evidence

**Files:** ffmpeg_final_renderer.py, pycapcut_adapter.py, App.tsx, styles.css, output tests, docs/development-status-2026-06-29.ko.md.

- [ ] Step 1 — Write RED tests for BGM/SFX gain/fade, B-roll crop/fit/loop, missing font/media blocks, visible CapCut warnings.
- [ ] Step 2 — Add normalized gain_db, fade_in_sec, fade_out_sec, loop, ducking and map once in both adapters while preserving loop/pad/trim.
- [ ] Step 3 — Preview/final/CapCut errors retain last successful artifact and use existing UI error boundary.
- [ ] Step 4 — Release verify.

Run: .venv\Scripts\python.exe -m pytest -q
Run: npm --prefix apps/web test
Run: npm --prefix apps/web run build
Run: ./scripts/dev-fast-path.ps1 -Mode smoke
Expected: PASS. Run a 600-second Korean ingest → edit → SRT → styled MP4 → real CapCut draft smoke; record paths/warnings.

- [ ] Step 5 — Update SSOT, run git status --short and git diff --check, then commit feat: complete detailed editor upgrade.

## Coverage self-review

Tasks 1–5 cover all editor requirements and put the reverse-path P0 proof first. Free multilayer editing, keyframes, grading, speed ramps and advanced mixing remain excluded.
