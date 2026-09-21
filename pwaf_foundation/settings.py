"""Load and atomically update extensible settings.

A process-local lock serializes updates. Snapshots expose recognized fields only;
unknown persisted fields survive writes but are never returned through the API.
"""

import json
import logging
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pwaf_foundation.errors import DomainError, FieldError

logger = logging.getLogger(__name__)


class FoundationSettings(BaseModel):
    """Editable defaults; applications may subclass with independent settings fields."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)
    theme: Literal["light", "dark"] = "light"
    app_name: str = Field(default="Python Web App", min_length=1, max_length=100)


SettingsT = TypeVar("SettingsT", bound=FoundationSettings)


class SettingsStore(Generic[SettingsT]):
    """Own a JSON settings file and publish validated copies after successful saves."""

    def __init__(self, path: Path, schema: type[SettingsT]) -> None:
        self.path, self.schema = path, schema
        self._lock = RLock()
        self._current = schema()
        self._unknown: dict = {}

    def load(self) -> SettingsT:
        """Load tolerant fields; preserve malformed whole files and fail visibly."""
        with self._lock:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                raw = {}
            except (json.JSONDecodeError, UnicodeError) as exc:
                raise RuntimeError(
                    "Settings file is invalid; restore or repair it before startup"
                ) from exc
            if not isinstance(raw, dict):
                raise RuntimeError("Settings file must contain a JSON object")
            known = {key: value for key, value in raw.items() if key in self.schema.model_fields}
            # Remove invalid fields in groups, allowing valid siblings to survive.
            while True:
                try:
                    candidate = self.schema.model_validate(known)
                    break
                except ValidationError as exc:
                    invalid = {e["loc"][0] for e in exc.errors() if e["loc"]}
                    removable = invalid.intersection(known)
                    if not removable:
                        raise RuntimeError("Settings schema cannot recover invalid fields") from exc
                    for key in removable:
                        logger.warning("Ignoring invalid settings field: %s", key)
                        known.pop(key)
            self._unknown = {k: v for k, v in raw.items() if k not in self.schema.model_fields}
            self._current = candidate
            return self.snapshot()

    def snapshot(self) -> SettingsT:
        """Return an isolated copy of the current recognized settings."""
        with self._lock:
            return self._current.model_copy(deep=True)

    def update(self, changes: dict) -> SettingsT:
        """Validate and atomically save a partial update before publishing it."""
        with self._lock:
            try:
                candidate = self.schema.model_validate(self._current.model_dump() | changes)
            except ValidationError as exc:
                raise DomainError(
                    "validation_error",
                    "One or more fields are invalid.",
                    422,
                    [
                        FieldError(field=".".join(map(str, e["loc"])), message="Invalid value.")
                        for e in exc.errors()
                    ],
                ) from exc
            document = deepcopy(self._unknown) | candidate.model_dump(mode="json")
            try:
                self._save(document)
            except OSError as exc:
                logger.error("Could not save settings", exc_info=exc)
                raise DomainError(
                    "settings_write_failed", "Settings could not be saved.", 500
                ) from exc
            self._current = candidate
            return self.snapshot()

    def _save(self, document: dict) -> None:
        # The caller holds the lock. Replacement is the final fallible write step.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, prefix=".settings-", delete=False
            ) as stream:
                temporary = Path(stream.name)
                json.dump(document, stream, indent=2, ensure_ascii=False, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
