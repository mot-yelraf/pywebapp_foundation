"""Persist completed performance results and return bounded history pages.

Only successful measurements are written. Job identifiers connect durable results
to ephemeral job records without requiring those records to survive restart.
"""

from datetime import datetime, timezone

from pydantic import BaseModel

from app.services.performance import PerformanceResult
from pwaf_foundation.database import Database, utc_timestamp


class SavedResult(PerformanceResult):
    """A successful measurement and its persistence metadata."""

    id: int
    job_id: str
    recorded_at: str


class HistoryPage(BaseModel):
    """Offset-paginated result history with an explicit total."""

    items: list[SavedResult]
    total: int
    offset: int
    limit: int


class ResultRepository:
    """Application data access, independent of HTTP and templates."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def save(self, job_id: str, result: dict) -> None:
        """Validate and persist one successful job result in a transaction."""
        validated = PerformanceResult.model_validate(result)
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO performance_results "
                "(job_id, recorded_at, iterations, elapsed_ms, checksum) VALUES (?, ?, ?, ?, ?)",
                (
                    job_id,
                    utc_timestamp(datetime.now(timezone.utc)),
                    validated.iterations,
                    validated.elapsed_ms,
                    validated.checksum,
                ),
            )

    def history(self, offset: int = 0, limit: int = 10) -> HistoryPage:
        """Read a bounded page and count from the same database snapshot."""
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("Invalid history window")
        with self.database.transaction(read_only=True) as connection:
            total = connection.execute("SELECT COUNT(*) FROM performance_results").fetchone()[0]
            rows = connection.execute(
                "SELECT id, job_id, recorded_at, iterations, elapsed_ms, checksum "
                "FROM performance_results ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return HistoryPage(
            items=[
                SavedResult(
                    **dict(
                        zip(
                            ("id", "job_id", "recorded_at", "iterations", "elapsed_ms", "checksum"),
                            row,
                            strict=True,
                        )
                    )
                )
                for row in rows
            ],
            total=total,
            offset=offset,
            limit=limit,
        )
