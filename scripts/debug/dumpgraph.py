"""Print the actual filter graph the renderer builds for this project."""
import sqlite3
import sys
from pathlib import Path

sys.path[:0] = [
    "/app/packages/core-engine/src",
    "/app/packages/storage-abstractions/src",
    "/app/packages/timeline-schema/src",
    "/app/packages/domain-models/src",
]

DB = "file:/videobox-data/projects/project-318cc020/db/project.sqlite?mode=ro"
connection = sqlite3.connect(DB, uri=True)
tables = [r[0] for r in connection.execute("select name from sqlite_master where type='table'")]
print("TABLES:", tables)
for table in tables:
    if "timeline" in table or "session" in table:
        rows = list(connection.execute(f"select * from {table} limit 3"))
        cols = [d[0] for d in connection.execute(f"select * from {table} limit 1").description]
        print(f"\n== {table} cols={cols} rows={len(rows)}")
        for row in rows:
            print("   ", str(row)[:300])
