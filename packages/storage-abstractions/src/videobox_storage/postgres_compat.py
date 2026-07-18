from __future__ import annotations

import re


_REPLACE_PRIMARY_KEYS = {
    "media_analysis_profiles": "analysis_id",
    "media_scene_windows": "scene_window_id",
    "media_embeddings": "embedding_id",
    "projects": "project_id",
    "provider_trace_failed_runs": "job_id",
}

_REVISION_INCREMENT_TABLES = {
    "director_asset_index_revisions",
    "director_proposal_revisions",
}

_PROJECT_SCOPED_CONFLICT_TARGETS = {
    "review_approvals": ("timeline_id",),
}


def translate_sql(statement: str) -> str:
    """Translate the small, explicit SQLite dialect surface used by VideoBox.

    This is intentionally not a generic SQL translator. Unknown SQLite-only
    statements fail in PostgreSQL instead of being silently reinterpreted.
    """
    normalized = statement.strip()
    if normalized.upper() == "BEGIN IMMEDIATE":
        return "BEGIN"

    ignore_match = re.match(r"INSERT\s+OR\s+IGNORE\s+(INTO\s+.+)", normalized, flags=re.IGNORECASE | re.DOTALL)
    if ignore_match:
        normalized = f"INSERT {ignore_match.group(1)} ON CONFLICT DO NOTHING"

    replace_match = re.match(
        r"INSERT\s+OR\s+REPLACE\s+INTO\s+(?P<table>[a-z_]+)\s*\((?P<columns>[^)]+)\)\s*(?P<values>VALUES\s*\(.+\))",
        normalized,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if replace_match:
        table = replace_match.group("table")
        primary_key = _REPLACE_PRIMARY_KEYS.get(table)
        if primary_key is None:
            raise ValueError(f"unsupported SQLite INSERT OR REPLACE table: {table}")
        columns = [column.strip() for column in replace_match.group("columns").split(",")]
        updates = [
            f"{column} = EXCLUDED.{column}"
            for column in columns
            if column != primary_key
        ]
        normalized = (
            f"INSERT INTO {table} ({', '.join(columns)}) {replace_match.group('values')} "
            f"ON CONFLICT ({primary_key}) DO UPDATE SET {', '.join(updates)}"
        )

    revision_increment_match = re.match(
        r"(?P<prefix>INSERT\s+INTO\s+(?P<table>[a-z_]+)\s*\([^)]*\)\s*VALUES\s*\([^)]*\)\s*"
        r"ON\s+CONFLICT\s*\([^)]*\)\s+DO\s+UPDATE\s+SET\s+revision\s*=\s*)revision\s*\+\s*1$",
        normalized,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if revision_increment_match and revision_increment_match.group("table").lower() in _REVISION_INCREMENT_TABLES:
        normalized = (
            f"{revision_increment_match.group('prefix')}"
            f"{revision_increment_match.group('table')}.revision + 1"
        )

    insert_table_match = re.match(r"INSERT\s+INTO\s+([a-z_]+)", normalized, flags=re.IGNORECASE)
    if insert_table_match:
        table_name = insert_table_match.group(1).lower()
        conflict_columns = _PROJECT_SCOPED_CONFLICT_TARGETS.get(table_name)
        if conflict_columns is not None:
            conflict_pattern = ",\\s*".join(conflict_columns)
            normalized = re.sub(
                rf"ON\s+CONFLICT\s*\(\s*{conflict_pattern}\s*\)",
                f"ON CONFLICT (project_id, {', '.join(conflict_columns)})",
                normalized,
                flags=re.IGNORECASE,
            )

    return normalized.replace("?", "%s")
