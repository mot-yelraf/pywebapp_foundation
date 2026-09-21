"""Evaluate required services with bounded asynchronous readiness checks.

Checks are explicitly registered coroutine functions and must not block the event
loop. A timed-out check is cancelled; cancellation must not be suppressed.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReadinessCheck:
    """A named required service probe and its deadline in seconds."""

    name: str
    probe: Callable[[], Awaitable[bool]]
    timeout: float = 1.0

    def __post_init__(self) -> None:
        if not self.name or not 0 < self.timeout <= 30:
            raise ValueError("Readiness checks require a name and a timeout in (0, 30]")


class HealthResponse(BaseModel):
    """Public readiness with safe per-service outcomes."""

    status: str
    checks: dict[str, bool]


async def evaluate_checks(checks: tuple[ReadinessCheck, ...]) -> HealthResponse:
    """Run checks concurrently; service exceptions become visible failed readiness."""

    async def evaluate(check: ReadinessCheck) -> tuple[str, bool]:
        try:
            result = await asyncio.wait_for(check.probe(), timeout=check.timeout)
            return check.name, result is True
        except Exception:
            logger.warning("Readiness check failed: %s", check.name, exc_info=True)
            return check.name, False

    results = dict(await asyncio.gather(*(evaluate(check) for check in checks)))
    return HealthResponse(status="ready" if all(results.values()) else "not_ready", checks=results)
