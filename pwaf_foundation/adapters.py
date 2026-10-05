"""Adapt trusted Python services and executable commands to asynchronous jobs.

Threads require cooperative checkpoints. Subprocesses use bounded pipes and are
reaped on cancellation; POSIX descendants in the created process group are killed.
"""

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from pwaf_foundation.jobs import JobContext
from pwaf_foundation.processes import run_process


@dataclass(frozen=True)
class FunctionAdapter:
    """Offload a cooperative I/O service; use subprocesses for CPU-heavy workloads."""

    function: Callable[[dict, JobContext], dict]

    async def __call__(self, parameters: dict, context: JobContext) -> dict:
        work = asyncio.create_task(asyncio.to_thread(self.function, parameters, context))
        try:
            return await asyncio.shield(work)
        except asyncio.CancelledError:
            context.stop.set()
            await asyncio.gather(work, return_exceptions=True)
            raise


@dataclass(frozen=True)
class SubprocessAdapter:
    """Run a source-controlled command builder, never a browser-selected command.

    On Windows this adapter owns only the direct child: supported tools must not
    spawn descendants. POSIX tools must not detach from their owned process group.
    """

    command: Callable[[dict], Sequence[str]]
    output_limit: int = 65536
    cwd: str | None = None

    def __post_init__(self) -> None:
        if self.output_limit < 1:
            raise ValueError("Output limit must be positive")

    async def __call__(self, parameters: dict, context: JobContext) -> dict:
        context.checkpoint()
        result = await run_process(
            self.command(parameters), output_limit=self.output_limit,
            cwd=self.cwd, terminate_grace=0,
        )
        return {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
