from __future__ import annotations

import re


_REPLACE_PRIMARY_KEYS = {
    "media_analysis_profiles": "analysis_id",
    "media_scene_windows": "scene_window_id",
    "media_embeddings": "embedding_id",
    "projects": "project_id",
    "provider_trace_failed_runs": "job_id",
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

    return normalized.replace("?", "%s")
