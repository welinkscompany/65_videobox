import inspect
import re

from videobox_storage.postgres_compat import translate_sql
from videobox_storage.postgres_schema import POSTGRES_MIGRATION_STATEMENTS, POSTGRES_SCHEMA_STATEMENTS
from videobox_storage.local_project_store import LocalProjectStore


def test_translate_sql_preserves_postgres_upsert_and_converts_sqlite_placeholders() -> None:
    statement = "UPDATE jobs SET status = ? WHERE project_id = ?"

    assert translate_sql(statement) == "UPDATE jobs SET status = %s WHERE project_id = %s"


def test_translate_sql_converts_sqlite_insert_or_ignore() -> None:
    statement = "INSERT OR IGNORE INTO media_analysis_cache (cache_id) VALUES (?)"

    assert translate_sql(statement) == "INSERT INTO media_analysis_cache (cache_id) VALUES (%s) ON CONFLICT DO NOTHING"


def test_translate_sql_converts_known_sqlite_replace_into_postgres_upsert() -> None:
    statement = "INSERT OR REPLACE INTO media_embeddings (embedding_id, embedding_json) VALUES (?, ?)"

    assert translate_sql(statement) == (
        "INSERT INTO media_embeddings (embedding_id, embedding_json) VALUES (%s, %s) "
        "ON CONFLICT (embedding_id) DO UPDATE SET embedding_json = EXCLUDED.embedding_json"
    )


def test_translate_sql_preserves_portable_hermes_ledger_revoke_upsert() -> None:
    statement = (
        "INSERT INTO hermes_capability_ledger (project_id, jti, state, expires_at, recorded_at) "
        "VALUES (?, ?, 'revoked', ?, ?) "
        "ON CONFLICT (project_id, jti) DO UPDATE SET "
        "state = EXCLUDED.state, expires_at = EXCLUDED.expires_at, recorded_at = EXCLUDED.recorded_at"
    )

    assert translate_sql(statement) == statement.replace("?", "%s")


def test_translate_sql_qualifies_revision_increment_for_known_operational_index_tables() -> None:
    for table in ("director_proposal_revisions", "director_asset_index_revisions"):
        statement = (
            f"INSERT INTO {table} (project_id, revision) VALUES (?, 1) "
            "ON CONFLICT(project_id) DO UPDATE SET revision = revision + 1"
        )

        assert translate_sql(statement) == (
            f"INSERT INTO {table} (project_id, revision) VALUES (%s, 1) "
            f"ON CONFLICT(project_id) DO UPDATE SET revision = {table}.revision + 1"
        )


def test_translate_sql_preserves_unknown_revision_upsert() -> None:
    statement = (
        "INSERT INTO unrelated_revisions (project_id, revision) VALUES (?, 1) "
        "ON CONFLICT(project_id) DO UPDATE SET revision = revision + 1"
    )

    assert translate_sql(statement) == (
        "INSERT INTO unrelated_revisions (project_id, revision) VALUES (%s, 1) "
        "ON CONFLICT(project_id) DO UPDATE SET revision = revision + 1"
    )


def test_postgres_schema_has_no_sqlite_only_autoincrement_syntax() -> None:
    assert POSTGRES_SCHEMA_STATEMENTS
    assert all("AUTOINCREMENT" not in statement for statement in POSTGRES_SCHEMA_STATEMENTS)


def test_director_message_queries_do_not_depend_on_sqlite_rowid() -> None:
    source = "\n".join(
        (
            inspect.getsource(LocalProjectStore.list_director_messages),
            inspect.getsource(LocalProjectStore.append_director_exchange),
        )
    )

    assert "rowid" not in source
    assert "ORDER BY message_order, message_id" in source
    assert "message_order = ?" in source


def test_all_director_message_writes_persist_durable_order() -> None:
    source = inspect.getsource(LocalProjectStore)
    inserts = re.findall(
        r"INSERT INTO director_messages\s*\((.*?)\)\s*VALUES",
        source,
        flags=re.DOTALL,
    )

    assert len(inserts) == 7
    assert all("message_order" in columns for columns in inserts)


def test_postgres_migrations_add_durable_capcut_handoff_claim_columns() -> None:
    statements = "\n".join(POSTGRES_MIGRATION_STATEMENTS)

    assert "ALTER TABLE exports ADD COLUMN IF NOT EXISTS handoff_claim_token TEXT" in statements
    assert "ALTER TABLE exports ADD COLUMN IF NOT EXISTS handoff_claim_job_id TEXT" in statements


def test_postgres_migrations_add_hermes_creator_context_identity_columns() -> None:
    statements = "\n".join(POSTGRES_MIGRATION_STATEMENTS)

    assert (
        "ALTER TABLE director_messages ADD COLUMN IF NOT EXISTS "
        "message_order BIGINT"
    ) in statements
    assert "PARTITION BY conversation_id" in statements
    assert "ORDER BY created_at, ctid" in statements
    assert (
        "ALTER TABLE director_messages ALTER COLUMN message_order SET NOT NULL"
        in statements
    )
    assert (
        "ALTER TABLE director_hermes_runs ADD COLUMN IF NOT EXISTS "
        "expected_session_revision INTEGER NOT NULL DEFAULT 0"
    ) in statements
    assert (
        "ALTER TABLE director_hermes_runs ADD COLUMN IF NOT EXISTS "
        "expected_asset_index_revision INTEGER NOT NULL DEFAULT -1"
    ) in statements
    assert (
        "ALTER TABLE director_hermes_runs ADD COLUMN IF NOT EXISTS "
        "selected_segment_id TEXT"
    ) in statements
    assert (
        "ALTER TABLE director_hermes_runs ADD COLUMN IF NOT EXISTS "
        "retry_of_run_id TEXT"
    ) in statements
    assert (
        "ALTER TABLE director_hermes_runs ADD COLUMN IF NOT EXISTS "
        "assistant_draft_text TEXT NOT NULL DEFAULT ''"
    ) in statements


def test_output_publish_transaction_explicitly_serializes_postgres_lineage_and_paths() -> None:
    class RecordingPostgresConnection:
        def __init__(self) -> None:
            self.statements: list[str] = []

        def execute(self, statement: str):
            self.statements.append(statement)

    connection = RecordingPostgresConnection()

    LocalProjectStore._begin_output_publish_transaction(connection)

    assert connection.statements == [
        "BEGIN",
        (
            "LOCK TABLE editing_sessions, assets, review_approvals, "
            "subtitle_renders, preview_renders, exports "
            "IN SHARE ROW EXCLUSIVE MODE"
        ),
    ]


def test_postgres_output_and_handoff_transactions_share_the_same_lock_order() -> None:
    class RecordingPostgresConnection:
        def __init__(self) -> None:
            self.statements: list[str] = []

        def execute(self, statement: str) -> None:
            self.statements.append(statement)

    output = RecordingPostgresConnection()
    handoff = RecordingPostgresConnection()

    LocalProjectStore._begin_output_publish_transaction(output)
    LocalProjectStore._begin_capcut_draft_handoff_transaction(handoff)

    for statements in (output.statements, handoff.statements):
        lock = statements[1]
        assert lock.index("editing_sessions") < lock.index("exports")


def test_director_transactions_explicitly_lock_postgres_truth_in_shared_order() -> None:
    class RecordingPostgresConnection:
        def __init__(self) -> None:
            self.statements: list[str] = []

        def execute(self, statement: str) -> None:
            self.statements.append(statement)

    connection = RecordingPostgresConnection()

    LocalProjectStore._begin_director_session_transaction(connection)

    assert connection.statements == [
        "BEGIN",
        (
            "LOCK TABLE editing_sessions, assets, director_asset_index_revisions, "
            "director_proposals, tts_candidates, review_approvals, subtitle_renders, "
            "preview_renders, exports, exact_preview_renders "
            "IN SHARE ROW EXCLUSIVE MODE"
        ),
    ]
    lock = connection.statements[1]
    assert translate_sql(lock) == lock
    assert lock.index("editing_sessions") < lock.index("assets")
    assert lock.index("assets") < lock.index("director_asset_index_revisions")
    assert lock.index("director_asset_index_revisions") < lock.index("director_proposals")
    assert lock.index("director_proposals") < lock.index("tts_candidates")
    assert lock.index("tts_candidates") < lock.index("review_approvals")
    assert lock.index("review_approvals") < lock.index("exports")
    assert lock.index("exports") < lock.index("exact_preview_renders")
    for method in (
        LocalProjectStore.apply_director_proposal_transaction,
        LocalProjectStore.update_yujin_image_overlay_transaction,
        LocalProjectStore.batch_apply_director_proposal_transaction,
    ):
        source = inspect.getsource(method)
        assert "transaction_start_hook=self._begin_director_session_transaction" in source
