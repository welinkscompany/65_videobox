from __future__ import annotations

from pathlib import Path

import pytest

from videobox_storage.local_project_store import DEFAULT_EXPORT_RETENTION_COUNT, LocalProjectStore


def test_save_final_render_prunes_exports_beyond_retention_count(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Export Retention Project")

    saved_exports = []
    for index in range(DEFAULT_EXPORT_RETENTION_COUNT + 3):
        source_output = tmp_path / f"render_{index}.mp4"
        source_output.write_bytes(f"fake render {index}".encode("utf-8"))
        saved = store.save_final_render(
            project_id=project.project_id,
            timeline_id="timeline_001",
            source_output_path=source_output,
        )
        saved_exports.append(saved)

    remaining_rows = store._fetchall(
        project.project_id,
        "SELECT export_id, file_uri FROM exports WHERE export_type = ? ORDER BY created_at ASC",
        ("final_render",),
    )
    assert len(remaining_rows) == DEFAULT_EXPORT_RETENTION_COUNT

    remaining_ids = {row["export_id"] for row in remaining_rows}
    newest_ids = {export["export_id"] for export in saved_exports[-DEFAULT_EXPORT_RETENTION_COUNT:]}
    assert remaining_ids == newest_ids

    oldest_export = saved_exports[0]
    oldest_path = store.resolve_storage_uri(
        project_id=project.project_id, storage_uri=oldest_export["file_uri"]
    )
    assert not oldest_path.exists()
    assert not oldest_path.parent.exists()

    with pytest.raises(KeyError):
        store.get_final_render_export(project_id=project.project_id, export_id=oldest_export["export_id"])

    newest_export = saved_exports[-1]
    newest_path = store.resolve_storage_uri(
        project_id=project.project_id, storage_uri=newest_export["file_uri"]
    )
    assert newest_path.exists()


def test_save_capcut_draft_export_prunes_independently_of_other_export_types(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Export Retention Mixed Types Project")

    # A single final_render export should not be pruned by capcut_draft_export saves.
    source_output = tmp_path / "render.mp4"
    source_output.write_bytes(b"fake render bytes")
    final_render_export = store.save_final_render(
        project_id=project.project_id,
        timeline_id="timeline_001",
        source_output_path=source_output,
    )

    for index in range(DEFAULT_EXPORT_RETENTION_COUNT + 2):
        draft_dir = tmp_path / f"draft_source_{index}"
        draft_dir.mkdir()
        (draft_dir / "draft_content.json").write_text("{}", encoding="utf-8")
        store.save_capcut_draft_export(
            project_id=project.project_id,
            timeline_id="timeline_001",
            source_draft_path=draft_dir,
        )

    final_render_rows = store._fetchall(
        project.project_id,
        "SELECT export_id FROM exports WHERE export_type = ?",
        ("final_render",),
    )
    assert len(final_render_rows) == 1
    assert final_render_rows[0]["export_id"] == final_render_export["export_id"]

    draft_rows = store._fetchall(
        project.project_id,
        "SELECT export_id FROM exports WHERE export_type = ?",
        ("capcut_draft_export",),
    )
    assert len(draft_rows) == DEFAULT_EXPORT_RETENTION_COUNT
