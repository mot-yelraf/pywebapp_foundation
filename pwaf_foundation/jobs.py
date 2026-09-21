"""Run bounded, ephemeral jobs with explicit lifecycle and idempotency.

The manager is owned by one event loop. Accepted tasks occupy a bounded number
of slots; only terminal records may be evicted. Adapters own cancellation cleanup.
"""

import asyncio
import hashlib
import json
import logging
import math
import threading
import uuid
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pwaf_foundation.database import utc_timestamp
from pwaf_foundation.errors import DomainError, ErrorBody, FieldError

logger = logging.getLogger(__name__)
TERMINAL = {"succeeded", "failed", "cancelled"}


class JobCancelled(Exception):
    """Signal cooperative cancellation from an importable synchronous service."""


@dataclass
class JobContext:
    """Cancellation and progress bridge shared with a cooperative service."""

    job_id: str
    stop: threading.Event = field(default_factory=threading.Event)
    progress: Callable[[float], None] = lambda value: None

    def checkpoint(self) -> None:
        """Raise when the service should stop; call between bounded work units."""
        if self.stop.is_set():
            raise JobCancelled()


class JobRecord(BaseModel):
    """Public job state; records are lost on restart or terminal-record eviction."""

    id: str
    operation: str
    owner: str = Field(default="local", exclude=True)
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"] = "queued"
    progress: float = 0
    created_at: str
    finished_at: str | None = None
    result: dict | None = None
    error: ErrorBody | None = None
    status_url: str


@dataclass(frozen=True)
class JobDefinition:
    """Trusted operation registration, input schema, runner, and optional result sink."""

    schema: type[BaseModel]
    run: Callable[[dict, JobContext], Awaitable[dict]]
    timeout: float = 30
    save: Callable[[str, dict], Awaitable[None]] | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("Job timeout must be finite and positive")


class JobSubmission(BaseModel):
    """Submit only a registered operation; arbitrary executable names are not accepted."""

    model_config = ConfigDict(extra="forbid", strict=True)
    operation: str = Field(min_length=1, max_length=100)
    parameters: dict = Field(default_factory=dict)


class JobManager:
    """Own a bounded task set and guarantee adapter cleanup before shutdown completes."""

    def __init__(
        self,
        definitions: dict[str, JobDefinition],
        *,
        concurrency: int = 1,
        queue_size: int = 4,
        history_size: int = 100,
    ) -> None:
        if concurrency < 1 or queue_size < 0 or history_size < concurrency + queue_size:
            raise ValueError("Invalid job capacity or history bound")
        self.definitions = dict(definitions)
        self.concurrency, self.queue_size, self.history_size = concurrency, queue_size, history_size
        self.records: OrderedDict[str, JobRecord] = OrderedDict()
        self._tasks: dict[str, asyncio.Task] = {}
        self._contexts: dict[str, JobContext] = {}
        self._keys: dict[tuple[str, str, str], tuple[str, str]] = {}
        self._committing: set[str] = set()
        self._semaphore = asyncio.Semaphore(concurrency)
        self.accepting = True

    def get(self, job_id: str, owner: str | None = None) -> JobRecord:
        """Read a defensive snapshot or report an expired/unknown identifier."""
        if job_id not in self.records or (
            owner is not None and self.records[job_id].owner != owner
        ):
            raise DomainError("job_not_found", "Job is unavailable or has expired.", 404)
        return self.records[job_id].model_copy(deep=True)

    def submit(self, operation: str, parameters: dict, key: str, owner: str = "local") -> JobRecord:
        """Validate and enqueue, reusing matching operation-scoped idempotency keys."""
        if not self.accepting:
            raise DomainError("jobs_stopping", "Job service is stopping.", 503)
        if operation not in self.definitions:
            raise DomainError("unknown_operation", "Operation is not registered.", 422)
        if not key or len(key) > 128:
            raise DomainError(
                "invalid_key", "An idempotency key of 1–128 characters is required.", 422
            )
        definition = self.definitions[operation]
        try:
            payload = definition.schema.model_validate(parameters).model_dump(mode="json")
        except ValidationError as exc:
            raise DomainError(
                "validation_error",
                "One or more fields are invalid.",
                422,
                [
                    FieldError(field=".".join(map(str, error["loc"])), message="Invalid value.")
                    for error in exc.errors()
                ],
            ) from exc
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()
        scoped = (owner, operation, key)
        if scoped in self._keys:
            previous_id, previous_fingerprint = self._keys[scoped]
            if fingerprint != previous_fingerprint:
                raise DomainError(
                    "idempotency_conflict", "This key was used with different input.", 409
                )
            return self.get(previous_id)
        active = sum(record.status not in TERMINAL for record in self.records.values())
        if active >= self.concurrency + self.queue_size:
            raise DomainError("queue_full", "Job capacity is full. Try again later.", 503)
        while len(self.records) >= self.history_size:
            expired = next(
                job_id for job_id, record in self.records.items() if record.status in TERMINAL
            )
            del self.records[expired]
            self._keys = {k: v for k, v in self._keys.items() if v[0] != expired}
        job_id = uuid.uuid4().hex
        record = JobRecord(
            id=job_id,
            operation=operation,
            owner=owner,
            created_at=utc_timestamp(datetime.now(timezone.utc)),
            status_url=f"/api/jobs/{job_id}",
        )
        self.records[job_id] = record
        self._keys[scoped] = (job_id, fingerprint)
        loop = asyncio.get_running_loop()

        def set_progress(value: float) -> None:
            if record.status == "running" and math.isfinite(value):
                record.progress = max(record.progress, min(0.99, max(0, value)))

        context = JobContext(
            job_id, progress=lambda value: loop.call_soon_threadsafe(set_progress, value)
        )
        self._contexts[job_id] = context
        task = loop.create_task(
            self._execute(record, definition, payload, context), name=f"job-{job_id}"
        )
        self._tasks[job_id] = task
        task.add_done_callback(lambda done: self._forget(job_id))
        return self.get(job_id)

    def _forget(self, job_id: str) -> None:
        self._tasks.pop(job_id, None)
        self._contexts.pop(job_id, None)

    async def _execute(
        self, record: JobRecord, definition: JobDefinition, payload: dict, context: JobContext
    ) -> None:
        try:
            async with self._semaphore:
                record.status = "running"
                result = await asyncio.wait_for(
                    definition.run(payload, context), definition.timeout
                )
                # Commit is a cancellation boundary: once begun, save and success finish together.
                self._committing.add(record.id)
                if definition.save is not None:
                    await definition.save(record.id, result)
                record.result = result
                record.progress = 1
                record.status = "succeeded"
        except (asyncio.CancelledError, JobCancelled):
            record.status = "cancelled"
        except asyncio.TimeoutError:
            record.status = "failed"
            record.error = ErrorBody(
                code="job_timeout", message="The operation exceeded its time limit."
            )
        except DomainError as exc:
            record.status = "failed"
            record.error = ErrorBody(code=exc.code, message=exc.message, details=exc.details)
        except Exception:
            logger.exception("Job %s failed", record.id)
            record.status = "failed"
            record.error = ErrorBody(code="job_failed", message="The operation failed.")
        finally:
            self._committing.discard(record.id)
            record.finished_at = utc_timestamp(datetime.now(timezone.utc))

    def cancel(self, job_id: str, owner: str | None = None) -> JobRecord:
        """Request cancellation; completed or committing jobs cannot be cancelled."""
        record = self.get(job_id, owner)
        if record.status in TERMINAL or job_id in self._committing:
            raise DomainError(
                "job_not_cancellable", "The job has completed or is saving its result.", 409
            )
        context = self._contexts[job_id]
        if not context.stop.is_set():
            context.stop.set()
            self._tasks[job_id].cancel()
        if record.status == "queued":
            self.records[job_id].status = "cancelled"
            self.records[job_id].finished_at = utc_timestamp(datetime.now(timezone.utc))
        return self.get(job_id)

    async def close(self) -> None:
        """Stop accepting work, cancel execution, and await cleanup or an ongoing save."""
        self.accepting = False
        for job_id in list(self._tasks):
            record = self.records.get(job_id)
            if (
                record is not None
                and record.status not in TERMINAL
                and job_id not in self._committing
            ):
                self.cancel(job_id)
        await asyncio.gather(*list(self._tasks.values()), return_exceptions=True)
