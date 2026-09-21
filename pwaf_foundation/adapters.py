"""Adapt trusted Python services and executable commands to asynchronous jobs.

Threads require cooperative checkpoints. Subprocesses use bounded pipes and are
reaped on cancellation; POSIX descendants in the created process group are killed.
"""

import asyncio
import os
import signal
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from pwaf_foundation.errors import DomainError
from pwaf_foundation.jobs import JobContext


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
        arguments = tuple(self.command(parameters))
        if not arguments or any(not isinstance(item, str) for item in arguments):
            raise ValueError("Command builder must return a nonempty argument list")
        context.checkpoint()
        spawn = asyncio.create_task(
            asyncio.create_subprocess_exec(
                *arguments,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd,
                start_new_session=os.name == "posix",
            )
        )
        try:
            process = await asyncio.shield(spawn)
        except asyncio.CancelledError:
            process = await spawn
            await _terminate(process)
            raise
        captured = 0

        async def read(stream: asyncio.StreamReader) -> str:
            nonlocal captured
            chunks = []
            while block := await stream.read(4096):
                captured += len(block)
                if captured > self.output_limit:
                    raise DomainError("output_limit", "Tool output exceeded its limit.")
                chunks.append(block)
            return b"".join(chunks).decode("utf-8", errors="replace")

        readers = [
            asyncio.create_task(read(process.stdout)),
            asyncio.create_task(read(process.stderr)),
        ]
        try:
            stdout, stderr = await asyncio.gather(*readers)
            code = await process.wait()
            if code != 0:
                raise DomainError("tool_failed", "The tool exited unsuccessfully.")
            return {"stdout": stdout, "stderr": stderr, "returncode": code}
        finally:
            for reader in readers:
                reader.cancel()
            await asyncio.gather(*readers, return_exceptions=True)
            await _terminate(process)


async def _terminate(process: asyncio.subprocess.Process) -> None:
    # Also kill descendants holding inherited pipes after the leader exits.
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        elif process.returncode is None:
            process.kill()
    except ProcessLookupError:
        pass
    # Drain bounded pipe/transport buffers after killing writers before waiting.
    await asyncio.gather(process.stdout.read(), process.stderr.read())
    await process.wait()
