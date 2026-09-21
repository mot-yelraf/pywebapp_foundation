"""Application-owned performance schema migrations.

Append versions instead of rewriting migrations that may already be installed.
"""

from pwaf_foundation.database import Migration

PERFORMANCE_MIGRATIONS = (
    Migration(
        1,
        (
            "CREATE TABLE performance_results ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT UNIQUE NOT NULL, "
            "recorded_at TEXT NOT NULL, iterations INTEGER NOT NULL, "
            "elapsed_ms REAL NOT NULL, checksum TEXT NOT NULL)",
        ),
    ),
)
