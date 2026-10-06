# AGENTS.md

Operational instructions for coding agents working in this repository.
This file defines project conventions for a reusable Python web-app foundation
that users can clone and extend with their own application logic.

## Scope and Project Status

- Applies to the entire repository unless a deeper `AGENTS.md` overrides a subtree.
- Prefer repo-local guidance over generic coding-agent defaults.
- Confirm the target repository before editing when switching repositories.
- Do not overwrite or revert user changes you did not make unless explicitly asked.
- Phases 1–8 are implemented. See README and the linked architecture, extension,
  jobs, installation, and deployment guides for current interfaces. Native platform
  verification is recorded separately in `docs/verification.md`; do not equate a
  configured CI matrix with successful runs on unavailable machines.
- LAN password authentication is optional and off by default. Keep local mode as
  the default process mode; explicit LAN mode supports password-free access, with
  authenticated HTTPS proxy access selectable through startup configuration.
- Missing implementation files are expected during initial scaffolding. If files
  referenced by an established implementation are unexpectedly missing, report
  the incomplete workspace and ask for their location before recreating them.

## Project Context

- Build a lightweight FastAPI foundation for adding a web UI to Python tools,
  including existing command-line applications.
- Target Python 3.10 or newer on Raspberry Pi, macOS, Windows 10/11, and Linux.
- The browser UI must run independently, including on headless installations.
  pywebview as the desktop launcher and supports browser operation must not
  require desktop libraries or a graphical session.
- Supply responsive, accessible defaults for navigation, dialogs, buttons,
  settings, and page layout. Derived applications may extend or replace the UI.
- Use SQLite for persisted application data and JSON for runtime settings.
- The UI in `~/Projects/pywebview_foundation` is a design reference when available,
  not a runtime dependency. Do not assume that directory exists on other machines.
- Provide idempotent installation utilities for supported platforms that create
  a user-owned runtime and virtual environment while preserving installed data.

## Foundation and Application Boundaries

- The foundation owns startup and shutdown, settings infrastructure, SQLite
  connection management, logging, shared UI components, and optional task support.
- The derived application owns business logic, routes, settings fields, data
  schemas, pages, and integrations with tools or hardware.
- Foundation modules must not import derived-application modules. The application
  composes the foundation through explicit functions and documented interfaces.
- Keep business logic independent of FastAPI, Jinja, and pywebview so the CLI and
  web interface can call the same Python services.
- Prefer small extension points for routers, settings, migrations, templates,
  navigation, and lifecycle services. Do not build a plugin discovery framework
  unless a concrete application requires one.
- `create_app` owns dependency wiring and application state. Manage resources
  through FastAPI lifespan; avoid import-time database access or worker startup.
- Optional background services must not become prerequisites for every app.

## Building a Derived Application with an AI Agent

Use this workflow when a user clones PWAF to build a new application. The README's
PingTest walkthrough and `docs/pingtest.md` are an example brief, not instructions
to add ping functionality to the shared foundation itself.

1. **Confirm the workspace and brief.** Read this file and any deeper instructions,
   inspect Git status/remotes and the existing application, and verify you are in
   the derived project's directory. Do not modify the source foundation checkout
   or another project's installation. Identify the desired app name, target OSes,
   existing CLI/service, inputs/results, persistence, and required UI features.
   Ask only for missing decisions that block useful work.
2. **Establish a baseline.** Use a project-local virtual environment. Run relevant
   existing tests before changes and distinguish pre-existing failures from new
   ones. A Git clone contains committed files only; do not claim uncommitted work
   or ignored runtime data was cloned. Never copy another installation's settings,
   credentials, database, or virtual environment into the new app by default.
3. **Map identity explicitly.** Track the folder/repository name, distribution name
   in `pyproject.toml`, settings `app_name` default, application title, native window
   title, page/navigation text, manifest identity, icons, README, and installer-facing
   branding. Preserve the `app` module entrypoints unless the task requires renaming
   and all launchers/tests/packaging are updated together. Keep `pwaf_foundation`'s
   package name and reusable contracts intact. Do not overwrite existing saved
   names or settings just to change a default. Follow the versioning rule below.
4. **Plan around the application boundary.** Describe the service/CLI, validated
   inputs/results, job adapter, application migrations/repositories, API routes,
   pages, and tests. Follow an explicitly requested plan-review checkpoint; once
   implementation is authorized, carry the plan through verification. Prefer
   application extension points over changes to shared infrastructure. If a shared
   extension is necessary, explain it and keep it independent of the app's domain.
5. **Build a working path incrementally.** Start with the tool service and CLI,
   then jobs/cancellation, persistence, and presentation. Replace or disconnect the
   performance demo only as the new path becomes functional. Preserve reusable
   settings, security, lifecycle, and persistence behavior; update example-specific
   tests and verification scripts to exercise the derived application.
6. **Make optional components an app decision.** Enable Graphum only when requested
   by the app brief. The app defines metric IDs, labels, units, available selections,
   sampling, null/loss semantics, and data access; supply these via `PWAF.graph`.
   Do not embed ping, weather, or other domain metrics in `pwaf_foundation/`.
7. **Verify the deliverable.** Use deterministic tool-output fixtures for routine
   tests, then bounded real checks on the supported host. Verify CLI/web agreement,
   failures, timeout/cancellation cleanup, SQLite reloads, relevant mobile/desktop UI,
   and installed-package startup independently of source imports. Never equate
   mocked cross-platform tests with successful native runs on those platforms.
8. **Leave the derived project maintainable.** Update its README and AGENTS.md with
   actual names, commands, configuration, schema, and domain conventions. Report
   changes, verification, and remaining limitations. Keep the foundation remote as
   `upstream` when requested; do not push to it, create external repositories, or
   publish the app without authorization. Foundation updates require deliberate
   review/merge and retesting, not replacement of the derived app directory.

## Personalization Brief and Completion Checklist

- Read the clone's `APP_BRIEF.md` before implementing a derived app and use
  [the personalization guide](docs/personalizing.md) to map requirements to files.
  The brief is a product specification, not executable configuration. Honor the
  user's current instructions when they revise it. Unfilled placeholders are
  undecided; record assumptions and resolve blocking choices without repeatedly
  asking about decisions already made.
- Maintain its implementation record: agreed requirements, assumptions, foundation
  starting revision, customization locations, actual verification, and limitations.
  Do not insert credentials or private runtime data into it.
- Personalization is complete only when the selected identity, icon/theme, product
  text, landing/navigation, optional features, settings, data, and launch choices
  are implemented and checked. Mark items not required by the brief explicitly;
  do not claim every template field is automatically supported.
- Prefer app-owned templates and CSS for branding. Preserve shared JavaScript IDs,
  accessibility behavior, and theme contrast. Same-name `base.html` overrides must
  not recursively extend themselves. Update package-data rules for new asset types.
- Replace example composition in both browser and desktop entrypoints and update
  the CLI and example-specific test scripts. Keep framework regression coverage;
  do not delete old persisted tables or user settings merely to remove demo UI.
- Set a distinct, stable application ID in `app/identity.json` before installing a clone.
  Never reuse another product’s ID or adopt its legacy installation.
- Keep each app's installation, runtime data, and simultaneous-listening port
  separate. Check inherited environment overrides when validating installed apps.
  Changes to defaults must not rewrite existing preferences or select another
  app's server/data. Desktop installs create per-user native app bundles/menu entries/shortcuts
  by default; `--no-shortcuts` / `-NoShortcuts` skips them. Browser-only installs
  skip them. Services and autostart still require explicit application requirements.
- Audit distribution metadata, support links, attribution, licensing decisions,
  and release notes without inventing ownership or permissions. Preserve inherited
  notices. Document unresolved release decisions rather than silently choosing them.
- Finish with clean-install and saved-data upgrade checks, source-independent package
  startup, and relevant desktop/mobile verification. Keep app-specific README and
  AGENTS instructions accurate. Document how to review upstream updates; never
  reset or replace the derived project to apply them.

## Replacing Icons in a Derived Application

- Treat product artwork as application branding. Work in the cloned application's
  workspace, not the source foundation checkout. Follow the user's supplied artwork
  or design brief; changing the app name alone does not replace any icon.
- The minimal supported customization replaces the contents of
  `pwaf_foundation/static/icons/pwaf.svg` and its generated assets while preserving
  filenames. This is a targeted branding customization in the clone, not permission
  to mix application logic into shared services. Reusable gear/graph glyphs may stay.
- Read `scripts/generate_icons.py` and [the icon guide](docs/icons.md) before editing.
  Its source contract is a 512×512 SVG viewBox with direct child background `rect`
  and foreground `g` elements. Preserve that contract or adapt the generator for
  the supplied artwork; do not claim arbitrary SVG/PNG input is supported.
- Regenerate through `python scripts/generate_icons.py` using the development
  environment and installed Playwright Chromium. Produce the complete set: SVG/
  favicon, desktop PNG/ICO/ICNS/iconset, iOS touch/app-catalog assets, and Android
  standard/maskable assets. Keep opaque mobile backgrounds and inspect the actual
  maskable foreground safe area after replacing the design.
- Update the SVG label, web manifest identity/colors, template theme color, and any
  app-catalog metadata in the generator. Edit sources and regenerate; do not make
  a one-off generated-file edit that the next generation will overwrite.
- If renaming assets, update every reference: generator outputs, base-template
  favicon/touch/sidebar/manifest links, manifest icon URLs, `Contents.json`, desktop
  icon loading, package-data patterns, tests, and docs. Do not mass-replace `PWAF`
  in unrelated package names, installer markers, or configuration contracts.
- Application-owned assets are also possible through `UIConfig.static_dir` and
  `template_dir`. Ensure nested icon files and manifests are included by packaging.
  Set `name`, `icon_dir`, and `icon_stem` in `app/identity.json` for app-owned
  native branding. Load `DesktopIdentity` in the desktop entrypoint, call
  `prepare_desktop_identity` before GUI imports/resource startup, and pass
  `identity` and `title=identity.name` to `launch_desktop`. This is independent of
  `UIConfig`; omitted identity preserves the foundation icon default.
- Verify icon tests, package contents, and changed browser/native surfaces. Inspect
  small-size legibility, transparent desktop corners, opaque mobile variants, and
  masks. Record native/mobile targets not actually tested. ICNS/ICO/catalog assets
  alone do not create a Finder app bundle, Windows shortcut, or native mobile app.
- Include editable artwork, generator changes, generated outputs, and updated docs
  in the derived project's eventual commit. Explain that installed copies need an
  update/restart and cached browser/home-screen icons may need refreshing. Do not
  overwrite other installations or clear unrelated user browser data.

## Target Repository Layout and Commands

Use these names consistently when creating the initial implementation:

```text
pwaf_foundation/              Reusable services and default UI
  __init__.py            Canonical foundation version
  templates/             Base layout and shared components
  static/                Default styles and browser scripts
app/                     Replaceable example / derived application
  __main__.py            Browser server entrypoint
  app.py                 Application factory and composition
  services/              Business logic shared by CLI and web routes
  templates/             Application pages and template overrides
  static/                Application assets
  migrations/            Application-owned schema migrations
tests/                   Automated tests
scripts/                 Verification and development utilities
README.md                Setup, run, and extension entrypoint
requirements.txt         Runtime dependencies
requirements-dev.txt     Runtime dependencies plus test and lint tools
install.sh               macOS / Linux / Raspberry Pi installation
install.ps1              Windows installation
```

The runtime, UI/job extension interfaces, installers, and commands below are
implemented. Do not report an unavailable platform check as successfully verified.

- Create a virtual environment: `python3 -m venv .venv`.
- Install runtime dependencies in that environment:
  `python3 -m pip install -r requirements.txt`.
- Install development dependencies:
  `python3 -m pip install -r requirements-dev.txt`.
- Start the browser server: `python3 -m app`.
- Source desktop: install `requirements-desktop.txt`, then `python3 -m app.desktop`.
- Standalone installs include pywebview and launch its window by default. Keep
  `--browser-only` / `-BrowserOnly` available for headless installs; the desktop
  server also serves browser clients while the window is open.
- Standalone install: `./install.sh` or `install.ps1`; see `docs/installation.md`.
  Open a native folder picker when no destination is supplied; explicit destination
  arguments support headless installs. Cancellation must not start installation.
- Default UI: `http://127.0.0.1:8191`; readiness: `/healthz`.
- Run tests: `python3 -m pytest -q`.
- Check resource and async lifecycles: `python3 -m pytest -q -W error`.
- Lint: `ruff check .`.
- Check syntax: `python3 -m compileall -q pwaf_foundation app tests`.
- On Windows, use the virtual environment's `python` executable where `python3`
  is unavailable. Document exact activation and installation steps in the README.

## Documentation

- Create and maintain a concise README covering installation, startup,
  configuration, architecture, and adding an application feature.
- Add topic documents under `docs/` when needed and link them from the README.
- Document public extension interfaces with a minimal working example when they
  are introduced. Keep examples synchronized with the implementation.
- Distinguish implemented features from planned behavior. If existing code and
  documentation disagree, inspect and test the code before updating either.

## Code and Architecture Conventions

- Keep changes targeted and easy to review; avoid unsolicited broad refactors.
- Use clear names, cohesive modules, type annotations on public interfaces, and
  explicit dependencies. Avoid deep or circular imports.
- Prefer the standard library and existing helpers. Discuss heavy dependencies
  before adding them; keep desktop-only dependencies optional.
- Add a module docstring with a one-line summary followed by a concise description
  of purpose and functionality. Add concise docstrings for public APIs.
- Keep FastAPI handlers thin; put substantial behavior in services.
- Keep blocking I/O off the event loop through synchronous handlers or explicit
  thread offloading. Merely putting work in an async background task does not
  make blocking operations safe.
- Use process execution or a separate worker for CPU-heavy jobs when appropriate.
  Do not introduce an external queue without a demonstrated requirement.

## Configuration and Settings

- Provide a shared settings service with explicit load, validate, and save APIs.
  Runtime code must write through that service rather than editing JSON directly.
- Separate foundation settings from application-specific fields. Do not require
  sensor, gateway, geography, polling, or retention settings in the foundation.
- Missing fields use defaults. Invalid fields fall back individually with an
  operator-visible warning; never silently reset the entire configuration.
- Tolerate unknown fields and preserve them when rewriting settings so another
  version or extension does not lose its data.
- Validate partial updates against a candidate settings value. Persist atomically
  before publishing the update to runtime consumers; failed writes must leave
  active settings unchanged. Serialize concurrent updates to avoid lost writes.
- Define how services receive live updates; do not mix stale snapshots with
  mutable shared settings without an explicit contract.
- Preserve existing user settings during installation and upgrades. Apply factory
  defaults only to absent values.
- Never store secrets in committed settings, examples, logs, or API responses.

## Environment Variable Reference

The following variables are implemented and validated at startup. Runtime
configuration is separate from editable settings; no fields currently overlap.

| Variable | Default | Meaning |
| --- | --- | --- |
| `PWAF_DESKTOP_IDENTITY` | unset | Internal macOS identity re-exec marker; launcher-owned, not user configuration. |
| `PWAF_HTTP_HOST` | `127.0.0.1`; `0.0.0.0` for direct LAN | IP or localhost; local/proxy modes require loopback. |
| `PWAF_HTTP_PORT` | `8191` | Integer from 1 through 65535. |
| `PWAF_DATA_DIR` | `./data` | Relative to startup directory; installed launchers use their absolute data path. |
| `PWAF_LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR, or CRITICAL. |
| `PWAF_MODE` | `local` | local or lan. |
| `PWAF_LAN_AUTH` | `none` | none or optional proxy authentication; proxy requires LAN mode. |
| `PWAF_PUBLIC_ORIGIN` | unset | Required for LAN: HTTP for direct mode, HTTPS for proxy mode; no path or credentials. |
| `PWAF_PROXY_TOKEN_FILE` | unset | Proxy mode only: file with a 64-character lowercase hex token. |
| `PWAF_LAN_USERS` | empty | Proxy mode allowlist, comma-separated usernames. |
| `PWAF_LAN_OPERATORS` | empty | Proxy mode users allowed to mutate state; subset of LAN users. |

The optional Caddyfile also reads `PWAF_PROXY_TOKEN`, `PWAF_OPERATOR_HASH`, and
`PWAF_VIEWER_HASH` with no defaults; these are proxy-only secrets, not app settings.
See `docs/deployment.md` for validation details and exact precedence.

- Keep this table comprehensive: document every added variable, default,
  validation rule, and precedence. Derived apps should document their own variables
  separately using an application-specific prefix.
- Resolve configuration once at startup. Explicit environment overrides take
  precedence over persisted values for overlapping fields, then built-in defaults.
  Do not persist environment overrides back into settings automatically.
- Invalid explicit environment values must fail startup with a clear diagnostic.
- Store settings at `<PWAF_DATA_DIR>/settings.json` and the default database at
  `<PWAF_DATA_DIR>/app.sqlite3`. Resolve the directory to an absolute path and
  report it at startup. Installers must configure a stable, user-owned location.

## Persistence Requirements

- Provide SQLite infrastructure without prescribing domain tables or metrics.
  Applications own their schemas and data-access services.
- Keep SQL out of route handlers. Use parameterized SQL and explicit transactions
  for related writes; document connection ownership and concurrency behavior.
- Close every SQLite connection explicitly. A connection context manager handles
  transactions but does not itself close the connection; use `contextlib.closing`
  or an equivalent explicit lifecycle.
- Track schema versions and provide migrations or a compatibility path when
  changing persisted structures. Prefer additive changes and preserve user data.
- For new timestamp fields, use aware UTC datetimes and fixed-width ISO 8601 text
  with microseconds and a `Z` suffix. Normalize before storage so lexical ordering
  is consistent. Changes to established formats require a compatibility migration.
- When retention or export windows are needed, use elapsed-time cutoffs rather
  than row-count estimates. Keep expensive maintenance out of request hot paths.
- Generate CSV with Python's `csv` module.

## Existing Tools and Background Jobs

- Prefer importing a tool's service functions. Keep its CLI entrypoint as a thin
  adapter and preserve existing CLI behavior when adding web access.
- If a tool cannot be imported, use a subprocess adapter with explicit argument
  lists, validated inputs, timeouts, exit-code handling, and bounded output capture.
  Do not construct shell commands from browser input or use `shell=True` for it.
- Long-running operations must return a job identifier promptly and expose status,
  results, and errors. Define concurrency limits and cancellation behavior.
- Document whether jobs survive restarts; do not imply durability for in-memory
  tasks. Do not let duplicate requests accidentally launch duplicate costly work.
- Track task handles and close resources during shutdown. Log unexpected failures
  and make failed state visible. Recurring tasks must use an explicit recovery
  policy without swallowing cancellation or retrying indefinitely in a tight loop.

## API and Endpoint Documentation

- Serve HTML pages at human-facing paths and JSON endpoints under `/api`.
  Use resource names such as `/api/jobs` and `/api/jobs/{job_id}`.
- GET requests must be read-only. Use POST for creation or execution, PATCH for
  partial updates, and DELETE for removal when those operations are applicable.
- Define request and response models, status codes, validation constraints, and
  concise endpoint descriptions. Keep generated OpenAPI documentation accurate;
  document `/docs` and `/openapi.json` availability in the README.
- Use 201 for created resources and 202 for accepted asynchronous work; include a
  resource or status URL where appropriate. Document pagination for growing lists.
- `/healthz` reports readiness: return 200 when configured required services are
  usable and 503 otherwise. Applications may register additional required checks;
  apps without background jobs must not require a running worker to be healthy.
- Document authentication and authorization for each deployment mode. The initial
  local mode may be unauthenticated but must bind to loopback by default.
  LAN mode defaults to no password as requested by the project owner. Preserve
  host/origin/CSRF checks in that mode. The optional proxy mode requires HTTPS,
  verified proxy credentials, allowed identity, and operator authorization for
  mutations; never silently fall back from proxy mode to unauthenticated access.
- Protect browser mutation routes, including JSON routes using cookie credentials,
  against CSRF. CSRF protection does not replace authentication. Do not enable
  unrestricted CORS by default or place credentials in URLs.
- Document API compatibility changes and update examples and contract tests with
  endpoint changes. Do not expose stack traces or internal filesystem details.

## Error Handling Standards

- Services raise specific domain exceptions without depending on HTTP. Translate
  them at the API boundary through shared exception handlers.
- Use one JSON error envelope for `/api` failures, including request validation,
  HTTP errors, and unexpected errors. Example:

```json
{
  "error": {
    "code": "validation_error",
    "message": "One or more fields are invalid.",
    "details": [{"field": "duration_seconds", "message": "Must be positive."}]
  }
}
```

- `code` is a stable machine-readable identifier; `message` is safe user-facing
  text; `details` is an optional list of safe field-level explanations. Do not
  copy raw exception strings or submitted secret values into responses.
- Map malformed requests to 400, authentication failures to 401, denied access
  to 403, missing resources to 404, state conflicts to 409, and model validation
  failures to 422. Unexpected failures return 500 with a generic message.
- Log unexpected exceptions once at the responsible boundary with traceback and
  useful operation context. Redact secrets and avoid noisy logging in hot paths.
- Never turn failures into successful empty results. HTML forms should show clear
  actionable errors, preserve safe user input, and leave saved state unchanged.
- Failed jobs use the same error fields in their status representation; successful
  retrieval of a failed job's status can still return HTTP 200.

## Web UI and Extension Examples

- Graphum is an optional development component, disabled by default through
  `UIConfig.graph_enabled`. Applications own metric definitions, selection policy,
  and data sources; do not add application-specific metrics to the foundation.

- Provide a default base template with documented blocks such as `title`,
  `content`, and `scripts`, shared component macros, and a navigation extension.
- Load application template overrides before foundation defaults. Namespace static
  assets to avoid collisions and generate their URLs through named routes.
- Preserve responsive layouts, semantic controls, labels, keyboard navigation,
  visible focus, accessible dialogs, and visible save/error status.
- Settings panes validate and save only their owned fields. If theme preview is
  offered, cancel restores the previous theme. Exact modal IDs, scene names, and
  footer placement belong to the default UI's documentation, not the extension
  contract.
- Keep template autoescaping enabled. Do not mark tool output as safe HTML.
- In Jinja, test values explicitly against `none` when rendering missing data;
  expressions such as `value or 'N/A'` incorrectly hide valid zero values.

Illustrative target for a derived page at `app/templates/performance.html`:

```jinja
{% extends "base.html" %}
{% block title %}Performance{% endblock %}
{% block content %}
<section aria-labelledby="performance-title">
  <h1 id="performance-title">Performance</h1>
  <p>Latest result: {{ result if result is not none else 'Not run yet' }}</p>
</section>
{% endblock %}
```

To implement this feature:

1. Put the performance operation in `app/services/` so both CLI and web can use it.
2. Add an application router for the page and any job endpoints; register it in
   `app/app.py` through `create_app`.
3. Render the page with a `result` context value and register its navigation entry
   through the foundation's documented navigation interface.
4. Add application assets only when shared components are insufficient. Protect
   execution actions with the same validation, access, and CSRF rules as other
   browser mutations.
5. Test service behavior, endpoint contracts, and the page's relevant UI behavior.

See `docs/extending.md` for implemented helper signatures and runnable examples.
The default launcher composes the performance example through `create_example_app`;
`create_app` remains usable independently of that example.

## Testing and Verification

- Prefer the smallest relevant verification. Add regression tests for bug fixes.
- Use `tmp_path` for settings and SQLite tests; never write test state into the
  repository's runtime data directory.
- Use fake application services, subprocess adapters, and hardware integrations.
  Route tests should start only the services they need; test real lifecycle wiring
  separately.
- Cover settings validation and atomic saves, migrations, error envelopes, access
  controls, job failures, and resource cleanup as those features are introduced.
- Run tests with `-W error` for resource or async lifecycle changes. Use `curl`
  for endpoint and readiness checks where a running server is relevant.
- For UI changes, use Playwright or headless Chromium to verify affected behavior,
  including mobile layout and keyboard interaction. Keep these checks runnable
  locally and in CI; document the actual command once the harness exists.
- Do not block documentation-only changes on unavailable UI scripts. Report
  missing verification tools and any behavior left unverified.
- CI should run tests and lint, measure coverage, and enforce a documented baseline
  once established. Prioritize meaningful behavior coverage over a percentage alone.
- Report verification performed and relevant assumptions: platform, browser versus
  desktop mode, fake versus real integrations, and exercised settings/UI paths.

## Safety Rules

- Do not run destructive commands without explicit user request.
- Prefer idempotent operations and preserve installed user data.
- Avoid broad search-and-replace unless the task specifically requires it.
- Treat public extension interfaces, settings, persisted schemas, and established
  CLI behavior as compatibility-sensitive.
- Surface major concurrency or storage refactors before implementation.

## Versioning Rule

When making code changes, update the canonical `__version__` in
`pwaf_foundation/__init__.py` once per completed change set, not once per edited file
or verification run. Initialize it when the package is first created.

```text
v0.<year>.<doy>.<x>
```

- `<year>`: two-digit UTC year.
- `<doy>`: three-digit UTC day of year.
- `<x>`: per-day incrementing patch counter, starting at 1.
- If the version date matches today's UTC date, increment `<x>`; otherwise reset
  it to 1 for today's date. Packaging metadata must derive from this same source.
- A derived application may maintain a separate application version; document its
  canonical source without duplicating the foundation version.
- Documentation-only changes, including this file, do not require a version bump.

## Reusable extensions added after downstream application review

- `create_app` exposes job concurrency, queue/history bounds, and snapshot byte limits.
- Use owner-scoped `JobManager.latest`/`list_records`, bounded `JobContext.publish`,
  and optional `JobDefinition.finalize`; see `docs/jobs.md` for cancellation and save rules.
- Use `pwaf_foundation.processes.run_process` for streamed native output; keep command
  construction, parsing, and metric semantics in the application.
- `UIConfig` supports General-field ownership and configurable Graphum ranges;
  shared browser code emits `settings-loaded` and tolerates omitted navigation/settings.
- `launch_desktop` accepts app-owned title and confirmation policy. Native icon
  selection remains the existing fixed-path contract.
- The repository remains private. Preserve notices and distinguish local verification
  from remote CI/native targets. Do not change visibility or publish without authorization.
