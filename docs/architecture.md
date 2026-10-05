# Architecture and extension guide

## Composition and lifecycle

`app.app.create_app` is the application composition root. The reusable `pwaf_foundation`
package never imports `app`. The factory accepts a `RuntimeConfig`, a settings
schema, namespaced migrations, required readiness checks, and application routers.
Importing modules or creating the app does not create runtime files.

FastAPI lifespan loads settings, migrates SQLite, creates the process CSRF token,
and marks the runtime ready. Failure prevents startup. Shutdown clears readiness
and the token. Storage operations own short-lived files and connections; there
are no persistent connection pools. Optional jobs are cancelled and joined during
shutdown; already-started result saves finish before shutdown completes.

State wiring is under `app.state`: `config`, `settings`, `database`, `templates`,
`csrf_token`, `readiness_checks`, `started`, `ui`, `settings_panes`,
`settings_schema`, and optional `jobs`. Application services should accept
explicit dependencies; only route adapters should reach into request state.

Start the default server with `python -m app`. To customize composition, edit the
replaceable `app/app.py` and preserve the entrypoint's startup validation. A custom
entrypoint must use the same configuration for server binding and factory creation.
Running Uvicorn directly with different bind settings bypasses startup guarantees
and is not a supported deployment method.

## Add a settings field, table, route, and readiness check

The following is a complete factory example, using the current public interfaces.
It can live in another application module; replace the default composition with
its equivalent when adapting the scaffold.

```python
from fastapi import APIRouter, Request
from pydantic import Field

from app.app import create_app
from pwaf_foundation.config import RuntimeConfig
from pwaf_foundation.database import Migration
from pwaf_foundation.health import ReadinessCheck
from pwaf_foundation.settings import FoundationSettings


class ToolSettings(FoundationSettings):
    repetitions: int = Field(default=3, ge=1, le=100)


router = APIRouter()


@router.get("/api/results")
def results(request: Request) -> list[dict[str, str | float]]:
    # A synchronous handler keeps this blocking SQLite operation off the event loop.
    with request.app.state.database.transaction(read_only=True) as connection:
        rows = connection.execute(
            "SELECT recorded_at, duration FROM results ORDER BY recorded_at DESC LIMIT 50"
        ).fetchall()
    return [{"recorded_at": row[0], "duration": row[1]} for row in rows]


async def tool_ready() -> bool:
    # Perform a genuinely asynchronous, bounded probe here if the tool needs one.
    return True


def build_tool_app():
    return create_app(
        RuntimeConfig.from_env(),
        settings_schema=ToolSettings,
        routers=[router],
        migrations={
            "performance": [
                Migration(
                    1,
                    (
                        "CREATE TABLE results (recorded_at TEXT PRIMARY KEY, duration REAL NOT NULL)",
                    ),
                )
            ]
        },
        readiness_checks=[ReadinessCheck("tool", tool_ready, timeout=1)],
    )
```

The built-in settings GET/PATCH routes and their OpenAPI models automatically
include `repetitions`; PATCH still validates the full resulting settings object.
Every field must have a valid default. Keep field validation independent where
possible so invalid loaded fields can fall back individually. If model-wide
validation cannot identify invalid fields, startup fails explicitly instead of
silently resetting unrelated values. Use plain field names, not aliases, for the
settings persistence/API contract. Settings must not contain secrets.

Use `settings.snapshot()` to get an isolated current value and `settings.update`
to validate, save, and publish a partial update. Async callers must offload both
operations because a snapshot can wait for an in-progress save's lock. File writes
use a flushed/fsynced temporary file and atomic replacement. Serialization is
process-local: do not run multiple processes against the same settings file or
modify it externally while the application runs. Cross-process locking and full
power-loss guarantees for directory metadata are not provided.

Unknown persisted fields are kept privately and round-tripped. They are neither
editable nor exposed through the recognized settings API. Startup environment
configuration is separate from this schema; adding overlapping fields in a future
extension requires explicit environment precedence without saving overrides.

## SQLite ownership and migrations

`Database.transaction()` creates, commits or rolls back, and closes its own
connection. Do not retain the connection after the context or share it across
threads. SQL parameters must be bound; migration SQL is trusted source code.
Read-only operations should use `transaction(read_only=True)` to avoid creating
an accidentally deleted database. Lock waiting is bounded to two seconds.

Migrations in each namespace start at 1 and are contiguous. A transaction applies
all supplied pending migrations and version records together. Failed statements
roll back, including DDL. A database version newer than the supplied namespace's
migration list rejects startup. Existing unknown namespaces are preserved; omitting
one does not delete its tables. `foundation` is reserved. Do not edit an already
applied migration: append a new one. Statements must not control transactions,
use `executescript`, or run operations such as VACUUM that require separate
transaction handling.

Use `utc_timestamp(aware_datetime)` for sortable fixed-width UTC text. Services
own domain repositories and data schemas; there is no generic sensor table.

## Readiness and errors

Checks are asynchronous callables returning a boolean, each with a deadline.
They run concurrently, and false results, exceptions, or timeout return 503 with
safe per-service outcomes. Names are unique; `database` is reserved. A check must
not block the event loop or suppress cancellation. Thread-offloaded operations
need their own I/O deadline because cancelling an await does not stop a thread.
Database readiness uses a read-only probe with a bounded SQLite lock wait.

Services raise `DomainError(code, safe_message, status, details)` for expected
failures. Routes use shared handlers for domain errors, validation, HTTP errors,
and unexpected exceptions. Only messages explicitly designated safe may enter a
domain error; do not put raw tool output, submitted secrets, or database exception
text there. Unexpected exceptions are logged with traceback and return generic
500 responses. Sanitize secrets before raising/logging integration errors.

Local, password-free LAN, and optional authenticated proxy modes share the
settings/storage services. Host/origin/CSRF checks apply to application routers as well as built-in routes.
Readiness is a distinct documented response shape; API errors use the shared error
envelope. For custom routes, add response models and shared `ERROR_RESPONSES` from
`pwaf_foundation.errors` to keep OpenAPI accurate. Optional execution endpoints are described in [jobs.md](jobs.md). Optional authenticated LAN access is described in [deployment.md](deployment.md).
WebSocket support is not implemented.

## Dependency and verification notes

Runtime uses FastAPI, Uvicorn, Pydantic, and Jinja. No ORM or desktop libraries are
required. Framework support was checked against the
[FastAPI package metadata](https://pypi.org/project/fastapi/) and lifecycle wiring
follows the [FastAPI lifespan documentation](https://fastapi.tiangolo.com/advanced/events/).
Tests use `httpx2`, as required by the current
[Starlette TestClient documentation](https://www.starlette.io/testclient/).
AnyIO is constrained below 4.15 because Starlette 1.6's test client still imports a
newly deprecated alias; re-evaluate this constraint with framework upgrades while
keeping `-W error` tests enabled.

CI covers the supported Python minimum and a current Python on three OSes, builds
packages, runs strict tests, lint, and syntax checks. The local machine has verified
Python 3.13 on macOS ARM64 only. Bundled Chromium browser checks run locally and in CI; see README for tested
viewports and behavior. Native desktop startup/shutdown has been exercised on macOS. See
[verification.md](verification.md) for the other platform limitations.


## UI and example composition

`create_example_app` adds the performance routes, application settings/migrations,
UI overrides, and registered jobs. `python -m app` calls this composition; use the
generic `create_app` to start without the demonstration. See [extending.md](extending.md)
for working UI and tool adapter recipes. `python -m app.cli` calls the same benchmark
service directly without starting a server or accessing persistent storage.
