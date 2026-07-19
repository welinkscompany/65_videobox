from videobox_storage.postgres_compat import translate_sql
from videobox_storage.postgres_schema import POSTGRES_SCHEMA_STATEMENTS


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
