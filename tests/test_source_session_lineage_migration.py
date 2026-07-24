from __future__ import annotations

import sqlite3
from pathlib import Path

from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.postgres_schema import POSTGRES_MIGRATION_STATEMENTS
from videobox_storage.sqlite_schema import PROJECT_SCHEMA_STATEMENTS


ARTIFACT_TABLES = (
    "review_approvals",
    "preview_renders",
    "subtitle_renders",
    "exports",
)


def _write_legacy_lineage_database(
    *,
    store: LocalProjectStore,
    project_id: str,
    sessions: tuple[tuple[str, int], ...],
) -> None:
    database = store.database_path(project_id)
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    try:
        for statement in PROJECT_SCHEMA_STATEMENTS:
            connection.execute(statement)
        for index, (session_id, session_revision) in enumerate(sessions, start=1):
            connection.execute(
                """
                INSERT INTO editing_sessions (
                    session_id, project_id, timeline_id, file_uri, summary_json,
                    session_revision, session_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, '{}', ?, '{}', ?, ?)
                """,
                (
                    session_id,
                    project_id,
                    "timeline-legacy",
                    f"local://projects/{project_id}/editing_sessions/{session_id}.json",
                    session_revision,
                    f"2026-07-24T00:00:0{index}+00:00",
                    f"2026-07-24T00:00:0{index}+00:00",
                ),
            )
        connection.execute(
            """
            INSERT INTO review_approvals (
                timeline_id, project_id, status, approved_at, updated_at,
                source_session_revision, is_current
            ) VALUES ('timeline-legacy', ?, 'approved', NULL, '2026-07-24T00:00:00+00:00', 1, 1)
            """,
            (project_id,),
        )
        connection.execute(
            """
            INSERT INTO preview_renders (
                preview_id, project_id, timeline_id, file_uri, status,
                summary_json, created_at, source_session_revision, is_current
            ) VALUES (
                'preview-legacy', ?, 'timeline-legacy', 'local://preview.mp4',
                'succeeded', '{}', '2026-07-24T00:00:00+00:00', 1, 1
            )
            """,
            (project_id,),
        )
        connection.execute(
            """
            INSERT INTO subtitle_renders (
                subtitle_id, project_id, timeline_id, format, file_uri, status,
                summary_json, created_at, source_session_revision, is_current
            ) VALUES (
                'subtitle-legacy', ?, 'timeline-legacy', 'srt',
                'local://subtitle.srt', 'succeeded', '{}',
                '2026-07-24T00:00:00+00:00', 1, 1
            )
            """,
            (project_id,),
        )
        connection.execute(
            """
            INSERT INTO exports (
                export_id, project_id, timeline_id, export_type, file_uri,
                status, metadata_json, created_at, source_session_id,
                source_session_revision, is_current
            ) VALUES (
                'export-legacy', ?, 'timeline-legacy', 'final_render',
                'local://final.mp4', 'succeeded', '{}',
                '2026-07-24T00:00:00+00:00', NULL, 1, 1
            )
            """,
            (project_id,),
        )
        connection.commit()
    finally:
        connection.close()


def _artifact_session_ids(store: LocalProjectStore, project_id: str) -> dict[str, str | None]:
    connection = sqlite3.connect(store.database_path(project_id))
    try:
        return {
            table: connection.execute(
                f"SELECT source_session_id FROM {table}"
            ).fetchone()[0]
            for table in ARTIFACT_TABLES
        }
    finally:
        connection.close()


def test_sqlite_migration_backfills_only_unambiguous_matching_legacy_lineage(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id = "legacy-unambiguous"
    _write_legacy_lineage_database(
        store=store,
        project_id=project_id,
        sessions=(("session-only", 1),),
    )

    connection = store._connection(project_id)
    connection.close()

    assert _artifact_session_ids(store, project_id) == {
        table: "session-only" for table in ARTIFACT_TABLES
    }


def test_sqlite_migration_leaves_same_revision_replacement_lineage_unstamped(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id = "legacy-ambiguous"
    _write_legacy_lineage_database(
        store=store,
        project_id=project_id,
        sessions=(("session-old", 1), ("session-new", 1)),
    )

    connection = store._connection(project_id)
    connection.close()

    assert _artifact_session_ids(store, project_id) == {
        table: None for table in ARTIFACT_TABLES
    }


def test_sqlite_migration_leaves_revision_mismatch_lineage_unstamped(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id = "legacy-revision-mismatch"
    _write_legacy_lineage_database(
        store=store,
        project_id=project_id,
        sessions=(("session-only", 2),),
    )

    connection = store._connection(project_id)
    connection.close()

    assert _artifact_session_ids(store, project_id) == {
        table: None for table in ARTIFACT_TABLES
    }


def test_sqlite_freshness_trigger_does_not_guess_between_same_revision_sessions(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id = "legacy-trigger-ambiguous"
    _write_legacy_lineage_database(
        store=store,
        project_id=project_id,
        sessions=(("session-old", 1), ("session-new", 1)),
    )
    connection = store._connection(project_id)
    try:
        connection.execute(
            """
            INSERT INTO preview_renders (
                preview_id, project_id, timeline_id, file_uri, status,
                summary_json, created_at, source_session_id,
                source_session_revision, is_current
            ) VALUES (
                'preview-after-migration', ?, 'timeline-legacy',
                'local://preview-after.mp4', 'succeeded', '{}',
                '2026-07-24T00:01:00+00:00', NULL, 1, 1
            )
            """,
            (project_id,),
        )
        connection.commit()
        row = connection.execute(
            """
            SELECT source_session_id
            FROM preview_renders
            WHERE project_id = ? AND preview_id = 'preview-after-migration'
            """,
            (project_id,),
        ).fetchone()
    finally:
        connection.close()

    assert row["source_session_id"] is None


def test_postgres_migrations_include_the_safe_artifact_lineage_backfill() -> None:
    backfills = [
        statement
        for statement in POSTGRES_MIGRATION_STATEMENTS
        if statement.lstrip().startswith("UPDATE ")
        and "source_session_id" in statement
        and "editing_sessions" in statement
    ]

    assert len(backfills) == len(ARTIFACT_TABLES)
    assert all("COUNT(*)" in statement for statement in backfills)
    assert all("source_session_revision" in statement for statement in backfills)
