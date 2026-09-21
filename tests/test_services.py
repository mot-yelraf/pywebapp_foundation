"""Verify configuration, settings durability, and SQLite lifecycle contracts.

All storage is isolated under pytest temporary directories.
"""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import Field

from pwaf_foundation.config import RuntimeConfig
from pwaf_foundation.database import Database, Migration, utc_timestamp
from pwaf_foundation.errors import DomainError
from pwaf_foundation.settings import FoundationSettings, SettingsStore


class ExampleSettings(FoundationSettings):
    """Independent example fields exercise reusable settings extensions."""

    count: int = Field(default=1, ge=0)
    label: str = "default"


def test_environment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = RuntimeConfig.from_env({})
    assert config.data_dir == tmp_path / "data"
    assert not config.data_dir.exists()
    assert (config.host, config.port, config.log_level) == ("127.0.0.1", 8191, "INFO")
    configured = RuntimeConfig.from_env(
        {
            "PWAF_HTTP_HOST": "::1",
            "PWAF_HTTP_PORT": "80",
            "PWAF_LOG_LEVEL": "DEBUG",
            "PWAF_DATA_DIR": "other",
        }
    )
    assert "http://[::1]" in configured.origins
    assert configured.data_dir == tmp_path / "other"


@pytest.mark.parametrize(
    "env",
    [
        {"PWAF_HTTP_PORT": "bad"},
        {"PWAF_HTTP_PORT": "0"},
        {"PWAF_HTTP_PORT": "65536"},
        {"PWAF_HTTP_HOST": "0.0.0.0"},
        {"PWAF_HTTP_HOST": "evil.example"},
        {"PWAF_DATA_DIR": " "},
        {"PWAF_LOG_LEVEL": "verbose"},
    ],
)
def test_invalid_environment(env):
    with pytest.raises(ValueError):
        RuntimeConfig.from_env(env)


def test_settings_recover_fields_and_preserve_unknown(tmp_path, caplog):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"count": -1, "label": "retained", "future": {"x": 2}}))
    store = SettingsStore(path, ExampleSettings)
    assert store.load().count == 1
    assert store.snapshot().label == "retained"
    assert "count" in caplog.text
    store.update({"count": 0})
    assert json.loads(path.read_text())["future"] == {"x": 2}
    assert "future" not in store.snapshot().model_dump()
    assert SettingsStore(path, ExampleSettings).load().count == 0
    before = path.read_bytes()
    for update in ({"count": "3"}, {"future": 4}, {"label": None}):
        with pytest.raises(DomainError) as caught:
            store.update(update)
        assert caught.value.status == 422
    assert path.read_bytes() == before


@pytest.mark.parametrize("contents", ["{broken", "[]", "null"])
def test_corrupt_settings_preserved(tmp_path, contents):
    path = tmp_path / "settings.json"
    path.write_text(contents)
    with pytest.raises(RuntimeError):
        SettingsStore(path, ExampleSettings).load()
    assert path.read_text() == contents


def test_atomic_save_failure(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    store = SettingsStore(path, ExampleSettings)
    assert store.load().count == 1
    store.update({"count": 2})
    original = path.read_bytes()

    def fail(*args):
        raise OSError("injected replacement failure")

    monkeypatch.setattr("pwaf_foundation.settings.os.replace", fail)
    with pytest.raises(DomainError):
        store.update({"count": 3})
    assert store.snapshot().count == 2
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_concurrent_partial_writes(tmp_path):
    store = SettingsStore(tmp_path / "settings.json", ExampleSettings)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(store.update, {"count": 8}),
            executor.submit(store.update, {"label": "updated"}),
        ]
        for future in futures:
            future.result()
    loaded = SettingsStore(store.path, ExampleSettings).load()
    assert (loaded.count, loaded.label) == (8, "updated")


def test_migration_upgrade_and_rollback(tmp_path):
    database = Database(tmp_path / "app.sqlite3")
    first = Migration(1, ("CREATE TABLE results (value INTEGER NOT NULL)",))
    database.migrate({"example": [first]})
    with database.transaction() as connection:
        connection.execute("INSERT INTO results VALUES (?)", (7,))
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
    database.migrate({"example": [first]})
    with pytest.raises(sqlite3.OperationalError):
        database.migrate(
            {
                "example": [
                    first,
                    Migration(
                        2,
                        (
                            "ALTER TABLE results ADD COLUMN label TEXT",
                            "INVALID SQL",
                        ),
                    ),
                ]
            }
        )
    with database.transaction() as connection:
        assert connection.execute("SELECT * FROM results").fetchall() == [(7,)]
        assert connection.execute(
            "SELECT version FROM foundation_schema_versions WHERE namespace='example'"
        ).fetchone() == (1,)
    database.migrate(
        {"example": [first, Migration(2, ("ALTER TABLE results ADD COLUMN label TEXT",))]}
    )
    with pytest.raises(RuntimeError):
        database.migrate({"example": [first]})
    with pytest.raises(ValueError):
        database.migrate({"other": [Migration(2, ())]})
    assert database.ready()
    with pytest.raises(RuntimeError), database.transaction() as connection:
        connection.execute("DELETE FROM results")
        raise RuntimeError("rollback")
    with database.transaction() as connection:
        assert connection.execute("SELECT value FROM results").fetchone() == (7,)


def test_utc_timestamps():
    instant = datetime(2026, 9, 21, 12, tzinfo=timezone(timedelta(hours=2)))
    assert utc_timestamp(instant) == "2026-09-21T10:00:00.000000Z"
    with pytest.raises(ValueError):
        utc_timestamp(datetime(2026, 9, 21))


def test_readiness_does_not_recreate_deleted_database(tmp_path):
    database = Database(tmp_path / "missing.sqlite3")
    with pytest.raises(sqlite3.OperationalError):
        database.ready()
    assert not database.path.exists()
