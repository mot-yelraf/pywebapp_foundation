# Contributing to pywebapp_foundation

pywebapp_foundation is a reusable Python foundation for adding desktop and browser
interfaces to existing tools. It provides FastAPI routes, shared UI components,
settings, SQLite infrastructure, cancellable jobs, optional Graphum graphs, and
pywebview desktop operation. Target platforms are Raspberry Pi, macOS, Windows,
and Linux. Stability and compatibility with installed user data are primary goals.

Read [AGENTS.md](AGENTS.md) for repository conventions and [README.md](README.md)
for setup. To build your own application rather than change the foundation, use
[APP_BRIEF.md](APP_BRIEF.md) and the [personalization guide](docs/personalizing.md).
All participants are expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Workflow

1. Fork or clone the repository and create a feature branch from `trunk`.
2. Make a focused change with appropriate tests and documentation.
3. Run the relevant verification below.
4. Submit a pull request against `trunk`, describing the problem, solution, and
   actual verification results.

Direct pushes to `trunk` are not accepted. Keep pull requests focused on one logical
change. Discuss major architectural changes or new heavy dependencies before
implementation. Maintainers of derived projects should update these branch and
review conventions for their own repository.

## Useful contributions

- Documentation, clone/personalization guides, and application extension examples
- Accessible, responsive UI components and optional graph capabilities
- Settings validation, atomic persistence, migrations, and resource lifecycle fixes
- Job adapters, bounded execution, cancellation, and error handling
- Desktop/browser startup and cross-platform installation improvements
- Regression tests and verification on supported platforms

Domain-specific tools, metrics, data schemas, and integrations belong in the
replaceable `app/` layer or a derived project. Keep `pwaf_foundation/` reusable;
it must not import `app/`.

## Dependencies and architecture

Prefer the standard library and existing helpers. Explain new dependencies and
consider their size and platform support. Discuss major upgrades to FastAPI,
Pydantic, Uvicorn, pywebview, or other core dependencies before changing them.
Desktop dependencies must remain optional for browser-only/headless installations.

Keep routes thin and business logic independent of HTTP and desktop libraries.
Run blocking I/O outside the event loop. Own background work and child processes
explicitly, bound workloads/output, and clean up on cancellation and shutdown.
Do not silently weaken host/origin/CSRF checks or optional authentication behavior.
See [architecture](docs/architecture.md) and [job contracts](docs/jobs.md).

## Data and configuration

Runtime state uses `<PWAF_DATA_DIR>/settings.json` and `app.sqlite3`. Source runs
default to `./data`; installed launchers use their installation's `data/` directory.
Runtime environment configuration and editable saved settings have distinct roles.

- Preserve saved preferences, unknown settings fields, and installed application data.
- Use application-owned migration namespaces and additive migrations or explicit
  compatibility paths; do not assume any particular domain schema.
- Close SQLite connections explicitly and use temporary directories for tests.
- Do not commit runtime databases, settings copies, credentials, or private network
  information. Use placeholders and deterministic fixtures.
- Keep installation/reinstallation idempotent and preserve existing data.

## Code style

Use clear names, cohesive modules, concise public API docstrings, and useful,
non-noisy logging. Reuse helpers and avoid unrelated refactors. Preserve documented
interfaces and update callers, tests, and documentation when a contract changes.
The full conventions and versioning rule are in [AGENTS.md](AGENTS.md).

## Verification

Create a local virtual environment using the README, then run these commands with
that environment active (`python` also works in an activated Windows environment):

```sh
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python -m pytest -q tests/test_web.py
python -m pytest -q -W error --cov --cov-report=term-missing
python -m ruff check .
python -m compileall -q pwaf_foundation app tests scripts
```

Start with tests relevant to the change; run the full suite for shared behavior.
The current combined statement/branch coverage gate is 95%. Add regression coverage
for bug fixes. Use fakes/fixtures for external tools, hardware, and failure cases.

For affected browser, runtime, or packaging behavior, use the applicable checks:

```sh
python scripts/playwright_verify.py
python scripts/smoke_verify.py
python scripts/verify_clone.py
python scripts/verify_lan.py
python scripts/verify_install.py
python -m build
```

The browser check uses bundled headless Chromium and covers desktop/mobile layouts.
The configured [CI workflow](.github/workflows/tests.yml) runs Playwright as well as
unit tests and other checks. This repository does not currently ship a `.githooks`
pre-commit gate; do not configure a nonexistent hook directory.

Native desktop verification additionally needs desktop dependencies and a graphical
session; see [installation](docs/installation.md) and [verification](docs/verification.md).
Real installation checks download dependencies and use disposable installations.
Report platform/Python version, commands run, exercised UI and persistence paths,
real versus simulated integrations, and any unverified platforms. A configured CI
matrix is not evidence of a successful native run on every target.

## Pull request and release notes

Explain what changed, why it helps, and how it was verified. Update documentation
for behavior changes and identify compatibility or migration implications. For code
changes, update `pwaf_foundation/__init__.py` using the repository version rule;
documentation-only edits do not require a bump.

Preserve [license](LICENSE), attribution, and [third-party notices](THIRD_PARTY_NOTICES.md).
When adding dependencies or assets, document their source and applicable notices.
Do not claim planned features or untested platforms are verified. The project is
pre-1.0; shared interfaces can evolve, but installed settings/data and documented
extension contracts require deliberate compatibility handling.
