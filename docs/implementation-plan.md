# Foundation implementation plan

Status: phases 1–8 implemented locally on 2026-09-21. See
[verification.md](verification.md) for reproducible results and platform limits.

The delivered foundation includes runtime/services, responsive UI, jobs, a complete
CLI-to-web example, user-owned installers, optional pywebview, and LAN deployment.
Per the project owner's clarification, **LAN password authentication is off by
default**, with authenticated HTTPS proxy access opt-in. Local mode remains the
default process mode. This supersedes earlier plan assumptions that all LAN use
would require authentication.

Local verification includes the real native window, temporary install/reinstall,
source/wheel packaging, desktop/mobile browser checks, and an isolated adaptation
that changes application features while leaving foundation files unchanged. The
cross-platform CI matrix is configured; actual Windows/Linux/Raspberry Pi runtime
checks remain open environmental verification, not claims of completed native tests.

## Outcome

A developer can clone this repository, run a working browser application, and
replace the example business logic with an existing Python tool. The CLI and web
UI use the same services. Settings and results survive restarts, and the default
UI can be extended or replaced without editing foundation internals.

`AGENTS.md` defines implementation conventions. This plan defines delivery order
and acceptance criteria. Update both when implemented behavior replaces a target.

## Initial scope and decisions

- Browser-first FastAPI server, Jinja templates, plain CSS and JavaScript. No
  frontend build pipeline is required for the initial foundation.
- Reusable code lives in `pwaf_foundation/`; the replaceable example lives in `app/`.
  The application composes foundation services through `app.app.create_app`.
- Use standard-library SQLite, JSON, logging, and subprocess facilities. Keep
  pywebview optional and separate from browser runtime dependencies.
- Start with one server process. Settings updates and in-memory jobs are coordinated
  within that process; multi-worker deployment is outside the initial contract.
- Local use defaults to `127.0.0.1:8191`. Explicit LAN mode is password-free by
  default; an optional authenticated HTTPS proxy mode adds identity/operator checks.
- Job execution is initially in memory with bounded concurrency and queue size.
  Completed example results are persisted separately in SQLite. Active jobs do
  not resume after restart, and the UI must say so.
- Use a small, bounded performance demonstration with an importable service and
  CLI entrypoint. Avoid arbitrary browser-supplied executable names or commands.
- Defer external task queues, plugin discovery, multi-user administration, WebSocket
  streaming, and automatic update services until a concrete application needs them.

## Phase 1 — Runnable skeleton and development tooling (implemented)

Deliverables:

- Create the package layout in `AGENTS.md`, initial version, module docstrings,
  virtual-environment instructions, dependency files, and `pyproject.toml` for
  packaging/tool configuration. Derive package version from the canonical source.
- Add `python3 -m app`, the application factory, lifespan wiring, logging, a minimal
  landing page, and `/healthz` readiness without any required background worker.
- Implement startup parsing for the four documented `PWAF_*` variables. Reject
  invalid explicit values and resolve the data directory once.
- Add `.gitignore` for virtual environments, caches, runtime data, and local secrets.
- Establish pytest, Ruff, coverage reporting, and a CI test matrix covering the
  minimum supported Python plus a current supported Python on desktop/server OSes.
  Verify current dependency support before choosing version constraints.

Acceptance:

- A fresh virtual environment can install and start the application using README
  commands; `curl` confirms the landing page and readiness.
- Importing modules creates no files, database connections, or background workers.
- Startup failure and shutdown clean up resources. Initial tests and lint pass.

## Phase 2 — Settings and SQLite services (implemented)

Deliverables:

- Separate startup configuration from editable settings; environment overrides
  remain effective without being written back into persisted settings.
- Implement extensible settings schemas, field-level fallback on load, unknown
  field preservation, candidate validation, serialized updates, and atomic saves.
- Define live settings access through a settings service returning validated
  snapshots. Consumers retrieve current values rather than retaining stale copies.
- Provide explicit SQLite connection ownership, transactions, bounded busy waits,
  and ordered migrations tracked by namespace and version. Foundation and app
  migrations remain separate; incompatible or failed migrations stop startup.
- Establish UTC timestamp serialization and application-owned data repositories.

Acceptance:

- Missing, invalid, and unknown settings fields behave as documented. Malformed
  whole-file JSON is reported and preserved for recovery rather than overwritten.
- Failed saves leave disk and active settings unchanged; concurrent partial saves
  do not lose unrelated fields.
- Fresh and previously initialized databases migrate predictably; a failed
  transactional migration rolls back. Connections close under `-W error` tests.

## Phase 3 — API contracts and browser security (implemented)

Deliverables:

- Implement shared domain errors and API exception handlers, including validation,
  404/405 HTTP errors, and unexpected failures. Document response models in OpenAPI.
- Add settings read/update routes, safe partial-update responses, and readiness
  registration for application-required services with bounded check duration.
- Protect all browser mutation routes with CSRF validation. Validate allowed hosts
  and browser origins; do not enable wildcard CORS. Cover local unauthenticated
  mode as well as any later cookie-authenticated mode.
- Make deployment mode explicit. Later owner-approved LAN mode allows password-free
  execution; authenticated proxy mode always keeps the backend on loopback.

Acceptance:

- API failures use the documented envelope without exposing secret inputs,
  tracebacks, or internal paths. OpenAPI matches actual status codes and models.
- Missing/invalid CSRF tokens and disallowed browser origins cannot mutate state.
- Readiness works without optional jobs and returns 503 for a failed required
  service. GET endpoints have no mutation side effects.

## Phase 4 — Reusable responsive UI (implemented)

Deliverables:

- Inspect the sibling UI reference if available and record which visual conventions
  are adopted. Keep all required assets inside this repository.
- Create the base layout, navigation registration, button/form/dialog components,
  settings interface, and visible loading, success, empty, and error states.
- Define template blocks and macro signatures, application-first template lookup,
  and separate foundation/application static mounts.
- Support keyboard operation, focus restoration, mobile navigation, independent
  settings-pane saves, and cancel-time restoration of any theme preview.
- Add `scripts/playwright_verify.py` and run the same verification locally and in CI.

Acceptance:

- An application adds a page and navigation item without modifying foundation code.
- An application overrides the base layout and uses its own assets successfully.
- Playwright covers desktop/mobile layout, dialogs and focus, settings success and
  failure, and rendering zero values and escaped tool output.

## Phase 5 — Job execution and tool adapters (implemented)

Deliverables:

- Implement job states: queued, running, succeeded, failed, and cancelled, with
  explicit allowed transitions and stable identifiers.
- Expose POST `/api/jobs`, GET `/api/jobs/{job_id}`, and a documented cancellation
  action. Submission returns 202 and a status URL. Bound retained job records.
- Define duplicate-submission behavior using scoped idempotency keys; reuse with
  different input returns a conflict. Reject work when the bounded queue is full.
- Provide an importable-service adapter with cooperative cancellation and a
  subprocess adapter with argument lists, output limits, deadlines, and cleanup.
- Keep blocking I/O off the event loop. Execute CPU-heavy demonstration work in a
  process when necessary. Do not claim a running thread can be forcibly cancelled.
- Document shutdown behavior, timeouts, cancellation limitations, and restart loss.

Acceptance:

- Tests cover success, exceptions, timeout, cancellation races, duplicate requests,
  queue saturation, and shutdown without orphaned supported subprocesses.
- Subprocess output is bounded; nonzero exits produce safe errors. Browser input
  cannot select an arbitrary executable or inject shell syntax.
- Readiness and settings endpoints remain responsive during a running job.

## Phase 6 — Complete performance-tool example (implemented)

Deliverables:

- Add a deterministic, bounded example service, CLI command, and web page that
  submit work, display progress/status, cancel supported work, and show results.
- Persist completed example results in an app-owned table and show paginated
  history. Clearly distinguish saved results from ephemeral job status.
- Demonstrate one app-specific settings pane and migration.
- Write a walkthrough for integrating an existing importable CLI tool and a second
  recipe for wrapping an executable. Explain how to remove example features.

Acceptance:

- CLI and web use the same service and produce equivalent result structures.
- Results and settings survive restart; interrupted in-memory jobs are not shown
  as still running. Failed jobs never appear as successful empty results.
- A second tiny test application proves router, settings, migrations, navigation,
  and template extensions work without foundation importing example modules.

## Phase 7 — Desktop, installation, and optional authenticated LAN deployment (implemented)

Deliverables:

- Add an optional pywebview launcher with lazy imports, server-readiness waiting,
  clear startup failures, and coordinated window/server shutdown.
- Implement `install.sh` and `install.ps1` with explicit user-owned destinations,
  stable data paths, virtual environments, and repeatable launcher creation.
  Keep source/runtime replacement separate from persistent data.
- Document install, upgrade, backup, restore, and uninstall behavior; upgrades
  preserve settings, unknown fields, and existing databases.
- Support one documented authenticated reverse-proxy deployment for LAN use.
  Define the trusted proxy boundary, reject direct bypass, enforce authorization
  for execution, and document TLS and credential handling. This is an explicit
  integration contract, not a general identity-management subsystem.

Acceptance:

- Reinstall/upgrade tests preserve seeded settings and results, including when
  installation paths contain spaces. Installation failure does not delete data.
- Browser mode installs and runs without desktop dependencies.
- Desktop lifecycle is exercised on available platforms; actual Windows/Linux/macOS
  and Raspberry Pi checks are recorded separately from mocks and CI coverage.
- Remote tests reject missing/invalid credentials and forged proxy identity;
  authenticated authorized requests can execute work over the documented setup.

## Phase 8 — Release and clone-to-application verification (implemented)

Deliverables:

- Finish README and focused guides for architecture, extension APIs, settings,
  persistence, jobs, deployment, and troubleshooting. Link the guides from README.
- Audit documentation against code, remove stale scaffold status, and document
  platform limitations and dependency choices.
- Establish a measured coverage baseline and CI gate; retain explicit tests for
  critical failure paths rather than relying solely on aggregate coverage.
- Exercise a clean clone in a temporary location, replace the example service and
  branding, add a route/settings field/table, and verify no foundation edits are
  needed. Record exact commands and results.

Acceptance:

- Tests, strict warning checks, lint, syntax checks, and relevant Playwright checks
  pass. Installation smoke checks and endpoint checks are recorded.
- The clean-clone walkthrough is reproducible, and all documented commands exist.
- Supported-platform claims distinguish tested targets from unverified targets.

## Delivery checkpoints

1. After phases 1–3: tested local runtime with configuration, storage, and API rules.
2. After phases 4–6: usable local foundation with a complete CLI-to-web example.
3. After phases 7–8: distributable foundation with installers, optional desktop
   operation, documented remote access, and a verified extension walkthrough.

Implement in this order, completing each phase's acceptance checks before relying
on its interfaces. Keep changes reviewable and update this plan with actual
verification results. This plan does not authorize publishing, deployment, or
changes to external services.
