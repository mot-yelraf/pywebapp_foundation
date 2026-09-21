"""Manage SQLite connections and ordered migrations.

Each transaction owns its connection; migrations use statements rather than
executescript so SQLite DDL remains inside the explicit transaction.
"""

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class Migration:
    """A contiguous version and its SQL statements within an application namespace."""

    version: int
    statements: tuple[str, ...]


class Database:
    """Open short-lived connections and commit or roll back explicit transactions."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def transaction(self, *, read_only: bool = False) -> Iterator[sqlite3.Connection]:
        """Yield a connection owned by this context, with bounded lock waiting."""
        target = self.path.resolve().as_uri() + "?mode=ro" if read_only else self.path
        connection = sqlite3.connect(target, timeout=2, isolation_level=None, uri=read_only)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self, migrations: dict[str, Sequence[Migration]]) -> None:
        """Apply contiguous migrations atomically; reject incompatible database versions."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS foundation_schema_versions "
                "(namespace TEXT PRIMARY KEY, version INTEGER NOT NULL)"
            )
            for namespace, steps in migrations.items():
                if not namespace or [m.version for m in steps] != list(range(1, len(steps) + 1)):
                    raise ValueError("Migration versions must be contiguous and start at 1")
                row = connection.execute(
                    "SELECT version FROM foundation_schema_versions WHERE namespace = ?",
                    (namespace,),
                ).fetchone()
                current = row[0] if row else 0
                if current < 0 or current > len(steps):
                    raise RuntimeError("Database schema is incompatible with this application")
                for step in steps[current:]:
                    for statement in step.statements:
                        connection.execute(statement)
                    connection.execute(
                        "INSERT INTO foundation_schema_versions(namespace, version) VALUES (?, ?) "
                        "ON CONFLICT(namespace) DO UPDATE SET version = excluded.version",
                        (namespace, step.version),
                    )

    def ready(self) -> bool:
        """Probe the initialized schema through a short-lived connection."""
        with self.transaction(read_only=True) as connection:
            connection.execute("SELECT version FROM foundation_schema_versions LIMIT 1").fetchall()
        return True


def utc_timestamp(value: datetime) -> str:
    """Serialize an aware datetime as fixed-width UTC ISO text with microseconds."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must have an explicit timezone")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
