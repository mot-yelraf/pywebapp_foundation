"""Measure a bounded deterministic hashing workload.

CLI and web workers call the same function. The checksum is deterministic; elapsed
wall-clock time is a measurement and naturally varies between runs.
"""

import hashlib
import time
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field


class PerformanceInput(BaseModel):
    """Bounded workload settings shared by CLI and jobs."""

    model_config = ConfigDict(extra="forbid", strict=True)
    iterations: int = Field(default=100000, ge=1, le=5000000)


class PerformanceResult(BaseModel):
    """Identical result schema for CLI output and persisted web results."""

    iterations: int
    elapsed_ms: float
    checksum: str


def benchmark(
    parameters: PerformanceInput,
    checkpoint: Callable[[], None] = lambda: None,
    progress: Callable[[float], None] = lambda value: None,
) -> PerformanceResult:
    """Hash a fixed seed repeatedly, checking cancellation every bounded batch."""
    digest = b"pywebapp-foundation"
    started = time.perf_counter()
    for index in range(parameters.iterations):
        if index % 10000 == 0:
            checkpoint()
            progress(index / parameters.iterations)
        digest = hashlib.sha256(digest).digest()
    checkpoint()
    progress(1)
    return PerformanceResult(
        iterations=parameters.iterations,
        elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
        checksum=digest.hex(),
    )
