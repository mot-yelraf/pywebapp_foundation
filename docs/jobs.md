# Job lifecycle and limits

Jobs are optional. Applications provide a `job_factory(database)` returning a map
of operation names to `JobDefinition` values. Each lifespan creates a fresh manager;
no job workers or routes are installed when the factory is absent.

## API

| Request | Behavior |
| --- | --- |
| `POST /api/jobs` | Validates a registered operation and parameters; returns 202 with a job record and `Location` status URL. |
| `GET /api/jobs/{id}` | Reads a record, including result or safe error; returns 404 if absent/expired. |
| `POST /api/jobs/{id}/cancel` | Requests cancellation; returns 202 while cleanup completes, or 409 if already terminal or saving. |

Submission JSON is `{"operation":"performance","parameters":{"iterations":100000}}`.
It requires an `Idempotency-Key` header of 1–128 characters in addition to the
standard Origin/CSRF protection. Input schemas reject invalid values before a task
is created. Only server-registered operations can run.

Matching validated input with the same operation/key returns the same job. Reusing
a key for different input returns 409. Keys are scoped to an operation and identity. Local and password-free LAN modes
use a shared workspace identity. In optional proxy-authenticated mode each user
has separate idempotency keys and can read/cancel only their own transient jobs.
Successful persisted history remains shared. Keys expire with their records and
are not durable.

## Capacity and transitions

The default manager allows one executing job, four waiting jobs, and up to 100 total
retained records. Capacity rejection returns 503. A programmatic `JobManager` can
configure these limits; `create_app` also accepts `job_concurrency=1`,
`job_queue_size=4`, `job_history_size=100`, and `job_snapshot_limit=65536`; its history bound must cover all admitted jobs. Terminal
records are evicted oldest-first when room is needed. Active records are never
evicted. There is no external queue and no multi-worker coordination.

Allowed transitions are queued → running → succeeded/failed/cancelled, plus
queued → cancelled. Repeated cancellation while cleanup is pending does not
interrupt cleanup a second time. Terminal records have a completion timestamp;
only success exposes a result. Reading a failed job itself returns HTTP 200 with
its `error.code`, `error.message`, and `error.details`.

Service progress is optional and monotonic between 0 and 1. The subprocess-based
example shows an indeterminate running indicator instead of guessing progress;
a successful job reaches 1. Timing values vary between runs. The input workload
and resulting SHA-256 checksum are deterministic.

## Timeout, cancellation, and persistence

Each definition has a positive timeout (30 seconds for the example). Timeout covers
execution; adapter cleanup completes before the job becomes terminal. A save callback
is a separate commit boundary: once it begins, cancellation returns 409 and graceful
shutdown waits for the save. Save callbacks must use bounded I/O. A save exception
produces a failed job with no success result.

`FunctionAdapter` runs blocking I/O in a thread. It signals cancellation through
`JobContext.stop`, and services check `context.checkpoint()` between bounded work
units. A timeout cannot forcibly kill Python thread code. An uncooperative service
can delay shutdown, so it must use a process adapter instead.

`SubprocessAdapter` starts a command without a shell, drains stdout/stderr
concurrently, and bounds their combined captured payload (64 KiB by default, plus
bounded operating-system/asyncio pipe buffers). It kills and reaps owned processes
on timeout, cancellation, and output overflow, including cancellation during spawn.
On POSIX it owns a new process group; supported commands must not detach from it.
On Windows it owns the direct child only; supported commands must not spawn further
processes. The example runs a single Python child on all platforms.

Graceful shutdown stops admission, cancels queued/running work, and waits for
adapter cleanup or an ongoing save. Abrupt OS termination cannot guarantee child
cleanup or a final in-memory status. Jobs never resume automatically after restart.

The example persists successful measurements in `performance_results`, independently
of the ephemeral job records. A browser tab remembers its last job ID to recover
from a page reload; a 404 clears that status and directs the user to saved history.
History uses bounded `offset`/`limit` pagination, newest first. Offset pages can move
if other jobs finish while browsing; Refresh reloads the current page.

## Integrating a real tool

See [the extension guide](extending.md) for both importable-function and executable
recipes. Keep business logic independent of HTTP, validate inputs before execution,
and keep executable selection server-controlled. Never interpret returned tool
text as HTML. Back up durable application data before changing installed schemas.

## Live snapshots and owner-scoped queries

Runners may call `context.publish({"observed": 0})` from the event loop or a worker
thread. This publishes a detached JSON object; it does not persist it. Snapshots
must fit `job_snapshot_limit` UTF-8 bytes (64 KiB by default), contain finite JSON
values, and exclude secrets. Invalid or oversized snapshots raise `ValueError`
without replacing the previous snapshot. The additive `snapshot` field in job
responses is `null` until publication and remains available with terminal records.

Use `manager.latest(owner=identity)` or
`manager.list_records(owner=identity, limit=10, offset=0)` instead of inspecting
mutable `records`. Queries return defensive copies, newest-first, scoped to the
explicit owner. Limit defaults to the configured history size and cannot exceed
it; `latest` returns `None` if absent. Application routes obtain the identity from
`request.state.identity`, never from an untrusted query parameter. No public job
listing endpoint or persistence table is added by the foundation.

## Finalization for every outcome

`JobDefinition.finalize` is an optional async callback receiving a defensive
`JobRecord` with terminal status, result/error, final snapshot, owner, and completion
time. It runs once per admitted job, including immediate/queued cancellation,
timeout, and a failed success-save callback. Applications own storage and schemas.
`record.owner` is available to the callback but is excluded from public JSON.

```python
import asyncio
from pydantic import BaseModel
from pwaf_foundation.jobs import JobDefinition

class Input(BaseModel):
    count: int = 3

def make_jobs(repository):
    async def run(parameters, context):
        context.publish({"observed": parameters["count"]})
        return {"count": parameters["count"]}

    async def finalize(record):
        # App-owned repository accepts (job_id, owner, terminal JSON document).
        await asyncio.to_thread(repository.save, record.id, record.owner, record.model_dump())

    return {"tool": JobDefinition(Input, run, finalize=finalize)}
```

The existing `save(job_id, result)` hook remains success-only and runs first.
Terminal status is published after finalization finishes; cancel returns 409 while
saving/finalizing, and shutdown waits. Until then a cancelled queued job with a
finalizer may still report `queued`. Admission capacity stays occupied through
finalization. Hooks must use bounded I/O; there are no automatic retries. A failing
finalizer logs the failure and publishes `failed`/`job_finalize_failed` without a
success result. Already committed writes are not rolled back by the manager.
A hard process kill can still prevent finalization; this is not a durable queue.

## Streamed subprocess tools

`pwaf_foundation.processes.run_process` is independent of jobs, so a CLI can use
the same runner. Commands are trusted argument lists, never shell strings:

```python
import asyncio
import sys
from pwaf_foundation.processes import run_process

async def main():
    result = await run_process(
        [sys.executable, "-u", "-c", "print('ready')"],
        on_line=lambda stream, text: print(stream, text),
        timeout=10, output_limit=65536, capture=False,
    )
    print(result.returncode)

asyncio.run(main())
```

`on_line(stream, text)` runs on the event loop and must not block. Streams are
`stdout` and `stderr`; ordering between them is unspecified. UTF-8 lines are
reassembled across chunks, with replacement for invalid bytes. `line_limit`
defaults to 64 KiB. Both streams share `output_limit`, even with capture disabled.
The result includes captured strings and a tail of up to `tail_chunks=20` labeled
byte chunks (each at most 4096 bytes). Set zero to disable the tail.

`env` overlays inherited environment variables; `cwd` controls the working directory.
Windows console suppression defaults on. `accepted_exit_codes=(0,)` rejects other
codes with `tool_failed`; `None` lets the application interpret all exit codes.
Launch, timeout, and overflow failures use safe `tool_launch_failed`, `tool_timeout`,
and `output_limit` errors. Callback failures propagate after child cleanup.

`terminate_grace=2` requests termination before escalating to kill. Pipes are
drained without retaining cleanup output, and owned children are reaped. POSIX
process-group and Windows direct-child limitations described above still apply.
The timeout starts after spawn and covers output collection and process exit;
cleanup may add the grace period. `SubprocessAdapter` delegates to this runner
while retaining its existing result shape and immediate-kill policy.
