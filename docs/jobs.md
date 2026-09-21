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
configure these limits; its history bound must cover all admitted jobs. Terminal
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
