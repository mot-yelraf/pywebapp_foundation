"""Run trusted child processes with bounded capture and incremental output.

The caller owns command construction and parsing. POSIX process groups are owned
and reaped; on Windows only the direct child is owned. No shell is invoked.
"""

import asyncio
import math
import os
import signal
import subprocess
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from pwaf_foundation.errors import DomainError


@dataclass(frozen=True)
class ProcessResult:
    """Completed output and a bounded tail of (stream name, bytes) chunks."""

    returncode: int
    stdout: str
    stderr: str
    tail: tuple[tuple[str, bytes], ...]


async def run_process(
    arguments: Sequence[str],
    *,
    output_limit: int = 65536,
    capture: bool = True,
    on_line: Callable[[str, str], None] | None = None,
    line_limit: int = 65536,
    tail_chunks: int = 20,
    timeout: float | None = None,
    terminate_grace: float = 2,
    accepted_exit_codes: tuple[int, ...] | None = (0,),
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    hide_window: bool = True,
) -> ProcessResult:
    """Stream/capture bounded output and clean up on completion, cancellation, or error.

    on_line receives (stdout|stderr, text) on the event loop and must not block.
    Limits count bytes across both streams, including when capture is disabled.
    env overlays the inherited environment. None accepts every exit code.
    """
    if isinstance(arguments, (str, bytes)) or not arguments or not arguments[0] or any(
        not isinstance(item, str) or "\0" in item for item in arguments
    ):
        raise ValueError("Arguments must be a nonempty sequence of strings")
    if output_limit < 1 or line_limit < 1 or tail_chunks < 0:
        raise ValueError("Output/line limits must be positive and tail size nonnegative")
    if not math.isfinite(terminate_grace) or terminate_grace < 0 or (
        timeout is not None and (not math.isfinite(timeout) or timeout <= 0)
    ):
        raise ValueError("Process deadlines must be finite and valid")
    spawn = asyncio.create_task(asyncio.create_subprocess_exec(
        *arguments, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        cwd=cwd, env=None if env is None else {**os.environ, **env},
        start_new_session=os.name == "posix",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" and hide_window else 0,
    ))
    process = None
    readers = []
    total = 0
    tail: deque[tuple[str, bytes]] = deque(maxlen=tail_chunks)

    async def read(stream: asyncio.StreamReader, name: str) -> str:
        nonlocal total
        chunks = []
        pending = b""
        while block := await stream.read(4096):
            total += len(block)
            if total > output_limit:
                raise DomainError("output_limit", "Tool output exceeded its limit.")
            tail.append((name, block))
            if capture:
                chunks.append(block)
            if on_line is not None:
                pending += block
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    if len(line) > line_limit:
                        raise DomainError("output_limit", "Tool output line exceeded its limit.")
                    on_line(name, line.rstrip(b"\r").decode("utf-8", errors="replace"))
                if len(pending) > line_limit:
                    raise DomainError("output_limit", "Tool output line exceeded its limit.")
        if pending and on_line is not None:
            on_line(name, pending.decode("utf-8", errors="replace"))
        return b"".join(chunks).decode("utf-8", errors="replace")

    async def collect() -> ProcessResult:
        readers.extend([
            asyncio.create_task(read(process.stdout, "stdout")),
            asyncio.create_task(read(process.stderr, "stderr")),
        ])
        stdout, stderr = await asyncio.gather(*readers)
        code = await process.wait()
        if accepted_exit_codes is not None and code not in accepted_exit_codes:
            raise DomainError("tool_failed", "The tool exited unsuccessfully.")
        return ProcessResult(code, stdout, stderr, tuple(tail))

    try:
        try:
            process = await asyncio.shield(spawn)
        except asyncio.CancelledError:
            process = await spawn
            raise
        try:
            return await asyncio.wait_for(collect(), timeout)
        except asyncio.TimeoutError as exc:
            raise DomainError("tool_timeout", "The tool exceeded its time limit.") from exc
    except OSError as exc:
        raise DomainError("tool_launch_failed", "The tool could not be started.") from exc
    finally:
        for reader in readers:
            reader.cancel()
        await asyncio.gather(*readers, return_exceptions=True)
        if process is not None:
            await _terminate(process, terminate_grace)


async def _terminate(process: asyncio.subprocess.Process, grace: float) -> None:
    async def discard(stream):
        while await stream.read(4096):
            pass

    def send(sig):
        try:
            if os.name == "posix":
                os.killpg(process.pid, sig)
            elif process.returncode is None:
                process.kill()
        except ProcessLookupError:
            pass

    drains = [asyncio.create_task(discard(stream)) for stream in (process.stdout, process.stderr)]
    try:
        if grace and process.returncode is None:
            send(signal.SIGTERM)
            try:
                await asyncio.wait_for(process.wait(), grace)
            except asyncio.TimeoutError:
                pass
        # Kill remaining POSIX descendants even if the leader has already exited.
        send(signal.SIGKILL if os.name == "posix" else signal.SIGTERM)
        await process.wait()
        await asyncio.gather(*drains)
    finally:
        for drain in drains:
            drain.cancel()
        await asyncio.gather(*drains, return_exceptions=True)
